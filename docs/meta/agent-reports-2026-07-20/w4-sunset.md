# w4 sunset detector report

VERDICT: PASS — WS-GPT-207·208의 fail-open을 typed refusal로 닫았고 최종 full suite 821 tests가 rc=0이다.
COMMITS: db4c9b377e3cca083359de577496e5f4342bea53, 37ea9803ed93194a1281336b41a9ea5b79ddc8bd
HOTFILES: `scripts/common.py` sunset detector의 preserved-profile 비교 helper와 marker-container 검사 구획; `scripts/tests/run_tests.py`의 기존 `MarkerTests` HOME 격리 및 `MigrationSunsetTests` 인접 테스트. plan·review.py는 접촉하지 않았다.
VERIFIED: 아래 RED/green 명령과 최종 full suite를 실행했다. base `81bd177` 대비 변경 파일은 `scripts/common.py`, `scripts/tests/run_tests.py`뿐이며 `git diff --check 81bd177..HEAD` rc=0, 최종 worktree clean이다.
NOT-RUN: 금지된 `waystone` CLI는 실행하지 않았다. GPU·외부 데이터 검증은 이 작업에 해당하지 않는다.

## WS-GPT-207 — preserved profile divergence

- RESUME 판단: 잔존 +44행은 전부 이 task의 테스트 2개였고 계약상 올바르므로 승계했다. 다만 live offender 기대 경로는 detector가 canonical project root를 사용하는 기존 동작에 맞게 `live.resolve()`로 교정했다. WS-GPT-208 테스트 잔존은 없었다.
- 구현: 각 real `.pre-0.9` host root의 regular `profile.yml`을 no-follow로 수집해 raw bytes를 비교한다. preserved profile이 하나라도 있으면 존재하는 live profile도 같은 비교에 포함한다. 분기하면 모든 참여 profile 경로를 기존 `Pre09StateError` offender로 넘기며 원본을 읽기 외에는 건드리지 않는다. symlink/non-directory root·profile은 따라가지 않고 typed refusal한다.
- RED 원문: `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py MigrationSunsetTests.test_divergent_preserved_profiles_are_refused_without_repair MigrationSunsetTests.test_preserved_profile_mismatching_live_is_refused_without_repair > /tmp/w4-207-red.log 2>&1; rc=$?; sed -n '1,220p' /tmp/w4-207-red.log; echo "focused 207 RED rc=$rc"` → rc=1, 2/2 `Pre09StateError not raised`.
- GREEN 원문: `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py MigrationSunsetTests.test_divergent_preserved_profiles_are_refused_without_repair MigrationSunsetTests.test_preserved_profile_mismatching_live_is_refused_without_repair MigrationSunsetTests.test_completed_0_11_seed_and_empty_scaffolding_are_accepted > /tmp/w4-207-green-after-audit.log 2>&1; rc=$?; sed -n '1,180p' /tmp/w4-207-green-after-audit.log; echo "focused 207 audited rc=$rc" && git diff -- scripts/common.py && git diff -- scripts/tests/run_tests.py | sed -n '1,180p'` → rc=0, 3 tests. 분기 2종은 거부되고 동일 preserved + 동일 live seed는 계속 수용된다.
- 전체 suite 첫 실행은 실제 사용자 HOME의 preserved profile을 임시 project fixture와 섞던 기존 비격리 `MarkerTests.test_review_cli_reports_missing_reviewer_binding_without_traceback` 1건 때문에 rc=1(821 tests)이었다. production 계약을 완화하지 않고 해당 CLI test를 임시 HOME으로 격리했다. focused 원문 `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py MarkerTests.test_review_cli_reports_missing_reviewer_binding_without_traceback > /tmp/w4-hermetic-marker.log 2>&1; rc=$?; sed -n '1,180p' /tmp/w4-hermetic-marker.log; echo "focused hermetic marker rc=$rc" && git diff --check && git diff -- scripts/tests/run_tests.py` → rc=0.

## WS-GPT-208 — marker container symlink/non-directory

- RESUME 판단: 이전 기체의 symlink/regular-file 테스트나 재현 증거는 worktree에 없었다. 두 fixture를 새로 작성하고 production 변경 전에 직접 RED를 캡처했다.
- 구현: `cache/worktrees/<slug>`가 존재하지만 lstat 기준 real directory가 아니면 container 자체를 offender로 추가한다. symlink target은 follow/unlink하지 않고 regular file도 수정하지 않는다. real directory에서는 기존대로 immediate `*.migrating` child만 offender다.
- RED 원문: `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py MigrationSunsetTests.test_symlinked_marker_container_is_refused_without_repair MigrationSunsetTests.test_regular_file_marker_container_is_refused_without_repair > /tmp/w4-208-red.log 2>&1; rc=$?; sed -n '1,220p' /tmp/w4-208-red.log; echo "focused 208 RED rc=$rc"` → rc=1, 2/2 `Pre09StateError not raised`.
- GREEN 원문: `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py MigrationSunsetTests.test_symlinked_marker_container_is_refused_without_repair MigrationSunsetTests.test_regular_file_marker_container_is_refused_without_repair MigrationSunsetTests.test_pending_worktree_marker_is_refused_without_repair > /tmp/w4-208-green.log 2>&1; rc=$?; sed -n '1,220p' /tmp/w4-208-green.log; echo "focused 208 green rc=$rc"` → rc=0, 3 tests.
- 클러스터 원문: `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py MigrationSunsetTests > /tmp/w4-sunset-class-final.log 2>&1; rc=$?; sed -n '1,220p' /tmp/w4-sunset-class-final.log; echo "MigrationSunsetTests final rc=$rc"` → 8 tests, rc=0.
- 최종 gate 원문: `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"` → `suite rc=0`; `/tmp/suite.log`에는 `Ran 821 tests in 143.401s`, `OK`가 기록됐다.
