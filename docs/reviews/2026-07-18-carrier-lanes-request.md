# Review Request — 2026-07-18-carrier-lanes

The reviewer has the repository via git. This is a domain/code review — 이 repo의 도메인은 플러그인 하네스 자체이므로 아래 변경의 코드·설계 타당성을 본다.

- Project / Branch: waystone / dev
- Reviewing: e9e5c140947375f3a55cc9b8c2c681ff6c458da4   (diff against 84ad6a799b38d74d95e490aebcd69fc8c1b8c41e)

## What changed and why

fix-wave 리뷰가 남긴 대기 큐 전량을 3-lane 병렬 체인으로 해소하고, CC Workflow를 deterministic-workflow의 캐리어로 편입한 라운드다. 큰 묶음 여섯:

1. **publication gate 직접 결속 재설계** — ancestry/topology 추론(merge-parent 형태, first-parent 체인, HEAD 재해석)을 전부 삭제하고 단일 명제만 증명: round의 LATEST binding이 가리키는 closeout SHA가 고정된 remote-tracking ref에 포함되고, 그 원격 트리가 request+binding sidecar를 로컬과 byte-identical하게 보유한다. 종전 게이트는 committed-but-unpushed packet을 통과시키는 실 구멍(RED 고정)이 있었다.
2. **review 표면 결정론화** — packet 렌더링을 round exposure 기반 script 렌더링으로 전환(서사만 모델 입력), freeze는 디스크 request 파일을 재신뢰하지 않고 exposure+보존된 서사에서 재렌더. 회신 헤더 파서는 헤더 블록 한정 단일 UTF-8 decode 규칙으로 단순화. pending review는 저장 없이 순수 파생(`waystone review pending`). lookalike 검증은 마커 정규화로 우회 봉쇄.
3. **codex-companion 전면 제거** — verify를 모든 호스트에서 단일 `codex exec` 직결로 통일(ruling 2026-07-17). broker 발견/정리·companion transport 삭제, legacy profile 값은 deprecation notice와 함께 정규화. verifier transport는 timeout(부분 stderr+경과 예산)·signal(번호+이름)·빈 출력(무산출 명시 실패 클래스)을 각각 정직 보고.
4. **delegate 실행 표면 경화** — done 아닌 의존이 있으면 위임 거부(dep gate), sandbox 프리플라이트 프로브 격리+`delegation.codex_runner_verified` config로 1회 실행, hook matrix 양 모드 mutation-kill 커버리지.
5. **deterministic-workflow carrier (ADR-0001, 2026-07-18 사용자 비준)** — 3축 분리(execution=manifest 절차 / host carrier / leaf runner). `delegate plan <ids> --json`(불변 fan-out manifest, corrupt fail-closed), `run --expect-packet-sha/--expect-profile/--carrier/--carrier-instance/--json-events`(NDJSON), `status --json`, 캐리어 템플릿 `delegate-fanout.workflow.js`(manifest 전용 인자, overlap 시 강제 직렬, 집계 비권위). carrier 부재 호스트는 fail-loud, ultra는 codex 전용.
6. **release 경화 + 정리** — main이 어느 워크트리에든 체크아웃돼 있으면 릴리스 거부, env-allowlist smoke, TMPDIR guard, fail-loud manifest 열거. over-engineering 감사 batch 1 prune, 미초기화 root의 상태 생성을 lock chokepoint에서 차단, triage 쓰기 규율(마커 섹션+읽기 시점 재계산), README 표면 staleness 정정+docs gate 확장.

## Read these first

1. `scripts/review.py` — 직접 결속 publication gate, 결정론 packet 렌더링, 헤더 파서, pending 파생 (이번 라운드 최다 변경)
2. `scripts/delegate.py` — companion 제거, dep gate, 프로브 격리/1회 gate, transport 정직성, `plan --json`/`--carrier`/`--json-events`
3. `templates/hosts/claude-code/delegate-fanout.workflow.js` + `docs/adr/ADR-0001-deterministic-workflow-carrier.md` — 캐리어 계약과 그 근거
4. `release-to-main.sh` — checked-out-main 거부와 경화 잔여
5. `scripts/waystone.py` — statusline 파생 1줄과 consent 설치

## Claims to attack

