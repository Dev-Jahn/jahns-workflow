# M1-A registry move — execution report

VERDICT: PASS — `scripts/tasks.py`의 선언 32개를 source-identical하게 `waystone/project/tasks_cli.py`로 이동하고, 구 AST-bound 49개 이름·runpy/direct dispatcher·module monkeypatch·import-shadow 관측면을 thin adapter로 보존했으며 pinned 838 suite 전수가 green이다.
COMMITS: `2b2d8ad9284e1614e9704ecc0de4f0171fef8a96` (`[m1a-move]`), `e7da20e36953865606a2b6452432c8b149cf2bd5` (`[m1a-adapter]`)
HOTFILES: `dev_docs/0.12.0-refactor-plan.md`, `scripts/review.py`, `scripts/common.py`, `scripts/tests/run_tests.py` 모두 미접촉. 허용된 신규 `waystone/project/tasks_cli.py`와 adapter `scripts/tasks.py`만 접촉했다.
VERIFIED: 선언 AST 32/32(함수 19·클래스 0·상수 13), missing/added/duplicate/changed 0; adapter 49/49, missing/added 0; setattr/delattr monkeypatch bridge 및 import-shadow 복원; temp fixture `task list`+`task show` 전후 stdout/stderr byte-identical; runpy adapter도 동일; 표적 32/32 green; manifest/source 838/838 delta 0; full suite `Ran 838 tests in 146.956s`, `OK`, suite rc=0; `run_tests.py` base/HEAD/worktree blob 동일; range `git diff --check` rc=0; 최종 worktree clean.
NOT-RUN: 금지된 installed/bare `waystone` CLI와 `bin/waystone`은 실행하지 않았다. sibling scripts·tests·bin·`waystone/project/__init__.py`·`tasks.yaml`·`ROADMAP.md`·`PROGRESS.md`·기존 `docs/reviews`는 수정하지 않았다. push/GPU/release harness 없음.

## 0. 기준·판단

- 시작 base: `c597b6b788e0c20e8b17508daa014c845884ff9f`.
- base의 `scripts/tasks.py`는 brief의 “781줄 부근”과 달리 679줄이었다. 외부 SHA를 조사하지 않고 시작 HEAD blob만 권위로 사용했다.
- `round`와 `validate`가 계속 `scripts/`에 남고 두 모듈 모두 legacy `common` 표면을 사용하므로, moved module은 기존 common shim 경유를 유지했다. 변경은 새 위치에서 sibling scripts를 찾는 bootstrap 한 줄뿐이다:

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
```

- 단순 re-export는 불충분했다. `scripts/tests/run_tests.py:6800`이 `tasks.migrate_project_state`를 monkeypatch하고 moved `main()`은 owner module global을 조회하므로, `scripts/common.py`와 같은 module-class setattr/delattr bridge를 사용했다.
- adapter가 package owner를 import한 뒤 root `waystone` package를 남기면 이후 `import waystone`이 `scripts/waystone.py` 대신 package stub을 선택한다. 진입 전에 root가 없었던 경우에만 이를 제거했다.
- moved owner가 legacy처럼 `scripts`를 `sys.path`에 추가하므로 adapter bootstrap은 blind `pop(0)`가 아니라 자신이 추가한 repo-root 항목만 `remove`했다. 별도 child-process 대조에서 old/new `sys.path`와 이후 `waystone.__file__`이 완전히 같았다.
- adapter는 기존 실행 비트를 유지했다(`100755`).

수정 전 구조 RED 원문:

```bash
uv run python - <<'PY' > /tmp/m1a-registry-red.log 2>&1
from pathlib import Path
path = Path('waystone/project/tasks_cli.py')
print(f'tasks_cli_exists={path.is_file()}')
raise SystemExit(not path.is_file())
PY
```

결과: `tasks_cli_exists=False`, rc=1. 이후 같은 구조 조건은 green이다.

진단 중 최초 adapter path oracle은 owner만 scripts를 한 번 추가한다고 잘못 가정해 rc=1이었다. 실제 legacy import는 `tasks`, `round`, `validate` 각 모듈의 scripts-path insert를 보존한다. old source와 final adapter를 각각 fresh child process에서 실행해 전체 `sys.path`를 직접 비교하는 아래 oracle로 교정했고 `sys_path_equal=True`, `import_shadow_equal=True`, rc=0이었다. 제품 코드나 테스트를 이 진단 실패에 맞춰 변경하지 않았다.

## 1. Move commit — AST source·1회 배치 증명

최종 실행 명령 원문:

```bash
BASE=c597b6b788e0c20e8b17508daa014c845884ff9f
export BASE
uv run python - <<'PY' > /tmp/m1a-registry-ast.log 2>&1
import ast
import hashlib
import os
import subprocess
from collections import Counter, defaultdict

