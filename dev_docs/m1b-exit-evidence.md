# M1-B exit 증거표 — gate/m1b-exit

- Status: **판정 확정** (2026-07-21, main; 리뷰 사이클 반영 갱신 — 하단 "리뷰 반영" 절)
- 기준: `dev_docs/m1b-slice-plan.md` §6 (9항)
- 대상: dev `dade8f8` (구현 15 task 전량 병합, 통합 suite 1088 green) → 리뷰 수리 후 `145e37b` (suite 1099 green)
- 검증 체계: 기체 suite → main 독립 재실행 → opus 반증 검증(대형 10기) → 병합 조합 suite
  4중 게이트. 기체별 상세는 `docs/meta/agent-reports-2026-07-21/*.md` (보고 12건).

| # | Exit 기준 | 판정 | 증거 |
|---|---|---|---|
| 1a | 단일 task run 완주 (fixture runner 계약 테스트) | **충족** | bridge e2e `test_one_task_cli_run_completes_...` — 실제 detached 서브프로세스, private ref OID == worker 결과 커밋, live tree porcelain 공백 (opus 진위 검증: mock 단계 건너뛰기 없음) |
| 1b | 실 backend 수동 smoke 1회 (D7) | **충족** | codex exec(gpt-5.6-sol, effort low) runner로 완주 — 하단 기록 |
| 2 | effect 종류별 crash recovery green | **충족** | effects `test_all_effect_kinds_crash_{before,after}_effect_...` — 5종 × 효과 전/후 사망, 실행 카운터로 재실행 0 실증 (opus probe A~D) |
| 3 | `actions next`가 engine-owned action 미반환 | **충족** | transport `test_actions_next_exhausts_engine_action...` + bridge e2e busy 분기 — opus가 반환 지점 전수 열거로 확인 |
| 4 | `run status`/`watch`가 §3-8 계약대로 | **충족** | observe 23건 (3분리·derived health·frozen closure 분모) + bridge read-only opener 조합 |
| 5 | fault fixture 8건 green | **충족** | 1·2 supervisor(stale heartbeat 무정리·PID 재사용 unknown), 3 effects(exited-unreconciled 정확-1회), 4 cancel(5 case, bytes 보존), 5 observe(반복 조회 무부작용 — opus 100회 byte probe), 6·7·8 lease(principal 주입·lock recheck·reclaim race — opus 20경로 mutation 0 probe). D10: fixture 8 공동 소유(lease stale-principal 절 + effects semantic dedupe 절) 양쪽 green |
| 6 | 승격 계약 귀속표(§3) M1-B분 green | **충족** | PC-14(review-uuid)·PC-15/17(spec)·PC-16/17/20/21/22(verify — opus 판별성 probe·11-artifact tamper matrix)·PC-18/19(store)·PC-27/28/29(preflight — WS-GPT-102 세탁 반증)·PC-31(spec+bridge 표면)·I-10(prompt 전문 oracle)·E-03(preflight 3축)·E-06(store)·E-08(supervisor/observe/cancel)·E-09(store/supervisor)·ADR-0003 취소 절(cancel)·ADR-0013 3행(lease) — 전부 suite 1088에 포함 green |
| 7 | legacy suite green + known-debt 대비 신규 위반 0 | **충족** | m1a manifest 838 기준 legacy 전체가 1088 안에서 green (구식화 8건은 D3 특례 main 승인·보고서 §6 전수 열거·opus 1:1 대체 판정). 신규 모듈은 known-debt 목록 외 invariant 위반 미도입 (opus 반증 검증 10기 blocker/major 0) |
| 8 | network-resilience 기질 S1–S3 (D4) | **충족** | S1: unknown-effect 정직 대기 + reconcile 수렴 (effects fixture 3·관측 불가 fixture). S2: detached supervisor 세션 사망 후 marker 완성 (supervisor e2e + opus probe: 세션리더·init reparent 실증). S3: transport envelope의 transient/terminal/unclassified 분류 (recoverable 필드) |
| 9 | JW-GPT-014/015 부류 처분 | **충족** | 014 부류: store 단일 transaction 증명 fixture(`test_jw_gpt_014_...`) — 새 store에서 관측-기록 분리 성립 불가. 015 부류: canonical UUID owner directory가 live packet 경로에 가동(3층 fixture) — flat delimiter collision 구조 소멸. 처분: 두 blocked task는 legacy 기계의 결함으로서 **legacy-residual 확정**(ADR-0009 문언대로 기존 flat evidence의 ambiguity는 소급 제거 불가) + 신규 시스템에서의 재현 불가는 위 fixture가 보증. blocked 해제 → 종결 |

