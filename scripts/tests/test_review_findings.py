from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from waystone.cli import review_group
from waystone.features import review_layout
from waystone.reviews import findings


class FindingChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.reviews = self.root / "docs/reviews"
        self.run_id = review_layout.new_run_id()
        self.finding_id = review_layout.new_run_id()
        self.lineage_id = review_layout.new_run_id()

    def tearDown(self):
        self.tmp.cleanup()

    def d(self, value: int) -> str:
        token = format(value, "x")
        return "sha256:" + (token * 64)[:64]

    def claim_payload(self):
        return {
            "schema": findings.CLAIM_SCHEMA, "finding_id": self.finding_id,
            "review_run_id": self.run_id,
            "target": {"run_spec_digest": self.d(1), "result_digest": self.d(2),
                        "review_artifact_digest": self.d(3)},
            "source_finding_id": "WS-GPT-001",
            "claim": "The bound result permits the failure mechanism.",
            "evidence": ["code observation"],
            "reviewer_assessment": {"impact": "major", "suggested_remediation": "repair local"},
            "reported_by": {"role": "reviewer", "binding_digest": self.d(4), "principal": None},
        }

    def validation_payload(self, claim_digest, **changes):
        row = {
            "schema": findings.VALIDATION_SCHEMA, "finding_id": self.finding_id,
            "finding_digest": claim_digest, "revision": 1, "supersedes_digest": None,
            "validity": "confirmed", "failure_mechanism": "X breaks because Y is reachable",
            "evidence_refs": [{"kind": "code", "digest": self.d(5)}],
            "validated_by": {"role": "coordinator", "binding_digest": self.d(6), "principal": None},
        }
        row.update(changes)
        return row

    def disposition_payload(self, claim_digest, validation_digest, **changes):
        row = {
            "schema": findings.DISPOSITION_SCHEMA, "finding_id": self.finding_id,
            "finding_digest": claim_digest, "confirmed_validation_digest": validation_digest,
            "revision": 1, "supersedes_digest": None,
            "objective_ref": {"kind": "project-fact", "commit": "a" * 40,
                              "path": "PROJECT_BRIEF.md", "fact_id": "commitment/outcome",
                              "fact_digest": self.d(7), "binding": "test-binding"},
            "lifecycle_stage": "explore",
            "applies_to": {"promotion_lineage_id": self.lineage_id,
                            "candidate_digest": self.d(8), "result_digest": self.d(9)},
            "impact": "major", "exposure": "edge", "relevance": "current-objective",
            "disposition": "fix-now", "remediation_scope": "local", "estimated_cost": "low",
            "rationale": "test ruling", "clearance": None,
            "decided_by": {"role": "coordinator", "binding_digest": self.d(10), "principal": None},
            "materialized_task_id": None,
        }
        row.update(changes)
        return row

    def test_immutable_claim_and_digest_bound_validation(self):
        claim = findings.write_claim(self.reviews, self.claim_payload())
        with self.assertRaises(findings.ImmutableArtifactConflict):
            findings.write_claim(self.reviews, dict(self.claim_payload(), claim="changed"))
        validation = findings.append_validation(
            self.reviews, self.run_id, self.finding_id, self.validation_payload(claim.digest))
        self.assertEqual(findings.validation_head(
            self.reviews, self.run_id, self.finding_id).digest, validation.digest)
        with self.assertRaises(findings.ChainConflict):
            findings.append_validation(
                self.reviews, self.run_id, self.finding_id,
                self.validation_payload(self.d(99), revision=2, supersedes_digest=validation.digest))

    def test_divergent_heads_are_typed_conflict(self):
        claim = findings.write_claim(self.reviews, self.claim_payload())
        first = findings.append_validation(
            self.reviews, self.run_id, self.finding_id, self.validation_payload(claim.digest))
        second = self.validation_payload(claim.digest, revision=2,
                                          supersedes_digest=first.digest,
                                          failure_mechanism="second head")
        review_layout.publish_finding_yaml(
            self.reviews, self.run_id, self.finding_id, review_layout.FINDING_VALIDATION, 2,
            findings.canonical_bytes(second))
        third = dict(second, failure_mechanism="third head")
        review_layout.publish_finding_yaml(
            self.reviews, self.run_id, self.finding_id, review_layout.FINDING_VALIDATION, 3,
            findings.canonical_bytes(third))
        with self.assertRaises(findings.DivergentHeadConflict):
            findings.validation_head(self.reviews, self.run_id, self.finding_id)

    def test_confirmed_major_accept_risk_does_not_materialize(self):
        (self.root / ".waystone.yml").write_text("version: 1\nproject: test\n")
        (self.root / "tasks.yaml").write_text("version: 1\nproject: test\ntasks: []\n")
        claim = findings.write_claim(self.reviews, self.claim_payload())
        validation = findings.append_validation(
            self.reviews, self.run_id, self.finding_id, self.validation_payload(claim.digest))
        findings.append_disposition(
            self.reviews, self.run_id, self.finding_id,
            self.disposition_payload(claim.digest, validation.digest,
                                      disposition="accept-risk", relevance="future"))
        with self.assertRaises(review_group.MaterializationRefused):
            review_group.materialize(self.root, self.run_id, self.finding_id)

    def test_q3_owner_only_boundaries(self):
        claim = findings.write_claim(self.reviews, self.claim_payload())
        validation = findings.append_validation(
            self.reviews, self.run_id, self.finding_id, self.validation_payload(claim.digest))
        for changes in ({"disposition": "accept-risk"}, {"remediation_scope": "architectural"}):
            with self.subTest(changes=changes), self.assertRaises(findings.OwnerDecisionRequired):
                findings.append_disposition(
                    self.reviews, self.run_id, self.finding_id,
                    self.disposition_payload(claim.digest, validation.digest, **changes))

    def test_promotion_clearance_is_structured_and_stale_disposition_cannot_materialize(self):
        (self.root / ".waystone.yml").write_text("version: 1\nproject: test\n")
        (self.root / "tasks.yaml").write_text("version: 1\nproject: test\ntasks: []\n")
        claim = findings.write_claim(self.reviews, self.claim_payload())
        validation = findings.append_validation(
            self.reviews, self.run_id, self.finding_id, self.validation_payload(claim.digest))
        initial = self.disposition_payload(
            claim.digest, validation.digest, disposition="fix-before-promotion",
            relevance="promotion-bound")
        first_disposition = findings.append_disposition(
            self.reviews, self.run_id, self.finding_id, initial)
        cleared = dict(initial)
        cleared.update({
            "revision": 2, "supersedes_digest": first_disposition.digest,
            "clearance": {"candidate_digest": self.d(14),
                           "supersedes_candidate_digest": self.d(15),
                           "verification_evidence_digest": self.d(16)},
        })
        findings.append_disposition(self.reviews, self.run_id, self.finding_id, cleared)
        newer = self.validation_payload(
            claim.digest, revision=2, supersedes_digest=validation.digest,
            failure_mechanism="new validation head")
        findings.append_validation(self.reviews, self.run_id, self.finding_id, newer)
        with self.assertRaises(findings.StaleDisposition):
            review_group.materialize(self.root, self.run_id, self.finding_id)

    def test_ingest_validate_disposition_and_materialize(self):
        (self.root / ".waystone.yml").write_text("version: 1\nproject: test\n")
        (self.root / "tasks.yaml").write_text("version: 1\nproject: test\ntasks: []\n")
        source = self.root / "feedback.yaml"
        source.write_bytes(yaml.safe_dump({
            "target": {"run_spec_digest": self.d(11), "result_digest": self.d(12)},
            "binding_digest": self.d(13),
            "findings": [{"source_finding_id": "WS-GPT-002",
                          "claim": "A confirmed failure mechanism", "evidence": ["reproduction"],
                          "impact": "major"}],
        }).encode())
        claim = review_group.ingest_feedback(self.root, self.run_id, source)[0]
        self.finding_id = claim.payload["finding_id"]
        validation_file = self.root / "validation.yaml"
        validation_file.write_bytes(findings.canonical_bytes(self.validation_payload(claim.digest)))
        validation = review_group.validate_file(
            self.root, self.run_id, claim.payload["finding_id"], validation_file)
        disposition_file = self.root / "disposition.yaml"
        disposition_file.write_bytes(findings.canonical_bytes(
            self.disposition_payload(claim.digest, validation.digest,
                                     disposition="fix-before-promotion", relevance="promotion-bound")))
        review_group.disposition_file(
            self.root, self.run_id, claim.payload["finding_id"], disposition_file)
        task_id = review_group.materialize(self.root, self.run_id, claim.payload["finding_id"])
        registry = yaml.safe_load((self.root / "tasks.yaml").read_text())
        self.assertEqual(registry["tasks"][0]["id"], task_id)
        head = findings.disposition_head(self.reviews, self.run_id, claim.payload["finding_id"])
        self.assertEqual(head.payload["materialized_task_id"], task_id)


if __name__ == "__main__":
    unittest.main()
