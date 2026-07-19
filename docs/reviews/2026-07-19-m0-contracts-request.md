# Review Request — 2026-07-19-m0-contracts

The reviewer has the repository via git. This is a domain/code review, not a workflow audit —
keep the waystone harness out of scope unless asked.

- Project: waystone
- Branch: dev
- Reviewer: chatgpt:gpt-5.6-pro
- Reviewing: fd7ee42b4b457a81870e20d8b63a291a8743a742   (diff against 2e06f717cda633d34c3e2a6b68147c9409836659)

<!-- Keep the Reviewing field on exactly one line with the literal spacing shown above. -->

# Review Request — 2026-07-19-residual-after-0.12

이것은 코드 리뷰가 아니라 **설계 공백 리뷰**다. 질문은 하나다: 2026-07-19 하루의 실제 운영에서
드러난 실패들 중, **0.12 리팩터 계획(r5)이 설계대로 전부 구현되고 확정된 ruling 6건과 ADR 8종이
모두 적용되어도 여전히 남는 것은 무엇이며, 그것들을 어떻게 다루는 것이 옳은가?**

## What changed and why

이 라운드는 **"수리 실패 + 설계 확정"이라는 비대칭 결과**를 냈고, 그래서 "설계가 무엇을 못
잡는가"를 묻기 좋은 시점이 됐다.

- round-5(JW-GPT-011~013) 착지 → 0.11.1 릴리스 → marketplace·설치 하네스 동기화.
- round-6: 5차 리뷰의 major 2건(JW-GPT-014·015)을 **각 4회전씩 총 8회 위임 시도 후 중단**.
  **병합 0건, dev 코드는 하루 종일 한 줄도 바뀌지 않았다**(스위트 828 불변). 014 attempt-4는
  구조적으로 옳은 방향(단일 chokepoint + 원자적 관측 레코드)이었으나 정상 축약형 v2 marker에서
  모든 online 명령을 차단하는 위양성을 유입시켜, 병합하면 원 결함보다 나빠지는 상태였다.
- 그 대신 확정된 것: 계획서 r3→r5 개정(외부 리뷰 2·3차 반영 + 사용자 지시로 실행 관측을 1급
  범위로 편입, **E-08**·**E-09** 신설), **ruling 6건 전부 확정**, **ADR-0002~0008 착지**,
  `docs/invariants.md`(I-01~12 + E-01~09) 확정, **baseline/0.12-refactor 동결**.
- 그 과정에서 하네스 결함 3건이 새로 발굴되고 조정자(main session)의 실수 4건이 기록됐다.

아래 8건은 내가 스스로 검토해 **0.12로 해결되지 않는다고 판단한 것들**이며, 그 판단 자체가 틀렸을
수 있다. 선별 기준은 "계획이 설계대로 전부 구현되어도 여전히 발생하는가"다.

> **diff 창 주의**: 이 라운드의 실제 창은 `4f4b90d..fd7ee42`다. 헤더의 diff base가 `2e06f71`로
> 표기되면 그것은 같은 라운드의 중간 커밋이다 — 재close 시 base 표기가 밀리는 알려진 버그
> (`fix/reclose-diff-base-drift`, minor). **이번 라운드는 코드 변경 0건이며 전부 문서·레지스트리다.**

## Read these first

1. `dev_docs/0.12.0-refactor-plan.md` (r5) — 특히 §0 성공의 정의, §3-4·§3-6·§3-8~§3-10, §4
   불변조건 표, §5-2·§5-4·§5-5, §6 M0-A/M1-B/M2, §9 ruling, §12 반영 기록
2. `docs/adr/ADR-0002`~`ADR-0008` · `docs/invariants.md`
3. `docs/known-issues.md` — baseline 동결 시점의 미해결 major 2건과 영향 범위
4. `PROGRESS.md`의 `2026-07-19-supersession-attribution-attempts`와
   `2026-07-19-evidence-authority-fixes` 두 항목
5. `waystone task show` — fix/merge-observed-demotion-persistence,
   fix/ingest-malformed-foreign-freeze-skip (둘 다 blocked, notes에 회전별 진단)

## Claims to attack

