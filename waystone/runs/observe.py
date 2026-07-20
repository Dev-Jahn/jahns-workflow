"""Read-only run status, JSON, and watch projections."""
from __future__ import annotations

import math
import sqlite3
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterator, Mapping

from waystone.core import WorkflowError
from waystone.runs import spec as spec_module, store as store_module
from waystone.runs.artifacts import ArtifactError, ArtifactStore
from waystone.runs.effects import (
    EffectEngine,
    EffectError,
    EffectKind,
    EffectPlan,
    EffectResultState,
)
from waystone.runs.lease import LeaseManager
from waystone.runs.store import (
    CorruptRuntimeRecordError,
    EntityKind,
    EntityRecord,
    RecordNotFoundError,
    RunStore,
    StateDatabaseError,
    StoreError,
)
from waystone.runs.supervisor import (
    HeartbeatFreshness,
    LivenessObservation,
    LivenessState,
    ProcessIdentity,
    Supervisor,
    SupervisorError,
    _read_runtime,
)


_TERMINAL_JOB_STATES = frozenset({"accepted", "canceled", "completed", "failed"})
_ACTIVE_ACTION_STATES = frozenset({"claimed", "effect", "observed"})
_EFFECT_OBSERVATION_STATES = frozenset({"effect", "observed"})


class StatusUnavailable(WorkflowError):
    """The runtime authority could not provide a status snapshot."""

    code = "status-unavailable"

    def __init__(self, run_id: str, detail: str):
        self.run_id = run_id
        self.detail = detail
        super().__init__(f"{self.code}: run {run_id!r}: {detail}")


@dataclass(frozen=True)
class LivenessProjection:
    state: str
    reason: str
    heartbeat: str = HeartbeatFreshness.UNKNOWN.value


@dataclass(frozen=True)
class ProgressProjection:
    state: str
    reason: str | None
    completed_tasks: int | None
    total_tasks: int | None
    task_state_counts: tuple[tuple[str, int], ...]
    job_state_counts: tuple[tuple[str, int], ...]
    task_id: str | None = None
    job_id: str | None = None


@dataclass(frozen=True)
class CurrentProjection:
    state: str
    reason: str | None
    action_kind: str | None
    claimed_at: str | None
    action_id: str | None = None
    lease_epoch: int | None = None
    worktree_path: str | None = None
    process_identity: tuple[tuple[str, object], ...] | None = None


@dataclass(frozen=True)
class ActionProjection:
    action_id: str
    state: str
    action_kind: str | None
    effect_state: str | None
    liveness: LivenessProjection
    active_claim: bool
    claimed_at: str | None
    lease_epoch: int | None
    worktree_path: str | None
    process_identity: tuple[tuple[str, object], ...] | None
    progress_capable: bool
    blocker_reason: str | None


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    run_state: str
    health: str
    health_reason: str
    liveness: LivenessProjection
    progress: ProgressProjection
    current: CurrentProjection
    actions: tuple[ActionProjection, ...]


def _counts(states: list[str]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(Counter(states).items()))


@contextmanager
def _database_snapshot(
        store: RunStore, effects: EffectEngine,
) -> Iterator[tuple[RunStore, EffectEngine]]:
    """Copy one coherent DB read point into a query-only in-memory store."""
    connection = sqlite3.connect(
        ":memory:", isolation_level=None, check_same_thread=False)
    snapshot_store: RunStore | None = None
    try:
        connection.row_factory = sqlite3.Row
        with store._connection_lock:  # noqa: SLF001 - one source snapshot boundary
            try:
                store._connection.backup(connection)  # noqa: SLF001
            except sqlite3.DatabaseError as error:
                raise StateDatabaseError(
                    "read status snapshot", str(error)) from error
        connection.execute("PRAGMA query_only=ON")
        snapshot_store = RunStore(
            store.project_root,
            store.database_path,
            connection,
            store.filesystem,
            store.schema_version,
            _token=store_module._RUN_STORE_CONSTRUCTION_TOKEN,  # noqa: SLF001
        )
        snapshot_leases = LeaseManager(snapshot_store)
        snapshot_effects = EffectEngine(
            snapshot_store,
            snapshot_leases,
            runner_executor=effects._runner_executor,  # noqa: SLF001
            runner_identity_verifier=effects._runner_identity_verifier,  # noqa: SLF001
        )
        yield snapshot_store, snapshot_effects
    finally:
        if snapshot_store is not None:
            snapshot_store.close()
        else:
            connection.close()


