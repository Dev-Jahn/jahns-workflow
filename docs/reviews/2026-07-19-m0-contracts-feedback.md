<!-- waystone feedback: the body below is the reviewer reply VERBATIM (byte-exact copy via `waystone review ingest`) — do not edit it; a triage skeleton is appended beneath it. -->
round: 2026-07-19-m0-contracts
reviewer: chatgpt:gpt-5.6-pro
reviewer-effort: high
review-target: fd7ee42b4b457a81870e20d8b63a291a8743a742
reply-metadata-json: {"metadata":{"effort":"high","model":"chatgpt:gpt-5.6-pro","request-digest":"sha256:4f2d033dad550a585500b2b42fd91f8400bf16786de5efecd88938e5fb282a8c","review-target":"fd7ee42b4b457a81870e20d8b63a291a8743a742"},"narrative_digest":"sha256:e0349536182839688ca61a952c4f236d92b3a4eea1975f2865deb046aa745ecf","rendered_request_coverage_reason":null,"rendered_request_digest":"sha256:4f2d033dad550a585500b2b42fd91f8400bf16786de5efecd88938e5fb282a8c","rendered_request_digest_matches":true}
ingested: 2026-07-19
source: /tmp/review.md
verbatim-bytes: 26135

---





```text
model: chatgpt:gpt-5.6-pro
effort: high
review-target: fd7ee42b4b457a81870e20d8b63a291a8743a742
request-digest: sha256:4f2d033dad550a585500b2b42fd91f8400bf16786de5efecd88938e5fb282a8c
```

# Review verdict — CHANGES REQUESTED

**Critical 0 / Major 5**

ADR-0002~0008은 전반적으로 강합니다. 특히 external-effect reconciliation, fencing/CAS, liveness의 양방향 증거 규칙, cancel-pending, read-only status/watch, fact authority 분리는 구현 기준으로 사용할 수 있는 수준입니다. `observed`를 “명령 성공”이 아니라 권위 채널의 재관측으로 정의하고, 관측 불가를 `unknown-effect`로 유지한 것은 적절합니다. fileciteturn98file0L23-L38 fileciteturn98file0L46-L58 ADR-0003도 침묵·heartbeat 부재와 긍정적 종료 증거를 분리하고, unknown 상태에서 signal·cleanup을 금지합니다. fileciteturn100file0L37-L49 fileciteturn100file0L105-L139

다만 요청서의 자기 진단은 대체로 맞습니다. **R-3·R-6·R-7·R-8은 현재 M0 계약의 실제 빈칸**이고, **R-1·R-4·R-5는 coordinator control plane에 최소한의 readiness·budget·review gate가 빠진 하나의 공통 문제**입니다. R-2는 조금 다릅니다. 임의의 수동 shell 행위를 Waystone이 보장해야 한다는 주장은 성립하지 않지만, 그 행위가 run의 authoritative state로 승격되는 경계에는 관측과 reconcile이 필요합니다.

M0-C의 inventory·ledger 작업은 시작할 수 있으나, **`characterization-baseline` exit는 아래 계약 수정 전 통과시키지 않는 것**이 맞습니다. 특히 R-6의 잘못된 구조적 해소 주장을 그대로 두면 M0-C가 그 모순을 다음 구현의 전제로 고정하게 됩니다.

---

# 8개 주장 판정

| 항목 | 판정 | 권고 처분 |
|---|---|---|
| **R-1 acceptance 품질** | **남음** | 0.12 편입: dispatch 전 contract-readiness gate |
| **R-2 엔진 밖 수동 행위** | **부분적으로 이미 해결됨** | 임의 shell은 비보장으로 명시하되, authoritative admission에는 engine 재관측 필수 |
| **R-3 cwd 기반 root** | **남음, 현재보다 악화 가능** | 0.12 필수: canonical project identity와 worktree context 분리 |
| **R-4 중단·발산 규칙** | **남음** | 0.12에 hard attempt/budget ceiling, 정교한 trajectory heuristic은 0.13+ |
| **R-5 green gate와 설계 결함** | **남음** | 0.12에 risk-gated reviewer requirement; 모든 run 강제는 불필요 |
| **R-6 review 파일 신원** | **남음. 자기 정정이 맞음** | 신규 run은 UUID-keyed directory/path, 구 flat 파일은 legacy residual |
| **R-7 verification environment** | **부분 개념화됐지만 계약은 없음** | 0.12 필수: verification plan과 capability preflight |
| **R-8 E-09 범위** | **남음** | 0.12에서 durable identity와 scoped ambient observation을 구분하도록 개정 |