아래 8개는 전부 **"이것은 0.12 이후에도 남는다"**는 내 주장이다. 각각에 대해 *실제로 남는가 /
이미 설계로 해결되는데 내가 놓쳤는가(그렇다면 계획서 어느 절인가) / 애초에 문제가 아닌가*를
판정해달라.

### R-1. 조정자가 작성하는 acceptance 조항의 품질을 검사하는 기계가 없다

**무슨 일이 있었나.** round-6의 기각 사유 12건 중 **3건의 근본 원인이 내가 쓴 조항**이었다.

1. *"improve와 동일한 fallback owner 파생 규칙으로 일원화하라"* — improve의 규칙이 안전한지
   **검증하지 않고 기준으로 삼았다.** 구현자는 지시대로 했고, 결과적으로 안전하지 않은 쪽으로
   통일시킬 뻔했다(적대 리뷰가 잡음).
2. *"기록되지 않은 supersession이 offline에서 explicit으로 되살아나는 경로가 남지 않는다"* —
   reviews 디렉터리가 통째로 쓰기 불가면 **원리적으로 달성 불가능한 요구**였다. 리뷰어가
   "미충족"이라고 정확히 판정했지만, 그게 구현 결함인지 조항 결함인지는 내가 코드를 읽고서야
   구분됐다.
3. *"식별 가능한 **모든** v2 contract를 demote하고"* — cycle 범위를 안 적었다. 구현자가 문자
   그대로 구현해 **무관한 과거 라운드의 유효한 증거를 손상시키는 결함을 직접 유발**했다.

**왜 0.12가 못 잡나.** 계획의 핵심 철학은 "harness-derived prompt를 최소화하고 목적은 모델
외부의 script와 workflow 설계로 달성한다"이다. 그런데 acceptance 조항은 **정의상 모델이 자유
문장으로 쓰는 것**이고, 계획 어디에도 그 문장이 (a) 달성 가능한지 (b) 범위가 정확한지 (c) 검증
안 된 것을 기준으로 삼지 않았는지를 확인하는 단계가 없다. RED-first 요구와 적대 리뷰가 있지만
**둘 다 사후**다 — 이번엔 회전 8번을 쓰고 나서야 드러났다.

**부분 완화의 실측.** 조항을 "이렇게 고쳐라"(구현 지시)에서 **"이 성질이 성립해야 한다"**(속성
기술)로 바꾼 회전에서 두 lane 모두 구조적 해법으로 전환했다(014→단일 chokepoint,
015→unattributable 1급 상태). 즉 **작성 양식이 결과를 바꿨다**. 그러나 이건 내가 그때 그렇게
쓰기로 마음먹었기 때문이지 기계가 강제한 게 아니다.

**묻고 싶은 것.** dispatch 전에 조항 자체를 심사하는 값싼 단계(예: 조항만 읽는 독립 critic,
또는 "달성 불가능/범위 미기재/미검증 기준" 3개 축의 체크)를 두는 게 맞나? 아니면 그건 또 하나의
모델 의존 단계라 계획 철학에 역행하나? 속성 기술을 **양식으로 강제**하는 것(자유 문장 금지)은
현실적인가?

---

### R-2. 엔진 밖에서 조정자가 손으로 하는 행위는 여전히 조용히 실패한다

**무슨 일이 있었나.** ADR 6종을 lane worktree에 적용한 뒤 `git merge --squash task/adr-state`를
실행했다. **명령은 성공했고 오류도 경고도 없었다.** 그런데 실제로는 아무것도 병합되지 않았다 —
worktree의 index에만 적용하고 커밋을 안 해서 브랜치에 커밋이 0개였기 때문이다. 내가 습관적으로
`ls docs/adr/`를 실행하지 않았다면 **"ADR 6종 병합 완료"라고 보고하고 넘어갔을 것이다.**

**왜 0.12가 부분적으로만 잡나.** ADR-0002의 `observed` 단계가 정확히 이 문제를 다룬다 —
*"명령이 성공을 보고했다가 아니라 권위 채널에서 기대한 외부 상태를 다시 읽었다"*. patch
integration도 expected parent/tree 재도출이 계약이다. **그러나 그건 엔진이 수행하는 action에만
적용된다.** 이번 병합은 내가 main session에서 손으로 친 것이고, 계획은 "조정자가 엔진 밖에서
직접 하는 행위"를 모델링하지 않는다. 그리고 그런 행위는 계속 존재한다 — 계획 자체가 하네스
버그 시 raw 우회를 보존하고(ADR-0000), 오늘도 8회전 중 상당수를 내가 손으로 검증했다.

