# w2 manifest gaps closeout

VERDICT: PASS — 4개 계약 공백을 ADR-0006 Amendment로 폐쇄했고 full suite rc=0.
COMMITS: b1eca2d1d01c5a95a13ded721ea97e336b34146f
HOTFILES: dev_docs/0.12.0-refactor-plan.md 미접촉; scripts/review.py 미접촉; scripts/common.py 미접촉; scripts/tests/run_tests.py 미접촉. ADR-0006 `Amendment (2026-07-20)`만 append.
VERIFIED: `env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"` → `suite rc=0`; 기존 53줄 SHA-256 `129acb81dfd49e0d5117e347ef5af5101157dac4af51fcdda381aa42c1dae093` 일치; `git diff HEAD^ --check` rc=0.
NOT-RUN: `waystone` CLI; push; 코드/plan/ADR-0003/ADR-0005 변경.

## Acceptance 대조

| 공백 | 확정 규칙 | ADR-0006 anchor | 정합 anchor |
|---|---|---|---|
| 계획 §5-4 deviation | 각 필드 차이를 의도적/누락으로 판정하고 `task_id` 축소만 `task_ids`로 교정 | 63-78 | ADR-0003 read-only projection, ADR-0010 frozen run spec |
| multi-task mapping | run당 manifest 하나, frozen closure와 set-equal인 정렬 `task_ids`; M1 singleton, M2 전체 wave closure | 80-110 | ADR-0003:70-79, plan:649,674-681 |
| no-result terminal | SHA/null tagged pair, typed absence reason, non-null에만 remote reachability, unknown·unreachable 강등 금지 | 112-136 | ADR-0003:115-137, E-08 |
| canonical path | repo-relative `docs/runs/<run-id>/closeout.yaml` 하나, ADR-0005 identity 참조, payload byte equality, alias/fallback 금지 | 138-150 | ADR-0005:33-39, E-04 |

기존 본문은 수정하지 않았다. 시작 HEAD의 ADR-0006 전체 53줄과 변경 후 파일의 선두 53줄
SHA-256이 모두 아래 값으로 일치한다.

```text
129acb81dfd49e0d5117e347ef5af5101157dac4af51fcdda381aa42c1dae093
```

## 재현/검증 명령

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"
```

```text
suite rc=0
```

```bash
git show HEAD^:docs/adr/ADR-0006-run-closeout-manifest.md | shasum -a 256
head -n 53 docs/adr/ADR-0006-run-closeout-manifest.md | shasum -a 256
git diff HEAD^ --check
git diff --name-only HEAD^ HEAD
```

두 hash는 위 값으로 일치했고 `git diff HEAD^ --check`는 rc=0, 변경 파일 목록은
`docs/adr/ADR-0006-run-closeout-manifest.md` 하나였다.
