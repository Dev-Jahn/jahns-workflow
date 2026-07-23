<!-- waystone feedback: the body below is the reviewer reply VERBATIM (byte-exact copy via `waystone review ingest`) — do not edit it; a triage skeleton is appended beneath it. -->
round: 2026-07-23-013-review-closure
reviewer: chatgpt:gpt-5.6-pro
reviewer-effort: high
review-target: 3c411b2cba4ac6e757f768bb094aef737b4151b2
reply-metadata-json: {"metadata":{"effort":"high","model":"chatgpt:gpt-5.6-pro","request-digest":"sha256:d52a2b8c890bc466c941c0cdea83d6648e989ee4d7e363ee914ef8a3ce5526d0","review-target":"3c411b2cba4ac6e757f768bb094aef737b4151b2"},"narrative_digest":"sha256:b799f783dd28be1659899be6df2ed28c86f7f8f0381f9aeb4df69c8936ed6858","rendered_request_coverage_reason":null,"rendered_request_digest":"sha256:d52a2b8c890bc466c941c0cdea83d6648e989ee4d7e363ee914ef8a3ce5526d0","rendered_request_digest_matches":true}
ingested: 2026-07-23
source: /tmp/review.md
verbatim-bytes: 17633

---

```text
model: chatgpt:gpt-5.6-pro
effort: high
review-target: 3c411b2cba4ac6e757f768bb094aef737b4151b2
request-digest: sha256:d52a2b8c890bc466c941c0cdea83d6648e989ee4d7e363ee914ef8a3ce5526d0
```

# Review verdict — CHANGES REQUESTED

**Critical 0 / Major 3**

이번 closure round는 이전 리뷰의 표면적 지적사항을 그대로 패치한 수준이 아닙니다. 다음 변경은 실제 코드 계약으로 옮겨졌습니다.

* `VerifierEvidence`, `ReviewerEvidence`, `IntegrationDecision`이 별도 타입·artifact로 분리됨
* accepted-risks가 public promotion의 adversarial-review gate로 연결됨
* reject가 apply 이전의 별도 exact-tuple 판정 경로가 됨
* validation/disposition append와 materialize에서 authority를 다시 확인함
* semantic draft scaffold, canonical 4-role brief, 신규 release projection이 추가됨

이는 request가 설명한 closure 범위와 일치합니다.  방법론적 배경은 첨부된 Omniphysics realignment 기록과도 일관되지만, 이번 판정은 해당 방법론을 다시 평가하지 않고 지정된 trust-kernel 코드 경계만 대상으로 했습니다. 

그러나 **“typed evidence가 exact candidate에 결속되어 있다”는 것과 “그 판단 주체가 exact candidate를 실제로 보았다”는 것이 여전히 분리되어 있으며**, `execute_stage()`의 handler composition 경계도 published authority가 아니라 전달된 Python 객체를 신뢰합니다. Review disposition 역시 historical fact는 검증하지만 current project direction과의 일치는 검증하지 않습니다.

---

# Claims adjudication

| Claim                                                  | 판정                               |
| ------------------------------------------------------ | -------------------------------- |
| 1. Promote verifier/reviewer/decision의 실제 authority 분리 | **미폐쇄** — WS-GPT-023, WS-GPT-024 |
| 2. stale objective를 통한 finding materialization 차단      | **미폐쇄** — WS-GPT-025             |
| 3. Reject의 별도 exact-tuple 종결·apply 미실행                 | **승인**                           |
| 4. Candidate exact-object 검증의 worktree invariant 보존    | **좁은 의미에서 승인**                   |
| 5. Scaffold의 protocol-only 파생                          | **승인, major finding 없음**         |
| 6. Release projection 완결성과 legacy 제거                   | **정적 검토 기준 승인**                  |

## 승인된 부분

