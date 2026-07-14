<!-- waystone:begin (managed block — edit via $waystone:init) -->
## Workflow (waystone)

- **SSOT**: `{SSOT_PATH}` — binding but falsifiable. Read sections via `{GENERATED_DIR}/INDEX.md`; never re-read the whole file; cite by §-anchor, never line numbers. If implementation evidence contradicts it: STOP, register a `decision/...` task, get a ruling, amend via ADR. Never silently comply or diverge.
- **Task registry**: every unit of work gets an ID `<type>/<kebab-slug>` (feat|fix|perf|gate|spike|decision|docs|chore) registered in `tasks.yaml` with an explanatory title BEFORE first use. Bare codenames (P0, E3, Q1…) are banned. `ROADMAP.md` is generated — never edit it.
- **Waystone CLI**: each `$waystone:*` skill resolves its installed plugin root and runs the absolute `$WAYSTONE_PLUGIN_ROOT/bin/waystone-codex` launcher; never assume `waystone` is on `PATH`.
- **Read & mutate the registry through the CLI, not raw** (it grows to thousands of lines): use `task list [--status/--type/--milestone/--round]` and `task show <id>` to read; `task add <id> --title … [--severity/--deps/…]`, `task set <id> <field> <value>`, `task drop <id>` to mutate (validated, comment-preserving).
- **Severities** on review findings: blocker > major > minor (field, not ID). Blockers resolve before the next round.
- **Rounds**: close each work round with `$waystone:round` (updates registry, PROGRESS, roadmap, digest, review packet). Ingest external review replies with `$waystone:review`.
- Full convention: `docs/CONVENTIONS.md`.
<!-- waystone:end -->
