#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Integration tests for the jahns-workflow v0.2.0 correctness kernel.

Run: uv run scripts/tests/run_tests.py
Covers the deterministic core: merge-gate computation, review-cycle marker emit/parse/classify,
SHA-bound approval logic, tasks gate counts, remote push verification (real temp git repos),
and config review-mode validation. No network / no gh required.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import jw_common  # noqa: E402
import jw_lanes  # noqa: E402
import jw_merge  # noqa: E402
import jw_review  # noqa: E402
import jw_round  # noqa: E402


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def init_repo(root: Path):
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    (root / "f.txt").write_text("0")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "c0")


class MarkerTests(unittest.TestCase):
    def test_emit_parse_roundtrip(self):
        s = jw_review.emit_marker("review-cycle", {"round_id": "2026-06-15-x", "cycle": 1,
                                                   "target_sha": "a" * 40, "reviewers": ["codex", "gpt-5.5-pro"]})
        got = jw_review.parse_markers(s)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["_kind"], "review-cycle")
        self.assertEqual(got[0]["cycle"], 1)
        self.assertEqual(got[0]["target_sha"], "a" * 40)

    def test_latest_and_next_cycle(self):
        text = (jw_review.emit_marker("review-cycle", {"cycle": 1, "target_sha": "a" * 40})
                + "\n" + jw_review.emit_marker("review-cycle", {"cycle": 2, "target_sha": "b" * 40}))
        ms = jw_review.parse_markers(text)
        self.assertEqual(jw_review.latest_cycle(ms)["cycle"], 2)
        self.assertEqual(jw_review.next_cycle_number(ms), 3)
        self.assertEqual(jw_review.next_cycle_number([]), 1)

    def test_classify_fresh_vs_stale(self):
        head = "b" * 40
        # cycle frozen at a different sha => stale
        ms = jw_review.parse_markers(jw_review.emit_marker("review-cycle", {"cycle": 1, "target_sha": "a" * 40}))
        self.assertFalse(jw_review.classify(ms, head)["cycle_fresh"])
        # frozen at head => fresh
        ms = jw_review.parse_markers(jw_review.emit_marker("review-cycle", {"cycle": 1, "target_sha": head}))
        self.assertTrue(jw_review.classify(ms, head)["cycle_fresh"])

    def _bodies(self, head, *, reviewer="gpt-5.5-pro", cycle=1, verdict="shipped",
                approver="owner", decision=None):
        return [
            {"body": jw_review.emit_marker("review-cycle", {"cycle": 1, "target_sha": head}), "author": "owner"},
            {"body": jw_review.emit_marker("review-result", {"reviewer": reviewer, "review_cycle": cycle,
                                                             "reviewed_sha": head, "verdict": verdict,
                                                             "decision_required": decision or []}), "author": reviewer},
            {"body": jw_review.emit_marker("approval", {"sha": head, "by": approver}), "author": approver},
            {"body": jw_review.emit_marker("findings", {"cycle": 1, "resolved": True}), "author": "owner"},
        ]

    def test_classify_valid_binding(self):
        head = "c" * 40
        c = jw_review.classify(jw_review.parse_bodies(self._bodies(head)), head,
                               macro_reviewers=("gpt-5.5-pro",), approvers=("owner",))
        self.assertTrue(c["pro_result_at_head"])
        self.assertTrue(c["approved_at_head"])
        self.assertTrue(c["findings_resolved"])
        # different head invalidates all three (SHA-binding)
        c2 = jw_review.classify(jw_review.parse_bodies(self._bodies(head)), "d" * 40,
                                macro_reviewers=("gpt-5.5-pro",), approvers=("owner",))
        self.assertFalse(c2["pro_result_at_head"])
        self.assertFalse(c2["approved_at_head"])

    def test_classify_rejects_bad_provenance(self):
        head = "c" * 40
        mr, ap = ("gpt-5.5-pro",), ("owner",)
        # wrong reviewer
        c = jw_review.classify(jw_review.parse_bodies(self._bodies(head, reviewer="random-user")), head, macro_reviewers=mr, approvers=ap)
        self.assertFalse(c["pro_result_at_head"])
        # wrong cycle (result for cycle 99, latest is 1)
        c = jw_review.classify(jw_review.parse_bodies(self._bodies(head, cycle=99)), head, macro_reviewers=mr, approvers=ap)
        self.assertFalse(c["pro_result_at_head"])
        # not-shipped verdict
        c = jw_review.classify(jw_review.parse_bodies(self._bodies(head, verdict="not-shipped")), head, macro_reviewers=mr, approvers=ap)
        self.assertFalse(c["pro_result_at_head"])
        # decision required
        c = jw_review.classify(jw_review.parse_bodies(self._bodies(head, decision=["stop"])), head, macro_reviewers=mr, approvers=ap)
        self.assertFalse(c["pro_result_at_head"])
        # approval by untrusted author
        c = jw_review.classify(jw_review.parse_bodies(self._bodies(head, approver="anyone")), head, macro_reviewers=mr, approvers=ap)
        self.assertFalse(c["approved_at_head"])

    def test_fenced_marker_ignored(self):
        head = "c" * 40
        fenced = "```yaml\n" + jw_review.emit_marker("approval", {"sha": head, "by": "owner"}) + "\n```"
        self.assertEqual(jw_review.parse_markers(fenced), [])
        c = jw_review.classify(jw_review.parse_bodies([{"body": fenced, "author": "owner"}]), head, approvers=("owner",))
        self.assertFalse(c["approved_at_head"])

    def test_findings_resolved_strict_bool(self):
        # a non-True 'resolved' (e.g. arbitrary string) must not count as resolved
        m = jw_review.parse_markers(jw_review.emit_marker("findings", {"cycle": 1, "resolved": "maybe"}))
        c = jw_review.classify([{"_kind": "review-cycle", "cycle": 1, "target_sha": "x"}, *m], "x")
        self.assertFalse(c["findings_resolved"])

    def test_ci_strict(self):
        for bad in ("ACTION_REQUIRED", "NEUTRAL", "SKIPPED", "STALE", "WHATEVER"):
            self.assertEqual(jw_review.ci_state({"checks": [{"conclusion": bad}]}), "failing", bad)
        self.assertEqual(jw_review.ci_state({"checks": [{"conclusion": "SUCCESS"}]}), "passing")
        self.assertEqual(jw_review.ci_state({"checks": [{"conclusion": "PENDING"}]}), "pending")


