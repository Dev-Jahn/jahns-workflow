<!-- waystone feedback: the body below is the reviewer reply VERBATIM (byte-exact copy via `waystone review ingest`) — do not edit it; a triage skeleton is appended beneath it. -->
round: 2026-07-20-m1a-split
reviewer: codex:gpt-5.6-sol
reviewer-effort: ultra
review-target: 73789f9fd2a8bb829a36169d46137f173df4f52a
reply-metadata-json: {"metadata":{"effort":"ultra","model":"codex:gpt-5.6-sol","request-digest":"sha256:8dede37fa718e9d49c4e613b462c8a95a8115038fbc93cc46e71822ac372e3ea","review-target":"73789f9fd2a8bb829a36169d46137f173df4f52a"},"narrative_digest":"sha256:466877e6975f8baf1b7ec6e042e18711772c0e97cbc6d90e29d912b493e8b1ee","rendered_request_coverage_reason":null,"rendered_request_digest":"sha256:8dede37fa718e9d49c4e613b462c8a95a8115038fbc93cc46e71822ac372e3ea","rendered_request_digest_matches":true}
ingested: 2026-07-20
source: /tmp/review.md
verbatim-bytes: 9601

---

model: codex:gpt-5.6-sol
effort: ultra
review-target: 73789f9fd2a8bb829a36169d46137f173df4f52a
request-digest: sha256:8dede37fa718e9d49c4e613b462c8a95a8115038fbc93cc46e71822ac372e3ea

# External adversarial review — 2026-07-20-m1a-split

## Confirmed findings

### WS-GPT-401 — review target에는 규범상 move/adapter 분리 경계가 없다

- Severity: major

`dev_docs/m1a-split-plan.md:42-47`은 move commit(`git mv` + import 경로 수정)과 adapter commit을 분리하고 각각 `[m1a-move]`, `[m1a-adapter]`로 표기하도록 요구한다. 그러나 review target의 실제 ancestry에는 `b0a9283`, `c597b6b`, `aed8b3c`, `ced172e`, `41e315e` 다섯 squash만 있고, 모두 한 commit에 `[m1a-move][m1a-adapter]`를 동시에 달아 moved owner와 compatibility/aggregate adapter를 함께 변경한다. 따라서 target history 자체에는 adapter가 없는 move-only 상태가 한 번도 없다.

각 보고서가 분리 증거로 인용하는 task-branch SHA도 target history가 아니다. 예를 들어 `m1a-skel.md:3-4`의 `8d3f34e`/`0ad87b3`, `m1a-core.md:3-4`의 `0346839`/`d64bea0`, `m1a-runs.md:23-28`의 `c80febaa`/`0876a809`, `m1a-tests.md:214-220`의 네 SHA 모두 `git merge-base --is-ancestor <sha> 73789f9`가 rc=1이고 `git branch --contains <sha>`가 비어 있었다. 현재 object DB에 우연히 남은 unreferenced commit은 GC되거나 일반 clone에서 빠질 수 있으므로 review target으로부터 재생 가능한 증거가 아니다. 이 때문에 adapter가 move의 관측 차이를 같은 squash 안에서 보상했는지를 commit boundary로 감사할 수 없고, request의 “모든 이동은 move/adapter commit 분리” 주장 및 그 분리에 의존한 diff-0 증명은 성립하지 않는다.

### WS-GPT-402 — parent-only `sys.modules` cleanup이 orphan package graph를 만든다

- Severity: major

세 shim은 package child를 먼저 import한 뒤 기존 parent가 없었다면 root `sys.modules["waystone"]`만 삭제한다(`scripts/common.py:27-32,149-152`; `scripts/tasks.py:12-16,89-92`; `scripts/delegate.py:12-18,46-48`). `waystone.core`, `waystone.project`, `waystone.runs.delegate` 등의 child는 그대로 남는다. 그 다음 bare `import waystone`은 의도대로 `scripts/waystone.py:12-17`을 새 parent로 선택하지만, 이미 cache된 orphan child는 새 parent attribute로 재결속되지 않는다.

Fresh interpreter에서 `scripts`를 `sys.path[0]`에 넣고 `import common; import waystone.core`를 실행하면 import 자체 뒤에도 `waystone.__file__`은 `scripts/waystone.py`, `hasattr(waystone, "core")`는 `False`이며 `waystone.core` 접근은 `AttributeError`였다. `tasks -> waystone.project`, `delegate -> waystone.runs`도 동일하게 재현됐다. 즉 M1-C까지 공존해야 하는 legacy adapter를 먼저 사용한 정상 프로세스에서 새 package API의 표준 dotted import가 즉시 깨진다. `m1a-core.md:542-553`의 oracle은 parent 부재와 이후 `waystone.main/os`만 검사해 orphan child와 parent-child 결속을 전혀 보지 않는다.

