#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Focused ADR-0011 ProjectContext contracts."""
from __future__ import annotations

from support import *  # noqa: F401,F403

import json

from waystone.project.context import (
    ProjectContextError,
    WorktreeSelectorRequired,
    resolve_project_context,
)


class ProjectContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.base = Path(self._temporary_directory.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        init_repo(self.root)
        (self.root / ".waystone.yml").write_text(
            "version: 1\nproject: fixture\n", encoding="utf-8")
        (self.root / "tracked.txt").write_text("base\n", encoding="utf-8")
        git(self.root, "add", "-A")
        self.assertEqual(git(self.root, "commit", "-qm", "fixture").returncode, 0)
        self.registry = self.base / "machine" / "projects.json"
        self.registry.parent.mkdir()
        self.registry.write_text(json.dumps({"projects": [{
            "project_id": "project:test-opaque-id",
            "name": "fixture",
            "path": str(self.root.resolve()),
        }]}), encoding="utf-8")

    def test_canonical_root_identity_and_database_are_resolved_from_registry(self):
        context = resolve_project_context(self.root, registry=self.registry)

        self.assertEqual(context.project_id, "project:test-opaque-id")
        self.assertEqual(context.canonical_root, self.root.resolve())
        self.assertEqual(context.active_worktree_root, self.root.resolve())
        self.assertEqual(context.checkout_identity, "canonical")
        self.assertEqual(
            context.database_path, self.root.resolve() / ".waystone" / "state.db")
        self.assertTrue(context.is_canonical_checkout)

    def test_linked_worktree_has_distinct_identity_and_requires_explicit_run_selector(self):
        linked = self.base / "linked"
        self.assertEqual(
            git(self.root, "worktree", "add", "-q", "-b", "context-linked", str(linked)).returncode,
            0,
        )

        read_context = resolve_project_context(linked, registry=self.registry)

        self.assertEqual(read_context.canonical_root, self.root.resolve())
        self.assertEqual(read_context.active_worktree_root, linked.resolve())
        self.assertRegex(
            read_context.checkout_identity, r"^worktree:sha256:[0-9a-f]{64}$")
        self.assertFalse(read_context.is_canonical_checkout)
        with self.assertRaises(WorktreeSelectorRequired) as raised:
            resolve_project_context(
                linked, require_run_input=True, registry=self.registry)
        self.assertEqual(raised.exception.code, "worktree_selector_required")

        selected = resolve_project_context(
            linked,
            from_worktree=linked,
            require_run_input=True,
            registry=self.registry,
        )
        self.assertEqual(selected.checkout_identity, read_context.checkout_identity)
        self.assertEqual(selected.database_path, self.root.resolve() / ".waystone" / "state.db")

    def test_missing_opaque_project_id_refuses_without_reading_project_files(self):
        self.registry.write_text(json.dumps({"projects": [{
            "name": "fixture", "path": str(self.root.resolve()),
        }]}), encoding="utf-8")
        marker = self.root / ".waystone.yml"
        marker.chmod(0)
        self.addCleanup(marker.chmod, 0o644)

        with self.assertRaises(ProjectContextError) as raised:
            resolve_project_context(self.root, registry=self.registry)

        self.assertEqual(raised.exception.code, "project_context_unavailable")
        self.assertIn("lacks an opaque project_id", str(raised.exception))
        self.assertFalse((self.root / ".waystone" / "state.db").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