Reject는 integration decision 단계에서 accept와 동일한 tuple validator를 사용하되 expected outcome만 `REJECT`로 고정하고, 검증 직후 `_PromotionRejected`로 target apply 전에 빠져나갑니다. 이후 latest attempt는 completed, job/run은 failed로 종결됩니다.

Scaffold는 semantic draft의 필드를 exact-set으로 요구하고, ID·digest·binding·candidate/evaluation lineage 같은 protocol field만 현재 Git/store에서 계산합니다. 사용자 의미 필드는 `coordinator-summary`로 보존하며 누락 필드를 추측해 채우지 않습니다.   `/run` skill도 coordinator에게 semantic YAML만 작성하게 하고 digest나 lineage 계산을 요구하지 않습니다. 

Project Brief는 현재 `committed`이고, binding role fact는 canonical `coordinator·worker·verifier·reviewer` 4-role로 정렬됐습니다.

Release projection은 `waystone/` package를 포함하고 제거된 legacy script 여섯 개를 shipping manifest에서 제외했습니다. Projected runtime으로 project registration, brief check, status, typed run-start refusal, review help를 실행하는 smoke도 구성되어 있습니다.   Launcher가 자신의 설치 root를 Python import 우선순위로 사용하므로 smoke project의 dev package를 우연히 import하는 경로도 확인되지 않았습니다.  

---

# Confirmed findings

## WS-GPT-023 — verifier 판단은 active worktree에서 생성된 뒤 exact candidate에 사후 재결속된다

* **Severity: major**

### 실패 메커니즘

Evaluate와 promote의 외부 Codex runner는 `self.input_root`를 cwd로 사용합니다. Sandbox만 read-only로 바뀔 뿐, candidate OID를 checkout한 engine-owned worktree나 candidate materialization을 runner cwd로 사용하지 않습니다.

Canonical public flow에서는 이 차이가 실제로 발생합니다. E2E test는 integration target의 HEAD와 candidate OID가 서로 다름을 명시적으로 확인한 후, canonical project root에서 promote를 시작합니다.

그 뒤 다음 순서가 실행됩니다.

1. 외부 verifier 모델은 canonical active worktree를 보고 `result_summary: pass|fail`을 반환합니다.
2. `_publish_promotion_verifier()`는 그 문자열 하나를 모든 completion criterion의 boolean으로 변환합니다.
3. 새 `VerifierAdapter`의 executor는 모델을 다시 실행하지 않고 이미 얻은 boolean과 evidence digest를 반환합니다.
4. `execute_verifier()`는 candidate ref에서 exact Git result를 파생하므로, 최종 `VerifierEvidence`에는 candidate OID가 기록됩니다.
5. `validate_promotion_evidence()`는 이제 well-formed candidate-bound evidence를 보게 되고 target apply를 허용합니다.

즉 모델의 판단 대상은 integration tree `B`인데, evidence는 candidate tree `C`에 결속될 수 있습니다.

```text
model actually inspected: B
VerifierEvidence.result_oid: C
promotion applied: C
```

`execute_verifier()` 내부에서 candidate를 read-only materialization하는 것은 이 문제를 해결하지 않습니다. 그 materialized root를 받는 adapter executor는 이미 계산된 `pass`를 재포장할 뿐이며, 외부 verifier 모델은 그 root에서 다시 실행되지 않습니다.

같은 문제가 evaluate에도 존재합니다. Evaluate runner 역시 active worktree에서 실행되고, 반환된 pass/fail을 `publish_evaluation_evidence()`가 frozen candidate에 결속합니다.

### 구체적 실패 예

```text
integration HEAD:
    security_check = enabled

candidate ref:
    security_check = disabled
    tests broken
```

Verifier는 integration HEAD를 읽고 pass를 반환합니다. Engine은 그 pass를 candidate의 exact Git triple에 재결속하고 candidate를 integration target에 적용할 수 있습니다. Actor와 artifact는 서로 다르지만, **판단과 대상의 provenance가 다릅니다.**

