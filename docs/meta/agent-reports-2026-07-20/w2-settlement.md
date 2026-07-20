# w2 settlement — archived-unverifiable legacy review receipts

## 결과

원 cohort 3건에만 Git-tracked `waystone-legacy-review-settlement-1` marker를 추가했다. marker는 review completion을 만들지 않고, 정상 completion gate가 실패한 round에 대해서만 request / 최신 binding / feedback의 현재 raw bytes가 세 digest와 모두 일치할 때 `archived-unverifiable`로 분류된다.

- `pending_reviews()`는 계속 actionable 전용이다. 따라서 round-close reminder, SessionStart, statusline, overlay check는 archived receipt를 세지 않는다.
- `review pending`과 packet `review status`는 actionable과 archived-unverifiable의 수와 round/reason을 별도로 표시한다.
- marker JSON은 정확히 9개 field만 허용한다. unknown field, duplicate JSON key, invalid digest/disposition/filename, 동일 round 복수 marker는 fail-closed다.
- marker namespace의 비정규 JSON도 무시하지 않는다. declared round가 있으면 그 round를 ambiguous로 만들고, round조차 식별할 수 없는 손상 JSON은 settlement namespace 전체를 fail-closed로 무효화한다. 독립 diff review에서 발견한 `<round>.02.json` duplicate bypass를 이 규칙과 회귀 테스트로 닫았다.
- request/binding/feedback 중 하나라도 없거나 unreadable이면 exact match가 성립하지 않는다. marker filename round도 후보 집합에 넣어 request 자체가 사라져도 round가 actionable pending으로 남는다.
- 정상 completion gate는 marker 조회보다 먼저 실행된다. canonical-complete feedback에 exact-current marker가 있어도 archived나 pending을 합성하지 않는다.

구현 anchor:

- strict schema/reader/duplicate 격리: `scripts/review.py:63-65,80-82,543-648`
- 정상 completion 우선 + exact-byte settlement 분기: `scripts/review.py:1119-1245`
- actionable-only wrapper와 archived 조회: `scripts/review.py:1248-1260`
- packet pending/status 분리 표면: `scripts/review.py:2690-2731`
- 계약 테스트: `scripts/tests/run_tests.py:5626-5809,6071-6121`

## 원 cohort digest 대조와 marker

분석 보고서의 SHA-256 표를 신뢰해 복사하지 않고 현재 파일에서 다시 계산했다. 9개 값 모두 표와 exact-match했다.

| round | request SHA-256 | 최신 binding SHA-256 | feedback SHA-256 | 결과 |
|---|---|---|---|---|
| `2026-07-16-adopt-dogfooding` | `30ac20ce8649bb0a6202cc677666ce6993be70ceb1709ad7d91c63404ea7b2f9` | `bef65b554ebd4caf36c343a92de6d6d0d2968b78ad39f1965674345713e5a190` | `27e85cb41ec06b1c978302a3999e0e17a5e054b8fe592e51ecd34cfb09cb354a` | archived; reason에 request target `2035801…` vs latest binding target `c8ec816…` divergence 기록 |
| `2026-07-16-fix-wave` | `991c5715a0888a582b949c542abcce6d8f1836103e9aca67e1c66fdec058811b` | `a78430686c404cc51e236b92dd2c12fa5e711a48bd90700525182c2adccf14fc` | `e860b28780ef8b133dc571b1f383f5eddc8535013b31de1e83c809ed5d899bf5` | archived; latest는 `request.binding-2.json` |
| `2026-07-18-carrier-lanes` | `01e077b75aa167d47896af781bb0af058d4e5cd47a161f7cf25f39b7efbdeff1` | `ab4093b33e27c7ccaa870ff9b92a9be1cda6dd0d60ec94820ae373002df889c4` | `d48f5a67ebe2540c4b20263dd84da3b143e3f57b7230ba784c4196a1743d3724` | archived |

세 marker의 `decision_source`는 모두 정확히 `decision/pre-header-feedback-settlement-method ruling 2026-07-20`이다. 원 request/binding/feedback 파일은 수정하지 않았다.

재계산 명령:

```bash
shasum -a 256 \
  docs/reviews/2026-07-16-adopt-dogfooding-request.md \
  docs/reviews/2026-07-16-adopt-dogfooding-request.binding.json \
  docs/reviews/2026-07-16-adopt-dogfooding-feedback.md \
  docs/reviews/2026-07-16-fix-wave-request.md \
  docs/reviews/2026-07-16-fix-wave-request.binding-2.json \
  docs/reviews/2026-07-16-fix-wave-feedback.md \
  docs/reviews/2026-07-18-carrier-lanes-request.md \
  docs/reviews/2026-07-18-carrier-lanes-request.binding.json \
  docs/reviews/2026-07-18-carrier-lanes-feedback.md
```

