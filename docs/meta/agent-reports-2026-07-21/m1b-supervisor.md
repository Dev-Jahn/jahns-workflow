# REPORT — m1b-supervisor / feat/run-supervisor-identity

## 1. 구현 요약과 파일 목록

- 기준 커밋: `2f1dde2 feat(m1b): external effect commit protocol 엔진 (feat/run-effect-protocol)`
- 구현 커밋: `287f388 feat(m1b): add detached runner supervisor`
- `subprocess.Popen(..., start_new_session=True)`로 engine-owned supervisor를 detached 실행하고,
  supervisor가 worker spawn·heartbeat·wait status·stdout/stderr artifact·completion marker를 소유한다.
- effects의 `RunnerExecutor`/`RunnerIdentityVerifier` 경계에 직접 꽂는 adapter를 제공한다. 실행 argv/cwd는
  effects가 전달한 frozen `invocation_digest`에 exact-key로 결속된 `RunnerInvocation`에서만 찾고, 미등록
  digest는 typed refusal한다.
- spawn 직전 principal은 현재 version으로 재합성하지 않고 durable runner WAI가 결속된 `effect`
  transition의 `entity_version`을 재도출한다. 그 owner/fence/version tuple을 `guard_effect_start` 안에서
  detached `Popen`과 함께 재검증해 callback 내부 race를 닫는다.
- process identity는 boot identity, PID, process start token/time, action, owner, fencing epoch,
  resolved executable/invocation digest를 모두 가진다. Linux는 boot UUID + `/proc/<pid>/stat` start ticks,
  macOS는 `kern.boottime` sec/usec + `libproc.proc_pidinfo` start sec/usec를 사용한다. PID-only fallback은 없다.
- liveness는 `alive | exited | unknown(reason)` tri-state이고, stale heartbeat·silence는 exit로 바꾸지 않는다.
  boot/PID-start mismatch는 public liveness에서 `unknown(identity-mismatch)`이며 destructive resolution을
  허용하지 않는다. exact old-identity absence는 별도 evidence bit/probe로 보존한다.
- heartbeat는 `LeaseManager.renew()`로 기존 `leases/action_runtime` mutable telemetry를 갱신하고,
  freshness authority에 필요한 boot identity + monotonic 값은 atomic supervisor sidecar에 함께 기록한다.
  tick은 transition을 추가하지 않는다.
- stdout/stderr bytes는 `ArtifactStore`에 저장하고 marker에는 digest만 둔다. marker 전에 supervisor가 실제
  wait 결과에 결속된 immutable wait receipt를 게시하므로, live worker가 runtime identity/fence를 그대로
  복사해 marker를 직접 써도 verifier가 거부한다.
- 같은 action의 launch reservation은 `O_CREAT|O_EXCL` + mode `0600`으로 fencing한다. 동시 두 기동은
  정확히 하나만 시작하고 다른 하나는 `supervisor_already_started`로 거부한다. detached `Popen` 자체가
  명확히 실패한 경우에는 known-unused reservation을 제거하고 typed failure를 반환한다.
- 신규 의존성은 없다.

변경 파일:

- `waystone/runs/supervisor.py` — detached supervisor, identity/heartbeat/wait evidence, effects adapters,
  positive liveness/quiescence/absence probes
- `scripts/tests/test_run_supervisor.py` — supervisor 계약/fault fixture 11개
- `scripts/tests/run_tests.py` — `RunSupervisorTests` import와 aggregate tuple 등록만 추가

`REPORT.md`는 지시대로 untracked이며 구현 커밋에 포함하지 않았다.

## 2. 계약 매핑

이 task에 직접 귀속된 promoted PC 행은 없다. `dev_docs/m1b-slice-plan.md` §3/§5가 신규 의무
E-08, E-09(runtime identity), ADR-0003 supervision, fixture 1·2, D6/S2를 이 task에 귀속한다.

