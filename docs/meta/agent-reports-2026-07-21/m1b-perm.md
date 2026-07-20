# m1b-perm 구현 보고서

- Task: `fix/run-store-permission-hardening`
- Branch: `m1b/perm`
- Base: `2f1dde2 feat(m1b): external effect commit protocol 엔진 (feat/run-effect-protocol)`
- Implementation commit: `f373e9b fix(m1b): harden run store permissions`
- Push: 수행하지 않음

## 1. 구현 요약과 파일 목록

ADR-0013의 `DB·artifact permission과 symlink` 절을 run store 계층에 국소 적용했다.
기존 API signature, SQLite schema, effect package-internal surface는 바꾸지 않았다.

- `waystone/runs/store.py`
  - state directory를 신규 생성할 때 `0700`, DB/`-wal`/`-shm`을 `os.open`의
    `O_CREAT|O_EXCL|O_NOFOLLOW`와 `0600`으로 선생성한다.
  - 기존 state directory, DB, WAL, SHM의 owner·mode·kind·containment와 descriptor identity를
    검증하고 자동 `chmod`/`chown` 없이 typed refusal한다.
  - state symlink/escape/type mismatch와 검증 불가를 ADR의 typed code로 분리했다.
  - SQLite에는 이미 검증·생성된 DB만 열도록 URI `mode=rw`를 사용해 누락 시 재생성 fallback을
    막았다.
- `waystone/runs/artifacts.py`
  - `.waystone/`과 `artifacts/` 신규 directory를 `0700`으로 생성·검증한다.
  - staging leaf를 `O_CREAT|O_EXCL|O_NOFOLLOW`, `0600`으로 생성하고 descriptor에서 write/fsync/
    digest 검증한다.
  - 같은 staging descriptor를 `0400`으로 만든 뒤에만 atomic replace하여 final path가 처음
    나타나는 순간부터 immutable mode가 되게 했다.
  - root/leaf symlink, escape, kind, owner/mode 결함을 typed integrity finding으로 거부하고
    final bytes는 no-follow descriptor에서 읽고 재해시한다.
  - 동시 same-digest publisher의 정상 inode 교체는 bounded re-verification으로 처리한다.
- `waystone/runs/lease.py`
  - advisory lock의 engine-owned parent traversal을 lstat/no-follow로 재검증한다.
  - lock leaf를 공통 state-file opener로 열어 신규 `0600`과 `O_NOFOLLOW`를 강제하며,
    실제 handle 획득 뒤 기존 DB principal 재검사는 그대로 유지했다.
- `scripts/tests/test_run_store.py`
  - 기존 테스트 본문은 수정하지 않고 store/artifact 권한·owner·symlink·동시 publish 계약 테스트를
    추가했다.
- `scripts/tests/test_run_lease.py`
  - 기존 테스트 본문은 수정하지 않고 lock `0600`/`O_NOFOLLOW`와 regular-file target symlink
    refusal 테스트를 추가했다.

`scripts/tests/run_tests.py`에는 `RunStoreTests`, `ArtifactStoreTests`, `RunLeaseTests`가 이미 aggregate에
등록되어 있어 중복 등록 변경을 하지 않았다. 신규 의존성은 없다.

## 2. 계약 매핑

분해 계획상 이 task에 직접 귀속된 promoted-contract PC 또는 exit fixture 번호는 없고,
직접 귀속 행은 ADR-0013 permission/no-follow 절 하나다. 아래의 “필수 fixture”는 이번 briefing이
그 ADR 행을 구체화한 다섯 검증 의무를 뜻한다.

| 할당 계약 / fixture 행 | 이를 직접 단언하는 테스트 함수 |
|---|---|
| ADR-0013: 신규 runtime/artifact directory `0700` | `test_new_runtime_objects_have_exact_modes_and_nofollow`; `test_artifact_staging_creation_and_atomic_publish_have_exact_modes` |
| ADR-0013: 신규 DB/WAL/SHM과 lock leaf `0600` | `test_new_runtime_objects_have_exact_modes_and_nofollow`; `test_advisory_lock_creation_is_0600_and_nofollow` |
| ADR-0013: staging은 생성 순간부터 `0600`, final artifact는 publish 전에 `0400` | `test_artifact_staging_creation_and_atomic_publish_have_exact_modes` |
| ADR-0013: 기존 state directory/sidecar의 unsafe mode 또는 foreign owner를 자동 수리하지 않고 `unsafe_state_permissions` | `test_existing_sidecar_unsafe_mode_or_foreign_owner_refuses_before_connect`; `test_unsafe_existing_state_directory_refuses_without_repair_or_write` |
| ADR-0013: DB leaf no-follow와 typed state symlink refusal | `test_state_database_symlink_is_refused_at_nofollow_open`; `test_new_runtime_objects_have_exact_modes_and_nofollow` |
| ADR-0013: artifact root/leaf symlink를 follow/hash/delete하지 않고 root/path typed finding으로 거부 | `test_artifact_root_and_leaf_symlinks_are_typed_without_following` |
| ADR-0013: lock leaf가 regular file을 가리키는 symlink여도 open 시 `O_NOFOLLOW`로 거부하고 `flock`에 진입하지 않음 | `test_advisory_lock_symlink_is_refused_at_open_before_flock` |
| 동시 same-digest publish가 no-follow descriptor 검증 중 정상 inode 교체를 corruption으로 오인하지 않음 | `test_concurrent_artifact_publish_survives_verified_inode_churn` |
| 인접 PC-18/PC-19 보존 확인(직접 귀속 아님) | `test_pc18_attempt_evidence_and_decision_identities_are_append_only`; `test_pc19_corrupt_run_is_typed_unknown_without_blocking_healthy_run`; `test_pc19_missing_or_reparented_children_and_historical_damage_are_run_local` |

