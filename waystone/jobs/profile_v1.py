"""Read-only adapter from legacy profile v1 bindings to the canonical job domain."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml

from .domain import ExecutionCategory, Role, RoleBinding


class ProfileV1RefusalCode(str, Enum):
    UNREADABLE = "profile_v1_unreadable"
    INVALID_PROFILE = "invalid_profile_v1"
    UNSUPPORTED_BINDING = "unsupported_profile_binding"


class LegacySurfaceKind(str, Enum):
    EXECUTION_LOCATION = "execution-location"
    ENGINE_ORCHESTRATION = "engine-orchestration"


@dataclass(frozen=True)
class BindingProvenance:
    source_schema: str | None
    legacy_role: str
    legacy_execution: str | None


@dataclass(frozen=True)
class AdaptedRoleBinding:
    binding: RoleBinding
    provenance: BindingProvenance


@dataclass(frozen=True)
class DeterministicStepBinding:
    """A legacy clerk binding classified as a step, not as a model role."""

    backend: str
    provenance: BindingProvenance


@dataclass(frozen=True)
class LegacyNonRoleBinding:
    """A legacy main/orchestrator surface retained without creating a Role."""

    kind: LegacySurfaceKind
    backend: str
    provenance: BindingProvenance


@dataclass(frozen=True)
class ProfileV1:
    source_schema: str | None
    role_bindings: tuple[AdaptedRoleBinding, ...]
    deterministic_steps: tuple[DeterministicStepBinding, ...]
    non_role_bindings: tuple[LegacyNonRoleBinding, ...]


@dataclass(frozen=True)
class ProfileV1Refusal:
    code: ProfileV1RefusalCode
    reason: str
    legacy_role: str | None = None
    legacy_execution: str | None = None

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("refusal reason must be non-empty")


ProfileV1ReadResult = ProfileV1 | ProfileV1Refusal


_SCHEMAS = ("waystone-profile-1", "jw-profile-1")
_ROLES = ("main", "orchestrator", "implementer", "clerk", "verifier", "reviewer")
_EXECUTIONS = (
    "main-session",
    "clean-subagent",
    "forked-subagent",
    "deterministic-workflow",
    "external-runner",
)
_LEGACY_VERIFIER_EXECUTIONS = ("codex-cli", "codex-companion")
_ROLE_EXECUTIONS = {
    "main": ("main-session",),
    "orchestrator": (
        "main-session", "clean-subagent", "forked-subagent", "deterministic-workflow"),
    "implementer": (
        "clean-subagent", "forked-subagent", "deterministic-workflow", "external-runner"),
    "clerk": (
        "clean-subagent", "forked-subagent", "deterministic-workflow", "external-runner"),
    "verifier": (
        "clean-subagent", "forked-subagent", "deterministic-workflow", "external-runner"),
    "reviewer": (
        "clean-subagent", "forked-subagent", "deterministic-workflow", "external-runner"),
}
_BINDING_FIELDS = {"execution", "backend", "use_for", "effort", "entry"}
_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "ultra")
_BACKEND_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*:[^\s:]+$")


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
        loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False,
) -> dict:
    loader.flatten_mapping(node)
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _invalid(reason: str) -> ProfileV1Refusal:
    return ProfileV1Refusal(ProfileV1RefusalCode.INVALID_PROFILE, reason)


def _unsupported(role: object, execution: object, reason: str) -> ProfileV1Refusal:
    role_name = role if isinstance(role, str) else None
    execution_name = execution if isinstance(execution, str) else None
    return ProfileV1Refusal(
        ProfileV1RefusalCode.UNSUPPORTED_BINDING,
        f"profile binding {role!r}/{execution!r} is unsupported: {reason}",
        legacy_role=role_name,
        legacy_execution=execution_name,
    )


def _validate_binding(role: str, binding: object) -> ProfileV1Refusal | None:
    if not isinstance(binding, dict):
        return _unsupported(role, None, "binding must be a mapping")
    unknown = set(binding) - _BINDING_FIELDS
    if unknown:
        names = ", ".join(sorted(map(str, unknown)))
        return _unsupported(role, binding.get("execution"), f"unknown field(s): {names}")

    execution = binding.get("execution")
    if role == "verifier" and (
            execution is None or execution in _LEGACY_VERIFIER_EXECUTIONS):
        pass
    elif execution not in _EXECUTIONS:
        return _unsupported(role, execution, "execution is not a profile v1 value")
    elif execution not in _ROLE_EXECUTIONS[role]:
        return _unsupported(role, execution, "execution is not valid for this legacy role")

    backend = binding.get("backend")
    if not isinstance(backend, str) or _BACKEND_RE.fullmatch(backend) is None:
        return _unsupported(role, execution, "backend must be '<runner>:<model>'")
    if (role == "verifier" and execution in _LEGACY_VERIFIER_EXECUTIONS
            and backend.partition(":")[0] != "codex"):
        return _unsupported(
            role, execution, "legacy Codex execution conflicts with a non-Codex backend")

    use_for = binding.get("use_for")
    if use_for is not None and (
            not isinstance(use_for, str) or not use_for.strip()
            or "\n" in use_for or "\r" in use_for):
        return _unsupported(role, execution, "use_for must be one non-empty line")

    effort = binding.get("effort")
    if effort is not None and effort not in _EFFORTS:
        return _unsupported(role, execution, "effort is not a profile v1 value")

    entry = binding.get("entry")
    if entry is not None and (role != "verifier" or entry != "adversarial-review"):
        return _unsupported(role, execution, "entry is not a supported verifier entry")
    return None


def _provenance(schema: str | None, role: str, execution: object) -> BindingProvenance:
    return BindingProvenance(
        source_schema=schema,
        legacy_role=role,
        legacy_execution=execution if isinstance(execution, str) else None,
    )


def _adapt_binding(
        schema: str | None, role: str, binding: dict,
) -> AdaptedRoleBinding | DeterministicStepBinding | LegacyNonRoleBinding | ProfileV1Refusal:
    execution = binding.get("execution")
    provenance = _provenance(schema, role, execution)
    backend = binding["backend"]

    if role == "main":
        return LegacyNonRoleBinding(
            LegacySurfaceKind.EXECUTION_LOCATION, backend, provenance)
    if role == "orchestrator":
        return LegacyNonRoleBinding(
            LegacySurfaceKind.ENGINE_ORCHESTRATION, backend, provenance)
    if role == "clerk":
        return DeterministicStepBinding(backend, provenance)

    canonical_role = {
        "implementer": Role.WORKER,
        "verifier": Role.VERIFIER,
        "reviewer": Role.REVIEWER,
    }[role]
    if execution in (None, *_LEGACY_VERIFIER_EXECUTIONS, "external-runner"):
        category = ExecutionCategory.EXTERNAL
    elif execution in ("clean-subagent", "forked-subagent"):
        category = ExecutionCategory.SUBAGENT
    else:
        return _unsupported(
            role,
            execution,
            "deterministic-workflow is an orchestration procedure, not an execution category",
        )
    return AdaptedRoleBinding(
        RoleBinding(canonical_role, category, backend),
        provenance,
    )


def _adapt_profile(document: object) -> ProfileV1ReadResult:
    if not isinstance(document, dict):
        return _invalid("profile document must be a mapping")
    unknown = set(document) - {"schema", "bindings"}
    if unknown:
        names = ", ".join(sorted(map(str, unknown)))
        return _invalid(f"profile has unknown top-level field(s): {names}")

    schema = document.get("schema")
    if schema is not None and schema not in _SCHEMAS:
        return _invalid("schema must be 'waystone-profile-1', legacy 'jw-profile-1', or null")
    bindings = document.get("bindings")
    if not isinstance(bindings, dict) or not bindings:
        return _invalid("bindings must be a non-empty mapping")

    role_bindings: list[AdaptedRoleBinding] = []
    deterministic_steps: list[DeterministicStepBinding] = []
    non_role_bindings: list[LegacyNonRoleBinding] = []
    for role, binding in bindings.items():
        if role not in _ROLES:
            execution = binding.get("execution") if isinstance(binding, dict) else None
            return _unsupported(role, execution, "role is not a profile v1 binding name")
        refusal = _validate_binding(role, binding)
        if refusal is not None:
            return refusal
        adapted = _adapt_binding(schema, role, binding)
        if isinstance(adapted, ProfileV1Refusal):
            return adapted
        if isinstance(adapted, AdaptedRoleBinding):
            role_bindings.append(adapted)
        elif isinstance(adapted, DeterministicStepBinding):
            deterministic_steps.append(adapted)
        else:
            non_role_bindings.append(adapted)

    return ProfileV1(
        source_schema=schema,
        role_bindings=tuple(role_bindings),
        deterministic_steps=tuple(deterministic_steps),
        non_role_bindings=tuple(non_role_bindings),
    )


def read_profile_v1(path: str | Path) -> ProfileV1ReadResult:
    """Read and adapt a profile without modifying or re-emitting its source file."""
    try:
        profile_path = Path(path)
        raw = profile_path.read_bytes()
    except (OSError, TypeError, ValueError) as error:
        return ProfileV1Refusal(
            ProfileV1RefusalCode.UNREADABLE,
            f"profile v1 cannot be read from {path!r}: {error}",
        )
    try:
        document = yaml.load(raw.decode("utf-8"), Loader=_UniqueKeyLoader)
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        return ProfileV1Refusal(
            ProfileV1RefusalCode.INVALID_PROFILE,
            f"profile v1 is not valid UTF-8 YAML: {error}",
        )
    return _adapt_profile(document)


__all__ = [
    "AdaptedRoleBinding",
    "BindingProvenance",
    "DeterministicStepBinding",
    "LegacyNonRoleBinding",
    "LegacySurfaceKind",
    "ProfileV1",
    "ProfileV1ReadResult",
    "ProfileV1Refusal",
    "ProfileV1RefusalCode",
    "read_profile_v1",
]