### 필수 수정

Evaluate와 promote의 실제 model invocation을 exact candidate context 안으로 옮겨야 합니다.

권장 구조:

1. candidate OID에서 engine-owned detached worktree 또는 immutable materialization 생성
2. 그 root를 verifier/evaluator runner의 실제 cwd로 사용
3. runner launch record에 candidate OID, materialized-root fingerprint, RunSpec digest 결속
4. 모델이 생성한 raw result artifact를 `VerifierEvidence`가 직접 참조
5. post-hoc `pass` replay adapter 제거
6. candidate root가 달라지거나 runner가 다른 cwd를 본 경우 fail-closed

최소 회귀는 두 개면 충분합니다.

* integration tree는 PASS, candidate tree는 FAIL → verifier가 FAIL을 반환해야 함
* integration tree는 FAIL, candidate tree는 PASS → verifier가 PASS를 반환해야 함

현재 fixture처럼 모델이 파일을 읽지 않고 schema만 보고 pass를 내는 test는 이 경계를 판별하지 못합니다.

---

## WS-GPT-024 — `execute_stage()`는 published artifact가 아니라 handler가 반환한 in-memory 객체를 신뢰한다

* **Severity: major**

### 실패 메커니즘

`validate_promotion_evidence()`는 다음을 엄격히 비교합니다.

* object type
* run/spec/candidate/evaluation/result field
* actor role와 actor ID distinctness
* artifact digest distinctness
* reviewer lineage

그러나 다음은 확인하지 않습니다.

* `VerifierEvidence.artifact_reference`가 store에 현재 attempt 소유로 등록됐는가
* 해당 CAS bytes를 다시 parse했을 때 전달된 객체와 동일한가
* `ReviewerEvidence`와 `ReviewCycle`이 현재 durable review chain에서 reload된 값인가
* `IntegrationDecision`이 decision artifact store에서 reload된 terminal record인가
* actor ID가 frozen profile binding과 일치하는가

검증 함수는 전달받은 dataclass의 field만 비교합니다.

`execute_stage()`는 caller-supplied handler map을 받고, `independent-verify`, `adversarial-review`, `integration-decision`이 반환한 객체를 그대로 위 validator에 전달합니다. Validator가 성공하면 같은 DAG에서 바로 `target-ref-apply`가 실행됩니다.

따라서 well-formed이지만 실제로 publish되지 않은 객체를 반환하는 composition path가 생기면 다음이 가능합니다.

```text
fake VerifierEvidence object
+ fake ReviewerEvidence object
+ fake IntegrationDecision object
→ field-level validator PASS
→ target-ref-apply
→ later closeout may fail, but integration target already moved
```

테스트도 validator가 store/CAS 없는 synthetic digest와 synthetic artifact references를 입력받는 pure object validator임을 보여줍니다. `valid_bundle()`은 임의 digest로 모든 객체를 생성하고, reject validator는 해당 bundle을 성공적으로 승인합니다.

이는 악의적인 Python caller만의 문제가 아닙니다. 새 carrier, alternate host adapter, retry composition, future multi-job scheduler가 “객체는 만들었지만 store transition 또는 artifact publication을 누락한” 경우에도 동일하게 발생합니다. 현재 closure round의 목표가 이름의 분리를 authority의 분리로 바꾸는 것이었다면, handler return value는 authority가 될 수 없습니다.

### 필수 수정

Promotion validator는 `RunAssembly` 또는 equivalent authority resolver를 받아 다음을 reload해야 합니다.

* verifier evidence: current attempt에 등록된 `verifier-evidence:*` reference와 actual CAS bytes
* reviewer evidence: durable `review-cycle:*` head와 actual reviewer artifact bytes
* integration decision: current attempt의 `integration-decision:*` reference와 actual CAS bytes
* actor binding: 해당 run에 frozen된 role binding
* artifact kind와 owner run/attempt

