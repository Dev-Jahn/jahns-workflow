# m1b-fx-engine 작업 보고

## ① 구현 요약과 파일 목록

- `waystone/runs/verify.py`
  - published terminal verifier evidence를 immutable artifact bytes부터 다시 읽고 재해시하며 frozen authority와 exact attempt/action lineage를 재검증하는 `reload_verifier_evidence()` public API를 추가했다.
  - verifier evidence를 다시 검증한 뒤 published integration decision과 producer intent까지 재검증하는 `reload_integration_decision()` public API를 추가했다.
- `waystone/runs/engine.py`
  - `_complete()`가 terminal verifier evidence와 integration decision의 존재를 단계별로 확인하고, 존재하면 신규 실행/기록 대신 public reload API로 소비를 재개한다.
  - published apply action은 immutable effect plan과 현재 spec/evidence/decision approval digest 묶음을 exact-match한 뒤 reconcile한다. 이미 completed면 저장된 terminal observed digest로 job/run 전이만 정합화한다.
  - `resume()`은 terminal verifier evidence가 발행된 run을 generic transport보다 completion reconcile로 먼저 라우팅한다.
- `scripts/tests/test_run_verify.py`
  - public reload의 정상 복원, exact lineage 거부, evidence/decision artifact bytes 변조 거부 계약을 추가했다.
- `scripts/tests/test_run_cli.py`
  - decision callback 예외, reviewer 원 재현(record decision 예외), decision 발행 후 crash, apply 완료 후 crash, claimed apply 중단, terminal store 일시 오류의 재진입 fixture를 추가했다.

커밋: `fe7db95 fix(m1b): resume terminal completion stages`

## ② 계약 매핑

| 계약 / 판정 / fixture | 이를 단언하는 테스트 함수 |
|---|---|
| ADR-0002 crash recovery: 발행된 terminal effect를 재실행하지 않고 관측·소비 재개 | `test_complete_reentry_after_apply_only_reconciles_terminal_transitions`, `test_complete_reentry_reconciles_published_nonterminal_apply` |
| PC-18 append-only evidence/decision을 덮어쓰지 않고 reload | `test_pc18_pc20_pc21_public_reload_revalidates_terminal_authority` |
| PC-20 verifier terminal evidence의 full rehash·authority 재검증 및 신규 verifier 실행 방지 | `test_pc18_pc20_pc21_public_reload_revalidates_terminal_authority`, `test_pc20_public_evidence_reload_refuses_tampered_terminal_bytes`, `test_complete_reentry_after_decision_callback_exception_resumes_at_decision` |
| PC-21 decision의 exact criterion/result/verifier lineage 재검증 | `test_pc18_pc20_pc21_public_reload_revalidates_terminal_authority`, `test_pc21_public_decision_reload_refuses_tampered_terminal_bytes`, `test_complete_reentry_after_decision_publication_resumes_at_apply` |
| PC-22 apply 시점 approval bundle 재검증과 completed apply의 non-reapply | `test_complete_reentry_after_apply_only_reconciles_terminal_transitions`, `test_complete_reentry_reconciles_published_nonterminal_apply`, `test_complete_reentry_after_terminal_store_error_does_not_reapply` |
| WS-GPT-601 reviewer 재현: `record_integration_decision` 예외 후 새 engine resume, `EffectRetryRefused` 없이 completed/accepted | `test_ws_gpt_601_record_decision_exception_does_not_brick_resume` |
| evidence 발행 후 실패 → decision부터 재개 | `test_complete_reentry_after_decision_callback_exception_resumes_at_decision`, `test_ws_gpt_601_record_decision_exception_does_not_brick_resume` |
| decision 발행 후 실패 → apply부터 재개 | `test_complete_reentry_after_decision_publication_resumes_at_apply` |
| apply 완료 후 실패/store 일시 오류 → terminal 전이만 정합화 | `test_complete_reentry_after_apply_only_reconciles_terminal_transitions`, `test_complete_reentry_after_terminal_store_error_does_not_reapply` |
| retry lineage: published terminal result 소비 경로가 신규 verifier retry 관문을 통과하지 않음 | `test_ws_gpt_601_record_decision_exception_does_not_brick_resume`, `test_complete_reentry_after_decision_callback_exception_resumes_at_decision` |

## ③ 검증 결과

- focused `uv run scripts/tests/test_run_verify.py`: rc 0, 29 tests
  - 로그: `/tmp/focused-m1b-fx-engine-verify.log`
- focused `uv run scripts/tests/test_run_cli.py`: rc 0, 14 tests
  - 로그: `/tmp/focused-m1b-fx-engine-cli.log`
- 필수 aggregate:
  - 명령: `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1b-fx-engine.log 2>&1`
  - rc: 0
  - 결과: 1099 tests, 156.138s, OK
  - 로그: `/tmp/suite-m1b-fx-engine.log`
- `git diff --check`: 통과
- `scripts/tests/run_tests.py`에는 두 신규 테스트 모듈이 이미 등록되어 있어 변경하지 않았다.

## ④ 계약 해석 / needs-ruling 후보

1. 지정된 `docs/reviews/2026-07-21-m1b-vertical-slice-feedback.md`는 pinned worktree와 모든 commit ref에 없었다. COMMON이 worktree 밖 접근을 read-only로 허용하므로 원본 repo의 untracked feedback을 읽기 전용으로 확인했고, WS-GPT-601 원문을 구현 근거로 사용했다. pinned input의 필독 문서 누락은 향후 fleet 생성 전에 publication/commit되어야 한다.
2. “같은 lineage”는 이 one-task engine이 결정적으로 발급하는 `attempt_id`, verifier action ID, decision action ID의 exact tuple로 구현했다. reference prefix만 맞거나 다른 attempt에서 발행된 terminal artifact는 typed refusal한다.
3. nonterminal apply reconcile의 quiescence는 patch apply가 detached executor가 아닌 동기 engine call이고, 재진입 호출은 이전 `_complete()` 호출이 종료된 뒤에만 시작한다는 현재 실행 모델에 한정했다. probe도 `PATCH_INTEGRATION` 이외 kind에는 false다. 향후 concurrent engine resume을 공식 지원한다면 durable engine invocation identity 또는 별도 serialization 계약이 필요하다.
4. terminal apply 완료 뒤 project ref의 사후 외부 변경을 다시 관측하는 의미는 추가하지 않았다. 현재 계약대로 completed action의 immutable plan/approval bundle과 저장된 observed digest를 재검증해 terminal transition만 정합화했다.

## ⑤ 스코프 밖 발견 사항

1. `_complete()` 전체를 직렬화하는 outer lock은 없으므로 동일 run에 대한 동시 `resume()` 두 건은 publication 존재 확인과 producer 호출 사이에서 경쟁할 수 있다. verifier/decision의 기존 terminal guard와 append-only 제약이 중복 publication을 거부하지만, 한 호출은 typed conflict를 받을 수 있다. 이번 task의 crash 후 순차 resume 범위 밖이라 수정하지 않았다.
2. 필수 suite가 worktree root에 ignored `.waystone/.gitignore`와 `.waystone/lock`을 생성/갱신했다. 지시대로 복원·삭제하지 않았다. ignored `.waystone/profile.yml`도 존재하지만 mtime이 2026-07-14로 이번 실행보다 앞서므로 기존 harness 상태다.
3. suite 실행으로 여러 `__pycache__/`가 ignored 상태로 존재한다. tracked 파일에는 영향이 없다.
