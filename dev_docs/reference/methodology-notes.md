# 방법론 노트 — 외부 리뷰의 "개발방법론 승화" 응답 (2026-07-22, 비구속 참고자료)

- Status: **reference — 비구속.** 사용자 지시: "저 내용을 그대로 반영하거나 구현할 의무는
  없고, 네가 자율 설계하는데에 도움이 될 것 같으면 개념만 참고하면 됨. 이름('ICPD')은
  구린 것 같으니까 갖다 쓰지는 말고."
- 관계: `dev_docs/0.13-redesign-mandate.md`(binding)와 동일 계보의 후속 대화 — mandate의
  내용을 일반 개발방법론으로 재정리한 것. 겹치는 부분이 대부분이나, mandate에 없는 추가
  개념이 있음: capability maturity 사다리(ABSENT→EXECUTABLE→CHARACTERIZED→EVALUATED→
  PROMOTED), 금지된 자동 전이 4종, bounded autonomy budget 일반화, Frame/Realign의 정식
  stage화, 최소 artifact 3종(PROJECT_BRIEF/CAPABILITIES/CHECKPOINT), MUST 규범 15개,
  suite의 confidence-per-execution-cost 관점.
- 아래는 응답 verbatim.

---

# 추천 명칭

## **Intent-Calibrated Progressive Development — ICPD**

한국어로 옮기면 **의도 보정형 점진 개발** 정도입니다. 짧게 부를 때는 **Calibrated Development**가 자연스럽습니다.

> **불확실한 사용자 의도를 곧바로 specification으로 굳히지 않고, 실행 가능한 capability를 통해 의도와 해법을 함께 학습하며, `Explore → Evaluate → Promote`로 갈수록 commitment와 assurance를 점진적으로 높이는 개발 방법론.**

핵심 표어는 다음이 적합합니다.

> **Explore freely. Evaluate honestly. Promote deliberately.**
> 자유롭게 탐색하고, 정직하게 평가하며, 신중하게 승격한다.

이름에 `agentic`을 넣지 않은 이유는, LLM agent가 중심 실행자이더라도 방법론 자체는 인간 개발자나 혼합 팀에도 적용될 수 있어야 하기 때문입니다. 대신 **agent-driven development를 주된 적용 대상으로 설계된 방법론**이라고 설명하면 됩니다.

---

# 왜 이 이름인가

## Intent-Calibrated

사용자 의도는 처음부터 완결된 요구사항이 아닙니다.

초기의 발화에는 보통 다음이 섞여 있습니다.

* 사용자가 실제로 확정한 목표
* 아직 검증되지 않은 기대
* domain knowledge 부족에서 나온 추측
* 장기적으로 하고 싶은 것
* 당장 만들어야 할 것
* 말로는 표현하지 못했지만 중요한 취향과 trade-off

ICPD는 requirements elicitation을 한 번 수행하고 종료하지 않습니다. **현재 agent가 이해한 프로젝트 방향을 사용자 반응과 실행 결과에 반복 대조하여 보정**합니다.

Omniphysics 대화에서 실제로 일어난 것도 단순한 scope reduction이 아니라, “VLA 데이터 공장”, “범용 통합 formulation”, “contact-first 인증” 같은 초기 명제를 분해해 사용자가 원한 물리적 인과관계와 prototype·long-term horizon을 다시 구분한 과정이었습니다.

## Progressive

점진적인 것은 코드 양만이 아닙니다.

* **Commitment:** 가설에서 owner commitment로
* **Assurance:** probe에서 독립 평가와 regression contract로
* **Permanence:** disposable candidate에서 mainline capability로
* **Governance:** 가벼운 기록에서 durable decision과 review로

확신과 되돌리기 비용이 커질수록 더 강한 증거를 요구합니다. 이는 Boehm 계열의 Incremental Commitment Spiral Model이 강조한 incremental commitment와 evidence/risk-based decision의 계보와도 맞닿아 있습니다. ([learning.acm.org][1])

## Development

이 방법론은 test, spec, prompt, code 중 하나를 개발의 중심으로 두지 않습니다.

중심 단위는 다음입니다.

> **현재 프로젝트 목적에 정렬된 executable capability와, 그 capability에 대해 정직하게 주장할 수 있는 evidence.**

---

# 기존 명칭을 그대로 쓰지 않는 이유