def _read_entity_ids(
        store: RunStore, kind: EntityKind, run_id: str) -> tuple[str, ...]:
    with store._connection_lock:  # noqa: SLF001 - package read-side composition boundary
        rows = store._connection.execute(  # noqa: SLF001
            "SELECT DISTINCT entity_id FROM transitions "
            "WHERE run_id = ? AND entity_kind = ? ORDER BY entity_id",
            (run_id, kind.value),
        ).fetchall()
        identities: list[str] = []
        for row in rows:
            value = row[0]
            if not isinstance(value, str) or not value:
                raise CorruptRuntimeRecordError(
                    run_id, kind, "<unknown>", "audit entity identity is malformed")
            owner = store._membership_owner(kind, value)  # noqa: SLF001
            if owner is not None and owner != run_id:
                continue
            identities.append(value)
    return tuple(identities)


def _read_children(
        store: RunStore, run_id: str, kind: EntityKind,
) -> tuple[tuple[EntityRecord, ...], bool]:
    records: list[EntityRecord] = []
    corrupt = False
    try:
        identities = _read_entity_ids(store, kind, run_id)
    except CorruptRuntimeRecordError:
        return (), True
    for identity in identities:
        try:
            record = store.get_entity(kind, identity)
        except (CorruptRuntimeRecordError, RecordNotFoundError):
            corrupt = True
            continue
        if record.run_id != run_id:
            corrupt = True
            continue
        records.append(record)
    return tuple(records), corrupt


def _read_graph(
        store: RunStore, run_id: str,
) -> tuple[EntityRecord | None, tuple[EntityRecord, ...], tuple[EntityRecord, ...], bool]:
    try:
        run = store.get_entity(EntityKind.RUN, run_id)
    except CorruptRuntimeRecordError:
        return None, (), (), True
    graph_corrupt = False
    try:
        store.get_run(run_id)
    except CorruptRuntimeRecordError:
        graph_corrupt = True
    jobs, jobs_corrupt = _read_children(store, run_id, EntityKind.JOB)
    actions, actions_corrupt = _read_children(store, run_id, EntityKind.ACTION)
    return run, jobs, actions, graph_corrupt or jobs_corrupt or actions_corrupt


def _read_progress(
        store: RunStore, run_id: str, jobs: tuple[EntityRecord, ...], *, corrupt: bool,
) -> ProgressProjection:
    job_counts = _counts([job.state for job in jobs])
    if corrupt:
        return ProgressProjection(
            "unknown-progress", "corrupt-runtime-record", None, None, (), job_counts)
    try:
        reference = store.get_artifact_reference(f"run-spec:{run_id}")
        payload = ArtifactStore(store.project_root).read_reference(reference)
        spec = spec_module._parse_run_spec(payload, run_id, reference.digest)  # noqa: SLF001
    except StateDatabaseError:
        raise
    except (ArtifactError, CorruptRuntimeRecordError, RecordNotFoundError,
            spec_module.RunSpecError):
        return ProgressProjection(
            "unknown-progress", "frozen-closure-unavailable", None, None, (), job_counts)
    matching = [job for job in jobs if job.entity_id == spec.job_id]
    if len(jobs) != 1 or len(matching) != 1:
        return ProgressProjection(
            "unknown-progress", "frozen-closure-job-mismatch", None, None, (), job_counts,
            task_id=spec.job_input.task_id, job_id=spec.job_id)
    state = matching[0].state
    completed = 1 if state in _TERMINAL_JOB_STATES else 0
    return ProgressProjection(
        "known", None, completed, 1, ((state, 1),), job_counts,
        task_id=spec.job_input.task_id, job_id=spec.job_id)


