# Review Request — 2026-07-18-generation-binding

The reviewer has the repository via git. This is a domain/code review — 이 repo의 도메인은 플러그인 하네스 자체이므로 아래 변경의 코드·설계 타당성을 본다. **carrier-lanes-fixes 재검토(CHANGES REQUESTED, major 4)의 3차 라운드다** — 당신의 4개 지적이 전부 해소되었는지가 핵심 질문이다.

- Project / Branch: waystone / dev
- Reviewing: 44a4b77db4e614b23721bfd601ab5aa4b96f6c65   (diff against 4c042031af9fe1722676de8bbe41fccba5464b30)

## What changed and why

직전 회신의 major 4건(JW-GPT-004 잔여 A/B·005·006·Q1 잔여)을 4개 lane으로 해소했다:

1. **binding schema v2 (JW-GPT-006 + 004-B)** — digest-capable binding은 `waystone-round-request-binding-2`로 발행되고 `narrative_digest`·`rendered_request_digest`가 필수(어느 하나라도 부재/무효 = corrupt). v1은 genuine legacy 읽기 전용 — **digest-capability의 앵커는 sidecar 밖**: round id 날짜가 2026-07-18보다 이후면 v1은 corrupt(schema 다운그레이드+digest 제거 2-필드 수술 차단), same-day 이전의 0.10.0 정품 v1은 보호. 비실재 달력 날짜는 packet·PR 리더 양쪽에서 corrupt. publication 게이트·freeze는 재렌더를 stored rendered digest와 대조하고 검증된 bytes를 그대로 게시(live template/exposure drift·request.md 변조 거부). `round close`는 신규 round의 mint 날짜를 검증(기존 round의 익일 재close는 허용). improve는 PR-mode에서도 request binding v2를 join해 digest·provenance 보존.
2. **프로브 증명 runtime 결속 (Q1 잔여)** — 마커가 versioned JSON fingerprint 계약: host identity(Linux `/etc/machine-id` 정규형 32-hex non-zero / macOS IOPlatformUUID UUID-검증), resolved codex 실행 파일 경로+stat(size·mtime_ns), `--version` stdout(stderr는 진단 기록 전용 — 동적 stderr 래퍼가 위임을 깨지 않음), platform/kernel, sandbox 호출 계약 라벨+관측 가능한 호스트 상태(Linux LSM), worktree cache mount(device/fsid/ro). **exact-match일 때만 프로브 생략**, 불일치는 축별 안내 후 재프로브, 획득 실패·sentinel은 fail-closed. probe·runner·verifier·--version 전부 resolved 절대경로로 실행. 테스트 스위트는 codex 부재 환경(CI-동등)에서 green.
3. **reprepare 원자성 (JW-GPT-005)** — 재-prepare가 새 binding을 선발행해 구 feedback을 먼저 무효화한 뒤 request·narrative를 갱신 — 시퀀스 어느 지점에서 죽어도 구 binding+구 feedback이 완료로 남지 않는다(RED: 양 지점 강제 종료). pending은 디스크 request·narrative가 최신 binding에서 재현되는지 확인.
4. **reply request-digest 에코 (JW-GPT-004-A)** — request가 자기 rendered digest를 노출(sentinel로 렌더→해시→스플라이스, 표시 라인 변조는 게이트가 거부), 회신 구조화 헤더의 `request-digest` 에코가 도장의 근거. echo-era(v2) 라운드에서 에코 부재 회신은 완료 불가(복사 가능한 digest를 인쇄하지 않는 출처 지시 안내) — ingest-time 도장 폴백은 legacy(v1) 라운드 한정+no-echo provenance. receipt는 에코가 명명하는 generation으로 일관 도장(라운드 불변 sidecar 조회, stale/미상 구분), 판독은 읽기 시점에 최신 binding과 재대조(복원된 generation은 자동 회복).

각 lane은 매 attempt마다 호스트 스위트+ruff 실측을, 설계 회전에는 raw codex 적대 리뷰(xhigh)를 통과해 인수됐다(1번 5회전·2번 4회전·4번 3회전·3번 1회전). 전 회전의 기각 사유·반박·잔여 처분은 delegation record의 verdict artifact에 남아 있다.

## Read these first

