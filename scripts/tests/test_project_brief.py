from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from waystone.project import brief, load_config
from waystone.runs.artifacts import ArtifactStore


def project_brief(status: str = "committed") -> bytes:
    return f"""---
schema: waystone-project-brief-1
status: {status}
---
# Demo

## Purpose
의미 있는 목적 설명.

## Commitments
- [commitment/primary-user] 연구자

## Prototype scope
- [prototype/first-result] 첫 결과
  - 결과의 세부 범위

## Long-term direction
- [long-term/future-scale] 나중에 확장

## Non-goals
- [non-goal/not-platform] 플랫폼 아님

## Working hypotheses
- [hypothesis/solver-family] solver A가 적합할 수 있음

## Open questions
- [question/accuracy] 필요한 정확도는 미정

## Revision triggers
- [trigger/user-conflict] 사용자 피드백 충돌
""".encode("utf-8")


class ProjectBriefTests(unittest.TestCase):
    def test_fact_spans_bind_exact_bytes_and_committed_authority(self):
        content = project_brief()
        frame = brief.parse_project_brief(content, commit="a" * 40)
        self.assertEqual(frame.status, "committed")
        self.assertEqual(len(frame.facts), 7)
        fact = frame.fact("prototype/first-result")
        self.assertEqual(content[fact.source_span.start_byte:fact.source_span.end_byte], fact.raw_bytes)
        self.assertEqual(fact.digest, "sha256:" + hashlib.sha256(fact.raw_bytes).hexdigest())
        self.assertIn("세부 범위".encode("utf-8"), fact.raw_bytes)
        self.assertEqual(fact.binding, "binding")
        self.assertEqual(frame.fact("hypothesis/solver-family").binding, "nonbinding")
        self.assertEqual(frame.fact_ref(fact.id).fact_digest, fact.digest)

    def test_marker_syntax_is_rejected_anywhere_not_just_fact_sections(self):
        malformed = project_brief().replace(
            "의미 있는 목적 설명.".encode(),
            "잘못 놓인 [commitment/BAD_ID] 표식.".encode(),
        )
        with self.assertRaises(brief.BriefMarkerRefusal):
            brief.parse_project_brief(malformed)

    def test_status_duplicate_and_missing_marker_have_typed_refusals(self):
        with self.subTest("status"), self.assertRaises(brief.BriefStatusRefusal):
            brief.parse_project_brief(project_brief("superseded"))
        duplicate = project_brief().replace(
            b"- [commitment/primary-user] ",
            b"- [commitment/primary-user] ",
        ).replace(
            b"- [prototype/first-result] first", b"- [prototype/first-result] first"
        )
        duplicate = duplicate.replace(
            "- [prototype/first-result] 첫 결과".encode(),
            "- [prototype/first-result] 첫 결과\n- [prototype/first-result] 중복".encode(),
        )
        with self.subTest("duplicate"), self.assertRaises(brief.BriefDuplicateRefusal):
            brief.parse_project_brief(duplicate)
        missing = project_brief().replace(
            "- [question/accuracy] 필요한 정확도는 미정".encode(),
            "- 필요한 정확도는 미정".encode(),
        )
        with self.subTest("missing"), self.assertRaises(brief.BriefMarkerRefusal):
            brief.parse_project_brief(missing)

    def test_adopt_preserves_and_binds_owner_evidence_before_status_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".waystone.yml").write_text(
                "version: 1\nproject: demo\nbrief: PROJECT_BRIEF.md\n", encoding="utf-8")
            (root / "PROJECT_BRIEF.md").write_bytes(project_brief("provisional"))
            evidence = "사용자 확인: 이 brief를 채택합니다.\n".encode("utf-8")
            result = brief.adopt_project_brief(root, evidence)
            store = ArtifactStore(root)
            self.assertEqual(store.read(result.owner_evidence.digest), evidence)
            record = json.loads(store.read(result.adoption_record.digest))
            self.assertEqual(record["owner_evidence"]["digest"], result.owner_evidence.digest)
            self.assertEqual(record["after_digest"], "sha256:" + hashlib.sha256(
                (root / "PROJECT_BRIEF.md").read_bytes()).hexdigest())
            self.assertEqual(brief.read_project_frame(root).status, "committed")

    def test_superseded_status_is_derived_from_git_ancestry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".waystone.yml").write_text(
                "version: 1\nproject: demo\nbrief: PROJECT_BRIEF.md\n", encoding="utf-8")
            source = root / "PROJECT_BRIEF.md"
            source.write_bytes(project_brief())
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            subprocess.run(["git", "add", ".waystone.yml", "PROJECT_BRIEF.md"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "first"], cwd=root, check=True)
            first = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, check=True,
                stdout=subprocess.PIPE, text=True,
            ).stdout.strip()
            source.write_bytes(project_brief().replace(b"# Demo", b"# Demo revised"))
            subprocess.run(["git", "add", "PROJECT_BRIEF.md"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "second"], cwd=root, check=True)
            second = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, check=True,
                stdout=subprocess.PIPE, text=True,
            ).stdout.strip()
            historical = brief.read_project_frame_at_commit(
                root, first, current_commit=second)
            self.assertEqual(historical.status, "superseded")
            with self.assertRaises(brief.BriefStatusRefusal):
                historical.fact_ref("commitment/primary-user")

    def test_config_canonicalizes_brief_and_refuses_ssot_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / ".waystone.yml"
            config.write_text("version: 1\nproject: demo\n", encoding="utf-8")
            self.assertEqual(load_config(root)["brief"], "PROJECT_BRIEF.md")
            config.write_text("version: 1\nproject: demo\nssot: SSOT.md\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "canonical brief"):
                load_config(root)


if __name__ == "__main__":
    unittest.main()
