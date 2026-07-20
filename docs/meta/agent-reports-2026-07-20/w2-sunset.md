# w2 sunset — pre-0.9 migration subsystem removal

## Result

The current-name pre-0.9 Phase 1/Phase 2 migration subsystem has been removed. Waystone 0.12 now performs only read-only detection and raises `Pre09StateError` (`code = unsupported_pre_0_9_layout`) with released-0.11.x/manual-migration guidance. It does not move, copy, merge, seed, resume, quarantine, repair, or discard legacy state.

The compatibility names `migrate_home_data()` and `migrate_project_state()` remain because no-touch callers in the hook and `scripts/review.py` still import them. Each is now a one-line shim to the refusal check and cannot migrate state.

Removed behavior includes:

- Phase 1 registry union, decisions/improve merge, legacy-root preservation/rename, conflict handling, and orphan reporting.
- Phase 2 profile seeding, resume/start-here/tree/overlay/delegation migration, cross-host conflict/quarantine logic, and self-extinguishing cleanup.
- Worktree `git worktree move`, filesystem fallback, `.migrating` resume, `worktree repair`, and discard-only recovery.
- The legacy auto-migration tests that asserted those behaviors.

Preserved behavior includes current machine/project path and registry primitives, 0.9+ schema/review-marker adapters, existing lock order, statusline's read-only bypass, and the linked-worktree mutation guard occurring before the module-level state check.

## RED-first evidence

| Stage | Command | Result |
|---|---|---|
| Before deletion: existing fixture demonstrated automatic migration | `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py WaystoneStorageCliTests.test_dispatcher_runs_lazy_migration_for_explicit_project_root` | `rc=0`, 1 test; the pre-0.9 source was automatically migrated. |
| New refusal contract added before implementation | `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py MigrationSunsetTests.test_pre_0_9_layout_is_refused_with_0_11_x_guidance` | `rc=1`; `AssertionError: WorkflowError not raised`. |
| Same contract after implementation | same command | `rc=0`, 1 test. Typed refusal, `0.11.x` guidance, and source/no-destination byte assertions passed. |

## Detector boundary

The remaining detector refuses unresolved evidence without writing:

- Machine-level data still in the plain current-name host roots (`~/.claude/waystone`, `$CODEX_HOME/waystone`), excluding empty project-area scaffolding that is checked by project identity.
- Current-project slug residue under either a plain root or a completed migration's `.pre-0.9` preserved root.
- Pending project worktree `*.migrating` markers.
- Symlink/non-directory state encountered at a checked unsupported location.

A completed 0.11 layout may legitimately retain host-level `.pre-0.9/profile.yml` and `projects.json`; those files alone do not identify an unresolved project and are not refused. Current-project residue or a pending marker still is. This boundary was pinned by a green acceptance test.

## Test issue found and resolved

The first full `TaskCliTests` run produced 6 failures because the initial detector treated an intentionally preserved 0.11 `profile.yml` in the executing machine's home as unresolved for every project. That was a detector false positive, not a task CLI defect. The detector was corrected at the root cause: preserved host-only seed files are accepted, while project-slug residue and pending markers remain typed refusals. The unchanged TaskCli cluster then passed 17/17, including the linked-worktree-before-state-check guard.

No threshold was relaxed and no failing contract was skipped.

## Residual `rg "pre-0.9|pre_0_9"` audit

Counts below are matching lines from the complete repository scan (68 total).

| Category | Files | Matching lines | Why it remains |
|---|---|---:|---|
| Minimal live detector/refusal | `scripts/common.py` | 19 | Error type/code/message, read-only path inspection, and refusal entry points only. No move/copy/merge/repair implementation remains. |
| Contract tests | `scripts/tests/run_tests.py` | 12 | Typed refusal, no-mutation assertions, completed-0.11 acceptance, hook warning, and documentation literal coverage. |
| Current operator guidance | `references/conventions.md`, generated `docs/CONVENTIONS.md` | 4 | States that 0.12 does not migrate/repair and directs operators to released 0.11.x or manual migration. |
| Historical/governance records | `tasks.yaml`, `tasks.archive.yaml`, `ROADMAP.md`, `PROGRESS.md`, `dev_docs/0.9-pre-adr-storage-lock-autonomy.md`, `dev_docs/0.12.0-refactor-plan.md`, `dev_docs/overengineering-audit-2026-07-17.md`, `docs/adr/ADR-0011-project-context.md`, prior agent reports, prior review request/feedback | 33 | Task history, accepted ADR/design history, audit finding 5, incident records, and prior-review evidence; none is executable migration code. |

Additional live-call scan:

`rg -n 'migrate_project_state|migrate_home_data|require_supported_(machine|project)_state|Phase ?[12]|phase[ _-]?[12]|repair' scripts hooks references docs/CONVENTIONS.md --glob '!scripts/tests/run_tests.py' --glob '!docs/reviews/**' --glob '!docs/meta/**'`

This found only the two refusal shims, the new direct checks, unchanged callers, and refusal documentation. There is no remaining Phase 1/2 implementation or automatic repair path.

## Verification

- Focused refusal/dispatcher/hook/guard set: 7 tests, `rc=0`.
- `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py TaskCliTests`: 17 tests, `rc=0` after the false-positive correction above.
- `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py StoragePathTests DashboardLockingTests WaystoneStorageCliTests TaskCliTests UninitializedRootGateTests MigrationSunsetTests MigrationV2HookTests MigrationTests M2DocsTests CodexPluginContractTests`: 62 tests, `rc=0`.
- `uv tool run ruff@0.15.22 check scripts/common.py scripts/waystone.py scripts/tests/run_tests.py --select F401,F841`: `rc=0`, all checks passed.
- `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run python -m py_compile scripts/common.py scripts/waystone.py scripts/tests/run_tests.py`: `rc=0`.
- `git diff --check`: `rc=0`.
- Final full gate: `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/w2-sunset-suite.log 2>&1; sunset_suite_rc=$?; echo "suite rc=$sunset_suite_rc"; exit $sunset_suite_rc`: `rc=0`; log contains exactly `Ran 808 tests in 135.585s` and `OK`.
- Final worktree status: clean.

## Acceptance mapping

1. RED-first automatic behavior -> refusal transition: PASS.
2. Current-layout behavior and linked-worktree guard: PASS (focused and broad clusters green).
3. Complete residual scan and classification: PASS; live remainder is detection/refusal only.
4. Full suite: PASS, 808/808, `rc=0`.

VERDICT: PASS — pre-0.9 자동 이관·재개·repair 상태기계를 제거하고 typed 무변이 거부 계약으로 교체했으며 full suite 808/808을 통과했다.
COMMITS: 9d010c3ef5e22afd53d6d1a12974f499eb13ca5a
HOTFILES: `dev_docs/0.12.0-refactor-plan.md` 미접촉; `scripts/review.py` 미접촉; `scripts/common.py`의 pre-0.9 migration 구획을 detector/refusal로 교체; `scripts/tests/run_tests.py`의 Migration/TaskCli 및 직접 관련 dispatcher/hook 테스트만 접촉.
VERIFIED: RED old-green/new-red/new-green; 관련 62 tests rc=0; Ruff/py_compile/diff-check rc=0; full suite `Ran 808 tests`, `OK`, rc=0; worktree clean.
NOT-RUN: 금지된 `waystone` CLI, push, GPU 작업; `git add -A`도 실행하지 않음.
