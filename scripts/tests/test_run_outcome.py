#!/usr/bin/env python3
"""Focused OutcomeDelta publication and objective-first status contracts."""
from __future__ import annotations

from support import *  # noqa: F401,F403

import contextlib
import io
import json
import subprocess
from types import SimpleNamespace
from unittest import mock

import yaml

from test_work_brief import completion_contract, init_project, payload
from waystone.cli import run_group, status_group
from waystone.features.review_layout import new_run_id
from waystone.jobs import completion
from waystone.jobs.domain import Role
from waystone.jobs.profile import assemble_run
from waystone.project.context import ProjectContext
from waystone.runs import observe as observe_module
from waystone.runs import outcome as outcome_module
from waystone.runs.artifacts import ArtifactReference, ArtifactReferenceKind
from waystone.runs.assurance import compile_assurance_plan
from waystone.runs.engine import StagedRunEngine
from waystone.runs.observe import project_status_json, project_status_projection
from waystone.runs.outcome import (
    CloseoutIncomplete,
    OutcomeLedgerRefusal,
    OutcomeSchemaRefusal,
    parse_outcome_delta_bytes,
    read_outcome_ledger,
)
from waystone.runs.spec import plan_one_task_run
from waystone.runs.store import EntityKind, FilesystemInfo, TransitionReason


class OutcomeFixture:
    def __init__(self, case: unittest.TestCase):
        self.case = case
        temporary = tempfile.TemporaryDirectory()
        case.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repo"
        self.root.mkdir()
        self.head, self.frame = init_project(self.root)
        self.root.joinpath("tasks.yaml").write_text(
            "version: 1\nproject: demo\ntasks:\n"
            "  - id: feat/semantic-brief\n"
            "    title: Explore candidate\n"
            "    status: pending\n"
            "    scope: [src.py]\n"
            "    deps: []\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "-C", str(self.root), "add", "tasks.yaml"], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-qm", "task"], check=True)
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
        common = Path(subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "--git-common-dir"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()).resolve()
        self.context = ProjectContext(
            "project:test", self.root, self.root, common, "canonical",
            state / "state.db",
        )
        self.filesystem = mock.patch(
            "waystone.runs.store._probe_state_filesystem",
            return_value=FilesystemInfo("apfs", Path("/"), writable=True),
        )
        self.filesystem.start()
        case.addCleanup(self.filesystem.stop)
        self.assembly = assemble_run(self.context)
        case.addCleanup(self.assembly.close)
        self.contract = completion_contract(self.root, self.frame)

    def ready_run(self):
        brief = completion.canonical_json(
            payload(self.head, self.frame, new_run_id()))
        spec = plan_one_task_run(
            "feat/semantic-brief",
            work_brief_content=brief,
            completion_contract_content=self.contract.canonical_bytes(),
            assurance_plan_content=compile_assurance_plan("explore").canonical_bytes(),
            frame_status_ref=self.frame.status_ref,
            project_fact_refs=(self.frame.fact_ref("hypothesis/solver"),),
            artifact_store=self.assembly.artifact_store,
            run_store=self.assembly.store,
            start=self.root,
        )
        attempt_id = f"{spec.run_id}:attempt:1"
        attempt = self.assembly.store.create_attempt(
            spec.run_id, spec.job_id, attempt_id, initial_state="running")
        result = self.assembly.artifact_store.write(
            yaml.safe_dump({
                "schema": "waystone-worker-result-1",
                "status": "completed",
                "run_spec_digest": spec.run_spec_digest,
                "attempt_id": attempt_id,
                "result_summary": "The bounded run completed.",
                "evidence_refs": [],
            }, sort_keys=False).encode())
        self.assembly.store.record_transition(
            EntityKind.ATTEMPT,
            attempt_id,
            expected_version=attempt.version,
            next_state="completed",
            reason=TransitionReason.COMPLETED,
            evidence_digest=result.digest,
            artifact_references=(ArtifactReference(
                f"worker-result:{attempt_id}", ArtifactReferenceKind.EVIDENCE,
                result.digest, result.size,
            ),),
        )
        job = self.assembly.store.get_entity(EntityKind.JOB, spec.job_id)
        self.assembly.store.record_transition(
            EntityKind.JOB, spec.job_id, expected_version=job.version,
            next_state="completed", reason=TransitionReason.COMPLETED,
            evidence_digest=result.digest,
        )
        run = self.assembly.store.get_run(spec.run_id)
        self.assembly.store.record_transition(
            EntityKind.RUN, spec.run_id, expected_version=run.version,
            next_state="closeout-ready", reason=TransitionReason.COMPLETED,
            evidence_digest=result.digest,
        )
        return spec, result

    def outcome_bytes(self, spec, result, *, kind="no-objective-delta") -> bytes:
        binding = self.assembly.profile.binding_for(
            Role.COORDINATOR).binding_digest
        body = {
            "schema": "waystone-outcome-delta-1",
            "run_id": spec.run_id,
            "run_spec_digest": spec.run_spec_digest,
            "lifecycle_stage": spec.lifecycle_stage.value,
            "objective_ref": spec.objective_ref.to_dict(),
            "kind": kind,
            "summary": "The run closed without changing the objective.",
            "result_digest": result.digest,
            "evidence_refs": [],
            "finding_refs": [],
            "recorded_by": {
                "role": "coordinator",
                "binding_digest": binding,
                "principal": None,
            },
            "rationale": "This was bounded remediation, not objective progress.",
        }
        return yaml.safe_dump(body, sort_keys=False).encode()


