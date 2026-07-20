# m1b-prompt implementation report

## 1. Implementation summary

Committed as `464b531` (`fix(m1b): render minimal I-10 worker prompt`).

- `waystone/runs/prompt.py`
  - Added `render_worker_prompt(spec: RunSpec) -> str`.
  - Reads only the frozen title, declared scope, and acceptance criteria.
  - Emits exactly Goal, Bounds, Acceptance criteria, and the allowed
    `WAYSTONE_REPORT.yaml` report-contract stanza.
  - Does not read the registry, project state, filesystem, `VerificationPlan`, or any
    routing/bookkeeping field.
- `scripts/tests/test_run_prompt.py`
  - Added five I-10 contract tests with an independent literal full-prompt oracle.
  - Added adversarial extra-field sentinels for all named debt/internal surfaces.
- `scripts/tests/run_tests.py`
  - Additively registered `RunPromptTests`; no existing registration was changed.

No legacy `scripts/*` implementation, `spec.py`, `preflight.py`, jobs module, or template was
modified. No dependency was added.

## 2. Contract mapping

| Assigned contract / fixture row | Contract assertion test |
|---|---|
| promoted-contracts I-10; ADR-0014 Amendment 2 §5 — minimal prompt and only the reporting bookkeeping exception | `RunPromptTests.test_full_text_contains_only_the_four_allowed_blocks` |
| ADR-0014 Amendment 2 Addendum §2 positive form — goal, bounds, acceptance, WAYSTONE_REPORT stanza | `RunPromptTests.test_renders_the_four_allowed_components_from_frozen_input` |
| Brief full-text oracle — only the four allowed blocks and whitespace remain | `RunPromptTests.test_full_text_contains_only_the_four_allowed_blocks` |
| Addendum debt reversal — status, milestone, round, original anchor, routing_note, dependency status, and the named internal surfaces are absent even when populated | `RunPromptTests.test_omits_debt_fields_dependency_status_and_internal_surfaces` |
| Addendum 2 §2 routing_note value channel — projection removed, including a unique value sentinel | `RunPromptTests.test_routing_note_value_channel_is_not_projected` |
| Brief determinism fixture — same frozen RunSpec produces byte-identical UTF-8 prompt bytes | `RunPromptTests.test_rendering_is_byte_identical_for_the_same_run_spec` |

## 3. Verification

- Focused aggregate:
  - Command: `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py RunPromptTests`
  - Result: rc `0`, 5/5 tests passed.
- Required full aggregate:
  - Command: `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1b-prompt.log 2>&1; echo "suite rc=$?"`
  - Result: `suite rc=0`; 954 tests passed in 104.851 seconds.
  - Log: `/tmp/suite-m1b-prompt.log`
- `git diff --check`: rc `0` before commit.
- Independent read-only verifier: PASS, no blocker/major/minor findings; focused 5/5 and
  `py_compile` passed.

An auxiliary stdin-only report-stanza comparison initially failed with
`ModuleNotFoundError: yaml`: `uv run -` did not inherit the PEP 723 dependency metadata from the
test script. Re-running that auxiliary comparison with the repository's existing `pyyaml`
dependency succeeded. This was an invocation-environment error, not a product or contract-test
failure, and no dependency was added.

## 4. Contract interpretation / needs-ruling candidates

1. Canonical `RunSpec` currently has none of `status`, `milestone`, `round`, `anchor`,
   `routing_note`, or dependency status. `FrozenJobInput` contains only dependency IDs in addition
   to the three allowed prompt fields. Because `spec.py` is out of scope, the negative tests attach
   adversarial extra attributes to a valid frozen `RunSpec` and prove the renderer does not mine
   them. If those fields are ever added canonically, the strict allowlist behavior remains the
   intended result.
2. `anchor` cannot be reorganized into Goal/Bounds because it is not frozen in the current
   `RunSpec`. Re-reading the registry to recover it would violate the frozen-input-only contract,
   so this implementation uses the frozen title and scope only.
3. Current `VerificationPlan` has no worker acceptance text; it contains checks/tooling surfaces.
   The optional parameter was therefore omitted instead of exposing a new surface with no current
   contract use.
4. Empty scope is valid in `FrozenJobInput`, but the brief does not pin an invented placeholder,
   typed refusal, or other rendering. The conservative implementation emits an empty Bounds block
   rather than inventing scope or silently substituting a default.
5. Frozen owner-authored title/scope/acceptance strings may themselves contain newlines or words
   such as `tasks.yaml`. ADR-0014 Addendum 2 distinguishes code-derived projection from supplied
   content, while explicitly assigning the routing_note value channel for removal. The renderer
   therefore preserves the three allowed owner fields verbatim and tests forbidden surfaces via
   hidden-channel sentinels rather than censoring acceptance text.

## 5. Out-of-scope observations

- No out-of-scope code defect was found.
- After the required aggregate suite, ignored worktree-local files
  `.waystone/.gitignore`, `.waystone/lock`, and `.waystone/profile.yml` are present. The aggregate's
  known legacy diagnostic path updated `.waystone/lock`; it was neither restored nor deleted.
  `profile.yml` predates this run and was not intentionally modified.