marker 생성 후에는 `uv run python`으로 각 marker의 세 digest를 현재 request / filename sequence상 최신 binding / feedback bytes에서 다시 계산해 assert했다; rc=0.

## RED-first와 계약 테스트

marker 추가 전 실제 원 cohort를 직접 평가한 결과는 다음과 같았다; rc=0이며 세 round가 전부 actionable임을 assert했다.

```text
2026-07-16-adopt-dogfooding  feedback-receipt-corrupt
2026-07-16-fix-wave          feedback-receipt-corrupt
2026-07-18-carrier-lanes     feedback-receipt-corrupt
```

새 exact-marker 테스트를 코드 구현 전에 실행한 RED는 rc=1이었다. 실제 실패는 기대대로 `pending_reviews()`가 `2026-01-01-archived`를 `feedback-receipt-corrupt` actionable row로 반환한 것이었다. 구현 후 같은 테스트와 전체 `PendingReviewTests`가 green이다.

영구 테스트에는 다음을 고정했다.

- settlement loader를 비활성화하면 tracked 원 cohort 3건 모두 다시 `feedback-receipt-corrupt` actionable이다.
- exact marker만 archived로 분리되고 strict feedback metadata의 `review_target_matches`는 계속 `None`이다.
- corrupt JSON, unknown field, invalid digest, duplicate JSON key, canonical/noncanonical duplicate marker가 모두 fail-closed다.
- request/binding/feedback 부재, feedback byte 변경, 새 binding 발행은 actionable pending을 재개한다.
- canonical force re-ingest는 stale marker를 대체하여 pending도 archived도 남기지 않는다.
- canonical-complete receipt와 exact-current marker가 공존하면 정상 completion이 먼저 승리한다.
- `review pending`/packet `review status`는 두 disposition을 보이고, SessionStart/round-close는 actionable round만 보인다.
- 기존 `IngestTests.test_pre_echo_receipt_without_verbatim_envelope_is_not_promoted`와 file-existence 비완료 테스트는 수정하지 않았고 green이다.

초기 focused 검증에서 존재하지 않는 class selector `ReviewIngestTests...`를 한 번 사용해 rc=1이 났다. 구현 실패가 아니라 테스트 class 이름 오기였고, 실제 class `IngestTests...`로 즉시 재실행해 rc=0을 확인했다.

## 추가 동종 3건 감사 — marker 미생성

세 round 모두 feedback `:1-7`은 old outer envelope이며 `reply-metadata-json`, `verbatim-bytes`, canonical triage BEGIN/END가 없다. `_read_feedback_header_and_body_prefix()`의 첫 실패는 세 건 모두 정확히 `WorkflowError: feedback receipt has no unique verbatim body length`였다. body target은 각 feedback `:10-12`, request target은 request `:6`, raw binding target/schema는 binding `:1`에서 대조했다.

| round | request / latest binding / feedback SHA-256 | 정확한 envelope 실패 | body target ↔ raw latest binding | 현행 pending reason |
|---|---|---|---|---|
| `2026-07-18-carrier-lanes-fixes` | `16e50f2166e6e8603340d7820fe62bd1483da31103499669006b5e4a25468b5e` / `24ecbefff0d262286ad085f62a27af9955fb90331f7764c048a1d5a0c99750a8` / `2482aa15ef93777b8eb40d3733c14c0922b0581321c5151b8c93903b8573b1b7` | unique `verbatim-bytes` 0개 | `4c042031af9fe1722676de8bbe41fccba5464b30` = `4c042031af9fe1722676de8bbe41fccba5464b30` | `feedback-receipt-corrupt` |
| `2026-07-18-generation-binding` | `3a378457076b5ddd1e0c342f6e072154c39f06138d68b6f835eca4327b92df42` / `0bc63246f74efd3dc25bf9dc5d3af41634a525f74b6aee26b23dcd277567b44f` / `a4740da4607cfe01c9cd96b0d9cf32a15c5efc7805a74c7bfbd183ae8545e84b` | unique `verbatim-bytes` 0개 | `44a4b77db4e614b23721bfd601ab5aa4b96f6c65` = `44a4b77db4e614b23721bfd601ab5aa4b96f6c65` | `feedback-receipt-corrupt` |
| `2026-07-19-evidence-authority` | `9a31f04c8defe811979911e4c3cb17094b305ba87ef8e3d1299594667d85f4db` / `b0420470ce23d95ac2b2318e439903f04d23faba833b5f70fb9301f9f5f242fa` / `99042816bf7266015d049e3f1d51cd137f0f94a65154941ebb706cd661c056dd` | unique `verbatim-bytes` 0개 | raw JSON상 `2e0f1fbe9a9d0c2cdc52d4da919f617c148d9d06` = `2e0f1fbe9a9d0c2cdc52d4da919f617c148d9d06` | `binding-unavailable` |

