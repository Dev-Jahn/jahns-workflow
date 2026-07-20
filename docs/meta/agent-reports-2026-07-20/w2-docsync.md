# w2 docs/m0-exit-review-sync report

## 범위

- 시작 HEAD: `8392d5afe440b5073afd0adb7fcde1a958f9a7bc`
- 변경 파일: `dev_docs/0.12.0-refactor-plan.md`, `docs/invariants.md`,
  `docs/porting-ledger.md`, `docs/runtime-state-audit.md`, `docs/traceability-matrix.md`
- 건너뛴 결정 지점: 없음. 여섯 항목 모두 완료 ruling, accepted ADR, dated audit disposition 또는
  M0 exit 판정에 직접 anchor가 있었다.

## 항목별 주장 ↔ authority anchor 대조

| 항목 | 기존 authority/fact anchor | 반영 | 결과 |
|---|---|---|---|
| CDX-8 | `tasks.yaml:127-142`의 완료 ruling 2건; `m0-exit-adjudication.md:25,38`의 stale/doc-sync 판정 | ledger `needs-ruling` 집계 2→0; #473을 effect 미개시 적극 증명(fencing epoch 미진행 + action-id 각인 worktree/ref/process/artifact 부재 관측, 관측 불가 시 `unknown-effect`)으로, #486을 executable content digest 결속(size/mtime 단독 금지)으로 확정; matrix의 질문형 문구도 같은 계약으로 교체 | PASS — 완료 ruling의 직접 축약이며 새 cleanup/identity 기준 없음 |
| CDX-9 | accepted `ADR-0009:20-24,69-91`; `docs/invariants.md` E-09 확정 행; `m0-exit-adjudication.md:26` | 계획 §4 E-09를 확정 행과 정확히 일치시킴; r4 원문은 개정 note에 보존하고 ADR-0009 supersession 명시; invariants 권위 포인터에 충돌 시 확정 문구+해당 accepted ADR 우선 규칙 추가 | PASS — E-09 contract cell exact match 확인 |
| CDX-10 | `ADR-0003:103`의 실제 heading `취소, quiescence, cleanup 안전 계약`; `m0-exit-adjudication.md:27` | matrix 상단과 독립 행의 가짜 `§3-9` anchor를 실제 heading 인용으로 교체 | PASS — stale anchor 0건 |
| CDX-11 | `docs/runtime-state-audit.md`의 `Finding 처분 (main 판정 2026-07-20)` 및 수용 조건; `m0-exit-adjudication.md:28` | 상단 결론을 감사 시점 원결과(2026-07-19, 6건)와 현 처분(2026-07-20, task 2건 + 명시 수용 4건)으로 분리하고 후속 절 링크 추가 | PASS — finding 본문은 미변경 |
| CDX-7 | 계획 §5-1의 `.waystone/profile.yml` 전이 상태와 machine-tier `~/.waystone/projects.json`; `tasks.yaml:103-117`; `m0-exit-adjudication.md:24` | §5-2 표에 canonical mapping(machine-local)과 M3 split 전 profile routing intent(local, split task owner) back-reference 2행 추가 | PASS — 미래 Git path/schema/cache는 결정하지 않음 |
| CDX-2 | `m0-exit-adjudication.md:19`의 I-10/E-04/E-08 잔여 gap 판정 | matrix의 세 gap 행에 `M0 exit에서 공개 인지된 이월(TODO M1)` note 추가 | PASS — note 정확히 3건 |

## 검증 명령과 결과

```bash
git diff --check 8392d5afe440b5073afd0adb7fcde1a958f9a7bc..HEAD
git diff --name-only 8392d5afe440b5073afd0adb7fcde1a958f9a7bc..HEAD | sort
```

- rc=0; 허용된 위 5개 문서만 출력.

```bash
uv run python -c 'from pathlib import Path; p=next(x for x in Path("dev_docs/0.12.0-refactor-plan.md").read_text().splitlines() if x.startswith("| **E-09**")); i=next(x for x in Path("docs/invariants.md").read_text().splitlines() if x.startswith("| E-09 |")); assert p.split("|")[2].strip() == i.split("|")[2].strip(); print("E-09 exact contract match: yes")'
```

- rc=0; `E-09 exact contract match: yes`.

```bash
if rg -n '\| needs-ruling \|' docs/porting-ledger.md docs/traceability-matrix.md; then exit 1; fi
if rg -n -F 'ADR-0003 §3-9' docs/traceability-matrix.md; then exit 1; fi
test "$(rg -o -F 'M0 exit에서 공개 인지된 이월(TODO M1)' docs/traceability-matrix.md | wc -l | tr -d ' ')" = 3
```

- rc=0; 실제 `needs-ruling` cell 0건, stale ADR anchor 0건, 공개 M1 이월 note 3건.

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"
```

- `suite rc=0`; `/tmp/suite.log`: `Ran 833 tests in 139.976s`, `OK`.

## 최종 요약

VERDICT: PASS — 6개 M0 exit doc-sync 지적을 기존 ruling/사실만으로 반영했고 full suite가 통과했다.
COMMITS: b40b9f93a749cf504431466047b4268f7aa48cee, 2efa0c64f65ad969102ed3c43ad51e70841d7601, a32dc5f4958bb74ccc471c671a3291d1603ca3c8, b2cb2102db4a8c7b60c9c08a066dd5e8404dca60, 75c04532e689c1a1425a7c5933dd7f6f4ff72854, e131eeef966ac420fc4d5841a113da4802aef5ca
HOTFILES: `dev_docs/0.12.0-refactor-plan.md` §4 E-09 행+개정 note 및 §5-2 back-reference 2행; `docs/invariants.md` 권위 포인터만; `scripts/review.py`, `scripts/common.py`, `scripts/tests/run_tests.py` 미접촉.
VERIFIED: 누적 `git diff --check` rc=0; E-09 exact-cell 대조 rc=0; 실제 needs-ruling/stale ADR anchor 0/0, 공개 M1 이월 note 3; full suite `suite rc=0` (`Ran 833 tests`, `OK`).
NOT-RUN: `waystone` CLI(금지), push(금지), GPU 검증(GPU 없음).
