#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Delegation primitive — `jw delegate` (0.8.0 M1).

Delegate a single implementation task to an external runner (codex) in an isolated git worktree,
then bring the result back through an explicit, harness-computed artifact contract. The dirty working
tree is fixed as an immutable snapshot commit (no history pollution) and used as the delegation base,
so what the delegate sees is exactly what the user sees now. The harness computes the patch and
changed-files list from git directly (explicit provenance); the delegate's own report (verification,
limitations, risks) is carried through labeled delegate-claimed and never promoted to fact — an
independent verifier (main) accepts or discards via `apply`/`discard`.

See dev_docs/0.8.0-m1-implementation-notes.md for the binding spec.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jw_common import WorkflowError, git_full_sha  # noqa: E402

DELEG_REF_NS = "refs/jw/delegations"


# ---- git plumbing (private; jw_common.git_rc has no env/cwd-index support) ----
def _git(cwd: Path, *args: str, env: dict | None = None, timeout: int = 30) -> tuple[int, str, str]:
    """Run git in `cwd`; return (rc, stdout, stderr). `env` overlays os.environ (for GIT_INDEX_FILE)."""
    full = {**os.environ, **env} if env else None
    try:
        p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                           env=full, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return (127, "", str(e))
    return (p.returncode, p.stdout.strip(), p.stderr.strip())


def _git_out(cwd: Path, *args: str, env: dict | None = None) -> str:
    """git that must succeed — raises WorkflowError on failure so a raw git rc never leaks to exit."""
    rc, out, err = _git(cwd, *args, env=env)
    if rc != 0:
        raise WorkflowError(f"git {args[0]} failed: {err or out or f'rc {rc}'}")
    return out


def _git_path(root: Path, name: str) -> Path | None:
    """Resolve a repo internal path (e.g. MERGE_HEAD, rebase-merge) via `git rev-parse --git-path`,
    which is worktree-aware. Returns an absolute Path or None if git could not resolve it."""
    rc, out, _ = _git(root, "rev-parse", "--git-path", name)
    if rc != 0 or not out:
        return None
    p = Path(out)
    return p if p.is_absolute() else (root / p)


# ---- snapshot primitive (§3 — temp-index read-tree-HEAD, verified sequence) ---
def _check_snapshot_preconditions(root: Path) -> None:
    """Fail loud (WorkflowError) on any state that would bake a partial/conflicted tree into the base:
    unborn HEAD, submodules, unmerged index, or an in-progress merge/cherry-pick/revert/rebase (§3)."""
    if git_full_sha(root, "HEAD") is None:
        raise WorkflowError("repository has no commits yet (unborn HEAD) — commit something before delegating")
    if (root / ".gitmodules").exists():
        raise WorkflowError("submodules are not supported in M1 (.gitmodules present) — refusing a partial snapshot")
    rc, out, _ = _git(root, "ls-files", "-u")
    if rc == 0 and out:
        raise WorkflowError("repository has unmerged paths — resolve the conflict before delegating")
    for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
        p = _git_path(root, name)
        if p is not None and p.exists():
            raise WorkflowError(f"an operation is in progress ({name}) — finish or abort it before delegating")
    for name in ("rebase-merge", "rebase-apply"):
        p = _git_path(root, name)
        if p is not None and p.is_dir():
            raise WorkflowError(f"a rebase is in progress ({name}) — finish or abort it before delegating")


def _snapshot(cwd: Path, message: str) -> tuple[str, bool]:
    """Fix cwd's current tracked+staged+untracked(non-ignored) state as an immutable commit object,
    seeded from HEAD via a throwaway index (§3 verified sequence — the live index/worktree are never
    touched). If the resulting tree equals HEAD's tree the state is clean: return (HEAD, False) and
    create no commit (clean-tree shortcut). Otherwise commit-tree the snapshot parented on HEAD and
    return (snapshot_sha, True). Works identically in the main repo and a linked worktree (HEAD there
    is the detached base, so `-p HEAD` parents the result on the base)."""
    head = _git_out(cwd, "rev-parse", "HEAD")
    head_tree = _git_out(cwd, "rev-parse", "HEAD^{tree}")
    tmpdir = tempfile.mkdtemp(prefix="jw-snap-")
    try:
        env = {"GIT_INDEX_FILE": str(Path(tmpdir) / "index")}
        _git_out(cwd, "read-tree", "HEAD", env=env)          # seed (S1 — not an index copy)
        _git_out(cwd, "add", "-A", env=env)                  # tracked mods + staged + untracked(non-ignored)
        tree = _git_out(cwd, "write-tree", env=env)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if tree == head_tree:
        return head, False
    sha = _git_out(cwd, "commit-tree", tree, "-p", head, "-m", message)
    return sha, True


def _make_did(task_id: str) -> str:
    """Delegation id: `<UTC yyyymmddTHHMMSSZ>-<task-slug>` (task slug = id with '/' -> '-'). It records
    an execution event, so a timestamp is intentional (the 0.7 decisions.jsonl precedent)."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{task_id.replace('/', '-')}"
