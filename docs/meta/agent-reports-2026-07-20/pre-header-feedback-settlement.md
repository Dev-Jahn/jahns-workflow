VERDICT: PASS — 등록 당시 역사 cohort 3건을 증거로 특정했고 세 settlement 옵션을 비교했으며, Git-tracked `archived-unverifiable` marker를 단일 권고안으로 제시한다; 현재 HEAD에는 동일 계열 residual 3건이 추가로 보여 구현 전 범위 확인이 필요하다.
COMMITS: none
HOTFILES: run_tests.py 미접촉; common.py 미접촉; delegate.py 미접촉. scripts/review.py와 scripts/round.py는 판정 경로만 읽었고 수정하지 않았다.
VERIFIED: `git ls-tree -r --name-only ea6292a docs/reviews | rg -- '-feedback\.md$' | sort` rc=0(등록 시점 feedback 정확히 3개); `nl -ba`/`rg`로 scripts/review.py·3개 feedback·binding·main `.waystone` 상태 교차 관찰 rc=0; 3개 request/binding/feedback `shasum -a 256` rc=0; 최종 `git status --short`/`git diff --stat`로 repo 변경 없음 확인 rc=0.
NOT-RUN: `waystone` CLI 전부; pending live 실행; 표적/전체 테스트; re-ingest·marker 생성·어떤 구현도 수행하지 않았다. 이 기는 read-only 분석이며 보고서만 작성했다.

# 결론

권고는 **(a) 원문과 분리된 Git-tracked `archived-unverifiable` marker**다. 이것은 역사 feedback을 “검증 완료”로 승격하지 않는다. 다만 사용자가 더 이상 새 회신을 기다리지 않기로 정착시킨 역사 receipt임을 별도 disposition으로 기록하여 actionable pending 집계에서만 뺀다. marker는 각 라운드의 정확한 request, 최신 binding, feedback bytes의 SHA-256에 결속해야 한다. 파일이 바뀌거나 새 binding이 발행되면 marker가 자동으로 stale되어 pending이 다시 열린다.

이 선택은 세 가지를 동시에 만족한다.

1. 기존 feedback bytes와 path provenance를 고치지 않는다.
2. 구조적으로 증명할 수 없는 review-target/generation을 “완료”라고 주장하지 않는다.
3. 프로젝트별 사용자 결정을 제품 코드의 날짜 cutoff나 round-id allowlist에 숨기지 않는다.

단, task의 “3건”은 **task 등록 시점의 원래 cohort**다. 현재 HEAD에는 이후 추가된 old-envelope feedback 3건도 있다. 아래에서 둘을 구분한다.

# 1. pending 판정 위치와 규칙

프로젝트는 packet mode이고 reviews dir은 `docs/reviews`다(`.waystone.yml:6,10-12`). 판정의 단일 핵심은 `scripts/review.py:997-1095`의 `pending_reviews()`다.

1. `*-request.md`가 후보 라운드를 만든다(`scripts/review.py:1008-1016`).
2. filename sequence상 최신 `*-request.binding*.json`만 선택한다. 최신 후보가 손상되면 과거 binding으로 fallback하지 않고 unknown으로 남긴다(`scripts/review.py:509-526,1017-1029`).
3. `<round>-feedback.md`는 `read_feedback_reply_metadata()`로 읽고 request/narrative projection도 최신 binding에서 재현되는지 확인한다(`scripts/review.py:1031-1035`).
4. 완료로 pending에서 빠지는 조건은 다음 네 가지가 모두 참일 때뿐이다(`scripts/review.py:1036-1053`).
   - 유효한 최신 binding이 존재한다.
   - request/narrative projection 불일치가 없다.
   - verbatim reply에서 재파생한 `review-target`이 최신 binding과 일치한다.
   - v2는 두 generation digest가 일치하고, genuine v1은 명시된 legacy coverage 조건을 만족한다.
5. reviewer model이 configured인지와 effort는 coverage 정보이지 receipt 완료 게이트가 아니다(`scripts/review.py:1040-1041`; unconfigured model 완료 characterization은 `scripts/tests/run_tests.py:5694-5705`).
6. receipt 손상은 `feedback-receipt-corrupt`, target 부재/불일치는 matching unavailable/mismatch로 남아 pending row가 된다(`scripts/review.py:1055-1094`).

`review pending`, packet `review status`, prompt statusline, round-close reminder가 모두 이 파생값을 소비한다(`scripts/review.py:2518-2536`; `scripts/waystone.py:124-137`; `scripts/round.py:418-427`). round close 자체는 reminder 때문에 실패하지 않는다.

## 두 종류의 “헤더”를 구분해야 한다

