# m1b-store 구현 보고서

## 1. 구현 요약과 파일 목록

커밋: `7b89e89` (`feat: add transactional run store kernel`)

- `waystone/runs/store.py`
  - 초기화 marker와 project-local filesystem을 먼저 검증한 뒤 `.waystone/state.db`만 연다.
  - WAL 실제 mode 확인, schema v1과 transactional migration registry, `BEGIN IMMEDIATE` 기반 CAS를 구현했다.
  - `runs`/`jobs`/`attempts`/`actions` current rows, append-only `transitions`, telemetry 자리,
    artifact-reference index, cache를 생성한다.
  - current/audit/reference 쓰기를 하나의 transaction으로 묶고, code authorizer와 persistent trigger로
    immutable identity 및 audit/reference 재작성을 차단한다.
  - RFC 9562 UUIDv7을 48-bit Unix-ms + 74 CSPRNG bits로 생성하고 UNIQUE collision을 bounded retry한다.
  - record digest와 audit chain을 검증하며 logical corruption을 해당 run의 typed `unknown`으로 격리한다.
- `waystone/runs/artifacts.py`
  - `.waystone/artifacts/sha256-<hex>` content-addressed 저장, same-directory tempfile, file/directory
    `fsync`, atomic rename, publish 뒤 재해시를 구현했다.
  - raw absence, durable-reference dangling, unreadable/disappearing/tampered bytes를 서로 다른 typed
    결과로 보존한다.
- `scripts/tests/test_run_store.py`
  - store/artifact 계약 테스트 26건과 tempdir project fixture를 추가했다.
- `scripts/tests/run_tests.py`
  - 기존 항목은 바꾸지 않고 `ArtifactStoreTests`, `RunStoreTests`만 aggregate에 추가 등록했다.

## 2. 계약 매핑

| 계약 / fixture | 이를 단언하는 테스트 함수 |
|---|---|
| 계획 §3-1 schema v1 / mark-root 가능한 artifact index | `test_schema_v1_has_required_authority_audit_telemetry_reference_and_cache_tables` |
| 계획 §2-2 schema migration 기계, rollback, idempotence, newer-version refusal | `test_schema_bootstrap_is_transactional_idempotent_and_refuses_newer_version`, `test_concurrent_first_open_bootstraps_one_idempotent_wal_schema` |
| JW-GPT-014: transition → current-state → artifact reference 단일 transaction | `test_jw_gpt_014_transition_current_state_and_artifact_reference_are_one_transaction` |
| CAS conflict와 partial write 0 | `test_stale_concurrent_cas_is_typed_conflict_and_loser_has_zero_partial_writes`, `test_same_store_concurrent_cas_is_serialized_to_one_typed_conflict` |
| transitions code + trigger append-only | `test_transitions_reject_update_and_delete_in_code_and_persistent_triggers` |
| PC-18 attempt/evidence/decision append-only | `test_pc18_attempt_evidence_and_decision_identities_are_append_only`, `test_corrupt_existing_artifact_is_not_silently_repaired` |
| PC-19 corrupt/unknown run-local 격리와 healthy 조회 무중단 | `test_pc19_corrupt_run_is_typed_unknown_without_blocking_healthy_run`, `test_pc19_missing_or_reparented_children_and_historical_damage_are_run_local`, `test_damaged_artifact_link_is_corrupt_not_missing_reference` |
| ADR-0005 RFC 9562 UUIDv7와 uniqueness 책임 | `test_run_id_is_canonical_lowercase_rfc9562_uuid7`, `test_run_id_unique_collision_retries_without_touching_existing_run` |
| ADR-0007 filesystem 선판정, no fallback, WAL 실제 결과 확인 | `test_unsupported_filesystem_refuses_before_database_open`, `test_filesystem_probe_does_not_use_unrelated_same_device_mount`, `test_darwin_firmlink_uses_writable_data_volume_not_sealed_root`, `test_wal_io_error_and_virtual_or_read_only_filesystem_are_typed_refusals`, `test_wal_mismatch_is_typed_refusal_without_path_or_journal_fallback`, `test_run_store_constructor_cannot_bypass_root_filesystem_or_wal_gate` |
| 초기화되지 않은 root refusal + no-write (PC-31 기질) | `test_uninitialized_root_is_typed_refusal_with_no_waystone_write` |
| E-06 artifact atomic publish, 재해시, corruption/dangling 구분 | `test_artifact_write_uses_same_directory_temp_atomic_rename_and_post_write_rehash`, `test_artifact_read_reports_corruption_and_unreadable_bytes_as_integrity_errors`, `test_missing_raw_digest_and_dangling_reference_are_typed_differently`, `test_concurrent_first_artifact_write_is_idempotent_and_self_ignored` |
| E-09 runtime identity에서 ambient authority 배제 | `test_e09_runtime_identity_ignores_ambient_host_cwd_and_filesystem_metadata` |

## 3. 검증 결과

- 요청된 전체 명령:
  `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1b-store.log 2>&1; echo "suite rc=$?"`
- 결과: `suite rc=0`
- 전체: `Ran 864 tests in 85.837s`, `OK`
- 로그: `/tmp/suite-m1b-store.log`
- 신규 focused suite: 26/26 green
- `git diff --check`: green
- 실제 macOS APFS firmlink 경로에서 fresh DB open/WAL/schema/run 생성 smoke: green
- 최종 확인 시 worktree 루트의 `.waystone/`은 존재하지 않는다.