def _read_lease(store: RunStore, action: EntityRecord) -> tuple[dict[str, object] | None, bool]:
    with store._connection_lock:  # noqa: SLF001 - package read-side composition boundary
        rows = store._connection.execute(  # noqa: SLF001
            "SELECT l.lease_id, l.run_id, l.entity_kind, l.entity_id, l.entity_version, "
            "l.owner_token, l.fencing_epoch, l.expires_at, l.observed_at, "
            "r.entity_version AS runtime_entity_version, r.heartbeat_at "
            "FROM leases l LEFT JOIN action_runtime r ON r.action_id = l.entity_id "
            "WHERE l.lease_id = ? OR (l.entity_kind = ? AND l.entity_id = ?)",
            (action.entity_id, EntityKind.ACTION.value, action.entity_id),
        ).fetchall()
    if not rows:
        return None, action.state in _ACTIVE_ACTION_STATES
    if len(rows) != 1:
        return None, True
    row = dict(rows[0])
    epoch = row["fencing_epoch"]
    owner = row["owner_token"]
    lease_version = row["entity_version"]
    valid_principal = (
        owner is None and LeaseManager._valid_epoch(epoch, allow_zero=True)  # noqa: SLF001
    ) or (
        isinstance(owner, str) and bool(owner)
        and LeaseManager._valid_epoch(epoch)  # noqa: SLF001
    )
    coherent = (
        row["lease_id"] == action.entity_id
        and row["run_id"] == action.run_id
        and row["entity_kind"] == EntityKind.ACTION.value
        and row["entity_id"] == action.entity_id
        and not isinstance(lease_version, bool)
        and isinstance(lease_version, int)
        and lease_version == action.version
        and valid_principal
    )
    runtime_version = row["runtime_entity_version"]
    if runtime_version is not None and runtime_version != action.version:
        coherent = False
    return (row if coherent else None), not coherent


def _claimed_at(lease: Mapping[str, object]) -> str | None:
    owner = lease.get("owner_token")
    observed_at = lease.get("observed_at")
    heartbeat_at = lease.get("heartbeat_at")
    if not isinstance(owner, str) or not owner or not isinstance(observed_at, str):
        return None
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        return None
    # renew writes the same timestamp to leases and action_runtime atomically.  A missing
    # heartbeat, or an older heartbeat left by a prior principal, proves observed_at came
    # from the current claim/reclaim rather than a heartbeat renewal.
    if heartbeat_at is None or heartbeat_at != observed_at:
        return observed_at
    return None


def _read_plan(
        store: RunStore, effects: EffectEngine, action: EntityRecord,
) -> tuple[EffectPlan | None, bool]:
    try:
        store.get_artifact_reference(f"effect-plan:{action.entity_id}")
    except StateDatabaseError:
        raise
    except RecordNotFoundError:
        return None, True
    except CorruptRuntimeRecordError:
        return None, True
    try:
        return effects._load_plan(action.entity_id), False  # noqa: SLF001
    except StateDatabaseError:
        raise
    except (CorruptRuntimeRecordError, EffectError):
        return None, True


def _runner_identity_fields(
        store: RunStore, effects: EffectEngine, supervisor: Supervisor,
        action: EntityRecord, plan: EffectPlan,
        lease: Mapping[str, object] | None,
) -> tuple[tuple[tuple[str, object], ...] | None, str | None]:
    """Bind supervisor evidence to the current action, principal, and frozen intent."""
    if lease is None:
        return None, "identity-incomplete"
    try:
        runtime = _read_runtime(  # noqa: SLF001
            supervisor._runtime_path(action.entity_id))
        identity = ProcessIdentity.from_payload(runtime["process_identity"])
        supervisor_identity = ProcessIdentity.from_payload(runtime["supervisor_identity"])
    except (SupervisorError, KeyError, TypeError, ValueError):
        return None, "identity-incomplete"

    owner = lease.get("owner_token")
    epoch = lease.get("fencing_epoch")
    if not isinstance(owner, str) or not owner:
        return None, "identity-incomplete"
    invocation_digest = plan.spec.get("invocation_digest")
    envelope_matches = (
        runtime.get("run_id") == action.run_id == plan.run_id
        and runtime.get("job_id") == action.parent_job_id == plan.job_id
        and runtime.get("action_id") == action.entity_id == plan.action_id
        and runtime.get("owner_token") == owner
        and runtime.get("fencing_epoch") == epoch
        and runtime.get("invocation_digest") == invocation_digest
    )
    identity_matches = (
        identity.action_id == action.entity_id
        and identity.supervisor_owner_token == owner
        and identity.fencing_epoch == epoch
        and identity.invocation_digest == invocation_digest
        and supervisor_identity.action_id == action.entity_id
        and supervisor_identity.supervisor_owner_token == owner
        and supervisor_identity.fencing_epoch == epoch
        and supervisor_identity.resolved_executable is not None
        and supervisor_identity.host_boot_identity == identity.host_boot_identity
    )
    if not envelope_matches or not identity_matches:
        return None, "identity-mismatch"

    try:
        intent = effects._load_intent(plan)  # noqa: SLF001
    except (CorruptRuntimeRecordError, EffectError, RecordNotFoundError):
        return None, "identity-incomplete"
    with store._connection_lock:  # noqa: SLF001 - snapshot-local attribution read
        row = store._connection.execute(  # noqa: SLF001
            "SELECT t.entity_version FROM artifacts a JOIN transitions t "
            "ON t.transition_id = a.transition_id "
            "WHERE a.reference_id = ? AND a.entity_kind = ? AND a.entity_id = ?",
            (f"effect-intent:{action.entity_id}", EntityKind.ACTION.value,
             action.entity_id),
        ).fetchone()
    if row is None:
        return None, "identity-incomplete"
    if (
            runtime.get("launch_token") != intent.get("launch_token")
            or runtime.get("fencing_epoch") != intent.get("fencing_epoch")
            or runtime.get("entity_version") != row["entity_version"]):
        return None, "identity-mismatch"
    return tuple(sorted(identity.to_payload().items())), None


