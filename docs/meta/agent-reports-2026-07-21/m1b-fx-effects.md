# REPORT — m1b-fx-effects / WS-GPT-602 + WS-GPT-604

- base: `c390c1c docs(round): close and publish 2026-07-21-m1b-vertical-slice`
- 구현 커밋: `d845641 fix(m1b): bind patch approvals and runner absence`
- push: 하지 않음

## 1. 구현 요약과 파일 목록

- `waystone/runs/effects.py`
  - `PatchApprovalDigests`를 추가해 patch plan에 RunSpec, VerificationPlan, verifier evidence,
    integration decision의 content digest를 optional additive field로 결속했다.
  - 기존 `waystone-effect-plan-1` tag를 유지하고 `approval_digests` 부재를
    `PatchIntegrationEffect.approval_digests is None`인 legacy plan으로 판독한다.
  - approval-bound patch action을 reconcile해 아직 실행되지 않은 effect를 수행하기 전에 네 artifact를
    content-addressed store에서 재로드·재해시한다. 부재·변조·permission 불일치는
    `ApprovalAuthorityMismatch(code=approval_authority_mismatch)`로 거부한다.
  - runner WAI + completion marker 부재 분기에 plan-shaped `runner_absence_probe` 소비 seam을 추가했다.
    exact `True`일 때만 기존 WAI를 아직 소비되지 않은 최초 실행으로 사용하며, probe 부재·False·예외는
    `unknown-effect`를 유지한다.
- `waystone/runs/verify.py`
  - execution-time `_reload_apply_authority` 결과에서 위 네 digest를 가져와
    `PatchIntegrationEffect` plan에 동봉한다.
- `scripts/tests/test_run_effects.py`
  - WS-GPT-604 crash fixture 1건 추가. 기존 테스트·assertion은 수정하지 않았다.
- `scripts/tests/test_run_verify.py`
  - WS-GPT-602 crash/tamper/missing/clean reconcile fixture 1건 추가. 기존 테스트·assertion은
    수정하지 않았다.
- `scripts/tests/run_tests.py`
  - 두 테스트 모듈이 이미 aggregate에 등록되어 있어 수정하지 않았다.

## 2. 계약 매핑

| 할당 계약 / ADR / fixture 행 | 이를 단언하는 테스트 함수 |
|---|---|
| WS-GPT-602 / PC-22 — apply plan이 RunSpec·VerificationPlan·verifier evidence·integration decision content digest를 durable하게 동봉 | `test_pc22_patch_reconcile_rehashes_durable_approval_bundle` |
| WS-GPT-602 / PC-22 — plan 저장 뒤 crash, verifier/decision bytes 변조 또는 artifact 부재 시 `approval_authority_mismatch`, driver 0, ref 불이동 | `test_pc22_patch_reconcile_rehashes_durable_approval_bundle` |
| WS-GPT-602 — 변조 없는 crash reconcile은 patch driver 1회 후 completed, target ref는 승인 result로 이동 | `test_pc22_patch_reconcile_rehashes_durable_approval_bundle` |
| additive v1 schema — 신규 plan의 optional approval field와 기존 patch plan 판독/reconcile 호환 | `test_pc22_patch_reconcile_rehashes_durable_approval_bundle`, `test_all_effect_kinds_crash_before_effect_reconcile_one_first_execution`, `test_patch_adoption_rederives_expected_parent_tree_precondition` |
| WS-GPT-604 / ADR-0002 runner crash table — WAI 뒤 effect 전 사망 + positive exact-identity absence에서 같은 action의 최초 실행으로 수렴 | `test_runner_positive_absence_probe_converges_wai_to_one_first_execution` |
| WS-GPT-604 / E-08 — probe 부재는 침묵을 absence로 붕괴시키지 않고 기존 `unknown-effect`, process 실행 0 | `test_runner_positive_absence_probe_converges_wai_to_one_first_execution` |
| WS-GPT-604 / runner at-most-once — positive absence 소비 뒤 runner/driver 각 1회, 다음 reconcile은 no-op | `test_runner_positive_absence_probe_converges_wai_to_one_first_execution` |