그 후 handler가 반환한 객체가 아니라 **reload된 artifact object**를 validation과 apply에 사용해야 합니다.

더 단순한 대안은 promote의 handler map을 외부에서 주입할 수 없게 하고, production composition을 private closed path로 만드는 것입니다. 다만 test fixture가 필요하면 effect executor나 backend adapter만 주입하고, authority artifact 생성·조회·validation 순서는 engine이 소유해야 합니다.

필수 negative test:

```text
handler returns type-correct verifier/reviewer/decision objects
but no corresponding store/CAS references exist
→ target ref remains unchanged
```

---

## WS-GPT-025 — 과거 commit의 project fact는 현재 brief에서 폐기됐어도 disposition authority로 계속 유효하다

* **Severity: major**

### 실패 메커니즘

`validate_disposition_authority()`는 `objective_ref`를 parse하고 `AuthorityResolver.validate()`를 호출합니다. Append와 materialize 모두 이 검사를 수행하므로 nonexistent commit, missing CAS, 해당 commit 내 digest mismatch는 잘 차단됩니다.

그러나 `AuthorityResolver`의 project-fact 검증은 다음만 수행합니다.

```text
git show <ref.commit>:PROJECT_BRIEF.md
→ fact_id 조회
→ fact_digest / binding 비교
```

현재 HEAD 또는 현재 채택된 Project Brief와는 비교하지 않습니다.

`read_project_frame_at_commit()`에는 `current_commit`을 전달하면 과거 frame을 `superseded`로 판정하는 기능이 이미 있지만, disposition resolver는 이 인자를 사용하지 않습니다.

따라서 다음 경로가 열려 있습니다.

1. commit `A`에서 `commitment/outcome`이 binding fact였다.
2. owner가 realignment 후 commit `B`에서 해당 fact를 수정하거나 폐기했다.
3. disposition은 original `ProjectFactRef(commit=A, digest=A.digest)`를 사용한다.
4. resolver는 `A:PROJECT_BRIEF.md`만 읽으므로 성공한다.
5. `fix-now` 또는 `fix-before-promotion` task가 materialize된다.

이는 abandoned branch의 committed fact에도 적용될 수 있습니다. 현재 HEAD의 ancestor인지조차 검사하지 않기 때문입니다.

현재 “stale fact” 회귀는 이 경로를 판별하지 않습니다. Test는 brief를 수정한 뒤 **commit을 새 HEAD로 바꾸면서 digest만 과거 값으로 유지**합니다. 당연히 새 commit의 bytes와 old digest가 다르므로 거부되지만, original old commit을 그대로 유지한 ref는 시험하지 않습니다.

### 필수 수정

Generic `AuthorityResolver`의 historical provenance 성질은 유지하되, disposition 전용 current-objective 검증을 추가하는 편이 맞습니다.

권장 규칙:

1. current HEAD와 current committed Project Brief를 읽는다.
2. referenced commit이 current HEAD의 ancestor인지 확인한다.
3. current brief에서 동일 `fact_id`가 존재해야 한다.
4. current fact의 digest와 binding이 disposition ref와 동일해야 한다.
5. 다르면 `objective-superseded` typed refusal
6. materialize 시에도 같은 검사를 반복한다.

즉 unrelated commit이 추가된 것만으로 과거 ref를 무효화해서는 안 되지만, **current fact 내용이나 binding이 바뀌었다면 반드시 무효화**해야 합니다.

필수 회귀:

```text
old_ref = fact_ref at commit A
brief fact changed and committed at B
append/materialize using unchanged old_ref(commit=A)
→ refusal
```

---

# Open domain questions

## 1. Owner-only disposition은 실제 owner authority인가, 단순 role label인가

현재 owner-only check는 `decided_by.role == "owner"`만 확인합니다. `binding_digest`는 SHA-256 형식만 검증하며 owner evidence, signature, explicit CLI confirmation, stored principal과 대조하지 않습니다. 따라서 coordinator가 payload에 `role: owner`를 적으면 blocker/current-objective `accept-risk` 경계를 통과할 수 있습니다.