세 round 모두 binding 후보는 unsuffixed `request.binding.json` 하나뿐이라 filename상 최신이다.

`evidence-authority`의 추가 결함: 최신 raw binding은 `waystone-round-request-binding-1`인데 round 날짜가 2026-07-19다(`docs/reviews/2026-07-19-evidence-authority-request.binding.json:1`). cutoff는 2026-07-18이고 그 이후 v1은 strict reader가 거부한다(`scripts/review.py:66-71,443-487`). 따라서 raw target 문자열은 같아도 유효한 binding과의 match로 승격할 수 없으며 현행 reason은 `binding-unavailable`이다.

사용자 brief가 전한 round-close 분포 `feedback-receipt-corrupt` 2건 + `feedback-review-target-mismatch` 1건은 현재 tracked bytes와 현행 판정에서 재현되지 않았다. 현재 재현은 `feedback-receipt-corrupt` 2건 + `binding-unavailable` 1건이고, 세 body target 모두 raw 최신 binding target과 같다. 그러므로 mismatch를 세 round 중 하나에 임의 귀속하지 않았다. 과거 출력은 다른 코드 상태/artifact 상태였을 수 있으나 현재 증거만으로 원인을 단정할 수 없다.

감사 재현 명령:

```bash
for round_id in \
  2026-07-18-carrier-lanes-fixes \
  2026-07-18-generation-binding \
  2026-07-19-evidence-authority
do
  shasum -a 256 \
    "docs/reviews/${round_id}-request.md" \
    "docs/reviews/${round_id}-request.binding.json" \
    "docs/reviews/${round_id}-feedback.md"
done
```

```bash
uv run python - <<'PY'
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "scripts")
import review

rounds = (
    "2026-07-18-carrier-lanes-fixes",
    "2026-07-18-generation-binding",
    "2026-07-19-evidence-authority",
)
root = Path.cwd()
reviews = root / "docs/reviews"
for round_id in rounds:
    try:
        review._read_feedback_header_and_body_prefix(
            reviews / f"{round_id}-feedback.md")
    except Exception as error:
        print(round_id, "envelope", type(error).__name__, str(error))
rows = {
    row["round_id"]: row["reason"]
    for row in review.pending_reviews(
        root, now=datetime(2026, 7, 20, tzinfo=timezone.utc))
}
print("pending", [(round_id, rows[round_id]) for round_id in rounds])
PY
```

추가 3건 marker는 생성하지 않았다.

## 최종 검증

- `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py PendingReviewTests IngestTests.test_pre_echo_receipt_without_verbatim_envelope_is_not_promoted` → rc=0, 24 tests.
- `uv tool run ruff@0.15.22 check scripts/review.py scripts/tests/run_tests.py --select F401,F841,E9` → rc=0.
- `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"` → `suite rc=0`; `/tmp/suite.log`에 `Ran 842 tests in 145.648s`, `OK`.
- `git diff --check` / staged `git diff --cached --check` → rc=0.
- commit 후 `git status --short` → 출력 없음.

VERDICT: PASS — 원 cohort 3건만 exact-content-bound archived-unverifiable로 분리했고 fail-closed·표면·actionable 경계를 검증했으며 full suite 842 tests rc=0이다.
COMMITS: 99d1193
HOTFILES: scripts/review.py strict settlement reader + packet_review_dispositions + packet pending/status 표면; scripts/tests/run_tests.py PendingReviewTests 인접 클러스터. dev_docs/0.12.0-refactor-plan.md·scripts/common.py 미접촉.
VERIFIED: marker 전 실제 cohort pending rc=0; exact-marker RED rc=1 → green; focused 24 tests rc=0; ruff F401,F841,E9 rc=0; 원 cohort 9 digest + 추가 감사 9 digest 재계산 rc=0; full suite exact command rc=0 (842 tests); git diff checks rc=0; post-commit clean.
NOT-RUN: waystone CLI 전부(금지 준수), push, 추가 3건 marker 생성, ingest/re-ingest production 경로 변경, GPU 작업.
