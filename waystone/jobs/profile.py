"""Canonical four-role profile and production run-kernel assembly."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml

from waystone.core import WorkflowError
from waystone.jobs.domain import ExecutionCategory, Role, RoleBinding
from waystone.project.context import ProjectContext, resolve_project_context
from waystone.runs.artifacts import ArtifactStore
from waystone.runs.effects import EffectEngine
from waystone.runs.lease import LeaseManager
from waystone.runs.store import RunStore
from waystone.runs.supervisor import RunnerInvocation, Supervisor
from waystone.runs.transport import ActionTransport


PROFILE_SCHEMA = "waystone-profile-2"
_BACKEND_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*:[^\s:]+$")


class ProfileError(WorkflowError):
    code = "profile_error"

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(f"{self.code}: {detail}")


class ProfileUnreadable(ProfileError):
    code = "profile_unreadable"


class ProfileSchemaRefusal(ProfileError):
    code = "profile_schema_refusal"


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False,
) -> dict:
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as error:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                "found an unhashable key", key_node.start_mark,
            ) from error
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                f"found duplicate key {key!r}", key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class CanonicalRoleBinding:
    binding: RoleBinding
    binding_digest: str


@dataclass(frozen=True)
class CanonicalProfile:
    bindings: tuple[CanonicalRoleBinding, ...]
    content_digest: str

    def binding_for(self, role: Role) -> CanonicalRoleBinding:
        typed_role = Role(role)
        matches = tuple(item for item in self.bindings if item.binding.role is typed_role)
        if len(matches) != 1:
            raise ProfileSchemaRefusal(
                f"profile does not contain exactly one {typed_role.value} binding")
        return matches[0]


@dataclass(frozen=True)
class RoleAdapter:
    """A profile-selected adapter identity; invocation materialization is stage-owned."""

    role: Role
    execution_category: ExecutionCategory
    backend: str
    binding_digest: str


@dataclass
class RunAssembly:
    """The complete production kernel graph bound to one canonical project context."""

    context: ProjectContext
    profile: CanonicalProfile
    role_adapters: Mapping[Role, RoleAdapter]
    store: RunStore
    artifact_store: ArtifactStore
    lease_manager: LeaseManager
    supervisor: Supervisor
    effect_executor: EffectEngine
    transport: ActionTransport

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "RunAssembly":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback
        self.close()


def read_profile_bytes(content: bytes) -> CanonicalProfile:
    if not isinstance(content, bytes):
        raise TypeError("profile content must be bytes")
    try:
        document = yaml.load(content.decode("utf-8"), Loader=_UniqueKeyLoader)
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise ProfileSchemaRefusal(f"profile must be valid UTF-8 YAML: {error}") from error
    if not isinstance(document, dict) or set(document) != {"schema", "bindings"}:
        raise ProfileSchemaRefusal("profile fields must be exactly schema and bindings")
    if document["schema"] != PROFILE_SCHEMA:
        raise ProfileSchemaRefusal(f"schema must be {PROFILE_SCHEMA}")
    raw_bindings = document["bindings"]
    expected_roles = {role.value for role in Role}
    if not isinstance(raw_bindings, dict) or set(raw_bindings) != expected_roles:
        raise ProfileSchemaRefusal(
            "bindings must contain exactly coordinator, worker, verifier, and reviewer")

    bindings = []
    for role in Role:
        raw = raw_bindings[role.value]
        if not isinstance(raw, dict) or set(raw) != {"execution", "backend"}:
            raise ProfileSchemaRefusal(
                f"bindings.{role.value} fields must be exactly execution and backend")
        try:
            execution = ExecutionCategory(raw["execution"])
        except (TypeError, ValueError) as error:
            raise ProfileSchemaRefusal(
                f"bindings.{role.value}.execution must be in-session, subagent, or external") from error
        backend = raw["backend"]
        if not isinstance(backend, str) or _BACKEND_RE.fullmatch(backend) is None:
            raise ProfileSchemaRefusal(
                f"bindings.{role.value}.backend must be '<adapter>:<backend>'")
        if role is Role.COORDINATOR and execution is not ExecutionCategory.IN_SESSION:
            raise ProfileSchemaRefusal("coordinator must use the in-session host actor")
        payload = {
            "role": role.value,
            "execution_category": execution.value,
            "backend": backend,
        }
        bindings.append(CanonicalRoleBinding(
            RoleBinding(role, execution, backend),
            _digest(_canonical_json(payload)),
        ))
    return CanonicalProfile(tuple(bindings), _digest(content))


def read_profile(path: str | Path) -> CanonicalProfile:
    try:
        content = Path(path).read_bytes()
    except (OSError, TypeError, ValueError) as error:
        raise ProfileUnreadable(f"cannot read canonical profile from {path!r}: {error}") from error
    return read_profile_bytes(content)


def assemble_run(
    start: ProjectContext | Path,
    *,
    from_worktree: Path | None = None,
    require_run_input: bool = False,
    registry: Path | None = None,
    invocations: Mapping[str, RunnerInvocation] | None = None,
) -> RunAssembly:
    """Resolve context before DB open, then construct one production kernel graph."""
    context = (
        start
        if isinstance(start, ProjectContext)
        else resolve_project_context(
            Path(start),
            from_worktree=from_worktree,
            require_run_input=require_run_input,
            registry=registry,
        )
    )
    profile = read_profile(context.canonical_root / ".waystone" / "profile.yml")
    store = RunStore.open(context.canonical_root)
    try:
        artifact_store = ArtifactStore(context.canonical_root)
        leases = LeaseManager(store)
        supervisor = Supervisor(store, leases, invocations=dict(invocations or {}))
        effects = EffectEngine(
            store,
            leases,
            runner_executor=supervisor.runner_executor,
            runner_identity_verifier=supervisor.runner_identity_verifier,
        )
        adapters = {
            item.binding.role: RoleAdapter(
                item.binding.role,
                item.binding.execution_category,
                item.binding.backend,
                item.binding_digest,
            )
            for item in profile.bindings
        }
        return RunAssembly(
            context=context,
            profile=profile,
            role_adapters=adapters,
            store=store,
            artifact_store=artifact_store,
            lease_manager=leases,
            supervisor=supervisor,
            effect_executor=effects,
            transport=ActionTransport(store, effects),
        )
    except BaseException:
        store.close()
        raise


__all__ = [
    "CanonicalProfile",
    "CanonicalRoleBinding",
    "PROFILE_SCHEMA",
    "ProfileError",
    "ProfileSchemaRefusal",
    "ProfileUnreadable",
    "RoleAdapter",
    "RunAssembly",
    "assemble_run",
    "read_profile",
    "read_profile_bytes",
]
