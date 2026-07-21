<!-- waystone feedback: the body below is the reviewer reply VERBATIM (byte-exact copy via `waystone review ingest`) — do not edit it; a triage skeleton is appended beneath it. -->
round: 2026-07-21-m1b-vertical-slice
reviewer: codex:gpt-5.6-sol
reviewer-effort: high
review-target: 885a7ad311d3aca063628f78053503e8c21b767f
reply-metadata-json: {"metadata":{"effort":"high","model":"codex:gpt-5.6-sol","request-digest":"sha256:a6fad9c6b51246bb40e68d897a3cd2f776c1554fd099992d5c5c6d16b75841d4","review-target":"885a7ad311d3aca063628f78053503e8c21b767f"},"narrative_digest":"sha256:4509a16a18f000c9ff6a0693f214743a5594b284d7a0a566420d909c39b1dc26","rendered_request_coverage_reason":null,"rendered_request_digest":"sha256:a6fad9c6b51246bb40e68d897a3cd2f776c1554fd099992d5c5c6d16b75841d4","rendered_request_digest_matches":true}
ingested: 2026-07-21
source: /tmp/review.md
verbatim-bytes: 12642

---

model: codex:gpt-5.6-sol
effort: high
review-target: 885a7ad311d3aca063628f78053503e8c21b767f
request-digest: sha256:a6fad9c6b51246bb40e68d897a3cd2f776c1554fd099992d5c5c6d16b75841d4

## Confirmed findings

### WS-GPT-601 — verifier 발행 직후 crash는 `resume`으로 복구되지 않는다

Severity: major

`RunEngine._complete()`는 재진입 상태를 검사하지 않고 verifier부터 다시 실행한다(`waystone/runs/engine.py:528-558`). verifier evidence 발행 뒤 decision 기록 전에 죽으면 run은 여전히 `dispatch-ready`이고, 다음 `resume()`은 terminal artifact를 reload하지 않은 채 `_complete()`를 재호출한다(`waystone/runs/engine.py:617-647`).

그러나 동일 lineage에 verifier evidence가 있으면 `_refuse_successful_verifier_retry()`가 `EffectRetryRefused`를 발생시킨다(`waystone/runs/verify.py:1123-1149`). 이 거부 동작 자체도 `scripts/tests/test_run_verify.py:1697-1714`에서 단언된다. 따라서 정상적인 crash가 영구적인 진행 불능으로 바뀐다.

재현 절차:

1. fixture assembly로 runner completion까지 진행한다.
2. `record_integration_decision`을 `BaseException`으로 대체하여 `execute_verifier()` 발행 직후 process crash를 모사한다.
3. 새 `RunEngine`으로 동일 run을 `resume()`한다.
4. decision/apply로 복구되지 않고 `EffectRetryRefused: published verifier evidence is terminal and cannot be retried`에 도달한다.

현 CLI 통합 테스트는 무장애 happy path만 검사한다(`scripts/tests/test_run_cli.py:377-413`). 따라서 exit #2의 “effect 종류별 crash recovery”가 green이어도 조립 stage 전체의 crash recovery는 성립하지 않는다.

### WS-GPT-602 — PC-22 approval 재검증은 durable reconcile 경로에서 우회된다

Severity: major

동기 apply 경로는 authority를 재로드하지만(`waystone/runs/verify.py:2753-2792`), 이후 저장하는 `PatchIntegrationEffect`에는 repository/ref와 parent/tree/commit만 있고 verifier·decision·contract digest가 없다(`waystone/runs/effects.py:184-190,535-560`).

plan 저장 뒤 crash가 발생하면 generic reconcile은 approval bundle을 읽지 않고 plan과 Git 상태만으로 effect를 실행한다(`waystone/runs/effects.py:1720-1782`). 실제 mutation도 commit parent/tree 확인 뒤 `git update-ref` CAS만 수행한다(`waystone/runs/effects.py:1444-1458`).

따라서 다음 순서가 가능하다.

