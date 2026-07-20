<!-- waystone feedback: the body below is the reviewer reply VERBATIM (byte-exact copy via `waystone review ingest`) — do not edit it; a triage skeleton is appended beneath it. -->
round: 2026-07-20-m1a-review-closeout
reviewer: codex:gpt-5.6-sol
reviewer-effort: ultra
review-target: bc18acf7508fe03dab91248adefb55c817487731
reply-metadata-json: {"metadata":{"effort":"ultra","model":"codex:gpt-5.6-sol","request-digest":"sha256:d93c4539458e7b669e2cebddd722faf029580fdec19cc94aef31a986918bbc4f","review-target":"bc18acf7508fe03dab91248adefb55c817487731"},"narrative_digest":"sha256:ba310aa297bebec5fbd497cf646a1de2ad184964babc65152b9616a4773b2a8a","rendered_request_coverage_reason":null,"rendered_request_digest":"sha256:d93c4539458e7b669e2cebddd722faf029580fdec19cc94aef31a986918bbc4f","rendered_request_digest_matches":true}
ingested: 2026-07-20
source: /tmp/review.md
verbatim-bytes: 5874

---

model: codex:gpt-5.6-sol
effort: ultra
review-target: bc18acf7508fe03dab91248adefb55c817487731
request-digest: sha256:d93c4539458e7b669e2cebddd722faf029580fdec19cc94aef31a986918bbc4f

# External adversarial review — 2026-07-20-m1a-review-closeout

## Confirmed findings

### WS-GPT-501 — orphan rebind가 정상적인 repo-first 경로에서는 실행되지 않는다

- Severity: major

수리는 `scripts/waystone.py:14-23`에만 있다. 그러나 shim은 owner들을 import한 뒤 root parent만
지우고 child cache는 남긴다(`scripts/common.py:27-32,155-157`; tasks/delegate도 동형). 따라서
repo root가 `scripts`보다 먼저 탐색되는 경우 다음 `import waystone`은 rebind가 있는 scripts
adapter가 아니라 빈 `waystone/__init__.py`를 선택한다.

이 경로는 인위적이지 않다. repo cwd에서 `PYTHONPATH="$PWD/scripts"`로 legacy modules를 쓰면
Python의 cwd entry가 `PYTHONPATH`보다 앞선다. `/tmp` fresh clone에서 다음 순서를 실행했다.

```text
import common
import waystone
import waystone.core
print(waystone.core)
```

Pre-split `c6ba063`에서는 `import waystone`이 `scripts/waystone.py`를 선택해 `main`/`os`를
노출했다. Target에서는 `waystone/__init__.py`가 선택되고 `main`/`os`가 모두 없었다. 더구나
`sys.modules["waystone.core"]`에는 기존 child object가 남아 있는데도 parent에는 `core`가
결속되지 않았다. `import waystone.core` 뒤 `waystone.core` 접근은 `AttributeError`, rc=1이었다.

W6 증명은 `scripts`를 강제로 `sys.path[0]`에 넣고 adapter 선택을 assert한다
(`w6-shimfix.md:61-73`). 그래서 이 경로를 검증하지 않는다. 보고서도 real-package guard를 넣지
않았다고 명시한다(`:42-45`). 이는 단순 미커버가 아니라 legacy import 관측면과 표준 dotted
package invariant가 동시에 깨지는 재현 가능한 상태다. M1-A의 동작 변경 0 계약
(`ADR-0014:109-118`; `dev_docs/0.12.0-refactor-plan.md:641-645`)에 이 import-order carve-out을
승인한 근거가 없으므로 M1-C까지 수용한다는 귀결은 성립하지 않는다.

### WS-GPT-502 — WS-GPT-403은 docstring만 바뀌었고 silent real-I/O 회귀는 그대로다

- Severity: major

Target의 변경은 `_CommonShim`, `_TasksShim`, `_DelegateShim` type docstring뿐이다
(`scripts/common.py:127-134`, `scripts/tasks.py:69-76`, `scripts/delegate.py:26-33`;
`w6-shimfix.md:151-187`). Direct module-dict mutation은 여전히 shim dict만 바꾸고 moved
function의 owner globals에는 전달되지 않는다.

`/tmp` fresh clone에서 pre-split `c6ba063`과 target을 같은 probe로 대조했다.

- `patch.dict(common.__dict__, git_rc=fake)` 후 `common.git_full_sha(...)`: pre-split은
  `fake_calls=1`과 sentinel SHA, target은 `fake_calls=0`과 실제 target SHA.
- `patch.dict(tasks.__dict__, _tasks=fake)` 후 `tasks.render_list(...)`: pre-split은 fake task,
  target은 real task, `fake_calls=0`.
- `patch.dict(delegate.__dict__, _git=fake)` 후 `delegate._git_out(...)`: pre-split은 sentinel,
  target은 실제 Git HEAD, `fake_calls=0`.

즉 patch context는 정상 진입한 것처럼 보이지만 실제 Git/subprocess/runner 경로가 실행될 수 있다.
Repo 내부 소비자 0이라는 수색은 retained compatibility module의 외부·embedding 소비자 0을
증명하지 못한다. 또한 제한 문구는 일반 module docstring이 아니라 동적으로 설치된
`type(module).__doc__`에만 있어 정상적인 module 문서에서도 보이지 않는다. 구현상 전달이 어렵다는
사실은 기존 동작을 사후에 비계약으로 바꿀 권위가 아니다. 동작 변경 0 계약에 direct namespace
mutation을 제외한 accepted ruling이 target에 없으므로 원 major의 핵심 귀결은 기각되지 않았다.