## 부수 산출물

- `docs/run-engine-formats.md` — v1 format registry 확정 (decision/run-engine-format-pinning-batch 이행)
- 후속 task 등록 12건 (opus/기체 발견 전량 추적): principal project/executor 축·absence seam·
  approval reconcile 결속·probe binding·canceled-run child 거부·readonly opener·production
  assembly·CLI 커버리지·label 커버리지·status 격리·PR canonical·profile drift
- 미해소 known-gap은 전부 registry(§9 미고정 포함)와 decision/run-engine-format-pinning-batch
  ruling에 기록 — silent 공백 0

## 1b 실 backend smoke 기록 (2026-07-21, PASS)

- run_id `019f81f9-78d5-76bd-9243-c3c0c124998b` — bridge e2e fixture 조립을 재사용하되
  RunnerInvocation argv를 실제 `codex exec -m gpt-5.6-sol -c model_reasoning_effort=low ...`로
  치환 (D7 의도대로 실 backend 대상은 runner 경로; verifier/decision은 fixture adapter).
- `start()` 0.22s 반환(detached 실증) → supervisor가 codex 기동(~14s) → completion marker
  returncode 0 → resume 2회로 reconcile→verify→ACCEPT→apply → run `completed`·job `accepted`.
- `refs/waystone/integration/<run_id>` OID == worker 결과 커밋 OID(`8e80f2e3…`) — frozen base의
  정확한 단일 직계 자식이며 내용(`result.txt`)이 codex 산출물임을 확인. live tree 불변
  (`git status --porcelain` 공백).
- 최초 실행의 red 1건은 smoke 스크립트의 exact-string 단언에 codex가 마침표를 덧붙인 것
  (엔진 경로는 동일 green) — 단언을 token 매칭으로 정정 후 clean 재실행. 엔진/하네스 typed
  error 0회.
- 스크립트·로그: scratchpad/fleet/smoke/{smoke.py,smoke.log} (세션 산출물, repo 외부).

## 리뷰 반영 (2026-07-21-m1b-vertical-slice 회신, codex high — major 6)

외부 리뷰가 초판 판정의 과대 항목 2곳을 정당하게 잡았고, 즉시 수리로 폐쇄했다:

- **행 6 (PC-22)**: 초판은 crash-reconcile 창(공개·등록 상태)을 두고 green을 선언 —
  과대. WS-GPT-602 수리(`ac863f7`: approval digest 4종 plan 동봉 + reconcile 재해시 대조)로
  창 폐쇄 후 충족 확정.
- **행 8 (S1)**: 초판은 WAI+launch 실패의 영구 unknown-effect(공개·등록 상태)를 두고 충족
  선언 — 과대. WS-GPT-604 수리(`ac863f7`: RunnerAbsenceProbe seam, positive exact-identity
  absence만 소비)로 수렴 경로 확보 후 충족 확정.
- **추가 폐쇄**: WS-GPT-601(CONFIRMED major — verifier 발행 후 crash 시 resume 영구 brick,
  exit 표가 놓친 조립 단계 crash recovery)을 `145e37b`(단계별 재진입 reload)로 폐쇄.
- 나머지: 603 minor(ruling 유지·hardening task), 605 REJECTED(M1-C 계획 소관),
  606 CONFIRMED(registry 정정 완료). 상세는 feedback triage.

수리 3건 전부 4중 게이트(RED-first/기체 suite/main 재실행/opus 반증) 통과, 최종 suite
**1099 green** @ `145e37b`. exit 9항 판정은 이 갱신 기준으로 확정이다.
