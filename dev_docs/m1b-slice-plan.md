# M1-B 분해 계획 — one-task vertical slice

- Status: 확정 (main 설계, 2026-07-21) — `docs/m1b-slice-decomposition`의 산출물
- 상위 권위: `dev_docs/0.12.0-refactor-plan.md` §M1-B·§3-1·§3-4·§3-5·§3-6·§3-8·§3-9·§3-10,
  ADR-0014(합격 기준·단계별 귀속 원칙), accepted ADR-0002/0003/0004/0005/0007/0008/0010/0012/0013,
  `docs/promoted-contracts.md`
- ADR-0014 Amendment §2에 따라 **M1-B의 승격 계약 귀속표는 이 문서가 확정한다** (§3).

## 1. 범위와 비-범위

**범위:** 단일 task = 단일 run/job의 vertical slice. transactional store(§3-1) + artifacts +
effect commit protocol(§3-4) + lease/fencing(§3-5) + executor 경계(§3-6) + 관측(§3-8) +
취소 안전(§3-9) + supervision/identity(§3-10) + 4-role domain model + profile v1 adapter +
frozen RunSpec/VerificationPlan + I-10 minimal prompt + `waystone run` 사용자/transport 표면 +
delegate opt-in bridge + fault fixture 8건 + JW-GPT-014/015 부류 처분 + ADR-0009 runs/<uuid>/
writer/reader.

**비-범위 (명시):** multi-job run·integration worktree·delivery policy·`run deliver`(M2),
improve/overlay/review feature 이동(M2+), front-door delegate 경로의 기본 전환과 legacy
characterization 호환(M1-C), DB schema upgrade smoke·backup 경로 검증(M1-C, PC-24 포함),
push/GitHub-marker effect kind의 실사용(M2 — kind 표는 확장 가능하게만).

## 2. 분해 결정 (falsifiable)

- **D1 — 신규 코드는 `waystone/` 패키지 전용, legacy `scripts/*` 무변경.** 예외 2건만 허용:
  ⑴ `scripts/tests/run_tests.py`의 신규 테스트 모듈 등록(추가만) ⑵ `feat/review-runs-uuid-owner-directory`가
  ADR-0009 wiring을 위해 touch하는 review 경로(§2 D3). legacy suite 838 green이 무변경 경로의
  공짜 drift 신호로 유지된다. `docs/m1a-suite-manifest.txt`는 legacy suite identity로 계속
  유효하며, M1-B 신규 테스트는 신규 모듈로 추가되고 이 계획 §5가 그 목록을 소유한다.
- **D2 — M1-B의 주 표면은 `waystone run …`이고 delegate 연결은 명시 opt-in.** 계획서 M1-B의
  "기존 delegate wrapper가 새 엔진 호출"은 opt-in bridge(`waystone run start <task-id>`가
  one-task delegate 동등 흐름을 수행 + delegate 표면에서의 명시 플래그 진입)로 이행한다.
  기본 경로 전환은 M1-C 소유 — M1-B가 기본을 바꾸면 M1-C의 cut-over exit가 공집합이 된다.
  silent switch 금지(전역 원칙).
- **D3 — JW-GPT-014 부류 fixture는 store kernel이 소유** (관측-기록이 한 transaction — 분류
  경로 단일성 증명). **JW-GPT-015의 보상 vehicle은 `feat/review-runs-uuid-owner-directory`**:
  live packet-mode review write 경로를 `docs/reviews/runs/<uuid>/`로 전환 + flat legacy는
  read-only adapter. 이 task만 legacy review 코드·테스트를 touch할 수 있고, 변경되는 legacy
  test-ID는 보고서에 전수 열거해 main 승인 후 PROGRESS에 기록한다(m1a manifest의
  approved-diffs 방식 준용). 두 blocked task(fix/merge-observed-demotion-persistence·
  fix/ingest-malformed-foreign-freeze-skip)는 각 fixture/구현 착지 시 gate/m1b-exit에서
  처분(superseded 또는 legacy-residual 확정)한다.
