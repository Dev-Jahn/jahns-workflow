from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from waystone.features.review_layout import new_run_id
from waystone.jobs import completion, work_brief
from waystone.project import brief
from waystone.runs.artifacts import ArtifactStore


def project_bytes() -> bytes:
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
- [prototype/first-result] Support one result.

## Long-term direction
- [long-term/scale] Scale later.

## Non-goals
- [non-goal/no-platform] Do not build a platform.

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
    (root / "PROJECT_BRIEF.md").write_bytes(project_bytes())
    (root / "src.py").write_text("baseline = False\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(["git", "add", ".waystone.yml", "PROJECT_BRIEF.md", "src.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    return head, brief.read_project_frame_at_commit(root, head)


def item(text: str, provenance: str, *, source: dict | None = None, sources: list[dict] | None = None) -> dict:
    row = {"text": text, "provenance": provenance}
    if source is not None:
        row["source"] = source
    else:
        row["sources"] = sources or []
    return row


def completion_contract(root: Path, frame: brief.ProjectFrame) -> completion.CompletionContract:
    objective = frame.fact_ref("hypothesis/solver").to_dict()
    return completion.compile_completion_contract(root, "explore", objective, [{
        "id": "candidate-produced",
        "mode": "learning",
        "text": "Record the answer or candidate.",
        "source": objective,
        "binding": "nonbinding",
        "evidence": {"kind": "candidate"},
    }])


def payload(head: str, frame: brief.ProjectFrame, brief_id: str) -> dict:
    hypothesis = frame.fact_ref("hypothesis/solver").to_dict()
    commitment = frame.fact_ref("commitment/outcome").to_dict()
    non_goal = frame.fact_ref("non-goal/no-platform").to_dict()
    question = frame.fact_ref("question/accuracy").to_dict()
    source_digest = "sha256:" + hashlib.sha256(b"baseline = False\n").hexdigest()
    evidence_digest = "sha256:" + "e" * 64
    return {
        "schema": work_brief.WORK_BRIEF_SCHEMA,
        "brief_id": brief_id,
        "task_id": "feat/semantic-brief",
        "revision": 1,
        "supersedes_digest": None,
        "resolves_context_request_digest": None,
        "lifecycle_stage": "explore",
        "objective": {
            "ref": hypothesis,
            "desired_delta": "Measure two candidate approaches.",
            "why_now": item(
                "The current uncertainty blocks the first supported result.",
                "coordinator-summary",
                sources=[hypothesis],
            ),
        },
        "current_state": [item(
            "The baseline currently fails the representative input.",
            "harness-observation",
            source={"kind": "git", "commit": head, "path": "src.py", "digest": source_digest},
        )],
        "decisions": {
            "fixed": [item("Preserve the intended outcome.", "owner-source", source=commitment)],
            "worker_may_choose": [item(
                "Choose the smallest sound comparison method.", "coordinator-summary", sources=[])],
            "requires_escalation": [item(
                "Do not turn this into a platform.", "owner-source", source=non_goal)],
        },
        "constraints": [item("Keep the public seam stable.", "owner-source", source=commitment)],
        "non_goals": [item(
            "Distributed scheduling is outside this work.",
            "coordinator-summary",
            sources=[{"kind": "owner-artifact", "digest": "sha256:" + "a" * 64}],
        )],
        "known_failures": [item(
            "The baseline failure is reproduced.",
            "harness-observation",
            source={"kind": "evidence", "digest": evidence_digest},
        )],
        "evidence_expected": [{"criterion_id": "candidate-produced", "kind": "candidate"}],
        "references": [{
            "path": "src.py",
            "anchor": "baseline",
            "digest": source_digest,
            "purpose": "Current implementation seam.",
        }],
        "open_questions": [item(
            "Required accuracy remains owner-unresolved.",
            "coordinator-summary",
            sources=[question],
        )],
    }


class WorkBriefTests(unittest.TestCase):
    def test_semantic_prompt_has_seven_sections_and_no_bookkeeping_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            head, frame = init_project(root)
            contract = completion_contract(root, frame)
            raw = completion.canonical_json(payload(head, frame, new_run_id()))
            published = work_brief.publish_work_brief(
                root, raw, completion_contract=contract)
            prompt = work_brief.render_semantic_prompt(published.brief, contract)
            self.assertEqual(len(re.findall(r"(?m)^## ", prompt)), 7)
            for expected in (
                "Why this matters", "baseline currently fails", "Measure two candidate",
                "Preserve the intended outcome", "Choose the smallest", "project-fact sha256:",
                "interpretation, not owner authority",
            ):
                self.assertIn(expected, prompt)
            for forbidden in (
                "tasks.yaml", "round", "overlay", "lease", "retry", "transition",
                "artifact filename",
            ):
                self.assertNotIn(forbidden, prompt.lower())

    def test_every_provenance_source_must_be_digest_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            head, frame = init_project(root)
            body = payload(head, frame, new_run_id())
            body["current_state"][0]["source"] = {"kind": "evidence"}
            with self.assertRaises(work_brief.ProvenanceRefusal):
                work_brief.parse_work_brief_bytes(completion.canonical_json(body))

    def test_revision_loads_actual_immediate_predecessor_from_cas(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            head, frame = init_project(root)
            store = ArtifactStore(root)
            lineage_id = new_run_id()
            first_body = payload(head, frame, lineage_id)
            first = work_brief.publish_work_brief(
                root,
                completion.canonical_json(first_body),
                artifact_store=store,
            )
            second_body = payload(head, frame, lineage_id)
            second_body.update({
                "revision": 2,
                "supersedes_digest": first.artifact.digest,
                "resolves_context_request_digest": "sha256:" + "c" * 64,
            })
            second = work_brief.publish_work_brief(
                root,
                completion.canonical_json(second_body),
                artifact_store=store,
                context_resume=True,
            )
            self.assertEqual(second.brief.revision, 2)

            foreign = payload(head, frame, new_run_id())
            foreign_artifact = store.write(completion.canonical_json(foreign))
            second_body["supersedes_digest"] = foreign_artifact.digest
            with self.assertRaises(work_brief.WorkBriefLineageRefusal):
                work_brief.publish_work_brief(
                    root,
                    completion.canonical_json(second_body),
                    artifact_store=store,
                    context_resume=True,
                )

    def test_owner_source_ingress_preserves_exact_bytes_and_checks_declared_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_project(root)
            content = b"exact owner request\n"
            digest = "sha256:" + hashlib.sha256(content).hexdigest()
            imported = work_brief.import_owner_source_bytes(
                root,
                content,
                reference_id="owner-request:one",
                declared_digest=digest,
            )
            self.assertEqual(ArtifactStore(root).read(imported.artifact.digest), content)
            with self.assertRaises(work_brief.OwnerSourceIngressRefusal):
                work_brief.import_owner_source_bytes(
                    root,
                    content,
                    reference_id="owner-request:wrong",
                    declared_digest="sha256:" + "0" * 64,
                )


if __name__ == "__main__":
    unittest.main()
