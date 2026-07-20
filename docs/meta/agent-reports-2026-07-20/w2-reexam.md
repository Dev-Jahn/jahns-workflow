VERDICT: M0-exit 재심 FAIL — blocker 1 / major 1 / minor 2; 원 판정표의 비완전 10행은 9 해소 + 1 전환 소멸이나, 새 M1-A scope/exit 계약이 동시에 성립하지 않음
COMMITS: none
HOTFILES: `dev_docs/0.12.0-refactor-plan.md` §3-3·§4 E-09·§5-2·M0-B exit·M1-A read-only; `scripts/review.py`·`scripts/common.py` 미접촉; `scripts/tests/run_tests.py` 수정 없이 full suite로만 실행
VERIFIED: `git status --short` (전·후 rc=0, output 없음); E-09 추출 비교 `equal=true` (각 760 chars, rc=0); baseline suite SHA-256 `bd781a4337a481b94ac1170808b828191518a368eebea937520f3795122a0f2a` (rc=0); `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"` → suite rc=0, Ran 817 tests, OK
NOT-RUN: `waystone` CLI(명시적 금지); ruff(저장소 변경 0); 구현·fixture mutation

# M0 exit 경량 재심

## 결론

원 리뷰의 완전 충족이 아니었던 10행 자체는 현재 tracked 문서에서 모두 폐쇄됐다. 9행은 현재
anchor로 해소됐고, 실행 불가능했던 legacy 출력 comparator 행은 ADR-0014가 정확한 구 gate를
명명해 명시적으로 supersede하므로 전환 소멸했다.

그러나 병렬 작성 문서 사이에서 새 blocker를 발견했다. 계획은 M1-A를 동작·저장 형식 변경 없는
mechanical-only 범위로 유지하고 review·policy 이동을 금지하지만, ADR-0014의 새 M1-A exit는
PC-01~PC-30 전량의 새-system 계약 테스트 green을 요구한다. 두 계약은 동시에 만족할 수 없다.
따라서 **원 판정표 폐쇄 여부와 별개로 현재 M1-A 착수는 NO-GO**다.

## 원 Exit 기준 판정표의 비완전 행 재심

