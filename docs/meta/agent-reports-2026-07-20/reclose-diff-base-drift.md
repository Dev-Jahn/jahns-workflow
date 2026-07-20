VERDICT: PASS — 같은 round의 close 재수행이 최초 previous-round tip을 review diff base로 보존한다
COMMITS: 2b11aefc245bc4f582a10afba97aad3f742fe599
HOTFILES: scripts/tests/run_tests.py 접촉 — RoundExposureTests의 기존 reclose exposure 클러스터 인접 위치에 신규 테스트 1건 추가; scripts/common.py·scripts/delegate.py 미접촉
VERIFIED: RED 재현 rc=1; 표적 재현 rc=0; RoundExposureTests/RoundCloseTests/PacketPublicationTests 75건 rc=0; 경계 회귀 2건 rc=0; git diff --check rc=0; 최종 전체 스위트 829건 rc=0
NOT-RUN: waystone CLI(계약상 금지); push·merge(계약상 금지); GPU(불필요). 도구만 구축한 검증은 없으며 위 테스트는 모두 실제 실행 완료

## 구현

- `scripts/review.py`가 같은 round의 모든 immutable exposure generation을 기존 계약대로 검증한 뒤, unsuffixed generation 1을 명시적으로 읽을 수 있게 했다. suffix exposure만 있고 generation 1이 없으면 원 base를 추측하지 않고 실패한다.
- `scripts/round.py`의 반복 close는 현재 config watermark(`prev_wm`)와 review base를 분리한다. 최초 close는 기존처럼 `prev_wm`을 base로 쓰고, 같은 round의 후속 close는 generation 1에 결속된 `base_sha`를 재사용한다.
- 최신 exposure 선택과 review request 소비 계약은 그대로 유지했다. 따라서 후속 close의 새 HEAD가 target이 되면서도 diff base는 원 previous-round tip으로 남는다.
- 상태 스키마나 review request 형식은 변경하지 않았다.

## 검증 증거

1. 수정 전 재현:

   `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py RoundExposureTests.test_same_round_reclose_preserves_original_previous_round_diff_base`

   rc=1. 두 번째 close exposure가 원 previous-round tip 대신 첫 close tip을 base로 기록하는 기존 결함을 확인했다.

2. 수정 후 표적 재현:

   동일 명령 rc=0. 테스트는 비-null previous-round tip을 만든 뒤 첫 close를 대조군으로 확인하고, drift된 generation 2와 추가 커밋을 거쳐 같은 round를 다시 close한다. 최신 exposure와 생성된 review request/binding 모두 원 base와 새 target을 사용함을 검증한다.

3. 관련 클러스터:

   `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py RoundExposureTests RoundCloseTests PacketPublicationTests`

   75 tests, rc=0.

4. 첫 전체 스위트에서 기존 `BoundaryWarnTests.test_round_close_warn_import_failure_keeps_committed_close_success` 1건이 실패했다. 원인은 새 preflight가 `overlay`를 먼저 import하여 해당 테스트의 의도된 import-fault 순서를 소비한 것이었다. 테스트를 완화하지 않고 exposure directory 계산을 기존 공용 `project_state_path`로 바꿔 조기 import를 제거했다.

   `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py BoundaryWarnTests.test_round_close_warn_import_failure_keeps_committed_close_success RoundExposureTests.test_same_round_reclose_preserves_original_previous_round_diff_base`

   2 tests, rc=0.

5. 최종 게이트:

   `git diff --check && env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py; suite_rc=$?; echo "suite rc=$suite_rc"; exit "$suite_rc"`

   `Ran 829 tests in 136.853s`, `OK`, `suite rc=0`.

## 리스크와 머지 주의

- 반복 `round close` 결함 경로만 수정했다. 별도 `round reclose` 명령의 계약과 review/exposure 형식은 변경하지 않았다.
- generation 1이 보존된 기존 기록은 이후 반복 close에서 스스로 원 base로 복구된다. generation 1 자체가 없는 손상된 기록은 정확한 base를 복원할 근거가 없으므로 fail-closed 한다.
- 커밋은 hot-file 테스트 추가를 관련 기존 클러스터에 인접시켰으며, 다른 hot-file은 건드리지 않았다.
