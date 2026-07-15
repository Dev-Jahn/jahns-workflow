---
name: round
description: This skill should be used when the user runs "/waystone:round" in Claude Code or "$waystone:round" in Codex, says to "close the round", "wrap up this round", "finish the work cycle", or when an autonomous work round (implement → verify → push) reaches its end and the project's host instruction file mandates round closeout. Updates the task registry, PROGRESS, roadmap, SSOT views, and writes the round's markdown review request.
argument-hint: "[round-slug] e.g. lstream-seams"
---

# waystone: round

## Host contract

- Claude Code: invoke `/waystone:round`; assign `$CLAUDE_PLUGIN_ROOT` to
  `WAYSTONE_PLUGIN_ROOT`, then run command examples with `waystone` from `PATH`.
- Codex: invoke `$waystone:round`; from this skill's directory walk up two parents, assign that
  absolute path to `WAYSTONE_PLUGIN_ROOT`, then run command examples with
  `$WAYSTONE_PLUGIN_ROOT/bin/waystone-codex`.
- Resolve plugin resources from `$WAYSTONE_PLUGIN_ROOT`. Ask required choices through the host's native
  user-interaction mechanism; never require a specifically named question tool.

Close the current work round: bring the task registry up to date, record the round in
PROGRESS, refresh generated views, and write the round's external review request (one markdown
file; the reviewer reads the repo over git).

Requires an initialized project (`.waystone.yml`). If missing, stop and point the user
at `/waystone:init` in Claude Code or `$waystone:init` in Codex.

## Step 1 — Determine the round id

`<today YYYY-MM-DD>-<slug>`: slug from the argument if given, else derive a short one from the
round's dominant theme. Check PROGRESS for an existing entry with the same id (extend it
rather than duplicating).

## Step 2 — Sync the task registry

First register any newly discovered work as new tasks via the CLI — `waystone task add
<type>/<slug> . --title "..." [--severity ...] [--deps a,b]` (proper IDs + explanatory
titles; set `anchor:` to the governing SSOT §-anchor when known) — rather than hand-editing the
registry. Unresolved questions for the user become `decision/...` tasks; when a `decision/...` is
answered, record the ruling with `waystone task set <id> ruling "..."`.

Before handing off nontrivial work, resolve the profile with `waystone paths --root <project-root>`
and follow the selected role's `execution`/`backend`. Use `waystone delegate run <task-id>` only for
an `implementer` bound to `external-runner`. For `clean-subagent`, `forked-subagent`,
`deterministic-workflow`, or `main-session`, use the host's native execution mechanism instead and
preserve the role attribution. When exact path scope is derivable, record it first with repeated
`waystone task set <task-id> --scope-add "<repo-relative-prefix>"` calls. Whichever route ran, include
the task in this round's `--done` or `--touched` set and record its role/execution/backend and result
in PROGRESS.

Then close the round in one atomic, deterministic step instead of hand-editing each field:

```bash
waystone round close . --round <round-id> \
    --done <comma-ids that fully passed> --touched <comma-ids worked but not done> \
    --route-note <role>,<execution>,<backend>
```

Repeat `--route-note` once for each host-guided role actually used in the round. Do not record an
external-runner here; delegation exposure already records it. The close command validates every
note against the current profile and stores it in the immutable round exposure. If no host-guided
route was used, omit the flag; downstream role attribution remains unknown rather than guessed.

`round close` flips the `--done` tasks to `done`, stamps `round:` on every worked task, validates
the registry, regenerates `ROADMAP.md` (and SSOT views if configured), and advances
`state.last_round_commit`.
A `gate/...` task goes in `--done` only if the bar actually passed (link evidence in PROGRESS).
If `round close` reports the registry invalid, fix the reported issues before continuing.
If lanes were used this round, first verify them: `waystone lanes verify .`.

Relay adaptive-rule results with tri-state wording: **fired**, **did not fire (evaluable)**, or
**unevaluable (<coverage reason>)**. Never call an unevaluable rule a non-fire. Keep a
`waystone warn conflict` line labeled as a policy conflict whose effective stage was resolved
least-restrictively; do not relabel it as a rule fire.