| # | 원 판정 행 | 현재 판정 | 현재 tracked anchor와 반증 결과 |
|---:|---|---|---|
| 1 | M0-B 최소 operational threat model — 미충족 | **해소** | 요구축은 `dev_docs/0.12.0-refactor-plan.md:617-619`. accepted ADR-0013은 보호/비보호 경계(`docs/adr/ADR-0013-operational-threat-model.md:23-33`), 기존 계약 흡수(`:35-43`), permission·symlink·env·lease 전 축과 fail 방향(`:44-55`), closed child-env allowlist(`:93-116`), opaque lease principal과 CAS(`:118-144`)을 고정한다. |
| 2 | M0-B fact authority matrix — 미충족 | **해소** | ADR-0005가 계획 §5-2를 권위 원천으로 명시한다(`docs/adr/ADR-0005-fact-authority-matrix.md:3-7`). 계획은 machine-tier 경계를 추가하고(`dev_docs/0.12.0-refactor-plan.md:467-480`), §5-2에 canonical project mapping과 profile 전이 권위를 명시했다(`:484-504`, 특히 `:492-493`). adjudication의 잔여 §5-2 back-reference가 닫혔다. |
| 3 | M0-B closeout manifest 최소 계약 — 미충족 | **해소** | Amendment 우선순위와 구 cardinality 폐기(`docs/adr/ADR-0006-run-closeout-manifest.md:55-61`), 계획 대비 deviation(`:63-78`), 9-field schema와 frozen-closure multi-task mapping(`:80-110`), no-result terminal tagged pair·unknown 거부(`:112-136`), exact canonical path/CAS(`:138-150`)가 원 finding의 네 세부를 모두 닫는다. |
| 4 | I-01~12·E-01~09 확정 — 부분 미충족(E-09) | **해소** | precedence가 명시됐다(`docs/invariants.md:4-6`). E-09 본문은 invariants `:37`과 계획 `dev_docs/0.12.0-refactor-plan.md:437`이 추출 비교상 문자 단위로 동일하고, 계획은 ADR-0009 supersession을 명시한다(`:440-444`). |
| 5 | M0-C contract-level test 선별·태깅 — 판정불가 | **해소** | ledger가 baseline source SHA와 85 classes/828 methods의 닫힌 inventory를 고정하고(`docs/porting-ledger.md:3-18`) method별 판정 규칙을 둔다(`:20-33`). ADR-0014는 이를 characterization 기록·채굴 체크리스트로 재분류한다(`docs/adr/ADR-0014-m1a-acceptance-basis.md:55-60`). 보존/비승격 의미 경계는 PC-01~30과 비승격 목록에 닫혀 있다(`docs/promoted-contracts.md:20-65,85-133`). 확정 상태 문구의 별도 모순은 WS-RX-2다. |
| 6 | M0-C 출력 등급 합계 — 산술 충족, gate 미충족 | **전환 소멸** | ADR-0014가 legacy 등급을 acceptance에서 제외하고(`:24-31`) suite를 retire-by-default로 전환한다(`:33-38`). 구 M1-A r3 등급표 전체를 정확히 명명해 supersede하고 WS-CDX-3 소멸을 선언한다(`:62-75`). 계획에도 동일 banner가 있다(`dev_docs/0.12.0-refactor-plan.md:647-648`). |
| 7 | M0-C traceability matrix — 구조 충족, I-10 gap | **해소(명시적 M1 이월)** | matrix는 21 invariant와 독립 cancellation 행 및 M1 TODO의 의미를 명시한다(`docs/traceability-matrix.md:3-15,17-38`). I-10·E-04·E-08·cancellation 공백은 각각 `:26,32,36,38`에 숨김없이 기록됐고 새 계약 테스트 의무로 등록됐다(`docs/promoted-contracts.md:67-83`). 골격 exit는 충족하며 gap은 M1 구현 입력이다. |
| 8 | M0-C legacy fixture set — 미충족 | **해소** | 적대 검증은 SHA-pinned closed ledger와 `run_tests.py` inline fixture를 반증 증거로 수용했다(`docs/meta/agent-reports-2026-07-20/m0-exit-adjudication.md:18-20`). ledger pin은 `docs/porting-ledger.md:14-18`; `git show baseline/0.12-refactor:scripts/tests/run_tests.py \| shasum -a 256` 재검증값도 ledger와 동일하다. 별도 fixture directory를 요구한 원 리뷰의 형태 가정은 유지되지 않는다. |
| 9 | M0-C runtime-state audit — 산출물 충족, 현재 verdict 불명료 | **해소** | 상단이 감사 시점 6건과 현재 처분을 분리했다(`docs/runtime-state-audit.md:9-24`). 상세 처분은 F-01/F-06 task와 F-02~05 수용 잔여로 일치한다(`:192-221`); 계획의 machine-tier 반영도 `dev_docs/0.12.0-refactor-plan.md:467-480`에 있다. |
| 10 | M0-C 핵심 flow observable contract — 판정불가 | **해소** | PC-01~30이 tracked-record/review/delegation/policy 보존 의미를 열거하고(`docs/promoted-contracts.md:20-65`), legacy coverage 없는 필수 계약(`:67-83`)과 비승격 경계(`:85-133`)도 닫는다. ADR-0014는 이 의미를 새 architecture 경계의 계약 테스트로 다시 쓰도록 요구한다(`docs/adr/ADR-0014-m1a-acceptance-basis.md:33-38,68-72`). 확정 상태 문구의 별도 모순은 WS-RX-2다. |

요약: **해소 9 / 전환 소멸 1 / 미해소 0**.

## adjudication의 비-행 finding 처분 확인

- WS-CDX-4: 구현 vehicle `feat/review-runs-uuid-owner-directory`가 등록됐고(`tasks.yaml:152-155`),
  계획 M1-B가 UUID owner directory 의존을 명시한다(`dev_docs/0.12.0-refactor-plan.md:668-672`).
- WS-CDX-6: ADR-0005 UUIDv7 계약(`docs/adr/ADR-0005-fact-authority-matrix.md:33-46`)과 계획의
  두 supersession note(`dev_docs/0.12.0-refactor-plan.md:195-197,509-510`)가 canonical grammar를
  하나로 만든다.
- WS-CDX-8: ledger #473/#486은 `settled`로 갱신됐고(`docs/porting-ledger.md:764,782`), matrix도
  positive absence proof와 content digest ruling을 반영한다(`docs/traceability-matrix.md:53-62`).
- WS-CDX-10: 원 matrix anchor는 ADR heading 이름으로 고쳐졌다(`docs/traceability-matrix.md:3-5`).
  다만 새 promoted 문서가 같은 stale shorthand를 다시 만들었다(WS-RX-4).
- WS-CDX-11: 위 표 9행대로 current/as-of 분리가 완료됐다.

## 새 교차 모순 findings

### WS-RX-1 — blocker — M1-A의 고정 scope와 새 exit가 동시에 성립하지 않는다

