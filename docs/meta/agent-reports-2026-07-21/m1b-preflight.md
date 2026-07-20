# m1b-preflight 구현 보고 — `feat/run-verification-preflight`

## ① 구현 요약과 파일 목록

기존 frozen `RunSpec` 위에 immutable `VerificationPlan`과 dispatch 전 capability preflight를
구현했다. plan은 required deterministic check, expected evidence, exact command/input digest,
toolchain source/content digest, environment preparation/network/cache contract, worker/verifier role
binding, sandbox, RED-first 조건을 canonical JSON + SHA-256 artifact로 저장하고 run의
`verification-plan:<run_id>` reference에 결속한다. profile role binding은 한 번 읽은 exact bytes를
같은 bytes에서 parse하여 profile digest와 binding 사이의 read race를 제거했다.

Preflight는 exact runner proof, closed child-environment contract, engine/worker command probe,
environment-preparation receipt, verifier capability, materialized toolchain 재해시가 모두 일치할
때만 `dispatch-ready`로 전이한다. required check는 준비 receipt와 child env까지 포함한
`prepared_input_digest`의 engine-owned action으로만 발행한다. worker check report를 authority로
수용하는 API는 없으며 명시적 typed refusal API만 있다. 성공 evidence와 모든 capability receipt는
content-addressed artifact/reference로 함께 결속하고, `load_dispatch_ready`가 이를 전부 다시 읽고
rehash/semantic validation한 뒤에만 재시작 가능한 dispatch authority를 복원한다.

Runner proof는 digest-only checkout/machine/principal identity, project/profile config content,
fixed-source 7개 runtime axis의 exact set으로 제한했다. state-equivalent `not-observed`만 재사용하고
content/status/identity 변화는 fresh probe를 요구한다. hostname, cwd, mtime/inode, 열거 순서와
worktree 절대경로는 durable authority에서 제외한다. materialized toolchain path는 runtime의 explicit
absolute input일 뿐 digest에 넣지 않고, frozen source/content/size를 실행 직전에 다시 대조한다.

변경 파일:

- `waystone/runs/preflight.py` — frozen plan domain/codec/store binding, runner proof,
  capability/toolchain/RED/child-env preflight, durable receipt reload, typed refusal.
- `scripts/tests/test_run_preflight.py` — 32개 신규 계약·회귀 테스트.
- `scripts/tests/run_tests.py` — `RunPreflightTests` import와 aggregate 등록만 추가.

기존 `store.py`, `lease.py`, `spec.py`, `jobs/*`, `adapters/*`, legacy `scripts/*` 구현은 수정하지
않았고 신규 dependency도 추가하지 않았다.

커밋:

- `2cdaf1c` — `feat(m1b): add verification preflight gate`

## ② 계약 매핑 표