## 3. 검증 결과

- red 재현: 구현 전 `test_run_effects.py`는 `runner_absence_probe` 부재로 rc=1,
  `test_run_verify.py`는 durable `approval_digests` 부재로 rc=1
  (`/tmp/red-m1b-fx-effects.log`).
- focused:
  - `scripts/tests/test_run_effects.py`: 24 tests, OK
  - `scripts/tests/test_run_verify.py`: 26 tests, OK
  - `scripts/tests/test_run_supervisor.py`: 11 tests, OK
  - 로그: `/tmp/focused-m1b-fx-effects.log`
- 필수 aggregate 명령:

  `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1b-fx-effects.log 2>&1; echo "suite rc=$?"`

- 결과: `suite rc=0`; `Ran 1090 tests in 147.632s`; `OK`
- 로그: `/tmp/suite-m1b-fx-effects.log`
- `git diff --check`: green
- aggregate가 ignored `.waystone/lock`을 `2026-07-21 09:36:48 +0900`에 갱신했다.
  ignored `.waystone/.gitignore`와 pre-existing `.waystone/profile.yml`도 존재한다. 복원·삭제하지 않았다.

## 4. 계약 해석 및 needs-ruling 후보

1. 브리핑이 먼저 전문을 읽으라고 지정한
   `docs/reviews/2026-07-21-m1b-vertical-slice-feedback.md`는 pinned base와 모든 local branch/history에
   존재하지 않았다. 동일 request의 Known weak spots, task 행, 브리핑에 인용된 WS-GPT-602/604 문언,
   m1b-verify ④1, m1b-supervisor ④1, m1b-effects ④5를 보수적 권위로 사용했다.
2. generic patch reconcile은 브리핑대로 네 content digest의 bytes availability/integrity만 대조한다.
   `_reload_apply_authority`의 전체 의미 재검증과 reference lineage 재파생은 반복하지 않는다.
   crash reconcile에서도 full semantic reload가 필요하다는 별도 계약이 생기면 effects/verify 사이에
   authority callback 또는 public verifier boundary가 추가로 필요하다.
3. plan schema는 additive 확장 규칙으로 v1 tag를 유지했다. `approval_digests`가 없는 기존 plan은
   typed `None` legacy variant로 계속 판독하고 기존 crash 결정표를 보존한다. legacy plan까지 새 approval
   재검증을 소급 강제하면 역사 plan에 digest가 없어 실행 불가능하므로 별도 migration/ruling이 필요하다.
4. positive absence 뒤 runner는 durable WAI에 기록된 current principal/fencing epoch를 그대로 검증해
   최초 launch한다. 현 supervisor가 WAI의 원 epoch를 exact-match하므로 새 epoch reclaim 뒤 같은 immutable
   WAI를 launch하는 경로는 성립하지 않는다. 새 epoch를 필수로 요구한다면 WAI rebind/versioning과
   supervisor 변경이 필요하다. 현재 구현은 positive absence가 실제 process 실행 0을 증명한 경우에만
   이 경로를 열어 같은 action의 두 번째 process 실행을 허용하지 않는다.

## 5. 스코프 밖에서 발견한 문제

- 현 `Supervisor.positive_absence_probe`는 runtime identity가 전혀 게시되지 않은 아주 이른 startup crash를
  positive absent로 만들지 않고 `unknown`으로 둔다. 또한 기존 launch reservation이 남은 incarnation은
  `Supervisor.launch`가 재기동을 거부한다. 이번 수정은 consumer seam만 허용된 범위라 producer-side
  startup acknowledgement/reservation settlement는 수정하지 않았다(m1b-supervisor ④2·④3 계열).
- 지정된 feedback 원문 파일 부재는 위 ④1과 같다. remote fetch는 shared Git metadata를 수정하므로
  전용 worktree 밖 write 금지에 따라 시도하지 않았다.
- suite가 만든 ignored `__pycache__/` 경로는 추적하거나 정리하지 않았다.