**주장.** 계획은 M1-A를 `Mechanical structure only (동작·저장 형식 변경 0)`로 두고 새 package,
composition root, kernel 경계의 기계적 추출만 허용하며 improve/overlay/review 이동을 명시적으로
M2 이후로 미룬다(`dev_docs/0.12.0-refactor-plan.md:163-165,641-645`). ADR-0014도 구 출력 exit만
supersede하며 **구현 범위는 다시 결정하지 않는다**고 명시한다
(`docs/adr/ADR-0014-m1a-acceptance-basis.md:62-66`).

동시에 새 M1-A exit는 main-confirmed 승격 계약 각각에 새-system 계약 테스트가 존재하고 모두
green일 것을 요구한다(`:68-72`). promoted header는 PC-01~PC-30 전량을 confirmed로 선언한다
(`docs/promoted-contracts.md:3`). 여기에는 canonical review reader/writer·legacy adapter 계약
PC-09~14(`:34-39`)와 **새 policy state machine** 계약 PC-25~26(`:60-61`)이 포함된다. 이는 계획이
M1-A에서 이동하지 않는다고 한 review·policy 기능이다.

**영향.** M1-A 범위를 지키면 confirmed exit를 만족할 수 없고, exit를 만족하려 범위를 넓히면
계획과 ADR-0014의 “scope 미재결정”을 위반한다. 결과를 보기 전에 고정된 합격 기준이 달성 불가능하므로
M1-A run spec을 정당하게 freeze/dispatch할 수 없다. M1-A 착수 blocker다.

**반증 조건.** 동작 변경·review/policy 이동 없이 PC-01~PC-30의 새-system 계약 테스트를 모두
green으로 만들 수 있는 현재 tracked implementation/task mapping을 제시하거나, M1-A scope 또는
exit의 authoritative milestone mapping을 명시적으로 개정하면 기각할 수 있다.

### WS-RX-2 — major — 승격 목록이 같은 revision에서 확정과 미확정을 동시에 선언한다

**주장.** `docs/promoted-contracts.md:3`은 `confirmed v1 — main 인수 ... PC-01~PC-30 전량`이라고
선언하지만, 제목과 본문은 여전히 `main 인수용 초안`, `후보 목록`, `아직 확정 gate가 아니다`라고
현재형으로 말한다(`:1,7-10,20`). ADR-0014는 이 파일을 후보 초안으로 부르고 main이 확정한 행만
세 번째 acceptance set에 들어간다고 한다(`docs/adr/ADR-0014-m1a-acceptance-basis.md:52-53`).

**영향.** 같은 tracked revision에서 M1-A의 세 번째 계약 집합을 PC-01~30 전량과 미확정 빈 집합으로
다르게 계산할 수 있다. header와 사용자 ruling으로 의도는 복구 가능하므로 blocker보다는 major지만,
pre-registered gate membership은 단일하지 않다.

**반증 조건.** `:3`이 confirmation이 아닌 다른 상태임을 정의한 authority를 제시하거나, header와
후보/초안 문구를 하나의 확정 상태로 동기화하면 기각할 수 있다.

### WS-RX-3 — minor — action schema의 `lease_epoch`가 accepted `fencing_epoch` 계약과 이름이 갈린다

**주장.** 계획 §3-3의 action 최소 field는 `lease_epoch`라고 쓰지만 바로 다음 submit 검증은
`fencing epoch`를 검사한다(`dev_docs/0.12.0-refactor-plan.md:183-185`). repo 문서에서
`lease_epoch`의 계약 정의는 이 한 번뿐이고, ADR-0002의 claim/CAS(`docs/adr/ADR-0002-external-effect-commit-protocol.md:29,58-74`),
ADR-0003 process binding(`docs/adr/ADR-0003-run-observability-and-cancellation.md:139-170`),
ADR-0013 lease principal tuple(`docs/adr/ADR-0013-operational-threat-model.md:118-144`)은 모두
`fencing_epoch` 하나를 사용한다.

**영향.** accepted ADR로 correctness 의미는 복구 가능하지만 action schema 구현자는 두 필드인지
오타/alias인지 판단해야 한다.

**반증 조건.** `lease_epoch`와 `fencing_epoch`의 별도 의미·mapping을 정의한 current anchor를
제시하거나 §3-3 필드명을 accepted ADR과 동기화하면 기각할 수 있다.

### WS-RX-4 — minor — 새 promoted 문서가 폐쇄한 stale ADR section anchor를 다시 도입한다

**주장.** `docs/promoted-contracts.md:79,116`은 `ADR-0003 §3-9`를 참조하지만 ADR-0003에는 번호
`§3-9`가 없고 실제 anchor는 `취소, quiescence, cleanup 안전 계약`
(`docs/adr/ADR-0003-run-observability-and-cancellation.md:103`)이다. `§3-9`는 계획의 번호이며,
matrix는 이미 정확한 ADR heading으로 고쳐졌다(`docs/traceability-matrix.md:3-5`).