| 명칭                                | 유효한 부분                         | ICPD 전체를 설명하지 못하는 이유                                                                                                                                                                                     |
| --------------------------------- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Vibe coding**                   | 빠른 탐색, 낮은 초기 비용                | 장기 상태, 권위, 독립 검증, handoff가 약함                                                                                                                                                                            |
| **TDD**                           | 이미 정의된 behavior의 regression 계약 | 무엇을 만들어야 하는지 자체가 불확실한 연구·제품 탐색에는 너무 이른 영구 계약을 만들 수 있음                                                                                                                                                    |
| **Spec-Driven Development**       | 확정된 범위의 구현 일관성                 | 잘못된 spec을 높은 정밀도로 구현하는 문제를 해결하지 못함                                                                                                                                                                       |
| **Hypothesis-Driven Development** | 가설과 결과를 분리하고 실험으로 학습           | 일반적으로 제품 feature와 outcome metric 중심이며, deep technical research·multi-agent authority·promotion assurance까지는 포괄하지 않음. HDD는 change를 측정 가능한 hypothesis로 다루는 접근으로 이미 정립되어 있습니다. ([Confidence by Spotify][2]) |
| **Evidence-Driven Development**   | 주장보다 증거를 우선                    | 모든 단계에 같은 증거 강도를 적용하면 지금 경험한 verification attractor가 재발할 수 있음                                                                                                                                            |
| **Capability-Driven Development** | capability 중심이라는 표현은 가까움       | 이 이름은 이미 context-aware enterprise information systems를 위한 별도 방법론으로 사용되고 있으므로 혼동 가능성이 큼. ([AIS eLibrary][3])                                                                                              |

ICPD는 위 방식들을 부정하지 않습니다. **각 방식을 적절한 lifecycle stage에 배치하는 상위 방법론**입니다.

```text
Explore   → vibe-like iteration, spikes, probes
Evaluate  → hypothesis-driven evaluation, frozen evidence
Promote   → spec-driven implementation boundary, TDD/regression, risk-gated review
```

TDD나 spec-driven development가 잘못된 것이 아니라, **그것을 모든 종류의 work에 전역 적용하는 것이 잘못**이라는 판단입니다.

---

# ICPD의 정식 정의

> **Intent-Calibrated Progressive Development is a capability-centered development methodology in which uncertain intent remains explicitly provisional, executable candidates are produced under bounded autonomy, and commitment, verification, and permanence increase only as evidence justifies progression from exploration to evaluation and promotion.**

한국어 정의는 다음과 같습니다.

> **ICPD는 불확실한 의도를 명시적인 미확정 상태로 보존하고, 제한된 자율성 아래 실행 가능한 후보를 만들며, 증거가 충분해질 때만 탐색에서 평가와 승격으로 이동하면서 commitment·검증 강도·영속성을 높이는 capability 중심 개발 방법론이다.**

---

# 핵심 불변조건

## 1. 불확실성은 결함이 아니라 상태다

프로젝트 의도는 다음 세 범주로 구분합니다.

| 구분                     | 의미                 | 실행 권위                                       |
| ---------------------- | ------------------ | ------------------------------------------- |
| **Commitment**         | 사용자가 현재 확정한 방향과 제약 | task·acceptance·promotion constraint로 사용 가능 |
| **Working hypothesis** | 시험 중인 기술·제품 가설     | exploration 방향으로만 사용, requirement 자동 승격 금지  |
| **Open question**      | 아직 답하지 않은 문제       | agent가 임의로 닫지 않음                            |

이를 `PROJECT_BRIEF.md`에 명시합니다.

가장 중요한 규칙은 다음입니다.

```text
hypothesis → requirement
```

전이는 자동으로 일어나지 않습니다. 사용자 또는 미리 위임된 owner authority가 명시적으로 승격해야 합니다.

---

## 2. 진행률의 단위는 task가 아니라 capability다

Capability는 다음 maturity를 가집니다.

```text
ABSENT
→ EXECUTABLE
→ CHARACTERIZED
→ EVALUATED
→ PROMOTED
```

* `EXECUTABLE`: 실제로 end-to-end 실행된다.
* `CHARACTERIZED`: 지원 범위, 관측된 성질, 알려진 실패가 기록됐다.
* `EVALUATED`: 동결된 평가 조건에서 독립적으로 판정됐다.
* `PROMOTED`: mainline의 durable behavior로 채택되고 필요한 regression contract를 갖는다.

