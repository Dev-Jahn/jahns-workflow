#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Contract tests for M1-B read-only run observability."""
from __future__ import annotations

import hashlib
import itertools
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from waystone.runs import observe as observe_module, store as store_module  # noqa: E402
from waystone.runs.artifacts import ArtifactError  # noqa: E402
from waystone.runs.effects import (  # noqa: E402
    ArtifactWriteEffect,
    EffectEngine,
    EffectResult,
    EffectResultState,
    RunnerExecutionEffect,
    WorktreeEffect,
)
from waystone.runs.lease import LeaseManager  # noqa: E402
from waystone.runs.observe import (  # noqa: E402
    StatusUnavailable,
    json_projection,
    render_human,
    snapshot_run,
    watch_run,
)
from waystone.runs.spec import plan_one_task_run  # noqa: E402
from waystone.runs.store import (  # noqa: E402
    EntityKind,
    FilesystemInfo,
    RunStore,
    StateDatabaseError,
    TransitionReason,
)
from waystone.runs.supervisor import (  # noqa: E402
    HeartbeatFreshness,
    LivenessObservation,
    LivenessState,
    ProcessIdentity,
    Supervisor,
    SupervisorError,
)


class InjectedCrash(BaseException):
    """Model a crash after durable effect intent but before the external effect."""


class RunObserveTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.sandbox = Path(self._temporary_directory.name)
        self.root = self.sandbox / "project"
        self.root.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "fixture@example.com")
        self.git("config", "user.name", "Fixture")
        (self.root / ".waystone.yml").write_text(
            "version: 1\nproject: observe-fixture\n", encoding="utf-8")
        (self.root / "tasks.yaml").write_text(
            "version: 1\n"
            "project: observe-fixture\n"
            "tasks:\n"
            "  - id: feat/observe-fixture\n"
            "    title: observe one frozen task\n"
            "    status: pending\n"
            "    scope: [waystone/runs/observe.py]\n"
            "    accept:\n"
            "      - status remains read-only\n"
            "      - unknown evidence stays explicit\n",
            encoding="utf-8",
        )
        (self.root / "tracked.txt").write_text("base\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "observe fixture")
        with self.supported_filesystem():
            self.spec = plan_one_task_run("feat/observe-fixture", start=self.root)
            self.store = RunStore.open(self.root)
        self.addCleanup(self.store.close)
        self.leases = LeaseManager(self.store)
        self.effects = EffectEngine(
            self.store,
            self.leases,
            runner_executor=lambda _intent: None,
            runner_identity_verifier=lambda _marker: True,
        )
        self.supervisor = Supervisor(self.store, self.leases, invocations={})
        self._counter = 0

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    @contextmanager
    def supported_filesystem(self):
        with mock.patch.object(
                store_module, "_probe_state_filesystem",
                return_value=FilesystemInfo(
                    filesystem="apfs", mount_point=Path("/"), writable=True)):
            yield

    @staticmethod
    def sha256(payload: bytes) -> str:
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"

    def add_effect(self, effect: object, *, claim: bool = False):
        self._counter += 1
        suffix = str(self._counter)
        attempt_id = f"attempt-{suffix}"
        action_id = f"action-{suffix}"
        self.store.create_attempt(self.spec.run_id, self.spec.job_id, attempt_id)
        plan = self.effects.plan_effect(
            self.spec.run_id, self.spec.job_id, attempt_id, action_id, effect)
        claimed = self.effects.claim_effect(plan, ttl_seconds=30) if claim else None
        return plan, claimed

    def crash_after_intent(self, claimed) -> None:
        def fault(stage, _plan):
            if stage == "after-effect-intent":
                raise InjectedCrash()

        with mock.patch.object(self.effects, "_effect_fault_point", side_effect=fault):
            with self.assertRaises(InjectedCrash):
                self.effects.execute_effect(claimed)

    def runner_runtime_payload(
            self, plan, claimed, *, process_pid: int = 991234,
    ) -> dict[str, object]:
        action = self.store.get_entity(EntityKind.ACTION, plan.action_id)
        self.assertEqual(action.state, "effect")
        intent = self.effects._load_intent(plan)  # noqa: SLF001
        process_identity = ProcessIdentity(
            host_boot_identity="internal-boot-sentinel",
            pid=process_pid,
            process_start_token=f"internal-start-token-{process_pid}",
            action_id=plan.action_id,
            supervisor_owner_token=claimed.principal.owner_token,
            fencing_epoch=claimed.principal.fencing_epoch,
            invocation_digest=plan.spec["invocation_digest"],
        )
        supervisor_identity = ProcessIdentity(
            host_boot_identity="internal-boot-sentinel",
            pid=process_pid + 1,
            process_start_token=f"internal-supervisor-start-token-{process_pid}",
            action_id=plan.action_id,
            supervisor_owner_token=claimed.principal.owner_token,
            fencing_epoch=claimed.principal.fencing_epoch,
            resolved_executable=sys.executable,
        )
        return {
            "schema": "waystone-supervisor-runtime-1",
            "run_id": self.spec.run_id,
            "job_id": self.spec.job_id,
            "action_id": plan.action_id,
            "owner_token": claimed.principal.owner_token,
            "fencing_epoch": claimed.principal.fencing_epoch,
            "entity_version": action.version,
            "invocation_digest": plan.spec["invocation_digest"],
            "launch_token": intent["launch_token"],
            "started_at": "2026-07-21T00:00:00Z",
            "supervisor_identity": supervisor_identity.to_payload(),
            "process_identity": process_identity.to_payload(),
        }

    def publish_runner_runtime(self, action_id: str, payload: dict[str, object]) -> None:
        runtime_path = self.supervisor._runtime_path(action_id)  # noqa: SLF001
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path.write_text(
            json.dumps(payload, sort_keys=True), encoding="utf-8")

    def delete_artifact_reference(self, reference_id: str) -> None:
        external = sqlite3.connect(self.store.database_path)
        try:
            external.execute("DROP TRIGGER artifacts_no_delete")
            external.execute(
                "DELETE FROM artifacts WHERE reference_id = ?", (reference_id,))
            external.commit()
        finally:
            external.close()

    def snapshot(self):
        return snapshot_run(
            self.store, self.effects, self.supervisor, self.spec.run_id,
            stale_after=1.0)

    def persisted_state(self) -> dict[str, object]:
        rows: dict[str, object] = {}
        for table, order in (
                ("runs", "run_id"),
                ("jobs", "job_id"),
                ("attempts", "attempt_id"),
                ("actions", "action_id"),
                ("leases", "lease_id"),
                ("action_runtime", "action_id"),
                ("transitions", "transition_id"),
                ("artifacts", "reference_id"),
                ("cache", "cache_key")):
            rows[table] = [
                tuple(row) for row in self.store._connection.execute(  # noqa: SLF001
                    f"SELECT * FROM {table} ORDER BY {order}").fetchall()
            ]
        for path in (
                self.store.database_path,
                Path(str(self.store.database_path) + "-wal")):
            rows[f"bytes:{path.name}"] = path.read_bytes() if path.exists() else None
        supervisor_directory = self.root / ".waystone" / "supervisors"
        rows["supervisor-evidence"] = {
            str(path.relative_to(supervisor_directory)): path.read_bytes()
            for path in sorted(supervisor_directory.rglob("*"))
            if path.is_file()
        } if supervisor_directory.exists() else {}
        return rows

    def test_status_and_watch_repeated_polls_leave_store_and_evidence_byte_identical(
            self):
        """Fixture 1: polling leaves version, lease, heartbeat, transition unchanged."""
        _plan, claimed = self.add_effect(ArtifactWriteEffect(b"read-only"), claim=True)
        self.leases.renew(claimed.principal, ttl_seconds=30)
        _uncertain_plan, uncertain_claim = self.add_effect(
            ArtifactWriteEffect(b"inspect-read-only"), claim=True)
        self.crash_after_intent(uncertain_claim)
        self.add_effect(
            RunnerExecutionEffect(self.sha256(b"probe-read-only")), claim=True)
        evidence = self.root / ".waystone" / "supervisors" / "sentinel.heartbeat.json"
        evidence.parent.mkdir(parents=True)
        evidence.write_bytes(b"immutable-heartbeat-evidence")
        before = self.persisted_state()

        with mock.patch.object(
                RunStore, "open", side_effect=AssertionError("status must not open or migrate")):
            for _ in range(30):
                observed = self.snapshot()
                render_human(observed)
                json_projection(observed)
            frames = list(itertools.islice(watch_run(
                self.snapshot, poll_interval=0.01, sleeper=lambda _delay: None), 30))

        self.assertEqual(len(frames), 30)
        self.assertIn(
            "unknown-effect",
            {action.effect_state for action in observed.actions},
        )
        self.assertIn(
            "identity-incomplete",
            {action.liveness.reason for action in observed.actions},
        )
        self.assertEqual(self.persisted_state(), before)

    def test_stale_heartbeat_and_unobservable_process_keep_health_unknown_and_state_authoritative(
            self):
        """Fixture 2: stale heartbeat + unobservable process keeps state authoritative."""
        plan, claimed = self.add_effect(
            RunnerExecutionEffect(self.sha256(b"runner-current")), claim=True)
        self.crash_after_intent(claimed)
        self.publish_runner_runtime(
            plan.action_id, self.runner_runtime_payload(plan, claimed))
        run = self.store.get_entity(EntityKind.RUN, self.spec.run_id)
        self.store.record_transition(
            EntityKind.RUN,
            run.entity_id,
            expected_version=run.version,
            next_state="running",
            reason=TransitionReason.PROCESS_STARTED,
        )
        observation = LivenessObservation(
            LivenessState.UNKNOWN,
            "process-observation-unavailable:OSError",
            False,
            HeartbeatFreshness.STALE,
        )
        with mock.patch.object(
                self.supervisor, "probe_action", return_value=observation):
            snapshot = self.snapshot()

        self.assertEqual(snapshot.run_state, "running")
        self.assertEqual(snapshot.liveness.state, "unknown")
        self.assertEqual(
            snapshot.liveness.reason,
            "heartbeat-stale-process-observation-unavailable",
        )
        self.assertEqual(snapshot.health, "unknown")
        self.assertEqual(
            snapshot.health_reason,
            "heartbeat-stale-process-observation-unavailable",
        )

    def test_progress_capable_action_prevents_stalled_with_unknown_effect_lane(self):
        """Fixture 3a: a progress-capable action keeps one unknown lane from stalling the run."""
        _plan, claimed = self.add_effect(ArtifactWriteEffect(b"uncertain"), claim=True)
        self.crash_after_intent(claimed)
        self.add_effect(ArtifactWriteEffect(b"still-progressable"))

        snapshot = self.snapshot()

        self.assertNotEqual(snapshot.health, "stalled")
        self.assertEqual(snapshot.health, "degraded")

    def test_only_unresolved_unknown_effect_is_derived_stalled_not_a_run_state(self):
        """Fixture 3b: only unresolved unknown-effect with no progress action derives stalled."""
        _plan, claimed = self.add_effect(ArtifactWriteEffect(b"uncertain"), claim=True)
        self.crash_after_intent(claimed)
        before = self.store.get_entity(EntityKind.RUN, self.spec.run_id)

        snapshot = self.snapshot()

        self.assertEqual(snapshot.health, "stalled")
        self.assertEqual(snapshot.health_reason, "unresolved-unknown-effect-blocks-all-progress")
        self.assertEqual(snapshot.run_state, before.state)
        self.assertEqual(self.store.get_entity(EntityKind.RUN, self.spec.run_id), before)

    def test_database_read_failure_raises_typed_status_unavailable(self):
        """Fixture 4: an injected database read failure raises typed status-unavailable."""
        self.store.close()

        with self.assertRaises(StatusUnavailable) as raised:
            self.snapshot()

        self.assertEqual(raised.exception.code, "status-unavailable")
        self.assertIsInstance(raised.exception.__cause__, StateDatabaseError)

    def test_projection_setup_failure_raises_typed_status_unavailable(self):
        """Fixture 4: a read-side artifact setup failure is typed status-unavailable."""
        (self.root / ".waystone.yml").unlink()

        with self.assertRaises(StatusUnavailable) as raised:
            self.snapshot()

        self.assertEqual(raised.exception.code, "status-unavailable")
        self.assertIsInstance(raised.exception.__cause__, ArtifactError)

    def test_current_claim_reports_kind_and_proven_time_else_unknown_current(self):
        """Fixture 5: claimed action has kind+time; no claim is unknown-current."""
        empty = self.snapshot()
        self.assertEqual(empty.current.state, "unknown-current")
        self.assertEqual(empty.current.reason, "no-claimed-action")

        _plan, claimed = self.add_effect(ArtifactWriteEffect(b"current"), claim=True)
        current = self.snapshot()
        self.assertEqual(current.current.state, "claimed")
        self.assertEqual(current.current.action_kind, "artifact-write")
        self.assertIsNotNone(current.current.claimed_at)

        renewed_principal = self.leases.renew(claimed.principal, ttl_seconds=30)
        renewed = self.snapshot()
        self.assertEqual(renewed.current.state, "unknown-current")
        self.assertEqual(renewed.current.reason, "claimed-at-unavailable")
        self.assertEqual(renewed.current.action_kind, "artifact-write")

        self.effects.execute_effect(replace(claimed, principal=renewed_principal))
        completed = self.snapshot()
        self.assertEqual(completed.current.state, "unknown-current")
        self.assertEqual(completed.current.reason, "no-claimed-action")
        self.assertEqual(completed.liveness.state, "exited")
        self.assertEqual(completed.liveness.reason, "positive-action-exit")

    def test_terminal_run_state_without_action_exit_evidence_has_unknown_liveness(self):
        """Three-way split: terminal FSM state alone cannot prove liveness exit."""
        run = self.store.get_entity(EntityKind.RUN, self.spec.run_id)
        self.store.record_transition(
            EntityKind.RUN,
            run.entity_id,
            expected_version=run.version,
            next_state="completed",
            reason=TransitionReason.COMPLETED,
        )

        snapshot = self.snapshot()

        self.assertEqual(snapshot.run_state, "completed")
        self.assertEqual(snapshot.liveness.state, "unknown")
        self.assertEqual(snapshot.liveness.reason, "no-active-action")

    def test_positive_lane_with_unknown_lane_is_alive_but_derived_degraded(self):
        """Liveness aggregation preserves a positive lane and degrades a partial unknown."""
        first, first_claim = self.add_effect(
            RunnerExecutionEffect(self.sha256(b"alive-lane")), claim=True)
        self.crash_after_intent(first_claim)
        self.publish_runner_runtime(
            first.action_id, self.runner_runtime_payload(first, first_claim))
        second, _second_claim = self.add_effect(
            RunnerExecutionEffect(self.sha256(b"unknown-lane")), claim=True)
        observations = {
            first.action_id: LivenessObservation(
                LivenessState.ALIVE,
                "process-identity-matched",
                False,
                HeartbeatFreshness.FRESH,
            ),
            second.action_id: LivenessObservation(
                LivenessState.UNKNOWN,
                "process-observation-unavailable:OSError",
                False,
                HeartbeatFreshness.UNKNOWN,
            ),
        }
        with mock.patch.object(
                self.supervisor, "probe_action",
                side_effect=lambda action_id, **_kwargs: observations[action_id]):
            snapshot = self.snapshot()

        self.assertEqual(snapshot.liveness.state, "alive")
        self.assertEqual(snapshot.health, "degraded")

    def test_live_runner_with_unreconciled_effect_is_not_stalled(self):
        """Derived health: positive runner liveness remains progress-capable."""
        plan, claimed = self.add_effect(
            RunnerExecutionEffect(self.sha256(b"live-unreconciled")), claim=True)
        self.crash_after_intent(claimed)
        self.publish_runner_runtime(
            plan.action_id, self.runner_runtime_payload(plan, claimed))
        with mock.patch.object(
                self.supervisor, "probe_action",
                return_value=LivenessObservation(
                    LivenessState.ALIVE,
                    "process-identity-matched",
                    False,
                    HeartbeatFreshness.FRESH,
                )):
            snapshot = self.snapshot()

        self.assertEqual(snapshot.liveness.state, "alive")
        self.assertEqual(snapshot.actions[0].effect_state, "unknown-effect")
        self.assertTrue(snapshot.actions[0].progress_capable)
        self.assertNotEqual(snapshot.health, "stalled")

    def test_non_runner_effect_observation_does_not_invent_liveness(self):
        """Three-way split: effect progress cannot replace supervisor liveness evidence."""
        plan, claimed = self.add_effect(
            ArtifactWriteEffect(b"in-flight-is-not-liveness"), claim=True)
        self.crash_after_intent(claimed)
        with mock.patch.object(
                EffectEngine,
                "inspect_effect",
                return_value=EffectResult(
                    plan.action_id, EffectResultState.IN_FLIGHT),
        ):
            snapshot = self.snapshot()

        self.assertEqual(snapshot.actions[0].effect_state, "in-flight")
        self.assertTrue(snapshot.actions[0].progress_capable)
        self.assertEqual(snapshot.actions[0].liveness.state, "unknown")
        self.assertEqual(
            snapshot.actions[0].liveness.reason,
            "positive-liveness-unavailable",
        )

    def test_human_render_hides_internal_identifiers_while_json_includes_them(self):
        """Fixture 6: human hides path/action/fence/process identity; JSON includes them."""
        action_id = "internal-worktree-action-sentinel"
        self._counter += 1
        attempt_id = f"attempt-{self._counter}"
        self.store.create_attempt(self.spec.run_id, self.spec.job_id, attempt_id)
        worktree = self.sandbox / "internal-worktree-sentinel"
        plan = self.effects.plan_effect(
            self.spec.run_id,
            self.spec.job_id,
            attempt_id,
            action_id,
            WorktreeEffect(
                self.root,
                worktree,
                "refs/heads/internal-observe-fixture",
                self.git("rev-parse", "HEAD"),
            ),
        )
        self.effects.claim_effect(plan, ttl_seconds=30)
        runner_plan, runner_claimed = self.add_effect(
            RunnerExecutionEffect(self.sha256(b"identity-json")), claim=True)
        self.crash_after_intent(runner_claimed)
        self.publish_runner_runtime(
            runner_plan.action_id,
            self.runner_runtime_payload(runner_plan, runner_claimed),
        )
        with mock.patch.object(
                self.supervisor, "probe_action",
                return_value=LivenessObservation(
                    LivenessState.UNKNOWN, "identity-mismatch")):
            snapshot = self.snapshot()

        human = render_human(snapshot)
        structured = json_projection(snapshot)
        encoded = json.dumps(structured, sort_keys=True)

        for hidden in (
                action_id, runner_plan.action_id, str(worktree.resolve()), "991234",
                runner_claimed.principal.owner_token):
            self.assertNotIn(hidden, human)
            self.assertIn(hidden, encoded)
        self.assertNotIn("%", human)
        actions = {
            action["action_id"]: action
            for action in structured["internal"]["actions"]
        }
        self.assertEqual(actions[action_id]["worktree_path"], str(worktree.resolve()))
        self.assertEqual(actions[action_id]["fencing_epoch"], 1)
        self.assertEqual(actions[runner_plan.action_id]["process_identity"]["pid"], 991234)

    def test_foreign_runtime_identity_cannot_supply_positive_liveness(self):
        """E-08: a positive probe is unknown when runtime identity is not action-bound."""
        plan, claimed = self.add_effect(
            RunnerExecutionEffect(self.sha256(b"foreign-runtime")), claim=True)
        self.crash_after_intent(claimed)
        payload = self.runner_runtime_payload(plan, claimed)
        process_identity = payload["process_identity"]
        self.assertIsInstance(process_identity, dict)
        process_identity["action_id"] = "foreign-action-identity"
        self.publish_runner_runtime(plan.action_id, payload)

        with mock.patch.object(
                self.supervisor, "probe_action",
                return_value=LivenessObservation(
                    LivenessState.ALIVE,
                    "process-identity-matched",
                    False,
                    HeartbeatFreshness.FRESH,
                )):
            snapshot = self.snapshot()

        self.assertEqual(snapshot.liveness.state, "unknown")
        self.assertEqual(snapshot.liveness.reason, "identity-mismatch")
        self.assertIn("identity-mismatch", render_human(snapshot))
        action = json_projection(snapshot)["internal"]["actions"][0]
        self.assertEqual(action["liveness"]["reason"], "identity-mismatch")
        self.assertIsNone(action["process_identity"])
        self.assertNotIn("foreign-action-identity", json.dumps(json_projection(snapshot)))

    def test_runtime_identity_change_during_probe_cannot_supply_liveness(self):
        """E-08: positive liveness is refused if runtime binding changes during probe."""
        plan, claimed = self.add_effect(
            RunnerExecutionEffect(self.sha256(b"runtime-race")), claim=True)
        self.crash_after_intent(claimed)
        payload = self.runner_runtime_payload(plan, claimed)
        self.publish_runner_runtime(plan.action_id, payload)

        def replace_runtime(_action_id, **_kwargs):
            replaced = json.loads(json.dumps(payload))
            replaced["process_identity"]["action_id"] = "foreign-race-action"
            self.publish_runner_runtime(plan.action_id, replaced)
            return LivenessObservation(
                LivenessState.ALIVE,
                "process-identity-matched",
                False,
                HeartbeatFreshness.FRESH,
            )

        with mock.patch.object(
                self.supervisor, "probe_action", side_effect=replace_runtime):
            snapshot = self.snapshot()

        self.assertEqual(snapshot.liveness.state, "unknown")
        self.assertEqual(snapshot.liveness.reason, "identity-mismatch")
        action = json_projection(snapshot)["internal"]["actions"][0]
        self.assertEqual(action["liveness"]["reason"], "identity-mismatch")
        self.assertIsNone(action["process_identity"])

    def test_supervisor_observation_failure_is_reasoned_unknown(self):
        """E-08: a typed process-observation failure projects unknown instead of escaping."""
        plan, claimed = self.add_effect(
            RunnerExecutionEffect(self.sha256(b"observation-failure")), claim=True)
        self.crash_after_intent(claimed)
        self.publish_runner_runtime(
            plan.action_id, self.runner_runtime_payload(plan, claimed))

        with mock.patch.object(
                self.supervisor, "probe_action",
                side_effect=SupervisorError("host observation unavailable")):
            snapshot = self.snapshot()

        expected = "process-observation-unavailable:supervisor_error"
        self.assertEqual(snapshot.liveness.state, "unknown")
        self.assertEqual(snapshot.liveness.reason, expected)
        action = json_projection(snapshot)["internal"]["actions"][0]
        self.assertEqual(action["liveness"]["reason"], expected)

    def test_malformed_active_lease_is_corrupt_not_current(self):
        """PC-19: an active owner with epoch zero is corrupt, never a current claim."""
        plan, _claimed = self.add_effect(ArtifactWriteEffect(b"bad-lease"), claim=True)
        self.store._connection.execute(  # noqa: SLF001
            "UPDATE leases SET fencing_epoch = 0 WHERE lease_id = ?",
            (plan.action_id,),
        )

        snapshot = self.snapshot()

        self.assertEqual(snapshot.health, "unknown")
        self.assertEqual(snapshot.health_reason, "corrupt-runtime-record")
        self.assertEqual(snapshot.current.state, "unknown-current")
        action = json_projection(snapshot)["internal"]["actions"][0]
        self.assertIsNone(action["fencing_epoch"])

    def test_active_action_with_missing_lease_is_corrupt_not_healthy(self):
        """PC-19: a missing required active lease is corrupt, never healthy progress."""
        plan, _claimed = self.add_effect(
            ArtifactWriteEffect(b"missing-lease"), claim=True)
        self.store._connection.execute(  # noqa: SLF001
            "DELETE FROM leases WHERE lease_id = ?", (plan.action_id,))

        snapshot = self.snapshot()

        self.assertEqual(snapshot.health, "unknown")
        self.assertEqual(snapshot.health_reason, "corrupt-runtime-record")
        self.assertEqual(snapshot.current.state, "unknown-current")

    def test_missing_effect_plan_reference_is_corrupt_not_healthy(self):
        """PC-19: missing immutable action input is corrupt, never healthy progress."""
        plan, _claimed = self.add_effect(ArtifactWriteEffect(b"missing-plan"))
        self.delete_artifact_reference(f"effect-plan:{plan.action_id}")

        snapshot = self.snapshot()

        self.assertEqual(snapshot.actions[0].state, "planned")
        self.assertIsNone(snapshot.actions[0].action_kind)
        self.assertEqual(snapshot.health, "unknown")
        self.assertEqual(snapshot.health_reason, "corrupt-runtime-record")

    def test_completed_action_with_missing_plan_cannot_supply_positive_exit(self):
        """PC-19/E-08: corrupt completed input cannot become positive exit evidence."""
        plan, claimed = self.add_effect(
            ArtifactWriteEffect(b"completed-missing-plan"), claim=True)
        self.effects.execute_effect(claimed)
        self.delete_artifact_reference(f"effect-plan:{plan.action_id}")

        snapshot = self.snapshot()

        self.assertEqual(snapshot.actions[0].state, "completed")
        self.assertEqual(snapshot.actions[0].liveness.state, "unknown")
        self.assertEqual(
            snapshot.actions[0].liveness.reason,
            "positive-exit-evidence-unavailable",
        )
        self.assertEqual(snapshot.liveness.state, "unknown")
        self.assertEqual(snapshot.health_reason, "corrupt-runtime-record")

    def test_released_active_lease_is_unowned_reasoned_unknown(self):
        """Released lease rows remain valid but cannot imply current or healthy liveness."""
        _plan, claimed = self.add_effect(
            ArtifactWriteEffect(b"released-lease"), claim=True)
        self.leases.release(claimed.principal)

        snapshot = self.snapshot()

        self.assertEqual(snapshot.current.state, "unknown-current")
        self.assertEqual(snapshot.current.reason, "no-claimed-action")
        self.assertEqual(snapshot.liveness.state, "unknown")
        self.assertEqual(snapshot.health, "unknown")
        self.assertNotEqual(snapshot.health_reason, "corrupt-runtime-record")

    def test_projection_uses_one_coherent_database_read_point(self):
        """Read-only projection cannot mix action and lease versions across transitions."""
        plan, _claimed = self.add_effect(ArtifactWriteEffect(b"snapshot-race"))
        read_graph = observe_module._read_graph  # noqa: SLF001

        def claim_after_snapshot(read_store, run_id):
            self.effects.claim_effect(plan, ttl_seconds=30)
            return read_graph(read_store, run_id)

        with mock.patch.object(
                observe_module, "_read_graph", side_effect=claim_after_snapshot):
            snapshot = self.snapshot()

        self.assertEqual(snapshot.actions[0].state, "planned")
        self.assertNotEqual(snapshot.health_reason, "corrupt-runtime-record")
        self.assertEqual(
            self.store.get_entity(EntityKind.ACTION, plan.action_id).state,
            "claimed",
        )
        self.assertEqual(self.snapshot().actions[0].state, "claimed")

    def test_progress_uses_one_frozen_task_instead_of_dynamic_action_count(self):
        """Three-way split: progress denominator is frozen closure, never dynamic actions."""
        for number in range(5):
            self.add_effect(ArtifactWriteEffect(f"action-{number}".encode("utf-8")))

        snapshot = self.snapshot()

        self.assertEqual(snapshot.progress.state, "known")
        self.assertEqual(snapshot.progress.completed_tasks, 0)
        self.assertEqual(snapshot.progress.total_tasks, 1)
        self.assertIn("Tasks: 0/1 terminal", render_human(snapshot))

    def test_corrupt_run_is_unknown_without_interrupting_healthy_run_projection(self):
        """PC-19: corrupt record is local unknown and never stops a healthy run projection."""
        healthy = self.store.create_run(initial_state="healthy-authoritative")
        self.store.create_job(healthy.entity_id, "healthy-job", initial_state="planned")
        foreign = self.store.create_run(initial_state="foreign-authoritative")
        self.store.create_job(foreign.entity_id, "foreign-job", initial_state="planned")
        external = sqlite3.connect(self.store.database_path)
        self.addCleanup(external.close)
        external.execute("PRAGMA foreign_keys=OFF")
        external.execute("DROP TRIGGER jobs_identity_no_update")
        external.execute(
            "UPDATE jobs SET state = 'forged-valid-looking-state' WHERE job_id = ?",
            (self.spec.job_id,),
        )
        external.execute(
            "UPDATE jobs SET run_id = ? WHERE job_id = 'foreign-job'",
            (healthy.entity_id,),
        )
        external.commit()

        corrupt = self.snapshot()
        healthy_snapshot = snapshot_run(
            self.store, self.effects, self.supervisor, healthy.entity_id)

        self.assertEqual(corrupt.run_state, "frozen-ready")
        self.assertEqual(corrupt.progress.state, "unknown-progress")
        self.assertEqual(corrupt.health, "unknown")
        self.assertEqual(healthy_snapshot.run_state, "healthy-authoritative")
        self.assertEqual(healthy_snapshot.progress.state, "unknown-progress")
        self.assertNotEqual(healthy_snapshot.health_reason, "corrupt-runtime-record")


if __name__ == "__main__":
    unittest.main(verbosity=2)
