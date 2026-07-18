<!-- waystone feedback: the body below is the reviewer reply VERBATIM (byte-exact copy via `waystone review ingest`) — do not edit it; a triage skeleton is appended beneath it. -->
round: 2026-07-18-carrier-lanes-fixes
reviewer: chatgpt:gpt-5.6-pro
ingested: 2026-07-18
source: /tmp/review.md

---

```text
model: gpt-5.6-pro
effort: xhigh
review-target: 4c042031af9fe1722676de8bbe41fccba5464b30
```

## 판정

**CHANGES REQUESTED — Critical 0 / Major 4**

코드 계약상 `JW-GPT-001`, `002`, `003`은 닫혔습니다. 그러나 `JW-GPT-004`와 승격된 Q1은 완전히 해소되지 않았습니다. 추가로 reprepare 트랜잭션과 legacy fallback에서 두 개의 fail-open 경로가 확인됩니다.

## 직전 5건 상태

| 항목             | 판정               | 요약                                                                                                                                            |
| -------------- | ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `JW-GPT-001`   | **resolved**     | 정확한 upstream branch를 명시 refspec으로 전용 임시 ref에 fetch하고, 그 SHA만 사용합니다. `.` remote와 cleanup 실패도 거부됩니다.                                            |
| `JW-GPT-002`   | **resolved**     | digest와 implementer prompt가 동일한 `_registry_task_prompt_lines()` 투영을 공유하며 `milestone`, `round`, `anchor`, `notes`, deps, acceptance가 모두 들어갑니다. |
| `JW-GPT-003`   | **resolved**     | filename sequence로 최신 후보를 먼저 고르고 그 후보가 corrupt이면 이전 binding으로 폴백하지 않습니다. Sidecar publish도 완전 기록 후 hard-link 방식으로 바뀌었습니다.                      |
| `JW-GPT-004`   | **still-broken** | 이미 ingest된 A 뒤 B를 prepare하는 경우는 고쳤지만, delayed A reply가 B 이후 ingest되는 순서와 정확한 rendered-request revision 결속은 남아 있습니다.                           |
| Q1 probe proof | **still-broken** | 커밋 전파는 막았지만 marker는 checkout-local일 뿐 machine/runtime-bound가 아닙니다.                                                                            |

---

## Confirmed findings

### JW-GPT-004 — reviewer가 실제로 본 request revision이 여전히 결속되지 않음

* Severity: major

#### 실패 메커니즘 A: A 회신을 B binding으로 ingest-time 재도장

회신 헤더에는 narrative 또는 request digest가 없습니다. `ingest()`는 회신이 무엇을 보고 작성됐는지 증명받지 않고, **ingest 시점의 최신 binding**을 읽은 뒤 그 binding의 `narrative_digest`를 feedback metadata에 복사합니다.

따라서 다음 순서에서 잘못 완료됩니다.

1. request A를 prepare하고 reviewer에게 전달한다.
2. 회신이 도착하기 전에 같은 target으로 request B를 reprepare한다.
3. A를 보고 작성된 회신이 뒤늦게 도착한다.
4. ingest는 회신 자체가 아니라 현재 B binding의 digest를 도장한다.
5. pending은 target과 도장된 digest가 B에 맞으므로 완료로 처리한다.

pending의 완료 조건은 바로 이 ingest-time stamp를 신뢰합니다.  이 경로는 요청서에도 알려진 잔여로 명시돼 있습니다.

#### 실패 메커니즘 B: exact rendered request bytes가 binding에 없음

Binding에는 narrative digest만 들어가고 rendered request 또는 template/exposure digest는 들어가지 않습니다.  렌더러는 호출 시점의 live `templates/review-request.md`를 다시 읽으며, exposure 교차검증도 `head/base/reviewers/mode`만 비교해 `project.name`과 `project.branch`를 결속하지 않습니다.

그 결과 동일 target·동일 narrative digest에서 다음이 가능합니다.

1. V1 request에 대한 feedback이 완료된 상태다.
2. template의 static text 또는 exposure의 미결속 project 필드를 변경한다.
3. request를 V2 렌더와 일치하도록 갱신해 remote에 게시한다.
4. publication gate는 **원래 prepare된 V1**이 아니라 현재 live 입력으로 재렌더한 V2와 비교하므로 통과한다.
5. binding target과 narrative digest는 변하지 않았으므로 기존 feedback은 계속 완료로 계산된다.

즉 현재 계약이 증명하는 것은 “지금의 local template/exposure로 재현된다”이지, “이 binding이 처음 발행한 exact request revision이다”가 아닙니다.

**필수 수정.**

* 새 binding schema에 `rendered_request_digest`를 필수로 추가해야 합니다.
* reviewer reply가 `request-digest`를 직접 echo하도록 해야 합니다.
* 그 계약이 도입되기 전에는 동일 target reprepare를 허용하지 말고 새 round ID 또는 새 review target을 요구해야 합니다.
* Template과 렌더에 사용되는 exposure fields도 rendered digest를 통해 간접적으로 결속되어야 합니다.