def _projection_liveness(
        store: RunStore, effects: EffectEngine, supervisor: Supervisor,
        action: EntityRecord, plan: EffectPlan | None,
        lease: Mapping[str, object] | None, *, stale_after: float,
) -> tuple[LivenessProjection, tuple[tuple[str, object], ...] | None]:
    action_kind = None if plan is None else plan.kind.value
    process_identity = None
    identity_reason = None
    if plan is not None and plan.kind is EffectKind.RUNNER_EXECUTION:
        process_identity, identity_reason = _runner_identity_fields(
            store, effects, supervisor, action, plan, lease)
    if action.state == "completed":
        if plan is None:
            return LivenessProjection(
                "unknown", "positive-exit-evidence-unavailable"), None
        return LivenessProjection(
            "exited", "authoritative-effect-completed"), process_identity
    if action_kind == EffectKind.RUNNER_EXECUTION.value and action.state in _ACTIVE_ACTION_STATES:
        try:
            observation = supervisor.probe_action(
                action.entity_id, stale_after=stale_after)
        except SupervisorError as error:
            observation = LivenessObservation(
                LivenessState.UNKNOWN,
                f"process-observation-unavailable:{error.code}",
            )
        if not isinstance(observation, LivenessObservation):
            return LivenessProjection(
                "unknown", "process-observation-invalid"), None
        if identity_reason is not None:
            return LivenessProjection("unknown", identity_reason), None
        confirmed_identity, confirmed_reason = _runner_identity_fields(
            store, effects, supervisor, action, plan, lease)
        if confirmed_reason is not None or confirmed_identity != process_identity:
            reason = (
                "identity-mismatch"
                if confirmed_reason == "identity-mismatch"
                or confirmed_identity != process_identity
                else "identity-incomplete"
            )
            return LivenessProjection("unknown", reason), None
        reason = observation.reason
        if (observation.state is LivenessState.UNKNOWN
                and observation.heartbeat is HeartbeatFreshness.STALE
                and reason.startswith("process-observation-unavailable")):
            reason = "heartbeat-stale-process-observation-unavailable"
        return LivenessProjection(
            observation.state.value, reason, observation.heartbeat.value,
        ), process_identity
    if action.state in _ACTIVE_ACTION_STATES:
        return LivenessProjection("unknown", "positive-liveness-unavailable"), None
    return LivenessProjection("unknown", "action-not-active"), None