현재 reply parser는 verbatim body의 선두 key/value block에서 `model`, `effort`, `review-target`, `request-digest`를 읽는다. blank와 선택적 Markdown fence를 허용하고 32줄/16 KiB로 제한한다(`scripts/review.py:207-315`). target은 단일 target SHA prefix 또는 `base-target` range로 binding과 대조한다(`scripts/review.py:318-331`).

그러나 parser에 도달하기 전에 feedback 파일 자체의 strict receipt envelope가 통과해야 한다.

- 고유한 `verbatim-bytes`와 canonical separator가 있어야 한다(`scripts/review.py:825-840`).
- 그 길이로 계산한 body boundary 뒤에 정확한 triage BEGIN/END marker가 있어야 한다(`scripts/review.py:841-856`).
- outer header에 정확히 하나의 `round:`와 `reply-metadata-json:`이 있어야 한다(`scripts/review.py:875-911`).
- cached metadata는 verbatim body 재파생값과 일치해야 한다(`scripts/review.py:912-920`).

즉 body 안에 정상 `review-target`이 있어도 old outer envelope이면 body를 읽기 전에 `feedback-receipt-corrupt`가 된다. 이 fail-closed 계약은 `scripts/tests/run_tests.py:4964-4988`에 고정돼 있다. 단순 파일 존재만으로 pending을 닫지 않는 계약도 `scripts/tests/run_tests.py:5503-5524`에 있다.

# 2. 원래 3개 라운드의 특정

현재 registry는 이 task를 “역사 feedback 3라운드”로 정의한다(`tasks.yaml:510-513`). 최초 등록 맥락도 `PROGRESS.md:123-134`, 특히 `PROGRESS.md:131`, 그리고 당시 review request의 Known weak spot(`docs/reviews/2026-07-18-carrier-lanes-fixes-request.md:42-46`)에 남아 있다.

등록 커밋 `ea6292a`에서 다음 read-only 명령을 실행하면 feedback이 정확히 아래 세 개뿐이다.

```bash
git ls-tree -r --name-only ea6292a docs/reviews | rg -- '-feedback\.md$' | sort
```

```text
docs/reviews/2026-07-16-adopt-dogfooding-feedback.md
docs/reviews/2026-07-16-fix-wave-feedback.md
docs/reviews/2026-07-18-carrier-lanes-feedback.md
```

따라서 task가 지칭한 원래 cohort는 다음과 같다.

| round | tracked evidence와 형식 | machine-local 관찰 | 완료를 막는 정확한 이유 |
|---|---|---|---|
| `2026-07-16-adopt-dogfooding` | feedback outer header는 `round`, `reviewer`, `reviewer-note`, `ingested`, `source` 뒤 바로 `---`이며 body는 `# 리뷰 결과`로 시작한다(`docs/reviews/2026-07-16-adopt-dogfooding-feedback.md:1-14`). `reply-metadata-json`, `verbatim-bytes`, triage markers뿐 아니라 body structured header도 없다. | main `.waystone/overlay/review-ingests.jsonl:1`에 packet ingest event가 있다. | strict envelope가 corrupt다. 더 근본적으로 request는 review target을 `2035801…`로 명시하고(`docs/reviews/2026-07-16-adopt-dogfooding-request.md:5-6`) feedback도 `925acd5..2035801`을 검토했다고 서술하지만(`docs/reviews/2026-07-16-adopt-dogfooding-feedback.md:10-14`), 최신 binding은 `c8ec816…`이다(`docs/reviews/2026-07-16-adopt-dogfooding-request.binding.json:1`). 정직한 target 복원도 binding과 맞지 않는다. |
| `2026-07-16-fix-wave` | old outer envelope에는 receipt metadata/length/markers가 없지만 body 선두에는 raw `model`, `effort`, `review-target: 84ad6a…`가 있다(`docs/reviews/2026-07-16-fix-wave-feedback.md:1-13`). 최신 binding-2 target도 `84ad6a…`다(`docs/reviews/2026-07-16-fix-wave-request.binding-2.json:1`). | overlay `review-ingests.jsonl:2`. | body target은 맞지만 strict outer envelope 검증에서 먼저 탈락한다. |
| `2026-07-18-carrier-lanes` | old outer envelope 뒤 fenced block에 `model`, `effort`, `review-target: e9e5c1…`가 있다(`docs/reviews/2026-07-18-carrier-lanes-feedback.md:1-15`). binding target도 `e9e5c1…`다(`docs/reviews/2026-07-18-carrier-lanes-request.binding.json:1`). | overlay `review-ingests.jsonl:3`. | body target은 맞지만 strict outer envelope 검증에서 먼저 탈락한다. |

