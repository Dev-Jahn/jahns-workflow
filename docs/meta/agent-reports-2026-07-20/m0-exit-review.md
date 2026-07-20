VERDICT: M0-exit FAIL — blocker 3 / major 6 / minor 2; M0-A는 충족하나 M0-B·M0-C와 M1-A handoff gate가 닫히지 않음
COMMITS: none
HOTFILES: scripts/tests/run_tests.py read-only 정독·inventory 대조만 수행; scripts/common.py 미접촉; scripts/delegate.py 미접촉; 수정 0
VERIFIED: annotated baseline tag → 7cfecd313da2240bd1e397ff1d81bae93a2fa543; ledger↔source 828/828 unique·누락 0·line mismatch 0; port/rewrite/drop=818/10/0; grades=406/264/134/14/10; invariant/matrix 21/21·누락 0; matrix test refs 56/56 존재; git status clean
NOT-RUN: waystone CLI(명시적 금지); full suite·ruff(문서/소스 read-only 감사이며 .venv 생성도 피함 — 828 green은 tag/PROGRESS의 기록 증거만 확인); 구현·fixture 실행 없음

# M0 exit 적대 리뷰

## 결론

M0-A의 수정된 세 exit 조건은 충족한다. 그러나 M0-B의 명시적 필수 산출물인 operational threat model이 불완전하고, M0-C의 legacy fixture/characterization baseline을 식별할 수 없으며, M1-A exit의 유일한 비교 기준인 출력 등급표가 실제 테스트에 적용 가능한 comparator 계약을 제공하지 않는다. 따라서 M1-A 착수는 승인할 수 없다.

severity는 다음처럼 사용했다.

- `blocker`: 현재 문서만으로 M0 exit 또는 M1-A의 합격/불합격을 결정할 수 없거나, 계획이 명시한 필수 gate가 없음.
- `major`: M0-B 계약 또는 M1 handoff가 서로 다른 구현을 허용하지만 해당 결함만 국소 폐쇄하면 gate를 다시 평가할 수 있음.
- `minor`: 실행 계약의 핵심 의미는 추론 가능하나 참조·현재 verdict가 모순됨.

## Exit 기준 판정표

