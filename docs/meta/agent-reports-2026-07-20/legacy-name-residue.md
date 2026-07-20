VERDICT: PASS — 지정 live 표면의 legacy-name 패턴 0건, 보존 이력 245건만 잔존, 전체 suite rc=0
COMMITS: c191fb6 f6e9025 2c731b5 3f793e0 d1eff3b
HOTFILES: run_tests.py yes (관련 snapshot/delegate/ingest/improve/migration/hook/skill 클러스터만); common.py yes (CONFIG_NAME, old-home Phase 1, Phase 2 source, load_config 구획만); delegate.py yes (snapshot reserved-name 및 _read_report 구획만)
VERIFIED: required rg full scan rc=0 because preserved matches exist (28 files, 221 lines, 245 occurrences); live-surface rg rc=1 (0 matches); focused tests 52+84+36+3+1 all rc=0; `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py; echo "suite rc=$?"` => suite rc=0 (823 test methods)
NOT-RUN: `waystone` CLI (명시 금지); standalone ruff (acceptance 아님); push/merge (명시 금지); GPU 검증 (CPU-only task)

## 구현

- delegate worker report 계약을 `WAYSTONE_REPORT.yaml`로 일괄 전환했다. snapshot 사전조건, report 소비/삭제, worker prompt, synthetic runner fixtures와 assertions가 같은 커밋에 함께 이동했다.
- 신규 review finding ID 계약을 `WS-GPT-NNN`으로 전환했다. `review.FINDING_RE`, improve triage parser, review skill과 synthetic runtime fixtures를 함께 바꿨고, `IngestTests.test_ws_finding_blocks_build_triage_skeleton`로 실제 ingest 생성물을 직접 고정했다.
- old-name-only project/home migration 호환을 폐기했다. `.waystone.yml`만 project config로 인식하며, 구 home-path 선행 이관과 별도 Phase 2 worktree source를 제거했다. 반면 `.claude/waystone`, `.codex/waystone`, `waystone.pre-0.9`의 generic migration은 그대로 보존했다.
- resume/session shell hooks와 tasks-read nudge는 `.waystone.yml`만 인식한다. init skill도 현재 config/current managed markers만 안내한다.
- 새 계약과 모순되던 positive compatibility test 6개를 삭제했다. statusline, host-neutral storage, init marker 검증은 남은 독립 계약을 유지하도록 축소/개정했다. 신규 WS parser test 1개를 추가해 총 test method 수는 828에서 823으로 바뀌었다.

## 검증 증거

### 표적 검증

| 명령 | 결과 |
|---|---|
| `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py DelegateSnapshotTests DelegateRunTests` | 52 tests, rc=0 |
| `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py IngestTests ImproveReviewsTests ImproveM1DefectTests OverlayRuleTests EvidenceTests ImproveL2BTests ImproveL2BAdversarialTests` | 84 tests, rc=0 |
| `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py StatuslineTests MigrationV2Phase1Tests MigrationV2Phase2Tests MigrationTests CodexPluginContractTests.test_machine_data_root_is_host_neutral` | 36 tests, rc=0 |
| `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py TaskReadNudgeTests DelegateVerifyTests.test_verify_session_hook_does_not_seed_state_in_review_worktree` | 3 tests, rc=0 |
| `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py MigrationTests.test_init_skill_uses_current_managed_markers` | 1 test, rc=0 |

### 전체 게이트

