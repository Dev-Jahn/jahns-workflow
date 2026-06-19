#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Atomic round closeout — the deterministic ritual the round skill used to hand-run.

`close` performs, in one command and in order:
  1. flip the given tasks to done and stamp every worked task with the round id
     (surgical, comment-preserving edits to tasks.yaml — never a full rewrite),
  2. validate the registry and regenerate ROADMAP.md (and SSOT views if configured),
  3. set state.last_round_commit to the round's tip,
  4. report the SSOT churn since the previous round watermark (bulk-edit quarantine signal).

The text-surgery helpers (set_task_field, set_config_scalar) are pure and tested.

Usage (also `jw round close`):
  jw_round.py close [root] --round <id> [--done id,id] [--touched id,id] [--commit HEAD]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jw_common import (  # noqa: E402
    ROUND_RE, find_project_root, git, git_full_sha, load_config,
)


# ---- pure text surgery -------------------------------------------------------
def _task_block_span(lines: list[str], task_id: str) -> tuple[int, int] | None:
    """Return (start, end) line indices of the `- id: <task_id>` block, end exclusive."""
    id_re = re.compile(r'^(\s*)-\s+id:\s*["\']?' + re.escape(task_id) + r'["\']?\s*$')
    start = None
    indent = 0
    for i, ln in enumerate(lines):
        m = id_re.match(ln)
        if m:
            start = i
            indent = len(m.group(1))
            break
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        ln = lines[j]
        if not ln.strip():
            continue
        cur = len(ln) - len(ln.lstrip())
        if cur <= indent and (ln.lstrip().startswith("- ") or cur < indent):
            return (start, j)
    return (start, len(lines))


def set_task_field(text: str, task_id: str, field: str, value: str) -> str:
    """Set `field: value` inside a task block, preserving all other content/comments.
    Updates the field if present, else inserts it right after the id line. Raises if the
    task is absent (a round must not silently no-op)."""
    lines = text.splitlines(keepends=True)
    span = _task_block_span(lines, task_id)
    if span is None:
        raise KeyError(f"task id not found in registry: {task_id}")
    start, end = span
    nl = "\n" if not lines[start].endswith("\r\n") else "\r\n"
    field_indent = len(lines[start]) - len(lines[start].lstrip()) + 2
    # match ONLY a task-level field at the exact sibling indent — never a deeper nested key
    # (e.g. a `lane:`/`status:` sub-mapping must not be mistaken for the task's `status`).
    field_re = re.compile(rf"^ {{{field_indent}}}{re.escape(field)}:\s*.*$")
    for k in range(start + 1, end):
        if field_re.match(lines[k]):
            lines[k] = f"{' ' * field_indent}{field}: {value}{nl}"
            return "".join(lines)
    lines.insert(start + 1, f"{' ' * field_indent}{field}: {value}{nl}")
    return "".join(lines)


def set_config_scalar(text: str, key: str, value: str, section: str | None = None) -> str:
    """Replace the value of a `<key>:` line preserving indent/comments. When `section` is given
    (e.g. 'state'), only a key INSIDE that block is matched — so `last_round_commit` can't be
    confused with a same-named key elsewhere. Raises if absent."""
    lines = text.splitlines(keepends=True)
    key_re = re.compile(r"^(\s*)" + re.escape(key) + r":\s*.*$")

    def replace_at(i: int, indent: str) -> str:
        nl = "\r\n" if lines[i].endswith("\r\n") else "\n"
        lines[i] = f"{indent}{key}: {value}{nl}"
        return "".join(lines)

    if section is None:
        for i, ln in enumerate(lines):
            m = key_re.match(ln)
            if m:
                return replace_at(i, m.group(1))
        raise KeyError(f"config key not found: {key}")

    sec_re = re.compile(r"^(\s*)" + re.escape(section) + r":\s*$")
    start = sec_indent = None
    for i, ln in enumerate(lines):
        m = sec_re.match(ln)
        if m:
            start, sec_indent = i, len(m.group(1))
            break
    if start is None:
        raise KeyError(f"config section not found: {section}")
    child_indent = sec_indent + 2  # only a DIRECT child of the section, never a deeper nested key
    for j in range(start + 1, len(lines)):
        ln = lines[j]
        if not ln.strip():
            continue
        cur = len(ln) - len(ln.lstrip())
        if cur <= sec_indent:
            break  # dedented out of the section
        if cur != child_indent:
            continue  # nested deeper than a direct child — skip
        m = key_re.match(ln)
        if m:
            return replace_at(j, m.group(1))
    raise KeyError(f"config key {key!r} not found under section {section!r}")