---

# Confirmed findings

## JW-GPT-016 — coordinator control plane에 contract readiness·retry ceiling·review requirement가 없다

**Severity: major**

### 실패 메커니즘

새 구조에서도 coordinator는 scope, plan, acceptance를 고정하는 책임을 가집니다. ADR-0008은 이를 명시하지만, acceptance 자체가 달성 가능한지, 범위가 닫혔는지, 검증되지 않은 기준을 참조하는지는 검증하지 않습니다. I-01도 owner intent와 acceptance의 **우선순위**만 규정할 뿐 acceptance의 품질 조건은 규정하지 않습니다. fileciteturn106file0L53-L66 fileciteturn107file0L18-L20

그 결과 coordinator가 다음과 같은 조항을 만들 수 있습니다.

- 원리적으로 관측 불가능한 결과를 요구
- 다른 subsystem의 안전성이 검증됐다고 전제
- cycle·round·path 같은 적용 범위를 생략
- 구현 방식을 결과 성질처럼 오인
- 만족 여부를 판정할 evidence source를 지정하지 않음

이 상태에서도 engine은 잘 형식화된 job으로 dispatch할 수 있습니다. 이후 각 실패는 새 attempt·새 action으로 정직하게 기록될 수 있지만, ADR-0002는 **재시도의 안전한 기계**만 정의하고 “언제 더 이상 retry를 계획하지 않는가”는 정하지 않습니다. fileciteturn98file0L78-L88 실제 운영에서도 두 lane이 네 번씩 진행되며 finding 수와 patch 크기가 증가했지만 모든 기계적 gate는 green이었습니다. fileciteturn114file0L23-L32

마지막으로 reviewer 역할은 “run 수준 architecture·domain quality 평가”로 정의됐지만, 어떤 run이 reviewer evidence를 요구하는지와 completion gate에 어떻게 결속되는지는 정해지지 않았습니다. fileciteturn106file0L57-L62 현재 확정 ruling은 기본 `review_policy=off`이므로 trust-critical 변경도 verifier와 테스트만으로 완료될 수 있습니다. fileciteturn111file0L7-L14

### 필수 수정

세 부분을 하나의 **run-spec readiness contract**로 추가하는 것이 적절합니다.

#### 1. Acceptance contract readiness

자유 문장을 금지할 필요는 없습니다. 대신 coordinator가 합성한 criterion은 최소한 다음 구조를 가져야 합니다.

```text
claim/property
source pointer
subject scope
observable evidence kind
negative/failure case
explicit method constraint 여부
```

dispatch 전 두 층을 통과시킵니다.

- **결정론 검사:** source 존재, scope 지정, evidence adapter 존재, 중복·빈 criterion, 참조 대상 유효성
- **독립 contract critic:** `unachievable`, `unbounded`, `unverified-reference`, `scope-ambiguous`, `implementation-prescriptive`를 typed concern으로 반환

critic은 criterion을 자동 재작성하거나 구현법을 지시하지 않습니다. coordinator가 concern을 해소해 새 frozen run spec을 발행합니다. 이는 worker의 창의성을 억제하지 않습니다. 모델의 구현 자유가 아니라 **control-plane input의 품질**을 심사하는 단계입니다.

owner가 직접 작성한 명시적 criterion에는 critic을 선택적으로 둘 수 있지만, autonomous mode에서 coordinator가 합성한 criterion에는 필수로 두는 것이 좋습니다.

#### 2. Retry와 수렴 한계

run spec에 다음을 freeze해야 합니다.

```text
max_attempts_per_job
max_total_attempts
time/cost budget
retryable failure classes
budget exhaustion policy
```

budget이 끝나면 자동 연장하지 않고:

```text
waiting_user(reason=retry-budget-exhausted)
waiting_user(reason=lane-not-converging)
```

