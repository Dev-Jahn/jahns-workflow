#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Focused production run CLI ingress and ProjectContext ordering contracts."""
from __future__ import annotations

from support import *  # noqa: F401,F403

import contextlib
import io
import json
import os
from contextlib import contextmanager
from unittest import mock

from test_work_brief import init_project, payload
from waystone.cli import run_group
from waystone.features.review_layout import new_run_id
from waystone.jobs import completion
from waystone.runs.spec import load_run_spec
from waystone.runs.store import EntityKind, FilesystemInfo, RunStore


class RunCliTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "repo"
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
        self.machine = self.base / "machine"
        self.machine.mkdir()
        self.machine.joinpath("projects.json").write_text(json.dumps({"projects": [{
            "project_id": "project:run-cli",
            "name": "demo",
            "path": str(self.root.resolve()),
        }]}), encoding="utf-8")
        self.brief_path = self.base / "work-brief.json"
        self.brief_path.write_bytes(completion.canonical_json(
            payload(self.head, self.frame, new_run_id())))

    @contextmanager
    def runtime(self, cwd: Path | None = None):
        old = Path.cwd()
        target = self.root if cwd is None else cwd
        output = io.StringIO()
        try:
            os.chdir(target)
            with mock.patch.dict(os.environ, {"WAYSTONE_HOME": str(self.machine)}), mock.patch(
                    "waystone.runs.store._probe_state_filesystem",
                    return_value=FilesystemInfo(
                        filesystem="apfs", mount_point=Path("/"), writable=True)), \
                    contextlib.redirect_stdout(output):
                yield output
        finally:
            os.chdir(old)

    def test_start_uses_production_assembly_and_freezes_typed_ingress(self):
        with self.runtime() as output:
            result = run_group.main([
                "start",
                "feat/semantic-brief",
                "--work-brief",
                str(self.brief_path),
                "--stage",
                "explore",
            ])

        self.assertEqual(result, 0, output.getvalue())
        run_id = output.getvalue().split()[1]
        with mock.patch(
                "waystone.runs.store._probe_state_filesystem",
                return_value=FilesystemInfo(
                    filesystem="apfs", mount_point=Path("/"), writable=True)):
            spec = load_run_spec(run_id, start=self.root)
            with RunStore.open(self.root) as store:
                self.assertEqual(store.get_run(run_id).state, "dispatch-ready")
                self.assertEqual(
                    store.get_entity(
                        EntityKind.ATTEMPT, f"{run_id}:attempt:1").state,
                    "running",
                )
        self.assertEqual(spec.revision, 1)
        self.assertEqual(spec.lifecycle_stage.value, "explore")

    def test_stage_is_only_an_assertion_and_mismatch_creates_no_run(self):
        with self.runtime() as output:
            result = run_group.main([
                "start",
                "feat/semantic-brief",
                "--work-brief",
                str(self.brief_path),
                "--stage",
                "promote",
            ])

        self.assertEqual(result, 2, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["code"], "action_plan_invalid")
        with mock.patch(
                "waystone.runs.store._probe_state_filesystem",
                return_value=FilesystemInfo(
                    filesystem="apfs", mount_point=Path("/"), writable=True)), \
                RunStore.open(self.root) as store:
            count = store._connection.execute("SELECT count(*) FROM runs").fetchone()[0]  # noqa: SLF001
        self.assertEqual(count, 0)

    def test_linked_start_without_explicit_selector_refuses_before_ingress_or_db_open(self):
        linked = self.base / "linked"
        self.assertEqual(
            git(self.root, "worktree", "add", "-q", "-b", "cli-linked", str(linked)).returncode,
            0,
        )
        missing = self.base / "must-not-be-read.json"
        with self.runtime(linked) as output:
            result = run_group.main([
                "start", "feat/semantic-brief", "--work-brief", str(missing),
            ])

        self.assertEqual(result, 2, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["code"], "action_plan_invalid")
        self.assertFalse((self.root / ".waystone" / "state.db").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
