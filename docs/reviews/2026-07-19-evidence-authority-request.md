# Review Request — 2026-07-19-evidence-authority

The reviewer has the repository via git. This is a domain/code review — 이 repo의 도메인은 플러그인 하네스 자체이므로 아래 변경의 코드·설계 타당성을 본다. **generation-binding 3차 리뷰(CHANGES REQUESTED, major 4: JW-GPT-007~010)의 4차 라운드다** — 당신의 4개 지적이 전부 해소되었는지가 핵심 질문이다.

- Project / Branch: waystone / dev
- Reviewing: 2e0f1fbe9a9d0c2cdc52d4da919f617c148d9d06   (diff against 44a4b77db4e614b23721bfd601ab5aa4b96f6c65)

## What changed and why

3차 회신의 major 4건을 4개 lane으로 해소했다. 관통 주제는 당신의 표현대로 "완료 판정의 증거 사슬" — 권위를 가변 로컬 상태에서 불변·재파생 가능한 원천으로 옮겼다:

1. **receipt 읽기 권위 (JW-GPT-007)** — 완료 판정은 이제 `reply-metadata-json` cache를 신뢰하지 않는다. 읽기 경로가 verbatim reviewer body를 재파싱(bounded, CRLF 포함 정확한 byte 산술)하고, body가 선언한 `request-digest`를 라운드의 불변 request sidecar generation들에 resolve하며, cache/body 불일치는 corrupt-pending이다. legacy(no-echo) 경로의 coverage도 body(에코 부재)+binding v1-여부에서 재도출 — cache 키 추가 편집으로 역사 receipt를 승격할 수 없다. 손상은 구분된 taxonomy(envelope 손상/cache-body 불일치/named sidecar 부재 — narrative 축 포함 정직한 unknown)로 격리되고, 파일시스템에 닿는 모든 값(round id·request 파일명)은 glob 도달 전에 검증된다 — 한 손상 receipt가 pending/improve/overlay 투영을 중단시키지 못한다. overlay도 재파생 경로와 digest verdict를 공유한다(stale 회신을 recognized로 계상하지 않음).
2. **PR cycle generation 결속 (JW-GPT-008)** — `waystone-review-cycle` marker와 freeze sidecar가 digest 필수 **v2 schema**로 승격되어 `rendered_request_digest`를 명명한다(freeze가 이미 검증한 값과 단일 원천). 같은 cycle의 conflict 판정에 digest가 참여해 fail-closed. improve·`ingest_round_binding`의 PR 경로는 "latest request"가 아니라 cycle 증거가 명명한 sidecar를 조회 — freeze되지 않은 재-prepare generation이 이전 cycle의 provenance로 출력될 수 없다. GitHub marker 단독으로 exact generation 복구 가능(로컬 sidecar 부재는 정직한 unknown). v1 증거는 legacy 라벨 읽기 전용, v1/v2 혼재는 위양성 digest conflict가 아니라 정직한 version-skew 조건. cycle 번호는 신뢰 operator marker만 계상.
3. **round mint 앵커 (JW-GPT-009)** — round 기존성 판정에서 mutable `PROGRESS.md` heading이 제거되어 **검증된 immutable round exposure만** 인정된다. 문서 한 줄 편집으로 임의 과거-dated round를 mint해 v1 legacy 창을 재개하는 경로가 폐쇄됐다 — legacy-eligible 집합은 다시 유한·고정. 정당한 익일 재close(exposure 보유 round)는 무회귀.
4. **probe proof 실행 principal 결속 (JW-GPT-010)** — fingerprint에 effective UID/GID·supplementary groups(획득 실패 fail-closed), codex config root 정체성(CODEX_HOME/~/.codex resolve+stat, 부재 정직 기록), Linux best-effort process context(/proc/self/status의 Seccomp·NoNewPrivs·CapEff, /proc/self/attr/current)가 추가됐다 — 공유 checkout의 타 사용자/설정이 marker에 적중하지 못한다. 관측 불가 축은 명시적 not-observed로 기록되고, **not-observed는 상태 동등으로 대조**된다: 동일 not-observed는 재사용 허용(macOS에서 probe-once 유지), observed↔not-observed 비대칭 전이는 재프로브(관측 저하 공격은 marker가 observed라 비대칭 유지 — 안전).

각 lane은 매 attempt 실측과 설계 회전의 raw codex 적대 리뷰(xhigh)를 통과해 인수됐다(007: 3회전·008: 2회전·009: 1회전·010: 2회전). 전 회전의 기각·반박 근거는 delegation verdict artifacts에 있다.

