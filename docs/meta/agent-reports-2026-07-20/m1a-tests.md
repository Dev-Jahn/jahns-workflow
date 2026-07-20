# M1-A test suite split report

- Branch: `task/m1a-tests`
- Start/base HEAD: `ced172eddc2901948f82d1b73f2b56ecb2bfcdf6`
- Final HEAD: `dc9d3da204b1618781c2f1801aaab6e44044e201`
- Scope: `scripts/tests/**` only

## Result

`scripts/tests/run_tests.py`의 84개 top-level `unittest.TestCase` 클래스와 직접 정의된
838개 `test_*` 메서드를 13개 주제 모듈로 기계 분할했다. 클래스명·메서드명·클래스 원문은
base blob과 source-identical이다. 기존 module-level helper/fixture/상수 43개 노드(함수 27,
named assignment 15, `round._current_date` side-effect assignment 1)는 `support.py`에 각각
정확히 한 번만 존재한다.

`run_tests.py`는 PEP 723 metadata와 기존 CLI 표면을 유지하는 218행 집계 adapter다. 84개
클래스를 명시적으로 import하고 `cls.__module__ = __name__` bridge를 적용하므로 실행 시 모든
클래스가 `__main__`에 노출되고 기존 `Class[.method]` 선택자 및 test identity 출력이 유지된다.
`run_tests`/`__main__` 자체를 import·참조·monkeypatch하는 기존 테스트는 없었다.

## Cluster inventory

| file | classes | direct tests |
|---|---:|---:|
| `test_release.py` | 1 | 18 |
| `test_review_protocol.py` | 8 | 130 |
| `test_project.py` | 9 | 60 |
| `test_review_settlement.py` | 6 | 83 |
| `test_tasks.py` | 7 | 57 |
| `test_improve.py` | 16 | 108 |
| `test_delegate_core.py` | 5 | 110 |
| `test_delegate_lifecycle.py` | 4 | 38 |
| `test_delegate_cli.py` | 8 | 39 |
| `test_overlay.py` | 5 | 39 |
| `test_delegate_verify.py` | 4 | 39 |
| `test_migrations.py` | 5 | 29 |
| `test_policy.py` | 6 | 88 |
| **total** | **84** | **838** |

교차 클래스 참조 3개는 같은 파일에 배치했다:

- `RoundExposureTests` -> `PacketPublicationTests.NARRATIVE`
- `ImproveL2BAdversarialTests` -> `ImproveL2BTests._project`
- `ContractInjectTests` -> `DelegateVerifyTests._PROFILE`

## Acceptance evidence

### 1. Base AST source identity + exactly-once, manifest, adapter namespace

실행 원문:

```bash
uv run python - <<'PY'
import ast
import runpy
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path

BASE = 'ced172eddc2901948f82d1b73f2b56ecb2bfcdf6'
base = subprocess.run(
    ['git', 'show', f'{BASE}:scripts/tests/run_tests.py'],
    check=True, capture_output=True, text=True,
).stdout
base_tree = ast.parse(base)
current_paths = sorted(Path('scripts/tests').glob('*.py'))
current = []
for path in current_paths:
    text = path.read_text()
    current.append((path, text, ast.parse(text)))

base_classes = {
    node.name: ast.get_source_segment(base, node)
    for node in base_tree.body if isinstance(node, ast.ClassDef)
}
class_occurrences = {}
for path, text, tree in current:
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_occurrences.setdefault(node.name, []).append(
                (path, ast.get_source_segment(text, node)))
assert base_classes.keys() == class_occurrences.keys()
for name, segment in base_classes.items():
    found = class_occurrences[name]
    assert len(found) == 1 and found[0][1] == segment, (name, found)

support_node_types = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Assign, ast.AnnAssign)
base_support = [
    ast.get_source_segment(base, node)
    for node in base_tree.body if isinstance(node, support_node_types)
]
current_segments = {}
for path, text, tree in current:
    for node in tree.body:
        if isinstance(node, support_node_types):
            current_segments.setdefault(ast.get_source_segment(text, node), []).append(path)
for segment in base_support:
    found = current_segments.get(segment, [])
    assert found == [Path('scripts/tests/support.py')], (segment.splitlines()[0], found)

suite_paths = [Path('scripts/tests/run_tests.py'), *sorted(Path('scripts/tests').glob('test_*.py'))]
ids = []
for path in suite_paths:
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            ids.extend(
                f'{node.name}.{child.name}'
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name.startswith('test_')
            )
manifest = [
    line for line in Path('docs/m1a-suite-manifest.txt').read_text().splitlines()
    if line and not line.startswith('#')
]
counts = Counter(ids)
missing = sorted(set(manifest) - set(ids))
extra = sorted(set(ids) - set(manifest))
duplicates = sorted(name for name, count in counts.items() if count != 1)
assert len(ids) == len(counts) == len(manifest) == 838
assert not missing and not extra and not duplicates

sys.path.insert(0, str(Path('scripts/tests').resolve()))
namespace = runpy.run_path('scripts/tests/run_tests.py', run_name='__suite_contract__')
classes = namespace['_TEST_CLASSES']
assert len(classes) == len(set(classes)) == 84
assert all(issubclass(cls, unittest.TestCase) for cls in classes)
assert all(namespace[cls.__name__] is cls for cls in classes)
assert all(cls.__module__ == '__suite_contract__' for cls in classes)

print(f'files={len(current_paths)}')
print(f'classes={len(base_classes)} source-identical=true exactly-once=true')
print(f'support_nodes={len(base_support)} source-identical=true exactly-once=true')
print('manifest expected=838 actual=838 missing=0 extra=0 duplicates=0')
print('adapter exposed=84 namespace_rebound=84')
PY
```