으로 전이합니다. 이는 “routine 질문 0” 위반이 아닙니다. 정상 흐름의 질문이 아니라 명시적으로 열거된 hard escalation입니다.

finding 수 증가, patch 증가, 동일 criterion 반복 실패 등의 trajectory scoring은 0.12에서는 **advisory health**로만 두는 편이 낫습니다. 자동 correctness 판정으로 쓰는 것은 아직 근거가 부족합니다. 정교한 convergence heuristic은 0.13 이후 실제 run data로 조정할 수 있습니다.

#### 3. Risk-gated adversarial review

모든 run에 적대 리뷰를 강제할 필요는 없습니다. 대신 frozen run spec에 다음을 둡니다.

```text
review_requirement: none | required
review_reason: <typed code>
```

project policy나 coordinator가 trust-critical 변경을 `required`로 고정하면, integrated result digest에 결속된 reviewer evidence 없이는 해당 run을 완료로 만들지 못해야 합니다. 자동으로 trust surface를 분류하는 일반화된 risk classifier는 후속 버전으로 미뤄도 되지만, **required review를 FSM이 실제 gate로 소비하는 구조**는 0.12에 있어야 합니다.

Waystone 자체에서는 store, review binding, merge gate, migration, sandbox, evidence authority를 건드리는 task에 이 정책을 적용하면 됩니다.

---

## JW-GPT-017 — canonical project identity와 active worktree identity가 분리되지 않았다

**Severity: major**

### 실패 메커니즘

ADR-0007은 기본 DB 위치를 project-local `.waystone/state.db`로 확정합니다. 그러나 “project root”가 canonical registered project인지, 현재 cwd에서 발견한 linked-worktree root인지 정의하지 않습니다. fileciteturn105file0L17-L23

현행 CLI의 root resolver는 명시적 `--root`가 없으면 `Path.cwd()`에서 `find_project_root()`를 호출합니다. 따라서 linked worktree 안에서 실행하면 그 worktree가 project root가 됩니다. fileciteturn83file0L3-L8 실제로 task mutation이 linked worktree의 `tasks.yaml`을 수정하고 project state migration까지 일으킨 사고가 두 번 발생했습니다. fileciteturn113file0L22-L28

0.12에서 동일한 해석을 사용하면 사고가 더 조용해집니다.

```text
main checkout/.waystone/state.db
linked worktree/.waystone/state.db
```

가 따로 만들어질 수 있고, 한쪽에서는 run이 진행 중인데 다른 쪽에서는 존재하지 않는 것처럼 보입니다. `status`, claim uniqueness, cancellation, artifact GC까지 분기될 수 있습니다. 단순 YAML 오염보다 훨씬 깊은 authority split입니다.

### 필수 수정

M0 계약에 다음 domain object를 추가해야 합니다.

```text
ProjectContext
  project_id
  canonical_root
  active_worktree_root
  git_common_dir
  checkout_identity
```

권장 규칙은 다음과 같습니다.

- `project_id`와 runtime DB 위치는 **등록된 canonical project**에 결속한다.
- linked worktree는 별도의 project가 아니라 같은 project의 checkout context다.
- read-only `status`·`inspect`는 linked worktree에서도 canonical DB로 정규화한다.
- task/config/consent처럼 project intent를 변경하는 command는 noncanonical linked worktree에서 기본 거부한다.
- linked worktree를 run input으로 의도적으로 사용할 때만 `--from-worktree` 또는 동등한 명시적 selector를 요구한다.
- Waystone-owned worker/integration worktree에서는 project-intent mutation을 항상 거부한다.
- canonical mapping을 확정할 수 없을 때 main worktree를 추측하지 않고 typed refusal한다.

모든 사용자에게 `--root`를 요구할 필요는 없습니다. 정상적인 canonical checkout에서는 현재 UX를 유지하고, **위험한 linked-worktree context에서만 명시성을 요구**하면 됩니다.

ADR-0005와 ADR-0007 모두 이 구분을 반영해야 합니다. 현재의 “active project”와 “project-local”만으로는 충분하지 않습니다.

---

## JW-GPT-018 — review evidence의 신원이 store key로 이전된다는 M1-B 주장은 성립하지 않는다

**Severity: major**

### 실패 메커니즘

자기 정정 R-6이 맞습니다.