**묻고 싶은 것.** 이 공백을 좁히는 게 맞나, 아니면 "엔진 밖 행위는 원래 보장 대상이 아니다"로
정직하게 선을 긋는 게 맞나? 좁힌다면 어떤 형태인가 — 조정자용 얇은 확인 도우미(`waystone verify
merged <ref>` 류)? 아니면 조정자가 손으로 하는 일 자체를 줄이는 방향(더 많은 것을 엔진 action으로)?
후자는 executor 경계(ADR-0004)의 `user` 범주를 넓히는 셈인데, 그러면 "사용자가 알 필요 없어야
한다"는 지향점과 충돌하지 않나?

---

### R-3. cwd 기반 root 해석은 0.12에서 오히려 위험해질 수 있다

**무슨 일이 있었나.** `waystone task set`을 실행했는데 셸에 잔류한 `cd` 때문에 **linked
worktree 안에서 실행**됐다. 그쪽 `tasks.yaml`에 기록되고 pre-0.9 migration까지 유발해
`.waystone/profile.yml`을 seed했다. 오류는 없었다. **같은 사고가 이 세션에서 2회** 발생했고,
1회차 후 "registry 조작은 main repo에서만"이라고 규칙까지 적어뒀는데 내가 반복했다.
(`fix/registry-worktree-misroute-guard` major로 등록)

**왜 0.12가 못 잡나 — 그리고 악화될 수 있나.** 계획은 root 해석 규칙을 전혀 다루지 않는다.
그런데 0.12는 실행 상태를 `.waystone/state.db`로 옮기고(ruling ④, ADR-0007), DB 경로는 resolved
project root 아래다. **linked worktree에서 명령이 실행되면 그 worktree의 `.waystone/state.db`를
열거나 만들게 된다.** 지금은 YAML 한 파일이 오염되고 눈으로 보이지만, 그때는 **runtime 상태가
통째로 다른 DB에 쌓이고** 원본 프로젝트의 run은 그것을 보지 못한다. 실패가 더 조용하고 더 깊다.

**묻고 싶은 것.** ADR-0007에 "resolved root가 linked worktree면 거부 또는 명시적 확인"을 추가하는
게 맞나? 아니면 root 해석 자체를 cwd에서 떼어내야 하나(예: 명시적 `--root` 필수, 또는 main
worktree로 정규화)? 후자는 UX를 해치는데, 이 위험과 어떻게 저울질하나?

---

### R-4. 자율 라운드에 "언제 그만둘 것인가"의 규칙이 없다

**무슨 일이 있었나.** round-6에서 두 lane이 각각 4회전을 돌았다. 014는 major 2→2→3→**4**로
**증가**했고 변경 규모는 149→908줄로 불었다. attempt-4는 구조적으로 옳은 방향이었지만 정상
입력을 차단하는 위양성을 유입시켰다 — 병합하면 원 결함보다 나빠지는 상태였다. **내가 ad hoc으로
"여기서 멈춘다"고 판단**했고, 그 판단의 근거는 회전 수가 아니라 궤적(폐쇄율 < 유입율)이었다.

**왜 0.12가 못 잡나.** 계획의 M2는 closure 고정, 최대 task 수, budget 제한을 두지만 **"이 lane이
수렴하지 않고 있다"를 감지하거나 중단하는 규칙이 없다.** 그런데 계획의 목표는 자율 round이고,
사용자 지시사항에도 "round skill을 자율 실행 flow로"가 고려사항으로 들어 있다. **자율 실행 중에
사용자가 자리에 없다면, 이 판단은 누가 하는가?** 무한히 재시도하면 예산을 태우고, 고정 횟수로
자르면 정당한 3회전(round-5의 011이 3회전에 인수됐다)을 죽인다.