1. 유효한 approval로 patch effect plan을 저장한다.
2. 실행 전에 crash한다.
3. verifier 또는 decision artifact를 삭제·변조한다.
4. generic `reconcile_actions([apply_action])`를 실행한다.
5. 손상된 approval을 재검증하지 않고 target ref가 이동한다.

기존 PC-22 테스트는 직접 apply 호출 시의 artifact tamper와 ref CAS race만 검사한다(`scripts/tests/test_run_verify.py:1448-1578`). plan 저장 후 재시작 경로는 다루지 않는다. 구현 보고서도 같은 결함을 명시한다(`docs/meta/agent-reports-2026-07-21/m1b-verify.md:68-71,81-84`).

이는 “실행 시점에 contract·decision·verifier digest를 다시 검증”한다는 PC-22 문언(`docs/promoted-contracts.md:55`)의 필수 경로 누락이다. 후속 task 등록은 현재 exit 충족의 근거가 될 수 없다.

### WS-GPT-603 — checkout 검사와 ref CAS 사이 TOCTOU가 PC-17의 no-write를 깨뜨린다

Severity: major

마지막 checked-out/symref 검사는 `waystone/runs/verify.py:2792`에서 끝나고, 그 뒤 effect plan·claim·execution이 진행된다. Patch observer와 driver는 worktree attachment나 symbolic-ref 여부를 다시 확인하지 않는다(`waystone/runs/effects.py:1311-1359,1444-1458`).

그 사이 다른 정상 Git 프로세스가 private target ref를 linked worktree의 `HEAD`로 attach하면, ref OID가 expected parent와 동일한 한 `git update-ref <target> <result> <expected>`는 성공한다. 그 결과 checked-out branch ref만 이동하고 해당 worktree의 index와 파일은 이전 commit에 남는다.

기존 race 테스트는 `race_hook`에서 attachment한 뒤 두 번째 검사에 걸리는 경우만 다룬다(`scripts/tests/test_run_verify.py:1393-1446`). 마지막 검사 이후 또는 crash-reconcile 동안의 창은 검사하지 않는다.

PC-17은 concurrent drift에서 원자적 no-write를 요구한다(`docs/promoted-contracts.md:50`). 이를 ADR-0013의 “의도적 same-account 간섭” 제외로 수용한 ruling(`tasks.yaml:607`)은 일반적인 concurrent `git worktree` 조작까지 악성 tampering으로 간주하므로 계약보다 보호 범위를 좁힌다.

### WS-GPT-604 — S1의 WAI+launch 실패는 영구 `unknown-effect`이며 `resume`으로 수렴하지 않는다

Severity: major

runner effect는 외부 실행 전에 durable intent를 기록한다(`waystone/runs/effects.py:1625-1633`). 이후 backend/supervisor launch가 실패하여 completion marker가 없으면 observer는 `UNKNOWN`을 반환한다(`waystone/runs/effects.py:1200-1211`).

Reconcile은 이 `UNKNOWN`을 quiescence나 positive-absence 검사보다 먼저 반환한다(`waystone/runs/effects.py:1758-1767`). 같은 action의 runner 재실행도 무조건 금지된다(`waystone/runs/effects.py:1696-1702`). Supervisor가 제공하는 exact-identity absence probe(`waystone/runs/supervisor.py:990-1004`)에는 effect 쪽 소비 경로가 없다.

기존 테스트가 이 영구 정지를 직접 단언한다.

```sh
uv run scripts/tests/run_tests.py RunEffectTests
```

관련 본문은 `scripts/tests/test_run_effects.py:700-722`이며, positive quiescence를 주어도 두 reconcile 결과가 계속 `UNKNOWN_EFFECT`이다. Exit evidence가 인용한 fixture 3은 completion marker가 이미 존재하는 경우(`scripts/tests/test_run_effects.py:443-479`)라 이 반례와 다르다.

따라서 `dev_docs/m1b-exit-evidence.md:18`의 “unknown-effect 정직 대기 + reconcile 수렴”과 계획의 S1 요구(`dev_docs/m1b-slice-plan.md:159-163`)는 충족되지 않는다.

