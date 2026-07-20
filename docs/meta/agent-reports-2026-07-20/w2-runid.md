# w0720b — canonical run id grammar unification

VERDICT: PASS — UUIDv7을 유일한 canonical `run_id` 문법으로 고정했고, 구 문법 산출물은 tracked 실사에서 발견되지 않았으며 full suite가 통과했다.
COMMITS: ec617a574accd1afcefac0cd73bf914878106375
HOTFILES: `dev_docs/0.12.0-refactor-plan.md` §3-3 run-id 문단과 §5-2 run-id uniqueness 문단만 접촉; `scripts/review.py`, `scripts/common.py`, `scripts/tests/run_tests.py` 미접촉.
VERIFIED: 아래 명령과 결과 참조 — 문서 계약 대조 0모순, tracked 산출물 실사 결과 없음, full suite rc=0 (833 tests).
NOT-RUN: `waystone` CLI(명시적 금지). 별도 focused runtime test는 코드 변경이 없어 실행하지 않았고, 전체 gate는 실행했다.

## 전제 및 주장 ↔ anchor 대조

| 주장 | anchor | 판정 |
|---|---|---|
| 계획 §3-3의 대상은 `round`/delegation이 아니라 canonical `run id`다 | plan :167-180, :190-193; ADR-0008 :46-49 | 일치 |
| 신규 canonical 문법은 RFC 9562 UUIDv7 lowercase hyphenated string이다 | ADR-0005 :33-39; ADR-0006 :22; ADR-0009 :30-46 | 일치 |
| 구 timestamp-slug-random 문법은 원문 보존 상태로 명시적 supersession된다 | plan :190-197, :498-502 | 일치 |
| deviation 근거는 ambient/label ad hoc 조합 금지와 E-09 durable identity 원칙이다 | ADR-0005 :35-46; `docs/invariants.md` :36 | 일치 |

대조 결과: 모순 0. `git diff --exit-code HEAD^ -- docs/adr/ADR-0006-run-closeout-manifest.md docs/adr/ADR-0009-review-artifact-addressing.md docs/invariants.md scripts` → rc=0.

## 구 문법 산출물 전수 실사

명시적인 `run_id` 주변에서 timestamp-slug-6자 형태를 찾았다.

```bash
git ls-files -z | xargs -0 rg -n --no-heading --pcre2 '(?i)(?:run_id|run-id|run id).{0,120}20[0-9]{6}T[0-9]{6}Z-[a-z0-9][a-z0-9._-]*-[A-Za-z0-9]{6}(?![A-Za-z0-9._-])' -- || true
```

결과: 출력 없음. **계획 문법으로 생성된 tracked `run_id` 실사 결과 없음.**

형태만으로 누락을 막기 위해 identifier 종류와 무관한 broad scan도 수행했다.

```bash
git ls-files -z | xargs -0 rg --pcre2 -n --no-heading '\b[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9._-]*-[A-Za-z0-9]{6}(?![A-Za-z0-9._-])' -- || true
```

결과: 2건.

- `tasks.archive.yaml:268` — `.waystone/delegations/20260716T104742Z-feat-task-status-parked`
- `tasks.archive.yaml:475` — `.waystone/delegations/20260716T141912Z-feat-review-reply-structured-header`

둘 다 인접한 task id(`feat/task-status-parked`, `feat/review-reply-structured-header`) 전체를 붙인 historical delegation path다. 마지막 6글자는 random suffix가 아니라 task-slug의 의미 있는 단어다. `scripts/delegate.py:293-297`의 `_make_did()`도 delegation id를 `<timestamp>-<task-slug>`로 정의하며 random suffix를 생성하지 않는다.

tracked runtime record 존재 여부:

```bash
git ls-files '.waystone/**' '.waystone/*'
```

결과: 출력 없음.

UUIDv7 산출물 교차 확인:

```bash
git ls-files -z | xargs -0 rg -n --no-heading '\b[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b' -- || true
```

결과: 출력 없음.

코드 구현 교차 확인:

```bash
git ls-files -z -- scripts hooks templates | xargs -0 rg -n --no-heading -i 'run[_ -]?id|uuidv?7|RFC[ -]?9562' --
```

결과는 `scripts/delegate.py:3648`의 “실제 host workflow run id는 나중에 join된다”는 주석 1건뿐이고 run-id generator/store는 없다. `_make_fanout_correlation_id()`(:3646-3653)는 timestamp-`fanout`-6hex 형태지만 `carrier.instance_id`용 correlation id이며 실제 run id가 아니고, 해당 형태의 tracked 산출물도 없다. `scripts/common.py:1607`의 UUIDv4는 temporary Git fetch ref suffix다. 따라서 두 canonical run-id 문법 모두 현행 코드에 미구현이며, ADR-0005에 legacy 판독 note를 추가할 조건은 성립하지 않았다.

## 문서 범위 및 gate

원문과 신규 note 존재 확인:

```bash
rg -n -F '**run id 생성 (r3 확정):** canonical id = `<UTC compact timestamp>-<slug>-<6자 random>`.' dev_docs/0.12.0-refactor-plan.md
rg -n -F '**개정 (2026-07-20):** 위 timestamp-slug-random 문법은 ADR-0005의 RFC 9562 UUIDv7 canonical' dev_docs/0.12.0-refactor-plan.md
rg -n -F 'run id uniqueness: 생성 단계 충돌은 §3-3의 random suffix가, 프로젝트 전체 사후 검출은 closeout' dev_docs/0.12.0-refactor-plan.md
rg -n -F '**개정 (2026-07-20):** 위 §3-3의 random suffix 방식은 ADR-0005의 UUIDv7 generator/CSPRNG' dev_docs/0.12.0-refactor-plan.md
rg -n -F '**Deviation note (2026-07-20).** 이 ADR은 권위 원천으로 적은 계획서 §5-2가 참조하는 §3-3의' docs/adr/ADR-0005-fact-authority-matrix.md
git diff --check HEAD^
```

결과: 전부 rc=0. commit diff는 2 files changed, 14 insertions(+), 삭제/원문 변경 없음.

full suite(파이프 없이 rc 직접 캡처):

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"
```

결과: `suite rc=0`; `/tmp/suite.log` — `Ran 833 tests in 140.657s`, `OK`.
