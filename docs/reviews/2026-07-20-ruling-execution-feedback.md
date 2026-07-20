<!-- waystone feedback: the body below is the reviewer reply VERBATIM (byte-exact copy via `waystone review ingest`) — do not edit it; a triage skeleton is appended beneath it. -->
round: 2026-07-20-ruling-execution
reviewer: codex:gpt-5.6-sol
reviewer-effort: ultra
review-target: 1f7d942b418025296704ff5bac4a13ac54d00ca5
reply-metadata-json: {"metadata":{"effort":"ultra","model":"codex:gpt-5.6-sol","request-digest":"sha256:c4d08a80fae8876813d79af615199860228c398b43958efeb7fb650de51859ff","review-target":"1f7d942b418025296704ff5bac4a13ac54d00ca5"},"narrative_digest":"sha256:c8c986b4ecbcaa961e42e61f2b863113bf52cb8dd9229af0059b0347771421e1","rendered_request_coverage_reason":null,"rendered_request_digest":"sha256:c4d08a80fae8876813d79af615199860228c398b43958efeb7fb650de51859ff","rendered_request_digest_matches":true}
ingested: 2026-07-20
source: /tmp/review.md
verbatim-bytes: 14311

---

model: codex:gpt-5.6-sol
effort: ultra
review-target: 1f7d942b418025296704ff5bac4a13ac54d00ca5
request-digest: sha256:c4d08a80fae8876813d79af615199860228c398b43958efeb7fb650de51859ff

# Verdict

CHANGES REQUESTED — blocker 1건, major 7건.

현재 full suite가 green이라는 사실은 이 판정을 바꾸지 않는다. 이번 라운드가 만든 acceptance 권위에는 스스로 달성할 수 없는 M1-A exit, 같은 변경이 약화할 수 있는 자기참조 gate, 그리고 실제로 fail-open하는 settlement/sunset 경계가 남아 있다.

## Confirmed findings

### WS-GPT-201 — blocker — M1-A exit는 여전히 동시에 달성할 수 없다

ADR-0014 Amendment는 M1-A를 동작·저장 형식 변경 0으로 고정하면서 `I-01~I-12·E-01~E-09 위반 0`과 현행 legacy suite green을 동시에 요구한다(`docs/adr/ADR-0014-m1a-acceptance-basis.md:109-115`). 그러나 target의 green suite는 그 invariant에 반하는 동작을 성공 조건으로 고정한다. E-08은 `unknown` 또는 running effect가 destructive resolution의 근거가 될 수 없다고 명시한다(`docs/invariants.md:36`). 반대로 `DelegateCorruptRecordTests.test_discard_accepts_corrupt_record`는 status와 exposure가 모두 unreadable인 record의 worktree 삭제와 `rc == 0`을 요구하고(`scripts/tests/run_tests.py:13748-13764`), `DelegateApplyTests.test_discard_cleanup_and_accepts_running`도 synthetic running record의 worktree 삭제를 요구한다(`scripts/tests/run_tests.py:13098-13110`). ledger와 matrix도 이들을 보존 계약이 아닌 E-08 역-계약으로 이미 분류했다(`docs/porting-ledger.md:816,822-824,849,853`; `docs/traceability-matrix.md:36,38,40-48`). 표적 test를 target에서 직접 실행해 1/1 green을 재현했다.

따라서 현행 동작과 suite를 보존하면 E-08 위반 0이 될 수 없고, E-08을 구현하면 동작 무변경 및 현행 suite green을 깨뜨린다. E-09에도 같은 독립 충돌이 있다. target은 executable identity를 size/mtime으로만 기록하지만(`scripts/delegate.py:1286-1322`), ledger는 이를 E-09 위반이라 확정하고 content digest 기반 rewrite를 요구한다(`docs/porting-ledger.md:782`). M1-A를 순수 기계 단계로 유지하려면 gate를 “pinned baseline 대비 신규 위반 0”처럼 알려진 debt와 분리해야 하고, 절대 위반 0을 유지하려면 동작 수정 범위와 suite rewrite를 M1-A에 명시적으로 포함해야 한다. 현재 문구로는 어느 구현도 합법적으로 exit할 수 없다.