Then keep the registry small: `waystone task archive .` relocates old
done/dropped tasks into `tasks.archive.yaml` once the registry crosses a size threshold (it keeps
the most-recent few for decision context, and never archives a task a live one still depends on).
It is a safe no-op below the threshold, so run it every round.

## Step 3 — PROGRESS entry + archive

Append an entry from `$WAYSTONE_PLUGIN_ROOT/templates/progress-entry.md` (content in the user's
configured language). Then archive: move dated sections from months before the current one
into `docs/progress/<YYYY-MM>.md` (mechanical cut-paste, newest-first preserved), leaving
PROGRESS.md with the current month + the header pointers.

## Step 4 — Request review

**Push gate first (both modes):** run `waystone remote verify .`. A review
must point at a pushed commit; if it exits non-zero, STOP and have the user push the round's commits.
If your conventions end a round in a commit, commit the closeout (`docs(round): close <round-id>`)
and push it FIRST so `tasks.yaml` / PROGRESS carry the round's final state.

Write `<reviews_dir>/<round-id>-request.md` from `$WAYSTONE_PLUGIN_ROOT/templates/review-request.md`: what
changed and *why*, the files to read first, falsifiable "claims to attack", evidence pointers (to
where logs/PROGRESS already live — do **not** copy them), known weak spots, and the domain lens. Fill
`Reviewing` with `git rev-parse HEAD` and the diff base with the **`review diff base`** value
`waystone round close` printed in Step 2 (the previous round's tip, or `(root)` for the first round — the
live `state.last_round_commit` is no longer it, having just advanced to this round's tip). The
reviewer reaches the repo over git, so the request is the only artifact you author — no zip, no bundle.

**Packet mode** (`review.mode: packet`, default): give the user the request file and a one-line
prompt, e.g.:

> `docs/reviews/<round-id>-request.md`를 읽고, 거기 적힌 claim이 코드/테스트로 성립하는지 repo를
> 직접 확인하며 major 위주로 도메인 리뷰해줘.

If a repo-local `docs/review-profile.md` exists (the project's standing domain lens), the reviewer
reads it too — the brief points there.

**PR mode** (`review.mode: pr`): also freeze a SHA-bound review cycle and post the `@codex` request:
`waystone review freeze --pr <N> --round <round-id> .` (stamps the current
PR head as cycle N + posts the request). The macro reviewer reads the PR + the request file. Check
progress with `waystone review status --pr <N>`; never treat "a comment appeared" as "review done" — a
review is `(reviewer, cycle, reviewed_sha)`.

## Step 5 — Report

Report in the user's configured language: shipped tasks (id — title), registry/roadmap state, where
the review request (`<reviews_dir>/<round-id>-request.md`) is, and a suggested commit message
(`docs(round): close <round-id>`). Do not commit unless the project's conventions say rounds end in
a commit and the user has authorized committing.

End with the **next-step reminder** (so the reply is preserved byte-exact, not re-typed by a model):

> Give the reviewer the round request (`<reviews_dir>/<round-id>-request.md`) and the prompt; the
> reviewer reads the repo over git. To ingest the reply, save it **in a separate shell**:
> `cat > /tmp/review.md` → paste → `Ctrl-D`. Then run `/waystone:review <round-id>` in Claude
> Code or `$waystone:review <round-id>` in Codex; it copies `/tmp/review.md` verbatim into the
> reviews dir (no model retyping) and triages it.

## Step 6 — Refresh the re-entry pointer

**OVERWRITE** the project's persistent re-entry file so the next session — or a post-compaction
resume — picks up the live frontier without you re-explaining "where were we". Get its path:

```bash
waystone resume --start-here-path .
```

Then overwrite that file — never append — with **≤ ~35 lines / ~2.5KB**:

- first line: `# re-entry @ <round-id> / HEAD <short-sha>`
- then the live frontier: what just landed, the open decision / next probe and **why**, the active
  lane(s) — with detail **linked** to PROGRESS / topic files, not inlined.

This replaces the old habit of growing a "START HERE" blob inside the agent-memory `MEMORY.md`
(which accumulates unbounded). The SessionStart hook injects this file automatically each session;
it is reset every round, so keep it short and current. Authoritative state stays in
tasks.yaml / PROGRESS — this is only a pointer.
