<!-- waystone feedback: the body below is the reviewer reply VERBATIM (byte-exact copy via `waystone review ingest`) — do not edit it; a triage skeleton is appended beneath it. -->
round: 2026-07-18-carrier-lanes
reviewer: chatgpt:gpt-5.6-pro
ingested: 2026-07-18
source: /tmp/review.md

---

```text
model: gpt-5.6-pro
effort: xhigh
review-target: e9e5c140947375f3a55cc9b8c2c681ff6c458da4
```

## 판정

**CHANGES REQUESTED — Critical 0 / Major 4**

### JW-GPT-001 — 삭제되거나 fetch 대상에서 제외된 upstream을 stale remote-tracking ref로 검증할 수 있음

* Severity: major

**실패 메커니즘.** `waystone remote verify --round`는 upstream의 remote 이름만 추출하여 `git fetch --quiet <remote>`를 실행합니다. 그러나 이 명령의 성공은 해당 upstream branch가 실제로 fetch되어 `refs/remotes/<upstream>`이 갱신됐다는 증거가 아닙니다. 그 뒤 publication gate는 기존 로컬 `refs/remotes/<upstream>`을 SHA로 고정하고, 그 SHA의 로컬 object store에서 packet과 sidecar를 읽습니다.

다음 경로가 재현됩니다.

1. packet이 포함된 `origin/main`을 한 번 fetch한다.
2. 원격 `refs/heads/main`을 삭제하거나 `remote.origin.fetch`에서 해당 branch를 제외한다.
3. `git fetch --quiet origin`은 성공하지만, `--prune`이나 명시적 ref fetch가 없으므로 로컬 `refs/remotes/origin/main`은 과거 SHA를 유지한다.
4. publication gate는 과거 remote-tracking tree에서 packet bytes를 찾아 성공한다. 현재 원격에는 해당 branch나 packet이 존재하지 않아도 된다.

별도 로컬 bare-repository 실험에서도 원격 `refs/heads/main` 삭제 후 `git fetch --quiet origin`은 **rc 0**이었고, `refs/remotes/origin/main`은 삭제 전 SHA에 그대로 남았습니다.

**필수 수정.** remote 이름만 fetch한 뒤 기존 remote-tracking ref를 신뢰하면 안 됩니다. 현재 branch에 설정된 정확한 remote merge ref를 명시적으로 fetch하고, 그 호출이 산출한 `FETCH_HEAD` 또는 전용 임시 ref의 SHA를 publication evidence로 사용해야 합니다. 다음 두 RED를 추가해야 합니다.

* upstream branch가 원격에서 삭제된 상태
* upstream branch가 remote fetch refspec에서 제외된 상태

---

### JW-GPT-002 — fan-out packet digest가 실제 실행 지시를 누락하여 stale manifest가 변경된 task를 실행함

* Severity: major

**실패 메커니즘.** 계획 시 기록되는 `packet_sha256`은 `milestone`, `round`, `anchor`, `notes`를 포함하지 않습니다. 그러나 네 필드는 실제 implementer prompt에 들어갑니다. 즉 해시가 “runner가 받은 실행 지시”를 대표하지 않습니다.

구체적인 우회는 다음과 같습니다.

1. `notes: A`인 task로 fan-out plan을 만들고 digest `D`를 얻는다.
2. plan 생성 후 `tasks.yaml`의 `notes`, `anchor` 또는 `round`를 `B`로 변경한다.
3. 기존 manifest가 `delegate run --expect-packet-sha D`를 호출한다.
4. `_prepare_run()`은 변경된 packet `B`를 다시 만들지만, 누락된 필드 때문에 digest가 여전히 `D`여서 통과한다.
5. `_claim_run()`의 exact packet 비교도 원래 manifest packet과 비교하지 않는다. 같은 run 호출에서 방금 만든 `plan["packet"]`과 다시 읽은 현재 packet `B`를 비교하므로 역시 통과한다.
6. implementer에게는 변경된 지시 `B`가 전달된다.