### WS-GPT-202 — major — M1-A의 “현행 suite”는 같은 변경이 약화할 수 있는 자기참조 gate다

Amendment는 suite의 commit, test-ID manifest, assertion 비약화 조건을 고정하지 않고 남은 test가 green일 것만 요구한다(`docs/adr/ADR-0014-m1a-acceptance-basis.md:112-115`). 실제 method 수는 `baseline/0.12-refactor`의 828에서 review base의 833, target의 817로 변했다. 동시에 M1-A 범위 자체가 “테스트 기계적 분할”을 포함한다(`dev_docs/0.12.0-refactor-plan.md:641-645`), runner는 count/inventory assertion 없는 `unittest.main()`뿐이다(`scripts/tests/run_tests.py:21398-21399`).

실패 메커니즘은 단순하다. M1-A patch가 import 분할 중 test를 누락하거나 assertion을 약화해도 같은 patch의 축소된 suite가 green이면 ③을 통과한다. 이는 동작 drift를 검출하지 못하며 legacy 모사를 거부했는지도 증명하지 못한다. M1-A 시작 commit의 test identity와 기대 수를 외부 manifest로 pin하고, 의도적 변경은 별도 승인된 차이로만 허용해야 한다.

### WS-GPT-203 — major — M1-C에는 폐기한 legacy comparator가 아직 필수 exit로 남아 있다

ADR-0014는 재구축 마일스톤에서 legacy output equality와 legacy suite green이 필요조건도 충분조건도 아니라고 정한다(`docs/adr/ADR-0014-m1a-acceptance-basis.md:24-31,116-118`). 그러나 현행 계획의 M1-C는 여전히 “기존 delegate characterization green”, “old-new 출력 등급별 호환”, “구 관측 계약과 동일”을 exit로 요구한다(`dev_docs/0.12.0-refactor-plan.md:687-691`). Amendment는 마일스톤별 귀속을 계획서가 소유한다고 명시하므로(`docs/adr/ADR-0014-m1a-acceptance-basis.md:104-108`), 이 문구를 단순한 역사 기록으로 무시할 근거도 없다.

그 결과 같은 M1-C 구현이 ADR 기준으로는 통과하지만 계획 기준으로는 거부될 수 있고, 구현자는 노선 B가 폐기한 old-output 모사로 다시 유도된다. M1-C exit를 PC/invariant/accepted-ADR의 semantic contract로 다시 쓰고 legacy comparator 문구를 명시적으로 supersede해야 한다.

### WS-GPT-204 — major — 승격 inventory 검증은 한 방향뿐이며 criterion ② 의미가 실제로 무소유 상태다

confirmed 문서는 85 classes/828 methods를 검토했고, 명명하지 않은 assertion은 자동 승격되지 않으며 명시적 비승격은 누락과 구분한다고 선언한다(`docs/promoted-contracts.md:5,9-11,86-89`). 하지만 자체 validator는 각 PC가 참조한 class가 ledger에 존재하는지만 검사한다. ledger의 각 class가 PC 또는 비승격 중 정확히 한 결정에 들어갔는지는 역검사하지 않고, criterion ②가 필요한 누락도 검사하지 않는다(`docs/meta/agent-reports-2026-07-20/w2-acceptance-basis.md:27-55`).

역대조에서 `UninitializedRootGateTests`는 PC 행과 비승격 절 어디에도 없다. 그 핵심 계약은 초기화되지 않은 root에서 project state를 만들지 않는 것이고, 현재 test는 `.waystone` no-write를 직접 단언한다(`docs/porting-ledger.md:468-478`; `scripts/tests/run_tests.py:6837-6850`). 잘못된 root에 조용히 project state를 쓰는 것을 막으므로 criterion ② 경계다. legacy suite를 retire하면 이 class는 새 contract test 의무도 명시적 폐기 결정도 없이 사라질 수 있다. ADR-0011의 넓은 ProjectContext prose가 의미상 겹치더라도 이 legacy-covered assertion의 owning milestone/test가 등록되어 있지 않다. 전 85 classes에 대해 `promoted | explicitly non-promoted`의 reverse closure와 criterion ② 결정을 강제하고, 이 계약을 승격하거나 근거를 적어 비승격해야 한다.