| 귀속 계약 / fixture | 이를 단언하는 테스트 함수 |
|---|---|
| §6 fixture 1 — heartbeat stale + matching live child는 exited/quiescent/cleanup으로 판정하지 않음 | `test_fixture_1_stale_heartbeat_matching_live_child_is_not_exited_or_quiescent` |
| §6 fixture 2 — PID reuse 또는 boot mismatch는 `unknown(identity-mismatch)`, destructive 판정 0 | `test_fixture_2_pid_reuse_and_boot_mismatch_are_unknown_identity_mismatch` |
| D6·S2 — detached supervisor가 launcher parent 종료 뒤에도 wait/marker/artifact를 완성 | `test_detached_supervisor_survives_launcher_parent_death_and_publishes_marker`, `test_detached_launcher_uses_start_new_session_and_returns_pid` |
| 동일 action 이중 supervisor 기동 fencing / typed refusal | `test_same_action_concurrent_supervisor_launch_refuses_one`, `test_failed_detached_popen_does_not_poison_launch_reservation` |
| effects ④6 — callback 내부 실제 spawn 직전 WAI-bound principal 재검증, stale principal에서 Popen 0 | `test_spawn_revalidates_principal_inside_callback_and_refuses_before_popen` |
| E-08 — silence가 아닌 matching OS identity/wait status만 positive alive/exit; signal/returncode 양자택일 | `test_fixture_1_stale_heartbeat_matching_live_child_is_not_exited_or_quiescent`, `test_detached_supervisor_survives_launcher_parent_death_and_publishes_marker`, `test_signal_exit_uses_signal_field_and_stream_bytes_are_artifacts` |
| effects ④17 — process identity 기반 positive quiescence/absence producer와 callback-shaped adapter | `test_fixture_1_stale_heartbeat_matching_live_child_is_not_exited_or_quiescent`, `test_fixture_2_pid_reuse_and_boot_mismatch_are_unknown_identity_mismatch`, `test_detached_supervisor_survives_launcher_parent_death_and_publishes_marker` |
| effects ④5 — WAI+marker 부재에 대한 boot/start-token exact-identity absence evidence 산출 | `test_fixture_2_pid_reuse_and_boot_mismatch_are_unknown_identity_mismatch` (producer만 검증; 현 effects consumer 부재는 §4-1) |
| worker가 marker 직접 작성 불가 — copied live identity도 wait receipt/fence 불일치로 거부 | `test_worker_written_marker_with_copied_identity_or_wrong_fence_is_rejected` |
| completion 최소 필드 + stdout/stderr CAS artifact digest-only | `test_detached_supervisor_survives_launcher_parent_death_and_publishes_marker`, `test_signal_exit_uses_signal_field_and_stream_bytes_are_artifacts` |
| §3-10 / E-09 runtime identity 최소 축과 canonical attribution | `test_process_identity_canonical_round_trip_binds_all_minimum_axes`, `test_fixture_2_pid_reuse_and_boot_mismatch_are_unknown_identity_mismatch` |
| heartbeat freshness는 wall time이 아니라 same-boot monotonic domain | `test_heartbeat_freshness_never_crosses_boot_or_wall_clock_domains`, `test_detached_supervisor_survives_launcher_parent_death_and_publishes_marker` |

## 3. 검증 결과

- 계약 지정 aggregate 명령:
  `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1b-supervisor.log 2>&1; echo "suite rc=$?"`
- 결과: `suite rc=0`
- 로그: `/tmp/suite-m1b-supervisor.log`
- 로그 종결: `Ran 988 tests in 103.103s` / `OK`
- focused: `uv run scripts/tests/test_run_supervisor.py` — `Ran 11 tests in 0.896s` / `OK`
- supervisor + effects + lease 집중 aggregate: 46 tests / `OK`
- `git diff --check`: green
- 독립 검토에서 재현된 두 결함을 수정 후 재검증했다.
  - current-version laundering은 durable WAI-bound transition version guard로 폐쇄
  - live worker의 exact copied identity marker 위조는 supervisor wait receipt 필수화로 폐쇄

## 4. 계약 해석 및 needs-ruling 후보

1. **현재 effects runner reconcile에는 positive absence 소비 seam이 없다.** Supervisor는 rich tri-state
   `probe_action`, `positive_absence_probe`, plan-shaped `effect_absence_probe`, `quiescence_probe`를 제공한다.
   그러나 `effects.py`는 runner WAI가 있고 marker가 없으면 quiescence callback을 호출하기 전에
   `unknown-effect`를 반환하며, runner branch는 same-action relaunch도 무조건 금지한다. 따라서 ④5의
   “영구 unknown-effect를 stronger absence evidence로 해소”는 producer까지 구현했지만 현 consumer에
   연결할 수 없다. 기존 모듈 수정 금지 때문에 우회하지 않았다. runner-specific absence observer를
   effects 경계에 추가할지 ruling이 필요하다.

2. **supervisor crash의 portable wait-status 한계.** Runtime identity 게시 뒤 supervisor만 죽고 worker가
   계속되면 resume은 동일 identity의 alive/absence를 재관측할 수 있지만, 다른 process는 POSIX
   `waitpid`로 원래 returncode/signal을 회수할 수 없다. marker/wait receipt 전에 둘 다 죽은 경우 status를
   추측하지 않고 unknown에 둔다. 완전한 completion 복구가 필요하면 worker exec 전 barrier를 가진
   engine-owned exit-receipt trampoline 또는 동등한 OS adapter 계약이 필요하다.