PASS = dict(cycle_fresh=True, require_ci=True, ci="passing", want_codex=True, codex_fresh=True,
            findings_resolved=True, want_pro=True, pro_result_at_head=True, open_blockers=[],
            open_decisions=[], approved_at_head=True, remote_contains_head=None)


class MergeGateTests(unittest.TestCase):
    def test_all_pass(self):
        ok, fails = jw_merge.merge_gate(dict(PASS))
        self.assertTrue(ok, fails)
        self.assertEqual(fails, [])

    def test_each_condition_blocks(self):
        cases = {
            "cycle_fresh": (False, "stale"),
            "codex_fresh": (False, "Codex"),
            "findings_resolved": (False, "findings"),
            "pro_result_at_head": (False, "external"),
            "approved_at_head": (False, "approval"),
        }
        for key, (val, needle) in cases.items():
            g = dict(PASS); g[key] = val
            ok, fails = jw_merge.merge_gate(g)
            self.assertFalse(ok, key)
            self.assertTrue(any(needle.lower() in f.lower() for f in fails), (key, fails))

    def test_ci_only_blocks_when_required(self):
        g = dict(PASS); g["ci"] = "failing"
        self.assertFalse(jw_merge.merge_gate(g)[0])
        g["require_ci"] = False
        self.assertTrue(jw_merge.merge_gate(g)[0])
        # ci 'none' with require_ci blocks
        g2 = dict(PASS); g2["ci"] = "none"
        self.assertFalse(jw_merge.merge_gate(g2)[0])

    def test_blockers_and_decisions_block(self):
        g = dict(PASS); g["open_blockers"] = ["fix/x"]
        self.assertFalse(jw_merge.merge_gate(g)[0])
        g = dict(PASS); g["open_decisions"] = ["decision/y"]
        self.assertFalse(jw_merge.merge_gate(g)[0])

    def test_unpushed_local_head_blocks(self):
        g = dict(PASS); g["remote_contains_head"] = False
        self.assertFalse(jw_merge.merge_gate(g)[0])

    def test_gate_only_requires_configured_reviewers(self):
        # codex not wanted: a missing/false codex review must not block
        g = dict(PASS); g["want_codex"] = False; g["codex_fresh"] = False; g["findings_resolved"] = False
        self.assertTrue(jw_merge.merge_gate(g)[0], jw_merge.merge_gate(g)[1])
        # pro not wanted: a missing pro result must not block
        g = dict(PASS); g["want_pro"] = False; g["pro_result_at_head"] = False
        self.assertTrue(jw_merge.merge_gate(g)[0], jw_merge.merge_gate(g)[1])
        # but when wanted, they still block
        g = dict(PASS); g["want_codex"] = True; g["codex_fresh"] = False
        self.assertFalse(jw_merge.merge_gate(g)[0])

    def test_pr_state_and_head_read_block(self):
        g = dict(PASS); g["head_read_ok"] = False
        ok, fails = jw_merge.merge_gate(g)
        self.assertFalse(ok); self.assertTrue(any("PR head" in f for f in fails))
        for key, val in (("pr_state", "MERGED"), ("is_draft", True)):
            g = dict(PASS); g[key] = val
            self.assertFalse(jw_merge.merge_gate(g)[0], key)
        g = dict(PASS); g["base"] = "feature"; g["expected_base"] = "main"
        self.assertFalse(jw_merge.merge_gate(g)[0])


