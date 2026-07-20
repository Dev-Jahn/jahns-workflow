VERDICT: PASS — hook-matrix uv cache path parsing is now independent of caller color forcing; both pre-registered suites returned rc=0. A transient deleted temp-file process deviation is disclosed below.
COMMITS: 3a4ca781ec765c3fc9f2664aa183ce2c541faf74
HOTFILES: scripts/tests/run_tests.py touched only in DelegateVerifyTests.test_manifest_hook_matrix_covers_normal_and_verifier_modes, at the uv cache env/call block; scripts/common.py not touched; scripts/delegate.py not touched.
VERIFIED: `env FORCE_COLOR=3 uv run scripts/tests/run_tests.py` rc=0; `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py` rc=0; hostile focused FORCE_COLOR and CLICOLOR_FORCE runs with ambient NO_COLOR removed both rc=0; `git diff --check` rc=0; final worktree clean.
NOT-RUN: `waystone` CLI was not run (prohibited); push and merge were not performed. No acceptance gate was skipped.

## Implementation

The hook matrix resolves the shared uv cache with `uv cache dir`, strips stdout, and converts it to `Path`. The subprocess previously inherited the caller environment, so forced ANSI sequences became part of the parsed path.

The test now creates a subprocess-specific copy of `os.environ`, removes `FORCE_COLOR` and `CLICOLOR_FORCE`, sets `NO_COLOR=1`, and passes that environment to `uv cache dir`. This fixes the environment boundary instead of making the path parser tolerate ANSI.

Only `scripts/tests/run_tests.py` changed: 5 insertions and 1 deletion. No production code, hook, registry, roadmap, progress, ADR, or review file changed.

## Exhaustive same-pattern audit

Initial routing used:

```bash
rg -n "hook|matrix|uv cache|cache dir" scripts/tests/run_tests.py
```

The complete subprocess/output scan found no second site requiring the same repair.

- The hook matrix's actual hook subprocess already uses a from-scratch allowlist environment, so it cannot inherit `FORCE_COLOR` or `CLICOLOR_FORCE`; its JSON and exact-output assertions need no change.
- The shared `git()` helper has many stdout consumers, but git output was byte-clean under the audited color variables and is not the demonstrated color-sensitive CLI here.
- Release and Python CLI subprocesses assert return codes or diagnostic substrings rather than parsing color-sensitive structured output.
- Node lint only checks the return code.
- Boundary-hook exact-output checks use test-owned shell `printf` output.
- Remaining `delegate.subprocess.run` occurrences are monkeypatched synthetic results rather than caller-environment subprocess parsing.

## Verification evidence

Pre-registered acceptance commands, with shell rc captured directly:

```bash
env FORCE_COLOR=3 uv run scripts/tests/run_tests.py; rc=$?; echo "forced suite rc=$rc"; exit $rc
# forced suite rc=0

env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py; rc=$?; echo "neutral suite rc=$rc"; exit $rc
# neutral suite rc=0
```

The session had ambient `NO_COLOR=1`, so additional hostile focused checks explicitly removed it:

```bash
env -u NO_COLOR FORCE_COLOR=3 uv run scripts/tests/run_tests.py DelegateVerifyTests.test_manifest_hook_matrix_covers_normal_and_verifier_modes
# rc=0

env -u NO_COLOR CLICOLOR_FORCE=1 uv run scripts/tests/run_tests.py DelegateVerifyTests.test_manifest_hook_matrix_covers_normal_and_verifier_modes
# rc=0
```

A raw probe confirmed the underlying hostile behavior:

```bash
env -u NO_COLOR FORCE_COLOR=3 uv cache dir | sed -n l
# \033[36m/Users/jahn/.cache/uv\033[39m$
```

## Risk and process deviation

The patch is confined to one single-use test env block, so merge risk is limited to the hot-file vicinity around the existing hook matrix test.

During a delegated read-only audit, the auditor accidentally created `/private/tmp/w0720-node-out` and `/private/tmp/w0720-node-err` as 0-byte transient files, then immediately deleted them. This momentarily violated the external-write restriction. A final read-only check confirmed both paths are absent. The worktree and committed patch were unaffected, and the auditor made no edits or commits.

## Merge note

Cherry-pick `3a4ca781ec765c3fc9f2664aa183ce2c541faf74`. Resolve any hot-file conflict specifically at `DelegateVerifyTests.test_manifest_hook_matrix_covers_normal_and_verifier_modes`; no other file should enter the merge.
