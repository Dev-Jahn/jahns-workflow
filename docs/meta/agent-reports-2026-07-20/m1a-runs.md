# M1-A runs move report

Base HEAD: `c597b6b788e0c20e8b17508daa014c845884ff9f`

## Outcome

- Moved the complete 3,916-line `scripts/delegate.py` runtime to
  `waystone/runs/delegate.py`.
- Changed only the import bootstrap path and five repository resource roots in the moved source.
- Recreated `scripts/delegate.py` as a 53-line compatibility adapter.
- Preserved all 234 legacy runtime bindings by identity and forwarded adapter `setattr`/`delattr`
  operations to the moved owner module, including private monkeypatch surfaces such as
  `_render_prompt`, `_git`, `_run_codex`, `hold_lock`, and `worktrees_cache_dir`.
- Kept `from common import (...)` through the existing shim because it is the smallest valid import
  change and preserves body-source identity. The moved module also still performs three dynamic
  sibling imports from `scripts/`, so its bootstrap deliberately points there.
- Did not move the optional git helpers. Delegate `_git` has env-overlay, per-call timeout, and
  `surrogateescape` behavior that differs from `waystone.adapters.git.git_rc`; `_git_out` and
  `_git_path` also depend on the monkeypatchable delegate-owner `_git` global. Extracting them would
  require body changes and a second owner bridge, so it does not meet the brief's clean
  body-diff-zero condition.

## Commits

1. `c80febaa11a99e06e90f982f40f636b37d8b5d03`
   `[m1a-move] Move delegate runtime into runs package`
2. `0876a8099a9cc6355e702f7da9079a14ece246df`
   `[m1a-adapter] Preserve legacy delegate module surface`

Both changed artifacts are below 5 MiB: adapter 1,537 bytes; moved owner 186,980 bytes.

## Acceptance evidence

### 1. I-10 characterization

Executed before the move and immediately after the adapter was created:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py DelegatePacketTests.test_rendered_worker_prompt_pins_i10_contract_and_known_debt
```

Both invocations: rc=0, `Ran 1 test`, `OK`.

Final focused gate:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py DelegatePacketTests.test_rendered_worker_prompt_pins_i10_contract_and_known_debt DelegateRunTests.test_cli_prepares_slow_inputs_before_claim_lock_and_revalidates_inside DelegateStatusJsonTests.test_status_json_claim_only_record_is_claimed_not_corrupt DelegateCliTests.test_waystone_dispatcher_routes_delegate
```

Result: rc=0, `Ran 4 tests`, `OK`.

The delegate prompt template remained byte-identical at
`f5f43018a3b64db121529bf3f1a91439bdd888aa583575efbbebb424e50bbcd4`.

### 2. AST declaration and whole-source comparison

The executed checker compared the start-HEAD blob to the moved owner:

```bash
uv run python - <<'PY'
import ast
import collections
import subprocess
from pathlib import Path

base = 'c597b6b788e0c20e8b17508daa014c845884ff9f'
old = subprocess.check_output(['git', 'show', f'{base}:scripts/delegate.py'], text=True)
new = Path('waystone/runs/delegate.py').read_text(encoding='utf-8')

def declarations(source):
    tree = ast.parse(source)
    return collections.Counter(
        (type(node).__name__, node.name, ast.get_source_segment(source, node))
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )

assert declarations(old) == declarations(new)
assert len(declarations(old)) == 160
assert all(count == 1 for count in declarations(old).values())
normalized = new.replace(
    'sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))',
    'sys.path.insert(0, str(Path(__file__).resolve().parent))',
).replace('.resolve().parents[2] / "templates"',
          '.resolve().parent.parent / "templates"')
assert normalized == old
print('declarations=160 source-identical=160 duplicates=0')
print('whole-source delta=only import bootstrap + 5 resource roots')
PY
```

Result: rc=0; all 160 function/class declarations occurred exactly once with identical source, and
normalizing the six permitted path expressions made the full moved source byte-identical to base.

### 3. Adapter name completeness and monkeypatch bridge

Executed checker:

```bash
uv run python - <<'PY'
import subprocess
import symtable
import sys
from pathlib import Path

base = 'c597b6b788e0c20e8b17508daa014c845884ff9f'
old = subprocess.check_output(['git', 'show', f'{base}:scripts/delegate.py'], text=True)
table = symtable.symtable(old, 'delegate.py', 'exec')
expected = {
    symbol.get_name()
    for symbol in table.get_symbols()
    if symbol.is_imported() or symbol.is_assigned() or symbol.is_namespace()
}
sys.path.insert(0, str(Path('scripts').resolve()))
import delegate as adapter
owner = sys.modules['waystone.runs.delegate']
actual = {name for name in vars(adapter) if not name.startswith('__')}
owner_names = {name for name in vars(owner) if not name.startswith('__')}
assert expected == actual == owner_names
assert len(expected) == 234
assert all(vars(adapter)[name] is vars(owner)[name] for name in expected)
for name in sorted(expected):
    original = getattr(adapter, name)
    marker = object()
    setattr(adapter, name, marker)
    assert getattr(owner, name) is marker, name
    setattr(adapter, name, original)
original = adapter._render_prompt
del adapter._render_prompt
assert not hasattr(owner, '_render_prompt')
adapter._render_prompt = original
assert owner._render_prompt is original
print('adapter names=234 missing=0 extra=0 wrong-owner=0')
print('assignment bridge=234/234; delete/restore bridge=ok')
PY
```