def _read_action(
        store: RunStore, effects: EffectEngine, supervisor: Supervisor,
        action: EntityRecord, *, stale_after: float,
) -> tuple[ActionProjection, bool]:
    plan, plan_corrupt = _read_plan(store, effects, action)
    action_kind = None if plan is None else plan.kind.value
    worktree_path = None
    if plan is not None and plan.kind is EffectKind.WORKTREE:
        value = plan.spec.get("path")
        worktree_path = value if isinstance(value, str) else None

    effect_state: str | None = None
    effect_unknown = False
    if plan is not None and action.state in _EFFECT_OBSERVATION_STATES:
        try:
            result = effects.inspect_effect(action.entity_id)
            effect_state = result.state.value
        except StateDatabaseError:
            raise
        except (CorruptRuntimeRecordError, EffectError):
            effect_unknown = True

    lease, lease_corrupt = _read_lease(store, action)
    active_claim = bool(
        action.state in _ACTIVE_ACTION_STATES
        and lease is not None
        and isinstance(lease.get("owner_token"), str)
        and lease.get("owner_token")
    )
    claimed_at = _claimed_at(lease) if active_claim and lease is not None else None
    epoch = lease.get("fencing_epoch") if lease is not None else None
    lease_epoch = epoch if isinstance(epoch, int) and not isinstance(epoch, bool) else None
    liveness, process_identity = _projection_liveness(
        store, effects, supervisor, action, plan, lease, stale_after=stale_after)
    progress_capable = (
        action.state in {"planned", "claimed"}
        or liveness.state == LivenessState.ALIVE.value
        or effect_state in {
            EffectResultState.IN_FLIGHT.value,
            EffectResultState.EXITED_UNRECONCILED.value,
        }
    )
    blocker_reason = None
    if action.state in _EFFECT_OBSERVATION_STATES:
        if effect_state == EffectResultState.UNKNOWN_EFFECT.value:
            blocker_reason = "unknown-effect"
        elif effect_state == EffectResultState.CONFLICT.value:
            blocker_reason = "effect-conflict"
        elif plan_corrupt or effect_unknown:
            blocker_reason = "effect-inspection-unknown"
    projection = ActionProjection(
        action.entity_id, action.state, action_kind, effect_state, liveness,
        active_claim, claimed_at, lease_epoch, worktree_path, process_identity,
        progress_capable, blocker_reason,
    )
    return projection, plan_corrupt or effect_unknown or lease_corrupt


def _aggregate_liveness(
        actions: tuple[ActionProjection, ...]) -> LivenessProjection:
    lanes = tuple(
        action for action in actions
        if action.state in _ACTIVE_ACTION_STATES)
    if not lanes:
        if (actions and all(action.state == "completed" for action in actions)
                and all(action.liveness.state == "exited" for action in actions)):
            return LivenessProjection("exited", "positive-action-exit")
        return LivenessProjection("unknown", "no-active-action")
    states = [lane.liveness.state for lane in lanes]
    heartbeats = [lane.liveness.heartbeat for lane in lanes]
    heartbeat = (
        HeartbeatFreshness.STALE.value
        if HeartbeatFreshness.STALE.value in heartbeats
        else HeartbeatFreshness.FRESH.value
        if HeartbeatFreshness.FRESH.value in heartbeats
        else HeartbeatFreshness.UNKNOWN.value
    )
    if LivenessState.ALIVE.value in states:
        reason = (
            "positive-liveness-with-unknown-lane"
            if LivenessState.UNKNOWN.value in states
            else "positive-action-liveness")
        return LivenessProjection("alive", reason, heartbeat)
    if all(state == LivenessState.EXITED.value for state in states):
        return LivenessProjection("exited", "positive-action-exit", heartbeat)
    reason_counts = Counter(
        lane.liveness.reason for lane in lanes if lane.liveness.state == "unknown")
    reasons = sorted(reason_counts)
    reason = reasons[0] if len(reasons) == 1 else (
        "multiple-action-liveness-unknown:"
        + ",".join(f"{item}={reason_counts[item]}" for item in reasons)
    )
    return LivenessProjection("unknown", reason, heartbeat)


def _current(actions: tuple[ActionProjection, ...]) -> CurrentProjection:
    claims = [action for action in actions if action.active_claim]
    if not claims:
        return CurrentProjection("unknown-current", "no-claimed-action", None, None)
    if len(claims) != 1:
        return CurrentProjection("unknown-current", "ambiguous-current-claims", None, None)
    action = claims[0]
    reason = None
    if action.action_kind is None:
        reason = "action-kind-unavailable"
    elif action.claimed_at is None:
        reason = "claimed-at-unavailable"
    state = "claimed" if reason is None else "unknown-current"
    return CurrentProjection(
        state, reason, action.action_kind, action.claimed_at, action.action_id,
        action.lease_epoch, action.worktree_path, action.process_identity)


