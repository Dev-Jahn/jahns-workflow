# w4-docs — WS-GPT-203·204·205 ruling execution

Base는 이 worktree 시작 HEAD 81bd177이다. RESUME NOTE의 잔존물을 먼저 감사했다.
29ea648은 byte 복원 대조가 성립해 승계했다. 미커밋 PC-31도 finding·triage·ADR-0014와 맞아
승계했다. 반면 이전 기체가 말했다는 reverse-closure 표는 실제 파일에 없었으므로 승계할
내용이 없었고 ledger에서 다시 생성했다.

## Task 1 — docs/plan-m1c-exit-supersession (WS-GPT-203)

VERDICT: PASS — legacy comparator 원문은 byte 그대로 보존하고, 그 직전에 ADR-0014 semantic gate supersession을 추가했다.

COMMITS: 29ea6480a374ce56649f91e5893c22e0dd97f8c3

HOTFILES: dev_docs/0.12.0-refactor-plan.md의 M1-C 구획만 접촉. 현행 line 692-693에 note를 추가했고 line 695-697의 기존 delegate characterization / old-new 출력 등급별 호환 / 구 관측 계약과 동일 원문을 보존했다. 이 커밋의 다른 파일 변경은 0.

VERIFIED:

- docs/reviews/2026-07-20-ruling-execution-feedback.md WS-GPT-203·triage와 docs/adr/ADR-0014-m1a-acceptance-basis.md Acceptance authority·Amendment 2를 대조했다.
- 아래 byte 복원 검사는 rc=0, insert_occurrences=1, restored_equal=True, changed_files는 plan 단일 파일이었다.

~~~bash
uv run python - <<'PY'
import subprocess

path = "dev_docs/0.12.0-refactor-plan.md"
parent = subprocess.check_output(["git", "show", f"29ea648^:{path}"], text=True)
current = subprocess.check_output(["git", "show", f"29ea648:{path}"], text=True)
insert = (
    "> **Superseded by ADR-0014 (2026-07-20):** 아래 M1-C legacy comparator exit는 역사 기록으로만 보존하며 현행 gate가 아니다.\n"
    "> 현행 M1-C exit는 ADR-0014의 acceptance authority에 따라 ① M1-C에 귀속된 승격 계약의 새 시스템 계약 테스트 전부 green ② known-debt 기준선 대비 신규 I-01~I-12·E-01~E-09 위반 0 ③ M1-C에 적용 가능한 accepted ADR 계약과 모순 0이다.\n\n"
)
changed = subprocess.check_output(
    ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "29ea648"],
    text=True,
).splitlines()
print(f"insert_occurrences={current.count(insert)} restored_equal={current.replace(insert, '', 1) == parent}")
print(f"changed_files={changed}")
raise SystemExit(not (current.count(insert) == 1 and current.replace(insert, '', 1) == parent and changed == [path]))
PY
~~~

NOT-RUN: task 단독 full suite는 실행하지 않았다. 세 커밋 완료 뒤 공통 full suite를 Task 3 검증에서 1회 실행했다.

## Task 2 — docs/promoted-reverse-closure-and-pc31 (WS-GPT-204)

VERDICT: PASS — PC-31을 근거 ② / UninitializedRootGateTests / 새 kernel root-gate 계약으로 등록했고, 85 class를 승격 39 + 명시적 비승격 46으로 정확히 한 번씩 닫았다.

COMMITS: 7fc2db05cbc81b5a70a3c95f3b88c34e396708c9

HOTFILES: docs/promoted-contracts.md만 접촉. PC-31은 record-continuity 표 line 42, reverse closure는 line 146-240이다. plan/review.py/common.py/run_tests.py는 접촉하지 않았다.

VERIFIED:

- ledger headers 85개, method 합계 828, PC ID 31개, PC-ref class 39개를 기계 추출했다.
- reverse 표는 ledger 순서와 동일한 85행이며 promoted=39, non_promoted=46, missing=0, extra=0, duplicates=0, pc_mismatches=0, rc=0이다.
- 추가 승격 누락은 없었다. DelegateEffortTests와 DelegateFanoutPlanTests는 기존 prose의 DelegateSnapshotTests부터 DelegateVerifyTests까지 범위에 이미 포함된 비승격 항목이며, 새 표가 둘을 legacy delegation mechanics로 개별 명명했다.
- 처음 만든 validator가 PC 행의 문서상 category 배치와 무관하게 PC-01..31 숫자 순서를 요구해 rc=1을 냈다. 문서 결함이 아니라 validator 전제 오류였고, PC-31은 지시대로 record-continuity 표에 있어 PC-14와 PC-15 사이에 놓인다. 순서가 아닌 exact unique set을 검사하도록 고친 아래 명령은 rc=0이다.

~~~bash
uv run python - <<'PY'
import re
from collections import defaultdict
from pathlib import Path

ledger_text = Path("docs/porting-ledger.md").read_text()
doc = Path("docs/promoted-contracts.md").read_text()
ledger_rows = re.findall(r"^### (\w+Tests) \((\d+)\)$", ledger_text, re.M)
ledger = [name for name, _ in ledger_rows]
pc_by_class = defaultdict(list)
pc_ids = []
for line in doc.splitlines():
    match = re.match(r"^\| (PC-\d+) \|", line)
    if not match:
        continue
    pc = match.group(1)
    pc_ids.append(pc)
    for klass in re.findall(r"\x60(\w+Tests)\x60", line):
        pc_by_class[klass].append(pc)
section = doc.split("## Ledger reverse closure (85 classes)", 1)[1]
rows = re.findall(r"^\| \x60(\w+Tests)\x60 \| (승격|비승격) — (.+) \|$", section, re.M)
categories = re.findall(
    r"^- \*\*(.+?):\*\*",
    doc.split("## 명시적 비승격", 1)[1].split("## Ledger reverse closure", 1)[0],
    re.M,
)
errors = []
for klass, kind, anchor in rows:
    expected = pc_by_class.get(klass, [])
    if kind == "승격" and re.findall(r"PC-\d+", anchor) != expected:
        errors.append(f"{klass}: PC mismatch")
    if kind == "비승격" and (expected or anchor not in categories):
        errors.append(f"{klass}: non-promotion mismatch")
promoted = sum(kind == "승격" for _, kind, _ in rows)
ok = (
    len(ledger) == len(set(ledger)) == 85
    and sum(int(count) for _, count in ledger_rows) == 828
    and set(pc_ids) == {f"PC-{number:02d}" for number in range(1, 32)}
    and len(pc_ids) == len(set(pc_ids)) == 31
    and [klass for klass, _, _ in rows] == ledger
    and len(rows) == 85
    and promoted == 39
    and not errors
)
print(f"ledger={len(ledger)} methods={sum(int(count) for _, count in ledger_rows)} pc_rows={len(pc_ids)}")
print(f"closure={len(rows)} promoted={promoted} non_promoted={len(rows)-promoted} missing=0 extra=0 duplicates=0 pc_mismatches={len(errors)}")
raise SystemExit(not ok)
PY
~~~

NOT-RUN: PC-31의 새 kernel 계약 test는 kernel 미구현이므로 실행 대상이 없다. legacy suite의 UninitializedRootGateTests는 공통 full suite에 포함됐다.

## Task 3 — docs/matrix-regen-adr13-obligations (WS-GPT-205)

VERDICT: PASS — matrix의 56개 고유 test reference를 stale 4에서 0으로 수리하고, ADR-0013 세 fault 의무를 matrix·promoted-contracts·M1-B의 동일한 TODO(M1-B) owner에 등록했다.

COMMITS: 4f33822ad55745afa926012e383ca514da67b1fb

HOTFILES: dev_docs/0.12.0-refactor-plan.md는 M1-B fixture list line 675-688만 접촉(5→8 및 ADR-0013 3행). docs/promoted-contracts.md는 신규 계약 의무 line 83-90만 추가. docs/traceability-matrix.md는 intro, I-07, ADR-0013 row만 접촉. M1-C는 Task 1 커밋 외 Task 3에서 접촉하지 않았다. review.py/common.py/run_tests.py는 접촉하지 않았다.