| 구간 | 계획서 exit 항목 | 판정 | 증거 |
|---|---|---|---|
| M0-A | 미해결 trust major가 개발 하네스의 실제 표면 밖 | 충족 | 기준 `dev_docs/0.12.0-refactor-plan.md:580-582`; packet 설정 `.waystone.yml:10-12`; packet 조기 반환 `scripts/review.py:576-590`; PR-mode 한정과 gate 방향 `docs/known-issues.md:12-14,22-41,45-63,67-76`; tracked freeze/demotion sidecar 0개. |
| M0-A | 각 major의 영향 범위 문서화 | 충족 | `docs/known-issues.md:22-41`(JW-GPT-014), `:45-63`(JW-GPT-015), `:80-92`(해소 조건). |
| M0-A | baseline tag + feature freeze | 충족 | `refs/tags/baseline/0.12-refactor`는 annotated tag이고 dereference commit은 `7cfecd313da2240bd1e397ff1d81bae93a2fa543`; tag message에 feature freeze가 명시됨. 계획 기록 `dev_docs/0.12.0-refactor-plan.md:584-588`. |
| M0-B | ruling 6건 | 충족 | `dev_docs/0.12.0-refactor-plan.md:834-858`. |
| M0-B | 최소 operational threat model | **미충족** | 필수 축 `dev_docs/0.12.0-refactor-plan.md:602-604`; 실제 ruling은 보호/비보호 경계만 `:838-842`. WS-CDX-1. |
| M0-B | effect별 observation/unknown, fencing+CAS, recovery table | 충족 | `docs/adr/ADR-0002-external-effect-commit-protocol.md:38-56,58-74,88-105`. |
| M0-B | executor 경계와 비차단 next-action | 충족 | `docs/adr/ADR-0004-executor-boundary.md:15-35`. |
| M0-B | liveness/progress/current, cancel/quiescence/cleanup, supervision | 충족 | `docs/adr/ADR-0003-run-observability-and-cancellation.md:21-33,35-101,103-171`. |
| M0-B | fact authority matrix | **미충족** | 표는 존재(`docs/adr/ADR-0005-fact-authority-matrix.md:15-29`)하나 이후 신설한 canonical project registry와 profile policy의 authority를 일관되게 포함하지 못함. WS-CDX-7. |
| M0-B | closeout manifest 최소 계약 | **미충족** | 계획 schema `dev_docs/0.12.0-refactor-plan.md:504-539`와 ADR schema `docs/adr/ADR-0006-run-closeout-manifest.md:15-40`가 상충하고 일부 terminal run에는 적용 불가. WS-CDX-5. |
| M0-B | SQLite filesystem/backup/GC | 충족 | `docs/adr/ADR-0007-sqlite-operations.md:15-52`. |
| M0-B | cross-machine·delivery·terminology | 충족 | cross-machine `dev_docs/0.12.0-refactor-plan.md:497-502`; delivery `:683-705`; terminology `docs/adr/ADR-0008-terminology.md:20-86`. |
| M0-B | I-01~12·E-01~09 확정 | **부분 미충족** | 21행은 존재하지만 E-09의 선언된 권위 원천과 확정 문구가 다름. `docs/invariants.md:4-6,36`; WS-CDX-9. |
| M0-C | contract-level test 선별·태깅 | 판정불가 | ledger의 `port`가 characterization tag인지 정의되지 않고 별도 closed selection도 없음. 계획 `dev_docs/0.12.0-refactor-plan.md:621-624`; WS-CDX-2. |
| M0-C | porting ledger inventory | 충족 | source와 ledger 모두 85 classes / 828 unique methods, ID·source line 누락 0; `docs/porting-ledger.md:3-18,66-1328`. |
| M0-C | 처분 합계 818/10/0 | 충족 | 문서 `docs/porting-ledger.md:44-49`; 독립 파서 결과 동일. |
| M0-C | 출력 등급 합계 406/264/134/14/10 | 산술 충족, gate 미충족 | 문서 `docs/porting-ledger.md:35-42`; 독립 파서 결과 동일. 비교 계약은 실행 불가. WS-CDX-3. |
| M0-C | traceability matrix 골격 | 구조 충족 | I-01~12, E-01~09 각 1행 + cancellation 1행; 56 unique test ref 전부 실재. 다만 I-10 characterization은 명시적 gap. `docs/traceability-matrix.md:14-37`; WS-CDX-2. |
| M0-C | legacy fixture set | **미충족** | 요구 `dev_docs/0.12.0-refactor-plan.md:621-622`; tracked path·manifest·명시 목록 없음. WS-CDX-2. |
| M0-C | runtime-state disposition audit 실물 | 산출물 충족, 현재 verdict 불명료 | inventory/처분 `docs/runtime-state-audit.md:40-116`, finding `:118-162`, 후속 처분 `:184-213`; 상단 결론은 후속 처분과 동기화되지 않음. WS-CDX-11. |
| M0-C | expected-red 0 | 정적 증거상 충족 | `expectedFailure`/xfail/expected-red marker 0; 알려진 결함을 보존하는 test 0이라는 ledger 판정 `docs/porting-ledger.md:51-64`. suite는 이 리뷰에서 재실행하지 않음. |
| M0-C | 핵심 flow가 observable contract로 기술 | 판정불가 | 핵심 flow의 닫힌 inventory가 없고 I-10 characterization이 `TODO(M1)` gap이다. `docs/invariants.md:25,38-40`; `docs/traceability-matrix.md:25`. WS-CDX-2. |

## Findings

### WS-CDX-1 — blocker — 필수 operational threat model이 완결되지 않았다