- **D4 — `feat/delegation-network-resilience`는 M2 배치.** 사용자 요청(2026-07-20) 기능의
  전제 기질(substrate)은 M1-B가 놓고 exit에서 확인한다(§6 S1–S3): unknown-effect 정직 정지 +
  resume reconcile, **세션과 독립 생존하는 detached supervisor**, typed envelope의
  recoverable 분류. auto-wait/retry/backoff/resume 정책 자체는 이 기질 위의 M2 작업이다.
  (M2가 밀리면 동일 기질 위에서 M1-C 직후로 앞당길 수 있다 — 재배치는 main 결정.)
- **D5 — 신규 엔진의 Git 사실은 `waystone.adapters.git` 단일 원천.** 신규 모듈에서
  `runs/delegate.py`의 `_git*` 중복 구현 재생산 금지. legacy `_git` 정리·통합은 M1-C
  cut-over가 소유한다(예약 항목 "delegate _git↔adapters.git 정렬"의 처분).
- **D6 — supervisor는 detached engine process** (`start_new_session=True`): CLI/호스트 세션
  종료 후에도 heartbeat 갱신·exit status 회수·completion marker 작성을 계속한다. supervisor
  자체의 사망은 `run resume`의 reconcile(ADR-0002 결정표)이 복구한다.
- **D7 — 계약 테스트는 결정적 fixture runner**(스크립트 실행 파일)로 작성하고, 실 backend
  (codex exec) e2e는 gate에서 수동 1회 smoke로만 확인한다.
- **D8 — 신규 의존성 0.** stdlib `sqlite3` + 기존 pyyaml. Python ≥ 3.10.

## 3. 승격 계약 귀속표 (M1-B분 — ADR-0014 Amendment §2 위임 이행)

**M1-B exit에 귀속 (새 계약 테스트 의무):**

| 계약 | 소유 task |
|---|---|
| PC-14 (flat legacy review archive read + 신규 writer 소급 수정 금지) | feat/review-runs-uuid-owner-directory |
| PC-15 (job input freeze·drift 거부) | feat/run-spec-planning |
| PC-16 (Git-파생 사실 엔진 재도출·patch bytes 결속·tamper 거부) | feat/run-verify-decision |
| PC-17 (live tree/index 불변·apply의 user dirt 보존·drift no-write) | feat/run-spec-planning(snapshot) + feat/run-verify-decision(apply) |
| PC-18 (attempt·evidence·decision append-only) | feat/run-store-kernel |
| PC-19 (corrupt record 격리·healthy 무중단) | feat/run-store-kernel + feat/run-observability |
| PC-20 (verifier 분리·read-only·무효 출력 무발행) | feat/run-verify-decision |
| PC-21 (decision의 criterion·verifier evidence 결속) | feat/run-verify-decision |
| PC-22 (accept/apply 실행 시점 재검증) | feat/run-verify-decision |
| PC-27 (미지원 실행 typed refusal, worker 시작 전) | feat/run-domain-roles + feat/run-verification-preflight |
| PC-28 (runner proof bounded 관측축) | feat/run-verification-preflight |
| PC-29 (relocation-stable digest·config content 무효화) | feat/run-verification-preflight |
| PC-31 (미초기화 root typed refusal — **신규 run 표면 한정**) | feat/run-spec-planning + feat/run-cli-bridge |
| 신규 의무 I-10 (minimal worker prompt) | fix/delegate-prompt-i10-surface-strip |
| 신규 의무 E-03 잔여 (checkout·machine·principal mismatch proof 거부) | feat/run-verification-preflight |
| 신규 의무 E-06 잔여 (artifact reference 복구·digest 재검증) | feat/run-store-kernel |
| 신규 의무 E-08 (positive liveness/exit·사유 있는 unknown·destructive resolution 금지) | feat/run-supervisor-identity + feat/run-observability + feat/run-cancel-quiescence |
| 신규 의무 E-09 잔여 (**runtime identity 한정** — ambient 값 authority 금지) | feat/run-store-kernel + feat/run-supervisor-identity |
| ADR-0003 취소·quiescence·cleanup 절 | feat/run-cancel-quiescence |
| ADR-0013 lease principal CAS / lock 후 tuple recheck / reclaim race (TODO M1-B 3행) | feat/run-lease-fencing |