3. **아주 이른 supervisor startup crash.** Outer detached `Popen` 성공 뒤 runtime identity 게시 전에
   supervisor가 비동기 사망하면 launch reservation만 남을 수 있다. 이 경우 재진입은
   `reserved-without-observable-identity` typed refusal로 이중 기동을 막지만 자동 재기동하지 않는다.
   “resume reconcile이 supervisor 자체 사망을 복구”가 이 window의 재기동까지 뜻한다면 supervisor-start
   acknowledgement + worker pre-exec barrier/fenced re-entry protocol을 추가해야 한다. 현재 구현은
   at-most-once 안전 방향을 우선했다.

4. **heartbeat 저장 형식 경계.** 기존 schema v1의 `action_runtime`에는 boot identity/monotonic/process
   identity column이 없고 기존 store/lease 수정도 금지됐다. 따라서 `LeaseManager.renew()`의 DB mutable
   telemetry와 supervisor atomic heartbeat sidecar를 조합했다. freshness 판단은 sidecar의 same-boot
   monotonic 값만 사용하고 wall DB 시간은 authority로 쓰지 않는다. 이 세 축을 반드시 단일 SQLite row에
   넣어야 한다면 schema v-next/API ruling이 필요하다.

5. **boot/PID-start mismatch의 두 의미를 분리했다.** ADR-0003 fixture 문언에 따라 public liveness는
   `unknown(identity-mismatch)`이고 cleanup/quiescence는 false다. 동시에 ④5 예시에 따라 “기대했던 exact
   old identity는 현재 존재하지 않는다”는 absence evidence bit는 true로 보존한다. 다른 PID process를
   alive/exited라고 판정하지 않는다. mismatch 자체를 곧바로 public `exited`로 투영하는 대안은 기각했다.

6. **effects가 full principal과 invocation argv를 전달하지 않는 경계.** `RunnerLaunchIntent`에는
   `entity_version`과 argv/cwd가 없다. Version은 current row가 아니라 durable WAI-bound effect transition에서
   재도출해 owner/fence와 함께 guard한다. argv/cwd는 injected digest-keyed map으로 해결하고, pending format
   ruling을 선점하는 신규 전역 invocation digest canonicalization은 만들지 않았다. 장기적으로 intent에
   full principal 또는 WAI version을 직접 넣으면 adapter가 더 단순해진다.

7. **lease guard callback 문언.** `LeaseManager._guard_operation` docstring은 callback을 짧은 DB/telemetry
   mutation으로 설명한다. ④6 race를 실제로 닫기 위해 supervisor launch reservation과 즉시 반환하는
   detached `Popen`만 guard callback 내부에서 수행했고, process wait/lifetime은 밖의 detached process가
   담당한다. Popen을 guard 뒤에 두는 대안은 명시된 race를 재도입하므로 사용하지 않았다.

8. **marker authority와 same-account 위협 경계.** 단순 identity/fence 복사 위조는 실제 wait 뒤에만 생기는
   wait receipt가 없어서 거부된다. 동일 OS account의 악의적 worker가 supervisor state 전체까지 임의
   수정하는 공격을 암호학적으로 막는 것은 현재 ADR-0013 threat 경계 밖이다. 그 위협까지 포함한다면
   capability/permission 분리 또는 supervisor 전용 signing authority가 필요하다.

9. Existing effects marker schema는 구현 계약 최소 필드 외에 `run_id`, `job_id`, `launch_token`을 exact
   필수로 요구한다. 새 schema를 만들지 않고 이 세 필드를 포함하는 adapter를 사용했다.

## 5. 스코프 밖에서 발견·유보한 항목

- `effects.py` runner WAI + marker 부재 분기는 supervisor의 stronger absence evidence를 받을 수 없다
  (§4-1). 이 task의 기존 모듈 수정 금지 때문에 수정하지 않았다.
- supervisor crash 뒤 portable wait status 회수와 pre-runtime startup acknowledgement/trampoline은
  별도 substrate/ruling이 필요하다 (§4-2·3).
- stdout/stderr CAS bytes는 effects observer가 digest로 검증하지만 schema v1 DB에 직접 artifact reference를
  추가하지 않는다. 향후 GC가 observation receipt graph를 재귀 추적하지 않는다면 별도 reference/ruling이
  필요하다.
- aggregate suite 뒤 ignored `.waystone/.gitignore`와 `.waystone/lock`이 존재한다. 지시대로 복원·삭제하지
  않았다. `.waystone/profile.yml`은 harness-provided ignored state이며 `.waystone/resume.md`는 생성되지 않았다.
- suite가 만든 ignored `__pycache__/` 경로는 추적하지 않았고 변경하지 않았다.