### WS-GPT-205 — major — executable acceptance registry가 현재 코드와 어긋나고 ADR-0013 trust surface도 빠뜨린다

traceability matrix는 현재 실물 test가 모두 `scripts/tests/run_tests.py`에 있다고 명시하지만(`docs/traceability-matrix.md:3-13`), I-07 행은 삭제된 `MigrationV2Phase2Tests` method 4개를 현재 characterization/fault evidence로 계속 인용한다(`docs/traceability-matrix.md:23`). matrix의 56개 test reference를 HEAD와 기계 대조한 결과 누락은 정확히 그 4개였고, full suite green은 그 증거를 실행하지 않는다.

반대 방향의 공백도 있다. ADR-0013은 effect 시작·submit·completion·apply·cleanup마다 `owner_token + fencing_epoch + entity_version` CAS를 요구하고, OS lock handle 획득 뒤 DB tuple을 다시 확인하도록 정한다(`docs/adr/ADR-0013-operational-threat-model.md:118-144`). 이 순서는 ADR-0002의 fencing/positive-quiescence 계약과 문서상 정합하지만, matrix에는 ADR-0013 row가 없고, 신규 계약 의무 목록에도 principal/lock-order가 없으며(`docs/promoted-contracts.md:68-80`), M1-B의 5개 fault fixture도 token mismatch, lock→DB recheck, reclaim race를 검증하지 않는다(`dev_docs/0.12.0-refactor-plan.md:675-685`). 따라서 M1 구현이 이 CAS나 재확인을 누락해도 등록된 executable gate가 반드시 실패하지 않는다. matrix를 HEAD에서 재생성하고, ADR-0013의 mismatch/unknown, lock-acquire 뒤 stale tuple, reclaim race를 owning milestone의 필수 test로 등록해야 한다.

### WS-GPT-206 — major — settlement는 strict marker 뒤의 binding generation 충돌을 fail-open한다

binding filename regex는 sequence에 leading zero를 허용하고(`scripts/review.py:78-79`), identity는 이를 정수화한다(`scripts/review.py:507-512`). 따라서 `request.binding-2.json`과 `request.binding-02.json`은 같은 논리 generation이다. `latest_round_request_binding`은 `(sequence, path 문자열)`의 max 하나만 고르고 나머지 동세대 후보를 검사하지 않으며(`scripts/review.py:515-532`), settlement는 그 선택된 binding 한 파일의 SHA만 비교한다(`scripts/review.py:637-648,1147-1154,1227-1240`).

최소 fixture에서 hash-valid settlement와 canonical `-2` binding을 만든 뒤 target이 다른 `-02`를 추가했다. 두 identity는 모두 sequence 2였지만 canonical `-2`가 선택되어 결과는 `actionable=0`, `archived_unverifiable=1`로 유지됐다. 이는 PC-10의 배타적 generation/collision/corrupt-latest→pending·unknown 계약(`docs/promoted-contracts.md:36`)에 반한다. 또한 binding reader는 ordinary `json.loads`를 사용해 duplicate field를 거부하지 않으며(`scripts/review.py:456-492`), duplicate `target_sha` fixture도 정상 binding으로 수용했다. marker JSON 자체의 strict parser만으로 authority chain 전체가 fail-closed가 되지 않는다. sequence를 canonical `[1-9]\d*`로 제한하고, 논리 identity별 후보 수가 1이 아니면 round를 pending/unknown으로 만들며, binding에도 duplicate-key rejection을 적용해야 한다. 현재 저장된 settlement 3건의 request/binding/feedback SHA는 모두 재계산 일치했지만 이 잠재 우회를 제거하지 않는다.

### WS-GPT-207 — major — sunset detector가 상충하는 preserved profile authority를 완료된 seed로 오인한다