`docs/known-issues.md`는 JW-GPT-015 부류가 M1-B에서 “신원이 파일명이 아니라 store key”가 되므로 재현 불가능해진다고 기록합니다. fileciteturn108file0L82-L90 그러나 0.12 계약은 review request/reply/binding의 authority를 계속 Git-tracked 파일에 둡니다. 현재 ADR 집합은 runtime DB identity와 Git fact authority를 구분하지만, 새 review artifact의 owner identity/path grammar는 정의하지 않습니다. Git evidence가 계속 flat filename으로 owner를 표현한다면 기존 delimiter ambiguity는 자동으로 사라지지 않습니다.

JW-GPT-015는 의도적 crafted filename만의 문제가 아닙니다. 정상적인 round ID가 `-freeze-`를 포함할 수 있어 두 정상 ID 사이에 prefix collision이 생기는 문제이며, 이는 확정된 위협모델에서도 보호 대상으로 남아 있습니다. 현재 known-issues도 정상 PR-mode에서 다른 round의 파일이 healthy round를 차단할 수 있음을 인정합니다. fileciteturn108file0L47-L65

### 필수 수정

질문에 제시한 **(b)+(c)** 조합이 적절합니다.

#### 신규 0.12 artifact

새 run은 ADR-0005가 정한 canonical UUIDv7 `run_id`를 이미 가집니다. fileciteturn103file0L35-L41 이를 owner directory로 사용합니다.

예:

```text
docs/reviews/runs/<run-uuid>/
  request.md
  request.binding.json
  feedback.md
  pr-freeze/<cycle>.json
  pr-demotion/<observation-id>.json
```

핵심은 filename을 오른쪽이나 왼쪽에서 delimiter로 분해하여 owner를 추측하지 않는 것입니다. directory segment의 UUID grammar와 payload의 `run_id`가 일치해야 합니다.

#### 기존 artifact

기존 flat `YYYY-MM-DD-...-freeze-...` 파일은 bulk migration하지 않고 legacy adapter가 판독합니다. JW-GPT-014·015는 **legacy PR-mode residual**로 남길 수 있습니다. 0.12 writer는 새 layout만 발행하고, reader는 신·구를 모두 지원합니다.

이는 PR review의 의미론을 재설계하는 것이 아니라 **artifact addressing을 명확히 하는 strangler migration**입니다.

새 layout을 0.12 범위에 넣지 않기로 한다면, 최소한 계획서와 known-issues의 “015 부류 구조적 소멸” 주장을 제거하고 legacy residual로 명시해야 합니다. 현재 문구를 유지하는 것은 사실과 맞지 않습니다.

---

## JW-GPT-019 — required verification을 실행할 수 있는 환경이 dispatch precondition이 아니다

**Severity: major**

### 실패 메커니즘

E-07은 verifier artifact가 자신이 보지 않은 result digest를 승인하지 못하게 하지만, verifier나 deterministic check가 **실제로 실행 가능해야 한다**는 precondition은 규정하지 않습니다. fileciteturn107file0L36-L38

실제 운영에서는 8개 delegation 전부 worker worktree에서 전체 suite와 lint를 실행하지 못했고, 별도 major task로 등록됐습니다. fileciteturn113file0L15-L21 coordinator가 main checkout에서 대신 실행했기 때문에 결과가 보완됐지만, autonomous run에서는 다음과 같이 퇴화할 수 있습니다.

```text
worker self-check 불가
→ limitation만 기록
→ coordinator/engine의 ad hoc check 또는 check 생략
→ “독립 검증”이 실제로는 수행되지 않았거나 단일 actor 검증으로 축소
```

ADR-0004의 engine executor 경계는 deterministic checks를 engine-owned action으로 둘 수 있는 기반은 제공하지만, required verification plan과 environment capability gate를 요구하지는 않습니다. fileciteturn102file0L17-L25

### 필수 수정

run/job spec에 **verification plan**을 freeze해야 합니다.

```text
required checks
command/input digest
required toolchain
environment preparation
network/cache requirements
sandbox level
verifier backend capability
```

dispatch 전 engine이 다음을 확인합니다.

