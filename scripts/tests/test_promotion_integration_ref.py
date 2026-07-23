#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Promotion publishes only a lineage-owned private integration ref."""
from __future__ import annotations

from support import *  # noqa: F401,F403

import subprocess
from unittest import mock

from waystone.cli import run_group
from waystone.features.review_layout import new_run_id
from waystone.runs import effects as effects_module
from waystone.runs import store as store_module
from waystone.runs.effects import EffectEngine, EffectResultState, GitRefEffect
from waystone.runs.lease import LeaseManager
from waystone.runs.store import FilesystemInfo, RunStore


class PromotionIntegrationRefTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repo"
        self.root.mkdir()
        init_repo(self.root)
        (self.root / ".waystone.yml").write_text(
            "version: 1\nproject: promotion-integration-ref\n", encoding="utf-8")
        git(self.root, "add", ".waystone.yml")
        self.assertEqual(git(self.root, "commit", "-qm", "initialize").returncode, 0)
        self.public_ref = self._git("symbolic-ref", "HEAD")
        self.public_oid = self._git("rev-parse", "HEAD")

    def _git(self, *args: str, input_text: str | None = None) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.root), *args],
            input=input_text,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def _commit(self, message: str) -> str:
        tree = self._git("rev-parse", "HEAD^{tree}")
        return self._git(
            "commit-tree", tree, "-p", self.public_oid, input_text=f"{message}\n")

    def _effect_engine(
            self, target_ref: str, expected_oid: str, desired_oid: str,
    ) -> tuple[RunStore, EffectEngine, object]:
        filesystem = mock.patch.object(
            store_module,
            "_probe_state_filesystem",
            return_value=FilesystemInfo(
                filesystem="apfs", mount_point=Path("/"), writable=True),
        )
        filesystem.start()
        self.addCleanup(filesystem.stop)
        store = RunStore.open(self.root)
        self.addCleanup(store.close)
        run = store.create_run()
        store.create_job(run.entity_id, "job")
        store.create_attempt(run.entity_id, "job", "attempt")
        engine = EffectEngine(store, LeaseManager(store))
        plan = engine.plan_effect(
            run.entity_id,
            "job",
            "attempt",
            "promotion-target-ref-apply",
            GitRefEffect(self.root, target_ref, expected_oid, desired_oid),
        )
        return store, engine, engine.claim_effect(plan, ttl_seconds=30)

    def test_public_checkout_remains_clean_when_private_target_is_initialized(self):
        tracked_before = (self.root / "f.txt").read_bytes()
        index_before = self._git("write-tree")
        status_before = self._git("status", "--porcelain=v1")
        lineage_id = new_run_id()

        target_ref = run_group._integration_target(self.root, lineage_id)  # noqa: SLF001

        self.assertEqual(
            target_ref, f"refs/waystone/integration/{lineage_id}")
        self.assertEqual(self._git("rev-parse", target_ref), self.public_oid)
        self.assertEqual(self._git("symbolic-ref", "HEAD"), self.public_ref)
        self.assertEqual(self._git("rev-parse", "HEAD"), self.public_oid)
        self.assertEqual((self.root / "f.txt").read_bytes(), tracked_before)
        self.assertEqual(self._git("write-tree"), index_before)
        self.assertEqual(self._git("status", "--porcelain=v1"), status_before)

    def test_private_target_expected_old_cas_rejects_concurrent_advance(self):
        target_ref = run_group._integration_target(  # noqa: SLF001
            self.root, new_run_id())
        candidate_oid = self._commit("candidate")
        concurrent_oid = self._commit("concurrent")
        _store, engine, claimed = self._effect_engine(
            target_ref, self.public_oid, candidate_oid)
        self._git("update-ref", target_ref, concurrent_oid, self.public_oid)

        result = engine.execute_effect(claimed)

        self.assertEqual(result.state, EffectResultState.CONFLICT)
        self.assertEqual(self._git("rev-parse", target_ref), concurrent_oid)
        self.assertEqual(self._git("rev-parse", self.public_ref), self.public_oid)

    def test_private_target_apply_preserves_dirty_worktree_byte_exact(self):
        target_ref = run_group._integration_target(  # noqa: SLF001
            self.root, new_run_id())
        candidate_oid = self._commit("candidate")
        _store, engine, claimed = self._effect_engine(
            target_ref, self.public_oid, candidate_oid)
        dirty_tracked = b"\x00user-dirty\n"
        dirty_untracked = b"\xffuntracked\n"
        (self.root / "f.txt").write_bytes(dirty_tracked)
        (self.root / "untracked.bin").write_bytes(dirty_untracked)
        index_before = self._git("write-tree")
        status_before = subprocess.run(
            ["git", "-C", str(self.root), "status", "--porcelain=v1", "-z"],
            capture_output=True,
            check=True,
        ).stdout

        with mock.patch.object(
                effects_module, "_git_rc", wraps=effects_module._git_rc) as git_calls:
            result = engine.execute_effect(claimed)

        self.assertEqual(result.state, EffectResultState.COMPLETED)
        self.assertEqual(self._git("rev-parse", target_ref), candidate_oid)
        self.assertEqual(self._git("rev-parse", "HEAD"), self.public_oid)
        self.assertEqual((self.root / "f.txt").read_bytes(), dirty_tracked)
        self.assertEqual((self.root / "untracked.bin").read_bytes(), dirty_untracked)
        self.assertEqual(self._git("write-tree"), index_before)
        self.assertEqual(subprocess.run(
            ["git", "-C", str(self.root), "status", "--porcelain=v1", "-z"],
            capture_output=True,
            check=True,
        ).stdout, status_before)
        self.assertFalse(any(
            call.args[1] in {"checkout", "reset"} for call in git_calls.call_args_list))


if __name__ == "__main__":
    unittest.main()