**명시적 비-M1-B 귀속 (누락이 아니라 처분):** PC-01~08(task registry·round — §2-6 형식 불변,
재구축 안 함), PC-09~13(review 재구축 마일스톤 — ADR-0009 writer/reader만 M1-B), PC-23·25·26
(config·policy 재구축 마일스톤), PC-24 + I-07 잔여(M1-C schema upgrade smoke와 함께),
PC-30(M3 thin surface), E-04(M2 closeout manifest), E-09 잔여 중 review filename 분해 축(review
재구축). PC-31의 전 표면 폐쇄는 M4.

## 4. 대상 모듈 배치 (경계 pin — 내부 helper 분리는 worker 재량)

```text
waystone/runs/store.py        스키마 v1·open/txn/CAS·transitions·run_id(UUIDv7, ADR-0005)
waystone/runs/artifacts.py    content-addressed artifacts/sha256-* (E-06)
waystone/runs/lease.py        lease·fencing epoch·owner token·OS advisory lock (ADR-0013)
waystone/runs/effects.py      ADR-0002 lifecycle·effect-kind 계약표·reconcile 결정표
waystone/runs/supervisor.py   detached supervisor·process identity·completion marker (ADR-0003)
waystone/runs/observe.py      status/watch read-only projection (§3-8)
waystone/runs/cancel.py       취소·quiescence·cleanup (§3-9)
waystone/runs/spec.py         frozen RunSpec·job input freeze·snapshot (ADR-0010)
waystone/runs/preflight.py    frozen VerificationPlan·capability preflight (ADR-0012)
waystone/runs/prompt.py       I-10 minimal worker prompt 조립
waystone/runs/transport.py    actions next/submit·typed envelope (ADR-0004, §3-3)
waystone/runs/verify.py       verifier 실행·integration decision·apply
waystone/jobs/domain.py       4-role model + executor_kind (ADR-0008/0004)
waystone/jobs/profile_v1.py   profile v1 adapter (implementer→worker 판독)
waystone/cli/run_group.py     run start/resume/status/watch/cancel + actions + bridge
```

DB는 `.waystone/state.db` (ADR-0007: WAL 확인·filesystem 판정·silent fallback 금지). GC·backup
구현은 M1-C 이후로 미루되 store 스키마는 mark-root 질의가 가능하게 참조를 기록한다.

## 5. Task 분해 (계약·fixture 결속 포함)