현재 detector는 preserved host root에서 project slug별 resume/start_here/overlay/exposure/delegations/worktrees만 검사하고 `profile.yml`은 비교하지 않는다(`scripts/common.py:412-441`). 반면 base의 0.11 migrator는 Claude/Codex profile bytes가 다르면 live profile 존재 여부와 무관하게 typed conflict로 중단했다(`197b2cfa643f16188111e68a2c2f2255efd481c7:scripts/common.py:1322-1331`; 삭제된 regression test `197b2cfa...:scripts/tests/run_tests.py:17889-17910`). target의 acceptance test는 두 preserved profile과 이미 존재하는 live profile이 모두 같은 성공 사례만 검증한다(`scripts/tests/run_tests.py:17847-17864`).

서로 다른 Claude/Codex preserved profile을 만들고 live profile을 두지 않은 최소 fixture에서 `migrate_project_state`는 예외 없이 `False`를 반환했고 live profile도 생성하지 않았다. 즉 인간이 작성한 reviewer/executor routing authority가 해결되지 않았는데도 0.12는 지원 상태로 판정하여 0.11.x/manual-resolution 안내를 생략한다. preserved profile은 모두 동일하고 live profile과도 일치할 때만 완료된 seed로 수용하고, 그 외에는 원본을 보존한 typed refusal이어야 한다.

### WS-GPT-208 — major — pending-worktree marker directory의 symlink/non-directory가 detector를 우회한다

`_checked_entries`는 대상이 symlink 또는 non-directory면 빈 목록을 반환한다(`scripts/common.py:353-363`). marker 검사에서는 실제 directory일 때만 `*.migrating`을 offender로 추가하고, symlink/non-directory container 자체는 추가하지 않는다(`scripts/common.py:435-441`). base 0.11의 `_pending_worktree_markers`는 같은 경로를 `_real_directory`로 검증해 이 상태를 거부했다(`197b2cfa...:scripts/common.py:1236-1255`). 현재 test는 real directory 안의 ordinary marker만 다룬다(`scripts/tests/run_tests.py:17832-17845`).

`~/.waystone/cache/worktrees/<slug>`를 `did-pending.migrating`이 있는 directory로 향하는 symlink로 만든 fixture에서 detector는 다시 `False`를 반환했다. 부분 migration evidence를 숨긴 채 일반 current layout으로 진행하는 fail-open이다. marker container가 존재하면서 real directory가 아니면 container 자체를 offender로 보고, no-follow symlink와 regular-file cases를 acceptance test에 추가해야 한다.

## Open domain questions

1. M1-A는 정말로 순수 기계 단계인가, 아니면 알려진 E-08/E-09 debt를 고치는 첫 재구축 단계인가? 전자라면 absolute invariant-zero를 제거하고 pinned debt 대비 non-regression으로 정의해야 하며, 후자라면 동작 무변경과 현행-suite 조건을 제거해야 한다. 현재 문서만으로 둘 중 하나를 선택할 수 없다.
2. `decision/legacy-settlement-additional-cohort`의 추가 3건은 이번 3건과 같은 정책으로 정착할지 별도 사용자 ruling이 필요하다. 그 전에는 actionable 상태를 유지해야 하며 이번 marker 정책을 자동 확장하면 안 된다.

## Residual risks from unavailable GPU / data / environment

- GPU나 외부 dataset 의존성은 없었고, 이용 불가 자원 때문에 확인하지 못한 finding은 없다.
- M1 engine/store 구현이 아직 없으므로 ADR-0013의 실제 CAS/lock race는 동적 실행할 수 없었다. 문서 간 순서는 정합하다고 확인했지만 WS-GPT-205의 executable gate 공백은 구현 전 반드시 닫아야 한다.
- 타 머신의 전체 historical layout 조합은 없었다. 다만 WS-GPT-207/208은 임시 HOME fixture로 직접 재현했으며 filesystem 판정 로직 자체의 fail-open이다.

## Independent verification