1. required deterministic check를 engine-owned environment에서 실행할 수 있는가
2. required independent verifier를 사용할 수 있는가
3. 환경 준비가 재현 가능하고 기록 가능한가
4. RED-first가 acceptance의 일부라면 base snapshot에서 해당 RED를 생성할 수 있는가

불가능하면:

```text
waiting_user(reason=verification-environment-unavailable)
refused(reason=required-check-unexecutable)
```

로 두며, 조용히 worker self-report나 coordinator manual check로 강등하지 않습니다.

worker가 자기 worktree에서 테스트를 실행하는 것은 유용하지만 계속 **worker claim**입니다. 권위 있는 deterministic check는 engine이 격리된 job/integration worktree에서 실행하고 exact command·exit·artifact를 기록하면 됩니다. 이 방식은 verifier 독립성을 약화하지 않습니다. 오히려 구현자의 자기보고와 검증 사실을 분리합니다.

명시적 waiver는 가능하더라도 어떤 required verification이 생략됐는지와 누가 결정했는지를 decision artifact에 기록해야 합니다.

---

## JW-GPT-020 — E-09가 durable identity와 scoped ambient observation을 구분하지 못한다

**Severity: major**

### 실패 메커니즘

현재 E-09는 권위·귀속을 mtime, inode, directory stat 같은 **filesystem metadata**에 결속하지 않는다는 규칙입니다. fileciteturn107file0L38-L38 그러나 실제 probe fingerprint에는 hostname이 machine 축으로 들어가 있고, network/DHCP 변경만으로 proof가 무효화되는 문제가 별도 task로 등록됐습니다. fileciteturn111file0L35-L40 즉, 이미 관측된 세 번째 사례가 확정 불변조건의 문자 범위 밖입니다.

반대로 ambient 값을 전면 금지하면 ADR-0003의 다음 값도 사용할 수 없습니다.

- boot identity
- PID
- process start token
- monotonic time

이들은 ambient이지만, process identity와 liveness를 **한 boot epoch 안에서** 판정하는 데 정당하게 사용됩니다. fileciteturn100file0L141-L161

### 필수 수정

E-09를 filesystem-specific 금지에서 다음 원칙으로 일반화해야 합니다.

> **Durable identity·ownership·attribution·evidence ordering은 대상과 독립적으로 변할 수 있는 incidental ambient 값에 결속하지 않는다. Ambient 값은 명시된 observation scope와 lifetime 안에서 locator 또는 freshness evidence로만 사용할 수 있으며, scope 밖에서는 durable identity로 승격하지 않고 unknown으로 강등한다.**

세 범주를 ADR에 정의하면 경계가 선명해집니다.

| 범주 | 예 | 사용 |
|---|---|---|
| **Durable intrinsic identity** | UUID, content digest, Git object ID, 안정적 host identity | 장기 신원·귀속·결속에 사용 |
| **Scoped ephemeral evidence** | boot ID + PID + process start token, monotonic clock | 명시된 boot/process lifetime 안의 관측·freshness에 사용 |
| **Incidental ambient value** | hostname, cwd, mtime, directory enumeration order | 진단·표시에만 사용; durable authority 금지 |

판단 기준은 다음과 같습니다.

1. 유효 scope와 lifetime이 계약에 명시됐는가
2. 값이 변하면 실제 대상 identity 또는 observation epoch도 변한 것인가
3. 사용 시점에 재관측 가능한가
4. scope 밖에서 unknown으로 강등되는가
5. 더 안정적인 intrinsic identifier가 있는데 중복 신원축으로 쓰고 있지 않은가

따라서 boot ID와 PID 조합은 정당하지만 hostname은 진단으로 강등해야 합니다. `cwd`도 project identity가 아니라 locator일 뿐이며, 이는 R-3 수정과 직접 연결됩니다.

---

# R-2에 대한 별도 판정 — broad guarantee gap은 아님

R-2의 관찰 자체는 사실입니다. engine 밖에서 임의로 실행한 shell 명령은 계속 조용히 no-op할 수 있습니다. 그러나 이를 모두 Waystone이 보장하려 하면 shell wrapper, command interception, 새로운 prompt protocol이 필요해지고 제품 경계가 무너집니다.

