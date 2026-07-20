# w6-shimfix report

## Scope and base

- Start/base HEAD: `965a9ef7a4a1ff530f00e406f606e905ec2b3f52`
- The requested feedback file was absent from this worktree's base. Its WS-GPT-402/403/404
  verbatim findings and appended triage were read from the primary checkout at the same
  repository path, read-only. No external SHA comparison or write was performed.
- No tests were added: the brief reserves regression-test additions for the next manifest
  revision. The exact standalone probes are recorded below instead.

## Task 1 — WS-GPT-402 orphan-child rebind

### RED (before the fix)

Exact command:

```bash
uv run python - <<'PY'
import sys
from pathlib import Path

scripts = Path.cwd() / "scripts"
sys.path.insert(0, str(scripts))
import common
import waystone.core
import waystone

print(f"parent={waystone.__file__}")
print(f"cached_child={sys.modules['waystone.core'].__file__}")
print(f"parent_has_core={hasattr(waystone, 'core')}")
print(waystone.core)
PY
```

Result: rc=1. `parent` was `scripts/waystone.py`, `waystone.core` was cached, but
`parent_has_core=False`; attribute access raised `AttributeError`. This isolates the orphan
cache as the cause rather than adapter selection.

### Repair

In `scripts/waystone.py`, immediately after the adapter's `__path__` assignment, each already
cached one-level `waystone.*` child is attached to the current parent with `setattr`. The cached
module object is reused; no child is deleted or re-executed. The optional duplicate guard in
`waystone/__init__.py` was not added because the required scripts-first adapter surface is fixed.

### GREEN and invariant contracts

Exact final-state command (each case runs in a fresh child interpreter):

```bash
uv run python - <<'PY'
import subprocess
import sys

probe = r'''
import importlib
import sys
from pathlib import Path

shim_name, child_name, attr_name, routed_name = sys.argv[1:]
scripts_dir = (Path.cwd() / "scripts").resolve()
sys.path.insert(0, str(scripts_dir))
shim = importlib.import_module(shim_name)
assert "waystone" not in sys.modules
child_before = sys.modules[child_name]
importlib.import_module(child_name)
parent = importlib.import_module("waystone")
assert Path(parent.__file__).resolve() == scripts_dir / "waystone.py"
assert getattr(parent, attr_name) is child_before
assert sys.modules[child_name] is child_before
assert parent.main is sys.modules["waystone.cli.main"].main
assert parent.os is sys.modules["waystone.cli.main"].os
owners = type(shim)._routes[routed_name]
original = getattr(shim, routed_name)
marker = object()
setattr(shim, routed_name, marker)
assert all(getattr(owner, routed_name) is marker for owner in owners)
setattr(shim, routed_name, original)
assert all(getattr(owner, routed_name) is original for owner in owners)
print(f"GREEN {shim_name}: {attr_name} identity + main/os + {routed_name} bridge")
'''

for case in (
    ("common", "waystone.core", "core", "git_rc"),
    ("tasks", "waystone.project", "project", "_tasks"),
    ("delegate", "waystone.runs", "runs", "_git"),
):
    subprocess.run([sys.executable, "-c", probe, *case], check=True)
PY
```

Result: rc=0 for common/core, tasks/project, and delegate/runs. The scripts adapter remained the
selected parent; child identity, `main`/`os`, and each shim's `setattr` bridge were preserved.

Commit: `12fe51fa8e4f59e52fb286c3d562f62259b03b55`

## Task 2 — WS-GPT-404 self-directory bootstrap

### RED (before the fix)

Exact commands:

```bash
uv run python - <<'PY'
import runpy
runpy.run_path("scripts/tests/run_tests.py", run_name="probe")
PY

uv run python - <<'PY'
import scripts.tests.run_tests
PY

uv run python -m scripts.tests.run_tests TaskCliTests.test_render_list_filters

uv run scripts/tests/run_tests.py TaskCliTests.test_render_list_filters
```

Results: runpy/import/`-m` each returned rc=1 at the first bare sibling import with
`ModuleNotFoundError: No module named 'test_delegate_cli'`. The direct-file control returned rc=0
and ran one test, proving that surface was intact before the repair.

### Repair