# ---- orchestration -----------------------------------------------------------
def _parse_ids(s: str | None) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def close(root: Path, round_id: str, done: list[str], touched: list[str], commit: str) -> int:
    """Fail-closed: resolve the commit and confirm the watermark slot up front, apply edits in
    memory and validate BEFORE writing anything, then write tasks.yaml → views → watermark."""
    import shutil
    import tempfile
    import yaml
    import jw_roadmap
    import jw_validate

    if not ROUND_RE.match(round_id):
        print(f"jw_round close: --round must match YYYY-MM-DD-<slug>, got {round_id!r}", file=sys.stderr)
        return 1
    cfg = load_config(root)
    cfg_path = root / ".jahns-workflow.yml"
    tasks_path = root / "tasks.yaml"

    # --- preflight (no writes) ---
    full = git_full_sha(root, commit)
    if full is None:
        print(f"jw_round close: --commit {commit!r} does not resolve to a commit", file=sys.stderr)
        return 1
    ctext = cfg_path.read_text(encoding="utf-8")
    try:
        ctext_new = set_config_scalar(ctext, "last_round_commit", full, section="state")
    except KeyError:
        print("jw_round close: state.last_round_commit is missing from .jahns-workflow.yml — "
              "add it (under `state:`) before closing rounds.", file=sys.stderr)
        return 1

    orig_tasks_text = tasks_path.read_text(encoding="utf-8")
    text = orig_tasks_text
    data0 = yaml.safe_load(text) or {}
    by_id = {t.get("id"): t for t in data0.get("tasks", []) if isinstance(t, dict)}
    # done tasks must have all deps done — evaluated against the FINAL state (a dependency closed
    # in the SAME round counts), so closing a dependency and its dependent together is allowed.
    final_done = {tid for tid, t in by_id.items() if t.get("status") == "done"} | set(done)
    dep_problems = []
    for tid in done:
        for dep in (by_id.get(tid, {}).get("deps") or []):
            if dep not in final_done:
                dep_problems.append(f"{tid} cannot be done — dependency {dep} is not done "
                                    f"(and is not being closed in this round)")
    if dep_problems:
        for p in dep_problems:
            print(f"jw_round close: {p}", file=sys.stderr)
        return 1

    try:
        for tid in done:
            text = set_task_field(text, tid, "status", "done")
        for tid in dict.fromkeys(done + touched):
            text = set_task_field(text, tid, "round", round_id)
    except KeyError as e:
        print(f"jw_round close: {e}", file=sys.stderr)
        return 1

    errs = jw_validate.validate(yaml.safe_load(text))
    if errs:
        print(f"jw_round close: edits would make tasks.yaml invalid ({len(errs)} issue(s)) — aborted, "
              f"nothing written:", file=sys.stderr)
        for e in errs[:10]:
            print(f"  - {e}", file=sys.stderr)
        return 2

    # churn since the previous watermark (computed before advancing it)
    prev = (cfg.get("state") or {}).get("last_round_commit")
    churn = None
    if prev and cfg.get("ssot"):
        stat = git(root, "diff", "--numstat", f"{prev}..{full}", "--", cfg["ssot"])
        if stat:
            adds = sum(int(p.split("\t")[0]) for p in stat.splitlines() if p.split("\t")[0].isdigit())
            dels = sum(int(p.split("\t")[1]) for p in stat.splitlines() if p.split("\t")[1].isdigit())
            churn = adds + dels

    # --- commit phase (all preflight checks passed): write with rollback ---
    # ROADMAP.render reads tasks.yaml from disk, so the new registry must be written first. If any
    # later step raises, restore the primary mutated files (tasks.yaml, cfg, ROADMAP) AND the whole
    # generated SSOT dir from a snapshot — split/index/.hash/DIGEST must stay mutually consistent,
    # else `jw_ssot.check()` (which only diffs .hash) would report "up to date" over a stale digest.
    roadmap_path = root / "ROADMAP.md"
    orig_roadmap = roadmap_path.read_text(encoding="utf-8") if roadmap_path.exists() else None
    gen_dir = (root / cfg["generated_dir"]) if cfg.get("ssot") else None
    gen_existed = bool(gen_dir and gen_dir.exists())
    gen_backup = None
    if gen_existed:
        gen_backup = Path(tempfile.mkdtemp(prefix="jw-ssot-bak-")) / "g"
        shutil.copytree(gen_dir, gen_backup)
    try:
        tasks_path.write_text(text, encoding="utf-8")
        cfg_path.write_text(ctext_new, encoding="utf-8")
        roadmap_path.write_text(jw_roadmap.render(root), encoding="utf-8")
        if cfg.get("ssot"):
            import jw_ssot
            jw_ssot.split(root)
            jw_ssot.digest(root)
    except Exception as e:  # noqa: BLE001 — any failure must roll every written artifact back
        tasks_path.write_text(orig_tasks_text, encoding="utf-8")
        cfg_path.write_text(ctext, encoding="utf-8")
        if orig_roadmap is None:
            roadmap_path.unlink(missing_ok=True)
        else:
            roadmap_path.write_text(orig_roadmap, encoding="utf-8")
        if gen_dir is not None:
            shutil.rmtree(gen_dir, ignore_errors=True)
            if gen_existed:
                shutil.copytree(gen_backup, gen_dir)
        if gen_backup is not None:
            shutil.rmtree(gen_backup.parent, ignore_errors=True)
        print(f"jw_round close: closeout failed mid-write and was rolled back — {e}", file=sys.stderr)
        return 1
    if gen_backup is not None:
        shutil.rmtree(gen_backup.parent, ignore_errors=True)

    print(f"round {round_id} closed: {len(done)} done, {len(set(done + touched))} stamped; "
          f"watermark set @ {full[:12]}")
    if churn is not None:
        flag = "  ⚠ BULK EDIT (>100 lines) — run /jahns-workflow:audit on changed sections" if churn > 100 else ""
        print(f"SSOT churn since last round: {churn} lines{flag}")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] != "close":
        print(__doc__, file=sys.stderr)
        return 1
    rest = argv[1:]

    def opt(name):
        return rest[rest.index(name) + 1] if name in rest and rest.index(name) < len(rest) - 1 else None
    positional = [a for a in rest if not a.startswith("--") and (rest.index(a) == 0 or rest[rest.index(a) - 1] not in ("--round", "--done", "--touched", "--commit"))]
    root = Path(positional[0]).resolve() if positional else find_project_root(Path.cwd())
    if root is None:
        print("jw_round: no initialized project", file=sys.stderr)
        return 1
    round_id = opt("--round")
    if not round_id:
        print("jw_round close: --round <id> is required", file=sys.stderr)
        return 1
    return close(root, round_id, _parse_ids(opt("--done")), _parse_ids(opt("--touched")), opt("--commit") or "HEAD")


if __name__ == "__main__":
    sys.exit(main())