**주장.** M0-B는 단순한 보호/비보호 범위가 아니라 `DB·artifact permission`, shared checkout, symlink, config fingerprint 범위, env 전달, lease principal까지 최소 threat model로 확정하라고 명시한다(`dev_docs/0.12.0-refactor-plan.md:602-604`). M0-B exit는 이 결정을 전부 문서에 고정하는 것이다(`:613`). 그러나 확정 ruling은 우발 손상 대 의도적 로컬 조작/다중 사용자/namespace 경계만 정한다(`:838-842`). ADR-0002~0012와 `docs/invariants.md` 전수 검색에서도 나머지 축을 하나의 operational contract로 고정한 곳이 없다.

**영향.** M4의 사용자용 `SECURITY.md`로 미룰 수 없는 M0-B 설계 입력이 빠졌으므로 M0-B exit 자체가 미충족이다. 예를 들어 DB/artifact mode, child env allowlist, lease owner principal을 M1 구현자가 임의 결정할 수 있다.

**반증 조건.** 위 필수 축 각각의 보호 대상·비보호 대상·fail direction을 고정한 기존 M0 문서/ADR의 정확한 경로와 anchor를 제시하면 기각 가능하다.

### WS-CDX-2 — blocker — characterization baseline/legacy fixture set이 닫힌 산출물로 존재하지 않는다

**주장.** M0-C는 contract-level test 선별 태깅, legacy fixture set, 핵심 flow observable contract를 요구한다(`dev_docs/0.12.0-refactor-plan.md:619-624`), task 분해에도 `gate/characterization-baseline`이 있다(`:797-805`). 그러나 tracked tree에는 fixture/characterization path, fixture manifest, 또는 legacy fixture의 닫힌 목록이 없다. repo-wide 문구 검색에서 `legacy fixture`는 계획과 invariant의 일반 정의만 나온다. `tasks.yaml`에도 `gate/characterization-baseline` task가 없고, `PROGRESS.md:7-21`은 ledger/audit/matrix를 shipped로 열거하면서 곧바로 M0 완료를 선언한다.

추가로 보존 invariant I-10은 characterization layer를 요구한다(`docs/invariants.md:25`), 연결되지 않은 invariant는 이관 완료로 보지 않는다고 명시한다(`:38-40`). 실제 matrix는 I-10 characterization을 `TODO(M1)`인 `gap`으로 남긴다(`docs/traceability-matrix.md:25`).

**영향.** M1-A가 반드시 유지할 legacy input/output fixture와 “핵심 flow”의 경계가 닫히지 않아 silent contract drop을 판정할 기준이 없다.

**반증 조건.** 추적된 fixture set/manifest와 characterization selection, 그리고 I-10의 현재 characterization test를 제시하면 기각 가능하다.

### WS-CDX-3 — blocker — M1-A 출력 등급 gate는 실제 old/new comparator로 실행할 수 없다

**주장.** 계획은 machine JSON을 schema/value 동일, time/path record를 normalized 비교하도록 하고 ledger의 각 test 등급을 M1-A exit로 사용한다(`dev_docs/0.12.0-refactor-plan.md:632-643`). 합계는 맞지만 다음 배정은 계약과 맞지 않는다.

1. ledger #541~546은 `machine JSON`이나(`docs/porting-ledger.md:862-867`), source는 stdout을 버리고 exit 1과 stderr substring만 단언하며 JSON을 발행·파싱하지 않는다(`scripts/tests/run_tests.py:13246-13335`). 이 여섯 test의 실제 human/diagnostic contract가 미배정이다.
2. #538 manifest는 temp root와 time/random `correlation_id`를 포함하고, #539는 같은 초에도 ID가 달라야 한다고 단언하지만 둘 다 schema/value 동일로 배정됐다(`docs/porting-ledger.md:859-860`; `scripts/tests/run_tests.py:13189-13229`). field normalizer 없이는 정당한 실행끼리도 equality가 실패한다.
3. #454는 fake runner가 고정한 정확한 `duration_s=0.75`를 단언하는데 normalized 등급이고, #458은 실제 elapsed duration을 `>=0`으로만 단언하는데 schema/value 동일 등급이다(`docs/porting-ledger.md:745,749`; `scripts/tests/run_tests.py:10314-10339,10454-10490`).
4. `normalized 비교`의 field set, normal form, comparator는 계획의 한 줄과 10개 배정 외에 존재하지 않는다.

