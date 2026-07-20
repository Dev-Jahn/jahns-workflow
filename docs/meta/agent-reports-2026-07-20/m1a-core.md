# M1-A core/project split — execution report

VERDICT: PASS — common.py의 84개 선언을 core/project/git adapter로 source-identical 분할하고 102개 legacy 이름·monkeypatch·import-shadow 관측면을 shim으로 보존했으며 pinned 838 suite 전수가 green이다.
COMMITS: 0346839154aff46a642b7c0008704b23773fbb4e ([m1a-move]), d64bea08df0697df7d9670e76d2358a6acc9e631 ([m1a-adapter])
HOTFILES: dev_docs/0.12.0-refactor-plan.md 미접촉; scripts/review.py 미접촉; scripts/common.py 전체를 153-line re-export adapter로 교체; scripts/tests/run_tests.py 미접촉(byte-identical). 허용된 waystone/core/__init__.py, waystone/project/__init__.py, waystone/adapters/git.py만 추가 접촉.
VERIFIED: 선언 AST 84/84(함수 71·클래스 2·상수 11), missing/added/duplicate/changed 0; shim 102/102; core 상방 import 0; monkeypatch 3/3 및 import-shadow regression 34/34 green; fixture stdout/stderr 전후 byte-identical; manifest/source 838/838 delta 0; full suite Ran 838 tests, OK, suite rc=0; run_tests.py blob 동일; git diff --check rc=0; 최종 git status empty.
NOT-RUN: 금지된 installed/bare waystone CLI와 bin/waystone은 실행하지 않았다. sibling scripts·tests·bin·tasks.yaml·ROADMAP.md·PROGRESS.md·기존 docs/reviews는 수정하지 않았다. push/GPU/설치 release harness 없음.

## 0. 기준과 변경

- 시작 base: b0a92834cc47a0bf3985677a075246123ef36cee.
- 현행 common.py는 brief의 과거 표기 1114줄이 아니라 base에서 1127줄이었다. 외부 SHA를 조사하지 않고 이 시작 blob만 권위로 사용했다.
- plan의 830 표기는 stale이었다. brief, current manifest, 직전 skeleton evidence가 일치하는 838을 gate로 사용했다.
- move commit은 scripts/common.py를 제거하고 실제 선언을 세 owner로 이동했다.
- adapter commit은 PEP 723 metadata + temporary repo-root bootstrap + 84개 explicit re-export를 가진 scripts/common.py를 재생성했다.
- 기존 suite의 module-level monkeypatch를 보존하기 위해 shim module의 setattr/delattr을 동일 object를 가진 owner globals로 전달한다. 이는 common.git_rc 재바인딩 2건과 common.write_text_atomic patch 1건의 기존 의미를 보존한다.
- shim이 package owner를 import하면서 sys.modules["waystone"]를 선점하는 문제는, shim 진입 전에 root package가 없었던 경우에만 임시 parent 등록을 제거하고 bootstrap sys.path 항목도 pop하여 원래 import 순서를 복원했다. 이미 waystone.cli import 중인 front door에서는 parent를 유지한다.

## 1. Move commit AST source·1회 배치 증명

실행 명령 원문:

~~~bash
BASE=b0a92834cc47a0bf3985677a075246123ef36cee
MOVE=0346839154aff46a642b7c0008704b23773fbb4e
export BASE MOVE

uv run python - <<'PY'
import ast
import hashlib
import os
import subprocess
from collections import Counter, defaultdict

base = os.environ["BASE"]
move = os.environ["MOVE"]