base = os.environ['BASE']
head = subprocess.run(['git', 'rev-parse', 'HEAD'], check=True,
                      capture_output=True, text=True).stdout.strip()

def git_text(spec):
    return subprocess.run(['git', 'show', spec], check=True,
                          capture_output=True, text=True).stdout

old = git_text(f'{base}:scripts/tasks.py')
path = 'waystone/project/tasks_cli.py'
new = git_text(f'{head}:{path}')

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

def declarations(source, source_path):
    rows = []
    for node in ast.parse(source, filename=source_path).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            rows.append((node.name, 'function', ast.get_source_segment(source, node), source_path))
        elif isinstance(node, ast.ClassDef):
            rows.append((node.name, 'class', ast.get_source_segment(source, node), source_path))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for name in assignment_names(node):
                rows.append((name, 'constant', ast.get_source_segment(source, node), source_path))
    return rows

before_rows = declarations(old, f'{base}:scripts/tasks.py')
after_rows = declarations(new, f'{head}:{path}')
before = {name: (kind, segment) for name, kind, segment, _ in before_rows}
after_by_name = defaultdict(list)
for row in after_rows:
    after_by_name[row[0]].append(row)
duplicate_old = sorted(name for name, count in Counter(r[0] for r in before_rows).items()
                       if count != 1)
missing = sorted(set(before) - set(after_by_name))
added = sorted(set(after_by_name) - set(before))
duplicate_new = sorted(name for name, rows in after_by_name.items() if len(rows) != 1)
kind_changed = sorted(name for name in set(before) & set(after_by_name)
                      if len(after_by_name[name]) == 1
                      and before[name][0] != after_by_name[name][0][1])
changed = sorted(name for name in set(before) & set(after_by_name)
                 if len(after_by_name[name]) == 1
                 and before[name][1] != after_by_name[name][0][2])
print(f'before_declarations={len(before_rows)}')
print(f'after_declarations={len(after_rows)}')
print(f'before_functions={sum(kind == "function" for _, kind, *_ in before_rows)}')
print(f'before_classes={sum(kind == "class" for _, kind, *_ in before_rows)}')
print(f'before_constants={sum(kind == "constant" for _, kind, *_ in before_rows)}')
print(f'duplicate_old={duplicate_old}')
print(f'missing={missing}')
print(f'added={added}')
print(f'duplicate_new={duplicate_new}')
print(f'kind_changed={kind_changed}')
print(f'changed={changed}')
for name in sorted(before):
    rows = after_by_name.get(name, [])
    destination = rows[0][3] if len(rows) == 1 else '<invalid>'
    print(f'MAP {name} -> {destination}')
print('declaration_source_sha256=' + hashlib.sha256('\0'.join(
    f'{before[name][0]}\0{name}\0{before[name][1]}' for name in sorted(before)
).encode()).hexdigest())
raise SystemExit(bool(duplicate_old or missing or added or duplicate_new
                      or kind_changed or changed))