def _health(
        liveness: LivenessProjection, actions: tuple[ActionProjection, ...], *, corrupt: bool,
) -> tuple[str, str]:
    if corrupt:
        return "unknown", "corrupt-runtime-record"
    if liveness.reason == "heartbeat-stale-process-observation-unavailable":
        return "unknown", liveness.reason
    unsettled = [action for action in actions if action.state != "completed"]
    if (unsettled and not any(action.progress_capable for action in unsettled)
            and all(action.blocker_reason == "unknown-effect" for action in unsettled)):
        return "stalled", "unresolved-unknown-effect-blocks-all-progress"
    if (any(action.blocker_reason == "unknown-effect" for action in unsettled)
            and any(action.progress_capable for action in unsettled)):
        return "degraded", "unknown-effect-isolated-by-progress-capable-action"
    if any(action.blocker_reason == "effect-conflict" for action in unsettled):
        return "attention_required", "effect-conflict"
    active_unknown = [
        action for action in unsettled
        if action.state in _ACTIVE_ACTION_STATES
        and action.liveness.state == "unknown"]
    if active_unknown:
        if liveness.state == "alive":
            return "degraded", "partial-liveness-unknown"
        return "unknown", liveness.reason
    return "healthy", "no-derived-health-finding"


def _unknown_snapshot(run_id: str) -> RunSnapshot:
    liveness = LivenessProjection("unknown", "corrupt-runtime-record")
    progress = ProgressProjection(
        "unknown-progress", "corrupt-runtime-record", None, None, (), ())
    current = CurrentProjection("unknown-current", "corrupt-runtime-record", None, None)
    return RunSnapshot(
        run_id, "unknown", "unknown", "corrupt-runtime-record",
        liveness, progress, current, ())


def snapshot_run(
        store: RunStore, effects: EffectEngine, supervisor: Supervisor, run_id: str, *,
        stale_after: float = 5.0) -> RunSnapshot:
    """Project one run without claiming, renewing, reconciling, repairing, or writing."""
    if not isinstance(store, RunStore):
        raise TypeError("store must be a RunStore")
    if not isinstance(effects, EffectEngine):
        raise TypeError("effects must be an EffectEngine")
    if not isinstance(supervisor, Supervisor):
        raise TypeError("supervisor must be a Supervisor")
    if effects._store is not store or supervisor._store is not store:  # noqa: SLF001
        raise ValueError("store, effects, and supervisor must share one RunStore")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    if (isinstance(stale_after, bool) or not isinstance(stale_after, (int, float))
            or not math.isfinite(stale_after) or stale_after <= 0):
        raise ValueError("stale_after must be a positive finite number")
    try:
        with _database_snapshot(store, effects) as (read_store, read_effects):
            run, jobs, action_records, graph_corrupt = _read_graph(read_store, run_id)
            if run is None:
                return _unknown_snapshot(run_id)
            progress = _read_progress(
                read_store, run_id, jobs, corrupt=graph_corrupt)
            actions: list[ActionProjection] = []
            action_corrupt = False
            for action in action_records:
                projected, corrupt = _read_action(
                    read_store, read_effects, supervisor, action,
                    stale_after=float(stale_after))
                actions.append(projected)
                action_corrupt = action_corrupt or corrupt
            action_tuple = tuple(actions)
            liveness = _aggregate_liveness(action_tuple)
            current = _current(action_tuple)
            health, health_reason = _health(
                liveness, action_tuple, corrupt=graph_corrupt or action_corrupt)
            return RunSnapshot(
                run_id, run.state, health, health_reason,
                liveness, progress, current, action_tuple)
    except StatusUnavailable:
        raise
    except (RecordNotFoundError, StateDatabaseError, sqlite3.DatabaseError) as error:
        raise StatusUnavailable(run_id, type(error).__name__) from error
    except ArtifactError as error:
        raise StatusUnavailable(run_id, error.code) from error
    except StoreError as error:
        raise StatusUnavailable(run_id, error.code) from error