**묻고 싶은 것.** 발산 감지를 계약으로 만들 수 있나? 후보 신호: 회전당 신규 major 수의 추세,
변경 규모의 증가, 동일 조항의 반복 미충족, 신규 결함 유입률. 이걸 엔진이 판정하게 하는 게
맞나(결정론적 임계값), 아니면 `waiting_user(reason=lane-not-converging)`로 올려서 사람에게
넘기는 게 맞나? 후자면 "질문 0" 예산과 어떻게 조화하나 — 이건 질문이 아니라 보고인가?

---

### R-5. 게이트 green이 결함 부재를 뜻하지 않는다는 문제는 그대로다

**무슨 일이 있었나.** 기각된 attempt들은 **전부 게이트가 green이었다** — 828~840 tests OK,
ruff clean, 매번 내가 직접 재실측했다. 결함을 잡은 것은 언제나 **적대 리뷰**였다. 즉 이번 라운드에서
테스트는 회귀를 막았지만 **새 결함은 하나도 잡지 못했다.**

**왜 0.12가 못 잡나.** 계획은 fault-injection을 1급 테스트로 올리고 불변조건별 traceability
matrix를 두지만, 그건 **알려진 불변조건**에 대한 것이다. round-6의 결함들은 전부 "그 조항을
쓸 때는 존재를 몰랐던 변형"이었다(conflict 동시 성립, base-policy fallback 경로, 축약형 v2
marker, 이중 glob 매칭…). 그리고 계획에서 **적대 리뷰는 run engine 밖의 별도 라운드 활동**이다 —
M2의 "independent verification"은 *"조항이 충족됐는가"*를 보지 *"이 설계가 틀렸는가"*를 보지
않는다.

**묻고 싶은 것.** 적대적 설계 검증을 run 안의 1급 단계로 올리는 게 맞나? 그러면 자율 run의
비용이 크게 오르고, 계획이 경계한 "복잡성 재유입"이 될 수 있다. 아니면 라운드 수준에 두되 **어떤
변경이 적대 리뷰를 필수로 요구하는지**를 계약으로 정하는 게 맞나(예: 신뢰 표면 touch 시 필수)?

---

### R-6. 리뷰 증거의 파일명-신원 모호성은 0.12에서도 남는다 — 내 계획서의 주장이 과했다

**무슨 일이 있었나.** JW-GPT-015는 round id가 `-freeze-`를 포함할 수 있어 sidecar 파일명 귀속이
다의적이라는 문제다. 4회전이 전부 이 공간에서 실패했다(prefix 충돌 → phantom owner → 빈 cycle →
단조성 위반 → 이중 glob).

**내 계획서의 주장.** M0-A와 M1-B 수용 기준에 *"015 부류 — 신원이 파일명이 아니라 store 키라
귀속 다의성이 성립 불가"*라고 적었다.

**그런데 이 주장은 과하다.** 계획 §2-1과 §5-2는 **리뷰 증거(요청/회신/binding sidecar)를
git-tracked 파일로 유지**한다고 못박고 있다 — 머신 간 공유가 git으로 일어나야 하기 때문이다.
즉 store 키가 신원을 대체하는 것은 **runtime record**이고, **리뷰 증거는 여전히 파일명이 신원**이다.
따라서 015의 부류는 0.12에서 **자동으로 소멸하지 않는다.** 나는 대화 중 이 점을 스스로 정정했지만
계획서 본문의 주장은 그대로 남아 있다.

**묻고 싶은 것.** 셋 중 어느 쪽인가? (a) 리뷰 증거에도 store 키 신원을 도입하고 git 파일은
export/projection으로 격하 — 그러면 §2-1의 "git이 권위"와 충돌한다. (b) 파일명 모호성 자체를
제거 — round id에 구분자 금지, 또는 파일명 escaping, 또는 owner manifest 도입. (c) ruling ②
(우발적 손상만 방어)에 기대어 "정상 운영에서 생기는 prefix 충돌만 막고 나머지는 수용 잔여"로
범위를 좁힌다. 나는 (b)+(c) 조합이 맞다고 보는데, (b)는 기존 파일과의 호환을 어떻게 다루나?

---

### R-7. 위임 러너가 자기 검증을 수행할 수 없는 상태가 설계상 방치돼 있다