다음은 보조 산출물이지 그 자체로 progress가 아닙니다.

* test 수 증가
* 문서 수 증가
* task 완료 수 증가
* review finding 처리 수
* ADR 수
* harness rule 수

각 run은 최소한 다음 중 하나를 반환해야 합니다.

```text
new executable capability
measured improvement
validated decision
falsified hypothesis
simplification/removal
no objective delta
```

`no objective delta`도 정직한 결과이지만 milestone 진척으로 계산하지 않습니다.

현재 Waystone M1-B는 실행 신뢰성 면에서 큰 진전을 이뤘지만, 838개였던 suite가 1,088개로 증가했고 15개 구현 task와 다수의 반증 probe가 축적되었습니다. 이 자체가 잘못은 아니지만, **capability delta와 assurance cost를 대조하는 반대편 지표가 아직 없습니다.**

---

## 3. Assurance는 위험과 maturity에 비례한다

모든 변경에 같은 수준의 검증을 요구하지 않습니다.

검증 강도는 다음에 따라 증가합니다.

* lifecycle stage
* 변경의 되돌리기 비용
* 외부 노출 범위
* durable authority에 미치는 영향
* migration·데이터 손실 가능성
* 실패 복구 비용

```text
탐색 후보의 실패
  < 평가 결과의 오류
  < mainline promotion 오류
  < migration·권위·보안 표면 오류
```

따라서 “실제 bug가 존재한다”는 사실만으로 모든 작업에 최고 수준 assurance를 적용하지 않습니다.

---

## 4. Review는 sensor이지 commander가 아니다

Reviewer의 권위는 다음에 한정됩니다.

* 구체적인 failure mechanism 제시
* evidence 제시
* finding의 존재 여부를 공격
* impact의 상한을 분석
* 기존 평가가 놓친 영역을 제시

Reviewer는 다음을 결정하지 않습니다.

* 지금 수정해야 하는가
* 현재 milestone을 중단해야 하는가
* architecture를 일반화해야 하는가
* harness subsystem을 추가해야 하는가
* 어떤 remediation을 선택해야 하는가

Finding은 최소한 다음 축을 분리합니다.

```yaml
validity: confirmed | rejected | unresolved
impact: blocker | major | minor
exposure: common | edge | adversarial | unknown
objective_relevance: current | promotion | future | out-of-scope
remediation_scope: local | bounded | architectural
disposition: fix-now | fix-before-promotion | backlog | accept-risk | no-action
```

핵심 전이는 다음과 같습니다.

```text
confirmed finding
≠
registered task
≠
current blocker
```

현재 Waystone review skill은 REAL finding을 각각 task로 등록하고 blocker를 다음 round 전에 처리하도록 안내합니다. 이것이 finding truth와 remediation priority를 결합하는 현재의 구조적 원인입니다.

ICPD에서는 `fix-now`와 `fix-before-promotion`만 실행 task로 materialize합니다. 나머지는 finding record와 disposition으로 남습니다.

---

## 5. Test에는 lifecycle과 만료 조건이 있다

테스트를 세 종류로 나눕니다.

### Probe

탐색 중 가설을 빠르게 확인하는 검사입니다.

* candidate-local
* 임시적
* 반복적으로 수정 가능
* 실패한 candidate와 함께 삭제 가능
* mainline suite 편입 의무 없음

### Evaluation check

동결된 candidate와 evaluation generation을 판정합니다.

* candidate SHA·config·evaluation spec에 결속
* hold-out 노출 후 candidate를 바꾸면 기존 결과는 승격 증거가 아님
* 다음 generation에서 교체 가능
* 영구 public contract일 필요 없음

### Regression contract

PROMOTED behavior를 보호합니다.

영구 test가 되려면 다음 중 하나를 보호해야 합니다.

* promoted public behavior
* stable trust invariant
* 현실적으로 재발 가능한 production failure
* migration·authority·security 경계

단순히 “리뷰어가 실제 edge case를 찾았다”는 이유만으로 permanent test가 되지는 않습니다.

추가 규칙:

* 한 failure mechanism에 수십 개 incident-specific case를 붙이기보다 property/invariant test를 선호
* contract가 폐기되면 test도 삭제하거나 축소
* test 삭제를 trust loss로 간주하기 전에 보호하던 contract가 아직 존재하는지 확인
* suite size보다 **confidence per execution cost**를 관리

---

## 6. Context는 correctness의 일부다

Agent worker에게 코드와 acceptance만 주고 올바른 결과를 기대할 수 없습니다.

현재 M1-B worker prompt는 대체로 다음 네 블록만 전달합니다.

```text
Goal
Bounds
Acceptance criteria
Report
```

이는 bookkeeping noise를 제거한다는 점에서는 좋지만, architecture·research·product judgment가 필요한 작업에는 의미 정보가 부족합니다.

ICPD는 `Semantic Work Brief`를 사용합니다.

```yaml
objective:
  reference: "<project commitment / capability>"
  why_now: "..."

current_state:
  summary: "..."
  last_executable_result: "..."
  known_failures: [...]

decisions:
  fixed: [...]
  worker_may_choose: [...]
  requires_escalation: [...]

constraints: [...]
non_goals: [...]

relevant_evidence:
  - source: owner | harness | coordinator
    reference: "..."
    summary: "..."

open_questions: [...]
```

여기서 중요한 것은 provenance입니다.

| Context       | 권위                                      |
| ------------- | --------------------------------------- |
| `owner`       | 프로젝트 commitment와 explicit decision      |
| `harness`     | Git·runtime·artifact에서 재도출한 사실          |
| `coordinator` | main agent의 해석과 압축; owner authority가 아님 |

### I-10의 개정 의미

기존 취지는 다음처럼 해석해야 합니다.

> **모델에 전달하는 protocol을 최소화한다. 의미를 최소화하지 않는다.**

즉:

```text
minimize bookkeeping protocol
≠
minimize decision-relevant context
```

Worker가 중요 결정을 내릴 맥락이 부족하면 추측하지 않고 `context_request`를 발행합니다.

```yaml
question: "어느 compatibility contract가 authoritative한가?"
blocked_decision: "API 유지 여부"
why_required: "두 해석에 따라 architecture와 migration 범위가 달라짐"
```

run은 실패가 아니라 `waiting_context`로 전이하고, orchestrator가 brief revision을 제공한 뒤 재개합니다.

Context transfer loss가 너무 큰 작은 작업은 무조건 위임하지 않고 main session이 직접 수행할 수 있습니다.

---

## 7. Harness는 사고를 통제하지 않고 권위 경계를 통제한다

Harness가 강하게 통제해야 하는 것:

* external effect
* live-tree mutation
* state transition
* identity와 provenance
* evidence binding
* retry budget
* cancellation·cleanup
* actor authority
* immutable candidate/evaluation boundary

Harness가 통제하지 않아야 하는 것:

* domain reasoning 방식
* 구현 전략
* algorithm 후보
* 코드 구조의 세부 선택
* worker의 창의적 탐색
* 해결책을 찾는 내부 사고 과정

한 문장으로 표현하면 다음과 같습니다.

> **Constrain authority and effects, not thought.**

---

## 8. 자율성은 최대화하지 않고 bounded하게 운영한다

Autonomous agent가 실패한 formulation 위에 무기한 연구 프로그램을 생성하지 못하게 합니다.

각 exploration에는 다음이 고정됩니다.

```text
candidate families
family당 revision budget
total attempt/cost budget
architecture pivot allowance
review/fix cycle budget
fallback choices
human escalation boundary
```

Budget 소진 시 자동으로 새로운 대형 architecture를 만들지 않습니다.

```text
1. 현재 최선 후보를 제한된 scope로 채택
2. 더 단순한 model로 축소
3. 별도 장기 research backlog로 이동
4. 새 architecture track을 owner에게 제안
```

4번은 agent가 자동 선택할 수 없습니다.

---

# Lifecycle

## Stage 0 — Frame

### 목적

사용자가 현재 무엇을 원하는지와 무엇을 아직 모르는지를 분리합니다.

### 주요 산출물

`PROJECT_BRIEF.md`

```text
Purpose
Commitments
Prototype scope
Long-term direction
Non-goals
Working hypotheses
Open questions
Revision triggers
```

### 상태

```text
provisional
committed
superseded
```

`provisional` 상태에서도 exploration은 가능하지만, project-wide architecture와 promotion contract를 가설에 결속해서는 안 됩니다.