---

### JW-GPT-005 — reprepare 중 프로세스 종료가 B request를 A의 완료 증거 뒤에 숨김

* Severity: major

**실패 메커니즘.** Reprepare는 다음 순서로 파일을 갱신합니다.

1. request 파일 B 기록
2. stored narrative B 기록
3. 마지막에 binding B 생성

기존 A binding과 A feedback이 이미 완료된 상황에서 1번 또는 2번 이후 프로세스가 종료되면:

```text
request.md          = B
stored narrative    = B 또는 A
latest binding      = A
feedback            = A
```

가 됩니다. Sidecar 자체는 crash-atomic하지만, **request+narrative+binding이라는 generation 전체는 atomic하지 않습니다**.

`pending_reviews()`는 현재 request나 stored narrative를 최신 binding으로 재현하지 않습니다. A binding과 A feedback만 일치하면 round를 결과에서 제거합니다.  따라서 디스크에 B request가 있는데도 `review pending`과 statusline은 완료라고 표시합니다.

Publication gate를 나중에 다시 실행하면 불일치를 잡을 수 있지만, pending 완료 판정 자체가 이미 fail-open입니다. 해당 gate의 재실행은 ingest/pending의 전제조건도 아닙니다.

**필수 수정.**

새 binding을 먼저 발행하여 기존 feedback을 무효화한 뒤 request와 narrative projection을 갱신해야 합니다. 더 강한 방법은 generation directory를 완성한 뒤 현재-generation pointer를 atomic switch하는 것입니다. 어느 방식을 쓰든 pending은 완료를 숨기기 전에 request+narrative가 최신 binding에서 재현되는지 확인해야 합니다.

필요한 RED:

```text
prepare A → ingest A → reprepare B
→ request write 직후 강제 종료
→ pending에는 반드시 해당 round가 남아야 함
```

stored narrative write 직후 종료도 별도 계약으로 고정해야 합니다.

---

### JW-GPT-006 — 신규 digest binding을 ingest 전에 legacy로 downgrade할 수 있음

* Severity: major

**실패 메커니즘.** `narrative_digest`가 없는 binding은 여전히 같은 `waystone-round-request-binding-1` schema의 유효한 레코드로 허용됩니다. 즉 genuinely old legacy binding과 digest를 제거한 신규 binding을 구조적으로 구분할 수 없습니다.

다음 순서로 claim 5를 우회할 수 있습니다.

1. 정상적인 digest-bound request와 binding을 게시하고 publication gate를 통과한다.
2. 회신 ingest 전에 로컬 최신 binding JSON에서 `narrative_digest`만 제거한다.
3. `ingest()`는 현재 binding에 digest가 없으므로 feedback에도 digest를 기록하지 않는다.
4. `_assess_narrative_digest()`는 양측에 digest가 없다는 이유만으로 이를 `legacy-pre-digest`로 분류한다.
5. pending은 `legacy-pre-digest`를 정상 완료 조건으로 인정한다.

기존 테스트는 **feedback이 이미 digest로 도장된 뒤 binding digest만 제거하는 경우**만 검사합니다.  Digest 제거가 ingest 전에 일어나면 feedback stamp 자체가 생성되지 않아 fallback이 성공합니다.

Publication gate가 digestless binding을 거부하는 것은 이 경로를 닫지 못합니다. Gate는 요청 발송 전에 이미 성공했을 수 있고, ingest는 remote publication evidence를 다시 확인하지 않기 때문입니다.

**필수 수정.**

* Digest-capable binding은 별도 schema, 예를 들어 `waystone-round-request-binding-2`로 승격하고 `narrative_digest`와 `rendered_request_digest`를 필수 필드로 만들어야 합니다.
* `binding-1`만 legacy로 읽고, `binding-2`에서 digest가 없으면 corrupt로 처리해야 합니다.
* 현재 schema를 유지하려면 최소한 exposure/tool version 등 제거 불가능한 별도 provenance로 genuine legacy 여부를 결정해야 하지만, schema 분리가 더 명확합니다.
* Ingest는 이미 digest-capable한 round/exposure의 digestless binding을 거부해야 합니다.

---

### Q1 — probe proof는 커밋 비추적이지만 machine/runtime-bound가 아님

* Severity: major

커밋된 config key와 git-tracked marker를 무시하도록 바뀐 점은 유효한 개선입니다. 그러나 실제 marker는 고정 문자열 `verified\n` 하나이며, 파일이 현재 index에 tracked되지 않았다는 사실과 그 문자열만으로 proof를 인정합니다.

Marker가 유효하면 probe는 즉시 생략됩니다.  다음 값은 결속되지 않습니다.

* machine 또는 host identity
* resolved `codex` executable 및 version
* OS/kernel과 sandbox implementation
* sandbox policy version
* worktree cache filesystem/mount 특성

따라서 다음 두 경로가 남습니다.

