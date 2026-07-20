VERDICT: PASS — linked worktree의 task registry mutation을 migration/lock 전에 fail-closed로 차단했고 전체 829-test suite가 rc=0이다.
COMMITS: 6245a1e667f78264161ba8c9f7deb5141067044c
HOTFILES: run_tests.py 접촉(TaskCliTests의 기존 root-safety cluster 인접 신규 함수); common.py 미접촉; delegate.py 미접촉; tasks.py는 _SUB_OPTIONS/_resolve_root/need_root 인접 dispatch 구획만 접촉.
VERIFIED: 신규 actual linked-worktree 표적 테스트 rc=0; TaskCliTests+TaskArchiveTests 21건 rc=0; py_compile rc=0; git diff --check clean; env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py 최종 829건/137.211s/rc=0.
NOT-RUN: 금지된 waystone CLI 직접 실행 및 push는 하지 않았다. full ProjectContext 재설계와 list/show canonical normalization은 비-범위라 구현하지 않았다. 도구만 만들고 실행하지 않은 acceptance 검증은 없다.

## 구현

ADR-0011의 command policy와 warning-only 대안 기각에 따라 linked worktree에서의 registry mutation을 `noncanonical_intent_mutation`으로 거부한다. 대상은 `add`, 모든 `set` 형태, `drop`, 그리고 실제 두 registry 파일을 바꾸는 `archive`다. explicit linked root도 cwd-derived root와 같은 정책을 적용한다.

`scripts/tasks.py`의 root resolve 직후, 첫 `hold_project_lock()` 및 `migrate_project_state()`보다 앞에서 guard를 실행한다. 따라서 거부 경로는 linked checkout의 `.waystone/lock`을 만들거나 pre-0.9 Phase-2 project migration에 진입하지 않는다.

linked 판정은 `.git` file 모양만 사용하지 않는다. root에 결속된 단일 `git rev-parse --git-dir --git-common-dir` 관측을 수행하고 두 path를 absolute-normalize한 뒤 불일치를 linked signal로 사용한다. 이로써 submodule과 `--separate-git-dir` checkout의 file-only 오탐을 피한다. 잔류 `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR` 등 ambient Git repository 환경이 probe를 다른 checkout으로 돌리지 못하도록 probe 환경에서 모든 `GIT_*`를 제거한다.

Git metadata marker가 있는데 probe가 실패하거나 불완전하면 `project_context_unavailable`로 mutation을 fail-closed한다. filesystem Git metadata가 전혀 없는 기존 initialized project는 linked Git worktree가 아니므로 기존 동작을 유지한다. 이는 이 결함의 linked-worktree guard 범위이며 full ADR-0011 `ProjectContext` 구현을 가장하지 않는다.

## 검증 증거

사전 재현:

- guard 구현 전 actual repo + detached linked worktree 테스트는 implicit cwd와 explicit linked root의 `add/set/drop/archive` 5개 시도가 모두 rc=0이었고 `migrate_project_state` spy가 5회 호출되어 예상대로 실패했다.
- ambient canonical `GIT_DIR/GIT_WORK_TREE/GIT_COMMON_DIR` 회귀 case도 보강 전에는 rc=0 및 migration 1회 호출로 우회를 재현했다.

최종 회귀 테스트는 실제 Git repo에 `.waystone.yml`과 `tasks.yaml`을 commit하고 `git worktree add --detach`로 linked checkout을 만든다. 다음을 한 함수에서 검증한다.

- linked cwd implicit mutation 거부.
- explicit linked root의 `add/set/drop/archive` 전부 거부.
- 오도하는 ambient `GIT_*`가 있어도 거부.
- stderr에 stable code `noncanonical_intent_mutation`과 canonical checkout 실행 안내 포함.
- canonical/linked 양쪽 `tasks.yaml` bytes 불변, linked `.waystone` 미생성.
- 모든 거부 case에서 `migrate_project_state` 미호출.
- canonical cwd mutation 성공 및 linked cwd에서 explicit canonical root mutation 성공.

실행 명령과 결과:

```text
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py TaskCliTests.test_mutations_refuse_linked_worktree_before_migration_but_allow_canonical_checkout
=> rc=0

env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py TaskCliTests TaskArchiveTests
=> Ran 21 tests, rc=0

uv run python -m py_compile scripts/tasks.py scripts/tests/run_tests.py
=> rc=0

git diff --check
=> clean

env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py
=> Ran 829 tests in 137.211s, OK, suite rc=0
```

## 범위와 리스크

`task list/show`에는 mutation guard를 적용하지 않아 이번 패치의 동작 변경을 mutation으로 한정했다. 다만 현행 `need_root()` 공유 경로 때문에 list/show는 linked checkout의 local registry를 읽고 lazy migration도 수행할 수 있다. ADR-0011이 최종적으로 요구하는 canonical read normalization 및 strict read-only unavailable/refusal은 full `ProjectContext` 이관의 남은 gap이며, 이 패치가 해결했다고 주장하지 않는다.

`scripts/waystone.py`는 수정하지 않았다. `task`는 `_module_handles_phase2()` whitelist에 있어 dispatcher의 `_migrate_command_project()`를 건너뛰고 `tasks.py`가 Phase-2를 직접 소유한다. dispatcher Phase-1 machine migration은 project root와 무관하며 이번 결함의 pre-0.9 project migration 경로가 아니다.

bare repository validity, consent/install 등 다른 project-intent mutation surface, canonical machine-registry mapping은 비-범위다. 이 패치는 task registry 사고 경로만 수술적으로 닫는다.

## 머지 주의

- `scripts/tests/run_tests.py`: 기존 `TaskCliTests.test_uninitialized_explicit_root_is_refused_without_state_creation` 바로 뒤에 신규 함수 하나만 추가했다. 파일 말미 append나 무관 reformat은 없다.
- `scripts/tasks.py`: argument/dispatch root 구획만 변경했다. `scripts/common.py` 및 merge-base/ancestry 구획은 건드리지 않았다.
- local commit 1개만 존재하며 push하지 않았다.