## 3. 검증 결과

### 필수 aggregate

실행 명령:

```sh
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1b-perm.log 2>&1; echo "suite rc=$?"
```

- 결과: **suite rc=1**
- 로그: `/tmp/suite-m1b-perm.log`
- 총 986 tests, 109.644s
- 984 pass, error 2, failure 0
- error는 아래 §4.1의 기존 immutable-artifact fixture 두 건뿐이다.
  - `ArtifactStoreTests.test_artifact_read_reports_corruption_and_unreadable_bytes_as_integrity_errors`
  - `ArtifactStoreTests.test_corrupt_existing_artifact_is_not_silently_repaired`

따라서 “전체 suite green” 자체는 달성하지 못했다. 새 final artifact `0400` 계약과 기존 테스트의
직접 overwrite가 동시에 성립할 수 없고, briefing이 이 경우 기존 fixture를 수정하지 말고 보고하라고
명시했으므로 mode를 약화하거나 테스트를 바꾸지 않았다.

### 추가 검증

- `uv run scripts/tests/run_tests.py RunStoreTests RunLeaseTests`
  - rc=0, 39 tests green
- `uv run scripts/tests/run_tests.py RunEffectTests RunSpecTests RunPreflightTests`
  - rc=0, 66 tests green
- 신규 artifact concurrency stress
  - 8 writers × 200 rounds, 200/200 green
- `git diff --check`
  - clean
- 독립 diff reviewer
  - 동시 publish inode 교체와 owner-unverifiable 분류 지적을 반영한 뒤 신규 blocker 없음
  - SQLite actual-open no-follow 한계와 기존 fault-injection seam은 needs-ruling으로 분류

aggregate 실행 전후 ignored diagnostic:

- `.waystone/lock`: mode `0644`, size 219, mtime `1784578242`에서 size 90,
  mtime `1784580263`으로 legacy aggregate가 갱신했다.
- `.waystone/.gitignore`: 선재했고 size 2, mode `0600`, mtime `1784578242`로 전후 동일했다.
- `.waystone/resume.md`: 선재했고 size 3930, mode `0600`, mtime `1784580055`로 전후 동일했다.
- 계약의 알려진 aggregate 예외에 따라 위 파일을 복원·삭제하지 않았다.

## 4. 계약 해석 및 needs-ruling 후보

1. **Final `0400`과 기존 corruption fixture의 직접 overwrite 충돌 (aggregate blocker).**
   위 두 기존 테스트는 `ArtifactStore.write()`가 반환한 final path에 곧바로
   `Path.write_bytes()`를 호출한다. effective uid 501에서 새 계약의 `0400` file은 의도대로
   쓰기 불가여서 두 테스트 모두 검증 본문 전에 `PermissionError`로 끝난다. briefing은 기존
   테스트 수정 금지와 “새 mode 계약과 충돌하면 수정하지 말고 REPORT ④”를 함께 지시했다.
   보수적으로 ADR mode를 유지했다. suite green을 원하면 해당 기존 fixture가 의도적 운영 행위로
   mode를 명시적으로 열고 bytes를 훼손한 뒤 다시 `0400`으로 닫도록 owner ruling이 필요하다.

2. **Descriptor read와 기존 `Path.read_bytes` fault seam 충돌.**
   두 기존 corruption 테스트의 후속 분기는 `Path.read_bytes`를 mock하여 unreadable/disappearing
   상태를 주입한다. no-follow를 실제 read까지 유지하려면 verified descriptor에서 읽어야 하므로
   그 mock seam은 더 이상 실행되지 않는다. path-based fallback read를 추가하면 ADR no-follow를
   깨므로 넣지 않았다. 1번 fixture가 갱신될 때 fault 주입도 `os.open`/descriptor read 경계로
   옮겨야 한다.

