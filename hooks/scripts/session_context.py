#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SessionStart hook body: emit additionalContext (SSOT digest + active tasks + branch).

Called by session_context.sh with the project root as argv[1]; hook JSON on stdin (unused
beyond what the wrapper extracted). Output is capped to keep per-session token cost low.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from jw_common import git_branch_info, git_full_sha, load_config, load_tasks, next_actionable, resume_path, start_here_path  # noqa: E402

MAX_CHARS = 8000
MAX_TASK_LINES = 8
MAX_START_HERE = 2560  # ~2.5KB cap on the injected re-entry narrative (read-time, never truncates the file)


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    try:
        cfg = load_config(root)
        data = load_tasks(root)
    except Exception as e:  # malformed config must not break session start
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": f"[jahns-workflow] config/tasks unreadable: {e}",
        }}))
        return 0

    g = git_branch_info(root)
    tasks = [t for t in data.get("tasks", []) if isinstance(t, dict) and t.get("id")]
    done = sum(1 for t in tasks if t.get("status") == "done")
    active = [t for t in tasks if t.get("status") == "active"]
    blocked = [t for t in tasks if t.get("status") == "blocked"]
    decisions = [t for t in tasks if t.get("id", "").startswith("decision/") and t.get("status") not in ("done", "dropped")]
    rounds = sorted({t["round"] for t in active if t.get("round")})

    lines = [
        f"[jahns-workflow] project: {data.get('project', root.name)} | branch: {g['branch']}"
        f" ({'dirty +' + str(g['dirty']) if g['dirty'] else 'clean'}) | tasks: {done}/{len(tasks)} done",
    ]

    # persistent re-entry pointer (model-authored at round close / after review) — surfaced FIRST so a
    # new or post-compaction session picks up the live frontier without a manual "pick up". Read-time
    # capped; the file itself is never truncated. Authoritative state still lives in tasks.yaml/PROGRESS.
    sh = start_here_path(root)
    if sh.is_file():
        try:
            body = sh.read_text(encoding="utf-8").strip()
        except OSError:
            body = ""
        if body:
            if len(body) > MAX_START_HERE:
                body = body[:MAX_START_HERE].rstrip() + "\n…[START_HERE truncated — keep it ≤~35 lines]"
            lines.append("▶ START HERE (re-entry pointer — rewritten at round close / after review):")
            lines.append(body)

    if rounds:
        lines.append(f"active round: {', '.join(rounds)}")
    for label, group in (("active", active), ("blocked", blocked), ("pending decision", decisions)):
        for t in group[:MAX_TASK_LINES]:
            lines.append(f"  {label}: {t['id']} — {t.get('title', '')}")
    nxt = next_actionable(data, cap=5)
    if nxt:
        lines.append("next actionable (deps satisfied):")
        for tid, title in nxt:
            lines.append(f"  → {tid} — {title}")
    lines.append(f"Task registry: tasks.yaml | Roadmap: ROADMAP.md | Conventions: see CLAUDE.md workflow section")

    # consume a PreCompact/SessionEnd resume pointer if one was left, flagging staleness
    rp = resume_path(root)
    if rp.is_file():
        try:
            snap = rp.read_text(encoding="utf-8")
            captured = next((ln.split(":", 1)[1].strip() for ln in snap.splitlines()
                             if ln.startswith("captured_head:")), "")
            at = next((ln.split(":", 1)[1].strip() for ln in snap.splitlines()
                       if ln.startswith("captured_at:")), "")
            cur = git_full_sha(root, "HEAD") or ""
            stale = " [STALE: HEAD has moved since]" if captured and cur and captured != cur else ""
            lines.append(f"last checkpoint: {at} @ {captured[:12]}{stale}")
            rp.unlink()  # consume — a fresh one is written at the next PreCompact/SessionEnd
        except OSError:
            pass

    digest = root / cfg["generated_dir"] / "DIGEST.md"
    if digest.is_file():
        lines.append("")
        lines.append(digest.read_text(encoding="utf-8").rstrip())
    elif cfg.get("ssot"):
        lines.append(f"SSOT: {cfg['ssot']} (no digest generated yet — run /jahns-workflow:round or jw_ssot.py digest)")

    ctx = "\n".join(lines)
    if len(ctx) > MAX_CHARS:
        ctx = ctx[:MAX_CHARS] + "\n…[truncated by jahns-workflow cap]"
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": ctx,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
