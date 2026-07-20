# w5-writer — WS-GPT-303

## Outcome

- `write_round_request_binding` now rejects any glob-visible request-binding sibling whose filename has no canonical `round_request_binding_identity`. The typed `WorkflowError` includes the offending path, so prepare returns `rc=1` without a success message.
- `_request_generation_in_directory` and `_round_has_legacy_request_generation` now ignore noncanonical filename candidates before reading content.
- Canonical single-generation idempotency, canonical `-2` reissue, the existing generation-alias settlement demotion, and the tracked three-settlement archive cohort remain unchanged.

## RED evidence

1. `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py PacketPublicationTests.test_prepare_rejects_noncanonical_binding_instead_of_reporting_success`
   - test command `rc=1`; the assertion observed production `prepare_review_request` returned `0` after canonical was renamed to `...binding-02.json`.
2. `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py PendingReviewTests.test_binding_writer_rejects_renamed_noncanonical_generation PendingReviewTests.test_generation_lookups_ignore_noncanonical_binding_names`
   - `rc=1`; writer raised no `WorkflowError`, and exact-digest lookup returned the `...binding-02.json` alias as its source.

## Green verification

1. `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py PacketPublicationTests.test_prepare_rejects_noncanonical_binding_instead_of_reporting_success PendingReviewTests.test_binding_writer_rejects_renamed_noncanonical_generation PendingReviewTests.test_generation_lookups_ignore_noncanonical_binding_names`
   - `rc=0`; 3/3 passed.
2. `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py PacketPublicationTests.test_prepare_binds_request_to_closeout_head_and_is_idempotent PacketPublicationTests.test_narrative_only_reprepare_reissues_binding_and_reopens_pending PendingReviewTests.test_tracked_legacy_settlement_cohort_is_exactly_three_and_archived PendingReviewTests.test_binding_generation_alias_collision_demotes_settlement_to_pending_unknown`
   - `rc=0`; 4/4 passed.
3. `uv run python -m py_compile scripts/review.py scripts/tests/run_tests.py`
   - `rc=0`.
4. `git diff --check`
   - `rc=0` before commit.
5. `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"`
   - `suite rc=0`; 833 tests passed in 134.824s.

VERDICT: PASS — writer fails closed on noncanonical request-binding siblings and path-B lookups no longer trust them; all acceptance regressions and the 833-test full suite pass.
COMMITS: 58cdce84ce97dcc89f0db6a65fbddab7fe40e8b1
HOTFILES: dev_docs/0.12.0-refactor-plan.md untouched; scripts/review.py writer :365-430 and digest/legacy lookup :854-905; scripts/common.py untouched; scripts/tests/run_tests.py PacketPublicationTests prepare cluster and PendingReviewTests binding cluster adjacent to the existing :5768 regression.
VERIFIED: RED commands above reproduced prepare rc=0, writer silent reuse, and digest alias return; new tests 3/3 rc=0; required regressions 4/4 rc=0; py_compile rc=0; git diff --check rc=0; full suite command above suite rc=0 (833 tests).
NOT-RUN: waystone CLI (prohibited), push (prohibited), GPU checks (not applicable).