def _render_counts(counts: tuple[tuple[str, int], ...]) -> str:
    return " · ".join(f"{state} {count}" for state, count in counts) or "none"


def render_human(snapshot: RunSnapshot) -> str:
    """Render a bounded count view without internal runtime identifiers."""
    if not isinstance(snapshot, RunSnapshot):
        raise TypeError("snapshot must be a RunSnapshot")
    if snapshot.progress.state == "known":
        tasks = (
            f"{snapshot.progress.completed_tasks}/{snapshot.progress.total_tasks} terminal")
    else:
        tasks = f"unknown-progress ({snapshot.progress.reason})"
    current = snapshot.current.state
    if snapshot.current.state == "claimed":
        current = f"{snapshot.current.action_kind} since {snapshot.current.claimed_at}"
    elif snapshot.current.reason is not None:
        current = f"unknown-current ({snapshot.current.reason})"
    return "\n".join((
        f"Run state: {snapshot.run_state}",
        f"Health: {snapshot.health} ({snapshot.health_reason})",
        f"Liveness: {snapshot.liveness.state} ({snapshot.liveness.reason})",
        f"Tasks: {tasks}",
        f"Jobs: {_render_counts(snapshot.progress.job_state_counts)}",
        f"Current: {current}",
    ))


def json_projection(snapshot: RunSnapshot) -> dict[str, object]:
    """Return the structured projection, including verbose internal identifiers."""
    if not isinstance(snapshot, RunSnapshot):
        raise TypeError("snapshot must be a RunSnapshot")
    return {
        "run_id": snapshot.run_id,
        "run_state": snapshot.run_state,
        "health": snapshot.health,
        "health_reason": snapshot.health_reason,
        "liveness": {
            "state": snapshot.liveness.state,
            "reason": snapshot.liveness.reason,
            "heartbeat": snapshot.liveness.heartbeat,
        },
        "progress": {
            "state": snapshot.progress.state,
            "reason": snapshot.progress.reason,
            "completed_tasks": snapshot.progress.completed_tasks,
            "total_tasks": snapshot.progress.total_tasks,
            "task_state_counts": dict(snapshot.progress.task_state_counts),
            "job_state_counts": dict(snapshot.progress.job_state_counts),
        },
        "current": {
            "state": snapshot.current.state,
            "reason": snapshot.current.reason,
            "action_kind": snapshot.current.action_kind,
            "claimed_at": snapshot.current.claimed_at,
        },
        "internal": {
            "task_id": snapshot.progress.task_id,
            "job_id": snapshot.progress.job_id,
            "current_action_id": snapshot.current.action_id,
            "actions": [
                {
                    "action_id": action.action_id,
                    "state": action.state,
                    "action_kind": action.action_kind,
                    "effect_state": action.effect_state,
                    "fencing_epoch": action.lease_epoch,
                    "liveness": {
                        "state": action.liveness.state,
                        "reason": action.liveness.reason,
                        "heartbeat": action.liveness.heartbeat,
                    },
                    "process_identity": (
                        None if action.process_identity is None
                        else dict(action.process_identity)),
                    "worktree_path": action.worktree_path,
                }
                for action in snapshot.actions
            ],
        },
    }


def watch_run(
        snapshotter: Callable[[], RunSnapshot], *, poll_interval: float = 1.0,
        sleeper: Callable[[float], None] = time.sleep) -> Iterator[str]:
    """Yield human frames by polling the exact same read-only snapshot function."""
    if not callable(snapshotter):
        raise TypeError("snapshotter must be callable")
    if not callable(sleeper):
        raise TypeError("sleeper must be callable")
    if (isinstance(poll_interval, bool) or not isinstance(poll_interval, (int, float))
            or not math.isfinite(poll_interval) or poll_interval <= 0):
        raise ValueError("poll_interval must be a positive finite number")
    first = True
    while True:
        if not first:
            sleeper(float(poll_interval))
        first = False
        yield render_human(snapshotter())


__all__ = [
    "ActionProjection",
    "CurrentProjection",
    "LivenessProjection",
    "ProgressProjection",
    "RunSnapshot",
    "StatusUnavailable",
    "json_projection",
    "render_human",
    "snapshot_run",
    "watch_run",
]