| 계약 / ADR / fixture | 이를 단언하는 테스트 함수 |
|---|---|
| ADR-0012 frozen VerificationPlan: RunSpec/base/task 결속, canonical artifact/reference, expected evidence, engine executor | `test_freeze_plan_persists_canonical_artifact_reference_and_profile_bindings` |
| ADR-0012 role binding은 VerificationPlan/preflight 소유, exact profile bytes와 worker/verifier provenance 동결 | `test_freeze_plan_persists_canonical_artifact_reference_and_profile_bindings`, `test_profile_role_binding_is_parsed_from_the_exact_digested_snapshot` |
| plan 부재/불완전/재작성 상태에서는 dispatch 불가, optional plan/launcher API 부재 | `test_incomplete_or_missing_plan_cannot_satisfy_dispatch_precondition`, `test_frozen_plan_cannot_be_mutated_rebuilt_from_live_profile_or_overwritten`, `test_public_dispatch_precondition_has_no_optional_plan_or_worker_launcher` |
| command input이 command/env/base/fixture/toolchain/source/environment-preparation content에 결속 | `test_command_input_digest_binds_command_environment_base_fixture_and_toolchain` |
| PC-27 profile_v1 refusal 값 보존 + preflight code wrapping, unsupported verifier entry no-launch | `test_profile_v1_refusal_is_wrapped_without_losing_original_fields` |
| PC-27 unsupported execution category/backend binding/engine·worker·verifier sandbox를 dispatch 전에 typed refusal | `test_unsupported_execution_binding_and_sandbox_each_refuse_before_dispatch` |
| ADR-0012 verifier가 frozen base, patch bytes, result digest를 받고 artifact를 내는 capability 요구 | `test_verifier_requires_frozen_base_patch_result_and_artifact_capabilities` |
| exact probe가 실행 불가능하면 refusal, RED-first 아닌 structured nonzero result는 capability failure로 오분류하지 않음 | `test_unexecutable_probe_refuses_but_structured_nonzero_result_is_capable` |
| ADR-0012 RED-first는 frozen base/command/input/preparation/env와 expected nonzero failure에 결속하고 artifact 저장 | `test_red_first_expected_failure_is_base_bound_and_persisted`, `test_red_first_snapshot_or_exit_mismatch_refuses_before_dispatch` |
| authoritative deterministic check는 engine action, worker report는 authority가 아님 | `test_successful_preflight_is_capability_only_and_worker_result_is_not_authority` |
| ADR-0013 delegated child env: closed name/source/normalization, missing/extra/credential·lease authority typed refusal, full parent env 비상속 | `test_probes_and_actions_bind_selected_preparation_and_closed_child_environment`, `test_ambient_parent_environment_never_enters_plan_or_preflight_authority` |
| environment preparation/network/cache receipt exact-match, unrelated ambient cache로 강등 금지 | `test_network_cache_receipt_must_exactly_match_frozen_environment`, `test_probes_and_actions_bind_selected_preparation_and_closed_child_environment` |
| capability fact set의 extra probe·중복 receipt·비정상 toolchain observation은 commit 전 refusal | `test_probes_and_actions_bind_selected_preparation_and_closed_child_environment`, `test_duplicate_environment_receipts_fail_validation_without_sort_type_error` |
| capability/probe/runner/preparation receipts는 canonical artifact/reference로 저장되고 reload 시 전부 rehash | `test_successful_preflight_is_capability_only_and_worker_result_is_not_authority`, `test_dispatch_reload_refuses_dangling_receipt` |
| transition 직후 return crash에서도 durable dispatch action과 reusable runner proof 복원 | `test_post_commit_reload_recovers_dispatch_after_return_path_crash` |
| PC-28 state-equivalent `not-observed` proof 재사용 | `test_state_equivalent_not_observed_runner_proof_is_reusable` |
| PC-28 observed↔unobserved 전이 fresh probe 요구 | `test_observed_unobserved_runner_axis_transitions_require_reprobe` |
| PC-28/PC-29 directory stat 동일이어도 config content 변화 시 proof 무효화 | `test_config_content_change_with_unchanged_directory_stat_requires_reprobe` |
| E-03 잔여 checkout mismatch proof 재사용 거부 | `test_checkout_identity_mismatch_requires_fresh_probe` |
| E-03 잔여 machine mismatch proof 재사용 거부 | `test_machine_identity_mismatch_requires_fresh_probe` |
| E-03 잔여 principal mismatch proof 재사용 거부 | `test_principal_identity_mismatch_requires_fresh_probe` |
| PC-29 relocation-stable plan/proof digest, runtime/capability 열거 순서 canonicalization, hostname·mtime·inode 비권위 | `test_plan_and_runner_proof_digests_are_relocation_and_ambient_order_stable` |
| E-09 closed bounded runtime axes, raw hostname/빈 observation set 거부, unavailable typed refusal | `test_runner_proof_observer_is_engine_owned_and_unavailable_probe_is_typed` |
| worktree 절대경로가 plan 어디에 들어와도 freeze 거부 | `test_absolute_worktree_path_is_rejected_anywhere_in_plan_authority` |
| materialized toolchain relative path가 ambient cwd로 bytes를 선택하지 못함 | `test_relative_toolchain_path_cannot_select_bytes_through_ambient_cwd` |
| `fix/env-prep-toolchain-digest-binding`: WS-GPT-102 동일 version/size/mtime/inode의 위조 bytes가 offline gate 통과 불가 | `test_ws_gpt_102_forged_toolchain_bytes_refuse_before_offline_gate` |
| toolchain bytes가 같아도 frozen source가 ambient index로 치환되면 refusal | `test_toolchain_source_substitution_refuses_even_when_bytes_match` |

