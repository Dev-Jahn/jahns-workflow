# WAVE w0720 + w0720b + w3(리뷰) — 관제 manifest (main 세션 전용)

## W4 — 리뷰 수리 wave (base 81bd177, 2차 발사 = 승계 재발사)
**1차 발사 5기 격추** (09:10 네트워크/DNS 장애, codex 백엔드 단절 — 작업 결함 아님). w4-litter(bozndxbbb)만 생존 비행 중. 5기는 잔존 작업 감사·승계 지시(briefs/*-resume.md)를 붙여 재발사:
수확 완료 5 (8/9 task done): banw47bb7=w4-reader(dev b6bde56) · bhctnb8iw=w4-binding(dev 6298c3d) · b1foycw3x=w4-sunset(dev c1cfb6a, 207+208, 부수: MarkerTests HOME 격리) · b1cumna9t=w4-docs(dev 0ae2457, 203·204/PC-31·205) · btv18l8ev=w4-i10-v2(dev a6e9ea0, **WS-GPT-101 blocker 폐쇄** — pinned-debt 3중 고정+template SHA-256 oracle, 보고서 v1·v2 아카이브 스테이징됨).
비행 중 1: **bzq3hut10=w4-litter 3차** — 1차 생존기(bozndxbbb)가 실은 첫 응답도 못 받고 39분 스톨(UTC/KST 착오로 늦게 발견) → TaskStop 격추, worktree clean 확인, base a6e9ea0 재핀 후 신규 발사. 착지 시 마지막 수확 → wave 마감 시퀀스.
**w4-i10 NO-GO 인수됨** (bclc1ej47 v1 보고 = 현행 prompt가 status·milestone·round·anchor·routing_note 전달, main 독립 재현 완료) → ADR-0014 Amendment 2 **Addendum** 커밋(dev d95931b, push됨): 위반=known-debt 편입, 수리=fix/delegate-prompt-i10-surface-strip(M1-B, 등록됨), 특성화=pinned-debt 형태 재규정. **btv18l8ev=w4-i10 v2** (base d95931b 재핀, briefs/w4-i10-v2.md) 비행 중 — 보고서는 w4-i10-v2.md로. WS-GPT-101 blocker는 v2 테스트 착지로 폐쇄.
완료 상태: 리뷰 2건 ingest+triage 커밋(81bd177 push됨) · Amendment 2 착지(201·202 폐쇄, task done) · 11 task 등록(이월 2: env-prep digest=M1, 없음) · profile reviewer → codex:gpt-5.6-sol ultra(사용자 지시) · reviewer worktree 정리.
hot-file: review.py=binding 단독 · common.py detector 구획=sunset 단독 · tasks.py=litter 단독 · improve.py=reader 단독 · plan(M1-C 절=docs task1, M1-B fixture 절=docs task3) · promoted/matrix=docs 단독. 머지 순서 자유(구획 분리), run_tests.py는 전 기 클러스터 인접 규약.
w4 마감 후: full gate → 보고서 아카이브 → round close(2026-07-20-review-remediation) → **blocker 0 확인 → M1-A 착수 판정**(decision/m1a-start-approval).

## W3 triage 축적 (verifier 회신 도착분)
- 회신 2건 ingest 완료(verbatim): fleet-fix-wave(REJECT 1b/4M, WS-GPT-101~105) · ruling-execution(CHANGES REQUESTED 1b/7M, WS-GPT-201~208). 양쪽 다 "reviewer model mismatch" 경고(의도적 대체) — 다음 라운드 전 profile reviewer를 codex로 변경 예정.
- **main 인라인 검증 REAL 확정**: 105(단 현 HEAD서 이미 해소 — docsync가 수리, task 불요) · 201(ledger #473/510/516의 E-08 반-계약 분류가 증거 — Amendment "위반 0" 동시성립 불가) · 202(suite pinning 부재) · 203(plan M1-C legacy comparator 잔존 — 원문 확인) · 204(UninitializedRootGateTests 양쪽 부재 rc=1) · 205(matrix가 삭제된 MigrationV2Phase2Tests 4건 인용 + ADR-0013 row/의무 부재 rc=1)
- **opus verifier 회신**: 101 REAL(blocker 유지, 폐쇄는 저비용 — I-10 특성화 테스트 1개+bookkeeping 경계 1줄. 현 템플릿의 WAYSTONE_REPORT stanza는 허용 범위로 확정 필요) · 104 REAL(major-low: 21→0 재현 확정, 현 blast radius는 진단 표면+휴면 정책 경로. 수리 정제: dual-prefix는 improve._FINDING_ID_RE(아카이브 reader)만, review.FINDING_RE는 WS 유지, 실제 보존 파일 대상 회귀 테스트) · 102 REAL(**major→minor 강등**: 메커니즘 재현됐으나(위조 ruff rc=0) 동일 gap이 done task 결과에 명시 이월돼 있고(env/source digest 결속 = 비-범위), ADR-0012 digest 결속은 M1 target, 잔여 공격은 coordinator ambient env 장악 필요 = 마스터 경계 밖. 수리 = ruff 단독 hash-lock이 아니라 M1 VerificationPlan digest 결속에 편입) · 103 PARTIAL(**major→minor**: 파괴적 절반은 sunset이 해소(이동/삭제 코드 소멸 실측), 잔여 = 순수 read가 linked checkout에 .waystone/{.gitignore,lock} 생성 — 거부보다 먼저 발생함까지 재현. 수리 = need_root read 경로에서 canonical 정규화 또는 typed 거부를 lock 이전에) · 208 REAL(major 유지: fail-open 재현 — CONTROL 거부 True vs symlink ATTACK False, 구 0.11은 typed 거부했음 확인, ADR-0013:52 위반. 형제 helper들은 올바름 = 국소 불일치. 수리 = marker container가 real dir 아니면 container 자체를 offender로 + symlink/regular-file 테스트) · 207 REAL(major 유지 — 경계선상: 재현 확정(preserved 분기 profile → 조용한 False, plain root 동형은 typed 거부 = 비대칭), 구 0.11의 conflict 거부 테스트가 후계 없이 삭제됨, "정상 완료된 이관은 분기 profile을 만들 수 없다"는 논증으로 구현자 방어 반박. 수리 = 분기 시 profile을 offender로 → typed 거부, 동일-잔재 수용은 유지) · 206 대기
- 처리 방향 초안: [A] ADR-0014 Amendment 2(main 직접 설계): M1-A invariant 조건을 "pinned known-debt 대비 신규 위반 0"으로(debt 목록 = ledger E-08 반-계약 3건+#486 E-09), suite identity manifest pin(202), M1-A 성격 ruling(Q1: 순수 기계 단계 유지). [B] doc bird: plan M1-C supersession(203)+matrix HEAD 재생성/ADR-0013 의무 등록(205)+promoted reverse closure & PC-31 uninitialized-root(204)+I-10 특성화 테스트(101). [C] code bird: settlement binding alias fail-open(206). [D] code bird: sunset detector 2건(207 profile conflict+208 symlink container). [E] fleet 회신분: 102 ruff digest·103 linked read 잔여·104 dual-prefix reader — verifier 확정 후.

## W3 — packet 리뷰 처리 (사용자 위임: codex ultra가 외부 리뷰어 대체, 이후 전면 자율개발)
- bb5xjkd4k = rev-fleet: round 2026-07-20-fleet-fix-wave 리뷰 (worktree @197b2cf, 회신 → fleet/reports/reply-fleet-fix-wave.md, finding WS-GPT-101~)
- bqauvn9fl = rev-ruling: round 2026-07-20-ruling-execution 리뷰 (worktree @1f7d942, 회신 → reply-ruling-execution.md, WS-GPT-201~)
- 회신 처리 절차: 회신 파일 → /tmp/review.md 복사 → /waystone:review <round-id> ingest(verbatim+triage) → finding당 opus verifier 반증 → CONFIRMED 수리/등록 → 완료.
- **decision/m1a-start-approval**: 사용자 자율 위임 기록됨 — 두 리뷰 처리에서 미해소 blocker 0이면 main이 착수 판정. 착수 시: M1-A 분해(기계 분할, Amendment exit 3항) + PC 마일스톤 귀속표 + feat/review-runs-uuid-owner-directory M1-B 편입.

## WAVE-2 (w0720b) — ruling 집행 wave, base **8392d5a**, 발사 2026-07-20 오후
사용자 ruling: 2-a(marker)·3-삭제(집행됨)·4-통째삭제·**1-B**(합격기준 전환+git 기록 연속성 승격 원칙).
| bg id | worktree | task | 성격 |
|---|---|---|---|
| bns2vctxk | w0720b-settlement | chore/pre-header-feedback-settlement | 구현: marker 기계+원 3건, 추가 3건은 감사만 |
| bdqqyedox | w0720b-sunset | chore/migration-sunset | 구현: pre-0.9 기계 삭제→typed 거부 |
| boqgl5h6m | w0720b-threat | fix/m0-threat-model-completion (blocker) | ADR-0013 신규 |
| bhv32ru33 | w0720b-basis | docs/adr-m1a-acceptance-basis (blocker) | ADR-0014+promoted-contracts.md 초안 |
| b96c3t5xa | w0720b-manifest | fix/adr-0006-closeout-manifest-gaps | ADR-0006 amend |
| b5tioja7u | w0720b-runid | fix/run-id-grammar-unification | plan supersession+ADR-0005 note |
| bw0rr3h9i | w0720b-docsync | docs/m0-exit-review-sync | 사실 반영 6항목 |
hot-file: **plan 4분할**(threat=:613 / basis=:632-643 / runid=:190-193·:494 / docsync=:433·:479-492) ·
review.py=settlement 단독 · common.py=sunset 단독. 머지: 코드 2기 먼저(settlement→sunset), docs 이후 순차.
회수 후: basis의 promoted-contracts 초안은 **main 정독 인수 필수**(codex 제안일 뿐). threat·basis 착지+인수
= M0 exit 재심 조건 충족 → 재심 리뷰(경량) → M1-A. w0720b 마감 시 round close.
registry: m0-exit-verdict done(B)·settlement-method done·delegate-readme done(파일 삭제 f2bedea)·
migration-sunset 조건해제·grade-gate blocker dropped→docs/adr-m1a-acceptance-basis 등록.
Stop hook: install.hooks consent 기록+마커 활성화(이 프로젝트, 2026-07-20) — 기능 자체는 07-16 구현 완료였음.

---
# (이하 WAVE-1 기록)

## 진행 상태 (갱신: 회수 시마다)
- ✅ colorenv → dev 22ec0db (push·registry done·worktree 정리)
- ✅ settlement 분석 → 메모 회수·핵심사실 재검증·ruling 2건 대기 목록行
- ✅ ancestry → dev 2ddd8f8 (표적 61 rc=0, push·done·정리)
- ✅ probe duo → dev 340514e (표적 rc=0, push·task 2건 done·정리)
- ✅ m0-review 착지: **M0-exit FAIL 주장 (blocker 3/major 6/minor 2)** → opus verifier 11기 발사, ✅ reclose → dev caf1b34 (표적 75 rc=0, push·done·정리)
✅ verifier 11/11 완료 — **M0 exit 최종 판정표**: blocker 2 생존(CDX-1 threat model[공백 좁혀짐: env 전달·lease principal·permission/symlink fail-direction], CDX-3 등급 gate 실행불가[4세부 전부+내적모순]) · major 4 생존(CDX-4 015 보상 구현 미등록, CDX-5 manifest 계약 ADR간 충돌[멀티task·no-result·path grammar], CDX-6 run id 이중 canonical, CDX-8 stale needs-ruling) · minor 5(CDX-2·7·9·10·11 — blocker/major에서 강등 4 포함). **리뷰어 원판정 3/6/2 → 검증 후 2/4/5.**
✅ finding task 등록 완료: fix/m0-threat-model-completion(blocker) · fix/porting-ledger-grade-gate-executability(blocker) · feat/review-runs-uuid-owner-directory(major) · fix/adr-0006-closeout-manifest-gaps(major) · fix/run-id-grammar-unification(major) · docs/m0-exit-review-sync(major 번들: CDX-8+minor 5)
🛬 rename 착지·검수 완료(5커밋, live 표면 0, 보존 245건 분류표, 823 tests rc=0) — **최후 머지 대기** (env-prep 이후)
✅ misroute → dev 0c4ac61 (common.py 미접촉 — ancestry 충돌쌍 소멸. 표적 21 rc=0, push·done·정리. 잔여 gap: list/show read 정규화 = ADR-0011 M1 몫)
현재 회신 10 (CDX-5만 대기):
  - CDX-1 CONFIRMED(blocker 유지·범위 좁힘): threat model 산출물 자체는 미충족이나 E-03/ADR-0011/0007이 부분 흡수 — 실공백 = env 전달·lease principal·permission/symlink별 fail-direction. "흡수 명시+빠진 축 기록"으로 폐쇄 가능
  - CDX-3 CONFIRMED(blocker): 4개 세부 전부 생존. ledger 자체 판정 규칙(:26 "failure 결정 관측면")이 대안 해석을 봉쇄, 동형 refusal 테스트가 다른 곳선 diagnostic 등급 = 내적 모순까지
  - CDX-11 PARTIAL(minor 유지): 상단 6건 현재형+disposition 미역동기화 실재, 단 :186이 3-bucket 화해 명시라 영향 과장
  - CDX-7 PARTIAL(major→minor): 권위는 이미 확정·배치(projects.json=machine-tier F-06 done, profile 전이 권위=plan:448+F-01 M3) — 반증 조건 이미 충족. 잔여 = §5-2 표 back-reference nit, 기존 task로 흡수
  - CDX-4 CONFIRMED(major): 015 보상 구현(UUID owner dir writer/reader)이 어느 task acceptance에도 없음 — 지목된 vehicle(feat/review-artifact-addressing)은 docs-only로 이미 done
  - CDX-6 CONFIRMED(major): run id 문법 2개(계획 timestamp-slug-random vs ADR-0005/0009 UUIDv7) 모두 canonical 자칭, supersession 없음 — ADR-0005가 자기 권위 원천(§5-2)과 조용히 어긋남
  - CDX-8 CONFIRMED(major): ledger·matrix가 완료된 ruling 2건(#473/#486)을 needs-ruling으로 유지 — forward-reference 규약 없음
  - CDX-10 PARTIAL(→minor): matrix의 "ADR-0003 §3-9" anchor 오류만 생존; ADR-0012 Tasks 필드는 반증(정당 연결)
  - CDX-9 PARTIAL(major→minor): 문구 충돌 실재하나 ADR-0009가 이미 amend 경로로 supersede — 잔여는 plan §4 미역동기화 + invariants.md:4-5 stale 권위 포인터(E-04식 precedence 절 부재)
  - CDX-2 PARTIAL(blocker→minor): 핵심 부재 주장 반증 — porting-ledger가 SHA-pin된 닫힌 특성화 manifest이고 fixture는 run_tests.py 인라인(plan §2-5가 ledger+matrix를 특성화 산출물로 정의). 잔여 = I-10/E-04/E-08 특성화 공백(공개된 M1 이월) + gate/characterization-baseline task id 미등록(chore 2건으로 대체)
나머지 5 대기(1,3,5,7,11). m0-review worktree는 유지 중(정리 대기)
- 🛫 비행 중: misroute(b5x08hbwz) · env-prep(busy2es4n) · reclose(b61fz3unz) · rename(ba58ks38v — 최후 머지)
- ⚠ wave 관찰: porting-ledger는 baseline 7cfecd3의 run_tests.py(sha bd781a…)에 pin — 이번 wave 머지로 dev의 테스트 수 828→834+ drift (ledger는 baseline 특성화 문서라 정합이나, M1-A 게이트 운용 시 재조정 필요. round close 때 기록)

- base: **662f2e3** (dev tip, origin 동기화, clean) — 전 worktree 공통
- worktree 위치: `/Users/jahn/workspace/waystone/.claude/worktrees/w0720-<name>`
- 보고서: `<scratchpad>/fleet/reports/<task>.md`
- codex: `gpt-5.6-sol`, effort ultra, bypass sandbox, harness background

## 로스터

| # | worktree | branch | task | 성격 | 보고서 파일 |
|---|---|---|---|---|---|
| 1 | w0720-colorenv | task/w0720-colorenv | fix/hook-matrix-color-env (minor) | 구현 | hook-matrix-color-env.md |
| 2 | w0720-misroute | task/w0720-misroute | fix/registry-worktree-misroute-guard (major) | 구현 | registry-worktree-misroute-guard.md |
| 3 | w0720-env-prep | task/w0720-env-prep | fix/delegate-env-prep-uv-cache (major) | 구현 | delegate-env-prep-uv-cache.md |
| 4 | w0720-ancestry | task/w0720-ancestry | fix/shallow-ancestry-honesty (minor) | 구현 | shallow-ancestry-honesty.md |
| 5 | w0720-reclose | task/w0720-reclose | fix/reclose-diff-base-drift (minor) | 구현 | reclose-diff-base-drift.md |
| 6 | w0720-probe | task/w0720-probe | fix/probe-machine-axis-hostname-drift + fix/marker-diagnostics-polish (duo, minor×2) | 구현 | probe-duo.md |
| 7 | w0720-rename | task/w0720-rename | chore/legacy-name-residue (minor) | 구현·광폭 | legacy-name-residue.md |
| 8 | w0720-settlement | (detached) | chore/pre-header-feedback-settlement | read-only 분석 | pre-header-feedback-settlement.md |
| 9 | w0720-m0-review | (detached) | M0 exit 적대 리뷰 | read-only 리뷰 | m0-exit-review.md |

## background task ID (발사 2026-07-20, 전기 정상 기동)
bii8jzmf1=colorenv · b5x08hbwz=misroute · busy2es4n=env-prep · b2sjra3mn=ancestry ·
b61fz3unz=reclose · b6bve70ey=probe · ba58ks38v=rename · b1o0n3xhm=settlement · bk9tyrdke=m0-review
(output: /private/tmp/claude-501/-Users-jahn-workspace-waystone/0ce199b5-c513-485a-bf2b-c5bbd01945e9/tasks/<id>.output)

## hot-file 소유 구획
- `scripts/tests/run_tests.py`: 전 기 — 클러스터 인접 추가만, 말미 append 금지
- `scripts/common.py`: misroute(root 해석) / ancestry(:1580~1690 merge-base·temp ref)
- `scripts/delegate.py`: env-prep(:150~210, :690~710, :2107) / probe(:1040~1440) / rename(JW_REPORT 문자열, 최후)

## 머지 파이프라인 (통지 도착 순서대로, 단 제약 우선)
1. 도착 시: output tail + 보고서 헤더 + `git -C <wt> log --oneline 662f2e3..HEAD` + `diff --stat` 검수
2. main tree에서 `git merge --squash task/w0720-<n>` → 서술형 커밋(원 sha 병기) — cd 잔류 주의
3. 머지 후 표적 게이트 재실행(`env -u FORCE_COLOR uv run scripts/tests/run_tests.py`; FORCE_COLOR 세션이므로 colorenv 머지 전에는 full suite rc 해석 주의 — 기존 hook matrix 실패 1건은 기지 부채)
4. registry 갱신(task done + result 한 줄) — main tree cwd에서만
5. **rename(#7)은 항상 최후 머지**. misroute(#2)·ancestry(#4)는 common.py 충돌쌍 — 순차 머지. env-prep(#3)·probe(#6)는 delegate.py 충돌쌍 — 순차 머지.
6. wave 마감: full gate 1회 → 실패는 base 662f2e3 재현 여부로 부채/회귀 분리 → push → 보고서·synthesis repo 이관(docs/meta/agent-reports-2026-07-20/) → worktree/branch 일괄 정리 → /waystone:round

## 리뷰 회신 처리 (8·9)
- settlement 메모 → 옵션 검증 후 사용자 ruling 목록에 (비차단)
- m0-exit 리뷰 finding → finding당 opus verifier 1기로 반증 → CONFIRMED만 편입 (blocker/major면 M1-A 착수 보류 판단)

## 사용자 ruling 대기 목록 (비차단 수집)
- [ ] chore/migration-sunset: 모든 머신 0.11+ 이관 완료 확인 필요 — 확인 전 실행 불가 (이번 wave 제외 사유)
- [ ] chore/pre-header-feedback-settlement: 메모 도착·핵심 사실 main 재검증 완료. 권고 = Git-tracked archived-unverifiable marker(digest 결속·fail-closed). ruling ① 권고 채택 여부 ② 범위: 원 cohort 3건만 vs 현 HEAD 동종 추가 3건(carrier-lanes-fixes·generation-binding·evidence-authority) 개별 감사 후 포함
- [ ] dev_docs/delegate_readme.md 보존/삭제 (rename task는 건드리지 않음)
- [ ] M0 exit 판정 (리뷰 결과 + verifier 검증 후 제시)
