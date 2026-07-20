# REPORT — m1b-observe / feat/run-observability

- Branch: `m1b/observe`
- Base: `943147c feat(m1b): detached runner supervisor + process identity (feat/run-supervisor-identity)`
- Implementation commit: `09fa5e3 feat(m1b): add read-only run observability`
- Push: 수행하지 않음

## ① 구현 요약과 파일 목록

`run status`/`watch`가 공유할 read-only projection 라이브러리를 추가했다. 한 번의 SQLite
backup snapshot으로 DB 사실을 고정한 뒤 `liveness`, frozen-closure 기반 `progress`, 현재
claim 기반 `current`를 서로 독립적으로 계산한다. DB의 `run_state`는 그대로 보존하고,
`health`/`health_reason`은 조회 시점에만 파생한다. `stalled`는 저장 상태가 아니며 모든 미완료
action이 진행 불가능하고 그 유일한 blocker가 `unknown-effect`인 경우에만 산출한다.

runner liveness는 supervisor runtime envelope, 현재 lease principal/fence, frozen effect intent,
process identity를 probe 전후에 재대조한다. 상태 조회는 claim/renew/reconcile/transition/cache
migration/artifact repair를 실행하지 않는다. 사람용 출력은 상태 count 중심이며 내부 식별자를
감추고, JSON projection만 verbose 내부 식별자를 포함한다. `watch_run`은 같은 snapshotter와
사람용 renderer를 반복 호출하는 iterator다.

| 파일 | 변경 |
|---|---|
| `waystone/runs/observe.py` | 신규 snapshot, projection dataclass, human/JSON renderer, watch iterator, typed `StatusUnavailable` |
| `scripts/tests/test_run_observe.py` | 신규 계약·fault-injection 테스트 23개 |
| `scripts/tests/run_tests.py` | `RunObserveTests` import와 aggregate tuple 항목만 추가 |
| `REPORT.md` | 본 보고서. 요구대로 untracked이며 구현 커밋에 포함하지 않음 |

기존 `waystone/` 모듈과 legacy `scripts/*`는 수정하지 않았다. 허용된 aggregate 등록 파일만
기존 파일 중 수정했다. 신규 의존성은 없다.

## ② 계약 매핑 표

| 할당 계약 / fixture | 이를 단언하는 테스트 함수 |
|---|---|
| §3-8 / ADR-0003 3분리: liveness는 positive supervisor evidence만 사용하고 progress/current로 메우지 않음 | `test_non_runner_effect_observation_does_not_invent_liveness`, `test_terminal_run_state_without_action_exit_evidence_has_unknown_liveness`, `test_positive_lane_with_unknown_lane_is_alive_but_derived_degraded` |
| §3-8 / ADR-0003 frozen closure 분모, action 수 비사용 | `test_progress_uses_one_frozen_task_instead_of_dynamic_action_count` |
| §3-8 / ADR-0003 derived health: 진행 가능한 lane이 있으면 non-stalled | `test_progress_capable_action_prevents_stalled_with_unknown_effect_lane`, `test_live_runner_with_unreconciled_effect_is_not_stalled` |
| §3-8 / ADR-0003 derived health: 유일 원인이 미해소 unknown-effect이면 stalled | `test_only_unresolved_unknown_effect_is_derived_stalled_not_a_run_state` |
| E-08 positive liveness/exit와 identity 결속, 이유 있는 unknown | `test_foreign_runtime_identity_cannot_supply_positive_liveness`, `test_runtime_identity_change_during_probe_cannot_supply_liveness`, `test_supervisor_observation_failure_is_reasoned_unknown`, `test_terminal_run_state_without_action_exit_evidence_has_unknown_liveness`, `test_completed_action_with_missing_plan_cannot_supply_positive_exit` |
| PC-19 corrupt record의 해당 run 격리와 healthy run projection 무중단 | `test_corrupt_run_is_unknown_without_interrupting_healthy_run_projection` |
| PC-19 관련 필수 입력/lease 손상을 healthy/current/positive exit로 오판하지 않음 | `test_malformed_active_lease_is_corrupt_not_current`, `test_active_action_with_missing_lease_is_corrupt_not_healthy`, `test_missing_effect_plan_reference_is_corrupt_not_healthy`, `test_completed_action_with_missing_plan_cannot_supply_positive_exit`, `test_released_active_lease_is_unowned_reasoned_unknown` |
| Fixture 1: status/watch 수십 회 전후 entity version·lease·heartbeat·transition과 DB/WAL/evidence bytes 불변 | `test_status_and_watch_repeated_polls_leave_store_and_evidence_byte_identical` |
| Fixture 1 보강: action/lease transition 중에도 단일 coherent DB read point | `test_projection_uses_one_coherent_database_read_point` |
| Fixture 2: stale heartbeat + process 관측 불가 => reasoned `health: unknown`, authoritative `run_state` 유지 | `test_stale_heartbeat_and_unobservable_process_keep_health_unknown_and_state_authoritative` |
| Fixture 3: 진행 가능한 action + unknown lane은 non-stalled / unknown-effect만 남으면 stalled | `test_progress_capable_action_prevents_stalled_with_unknown_effect_lane`, `test_only_unresolved_unknown_effect_is_derived_stalled_not_a_run_state` |
| Fixture 4: DB 잠금/조회 준비 실패 => typed `status-unavailable`, 예외를 성공으로 삼키지 않음 | `test_database_read_failure_raises_typed_status_unavailable`, `test_projection_setup_failure_raises_typed_status_unavailable` |
| Fixture 5: proven claim이면 kind+시각, claim 부재 또는 시각 미확정이면 `unknown-current` | `test_current_claim_reports_kind_and_proven_time_else_unknown_current` |
| Fixture 6: 사람용 출력에서 내부 ID 비노출, JSON projection에는 포함 | `test_human_render_hides_internal_identifiers_while_json_includes_them` |
| status/watch 동일 projection·renderer 사용 | `test_status_and_watch_repeated_polls_leave_store_and_evidence_byte_identical` |

