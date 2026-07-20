#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Contract tests for M1-B detached supervision and process identity."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
_WAYSTONE_PRELOADED = "waystone" in sys.modules
sys.path.insert(0, str(ROOT))
try:
    from waystone.runs import supervisor as supervisor_module  # noqa: E402
    from waystone.runs.artifacts import ArtifactStore  # noqa: E402
    from waystone.runs.effects import (  # noqa: E402
        ClaimedEffect,
        EffectEngine,
        EffectResultState,
        RunnerCompletionMarker,
        RunnerExecutionEffect,
        publish_runner_completion,
    )
    from waystone.runs.lease import (  # noqa: E402
        LeaseManager,
        LeasePrincipalMismatch,
    )
    from waystone.runs.store import EntityKind, RunStore  # noqa: E402
    from waystone.runs.supervisor import (  # noqa: E402
        CompletionMarkerRefused,
        HeartbeatFreshness,
        LivenessState,
        ProcessIdentity,
        RunnerInvocation,
        Supervisor,
        SupervisorAlreadyStarted,
        SupervisorHeartbeat,
        SupervisorLaunchRefused,
        capture_process_identity,
        heartbeat_freshness,
        host_boot_identity,
        observe_process_identity,
        process_start_token,
    )
finally:
    sys.path.pop(0)
    if not _WAYSTONE_PRELOADED:
        sys.modules.pop("waystone", None)
del _WAYSTONE_PRELOADED


class RunSupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.sandbox = Path(self._temporary_directory.name)
        self.root = self.sandbox / "project"
        self.root.mkdir()
        (self.root / ".waystone.yml").write_text(
            "version: 1\nproject: supervisor-fixture\n", encoding="utf-8")
        self.store = RunStore.open(self.root)
        self.addCleanup(self.store.close)
        self.leases = LeaseManager(self.store)
        self.run = self.store.create_run()
        self.store.create_job(self.run.entity_id, "job")
        self._counter = 0

    @staticmethod
    def sha256(payload: bytes) -> str:
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"

    @staticmethod
    def wait_for(predicate, *, timeout: float = 10.0, interval: float = 0.02) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(interval)
        raise AssertionError("timed out waiting for supervisor fixture")

    @staticmethod
    def marker_from(path: Path) -> RunnerCompletionMarker:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return RunnerCompletionMarker(
            run_id=payload["run_id"],
            job_id=payload["job_id"],
            action_id=payload["action_id"],
            fencing_epoch=payload["fencing_epoch"],
            launch_token=payload["launch_token"],
            process_identity=payload["process_identity"],
            started_at=payload["started_at"],
            finished_at=payload["finished_at"],
            returncode=payload["returncode"],
            signal=payload["signal"],
            stdout_artifact_digest=payload["stdout_artifact_digest"],
            stderr_artifact_digest=payload["stderr_artifact_digest"],
        )

    def make_case(
            self, *, worker_source: str, prefix: str,
            executor_wrapper=None, heartbeat_interval: float = 0.05):
        self._counter += 1
        suffix = f"{prefix}-{self._counter}"
        attempt_id = f"attempt-{suffix}"
        action_id = f"action-{suffix}"
        digest = self.sha256(f"invocation-{suffix}".encode("utf-8"))
        invocation = RunnerInvocation(
            (sys.executable, "-c", worker_source), self.root)
        supervisor = Supervisor(
            self.store, self.leases,
            invocations={digest: invocation},
            heartbeat_interval=heartbeat_interval,
            lease_ttl=max(heartbeat_interval * 4, 0.25),
        )
        captured = []

        def executor(intent):
            captured.append(intent)
            if executor_wrapper is None:
                supervisor.runner_executor(intent)
            else:
                executor_wrapper(supervisor, intent)

        engine = EffectEngine(
            self.store, self.leases,
            runner_executor=executor,
            runner_identity_verifier=supervisor.runner_identity_verifier,
        )
        self.store.create_attempt(self.run.entity_id, "job", attempt_id)
        plan = engine.plan_effect(
            self.run.entity_id, "job", attempt_id, action_id,
            RunnerExecutionEffect(digest),
        )
        claimed = engine.claim_effect(plan, ttl_seconds=5)
        return engine, supervisor, plan, claimed, captured, invocation

    def test_fixture_1_stale_heartbeat_matching_live_child_is_not_exited_or_quiescent(self):
        """§6 fixture 1: stale heartbeat + matching live child forbids cleanup."""
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(lambda: process.poll() is not None or process.wait(timeout=5))
        self.addCleanup(lambda: process.poll() is None and process.terminate())
        identity = capture_process_identity(
            process.pid,
            action_id="fixture-1",
            owner_token="owner-fixture-1",
            fencing_epoch=1,
            resolved_executable=str(Path(sys.executable).resolve()),
        )
        heartbeat = SupervisorHeartbeat(
            action_id=identity.action_id,
            fencing_epoch=identity.fencing_epoch,
            host_boot_identity=identity.host_boot_identity,
            monotonic_observed_at=time.monotonic() - 100,
            wall_observed_at="2026-07-21T00:00:00Z",
            process_identity=identity,
        )
        freshness = heartbeat_freshness(heartbeat, stale_after=1)
        observation = observe_process_identity(identity, heartbeat=freshness)

        self.assertEqual(freshness, HeartbeatFreshness.STALE)
        self.assertEqual(observation.state, LivenessState.ALIVE)
        self.assertEqual(observation.reason, "process-identity-matched")
        self.assertFalse(observation.exact_identity_absent)
        self.assertFalse(observation.destructive_resolution_allowed)

    def test_fixture_2_pid_reuse_and_boot_mismatch_are_unknown_identity_mismatch(self):
        """§6 fixture 2: PID reuse/boot mismatch stays unknown, never alive/exited."""
        actual_token = process_start_token(os.getpid())
        identity = ProcessIdentity(
            host_boot_identity=host_boot_identity(),
            pid=os.getpid(),
            process_start_token="different-start-token",
            action_id="fixture-2",
            supervisor_owner_token="owner-fixture-2",
            fencing_epoch=2,
            resolved_executable=str(Path(sys.executable).resolve()),
        )
        reused = observe_process_identity(
            identity, start_token_reader=lambda _pid: actual_token)
        rebooted = observe_process_identity(
            replace(identity, process_start_token=actual_token),
            current_boot_identity="different-boot-identity",
        )

        for observation in (reused, rebooted):
            with self.subTest(reason=observation.reason):
                self.assertEqual(observation.state, LivenessState.UNKNOWN)
                self.assertEqual(observation.reason, "identity-mismatch")
                self.assertTrue(observation.exact_identity_absent)
                self.assertFalse(observation.destructive_resolution_allowed)

    def test_spawn_revalidates_principal_inside_callback_and_refuses_before_popen(self):
        failures = []

        def stale_executor(supervisor, intent):
            try:
                supervisor.launch(replace(intent, owner_token="stale-owner"))
            except LeasePrincipalMismatch as error:
                failures.append(error)
                raise

        engine, supervisor, _plan, claimed, _captured, _invocation = self.make_case(
            worker_source="print('must not run')",
            prefix="spawn-guard",
            executor_wrapper=stale_executor,
        )
        with mock.patch.object(supervisor_module.subprocess, "Popen") as popen:
            result = engine.execute_effect(claimed)

        self.assertEqual(result.state, EffectResultState.UNKNOWN_EFFECT)
        popen.assert_not_called()
        self.assertFalse(supervisor._launch_path(claimed.plan.action_id).exists())  # noqa: SLF001
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].code, "lease_principal_mismatch")

    def test_detached_supervisor_survives_launcher_parent_death_and_publishes_marker(self):
        """D6/S2 fixture: launcher exits while detached supervisor still writes marker."""
        action_id = "action-detached-parent-death"
        attempt_id = "attempt-detached-parent-death"
        digest = self.sha256(b"detached-parent-death")
        worker_gate = self.root / "release-detached-worker"
        worker_source = (
            "import pathlib,sys,time\n"
            f"gate=pathlib.Path({str(worker_gate)!r})\n"
            "while not gate.exists():\n"
            "    time.sleep(0.02)\n"
            "sys.stdout.buffer.write(b'detached-stdout')\n"
            "sys.stderr.buffer.write(b'detached-stderr')\n"
        )
        invocation = RunnerInvocation(
            (sys.executable, "-c", worker_source), self.root)
        planner = EffectEngine(self.store, self.leases)
        self.store.create_attempt(self.run.entity_id, "job", attempt_id)
        plan = planner.plan_effect(
            self.run.entity_id, "job", attempt_id, action_id,
            RunnerExecutionEffect(digest),
        )
        planner.claim_effect(plan, ttl_seconds=5)
        self.store.close()

        launcher = f"""
import os, sys
from pathlib import Path
from waystone.runs.effects import ClaimedEffect, EffectEngine
from waystone.runs.lease import LeaseManager
from waystone.runs.store import EntityKind, RunStore
from waystone.runs.supervisor import RunnerInvocation, Supervisor
root = Path({str(self.root)!r})
store = RunStore.open(root)
leases = LeaseManager(store)
invocation = RunnerInvocation({invocation.argv!r}, root)
supervisor = Supervisor(store, leases, invocations={{{digest!r}: invocation}}, heartbeat_interval=0.05, lease_ttl=0.25)
engine = EffectEngine(store, leases, runner_executor=supervisor.runner_executor, runner_identity_verifier=supervisor.runner_identity_verifier)
plan = engine._load_plan({action_id!r})
action = store.get_entity(EntityKind.ACTION, {action_id!r})
principal = engine._current_principal(action)
engine.execute_effect(ClaimedEffect(plan, principal))
store.close()
os._exit(0)
"""
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(ROOT), environment.get("PYTHONPATH", "")])
        completed = subprocess.run(
            [sys.executable, "-c", launcher],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        marker_path = (
            self.root / ".waystone" / "runner-completions"
            / (hashlib.sha256(action_id.encode()).hexdigest() + ".json")
        )
        self.assertFalse(marker_path.exists(), "gated worker must outlive launcher")

        with RunStore.open(self.root) as observing_store:
            transition_count = observing_store._connection.execute(  # noqa: SLF001
                "SELECT COUNT(*) FROM transitions WHERE entity_kind = ? AND entity_id = ?",
                (EntityKind.ACTION.value, action_id),
            ).fetchone()[0]
        worker_gate.write_text("release\n", encoding="utf-8")
        self.wait_for(marker_path.is_file)

        reopened = RunStore.open(self.root)
        self.addCleanup(reopened.close)
        self.store = reopened
        self.leases = LeaseManager(reopened)
        supervisor = Supervisor(
            reopened, self.leases, invocations={digest: invocation},
            heartbeat_interval=0.05, lease_ttl=0.25,
        )
        marker = self.marker_from(marker_path)
        supervisor.validate_completion_marker(marker)
        artifacts = ArtifactStore(self.root)
        self.assertEqual(
            artifacts.read(marker.stdout_artifact_digest), b"detached-stdout")
        self.assertEqual(
            artifacts.read(marker.stderr_artifact_digest), b"detached-stderr")
        self.assertIsNotNone(marker.returncode)
        self.assertIsNone(marker.signal)
        self.assertEqual(marker.returncode, 0)
        after_heartbeat_count = reopened._connection.execute(  # noqa: SLF001
            "SELECT COUNT(*) FROM transitions WHERE entity_kind = ? AND entity_id = ?",
            (EntityKind.ACTION.value, action_id),
        ).fetchone()[0]
        self.assertEqual(after_heartbeat_count, transition_count)

        engine = EffectEngine(
            reopened, self.leases,
            runner_executor=supervisor.runner_executor,
            runner_identity_verifier=supervisor.runner_identity_verifier,
        )
        result = engine.reconcile_actions(
            [action_id], quiescence_probe=supervisor.quiescence_probe)
        self.assertEqual(result[0].state, EffectResultState.COMPLETED)
        observation = supervisor.probe_action(action_id)
        self.assertEqual(observation.state, LivenessState.EXITED)
        self.assertEqual(observation.reason, "supervisor-wait-status")

    def test_same_action_concurrent_supervisor_launch_refuses_one(self):
        """Two concurrent starts have one winner and one typed fencing refusal."""
        engine, supervisor, _plan, claimed, captured, _invocation = self.make_case(
            worker_source="import time; time.sleep(0.4)",
            prefix="double-start",
            executor_wrapper=lambda _supervisor, _intent: None,
        )
        initial = engine.execute_effect(claimed)
        self.assertEqual(initial.state, EffectResultState.UNKNOWN_EFFECT)
        self.assertEqual(len(captured), 1)
        barrier = threading.Barrier(2)

        def launch_once():
            barrier.wait(timeout=5)
            try:
                return "started", supervisor.launch(captured[0])
            except SupervisorAlreadyStarted as error:
                return "refused", error

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _index: launch_once(), range(2)))

        self.assertEqual(sorted(outcome[0] for outcome in outcomes), ["refused", "started"])
        refusal = next(value for state, value in outcomes if state == "refused")
        self.assertEqual(refusal.code, "supervisor_already_started")
        self.assertIn("prior supervisor incarnation", str(refusal))
        marker_path = Path(claimed.plan.spec["completion_marker"])
        self.wait_for(marker_path.is_file)

    def test_detached_launcher_uses_start_new_session_and_returns_pid(self):
        engine, supervisor, _plan, claimed, captured, _invocation = self.make_case(
            worker_source="print('not reached by mocked detached launcher')",
            prefix="setsid",
            executor_wrapper=lambda _supervisor, _intent: None,
        )
        initial = engine.execute_effect(claimed)
        self.assertEqual(initial.state, EffectResultState.UNKNOWN_EFFECT)
        fake_process = mock.Mock(pid=4242)
        fake_process.wait.return_value = 0
        with mock.patch.object(
                supervisor_module.subprocess, "Popen",
                return_value=fake_process) as popen:
            handle = supervisor.launch(captured[0])

        self.assertEqual(handle.pid, 4242)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertTrue(popen.call_args.kwargs["close_fds"])
        self.assertIs(popen.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertIs(popen.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(popen.call_args.kwargs["stderr"], subprocess.DEVNULL)

    def test_failed_detached_popen_does_not_poison_launch_reservation(self):
        engine, supervisor, _plan, claimed, captured, _invocation = self.make_case(
            worker_source="print('not launched')",
            prefix="popen-failure",
            executor_wrapper=lambda _supervisor, _intent: None,
        )
        initial = engine.execute_effect(claimed)
        self.assertEqual(initial.state, EffectResultState.UNKNOWN_EFFECT)
        launch_path = supervisor._launch_path(captured[0].action_id)  # noqa: SLF001

        with mock.patch.object(
                supervisor_module.subprocess, "Popen",
                side_effect=OSError("injected Popen failure")):
            with self.assertRaises(SupervisorLaunchRefused) as raised:
                supervisor.launch(captured[0])

        self.assertEqual(raised.exception.code, "supervisor_launch_refused")
        self.assertFalse(launch_path.exists())

    def test_worker_written_marker_with_copied_identity_or_wrong_fence_is_rejected(self):
        """Worker marker writes cannot replace supervisor identity/fencing authority."""
        worker_gate = self.root / "release-forgery-worker"
        worker_source = (
            "import pathlib,time\n"
            f"gate=pathlib.Path({str(worker_gate)!r})\n"
            "while not gate.exists():\n"
            "    time.sleep(0.02)\n"
        )
        engine, supervisor, _plan, claimed, captured, _invocation = self.make_case(
            worker_source=worker_source,
            prefix="worker-forgery",
        )
        initial = engine.execute_effect(claimed)
        self.assertEqual(initial.state, EffectResultState.UNKNOWN_EFFECT)
        self.assertEqual(len(captured), 1)
        intent = captured[0]
        runtime_path = supervisor._runtime_path(intent.action_id)  # noqa: SLF001
        self.wait_for(runtime_path.is_file)
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        copied_identity = ProcessIdentity.from_payload(
            runtime["process_identity"]).canonical
        self.assertEqual(
            observe_process_identity(
                ProcessIdentity.from_payload(runtime["process_identity"])).state,
            LivenessState.ALIVE,
        )
        empty = ArtifactStore(self.root).write(b"").digest
        forged = RunnerCompletionMarker(
            run_id=intent.run_id,
            job_id=intent.job_id,
            action_id=intent.action_id,
            fencing_epoch=intent.fencing_epoch,
            launch_token=intent.launch_token,
            process_identity=copied_identity,
            started_at="2026-07-21T00:00:00Z",
            finished_at="2026-07-21T00:00:01Z",
            returncode=0,
            signal=None,
            stdout_artifact_digest=empty,
            stderr_artifact_digest=empty,
        )
        publish_runner_completion(intent.completion_marker_path, forged)

        with self.assertRaises(CompletionMarkerRefused) as wrong_identity:
            supervisor.validate_completion_marker(forged)
        self.assertEqual(wrong_identity.exception.code, "completion_marker_refused")
        result = engine.inspect_effect(intent.action_id)
        self.assertEqual(result.state, EffectResultState.UNKNOWN_EFFECT)
        self.assertIn("identity", result.reason)
        worker_gate.write_text("release\n", encoding="utf-8")
        wait_path = supervisor._wait_path(intent.action_id)  # noqa: SLF001
        self.wait_for(wait_path.is_file)
        with self.assertRaises(CompletionMarkerRefused) as wrong_fence:
            supervisor.validate_completion_marker(
                replace(forged, fencing_epoch=forged.fencing_epoch + 1))
        self.assertIn("fencing", str(wrong_fence.exception))
        with self.assertRaises(CompletionMarkerRefused) as copied_but_unwaited:
            supervisor.validate_completion_marker(forged)
        self.assertIn("wait evidence", str(copied_but_unwaited.exception))
        self.wait_for(
            lambda: observe_process_identity(
                ProcessIdentity.from_payload(json.loads(
                    runtime_path.read_text(encoding="utf-8"))["process_identity"])
            ).state is not LivenessState.ALIVE,
            timeout=5,
        )

    def test_heartbeat_freshness_never_crosses_boot_or_wall_clock_domains(self):
        identity = ProcessIdentity(
            host_boot_identity="boot-a",
            pid=123,
            process_start_token="start-a",
            action_id="heartbeat-action",
            supervisor_owner_token="heartbeat-owner",
            fencing_epoch=3,
            invocation_digest=self.sha256(b"heartbeat-invocation"),
        )
        heartbeat = SupervisorHeartbeat(
            action_id=identity.action_id,
            fencing_epoch=identity.fencing_epoch,
            host_boot_identity=identity.host_boot_identity,
            monotonic_observed_at=100.0,
            wall_observed_at="2099-01-01T00:00:00Z",
            process_identity=identity,
        )
        self.assertEqual(
            heartbeat_freshness(
                heartbeat, stale_after=5, current_boot_identity="boot-a",
                monotonic_now=104.9),
            HeartbeatFreshness.FRESH,
        )
        self.assertEqual(
            heartbeat_freshness(
                heartbeat, stale_after=5, current_boot_identity="boot-a",
                monotonic_now=105.1),
            HeartbeatFreshness.STALE,
        )
        self.assertEqual(
            heartbeat_freshness(
                heartbeat, stale_after=5, current_boot_identity="boot-b",
                monotonic_now=101),
            HeartbeatFreshness.UNKNOWN,
        )

    def test_signal_exit_uses_signal_field_and_stream_bytes_are_artifacts(self):
        worker = "import os,signal; os.kill(os.getpid(), signal.SIGTERM)"
        engine, supervisor, _plan, claimed, _captured, _invocation = self.make_case(
            worker_source=worker,
            prefix="signal-exit",
        )
        result = engine.execute_effect(claimed)
        self.assertEqual(result.state, EffectResultState.UNKNOWN_EFFECT)
        marker_path = Path(claimed.plan.spec["completion_marker"])
        self.wait_for(marker_path.is_file)
        marker = self.marker_from(marker_path)
        supervisor.validate_completion_marker(marker)
        self.assertIsNone(marker.returncode)
        self.assertEqual(marker.signal, 15)
        artifacts = ArtifactStore(self.root)
        self.assertEqual(artifacts.read(marker.stdout_artifact_digest), b"")
        self.assertEqual(artifacts.read(marker.stderr_artifact_digest), b"")

    def test_process_identity_canonical_round_trip_binds_all_minimum_axes(self):
        identity = ProcessIdentity(
            host_boot_identity="boot-round-trip",
            pid=1234,
            process_start_token="start-round-trip",
            action_id="action-round-trip",
            supervisor_owner_token="owner-round-trip",
            fencing_epoch=7,
            resolved_executable="/resolved/runner",
            invocation_digest=self.sha256(b"round-trip"),
        )
        decoded = ProcessIdentity.from_payload(json.loads(identity.canonical))
        self.assertEqual(decoded, identity)
        self.assertEqual(set(json.loads(identity.canonical)), {
            "host_boot_identity", "pid", "process_start_token", "action_id",
            "supervisor_owner_token", "fencing_epoch", "resolved_executable",
            "invocation_digest",
        })


if __name__ == "__main__":
    unittest.main(verbosity=2)
