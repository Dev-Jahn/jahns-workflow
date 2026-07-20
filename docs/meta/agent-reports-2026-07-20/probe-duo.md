VERDICT: PASS — hostname identity drift와 marker 진단 3건을 수리했고 최종 전체 833 tests가 rc=0이다.
COMMITS: f25c62d75b6b9d050c16b588ac343b6541a80b49 (task 1), ba474001389b1837620b2b3b77b909f01eabb407 (task 2)
HOTFILES: scripts/delegate.py의 Codex runner fingerprint 비교/marker 판독·진단 구획 접촉; scripts/tests/run_tests.py의 기존 CodexRunnerVerificationGateTests 인접 구획 접촉; scripts/common.py 미접촉. env_prep/JW_REPORT 구획 미접촉.
VERIFIED: task 1 표적 4 tests rc=0 및 관련 클러스터 27 tests rc=0; task 2 표적 5 tests rc=0 및 관련 클러스터 30 tests rc=0; `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py` 최종 833 tests/134.494s, suite rc=0; base..HEAD `git diff --check` rc=0; 최종 worktree clean.
NOT-RUN: `waystone` CLI, push, merge는 계약상 실행하지 않았다. GPU 검증은 CPU-only 범위라 실행하지 않았다. 도구만 구축하고 미실행한 검증은 없다.

## Task 1 — fix/probe-machine-axis-hostname-drift

VERDICT: PASS — hostname-only 변화는 proof를 무효화하지 않고, stable host_identity 변화는 계속 재프로브한다.

### 구현과 선택 근거

- top-level `machine`(실제 값은 `platform.uname().node`)을 명시적인 `hostname` 진단 필드로 바꿨다.
- fingerprint 원문/marker JSON에는 `hostname`을 유지하되 `_codex_runner_comparison_view()`에서만 제거했다. 따라서 진단에는 남고 reuse·probe-during-change 판정에는 참여하지 않는다.
- hostname이 비어 있어도 진단 관측 실패가 fingerprint 수집을 막지 않도록 platform completeness gate에서 `uname.node`를 제거했다.
- `host_identity`(Linux machine-id/macOS IOPlatformUUID), platform architecture, principal, runtime/config, mount 축은 기존대로 exact-match 비교에 남겼다.
- proof schema를 `waystone-codex-runner-proof-2`에서 `-3`으로 올렸다. v2 proof는 hostname exact-match 의미로 발행됐으므로 새 의미로 조용히 재해석하지 않고 첫 실행에서 schema mismatch로 한 번 재프로브한 뒤 v3로 재기록한다. 그 다음 실행부터는 v3를 재사용한다.
- 기존 `machine` mismatch를 identity mismatch로 단언하던 테스트는 E-09와 모순되는 결함 계약이어서 개정했다. 대신 hostname-only reuse, isolated host_identity mismatch, v2→v3 1회 migration을 각각 고정했다.

### 검증 증거

- 표적 명령:
  `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py CodexRunnerVerificationGateTests.test_runtime_fingerprint_records_all_bounded_axes CodexRunnerVerificationGateTests.test_hostname_change_is_diagnostic_only_and_skips_probe CodexRunnerVerificationGateTests.test_environment_identity_and_version_mismatch_reprobe_and_name_axes CodexRunnerVerificationGateTests.test_v2_marker_reprobes_once_and_is_rewritten_as_v3`
  — 4 tests, rc=0.
- task 1 완료 시 `CodexRunnerVerificationGateTests` — 27 tests, rc=0.
- 최종 전체 suite에도 task 1 acceptance tests가 포함되어 rc=0.

### 리스크와 머지 주의

- 기존 v2 checkout-local marker는 의도적으로 한 번만 재프로브한다. 이는 silent reinterpretation을 피하기 위한 호환 정책이다.
- `docs/porting-ledger.md:771`에는 historical proof-2 인용과 이전 테스트 수가 남아 있다. 이 task의 금지/최소 범위를 지켜 수정하지 않았으며 main 문서 정리 시 갱신 여부를 판단해야 한다.

## Task 2 — fix/marker-diagnostics-polish

VERDICT: PASS — 세 진단 케이스를 정확히 안내/억제하면서 probe와 runner 실행은 유지한다.

### 구현

- marker 파일이 working tree에서 없어도 즉시 반환하지 않고 `git ls-files --stage`를 확인한다. index에 tracked 상태가 남은 삭제 marker는 첫 실행에서 untrack 안내를 한 번 출력하고 fresh probe를 실행한다.
- tracked/staged marker 안내를 `git rm --cached -f -- .waystone/codex-runner-verified`로 강화했다.
- lock 전 marker 판독은 `diagnose=False`, lock-held 재판독은 `diagnose=True`로 고정했다. 권위 있는 최종 상태만 안내하므로 다음 네 상태가 성립한다.
  - invalid→invalid: 안내 1회 + probe
  - invalid→valid: stale 안내 없음 + probe skip
  - valid→invalid: 새 mismatch 안내 1회 + probe
  - valid→valid: 안내 없음 + probe skip
- tracked present/deleted, staged invalid 테스트 모두 probe 1회와 runner 1회를 함께 단언해 안내가 실행을 막지 않음을 고정했다.

### 검증 증거

- 표적 명령:
  `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py CodexRunnerVerificationGateTests.test_lock_recheck_reports_fingerprint_mismatch_discovered_after_initial_check CodexRunnerVerificationGateTests.test_lock_recheck_suppresses_prelock_mismatch_if_race_resolves CodexRunnerVerificationGateTests.test_git_tracked_marker_is_ignored_and_reprobed_with_untrack_guidance CodexRunnerVerificationGateTests.test_tracked_marker_deleted_from_worktree_still_prints_untrack_guidance CodexRunnerVerificationGateTests.test_staged_invalid_marker_guidance_uses_forced_cached_removal`
  — 5 tests, rc=0.
- 관련 클러스터 첫 실행은 `test_marker_write_failure_is_loud_and_does_not_start_runner`에서 rc=1이었다. missing marker의 새 필수 `git ls-files` 호출을 기존 광범위 subprocess stub이 main runner로 오인한 것이 원인이었다. 테스트가 Git subprocess만 원 구현으로 통과시키도록 mock 경계를 바로잡았고, 해당 단일 test rc=0 및 전체 클러스터 30 tests rc=0으로 재검증했다. 실제 runner 0회 계약은 유지된다.
- 최종 전체 suite: `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py` — 833 tests, 134.494s, suite rc=0.

### 리스크와 머지 주의

- missing marker 판독도 Git index를 조회하므로 exposure-backed marker 테스트의 subprocess fake는 Git을 통과시켜야 한다. 관련 기존 fake를 보강했고 전체 suite가 통과했다.
- 두 커밋 모두 `scripts/delegate.py`와 hot-file `scripts/tests/run_tests.py`를 접촉한다. task 1 뒤 task 2 순서로 적용해야 하며, 테스트는 각각 기존 fingerprint/lock/tracked-marker 클러스터 인접 위치에만 추가했다.
- push/merge는 수행하지 않았다.