VERIFIED:

- 변경 전 unique reference 56개 중 stale 4개는 모두 삭제된 MigrationV2Phase2Tests였다:
  - test_phase2_is_self_extinguishing_and_second_run_changes_nothing
  - test_profile_seed_recovers_after_atomic_replace_commits_then_raises
  - test_file_move_recovers_after_atomic_replace_commits_then_raises
  - test_symlinked_project_state_is_rejected_without_external_write
- 현행 대응 증거 4개를 MigrationSunsetTests에서 인용했다. 아래 focused run은 Ran 4 tests / OK / rc=0이었다.

~~~bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py MigrationSunsetTests.test_pre_0_9_layout_is_refused_with_0_11_x_guidance MigrationSunsetTests.test_plain_machine_state_is_refused_without_registry_merge MigrationSunsetTests.test_pending_worktree_marker_is_refused_without_repair MigrationSunsetTests.test_completed_0_11_seed_and_empty_scaffolding_are_accepted
~~~

- 이 현행 evidence는 sunset no-write/no-repair/completed no-op까지만 증명한다. positive two-run idempotence, atomic-replace crash resume, file-move recovery, symlink refusal, previewable adoption은 대응 test가 없어 I-07에 gap/TODO(M1)으로 정직하게 남겼다.
- 아래 AST exact class+method 대조는 references=56 actual=817 stale=0, rc=0이었다.

~~~bash
uv run python - <<'PY'
import ast
import re
from pathlib import Path

matrix = Path("docs/traceability-matrix.md").read_text()
refs = set(re.findall(
    r'\x60([A-Za-z0-9_]+Tests\.test_[A-Za-z0-9_]+)\x60',
    matrix,
))
tree = ast.parse(Path("scripts/tests/run_tests.py").read_text())
actual = {
    f"{cls.name}.{method.name}"
    for cls in tree.body
    if isinstance(cls, ast.ClassDef)
    for method in cls.body
    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
    and method.name.startswith("test_")
}
stale = sorted(refs - actual)
print(f"references={len(refs)} actual={len(actual)} stale={len(stale)}")
for ref in stale:
    print(ref)
raise SystemExit(bool(stale))
PY
~~~

- ADR-0013 live-test 검색은 아래 명령 rc=1/no matches였다. 즉 token/epoch/version principal CAS, lock 후 tuple recheck, reclaim race의 현행 test가 없다는 matrix 표기가 source와 일치한다.

~~~bash
rg -n "owner_token|fencing_epoch|entity_version|lease_principal|lock_principal|reclaim" scripts/tests/run_tests.py
~~~

- 문서 anchor cross-check는 matrix ADR-0013 row=1, promoted obligations=3, M1-B ADR-0013 fixtures=3, total fixtures=8, rc=0이었다.
- 최종 공통 gate는 브리프 방식대로 파이프 없이 직접 rc를 보존했다. suite rc=0, Ran 817 tests in 140.609s, OK.

~~~bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; suite_rc=$?; echo "suite rc=$suite_rc"; exit $suite_rc
rg -n "Ran [0-9]+ tests|^OK$|FAILED|ERROR" /tmp/suite.log
~~~

- git diff --check rc=0. 81bd177..HEAD 변경 파일은 dev_docs/0.12.0-refactor-plan.md, docs/promoted-contracts.md, docs/traceability-matrix.md 세 개뿐이다. 최종 worktree clean.
- line-number 확인용 read-only rg를 처음 한 번 실행할 때 pattern의 backtick을 shell에서 quote하지 않아 zsh command-substitution warning이 났다. escaping 오류였고 파일 변경은 없었다. single-quoted pattern으로 재실행해 정상 확인했다.

NOT-RUN: waystone CLI는 금지에 따라 실행하지 않았다. ADR-0013 새 kernel test는 아직 TODO(M1-B)이므로 실행할 실물이 없다. GPU·network 검증은 이 docs task에 필요하지 않아 실행하지 않았다.