ADR-0002는 engine action에 대해 external effect를 재관측한 뒤에만 완료하도록 이미 규정합니다. fileciteturn98file0L23-L38 ADR-0004도 engine/carrier/user action의 실행 책임을 고정하고 다른 executor의 silent fallback을 금지합니다. fileciteturn102file0L17-L25 따라서 **run 안에서 발생하는 routine merge·integration·push는 이미 engine action으로 내려야 하고**, 그 경우 이번 `git merge --squash` 사고 부류는 ADR-0002가 잡습니다.

남은 계약은 한 문장입니다.

> Engine 밖의 unmanaged mutation은 run action의 성공이나 authority evidence가 될 수 없다. Engine이 해당 effect를 권위 채널에서 재관측하고 현재 action input·fencing·expected state에 reconcile하기 전에는 run progress나 completion으로 승격하지 않는다.

이 규칙을 ADR-0002 또는 ADR-0004에 추가하면 충분합니다.

별도의 범용 `waystone verify merged <ref>` 명령은 필수적이지 않습니다. out-of-band 변경이 run worktree에 나타나면 engine이 drift를 발견하여 typed reconciliation action을 만들면 됩니다. 분석, 임시 probe, 하네스 버그 우회처럼 완전히 engine 밖에서 한 작업은 명시적으로 **unmanaged / no guarantee**입니다.

`unmanaged`를 네 번째 `executor_kind`로 만들지는 않는 편이 좋습니다. 이는 executor가 아니라 Waystone의 권위 밖이라는 뜻입니다.

---

# 메타 질문에 대한 견해

## 조정자 실수는 막을 대상인가, 회수할 대상인가

둘 다이지만 경계가 다릅니다.

### 모델 내부의 사고 과정

규율을 최소화해야 합니다.

- 해법 탐색
- decomposition 후보
- 구현 전략
- domain reasoning
- alternative 비교

이 부분을 harness prompt로 촘촘히 묶으면 모델 고유의 능력을 잃습니다.

### 모델이 시스템 권위에 제출하는 control-plane output

자유로운 주장으로 취급하면 안 됩니다.

- frozen run spec
- acceptance criteria
- retry 제안
- review requirement
- delivery decision
- manual effect receipt
- waiver

이들은 **proposal**이며 engine fact가 아닙니다. schema, provenance, bounded critic, capability check, expected postcondition을 통과한 뒤에만 권위 상태로 commit해야 합니다.

따라서 적절한 모델은 다음과 같습니다.

```text
coordinator = 창의적인 planner + untrusted control-plane proposer
engine      = validator + recorder + effect owner
reviewer    = independent semantic challenger
```

이는 모델을 특수 prompt에 묶는 방향이 아닙니다. 모델의 사고는 자유롭게 두고 **외부 세계를 바꾸는 경계만 typed**로 만드는 방향입니다.

계획은 이미 live-tree 불변, immutable attempt, observed effect, cancellation safety를 통해 회수 가능성을 강하게 설계했습니다. 부족한 부분은 coordinator output 중 무엇이 authority boundary인지 완전히 열거하지 않았다는 점입니다. R-1, R-2, R-4, R-5가 그 누락을 각각 다른 방향에서 보여줍니다.

---

# 처분 권고

## 0.12 범위에 편입

1. **Contract-readiness gate** — R-1  
2. **Canonical project/worktree identity 계약** — R-3  
3. **Attempt·time·cost ceiling과 typed nonconvergence escalation** — R-4  
4. **Run-spec review requirement와 integrated-result binding** — R-5  
5. **UUID-keyed 신규 review artifact path** — R-6  
6. **Verification plan + environment capability preflight** — R-7  
7. **E-09의 durable/scoped/incidental 구분** — R-8  
8. **Unmanaged effect는 authority로 승격 불가**라는 ADR 문구 — R-2  

이 항목들은 전부 대형 구현을 즉시 요구하지 않습니다. M0에서는 계약과 acceptance만 고정하면 되고, 구현은 M1-B·M2에 배치할 수 있습니다.

## 0.13+로 이월

- finding 추세·patch growth를 결합한 자동 convergence scoring
- 일반 프로젝트용 trust-surface 자동 분류기
- acceptance critic의 과거 정확도 측정과 adaptive threshold
- legacy flat review artifact의 bulk migration
- arbitrary shell command의 generic postcondition inference