class TasksGateTests(unittest.TestCase):
    def test_counts(self):
        data = {"tasks": [
            {"id": "fix/a", "severity": "blocker", "status": "pending"},
            {"id": "fix/b", "severity": "blocker", "status": "done"},
            {"id": "decision/c", "status": "pending"},
            {"id": "decision/d", "status": "done"},
            {"id": "feat/e", "status": "active"},
        ]}
        c = jw_merge.tasks_gate_counts(data)
        self.assertEqual(c["open_blockers"], ["fix/a"])
        self.assertEqual(c["open_decisions"], ["decision/c"])


class RemoteTests(unittest.TestCase):
    def test_pushed_vs_unpushed(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            bare = d / "remote.git"
            work = d / "work"
            subprocess.run(["git", "init", "-q", "--bare", str(bare)])
            work.mkdir()
            init_repo(work)
            git(work, "remote", "add", "origin", str(bare))
            git(work, "push", "-q", "-u", "origin", "main")
            pushed, info = jw_common.head_pushed(work, fetch=True)
            self.assertTrue(pushed, info)
            # new local commit, not pushed
            (work / "f.txt").write_text("1")
            git(work, "commit", "-aqm", "c1")
            pushed2, info2 = jw_common.head_pushed(work, fetch=True)
            self.assertFalse(pushed2, info2)
            self.assertEqual(info2.get("behind"), 0)

    def test_no_upstream(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            init_repo(work)
            pushed, info = jw_common.head_pushed(work, fetch=False)
            self.assertFalse(pushed)
            self.assertIn("reason", info)

    def test_fetch_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            bare = d / "remote.git"; work = d / "work"
            subprocess.run(["git", "init", "-q", "--bare", str(bare)])
            work.mkdir(); init_repo(work)
            git(work, "remote", "add", "origin", str(bare))
            git(work, "push", "-q", "-u", "origin", "main")
            import shutil
            shutil.rmtree(bare)  # remote now unreachable
            pushed, info = jw_common.head_pushed(work, fetch=True)
            self.assertFalse(pushed)  # must NOT trust the stale ref
            self.assertIn("fetch failed", info.get("reason", ""))


class ConfigTests(unittest.TestCase):
    def _cfg(self, body: str) -> dict:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".jahns-workflow.yml").write_text(body)
            return jw_common.load_config(root)

    def test_default_review_mode_packet(self):
        cfg = self._cfg("version: 1\nproject: x\n")
        self.assertEqual(cfg["review"]["mode"], "packet")
        self.assertFalse(cfg["review"]["require_ci"])

    def test_pr_mode_ok(self):
        cfg = self._cfg("version: 1\nproject: x\nreview:\n  mode: pr\n  require_ci: true\n")
        self.assertEqual(cfg["review"]["mode"], "pr")
        self.assertTrue(cfg["review"]["require_ci"])

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            self._cfg("version: 1\nproject: x\nreview:\n  mode: bogus\n")


TASKS_FIXTURE = """# registry — comments must be preserved
version: 1
project: x
tasks:
  - id: feat/alpha
    title: "first task"
    status: active
    deps: []
  - id: gate/beta
    title: "a gate blocked on alpha"
    status: blocked
    deps: [feat/alpha]
"""


class TextSurgeryTests(unittest.TestCase):
    def test_set_existing_field(self):
        out = jw_round.set_task_field(TASKS_FIXTURE, "feat/alpha", "status", "done")
        self.assertIn("status: done", out)
        self.assertIn("# registry — comments must be preserved", out)  # comment preserved
        self.assertIn('title: "first task"', out)  # other fields intact
        self.assertEqual(out.count("status: active"), 0)

    def test_insert_missing_field(self):
        out = jw_round.set_task_field(TASKS_FIXTURE, "feat/alpha", "round", "2026-06-19-z")
        self.assertIn("round: 2026-06-19-z", out)
        # inserted into feat/a block, not gate/b
        a_block = out.split("gate/beta")[0]
        self.assertIn("round: 2026-06-19-z", a_block)

    def test_only_targets_named_task(self):
        out = jw_round.set_task_field(TASKS_FIXTURE, "gate/beta", "status", "done")
        self.assertIn("status: active", out)  # feat/a untouched
        self.assertEqual(out.count("status: done"), 1)

    def test_missing_task_raises(self):
        with self.assertRaises(KeyError):
            jw_round.set_task_field(TASKS_FIXTURE, "feat/nope", "status", "done")

    def test_set_config_scalar_nested(self):
        cfg = "version: 1\nstate:\n  last_audit_commit: null\n  last_round_commit: null\n"
        out = jw_round.set_config_scalar(cfg, "last_round_commit", "abc123")
        self.assertIn("  last_round_commit: abc123", out)
        self.assertIn("  last_audit_commit: null", out)  # sibling preserved
        with self.assertRaises(KeyError):
            jw_round.set_config_scalar(cfg, "nonexistent_key", "v")


class NextActionableTests(unittest.TestCase):
    def test_deps_gate(self):
        data = {"tasks": [
            {"id": "feat/a", "title": "A", "status": "done"},
            {"id": "feat/b", "title": "B", "status": "pending", "deps": ["feat/a"]},
            {"id": "feat/c", "title": "C", "status": "pending", "deps": ["feat/b"]},  # dep b not done
            {"id": "feat/d", "title": "D", "status": "active", "deps": []},
            {"id": "gate/e", "title": "E", "status": "blocked", "deps": ["feat/a"]},  # stale-blocked
        ]}
        got = dict(jw_common.next_actionable(data))
        self.assertIn("feat/b", got)   # dep a done
        self.assertIn("feat/d", got)   # no deps
        self.assertIn("gate/e", got)   # stale-blocked: dep a done → actionable now
        self.assertNotIn("feat/c", got)  # dep b not done
        self.assertNotIn("feat/a", got)  # already done


class LaneTests(unittest.TestCase):
    def test_contains_base(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            init_repo(root)
            base = git(root, "rev-parse", "HEAD").stdout.strip()
            git(root, "checkout", "-q", "-b", "feat/foo")
            (root / "g.txt").write_text("1"); git(root, "add", "-A"); git(root, "commit", "-qm", "c1")
            self.assertEqual(jw_lanes.check_lane(root, "feat/foo", {"branch": "feat/foo", "base_sha": base}), [])
            # a base the branch does NOT contain: make an unrelated commit on a sibling branch
            git(root, "checkout", "-q", "main")
            (root / "h.txt").write_text("2"); git(root, "add", "-A"); git(root, "commit", "-qm", "sib")
            sib = git(root, "rev-parse", "HEAD").stdout.strip()
            fails = jw_lanes.check_lane(root, "feat/foo", {"branch": "feat/foo", "base_sha": sib})
            self.assertTrue(fails and "does NOT contain" in fails[0])

    def test_missing_branch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            init_repo(root)
            base = git(root, "rev-parse", "HEAD").stdout.strip()
            fails = jw_lanes.check_lane(root, "t", {"branch": "no/such", "base_sha": base})
            self.assertTrue(fails and "does not exist" in fails[0])

    def test_done_lane_with_deleted_branch_not_verified(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            init_repo(root)
            (root / ".jahns-workflow.yml").write_text("version: 1\nproject: x\n")
            (root / "tasks.yaml").write_text(
                "version: 1\nproject: x\ntasks:\n"
                "  - id: feat/old-lane\n    title: 'a merged & cleaned-up lane'\n    status: done\n"
                "    lane:\n      branch: deleted/gone\n      base_sha: deadbeef\n")
            self.assertEqual(jw_lanes.verify(root), 0)  # done lane skipped, not a permanent failure


class RoundCloseTests(unittest.TestCase):
    def test_close_integration(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            init_repo(root)
            (root / ".jahns-workflow.yml").write_text(
                "version: 1\nproject: x\nstate:\n  last_audit_commit: null\n  last_round_commit: null\n")
            (root / "tasks.yaml").write_text(TASKS_FIXTURE)
            git(root, "add", "-A"); git(root, "commit", "-qm", "setup")
            rc = jw_round.close(root, "2026-06-19-z", done=["feat/alpha"], touched=["gate/beta"], commit="HEAD")
            self.assertEqual(rc, 0)
            txt = (root / "tasks.yaml").read_text()
            # feat/a flipped to done and stamped
            a = txt.split("gate/beta")[0]
            self.assertIn("status: done", a)
            self.assertIn("round: 2026-06-19-z", a)
            # gate/b stamped with round but NOT flipped to done
            b = "gate/beta" + txt.split("gate/beta")[1]
            self.assertIn("round: 2026-06-19-z", b)
            self.assertIn("status: blocked", b)
            # comment preserved, ROADMAP generated, watermark advanced
            self.assertIn("# registry — comments must be preserved", txt)
            self.assertTrue((root / "ROADMAP.md").is_file())
            head = git(root, "rev-parse", "HEAD").stdout.strip()
            self.assertIn(f"last_round_commit: {head}", (root / ".jahns-workflow.yml").read_text())

    def _setup(self, root, cfg_body):
        init_repo(root)
        (root / ".jahns-workflow.yml").write_text(cfg_body)
        (root / "tasks.yaml").write_text(TASKS_FIXTURE)
        git(root, "add", "-A"); git(root, "commit", "-qm", "setup")

    def test_missing_watermark_fails_closed_no_write(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._setup(root, "version: 1\nproject: x\n")  # no state.last_round_commit
            before = (root / "tasks.yaml").read_text()
            rc = jw_round.close(root, "2026-06-19-z", done=["feat/alpha"], touched=[], commit="HEAD")
            self.assertEqual(rc, 1)
            self.assertEqual((root / "tasks.yaml").read_text(), before)  # nothing written
            self.assertFalse((root / "ROADMAP.md").exists())

    def test_unresolvable_commit_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._setup(root, "version: 1\nproject: x\nstate:\n  last_round_commit: null\n")
            before = (root / "tasks.yaml").read_text()
            rc = jw_round.close(root, "2026-06-19-z", done=["feat/alpha"], touched=[], commit="nope-not-a-ref")
            self.assertEqual(rc, 1)
            self.assertEqual((root / "tasks.yaml").read_text(), before)

    def test_done_task_with_unmet_dep_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._setup(root, "version: 1\nproject: x\nstate:\n  last_round_commit: null\n")
            before = (root / "tasks.yaml").read_text()
            # gate/beta depends on feat/alpha (active) — closing gate/beta as done must fail
            rc = jw_round.close(root, "2026-06-19-z", done=["gate/beta"], touched=[], commit="HEAD")
            self.assertEqual(rc, 1)
            self.assertEqual((root / "tasks.yaml").read_text(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
