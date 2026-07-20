# m1b-lease 구현 보고서

- Task: `feat/run-lease-fencing`
- Base: `703134b feat(m1b): transactional run store kernel + artifact store (feat/run-store-kernel)`
- Commit: `8923e30 feat(m1b): add lease fencing primitives`

## 1. 구현 요약과 파일 목록

`waystone/runs/lease.py`에 기존 store v1의 `leases`·`action_runtime` 위에서 동작하는
lease/fencing 원시 계층을 추가했다.

- CSPRNG `owner_token`, release 뒤에도 보존되는 단조 `fencing_epoch`, action
  `entity_version` exact-match claim/renew/release/reclaim
- `lease_principal_mismatch`, `lease_principal_unknown`, `lock_busy`,
  `lock_principal_unknown` 등 fail-closed typed error
- heartbeat renew·effect start·submit·completion·apply·cleanup 여섯 guard entry
- 실제 `fcntl.flock` handle 획득 뒤 DB principal을 재확인하는 advisory-lock context
- wall-clock `expires_at`은 telemetry로만 저장하고, in-process expiry hint는
  `time.monotonic()`으로만 비교
- reclaim CAS 직전에 positive quiescence와 effect-absence probe를 다시 관측

변경 파일:

- `waystone/runs/lease.py` — lease, fencing, guard, reclaim, OS advisory lock
- `scripts/tests/test_run_lease.py` — 신규 계약/fault/race 테스트 12건
- `scripts/tests/run_tests.py` — `RunLeaseTests` import와 aggregate 등록만 추가

`waystone/runs/store.py`, `waystone/runs/artifacts.py`, legacy `scripts/*` 구현은 수정하지
않았다.

## 2. 계약 매핑

| 계약 / fixture | 이를 직접 단언하는 테스트 함수 |
|---|---|
| ADR-0013 promoted row 1: 여섯 principal guard의 exact tuple mismatch/unknown, mutation 0 | `test_fixture_6_all_guard_entries_fail_typed_before_callback`; `test_principal_classification_covers_each_tuple_axis_and_incoherent_authority` |
| Guard callback의 동일 transaction DB marker commit 및 예외 rollback | `test_guarded_entry_commits_db_marker_and_rolls_back_failed_marker`; `test_commit_and_rollback_faults_remain_typed` |
| M1-B exit fixture 6: stale/unknown heartbeat·effect·submit·completion·apply·cleanup 전부 거부 | `test_fixture_6_all_guard_entries_fail_typed_before_callback` |
| ADR-0013 promoted row 2 / fixture 7: 실제 lock 대기 뒤 DB tuple post-acquire recheck, critical section 0 | `test_fixture_7_lock_waiter_rechecks_db_tuple_after_actual_handle_acquisition`; `test_lock_contention_and_unprovable_handle_are_typed` |
| ADR-0013 promoted row 3 / fixture 8: positive evidence reclaim과 구 owner race, stale path 0 | `test_fixture_8_reclaim_wins_cas_and_rejects_every_old_owner_path`; `test_fixture_8_old_guarded_start_invalidates_stale_reclaim_evidence` |
| Fixture 8의 같은 action effect·cleanup 중복 0 (transaction-bound mock expected-state CAS) | `test_fixture_8_reclaim_wins_cas_and_rejects_every_old_owner_path` |
| Reclaim은 quiescence와 effect absence 모두 exact `True`일 때만 허용 | `test_reclaim_requires_fresh_positive_quiescence_and_effect_absence` |
| ADR-0002 fencing epoch 단조성·release 후 비재사용·overflow refusal | `test_claim_renew_release_use_csprng_and_never_reuse_fencing_epoch`; `test_concurrent_reclaimable_claim_has_one_winner_and_epoch_overflow_never_wraps` |
| owner token CSPRNG 직접 사용, ambient owner/host 값 비사용 | `test_claim_renew_release_use_csprng_and_never_reuse_fencing_epoch` |
| expiry는 liveness hint일 뿐 claim/takeover/stale mutation 권한이 아님 | `test_expiry_is_only_a_hint_and_never_authorizes_claim_or_stale_write` |
| Store 보고 ④4의 version 규약(initial 0, current action/lease coherence) | `test_principal_classification_covers_each_tuple_axis_and_incoherent_authority` |

Fixture 6·7·8 테스트 docstring은 각 M1-B exit 행 번호를 직접 인용한다.

## 3. 검증 결과

- `uv run scripts/tests/test_run_lease.py` — 12 tests, rc 0
- `uv run scripts/tests/test_run_store.py` — 26 tests, rc 0
- `uv run scripts/tests/run_tests.py RunLeaseTests RunStoreTests` — 33 tests, rc 0
- 지정 aggregate command:
  `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1b-lease.log 2>&1; echo "suite rc=$?"`
  — **suite rc=0**, 882 tests, 88.805s
- 최종 로그: `/tmp/suite-m1b-lease.log`
- `git diff --check` — clean
- 독립 reviewer 최종 판정 — 할당된 lease triple/fixture 6–8 기준 신규 blocker 없음

## 4. 계약 해석 및 needs-ruling 후보