따라서 “세 파일 모두 reviewer reply structured header가 없다”는 설명은 부정확하다. 공통점은 **pre-canonical ingest envelope**이고, body header까지 없는 것은 adopt 한 건이다. 현행 정상 예시는 `docs/reviews/2026-07-19-evidence-authority-fixes-feedback.md:2-17,73-82`로, outer `reply-metadata-json`/`verbatim-bytes`와 triage BEGIN/END가 모두 보인다.

main tree의 machine-local state는 세 ingest가 실제로 관찰됐음을 보조한다. 그러나 `.waystone/.gitignore:1`은 전체를 ignore하고, 현재 pending derivation은 overlay를 읽지 않는다. 감사 문서도 tracked `docs/reviews/*`를 Git authority로 두고(`docs/runtime-state-audit.md:99`), overlay의 ingest provenance는 local-only라고 구분한다(`docs/runtime-state-audit.md:108,150-155`). 따라서 overlay event는 history 증거지만 completion 또는 settlement authority로 사용할 수 없다.

## marker에 사용할 수 있는 현재-base intrinsic digests

`shasum -a 256`으로 관찰한 값이다. marker를 구현할 경우 문자열 round id나 timestamp만이 아니라 이 세 축을 모두 결속해야 한다.

| round | request SHA-256 | latest binding SHA-256 | feedback SHA-256 |
|---|---|---|---|
| adopt-dogfooding | `30ac20ce8649bb0a6202cc677666ce6993be70ceb1709ad7d91c63404ea7b2f9` | `bef65b554ebd4caf36c343a92de6d6d0d2968b78ad39f1965674345713e5a190` | `27e85cb41ec06b1c978302a3999e0e17a5e054b8fe592e51ecd34cfb09cb354a` |
| fix-wave | `991c5715a0888a582b949c542abcce6d8f1836103e9aca67e1c66fdec058811b` | `a78430686c404cc51e236b92dd2c12fa5e711a48bd90700525182c2adccf14fc` | `e860b28780ef8b133dc571b1f383f5eddc8535013b31de1e83c809ed5d899bf5` |
| carrier-lanes | `01e077b75aa167d47896af781bb0af058d4e5cd47a161f7cf25f39b7efbdeff1` | `ab4093b33e27c7ccaa870ff9b92a9be1cda6dd0d60ec94820ae373002df889c4` | `d48f5a67ebe2540c4b20263dd84da3b143e3f57b7230ba784c4196a1743d3724` |

# 3. 현재 HEAD의 범위 드리프트

다음 file-observation 명령은 현재 feedback 중 현행 `reply-metadata-json` 또는 `verbatim-bytes`가 없는 파일을 찾는다.

```bash
for f in docs/reviews/*-feedback.md; do
  if ! rg -q '^reply-metadata-json: ' "$f" || ! rg -q '^verbatim-bytes: ' "$f"; then
    printf '%s\n' "$f"
  fi
done
```

원래 3건 외에 다음 세 파일도 출력됐다.

- `docs/reviews/2026-07-18-carrier-lanes-fixes-feedback.md:1-13`
- `docs/reviews/2026-07-18-generation-binding-feedback.md:1-13`
- `docs/reviews/2026-07-19-evidence-authority-feedback.md:1-13`

이들도 현재 strict reader에 필요한 envelope가 없다. 따라서 이 보고서에서 “3개”는 **등록 당시 원래 cohort**를 뜻한다. `waystone` CLI를 금지대로 실행하지 않았으므로 live pending 개수를 주장하지는 않지만, 현재 파일과 코드만으로도 “현재 residual이 오직 3개”라는 전제는 유지할 수 없다. 구현 시 날짜 cutoff나 broad legacy rule로 한꺼번에 숨기지 말고, 후속 3건도 각각 동일한 증거 감사를 거친 뒤 별도 marker entry 포함 여부를 결정해야 한다.

# 4. 옵션 비교