## ③ 테스트 및 전체 suite 결과

- 집중 aggregate: `uv run scripts/tests/run_tests.py RunObserveTests`
  - rc `0`, 23 tests, `4.475s`, `OK`
- 구문 검사: `uv run -m py_compile waystone/runs/observe.py scripts/tests/test_run_observe.py`
  - rc `0`
- diff 검사: `git diff --check` 및 commit 전 `git diff --cached --check`
  - rc `0`
- 필수 전체 suite 명령:

  ```text
  env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1b-observe.log 2>&1; echo "suite rc=$?"
  ```

  - `suite rc=0`
  - `Ran 1011 tests in 104.362s`
  - `OK`
  - 로그: `/tmp/suite-m1b-observe.log`

## ④ 계약 해석 / needs-ruling 후보

1. **원래 claim 시각을 보존하는 필드가 없다.** 계약은 current에 claimed action의 kind와
   `claimed_at`을 요구하지만, 현재 schema의 `leases.observed_at`은 heartbeat renew 때마다
   덮어써지고 transition에는 시각이 없다. 구현은 heartbeat가 아직 없거나 과거 principal의
   값이라 현재 claim/reclaim 시각임을 증명할 수 있을 때만 `observed_at`을 `claimed_at`으로
   사용한다. renew 후에는 heartbeat 시각을 claim 시각으로 거짓 표시하지 않고
   `unknown-current(claimed-at-unavailable)`을 반환한다. 모든 claimed action에서 영구적으로
   kind+시각을 요구한다면 store schema에 immutable `claimed_at` 또는 timestamped claim
   transition이 필요하다.
2. **CLI 전체 경로의 read-only open 경계가 아직 없다.** 이 모듈은 이미 열린 동일
   `RunStore`/`EffectEngine`/`Supervisor`를 받아 projection하며 `RunStore.open`을 호출하지 않는다.
   현 public `RunStore.open`은 schema migration, WAL negotiation, `.waystone/.gitignore` 생성
   가능성이 있어 CLI bridge가 이를 그대로 status에 사용하면 “완전한 read-only”를 end-to-end로
   보장할 수 없다. cli-bridge 소유 단계에서 read-only opener 또는 이미 초기화된 store lifecycle
   계약을 확정해야 한다.
3. **non-runner action의 liveness 증거 범위가 문서 층위별로 다소 열려 있다.** ADR-0003은
   action별 관측 계약의 positive signal을 일반 원칙으로 쓰지만, 본 task briefing과 §3-8 표는
   supervisor process identity + heartbeat를 구체적 liveness 증거로 지정한다. 보수적으로
   non-runner `inspect_effect` 결과는 progress 판단에만 사용하고 liveness는
   `unknown(positive-liveness-unavailable)`로 유지했다. effect-kind별 positive liveness를 추가할지는
   별도 계약표가 필요하다.
4. **terminal FSM state 자체를 exit evidence로 쓰지 않았다.** `run_state=completed/canceled/failed`
   만으로 liveness를 `exited`로 만들지 않고, action에 결속된 positive completion/exit evidence가
   있을 때만 `exited`를 집계한다. 이는 E-08의 양방향 규칙을 가장 보수적으로 적용한 선택이다.
5. **정상 health label과 terminal job 집합은 exact enum으로 고정되어 있지 않다.** 정상 파생값은
   `healthy/no-derived-health-finding`, frozen one-task 분자는 현재 domain에서 terminal로 쓰이는
   `accepted|canceled|completed|failed`를 사용했다. 향후 domain enum이 공식화되면 이 집합을
   그 권위 원천에 결속해야 한다.
6. **필요한 read API가 public surface로 모두 제공되지는 않는다.** coherent DB snapshot, child
   entity 열거, frozen RunSpec/effect plan/intent 판독, probe한 identity 반환 API가 없어 같은
   package의 private helper와 connection을 조합했다. 기존 모듈 수정 금지 조건에서의 보수적
   선택이며, 후속 통합에서 public read-session/API로 승격할지 결정이 필요하다.

## ⑤ 스코프 밖에서 발견한 문제

1. 기존 `Supervisor.probe_action`은 runtime `ProcessIdentity`가 요청 action, 현재 lease
   principal/fence, frozen invocation/intent에 결속됐는지 자체 검증하지 않으며 관측한 identity를
   반환하지도 않는다. 본 observer는 probe 전후 runtime binding을 재검증해 TOCTOU와 foreign
   runtime 오판을 막았지만, `probe_action`을 직접 쓰는 다른 소비자는 같은 방어를 얻지 못한다.
   기존 모듈 수정 금지에 따라 supervisor는 수정하지 않았다.
2. 필수 aggregate suite 및 host harness가 worktree root의 ignored `.waystone/lock`,
   `.waystone/.gitignore`, `.waystone/resume.md`를 생성/갱신했다. 계약에 명시된 diagnostic/hook
   예외로 보고 복원·삭제하지 않았다. `.waystone/profile.yml`은 base부터 존재한 ignored 파일이며
   이번 구현에서 만들거나 수정하지 않았다.
3. 그 밖의 tracked 파일 변경이나 스코프 밖 수정은 발견하지 못했다.