Manifest에는 전체 `registry_fingerprint`가 기록되지만, carrier는 이를 검증하거나 `delegate run`에 전달하지 않습니다. 실제 dispatch 결속은 packet digest와 profile fingerprint뿐입니다.

**필수 수정.** 최소한 registry에서 유래하고 prompt 또는 provenance에 소비되는 모든 필드를 canonical packet digest에 포함해야 합니다. 더 안전한 계약은 “의도적으로 변동 가능한 carrier/retry metadata만 제외한 정확한 canonical packet”을 해시하는 것입니다. 다음 필드별 RED가 필요합니다.

* `notes`
* `anchor`
* `round`
* `milestone`

각 테스트는 기존 manifest로 실행했을 때 claim record를 만들기 전에 거부되는지 확인해야 합니다. 사용하지 않는 `registry_fingerprint`는 실제 gate로 연결하거나 manifest에서 제거해 의미를 정직하게 해야 합니다.

---

### JW-GPT-003 — corrupt 최신 binding을 건너뛰고 과거 feedback으로 pending을 해소함

* Severity: major

**실패 메커니즘.** `pending_reviews()`는 sidecar를 순회하면서 파싱 실패를 단순히 `continue`합니다. 하나라도 과거의 유효한 sidecar가 있으면 그 유효한 집합에서 최신 항목을 선택하고, 과거 feedback의 `review-target`이 거기에 맞으면 round를 완료된 것으로 제거합니다. 코드 주석의 “damaged round itself stays listed as pending”은 **모든 sidecar가 손상된 경우에만** 사실입니다.

다음 파일 상태만으로 재현됩니다.

```text
R-request.binding.json     # 유효, target A
R-request.binding-2.json   # corrupt 또는 부분 기록
R-feedback.md              # review-target A
```

`binding-2`는 무시되고 binding 1이 선택되며, feedback이 A와 일치하므로 `R`은 pending 결과에서 사라집니다. 최신 binding의 상태와 target은 알 수 없는데도 과거 증거로 완료 처리됩니다.

이는 단순 인위적 손상만의 문제가 아닙니다. Sidecar 생성은 파일을 `open("x")`로 먼저 만든 다음 내용을 쓰므로, 생성과 write 사이의 프로세스 종료는 빈 파일이나 부분 JSON을 남길 수 있습니다.

**필수 수정.**

* 파일명 sequence로 최신 후보를 먼저 결정한 뒤, 그 후보가 corrupt하면 해당 round를 반드시 pending/unknown으로 유지해야 합니다.
* 더 단순하고 안전하게는 해당 round의 sidecar 중 하나라도 corrupt하면 completion 파생을 금지할 수 있습니다.
* Sidecar 생성 자체도 임시 파일 완전 기록 후 exclusive publish하는 방식으로 crash-atomic하게 바꿔야 합니다.

`valid binding-1 + matching feedback + corrupt binding-2` 계약 테스트가 필요합니다.

---

### JW-GPT-004 — request binding이 request/narrative bytes를 결속하지 않아 동일 SHA의 재발행이 과거 증거를 재사용함

* Severity: major

**실패 메커니즘.** `review prepare`는 request와 보존 narrative를 덮어쓴 다음 binding을 기록합니다. 그러나 binding contract에는 target/base/reviewers/mode만 있고 request 또는 narrative digest가 없습니다. 동일 exposure에서 narrative만 바뀌면 기존 contract와 같다고 판단하여 새 sidecar를 만들지 않고 기존 sidecar를 반환합니다.

따라서 다음 정상 CLI 경로가 가능합니다.

1. target `T`, narrative `A`로 prepare하고 feedback을 ingest한다.
2. 같은 round와 target `T`에 narrative `B`로 prepare를 다시 실행한다.
3. request와 stored narrative는 `B`로 바뀌지만 binding은 기존 sidecar 그대로다.
4. packet mode에서는 기존 feedback의 `review-target: T`가 계속 일치하므로 새 request `B`가 pending에 나타나지 않는다.
5. PR mode에서는 freeze가 mutable stored narrative를 다시 읽어 `B`를 게시하지만, sidecar에는 `A`와 `B`를 구분할 증거가 없다. Freeze 시 검증되는 것은 target/base/reviewers뿐입니다.