이번 request가 이를 known NO-GO로 명시했고 현재 지원 범위가 solo local trust domain이므로 별도 major finding으로 중복 계상하지 않았습니다.  다만 이 상태에서 `OwnerDecisionRequired`를 hard authority boundary라고 문서화해서는 안 됩니다. 최소한 owner evidence artifact 또는 interactive confirmation receipt가 필요합니다.

## 2. 동일 candidate에 대한 semantic reject를 재시도해도 되는가

현재 명시적 retry lineage가 있으면 동일 candidate·RunSpec·evaluation generation에 대해 rejected verifier를 다시 호출할 수 있고, 두 번째 verifier가 pass하면 같은 candidate가 승격될 수 있습니다. Test도 동일 result에 대해 첫 reject 후 두 번째 accept를 정상 경로로 규정합니다.

다음 구분이 필요합니다.

* process/backend failure → 동일 candidate retry 가능
* malformed output → 동일 candidate retry 가능
* verifier가 criterion을 실제로 fail 판정 → 새 candidate 또는 owner ruling 필요

이를 구분하지 않으면 최대 2회라는 제한이 있더라도 stochastic retry-to-pass가 됩니다.

## 3. Evaluate scaffold가 task ID만으로 candidate를 고르는 것이 의도적인가

Evaluate scaffold는 latest candidate를 `task_id + explore stage`로만 선택하며, candidate producer의 objective와 현재 evaluate objective는 비교하지 않습니다.  현재 objective 아래에서 과거 candidate를 새로 평가하는 것을 허용하려는 설계라면 타당합니다. Objective continuity를 요구한다면 candidate selector에도 project-fact equality가 필요합니다.

---

# Residual risks from unavailable environment

* 지정 target에 연결된 GitHub Actions run과 combined status는 확인되지 않았습니다. Connector 결과에는 해당 SHA의 workflow run이 없습니다.
* Request에 기록된 258-test suite, `/tmp` release rehearsal, dogfood S1–S3, store stress 결과는 실행 로그의 주장으로 읽었으며 제가 독립 재실행하지는 않았습니다.
* 실제 Codex backend에서 verifier가 어느 파일을 읽었는지, launch cwd와 candidate OID의 관계를 동적 trace로 재현하지 않았습니다. WS-GPT-023은 production invocation, adapter composition, E2E fixture의 서로 다른 HEAD/candidate OID를 정적으로 추적해 확인했습니다.
* GPU나 별도 dataset은 이번 trust-kernel 검토에 필요하지 않았습니다.
* Release script 전체를 실제로 실행하거나 marketplace sync를 발생시키지 않았습니다. 따라서 release projection 자체는 정적으로 승인하지만 **release readiness 전체는 위 세 major가 폐쇄될 때까지 승인하지 않습니다.**

# 최종 판정

이번 round로 다음은 폐쇄된 것으로 봅니다.

* 4-role Project Brief 정합성
* semantic draft scaffold
* risk record의 review gate 연결
* reject의 apply 이전 typed terminal
* release manifest의 legacy 제거와 신규 runtime 포함

하지만 closure의 핵심인 promote authority는 아직 다음 두 수준에서 불완전합니다.

```text
judgment provenance != candidate provenance
in-memory typed object != published authority artifact
```

그리고 review disposition은:

```text
historically valid objective != currently active objective
```

를 구분하지 못합니다.

따라서 `3c411b2cba4ac6e757f768bb094aef737b4151b2`는 **CHANGES REQUESTED**입니다.


---

<!-- waystone triage: BEGIN -->
## Findings (triage — 자유 형식 리뷰(WS-GPT- prefix라 skeleton 미파싱), verbatim 본문에서 직접 추출; 전 항목 main 독립 코드 대조 + finding당 codex verifier 1기 적대 검증 완료)