| Task | Deps | 핵심 계약 | 신규 테스트 모듈 |
|---|---|---|---|
| feat/run-store-kernel | — | ADR-0005/0007, PC-18·19, E-06·E-09 잔여, **JW-GPT-014 부류 fixture** | test_run_store.py |
| feat/run-lease-fencing | store-kernel | ADR-0013 3계약, **fixture 6·7·8** | test_run_lease.py |
| feat/run-domain-roles | — | ADR-0008/0004 enum·adapter, PC-27(binding 판독) | test_run_domain.py |
| feat/review-runs-uuid-owner-directory | — | ADR-0009, PC-14, **JW-GPT-015 fixture** (D3 특례) | test_review_runs_layout.py |
| feat/run-effect-protocol | store-kernel, lease-fencing | ADR-0002 전체, **fixture 3** + effect-kind별 crash fixture | test_run_effects.py |
| feat/run-spec-planning | store-kernel, domain-roles | ADR-0010, PC-15·17(snapshot)·31 | test_run_spec.py |
| feat/run-verification-preflight | spec-planning | ADR-0012, PC-27·28·29, E-03 잔여, **env-prep toolchain digest 편입**(fix/env-prep-toolchain-digest-binding 동시 폐쇄) | test_run_preflight.py |
| feat/run-supervisor-identity | effect-protocol | ADR-0003 supervision, **fixture 1·2**, D6 detached | test_run_supervisor.py |
| feat/run-observability | store-kernel, supervisor-identity | §3-8 계약, **fixture 5**, PC-19(healthy 무중단) | test_run_observe.py |
| feat/run-cancel-quiescence | supervisor-identity, effect-protocol | §3-9·ADR-0003 취소 절, **fixture 4** | test_run_cancel.py |
| fix/delegate-prompt-i10-surface-strip | spec-planning | I-10 신규 의무 — goal·bounds·acceptance·WAYSTONE_REPORT stanza만; routing_note는 **투영 자체 제거**(값 검증 아님 — 단순안); anchor는 goal/bounds 자료로 재편성 | test_run_prompt.py |
| feat/run-actions-transport | effect-protocol, spec-planning | ADR-0004 3분기 비차단·submit 5검증·engine-owned 내부 소진·typed envelope | test_run_transport.py |
| feat/run-verify-decision | verification-preflight, effect-protocol | PC-16·17(apply)·20·21·22, retry=새 attempt+새 action id, D5 adapters.git 단일 원천 | test_run_verify.py |
| feat/run-cli-bridge | actions-transport, verify-decision, observability, cancel-quiescence, i10-strip | §3-3 사용자 표면·D2 opt-in bridge·PC-31(표면) | test_run_cli.py |
| gate/m1b-exit | 전부 | §6 exit 전 항목 검증 + 처분 기록 | — |

## 6. Exit (gate/m1b-exit가 검증)

1. 단일 task run이 새 엔진으로 완주 (fixture runner 계약 테스트 + 실 backend 수동 smoke 1회).
2. effect-protocol 기반 crash recovery green — effect 종류별 fixture (git ref·worktree·
   artifact·runner at-most-once·patch integration).
3. `actions next`가 engine-owned action을 반환하지 않음.
4. `run status`/`watch`가 §3-8 계약(liveness/progress/current 분리·derived health)대로 답함.
5. **fault-injection fixture 8건 green** (소유: §5 표 — 1·2 supervisor, 3 effects, 4 cancel,
   5 observe, 6·7·8 lease).
6. 승격 계약 귀속표(§3)의 M1-B분 계약 테스트 전부 green.
7. legacy suite green (m1a manifest 838 기준; D3 특례 diff는 승인 기록 필수) + known-debt
   기준선 대비 신규 I-01~12·E-01~09 위반 0.
8. **network-resilience 기질 확인 (D4):**
   - S1 — runner effect 중 네트워크/backend 소실 시 run이 실패로 붕괴하지 않고
     `unknown-effect`/waiting으로 정직 정지, `run resume`이 reconcile로 복구.
   - S2 — supervisor가 호출 세션 종료 후에도 생존해 completion marker를 회수(D6).
   - S3 — typed envelope가 transient(network/API)·terminal 실패를 recoverable 분류로 구분.
9. JW-GPT-014/015 부류 처분 기록(D3) — blocked 2건의 종결 상태 확정.

## 7. Wave 계획 (deps 위상순 — 병렬은 scope 분리 확인 후)

```text
A: run-store-kernel ∥ run-domain-roles ∥ review-runs-uuid-owner-directory
B: run-lease-fencing ∥ run-spec-planning
C: run-effect-protocol ∥ run-verification-preflight
D: run-supervisor-identity ∥ i10-surface-strip
E: run-observability ∥ run-cancel-quiescence ∥ run-actions-transport
F: run-verify-decision
G: run-cli-bridge → gate/m1b-exit
```

운영 규칙(M1-A 교훈 승계): 기체별 고유 suite 로그 · rc는 파이프 없이 직접 캡처 · suite
timeout 300s+ · codex 로그는 UTC · worktree는 dev HEAD pinned commit에서 생성 · 병렬 기체 간
공유 파일 금지 · 신규 테스트 모듈명은 §5 표 고정(중복 등록 방지).
