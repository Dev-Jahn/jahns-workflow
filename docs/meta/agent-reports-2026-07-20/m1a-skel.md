# M1-A package skeleton — execution report

VERDICT: PASS — package skeleton과 dispatcher의 순수 기계 이동을 2개 계약 커밋으로 완료했고, pinned manifest 838개 전수가 green이다.
COMMITS: `8d3f34e4cbbe2c615b04d3106b61bdcc165252ea` (`[m1a-move]`), `0ad87b35a3e1127a014a89fb3c44fcfaf7b20278` (`[m1a-adapter]`)
HOTFILES: `dev_docs/0.12.0-refactor-plan.md`, `scripts/review.py`, `scripts/common.py`, `scripts/tests/run_tests.py` 모두 미접촉. 허용 파일 중 `scripts/waystone.py`와 신규 `waystone/**`만 접촉했고 `bin/waystone`은 불변이다.
VERIFIED: move 함수 source block 21/21 동일(rc=0); manifest/source 838/838, delta 0; fixture front-door 전후 stdout/stderr byte-identical(rc=0); full suite `Ran 838 tests ... OK`, `suite rc=0`; `git diff --check` rc=0; 최종 `git status --porcelain=v1` empty.
NOT-RUN: 금지된 `waystone` CLI와 설치 release harness는 실행하지 않았고, 실제 프로젝트 registry/state를 접촉하지 않았다. `bin/waystone`도 실행하지 않았다. push/GPU 작업 없음.

## 변경 내용

- 빈 package stub 8개 신설: `waystone/__init__.py` 및 `cli/core/project/runs/jobs/adapters/features/__init__.py`.
- 원본 `scripts/waystone.py` 전체를 `waystone/cli/main.py`로 이동.
- 이동 파일의 유일한 내용 변경은 새 위치에서 기존 sibling scripts를 계속 찾기 위한 다음 경로 수정이다.

```python
HERE = Path(__file__).resolve().parents[2] / "scripts"
```

- `scripts/waystone.py`는 PEP 723 metadata, package bootstrap, 기존 import 관측면(`main`, moved docstring, `os`) 전달, `main(sys.argv[1:])` 호출만 가진 21-line thin adapter로 재생성했다.
- 기존 suite가 `scripts/`를 `sys.path[0]`에 둔 뒤 `import waystone`을 사용하므로, adapter의 `__path__` 지정은 새 root package와의 이름 충돌을 피하기 위한 필수 import-path 조정이다.
- `bin/waystone`, 테스트, 문서, kernel 파일은 변경하지 않았다.

## 1. Move commit 함수 본문 기계 대조

이동 전 객체(`move commit`의 parent)와 이동 후 객체(`move commit`)에서 모든 top-level 함수의 exact source segment(def/signature/body/comments 포함)를 추출해 대조했다.

실행 명령 원문:

```bash
uv run python - <<'PY'
import ast
import hashlib
import subprocess

move_commit = "8d3f34e4cbbe2c615b04d3106b61bdcc165252ea"
before = subprocess.run(
    ["git", "show", f"{move_commit}^:scripts/waystone.py"],
    check=True,
    capture_output=True,
    text=True,
).stdout
after = subprocess.run(
    ["git", "show", f"{move_commit}:waystone/cli/main.py"],
    check=True,
    capture_output=True,
    text=True,
).stdout

def functions(source: str) -> dict[str, str]:
    tree = ast.parse(source)
    return {
        node.name: ast.get_source_segment(source, node)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

before_functions = functions(before)
after_functions = functions(after)
missing = sorted(before_functions.keys() - after_functions.keys())
added = sorted(after_functions.keys() - before_functions.keys())
changed = sorted(
    name for name in before_functions.keys() & after_functions.keys()
    if before_functions[name] != after_functions[name]
)
digest = hashlib.sha256(
    "\n".join(before_functions[name] for name in sorted(before_functions)).encode()
).hexdigest()
print(f"before_functions={len(before_functions)}")
print(f"after_functions={len(after_functions)}")
print(f"missing={missing}")
print(f"added={added}")
print(f"changed={changed}")
print(f"function_source_sha256={digest}")
raise SystemExit(bool(missing or added or changed))
PY
```

