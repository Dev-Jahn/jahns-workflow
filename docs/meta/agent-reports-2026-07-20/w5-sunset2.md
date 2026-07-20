# w5-sunset2 — sunset profile regression + worktree-cache ancestor defense

## Task 1 — fix/sunset-live-profile-overreach (WS-GPT-304 ②)

- 계약 대조: preserved host profile끼리의 raw-byte 분기만 pre-0.9 ambiguity다. live `.waystone/profile.yml`은 복원 불가능한 현재 human-authored 권위이므로 content 비교/offender 집합에서 제외했다. live의 기존 symlink/non-regular-file guard는 별도 type 관심사로 유지했다.
- RED 명령 원문:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE HOME=/private/tmp/w5-sunset2-task1-red-home uv run scripts/tests/run_tests.py MigrationSunsetTests.test_divergent_preserved_profiles_are_refused_without_repair MigrationSunsetTests.test_preserved_profile_mismatching_live_is_accepted_without_repair MigrationSunsetTests.test_preserved_profile_without_live_is_accepted_without_repair
```

  결과: `rc=1`; 새 live-mismatch 수용 oracle만 현행 `Pre09StateError`로 ERROR, missing-live와 preserved-host divergence는 각각 기대대로 통과했다.
- 수리: `scripts/common.py::_append_preserved_profile_conflicts`에서 live를 `profiles` content 집합에 추가하던 한 줄을 제거했다. 원본 복사·수정·seed fallback은 추가하지 않았다.
- 계약 테스트: 기존 live-mismatch oracle을 수용으로 반전했고 bytes 무수정을 유지했다. preserved 단독 + missing-live 수용 테스트를 추가했다. 기존 divergent-preserved 거부 테스트는 변경하지 않았다.
- GREEN 명령 원문:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE HOME=/private/tmp/w5-sunset2-task1-green-home uv run scripts/tests/run_tests.py MigrationSunsetTests.test_divergent_preserved_profiles_are_refused_without_repair MigrationSunsetTests.test_preserved_profile_mismatching_live_is_accepted_without_repair MigrationSunsetTests.test_preserved_profile_without_live_is_accepted_without_repair
env -u FORCE_COLOR -u CLICOLOR_FORCE HOME=/private/tmp/w5-sunset2-task1-cluster-home uv run scripts/tests/run_tests.py MigrationSunsetTests
```

  결과: 각각 `3 tests, OK, rc=0`; `9 tests, OK, rc=0`.
- 커밋: `0746bc55c072c85903e91930648616881ef2f703` (`fix: exclude live profile from sunset conflicts`).

## Task 2 — fix/worktrees-cache-ancestor-symlink (WS-GPT-305)

- `_mkdir_or_refuse` 호출처 전수 분석(3/3 모두 engine-owned, 범위 제외 0):
  - `.waystone/delegations` → owned root `project_state_path(root)`
  - `.waystone/delegations/<did>/artifact` → owned root `project_state_path(root)`; `record_dir`를 root로 쓰지 않아 상위 `delegations`도 재검사
  - machine `cache/worktrees/<slug>` → owned root `machine_dir()`; `worktrees_cache_dir()`를 root로 쓰지 않아 `cache` 조상도 검사
- RED 명령 원문:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE HOME=/private/tmp/w5-sunset2-task2-red-home uv run python - <<'PY'
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "scripts"))
import common
import delegate

with tempfile.TemporaryDirectory() as d:
    base = Path(d)
    home = base / "home"
    root = base / "repo"
    external = base / "external"
    home.mkdir()
    root.mkdir()
    external.mkdir()
    os.environ["HOME"] = str(home)
    os.environ["CODEX_HOME"] = str(home / ".codex")
    os.environ["WAYSTONE_HOME"] = str(home / ".waystone")

    worktrees = home / ".waystone" / "cache" / "worktrees"
    worktrees.parent.mkdir(parents=True)
    worktrees.symlink_to(external, target_is_directory=True)
    target = worktrees / common._project_slug(root)

    detector_result = common.migrate_project_state(root)
    delegate._mkdir_or_refuse(target)

    print(f"detector_result={detector_result}")
    print(f"ancestor_is_symlink={worktrees.is_symlink()}")
    print(f"external_write={(external / target.name).is_dir()}")
