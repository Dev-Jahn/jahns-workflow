#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Focused waiting-context CAS, resume, and race contracts."""
from __future__ import annotations

from support import *  # noqa: F401,F403

import json
from contextlib import contextmanager
from unittest import mock

from test_work_brief import completion_contract, init_project, payload
from waystone.features.review_layout import new_run_id
from waystone.jobs import completion
from waystone.jobs.domain import Role
from waystone.jobs.profile import assemble_run
from waystone.project.context import resolve_project_context
from waystone.runs.artifacts import ArtifactReference, ArtifactReferenceKind, ArtifactStore
from waystone.runs.assurance import compile_assurance_plan
from waystone.runs.engine import StagedRunEngine
from waystone.runs.spec import load_run_spec
from waystone.runs.store import (
    ContextNotCurrent,
    EntityKind,
    FilesystemInfo,
    RecordNotFoundError,
    RunStore,
    TransitionReason,
)
from waystone.runs.worker_result import ContextRequest


class RunContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name) / "repo"
        self.root.mkdir()
        init_repo(self.root)
        (self.root / ".waystone.yml").write_text(
            "version: 1\nproject: fixture\n", encoding="utf-8")
        git(self.root, "add", ".waystone.yml")
        self.assertEqual(git(self.root, "commit", "-qm", "fixture").returncode, 0)

    @contextmanager
    def supported_filesystem(self):
        with mock.patch(
                "waystone.runs.store._probe_state_filesystem",
                return_value=FilesystemInfo(
                    filesystem="apfs", mount_point=Path("/"), writable=True)):
            yield

    def store(self) -> RunStore:
        with self.supported_filesystem():
            store = RunStore.open(self.root)
        self.addCleanup(store.close)
        return store

    @staticmethod
    def ref(identity: str, digest: str, size: int, kind=ArtifactReferenceKind.INPUT):
        return ArtifactReference(identity, kind, digest, size)

    def active_run(self, store: RunStore):
        run = store.create_run("dispatch-ready")
        job_id = f"{run.run_id}:job"
        store.create_job(run.run_id, job_id, "planned")
        attempt_id = f"{run.run_id}:attempt:1"
        store.create_attempt(run.run_id, job_id, attempt_id, "running")
        return run.run_id, job_id, attempt_id

    def request(self, store: RunStore, run_id: str, job_id: str, attempt_id: str):
        artifacts = ArtifactStore(self.root)
        worker = artifacts.write(b"worker-result")
        request = artifacts.write(b"context-request")
        references = (
            self.ref(
                f"worker-result:{attempt_id}", worker.digest, worker.size,
                ArtifactReferenceKind.EVIDENCE),
            self.ref(
                f"context-request:{run_id}:1", request.digest, request.size,
                ArtifactReferenceKind.EVIDENCE),
        )
        transition = store.record_context_request(
            run_id, job_id, attempt_id,
            context_request_digest=request.digest,
            artifact_references=references,
        )
        return request, transition

    def response_refs(self, run_id: str):
        artifacts = ArtifactStore(self.root)
        result = []
        for label in ("context-response", "work-brief", "assurance-plan", "completion-contract"):
            stored = artifacts.write(label.encode())
            result.append(self.ref(f"{label}:{run_id}:2", stored.digest, stored.size))
        spec = artifacts.write(b"run-spec-revision-2")
        result.append(self.ref(f"run-spec:{run_id}:2", spec.digest, spec.size))
        return spec, tuple(result)

    def test_context_request_and_response_create_new_revision_attempt_without_resetting_budget(self):
        store = self.store()
        run_id, job_id, attempt_id = self.active_run(store)
        request, waiting = self.request(store, run_id, job_id, attempt_id)
        self.assertEqual(waiting.run.state, "waiting_context")
        self.assertEqual(waiting.job.state, "waiting_context")
        self.assertEqual(waiting.attempt.state, "context_requested")
        spec, references = self.response_refs(run_id)

        resumed = store.provide_context(
            run_id, job_id,
            request_digest=request.digest,
            run_spec_digest=spec.digest,
            max_total_attempts=2,
            artifact_references=references,
        )

        self.assertEqual(resumed.run.state, "dispatch-ready")
        self.assertEqual(resumed.job.state, "dispatch-ready")
        self.assertEqual(resumed.attempt.entity_id, f"{run_id}:attempt:2")
        self.assertEqual(resumed.attempt.state, "running")
        self.assertEqual(
            store._connection.execute(  # noqa: SLF001
                "SELECT count(*) FROM attempts WHERE run_id = ?", (run_id,)).fetchone()[0],
            2,
        )
        self.assertEqual(store.get_artifact_reference(f"run-spec:{run_id}:2").digest, spec.digest)

    def test_cancel_and_response_race_has_one_winner_and_loser_leaves_no_references(self):
        with self.subTest("cancel wins"):
            store = self.store()
            run_id, job_id, attempt_id = self.active_run(store)
            request, _ = self.request(store, run_id, job_id, attempt_id)
            run = store.get_run(run_id)
            store.record_transition(
                EntityKind.RUN, run_id, expected_version=run.version,
                next_state="cancel-requested", reason=TransitionReason.CANCEL_REQUESTED)
            spec, references = self.response_refs(run_id)
            with self.assertRaises(ContextNotCurrent):
                store.provide_context(
                    run_id, job_id, request_digest=request.digest,
                    run_spec_digest=spec.digest, max_total_attempts=2,
                    artifact_references=references)
            with self.assertRaises(RecordNotFoundError):
                store.get_artifact_reference(f"run-spec:{run_id}:2")

        with self.subTest("response wins"):
            second_root = Path(self._temporary_directory.name) / "repo-second"
            second_root.mkdir()
            init_repo(second_root)
            (second_root / ".waystone.yml").write_text(
                "version: 1\nproject: fixture\n", encoding="utf-8")
            old_root, self.root = self.root, second_root
            try:
                second_store = self.store()
                run_id, job_id, attempt_id = self.active_run(second_store)
                request, _ = self.request(second_store, run_id, job_id, attempt_id)
                spec, references = self.response_refs(run_id)
                resumed = second_store.provide_context(
                    run_id, job_id, request_digest=request.digest,
                    run_spec_digest=spec.digest, max_total_attempts=2,
                    artifact_references=references)
                second_store.record_transition(
                    EntityKind.RUN, run_id, expected_version=resumed.run.version,
                    next_state="cancel-requested", reason=TransitionReason.CANCEL_REQUESTED)
                self.assertEqual(
                    second_store.get_entity(
                        EntityKind.ATTEMPT, f"{run_id}:attempt:2").state,
                    "running",
                )
            finally:
                self.root = old_root

    def test_crash_before_request_publication_leaves_no_state_or_reference(self):
        store = self.store()
        run_id, job_id, attempt_id = self.active_run(store)
        artifacts = ArtifactStore(self.root)
        worker = artifacts.write(b"worker")
        request = artifacts.write(b"request")
        references = (
            self.ref(f"worker-result:{attempt_id}", worker.digest, worker.size,
                     ArtifactReferenceKind.EVIDENCE),
            self.ref(f"context-request:{run_id}:1", request.digest, request.size,
                     ArtifactReferenceKind.EVIDENCE),
        )

        def crash(stage: str):
            if stage == "context_request_before_publication":
                raise RuntimeError("crash before publication")

        with mock.patch.object(store, "_transaction_fault_point", side_effect=crash):
            with self.assertRaisesRegex(RuntimeError, "crash before publication"):
                store.record_context_request(
                    run_id, job_id, attempt_id,
                    context_request_digest=request.digest,
                    artifact_references=references)

        self.assertEqual(store.get_run(run_id).state, "dispatch-ready")
        with self.assertRaises(RecordNotFoundError):
            store.get_artifact_reference(f"context-request:{run_id}:1")

    def test_crash_after_request_publication_rolls_back_and_retry_succeeds(self):
        store = self.store()
        run_id, job_id, attempt_id = self.active_run(store)
        artifacts = ArtifactStore(self.root)
        worker = artifacts.write(b"worker")
        request = artifacts.write(b"request")
        references = (
            self.ref(f"worker-result:{attempt_id}", worker.digest, worker.size,
                     ArtifactReferenceKind.EVIDENCE),
            self.ref(f"context-request:{run_id}:1", request.digest, request.size,
                     ArtifactReferenceKind.EVIDENCE),
        )
        original = store._transaction_fault_point  # noqa: SLF001

        def crash(stage: str):
            if stage == "context_request_after_publication":
                raise RuntimeError("crash after publication")
            original(stage)

        with mock.patch.object(store, "_transaction_fault_point", side_effect=crash):
            with self.assertRaisesRegex(RuntimeError, "crash after publication"):
                store.record_context_request(
                    run_id, job_id, attempt_id,
                    context_request_digest=request.digest,
                    artifact_references=references)
        self.assertEqual(store.get_run(run_id).state, "dispatch-ready")
        with self.assertRaises(RecordNotFoundError):
            store.get_artifact_reference(f"context-request:{run_id}:1")

        self.request(store, run_id, job_id, attempt_id)
        self.assertEqual(store.get_run(run_id).state, "waiting_context")