1. `scripts/review.py` — `read_round_request_binding`(v1/v2 판별·날짜 앵커) / `_render_review_request`(sentinel digest 노출) / `parse_review_reply_header`(request-digest) / ingest의 에코 도장·폴백 경계 / `pending_reviews` 재현성 확인
2. `scripts/delegate.py` — `_codex_runner_fingerprint` / `_codex_runner_marker_recorded` / resolved 경로 실행 통일
3. `scripts/round.py` — mint-date 검증(`_round_has_existing_closeout` 게이트)
4. `scripts/improve.py` — v2 digest·receipt 필드 보존
5. `docs/reviews/2026-07-18-carrier-lanes-fixes-feedback.md` — 당신의 원 지적(대조용)

## Claims to attack

1. 어떤 로컬 단일-파일 편집(digest strip·schema 다운그레이드 포함)으로도 2026-07-18 이후 라운드가 리뷰 없이 완료로 판정될 수 없다.
2. 회신이 실제로 검토한 request generation과 다른 generation을 완료시킬 수 없다 — 지연 회신·재-prepare 경합·에코 누락 전부에서.
3. reprepare 시퀀스의 어느 crash 지점도 완료 상태를 위조하지 않고, 복구(재실행) 가능하다.
4. 전파된(커밋·복사·공유된) 프로브 증명이 다른 머신/런타임의 프로브를 생략시키지 못한다 — fingerprint 어느 축의 드리프트도 재프로브를 유발한다.
5. 위 보장의 실패 방향은 전부 fail-closed(추가 프로브/정직한 pending/게시 거부)다 — fail-open 경로가 없다.

## Evidence already produced (mine — inspect, don't trust)

| Claim | Command / artifact | My reading | Where it lives |
|---|---|---|---|
| 전체 무회귀 | `uv run scripts/tests/run_tests.py` | 748→777 green(lane별 병합 후 재실측) + ruff clean | PROGRESS `2026-07-18-generation-binding` Gates |
| CI-동등 | codex 부재 PATH에서 전체 스위트 | 777 OK (1 skip: 기존 node 의존) | 동 Gates 항목 |
| RED-first | 각 delegation record `delegate_report.verification` | 신규 계약 전건 사전 rc=1 재현 | `.waystone/delegations/20260718T*/artifact/contract.yaml` (미커밋 로컬 티어 — 요청 시 발췌) |
| 회전별 기각·반박 근거 | verdict artifacts | 발견 심각도가 회전마다 단조 수렴 | 동 record `artifact/verdict-1.json` |

## Known weak spots

1. **전환일 유한 잔여** — 2026-07-18 이전·당일 라운드(고정 집합)는 0.11 도구로 재-prepare된 v2 binding을 v1로 되돌리는 2-필드 수술이 여전히 legacy로 읽힌다. 새 라운드는 영원히 비해당. 코드 주석 문서화, 역사 라운드 정착(chore/pre-header-feedback-settlement)으로 이관.
2. **정적 shim 은닉** — stderr로만 버전을 내는 래퍼가 stdout 배너·stat을 보존한 채 하부 codex를 교체하면 비탐지(주석 문서화된 내재 한계 — 등가 축의 결정론과 상충).
3. **역사 라운드 3건 영구 pending** — 0.10 구조화 헤더 이전 feedback(기존 부채, 정착 task).

## Domain lens

직전과 동일: 신뢰 표면의 fail-direction 일관성 — fail-open(리뷰 없는 완료·거짓 published·프로브 생략)을 찾으면 그것이 major다. 이번 라운드는 특히 **"완료"라는 판정이 어떤 증거 사슬로 지탱되는가**(request generation 정체성 → 회신 증언 → receipt → 읽기 시점 재계산)를 본다.

## Out of scope

`dev_docs/`, 직전 tip(4c04203) 이전 이력, 이 문서를 만든 워크플로 절차, 문서화된 유한 잔여의 재발견(위 Known weak spots — 새 공격 경로가 아니면).

## Response wanted

Start the reply with this block (replace values; key case/order/spacing and a Markdown fence are
optional; extra keys are preserved). Echo the `Reviewing` target, alone or as a 12–40 hex
`base-target` range; missing/damaged values stay unknown, and no model/target means ordinary prose:
```text
model: <model-id>
effort: <effort>
review-target: 44a4b77db4e614b23721bfd601ab5aa4b96f6c65
```

Major / critical issues only. For each: a concrete failure mechanism and where you confirmed it. Separate confirmed findings, open domain questions, and residual risks from unavailable environment. 직전 회신의 4건 각각에 대해 resolved / still-broken / new-concern 판정을 명시해달라.
