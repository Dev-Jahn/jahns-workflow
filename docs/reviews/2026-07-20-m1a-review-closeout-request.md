# Review Request — 2026-07-20-m1a-review-closeout

The reviewer has the repository via git. This is a domain/code review, not a workflow audit —
keep the waystone harness out of scope unless asked.

- Project: waystone
- Branch: dev
- Reviewer: codex:gpt-5.6-sol
- Reviewing: bc18acf7508fe03dab91248adefb55c817487731   (diff against 73789f9fd2a8bb829a36169d46137f173df4f52a)

<!-- Keep the Reviewing field on exactly one line with the literal spacing shown above. -->

## What changed and why

m1a-split packet에 대한 codex ultra 적대 리뷰(major 5)의 처리 라운드다. opus verifier 5기의
반증 검증으로 전 건 minor 강등·blocker 0·M1-A exit 유지를 확정했고, 처분을 전량 집행했다:
manifest를 ID별 approved-diffs ledger + 시작 commit 재정의 ruling을 보유한 self-authorizing
기록으로 정정, split-plan에 squash deviation note, shim orphan-child identity-보존 rebind,
run_tests self-dir bootstrap(4표면 복원), bridge 지원 표면 문서화.

## Read these first

1. `docs/reviews/2026-07-20-m1a-split-feedback.md` — 원 finding 5건 + verifier 반증 triage
2. `docs/m1a-suite-manifest.txt` 헤더+approved-diffs 절 (정정본)
3. `dev_docs/m1a-split-plan.md` 커밋 규율 deviation note
4. `docs/meta/agent-reports-2026-07-20/w6-shimfix.md` — 수리 3건 RED/GREEN 원문
5. `scripts/waystone.py`(rebind 블록)·`scripts/tests/run_tests.py` 상단(bootstrap)

## Claims to attack

1. verifier 반증들이 옳다 — 특히 405의 "무감사 변경 0" ID별 추적과 401의 fresh-clone diff-0
   재생이 실제로 리뷰어 귀결을 기각하기에 충분하다.
2. orphan rebind가 새 회귀를 만들지 않는다 — identity 보존·bridge 무결·import-shadow 계약
   유지(fresh-process 증명들). 커버 안 한 repo-first real-package parent 경로의 수용이 정당하다.
3. self-dir bootstrap이 suite 실행 의미를 바꾸지 않는다(sys.path 선두 삽입의 부작용 없음).
4. manifest 정정이 §4 문언을 이제 충족한다 — ledger 형식·근거 결속이 auditable하다.

## Evidence already produced (mine — inspect, don't trust)

- feedback triage의 verifier 판정 요지(각 반증의 실증 방법 포함) + w6 보고서의 RED/GREEN
  명령 원문(-I 격리 검증 포함). full gate 838 rc=0 (머지 후 main 재실행).

## Known weak spots

- rebind는 adapter-parent 경로만 커버 — real-package parent 선행 + scripts shim 후행 조합은
  미커버 수용(M1-C sunset 전제). 후속 등록 예정 항목으로 PROGRESS Next에 기재.
- 이 라운드 diff는 33+/3−로 작다 — 리뷰 가치는 verifier 반증의 타당성 검토에 있다.

## Domain lens

이 라운드는 코드보다 **판정의 감사**다: 외부 리뷰어의 major 5건을 내부 검증자가 기각/강등한
근거가 실증적으로 충분한지, 그리고 기록 기계(manifest·plan·triage)가 이제 자체 감사 가능한지.

## Response wanted

Start the reply with this block (replace values; key case/order/spacing and a Markdown fence are
optional; extra keys are preserved). Echo the `Reviewing` target, alone or as a 12–40 hex
`base-target` range, and copy the request digest exactly; missing/damaged values stay unknown, and
no model/target means ordinary prose:
```text
model: codex:gpt-5.6-sol
effort: high
review-target: bc18acf7508fe03dab91248adefb55c817487731
request-digest: sha256:d93c4539458e7b669e2cebddd722faf029580fdec19cc94aef31a986918bbc4f
```

Major / critical issues only. For each: a concrete failure mechanism and where you confirmed it.
Separate confirmed findings, open domain questions, and residual risks from unavailable
GPU / data / environment.
