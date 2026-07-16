# Review Request — 2026-07-16-fix-wave

The reviewer has the repository via git. This is a domain/code review — 이 repo의 도메인은 플러그인 하네스 자체이므로 아래 변경의 코드·설계 타당성을 본다.

- Project / Branch: waystone / dev
- Reviewing: 84ad6a799b38d74d95e490aebcd69fc8c1b8c41e   (diff against c8ec816c6745e67efd73b05b56c711238b7cc550)

## What changed and why

직전 라운드 리뷰의 REAL major 2건과 세 현장 보고(사용자 적발, bw2/newton 요구, spark1 사고)를 병렬 위임으로 해소한 라운드다. 여덟 묶음:

1. **release 안전화** — `release-to-main.sh`가 현 워킹트리를 staging으로 쓰며 ignored 로컬 파일을 삭제하던 것을, temp-index 투영 + positive SHIP manifest(ruling) + `commit-tree`/CAS로 재작성.
2. **verifier hermetic화** — verifier 세션에서 모든 waystone hook이 no-op (ruling: 전 hook hermetic). 공용 `verifier_guard.sh`, record-local uv cache.
3. **packet publication 게이트** — push된 HEAD 트리에 round의 request+binding 실존을 검증(실 bare-remote RED-first), 엄격 Reviewing 파서, bind 단계 분리.
4. **effort 어휘** — ultra 추가(codex CLI 실 argv 계약) 후, pro는 실측(웹 gpt-5.6-sol pro가 `model: gpt-5.6-pro / effort: high`로 자기선언)에 따라 제거.
5. **parked 상태** — 6번째 task 상태(의도적 보류): 선정·주입 제외, blocked와 구별 렌더링, archive 비대상.
6. **runner 환경 실패 감지** — rc0+빈patch+report부재+쓰기실패 stderr 조합을 fail-loud 분류, 동일 sandbox 조건 프리플라이트 프로브, `show --failure` 진단 힌트 (spark1 AppArmor/bwrap 사고).
7. **구조화 회신 헤더** — 이 문서 하단의 key:value 블록이 그 결과물. ingest가 robust 파싱해 identity·결속 증거로 기록, 레거시 무사이드카는 정직한 unevaluable, 강제 재ingest의 identity 정정 일관성(구형식 행 포함).
8. **review-target prefix 12+ hex 강제** — 6-hex 매칭의 약함(steno 7-hex 충돌 실측)을 적대 리뷰가 지적, main-session이 같은 착지에서 상향.

## Read these first

1. `release-to-main.sh` — temp-index 투영·manifest·CAS 전체 로직
2. `hooks/scripts/verifier_guard.sh` + `hooks/hooks.json` — hermetic 가드의 적용 방식
3. `scripts/review.py` — publication 게이트, 엄격 Reviewing 파서, 회신 헤더 파서/리더 (이번 라운드 최다 변경)
4. `scripts/delegate.py` — 빈-성공 분류·프리플라이트 프로브·effort 검증
5. `templates/review-request.md` — 회신 헤더 블록 계약 (이 문서가 그 소비자)

## Claims to attack

1. 성공한 release는 호출자 워킹트리·ignored 로컬 파일을 바이트 하나도 바꾸지 않고, 실패 주입 시 시작 상태가 완전 보존된다.
2. `WAYSTONE_VERIFIER_SESSION=1`에서 어떤 waystone hook도 출력·deny·상태 변경을 하지 않으며, 정상 세션 동작은 불변이다.
3. 미추적·부분 커밋된 packet은 publication 게이트를 통과할 수 없다 (알려진 edge 우회 5건은 fix/publication-gate-bypasses로 기록됨 — 그 외 새 우회를 찾아보라).
4. rc0 빈-성공 분류는 정직한 무변경 결과(report 동반)를 절대 오분류하지 않는다.
5. 이 문서 하단 블록을 채운 회신은 ingest에서 정확한 identity·결속 증거로 기록되고, 블록 없는 회신은 unknown으로 정직 처리된다.
6. parked는 종결도 착수 후보도 아니다 — 선정·archive·의존충족 어디서도 새 나가지 않는다.

## Evidence already produced (mine — inspect, don't trust)

| Claim | Command / artifact | My reading | Where it lives |
|---|---|---|---|
| 1 | ReleaseToMainTests 4계약(실 temp repo, RED-first) + 구현자·리뷰어 이중 zero-diff 투영 대조 | ignored byte-identical, 실패 원상, manifest≡구방식 | 커밋 adfccf5, 각 위임 record의 verdict-1.json |
| 2 | hook-matrix 실 subprocess 테스트 + 픽스처 실측(가드/정상 차등) | 6 hook 전부 hermetic, 정상 deny 불변 | 커밋 76bd515 |
| 3 | PacketPublicationTests(실 bare-remote, 미추적/부분/완전 push) | 일반 경로 거부·수용 정확 | 커밋 594b8ad |
| 4 | DelegateRunTests conjunctive 게이트 + report 단락 | 무변경+report 보호 확인 | 커밋 a0599aa |
| 5 | IngestTests round-trip·관대 파싱·unknown 계약 32건 | 헤더 파싱·결속·정정 일관 | 커밋 02bb199·84ad6a7 |
| 전체 | 전체 스위트 558→600 + ruff, 각 apply 후 dev 게이트 재실행 | green | git log c8ec816..84ad6a7 |

## Known weak spots

- 위임별 적대 리뷰가 남긴 잔여가 major 5건으로 registry에 기록돼 있다: publication 게이트 edge 우회 5종(심링크·round 재사용·stale upstream 등), companion transport의 effort 폐기, delegate run의 의존 상태 미검사, 프리플라이트 프로브의 편집 잔류 가능성(출처 오염), 회신 헤더 리더의 32KiB 경계·improve 저장값 무재검. 이들이 실제로 위험 순위가 맞는지, 더 급한 것이 있는지 의견 환영.
- 실 호스트 라이프사이클(설치본 hook 발화, guard 전파)은 다음 릴리스 후 라이브 검증 예정 — 현재는 subprocess 픽스처 수준.
- RED-first는 대부분 구현자 보고 근거(마지막 헤더 건은 실행 기록 부재, 리뷰어의 반사실 확인으로 대체).

## Domain lens

shell 안전성(비차단·인용·stdin), 상태 격리(worktree≠project, verifier hermetic), 게이트 우회 저항성, 파생 증거의 정직성(추측·합성 금지).

## Out of scope

`dev_docs/`(로컬 설계 노트), 직전 라운드(c8ec816c) 이전 이력, 이 문서를 만든 워크플로 절차.

## Response wanted

Start the reply with this block (replace values; key case/order/spacing and a Markdown fence are
optional; extra keys are preserved). Echo the `Reviewing` target, alone or as a 12–40 hex
`base-target` range; missing/damaged values stay unknown, and no model/target means ordinary prose:
```text
model: <model-id>
effort: <effort>
review-target: 84ad6a799b38d74d95e490aebcd69fc8c1b8c41e
```

Major / critical issues only. For each: a concrete failure mechanism and where you confirmed it. Separate confirmed findings, open domain questions, and residual risks from unavailable environment.