### Exit

* primary outcome을 한 문장으로 설명 가능
* prototype scope와 long-term horizon이 분리됨
* non-goal이 명시됨
* 방향을 바꿀 수 있는 open question이 숨겨져 있지 않음
* 사용자가 commitments를 확인함

---

## Stage 1 — Explore

### 목적

정답을 증명하는 것이 아니라 **실행 가능한 candidate와 학습**을 얻습니다.

### 허용

* 구현과 측정의 빠른 반복
* calibration data 재사용
* formulation 변경
* temporary probe
* 실패한 candidate 폐기
* 경쟁 candidate 병렬화
* bounded legacy asset reuse

### 기본적으로 요구하지 않음

* 영구 ADR
* macro adversarial review
* exhaustive regression suite
* 완성된 formal spec
* 모든 micro-task 등록
* one-shot correctness claim

### Exit

다음 중 하나입니다.

* executable candidate
* measurable improvement
* hypothesis falsification
* bounded budget exhaustion
* architectural owner decision 필요

실패한 탐색도 유효한 outcome입니다.

---

## Stage 2 — Evaluate

### 목적

동결된 candidate가 미리 정한 주장을 실제로 만족하는지 판정합니다.

### Freeze

* candidate commit
* configuration
* parameters
* evaluation scenes
* metrics
* hold-out split
* repetition·seed policy
* compute budget
* baseline conditions

### 규칙

* implementer가 evaluation 중 candidate를 수정하지 않음
* evaluator가 threshold를 변경하지 않음
* 수정 시 새 candidate revision
* 노출된 hold-out을 보고 수정했다면 다음 공식 평가는 새 generation 사용
* worker self-report는 claim
* evaluator evidence는 independent fact
* evaluator와 reviewer는 다른 역할

### Exit

* pass
* fail
* inconclusive
* unsupported regime
* new evidence generation required

---

## Stage 3 — Promote

### 목적

실험 후보를 durable project capability로 승격합니다.

### 이때 처음 강하게 요구

* 최소 regression contract
* required independent verification
* risk-gated adversarial review
* concise ADR
* supported/unsupported envelope
* migration·compatibility 검토
* performance·reproducibility evidence
* public behavior와 failure semantics

### Exit

```text
PROMOTED capability
+ evidence bound to exact result
+ accepted risk
+ regression contract
+ handoff/checkpoint
```

ADR은 구현 허가서가 아니라 **이미 증거가 있는 결정을 고정하는 기록**입니다.

---

## Cross-cutting — Realign

Realignment는 실패 복구가 아니라 정상 transition입니다.

다음은 trigger 후보입니다.

* 사용자 피드백이 current commitment와 반복 충돌
* 여러 run 동안 capability delta가 없음
* active work가 review/fix/governance에 편중
* milestone의 임계경로가 unresolved hypothesis 하나에 장기간 종속
* test·gate 수는 증가하지만 executable outcome이 변하지 않음
* candidate family budget이 반복 소진됨
* worker가 같은 목적 혼동을 반복

Trigger는 자동 방향 변경이 아니라 다음 상태를 만듭니다.

```text
project-direction-may-be-stale
```

이후 `ideate`가 realignment dialogue를 수행합니다.

---

# 역할과 권위

| 역할                       | 소유하는 것                                                                                       | 소유하지 않는 것                           |
| ------------------------ | -------------------------------------------------------------------------------------------- | ----------------------------------- |
| **Owner**                | commitments, non-goals, risk appetite, 평가 기준의 중대한 변경, 대형 research fork                       | 구현 세부                               |
| **Orchestrator**         | lifecycle stage, candidate budget, semantic brief, routing, finding disposition, integration | owner intent 임의 변경                  |
| **Worker**               | candidate 구현, local experiment, 측정, limitation 보고                                            | 자기 결과 promotion, metric 변경          |
| **Evaluator / Verifier** | frozen candidate에 대한 독립 판정                                                                   | candidate 수정, 제품 우선순위               |
| **Reviewer**             | failure mechanism 탐색, architecture·domain 공격                                                 | task 우선순위, remediation architecture |
| **Engine / Harness**     | state, effect, provenance, evidence, authority, cancellation                                 | domain solution 선택                  |