## ③ 검증 결과

- Focused: `uv run scripts/tests/test_run_preflight.py` → **32 tests, rc=0**.
- 인접 aggregate: `uv run scripts/tests/run_tests.py RunDomainTests RunStoreTests RunSpecTests RunPreflightTests` → **70 tests, rc=0**.
- 독립 read-only 계약 리뷰: **PASS, blocker/major 없음**.
- 독립 read-only 코드 감사: **PASS, blocker/major 없음**.
- `git diff --check` → **rc=0**.
- 필수 full suite 명령:

  ```sh
  env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1b-preflight.log 2>&1; echo "suite rc=$?"
  ```

  결과: **suite rc=0**, `Ran 949 tests in 100.439s`, `OK`.
  로그: `/tmp/suite-m1b-preflight.log`.

## ④ 계약 해석 및 needs-ruling 후보

1. **RunSpec에 VerificationPlan digest 필드가 없다.** briefing의 명시적 대안을 따라 spec을
   수정하지 않고 canonical plan을 `EVIDENCE` artifact와 `verification-plan:<run_id>` reference로
   run에 별도 결속했다. store v1에 plan/preflight 전용 artifact kind와 transition reason도 없어
   `EVIDENCE`와 `TransitionReason.PLANNED`를 사용했다. 이 kind/reason/reference id를 영구 공개
   schema로 고정할지는 main 판정이 필요하다.

2. **Plan 변경의 revision 모델이 없다.** ADR은 dispatch 뒤 변경 시 새 plan을 다시 freeze하라고
   쓰지만 현 RunSpec/store와 task briefing에는 같은 run의 VerificationPlan revision/CAS schema가
   없다. 가장 보수적으로 run당 plan 한 건을 immutable하게 두고 두 번째 freeze를 거부했다. 변경은
   새 run으로 다시 planning해야 한다. 같은 run 안 revision이 필요하면 store/schema owner의 별도
   설계가 필요하다.

3. **Runner proof bounded axis의 이름은 ADR이 byte-level로 pin하지 않았다.** legacy 의미를
   `runner-binary`, `runner-version`, `runner-config-content`, `platform-kernel`, `sandbox-contract`,
   `process-security`, `cache-boundary`의 fixed-source 7축으로 구체화했다. checkout/machine/principal과
   config content는 별도 digest 축이다. `runner-config-content=not-observed`는 확인된 config 부재에만
   쓰는 호출자 규범이며 실제 read/probe 실패는 `runner_probe_unavailable`이어야 한다. 축 이름·source
   identifier를 후속 producer가 의존하기 전에 main에서 고정해야 한다.

4. **Child environment는 지원 가능한 closed subset만 열었다.** 현재 locale/color, isolated
   temp/cache, frozen toolchain path, `UV_OFFLINE` 이름과 exact source/normalization 조합만 지원한다.
   credential은 consent/capability artifact schema가 없으므로 `child_env_not_allowed`로 거부하고,
   owner token/fencing/entity version/DB mutation/lock handle도 항상 금지한다. 실제 빈 map 구성과 spawn은
   후속 transport가 소유한다. credential binding schema와 adapter별 추가 allowlist가 필요하면 별도
   task/ruling이 필요하다.

5. **Capability receipt/probe는 engine 내부 typed fact 입력이다.** 이 slice에는 실제 worker/check
   subprocess executor가 없으므로 canonical engine-observed preparation/probe/verifier receipts를
   검증·persist하고 engine action을 발행하는 경계까지만 구현했다. worker가 같은 이름의 값을
   만들거나 executor kind를 caller가 지정할 수 없게 했지만, 실제 command 실행/관측은 briefing대로
   후속 supervisor/transport 위에 남는다.

6. **Sandbox capability는 exact-match로 판정했다.** 어느 sandbox가 다른 sandbox보다 "더 강함"인지
   비교하는 lattice/adapter 계약이 없고 다른 실행 형태나 약한 sandbox로 가장하는 것이 금지되어,
   문자열별 exact contract 외의 승격/강등을 하지 않는다. 향후 capability partial order를 허용하려면
   별도 ADR이 필요하다.