def git_text(spec):
    return subprocess.run(
        ["git", "show", spec],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

old = git_text(f"{base}:scripts/common.py")
paths = subprocess.run(
    [
        "git", "ls-tree", "-r", "--name-only", move, "--",
        "waystone/core", "waystone/project", "waystone/adapters",
    ],
    check=True,
    capture_output=True,
    text=True,
).stdout.splitlines()
paths = sorted(path for path in paths if path.endswith(".py"))
sources = {path: git_text(f"{move}:{path}") for path in paths}

def assignment_names(node):
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    out = []

    def walk(target):
        if isinstance(target, ast.Name):
            out.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                walk(item)

    for target in targets:
        walk(target)
    return out

def exact_segment(source, node):
    segment = ast.get_source_segment(source, node)
    if (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.decorator_list
    ):
        lines = source.splitlines(keepends=True)
        start = min(decorator.lineno for decorator in node.decorator_list)
        segment = "".join(lines[start - 1:node.lineno - 1]) + segment
    return segment

def declarations(source, path):
    rows = []
    for node in ast.parse(source, filename=path).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            rows.append((node.name, "function", exact_segment(source, node), path))
        elif isinstance(node, ast.ClassDef):
            rows.append((node.name, "class", exact_segment(source, node), path))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for name in assignment_names(node):
                rows.append((name, "constant", exact_segment(source, node), path))
    return rows

before_rows = declarations(old, f"{base}:scripts/common.py")
after_rows = [
    row
    for path, source in sources.items()
    for row in declarations(source, path)
]
before = {name: (kind, segment) for name, kind, segment, _ in before_rows}
after_by_name = defaultdict(list)
for row in after_rows:
    after_by_name[row[0]].append(row)

old_counts = Counter(name for name, *_ in before_rows)
duplicate_old = sorted(name for name, count in old_counts.items() if count != 1)
missing = sorted(set(before) - set(after_by_name))
added = sorted(set(after_by_name) - set(before))
duplicate_new = sorted(
    name for name, rows in after_by_name.items() if len(rows) != 1
)
kind_changed = sorted(
    name
    for name in set(before) & set(after_by_name)
    if len(after_by_name[name]) == 1
    and before[name][0] != after_by_name[name][0][1]
)
changed = sorted(
    name
    for name in set(before) & set(after_by_name)
    if len(after_by_name[name]) == 1
    and before[name][1] != after_by_name[name][0][2]
)

print(f"target_files={paths}")
print(f"before_declarations={len(before_rows)}")
print(f"after_declarations={len(after_rows)}")
print(f"before_functions={sum(kind == 'function' for _, kind, *_ in before_rows)}")
print(f"before_classes={sum(kind == 'class' for _, kind, *_ in before_rows)}")
print(f"before_constants={sum(kind == 'constant' for _, kind, *_ in before_rows)}")
print(f"duplicate_old={duplicate_old}")
print(f"missing={missing}")
print(f"added={added}")
print(f"duplicate_new={duplicate_new}")
print(f"kind_changed={kind_changed}")
print(f"changed={changed}")

for name in sorted(before):
    rows = after_by_name.get(name, [])
    destination = rows[0][3] if len(rows) == 1 else "<invalid>"
    print(f"MAP {name} -> {destination}")

digest = hashlib.sha256(
    "\0".join(
        f"{before[name][0]}\0{name}\0{before[name][1]}"
        for name in sorted(before)
    ).encode("utf-8")
).hexdigest()
print(f"declaration_source_sha256={digest}")

failed = (
    duplicate_old
    or missing
    or added
    or duplicate_new
    or kind_changed
    or changed
)
raise SystemExit(bool(failed))
PY
~~~

결과(rc=0):

~~~text
target_files=['waystone/adapters/__init__.py', 'waystone/adapters/git.py', 'waystone/core/__init__.py', 'waystone/project/__init__.py']
before_declarations=84
after_declarations=84
before_functions=71
before_classes=2
before_constants=11
duplicate_old=[]
missing=[]
added=[]
duplicate_new=[]
kind_changed=[]
changed=[]
declaration_source_sha256=4031b4199bb91f54dbf58ccf28cdb73f91331da3c01ebaf88b76ca5cc563c9de
~~~

전수 이름→새 모듈 매핑:

~~~text
MAP CONFIG_NAME -> waystone/project/__init__.py
MAP MILESTONE_ID_RE -> waystone/project/__init__.py
MAP MILESTONE_STATUSES -> waystone/project/__init__.py
MAP Pre09StateError -> waystone/core/__init__.py
MAP ROUND_RE -> waystone/project/__init__.py
MAP SEVERITIES -> waystone/project/__init__.py
MAP TASKS_NAME -> waystone/project/__init__.py
MAP TASK_ID_RE -> waystone/project/__init__.py
MAP TASK_STATUSES -> waystone/project/__init__.py
MAP TASK_TYPES -> waystone/project/__init__.py
MAP WorkflowError -> waystone/core/__init__.py
MAP _VERIFY_FETCH_REF_PREFIX -> waystone/adapters/git.py
MAP _VERIFY_FETCH_REF_RE -> waystone/adapters/git.py
MAP _append_children -> waystone/project/__init__.py
MAP _append_existing -> waystone/project/__init__.py
MAP _append_preserved_profile_conflicts -> waystone/project/__init__.py
MAP _checked_entries -> waystone/project/__init__.py
MAP _checked_lstat -> waystone/project/__init__.py
MAP _ensure_project_self_ignore -> waystone/core/__init__.py
MAP _lock_holder_message -> waystone/core/__init__.py
MAP _lock_timeout -> waystone/core/__init__.py
MAP _lock_verb -> waystone/core/__init__.py
MAP _normalized_registry_path -> waystone/project/__init__.py
MAP _packet_declared_scope -> waystone/core/__init__.py
MAP _path_in_declared_scope -> waystone/core/__init__.py
MAP _pre_0_9_host_roots -> waystone/project/__init__.py
MAP _preserved_pre_0_9_root -> waystone/project/__init__.py
MAP _project_slug -> waystone/project/__init__.py
MAP _read_registry -> waystone/project/__init__.py
MAP _real_directory -> waystone/core/__init__.py
MAP _record_scope_path -> waystone/core/__init__.py
MAP _regular_file -> waystone/core/__init__.py
MAP _sweep_stale_verify_fetch_refs -> waystone/adapters/git.py
MAP _unresolved_pre_0_9_machine_paths -> waystone/project/__init__.py
MAP _unresolved_pre_0_9_project_paths -> waystone/project/__init__.py
MAP _upstream_tracking -> waystone/adapters/git.py
MAP ancestry_status -> waystone/adapters/git.py
MAP canonical_payload_hash -> waystone/core/__init__.py
MAP canonical_scope_prefixes -> waystone/core/__init__.py
MAP consent_path -> waystone/project/__init__.py
MAP content_hash -> waystone/core/__init__.py
MAP delegation_scope_drift -> waystone/core/__init__.py
MAP ensure_project_state_dir -> waystone/project/__init__.py
MAP fetch_upstream_head -> waystone/adapters/git.py
MAP find_project_root -> waystone/project/__init__.py
MAP git -> waystone/adapters/git.py
MAP git_branch_info -> waystone/adapters/git.py
MAP git_full_sha -> waystone/adapters/git.py
MAP git_rc -> waystone/adapters/git.py
MAP has_accepted_consent -> waystone/project/__init__.py
MAP has_project_config -> waystone/project/__init__.py
MAP head_pushed -> waystone/adapters/git.py
MAP hold_lock -> waystone/core/__init__.py
MAP hold_project_lock -> waystone/project/__init__.py
MAP is_ancestor -> waystone/adapters/git.py
MAP load_config -> waystone/project/__init__.py
MAP load_tasks -> waystone/project/__init__.py
MAP load_yaml -> waystone/core/__init__.py
MAP machine_dir -> waystone/project/__init__.py
MAP migrate_home_data -> waystone/project/__init__.py
MAP migrate_project_state -> waystone/project/__init__.py
MAP next_actionable -> waystone/project/__init__.py
MAP normalize_config -> waystone/project/__init__.py
MAP normalize_scope_prefix -> waystone/core/__init__.py
MAP overlay_lock_path -> waystone/project/__init__.py
MAP parse_iso_timestamp -> waystone/core/__init__.py
MAP project_lock_path -> waystone/project/__init__.py
MAP project_state_path -> waystone/project/__init__.py
MAP record_consent -> waystone/project/__init__.py
MAP registry_entry_paths -> waystone/project/__init__.py
MAP registry_lock_path -> waystone/project/__init__.py
MAP registry_path -> waystone/project/__init__.py
MAP require_initialized_root -> waystone/project/__init__.py
MAP require_supported_machine_state -> waystone/project/__init__.py
MAP require_supported_project_state -> waystone/project/__init__.py
MAP resolve_project_paths -> waystone/project/__init__.py
MAP resume_path -> waystone/project/__init__.py
MAP slugify -> waystone/core/__init__.py
MAP start_here_path -> waystone/project/__init__.py
MAP upstream_ref -> waystone/adapters/git.py
MAP validate_registry_path_uniqueness -> waystone/project/__init__.py
MAP worktrees_cache_dir -> waystone/project/__init__.py
MAP write_bytes_atomic -> waystone/core/__init__.py
MAP write_text_atomic -> waystone/core/__init__.py
~~~

## 2. Shim 완전성

구 module의 AST-bound 이름은 future feature binding annotations를 포함해 102개다. import 후 interpreter dunder 8개만 제외한 실제 shim namespace와 대조했다. bootstrap-only owner/flag/class 이름은 설치 직후 제거된다.

실행 명령 원문:

~~~bash
BASE=b0a92834cc47a0bf3985677a075246123ef36cee
export BASE

uv run python - <<'PY'
import ast
import hashlib
import importlib
import os
import subprocess
import sys
from pathlib import Path

old = subprocess.run(
    ["git", "show", f"{os.environ['BASE']}:scripts/common.py"],
    check=True,
    capture_output=True,
    text=True,
).stdout

def target_names(target):
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names = set()
        for item in target.elts:
            names.update(target_names(item))
        return names
    return set()

def ast_bindings(source):
    names = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            names.update(
                alias.asname or alias.name.split(".")[0]
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name != "*"
            )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names.update(target_names(target))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            names.update(target_names(node.target))
    return names

expected = ast_bindings(old)
sys.path.insert(0, str(Path("scripts").resolve()))
expected_after_insert = list(sys.path)
shim = importlib.import_module("common")
path_restored = sys.path == expected_after_insert

implicit = {
    "__name__", "__doc__", "__package__", "__loader__", "__spec__",
    "__file__", "__cached__", "__builtins__",
}
actual = set(vars(shim)) - implicit
missing = sorted(expected - actual)
added = sorted(actual - expected)
expected_file = (Path.cwd() / "scripts/common.py").resolve()
wrong_file = Path(shim.__file__).resolve() != expected_file

print(f"old_ast_names={len(expected)}")
print(f"shim_runtime_names={len(actual)}")
print(f"shim_file={Path(shim.__file__).resolve()}")
print(f"bootstrap_path_restored={path_restored}")
print(f"missing={missing}")
print(f"added={added}")
print(
    "name_set_sha256="
    + hashlib.sha256("\0".join(sorted(expected)).encode()).hexdigest()
)
raise SystemExit(bool(missing or added or wrong_file or not path_restored))
PY
~~~

결과(rc=0):

~~~text
old_ast_names=102
shim_runtime_names=102
shim_file=/Users/jahn/workspace/waystone/.claude/worktrees/m1a-core/scripts/common.py
bootstrap_path_restored=True
missing=[]
added=[]
name_set_sha256=d530bac881b9b2197cd0b0f75009563dc0329a28ef9749bd5e54da14c1109fa3
~~~

## 3. core 상방 import 0

실행 명령 원문:

~~~bash
uv run python - <<'PY'
import ast
import importlib.util
from pathlib import Path

forbidden = (
    "waystone.project",
    "waystone.adapters",
    "waystone.features",
)
violations = []
imports_scanned = 0
files = sorted(Path("waystone/core").rglob("*.py"))

for path in files:
    relative = path.with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    module = ".".join(parts)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        candidates = []
        if isinstance(node, ast.Import):
            imports_scanned += 1
            candidates.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports_scanned += 1
            if node.level:
                relative_name = "." * node.level + (node.module or "")
                base = importlib.util.resolve_name(relative_name, package)
            else:
                base = node.module or ""
            candidates.append(base)
            candidates.extend(
                f"{base}.{alias.name}" if base else alias.name
                for alias in node.names
            )

        for candidate in candidates:
            if any(
                candidate == prefix or candidate.startswith(prefix + ".")
                for prefix in forbidden
            ):
                violations.append(f"{path}:{node.lineno}: {candidate}")

print(f"core_files={len(files)}")
print(f"imports_scanned={imports_scanned}")
print(f"upward_import_violations={len(violations)}")
for violation in violations:
    print(violation)
raise SystemExit(bool(violations))
PY
~~~

결과(rc=0):

~~~text
core_files=1
imports_scanned=15
upward_import_violations=0
~~~

실제 moved-definition cross-group lexical edge도 project→core 7개 binder뿐이고 git은 stdlib-only다. core→project/adapters/features edge는 없다.

## 4. Tempdir fixture front-door byte 대조

Fixture: /tmp/m1a-core-smoke.ixrC8y/project. .waystone.yml, 2-task tasks.yaml, 빈 docs/reviews만 만들었고 HOME/CODEX_HOME/WAYSTONE_HOME은 fixture 하위로 격리했다.

수정 전 시작 HEAD 실행 명령 원문:

~~~bash
env -u FORCE_COLOR -u CLICOLOR_FORCE \
  HOME=/tmp/m1a-core-smoke.ixrC8y/home \
  CODEX_HOME=/tmp/m1a-core-smoke.ixrC8y/home/.codex \
  WAYSTONE_HOME=/tmp/m1a-core-smoke.ixrC8y/home/.waystone \
  uv run python scripts/waystone.py task list \
  /tmp/m1a-core-smoke.ixrC8y/project \
  > /tmp/m1a-core-smoke-before.stdout \
  2> /tmp/m1a-core-smoke-before.stderr
~~~

결과: front_door_before_rc=0.

최종 HEAD 실행 및 대조 명령 원문:

~~~bash
env -u FORCE_COLOR -u CLICOLOR_FORCE \
  HOME=/tmp/m1a-core-smoke.ixrC8y/home \
  CODEX_HOME=/tmp/m1a-core-smoke.ixrC8y/home/.codex \
  WAYSTONE_HOME=/tmp/m1a-core-smoke.ixrC8y/home/.waystone \
  uv run python scripts/waystone.py task list \
  /tmp/m1a-core-smoke.ixrC8y/project \
  > /tmp/m1a-core-smoke-final.stdout \
  2> /tmp/m1a-core-smoke-final.stderr

cmp -s /tmp/m1a-core-smoke-before.stdout /tmp/m1a-core-smoke-final.stdout
cmp -s /tmp/m1a-core-smoke-before.stderr /tmp/m1a-core-smoke-final.stderr
shasum -a 256 \
  /tmp/m1a-core-smoke-before.stdout /tmp/m1a-core-smoke-final.stdout \
  /tmp/m1a-core-smoke-before.stderr /tmp/m1a-core-smoke-final.stderr
~~~

결과:

~~~text
front_door_final_rc=0
stdout_cmp_rc=0
stderr_cmp_rc=0
1312db0f6d6b525e451924a9d45583159f0c17c10161f0490a7199ffdb285f5e  before.stdout
1312db0f6d6b525e451924a9d45583159f0c17c10161f0490a7199ffdb285f5e  final.stdout
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  before.stderr
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  final.stderr
~~~

stdout 69 bytes:

~~~text
feat/done  [done]  completed task
feat/active  [active]  active task
~~~

stderr는 양쪽 모두 0 bytes다.

## 5. Monkeypatch·import-shadow 역추적

수정 전 다음 3개 특성화는 3/3 green이었다.

~~~bash
env -u FORCE_COLOR -u CLICOLOR_FORCE \
  uv run scripts/tests/run_tests.py \
  RemoteTests.test_empty_temporary_fetch_ref_fails_closed \
  RemoteTests.test_live_fetch_evidence_ignores_fetch_head_overwrite_and_cleans_ref \
  UninitializedRootGateTests.test_state_self_ignore_is_restored_atomically_before_marker_write \
  > /tmp/m1a-core-monkeypatch-before.log 2>&1
~~~

일반 re-export는 함수의 globals가 owner module로 이동하므로 common.git_rc 대입과 common.write_text_atomic patch를 잃는다. adapter의 module class bridge를 추가한 뒤 같은 명령은 다시 3/3, rc=0이었다.

첫 full suite 진단 실행은 838개를 모두 실행한 뒤 rc=1, errors=26이었다. 모든 오류가 common이 owner package를 import한 뒤 빈 root package가 scripts/waystone.py adapter보다 먼저 선택되어 waystone.main/os가 사라진 동일 원인이었다. 테스트를 수정하지 않았고, bootstrap path 복원 + 기존 root 부재 시 임시 parent 제거로 해결했다.

해당 실패 경계 전수에 가까운 regression 명령:

~~~bash
env -u FORCE_COLOR -u CLICOLOR_FORCE \
  uv run scripts/tests/run_tests.py \
  WaystoneStorageCliTests \
  StatuslineTests \
  L2DPolicyMachineTests \
  L2DAdversarialFindingTests.test_f8_consent_is_bound_to_candidate_stage_target_and_template_hash \
  DelegateCliTests.test_waystone_dispatcher_routes_delegate \
  ImproveScopeTests.test_project_default_filters_claude_and_keeps_outputs_and_decisions_local \
  ImproveScopeTests.test_user_wide_scans_all_projects_and_never_touches_project_improve \
  OverlayStoreTests.test_waystone_dispatcher_routes_overlay \
  M2DocsTests.test_readme_and_front_door_name_all_new_surfaces \
  UninitializedRootGateTests.test_stale_registered_project_can_still_be_unregistered \
  > /tmp/m1a-core-shadow-regressions.log 2>&1
~~~

결과(rc=0): Ran 34 tests, OK.

standalone import-order probe도 다음을 증명했다.

~~~text
import common
assert sys.path == before
assert "waystone" not in sys.modules
import waystone
assert callable(waystone.main)
assert waystone.os is not None
~~~

결과: scripts/waystone.py가 선택되고 main/os가 존재하며 bootstrap 전후 sys.path가 동일했다.

## 6. Pinned suite와 identity

최종 full suite 실행 명령 원문(파이프 없음, 지정 고유 로그):

~~~bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1a-core.log 2>&1; echo "suite rc=$?"
~~~

최종 결과:

~~~text
suite rc=0
Ran 838 tests in 152.799s
OK
~~~

manifest/source 정적 대조:

~~~bash
manifest_count=$(awk '!/^#/ && NF {n++} END{print n+0}' docs/m1a-suite-manifest.txt)
source_count=$(awk '/^class [A-Za-z0-9_]+\(/ {name=$2; sub(/\(.*/, "", name)} /^    def test_[A-Za-z0-9_]+\(/ {test=$2; sub(/\(.*/, "", test); print name "." test}' scripts/tests/run_tests.py | wc -l | tr -d ' ')
source_unique=$(awk '/^class [A-Za-z0-9_]+\(/ {name=$2; sub(/\(.*/, "", name)} /^    def test_[A-Za-z0-9_]+\(/ {test=$2; sub(/\(.*/, "", test); print name "." test}' scripts/tests/run_tests.py | LC_ALL=C sort -u | wc -l | tr -d ' ')
delta=$(comm -3 <(awk '!/^#/ && NF {print}' docs/m1a-suite-manifest.txt | LC_ALL=C sort) <(awk '/^class [A-Za-z0-9_]+\(/ {name=$2; sub(/\(.*/, "", name)} /^    def test_[A-Za-z0-9_]+\(/ {test=$2; sub(/\(.*/, "", test); print name "." test}' scripts/tests/run_tests.py | LC_ALL=C sort) | wc -l | tr -d ' ')
~~~

결과:

~~~text
manifest_count=838
source_count=838
source_unique=838
symmetric_delta=0
~~~

run_tests.py blob 대조:

~~~bash
BASE=b0a92834cc47a0bf3985677a075246123ef36cee
base_blob=$(git rev-parse "$BASE:scripts/tests/run_tests.py")
head_blob=$(git rev-parse "HEAD:scripts/tests/run_tests.py")
worktree_blob=$(git hash-object scripts/tests/run_tests.py)
~~~

결과(rc=0):

~~~text
run_tests_base_blob=73b5472f0cae1c0e19447f00ec9a5dacdcbba769
run_tests_head_blob=73b5472f0cae1c0e19447f00ec9a5dacdcbba769
run_tests_worktree_blob=73b5472f0cae1c0e19447f00ec9a5dacdcbba769
~~~

## 7. 범위·whitespace·cleanliness

실행 명령 원문:

~~~bash
git diff --check b0a92834cc47a0bf3985677a075246123ef36cee HEAD
git diff --check
git diff --name-only b0a92834cc47a0bf3985677a075246123ef36cee HEAD
git status --porcelain=v1
~~~

결과:

- range diff check rc=0.
- worktree diff check rc=0.
- changed paths는 scripts/common.py, waystone/adapters/git.py, waystone/core/__init__.py, waystone/project/__init__.py 네 개뿐이다.
- git status --porcelain=v1 출력 없음.
- 두 커밋 모두 5 MiB보다 훨씬 작고 push하지 않았다.

## 최종 요약

VERDICT: PASS — source-identical 84-name split, complete 102-name shim, monkeypatch/import-shadow compatibility, pinned 838 suite gate를 모두 통과했다.
COMMITS: 0346839154aff46a642b7c0008704b23773fbb4e, d64bea08df0697df7d9670e76d2358a6acc9e631
HOTFILES: scripts/common.py 전체 adapter 교체만 수행; plan/review.py/run_tests.py 미접촉. 허용된 신규 package 파일 3개 외 변경 없음.
VERIFIED: AST 84/84·changed 0; shim 102/102; core upward import 0; fixture byte identity; targeted 3/3 + 34/34; full suite 838/838 rc=0; manifest delta 0; run_tests blob identity; diff check rc=0; clean.
NOT-RUN: installed/bare waystone CLI, bin/waystone, push, GPU, release install harness.

