# Review Request — 2026-07-21-m1b-vertical-slice

The reviewer has the repository via git. This is a domain/code review, not a workflow audit —
keep the waystone harness out of scope unless asked.

- Project: waystone
- Branch: dev
- Reviewer: codex:gpt-5.6-sol
- Reviewing: 885a7ad311d3aca063628f78053503e8c21b767f   (diff against bc18acf7508fe03dab91248adefb55c817487731)

<!-- Keep the Reviewing field on exactly one line with the literal spacing shown above. -->

## What changed and why

M1-B one-task vertical slice 전체가 하루에 착지했다: 새 run engine의 저장(store/artifacts)·
잠금(lease/fencing)·계획(spec)·검증준비(preflight)·실행(effects)·감독(supervisor)·관측
(observe)·취소(cancel)·프롬프트(prompt)·전송(transport)·인수(verify)·조립(engine/CLI) 12개
신규 모듈 + ADR-0009 canonical review layout의 live 가동 + ADR-0013 permission 강화.
suite 838→1088 (신규 계약 테스트 ~250, legacy 구식화 8건은 main 승인 대체). exit 판정은
`dev_docs/m1b-exit-evidence.md`가 9항 전항 충족으로 기록하며, 실 backend smoke(codex exec
runner 완주)까지 포함한다. 설계 권위는 `dev_docs/m1b-slice-plan.md`(D1–D10 + PC 귀속표)다.

## Read these first

1. `dev_docs/m1b-slice-plan.md` — 분해 결정과 M1-B 계약 귀속표 (ADR-0014 Amendment §2 위임 이행)
2. `dev_docs/m1b-exit-evidence.md` — exit 9항 증거표 + 실 backend smoke 기록
3. `docs/run-engine-formats.md` — v1 format registry (§9 미고정 목록 포함)
4. `docs/meta/agent-reports-2026-07-21/` — 기체 보고 12건 (각 ④절이 해석·needs-ruling 전수)
5. `docs/adr/ADR-0010-run-spec-readiness.md` Amendment (2026-07-21) — v1 acceptance adapter ruling
6. PROGRESS.md 2026-07-21-m1b-vertical-slice 절

## Claims to attack

1. **M1-B exit 9항 충족 판정이 성립한다** — 특히 fault fixture 8건이 계획 §6 문언을 실제로
   검사하며(자명통과·이름-본문 불일치 없음), 실 backend smoke가 D7의 의도(runner 경로가 실
   backend)를 충족한다는 판정.
2. **PC 귀속표(M1-B분)의 계약 테스트가 각 PC 행의 의미를 실제로 재작성했다** — 특히
   PC-21(worker 자기수용 차단)·PC-22(실행 시점 재검증)·PC-17(live tree 불변)의 구현이 계약
   문언과 등가라는 주장. 알려진 잔여 창(PC-22 crash-reconcile, checkout-CAS TOCTOU)은
   등록·ruling됐다 — 그 처분의 타당성 자체를 공격하라.
3. **legacy 구식화 8건(리뷰 test-ID 삭제)이 유효한 보호의 약화가 아니다** — ADR-0009 하에서
   재발행/legacy-write 계약이 진짜 구식이라는 판정 (docs/meta/agent-reports-2026-07-21/
   m1b-review-uuid.md §6 전수).
4. **v1 표현 계약(format registry)과 그 미고정 목록(§9)의 경계가 정직하다** — 고정했다고
   주장하면서 실제로는 코드에 없는 항목, 또는 고정해야 하는데 미고정에 숨긴 항목이 없다.
5. **네트워크 복원 기질 S1–S3이 실재한다** — unknown-effect 정직 대기+resume 수렴, 세션 사망
   후 supervisor 생존, transient/terminal recoverable 분류.
6. **ADR-0010 Amendment의 v1 adapter가 silent 준수 위장이 아니다** — critic-not-required
   기록이 면제가 아니라 이월임이 문언·구현 양쪽에서 성립하는가.

## Evidence already produced (mine — inspect, don't trust)

- 4중 게이트: 기체 suite → main 독립 재실행 → opus 반증 검증 10기(전 기 blocker/major 0,
  직접 probe 포함: raw sqlite 트리거 우회, stale principal 20경로 mutation 0, 위조 toolchain
  세탁 반증, detached 생존(세션리더·init reparent), status 100회 byte 불변, 파괴 경로
  4벡터+store-일관 위조, decision 판별성 5공격, I-03 위조 13종) → 병합 조합 suite. 각 검증
  전문은 기체 보고와 이 세션 기록에 있으며 suite 로그는 /tmp/suite-dev-merge-*.log 계열.
- 실 backend smoke: run_id 019f81f9-78d5-76bd-9243-c3c0c124998b, marker rc=0, private
  integration ref OID == codex 결과 커밋 OID, live tree porcelain 공백.
- 병합 사고 1건 자진 기록: run_tests.py 충돌 마커 커밋(e61201a) 즉시 수리(7ec778a).

## Known weak spots

1. PC-22 crash-reconcile 창: patch effect plan 저장~generic reconcile 사이 crash 시 approval
   bundle 재검증 없음 — `fix/patch-effect-approval-reconcile-binding` 등록, M1-B 내 미수리.
2. effects가 supervisor의 positive absence 증거를 소비할 seam 부재 — 영구 unknown-effect 해소
   경로 미연결(`fix/effects-runner-absence-seam`).
3. lease principal의 project/executor 축 미결속 — cross-project DB 복사 시 원 principal 통과
   (재현 확인, `fix/lease-principal-project-executor-binding`).
4. production RunAssembly factory 부재 — 실운영 `run start`는 typed refusal (bridge ④1, gate
   smoke는 수동 조립).
5. run FSM seam: 정상 경로가 running을 거치지 않고 dispatch-ready→completed 직행, engine이
   run/job terminal 전이를 직접 기록 (bridge 보고 ④2).
6. opus 검증이 지적한 minor 커버리지 공백들(front-door dispatch e2e·no-assembly refusal·
   legacy-read 라벨 2종) — 전부 task 등록됨.

## Domain lens

이 라운드는 correctness-critical 인프라(트랜잭션 store, 분산 잠금 상당의 fencing, process
supervision, 인수 무결성)다. 리뷰 관점: ⑴ ADR-0002의 "correctness는 fencing+CAS" 원칙이
모듈 경계를 넘어 일관 적용되는가 — 특히 여러 모듈이 package-private surface를 조합한 지점
(observe·cancel·bridge)에서 우회로가 생기지 않았는가 ⑵ fail-closed 선택들이 실제 운영에서
견딜 수 있는가(과도한 refusal이 harness 사용성을 죽이는 지점) ⑶ 15개 병렬-순차 병합이
남긴 계약 간 상호작용 결함(한 기체의 가정이 다른 기체 병합으로 깨진 사례 — 0400↔fixture
충돌 2건은 잡았지만 더 있는가).

## Response wanted

Start the reply with this block (replace values; key case/order/spacing and a Markdown fence are
optional; extra keys are preserved). Echo the `Reviewing` target, alone or as a 12–40 hex
`base-target` range, and copy the request digest exactly; missing/damaged values stay unknown, and
no model/target means ordinary prose:
```text
model: codex:gpt-5.6-sol
effort: high
review-target: 885a7ad311d3aca063628f78053503e8c21b767f
request-digest: sha256:a6fad9c6b51246bb40e68d897a3cd2f776c1554fd099992d5c5c6d16b75841d4
```

Major / critical issues only. For each: a concrete failure mechanism and where you confirmed it.
Separate confirmed findings, open domain questions, and residual risks from unavailable
GPU / data / environment.