리뷰 정식 판정: "**CHANGES REQUESTED** — Critical 0 / Major 3". Claims adjudication: 6개 중 4개 승인(reject terminal·candidate exact-object 검증(좁은 의미)·scaffold·release projection(정적)), 미폐쇄 2개(promote authority 분리 → WS-GPT-023·024, stale objective 차단 → WS-GPT-025). 승인 항목: 4-role brief 정합·semantic draft scaffold·risk record→review gate 배선·reject의 apply 이전 typed terminal·release manifest legacy 제거. **Release readiness는 major 3건 폐쇄까지 미승인.**

| # | finding (리뷰 절) | verdict | type | severity | evidence (검증 근거) | task id |
|---|---|---|---|---|---|---|
| WS-GPT-023 | "verifier 판단은 active worktree에서 생성된 뒤 exact candidate에 사후 재결속된다" — evaluate/promote 외부 runner cwd가 candidate checkout이 아니라 input_root; result_summary 하나가 post-hoc replay adapter로 모든 criterion에 복제된 뒤 candidate exact tuple에 결속 | REAL | verification | major | main 독립 확인: `engine.py:462`(input_root=active worktree)·`:715-719`(sandbox만 read-only)·`:733`(RunnerInvocation cwd=input_root)·`:1264-1286`(pass replay executor)·`:1310-1324`(candidate ref로 exact 결속). verifier v023 CONFIRMED — 추가로 supervisor spawn(`supervisor.py:1280-1289`), E2E가 HEAD≠candidate를 명시 assert(`test_run_cli.py:618-627`), fixture는 파일을 읽지 않는 content-blind pass(`:79-108`), promotion verification plan은 check-free(`engine.py:1295-1297`)라 mandatory engine check도 없음. 반증 4방향 전부 실패(materialization은 실재하나 executor가 미사용; launch/result binding에 cwd tree OID 부재; prompt 강제 없음; 정상 flow에서 불일치 도달 가능). "materialization만으로는 해결 아님" 주장도 정확(`verify.py:1366-1387` review_root 미사용) | fix/promote-verifier-candidate-context |
| WS-GPT-024 | "execute_stage()는 published artifact가 아니라 handler가 반환한 in-memory 객체를 신뢰한다" — validator는 field 비교만, store/CAS reload 없음; well-formed unpublished tuple로 target-ref-apply 도달 가능 | REAL | architecture | major (main ruling — verifier는 minor 이견) | main 독립 확인: `engine.py:396-451`(validator는 plan+객체만 받는 순수 함수, store/root 인자 없음)·`:1600-1603`(public handler map)·`:1702-1714`(in-memory promotion_results→validator→apply). verifier v024 메커니즘 CONFIRMED — apply(`:1194-1213`)·post-apply(`:1757-1772`)·completion(`:2017-2040`) 어디에도 publication reload 없음; test도 synthetic digest 순수 객체 검증(`test_promote_evidence.py:47-157`). **단 도달성 반례**: canonical CLI/resume 경로는 engine 내부 조립(`:1475-1492`)이고 정상 publisher는 durable 경계 보유(`verify.py:1601-1638`·`2600-2644`) — 현행 carrier/retry에 handler 주입 호출점 없음. main ruling: round의 binding 목표(이름의 분리→authority의 분리)와 release gate 결속상 major 유지, 수정은 verifier 권고대로 최소화(기존 reload primitive `verify.py:2881-2913`·`2978-3017` 활용 + composition 봉쇄, RunAssembly 통주입은 과잉) | fix/promote-authority-published-reload |
| WS-GPT-025 | "과거 commit의 project fact는 현재 brief에서 폐기됐어도 disposition authority로 계속 유효하다" — resolver가 ref.commit만 조회, current HEAD/brief 대조·ancestor 검사 없음 | REAL | correctness | major | main 독립 확인: `completion.py:431-440`(read_project_frame_at_commit을 current_commit 없이 호출, fact digest/binding만 대조)·`brief.py:432·452-472`(current_commit/superseded 기능 실재·미사용)·`test_review_findings.py:252`(기존 회귀는 commit을 revised_head로 치환 — unchanged old_ref 경로 미시험). verifier v025 CONFIRMED — 반증 5방향 전부 실패; ADR-0015가 실증하듯 realignment는 정상 상태 전이라 도달성 실재. 구현 함정 pre-register: superseded(단순 과거)를 곧장 거부하면 "unrelated commit 허용" 규칙과 충돌 — ancestry + HEAD frame의 동일 fact digest/binding 대조 + 불일치만 objective-superseded refusal | fix/disposition-current-objective-binding |

