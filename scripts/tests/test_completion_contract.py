from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from waystone.jobs import completion
from waystone.project import brief
from waystone.runs.artifacts import ArtifactStore


def brief_bytes() -> bytes:
    return b"""---
schema: waystone-project-brief-1
status: committed
---
# Demo

## Purpose
Demo.

## Commitments
- [commitment/outcome] Produce the intended result.

## Prototype scope
- [prototype/first-result] Support one reproducible result.

## Long-term direction
- [long-term/scale] Scale later.

## Non-goals
- [non-goal/platform] Do not build a platform.

## Working hypotheses
- [hypothesis/solver] Solver A may work.

## Open questions
- [question/accuracy] Required accuracy is unknown.

## Revision triggers
- [trigger/user-conflict] Owner feedback conflicts.
"""


def init_project(root: Path) -> tuple[str, brief.ProjectFrame]:
    (root / ".waystone.yml").write_text(
        "version: 1\nproject: demo\nbrief: PROJECT_BRIEF.md\n", encoding="utf-8")
    (root / "PROJECT_BRIEF.md").write_bytes(brief_bytes())
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(["git", "add", ".waystone.yml", "PROJECT_BRIEF.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "brief"], cwd=root, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    return head, brief.read_project_frame_at_commit(root, head)


def criterion(source: dict, *, mode: str, kind: str = "measurement", binding: str = "nonbinding") -> dict:
    return {
        "id": "result",
        "mode": mode,
        "text": "Record the answer or candidate.",
        "source": source,
        "binding": binding,
        "evidence": {"kind": kind},
    }


class CompletionContractTests(unittest.TestCase):
    def test_closed_objective_union_and_learning_mode(self):
        with self.assertRaises(completion.AuthorityRefRefusal):
            completion.parse_objective_ref({"kind": "task", "id": "feat/not-authority"})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, frame = init_project(root)
            objective = frame.fact_ref("hypothesis/solver").to_dict()
            contract = completion.compile_completion_contract(
                root, "explore", objective,
                [criterion(objective, mode="learning")],
            )
            self.assertEqual(contract.to_dict()["schema"], completion.COMPLETION_CONTRACT_SCHEMA)
            self.assertEqual(contract.criteria[0].mode, completion.CompletionMode.LEARNING)
            self.assertRegex(contract.compiler_digest, r"^sha256:[0-9a-f]{64}$")
            parsed = completion.parse_completion_contract_bytes(
                root, contract.canonical_bytes())
            self.assertEqual(parsed, contract)

    def test_promotion_allows_committed_prototype_but_refuses_hypothesis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, frame = init_project(root)
            objective = frame.fact_ref("prototype/first-result").to_dict()
            contract = completion.compile_completion_contract(
                root, "promote", objective,
                [criterion(
                    objective,
                    mode="promotion",
                    kind="regression-contract",
                    binding="binding",
                )],
            )
            self.assertEqual(contract.lifecycle_stage, completion.LifecycleStage.PROMOTE)
            hypothesis = frame.fact_ref("hypothesis/solver").to_dict()
            with self.assertRaises(completion.StageModeRefusal):
                completion.compile_completion_contract(
                    root, "promote", objective,
                    [criterion(
                        hypothesis,
                        mode="promotion",
                        kind="regression-contract",
                        binding="binding",
                    )],
                )

    def test_promotion_reloads_cas_evaluation_evidence_for_pass_and_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, frame = init_project(root)
            store = ArtifactStore(root)
            candidate_digest = "sha256:" + "c" * 64
            evidence_body = {
                "schema": completion.EVALUATION_EVIDENCE_SCHEMA,
                "candidate_digest": candidate_digest,
                "evaluation_spec_digest": "sha256:" + "s" * 64,
                "evaluation_generation": 3,
                "evaluator_action_id": "evaluate:3",
                "result": "pass",
                "metric_artifacts": [],
            }
            # Replace the deliberately non-hex placeholder before canonical publication.
            evidence_body["evaluation_spec_digest"] = "sha256:" + "d" * 64
            evidence = store.write(completion.canonical_json(evidence_body))
            source = {
                "kind": "evaluation-evidence",
                "reference_id": "evaluation-evidence:3",
                "candidate_digest": candidate_digest,
                "generation": 3,
                "digest": evidence.digest,
            }
            objective = frame.fact_ref("prototype/first-result").to_dict()
            contract = completion.compile_completion_contract(
                root, "promote", objective,
                [criterion(source, mode="promotion", kind="verifier-evidence", binding="binding")],
                artifact_store=store,
            )
            self.assertEqual(contract.criteria[0].source.digest, evidence.digest)

            failed_body = dict(evidence_body)
            failed_body["result"] = "fail"
            failed = store.write(completion.canonical_json(failed_body))
            failed_source = dict(source, digest=failed.digest)
            with self.assertRaises(completion.EvaluationEvidenceRefusal):
                completion.compile_completion_contract(
                    root, "promote", objective,
                    [criterion(
                        failed_source,
                        mode="promotion",
                        kind="verifier-evidence",
                        binding="binding",
                    )],
                    artifact_store=store,
                )


if __name__ == "__main__":
    unittest.main()