At the top of `scripts/tests/run_tests.py`, before all sibling imports, added `sys`, `Path`, and:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
```

### GREEN across all surfaces

Exact commands:

```bash
env -u PYTHONPATH uv run --with pyyaml python -I -c 'import runpy; from pathlib import Path; ns = runpy.run_path(str(Path("scripts/tests/run_tests.py").resolve()), run_name="probe"); assert ns["TaskCliTests"] in ns["_TEST_CLASSES"]; assert ns["TaskCliTests"].__module__ == "probe"'

env -u PYTHONPATH uv run --with pyyaml python -I -c 'import sys; from pathlib import Path; root = Path.cwd().resolve(); testdir = root / "scripts/tests"; sys.path.insert(0, str(root)); assert all(Path(p).resolve() != testdir for p in sys.path if p); import scripts.tests.run_tests as m; assert m.TaskCliTests in m._TEST_CLASSES; assert m.TaskCliTests.__module__ == "scripts.tests.run_tests"'

env -u PYTHONPATH uv run --with pyyaml python -m scripts.tests.run_tests TaskCliTests.test_render_list_filters

env -u PYTHONPATH uv run scripts/tests/run_tests.py TaskCliTests
```

Results: all four commands returned rc=0. The first two begin without caller injection of
`scripts/tests`; the actual `-m` surface ran one test; the direct-file contract ran all 21
`TaskCliTests` green.

Commit: `eaa730605ae5e68c0382ddbd1376339276a40996`

## Task 3 — WS-GPT-403 supported patch surface

Only the `_CommonShim`, `_TasksShim`, and `_DelegateShim` class docstrings changed. They now state
that legacy forwarding supports `setattr`/`delattr` only; direct module `__dict__` mutation such
as `mock.patch.dict` is not forwarded because the dict cannot be replaced with an intercepting
mapping; and that this is a non-conventional surface with no current consumers. `_routes`,
`__setattr__`, `__delattr__`, and all runtime behavior are unchanged.

Exact verification command:

```bash
set -e
uv run python -m py_compile scripts/common.py scripts/tasks.py scripts/delegate.py
uv run python - <<'PY'
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "scripts"))
for name in ("common", "tasks", "delegate"):
    module = importlib.import_module(name)
    doc = type(module).__doc__
    assert "supports only setattr/delattr" in doc
    assert "mock.patch.dict" in doc
    assert "cannot be replaced with an intercepting mapping" in doc
    assert "no current consumers" in doc
    print(f"documented: {name}")
PY
git diff --check
git diff --stat
git diff -- scripts/common.py scripts/tasks.py scripts/delegate.py
```

Result: rc=0; all three installed shim types exposed the limitation text, and manual diff review
showed docstring-only edits.

Commit: `eb364fe7d6090310142d97f354389d4c59aef740`

## Final gates

Full suite exact command:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-w6-shimfix.log 2>&1; echo "suite rc=$?"
```

Result: `suite rc=0`; `/tmp/suite-w6-shimfix.log` records `Ran 838 tests in 136.789s` and `OK`.

Final repository checks:

```bash
git diff --check
git diff --check 965a9ef7a4a1ff530f00e406f606e905ec2b3f52..HEAD
git status --porcelain=v1
```

Result: rc=0 and no status output. The worktree is clean. Base-to-HEAD changes are limited to the
five authorized files (`scripts/waystone.py`, `scripts/tests/run_tests.py`, and the three shim
docstring files), with 33 insertions and 3 deletions.

VERDICT: PASS — WS-GPT-402/403/404 지정 수리 완료, 838/838 green, worktree clean.
COMMITS: 12fe51fa8e4f59e52fb286c3d562f62259b03b55; eaa730605ae5e68c0382ddbd1376339276a40996; eb364fe7d6090310142d97f354389d4c59aef740
HOTFILES: dev_docs/0.12.0-refactor-plan.md 미접촉; scripts/review.py 미접촉; scripts/common.py _CommonShim docstring only; scripts/tests/run_tests.py 상단 self-dir bootstrap; scripts/waystone.py adapter parent-rebind block; scripts/tasks.py·scripts/delegate.py bridge docstring only.
VERIFIED: WS-GPT-402 RED rc=1→fresh-process 3-shim GREEN rc=0; WS-GPT-404 3표면 RED rc=1→4표면 GREEN rc=0; direct TaskCliTests 21/21; full suite `/tmp/suite-w6-shimfix.log` 838/838, rc=0; `git diff --check` rc=0; clean.
NOT-RUN: `waystone` CLI (금지); 신규 회귀 테스트 추가 (manifest 규칙); optional `waystone/__init__.py` duplicate guard.