**영향.** 현재 gate는 동적 값 때문에 정당한 M1-A를 false-fail하거나, 반대로 normalization이 정의되지 않아 필수 시간/경로 의미의 drop을 false-pass할 수 있다. M1-A exit의 판정 절차가 없다.

**반증 조건.** test별 실제 표면을 재배정하고 dynamic field별 normal form을 고정한 executable comparator/fixture를 제시하면 기각 가능하다.

### WS-CDX-4 — major — JW-GPT-015 이월 보상 구현이 어느 milestone에도 남아 있지 않다

**주장.** M0-A는 open major 014·015를 M1-B acceptance에 편입하는 조건으로 baseline을 동결했다(`dev_docs/0.12.0-refactor-plan.md:595-598`). 같은 계획은 015가 store로 자동 소멸하지 않고 UUID owner directory 구현이 필요하다고 정정한다(`:650-654`); known issue도 동일하다(`docs/known-issues.md:82-90`). 하지만 M1 task 분해에는 해당 구현이 없다(`dev_docs/0.12.0-refactor-plan.md:806-809`). `feat/review-artifact-addressing`은 ADR/invariant만 scope로 하여 이미 `done`이다(`tasks.yaml:749-756`), 실제 산출물 `ADR-0009`도 layout 결정 문서일 뿐이다(`docs/adr/ADR-0009-review-artifact-addressing.md:28-67`). 현재 `scripts/review.py`에는 canonical `docs/reviews/runs/<uuid>/` writer/reader가 없다.

**영향.** M0-A에서 허용한 trust major의 보상 조건을 M1-B가 실행할 수 없다. M1 task 생성 전에 구현 task와 milestone acceptance를 다시 열어야 한다.

**반증 조건.** ADR 작성과 별개인 구현 task가 M1-B(또는 그 이전)의 acceptance에 등록되어 있음을 제시하면 기각 가능하다.

### WS-CDX-5 — major — closeout manifest 계약이 단일 schema로 구현 불가능하다

**주장.** 다음 네 계약이 동시에 성립하지 않는다.

1. 계획은 `base_snapshot_sha`, `closure_digest`, `task_ids`, `decision_digest`, integrated verification, delivery, review를 명시한다(`dev_docs/0.12.0-refactor-plan.md:514-530`). 계획이 ADR에 남긴 선택은 verifier artifact 보존 option a/b뿐이다(`:536-539`).
2. 자신을 계획 §5-4의 확정판이라고 선언한 ADR은(`docs/adr/ADR-0006-run-closeout-manifest.md:6`) `task_id` 단수, `outcome`, `base_sha`, `run_spec_digest`, `verifier_artifact_digests`만 허용하고 schema version 없이 편의 필드 추가를 금지한다(`:15-30`). 이는 multi-task run의 frozen closure(`dev_docs/0.12.0-refactor-plan.md:674,679-681`; `docs/adr/ADR-0003-run-observability-and-cancellation.md:70-74`)를 표현하지 못한다.
3. ADR은 각 `run_id`에 manifest 정확히 하나를 요구하고 `cancelled`/`failed`를 outcome으로 허용하면서도 모든 manifest에 non-null `code_result_sha`와 remote reachability를 요구한다(`docs/adr/ADR-0006-run-closeout-manifest.md:15,24-32`). process/effect 시작 전 정상 취소(`docs/adr/ADR-0003-run-observability-and-cancellation.md:115-132`)에는 run이 만든 result commit이 없으며 null/base/no-result 규칙도 없다.
4. ADR은 “deterministic Git-tracked path”에서 add-only CAS한다고만 하고 canonical path grammar를 정하지 않는다(`docs/adr/ADR-0006-run-closeout-manifest.md:15`). 서로 다른 writer가 서로 다른 deterministic path를 택하면 둘 다 absent-CAS를 통과할 수 있다.