결과: rc=0.

```text
files=15
classes=84 source-identical=true exactly-once=true
support_nodes=43 source-identical=true exactly-once=true
manifest expected=838 actual=838 missing=0 extra=0 duplicates=0
adapter exposed=84 namespace_rebound=84
```

검증 중 최초 `runpy.run_path()` probe는 CLI와 달리 `scripts/tests`를 `sys.path`에 넣지 않아
`ModuleNotFoundError: No module named 'test_delegate_cli'`로 rc=1이었다. 이는 suite/adapter 실행
실패가 아니라 probe 환경 차이였다. 실제 CLI는 앞선 두 full run 모두 정상 import했다. 위 성공
원문처럼 CLI와 동일한 sibling import path를 probe에 명시한 뒤 전 항목 rc=0을 확인했다.

### 2. Selector contract: before/after

기준선과 최종 상태에서 동일한 명령을 실행했다.

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py TaskCliTests
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py DelegatePacketTests.test_rendered_worker_prompt_pins_i10_contract_and_known_debt
```

| selector | base | final |
|---|---|---|
| `TaskCliTests` | rc=0, Ran 21, OK, `__main__` | rc=0, Ran 21, OK, `__main__` |
| I-10 representative method | rc=0, Ran 1, OK, `__main__` | rc=0, Ran 1, OK, `__main__` |

로그: `/tmp/m1a-baseline-taskcli.log`, `/tmp/m1a-baseline-delegatepacket.log`,
`/tmp/m1a-final-taskcli.log`, `/tmp/m1a-final-i10.log`.

### 3. Full suite 838 green twice

첫 실행 원문:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1a-tests.log 2>&1
suite_rc=$?
echo "suite rc=$suite_rc"
exit "$suite_rc"
```

결과: rc=0, `Ran 838 tests in 134.054s`, `OK`; test output 행 838.

두 번째 실행 원문(커밋된 최종 HEAD):

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1a-tests-2.log 2>&1
suite_rc=$?
echo "suite rc=$suite_rc"
exit "$suite_rc"
```

결과: rc=0, `Ran 838 tests in 132.299s`, `OK`; test output 행 838.

### 4. Diff, scope, clean

실행 원문:

```bash
git diff ced172eddc2901948f82d1b73f2b56ecb2bfcdf6..HEAD --check
git diff --name-only ced172eddc2901948f82d1b73f2b56ecb2bfcdf6..HEAD
git status --short --branch
```

- `git diff --check`: rc=0.
- changed path 15개 모두 `scripts/tests/**`.
- final status: `## task/m1a-tests`만 출력; tracked/untracked 변경 없음.
- `scripts/common.py`, `scripts/tasks.py`, `scripts/delegate.py`, `waystone/**`, 문서/registry/review
  파일은 수정하지 않았다.

## Commits

1. `a1b1cf5c810bfa0f7d029aca80801779d5cafaf9` — core test clusters `[m1a-move]`
2. `8434b5b2f3751cfb0525f2c104aede25f19788de` — improve/delegate clusters `[m1a-move]`
3. `48dad0aef541d0fe6039883586598335e14c7fc1` — verification/policy clusters `[m1a-move]`
4. `dc9d3da204b1618781c2f1801aaab6e44044e201` — aggregate entrypoint `[m1a-adapter]`

VERDICT: PASS — 84 classes / 838 test IDs source-identical 분할, selector 계약 보존, full suite 2회 green
COMMITS: a1b1cf5c810bfa0f7d029aca80801779d5cafaf9 8434b5b2f3751cfb0525f2c104aede25f19788de 48dad0aef541d0fe6039883586598335e14c7fc1 dc9d3da204b1618781c2f1801aaab6e44044e201
HOTFILES: scripts/tests/run_tests.py 전체(:1-218) 집계 adapter; plan/review.py/common.py 미접촉
VERIFIED: AST class 84/support 43 source-identical·각 1회; manifest 838 delta 0; selectors 21/1 rc=0; full 838 rc=0 x2; git diff --check rc=0; clean
NOT-RUN: waystone CLI, GPU, network, push — 금지/불필요; 필수 테스트 생략 없음