결과(rc=0):

```text
before_functions=21
after_functions=21
missing=[]
added=[]
changed=[]
function_source_sha256=93a7efe564e436dec20e4b409626ac4be4d52765dd02425261d3ad6e232b908e
```

`git show --find-renames` 관측도 rename 99%, 내용 diff는 `HERE` 한 줄의 `1 insertion(+), 1 deletion(-)`뿐이었다.

## 2. Suite identity 정적 대조

실행 명령 원문:

```bash
set -o pipefail
manifest_count=$(awk '!/^#/ && NF {n++} END{print n+0}' docs/m1a-suite-manifest.txt)
source_count=$(awk '/^class [A-Za-z0-9_]+\(/ {name=$2; sub(/\(.*/, "", name)} /^    def test_[A-Za-z0-9_]+\(/ {test=$2; sub(/\(.*/, "", test); print name "." test}' scripts/tests/run_tests.py | wc -l | tr -d ' ')
source_unique=$(awk '/^class [A-Za-z0-9_]+\(/ {name=$2; sub(/\(.*/, "", name)} /^    def test_[A-Za-z0-9_]+\(/ {test=$2; sub(/\(.*/, "", test); print name "." test}' scripts/tests/run_tests.py | LC_ALL=C sort -u | wc -l | tr -d ' ')
delta=$(comm -3 <(awk '!/^#/ && NF {print}' docs/m1a-suite-manifest.txt | LC_ALL=C sort) <(awk '/^class [A-Za-z0-9_]+\(/ {name=$2; sub(/\(.*/, "", name)} /^    def test_[A-Za-z0-9_]+\(/ {test=$2; sub(/\(.*/, "", test); print name "." test}' scripts/tests/run_tests.py | LC_ALL=C sort) | wc -l | tr -d ' ')
printf 'manifest_count=%s source_count=%s source_unique=%s symmetric_delta=%s\n' "$manifest_count" "$source_count" "$source_unique" "$delta"
awk '!/^#/ && NF {print}' docs/m1a-suite-manifest.txt | LC_ALL=C sort -c
printf 'manifest_sort_check_rc=%s\n' "$?"
```

결과(rc=0):

```text
manifest_count=838 source_count=838 source_unique=838 symmetric_delta=0
manifest_sort_check_rc=0
```

## 3. Tempdir fixture front-door 관측 동등성

Fixture root: `/tmp/m1a-skel-smoke.khSTHQ/project`. 실제 project와 machine state 접촉을 막기 위해 `HOME`, `CODEX_HOME`, `WAYSTONE_HOME`을 fixture 하위로 격리했다. Fixture는 `.waystone.yml`, 아래 2-task `tasks.yaml`, `docs/reviews/`만 가진다.

이동 전 base `c6ba0630f83c17109f64c7c5355ead54067d6cd8`에서 실행한 명령 원문:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE HOME=/tmp/m1a-skel-smoke.khSTHQ/home WAYSTONE_HOME=/tmp/m1a-skel-smoke.khSTHQ/home/.waystone uv run python scripts/waystone.py task list /tmp/m1a-skel-smoke.khSTHQ/project > /tmp/m1a-skel-smoke-before.stdout 2> /tmp/m1a-skel-smoke-before.stderr
```

최종 HEAD에서 실행한 명령 원문:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE HOME=/tmp/m1a-skel-smoke.khSTHQ/home CODEX_HOME=/tmp/m1a-skel-smoke.khSTHQ/home/.codex WAYSTONE_HOME=/tmp/m1a-skel-smoke.khSTHQ/home/.waystone uv run python scripts/waystone.py task list /tmp/m1a-skel-smoke.khSTHQ/project > /tmp/m1a-skel-smoke-final.stdout 2> /tmp/m1a-skel-smoke-final.stderr; echo "smoke rc=$?"
```

결과:

```text
smoke rc=0
feat/done  [done]  completed task
feat/active  [active]  active task
```

stderr는 양쪽 모두 empty. 전후 byte 대조 명령과 결과:

```bash
cmp -s /tmp/m1a-skel-smoke-before.stdout /tmp/m1a-skel-smoke-final.stdout
cmp -s /tmp/m1a-skel-smoke-before.stderr /tmp/m1a-skel-smoke-final.stderr
shasum -a 256 /tmp/m1a-skel-smoke-before.stdout /tmp/m1a-skel-smoke-final.stdout /tmp/m1a-skel-smoke-before.stderr /tmp/m1a-skel-smoke-final.stderr
```

```text
stdout cmp rc=0
stderr cmp rc=0
1312db0f6d6b525e451924a9d45583159f0c17c10161f0490a7199ffdb285f5e  before.stdout
1312db0f6d6b525e451924a9d45583159f0c17c10161f0490a7199ffdb285f5e  final.stdout
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  before.stderr
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  final.stderr
```

## 4. Adapter 표적 검증

기존 import shadow 경계와 공개 관측면을 직접 포함하는 표적 테스트:

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py WaystoneStorageCliTests StatuslineTests M2DocsTests.test_readme_and_front_door_name_all_new_surfaces > /tmp/m1a-skel-targeted-corrected.log 2>&1
```

결과(rc=0): `Ran 15 tests in 0.053s`, `OK`.

진단 중 최초 명령은 존재하지 않는 selector `ContractSurfaceTests`를 지정해 rc=1이었다. 로그는 14개 실제 테스트 green 뒤 `AttributeError: module '__main__' has no attribute 'ContractSurfaceTests'`를 보였다. 제품 실패가 아니라 selector 이름 오기였고, 실제 소유 class `M2DocsTests`의 정확한 method selector로 위 명령을 재실행해 15/15 green을 확인했다. 테스트 파일은 수정하지 않았다.

또한 fixture cwd에서 absolute script로 `uv run python ... statusline`을 시도한 사전 진단은 rc=1 (`ModuleNotFoundError: yaml`)이었다. 원인은 `uv run python`이 외부 cwd에서 script의 PEP 723 dependency block을 선택하지 않는 환경 해석이었다. acceptance는 worktree cwd에서 브리프가 지정한 정확한 `uv run python scripts/waystone.py` 형태와 fixture root 인자를 쓰는 위 `task list` smoke로 수행했고 rc=0 및 전후 byte identity를 확인했다. dependency fallback이나 코드 변경은 하지 않았다.

## 5. Pinned full suite

실행 명령 원문(파이프 없이 rc 직접 캡처, 지정 고유 로그):

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1a-skel.log 2>&1; echo "suite rc=$?"
```

결과:

```text
suite rc=0
Ran 838 tests in 147.590s
OK
```

`scripts/tests/run_tests.py`는 base 대비 byte diff 0이다:

```bash
git diff --quiet c6ba0630f83c17109f64c7c5355ead54067d6cd8 HEAD -- scripts/tests/run_tests.py
```

결과: rc=0.

## 6. 범위·whitespace·cleanliness

```bash
git diff --quiet c6ba0630f83c17109f64c7c5355ead54067d6cd8 HEAD -- bin/waystone
git diff --check
git status --porcelain=v1
find waystone -name __init__.py -type f -exec wc -c {} +
```

결과:

- `bin/waystone` diff check rc=0.
- `git diff --check` rc=0.
- `git status --porcelain=v1` 출력 없음(final worktree clean).
- 8개 `__init__.py` 모두 0 bytes, total 0.
- 커밋 diff는 move commit 1 insertion/1 deletion + empty stubs, adapter commit 21 insertions뿐이며 5 MiB 제한보다 충분히 작다.

## 최종 요약

VERDICT: PASS — 순수 기계 package skeleton/dispatcher split 완료, 동작·저장 형식 변경 증거 없음, pinned 838 suite green.
COMMITS: `8d3f34e4cbbe2c615b04d3106b61bdcc165252ea`, `0ad87b35a3e1127a014a89fb3c44fcfaf7b20278`
HOTFILES: 공유 hot-file 4종 미접촉; `scripts/waystone.py` 허용 범위만 adapter로 접촉; `bin/waystone` 불변.
VERIFIED: 함수 source 21/21 동일; manifest 838 delta 0; temp fixture smoke rc=0 및 전후 byte-identical; full suite 838/838 rc=0; diff check rc=0; clean.
NOT-RUN: 금지된 `waystone` CLI/installed release harness/실제 registry, `bin/waystone`, push, GPU.