Reviewer가 main agent보다 더 강한 reasoning을 보여도 권위 구조는 변하지 않습니다.

Reviewer는 더 좋은 **defect sensor**일 수 있지만, project objective의 소유자는 아닙니다.

---

# 최소 artifact 체계

이 방법론을 도입한다고 문서가 다시 폭증해서는 안 됩니다.

## 사용자에게 보이는 문서

```text
PROJECT_BRIEF.md
CAPABILITIES.md
CHECKPOINT.md
```

## 실행 중 내부 artifact

```text
Semantic Work Brief
Candidate Record
Evaluation Spec
Evaluation Result
Finding Record + Disposition
Promotion Record
```

이들은 각각 별도 Markdown 파일일 필요가 없습니다. Waystone runtime store와 content-addressed artifact에 저장하고, 사용자에게는 필요한 projection만 보여줄 수 있습니다.

## ADR

다음에만 작성합니다.

* promotion된 durable architecture decision
* public contract
* migration/authority decision
* owner approval가 필요한 장기적 trade-off

탐색 후보마다 ADR을 만들지 않습니다.

---

# ICPD가 금지하는 네 가지 자동 전이

이 네 가지가 방법론의 가장 압축된 핵심입니다.

```text
Hypothesis       → Requirement
Confirmed finding → Task
Probe             → Permanent regression test
Coordinator summary → Owner authority
```

모두 별도의 명시적 promotion decision이 필요합니다.

반대로 허용되는 전이는 다음입니다.

```text
Owner commitment
  → execution constraint

Executable candidate + frozen evaluation
  → evaluated evidence

Evaluation pass + promotion decision
  → durable capability

Durable capability
  → regression contract
```

---

# Waystone에 적용할 경우

## M1-B는 폐기 대상이 아님

현재 구축한 transactional store, artifact binding, lease/fencing, effect reconciliation, observability, cancellation safety, independent verification은 ICPD의 **execution trust kernel**로 그대로 유지해야 합니다.

빠진 것은 그 위의 **development direction control plane**입니다.

## M1-C 전에 필요한 변경

### Intent & Context

* `RunSpec.lifecycle_stage`
* `RunSpec.objective_ref`
* `semantic_brief_reference`
* `semantic_brief_digest`
* `context_request` action
* I-10 개정: protocol 최소화와 semantic context 최소화를 구분

현재 RunSpec이 freeze하는 것은 주로 `title`, `acceptance`, `scope`, `dependencies`입니다.

이 상태로 delegate front door를 새 engine에 연결하면 context-starved delegation이 canonical model로 굳어질 가능성이 큽니다.

## Review 경로에서 즉시 변경할 것

* `REAL → task` 자동 materialization 제거
* finding record와 disposition 분리
* current objective와 lifecycle stage 반영
* `fix-now`, `fix-before-promotion`만 task 생성
* architectural remediation은 owner 또는 명시적 decision 필요
* review/fix generation budget 적용

## M2 전에 필요한 것

Multi-job scheduler가 다음을 알아야 합니다.

* 이 run이 `explore`, `evaluate`, `promote` 중 무엇인지
* objective가 무엇인지
* candidate budget이 얼마인지
* 어느 finding이 실제 blocker인지
* 어떤 test가 disposable인지 permanent인지
* 어떤 worker가 semantic context를 더 요청했는지

그렇지 않으면 M2는 기존의 잘못된 incentive를 더 빠르고 병렬적으로 실행합니다.

## M3에 넣을 것

* `ideate`의 existing-project realignment mode
* `PROJECT_BRIEF.md` provisional/committed state
* status의 capability maturity와 outcome delta
* review-remediation spiral advisory
* SessionStart capsule에는 현재 objective, lifecycle stage, last executable result만
* task count·test count는 progress headline에서 제외

---

# 방법론을 위한 최소 규범

정식 methodology 문서에는 다음을 `MUST` 수준으로 넣는 것이 적절합니다.