## 4. 계약 해석 및 needs-ruling 후보

알려진 명시 계약 불일치는 없다. 아래는 문언이 하나의 의미를 고정하지 않아 가장 보수적으로
구현했거나 후속 ruling이 필요한 지점이다.

1. `transitions.evidence_digest`와 `EVIDENCE` artifact reference의 cardinality/equality가 고정돼
   있지 않다. 현재는 각 digest의 canonical form과 reference immutability만 검증하며 둘을 임의로
   같다고 강제하지 않는다. `exactly one`, `at least one match`, 독립 observation receipt 중 무엇인지
   ruling이 필요하다. artifact bytes 존재도 link transaction에서 강제하지 않고 read 시 재검증한다.
2. child ID scope가 명시되지 않아 `job_id`/`attempt_id`/`action_id`/`reference_id`를 project-global
   primary key로 두고 composite parent FK로 run binding을 검증했다. run-scoped identity가 의도라면
   v2 migration과 API 변경이 필요하다.
3. v1 `TransitionReason`의 완전한 vocabulary가 고정되지 않았다. accepted runtime 문서에서 직접
   필요한 `created`, `planned`, `claimed`, `process-started`, `effect-observed`, `completed`,
   `cancel-requested`만 닫힌 enum으로 두었다. 추가 reason은 schema migration으로 확장해야 한다.
4. initial entity version을 0, 성공 transition의 `entity_version`을 `expected_version + 1`로
   해석했다. attempt append-only는 identity/parent row의 UPDATE/DELETE 금지이며 state/version은
   CAS와 transitions audit를 통해서만 변한다는 계획 §3-1/E-05 해석을 적용했다.
5. artifact schema는 별도 evidence/decision table 대신 immutable reference row 하나에
   `reference_kind`를 둔다. 최소 v1과 future mark-root 질의를 만족하지만 kind별 별도 authority가
   필요하면 migration ruling이 필요하다.
6. filesystem 증명은 containing mount의 known-local allowlist, actual writability, explicit read-only,
   알려진 macOS sync-overlay 경로, 실제 WAL negotiation을 조합한다. 모든 OS/cloud-sync provider를
   포괄하는 authoritative taxonomy는 문서에 없으므로 unknown/ambiguous는 fail-closed한다.
7. artifact publication은 계약의 tempfile + same-filesystem atomic rename을 `os.replace`로 구현했다.
   협력 writer는 같은 digest의 같은 bytes만 publish하므로 idempotent하지만, 마지막 확인 직후
   비협력 writer가 corrupt target을 만드는 TOCTOU까지 portable stdlib로 atomic no-clobber하려면
   hard-link 또는 platform-specific primitive를 허용할지 ruling이 필요하다.
8. current row binding과 append-only creation transition이 서로 다를 때, 한쪽 digest가 깨진
   single-source damage는 origin run으로 격리한다. 보호 trigger를 제거하고 current binding과
   unkeyed record digest를 함께 일관되게 재작성한 경우에는 어느 immutable source가 원본인지
   v0-only record만으로 판별할 수 없다. 이를 logical corruption 위협모델에 포함하려면 keyed 또는
   제3의 immutable ownership authority가 필요하다. 임의 precedence는 반대쪽 단일 손상 fixture를
   오염시키므로 적용하지 않았다.
9. WAL/migration refusal 뒤 새 `.waystone/`이나 빈 `state.db`를 자동 삭제하지 않는다. 기존 상태와
   경합 생성물을 안전하게 구분할 계약이 없으므로 destructive cleanup보다 typed refusal과 원본
   보존을 택했다.
10. `ArtifactStore.read_reference`는 `RunStore.get_artifact_reference`가 반환한 durable reference를
    받는 경계로 구현했다. 타입만으로 DB provenance까지 증명하는 combined facade가 필요한지는
    후속 API ruling 대상이다.
11. ADR-0013의 directory/DB/sidecar/staging/final-artifact permission 및 no-follow 조항은 이 기체의
    지정 필독/귀속(ADR-0005/0007, lease task의 ADR-0013 3계약)에 포함되지 않았다. 현재는 symlinked
    marker/state/database/artifact 경로를 거부하지만 0700/0600/0400 mode 고정과 WAL/SHM owner-mode
    검증은 구현하지 않았다. 해당 store 조항의 task ownership을 확정해야 한다.

## 5. 스코프 밖에서 발견한 문제

- 요청된 기존 aggregate suite가 실행 중 worktree 루트에 `.waystone/.gitignore`와 `.waystone/lock`을
  생성한다. 신규 store/artifact 테스트는 모두 tempdir에 격리돼 있으며, suite가 만든 두 파일과
  디렉터리는 검증 직후 제거했다. D1 때문에 legacy test/runner 동작은 수정하지 않았다.
- ADR-0007의 backup/GC 실행기와 `doctor`의 orphan/dangling 집계는 명시적으로 이 task 스코프 밖이다.
  v1 `artifacts` index에는 후속 mark-root 질의에 필요한 run/entity/transition/digest 참조를 남겼다.
- explicit machine-local state relocation 설정과 effect/verification 계층의 evidence 의미 결속은 후속
  task 소유이며, 이 커널은 어떤 ambient path나 journal mode로도 자동 fallback하지 않는다.
