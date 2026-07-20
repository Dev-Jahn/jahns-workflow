# WS-GPT-306 — linked read selector initialization gate

- Base HEAD: `99d773005be1cc79da79642ccde9e8e532e13ddf`
- Result HEAD: `9d7edaabbbabc7ac6b81c87e65faf097a1f0ff04`

## Change

- `scripts/tasks.py`: `_canonical_read_root`가 Git/canonical 탐침 전에 active selector 자체를
  `require_initialized_root(root)`로 검증한다. 따라서 config가 없는 explicit selector는 기존 typed
  error로 거부되고 canonical same-relative project로 치환되지 않는다.
- `scripts/tests/run_tests.py`: canonical main에만 initialized nested project/task가 있고 linked orphan
  branch의 같은 상대경로에는 config가 없는 실제 worktree fixture를 추가했다. rc·task 노출·typed
  refusal·linked state·canonical lock/state를 함께 검증한다.

## Acceptance evidence

### 1. RED → green

수정 전 실행:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py TaskCliTests.test_linked_read_refuses_uninitialized_explicit_selector_before_canonical_redirect
```

- rc=1 (expected RED)
- actual tuple: `(0, True, False, False, True)`
  - task command rc=0
  - canonical-only task 노출=True
  - typed refusal=False
  - linked state 생성=False
  - canonical lock 생성=True

수정 후 아래 focused run에 같은 테스트를 포함했고 green이었다.

### 2. 관련 계약 회귀

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py TaskCliTests.test_linked_read_refuses_uninitialized_explicit_selector_before_canonical_redirect TaskCliTests.test_mutations_refuse_linked_worktree_before_state_check_but_allow_canonical_checkout TaskCliTests.test_linked_worktree_reads_use_canonical_checkout_without_linked_state TaskCliTests.test_linked_nested_project_read_maps_to_same_canonical_project TaskCliTests.test_linked_read_refuses_unprovable_canonical_root_before_state_creation TaskCliTests.test_uninitialized_explicit_root_is_refused_without_state_creation
```

- rc=0, `Ran 6 tests`, `OK`
- 정상 linked read 정규화 3건, mutation guard, cwd 암묵 discovery subcase, explicit
  uninitialized-root typed refusal를 포함한다.

### 3. Full suite

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"
```

- `suite rc=0`
- `/tmp/suite.log`: `Ran 833 tests in 134.824s`, `OK`

### 4. Scope/diff

```bash
git diff --check
git status --short --branch
```

- diff check rc=0
- commit 후 worktree clean
- 허용된 `scripts/tasks.py`, `scripts/tests/run_tests.py` 외 repo 파일 변경 없음

VERDICT: PASS — active explicit selector의 초기화를 canonical 정규화 전에 강제해 조용한 권위 치환과 canonical lock 생성을 막았고, 모든 pre-registered acceptance를 통과했다.
COMMITS: 9d7edaabbbabc7ac6b81c87e65faf097a1f0ff04
HOTFILES: scripts/tests/run_tests.py의 TaskCliTests linked-read normalization cluster에 신규 회귀 테스트 추가; dev_docs/0.12.0-refactor-plan.md·scripts/review.py·scripts/common.py 미접촉.
VERIFIED: RED 명령 rc=1(actual `(0, True, False, False, True)`); focused 6 tests rc=0; full suite 833 tests rc=0; git diff --check rc=0.
NOT-RUN: waystone CLI는 금지에 따라 실행하지 않았다. GPU·network 검증은 이 task에 불필요해 실행하지 않았다.