1. 프로젝트 의도는 commitment, hypothesis, open question으로 구분한다.
2. Hypothesis는 owner decision 없이 requirement가 될 수 없다.
3. 모든 substantive run은 lifecycle stage와 objective를 가진다.
4. 모든 worker는 protocol이 아니라 decision-relevant semantic context를 받는다.
5. Worker는 context 부족을 추측으로 메우지 않고 요청할 수 있다.
6. Exploration의 probe와 failed candidate는 영구 보존 의무가 없다.
7. Evaluation은 candidate와 protocol을 먼저 freeze한 뒤 독립적으로 수행한다.
8. Confirmed finding은 자동 task가 아니다.
9. Permanent regression test는 promoted contract를 명명해야 한다.
10. Reviewer는 finding을 제시하지만 remediation priority를 소유하지 않는다.
11. Progress는 executable capability 또는 decision-relevant learning으로 측정한다.
12. Harness는 authority와 effects를 통제하고 model reasoning을 규격화하지 않는다.
13. 자율 research와 review/fix loop에는 유한 budget이 있어야 한다.
14. Project commitment, evaluation 기준, 대형 architecture fork, 핵심 메커니즘 포기는 owner 경계를 통과한다.
15. Evidence가 project direction을 반박하면 realignment를 정상 transition으로 허용한다.

---

# Omniphysics에 대입한 예

## Frame

```text
Commitment:
  standalone predictive physics engine
  rigid/contact + liquid/wet가 주력
  cloth는 architecture consumer
  single high-end GPU에서 준실시간

Hypothesis:
  특정 contact formulation이 적합할 것이다
  surface-film reduced model이 충분할 것이다

Open question:
  첫 solver family
  실제 calibration noise floor
```

## Explore

* rigid/contact baseline 1개
* challenger 최대 2개
* family당 major revision 최대 2개
* canonical scene에서 빠르게 측정
* temporary probe 사용
* macro review 없음

## Evaluate

* candidate SHA 동결
* dry/wet slip, squeeze-and-lift, insertion 평가
* PhysX/Newton matched-budget baseline
* candidate를 보지 않고 정한 evaluation generation
* independent evaluator

## Review finding 예

```yaml
validity: confirmed
impact: major
exposure: edge
objective_relevance: future
remediation_scope: architectural
disposition: accept-risk
reason: >
  현재 supported envelope 밖이며, 이를 일반 방어하려면
  prototype objective와 무관한 새로운 state machine이 필요하다.
```

Finding은 사실로 보존되지만 prototype 개발을 탈선시키지 않습니다.

## Promote

* 평가를 통과한 contact capability만 mainline으로
* 그때 필요한 property regression 추가
* 지원 범위와 accepted risk 기록
* concise ADR 작성
* 다음 capability로 진행

---

# 최종 형태

정리하면 이 방법론의 정체성은 다음입니다.

## 이름

**Intent-Calibrated Progressive Development**

## 대상

불명확한 초기 의도, 장기 research horizon, 다중 agent, 강한 reviewer, session discontinuity가 있는 프로젝트.

## 핵심 lifecycle

```text
Frame
→ Explore
→ Evaluate
→ Promote
↘ Realign when evidence contradicts direction
```

## 진행 단위

```text
Executable capability
or
decision-relevant learning
```

## Assurance 원칙

```text
Cheap and reversible work → light assurance
Durable and costly commitment → strong assurance
```

## Harness 원칙

```text
Constrain authority and effects, not thought.
```

## Review 원칙

```text
A finding can be true without being urgent.
```

## Context 원칙

```text
Minimize protocol, not meaning.
```

## Test 원칙

```text
Probes explore.
Evaluations judge.
Regressions protect promoted contracts.
```

가장 짧은 선언문은 다음이 적합합니다.

> **ICPD는 불확실성을 곧바로 명세로 바꾸지 않는다. 실행 가능한 capability로 학습하고, 후보를 동결해 정직하게 평가하며, 증거가 충분한 것만 영구 계약으로 승격한다. Agent는 자유롭게 해법을 찾지만, 사용자 의도·평가 기준·외부 효과·승격 권위는 넘을 수 없다.**

[1]: https://learning.acm.org/techtalks/icsm?utm_source=chatgpt.com "The Incremental Commitment Spiral Model (ICSM) with Barry Boehm"
[2]: https://confidence.spotify.com/glossary/hypothesis-driven-development?utm_source=chatgpt.com "What is a Hypothesis-Driven Development? | Confidence by Spotify"
[3]: https://aisel.aisnet.org/bise/vol57/iss1/3/?utm_source=chatgpt.com "\"Capability Driven Development: An Approach to Designing Digital Enterp\" by Solvita Berzisa, George Bravos et al."