명령 원문:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py; echo "suite rc=$?"
```

결과: `suite rc=0`. 별도 정적 계수 `rg -n '^    def test_' scripts/tests/run_tests.py | wc -l`은 823이다.

### acceptance rg 전수표

명령 원문:

```bash
rg -n "JW_REPORT|jahns.workflow|jw_|JW-" --hidden -g '!.git'
```

결과는 rc=0이다. 이는 보존 대상이 의도적으로 남아 있기 때문이다. 현재 결과는 28 files / 221 matching lines / 245 matching occurrences이고, live directories에 같은 검색을 제한하면 rc=1(0건)이다:

```bash
rg -n "JW_REPORT|jahns.workflow|jw_|JW-" scripts hooks skills templates
```

남은 파일 전부의 분류:

| 파일 | occurrence | 보존 근거 |
|---|---:|---|
| `PROGRESS.md` | 18 | 금지된 역사 진행 기록 |
| `ROADMAP.md` | 39 | 금지된 역사 roadmap/provenance |
| `tasks.yaml` | 45 | 금지된 registry finding/task provenance |
| `dev_docs/0.12.0-refactor-plan.md` | 6 | 역사 refactor/finding 노트 |
| `dev_docs/0.8.0-m1-implementation-notes.md` | 14 | 역사 구현 노트 |
| `dev_docs/0.8.0-m2-implementation-notes.md` | 2 | 역사 구현 노트 |
| `dev_docs/0.9-pre-adr-storage-lock-autonomy.md` | 1 | 역사 구현 노트 |
| `dev_docs/delegate_readme.md` | 2 | 사용자 판단 대기 명시 비범위 |
| `docs/adr/ADR-0009-review-artifact-addressing.md` | 4 | ADR provenance; docs/adr 수정 금지 |
| `docs/adr/ADR-0010-run-spec-readiness.md` | 1 | ADR provenance; docs/adr 수정 금지 |
| `docs/adr/ADR-0011-project-context.md` | 1 | ADR provenance; docs/adr 수정 금지 |
| `docs/adr/ADR-0012-verification-capability-preflight.md` | 1 | ADR provenance; docs/adr 수정 금지 |
| `docs/known-issues.md` | 3 | 기존 finding/residual provenance |
| `docs/porting-ledger.md` | 10 | 명시 보존 대상 provenance ledger |
| `docs/runtime-state-audit.md` | 1 | 기존 finding audit provenance |
| `docs/reviews/2026-07-16-adopt-dogfooding-feedback.md` | 1 | verbatim review archive |
| `docs/reviews/2026-07-16-fix-wave-feedback.md` | 1 | verbatim review archive |
| `docs/reviews/2026-07-18-carrier-lanes-feedback.md` | 10 | verbatim review archive |
| `docs/reviews/2026-07-18-carrier-lanes-fixes-feedback.md` | 12 | verbatim review archive |
| `docs/reviews/2026-07-18-carrier-lanes-fixes-request.md` | 3 | historical review request/archive |
| `docs/reviews/2026-07-18-generation-binding-feedback.md` | 13 | verbatim review archive |
| `docs/reviews/2026-07-18-generation-binding-request.md` | 4 | historical review request/archive |
| `docs/reviews/2026-07-19-evidence-authority-feedback.md` | 14 | verbatim review archive |
| `docs/reviews/2026-07-19-evidence-authority-fixes-feedback.md` | 9 | verbatim review archive |
| `docs/reviews/2026-07-19-evidence-authority-fixes-request.md` | 5 | historical review request/archive |
| `docs/reviews/2026-07-19-evidence-authority-request.md` | 5 | historical review request/archive |
| `docs/reviews/2026-07-19-m0-contracts-feedback.md` | 16 | verbatim review archive |
| `docs/reviews/2026-07-19-m0-contracts-request.md` | 4 | historical review request/archive |
| **합계** | **245** | **모두 명시 보존/비범위** |

## 멱등 재적용 규칙

dev 최신 위에서 충돌 재적용 시 아래 세 명령은 대상 파일을 제한한 멱등 치환이다. 이미 적용된 파일에는 변화가 없다.

```bash
perl -pi -e 's/JW_REPORT/WAYSTONE_REPORT/g' \
  scripts/delegate.py scripts/tests/run_tests.py templates/delegate-prompt.md

perl -pi -e 's/jw_report/waystone_report/g' scripts/tests/run_tests.py

