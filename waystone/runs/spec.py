"""Stage-aware RunSpec v2 planning and read-only base snapshot capture."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from contextlib import nullcontext
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from waystone.adapters.git import GitReadError, git_full_sha, git_read_bytes
from waystone.core import WorkflowError
from waystone.jobs.completion import (
    CompletionContract,
    LifecycleStage,
    ObjectiveRef,
    parse_completion_contract_bytes,
    parse_objective_ref,
)
from waystone.jobs.work_brief import parse_work_brief_bytes
from waystone.project import find_project_root, load_tasks
from waystone.project.brief import FrameStatusRef, ProjectFactRef, SourceSpan
from waystone.runs.artifacts import (
    ArtifactReference,
    ArtifactReferenceKind,
    ArtifactStore,
    StoredArtifact,
    validate_sha256_digest,
)
from waystone.runs.assurance import (
    AssurancePlan,
    digest_bytes,
    parse_assurance_plan_bytes,
    parse_candidate_bytes,
    parse_evaluation_evidence_bytes,
    parse_evaluation_spec_bytes,
)
from waystone.runs.store import EntityKind, RecordNotFoundError, RunStore, TransitionReason


_RUN_SPEC_SCHEMA = "waystone-run-spec-2"
_SNAPSHOT_SCHEMA = "waystone-run-base-snapshot-1"
_RUN_SPEC_REFERENCE_PREFIX = "run-spec:"
_SNAPSHOT_REFERENCE_PREFIX = "base-snapshot:"
_TIME_UNITS = frozenset({"day"})
_COST_UNITS = frozenset({"attempt"})
_COST_METERS = frozenset({"attempt-start"})
_RESULT_POLICY_MODES = frozenset({"candidate-ref", "evidence-only", "integration-ref"})


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


class RunSpecError(WorkflowError):
    """Base class for typed RunSpec planning and integrity failures."""

    code = "run_spec_error"

    def __init__(self, message: str):
        super().__init__(f"{self.code}: {message}")


class UninitializedRunSpecError(RunSpecError):
    code = "uninitialized_project"

    def __init__(self, start: Path):
        self.start = Path(start)
        super().__init__(
            f"no regular .waystone.yml identifies an initialized project from {start}")


class TaskNotFoundError(RunSpecError):
    code = "task_not_found"

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"task {task_id!r} does not exist in the project registry")


class InvalidTaskInputError(RunSpecError):
    code = "invalid_task_input"

    def __init__(self, task_id: str, detail: str):
        self.task_id = task_id
        self.detail = detail
        super().__init__(f"task {task_id!r}: {detail}")


class AcceptanceReadinessError(RunSpecError):
    code = "criterion-empty"

    def __init__(self, task_id: str, detail: str = "acceptance criteria are absent or empty"):
        self.task_id = task_id
        self.detail = detail
        super().__init__(f"task {task_id!r}: {detail}; refusing run creation")


class DuplicateCriterionError(RunSpecError):
    code = "criterion-duplicate"

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"task {task_id!r} contains duplicate acceptance criteria")


class SnapshotError(RunSpecError):
    code = "snapshot_unavailable"

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class RunSpecArtifactError(RunSpecError):
    code = "run_spec_artifact_invalid"

    def __init__(self, run_id: str, detail: str):
        self.run_id = run_id
        self.detail = detail
        super().__init__(f"run {run_id!r}: {detail}")


class RunInputDriftError(RunSpecError):
    code = "run_input_drift"

    def __init__(self, drift: "RunInputDrift"):
        self.drift = drift
        self.run_id = drift.run_id
        self.task_id = drift.task_id
        changed = ", ".join(drift.changed_fields) or "task availability"
        super().__init__(
            f"run {drift.run_id!r} frozen task {drift.task_id!r} drifted in {changed}; "
            "the frozen job input remains authoritative")


class RunInputChangedDuringPlanningError(RunSpecError):
    code = "run_input_changed_during_planning"

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(
            f"task {task_id!r} changed while its RunSpec was being planned; refusing run creation")


@dataclass(frozen=True)
class BudgetLimit:
    limit: int
    unit: str

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit <= 0:
            raise ValueError("budget limit must be a positive integer")
        if self.unit not in _TIME_UNITS:
            raise ValueError(f"time budget unit must be one of {sorted(_TIME_UNITS)}")


@dataclass(frozen=True)
class CostBudget:
    limit: int
    unit: str
    meter: str

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit <= 0:
            raise ValueError("cost budget limit must be a positive integer")
        if self.unit not in _COST_UNITS:
            raise ValueError(f"cost budget unit must be one of {sorted(_COST_UNITS)}")
        if self.meter not in _COST_METERS:
            raise ValueError(f"cost budget meter must be one of {sorted(_COST_METERS)}")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts_per_job: int
    max_total_attempts: int
    time_budget: BudgetLimit
    cost_budget: CostBudget
    retryable_failure_classes: tuple[str, ...]
    budget_exhaustion_policy: str

    def __post_init__(self) -> None:
        for label, value in (
                ("max_attempts_per_job", self.max_attempts_per_job),
                ("max_total_attempts", self.max_total_attempts)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{label} must be a positive integer")
        if self.max_total_attempts < self.max_attempts_per_job:
            raise ValueError("max_total_attempts cannot be below max_attempts_per_job")
        if self.retryable_failure_classes:
            raise ValueError("M1-B has no registered retryable failure class")
        if self.budget_exhaustion_policy != "stop":
            raise ValueError("budget_exhaustion_policy must be 'stop'")


DEFAULT_RETRY_POLICY = RetryPolicy(
    max_attempts_per_job=2,
    max_total_attempts=2,
    time_budget=BudgetLimit(limit=1, unit="day"),
    cost_budget=CostBudget(limit=2, unit="attempt", meter="attempt-start"),
    retryable_failure_classes=(),
    budget_exhaustion_policy="stop",
)


@dataclass(frozen=True)
class ArtifactDescriptor:
    reference_id: str
    digest: str
    size: int

    def __post_init__(self) -> None:
        if not isinstance(self.reference_id, str) or not self.reference_id.strip():
            raise ValueError("artifact descriptor reference_id must be non-empty")
        object.__setattr__(self, "digest", validate_sha256_digest(self.digest))
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0:
            raise ValueError("artifact descriptor size must be a non-negative integer")

    def to_dict(self, *, include_size: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "reference_id": self.reference_id,
            "digest": self.digest,
        }
        if include_size:
            result["size"] = self.size
        return result


@dataclass(frozen=True)
class PromotionLineage:
    id: str
    root_objective_ref_digest: str
    integration_target_ref: str
    parent_run_spec_digest: str | None
    candidate_chain_head_digest: str | None
    review_cycle_head_digest: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("promotion lineage id must be non-empty")
        object.__setattr__(
            self, "root_objective_ref_digest",
            validate_sha256_digest(self.root_objective_ref_digest))
        if (not isinstance(self.integration_target_ref, str)
                or not self.integration_target_ref.startswith("refs/")):
            raise ValueError("promotion lineage integration target must be a full refs/* name")
        for field in (
                "parent_run_spec_digest", "candidate_chain_head_digest",
                "review_cycle_head_digest"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, validate_sha256_digest(value))

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "root_objective_ref_digest": self.root_objective_ref_digest,
            "integration_target_ref": self.integration_target_ref,
            "parent_run_spec_digest": self.parent_run_spec_digest,
            "candidate_chain_head_digest": self.candidate_chain_head_digest,
            "review_cycle_head_digest": self.review_cycle_head_digest,
        }


@dataclass(frozen=True)
class ResultPolicy:
    mode: str
    target_ref: str | None
    expected_oid: str | None

    def __post_init__(self) -> None:
        if self.mode not in _RESULT_POLICY_MODES:
            raise ValueError("result policy mode is invalid")
        if self.mode == "integration-ref":
            if (not isinstance(self.target_ref, str) or not self.target_ref.startswith("refs/")
                    or not isinstance(self.expected_oid, str)
                    or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", self.expected_oid) is None):
                raise ValueError("integration-ref requires target_ref and expected_oid")
        elif self.expected_oid is not None:
            raise ValueError("expected_oid is valid only for integration-ref")
        elif self.target_ref is not None and (
                not isinstance(self.target_ref, str) or not self.target_ref.startswith("refs/")):
            raise ValueError("result policy target_ref must be a full refs/* name")

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "target_ref": self.target_ref,
            "expected_oid": self.expected_oid,
        }


@dataclass(frozen=True)
class FrozenJobInput:
    task_id: str
    title: str
    completion_contract: ArtifactDescriptor
    scope: tuple[str, ...]
    dependencies: tuple[str, ...]
    input_digest: str
    acceptance_criteria: tuple[str, ...] = ()

    def canonical_bytes(self) -> bytes:
        return _canonical_json(_job_input_payload(self, include_digest=False))


@dataclass(frozen=True)
class BaseSnapshotReference:
    head: str
    reference_id: str
    digest: str
    size: int


@dataclass(frozen=True)
class SnapshotEntry:
    path: bytes
    state: str
    mode: str | None
    content: bytes | None

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("snapshot path must be non-empty")
        if self.state not in ("present", "deleted"):
            raise ValueError("snapshot entry state must be present or deleted")
        if self.state == "deleted":
            if self.mode is not None or self.content is not None:
                raise ValueError("deleted snapshot entries cannot have mode or content")
        elif self.mode not in ("100644", "100755", "120000") or self.content is None:
            raise ValueError("present snapshot entries require Git mode and content")


@dataclass(frozen=True)
class BaseSnapshot:
    head: str
    entries: tuple[SnapshotEntry, ...]

    def canonical_bytes(self) -> bytes:
        return _snapshot_bytes(self.head, self.entries)


@dataclass(frozen=True)
class RunSpec:
    run_id: str
    job_id: str
    promotion_lineage: PromotionLineage | None
    revision: int
    supersedes_spec_digest: str | None
    lifecycle_stage: LifecycleStage
    frame_status_ref: FrameStatusRef
    objective_ref: ObjectiveRef
    project_fact_refs: tuple[ProjectFactRef, ...]
    work_brief: ArtifactDescriptor
    assurance_plan: ArtifactDescriptor
    job_input: FrozenJobInput
    candidate: Mapping[str, object] | None
    evaluation: Mapping[str, object]
    result_policy: ResultPolicy
    base_snapshot: BaseSnapshotReference
    retry: RetryPolicy
    run_spec_digest: str

    def canonical_bytes(self) -> bytes:
        return _canonical_json(_run_spec_payload(self))

    @property
    def readiness(self) -> str:
        return "frozen-ready"

    @property
    def critic_disposition(self) -> str:
        return "critic-not-applicable"

    @property
    def review_decision(self) -> None:
        return None


@dataclass(frozen=True)
class RunInputDrift:
    run_id: str
    task_id: str
    frozen_digest: str
    current_digest: str | None
    changed_fields: tuple[str, ...]


@dataclass(frozen=True)
class PreparedRunSpecRevision:
    spec: RunSpec
    work_brief_artifact: StoredArtifact
    assurance_plan_artifact: StoredArtifact
    completion_contract_artifact: StoredArtifact
    run_spec_artifact: StoredArtifact


def _find_root(start: Path | None) -> Path:
    requested = Path.cwd() if start is None else Path(start)
    root = find_project_root(requested)
    if root is None:
        raise UninitializedRunSpecError(requested)
    marker = root / ".waystone.yml"
    try:
        marker_mode = marker.lstat().st_mode
    except OSError as error:
        raise UninitializedRunSpecError(requested) from error
    if stat.S_ISLNK(marker_mode) or not stat.S_ISREG(marker_mode):
        raise UninitializedRunSpecError(requested)
    return root


def _task_rows(root: Path) -> list[dict]:
    try:
        data = load_tasks(root)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as error:
        raise InvalidTaskInputError("<registry>", f"cannot read tasks.yaml: {error}") from error
    rows = data.get("tasks", [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise InvalidTaskInputError("<registry>", "tasks must be a list of mappings")
    return rows


def _selected_task(root: Path, task_id: str) -> dict:
    if not isinstance(task_id, str) or not task_id.strip():
        raise InvalidTaskInputError(str(task_id), "task_id must be non-empty")
    matches = [row for row in _task_rows(root) if row.get("id") == task_id]
    if not matches:
        raise TaskNotFoundError(task_id)
    if len(matches) != 1:
        raise InvalidTaskInputError(task_id, "task id is duplicated")
    return matches[0]


def _string_tuple(task_id: str, value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value):
        raise InvalidTaskInputError(task_id, f"{field} must be a list of non-empty strings")
    return tuple(value)


def _freeze_task(
    task_id: str,
    task: dict,
    completion_contract: ArtifactDescriptor,
    acceptance_criteria: tuple[str, ...] = (),
) -> FrozenJobInput:
    title = task.get("title")
    if not isinstance(title, str) or not title.strip():
        raise InvalidTaskInputError(task_id, "title must be a non-empty string")
    scope = _string_tuple(task_id, task.get("scope"), "scope")
    dependencies = _string_tuple(task_id, task.get("deps"), "deps")
    candidate = FrozenJobInput(
        task_id=task_id,
        title=title,
        completion_contract=completion_contract,
        scope=scope,
        dependencies=dependencies,
        input_digest="sha256:" + "0" * 64,
        acceptance_criteria=acceptance_criteria,
    )
    return replace(candidate, input_digest=_digest(candidate.canonical_bytes()))


def _job_input_payload(job_input: FrozenJobInput, *, include_digest: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "completion_contract": job_input.completion_contract.to_dict(),
        "dependencies": list(job_input.dependencies),
        "scope": list(job_input.scope),
        "task_id": job_input.task_id,
        "title": job_input.title,
    }
    if include_digest:
        payload["input_digest"] = job_input.input_digest
    return payload


def _parse_nul_paths(payload: bytes, command: str) -> set[bytes]:
    if not payload:
        return set()
    if not payload.endswith(b"\0"):
        raise SnapshotError(f"git {command} returned a non-NUL-terminated path list")
    paths = payload[:-1].split(b"\0")
    for path in paths:
        parts = path.split(b"/")
        if (not path or path.startswith(b"/") or any(
                part in (b"", b".", b"..") for part in parts)):
            raise SnapshotError(f"git {command} returned an unsafe repository path")
    return set(paths)


def _parse_index_flags(payload: bytes) -> dict[bytes, bytes]:
    if not payload:
        return {}
    if not payload.endswith(b"\0"):
        raise SnapshotError("git ls-files -v returned a non-NUL-terminated path list")
    flags: dict[bytes, bytes] = {}
    for entry in payload[:-1].split(b"\0"):
        if len(entry) < 3 or entry[1:2] != b" ":
            raise SnapshotError("git ls-files -v returned a malformed entry")
        path = entry[2:]
        _parse_nul_paths(path + b"\0", "ls-files -v")
        flags[path] = entry[:1]
    return flags


def _read_regular_file(path: Path, initial: os.stat_result) -> bytes:
    try:
        payload = path.read_bytes()
        final = path.lstat()
    except OSError as error:
        raise SnapshotError(f"snapshot path {path} changed or became unreadable: {error}") from error
    identity_before = (
        initial.st_dev, initial.st_ino, initial.st_mode, initial.st_size, initial.st_mtime_ns)
    identity_after = (
        final.st_dev, final.st_ino, final.st_mode, final.st_size, final.st_mtime_ns)
    if identity_before != identity_after or not stat.S_ISREG(final.st_mode):
        raise SnapshotError(f"snapshot path {path} changed while it was read")
    return payload


def _snapshot_entry(root: Path, raw_path: bytes, *, must_exist: bool) -> SnapshotEntry:
    path = root / os.fsdecode(raw_path)
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        if must_exist:
            raise SnapshotError(f"required snapshot path {path} disappeared") from error
        return SnapshotEntry(raw_path, "deleted", None, None)
    except OSError as error:
        raise SnapshotError(f"cannot inspect snapshot path {path}: {error}") from error
    if stat.S_ISREG(info.st_mode):
        mode = "100755" if info.st_mode & 0o111 else "100644"
        return SnapshotEntry(raw_path, "present", mode, _read_regular_file(path, info))
    if stat.S_ISLNK(info.st_mode):
        try:
            target = os.fsencode(os.readlink(path))
            final = path.lstat()
        except OSError as error:
            raise SnapshotError(f"cannot read snapshot symlink {path}: {error}") from error
        if (not stat.S_ISLNK(final.st_mode)
                or (info.st_dev, info.st_ino, info.st_mtime_ns)
                != (final.st_dev, final.st_ino, final.st_mtime_ns)):
            raise SnapshotError(f"snapshot symlink {path} changed while it was read")
        return SnapshotEntry(raw_path, "present", "120000", target)
    raise SnapshotError(f"snapshot path {path} is neither a regular file nor a symlink")


def _snapshot_bytes(head: str, entries: tuple[SnapshotEntry, ...]) -> bytes:
    payload_entries = []
    for entry in entries:
        payload_entries.append({
            "content": (
                None if entry.content is None
                else base64.b64encode(entry.content).decode("ascii")),
            "mode": entry.mode,
            "path": base64.b64encode(entry.path).decode("ascii"),
            "state": entry.state,
        })
    return _canonical_json({
        "entries": payload_entries,
        "head": head,
        "schema": _SNAPSHOT_SCHEMA,
    })


@dataclass(frozen=True)
class _SnapshotGuard:
    head: str
    status: bytes
    index: bytes


def _snapshot_guard(root: Path) -> _SnapshotGuard:
    head = git_full_sha(root, "HEAD")
    if head is None:
        raise SnapshotError("repository HEAD is absent or unreadable")
    try:
        status_bytes = git_read_bytes(
            root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
        raw_index_path = git_read_bytes(root, "rev-parse", "--git-path", "index")
    except GitReadError as error:
        raise SnapshotError(str(error)) from error
    index_name = raw_index_path.rstrip(b"\r\n")
    if not index_name or b"\0" in index_name:
        raise SnapshotError("git rev-parse returned an invalid index path")
    index_path = Path(os.fsdecode(index_name))
    if not index_path.is_absolute():
        index_path = root / index_path
    try:
        index_bytes = index_path.read_bytes()
    except OSError as error:
        raise SnapshotError(f"cannot read live Git index {index_path}: {error}") from error
    return _SnapshotGuard(head=head, status=status_bytes, index=index_bytes)


def _snapshot_entries(root: Path) -> tuple[SnapshotEntry, ...]:
    try:
        unmerged = git_read_bytes(root, "ls-files", "-u", "-z")
        if unmerged:
            raise SnapshotError("repository index has unmerged entries")
        index_paths = _parse_nul_paths(
            git_read_bytes(root, "ls-files", "-z", "--cached"),
            "ls-files --cached",
        )
        head_paths = _parse_nul_paths(
            git_read_bytes(root, "ls-tree", "-r", "-z", "--name-only", "HEAD"),
            "ls-tree",
        )
        untracked = _parse_nul_paths(
            git_read_bytes(root, "ls-files", "-z", "--others", "--exclude-standard"),
            "ls-files",
        )
        index_flags = _parse_index_flags(
            git_read_bytes(root, "ls-files", "-v", "-z", "--cached"))
    except GitReadError as error:
        raise SnapshotError(str(error)) from error
    return tuple(
        _snapshot_entry(
            root,
            path,
            must_exist=(path in untracked or index_flags.get(path) in (b"S", b"s")),
        )
        for path in sorted(head_paths | index_paths | untracked)
    )


def _capture_snapshot(root: Path) -> BaseSnapshot:
    before = _snapshot_guard(root)
    first = _snapshot_entries(root)
    middle = _snapshot_guard(root)
    second = _snapshot_entries(root)
    after = _snapshot_guard(root)
    if before != middle or middle != after or first != second:
        raise SnapshotError(
            "repository HEAD, status, index, or captured content changed during snapshot")
    return BaseSnapshot(head=before.head, entries=first)


def _retry_payload(retry: RetryPolicy) -> dict[str, object]:
    return {
        "budget_exhaustion_policy": retry.budget_exhaustion_policy,
        "cost_budget": {
            "limit": retry.cost_budget.limit,
            "meter": retry.cost_budget.meter,
            "unit": retry.cost_budget.unit,
        },
        "max_attempts_per_job": retry.max_attempts_per_job,
        "max_total_attempts": retry.max_total_attempts,
        "retryable_failure_classes": list(retry.retryable_failure_classes),
        "time_budget": {
            "limit": retry.time_budget.limit,
            "unit": retry.time_budget.unit,
        },
    }


def _run_spec_payload(spec: RunSpec) -> dict[str, object]:
    return {
        "base_snapshot": {
            "digest": spec.base_snapshot.digest,
            "head": spec.base_snapshot.head,
            "reference_id": spec.base_snapshot.reference_id,
            "size": spec.base_snapshot.size,
        },
        "assurance_plan": spec.assurance_plan.to_dict(),
        "candidate": None if spec.candidate is None else dict(spec.candidate),
        "evaluation": dict(spec.evaluation),
        "frame_status_ref": {
            "commit": spec.frame_status_ref.commit,
            "path": spec.frame_status_ref.path,
            "status": spec.frame_status_ref.status,
            "digest": spec.frame_status_ref.digest,
        },
        "job_id": spec.job_id,
        "job_input": _job_input_payload(spec.job_input, include_digest=True),
        "lifecycle_stage": spec.lifecycle_stage.value,
        "objective_ref": spec.objective_ref.to_dict(),
        "project_fact_refs": [reference.to_dict() for reference in spec.project_fact_refs],
        "promotion_lineage": (
            None if spec.promotion_lineage is None else spec.promotion_lineage.to_dict()),
        "result_policy": spec.result_policy.to_dict(),
        "retry": _retry_payload(spec.retry),
        "revision": spec.revision,
        "run_id": spec.run_id,
        "schema": _RUN_SPEC_SCHEMA,
        "supersedes_spec_digest": spec.supersedes_spec_digest,
        "work_brief": spec.work_brief.to_dict(),
    }


def _new_spec(
        run_id: str, job_id: str, *, revision: int,
        supersedes_spec_digest: str | None, lifecycle_stage: LifecycleStage,
        promotion_lineage: PromotionLineage | None, frame_status_ref: FrameStatusRef,
        objective_ref: ObjectiveRef, project_fact_refs: tuple[ProjectFactRef, ...],
        work_brief: ArtifactDescriptor, assurance_plan: ArtifactDescriptor,
        job_input: FrozenJobInput, candidate: Mapping[str, object] | None,
        evaluation: Mapping[str, object], result_policy: ResultPolicy,
        snapshot: BaseSnapshotReference, retry: RetryPolicy) -> RunSpec:
    constructed = RunSpec(
        run_id=run_id,
        job_id=job_id,
        promotion_lineage=promotion_lineage,
        revision=revision,
        supersedes_spec_digest=supersedes_spec_digest,
        lifecycle_stage=lifecycle_stage,
        frame_status_ref=frame_status_ref,
        objective_ref=objective_ref,
        project_fact_refs=project_fact_refs,
        work_brief=work_brief,
        assurance_plan=assurance_plan,
        job_input=job_input,
        candidate=candidate,
        evaluation=evaluation,
        result_policy=result_policy,
        base_snapshot=snapshot,
        retry=retry,
        run_spec_digest="sha256:" + "0" * 64,
    )
    return replace(constructed, run_spec_digest=_digest(constructed.canonical_bytes()))


def _validate_assurance_plan(content: bytes, stage: LifecycleStage) -> AssurancePlan:
    try:
        plan = parse_assurance_plan_bytes(content)
    except WorkflowError as error:
        raise RunSpecArtifactError("<planning>", str(error)) from error
    if plan.lifecycle_stage is not stage:
        raise RunSpecArtifactError(
            "<planning>", "assurance plan schema/stage does not match the WorkBrief")
    return plan


def _bind_assurance_completion_contract(
        plan: AssurancePlan, reference_id: str, contract_digest: str) -> bytes:
    digest = validate_sha256_digest(contract_digest)
    existing = plan.completion.get("contract")
    if existing is not None:
        if not isinstance(existing, Mapping) or existing.get("digest") != digest:
            raise RunSpecArtifactError(
                "<planning>", "AssurancePlan completion contract digest differs from input")
    return replace(plan, completion={
        "contract": {"reference_id": reference_id, "digest": digest},
        "allowed_outcomes": list(plan.completion["allowed_outcomes"]),
    }).canonical_bytes()


def _validate_frame_status(reference: FrameStatusRef) -> None:
    if not isinstance(reference, FrameStatusRef):
        raise TypeError("frame_status_ref must be a FrameStatusRef")
    if (not isinstance(reference.commit, str)
            or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", reference.commit) is None):
        raise ValueError("frame status ref requires a full Git commit")
    if reference.status not in ("provisional", "committed", "superseded"):
        raise ValueError("frame status ref has an invalid status")
    validate_sha256_digest(reference.digest)


def _validate_stage_payload(
    stage: LifecycleStage,
    promotion_lineage: PromotionLineage | None,
    candidate: Mapping[str, object] | None,
    evaluation: Mapping[str, object] | None,
    result_policy: ResultPolicy,
) -> tuple[Mapping[str, object] | None, Mapping[str, object]]:
    if stage is LifecycleStage.EXPLORE:
        if candidate is not None or evaluation not in (None, {"spec": None, "evidence": None}):
            raise ValueError("explore requires candidate/evaluation to be null")
        if result_policy.mode not in ("candidate-ref", "evidence-only"):
            raise ValueError("explore result policy cannot integrate")
        return None, {"spec": None, "evidence": None}
    if promotion_lineage is None:
        raise ValueError("evaluate/promote requires promotion_lineage")
    if not isinstance(candidate, Mapping):
        raise ValueError("evaluate/promote requires a candidate descriptor")
    candidate_fields = {
        "reference_id", "digest", "target_ref", "target_oid", "code_sha",
        "config_digest", "producer_result_digest",
    }
    if set(candidate) != candidate_fields:
        raise ValueError("candidate descriptor fields are not canonical")
    for field in ("digest", "config_digest", "producer_result_digest"):
        validate_sha256_digest(candidate[field])  # type: ignore[arg-type]
    for field in ("target_oid", "code_sha"):
        if (not isinstance(candidate[field], str)
                or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", candidate[field]) is None):
            raise ValueError(f"candidate {field} is invalid")
    if not isinstance(candidate["target_ref"], str) or not candidate["target_ref"].startswith("refs/"):
        raise ValueError("candidate target_ref must be a full refs/* name")
    if not isinstance(evaluation, Mapping) or set(evaluation) != {"spec", "evidence"}:
        raise ValueError("evaluation fields must be spec/evidence")
    spec_ref = evaluation["spec"]
    if not isinstance(spec_ref, Mapping) or set(spec_ref) != {
            "commit", "path", "digest", "generation"}:
        raise ValueError("evaluation spec descriptor is invalid")
    validate_sha256_digest(spec_ref["digest"])  # type: ignore[arg-type]
    if type(spec_ref["generation"]) is not int or spec_ref["generation"] < 1:
        raise ValueError("evaluation generation must be positive")
    evidence = evaluation["evidence"]
    if stage is LifecycleStage.EVALUATE:
        if evidence is not None or result_policy.mode != "evidence-only":
            raise ValueError("evaluate requires null evidence and evidence-only result policy")
    else:
        if not isinstance(evidence, Mapping) or set(evidence) != {
                "reference_id", "digest", "generation"}:
            raise ValueError("promote requires evaluation evidence")
        validate_sha256_digest(evidence["digest"])  # type: ignore[arg-type]
        if evidence["generation"] != spec_ref["generation"]:
            raise ValueError("evaluation evidence generation does not match its spec")
        if result_policy.mode != "integration-ref":
            raise ValueError("promote requires integration-ref result policy")
    return dict(candidate), dict(evaluation)


def _validate_frozen_assurance_inputs(
        root: Path, artifact_store: ArtifactStore, stage: LifecycleStage,
        plan: AssurancePlan, candidate: Mapping[str, object] | None,
        evaluation: Mapping[str, object]) -> None:
    plan_spec = plan.verification.get("evaluation_spec")
    frozen_spec = evaluation.get("spec")
    if stage is LifecycleStage.EXPLORE:
        if plan_spec is not None:
            raise ValueError("explore assurance cannot freeze an evaluation spec")
        return
    if not isinstance(plan_spec, Mapping) or not isinstance(frozen_spec, Mapping):
        raise ValueError("evaluate/promote assurance requires the RunSpec evaluation tuple")
    if (plan_spec.get("digest") != frozen_spec.get("digest")
            or plan_spec.get("generation") != frozen_spec.get("generation")):
        raise ValueError("AssurancePlan and RunSpec evaluation spec tuples differ")
    assert candidate is not None
    candidate_content = artifact_store.read(candidate["digest"])  # type: ignore[arg-type]
    descriptor = parse_candidate_bytes(candidate_content)
    expected_candidate = {
        "target_ref": descriptor.target_ref,
        "target_oid": descriptor.target_oid,
        "code_sha": descriptor.code_sha,
        "config_digest": descriptor.config_digest,
        "producer_result_digest": descriptor.producer["result_digest"],
    }
    if any(candidate.get(key) != value for key, value in expected_candidate.items()):
        raise ValueError("candidate descriptor differs from its content-addressed bytes")
    if git_full_sha(root, descriptor.target_ref) != descriptor.target_oid:
        raise ValueError("candidate ref is not locally reachable at its frozen immutable OID")
    try:
        spec_content = git_read_bytes(
            root, "show", f"{frozen_spec['commit']}:{frozen_spec['path']}")
    except GitReadError as error:
        raise ValueError(f"evaluation spec is not locally readable: {error}") from error
    if digest_bytes(spec_content) != frozen_spec["digest"]:
        raise ValueError("evaluation spec digest differs from committed bytes")
    parsed_spec = parse_evaluation_spec_bytes(spec_content)
    if parsed_spec.generation != frozen_spec["generation"]:
        raise ValueError("evaluation spec generation differs from frozen descriptor")
    if stage is LifecycleStage.PROMOTE:
        evidence_ref = evaluation["evidence"]
        assert isinstance(evidence_ref, Mapping)
        evidence = parse_evaluation_evidence_bytes(
            artifact_store.read(evidence_ref["digest"]))  # type: ignore[arg-type]
        if (evidence.result != "pass"
                or evidence.candidate_digest != candidate["digest"]
                or evidence.evaluation_spec_digest != frozen_spec["digest"]
                or evidence.evaluation_generation != frozen_spec["generation"]):
            raise ValueError("promotion evidence does not pass the frozen candidate/spec tuple")


def _validate_promotion_lineage(
        artifact_store: ArtifactStore, stage: LifecycleStage,
        objective: ObjectiveRef, lineage: PromotionLineage | None,
        candidate: Mapping[str, object] | None, result_policy: ResultPolicy,
        assurance: AssurancePlan) -> None:
    if lineage is None:
        if stage is not LifecycleStage.EXPLORE:
            raise ValueError("evaluate/promote requires a promotion lineage")
        return
    objective_digest = _digest(_canonical_json(objective.to_dict()))
    if lineage.root_objective_ref_digest != objective_digest:
        raise ValueError("promotion lineage root objective digest does not rederive")
    if assurance.review.get("promotion_lineage_id") not in (None, lineage.id):
        raise ValueError("AssurancePlan review lineage differs from RunSpec lineage")
    if (assurance.review.get("cycle_chain_head_digest")
            != lineage.review_cycle_head_digest):
        raise ValueError("review cycle head differs between AssurancePlan and RunSpec lineage")
    if stage in (LifecycleStage.EVALUATE, LifecycleStage.PROMOTE):
        assert candidate is not None
        if lineage.candidate_chain_head_digest != candidate["digest"]:
            raise ValueError("promotion lineage candidate head differs from frozen candidate")
    if stage is LifecycleStage.PROMOTE:
        if result_policy.target_ref != lineage.integration_target_ref:
            raise ValueError("promotion result target differs from lineage integration target")
    if lineage.parent_run_spec_digest is None:
        return
    parent_content = artifact_store.read(lineage.parent_run_spec_digest)
    try:
        parent = json.loads(parent_content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"parent RunSpec is unreadable: {error}") from error
    if (not isinstance(parent, Mapping) or _canonical_json(parent) != parent_content
            or parent.get("schema") != _RUN_SPEC_SCHEMA):
        raise ValueError("parent RunSpec bytes are not canonical RunSpec v2")
    parent_lineage = parent.get("promotion_lineage")
    if parent_lineage is None:
        if stage is not LifecycleStage.EVALUATE or candidate is None:
            raise ValueError("only evaluate may start lineage from an unlineaged explore candidate")
        descriptor = parse_candidate_bytes(artifact_store.read(candidate["digest"]))
        if descriptor.producer["run_spec_digest"] != lineage.parent_run_spec_digest:
            raise ValueError("new evaluation lineage parent is not the candidate producer RunSpec")
        return
    if not isinstance(parent_lineage, Mapping) or any(
            parent_lineage.get(field) != getattr(lineage, field)
            for field in ("id", "root_objective_ref_digest", "integration_target_ref")):
        raise ValueError("parent RunSpec belongs to a different promotion intent")
    parent_assurance_ref = parent.get("assurance_plan")
    if not isinstance(parent_assurance_ref, Mapping):
        raise ValueError("parent RunSpec lacks its assurance descriptor")
    parent_assurance = parse_assurance_plan_bytes(
        artifact_store.read(parent_assurance_ref.get("digest")))
    if parent_assurance.review.get("max_cycles") != assurance.review.get("max_cycles"):
        raise ValueError("descendant RunSpec attempted to reset max_review_cycles")
    parent_candidate = parent_lineage.get("candidate_chain_head_digest")
    current_candidate = lineage.candidate_chain_head_digest
    if current_candidate != parent_candidate and candidate is not None:
        descriptor = parse_candidate_bytes(artifact_store.read(candidate["digest"]))
        if descriptor.supersedes_candidate_digest != parent_candidate:
            raise ValueError("descendant candidate does not supersede the parent lineage head")


def plan_one_task_run(
        task_id: str, *, work_brief_content: bytes,
        completion_contract_content: bytes, assurance_plan_content: bytes,
        frame_status_ref: FrameStatusRef, project_fact_refs: Sequence[ProjectFactRef],
        owner_request_reference: ArtifactReference | None = None,
        artifact_store: ArtifactStore | None = None,
        run_store: RunStore | None = None,
        start: Path | None = None, promotion_lineage: PromotionLineage | None = None,
        candidate: Mapping[str, object] | None = None,
        evaluation: Mapping[str, object] | None = None,
        result_policy: ResultPolicy | None = None,
        retry: RetryPolicy = DEFAULT_RETRY_POLICY) -> RunSpec:
    """Freeze typed semantic inputs and one read-only Git snapshot into RunSpec v2."""
    root = _find_root(start)
    artifact_store = artifact_store or ArtifactStore(root)
    stored_contract = artifact_store.write(completion_contract_content)
    contract = parse_completion_contract_bytes(
        root, completion_contract_content, artifact_store=artifact_store)
    stored_brief = artifact_store.write(work_brief_content)
    brief = parse_work_brief_bytes(
        work_brief_content, artifact_store=artifact_store, completion_contract=contract)
    if brief.task_id != task_id:
        raise InvalidTaskInputError(task_id, "WorkBrief task_id differs from the requested task")
    stage = LifecycleStage(brief.lifecycle_stage)
    assurance = _validate_assurance_plan(assurance_plan_content, stage)
    _bind_assurance_completion_contract(
        assurance, "completion-contract:<pending>", stored_contract.digest)
    _validate_frame_status(frame_status_ref)
    frozen_frame_status = FrameStatusRef(
        commit=frame_status_ref.commit,
        path=frame_status_ref.path,
        status=frame_status_ref.status,
        digest=frame_status_ref.digest,
        source_span=SourceSpan(0, 0, 0, 0),
    )
    facts = tuple(project_fact_refs)
    if any(not isinstance(reference, ProjectFactRef) for reference in facts):
        raise TypeError("project_fact_refs must contain ProjectFactRef values")
    if len({reference.fact_id for reference in facts}) != len(facts):
        raise ValueError("project_fact_refs must not duplicate fact ids")
    objective = brief.objective.ref
    if objective.to_dict() != contract.objective_ref.to_dict():
        raise ValueError("WorkBrief and CompletionContract objective refs differ")
    objective_payload = objective.to_dict()
    if objective_payload.get("kind") == "owner-request":
        if (not isinstance(owner_request_reference, ArtifactReference)
                or owner_request_reference.kind is not ArtifactReferenceKind.INPUT
                or owner_request_reference.reference_id
                != objective_payload["artifact_reference_id"]
                or owner_request_reference.digest != objective_payload["digest"]):
            raise ValueError("owner-request objective requires its exact imported input reference")
    elif owner_request_reference is not None:
        raise ValueError("owner_request_reference is valid only for an owner-request objective")
    if (objective.to_dict().get("kind") == "project-fact"
            and not any(objective.to_dict() == reference.to_dict() for reference in facts)):
        raise ValueError("project-fact objective must appear in project_fact_refs")
    policy_is_default = result_policy is None
    policy = result_policy or ResultPolicy(
        "candidate-ref" if stage is LifecycleStage.EXPLORE else "evidence-only", None, None)
    frozen_candidate, frozen_evaluation = _validate_stage_payload(
        stage, promotion_lineage, candidate, evaluation, policy)
    _validate_frozen_assurance_inputs(
        root, artifact_store, stage, assurance, frozen_candidate, frozen_evaluation)
    _validate_promotion_lineage(
        artifact_store, stage, objective, promotion_lineage,
        frozen_candidate, policy, assurance)

    placeholder_contract = ArtifactDescriptor(
        "completion-contract:<pending>", stored_contract.digest, stored_contract.size)
    acceptance = tuple(criterion.text for criterion in contract.criteria)
    job_input = _freeze_task(
        task_id, _selected_task(root, task_id), placeholder_contract, acceptance)
    snapshot_content = _capture_snapshot(root)
    confirmed_input = _freeze_task(
        task_id, _selected_task(root, task_id), placeholder_contract, acceptance)
    if confirmed_input.input_digest != job_input.input_digest:
        raise RunInputChangedDuringPlanningError(task_id)

    with (RunStore.open(root) if run_store is None else nullcontext(run_store)) as store:
        run = store.create_run(initial_state="candidate")
        frozen_policy = policy
        if (policy_is_default and stage is LifecycleStage.EXPLORE
                and policy.mode == "candidate-ref"):
            frozen_policy = ResultPolicy(
                "candidate-ref", f"refs/waystone/candidates/{run.run_id}", None)
        job_id = f"{run.run_id}:job"
        store.create_job(run.run_id, job_id, initial_state="planned")
        stored_snapshot = artifact_store.write(snapshot_content.canonical_bytes())
        snapshot_reference = BaseSnapshotReference(
            head=snapshot_content.head,
            reference_id=f"{_SNAPSHOT_REFERENCE_PREFIX}{run.run_id}",
            digest=stored_snapshot.digest,
            size=stored_snapshot.size,
        )
        revision = 1
        work_brief = ArtifactDescriptor(
            f"work-brief:{run.run_id}:{brief.revision}", stored_brief.digest, stored_brief.size)
        completion = ArtifactDescriptor(
            f"completion-contract:{run.run_id}:{revision}",
            stored_contract.digest, stored_contract.size)
        stored_assurance = artifact_store.write(_bind_assurance_completion_contract(
            assurance, completion.reference_id, completion.digest))
        assurance_plan = ArtifactDescriptor(
            f"assurance-plan:{run.run_id}:{revision}",
            stored_assurance.digest, stored_assurance.size)
        job_input = _freeze_task(
            task_id, _selected_task(root, task_id), completion, acceptance)
        spec = _new_spec(
            run.run_id, job_id,
            revision=revision,
            supersedes_spec_digest=None,
            lifecycle_stage=stage,
            promotion_lineage=promotion_lineage,
            frame_status_ref=frozen_frame_status,
            objective_ref=objective,
            project_fact_refs=facts,
            work_brief=work_brief,
            assurance_plan=assurance_plan,
            job_input=job_input,
            candidate=frozen_candidate,
            evaluation=frozen_evaluation,
            result_policy=frozen_policy,
            snapshot=snapshot_reference,
            retry=retry,
        )
        stored_spec = artifact_store.write(spec.canonical_bytes())
        if stored_spec.digest != spec.run_spec_digest:
            raise RunSpecArtifactError(run.run_id, "stored RunSpec digest changed")
        store.record_transition(
            EntityKind.RUN,
            run.run_id,
            expected_version=run.version,
            next_state="frozen-ready",
            reason=TransitionReason.PLANNED,
            evidence_digest=stored_spec.digest,
            artifact_references=(
                ArtifactReference(
                    reference_id=f"{_RUN_SPEC_REFERENCE_PREFIX}{run.run_id}:1",
                    kind=ArtifactReferenceKind.INPUT,
                    digest=stored_spec.digest,
                    size=stored_spec.size,
                ),
                ArtifactReference(
                    reference_id=work_brief.reference_id,
                    kind=ArtifactReferenceKind.INPUT,
                    digest=work_brief.digest,
                    size=work_brief.size,
                ),
                ArtifactReference(
                    reference_id=assurance_plan.reference_id,
                    kind=ArtifactReferenceKind.INPUT,
                    digest=assurance_plan.digest,
                    size=assurance_plan.size,
                ),
                ArtifactReference(
                    reference_id=completion.reference_id,
                    kind=ArtifactReferenceKind.INPUT,
                    digest=completion.digest,
                    size=completion.size,
                ),
                ArtifactReference(
                    reference_id=snapshot_reference.reference_id,
                    kind=ArtifactReferenceKind.INPUT,
                    digest=stored_snapshot.digest,
                    size=stored_snapshot.size,
                ),
                *((owner_request_reference,) if owner_request_reference is not None else ()),
            ),
        )
        return spec


def prepare_run_spec_revision(
        previous: RunSpec, *, work_brief_content: bytes,
        completion_contract_content: bytes, assurance_plan_content: bytes,
        resolves_context_request_digest: str, start: Path | None = None,
) -> PreparedRunSpecRevision:
    """Validate and materialize immutable CAS inputs for one context-resume revision."""
    if not isinstance(previous, RunSpec):
        raise TypeError("previous must be a RunSpec")
    root = _find_root(start)
    request_digest = validate_sha256_digest(resolves_context_request_digest)
    artifact_store = ArtifactStore(root)
    stored_contract = artifact_store.write(completion_contract_content)
    contract = parse_completion_contract_bytes(
        root, completion_contract_content, artifact_store=artifact_store)
    stored_brief = artifact_store.write(work_brief_content)
    brief = parse_work_brief_bytes(
        work_brief_content,
        artifact_store=artifact_store,
        completion_contract=contract,
        context_resume=True,
    )
    if (brief.task_id != previous.job_input.task_id
            or brief.lifecycle_stage != previous.lifecycle_stage.value
            or brief.revision != previous.revision + 1
            or brief.supersedes_digest != previous.work_brief.digest
            or brief.resolves_context_request_digest != request_digest):
        raise RunSpecArtifactError(
            previous.run_id, "WorkBrief does not continue the current context/spec lineage")
    if brief.objective.ref.to_dict() != previous.objective_ref.to_dict():
        raise RunSpecArtifactError(previous.run_id, "context resume cannot replace the objective")
    assurance = _validate_assurance_plan(
        assurance_plan_content, previous.lifecycle_stage)
    revision = previous.revision + 1
    work_brief = ArtifactDescriptor(
        f"work-brief:{previous.run_id}:{brief.revision}",
        stored_brief.digest,
        stored_brief.size,
    )
    completion = ArtifactDescriptor(
        f"completion-contract:{previous.run_id}:{revision}",
        stored_contract.digest,
        stored_contract.size,
    )
    stored_assurance = artifact_store.write(_bind_assurance_completion_contract(
        assurance, completion.reference_id, completion.digest))
    assurance_plan = ArtifactDescriptor(
        f"assurance-plan:{previous.run_id}:{revision}",
        stored_assurance.digest,
        stored_assurance.size,
    )
    job_input_candidate = replace(
        previous.job_input,
        completion_contract=completion,
        input_digest="sha256:" + "0" * 64,
        acceptance_criteria=tuple(criterion.text for criterion in contract.criteria),
    )
    job_input = replace(
        job_input_candidate,
        input_digest=_digest(job_input_candidate.canonical_bytes()),
    )
    spec = _new_spec(
        previous.run_id,
        previous.job_id,
        revision=revision,
        supersedes_spec_digest=previous.run_spec_digest,
        lifecycle_stage=previous.lifecycle_stage,
        promotion_lineage=previous.promotion_lineage,
        frame_status_ref=previous.frame_status_ref,
        objective_ref=previous.objective_ref,
        project_fact_refs=previous.project_fact_refs,
        work_brief=work_brief,
        assurance_plan=assurance_plan,
        job_input=job_input,
        candidate=previous.candidate,
        evaluation=previous.evaluation,
        result_policy=previous.result_policy,
        snapshot=previous.base_snapshot,
        retry=previous.retry,
    )
    stored_spec = artifact_store.write(spec.canonical_bytes())
    if stored_spec.digest != spec.run_spec_digest:
        raise RunSpecArtifactError(previous.run_id, "stored RunSpec revision digest changed")
    return PreparedRunSpecRevision(
        spec,
        stored_brief,
        stored_assurance,
        stored_contract,
        stored_spec,
    )


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _exact_keys(payload: dict[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields are not canonical")


def _parse_string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string list")
    return tuple(value)


def _descriptor(
    value: object, label: str, references: Mapping[str, ArtifactReference],
) -> ArtifactDescriptor:
    row = _require_mapping(value, label)
    _exact_keys(row, {"reference_id", "digest"}, label)
    reference_id = row["reference_id"]
    if not isinstance(reference_id, str) or reference_id not in references:
        raise ValueError(f"{label} durable reference is missing")
    reference = references[reference_id]
    if reference.digest != row["digest"]:
        raise ValueError(f"{label} digest differs from its durable reference")
    return ArtifactDescriptor(reference.reference_id, reference.digest, reference.size)


def _parse_run_spec(
    payload: bytes, expected_run_id: str, digest: str, *, root_path: Path,
    references: Mapping[str, ArtifactReference], artifact_store: ArtifactStore,
) -> RunSpec:
    try:
        decoded = json.loads(payload.decode("utf-8"))
        root = _require_mapping(decoded, "RunSpec")
        _exact_keys(root, {
            "assurance_plan", "base_snapshot", "candidate", "evaluation", "frame_status_ref",
            "job_id", "job_input", "lifecycle_stage", "objective_ref",
            "project_fact_refs", "promotion_lineage", "result_policy", "retry", "revision",
            "run_id", "schema", "supersedes_spec_digest", "work_brief",
        }, "RunSpec")
        if root["schema"] != _RUN_SPEC_SCHEMA or root["run_id"] != expected_run_id:
            raise ValueError("RunSpec schema or run identity does not match its reference")
        job = _require_mapping(root["job_input"], "job_input")
        _exact_keys(job, {
            "completion_contract", "dependencies", "input_digest", "scope", "task_id", "title",
        }, "job_input")
        completion = _descriptor(job["completion_contract"], "completion_contract", references)
        contract_bytes = artifact_store.read_reference(references[completion.reference_id])
        contract = parse_completion_contract_bytes(
            root_path, contract_bytes, artifact_store=artifact_store)
        job_input = FrozenJobInput(
            task_id=job["task_id"],
            title=job["title"],
            completion_contract=completion,
            scope=_parse_string_list(job["scope"], "scope"),
            dependencies=_parse_string_list(job["dependencies"], "dependencies"),
            input_digest=validate_sha256_digest(job["input_digest"]),
            acceptance_criteria=tuple(criterion.text for criterion in contract.criteria),
        )
        if _digest(job_input.canonical_bytes()) != job_input.input_digest:
            raise ValueError("job input digest does not match canonical owner fields")

        snapshot = _require_mapping(root["base_snapshot"], "base_snapshot")
        _exact_keys(snapshot, {"digest", "head", "reference_id", "size"}, "base_snapshot")
        base_snapshot = BaseSnapshotReference(
            head=snapshot["head"],
            reference_id=snapshot["reference_id"],
            digest=validate_sha256_digest(snapshot["digest"]),
            size=snapshot["size"],
        )
        retry_payload = _require_mapping(root["retry"], "retry")
        _exact_keys(retry_payload, {
            "budget_exhaustion_policy", "cost_budget", "max_attempts_per_job",
            "max_total_attempts", "retryable_failure_classes", "time_budget",
        }, "retry")
        time_budget = _require_mapping(retry_payload["time_budget"], "time_budget")
        cost_budget = _require_mapping(retry_payload["cost_budget"], "cost_budget")
        retry = RetryPolicy(
            max_attempts_per_job=retry_payload["max_attempts_per_job"],
            max_total_attempts=retry_payload["max_total_attempts"],
            time_budget=BudgetLimit(time_budget["limit"], time_budget["unit"]),
            cost_budget=CostBudget(
                cost_budget["limit"], cost_budget["unit"], cost_budget["meter"]),
            retryable_failure_classes=_parse_string_list(
                retry_payload["retryable_failure_classes"], "retryable_failure_classes"),
            budget_exhaustion_policy=retry_payload["budget_exhaustion_policy"],
        )
        stage = LifecycleStage(root["lifecycle_stage"])
        work_brief = _descriptor(root["work_brief"], "work_brief", references)
        assurance_plan = _descriptor(root["assurance_plan"], "assurance_plan", references)
        brief_bytes = artifact_store.read_reference(references[work_brief.reference_id])
        brief = parse_work_brief_bytes(
            brief_bytes, artifact_store=artifact_store, completion_contract=contract)
        assurance_bytes = artifact_store.read_reference(references[assurance_plan.reference_id])
        assurance = _validate_assurance_plan(assurance_bytes, stage)
        frame = _require_mapping(root["frame_status_ref"], "frame_status_ref")
        _exact_keys(frame, {"commit", "path", "status", "digest"}, "frame_status_ref")
        frame_ref = FrameStatusRef(
            commit=frame["commit"], path=frame["path"], status=frame["status"],
            digest=frame["digest"], source_span=SourceSpan(0, 0, 0, 0))
        _validate_frame_status(frame_ref)
        raw_facts = root["project_fact_refs"]
        if not isinstance(raw_facts, list):
            raise ValueError("project_fact_refs must be a list")
        facts = tuple(ProjectFactRef(
            commit=row["commit"], path=row["path"], fact_id=row["fact_id"],
            fact_digest=row["fact_digest"], binding=row["binding"],
        ) for row in (_require_mapping(value, "project_fact_ref") for value in raw_facts))
        objective = parse_objective_ref(root["objective_ref"])
        if brief.objective.ref.to_dict() != objective.to_dict():
            raise ValueError("RunSpec objective differs from WorkBrief")
        lineage_row = root["promotion_lineage"]
        lineage = None
        if lineage_row is not None:
            row = _require_mapping(lineage_row, "promotion_lineage")
            _exact_keys(row, {
                "id", "root_objective_ref_digest", "integration_target_ref",
                "parent_run_spec_digest", "candidate_chain_head_digest",
                "review_cycle_head_digest",
            }, "promotion_lineage")
            lineage = PromotionLineage(**row)
        policy_row = _require_mapping(root["result_policy"], "result_policy")
        _exact_keys(policy_row, {"mode", "target_ref", "expected_oid"}, "result_policy")
        policy = ResultPolicy(**policy_row)
        frozen_candidate, frozen_evaluation = _validate_stage_payload(
            stage, lineage, root["candidate"], root["evaluation"], policy)
        _validate_frozen_assurance_inputs(
            root_path, artifact_store, stage, assurance,
            frozen_candidate, frozen_evaluation)
        _validate_promotion_lineage(
            artifact_store, stage, objective, lineage,
            frozen_candidate, policy, assurance)
        supersedes = root["supersedes_spec_digest"]
        revision = root["revision"]
        if type(revision) is not int or revision < 1:
            raise ValueError("revision must be positive")
        if revision == 1:
            if supersedes is not None:
                raise ValueError("revision 1 cannot supersede another RunSpec")
        else:
            supersedes = validate_sha256_digest(supersedes)
        spec = RunSpec(
            run_id=root["run_id"],
            job_id=root["job_id"],
            promotion_lineage=lineage,
            revision=revision,
            supersedes_spec_digest=supersedes,
            lifecycle_stage=stage,
            frame_status_ref=frame_ref,
            objective_ref=objective,
            project_fact_refs=facts,
            work_brief=work_brief,
            assurance_plan=assurance_plan,
            job_input=job_input,
            candidate=frozen_candidate,
            evaluation=frozen_evaluation,
            result_policy=policy,
            base_snapshot=base_snapshot,
            retry=retry,
            run_spec_digest=validate_sha256_digest(digest),
        )
        if spec.canonical_bytes() != payload or _digest(payload) != spec.run_spec_digest:
            raise ValueError("RunSpec bytes are not canonical or do not match their digest")
        return spec
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise RunSpecArtifactError(expected_run_id, str(error)) from error


def load_run_spec(run_id: str, *, start: Path | None = None) -> RunSpec:
    """Load and revalidate one immutable RunSpec from its durable store reference."""
    root_path = _find_root(start)
    with RunStore.open(root_path) as store:
        store.get_run(run_id)
        with store._connection_lock:  # noqa: SLF001 - immutable spec-head lookup
            rows = store._connection.execute(  # noqa: SLF001
                "SELECT reference_id FROM artifacts WHERE reference_id LIKE ?",
                (f"{_RUN_SPEC_REFERENCE_PREFIX}{run_id}:%",),
            ).fetchall()
        revisions = []
        for row in rows:
            suffix = row["reference_id"].removeprefix(f"{_RUN_SPEC_REFERENCE_PREFIX}{run_id}:")
            if suffix.isdigit() and int(suffix) >= 1:
                revisions.append((int(suffix), row["reference_id"]))
        if not revisions:
            raise RecordNotFoundError("run spec", run_id)
        revision, reference_id = max(revisions)
        if len([item for item in revisions if item[0] == revision]) != 1:
            raise RunSpecArtifactError(run_id, "RunSpec revision head is ambiguous")
        reference = store.get_artifact_reference(reference_id)
        artifact_store = ArtifactStore(root_path)
        payload = artifact_store.read_reference(reference)
        decoded = json.loads(payload.decode("utf-8"))
        descriptor_ids = (
            decoded["work_brief"]["reference_id"],
            decoded["assurance_plan"]["reference_id"],
            decoded["job_input"]["completion_contract"]["reference_id"],
        )
        references = {
            identity: store.get_artifact_reference(identity) for identity in descriptor_ids
        }
    return _parse_run_spec(
        payload, run_id, reference.digest, root_path=root_path,
        references=references, artifact_store=artifact_store)


def _parse_snapshot(payload: bytes, expected_head: str) -> BaseSnapshot:
    try:
        decoded = json.loads(payload.decode("utf-8"))
        root = _require_mapping(decoded, "base snapshot")
        _exact_keys(root, {"entries", "head", "schema"}, "base snapshot")
        if root["schema"] != _SNAPSHOT_SCHEMA or root["head"] != expected_head:
            raise ValueError("base snapshot schema or HEAD is invalid")
        raw_entries = root["entries"]
        if not isinstance(raw_entries, list):
            raise ValueError("base snapshot entries must be a list")
        entries: list[SnapshotEntry] = []
        for raw in raw_entries:
            row = _require_mapping(raw, "snapshot entry")
            _exact_keys(row, {"content", "mode", "path", "state"}, "snapshot entry")
            path = base64.b64decode(row["path"], validate=True)
            content = (
                None if row["content"] is None
                else base64.b64decode(row["content"], validate=True))
            entries.append(SnapshotEntry(path, row["state"], row["mode"], content))
        snapshot = BaseSnapshot(head=root["head"], entries=tuple(entries))
        if tuple(sorted(entry.path for entry in snapshot.entries)) != tuple(
                entry.path for entry in snapshot.entries):
            raise ValueError("base snapshot entries are not path-sorted")
        if snapshot.canonical_bytes() != payload:
            raise ValueError("base snapshot bytes are not canonical")
        return snapshot
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise SnapshotError(f"stored base snapshot is invalid: {error}") from error


def read_base_snapshot(run_id: str, *, start: Path | None = None) -> BaseSnapshot:
    """Read and verify the canonical HEAD-rooted snapshot overlay for one run."""
    root = _find_root(start)
    spec = load_run_spec(run_id, start=root)
    with RunStore.open(root) as store:
        reference = store.get_artifact_reference(spec.base_snapshot.reference_id)
        if (reference.digest != spec.base_snapshot.digest
                or reference.size != spec.base_snapshot.size):
            raise RunSpecArtifactError(run_id, "base snapshot reference disagrees with RunSpec")
        payload = ArtifactStore(root).read_reference(reference)
    return _parse_snapshot(payload, spec.base_snapshot.head)


def _changed_fields(frozen: FrozenJobInput, current: FrozenJobInput) -> tuple[str, ...]:
    fields = ("dependencies", "scope", "task_id", "title")
    return tuple(field for field in fields if getattr(frozen, field) != getattr(current, field))


def detect_task_input_drift(
        run_id: str, *, start: Path | None = None) -> RunInputDrift | None:
    """Compare current owner fields with a run's frozen input without mutating either authority."""
    root = _find_root(start)
    spec = load_run_spec(run_id, start=root)
    try:
        current = _freeze_task(
            spec.job_input.task_id,
            _selected_task(root, spec.job_input.task_id),
            spec.job_input.completion_contract,
            spec.job_input.acceptance_criteria,
        )
    except (TaskNotFoundError, InvalidTaskInputError):
        return RunInputDrift(
            run_id=run_id,
            task_id=spec.job_input.task_id,
            frozen_digest=spec.job_input.input_digest,
            current_digest=None,
            changed_fields=("task_availability",),
        )
    if current.input_digest == spec.job_input.input_digest:
        return None
    return RunInputDrift(
        run_id=run_id,
        task_id=spec.job_input.task_id,
        frozen_digest=spec.job_input.input_digest,
        current_digest=current.input_digest,
        changed_fields=_changed_fields(spec.job_input, current),
    )


def assert_task_input_current(run_id: str, *, start: Path | None = None) -> RunSpec:
    """Return the frozen spec only when the owner registry still names the same input bytes."""
    drift = detect_task_input_drift(run_id, start=start)
    if drift is not None:
        raise RunInputDriftError(drift)
    return load_run_spec(run_id, start=start)


__all__ = [
    "ArtifactDescriptor",
    "BaseSnapshot",
    "BaseSnapshotReference",
    "BudgetLimit",
    "CostBudget",
    "DEFAULT_RETRY_POLICY",
    "FrozenJobInput",
    "InvalidTaskInputError",
    "PreparedRunSpecRevision",
    "PromotionLineage",
    "ResultPolicy",
    "RetryPolicy",
    "RunInputDrift",
    "RunInputDriftError",
    "RunInputChangedDuringPlanningError",
    "RunSpec",
    "RunSpecArtifactError",
    "RunSpecError",
    "SnapshotEntry",
    "SnapshotError",
    "TaskNotFoundError",
    "UninitializedRunSpecError",
    "assert_task_input_current",
    "detect_task_input_drift",
    "load_run_spec",
    "plan_one_task_run",
    "prepare_run_spec_revision",
    "read_base_snapshot",
]
