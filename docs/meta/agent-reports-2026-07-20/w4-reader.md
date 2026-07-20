# w4-reader — WS-GPT-104 dual-prefix archive reader

## Outcome

The historical improve reader now accepts both `JW-GPT-NNN` and `WS-GPT-NNN` finding IDs. The new-review ingest contract remains WS-only, and overlay recovers automatically because it consumes `improve._parse_triage()`.

The previous crashed worker's uncommitted changes were audited line by line before adoption. The production change and test direction were correct and were retained. One test comment was corrected to identify the JW fixture as historical rather than describing it as the current writer format.

## Changes

- `scripts/improve.py`
  - Restored only `_FINDING_ID_RE` to `(?:JW|WS)-GPT-\d+`.
- `scripts/tests/run_tests.py`
  - Added a real-corpus regression over the six preserved canonical feedback archives.
  - Asserted the archive remains non-empty and exactly 21 JW findings are projected.
  - Added a canonical synthetic WS row and asserted the combined reader accepts both `JW` and `WS`.
  - Restored the historical `_TRIAGE_FEEDBACK` fixture to JW.
  - Restored the historical overlay rule-2 fixture to JW.
  - Expanded the L2C feedback fixture to mixed rounds: r1 JW, r2 WS.
  - Kept current writer/ingest fixtures WS-only.

No production file other than `scripts/improve.py` changed. `scripts/review.py`, `scripts/overlay.py`, `scripts/common.py`, and `dev_docs/0.12.0-refactor-plan.md` were read only.

## RED → GREEN evidence

Command:

```bash
env PYTHONDONTWRITEBYTECODE=1 uv run --with pyyaml python - <<'PY'
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
base_source = subprocess.run(
    ["git", "show", "HEAD:scripts/improve.py"],
    text=True,
    capture_output=True,
    check=True,
).stdout
base_ns = {
    "__file__": str(Path("scripts/improve.py").resolve()),
    "__name__": "base_improve",
}
exec(compile(base_source, "HEAD:scripts/improve.py", "exec"), base_ns)

import improve

names = (
    "2026-07-18-carrier-lanes-feedback.md",
    "2026-07-18-carrier-lanes-fixes-feedback.md",
    "2026-07-18-generation-binding-feedback.md",
    "2026-07-19-evidence-authority-feedback.md",
    "2026-07-19-evidence-authority-fixes-feedback.md",
    "2026-07-19-m0-contracts-feedback.md",
)
base_rows = []
fixed_rows = []
for name in names:
    text = (Path("docs/reviews") / name).read_text(encoding="utf-8", errors="replace")
    before = base_ns["_parse_triage"](text)
    after = improve._parse_triage(text)
    base_rows.extend(before)
    fixed_rows.extend(after)
    print(f"{name}: before={len(before)} after={len(after)}")
print("before_total", len(base_rows))
print("after_total", len(fixed_rows))
print("before_prefixes", sorted({row["id"].split("-GPT-", 1)[0] for row in base_rows}))
print("after_prefixes", sorted({row["id"].split("-GPT-", 1)[0] for row in fixed_rows}))
PY
```

Observed, rc=0:

```text
2026-07-18-carrier-lanes-feedback.md: before=0 after=4
2026-07-18-carrier-lanes-fixes-feedback.md: before=0 after=3
2026-07-18-generation-binding-feedback.md: before=0 after=4
2026-07-19-evidence-authority-feedback.md: before=0 after=3
2026-07-19-evidence-authority-fixes-feedback.md: before=0 after=2
2026-07-19-m0-contracts-feedback.md: before=0 after=5
before_total 0
after_total 21
before_prefixes []
after_prefixes ['JW']
```

## Contract checks

Focused tests:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE PYTHONDONTWRITEBYTECODE=1 uv run scripts/tests/run_tests.py ImproveReviewsTests.test_triage_reads_preserved_archive_and_both_prefixes ImproveReviewsTests.test_triage_ignores_verbatim_body IngestTests.test_ws_finding_blocks_build_triage_skeleton OverlayRuleTests.test_rule2_open_severe_fires_excludes_done_rejected_minor L2CImproveFeedbackTests.test_feedback_fact_is_observed_bounded_and_byte_stable
```

Observed: rc=0, 5 tests, OK.

WS-only new-ingest regex:

```bash
env PYTHONDONTWRITEBYTECODE=1 uv run python - <<'PY'
import sys
sys.path.insert(0, "scripts")
import review
assert review.FINDING_RE.search("## WS-GPT-123 — current")
assert review.FINDING_RE.search("## JW-GPT-123 — historical") is None
print("review.FINDING_RE: WS-only")
PY
```

Observed: rc=0, `review.FINDING_RE: WS-only`.

Diff check:

```bash
git diff --check
```

Observed before commit: rc=0.

Full suite:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"
```

Observed: `suite rc=0`; `Ran 818 tests in 140.615s`; `OK`.

## Final summary

VERDICT: PASS — historical JW findings recover from 0 to 21 while current WS ingest remains WS-only.
COMMITS: 2e0d51e63a9202fc2b9babdd820ed425bc1ee603
HOTFILES: `scripts/tests/run_tests.py` — ImproveReviewsTests archive/body cases, OverlayRuleTests historical fixture, L2CImproveFeedbackTests mixed-prefix fixture; plan/review.py/common.py untouched.
VERIFIED: RED/GREEN corpus command rc=0 (0→21); focused 5 tests rc=0; review WS-only assertion rc=0; git diff --check rc=0; full suite command rc=0 (818 tests).
NOT-RUN: `waystone` CLI (prohibited); push (prohibited); rebase/merge (not required for isolated fleet worktree).
