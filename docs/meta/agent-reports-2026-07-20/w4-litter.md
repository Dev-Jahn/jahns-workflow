# w4-litter — linked read lock litter

## Result

- `list`/`show` now resolve scrubbed Git private/common/top-level context before the first project lock.
- A linked checkout is mapped to the proven canonical worktree and the same project-relative root; normal and nested projects read canonical `tasks.yaml` without creating linked `.waystone` state.
- If the canonical mapping cannot be proven, including a separate-Git-dir administrative-parent decoy, the command returns `project_context_unavailable` before lock/mkdir.
- The existing `noncanonical_intent_mutation` path and canonical mutation behavior remain green.

## RED evidence

Command:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py TaskCliTests.test_linked_worktree_reads_use_canonical_registry_without_linked_state > /tmp/w4-litter-red.log 2>&1; rc=$?; echo "red rc=$rc"; sed -n '1,120p' /tmp/w4-litter-red.log; exit $rc
```

Result: `rc=1`; both `list` and `show` failed because `linked/.waystone` existed after the read.

## Verification evidence

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py TaskCliTests > /tmp/w4-litter-taskcli-proof.log 2>&1; rc=$?; echo "TaskCliTests rc=$rc"; tail -n 35 /tmp/w4-litter-taskcli-proof.log; exit $rc
```

Result: `20 tests`, `OK`, `rc=0`. This covers canonical `list/show`, standard and nested linked normalization, fail-closed unprovable mapping, and the pre-existing mutation guard.

```bash
uv run python -m py_compile scripts/tasks.py scripts/tests/run_tests.py; rc=$?; echo "py_compile rc=$rc"; exit $rc
```

Result: `rc=0`.

```bash
git diff --check; rc=$?; echo "diff-check rc=$rc"; exit $rc
```

Result: `rc=0`.

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"
```

Result: `suite rc=0`; `Ran 830 tests in 147.274s`; `OK`.

VERDICT: PASS — linked task list/show는 lock 이전 canonical 정규화 또는 typed refusal하며 linked checkout 생성물은 0이고 full suite가 green이다.
COMMITS: 726dc9d9382d4af4c7bb383f4d9f58eba997c5dc
HOTFILES: scripts/tasks.py root-resolution/dispatch; scripts/tests/run_tests.py TaskCliTests 6763-6892; dev_docs/0.12.0-refactor-plan.md·scripts/review.py·scripts/common.py 미접촉
VERIFIED: RED rc=1(.waystone 생성 재현); TaskCliTests 20/20 rc=0; py_compile rc=0; git diff --check rc=0; full suite 830/830 rc=0(147.274s)
NOT-RUN: waystone CLI·push는 금지에 따라 미실행; rebase/merge는 이 task 범위 밖이라 미실행