## 명시적으로 수용할 잔여

- engine 밖 unmanaged shell의 성공 여부 자체
- legacy PR-mode flat review artifact의 기존 014·015
- 의도적 crafted filename과 로컬 write 권한자가 수행하는 변조
- 다른 머신에서 진행 중인 nonterminal run의 liveness

단, 이 잔여가 run authority나 completion으로 조용히 승격되는 것은 수용 대상이 아닙니다.

---

# Open domain questions

1. **Contract critic 의무 범위**  
   권고는 coordinator가 합성한 criterion + autonomous multi-job run에 필수, owner가 직접 작성한 one-task criterion에는 선택입니다.

2. **기본 attempt budget**  
   계약에는 반드시 있어야 하지만 숫자는 project profile로 결정할 수 있습니다. Waystone 자체에는 `3 attempts/job`, 전체 run ceiling 별도 정도가 현재 운영 근거와 맞습니다. 3회 이후 확장은 명시적 새 decision이어야 합니다.

3. **Review artifact path**  
   권고는 escaping된 flat filename보다 `docs/reviews/runs/<uuid>/` directory입니다. owner parser가 delimiter를 해석할 이유 자체가 없어집니다.

4. **Risk-gated review policy**  
   0.12에서는 project-defined path/rule과 coordinator의 frozen `review_requirement`만 지원하고, 범용 자동 risk classifier는 이월하는 편이 적절합니다.

---

# Residual risks and review limitations

- 이번 검토는 target commit의 ADR-0002~0008, `docs/invariants.md`, `docs/known-issues.md`, `PROGRESS.md`, `tasks.yaml`, review request를 정적으로 대조한 설계 리뷰입니다. 테스트나 실제 runner·GitHub roundtrip은 실행하지 않았습니다.
- request가 참조하는 r5 계획 본문은 `dev_docs/`에 있어 target Git tree에서 직접 읽을 수 없었습니다. 대화에 첨부된 본문은 r4이며, r5 변경은 request·PROGRESS·ADR를 권위로 재구성했습니다. fileciteturn90file0
- `.waystone/delegations/*`의 로컬 contract·verdict artifact는 connector에서 접근할 수 없으므로, 8회 attempt의 세부는 committed `PROGRESS.md`, task notes, request의 evidence table을 근거로 판정했습니다.
- GPU나 별도 dataset은 이 리뷰에 필요하지 않았습니다.

# 최종 판정

M0 contracts의 core runtime 설계는 승인 가능한 수준이지만, **M0-B 완료 및 invariants 확정 선언은 아직 이릅니다.**

특히 아래 네 항목은 M0-C exit 전에 반드시 계약에 반영되어야 합니다.

1. canonical project/worktree identity  
2. 신규 review artifact identity/path  
3. verification capability preflight  
4. E-09 ambient identity 일반화  

contract readiness, retry ceiling, risk-gated reviewer requirement도 M0 문서에 추가하되 구현은 M1-B/M2로 배치할 수 있습니다.

가장 중요한 수정 원칙은 다음입니다.

> **조정자의 창의성을 규율하지 말고, 조정자가 권위 경계에 제출하는 산출물을 검증하라.**

---

<!-- waystone triage: BEGIN -->
## Findings (triage skeleton — verify each before registering)

리뷰어 = chatgpt:gpt-5.6-pro (요청서 digest 결속 확인, 경고 0). 판정: CHANGES REQUESTED, major 5.
main 세션이 각 finding을 repo에서 직접 확인한 뒤 등록했다.