- `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py`: 직접 실행 rc=0; target test method inventory 817.
- `DelegateCorruptRecordTests.test_discard_accepts_corrupt_record`: 직접 실행 1/1 green.
- settlement generation-alias fixture: same logical sequence 2 두 개, `actionable=0`, `archived_unverifiable=1`; duplicate binding key도 accepted.
- sunset fixtures: divergent preserved profiles와 symlink marker directory 모두 `migrate_project_state == False`로 통과.
- current settlement marker 3건: 각 request/binding/feedback SHA 재계산 일치.
- matrix 56개 test reference 대조: HEAD 누락 4개, 모두 `MigrationV2Phase2Tests`.
- review target HEAD는 `1f7d942b418025296704ff5bac4a13ac54d00ca5`, worktree는 clean이며 어떤 repository file도 수정하지 않았다.


---

<!-- waystone triage: BEGIN -->
## Finding triage (main 판정, 2026-07-20 — 201~205 main 직접 검증 + 206~208 독립 opus verifier 재현 검증)

| finding | verdict | type | evidence / 처분 | task |
|---|---|---|---|---|
| WS-GPT-201 | REAL (blocker 유지) | verification | ledger #473/#510/#516이 E-08 반-계약 rewrite로 분류(settled)돼 있어 "절대 위반 0 + 동작 무변경 + 현행 suite green"은 동시 성립 불가 — main 확인. 폐쇄 = ADR-0014 Amendment 2 §1-3: known-debt 목록 고정 + exit ②를 "debt 대비 신규 위반 0"으로 + M1-A 순수 기계 단계 ruling(open question 1 답변) | docs/adr-0014-amendment2-m1a-debt-and-suite-pin |
| WS-GPT-202 | REAL (major 유지) | verification | Amendment 1 ③에 suite 고정 부재 — 같은 patch가 suite 축소해도 통과하는 자기참조. 폐쇄 = Amendment 2 §4: 착수 시점 test-ID manifest pin + 승인된 차이 목록 외 변경 불허 | docs/adr-0014-amendment2-m1a-debt-and-suite-pin |
| WS-GPT-203 | REAL (major 유지) | architecture | plan M1-C exit 원문("기존 delegate characterization green / old-new 출력 등급별 호환 / 구 관측 계약과 동일") 확인 — ADR-0014와 이중 기준. semantic contract 기준으로 supersession | docs/plan-m1c-exit-supersession |
| WS-GPT-204 | REAL (major 유지) | verification | UninitializedRootGateTests가 승격·비승격 어디에도 부재(rg rc=1) — validator가 단방향임을 확인. reverse closure + PC-31 승격 | docs/promoted-reverse-closure-and-pc31 |
| WS-GPT-205 | REAL (major 유지) | verification | matrix I-07이 삭제된 MigrationV2Phase2Tests 4건 인용(suite rg rc=1) + ADR-0013 row/의무 부재 확인. matrix HEAD 재생성 + ADR-0013 fault 의무(token mismatch·lock 후 recheck·reclaim race) 등록 | docs/matrix-regen-adr13-obligations |
| WS-GPT-206 | REAL (major 유지) | correctness | verifier 실라운드(fix-wave) 재현: -02 alias 추가에도 archived 유지, duplicate-key binding 수용. regex 단독 수리는 불충분(glob이 흡수) — ≠1 후보→pending 규칙이 하중. 3종 수리 | fix/review-binding-generation-collision |
| WS-GPT-207 | REAL (major 유지) | correctness | verifier 재현: preserved 분기 profile → 조용한 False(plain root 동형은 typed 거부 — 비대칭), 구 0.11 conflict 거부 테스트가 후계 없이 삭제. "정상 완료 이관은 분기 profile 불가" 논증으로 설계 방어 반박 | fix/sunset-preserved-profile-divergence |
| WS-GPT-208 | REAL (major 유지) | correctness | verifier 대조 재현: real dir 거부 True vs symlink container False(fail-open), 구 0.11 _real_directory typed 거부 회귀, ADR-0013:52 위반. 형제 helper는 올바름 = 국소 불일치 | fix/sunset-marker-container-symlink |

open question 1(M1-A 성격)은 Amendment 2 §3이 ruling으로 답변(순수 기계 단계). open question 2(추가 3건 정착)는 기존 decision/legacy-settlement-additional-cohort가 소유 — 자동 확장 안 함(리뷰어 권고와 일치).
<!-- waystone triage: END -->