**무슨 일이 있었나.** 이 세션의 **위임 8회 전부**에서 러너가 자기 worktree에서 전체 스위트와
ruff를 돌리지 못했다(`env_prep: none-detected`, worktree-local uv 캐시에 pyyaml·ruff 부재).
러너들은 이를 정직하게 `limitations`로 보고하고 escalation까지 남겼다. 015 attempt-1은 **RED
단계조차 실행하지 못했다.** 매번 내가 대신 실측해서 메웠다. (`fix/delegate-env-prep-uv-cache`
major로 등록)

**왜 0.12가 못 잡나.** 계획 M2는 fleet 실측 규칙으로 "env 정규화"를 언급하지만, **"worker의
환경이 프로젝트의 검증 명령을 실행할 수 있어야 한다"는 계약은 어디에도 없다.** 그런데 계획의
독립 검증(E-07, M2-3)은 worker/verifier가 실제로 검증을 **수행할 수 있다**는 것을 전제한다.
전제가 깨지면 독립 검증은 조용히 "조정자 단독 검증"으로 퇴화한다 — 이번처럼 조정자가 성실하면
메워지지만, 자율 run에서는 메울 사람이 없다.

**묻고 싶은 것.** worker 환경의 검증 능력을 **dispatch 전 preflight로 확인**하고 불가하면 typed
refusal하는 게 맞나? 아니면 검증을 worker에서 떼어내 엔진이 직접 수행하는 게 맞나(ADR-0004의
`engine` 범주 확대)? 후자면 "독립 검증"의 독립성이 약해지지 않나?

---

### R-8. E-09의 범위가 좁다 — ambient 값 일반이 아니라 파일시스템 메타데이터만 금지한다

**무슨 일이 있었나.** 같은 계열 실수가 **세 번** 나왔다.

1. round-5 JW-GPT-013 — probe가 `~/.codex` **디렉터리 stat**을 신뢰 축으로 사용 → 내용 digest로 교체
2. round-6 015 attempt-3 — 단조성을 **파일 mtime** 순서로 판정 → 내가 기각
3. round-6 운영 중 발견 — probe fingerprint의 `machine` 축이 **hostname**(`Mac.local`)이라
   **네트워크를 옮기면 증명이 무효화**된다. 같은 marker 안에 안정적인 하드웨어 UUID가 이미
   있는데도. (`fix/probe-machine-axis-hostname-drift` minor)

**왜 0.12가 부분적으로만 잡나.** 3번을 겪고 E-09를 신설했는데, 문구가
*"mtime/ctime/inode/디렉터리 stat/열거 순서"*로 **파일시스템 메타데이터에 한정**돼 있다.
hostname은 파일시스템 메타데이터가 아니다. 즉 **내가 방금 겪은 세 번째 사례가 내가 방금 만든
불변조건에 걸리지 않는다.**

**묻고 싶은 것.** E-09를 *"신원·귀속·권위 판정은 그 대상이 변하지 않았는데도 변할 수 있는
ambient 환경값에 결속하지 않는다"*로 일반화하는 게 맞나? 일반화하면 경계가 흐려지는 위험이
있다 — 예컨대 process identity(ADR-0003)는 boot id·pid를 쓰는데 그것도 ambient다. 무엇이
정당한 ambient 사용이고 무엇이 아닌가를 어떻게 가르나?

---


## Evidence already produced (mine — inspect, don't trust)

| Claim | 근거 | 어디에 있나 |
|---|---|---|
| 8회전 전부 게이트 green이었고 결함은 적대 리뷰만 잡았다 (R-5) | attempt별 스위트 828~840 OK + ruff clean, 매번 main이 재실측 | PROGRESS 해당 항목 Gates, delegation record verdict |
| 조항 결함 3건이 기각을 유발했다 (R-1) | 각 discard의 `--reason`에 조항 결함 여부를 명시 기록 | `waystone delegate` 레코드, task notes |
| 위임 8회 전부에서 러너가 자기 게이트를 못 돌렸다 (R-7) | 각 contract.yaml의 `limitations`·`escalations` | `.waystone/delegations/*/artifact/contract.yaml` |
| 014·015가 PR-mode 표면에 한정된다 (R-6 전제) | review.mode=packet · freeze sidecar 0개 · ingest가 packet 분기에서 조기 반환 | `docs/known-issues.md` 실측 표 |
| 불변조건 문구가 계획서와 일치한다 | 계획서 §4 ↔ invariants.md 기계 대조: 9건 전부 존재, 문구 표류 0 | 이 라운드 마감 로그 |