PY
```

결과(rc=0):

```text
before_declarations=32
after_declarations=32
before_functions=19
before_classes=0
before_constants=13
duplicate_old=[]
missing=[]
added=[]
duplicate_new=[]
kind_changed=[]
changed=[]
declaration_source_sha256=c6d08eab281d5c2c3b1dfaa2dbf3c68736df8847fa9e8be77f4e5406e7546397
```

32개 이름 모두 final `e7da20e...:waystone/project/tasks_cli.py`에 정확히 한 번 매핑되었다. move commit의 rename diff는 99%, 실제 내용 diff는 위 bootstrap 경로 한 줄의 `1 insertion(+), 1 deletion(-)`뿐이다.

## 2. Adapter 이름 완전성·monkeypatch·import-shadow

최종 실행 명령 원문:

```bash
BASE=c597b6b788e0c20e8b17508daa014c845884ff9f
export BASE
uv run python - <<'PY' > /tmp/m1a-registry-adapter.log 2>&1
import ast
import hashlib
import importlib
import os
import subprocess
import sys
from pathlib import Path

old = subprocess.run(
    ['git', 'show', f"{os.environ['BASE']}:scripts/tasks.py"],
    check=True, capture_output=True, text=True,
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
            names.update(alias.asname or alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names if alias.name != '*')
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names.update(target_names(target))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            names.update(target_names(node.target))
    return names

expected = ast_bindings(old)
sys.path.insert(0, str(Path('scripts').resolve()))
shim = importlib.import_module('tasks')
implicit = {
    '__name__', '__doc__', '__package__', '__loader__', '__spec__',
    '__file__', '__cached__', '__builtins__',
}
actual = set(vars(shim)) - implicit
missing = sorted(expected - actual)
added = sorted(actual - expected)
owner = sys.modules['waystone.project.tasks_cli']
original = shim.migrate_project_state
marker = object()
shim.migrate_project_state = marker
set_bridge = owner.migrate_project_state is marker
del shim.migrate_project_state
delete_bridge = not hasattr(owner, 'migrate_project_state')
shim.migrate_project_state = original
restore_bridge = owner.migrate_project_state is original
root_package_cleaned = 'waystone' not in sys.modules
waystone = importlib.import_module('waystone')
shadow_file = Path(waystone.__file__).resolve()
shadow_ok = shadow_file == Path('scripts/waystone.py').resolve()
wrong_file = Path(shim.__file__).resolve() != Path('scripts/tasks.py').resolve()
print(f'old_ast_names={len(expected)}')
print(f'adapter_runtime_names={len(actual)}')
print(f'adapter_file={Path(shim.__file__).resolve()}')
print(f'missing={missing}')
print(f'added={added}')
print(f'set_bridge={set_bridge}')
print(f'delete_bridge={delete_bridge}')
print(f'restore_bridge={restore_bridge}')
print(f'root_package_cleaned={root_package_cleaned}')
print(f'waystone_import_file={shadow_file}')
print('name_set_sha256=' + hashlib.sha256('\0'.join(sorted(expected)).encode()).hexdigest())
raise SystemExit(bool(
    missing or added or wrong_file or not set_bridge or not delete_bridge
    or not restore_bridge or not root_package_cleaned or not shadow_ok
))
PY
```

결과(rc=0):

```text
old_ast_names=49
adapter_runtime_names=49
missing=[]
added=[]
set_bridge=True
delete_bridge=True
restore_bridge=True
root_package_cleaned=True
waystone_import_file=.../scripts/waystone.py
name_set_sha256=1d37f39e78e7e45160cf64e128fb8651aeec32fc518d745ce5373b9161f3df4a
```

Bridge-sensitive 기존 회귀를 포함한 표적 gate 원문:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE \
  uv run scripts/tests/run_tests.py TaskCliTests TaskRegressionTests \
  > /tmp/m1a-registry-targeted-after.log 2>&1
```

결과(rc=0): `Ran 32 tests in 1.722s`, `OK`.

## 3. Temp fixture front-door·runpy byte 대조

Fixture root는 `mktemp -d /tmp/m1a-registry-smoke.XXXXXX`로 만든 `/tmp/m1a-registry-smoke.OBp6wf`이며 실제 project/machine state와 격리했다. `.waystone.yml`, 두 task를 가진 `tasks.yaml`, 빈 `docs/reviews`, fixture-local HOME만 만들었다.

이동 전 base에서 실행한 front-door 원문:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE \
  HOME="$smoke_root/home" \
  CODEX_HOME="$smoke_root/home/.codex" \
  WAYSTONE_HOME="$smoke_root/home/.waystone" \
  uv run python scripts/waystone.py task list "$smoke_root/project" \
  > /tmp/m1a-registry-before-list.stdout \
  2> /tmp/m1a-registry-before-list.stderr

env -u FORCE_COLOR -u CLICOLOR_FORCE \
  HOME="$smoke_root/home" \
  CODEX_HOME="$smoke_root/home/.codex" \
  WAYSTONE_HOME="$smoke_root/home/.waystone" \
  uv run python scripts/waystone.py task show feat/active "$smoke_root/project" \
  > /tmp/m1a-registry-before-show.stdout \
  2> /tmp/m1a-registry-before-show.stderr
```

final HEAD에서 동일 명령을 `after-list/show` 파일로 실행한 뒤 대조한 원문:

```bash
cmp -s /tmp/m1a-registry-before-list.stdout /tmp/m1a-registry-after-list.stdout
cmp -s /tmp/m1a-registry-before-list.stderr /tmp/m1a-registry-after-list.stderr
cmp -s /tmp/m1a-registry-before-show.stdout /tmp/m1a-registry-after-show.stdout
cmp -s /tmp/m1a-registry-before-show.stderr /tmp/m1a-registry-after-show.stderr
shasum -a 256 \
  /tmp/m1a-registry-before-list.stdout /tmp/m1a-registry-after-list.stdout \
  /tmp/m1a-registry-before-list.stderr /tmp/m1a-registry-after-list.stderr \
  /tmp/m1a-registry-before-show.stdout /tmp/m1a-registry-after-show.stdout \
  /tmp/m1a-registry-before-show.stderr /tmp/m1a-registry-after-show.stderr
```

결과:

```text
list rc=0 stdout_cmp=0 stderr_cmp=0
show rc=0 stdout_cmp=0 stderr_cmp=0
list stdout: 99 bytes, sha256 2a1df78016e79aa66e0d87c6fa2c1c5ef57dd6793e0f6e02cad5a6e19a69dbd3
show stdout: 65 bytes, sha256 2786c307e135142a71bec8313484ae77f9e9a5b6a71de9f72f3260bf6d1e784f
all stderr: 0 bytes, sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

Adapter의 runpy 표면도 다음 형태로 list/show 각각 실행했다:

```bash
SMOKE_PROJECT="$smoke_root/project" uv run python - <<'PY'
import os
import runpy
ns = runpy.run_path('scripts/tasks.py', run_name='__waystone_dispatch__')
raise SystemExit(ns['main'](['list', os.environ['SMOKE_PROJECT']]))
PY
```

`show`는 `ns['main'](['show', 'feat/active', os.environ['SMOKE_PROJECT']])`로 실행했다. 두 명령 모두 rc=0이고 각각의 before stdout/stderr와 `cmp` rc=0이었다.

금지된 installed/bare `waystone` 및 `bin/waystone`은 실행하지 않았다.

## 4. Pinned full suite

실행 원문(파이프 없이 rc 직접 캡처, 지정 고유 로그):

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE \
  uv run scripts/tests/run_tests.py \
  > /tmp/suite-m1a-registry.log 2>&1
suite_rc=$?
printf 'suite rc=%s\n' "$suite_rc"
exit "$suite_rc"
```

결과:

```text
suite rc=0
Ran 838 tests in 146.956s
OK
```

로그: `/tmp/suite-m1a-registry.log`, 181626 bytes, sha256 `a5449eb0aa83be2ee8e0a9f1d32f17f53a5b44b9034f3aa3ae644bd82ff4e42b`.

## 5. Suite identity·범위·cleanliness

실행 원문:

```bash
BASE=c597b6b788e0c20e8b17508daa014c845884ff9f

manifest_count=$(awk '!/^#/ && NF {n++} END{print n+0}' docs/m1a-suite-manifest.txt)
source_count=$(awk '/^class [A-Za-z0-9_]+\(/ {name=$2; sub(/\(.*/, "", name)} /^    def test_[A-Za-z0-9_]+\(/ {test=$2; sub(/\(.*/, "", test); print name "." test}' scripts/tests/run_tests.py | wc -l | tr -d ' ')
source_unique=$(awk '/^class [A-Za-z0-9_]+\(/ {name=$2; sub(/\(.*/, "", name)} /^    def test_[A-Za-z0-9_]+\(/ {test=$2; sub(/\(.*/, "", test); print name "." test}' scripts/tests/run_tests.py | LC_ALL=C sort -u | wc -l | tr -d ' ')
delta=$(comm -3 \
  <(awk '!/^#/ && NF {print}' docs/m1a-suite-manifest.txt | LC_ALL=C sort) \
  <(awk '/^class [A-Za-z0-9_]+\(/ {name=$2; sub(/\(.*/, "", name)} /^    def test_[A-Za-z0-9_]+\(/ {test=$2; sub(/\(.*/, "", test); print name "." test}' scripts/tests/run_tests.py | LC_ALL=C sort) \
  | wc -l | tr -d ' ')
printf 'manifest_count=%s source_count=%s source_unique=%s symmetric_delta=%s\n' \
  "$manifest_count" "$source_count" "$source_unique" "$delta"

git rev-parse "${BASE}:scripts/tests/run_tests.py"
git rev-parse "HEAD:scripts/tests/run_tests.py"
git hash-object scripts/tests/run_tests.py
git diff --check "$BASE" HEAD
git diff --name-status "$BASE" HEAD
git status --porcelain=v1
```

결과:

```text
manifest_count=838 source_count=838 source_unique=838 symmetric_delta=0
run_tests base blob=73b5472f0cae1c0e19447f00ec9a5dacdcbba769
run_tests HEAD blob=73b5472f0cae1c0e19447f00ec9a5dacdcbba769
run_tests worktree blob=73b5472f0cae1c0e19447f00ec9a5dacdcbba769
range diff check rc=0
changed files:
M scripts/tasks.py
A waystone/project/tasks_cli.py
git status --porcelain=v1: empty
```

각 커밋은 각각 1 insertion/1 deletion, 97 insertions으로 5 MiB보다 충분히 작다.

## 최종 요약

VERDICT: PASS — task registry 구현을 source-identical하게 project package로 이동했고, 49-name thin adapter가 import/runpy/monkeypatch/import-shadow 계약을 보존하며 pinned 838 suite를 통과했다.
COMMITS: `2b2d8ad9284e1614e9704ecc0de4f0171fef8a96`, `e7da20e36953865606a2b6452432c8b149cf2bd5`
HOTFILES: 공유 hot-file 4종 미접촉; 허용된 `scripts/tasks.py`, `waystone/project/tasks_cli.py`만 접촉.
VERIFIED: AST 32/32 source 동일; adapter 49/49; bridge/import-shadow/runpy/front-door byte identity; targeted 32/32; full suite 838/838 rc=0; manifest delta 0; run_tests blob 동일; range diff check rc=0; clean.
NOT-RUN: 금지된 installed/bare `waystone` CLI, `bin/waystone`, push, GPU, release harness, 실제 registry/state mutation 없음.