**영향.** M1/M2가 어떤 schema, task cardinality, no-result terminal semantics, publication path를 구현해도 문서 일부를 위반한다.

**반증 조건.** 계획을 명시적으로 supersede하는 하나의 schema와 path grammar, multi-task mapping, no-result terminal 규칙을 제시하면 기각 가능하다.

### WS-CDX-6 — major — canonical run identity가 두 가지다

**주장.** 계획은 canonical run id를 `<UTC compact timestamp>-<slug>-<6자 random>`으로 고정하고 slug는 identity 일부가 아니라고 말한다(`dev_docs/0.12.0-refactor-plan.md:190-193`). ADR-0005는 canonical run id를 RFC 9562 UUIDv7 lowercase string으로 고정하며 timestamp/PID/task 조합을 금지한다(`docs/adr/ADR-0005-fact-authority-matrix.md:33-39`). ADR-0009의 canonical review layout도 UUIDv7 grammar를 의무화한다(`docs/adr/ADR-0009-review-artifact-addressing.md:30-46`). 두 문서 모두 값을 canonical이라고 부르며 구 ID/신 ID mapping이나 명시적 supersession이 없다.

**영향.** M1 schema, closeout path, review owner directory가 서로 호환되지 않는 identity grammar로 구현될 수 있다.

**반증 조건.** 하나를 폐기하고 compatibility/migration 규칙을 명시한 authoritative decision을 제시하면 기각 가능하다.

### WS-CDX-7 — major — fact authority matrix가 이후 신설 권위를 흡수하지 못했다

**주장.** ADR-0011은 `~/.waystone/projects.json`의 registration으로 canonical project와 opaque `project_id`를 resolve하도록 한다(`docs/adr/ADR-0011-project-context.md:31-57`). 계획도 이를 machine-local canonical mapping authority로 수용한다(`dev_docs/0.12.0-refactor-plan.md:457-470`). 그러나 M0-B의 fact authority matrix(`docs/adr/ADR-0005-fact-authority-matrix.md:17-29`)에는 project mapping/registry fact가 없다.

또한 matrix는 Git-tracked project policy bytes를 authority로 둔다(`docs/adr/ADR-0005-fact-authority-matrix.md:19`). 실제 audit은 `.waystone/profile.yml`의 routing/config intent가 local-only project policy라서 major F-01이라고 판정한다(`docs/runtime-state-audit.md:101,120-125,184-190`), 해당 분리는 M3 pending이다(`tasks.yaml:795-802`). 계획 §5-1은 여전히 profile을 local 유지로 둔다(`dev_docs/0.12.0-refactor-plan.md:448`).

**영향.** M1~M3 사이에 canonical project mapping과 routing policy의 단일 authority를 matrix만으로 결정할 수 없다. “fact당 authority 1” 성공 기준(`dev_docs/0.12.0-refactor-plan.md:24-34`)을 검증할 수 없다.

**반증 조건.** matrix에 두 fact와 authority/cache/transfer 규칙을 추가하고 profile v1 transitional authority를 명시하면 기각 가능하다.

### WS-CDX-8 — major — M1-A ledger가 완료된 ruling 두 건을 여전히 미결로 표시한다

**주장.** ledger는 `needs-ruling` 2건이라고 선언하고(`docs/porting-ledger.md:29-34`) #473/#486을 실제로 `needs-ruling`으로 둔다(`:764,782`). traceability도 같은 결정을 미결로 남긴다(`docs/traceability-matrix.md:53,55-59`). 그러나 `tasks.yaml:819-833`은 positive effect-absence proof와 executable content digest라는 정확한 ruling을 각각 `done`으로 기록하고, `PROGRESS.md:13-15`도 둘 다 판정 완료라고 선언한다.

