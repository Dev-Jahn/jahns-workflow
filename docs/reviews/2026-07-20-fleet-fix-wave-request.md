# Review Request — 2026-07-20-fleet-fix-wave

The reviewer has the repository via git. This is a domain/code review, not a workflow audit —
keep the waystone harness out of scope unless asked.

- Project: waystone
- Branch: dev
- Reviewer: chatgpt:gpt-5.6-pro
- Reviewing: 197b2cfa643f16188111e68a2c2f2255efd481c7   (diff against f0f6f23add0c71adad2d2cb64d8bd6149db08e14)

<!-- Keep the Reviewing field on exactly one line with the literal spacing shown above. -->

## What changed and why

병렬 fleet 라운드다. 대기 중이던 하네스 결함 7건과 구명 잔재 청산을 커밋-고정 worktree 9기(codex, ultra)로 동시 착수해 순차 squash 머지했고, 같은 wave에서 M0 exit 적대 리뷰(read-only codex)를 돌려 finding 11건을 각각 독립 opus verifier로 반증 검증했다. 코드 변경의 공통 성격: 정직성 강등(모르면 모른다고 말한다 — shallow ancestry unverifiable, probe hostname 진단 강등), fail-closed 차단(linked worktree registry mutation, reclose generation-1 부재), 검증 능력 준비(delegate worktree uv pre-warm), 구명 계약 폐기(JW_REPORT→WAYSTONE_REPORT, WS-GPT). M0 exit는 검증 후 blocker 2/major 4/minor 5로 확정됐고 main 권고는 "보류 — blocker 2건 폐쇄 후 재심"이다.

## Read these first

- `docs/meta/agent-reports-2026-07-20/m0-exit-adjudication.md` — finding별 verifier 판정표와 처분(등록 task 매핑)
- `docs/meta/agent-reports-2026-07-20/wave-manifest.md` — 로스터·머지 순서·hot-file 구획 분할
- `PROGRESS.md`의 `2026-07-20-fleet-fix-wave` 절 — 커밋별 요약과 게이트 증거 포인터
- 개별 구현 보고서(같은 디렉터리) — 각 기의 VERIFIED/NOT-RUN 헤더가 실행된 검증의 전량이다
- `scripts/delegate.py`의 env_prep 구획과 `scripts/tests/run_tests.py.lock` — 이번 wave의 가장 큰 동작 변경

## Claims to attack

1. **env-prep의 오프라인 보장 범위**: "prepared cache 이후 runner의 offline gate만 보장"이라는 경계 설정이 ADR-0012의 preflight 취지를 실제로 충족하는가, 아니면 최초 prep의 네트워크 의존이 같은 결함을 한 단계 미룬 것인가.
2. **probe proof schema v2→v3 1회 재프로브**: "silent 재해석 금지"의 대가로 전 머신 1회 재프로브를 택했다 — 이 migration 정책이 기록된 v2 marker의 신뢰 의미를 바꾸는 다른 경로(예: v2 위조)를 열지 않는가.
3. **misroute guard의 커버리지**: mutation만 거부하고 list/show의 lazy migration은 남겼다 — 이 잔여가 실사고를 재발시킬 수 있는 경로인가, ADR-0011 full 구현까지 수용 가능한 경계인가.
4. **rename의 호환 삭제**: old-name migration 호환 폐기와 테스트 6건 삭제가 "마이그레이션 호환 불요" 지시의 정당한 적용인가, 지시 범위를 넘은 삭제가 섞였는가.
5. **M0 exit 강등 판정**: CDX-2를 blocker→minor로 내린 근거(porting-ledger = 닫힌 특성화 manifest)가 리뷰어의 원래 우려(M1-A가 유지할 경계의 닫힘)를 실제로 해소하는가. main이 자기 산출물(M0)을 옹호하는 방향으로 기운 판정은 없는가.
6. **reclose 수리의 완전성**: generation 1 결속이 이 라운드 자체의 close(재close 아님)에도 올바른 base(f0f6f23)를 만들었는가.

## Evidence already produced (mine — inspect, don't trust)

- 머지별 표적 게이트 rc=0 ×7과 rename 머지 트리 full gate 833 tests rc=0 — 명령 원문과 rc는 각 보고서 VERIFIED 헤더와 PROGRESS 절에 있다.
- RED-first 증거: ancestry·reclose·env-prep·misroute 보고서에 수정 전 rc=1 재현 기록.
- env-prep의 오프라인 재현: 임시 HTTP index로 lock 생성 → index 종료·삭제 → UV_OFFLINE=1에서 suite+ruff rc=0.
- rename acceptance: live 표면 rg 잔재 0(rc=1), 보존 이력 245건 분류표.
- verifier 반증 기록: adjudication 문서의 finding별 EVIDENCE(파일:라인).

## Known weak spots

- **verifier 독립성의 한계**: finding 검증 opus 11기는 내(main)가 브리핑했다 — 반증 조건은 리뷰어가 명시한 것을 썼지만, "특히 확인할 것" 유도문이 판정을 기울였을 가능성은 남는다. CDX-2·7·9 강등이 특히 그 의심 대상이다.
- **baseline drift**: 이번 wave로 dev 테스트가 828→833(신규 +10, 구명 삭제 -6, 계약 개정 1). porting-ledger는 baseline pin이라 유효하지만 M1-A 게이트 운용 규칙(증분 취급)은 미정 — CDX-3 task에 위임했다.
- **raw codex exec 우회**: 이번 wave는 delegate 하네스 대신 raw 레시피를 썼다(수리 대상이 그 하네스라서). 위임 exposure 기록이 없으므로 이 라운드의 implementer 실행 증거는 보고서·커밋뿐이다.
- **profile verifier 바인딩과의 불일치**: profile은 verifier=codex(위임 결과 검증)인데 finding 검증을 opus로 했다 — 표면이 다르다고 판단했지만 profile에 그 구분이 성문화돼 있지 않다.
- settlement 분석은 결정 준비물이지 검증된 설계가 아니다 — marker 구현 시 별도 적대 검증이 필요하다.

## Domain lens

개발 운영 하네스(Claude Code+Codex 플러그인)다. 이 라운드의 리뷰 가치는 두 축이다: ① 수리들이 하네스의 자기 신뢰 계약(fail-closed, 정직 강등, 권위 단일성)을 강화했는가 약화했는가 — 특히 delegate env_prep이 새로 만든 .waystone-uv-cache namespace와 lockfile이 새 권위 표면이 되지 않는지. ② M0 exit 판정 절차 자체의 건전성 — 내부 적대 리뷰 + per-finding 반증이 외부 리뷰(당신)의 대체가 아니라 전처리가 되도록, 강등 판정의 근거를 특히 의심해 달라.

## Response wanted

Start the reply with this block (replace values; key case/order/spacing and a Markdown fence are
optional; extra keys are preserved). Echo the `Reviewing` target, alone or as a 12–40 hex
`base-target` range, and copy the request digest exactly; missing/damaged values stay unknown, and
no model/target means ordinary prose:
```text
model: chatgpt:gpt-5.6-pro
effort: high
review-target: 197b2cfa643f16188111e68a2c2f2255efd481c7
request-digest: sha256:59648bf7f61dcf1abe669dcd42bb6168346dfb0082894b934f0279f81349d0cb
```

Major / critical issues only. For each: a concrete failure mechanism and where you confirmed it.
Separate confirmed findings, open domain questions, and residual risks from unavailable
GPU / data / environment.