3. **SQLite actual open에는 stdlib가 `O_NOFOLLOW`를 전달하지 못한다.**
   구현은 DB/WAL/SHM을 `O_NOFOLLOW` descriptor로 검증·선생성한 뒤 descriptor를 닫고,
   `sqlite3.connect(...?mode=rw, uri=True)`가 pathname을 다시 연다. CPython `sqlite3`에는 SQLite
   VFS open flag에 `O_NOFOLLOW`를 전달하거나 이미 연 fd와 WAL/SHM naming을 함께 넘기는 지원 API가
   없다. 따라서 actual SQLite open 자체에 `O_NOFOLLOW`를 적용했다고 주장하지 않는다. 현재 구현은
   ADR이 의도적 swap/TOCTOU를 비보호 대상으로 둔 경계 안의 fail-closed preflight이며, literal한
   “DB leaf를 no-follow 방식으로 연다”까지 요구하면 stdlib+D8 안에서 별도 architecture ruling이
   필요하다.

4. **기존 object mode는 ADR의 의미 검사로 판정했다.**
   briefing 요약의 “요구보다 넓으면”을 exact numeric upper bound로 읽으면 기존 `0755` directory나
   `0644` mutable file도 거부해야 한다. 그러나 ADR 전문은 기존 object에 대해 owner access,
   ownership, non-owner write 부재와 final artifact write-bit 부재를 명시한다. “절 전문 우선”에
   따라 신규 object만 exact `0700`/`0600`/`0400`, 기존 object는 그 의미 조건으로 검증했다.
   group/other read·search까지 금지하려는 의도였다면 ADR 문언 수정 또는 ruling이 필요하다.

5. **umask와 생성 후 chmod 금지의 결합.**
   POSIX `os.open`/`os.mkdir`에 explicit mode를 전달해도 process umask는 owner bit까지 더 좁힐 수
   있다. process-global umask를 일시 변경하면 thread race가 생기고, path 생성 후 chmod는 briefing이
   금지한 창을 만든다. 구현은 requested mode를 명시하고 descriptor/lstat에서 exact mode를 확인하여
   umask가 owner bit를 제거한 환경에서는 `unsafe_*_permissions`로 fail-closed한다. staging은
   `0600`으로 생성되고, final은 열린 staging descriptor를 `fchmod(0400)`한 뒤 publish되므로 final
   pathname에는 writable window가 없다.

6. **Sidecar 선생성 해석.**
   WAL/SHM에 생성 순간 `0600`을 원자적으로 부여하려고 SQLite connect 전에 empty regular file로
   선생성한다. SQLite는 같은 inode를 사용하며 clean close 때 sidecar를 삭제할 수 있다. 기존 sidecar는
   truncate/chmod하지 않는다. SQLite가 sidecar의 단독 생성 주체여야 한다는 별도 요구가 있다면
   stdlib hook 부재와 함께 ruling이 필요하다.

7. **Lock path error code 경계.**
   lock leaf의 filesystem path 결함은 ADR symlink 절의 `state_path_*`,
   `unsafe_state_permissions`, `engine_owned_path_unverifiable`로 드러낸다. 실제 `flock` contention/handle
   failure는 기존 `lock_busy`/`lock_principal_unknown`을 유지한다. lock leaf 결함도 모두
   `lock_principal_unknown`으로 감싸라는 의도라면 ADR의 두 typed-error 표 사이 우선순위 ruling이
   필요하다.

8. **`.waystone/.gitignore`는 이번 hardening leaf에서 제외했다.**
   ADR 표와 briefing이 열거한 DB/sidecar/lock/staging/final leaf에 `.gitignore`가 없고,
   그 helper는 허용 파일 밖 `waystone/core/__init__.py` 소유라 기존 호출을 유지했다. 현재 helper는
   symlinked `.gitignore`를 이 task의 `state_path_*`로 분류하지 않는다. “engine-owned subtree”가
   self-ignore leaf까지 포함한다면 별도 허용 범위와 typed contract가 필요하다.

## 5. 스코프 밖에서 발견한 문제

- 기존 artifact corruption 테스트 두 건은 immutable `0400` 계약을 반영하지 않은 fixture이며,
  이번 task의 “기존 테스트 수정 금지” 때문에 수정하지 않았다.
- `.waystone/.gitignore`의 permission/no-follow hardening은 `waystone/core/__init__.py` 변경이 필요하나
  허용 파일 밖이므로 수정하지 않았다.
- Python stdlib SQLite actual-open no-follow 한계는 이 세 모듈의 additive 변경만으로 제거할 수 없다.
- 의도적 local symlink swap/TOCTOU, ACL, 동일 account tampering, multi-user 격리는 ADR-0013이
  명시한 비보호 범위이며 이를 방어하는 speculative machinery를 추가하지 않았다.
- aggregate가 ignored `.waystone/lock` diagnostic을 갱신했다. 계약의 알려진 예외이므로 복원하지
  않았다.
