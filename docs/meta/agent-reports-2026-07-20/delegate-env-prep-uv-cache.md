VERDICT: PASS — locked suite dependency와 pinned Ruff를 worktree-local uv namespace에 pre-warm하고, source 제거 후 UV_OFFLINE=1인 runner에서 suite·lint 실행을 재현했다.
COMMITS: 1281eb0374b47e8290475ef7e5f08a6c84eff688
HOTFILES: run_tests.py — DelegateRunTests transport-env assertion 및 UvCacheTests 인접 회귀 함수; delegate.py — env_prep 구획(:700~746)과 run_external 호출부(:2157)만 접촉. common.py 미접촉, fingerprint/marker 구획(:1040~:1440) 미접촉.
VERIFIED: hostile-index offline 회귀 rc=0; 관련 7-test 묶음 rc=0; `env -u FORCE_COLOR -u CLICOLOR_FORCE uvx ruff check . --select F401,F841` rc=0; `git diff --check` rc=0; `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py; echo "suite rc=$?"` 829 tests, suite rc=0.
NOT-RUN: 금지된 `waystone` CLI, push, 실제 Codex/Claude external runner는 실행하지 않았다. production PyPI를 향한 cold-cache prep은 별도 실행하지 않았고, 동일 prep 명령을 임시 HTTP index의 cold worktree cache에서 실행했다.

## 구현과 설계 선택

방향 (a), worktree-local uv cache pre-warm을 채택했다.

- `.waystone.yml`에 `uv sync --script scripts/tests/run_tests.py --locked`와 `uv tool run ruff@0.15.22 --version`을 명시했다.
- 신규 `scripts/tests/run_tests.py.lock`은 PyYAML 6.0.3의 source, artifact hash, 전체 지원 wheel을 고정한다.
- prep과 implementer transport가 동일한 `.waystone-uv-cache` 아래 `UV_CACHE_DIR`, `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR`를 사용한다. 지속 cache가 필요한 계약이므로 inherited `UV_NO_CACHE`는 제거하며, verifier-session guard도 implementer scope에서는 제거한다.
- transport 실행 동안만 해당 env를 설치하고 `finally`에서 기존 process env를 정확히 복원한다. Codex/Claude transport 본체와 금지된 fingerprint/marker 구획은 수정하지 않았다.

방향 (b), 부모 checkout 환경을 직접 재사용하는 표면은 기각했다. 부모 cache/tool environment는 worktree 밖의 mutable ambient state이며 runner sandbox의 writeability를 보장하지 못한다. 지원되지 않는 uv cache 내부 복사나 외부 environment 경로 재사용 대신, 선언된 prep이 격리된 worktree namespace를 materialize하도록 했다.

## 검증 증거

RED에서는 신규 회귀가 repo config의 `env_prep: null`을 관측해 rc=1이었다.

최종 회귀는 다음 경계를 실제 uv 0.6.13으로 검증한다.

1. 임시 HTTP package index와 별도 fixture cache로 script lock을 만든 뒤 fixture cache를 삭제한다.
2. delegate env_prep이 새 runner worktree의 빈 `.waystone-uv-cache`에 locked PyYAML과 pinned Ruff를 준비한다.
3. runner 진입 시 HTTP server를 종료하고 index 파일도 삭제한다.
4. inherited hostile `UV_INDEX=http://127.0.0.1:9/simple`을 테스트 setup에서 격리한 상태로, runner가 `UV_OFFLINE=1`에서 실제 `uv run scripts/tests/run_tests.py`와 `uvx ruff check scripts --select F401,F841`를 모두 rc=0으로 실행한다.
5. Ruff fixture는 argv와 lint target 존재를 검사하므로 단순 always-zero stub 통과가 아니다.

준비 실패의 기존 fail-closed 계약은 `DelegateRunTests.test_env_prep_failure_is_failed_env_no_runner`로 재확인했다. prep non-zero는 `failed-env`가 되고 runner는 시작되지 않는다.

검토 중 원본 source가 남아 있으면 offline 테스트가 거짓 양성이 될 수 있음을 반증했고, source 양쪽을 제거하자 `uv tool install` 방식은 unpinned offline `uvx`를 준비하지 못했다. 최종 구현은 같은 ephemeral cache 경로를 채우는 pinned `uv tool run ... --version`으로 교정했으며 source 종료·삭제 후 green을 재확인했다.

## 잔여 리스크와 머지 주의

- 빈 worktree cache의 최초 prep에는 configured package index 접근이 필요하다. source/network가 없으면 silent fallback 없이 `failed-env`로 끝난다. prepared cache 이후 runner의 offline gate만 이 변경의 보장 범위다.
- Ruff version은 0.15.22로 고정했지만 relevant environment/source digest를 VerificationPlan에 결속하는 전면 preflight 재설계는 본 task의 명시적 비-범위다.
- merge 시 `scripts/delegate.py`에서는 env_prep helper 구획과 `_run_claimed_body`의 transport 호출 한 곳만 충돌 해소 대상으로 삼고, :1040~:1440 병행 변경은 이 커밋으로 덮어쓰지 말 것.
- `scripts/tests/run_tests.py` 신규 회귀는 기존 `UvCacheTests` cluster 인접 위치다. 새 lockfile `scripts/tests/run_tests.py.lock`을 반드시 함께 머지해야 `--locked` prep이 clean checkout에서 동작한다.