## Known weak spots

1. **R-6은 자기 지적이다.** 계획서 M0-A·M1-B에 "015 부류는 신원이 store 키라 소멸"이라고 적었는데,
   §2-1이 리뷰 증거를 git-tracked 파일로 유지한다고 못박고 있으므로 **자동 소멸하지 않는다.**
   대화 중 정정했으나 본문 주장은 그대로다. **이 정정 자체가 맞는지 확인이 필요하다.**
2. **R-4의 발산 판정은 ad hoc이었다.** "회전당 신규 major 수 증가 + 변경 규모 증가"를 근거로
   내가 멈췄지만, 임계값도 계약도 없었다. round-5의 011은 3회전에 정상 인수됐으므로 단순
   횟수 제한은 정당한 수렴을 죽인다.
3. **R-8의 일반화는 경계가 흐리다.** ambient 값 일반을 금지하면 ADR-0003이 쓰는
   boot id·pid도 걸린다. 정당한 ambient 사용과 아닌 것을 가르는 기준이 아직 없다.
4. 8건 선별은 내 판단이며, **내가 "해결된다"고 분류해 제외한 것 중에 남는 것이 있을 수 있다**
   (예: 로그 침묵을 죽음으로 오판한 사고는 E-08·§3-8로 해결된다고 보고 제외했다).

## Domain lens

설계 공백 리뷰다. 코드 결함이 아니라 **계약의 빈칸**을 찾아달라.

**메타 질문 — 8건을 관통하는 관찰.** 위 8건을 관통하는 관찰이 있다. **0.12 계획은 "엔진이 하는 일"을 매우 촘촘하게 설계했지만,
"조정자(모델)가 하는 일"은 거의 설계하지 않았다.** 그런데 이번 라운드의 실패 원인 중 상당수가
조정자 쪽에 있었다 — 조항 작성(R-1), 엔진 밖 수동 조작(R-2, R-3), 중단 판단(R-4).

이건 의도된 것일 수도 있다. 사용자의 불변 지향점 ②는 *"모델에 주입되는 harness-derived prompt를
최소화하고 목적 달성은 모델 외부의 script와 workflow 설계로 수행한다"*이므로, 조정자를 규율로
묶는 것은 명시적으로 피하려는 방향이다. **그렇다면 조정자 실수는 "설계로 막을 대상"이 아니라
"발생을 전제하고 회수 가능하게 만들 대상"인가?** 그 경우 필요한 것은 규율이 아니라 **되돌리기
쉬움**과 **조용한 실패의 제거**일 텐데, 계획이 그 방향으로 충분한가?


**회신에서 바라는 것**: 8건 각각의 판정(남음/이미 해결됨+절 지적/문제 아님), 남는 것들에 대한
처분 권고(0.12 범위 편입 / 0.13+ 이월 / "설계로 막지 않고 수용"으로 명시), 메타 질문에 대한 견해,
그리고 **내 판단 중 틀린 것**의 지적 — 특히 R-6.

범위 밖: 014·015의 구체적 수리 방법(M1 이월 확정) · 이미 확정된 ruling 6건의 재론 · 0.12 계획의
전면 재설계 · 코드 레벨 결함 탐색(이번 라운드는 코드 변경 0건).

## Response wanted

Start the reply with this block (replace values; key case/order/spacing and a Markdown fence are
optional; extra keys are preserved). Echo the `Reviewing` target, alone or as a 12–40 hex
`base-target` range, and copy the request digest exactly; missing/damaged values stay unknown, and
no model/target means ordinary prose:
```text
model: chatgpt:gpt-5.6-pro
effort: high
review-target: fd7ee42b4b457a81870e20d8b63a291a8743a742
request-digest: sha256:4f2d033dad550a585500b2b42fd91f8400bf16786de5efecd88938e5fb282a8c
```

Major / critical issues only. For each: a concrete failure mechanism and where you confirmed it.
Separate confirmed findings, open domain questions, and residual risks from unavailable
GPU / data / environment.