class ContextResumeE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        base = Path(self._temporary_directory.name)
        self.root = base / "repo"
        self.root.mkdir()
        self.head, self.frame = init_project(self.root)
        (self.root / "tasks.yaml").write_text(
            "version: 1\nproject: demo\ntasks:\n"
            "  - id: feat/semantic-brief\n"
            "    title: Compare candidate approaches\n"
            "    status: pending\n"
            "    scope: [src.py]\n"
            "    deps: []\n",
            encoding="utf-8",
        )
        git(self.root, "add", "tasks.yaml")
        self.assertEqual(git(self.root, "commit", "-qm", "task").returncode, 0)
        state = self.root / ".waystone"
        state.mkdir()
        state.joinpath("profile.yml").write_text(
            "schema: waystone-profile-2\nbindings:\n"
            "  coordinator: {execution: in-session, backend: 'host:current'}\n"
            "  worker: {execution: external, backend: 'codex:worker'}\n"
            "  verifier: {execution: external, backend: 'codex:verifier'}\n"
            "  reviewer: {execution: external, backend: 'codex:reviewer'}\n",
            encoding="utf-8",
        )
        self.registry = base / "machine" / "projects.json"
        self.registry.parent.mkdir()
        self.registry.write_text(json.dumps({"projects": [{
            "project_id": "project:context-e2e",
            "name": "demo",
            "path": str(self.root.resolve()),
        }]}), encoding="utf-8")

    @contextmanager
    def supported_filesystem(self):
        with mock.patch(
                "waystone.runs.store._probe_state_filesystem",
                return_value=FilesystemInfo(
                    filesystem="apfs", mount_point=Path("/"), writable=True)):
            yield

    def test_response_publishes_new_brief_spec_and_attempt(self):
        contract = completion_contract(self.root, self.frame)
        brief = completion.canonical_json(payload(self.head, self.frame, new_run_id()))
        assurance = compile_assurance_plan("explore").canonical_bytes()
        with self.supported_filesystem():
            context = resolve_project_context(self.root, registry=self.registry)
            with assemble_run(context) as assembly:
                engine = StagedRunEngine(assembly)
                started = engine.start(
                    "feat/semantic-brief",
                    work_brief_content=brief,
                    completion_contract_content=contract.canonical_bytes(),
                    assurance_plan_content=assurance,
                    frame_status_ref=self.frame.status_ref,
                    project_fact_refs=(self.frame.fact_ref("hypothesis/solver"),),
                )
                request_payload = ContextRequest(
                    run_id=started.spec.run_id,
                    job_id=started.spec.job_id,
                    attempt_id=started.attempt_id,
                    run_spec_digest=started.spec.run_spec_digest,
                    work_brief_digest=started.spec.work_brief.digest,
                    question="Which API contract is authoritative?",
                    blocked_decision="Preserve or replace the public API",
                    why_required="The answer changes the implementation scope",
                    observed_result_digest=started.spec.base_snapshot.digest,
                )
                request = assembly.artifact_store.write(
                    request_payload.canonical_bytes())
                worker = assembly.artifact_store.write(b"worker-result")
                assembly.store.record_context_request(
                    started.spec.run_id,
                    started.spec.job_id,
                    started.attempt_id,
                    context_request_digest=request.digest,
                    artifact_references=(
                        ArtifactReference(
                            f"worker-result:{started.attempt_id}",
                            ArtifactReferenceKind.EVIDENCE,
                            worker.digest,
                            worker.size,
                        ),
                        ArtifactReference(
                            f"context-request:{started.spec.run_id}:1",
                            ArtifactReferenceKind.EVIDENCE,
                            request.digest,
                            request.size,
                        ),
                    ),
                )
                binding = assembly.profile.binding_for(
                    Role.COORDINATOR).binding_digest
                owner_source = assembly.artifact_store.write(
                    b"Preserve the public API.")
                response = (
                    "schema: waystone-context-response-1\n"
                    f"request_digest: {request.digest}\n"
                    "answer:\n"
                    "  text: Preserve the public API.\n"
                    "  provenance: owner-source\n"
                    "  source:\n"
                    "    kind: owner-artifact\n"
                    f"    digest: {owner_source.digest}\n"
                    "issued_by:\n"
                    "  role: coordinator\n"
                    f"  binding_digest: {binding}\n"
                    "  principal: null\n"
                ).encode()

                resumed = engine.provide_context(started.spec.run_id, response)

                self.assertEqual(resumed.spec.revision, 2)
                self.assertEqual(
                    resumed.spec.supersedes_spec_digest, started.spec.run_spec_digest)
                self.assertEqual(
                    resumed.spec.work_brief.reference_id,
                    f"work-brief:{started.spec.run_id}:2",
                )
                self.assertEqual(
                    resumed.attempt_id, f"{started.spec.run_id}:attempt:2")
                self.assertEqual(
                    assembly.store.get_entity(
                        EntityKind.ATTEMPT, resumed.attempt_id).state,
                    "running",
                )
                self.assertEqual(
                    load_run_spec(started.spec.run_id, start=self.root), resumed.spec)


if __name__ == "__main__":
    unittest.main(verbosity=2)