## Confirmed dispositions with no additional major/critical finding

- **WS-GPT-401:** task SHA 12개가 모두 없는 `--no-local` fresh clone에서도 target ancestry만으로
  5개 bird를 재생했다. skeleton 21/21, core 84/84, runs 160 declarations와 normalized whole source,
  registry 32/32, tests 84 classes + 43 support nodes가 source-identical/exactly-once였고 보고서 digest도
  일치했다. 커밋 분리 규율 위반은 남지만 원 finding의 “diff-0 재생 불가” 귀결은 반증됐다.
- **WS-GPT-404:** runpy, package import, `-m` selector, direct selector가 fresh process에서 모두
  성공했고 full suite도 838/838 green이었다. self-dir entry의 영구 삽입과 top-level sibling-name
  collision 여지는 있으나 이 target에서 major/critical 실패로 확인되지는 않았다.
- **WS-GPT-405:** `b027d52`와 `568eebc`의 AST test-ID 대조는 정확히 DEL 1/ADD 9였고 공통 ID의
  test body 변경은 0이었다. 각 ID가 `13587b4`(+1), `1028217`(+3), `568eebc`(-1/+5)와 pre-split
  main disposition에 정확히 결속돼 무감사 suite 변경은 확인되지 않았다.

## Open domain questions

없음. 위 두 finding을 허용하는 pre-split compatibility contract 또는 accepted ruling은 target에서
찾지 못했다.

## Residual risks from unavailable GPU / data / environment

- GPU, 외부 dataset, network는 필요하지 않았다.
- Full suite를 독립 재실행해 `Ran 838 tests in 88.195s`, `OK`, rc=0을 확인했다. 로그는
  `/tmp/suite-rev-closeout.log`다. 이 suite는 WS-GPT-501의 repo-first 순서와 WS-GPT-502의
  direct-dict mutation을 커버하지 않으므로 두 finding을 반증하지 않는다.
- 실행 과정에서 원 review worktree의 기존 ignored `.waystone/lock` 진단 내용과 mtime이 실수로
  갱신됐다. tracked status는 clean이고 원래 lock bytes는 알 수 없어 삭제·복구하지 않았다. 이는
  finding의 재현 결과에는 영향을 주지 않지만 read-only 실행 계약 위반으로 명시한다.


---

<!-- waystone triage: BEGIN -->
## Finding triage (main 판정, 2026-07-20 — finding당 독립 opus verifier 반증 검증)

free-form 직접 triage(하네스 skeleton parser JW 전용 skew). 종합: **major 2건 모두 minor 강등,
blocker 0, M1-A exit 유지.** 리뷰어가 이전 처분 3건(401·404·405)을 스스로 재검증해 유지 확인한
점, read-only 계약 위반(ignored lock mtime 갱신) 자진 신고를 함께 기록한다(tracked 무결·워크트리
제거로 종결).

### WS-GPT-501 — repo-first 경로에서 rebind 미실행·legacy 표면 파괴 (리뷰어 major)
- verdict: **PARTIAL** (증상 실재·귀속 오류·수리안 역효과) → **minor** / taxonomy: architecture
- verifier: 재현 확정. 단 ①빈 package shadow는 w6 수리가 아니라 **skeleton(b0a9283)부터** —
  동일 probe로 실증(w6는 scripts-first 전용 수리로 범위 올바름) ②그 조합의 소비자 0(bare
  `import waystone`·main/os 독법 전무, front door는 import-order 무관 실증) — repo 유일의
  PYTHONPATH=scripts 용례는 release smoke가 **오염으로 규정·제거**하는 경로 ③리뷰어 수리안
  (root 재수출)은 cli.main→common→waystone.core **실제 순환 import** 도입(실증) — 기각.
- 조치: `docs/adr-0014-addendum3-shim-boundaries` **done** — Addendum 3 §1 수용 ruling(root
  의도적 공백·submodule import-order 무관성이 지원 계약·legacy 표면은 scripts-first 전용).

### WS-GPT-502 — 403 처분이 docstring뿐, ruling 부재 (리뷰어 major)
- verdict: **NEEDS-RULING** (기술·영향 프레임 기각, governance 핵심 REAL) → **minor** / taxonomy: 계약경계(governance)
- verifier: 실질 위험 기각 재확인(전달 기술 불가·소비자 0·invariant/suite 게이트 무손상·외부
  dict-patch 소비자는 사변). 단 **계약 경계 결정은 accepted ruling으로 남긴다는 프로젝트 실무**
  (모든 Amendment/Addendum 전례 동형)와 "silent 동작 금지" 헌법상, triage+비가시 docstring만으론
  부족 — 타당. metaclass docstring이 help()/module.__doc__에서 비가시인 문서 결함도 실증.
- 조치: 동상 **done** — Addendum 3 §2 ruling(지원 표면=setattr/delattr, dict mutation 계약 외,
  근거 3축 결속) + shim 3종 **모듈 docstring** 가시화. suite 838 rc=0.

### 종합 처분
- 두 건 모두 ADR-0014 Amendment 2 **Addendum 3**으로 폐쇄(main 직접, 전례 동형). **blocker 0·
  major 0 유지 — M1-A exit 불변.** M1-B 착수 장애 없음.
<!-- waystone triage: END -->
