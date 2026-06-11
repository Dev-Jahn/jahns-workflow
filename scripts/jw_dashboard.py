#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Cross-project terminal dashboard for all jahns-workflow projects.

Usage: jw_dashboard.py [--project NAME]
Reads the global registry (~/.claude/jahns-workflow/projects.json) populated by /jahns-workflow:init.
Deterministic, no LLM involved.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jw_common import REGISTRY_PATH, git_branch_info, load_tasks  # noqa: E402

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
BLUE, RED, GREEN, YELLOW = "\033[34m", "\033[31m", "\033[32m", "\033[33m"


def c(code: str, text: str) -> str:
    return f"{code}{text}{RESET}" if sys.stdout.isatty() else text


def show_project(name: str, path: Path) -> None:
    if not path.is_dir():
        print(f"{c(BOLD, '■ ' + name)}  {c(RED, '✗ path missing')} {c(DIM, str(path))}")
        return
    g = git_branch_info(path)
    dirty = c(YELLOW, f"±{g['dirty']}") if g["dirty"] else c(GREEN, "clean")
    sync = f"↑{g['ahead']}↓{g['behind']}" if g["ahead"] != "?" else c(DIM, "no upstream")
    print(f"{c(BOLD, '■ ' + name)}  ⎇ {c(BLUE, g['branch'])} {dirty} {sync}  {c(DIM, str(path))}")

    data = load_tasks(path)
    tasks = [t for t in data.get("tasks", []) if isinstance(t, dict) and t.get("id")]
    if not tasks:
        print(c(DIM, "    (no tasks registered)"))
        return
    done = sum(1 for t in tasks if t.get("status") == "done")
    rounds = sorted({t["round"] for t in tasks if t.get("round") and t.get("status") == "active"})
    latest = rounds[-1] if rounds else max((t.get("round") or "" for t in tasks), default="") or "—"
    bar_n = round(20 * done / len(tasks))
    bar = "█" * bar_n + "░" * (20 - bar_n)
    print(f"    {bar} {done}/{len(tasks)} done   round: {latest}")

    by_id = {t["id"]: t for t in tasks}
    for t in tasks:
        if t.get("status") == "active":
            print(f"    {c(BLUE, '● active ')} {c(BOLD, t['id'])} — {t.get('title', '')}")
    for t in tasks:
        if t.get("status") == "blocked":
            unmet = [d for d in t.get("deps", []) if by_id.get(d, {}).get("status") != "done"]
            why = f"  {c(DIM, 'waiting: ' + ', '.join(unmet))}" if unmet else ""
            print(f"    {c(RED, '⛔ blocked')} {c(BOLD, t['id'])} — {t.get('title', '')}{why}")
    pend = sum(1 for t in tasks if t.get("status") == "pending")
    if pend:
        print(c(DIM, f"    … {pend} pending"))


def main() -> int:
    idx = sys.argv.index("--project") if "--project" in sys.argv else -1
    only = sys.argv[idx + 1] if 0 <= idx < len(sys.argv) - 1 else None
    if not REGISTRY_PATH.is_file():
        print("no projects registered yet — run /jahns-workflow:init in a project first")
        return 0
    reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    projects = reg.get("projects", [])
    if only:
        projects = [p for p in projects if p.get("name") == only]
    if not projects:
        print(f"no registered project matches {only!r}" if only else "registry is empty")
        return 0
    for i, p in enumerate(projects):
        if i:
            print()
        show_project(p.get("name", "?"), Path(p.get("path", "")).expanduser())
    return 0


if __name__ == "__main__":
    sys.exit(main())