1. committed-but-unpushed(또는 부분 push·심링크·round 재사용·stale upstream) packet은 새 publication gate를 통과할 수 없다 — 종전 5종 우회가 전부 닫혔고, 직접 결속으로 새 우회 표면이 생기지 않았다.
2. companion 제거 후 어떤 코드 경로도 companion/broker transport로 폴백하지 않으며, legacy 값 정규화는 수용 시 반드시 가시적 deprecation notice를 남긴다.
3. `delegate run`은 done 아닌 의존을 가진 task를 어떤 경로(직접 호출·manifest 경유)로도 실행하지 않는다.
4. 동일 exposure+동일 서사 입력이면 packet 출력은 바이트 동일하고, prepare 이후 디스크 request 편집은 freeze가 공개하는 표면에 도달할 수 없다.
5. `waystone review pending`은 reviews 디렉토리에서 순수 파생되며, 최신 round binding과 회신의 review-target 대조 없이는 어떤 회신도 pending을 해소하지 못한다.
6. 캐리어 manifest 없이(free-form 인자로) fan-out 템플릿을 구동할 수 없고, deterministic-workflow binding은 effort 명시가 없으면 `delegate plan`이 fail-loud하며, `ultra`는 Claude 캐리어 매핑에서 거부된다.
7. verifier transport에서 어떤 실패 모드(timeout·signal·빈/공백 출력·rc0 빈 성공)도 성공이나 정상 무변경으로 위장되지 않는다.
8. statusline은 read-only·무락이며 corrupt config/registry에서도 한 줄 토큰으로 강등될 뿐 프롬프트 라인을 깨지 않는다.

## Evidence already produced (mine — inspect, don't trust)

| Claim | Command / artifact | My reading | Where it lives |
|---|---|---|---|
| 1 | PublicationGate 계열 테스트 (실 bare-remote, 우회 5종 RED 재현 → 직접 결속 GREEN) | 우회 전부 폐쇄 | 커밋 3598aea·dc16916 |
| 3 | dep-gate 테스트 (미완 의존 거부) | 거부 확인 | 커밋 c4a89aa |
| 4 | 결정론 packet 3차 계약 (lookalike 정규화·freeze 재렌더·reclose 순서) | 바이트 동일·재신뢰 차단 | 커밋 bf991a3 |
| 5·8 | pending 파생·statusline 강등 테스트 | 파생 전용·강등 정직 | 커밋 9fbf838·cff8576 |
| 6 | §4.1–4.3 테스트 클래스 (plan manifest·expect/carrier 결속·status rows) + validateOnly | manifest 전용·fail-loud | 커밋 14b0cff, run_tests.py §4 |
| 7 | transport 실패 모드별 테스트 (timeout/signal/빈 출력/rc0) | 각각 구분 보고 | 커밋 0ea791b·a0599aa |
| 전체 | 전체 스위트 600→719 green (112s, 2026-07-18 2회) + ruff F401/F841 clean | green | git log 84ad6a7..e9e5c14, PROGRESS §2026-07-18-carrier-lanes |

## Known weak spots

- **carrier의 라이브 fan-out 미실시** — 실 CC Workflow 엔진으로 multi-lane 위임을 실제 구동한 기록이 아직 없다(validateOnly+시나리오 matrix 수준). 다음 릴리스 후 라이브 검증 예정.
- **carrier feat 3건의 인수 경로** — 위임 verdict 경로가 아니라 사전 외부 설계 리뷰("Architecture approved") + 테스트 + 표면 실측으로 인수됐다. 이 리뷰가 사실상 첫 독립 코드 검증이다.
- verifier binding은 TEMP UNBOUND 지속(릴리스판 하네스에 수정 미반영) — 이 라운드 위임 검증은 전부 raw codex 적대 리뷰 + agent_checks 경로였다.
- publication gate의 "byte-identical sidecar" 대조가 원격 트리 읽기 방식에 의존한다 — 원격 조작 위협모델(force-push, ref 바꿔치기)은 pinned ref 신뢰 안에서만 방어된다.

## Domain lens

게이트 우회 저항성, provenance 정직성(귀속·carrier 과장 금지, 파생 증거의 추측 금지), 상태 격리(worktree≠project), shell 안전성. `docs/review-profile.md` 없음 — 이 절이 이번 라운드의 렌즈다.

## Out of scope

`dev_docs/`(로컬 설계 노트), 직전 라운드 tip(84ad6a79) 이전 이력, 이 문서를 만든 워크플로 절차.

## Response wanted

Start the reply with this block (replace values; key case/order/spacing and a Markdown fence are
optional; extra keys are preserved). Echo the `Reviewing` target, alone or as a 12–40 hex
`base-target` range; missing/damaged values stay unknown, and no model/target means ordinary prose:
```text
model: <model-id>
effort: <effort>
review-target: e9e5c140947375f3a55cc9b8c2c681ff6c458da4
```

Major / critical issues only. For each: a concrete failure mechanism and where you confirmed it. Separate confirmed findings, open domain questions, and residual risks from unavailable environment.