| 옵션 | 구현 위치/스케치 | 비용 | 역사 보존·신뢰 리스크 | pending/향후 ingest 영향 |
|---|---|---|---|---|
| (a) archive marker | Git-tracked legacy-settlement namespace + `scripts/review.py` strict reader/분류 | 중간 | marker가 completion bypass로 변질될 위험. exact content digests, 별도 disposition, fail-closed parser로 통제 가능. 원 feedback 0 bytes 변경. | valid marker만 actionable pending에서 제외. 새 binding/re-ingest/file mutation은 digest mismatch로 marker를 무효화하고 정상 판정을 재개. |
| (b) re-ingest | 세 `feedback.md`를 현재 `ingest --force` envelope로 교체하고 main `.waystone/overlay` correction 수행 | 중간~높음 | old receipt에 body length/marker가 없어 원 reply와 appended triage 경계를 권위 있게 복원할 수 없다. wrapper, ingest date/source, triage와 local event를 개서. adopt는 honest target 자체가 binding과 불일치. | fix-wave/carrier-lanes 일부만 닫힐 수 있고 adopt는 남는다. force re-ingest는 향후 canonical reader에는 유리하지만 3건 일괄 settlement가 아니다. |
| (c) pending 제외 규칙 | `scripts/review.py:1008-1053`에 date/format/ID 조건 또는 config allowlist | 낮음(코드), 높음(계약) | provenance 없이 missing/corrupt receipt를 success 방향으로 숨긴다. exact ID는 다른 프로젝트까지 영향을 주고, date/format rule은 crafted legacy receipt를 면제한다. | 즉시 count는 줄지만 새 generation에도 stale 면제가 남기 쉽고, file-existence 비완료 characterization과 충돌한다. exact digests까지 넣으면 (a)를 Python에 숨긴 열화판이다. |

## (a) archive marker — 권고

### 구현 스케치

1. 기존 feedback는 수정하지 않는다. 예를 들어 `docs/reviews/legacy-settlements/` 아래에 독립 JSON marker를 두되, normal review artifact가 아니라 legacy settlement 전용 schema로 명시한다. 제안 필드:

   ```text
   schema: waystone-legacy-review-settlement-1
   disposition: archived-unverifiable
   reason: pre-canonical-feedback-envelope
   round_id: ...
   request_sha256: sha256:...
   binding_sha256: sha256:...
   feedback_sha256: sha256:...
   decision_source: <user ruling pointer>
   rationale: <why no longer actionable>
   ```

   adopt marker의 reason에는 request/binding target divergence도 포함해야 한다. timestamp, filename prefix 또는 machine-local overlay row만으로 marker 신원을 정하지 않는다.

2. `scripts/review.py`의 binding strict readers 인접에 marker schema/reader를 둔다. 중복, unknown field policy, invalid digest, conflicting disposition, missing referenced file는 해당 round를 pending으로 유지한다.
3. `pending_reviews()`는 정상 completion gate를 먼저 평가한다. 정상 완료가 아니면서 marker가 request/latest-binding/feedback bytes에 exact-match할 때만 `archived-unverifiable`로 분리한다. 절대로 `review_target_matches=True`나 `complete`를 합성하지 않는다.
4. existing status/pending 표면은 actionable pending count와 archived legacy count/reason을 구분해 표시한다. round-close reminder는 actionable pending만 센다. marker 파일 자체와 status 진단으로 사라진 이유가 보이게 하여 silent exclusion을 피한다.
5. 새 request binding 발행, feedback 교체, 또는 실제 canonical re-ingest는 digest mismatch로 marker를 stale시킨다. 그 뒤 normal receipt 판정이 complete/pending을 결정한다.
6. 테스트는 `PendingReviewTests` 인접에 추가한다: exact marker만 archive, corrupt/conflicting marker fail-closed, feedback mutation/new binding에서 pending 재개, genuine re-ingest가 stale marker를 대체, marker가 `review_target_matches`를 만들지 않음. 기존 `test_pre_echo_receipt_without_verbatim_envelope_is_not_promoted`와 file-existence 테스트는 그대로 유지한다.

### 비용과 주의

strict reader, 좁은 pending 분기, status 진단, 3개 data marker, 회귀 테스트가 필요하므로 비용은 중간이다. 기존 archive marker 규약은 발견되지 않았다. 가장 가까운 구현 선례는 독립 schema를 strict하게 읽고 immutable sequence로 기록하는 PR demotion sidecar(`scripts/review.py:1213-1269,1280-1328`)다.

ADR-0009는 기존 flat review evidence를 bulk migrate/rename하지 말고 legacy adapter로 읽으라고 하며(`docs/adr/ADR-0009-review-artifact-addressing.md:56-67`), 신규 flat review artifact writer와 역사 파일 일괄 migration을 기각한다(`docs/adr/ADR-0009-review-artifact-addressing.md:95-113`). 따라서 marker는 기존 flat feedback을 고치지 않는 전용 legacy namespace여야 하고, 이것이 normal run artifact가 아닌 settlement-decision artifact임을 main 세션에서 좁게 계약화해야 한다. Git-tracked review evidence authority는 유지해야 하므로 machine-local `.waystone` marker는 부적합하다.

## (b) re-ingest — 기각