PY
```

  결과: `rc=0`, `detector_result=False`, `ancestor_is_symlink=True`, `external_write=True`.
- detector 수리: marker 경로를 보기 전에 `machine_dir(home) → cache → cache/worktrees`를 순서대로 `lstat`; missing이면 안전 종료하고 첫 symlink/non-directory를 기존 `Pre09StateError` offender로 반환한다. machine root 위 OS 조상은 검사하지 않는다.
- mkdir 수리: `_mkdir_or_refuse(path, *, owned_root)`로 모든 호출처가 root를 명시한다. `resolve()` 없이 lexical `abspath` + `relative_to`로 containment를 증명하고, owned root부터 target까지 기존 component를 `lstat`해 symlink/non-directory/관측 실패를 `_RefusedWrite`로 거부한 뒤에만 mkdir한다.
- 독립 방어 테스트: detector는 `cache` 및 `cache/worktrees` 각각의 symlink/non-directory를 첫 offender로 거부한다. library `run_delegation` 경로는 migration detector를 우회한 채 조상 symlink를 거부하고 external `<slug>`를 만들지 않는다. 별도 monkeypatch fixture로 machine root 밖 cache containment도 external write 없이 거부한다.
- GREEN/회귀 명령 원문:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE HOME=/private/tmp/w5-sunset2-task2-green-home uv run scripts/tests/run_tests.py MigrationSunsetTests.test_pending_worktree_marker_is_refused_without_repair MigrationSunsetTests.test_unsafe_marker_ancestor_is_refused_without_repair MigrationSunsetTests.test_symlinked_marker_container_is_refused_without_repair MigrationSunsetTests.test_regular_file_marker_container_is_refused_without_repair MigrationSunsetTests.test_completed_0_11_seed_and_empty_scaffolding_are_accepted DelegateRunTests.test_run_refuses_symlinked_worktrees_cache_ancestor_without_external_write DelegateRunTests.test_run_refuses_worktrees_cache_outside_machine_root_without_write DelegateRunTests.test_success_path_contract_and_exposure
env -u FORCE_COLOR -u CLICOLOR_FORCE HOME=/private/tmp/w5-sunset2-task2-cluster-home uv run scripts/tests/run_tests.py MigrationSunsetTests DelegateRunTests
```

  결과: 각각 `8 tests, OK, rc=0`; `53 tests, OK, rc=0`. 기존 leaf-symlink, leaf regular-file, pending marker, real-directory delegation 경로가 모두 green이다.
- 최종 suite 명령 원문:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"
```

  결과: `Ran 834 tests in 143.022s`, `OK`, `suite rc=0`; 최종 tracked worktree clean.
- 커밋: `704eb0f12dff192ca95b56b9d72356fa734931d3` (`fix: refuse redirected worktree cache paths`).

VERDICT: PASS — WS-GPT-304 ②와 WS-GPT-305를 계약대로 수리했고 전체 834-test gate가 rc=0이다.
COMMITS: 0746bc55c072c85903e91930648616881ef2f703, 704eb0f12dff192ca95b56b9d72356fa734931d3
HOTFILES: dev_docs/0.12.0-refactor-plan.md 미접촉; scripts/review.py 미접촉; scripts/common.py `_append_preserved_profile_conflicts`·marker ancestor 구획; scripts/delegate.py `_mkdir_or_refuse`·3개 호출처; scripts/tests/run_tests.py `DelegateRunTests`·`MigrationSunsetTests` 인접 클러스터
VERIFIED: task1 RED rc=1 → focused 3/3 + sunset 9/9 green; task2 RED detector=False/external_write=True → focused 8/8 + 관련 클래스 53/53 green; 지정 full suite `Ran 834 tests`, `OK`, rc=0
NOT-RUN: `waystone` CLI(금지 준수); GPU/network 검증(필요 없음); legacy 출력 동등성 gate(노선 B ruling상 합격 기준 아님)