7. **RED-first를 ADR-0012의 dispatch precondition으로 구현했다.** `phase=red-first`이면 base snapshot의
   exact command에서 expected nonzero exit를 낸 engine receipt가 없으면 거부한다. 일반 verification
   check의 structured nonzero capability probe는 실행 가능성 증거로 인정한다. RED artifact의 stdout/
   stderr 상세 형식과 실제 실행기는 후속 engine action schema가 정해야 한다.

8. **실패 preflight의 영속 audit schema가 없다.** 성공 receipts/evidence는 transition과 함께 reference로
   결속하지만 capability refusal은 run을 `verification-plan-frozen`에 그대로 두고 typed exception으로
   만 반환한다. failed-preflight attempt/reason을 append-only로 저장하려면 store reason/state/attempt
   owner가 schema를 추가해야 한다.

9. **Profile adapter에는 bytes 입력 public API가 없다.** profile path를 두 번 읽으면 role binding과
   content digest가 서로 다른 snapshot에서 나올 수 있어, 기존 모듈 수정 금지 범위 안에서
   `profile_v1`의 duplicate-key loader와 adapter를 사용해 한 번 캡처한 bytes 자체를 parse했다. 후속에는
   `read_profile_v1_bytes` 같은 public adapter를 domain owner가 제공하는 편이 경계를 더 명확히 한다.

10. **Canonical representation은 ADR에서 byte-level로 고정되지 않았다.** sorted-key compact UTF-8
    JSON과 `sha256:<lowercase hex>`를 선택했다. plan/preflight/receipt schema name과 canonical encoding을
    다른 producer가 작성하기 전에 main에서 고정해야 한다.

## ⑤ 스코프 밖에서 발견한 문제

- Receipt/preflight artifact bytes는 store transition 전에 content-addressed CAS에 publish된다. 이후
  concurrent run-state/version CAS가 실패하면 DB reference가 없는 immutable bytes가 남을 수 있다.
  잘못된 dispatch authority는 생기지 않지만 garbage collection/transactional staging은 store owner
  범위다.
- `load_verification_plan`의 artifact integrity 실패는 기존 store의 typed `ArtifactError`를 그대로
  전파한다. silent success는 아니지만 preflight 전용 error code로 일관되게 wrapping할지는 artifact/
  store error taxonomy owner의 결정이다.
- `fix/env-prep-toolchain-digest-binding` finding은 구현과 WS-GPT-102 fixture로 동시에 폐쇄했지만,
  `tasks.yaml` status/notes는 owner-authored registry이므로 이 worker가 수정하지 않았다.
- 필수 aggregate 실행 전 `.waystone/lock`은 size 90, mtime `1784573948`, SHA-256
  `f529eb1e0befcfdbf4947d00324f3368efb60dcf64114caed5435945b1d8be59`였고, 실행 후 size 89,
  mtime `1784576055`, SHA-256 `42fb2ea62932d916b85bbe71f9ebfa6464a86a331f0f3f1c5e9878eddca60bcc`로
  갱신됐다. briefing이 명시한 legacy aggregate diagnostic 예외이므로 복원·삭제하지 않았다.
  `.waystone/.gitignore`와 `.waystone/profile.yml`은 측정 전후 digest가 같았다.
- 세션의 Waystone `PreCompact` hook이 구현/테스트와 무관하게 ignored `.waystone/resume.md`를
  `2026-07-21 04:06:47 KST`에 생성했다(size 3893, SHA-256
  `58076b89176f7e58138665c705b6a8afeb4b07a031d757aaf59331065cdc42c2`). aggregate 전후에는 bytes가
  변하지 않았다. briefing의 허용 예외에 포함되지 않는 신규 diagnostic이므로, birth time과 내용을
  확인한 뒤 최종 상태에서 제거해 추가 `.waystone/` state가 남지 않게 했다. `SessionEnd` hook이 이를
  다시 생성할 수 있는 harness side effect와 worktree 무수정 계약의 우선순위는 harness owner가
  정리해야 한다.
