# WS-GPT-206 — review binding generation collision

VERDICT: PASS — binding generation alias/noncanonical collision과 duplicate-key binding을 fail-closed로 전환했고, 정상 단일/재발행 및 tracked settlement 3건의 판정을 보존했다.
COMMITS: 397caba09b75b3412c03809dcfe43e42bfd595dd
HOTFILES: `scripts/review.py` binding filename regex·strict binding reader·latest binding resolver·packet pending reason 구획; `scripts/tests/run_tests.py` PacketPublicationTests/PendingReviewTests 인접 클러스터. `dev_docs/0.12.0-refactor-plan.md`·`scripts/common.py` 미접촉.
VERIFIED: RED alias fixture rc=1 및 현행 actionable=0/archived=1; 수정 후 focused 9 tests rc=0; full suite 821 tests rc=0; `git diff --check` rc=0; post-commit worktree clean.
NOT-RUN: `waystone` CLI 직접 호출, push, GPU 작업. 테스트 fixture/suite 내부 dispatcher 실행만 있었음.

## 잔존 작업 승계 판단

이전 기체가 남긴 `scripts/tests/run_tests.py` 78행을 diff와 계약 anchor에 대조했다. 세 테스트는 각각 duplicate JSON field, canonical `-2`와 `-02` alias settlement 충돌, glob이 흡수하는 `-1`/`-02`/`-draft` 후보를 정확히 고정하므로 전부 그대로 승계했다. 폐기한 잔존 변경은 없다.

“논리 generation당 정확히 1개”가 latest generation만이 아니라 모든 generation에 적용됨을 고정하기 위해, generation 1만 충돌하고 generation 2는 유일한 stale-collision 회귀 테스트를 인접 위치에 추가했다.

## 구현

- round-request binding sequence regex를 명시 ruling대로 `[1-9]\d*`로 제한했다.
- selector가 모든 glob-visible 후보의 canonical identity와 generation 유일성을 먼저 검사한다. 비정규 이름 또는 동세대 중복이면 `(None, None)`, 유일 최신 파일의 내용만 손상됐으면 기존대로 `(path, None)`을 반환한다.
- packet projection은 전자를 `binding-generation-collision` reason으로 pending/status에 표면화하며 target/reviewers를 unknown으로 유지한다. 따라서 exact settlement SHA가 한 후보와 일치해도 archive되지 않는다.
- binding JSON reader를 기존 duplicate-field 거부 helper로 교체하고 helper의 `ValueError`를 `WorkflowError("corrupt review binding ...")`로 변환한다.

## 재현 및 검증 명령

### RED — 기존 selector가 alias 충돌 뒤 settlement를 archive

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py PendingReviewTests.test_binding_generation_alias_collision_demotes_settlement_to_pending_unknown > /tmp/w4-binding-red.log 2>&1; rc=$?; echo "red rc=$rc"; sed -n '1,160p' /tmp/w4-binding-red.log; exit $rc
```

결과: `rc=1`. 기대 actionable row가 없어서 실패했다.

동일 fixture의 실제 disposition을 수리 전에 직접 출력:

```bash
uv run python - <<'PY'
import json
import sys
import tempfile
sys.path.insert(0, "scripts/tests")
import run_tests as tests

case = tests.PendingReviewTests(
    "test_binding_generation_alias_collision_demotes_settlement_to_pending_unknown")
with tempfile.TemporaryDirectory() as directory:
    root = case._root(directory)
    round_id = "2026-01-01-binding-alias"
    case._request(root, round_id, "a" * 40)
    canonical = tests.review.write_round_request_binding(
        root, round_id, "c" * 40, "b" * 40, ["r2"], mode="packet",
        **case._projection_digests())
    case._legacy_feedback(root, round_id)
    case._settlement(root, round_id)
    alias = canonical.with_name(f"{round_id}-request.binding-02.json")
    alias_row = json.loads(canonical.read_text())
    alias_row["target_sha"] = "d" * 40
    alias.write_text(json.dumps(alias_row, sort_keys=True) + "\n")
    dispositions = tests.review.packet_review_dispositions(root)
    print("actionable=", len(dispositions["actionable"]))
    print("archived_unverifiable=", len(dispositions["archived_unverifiable"]))
    print("archived_rounds=",
          [row["round_id"] for row in dispositions["archived_unverifiable"]])
PY
```

결과: `actionable=0`, `archived_unverifiable=1`, archived round은 `2026-01-01-binding-alias`.

### GREEN — 공격 계약과 정상 회귀

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py PacketPublicationTests.test_round_request_binding_rejects_duplicate_json_fields PendingReviewTests.test_binding_generation_alias_collision_demotes_settlement_to_pending_unknown PendingReviewTests.test_latest_binding_resolver_rejects_ambiguous_candidate_names PendingReviewTests.test_latest_binding_resolver_rejects_collision_in_stale_generation PacketPublicationTests.test_prepare_renders_template_from_round_exposure_and_narrative PendingReviewTests.test_latest_binding_controls_pending_and_old_packet_feedback_cannot_silence_it PendingReviewTests.test_latest_binding_resolver_parses_only_highest_filename_sequence PendingReviewTests.test_binding_sequence_outranks_raw_timestamp_strings_across_offsets PendingReviewTests.test_tracked_legacy_settlement_cohort_is_exactly_three_and_archived > /tmp/w4-binding-focused.log 2>&1; rc=$?; echo "focused rc=$rc"; tail -n 80 /tmp/w4-binding-focused.log; exit $rc
```

결과: `rc=0`, 9 tests. duplicate-key 거부, latest/stale generation collision, 정상 단일 binding, 유일 최신 `-2`, 실제 legacy settlement 3건 archived를 포함한다.

### 전체 gate

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"
```

결과: `suite rc=0`; `Ran 821 tests in 143.673s`; `OK`.

### 최종 무결성

```bash
git diff --check
git status --short
```

결과: diff check `rc=0`; 커밋 후 status 출력 없음.
