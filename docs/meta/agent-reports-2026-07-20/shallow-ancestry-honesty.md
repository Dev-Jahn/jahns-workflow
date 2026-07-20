VERDICT: PASS — shallow merge-base rc=1 is now reasoned unverifiable, and dead-process verify-fetch refs are swept fail-closed
COMMITS: f92e95814542714858cb75ecca89e4a389a65a0c
HOTFILES: scripts/common.py touched only the upstream verify-fetch/ancestry block; scripts/tests/run_tests.py touched only adjacent RemoteTests and shallow PacketPublicationTests functions; scripts/delegate.py untouched
VERIFIED: pre-fix 2-test regression rc=1 with both expected failures; post-fix focused 4 tests rc=0; RemoteTests+PacketPublicationTests 61 tests rc=0; exact full gate 830 tests in 136.933s, suite rc=0; git diff --check rc=0
NOT-RUN: waystone CLI (prohibited); push (prohibited); separate lint/typecheck gates (not part of the registered acceptance and no repo lint gate was identified)

## Implementation

- `ancestry_status()` now probes `git rev-parse --is-shallow-repository` only after `git merge-base --is-ancestor` returns rc=1.
  - exact `true` returns `(None, reason)` because truncated history cannot prove non-containment;
  - exact `false` preserves the existing definitive `(False, "")` result;
  - probe failure or unexpected output also returns `(None, reason)` rather than guessing that topology is complete.
- `fetch_upstream_head()` now sweeps producer-shaped `refs/waystone/verify-fetch-<pid>-<uuid>` residues before all early returns.
  - only refs whose embedded PID is observed absent are deleted;
  - live, permission-unknown, overflow/unknown, and non-producer-shaped refs are preserved;
  - enumeration or deletion failure returns remote-unverifiable before fetching.
- The existing cleanup assertion used `refs/waystone/verify-fetch-`, which does not prefix-match a flat final ref component and was therefore vacuous. It now uses the actual `refs/waystone/verify-fetch-*` glob.

## Verification evidence

The real Git fixture creates `A -> B -> C`, keeps a branch at A, clones main at depth 1, and fetches the A branch at depth 1. Both endpoint objects resolve, but both are shallow boundaries. The test first proves raw `merge-base --is-ancestor A C` returns rc=1, then checks:

- shallow clone: `ancestry_status(A, C) == (None, reason containing "shallow")`;
- full clone: `ancestry_status(A, C) == (True, "")`;
- full clone reverse direction: raw rc=1 and `ancestry_status(C, A) == (False, "")`.

The sweep fixture plants three real refs: a producer-shaped dead-PID ref, a producer-shaped current/live-PID ref, and a near-match user ref. The next live fetch removes only the dead-PID residue, preserves the other two, and returns the pinned upstream SHA. Exact `show-ref --verify` assertions make the test non-vacuous.

Commands run:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py RemoteTests.test_next_fetch_sweeps_only_stale_generated_refs PacketPublicationTests.test_shallow_rc_one_is_unverifiable_but_full_history_is_definitive
# before implementation: rc=1, two expected failures

env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py RemoteTests.test_next_fetch_sweeps_only_stale_generated_refs RemoteTests.test_live_fetch_evidence_ignores_fetch_head_overwrite_and_cleans_ref PacketPublicationTests.test_shallow_rc_one_is_unverifiable_but_full_history_is_definitive PacketPublicationTests.test_shallow_validator_reports_unknown_ancestry
# rc=0, 4 tests

env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py RemoteTests PacketPublicationTests
# rc=0, 61 tests in 20.236s

env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py; echo "suite rc=$?"
# Ran 830 tests in 136.933s; OK; suite rc=0
```

## Caller audit and risks

- Direct tri-state callers remain fail-closed: `head_pushed()` converts unknown ancestry to `False` with a reason, and packet publication verification rejects it with a cannot-determine message. No caller maps `None` to containment success.
- The legacy boolean `is_ancestor()` wrapper deliberately returns true only for proven `True`; unknown remains operationally fail-closed. Its `lanes` and `reclose` callers cannot carry the tri-state reason and may retain definite-negative wording. Those files were not widened in this minor/hot-file repair; this is a diagnostic boundary, not a false-PASS path.
- PID is used only as a same-host cleanup liveness locator, never as durable identity or publication evidence. Ambiguity preserves a ref, so PID reuse or a same-process retry may delay cleanup but cannot create a false success.

## Merge notes

- Commit is based on the worktree's starting HEAD `662f2e3b227f720b6ac6779bcc2d54edd7b94592`.
- `scripts/common.py` changes are confined to the pre-registered verify-fetch and merge-base anchor.
- `scripts/tests/run_tests.py` adds new functions beside the existing temporary-ref and shallow ancestry clusters; there is no file-end append or unrelated reformat.
- Working tree was clean after commit. No push was performed.