즉 “request 파일을 재신뢰하지 않는다”는 목표는 달성했지만, 신뢰가 digest로 결속되지 않은 다른 로컬 파일로 이동했을 뿐입니다. 새 claims, known weaknesses, review instructions가 게시되어도 downstream state는 이를 이전에 검토된 packet과 구분하지 못합니다.

**필수 수정.** 다음 중 하나가 필요합니다.

* binding에 `narrative_sha256`, `rendered_request_sha256`, 필요하면 `exposure_sha256`을 포함하고 freeze/pending에서 검증한다.
* 기존 round binding이 있으면 request 또는 narrative bytes의 변경을 거부하고 새 round ID를 요구한다.
* 같은 target에서 request reissue를 지원하려면 feedback protocol도 target SHA뿐 아니라 request revision/digest에 결속해야 한다.

`prepare A → feedback T → prepare B at same T` 후 pending이 다시 열리거나 prepare 자체가 거부되는 RED가 필요합니다.

## Open domain questions

### 1. `delegation.codex_runner_verified`의 신뢰 범위

프로브 성공은 프로젝트 `.waystone.yml`에 기록되고, 값이 `true`이면 이후 프로브를 건너뜁니다. 따라서 한 머신의 결과가 다른 머신, 다른 OS, 다른 Codex 버전에도 그대로 전파될 수 있습니다.

반면 진단 메시지는 “this machine”에서 실패했으면 config key를 제거하라고 안내하여 이 증거가 실질적으로 host-specific임을 전제합니다.

이 proof가 machine/runtime scoped라면 현재 위치는 상태 격리 위반이며 Major로 승격해야 합니다. 그 경우 host-local project state에 저장하고 Codex executable/version, OS 및 sandbox policy fingerprint로 invalidate해야 합니다. Repository-scoped proof가 의도라면 이식 가능성을 성립시키는 구체적 전제가 ADR에 필요합니다.

### 2. release 중 concurrent worktree checkout을 위협모델에 포함하는지

`assert_main_not_checked_out`과 최종 `git update-ref`는 원자적이지 않습니다. 두 명령 사이에 다른 프로세스가 `main`을 checkout할 수 있습니다. Git의 `update-ref`는 checked-out branch도 이동시킬 수 있으며 worktree 파일은 자동 갱신하지 않습니다. 스크립트는 최종 검사 직후 CAS update를 하지만 branch occupancy에 대한 lease를 보유하지 않습니다.

동시 Git 조작이 지원 대상이라면 전용 main worktree를 일찍 점유해 release 종료까지 branch checkout을 배타화하는 등의 설계가 필요합니다. 단일 사용자·단일 프로세스만 지원한다면 그 제한을 명시하는 편이 정확합니다.

## Residual risks from unavailable environment

이번 검토에서는 GitHub connector로 정확한 target의 코드와 diff를 추적했지만, 실행 가능한 repository checkout이 없어 명시된 719-test suite와 ruff를 독립 재실행하지 못했습니다. `JW-GPT-001`의 Git remote 동작은 별도 로컬 bare-repository에서 동적으로 재현했고, 나머지 세 건은 확정적인 정적 실행 경로입니다.

실제 Claude Code Workflow 엔진의 background re-invocation, exactly-once 동작 및 multi-lane 집계는 실행하지 못했습니다. 요청서도 carrier의 live fan-out이 아직 수행되지 않았음을 명시합니다. 따라서 이 부분은 현재 scenario matrix와 `validateOnly` 이상의 독립 운영 증거가 없습니다.

**결론적으로 `e9e5c140947375f3a55cc9b8c2c681ff6c458da4`는 현재 상태에서 release 승인 대상이 아닙니다. `JW-GPT-001`부터 `004`까지 각각 RED 계약을 추가하고 수정한 뒤 재검토가 필요합니다.**




---

## Findings (triage skeleton — verify each before registering)