perl -pi -e 's/JW-GPT/WS-GPT/g' \
  scripts/review.py scripts/improve.py scripts/tests/run_tests.py skills/review/SKILL.md
```

맹목 치환하면 안 되는 수동 예외:

1. `scripts/common.py`
   - `LEGACY_CONFIG_NAME` 삭제.
   - `_legacy_data_dir()` 삭제.
   - `migrate_home_data()`에서 old-name home을 `.claude/waystone`으로 옮기던 선행 블록만 삭제.
   - `_phase2_worktree_sources()` 삭제; `migrate_project_state()`는 `sources`만 검사하고 `_worktree_sources(sources, slug)`를 호출.
   - `has_project_config()`는 `(root / CONFIG_NAME).is_file()`만 반환.
   - `_migrate_project_config()` 삭제; `load_config()`는 `root / CONFIG_NAME`을 직접 읽되 `source=path`는 유지.
   - `_legacy_claude_root`, `_legacy_codex_root`, `_legacy_roots`, `_phase2_sources`, `.pre-0.9` migration은 건드리지 않는다.
2. hooks
   - `resume_snapshot.sh`, `session_context.sh`의 find-root 조건에서 old config 대안만 제거.
   - `tasks_read_nudge.py`의 legacy constant/tuple probe를 삭제하고 `CONFIG_NAME` 단일 probe로 단순화.
3. `skills/init/SKILL.md`
   - repair mode는 `.waystone.yml`만 기술.
   - host instruction stanza는 current `waystone:begin/end` markers만 인식/교체하도록 기술.
4. `scripts/tests/run_tests.py`
   - 삭제: `TaskReadNudgeTests.test_legacy_config_still_activates_nudge`, `MigrationV2Phase1Tests.test_jahns_workflow_chain_keeps_linked_worktree_valid_until_phase2`, `MigrationTests`의 old-home 2개와 old-config 2개.
   - 개정: statusline outside-project test, host-neutral machine-root test, init current-marker test.
   - 추가: `IngestTests.test_ws_finding_blocks_build_triage_skeleton`을 기존 ingest cluster 인접 위치에 둔다.

이력 파일에는 위 perl을 절대 확대 적용하지 않는다.

## 리스크와 비범위

- pre-registered 검색식은 lowercase hyphen legacy schema/marker adapter를 포함하지 않는다. 별도 확인 결과 `jw-profile-1`, `jw-delta-1`, `jw-review-cycle` 호환이 `scripts/delegate.py`, `scripts/overlay.py`, `templates/profile-schema.json`, 해당 characterization tests에 남아 있다. 이들은 brief가 지정한 live 목록/검색식 밖이며 제거에는 별도 runtime schema/marker 로직 판단이 필요하므로 이번 이름 치환에서 건드리지 않았다.
- 기존 review archive의 `JW-GPT-*` 본문은 보존했지만 신규 parser는 `WS-GPT-*`만 생성/파싱한다. 이는 “신규 라운드부터”와 migration 호환 불요 지시의 의도된 경계다.
- old-name config/home을 더는 자동 탐지·이관하지 않는 동작 변화는 의도적이다. current-name pre-0.9 migration의 안전성 검증은 그대로 유지되고 표적 36 tests가 통과했다.

## 머지 주의

- 이 branch는 요청대로 최후 머지 대상이다. 특히 `scripts/tests/run_tests.py`는 여러 논리 커밋에서 관련 기존 cluster만 수정했으므로 파일 말미 통째 재적용보다 위 규칙/테스트 함수 단위로 resolve한다.
- `scripts/common.py`는 문자열을 `waystone`으로 바꾸면 current 경로/상수가 중복되어 잘못된 제어 흐름이 된다. 반드시 위 함수/분기 삭제 규칙으로 resolve한다.
- 커밋 순서: `c191fb6` report contract → `f6e9025` finding prefix → `2c731b5` config/home retirement → `3f793e0` hooks → `d1eff3b` init skill.
- branch는 clean이고 push하지 않았다.