**영향.** M1-A handoff의 권위 문서가 registry decision과 어긋나 rewrite contract가 미결인지 확정인지 알 수 없다. ruling을 발견할 수 있으므로 blocker보다는 major로 판정했다.

**반증 조건.** ledger와 matrix의 ruling cell/rewrite 문구가 완료 결정을 반영하면 기각 가능하다.

### WS-CDX-9 — major — E-09의 선언된 권위 원천과 확정 문구가 충돌한다

**주장.** `docs/invariants.md:4-6`은 E-01~E-09 문구의 authority를 계획 §4라고 선언한다. 계획의 E-09는 filesystem metadata만 금지하고 파일명은 판정 근거로 허용한다(`dev_docs/0.12.0-refactor-plan.md:433`). 확정 invariant와 ADR-0009는 hostname/cwd 등 incidental ambient 값도 금지하고 filename delimiter로 owner identity를 추론하지 못하게 한다(`docs/invariants.md:36`; `docs/adr/ADR-0009-review-artifact-addressing.md:69-91`). 후속 문구가 더 안전하지만 declared authority source와 정면으로 다르다.

**영향.** M1 adapter가 계획 문구를 따르면 ADR-0009가 금지한 filename owner inference를 재도입할 수 있다.

**반증 조건.** 계획 §4를 확정 E-09로 동기화하거나 authority precedence를 명시하면 기각 가능하다.

### WS-CDX-10 — minor — ADR/matrix의 cross-reference metadata 두 곳이 stale이다

**주장.** traceability matrix는 `ADR-0003 §3-9`를 참조하지만(`docs/traceability-matrix.md:4,37`), ADR의 관련 heading은 번호 없는 `취소, quiescence, cleanup 안전 계약`이다(`docs/adr/ADR-0003-run-observability-and-cancellation.md:103`). §3-9는 계획서 번호이지 ADR anchor다. 또한 `ADR-0012` header는 `Tasks: feat/canonical-project-identity`라고 쓰지만(`docs/adr/ADR-0012-verification-capability-preflight.md:7`), 실제 별도 task는 `feat/verification-capability-preflight`이며 ADR-0012를 result로 기록한다(`tasks.yaml:759-764`).

**영향.** 자동/수동 trace navigation과 provenance 추적이 잘못된 대상을 가리킨다. 의미 계약은 본문으로 복구 가능하다.

**반증 조건.** anchor와 task metadata를 실제 target으로 수정하면 기각 가능하다.

### WS-CDX-11 — minor — runtime audit의 현재 violation count가 한 문서 안에서 두 값이다

**주장.** audit 상단은 §5-1 위반 6건이라고 현재형으로 결론낸다(`docs/runtime-state-audit.md:7-16`). 같은 최종 파일의 후속 main disposition은 F-02~F-05를 “결함이 아니라 명시적으로 수용된 한계”로 확정한다(`:184-199`), F-06은 계획에 반영됐고 F-01만 M3 pending이다(`tasks.yaml:795-808`). 따라서 최종 문서의 current finding count가 상단과 후단에서 다르다.

**영향.** M0-C audit exit를 읽는 소비자가 open finding 수를 6, 2, 또는 1 중 무엇으로 해석해야 하는지 알 수 없다.

**반증 조건.** 상단을 original audit result와 current disposition으로 분리해 현 상태를 명시하면 기각 가능하다.

## 내적 일관성 검증 — 통과한 항목