1. **ADR-0013 full principal의 `project_id`·`executor_kind` 결속 공백 (major
   needs-ruling).** ADR 전문은 최소 current DB fact에 두 축도 포함하지만, store v1의
   `actions`/`leases`에는 두 column이 없고 canonical `ProjectContext`도 이 기체 dependency에
   없다. 독립 probe에서는 claimed DB를 다른 project로 복사했을 때 원 project principal이
   통과할 수 있음을 확인했다. path, `.waystone.yml` 문자열, ambient 값으로 authority를
   발명하는 것은 ADR의 current DB fact 계약을 만족하지 않으므로 하지 않았다. 명시 task
   triple(`owner_token + fencing_epoch + entity_version`)을 이번 acceptance로 좁힐지, 후속 v2
   migration에서 explicit project/executor binding을 추가할지 ruling이 필요하다. 현 store tests가
   schema v1을 hard-pin하고 D1이 기존 test 변경을 금지하므로 이번 기체에서 v2를 넣는 선택은
   기존 계약과 충돌한다.
2. **Lease guard와 public store transition의 shared-transaction 확장 필요 (major integration
   dependency).** guard callback은 exact tuple을 확인한 이미 열린 `BEGIN IMMEDIATE` 안에서
   짧은 DB/telemetry entry mutation만 수행한다. 여기서 public `RunStore.record_transition()`을
   호출하면 nested transaction이 되고, guard 밖에서 action version을 먼저 올리면
   lease/action version이 불일치해 `lease_principal_unknown`이 된다. 후속 effect task가
   action transition과 lease `entity_version` 전진을 한 transaction으로 묶으려면 store의
   package-internal shared-transaction 또는 guarded-transition surface가 필요하다. store 수정 금지
   문언에 따라 이번에는 private schema 재구현이나 transition 복제를 넣지 않았다.
3. **Fixture 8의 semantic idempotency 소유 경계.** 이 테스트는 lease race에서 old principal
   callback 0과, transaction-bound mock expected-state CAS가 동일 effect/cleanup 2차 시도를
   거부함을 증명한다. 실제 action-kind별 idempotency key·observation·reconcile은
   `feat/run-effect-protocol` 소유다. generic lease guard 자체가 current owner의 동일 callback을
   영구 dedupe하도록 만들면 effect protocol 책임을 잘못 흡수한다. gate에서 fixture 8의
   stale-principal 절은 lease가, 실제 effect semantic duplicate 절은 effects가 공동 소유한다고
   명시할지 ruling이 필요하다.
4. **Expiry 해석.** DB `expires_at`은 표시/telemetry이며 이 모듈에는 wall timestamp를 읽어
   takeover·cleanup을 결정하는 API가 없다. 같은 process의 `LeasePrincipal.is_expired_hint()`만
   monotonic deadline을 비교한다. 재시작 뒤 heartbeat freshness는 지정대로 supervisor task에
   남겼다.
5. **Lease identity scope.** store 보고 ④2대로 action ID가 project-global primary key이므로
   stable `lease_id = action_id`로 한 current row를 강제했다. foreign duplicate row는 임의 선택하지
   않고 `lease_principal_unknown`이다. action ID를 run-scoped로 바꾸는 ruling이 나면 v2 unique/FK
   migration이 필요하다.
6. **Lock leaf permission/no-follow.** 이 task는 실제 `fcntl` handle과 post-acquire tuple check만
   소유한다. 새 file은 `os.open(..., 0600)`으로 만들지만 existing leaf mode/symlink/no-follow
   hardening은 분해 계획의 `fix/run-store-permission-hardening` 소유다. 그 task가 lock leaf도
   포함하는지 확인이 필요하다.
7. **필수 aggregate suite와 `.waystone/` 무수정 제약의 충돌.** 실행 전 선재
   `.waystone/lock`은 size 220, mtime `1784569732`, SHA-256
   `3f5bd1df86ef908752794fdd2370864f64980b7166e97ac8fd3fc70ea72b7f2a`였다. 지정 aggregate
   command의 legacy lock code가 이를 run-tests diagnostic으로 truncate/write했고, 최종은 size
   90, mtime `1784571724`, SHA-256
   `1d56afe042e267165f7fdc1036024f4486e49ac0c2305f03a11683d0c25f88da`다. 원 bytes는 실행 전에
   checksum만 기록되어 정확히 복원할 수 없었으므로 추측 재작성·삭제하지 않았다.
   `.waystone/profile.yml`과 `.waystone/.gitignore`의 bytes/mtime은 불변이다. 신규 lease tests는
   모두 tempdir fixture만 사용한다. 두 필수 지시를 동시에 만족할 실행 방식(예: aggregate를
   isolated project root에서 구동)이 필요하다.

## 5. 스코프 밖에서 발견한 문제

- Store v1 `leases`에는 `(entity_kind, entity_id)` UNIQUE/FK가 없다. 이 모듈은 deterministic
  `lease_id`와 duplicate scan으로 fail-closed하지만, DB-level invariant로 승격하려면 위
  project/executor binding과 함께 v2 migration 대상이다.
- Legacy aggregate suite가 worktree root의 `.waystone/lock` diagnostic bytes를 갱신한다. 신규
  테스트 문제가 아니라 기존 suite 실행 경로 문제이며 이번 task에서 legacy code를 수정하지 않았다.
- Real effect-kind별 dedupe/reconcile와 action transition + lease version atomic integration은
  후속 `feat/run-effect-protocol` 및 필요한 store extension의 소유다.