| finding | severity | type | verdict (REAL/REJECTED/NEEDS-RULING) | evidence | task id |
|---|---|---|---|---|---|
| JW-GPT-001 — 삭제되거나 fetch 대상에서 제외된 upstream을 stale remote-tracking ref로 검증할 수 있음 | major | correctness | REAL | 적대 검증 동적 재현: 별도 clone이 원격 branch 삭제 → 검증 clone에서 `git fetch` rc0·stale ref 잔존 → 실제 `remote.py verify --round`가 삭제된 branch에 대해 PASS(rc0) 출력. 코드: remote.py:46(이름만 fetch, --prune/refspec 없음), review.py:909-927(persisted refs/remotes/* 고정 + 로컬 object store 읽기), common.py:1596(head_pushed 동일 패턴). 완화: force-push 대체는 잡힘 — 순수 삭제/refspec 제외에 한정 | fix/remote-verify-live-ref |
| JW-GPT-002 — fan-out packet digest가 실제 실행 지시를 누락하여 stale manifest가 변경된 task를 실행함 | major | correctness | REAL | 동적 재현: notes/milestone/round/anchor 변조 packet과 원본의 `_packet_core_digest` 동일 확인. 코드: digest core dict(delegate.py:611-621)에 4필드 부재, _render_prompt(645-647)는 4필드를 prompt에 렌더, _claim_run(1609,1619) 비교는 양쪽 다 run 시점 읽기라 plan→run 드리프트 무력, registry_fingerprint 소비처 전무(3265 생산만). docstring(601-608)상 의도적 제외 아님 — 누락 | fix/packet-digest-prompt-coverage |
| JW-GPT-003 — corrupt 최신 binding을 건너뛰고 과거 feedback으로 pending을 해소함 | major | correctness | REAL | main 직접 검증: review.py:502-509 — corrupt sidecar를 continue로 제외한 뒤 *파싱 성공 집합*에서 max 선택 → corrupt binding-2 존재 시 구 binding-1이 "최신"으로 승격, 521의 완료 판정이 구 target과 매칭. 주석(499-500)의 "damaged round stays pending"은 전부 손상 시에만 참. 쓰기 경로 346-347 `open("x")`+write — crash 시 빈/부분 파일 실재 가능 | fix/pending-corrupt-binding-honesty |
| JW-GPT-004 — request binding이 request/narrative bytes를 결속하지 않아 동일 SHA의 재발행이 과거 증거를 재사용함 | major | correctness | REAL | 단위 재현: 동일 target/base/reviewers/mode로 write_round_request_binding 2회 → 동일 sidecar 재사용(파일 1개), binding 필드에 narrative/request digest 부재. 코드: contract=row−at(review.py:330, 7필드뿐), 재-prepare 가드(810-816)는 exposure 상이 시에만 거부 — narrative-only 변경 통과 후 narrative store 무조건 덮어씀(820-823), 완료 판정은 순수 SHA 비교(265-279, 518-522), freeze는 mutable narrative 재신뢰(1495-1531) | fix/binding-narrative-digest |

### Open questions triage (main 판정)

- **Q1 (probe proof 신뢰 범위)** — **REAL major로 승격** (type: architecture). proof가 커밋 추적 `.waystone.yml`에 기록되고(delegate.py:1137-1158, 973-990; `git ls-files`로 추적 확인) skip 게이트가 그 커밋 값에 직접 종속 — 머신 A의 host-specific 증명이 pull만으로 머신 B의 프로브를 건너뛰게 하는 상태 격리 위반. 진단 메시지 자체가 "this machine" 전제(1239-1258). 완화: 현재 이 repo의 .waystone.yml에는 해당 키 부재(잠재), stderr 패턴 2차 안전망 존재(1216-1259) — 그러나 위반 자체는 확정. → `fix/probe-proof-machine-scope`
- **Q2 (release 동시 checkout)** — **REAL minor** (type: architecture). assert(249)→update-ref(250) 사이 비원자·lease 부재는 사실이나, SSOT §3(솔로 개발자)에 따라 동시 다중 프로세스는 지원 범위 밖 — lease 기계는 speculative machinery로 배제하고 제한을 스크립트에 명시(즉시 적용). → `docs/release-single-writer-assumption` (done)