- baseline ref: annotated tag `baseline/0.12-refactor` → `7cfecd313da2240bd1e397ff1d81bae93a2fa543`.
- source SHA-256: `scripts/tests/run_tests.py` = `bd781a4337a481b94ac1170808b828191518a368eebea937520f3795122a0f2a`; ledger `docs/porting-ledger.md:14`와 일치.
- source inventory: 85 TestCase classes / 828 test methods / 828 unique fully-qualified IDs.
- ledger: 828 rows, 번호 1..828 연속, unique IDs 828, source 대비 missing/extra 0, source-line mismatch 0.
- 처분: port 818 + rewrite 10 + drop 0 = 828.
- 출력 등급: machine JSON 406 + diagnostic 264 + canonical artifact 134 + human CLI 14 + time/path 10 = 828.
- invariant/matrix: I-01~12 + E-01~09 각각 정확히 1행, 누락·중복 0; cancellation 독립 행 1개.
- matrix test reference: 72 occurrences / 56 unique; 56개 class.method 모두 source에 존재.
- ADR-0002~0012 모두 tracked file과 accepted status 존재.

## 재현 명령과 결과

```bash
git log -1 --format='%H %s' baseline/0.12-refactor
# 7cfecd313da2240bd1e397ff1d81bae93a2fa543 ...

git cat-file -t baseline/0.12-refactor
# tag

git tag -n99 baseline/0.12-refactor
# feature freeze message 포함

shasum -a 256 scripts/tests/run_tests.py
# bd781a4337a481b94ac1170808b828191518a368eebea937520f3795122a0f2a

wc -l scripts/tests/run_tests.py
# 21306

git ls-files 'docs/reviews/*freeze*' 'docs/reviews/*demotion*' | wc -l
# 0

git ls-files | rg -i '(^|/)(fixtures?|characterization)(/|\.|$)|legacy.*fixture|fixture.*legacy'
# rc=1, output 없음

rg -n -i 'legacy fixture|fixture set|legacy_fixture' docs dev_docs tasks.yaml PROGRESS.md scripts
# plan과 invariant의 일반 문구만 존재

rg -n -i 'normalized 비교|normalized comparison|normalization (rule|rules)|정규화 (규칙|계약|필드)|normalize (time|path)|time/path.*normal' docs dev_docs scripts
# 계획 1행 + ledger 표/10개 배정만 존재; field normalizer/comparator 없음

rg -n 'docs/reviews/runs|pr-demotion|run-uuid|UUIDv7|uuid7' scripts
# rc=1, canonical layout 구현 없음

rg -n '@unittest\.expectedFailure|expected-red|xfail' scripts/tests/run_tests.py
# rc=1, marker 0

git status --short
# output 없음 (clean)
```

ledger/source 및 matrix/source 검증에는 read-only Ruby parser를 사용했다. 결과:

```text
source=828 source_unique=828 ledger=828 ledger_unique=828 missing=[] extra=[]
rows=828 number_range=1..828 gaps=[] duplicate_numbers={} line_mismatches=0
dispositions={port:818,rewrite:10} grades={canonical:134,diagnostic:264,machine:406,human:14,time_path:10}
invariants=21 matrix=21 missing=[] extra=[] duplicates={}
matrix_refs=56 unique; missing=[]
```

첫 Ruby 집계 시 이 머신의 구 Ruby에 `Array#tally`가 없어 rc=1이었고, 동일 read-only 검사를 호환되는 hash counter로 다시 실행해 rc=0을 얻었다. repo에는 어떤 파일도 쓰지 않았다.

## 리스크와 M1-A 재심 조건

M1-A 승인 전 최소 재심 조건은 다음 네 가지다.

1. WS-CDX-1의 threat model 필수 축을 M0-B 문서에 고정한다.
2. WS-CDX-2의 characterization selection + legacy fixture set + I-10 gap을 닫는다.
3. WS-CDX-3의 등급 재배정과 dynamic field normalization/comparator를 executable하게 만든다.
4. WS-CDX-5~9의 계약 충돌 및 stale handoff를 한 authority로 동기화한다. 특히 JW-GPT-015 구현 task를 별도로 다시 열어야 한다.

이 보고서는 repo 파일·git ref·runtime state를 수정하지 않았다. merge 대상 commit은 없다.
