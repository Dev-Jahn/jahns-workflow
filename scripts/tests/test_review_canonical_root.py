#!/usr/bin/env python3
"""Canonical ProjectContext authority contracts for the public review surface."""
from __future__ import annotations

from support import *  # noqa: F401,F403

import contextlib
import io
import json
from unittest import mock

from test_work_brief import init_project
from waystone.cli import review_group
from waystone.features import review_layout
from waystone.project import tasks_cli
from waystone.reviews import findings


class ReviewCanonicalRootTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        _head, self.frame = init_project(self.root)
        (self.root / "tasks.yaml").write_text(
            "version: 1\nproject: demo\ntasks: []\n", encoding="utf-8")
        self.reviews = self.root / "docs/reviews"
        self.run_id = review_layout.new_run_id()
        self.finding_id = review_layout.new_run_id()
        self.lineage_id = review_layout.new_run_id()
        claim = findings.write_claim(self.reviews, self._claim_payload())
        validation = findings.append_validation(
            self.reviews,
            self.run_id,
            self.finding_id,
            self._validation_payload(claim.digest),
            root=self.root,
        )
        disposition = findings.append_disposition(
            self.reviews,
            self.run_id,
            self.finding_id,
            self._disposition_payload(claim.digest, validation.digest),
            root=self.root,
        )
        self.disposition_digest = disposition.digest
        git(self.root, "add", "tasks.yaml", "docs/reviews")
        self.assertEqual(git(self.root, "commit", "-qm", "record review finding").returncode, 0)

        self.linked = self.base / "linked"
        self.assertEqual(
            git(
                self.root,
                "worktree",
                "add",
                "-q",
                "-b",
                "stale-review",
                str(self.linked),
            ).returncode,
            0,
        )
        brief_path = self.root / "PROJECT_BRIEF.md"
        brief_path.write_bytes(brief_path.read_bytes().replace(
            b"Produce the intended result.",
            b"Produce the canonical revised result.",
        ))
        git(self.root, "add", "PROJECT_BRIEF.md")
        self.assertEqual(git(self.root, "commit", "-qm", "revise canonical objective").returncode, 0)

        self.machine = self.base / "machine"
        self.machine.mkdir()
        self.machine.joinpath("projects.json").write_text(json.dumps({"projects": [{
            "project_id": "project:review-canonical-root",
            "name": "demo",
            "path": str(self.root.resolve()),
        }]}), encoding="utf-8")
        self.next_disposition = self.base / "next-disposition.yaml"
        self.next_disposition.write_bytes(findings.canonical_bytes(self._disposition_payload(
            claim.digest,
            validation.digest,
            revision=2,
            supersedes_digest=self.disposition_digest,
        )))

    @staticmethod
    def _digest(value: int) -> str:
        token = format(value, "x")
        return "sha256:" + (token * 64)[:64]

    def _claim_payload(self) -> dict:
        return {
            "schema": findings.CLAIM_SCHEMA,
            "finding_id": self.finding_id,
            "review_run_id": self.run_id,
            "target": {
                "run_spec_digest": self._digest(1),
                "result_digest": self._digest(2),
                "review_artifact_digest": self._digest(3),
            },
            "source_finding_id": "WS-GPT-028",
            "claim": "A linked checkout can reuse stale project authority.",
            "evidence": ["linked worktree topology"],
            "reviewer_assessment": {
                "impact": "major",
                "suggested_remediation": "resolve canonical context first",
            },
            "reported_by": {
                "role": "reviewer",
                "binding_digest": self._digest(4),
                "principal": None,
            },
        }

    def _validation_payload(self, claim_digest: str) -> dict:
        return {
            "schema": findings.VALIDATION_SCHEMA,
            "finding_id": self.finding_id,
            "finding_digest": claim_digest,
            "revision": 1,
            "supersedes_digest": None,
            "validity": "confirmed",
            "failure_mechanism": "The public review root follows the linked checkout HEAD.",
            "evidence_refs": [self.frame.fact_ref("commitment/outcome").to_dict()],
            "validated_by": {
                "role": "coordinator",
                "binding_digest": self._digest(5),
                "principal": None,
            },
        }

    def _disposition_payload(
            self,
            claim_digest: str,
            validation_digest: str,
            **changes,
    ) -> dict:
        row = {
            "schema": findings.DISPOSITION_SCHEMA,
            "finding_id": self.finding_id,
            "finding_digest": claim_digest,
            "confirmed_validation_digest": validation_digest,
            "revision": 1,
            "supersedes_digest": None,
            "objective_ref": self.frame.fact_ref("commitment/outcome").to_dict(),
            "lifecycle_stage": "explore",
            "applies_to": {
                "promotion_lineage_id": self.lineage_id,
                "candidate_digest": self._digest(6),
                "result_digest": self._digest(7),
            },
            "impact": "major",
            "exposure": "edge",
            "relevance": "current-objective",
            "disposition": "fix-now",
            "remediation_scope": "local",
            "estimated_cost": "low",
            "rationale": "repair the canonical review authority path",
            "clearance": None,
            "decided_by": {
                "role": "coordinator",
                "binding_digest": self._digest(8),
                "principal": None,
            },
            "materialized_task_id": None,
        }
        row.update(changes)
        return row

    @staticmethod
    def _tracked_review_bytes(root: Path) -> dict[str, bytes]:
        paths = [root / "tasks.yaml"]
        reviews = root / "docs/reviews"
        if reviews.is_dir():
            paths.extend(path for path in reviews.rglob("*") if path.is_file())
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(paths)
        }

    @contextlib.contextmanager
    def _runtime(self, cwd: Path):
        old = Path.cwd()
        stderr = io.StringIO()
        try:
            os.chdir(cwd)
            with mock.patch.dict(os.environ, {"WAYSTONE_HOME": str(self.machine)}), \
                    contextlib.redirect_stderr(stderr):
                yield stderr
        finally:
            os.chdir(old)

    def _assert_linked_refusal(self, argv: list[str], *, cwd: Path | None = None) -> None:
        before = {
            "canonical": self._tracked_review_bytes(self.root),
            "linked": self._tracked_review_bytes(self.linked),
        }
        with self._runtime(self.linked if cwd is None else cwd) as stderr:
            result = review_group.main(argv)
        self.assertEqual(result, 1)
        self.assertIn("canonical_root_is_linked_worktree", stderr.getvalue())
        self.assertEqual(self._tracked_review_bytes(self.root), before["canonical"])
        self.assertEqual(self._tracked_review_bytes(self.linked), before["linked"])

    def test_p1_review_cli_uses_one_project_context_front_door(self):
        source = Path(review_group.__file__).read_text(encoding="utf-8")
        self.assertIn("resolve_project_context", source)
        self.assertNotIn("find_project_root", source)
        self.assertNotIn("Path(value).resolve()", source)
        self.assertEqual(source.count("context = _review_context("), 2)
        commands = (
            ["ingest", self.run_id, "--file", str(self.next_disposition)],
            [
                "validate", self.finding_id, "--run-id", self.run_id,
                "--file", str(self.next_disposition),
            ],
            [
                "disposition", self.finding_id, "--run-id", self.run_id,
                "--file", str(self.next_disposition),
            ],
            ["materialize", self.finding_id, "--run-id", self.run_id],
            ["attach", self.run_id, review_layout.new_run_id()],
        )
        for argv in commands:
            with self.subTest(command=argv[0]):
                self._assert_linked_refusal(argv)

    def test_p2_linked_cwd_refuses_stale_disposition_and_materialize_without_writes(self):
        self._assert_linked_refusal([
            "disposition",
            self.finding_id,
            "--run-id",
            self.run_id,
            "--file",
            str(self.next_disposition),
        ])
        self._assert_linked_refusal([
            "materialize",
            self.finding_id,
            "--run-id",
            self.run_id,
        ])

    def test_p3_explicit_linked_root_is_a_typed_refusal(self):
        self._assert_linked_refusal([
            "materialize",
            self.finding_id,
            "--run-id",
            self.run_id,
            "--root",
            str(self.linked),
        ], cwd=self.root)

    def test_p4_materialize_requires_canonical_project_context_proof(self):
        before = self._tracked_review_bytes(self.linked)
        with mock.patch.object(tasks_cli, "cmd_add") as cmd_add, \
                self.assertRaises(review_group.MaterializationRefused):
            review_group.materialize(self.linked, self.run_id, self.finding_id)
        cmd_add.assert_not_called()
        self.assertEqual(self._tracked_review_bytes(self.linked), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