class RunOutcomeTests(unittest.TestCase):
    def test_pair_publication_binds_action_and_completes_only_after_observation(self):
        fixture = OutcomeFixture(self)
        spec, result = fixture.ready_run()
        outcome_path = fixture.root.parent / "outcome.yaml"
        outcome_path.write_bytes(fixture.outcome_bytes(spec, result))
        output = io.StringIO()
        with mock.patch.object(
                run_group, "resolve_project_context", return_value=fixture.context), \
                contextlib.redirect_stdout(output):
            returncode = run_group.main([
                "close", spec.run_id, "--outcome", str(outcome_path)])

        self.assertEqual(returncode, 0, output.getvalue())
        self.assertEqual(fixture.assembly.store.get_run(spec.run_id).state, "completed")
        entries = read_outcome_ledger(fixture.root)
        self.assertEqual([entry.outcome.run_id for entry in entries], [spec.run_id])
        self.assertIn(entries[0].commit_oid, output.getvalue())
        action_id = f"{spec.run_id}:outcome-publication"
        action = fixture.assembly.store.get_entity(
            EntityKind.ACTION, action_id)
        self.assertEqual(action.state, "completed")
        with fixture.assembly.store._connection_lock:  # noqa: SLF001
            rows = fixture.assembly.store._connection.execute(  # noqa: SLF001
                "SELECT reference_id, reference_kind FROM artifacts "
                "WHERE entity_kind = 'action' AND entity_id = ? ORDER BY reference_id",
                (action_id,),
            ).fetchall()
        references = {(row["reference_id"], row["reference_kind"]) for row in rows}
        self.assertIn((f"run-closeout:{spec.run_id}", "input"), references)
        self.assertIn((f"outcome:{spec.run_id}", "outcome"), references)

    def test_ledger_is_first_parent_add_only_across_two_run_pairs(self):
        fixture = OutcomeFixture(self)
        first, first_result = fixture.ready_run()
        StagedRunEngine(fixture.assembly).close(
            first.run_id, fixture.outcome_bytes(first, first_result))
        second, second_result = fixture.ready_run()
        StagedRunEngine(fixture.assembly).close(
            second.run_id, fixture.outcome_bytes(second, second_result))

        entries = read_outcome_ledger(fixture.root)
        self.assertEqual(
            [entry.outcome.run_id for entry in entries], [first.run_id, second.run_id])
        tip = entries[-1].commit_oid
        first_path = f"docs/runs/{first.run_id}/outcome.yaml"
        present = subprocess.run(
            ["git", "-C", str(fixture.root), "cat-file", "-e", f"{tip}:{first_path}"],
            check=False,
        )
        self.assertEqual(present.returncode, 0)

    def test_digest_tamper_in_ledger_pair_is_rejected(self):
        fixture = OutcomeFixture(self)
        spec, result = fixture.ready_run()
        first = StagedRunEngine(fixture.assembly).close(
            spec.run_id, fixture.outcome_bytes(spec, result))
        forged_id = new_run_id()
        outcome = yaml.safe_dump({
            **parse_outcome_delta_bytes(fixture.outcome_bytes(spec, result)).to_dict(),
            "run_id": forged_id,
        }, sort_keys=False).encode()
        closeout = yaml.safe_dump({
            "schema": "waystone-run-closeout-1",
            "run_id": forged_id,
            "final_run_spec_digest": spec.run_spec_digest,
            "lifecycle_stage": "explore",
            "result_digest": result.digest,
            "completion_contract_digest": spec.job_input.completion_contract.digest,
            "assurance_plan_digest": spec.assurance_plan.digest,
            "completion_evidence_refs": [{
                "reference_id": "forged-result", "digest": result.digest}],
            "outcome_digest": "sha256:" + "0" * 64,
            "publication_action_id": f"{forged_id}:outcome-publication",
        }, sort_keys=False).encode()
        forged = outcome_module._prepare_ledger_commit(  # noqa: SLF001
            fixture.root, first.commit_oid, forged_id, closeout, outcome)
        subprocess.run([
            "git", "-C", str(fixture.root), "update-ref",
            "refs/waystone/outcomes", forged, first.commit_oid,
        ], check=True)

        with self.assertRaises(OutcomeLedgerRefusal):
            read_outcome_ledger(fixture.root)

    def test_evaluate_property_claim_without_verifier_evidence_is_refused(self):
        objective = self._objective()
        body = {
            "schema": "waystone-outcome-delta-1",
            "run_id": new_run_id(),
            "run_spec_digest": self._digest(1),
            "lifecycle_stage": "evaluate",
            "objective_ref": objective,
            "kind": "validated-decision",
            "summary": "Candidate A is better.",
            "result_digest": self._digest(2),
            "evidence_refs": [{
                "kind": "worker-proposal",
                "reference_id": "worker-result:proposal",
                "digest": self._digest(3),
            }],
            "finding_refs": [],
            "recorded_by": {
                "role": "coordinator", "binding_digest": self._digest(4),
                "principal": None,
            },
            "rationale": "Worker-reported comparison.",
        }
        with self.assertRaisesRegex(OutcomeSchemaRefusal, "verifier-evidence"):
            parse_outcome_delta_bytes(yaml.safe_dump(body, sort_keys=False).encode())

    def test_failed_ledger_cas_records_closeout_incomplete_audit(self):
        fixture = OutcomeFixture(self)
        spec, result = fixture.ready_run()

        def race(stage, _plan):
            if stage == "after-effect-intent":
                subprocess.run([
                    "git", "-C", str(fixture.root), "update-ref",
                    "refs/waystone/outcomes", fixture.head,
                ], check=True)

        with mock.patch.object(
                fixture.assembly.effect_executor, "_effect_fault_point", side_effect=race):
            with self.assertRaises(CloseoutIncomplete) as raised:
                StagedRunEngine(fixture.assembly).close(
                    spec.run_id, fixture.outcome_bytes(spec, result))

        self.assertIsNotNone(raised.exception.audit_digest)
        self.assertEqual(
            fixture.assembly.store.get_run(spec.run_id).state, "closeout-ready")
        with fixture.assembly.store._connection_lock:  # noqa: SLF001
            row = fixture.assembly.store._connection.execute(  # noqa: SLF001
                "SELECT reference_id FROM artifacts WHERE reference_id LIKE ?",
                (f"closeout-incomplete:{spec.run_id}:%",),
            ).fetchone()
        self.assertIsNotNone(row)

    def test_status_does_not_call_zero_delta_progress_and_advises_only_after_repeat(self):
        fixture = OutcomeFixture(self)
        first, first_result = fixture.ready_run()
        StagedRunEngine(fixture.assembly).close(
            first.run_id, fixture.outcome_bytes(first, first_result))
        one = project_status_json(project_status_projection(
            fixture.root, fixture.assembly.store))
        self.assertFalse(one["outcome"]["last_delta"]["progress"])
        self.assertIsNone(one["advisory"])

        fixture.root.joinpath("tasks.yaml").write_text(
            "version: 1\nproject: demo\ntasks:\n"
            "  - {id: feat/semantic-brief, title: Explore, status: pending}\n"
            "  - {id: feat/one, title: One, status: done}\n"
            "  - {id: feat/two, title: Two, status: done}\n",
            encoding="utf-8",
        )
        second, second_result = fixture.ready_run()
        StagedRunEngine(fixture.assembly).close(
            second.run_id, fixture.outcome_bytes(second, second_result))
        two = project_status_json(project_status_projection(
            fixture.root, fixture.assembly.store))

        self.assertFalse(two["outcome"]["last_delta"]["progress"])
        self.assertIsNone(two["outcome"]["last_positive_delta"])
        self.assertEqual(two["advisory"]["reason"], "project-direction-may-be-stale")
        self.assertEqual(len(two["advisory"]["evidence"]), 2)
        self.assertEqual(two["audit"]["tasks"], {"done": 2, "pending": 1})
        output = io.StringIO()
        with mock.patch.object(
                status_group, "resolve_project_context", return_value=fixture.context), \
                contextlib.redirect_stdout(output):
            self.assertEqual(status_group.main(["--json"]), 0)
        cli = json.loads(output.getvalue())
        self.assertEqual(cli["outcome"]["last_delta"]["kind"], "no-objective-delta")
        self.assertIn("audit", cli)
        conflict = SimpleNamespace(
            commit_oid="a" * 40,
            outcome=SimpleNamespace(
                run_id=new_run_id(),
                kind="no-objective-delta",
                objective_ref={},
                evidence_refs=(SimpleNamespace(
                    kind="owner-conflict", reference_id="owner-feedback:1",
                    digest=self._digest(9)),),
            ),
        )
        explicit = observe_module._direction_advisory((conflict,))  # noqa: SLF001
        self.assertEqual(explicit["evidence"][0]["kind"], "owner-conflict")
        self.assertFalse(explicit["gate"])

    @staticmethod
    def _digest(value: int) -> str:
        return "sha256:" + f"{value:064x}"

    @classmethod
    def _objective(cls):
        return {
            "kind": "project-fact",
            "commit": "1" * 40,
            "path": "PROJECT_BRIEF.md",
            "fact_id": "hypothesis/solver",
            "fact_digest": cls._digest(5),
            "binding": "nonbinding",
        }


if __name__ == "__main__":
    unittest.main(verbosity=2)
