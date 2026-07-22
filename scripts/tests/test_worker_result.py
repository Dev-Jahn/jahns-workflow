#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Focused worker-result union and snapshot contracts."""
from __future__ import annotations

from support import *  # noqa: F401,F403

import json

from waystone.runs.spec import _capture_snapshot
from waystone.runs.worker_result import (
    CompletedWorkerResult,
    ContextResponseBindingMismatch,
    ContextRequestWithChanges,
    ContextRequestedWorkerResult,
    RunnerCompletionMarkerRefusal,
    RunnerCompletionMarkerV2,
    WorkerResultAdapter,
    WorkerResultBindingMismatch,
    capture_result_snapshot,
    parse_context_response_bytes,
    parse_runner_completion_marker_v2_bytes,
    parse_worker_result_bytes,
)


class WorkerResultTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name) / "repo"
        self.root.mkdir()
        init_repo(self.root)
        (self.root / ".waystone.yml").write_text(
            "version: 1\nproject: fixture\n", encoding="utf-8")
        (self.root / "code.py").write_text("value = 1\n", encoding="utf-8")
        git(self.root, "add", "-A")
        self.assertEqual(git(self.root, "commit", "-qm", "fixture").returncode, 0)
        self.spec_digest = "sha256:" + "a" * 64
        self.work_brief_digest = "sha256:" + "b" * 64
        self.run_id = "019f0000-0000-7000-8000-000000000001"
        self.job_id = f"{self.run_id}:job"
        self.attempt_id = f"{self.run_id}:attempt:1"

    def context_bytes(self) -> bytes:
        return (
            "schema: waystone-worker-result-1\n"
            "status: context-requested\n"
            f"run_spec_digest: {self.spec_digest}\n"
            f"attempt_id: {self.attempt_id}\n"
            "context_request:\n"
            "  question: Which contract is authoritative?\n"
            "  blocked_decision: Preserve or replace the public API\n"
            "  why_required: The answer changes the implementation scope\n"
        ).encode()

    def test_union_parses_completed_and_context_requested_without_stdout_inference(self):
        completed = parse_worker_result_bytes((
            "schema: waystone-worker-result-1\n"
            "status: completed\n"
            f"run_spec_digest: {self.spec_digest}\n"
            f"attempt_id: {self.attempt_id}\n"
            "result_summary: Implemented the bounded change.\n"
            "evidence_refs: []\n"
        ).encode())
        requested = parse_worker_result_bytes(self.context_bytes())

        self.assertIsInstance(completed, CompletedWorkerResult)
        self.assertIsInstance(requested, ContextRequestedWorkerResult)
        with self.assertRaises(WorkerResultBindingMismatch):
            parse_worker_result_bytes(
                self.context_bytes(),
                expected_run_spec_digest="sha256:" + "c" * 64,
                expected_attempt_id=self.attempt_id,
            )

    def test_reserved_control_file_is_excluded_from_result_snapshot(self):
        base = _capture_snapshot(self.root)
        base_digest = "sha256:" + hashlib.sha256(base.canonical_bytes()).hexdigest()
        (self.root / "WAYSTONE_RESULT.yaml").write_bytes(self.context_bytes())

        observed = capture_result_snapshot(self.root)

        self.assertEqual(observed.digest, base_digest)
        self.assertNotIn(
            b"WAYSTONE_RESULT.yaml", {entry.path for entry in observed.snapshot.entries})

    def test_context_request_publishes_exact_result_and_derived_request_without_changes(self):
        base = _capture_snapshot(self.root)
        base_digest = "sha256:" + hashlib.sha256(base.canonical_bytes()).hexdigest()
        control = self.context_bytes()
        (self.root / "WAYSTONE_RESULT.yaml").write_bytes(control)

        adapted = WorkerResultAdapter(self.root).adapt(
            run_id=self.run_id,
            job_id=self.job_id,
            attempt_id=self.attempt_id,
            run_spec_digest=self.spec_digest,
            work_brief_digest=self.work_brief_digest,
            base_snapshot_digest=base_digest,
        )

        self.assertEqual(
            adapted.worker_result_artifact.digest,
            "sha256:" + hashlib.sha256(control).hexdigest(),
        )
        self.assertEqual(adapted.context_request.observed_result_digest, base_digest)
        self.assertEqual(
            adapted.context_request_artifact.digest,
            "sha256:" + hashlib.sha256(
                adapted.context_request.canonical_bytes()).hexdigest(),
        )

    def test_context_request_with_code_delta_is_rejected(self):
        base = _capture_snapshot(self.root)
        base_digest = "sha256:" + hashlib.sha256(base.canonical_bytes()).hexdigest()
        (self.root / "WAYSTONE_RESULT.yaml").write_bytes(self.context_bytes())
        (self.root / "code.py").write_text("value = 2\n", encoding="utf-8")

        with self.assertRaises(ContextRequestWithChanges) as raised:
            WorkerResultAdapter(self.root).adapt(
                run_id=self.run_id,
                job_id=self.job_id,
                attempt_id=self.attempt_id,
                run_spec_digest=self.spec_digest,
                work_brief_digest=self.work_brief_digest,
                base_snapshot_digest=base_digest,
            )
        self.assertEqual(raised.exception.code, "context_request_with_changes")

    def test_stale_coordinator_binding_digest_is_rejected(self):
        request_digest = "sha256:" + "c" * 64
        current_binding = "sha256:" + "d" * 64
        response = (
            "schema: waystone-context-response-1\n"
            f"request_digest: {request_digest}\n"
            "answer:\n"
            "  text: Preserve the public API.\n"
            "  provenance: owner-source\n"
            "  source: {kind: owner-artifact, digest: 'sha256:"
            + "e" * 64 + "'}\n"
            "issued_by:\n"
            "  role: coordinator\n"
            f"  binding_digest: {'sha256:' + 'f' * 64}\n"
            "  principal: null\n"
        ).encode()

        with self.assertRaises(ContextResponseBindingMismatch) as raised:
            parse_context_response_bytes(
                response,
                expected_request_digest=request_digest,
                expected_binding_digest=current_binding,
            )

        self.assertEqual(raised.exception.code, "context_response_binding_mismatch")

    def test_runner_completion_marker_v2_requires_and_binds_worker_result_digest(self):
        marker = RunnerCompletionMarkerV2(
            run_id=self.run_id,
            job_id=self.job_id,
            action_id=f"{self.run_id}:runner",
            fencing_epoch=1,
            launch_token="launch-token",
            process_identity="process-identity",
            started_at="2026-07-22T00:00:00Z",
            finished_at="2026-07-22T00:00:01Z",
            returncode=0,
            signal=None,
            stdout_artifact_digest="sha256:" + "1" * 64,
            stderr_artifact_digest="sha256:" + "2" * 64,
            worker_result_digest="sha256:" + "3" * 64,
        )

        self.assertEqual(parse_runner_completion_marker_v2_bytes(marker.canonical_bytes()), marker)
        missing = json.loads(marker.canonical_bytes())
        del missing["worker_result_digest"]
        with self.assertRaises(RunnerCompletionMarkerRefusal):
            parse_runner_completion_marker_v2_bytes(
                json.dumps(
                    missing, sort_keys=True, separators=(",", ":")).encode())


if __name__ == "__main__":
    unittest.main(verbosity=2)