### WS-GPT-403 — module namespace monkeypatch가 bridge를 우회해 실제 I/O를 실행한다

- Severity: major

`_CommonShim`, `_TasksShim`, `_DelegateShim`은 module attribute의 `__setattr__`/`__delattr__`만 전달한다(`scripts/common.py:127-146`; `scripts/tasks.py:69-86`; `scripts/delegate.py:26-43`). 표준 `mock.patch.dict(module.__dict__, ...)`, `vars(module)[name] = value`, `exec(..., module.__dict__)`는 이 hook을 호출하지 않는다. 이동 전 함수의 `__globals__`는 legacy module dict였지만, 현재 re-export된 함수의 globals는 owner module dict이므로 shim dict 변경이 실제 실행에 도달하지 않는다.

동일 probe를 pre-split `c6ba063`과 target에서 대조했다. `patch.dict(common.__dict__, git_rc=fake)` 뒤 `common.git_full_sha`는 base에서 fake를 1회 호출해 sentinel SHA를 반환했지만 target에서는 fake 호출 0회이고 실제 HEAD를 읽었다(`waystone/adapters/git.py:22-25`). `tasks.__dict__["_tasks"]` patch는 base에서 fake task를 렌더했지만 target에서는 real task를 렌더했다(`waystone/project/tasks_cli.py:68-81`). `delegate.__dict__["_git"]` patch도 base에서 sentinel을 반환했지만 target에서는 fake 호출 0회로 실제 Git probe를 실행했다(`waystone/runs/delegate.py:224-239`). 이는 introspection 차이가 아니라 기존 test/embedding isolation이 조용히 해제되어 real Git, subprocess, runner 경로를 실행할 수 있는 동작 회귀다. 보고서의 `setattr/delattr` 234/234 검사는 이 동등한 module mutation 표면을 다루지 않는다.

### WS-GPT-404 — aggregate adapter가 기존 `-m`/import/runpy 실행 표면을 깨고 검증기는 path 주입으로 우회했다

- Severity: major

Test split 직전 `ced172e`에서는 `python -m scripts.tests.run_tests TaskCliTests.test_render_list_filters`, `import scripts.tests.run_tests`, `runpy.run_path('scripts/tests/run_tests.py', run_name='probe')`가 모두 성공했다. Target에서는 모두 `scripts/tests/run_tests.py:14`의 `from test_delegate_cli import ...`에서 `ModuleNotFoundError`로 끝난다. `run_tests.py:14-123`의 bare sibling imports가 direct-file 실행 때만 Python이 제공하는 `scripts/tests`의 `sys.path[0]`에 의존하기 때문이다.

Acceptance report도 원래 runpy probe가 이 오류로 실패했음을 인정한다(`docs/meta/agent-reports-2026-07-20/m1a-tests.md:152-155`). 그러나 성공시킨 checker는 호출 전에 `scripts/tests`를 `sys.path`에 수동 삽입했다(`:126-132`). 즉 기존 caller contract가 아니라 수정된 환경을 검증했다. Direct `uv run scripts/tests/run_tests.py ...` selector와 838 green은 유지되지만, 기존 module-mode gate/collector와 runpy embedding은 suite를 한 건도 load하지 못한다. 동작 변경 0인 기계 분할에서 aggregate entrypoint의 기존 실행 방식 전체가 사라진 major 회귀다.

### WS-GPT-405 — 시작 suite pin을 사후 재고정해 identity gate가 자기참조로 돌아갔다

- Severity: major

ADR-0014 Amendment 2 §4는 M1-A 시작 commit의 전수 test-ID를 pin하고 이후 비이동 suite 변경을 main 승인 차이 목록에 기록하도록 한다(`docs/adr/ADR-0014-m1a-acceptance-basis.md:141-144`). 최초 집행 commit `f513a4e`도 스스로 “M1-A 시작 시점”의 830 ID pin이라고 기록했고, 규범 계획과 registry는 여전히 830을 시작 denominator로 고정한다(`dev_docs/m1a-split-plan.md:5-6,52-60,75-79`; `tasks.yaml:333-358`).