### WS-GPT-605 — D2의 기본 `waystone run start`는 어떤 task도 실행할 수 없다

Severity: major

기본 CLI factory는 assembly 없는 `RunEngine(root)`를 만든다(`waystone/cli/run_group.py:23-27`). `start`는 이를 그대로 호출하고(`waystone/cli/run_group.py:117-124`), engine의 첫 동작은 assembly가 없으면 `run_engine_configuration_unavailable`을 발생시키는 것이다(`waystone/runs/engine.py:299-304,378-380`).

확인 명령:

```sh
rg -n 'RunEngine\(' waystone
uv run bin/waystone run start __review_probe__
```

production 코드의 유일한 생성은 assembly 없는 기본 factory다. 통합 테스트는 별도로 만든 fixture assembly를 주입한다(`scripts/tests/test_run_cli.py:377-380`). 실 backend smoke 역시 이 fixture assembly를 수동 재사용했다(`dev_docs/m1b-exit-evidence.md:30-36`).

Typed refusal이 silent fallback보다 정직한 것은 맞지만, D2는 M1-B의 주 표면이 `waystone run …`이며 `run start`가 one-task 흐름을 수행한다고 규정한다(`dev_docs/m1b-slice-plan.md:30-34`). 기본 사용자 표면이 항상 거부되는 상태에서는 exit #1의 vertical slice 완주를 production surface에 대해 충족했다고 볼 수 없다.

### WS-GPT-606 — v1 format registry가 실제 durable authority namespace를 누락하고 존재하지 않는 reference를 고정했다

Severity: major

Registry는 §3을 “전 네임스페이스”라고 선언하지만(`docs/run-engine-formats.md:27-49`) 다음 durable 형식을 누락했다.

- `runner-invocation:<lineage_digest>:<action_id>`: 동일 invocation의 at-most-once/retry authority(`waystone/runs/effects.py:613-669,729-738,823-838`)
- `transport-action-plan:<action_id>` 및 `waystone-transport-action-plan-1`(`waystone/runs/transport.py:51-54,531-551`)
- `transport-result:*` 및 `waystone-transport-result-1`(`waystone/runs/transport.py:51-54,1002-1028`)
- supervisor launch/runtime/heartbeat/wait schema(`waystone/runs/supervisor.py:36-39`)

반대로 registry의 `fixture-verification:<action_id>` reference(`docs/run-engine-formats.md:43`)는 artifact reference가 아니다. 코드에서는 completion marker의 `process_identity` 문자열로만 쓰인다(`waystone/runs/verify.py:1717-1720`).

확인 명령:

```sh
rg -n 'runner-invocation:|transport-action-plan:|transport-result:|waystone-transport-' waystone docs/run-engine-formats.md
rg -n 'fixture-verification:' waystone
```

§9의 명시적 비고정 목록에도 이 namespace/schema들은 없다(`docs/run-engine-formats.md:108-127`). Registry 변경 시 migration을 강제한다는 선언 아래에서 at-most-once 및 transport authority 형식이 목록 밖에서 변경될 수 있으므로 단순 문서 누락이 아니다. Claim 4의 “고정/미고정 경계가 정직하다”는 주장은 성립하지 않는다.

## Confirmed dispositions with no additional major/critical finding

