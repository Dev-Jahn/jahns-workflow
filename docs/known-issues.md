# Known issues — 0.11.1 (trust baseline)

이 문서는 **0.11.1을 0.12 리팩터의 source baseline으로 동결하면서**, 그 시점에 남아 있는
미해결 trust major와 그 영향 범위를 정확히 기록한다. 계획서 §6 M0-A의 exit 조건 ⑵에 해당한다.

작성 2026-07-19 · 대상 릴리스 0.11.1 (main a3db9b5)

---

## 요약

미해결 trust major **2건**. 둘 다 **PR-mode 표면에 한정**되며, **merge gate를 우회시키지
않는다**. 이 저장소의 dogfooding은 packet mode로 운영되므로 두 결함은 0.12 개발에 사용하는
하네스 경로를 지나지 않는다.

수정을 시도하지 않고 이월한 이유는 계획서 §6 M0-A에 있다 — 요약하면 round-6에서 각 4회전을
시도해 발산을 확인했고(수정이 원 결함보다 나쁜 위양성을 유입), 두 결함의 근본 원인이 정확히
M1이 제거하려는 구조이기 때문이다.

---

## JW-GPT-014 — 관측한 supersession이 offline 투영에 영속되지 않음

**task:** `fix/merge-observed-demotion-persistence` (blocked)

**증상.** PR의 online 경로(`review status` 제외)가 trusted late-v1 marker에 의한 v2 digest
권위 상실을 관측하고도 demotion sidecar를 남기지 않는다. 이후 offline 투영
(`ingest_round_binding`, `improve._review_binding`)은 로컬 v2 sidecar만 보고 기존 request
generation을 `explicit` exact-generation으로 재주장한다. **online은 unknown, offline은
explicit**으로 갈린다.

**영향 표면.** `waystone round merge --pr N` · `waystone approve --pr N` · `waystone review
freeze --pr N`. 전부 `pr: int`를 필수 인자로 받는 PR-mode 전용 경로다(`scripts/merge.py:90`,
`:130`).

**게이트 영향 없음.** `merge_gate()`는 `cycle_version_skew_reason`을 차단 사유로 계속
소비한다(`scripts/merge.py:60-63`). 즉 supersession이 있는 상태에서 merge는 여전히 실패한다.
잘못된 병합이 통과하는 경로는 확인되지 않았다.

**실제 피해.** 증거 투영의 정직성 — `improve` 리포트나 offline ingest가 이미 무효화된 리뷰
세대를 `explicit`으로 표시할 수 있다. 오해를 유발하지만 게이트를 우회시키지 않는다.

---

## JW-GPT-015 — foreign round의 malformed freeze sidecar가 healthy round ingest를 차단

**task:** `fix/ingest-malformed-foreign-freeze-skip` (blocked)

**증상.** `ingest_round_binding()`이 `{round}-freeze-*.binding*.json`으로 열거하는데, round id
자체가 `-freeze-`를 포함할 수 있어(`R = 2026-07-19-a` vs `F = 2026-07-19-a-freeze-b`) 다른
라운드의 파일이 R의 glob에도 걸린다. 그 파일의 이름이 손상되면 R이 즉시 `corrupt`가 된다 —
foreign-skip 분기에 도달하기 전에 반환하기 때문이다(`scripts/review.py:595-599`). 같은 파일을
`improve`는 다른 규칙으로 F에 격리하므로 두 투영의 결론이 갈린다.

**영향 표면.** freeze sidecar는 **PR mode에서만 생성·판독**된다. `ingest_round_binding()`은
`mode == "packet"`이면 request binding 분기에서 조기 반환하며 freeze glob에 **도달하지
않는다**(`scripts/review.py:579-588`).

**게이트 영향 없음.** 이 결함의 방향은 과잉 차단(위양성)이다 — healthy round를 `corrupt`로
만들어 판정을 막는다. stale 증거를 승격시키는 방향이 아니다.

**실제 피해.** PR mode를 쓰는 프로젝트에서 라운드 id가 prefix 충돌을 일으킬 때, 무관한
라운드의 증거 판독이 중단된다.

---

## 이 저장소(dogfooding)에서의 실측

| 확인 항목 | 결과 |
|---|---|
| `.waystone.yml` review mode | `packet` |
| `docs/reviews/`의 freeze/demotion sidecar 수 | **0** |
| `ingest_round_binding`의 packet 분기 | freeze glob 이전에 조기 반환 |
| 014 경로 진입 조건 | `--pr N` 필수 — 사용 이력 없음 |

따라서 **0.12 개발에 사용하는 하네스(0.11.1 릴리스판)는 두 결함 경로를 지나지 않는다.**

---

## 해소 계획

계획서 §6 **M1-B의 수용 기준에 편입**한다 — 새 transactional store에서 두 결함 **부류**가
재현 불가함을 fixture로 증명한다:

- **014 부류** — 분류 경로가 하나뿐(단일 chokepoint)이라 "관측했으나 기록하지 않음"이 성립 불가
- **015 부류** — ⚠ **정정(2026-07-19, JW-GPT-018)**: 초판은 "신원이 store 키라 다의성이 성립 불가"라고
  적었으나 **사실과 다르다.** 리뷰 증거는 git-tracked 파일로 유지되므로(계획 §2-1) store 키가 신원을
  대체하는 것은 runtime record뿐이다. 이 부류의 해소는 `feat/review-artifact-addressing`(UUID owner
  directory + legacy adapter)에 달려 있으며, 0.12에 넣지 않으면 **legacy PR-mode residual**로 남는다.
  정상 round id 간 prefix 충돌은 crafted filename이 아니므로 확정된 위협모델 안에서도 보호 대상이다

패치 수준의 재시도는 하지 않는다. round-6이 그 접근의 발산을 실측했다(계획서 §6 M0-A).

## 관련 ruling

`decision/trust-threat-model-boundary` (2026-07-19 확정) — 신뢰 기계는 **우발적 손상만**
방어한다. 두 결함의 잔여 변형 중 crafted filename·의도적 로컬 변조를 전제하는 것들은
**명시적 비보호**이며 수용된 잔여로 분류한다.