그 뒤 w5가 suite를 변경한 후 `c6ba063`은 denominator를 838 @ `568eebc`로 통째로 다시 pin했다. Target manifest는 재-pin 이유를 요약하면서도 공식 차이 절은 `approved-diffs: (없음)`이라고 선언한다(`docs/m1a-suite-manifest.txt:2-8`). 최초 manifest와 target을 `comm -3`로 비교하면 old ID `MigrationSunsetTests.test_preserved_profile_mismatching_live_is_refused_without_repair` 1개가 삭제되고, 의미가 반대인 `...is_accepted_without_repair`를 포함한 9개 ID가 추가됐다. 이는 단순 net +8 추가가 아니다.

이후 모든 838/838 checker는 post-change source와 post-change manifest만 서로 비교하므로, 최초 pin 이후의 삭제·oracle 반전이 승인된 차이였는지 검증할 수 없다. 실제 core 보고서도 plan의 830을 단순히 stale로 선언하고 838을 선택한다(`docs/meta/agent-reports-2026-07-20/m1a-core.md:11-14`). Target 안에는 최초 start pin을 폐기하는 별도 ruling이나 ID별 approved-diff 목록이 없으므로, Amendment 2가 막으려던 “같은 patch가 suite denominator를 바꾸고도 green”인 자기참조가 다시 열렸고 M1-A exit의 suite-identity 증거가 성립하지 않는다.

## Open domain questions

1. `waystone/runs/delegate.py:37-44`와 `waystone/project/tasks_cli.py:33-41`이 새 package에서 다시 legacy `scripts/common.py`로 역의존하고, runs가 dynamic sibling scripts import도 유지하는 상태를 M1-C 전까지 허용한다는 authority는 어디에 있는가? `m1a-runs.md:14-21`은 이 deviation을 명시하지만 plan의 target package 경계와 git-helper 정렬 요구를 변경하는 main ruling은 찾지 못했다.
2. M1-A의 시작 commit을 최초 pin `b027d52`/`f513a4e`가 아니라 `568eebc`로 재정의한 별도 authority와 1-delete/9-add ID별 승인 목록이 target 밖에 있다면 제공이 필요하다. 현재 target의 aggregate header만으로는 ADR의 auditable-diff 요건을 대체할 수 없다.

## Residual risks from unavailable GPU / data / environment

- GPU, 외부 dataset, network는 이 diff의 검증에 필요하지 않았다.
- 올바른 contract 환경에서 full suite를 독립 재실행해 `Ran 838 tests in 141.027s`, `OK`, rc=0을 확인했다(`/tmp/suite-rev-m1a-2.log`). 이는 direct-file entrypoint의 green만 증명하며 WS-GPT-402~405의 import/patch/provenance 경로를 반증하지 않는다.
- 첫 진단은 reviewer가 `WAYSTONE_HOME`까지 강제로 고정해 home-injection 계약 테스트 2건이 실패했다. 원인을 ambient override로 확인하고 해당 변수를 unset한 동일 suite를 재실행해 위 838 green을 얻었다. 테스트나 repo 파일은 수정하지 않았다.
- w5 네 수리는 코드·회귀 테스트와 full suite를 대조했으나 별도 major/blocker 회귀를 확인하지 못했다. installed/bare CLI와 release-install harness는 실행하지 않아 배포 설치 상태의 추가 import-order 조합은 잔여 위험이다.


---

<!-- waystone triage: BEGIN -->
## Finding triage (main 판정, 2026-07-20 — finding당 독립 opus verifier 반증 검증, 전 건 동적 재현·전수 추적 수반)

릴리스 하네스 skeleton parser는 JW 전용이라 표 미생성(알려진 skew) — free-form 직접 triage.
종합: **리뷰어 major 5건 전부 minor로 강등, blocker 0, M1-A exit 유지.** 기계적 사실은 5건 모두
정확했으나 severity·귀결이 전 건 과대 — 반증은 fresh-clone 재실행·ID별 출처 전수 추적·소비자
전수 수색 등 실증으로 확정.

### WS-GPT-401 — move/adapter 커밋 분리 부재 (리뷰어 major)
- verdict: **PARTIAL** (사실 참·핵심 귀결 기각) → **minor** / taxonomy: reproducibility(provenance)
- verifier: diff-0 증명은 커밋 경계 무의존 — **fresh clone(task SHA 전무)에서 인접 bird 커밋만으로
  동일 digest 재생 성공**(이동 파일은 task↔squash blob-identical, adapter 추가분은 bird delta로
  감사 가능). squash 원자성은 shim 없는 중간 상태를 배포하지 않는 의도된 성질. 커밋 분리는
  ADR-0014 합격 권위가 아닌 작업 규율. 잔여 = 보고서의 unreferenced SHA pin(위생).
