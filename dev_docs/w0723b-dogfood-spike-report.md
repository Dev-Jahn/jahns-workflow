VERDICT: NO-GO — S2는 PASS했지만 S1·S3 public run start가 backend/DB 이전의 불투명 action_plan_invalid에서 중단되어 3종 전체 P1을 충족하지 못했다.
COMMITS: none
HOTFILES: none
VERIFIED: 실제 dev CLI dogfood 3종(/tmp 독립 project + 각각의 temp WAYSTONE_HOME), S2 chain/status/hash 검증 PASS, repo HEAD/status 및 실 ~/.waystone stat 전후 동일; suite 249→249(추가 테스트·repo 변경 0, 실행은 NOT-RUN)
NOT-RUN: 전체 regression suite(커밋·repo 변경 없음), S1 backend/context provide/resume, S3 구현 및 test-after(각 시나리오가 public start 경계에서 중단)
DEVIATIONS: 시나리오 전 fixture helper 최초 호출 1회가 checkout import path 누락으로 ModuleNotFoundError였고 UV_CACHE_DIR도 명시하지 못했다. SUT 진입·fixture 출력 전 실패했으며, 이후 전 호출은 UV_CACHE_DIR=/tmp/waystone-uv-cache로 고정했다. 시나리오 결과에는 재시도·우회·제품 수정이 없다.

# spike/013-lifecycle-dogfood

## 사전 등록

결과 관찰 전 기준은 `/tmp/waystone-w0723b-dogfood.4WXlHV/preregistered-criteria.md`에 기록했다. 파일 mtime `1784774201`은 최초 시나리오 로그(S1 start mtime `1784774614`)보다 앞선다.

## 시나리오별 1:1 판정

| 시나리오 | 리뷰 표의 확인할 것 | 판정 | 실제 관찰 |
|---|---|---|---|
| S1 불확실한 architecture exploration | semantic brief와 context request가 실제 판단 품질을 높이는가 | **NO-GO / 미판정** | canonical WorkBrief는 read-only parser에서 정상 해석됐고 hypothesis/question authority, fixed decision, open question을 보존했다. 그러나 최초 `run start ... --stage explore`가 `{"code":"action_plan_invalid","next_actions":[],"ok":false,"recoverable":false}`만 내고 끝났다. `.waystone/state.db`, launch record, `WAYSTONE_RESULT.yaml`이 전부 없으므로 real Codex backend, context-requested, context provide/resume에 도달하지 못했다. 따라서 판단 품질 향상 및 새 WorkBrief/attempt 생성은 관찰되지 않았고 PASS로 승격하지 않는다. |
| S2 confirmed major + accept-risk | task가 생기지 않고 objective-first status가 정상인가 | **PASS** | 실제 public CLI로 ingest → confirmed validation → accept-risk disposition을 기록했다. `tasks.yaml` SHA-256은 전후 `9edd2bb9239ebebd0ae2a1632891ea5c1b16313acba1b248b108a1120b8992e5`로 동일하고 materialize는 실행하지 않았으며 disposition은 `materialized_task_id: null`이다. human status는 `Project Brief: committed`, `Current objective: commitment/parser-stability`를 먼저 표시하고 finding 1건을 마지막 `Audit`에만 표시했다. |
| S3 평범한 국소 bugfix | 가짜 hypothesis나 과도한 evaluation ceremony를 요구하지 않는가 | **FAIL — 과잉 확인** | 심은 결함은 `uv run --no-project test_clamp.py`에서 실제 AssertionError로 재현됐다. owner-request objective의 explore와 promote 시작을 각각 한 번 시도했으나 둘 다 public `action_plan_invalid`로 중단됐다. exact runtime 원인은 envelope가 숨겼지만 두 WorkBrief 자체는 정상 parse됐고 context/profile도 정상 해석됐다. 현재 계약은 explore criterion을 project hypothesis/question으로만 제한(`completion.py:592-600`, `run_group.py:149-155`)하고, owner request를 받아들이는 promote는 candidate, frozen evaluation lineage 및 passed evidence를 요구한다(`run_group.py:327-365`). 따라서 아래 세 과잉 기준은 메커니즘상 모두 확인된다. 실제 fix 실행은 public-start 중단 때문에 미완주다. |

### S1 명령/도달 지점

```console
WAYSTONE_HOME=/tmp/waystone-w0723b-dogfood.4WXlHV/S1/machine \
UV_CACHE_DIR=/tmp/waystone-uv-cache \
PATH=/tmp/waystone-w0723b-dogfood.4WXlHV/S1/bin:$PATH \
uv run <checkout>/scripts/waystone.py run start spike/cache-boundary \
  --work-brief /tmp/waystone-w0723b-dogfood.4WXlHV/S1/work-brief.json \
  --stage explore

{"code":"action_plan_invalid","next_actions":[],"ok":false,"recoverable":false}
```

- real backend wrapper는 `gpt-5.6-luna`, `model_reasoning_effort=low`로 준비했으나 launch되지 않았다.
- no DB, no supervisor launch record, no worker result, no context request.
- P3에 따라 fixture 변경, alternate start, backend 재시도를 하지 않았다.

### S2 명령/증거 요지

```console
waystone review ingest 019f8cdb-27a6-7ef3-a2c5-a9d1ad3af5a2 ...
review ingest: preserved feedback and recorded 1 claim(s)

waystone review validate 019f8cdb-27a6-7881-9aba-8eed127c8dad ...
review validate: recorded 0001.yaml

waystone review disposition 019f8cdb-27a6-7881-9aba-8eed127c8dad ...
review disposition: recorded 0001.yaml
```

기록된 chain:

- claim impact: `major`
- validation validity: `confirmed`
- disposition: `accept-risk`
- objective: `commitment/parser-stability`
- materialized task: `null`
- tasks SHA-256 전/후: 동일

human status의 실제 순서:

```text
Project Brief: committed
Current objective: { ... "fact_id": "commitment/parser-stability" ... }
Active run: null
...
Audit: {"findings": {"total": 1}, ... "tasks": {}}
```

### S3 과잉 기준 3종

| 기준 | 판정 | 근거 |
|---|---|---|
| ① 가짜 hypothesis를 brief에 추가해야 했나 | **예** | 실제 owner-request explore start는 거부됐고, 계약은 explore learning criterion source를 project hypothesis/question + nonbinding으로만 허용한다. throwaway의 기존 unrelated hypothesis에 bugfix를 억지로 결속하지 않는 한 explore를 사용할 수 없다. |
| ② 단순 회귀 확인에 별도 evaluation spec 문서가 필요했나 | **예** | direction-neutral owner request를 supported promote chain으로 보내려면 앞선 candidate와 evaluate lineage가 필요하고, evaluate criterion은 frozen evaluation spec authority만 허용한다. 실제 deterministic `test_clamp.py` 한 건만으로는 public chain을 구성할 수 없다. |
| ③ 방향 무관 변경이 full promotion ceremony를 요구했나 | **예** | owner-request objective는 binding promote에서만 허용되고 public promote assembly는 exact candidate, passed evaluation evidence/lineage, 이후 accepted-risks를 요구한다. promote start도 실제로 즉시 거부됐다. |

S3 파일은 수정하지 않았으며 focused test-after도 실행하지 않았다. 이는 실패한 의도 경로를 수동 수정으로 대체하지 않기 위한 P3 준수다.

## P2 최소 수정 방향 적합성 소견

구현하지 않았다. 이번 S3에는 리뷰가 제시한 세 방향이 모두 적합하다.

1. **owner request의 nonbinding explore objective 허용**: 가짜 project hypothesis를 만들지 않고 정확한 owner 요청을 exploration authority로 보존하므로 직접적인 최소 수정이다.
2. **low-risk maintenance assurance profile**: 새 lifecycle stage 없이 현 stage 안에서 candidate/evaluation/promotion ceremony를 국소·저위험 작업에 맞게 줄이므로 적합하다. 단, low-risk 분류 자체는 명시적이고 감사 가능해야 한다.
3. **deterministic focused check의 최소 evidence 인정**: 이번 `test_clamp.py`처럼 단일 failure mechanism과 회귀 조건이 정확히 대응할 때 별도 evaluation-spec 문서를 요구하지 않아도 충분하다. 실행 명령·exit/result artifact에 대한 결속은 유지해야 한다.

## Findings

1. **DF-HARNESS-01 — public run start refusal가 원인 불투명 (spike blocker)**
   - S1/S3의 세 start 시도가 모두 동일한 detail-less `action_plan_invalid`를 반환했다.
   - WorkBrief parse, project context, profile은 read-only 진단에서 정상이고 state DB/launch artifact는 생기지 않았다.
   - public output만으로 expected authority refusal와 fixture/preflight refusal를 구별할 수 없어 S1 lifecycle dogfood를 막았다.
   - 제품 defect로 확정하지 않고 harness/public-surface finding으로 한정한다.

2. **DF-LIFECYCLE-01 — 국소 owner-request bugfix의 ceremony 과잉 (confirmed mechanism)**
   - 실제 failing focused check가 있음에도 explore authority가 owner request를 받지 못한다.
   - owner request가 허용되는 promote는 candidate/evaluate/evidence lineage를 요구한다.
   - 리뷰의 F5 우려가 S3에서 반복 가능한 계약 제약으로 확인됐다.

3. **DF-UX-01 — canonical JSON 조립 부담 (관찰, 별도 소유)**
   - 동적 digest/fact ref를 맞추기 위해 `/tmp/fixture_tools.py`가 필요했다.
   - lifecycle/authority ceremony 판정과 분리하며, 병행 `feat/workbrief-scaffold`의 소유 문제로만 기록한다.

## 무오염 확인

- 대상 worktree 시작/종료 HEAD: `deb61c3e863d333abdc5b65afce5dc71614f5392`
- 종료 `git status --short --branch`: `## task/w0723b-dogfood-spike` (clean)
- repo 파일 변경/커밋: 없음
- 실 machine root `/Users/jahn/.waystone` stat 전/후 동일:
  - `inode=88995431`, `size=160`, `mtime=1784716850`, `ctime=1784716850`
- 사용한 격리 machine roots:
  - `/tmp/waystone-w0723b-dogfood.4WXlHV/S1/machine`
  - `/tmp/waystone-w0723b-dogfood.4WXlHV/S2/machine`
  - `/tmp/waystone-w0723b-dogfood.4WXlHV/S3/machine`
- 각 machine root에는 해당 `projects.json`과 `registry.lock`만 존재했다.
- `/tmp/waystone-w0723b-dogfood.4WXlHV` 아래 5 MiB 초과 산출물: 없음.

## 로그 경로

Root: `/tmp/waystone-w0723b-dogfood.4WXlHV`

- pre-registration: `preregistered-criteria.md`
- S1: `S1/logs/start.log`
- S2: `S2/logs/ingest.log`, `prepare-validation.log`, `validate.log`, `prepare-disposition.log`, `disposition.log`, `status.log`, `status-human.log`
- S3: `S3/logs/focused-test-before.log`, `explore-start.log`, `promote-start.log`

`script(1)` recorder가 child exit status를 전달하지 않는 환경이므로 보고서는 recorder rc를 scenario rc로 오인하지 않고, 캡처된 public envelope/trace만 판정 근거로 사용했다.