- Claim 1의 fault fixture 1–8 자체에서는 이름-본문 불일치나 자명통과를 확인하지 못했다. 다만 WS-GPT-601·604·605 때문에 exit 9항 전부 충족이라는 상위 판정은 무효다.
- Claim 2 중 PC-21의 exact criterion/result binding과 worker·verifier·coordinator actor-id 분리는 구현되어 있다(`waystone/runs/verify.py:2182-2265`). 추가 major bypass는 확인하지 못했다.
- Claim 3의 canonical UUID owner directory는 flat legacy write를 대체하고 기존 flat evidence를 read-only로 취급한다. 삭제된 8개 테스트가 현 canonical write 경로를 직접 약화했다는 major 증거는 확인하지 못했다.
- Claim 4에서 canonical JSON, digest 표기, TransitionReason, transport exit/recoverable enum 등 명시된 개별 값은 코드와 대체로 일치했다. 판정 실패는 WS-GPT-606의 누락·허위 항목에 한정된다.
- Claim 5의 S2는 실제 detached subprocess와 launcher-parent 사망 후 marker 회수를 검사하며, S3은 `ConnectionError`·timeout·HTTP 5xx와 terminal/unclassified를 구분한다. 추가 major는 확인하지 못했다. S1만 WS-GPT-604로 반증됐다.
- Claim 6의 ADR-0010 Amendment는 v1 transitional adapter와 `waystone-run-spec-1`을 문언상 공개한다. 현재 증거만으로 silent 준수 위장이라는 major finding은 확정하지 않았다.

## Open domain questions

- `critic-not-required`가 실제 critic 면제와 v1 adapter의 검증 이월을 구별하려면 RunSpec에 `adapter`/`deferred-validation` 또는 acceptance criterion별 origin을 durable하게 기록해야 하는가? 현재 payload만으로는 두 의미가 동일하게 보인다.
- ADR-0009가 같은 round의 canonical review 재발행을 금지하는가? 금지한다면 one-owner-per-round 규칙을 명문화해야 하고, 허용한다면 삭제된 legacy generation 보호를 canonical 방식으로 대체해야 한다.
- ADR-0013의 full principal에는 `project_id`와 `executor_kind`가 포함되지만(`docs/adr/ADR-0013-operational-threat-model.md:118-136`), D9는 이를 v2로 이월했다. Effect plan이 절대 repository 경로를 저장하므로 `.waystone` DB/artifact가 다른 프로젝트로 복사되면 원 프로젝트 mutation 가능성이 있다. 이를 허용된 M1-B scope cut으로 볼지, accepted ADR 위반으로 볼지 명시적인 상위 결정이 필요하다.
- PC-21에서 caller가 제공하는 `ActorIdentity`를 신뢰된 assembly configuration으로 볼지, durable executor principal과 결속해야 하는지 명확하지 않다. blocker override 역시 어떤 passing engine check가 어느 blocker를 정당화할 수 있는지 사전 관계가 없다.

## Residual risks from unavailable GPU / data / environment

- 허용된 focused suite 명령을 실행했으나 테스트 시작 전에 uv cache 접근이 거부됐다.

```text
error: failed to open file '/Users/jahn/.cache/uv/sdists-v9/.git': Operation not permitted (os error 1)
```

따라서 이 리뷰의 finding은 코드 경로와 checked-in 테스트의 정적 교차검증에 근거한다. 테스트 green을 독립 재확인했다고 주장하지 않는다.

- 실 backend smoke의 원본 `scratchpad/fleet/smoke/{smoke.py,smoke.log}`는 pinned worktree 밖에 있어 run ID, marker, Git OID를 독립 검증할 수 없었다.
- GPU나 별도 데이터셋은 이 검토 범위에 필요하지 않았다.
- 현재 publication HEAD는 `c390c1c08d03a6c1940ae4ad58e52b8c72851572`이며 Reviewing SHA 이후 차이는 publication 문서·task metadata뿐이다. 검토 대상 Python 및 테스트 경로에는 후속 diff가 없었다.
- tracked 파일 변경은 없었다.

---

<!-- waystone triage: BEGIN -->
## Triage (main, 2026-07-21)

회신은 free-form(WS-GPT-6NN)이라 verbatim 본문을 직접 triage한다. major 6 전량 처분 완료 —
수리 3·강등 1·기각 1·문서 정정 1. 수리분은 전부 RED-first + 기체 suite + main 독립 재실행 +
opus 반증의 4중 게이트 통과, 최종 suite **1099 green** @ dev `145e37b`.

