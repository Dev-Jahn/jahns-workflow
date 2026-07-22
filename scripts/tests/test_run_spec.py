#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Focused waystone-run-spec-2 contracts."""
from __future__ import annotations

from support import *  # noqa: F401,F403

from contextlib import contextmanager
from unittest import mock

from test_work_brief import completion_contract, init_project, payload
from waystone.features.review_layout import new_run_id
from waystone.jobs import completion
from waystone.runs.artifacts import ArtifactReferenceKind, ArtifactStore
from waystone.runs.assurance import compile_assurance_plan, parse_assurance_plan_bytes
from waystone.runs.spec import (
    ResultPolicy,
    RunInputDriftError,
    assert_task_input_current,
    detect_task_input_drift,
    load_run_spec,
    plan_one_task_run,
    read_base_snapshot,
)
from waystone.runs.store import FilesystemInfo, RunStore


class RunSpecTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name) / "repo"
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
        self.contract = completion_contract(self.root, self.frame)
        self.brief_bytes = completion.canonical_json(
            payload(self.head, self.frame, new_run_id()))
        self.assurance_bytes = compile_assurance_plan("explore").canonical_bytes()

    @contextmanager
    def supported_filesystem(self):
        with mock.patch(
                "waystone.runs.store._probe_state_filesystem",
                return_value=FilesystemInfo(
                    filesystem="apfs", mount_point=Path("/"), writable=True)):
            yield

    def plan(self):
        with self.supported_filesystem():
            return plan_one_task_run(
                "feat/semantic-brief",
                work_brief_content=self.brief_bytes,
                completion_contract_content=self.contract.canonical_bytes(),
                assurance_plan_content=self.assurance_bytes,
                frame_status_ref=self.frame.status_ref,
                project_fact_refs=(self.frame.fact_ref("hypothesis/solver"),),
                start=self.root,
            )

    def test_v2_freezes_stage_fact_brief_assurance_contract_and_revisioned_reference(self):
        spec = self.plan()

        self.assertEqual(spec.revision, 1)
        self.assertIsNone(spec.supersedes_spec_digest)
        self.assertEqual(spec.lifecycle_stage.value, "explore")
        self.assertIsNone(spec.promotion_lineage)
        self.assertIsNone(spec.candidate)
        self.assertEqual(spec.evaluation, {"spec": None, "evidence": None})
        self.assertEqual(
            spec.result_policy,
            ResultPolicy(
                "candidate-ref", f"refs/waystone/candidates/{spec.run_id}", None),
        )
        self.assertEqual(spec.frame_status_ref.digest, self.frame.status_ref.digest)
        self.assertEqual(
            spec.project_fact_refs, (self.frame.fact_ref("hypothesis/solver"),))
        self.assertEqual(spec.objective_ref.to_dict(), self.frame.fact_ref("hypothesis/solver").to_dict())
        self.assertEqual(spec.job_input.acceptance_criteria, ("Record the answer or candidate.",))
        self.assertEqual(spec.retry.max_total_attempts, 2)
        frozen_assurance = parse_assurance_plan_bytes(
            ArtifactStore(self.root).read(spec.assurance_plan.digest))
        self.assertEqual(frozen_assurance.completion["contract"], {
            "reference_id": spec.job_input.completion_contract.reference_id,
            "digest": spec.job_input.completion_contract.digest,
        })

        with self.supported_filesystem(), RunStore.open(self.root) as store:
            spec_ref = store.get_artifact_reference(f"run-spec:{spec.run_id}:1")
            self.assertEqual(spec_ref.kind, ArtifactReferenceKind.INPUT)
            for reference_id in (
                    spec.work_brief.reference_id, spec.assurance_plan.reference_id,
                    spec.job_input.completion_contract.reference_id):
                self.assertEqual(
                    store.get_artifact_reference(reference_id).kind,
                    ArtifactReferenceKind.INPUT,
                )
        self.assertEqual(ArtifactStore(self.root).read_reference(spec_ref), spec.canonical_bytes())
        with self.supported_filesystem():
            self.assertEqual(load_run_spec(spec.run_id, start=self.root), spec)

    def test_snapshot_and_task_drift_preserve_frozen_semantic_inputs(self):
        (self.root / "src.py").write_text("baseline = 'dirty'\n", encoding="utf-8")
        spec = self.plan()
        with self.supported_filesystem():
            snapshot = read_base_snapshot(spec.run_id, start=self.root)
        self.assertEqual(
            {entry.path: entry for entry in snapshot.entries}[b"src.py"].content,
            b"baseline = 'dirty'\n",
        )

        tasks = self.root / "tasks.yaml"
        tasks.write_text(
            tasks.read_text(encoding="utf-8").replace(
                "Compare candidate approaches", "Changed owner-selected work"),
            encoding="utf-8",
        )
        with self.supported_filesystem():
            drift = detect_task_input_drift(spec.run_id, start=self.root)
            self.assertEqual(drift.changed_fields, ("title",))
            with self.assertRaises(RunInputDriftError):
                assert_task_input_current(spec.run_id, start=self.root)
            self.assertEqual(load_run_spec(spec.run_id, start=self.root), spec)

    def test_stage_mismatch_refuses_before_creating_run_rows(self):
        invalid_assurance = compile_assurance_plan(
            "promote",
            evaluation_spec={"digest": "sha256:" + "1" * 64, "generation": 1},
            promotion_lineage_id=new_run_id(),
        ).canonical_bytes()
        with self.assertRaisesRegex(Exception, "assurance plan schema/stage"):
            with self.supported_filesystem():
                plan_one_task_run(
                    "feat/semantic-brief",
                    work_brief_content=self.brief_bytes,
                    completion_contract_content=self.contract.canonical_bytes(),
                    assurance_plan_content=invalid_assurance,
                    frame_status_ref=self.frame.status_ref,
                    project_fact_refs=(self.frame.fact_ref("hypothesis/solver"),),
                    start=self.root,
                )
        database = self.root / ".waystone" / "state.db"
        self.assertFalse(database.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