현재 `ingest --force`는 source body를 새 envelope에 넣고 기존 feedback 전체를 교체하며, forced overlay correction이 실패하면 rollback한다(`scripts/review.py:2599-2608,2724-2766`). 이 방식의 문제는 다음과 같다.

- 세 old feedback에는 `verbatim-bytes`와 canonical triage markers가 없다. 실제 reply 끝과 이후 수기 triage 시작을 기계적으로 증명할 수 없다. 파일 안에는 여러 `---`가 있어 separator 추측도 권위가 아니다.
- fix-wave와 carrier-lanes는 body header target이 binding과 맞으므로 정확한 원 reply bytes가 별도 보존돼 있다면 canonical re-envelope가 가능하다. 현재 관찰한 tracked file만으로는 그 byte boundary가 고정되지 않았다.
- adopt body에는 structured header가 없고, request가 명명한 target과 binding target도 다르다. synthetic header를 앞에 붙이면 “reply byte-exact” 계약(`docs/CONVENTIONS.md:113-118`; `scripts/review.py:2601-2608`)을 위반하고, honest target을 쓰면 최신 binding과 불일치한다.
- wrapper/ingested date/source/triage를 교체하고 machine-local overlay event도 수정한다. feedback outer header의 reviewer correction(`docs/reviews/2026-07-16-adopt-dogfooding-feedback.md:3-4`)과 main `.waystone/overlay/review-ingests.jsonl:1`의 옛 reviewer 사이 차이도 별도 ruling 없이 덮을 수 없다.

따라서 새 reviewer가 현재 계약의 header를 포함해 다시 review하지 않는 한, (b)는 3건을 정직하게 일괄 settlement할 수 없다. 일부 파일을 고쳐 count만 줄이는 것은 이 task의 단일 처분안이 아니다.

## (c) pending 제외 규칙 — 기각

날짜 cutoff, missing-header, old-envelope, hard-coded round id 어느 방식도 권고하지 않는다.

- broad date/format rule은 실제 회신이 없거나 손상된 과거 파일도 숨길 수 있다. 코드도 genuine legacy window를 넓히거나 provenance를 추측하면 authentic artifact를 오염시킨다고 경고한다(`scripts/review.py:63-68`).
- file existence만으로 닫지 않는 테스트(`scripts/tests/run_tests.py:5503-5524`)와 corrupt old envelope를 승격하지 않는 테스트(`scripts/tests/run_tests.py:4964-4988`)를 의도적으로 변경해야 한다. 몰래 개정할 수 있는 characterization이 아니다.
- exact 3-ID allowlist는 plugin 전역 코드가 다른 프로젝트의 동일 round id까지 숨기는 프로젝트 특화 분기다. config allowlist도 새 binding 이후 stale 면제가 남는 mutable policy surface가 된다.
- request/binding/feedback digests까지 대조하면 안전성은 생기지만, 그것은 결국 (a)의 명시적 marker를 Python/config에 숨긴 형태다.

pending 집계는 즉시 조용해지지만 “왜 review receipt가 완료 증거가 되었는가”를 설명할 authority가 없다. I-09의 “provenance 불일치는 success로 degrade하지 않는다”와 fail-toward-verification 원칙(`docs/invariants.md:24,38-40`), E-02의 verbatim read-time authority(`docs/invariants.md:28-29`)에 가장 크게 충돌한다.

# 5. 최종 권고와 구현 전 ruling

**단일 권고: (a), exact-content-bound Git-tracked `archived-unverifiable` marker.**

- 원래 3개 feedback는 그대로 둔다.
- marker는 user settlement decision을 기록하되 review completion을 주장하지 않는다.
- pending에서 제외되는 이유를 status에서 별도 표시한다.
- 모든 marker는 request/latest binding/feedback digest에 결속한다.
- 손상, 충돌, 파일 변경, 새 generation은 fail-closed로 pending을 재개한다.

기각 근거는 명확하다. (b)는 원 reply boundary와 adopt target을 정직하게 복원할 수 없어 3건 일괄 처분이 불가능하고 역사 wrapper/triage/local provenance를 개서한다. (c)는 증거가 아니라 규칙으로 pending을 숨기며 future generation까지 면제할 수 있다.

구현 전 main 세션이 결정할 남은 한 가지는 marker entry의 범위다. pre-registered cohort는 위의 3건으로 확정된다. 그러나 현재 HEAD에는 같은 strict-envelope 실패 부류가 추가로 3건 있다. **원래 3건을 우선 marker로 정착시키되, 추가 3건은 각각 감사 후 별도 entry로 포함할지 명시적으로 ruling**해야 한다. 날짜/format wildcard로 자동 확대해서는 안 된다.