| Finding | Verdict | Type | 근거/처분 | Task |
|---|---|---|---|---|
| WS-GPT-601 verifier 발행 후 crash → resume 영구 brick | **REAL** (opus 재현 CONFIRMED — 결정론적·비가역, 범위는 _complete 전 구간으로 확대) | correctness | `145e37b`: reload_verifier_evidence/reload_integration_decision public API(원 소비 경로와 동일 loader — bytes 재해시·frozen authority·exact lineage) + _complete 단계별 재진입 + resume completion 우선 라우팅. opus 반증: 우회 없음·보호 무약화·non-re-execution 트립와이어 실단언 | fix/engine-complete-reentry (done) |
| WS-GPT-602 PC-22 crash-reconcile approval 우회 | **REAL** (기공개 공백 — verify ④1·기등록; "등록은 exit 근거가 못 된다"는 지적 수용) | correctness | `ac863f7`: PatchApprovalDigests 4종을 plan에 additive 동봉 + reconcile 미실행 3분기 전부에서 재로드·재해시 대조(approval_authority_mismatch), legacy plan typed 구분. exit 증거표 행 6 갱신 | fix/patch-effect-approval-reconcile-binding (done) |
| WS-GPT-603 checkout 검사~CAS TOCTOU | **PARTIAL → minor** | architecture | opus 검증: 메커니즘 CONFIRMED(재현)이나 "정상 Git 프로세스" 전제 REFUTED — porcelain 전부 detached(worktree add/checkout/switch 실측), waystone도 branch-attach 안 함; 유해 상태는 UUID ref를 겨냥한 의도적 plumbing symref 조작뿐 = ADR-0013 명시 비보호 클래스. 기존 ruling 유지, 선택적 검출 hardening만 등록 | chore/apply-post-cas-attachment-alarm (minor) |
| WS-GPT-604 S1 반례: WAI+launch 실패 영구 unknown | **REAL** (기공개 공백 — supervisor ④1·기등록; S1 충족 선언은 과대였음 인정) | correctness | `ac863f7`: RunnerAbsenceProbe seam — positive exact-identity absence가 정확히 True일 때만 기존 WAI를 최초 실행으로 소비(E-08 무붕괴·at-most-once 보존·probe 부재 시 기존 동작 불변). exit 증거표 행 8 갱신 | fix/effects-runner-absence-seam (done) |
| WS-GPT-605 기본 run start 실행 불능 | **REJECTED** (exit 침해로서) | scope | D2·D7 문언이 계획한 상태: 계약 테스트=fixture assembly, 실 backend=수동 smoke(PASS), production factory는 M1-C 소유로 분해 시점부터 계획·등록됨. typed refusal은 D2의 anti-silent-fallback 요구 그 자체. 사용성 사실은 인정 — M1-C 최우선 | feat/run-production-assembly (M1-C, 기등록) |
| WS-GPT-606 format registry 누락 4·허위 1 | **REAL** (opus 전수 대조 CONFIRMED — 추가 누락 없음 확인) | reporting | registry 정정 완료: runner-invocation·transport-action-plan·transport-result 2형 행 추가, fixture-verification 허위 행 삭제, transport schema 2종 + supervisor sidecar schema 4종 추가, 정정 이력 명기 | (문서 정정 — task 불요) |

**Open domain questions 처분**: Q1(critic-not-required와 adapter 이월의 durable 구별)은 ADR-0010
Amendment §2의 M2 envelope 조립이 소유. Q2(same-round 재발행 규칙)는
docs/adr-0009-reprepare-clarification(minor) 등록. Q3(project/executor 축)은 D9 ruling의 명시적
scope cut — fix/lease-principal-project-executor-binding이 소유(ADR 위반 아닌 이월로 판정).
Q4(ActorIdentity 신뢰 경계)는 chore/decision-actor-principal-binding(minor) 등록.

**Residual risks 응답**: 리뷰어의 uv cache 접근 거부로 suite 미재실행은 기록된 한계 — main이
동일 명령으로 1099 green을 독립 재확인했다(/tmp/suite-main-fxengine-verify.log). smoke 산출물이
pinned worktree 밖이라는 지적은 사실 — exit 증거표에 run_id·OID·절차를 명기해 보완했다.
<!-- waystone triage: END -->