1. NFS/shared checkout 또는 `.waystone`까지 포함한 checkout 복사에서 머신 A의 untracked marker가 머신 B로 이동하면, 머신 B에서도 `git ls-files`는 빈 결과이고 내용은 `verified\n`이므로 probe를 생략합니다.
2. 동일 checkout에서 Codex binary, kernel 또는 sandbox policy가 바뀌어도 marker가 그대로 유지되어 재프로브하지 않습니다.

이는 repository-scoped proof 전파는 막지만, 직전 Q1에서 요구한 machine/runtime scope는 충족하지 못합니다.

**필수 수정.**

Marker를 versioned JSON 계약으로 만들고 최소한 다음 fingerprint를 포함해야 합니다.

```text
proof_schema
resolved_codex_path
codex_version
platform / kernel
sandbox_policy_version
worktree_cache_device_or_mount_identity
```

현재 환경의 fingerprint와 exact-match할 때만 probe를 생략해야 합니다. Checkout-local 위치는 유지할 수 있지만, 위치만으로 machine isolation을 주장하면 안 됩니다.

---

## Open domain questions

직전 Q2는 더 이상 open question으로 남길 필요가 없습니다. Release script가 동시 checkout을 지원 범위 밖으로 명시하고 CAS가 보호하는 범위를 정확히 제한했습니다.  이는 코드 동시성 해결이 아니라 **single-user, single-process 위협모델 확정**으로 해소된 것으로 판단합니다.

Q1은 domain question이 아니라 위의 confirmed Major입니다.

## Residual risks from unavailable environment

GitHub connector에서 target commit에 연결된 commit status와 workflow run은 발견되지 않았습니다.  따라서 요청서가 보고한 748-test green과 ruff 결과를 CI 증거로 독립 확인하지는 못했습니다. 이번 판정은 target 코드와 추가된 계약 테스트에 대한 정적 경로 검증입니다.

## 결론

`4c042031af9fe1722676de8bbe41fccba5464b30`은 아직 release 승인 대상이 아닙니다.

다음 재검토 전 최소 조건은:

1. Reviewer-echoed request digest 도입 또는 동일-target reprepare 금지
2. Reprepare generation의 fail-closed atomic ordering
3. Legacy binding과 digest-capable binding의 schema 분리
4. Probe marker의 machine/runtime fingerprint 결속

입니다.


---

## Findings (triage skeleton — verify each before registering)

| finding | severity | type | verdict (REAL/REJECTED/NEEDS-RULING) | evidence | task id |
|---|---|---|---|---|---|
| JW-GPT-004 — reviewer가 실제로 본 request revision이 여전히 결속되지 않음 | major | verification | REAL | 메커니즘 A는 요청서에 자인한 잔여(ingest가 현재 binding digest 도장 — review.py ingest부 주석으로 명시 위양). 메커니즘 B는 코드 확증: `_render_review_request`가 `exposure["project"]`·live template을 소비하나 binding 교차검증은 head/base/reviewers/mode만 대조(review.py:904 인근) — 게이트가 증명하는 것은 '현재 입력으로 재현됨'이지 '발행 당시의 exact revision'이 아님. | A: fix/reply-narrative-echo (기존, deps 갱신) · B: fix/binding-schema-v2-digests |
| JW-GPT-005 — reprepare 중 프로세스 종료가 B request를 A의 완료 증거 뒤에 숨김 | major | correctness | REAL | 코드 확증: prepare 쓰기 순서 request(review.py:904)→narrative(907)→binding(908). 904/907 직후 종료 시 최신 binding=A + feedback=A로 pending 완료 유지, 디스크 request=B. pending은 request/narrative의 binding 재현성을 확인하지 않음 — 표시 표면 fail-open. | fix/reprepare-generation-atomicity |
| JW-GPT-006 — 신규 digest binding을 ingest 전에 legacy로 downgrade할 수 있음 | major | correctness | REAL | 코드 확증: `_assess_narrative_digest`는 양측 digest 부재를 legacy-pre-digest로 분류하고 pending이 이를 완료 조건으로 인정. ingest 전 strip이면 feedback 도장 자체가 없어 attempt-3의 RED(도장 후 strip)가 커버 못함. schema-1이 genuine legacy와 stripped를 구조적으로 구분 불가한 것이 근인 — v2 분리가 근본 해소. | fix/binding-schema-v2-digests |
| Q1 — probe proof는 커밋 비추적이지만 machine/runtime-bound가 아님 | major | architecture | REAL | 코드 확증: 마커는 고정 문자열 verified\n + untracked 검사뿐(delegate.py `_codex_runner_marker_recorded`) — fingerprint 무결속. NFS/checkout 복사로 untracked 마커가 머신 간 이동 가능(자인된 risk note와 일치), runtime drift(codex 버전·sandbox policy) 미재프로브. checkout-local 위치는 유지하되 fingerprint exact-match 결속 필요. | fix/probe-proof-runtime-fingerprint |