## Read these first

1. `scripts/review.py` — `read_feedback_reply_metadata`(body 재파생·taxonomy) / PR freeze v2 schema·skew 판정 / `next_cycle_number` operator 필터
2. `scripts/round.py` — `_round_has_existing_closeout`(exposure 단독)
3. `scripts/delegate.py` — `_codex_runner_fingerprint`(principal·config root·process context) / reuse의 상태 동등 대조
4. `scripts/overlay.py`·`scripts/improve.py` — 투영 패리티(격리·digest verdict·명명 조회)
5. `docs/reviews/2026-07-18-generation-binding-feedback.md` — 당신의 원 지적(대조용)

## Claims to attack

1. 완료 판정에 이르는 어떤 값도 가변 로컬 cache 단독에서 오지 않는다 — 전부 verbatim body, 불변 sidecar, 또는 읽기 시점 재계산에서 파생된다.
2. 한 파일의 어떤 손상/편집도 (a) 완료를 위조하지 못하고 (b) 다른 라운드의 투영을 중단시키지 못한다.
3. PR cycle의 durable 증거는 게시된 exact generation만 명명한다 — 혼합 버전 호스트에서도 위양성 conflict 없이 정직하게 동작한다.
4. legacy-eligible round 집합은 불변 exposure로만 정의되며 어떤 tracked/mutable 편집으로도 확장 불가하다.
5. 프로브 증명은 checkout·machine·principal·runtime 축의 exact-match에서만 재사용되고, 관측 불가는 재사용 확대가 아니라 상태 동등으로만 작동한다.

## Evidence already produced (mine — inspect, don't trust)

| Claim | Command / artifact | My reading | Where it lives |
|---|---|---|---|
| 전체 무회귀 | `uv run scripts/tests/run_tests.py` | 777→804 green(lane별 병합 후 재실측) + ruff clean | PROGRESS `2026-07-19-evidence-authority` Gates |
| RED-first | 각 delegation record `delegate_report.verification` | 신규 계약 전건 사전 rc=1 재현(007은 6항목 일괄 RED 포함) | `.waystone/delegations/20260718T1*/artifact/contract.yaml` |
| 회전별 기각·반박 | verdict artifacts | 심각도 단조 수렴, 반박·위양 근거 명시 | 동 record `artifact/verdict-1.json` |

## Known weak spots

1. **위협모델 경계 미판정** — 컨테이너/namespace 심층 축(namespace-상대 UID 구분), 로컬 단일-파일 변조의 강한 변형(receipt를 append-only 이벤트/원격 canonical store로) 채택 여부는 `decision/trust-threat-model-boundary`로 사용자 ruling 대기. 현 라운드는 확립 원칙의 연장선(재파생·불변 앵커·상태 동등)까지만 하드닝했다.
2. **정적 shim 은닉·전환일 유한 잔여** — 직전 라운드에서 문서화된 그대로(재지적 불요).
3. **역사 라운드 3건 영구 pending** — 기존 부채, 정착 task 대기.

## Domain lens

직전과 동일 — 증거 사슬의 fail-direction. 이번엔 특히 **혼합 버전/혼합 머신 상태에서의 정직성**(v1/v2 skew, not-observed 동등, marker 단독 복구)이 위양성 차단(가짜 conflict·영구 재프로브·무한 pending)과 위음성 차단(위조 완료) 사이에서 올바른 쪽으로 넘어지는지를 본다.

## Out of scope

`dev_docs/`, 직전 tip(44a4b77) 이전 이력, 워크플로 절차, 문서화된 잔여의 재발견(새 진입 경로가 아니면), decision/trust-threat-model-boundary에 위양된 강한 변형들.

## Response wanted

Start the reply with this block (replace values; key case/order/spacing and a Markdown fence are
optional; extra keys are preserved). Echo the `Reviewing` target, alone or as a 12–40 hex
`base-target` range; missing/damaged values stay unknown, and no model/target means ordinary prose:
```text
model: <model-id>
effort: <effort>
review-target: 2e0f1fbe9a9d0c2cdc52d4da919f617c148d9d06
```

Major / critical issues only. For each: a concrete failure mechanism and where you confirmed it. Separate confirmed findings, open domain questions, and residual risks from unavailable environment. 직전 회신의 4건 각각에 대해 resolved / still-broken / new-concern 판정을 명시해달라.