**영향.** 의미는 인접 문구로 복구 가능하지만 provenance/navigation이 다시 잘못된 대상을 가리킨다.

**반증 조건.** ADR-0003에 실제 numbered §3-9 anchor가 존재함을 보이거나 promoted 참조를 named
ADR heading 또는 계획 §3-9로 정정하면 기각할 수 있다.

## 요청된 교차 각도의 무-finding 결과

- **ADR-0013 env ↔ ADR-0012:** ADR-0012는 relevant environment를 command input digest에 결속하고
  환경 변경 시 새 freeze/preflight를 요구한다(`docs/adr/ADR-0012-verification-capability-preflight.md:32-46,50-72`).
  ADR-0013의 empty-map closed allowlist와 동일 effective environment 요구(`:93-113`)는 정밀화이며
  충돌이 아니다.
- **ADR-0013 lease ↔ ADR-0002/0003:** supervisor-owned owner token, fencing epoch, entity version CAS는
  ADR-0002 `:58-74`와 ADR-0003 `:139-170`에 일치한다. WS-RX-3의 field 이름 외 의미 충돌은 없다.
- **ADR-0014 승격 경계 ↔ ADR-0013:** ADR-0013은 accepted(`docs/adr/ADR-0013-operational-threat-model.md:3`)이므로
  ADR-0014 acceptance set 2에 자동 포함된다(`docs/adr/ADR-0014-m1a-acceptance-basis.md:24-28`).
  promoted 문서도 legacy 승격 후보와 accepted-ADR 직접 의무를 분리한다(`docs/promoted-contracts.md:67-70`).
  별도 PC 행 부재는 계약 누락이나 중복이 아니다.
- **closeout ↔ review namespace:** closeout은 오직 `docs/runs/<run-id>/closeout.yaml`
  (`docs/adr/ADR-0006-run-closeout-manifest.md:138-150`), review evidence는 오직
  `docs/reviews/runs/<run-uuid>/...`(`docs/adr/ADR-0009-review-artifact-addressing.md:28-54`)다.
  ADR-0006도 review protocol을 별도 Git authority로 명시한다(`:77`). 공존 경계가 명확하다.
- **UUIDv7:** ADR-0005 `:33-46`, 계획 `:195-197,509-510`, ADR-0006 `:146-150`, ADR-0009
  `:42-46`이 RFC 9562 UUIDv7 lowercase grammar와 path/payload 일치를 일관되게 요구한다.
- **E-09:** 계획 `:437`과 invariants `:37`의 본문 추출 비교는 `equal=true`이고, promoted PC-29와
  신규 E-09 의무(`docs/promoted-contracts.md:64,78`)도 같은 durable/incidental 경계를 유지한다.

## 재현·검증 명령

```bash
git status --short
# rc=0, output 없음 (검토 전·full suite 후 모두 clean)

ruby -e 'a=File.readlines("docs/invariants.md").find { |l| l.start_with?("| E-09 |") }.split("|")[2].strip; b=File.readlines("dev_docs/0.12.0-refactor-plan.md").find { |l| l.start_with?("| **E-09**") }.split("|")[2].strip; puts "equal=#{a == b} invariants_chars=#{a.length} plan_chars=#{b.length}"; exit(a == b ? 0 : 1)'
# rc=0: equal=true invariants_chars=760 plan_chars=760

git show baseline/0.12-refactor:scripts/tests/run_tests.py | shasum -a 256
# rc=0: bd781a4337a481b94ac1170808b828191518a368eebea937520f3795122a0f2a  -

rg -n "UUIDv7|timestamp-slug-random|Canonical publication path|docs/runs/<run-id>|docs/reviews/runs/<run-uuid>" \
  docs/adr/ADR-0005-fact-authority-matrix.md \
  docs/adr/ADR-0006-run-closeout-manifest.md \
  docs/adr/ADR-0009-review-artifact-addressing.md \
  dev_docs/0.12.0-refactor-plan.md
# rc=0; ADR-0005:35,45 / ADR-0006:138,143 / ADR-0009:34,42 / plan:195,509

rg -n "ADR-0003 §3-9|lease_epoch|confirmed v1|아직 확정 gate" \
  docs/promoted-contracts.md dev_docs/0.12.0-refactor-plan.md
# rc=0; promoted:3,7,79,116 / plan:184

env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"
# suite rc=0; /tmp/suite.log: Ran 817 tests in 94.620s; OK
```

저장소 파일·git ref·runtime state는 수정하지 않았다. 보고서 외 산출물과 commit은 없다.