- 조치: `docs/m1a-provenance-hygiene` **done** (plan deviation note + 재실행 처방, dev 965a9ef).
  history 재작성은 기각(깨진 중간 상태를 도로 배포하게 됨).

### WS-GPT-402 — orphan child 캐시로 dotted import 파괴 (리뷰어 major)
- verdict: **PARTIAL** (REAL latent·현 소비자 0·메커니즘 일부 정정) → **minor** / taxonomy: correctness
- verifier: 재현 확정. 단 원인은 adapter 선택이 아니라 orphan 캐시 자체(repo-first 순서에서도
  동일 실패). 현 노출 0 — fromlist 경유(from waystone.X import)는 전 모드 동작, front door는
  _waystone_preloaded=True라 면역, suite green은 우연 아님. **리뷰어 수리안(children 삭제)은
  재-exec fork로 monkeypatch 침묵 miss 회귀를 낳음을 실증** — identity-보존 rebind가 옳은 형태
  (tempdir 검증 완료). M1-B dotted-import 소비자 착지 전 수리 조건.
- 조치: `fix/shim-orphan-child-rebind` 등록 → w6 수리 wave.

### WS-GPT-403 — dict-직접 monkeypatch가 bridge 우회 (리뷰어 major)
- verdict: **PARTIAL** (메커니즘 참·영향 과대) → **minor** known-limitation / taxonomy: verification
- verifier: 재현 확정. 단 **소비자 0**(suite의 module-attr patch ~144건 전부 setattr 표면,
  patch.dict 20건 전부 os.environ) — suite green과 정합. module __dict__는 교체 불가라 dict-수준
  전달은 기술적 불가, wrapper 우회는 re-export identity 파괴로 더 큰 관측 변경. dict-직접 조작은
  비관례 표면으로 "관측 동작" 계약 밖.
- 조치: `docs/shim-supported-patch-surface` 등록(지원 표면 주석) → w6.

### WS-GPT-404 — -m/import/runpy 표면 파괴 + 검증기 path 주입 (리뷰어 major)
- verdict: **PARTIAL** (재현 참·"사용 계약" 기각) → **minor** / taxonomy: correctness(잠재 협소화)
- verifier: 3표면 파괴 재현. 단 **그 표면 소비자 0** — CI·release-to-main.sh·.waystone.yml·README·
  ADR-0014 전부 direct-file 표면(무결)이고 __init__.py도 원래 부재(-m은 설계 표면 아님). 838
  green 인수 증거는 direct 표면 의존이라 "우회 검증" 우려는 부수 probe에 한정. 3행 self-dir
  bootstrap으로 전 표면 복원 tempdir 실증.
- 조치: `fix/run-tests-selfdir-bootstrap` 등록 → w6.

### WS-GPT-405 — manifest 재-pin 자기참조 (리뷰어 major)
- verdict: **PARTIAL** (형식 위반 참·실질 위협 공허) → **minor** / taxonomy: reporting
- verifier: **순변화 10건(−1+9) 전수를 ID별로 추적해 전부 main-인수 finding(WS-GPT-303/304②/
  305/306)·done task·커밋에 결속 — 무감사 변경 0.** oracle 반전은 REAL major 수리(304②)의 직접
  산물. 시작 commit 재정의 정당(분할 커밋 5개 전부 568eebc 이후, 수리-선행은 main 명시 지시가
  git-tracked). §4의 자기참조 금지도 불성립 — 분모 변경 patch(수리 wave)와 exit 판정 대상(분할
  patch, delta 0)이 분리돼 있음. **M1-A exit 재판정 불요.** 잔여 = approved-diffs 절의 "(없음)"
  문언 위반.
- 조치: `docs/m1a-manifest-approved-diffs` **done** (ID별 ledger + ruling 명문화, dev 965a9ef).

### Open questions 처분
1. shim의 legacy 역의존·dynamic sibling import 허용 authority → M1-A는 "이동+호환 shim"이 계약
   이며 consumer 전환·git 헬퍼 정렬은 각 모듈 후속/M1-B 소유(split-plan·runs 보고서에 기록됨).
   plan deviation note가 이번에 이를 명문화(965a9ef). 별도 ruling 불요.
2. 시작 commit 재정의 authority·ID별 목록 → manifest에 명문화 완료(965a9ef, 위 405).

### 종합 처분
- 문서 2건 즉시 집행(done, 965a9ef) · 코드/주석 3건 w6 수리 기체로 위임(등록 완료).
- **blocker 0·major 0 확정 — M1-A exit 유지, M1-B 착수 가능.** w6 마감 후 round close.
<!-- waystone triage: END -->