Result: rc=0; exact 234-name set, 234/234 identity mappings, assignment forwarding for every name,
and delete/restore forwarding for `_render_prompt`.

One preliminary checker used raw `symtable.get_identifiers()` and incorrectly treated referenced-only
`__file__`, `__name__`, `str`, and `tuple` as runtime module bindings. That checker failed on those
four names. The corrected checker above selects import/assignment/namespace bindings and agrees
exactly with both the base runtime module and moved owner (234 names); no production change or
acceptance relaxation was made.

The runpy load path was also checked without invoking the CLI:

```bash
uv run python - <<'PY'
import runpy
ns = runpy.run_path('scripts/delegate.py', run_name='__waystone_dispatch__')
assert callable(ns['main'])
assert ns['_render_prompt'].__module__ == 'waystone.runs.delegate'
print('runpy adapter load=ok')
PY
```

Result: rc=0.

### 4. Front-door status byte comparison

The legacy import surface was called directly in an isolated temp fixture; no `waystone` CLI,
delegation execution, or external runner was invoked. The exact harness was executed before and
after the move:

```bash
uv run python - <<'PY'
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path('scripts').resolve()))
import delegate

with tempfile.TemporaryDirectory() as d:
    base = Path(d)
    root = base / 'repo'
    home = base / 'home'
    rec = root / '.waystone' / 'delegations' / '20260720T000000Z-feat-smoke'
    rec.mkdir(parents=True)
    home.mkdir()
    (root / '.waystone.yml').write_text('version: 1\nproject: smoke\n', encoding='utf-8')
    (rec / 'claim.json').write_text(json.dumps({
        'schema': 'waystone-delegation-claim-1', 'task_id': 'feat/smoke',
    }) + '\n', encoding='utf-8')
    (rec / 'exposure.json').write_text(json.dumps({
        'task_id': 'feat/smoke', 'base': {'snapshot_sha': 'a' * 40},
    }) + '\n', encoding='utf-8')
    (rec / 'status.json').write_text(json.dumps({
        'state': 'needs-review',
        'at_transitions': [{'at': '2026-07-20T00:00:00+00:00'}],
    }) + '\n', encoding='utf-8')
    before = {name: os.environ.get(name)
              for name in ('HOME', 'CODEX_HOME', 'WAYSTONE_HOME')}
    os.environ['HOME'] = str(home)
    os.environ['CODEX_HOME'] = str(home / '.codex')
    os.environ['WAYSTONE_HOME'] = str(home / '.waystone')
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = delegate.main(['status', '--root', str(root)])
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    stdout = out.getvalue().encode()
    stderr = err.getvalue().encode()
    digest = hashlib.sha256(stdout + b'\0' + stderr).hexdigest()
    print(rc, digest, stdout.hex(), stderr.hex())
PY
```

Pre/post results were byte-identical:

- rc: 0
- stdout: `20260720T000000Z-feat-smoke  feat/smoke  [needs-review]  aaaaaaa  2026-07-20T00:00:00+00:00\n`
- stderr: empty
- `sha256(stdout + NUL + stderr)`:
  `797f89d692d7b9ee78dcb703482af1b19f0b4e51ddbee19f65a235d0d352242d`

### 5. Suite identity and full gate

AST IDs were compared to the authoritative manifest: 838 unique IDs and exact sorted equality.

The test runner remained byte-identical to base:

```bash
git diff --exit-code c597b6b788e0c20e8b17508daa014c845884ff9f -- scripts/tests/run_tests.py
shasum -a 256 scripts/tests/run_tests.py
```

Result: rc=0; SHA-256
`0bdec284739fd8c0bbebb4a156b13d1efc28d0de57430074a8b56b34cb016b34`.

Required full gate:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1a-runs.log 2>&1
```

Result: rc=0; `Ran 838 tests in 143.989s`; `OK`. `rg -c '^test_'` returned 838. Log
SHA-256: `8376a0a65da279131d92abdec183dbf87dc06397701855be4be705a6d3e753bf`.

### 6. Final repository checks

```bash
git diff --check c597b6b788e0c20e8b17508daa014c845884ff9f..HEAD
git diff --name-status c597b6b788e0c20e8b17508daa014c845884ff9f..HEAD
git status --short --branch
```

Results:

- `git diff --check`: rc=0
- Base-to-HEAD paths: only `M scripts/delegate.py` and `A waystone/runs/delegate.py`
- Final status: clean (`## task/m1a-runs`)
- `waystone/adapters/git.py`, `scripts/common.py`, `scripts/review.py`,
  `scripts/tests/run_tests.py`, sibling scripts/tests/bin/project/core, plan, registry, roadmap,
  progress, and review archives were not modified.

## Final summary

VERDICT: PASS — delegate runtime moved with body semantics unchanged; adapter, byte oracle, and 838-test gate all pass.
COMMITS: c80febaa11a99e06e90f982f40f636b37d8b5d03 0876a8099a9cc6355e702f7da9079a14ece246df
HOTFILES: dev_docs/0.12.0-refactor-plan.md untouched; scripts/review.py untouched; scripts/common.py untouched; scripts/tests/run_tests.py untouched and byte-identical.
VERIFIED: I-10 rc=0; focused 4/4 rc=0; AST 160/160 exact; adapter 234/234 exact; front-door pre/post SHA-256 equal; full suite rc=0, 838/838; git diff --check rc=0; clean.
NOT-RUN: waystone CLI; real delegation/external runner; optional git-helper extraction (not cleanly body-diff-zero).