| finding | severity | type | verdict | evidence | task id |
|---|---|---|---|---|---|
| JW-GPT-016 — coordinator control plane에 contract readiness·retry ceiling·review requirement가 없다 | major | architecture | REAL | 직접 확인: `docs/invariants.md:16`의 I-01은 owner intent와 acceptance의 **우선순위만** 규정하고 품질 조건은 없음. `ADR-0008:57`은 coordinator가 "acceptance를 고정한다"고만 정의. 계획서·ADR 전체에서 달성가능성/범위닫힘/미검증기준 관련 개념 **0건**. round-6 실측이 이를 뒷받침 — 기각 12건 중 3건이 조항 결함(미검증 기준 채택·달성 불가 요구·범위 미기재로 인한 과잉 demotion 유발) | feat/run-spec-readiness-contract |
| JW-GPT-017 — canonical project identity와 active worktree identity가 분리되지 않았다 | major | architecture | REAL | 직접 확인: `canonical_root`·`active_worktree`·`project_id`·`linked worktree` 어느 것도 ADR 8종·계획서에 **0건**. ADR-0007은 DB를 project-local `.waystone/state.db`로 두되 root 해석 규칙을 정의하지 않음 → linked worktree에서 실행되면 그쪽 DB를 열게 됨. 이 세션에서 registry 오배선이 **2회** 발생(YAML 오염 + pre-0.9 migration 유발)했고, 0.12에서는 runtime 상태 전체가 다른 DB에 쌓이는 형태로 **악화**된다 | feat/canonical-project-identity |
| JW-GPT-018 — review evidence의 신원이 store key로 이전된다는 M1-B 주장은 성립하지 않는다 | major | reporting | REAL | 직접 확인: 과잉 주장이 **두 곳**에 존재 — `dev_docs/0.12.0-refactor-plan.md:636`, `docs/known-issues.md:86`. 계획 §2-1·§5-2는 리뷰 증거를 git-tracked 파일로 유지하므로 store 키가 신원을 대체하는 것은 runtime record뿐. R-6 자기 정정이 맞다고 확인됨. **또한 정상 round id 간 prefix 충돌은 crafted filename이 아니므로 확정된 위협모델(우발적 손상만 방어) 안에서도 보호 대상으로 남는다** | feat/review-artifact-addressing |
| JW-GPT-019 — required verification을 실행할 수 있는 환경이 dispatch precondition이 아니다 | major | verification | REAL | 직접 확인 + 자체 실측: 이 세션의 위임 **8회 전부**에서 러너가 worktree-local uv 캐시에 pyyaml·ruff 부재로 전체 스위트·lint를 실행 못 함(각 contract.yaml의 `limitations`·`escalations`). 015 attempt-1은 **RED 단계조차** 실행 실패. 계획 M2는 "env 정규화"를 fleet 규칙으로 언급하나 **worker 환경의 검증 수행 능력을 dispatch 전 확인하는 계약은 없음**. E-07·M2-3의 독립 검증은 검증이 실제로 수행 가능함을 전제하며, 전제가 깨지면 조용히 조정자 단독 검증으로 퇴화 | feat/verification-capability-preflight |
| JW-GPT-020 — E-09가 durable identity와 scoped ambient observation을 구분하지 못한다 | major | architecture | REAL | 직접 확인: `docs/invariants.md:36`의 E-09는 "mtime/ctime/inode/디렉터리 stat/열거 순서"로 **파일시스템 메타데이터에 한정** → 이 세션에서 발견한 세 번째 사례(probe의 `machine` 축 = hostname, 네트워크 이동 시 증명 무효화)를 못 잡음. **추가 관찰(리뷰어 미지적)**: E-09는 "판정 근거는 파일 내용·**파일명**·git-tracked 사실에서만 나온다"고 파일명을 정당한 근거로 명시하는데, 이는 JW-GPT-018이 요구하는 "filename delimiter 분해로 owner를 추측하지 않음"과 **정면 충돌**한다. 두 finding은 함께 개정해야 한다 | docs/e09-durable-identity-scope |

**R-2 판정(별도)**: 리뷰어는 "임의 수동 shell 행위를 waystone이 보장해야 한다"는 주장은 성립하지 않되, 그 행위가 **run의 authoritative state로 승격되는 경계**에는 engine 재관측이 필요하다고 판정. main도 동의 — 별도 task 없이 JW-GPT-016의 readiness 계약과 ADR-0002의 `observed` 규칙이 그 경계를 덮는다.

**M0-C 게이팅**: 리뷰어 권고 — M0-C의 inventory·ledger 작업은 착수 가능하나 `gate/characterization-baseline` **exit는 위 계약 수정 전 통과시키지 않는다.** 특히 JW-GPT-018의 잘못된 구조적 해소 주장을 남겨두면 M0-C가 그 모순을 다음 구현의 전제로 고정한다. main 동의.
<!-- waystone triage: END -->