### Open domain questions 처분 (ruling 자율권 정책)

- **Q1 (owner-only disposition의 role label)**: 리뷰어 스스로 major 중복 계상 안 함(solo local trust domain 명시 NO-GO). 기존 `chore/decision-actor-principal-binding`에 승계 기록 — "OwnerDecisionRequired를 hard authority boundary로 문서화 금지, owner evidence artifact/interactive receipt가 최소 요건".
- **Q2 (semantic reject의 동일 candidate retry)**: 실재 gap으로 판단 — process/backend 실패·malformed output과 verifier의 semantic fail을 구분하지 않으면 2회 상한이 있어도 stochastic retry-to-pass. 신규 등록: `chore/promote-retry-failure-taxonomy` (minor).
- **Q3 (evaluate scaffold의 task_id-only candidate 선택)**: ruling — 현 설계는 "과거 candidate를 현 objective 아래 재평가 허용" 의도로 수용. 단 objective continuity를 selector로 확장할지는 WS-GPT-025 수정과 동일 논점이므로 `fix/disposition-current-objective-binding` 착수 시 함께 판단(task notes에 기록).

### 등록 요약

- REAL 3건 / REJECTED 0건 / NEEDS-RULING 0건 (Q1–Q3는 finding 아님 — 위 처분). 신규 등록 4건(major 3 + minor 1) + 기존 승계 1건(Q1→chore/decision-actor-principal-binding notes).
- major 3건이 release readiness를 직접 gate — 리뷰어 명시("release readiness 전체는 위 세 major가 폐쇄될 때까지 승인하지 않습니다"). 실 release 실행(owner 대기)은 이 3건 폐쇄 후로 순연 권고.
- 파일 충돌: WS-GPT-023·024는 engine.py/verify.py 공유 — 병렬 발진 금지, 순차(또는 단일 위임 통합).
- 검증 방법: finding당 codex(gpt-5.6-sol, high) 적대 verifier 1기(read-only·정적, 보고서 scratchpad/reports/v023·v024·v025.md) + main 독립 라인 추적. verifier 3기 모두 "동적 재현 불필요(정적 완결)" 판정.

### ingest 메타 상태

- reply 헤더의 request-digest는 이 round의 immutable sidecar와 일치, review-target `3c411b2…`도 round exposure 대상 커밋과 일치. **단 declared model(chatgpt:gpt-5.6-pro)이 frozen reviewer(codex, gpt-5.5-pro — release 0.11.1 기본값 동결, dev config가 review: 키 금지라 교정 불가)와 불일치 → ingest 경고 "reply cannot count as configured feedback", receipt는 pending**(사전 공지된 비치명 상태; finding 채택은 상기 main 독립 검증 경로로 수행 — attestation 재작성 없음).
- `review-skipped-closes-v1`: **unevaluable(identity 불일치로 configured feedback 미집계)** — non-fire로 집계하지 않음. 그 외 adaptive-rule 출력 없음(경고는 rule fire 아님). verbatim 사본 17,633 bytes = drop-file 크기와 일치(byte-exact, drop-file 소비됨).
<!-- waystone triage: END -->
