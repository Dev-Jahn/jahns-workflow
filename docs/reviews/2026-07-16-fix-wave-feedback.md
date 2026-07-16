<!-- waystone feedback: the body below is the reviewer reply VERBATIM (byte-exact copy via `waystone review ingest`) — do not edit it; a triage skeleton is appended beneath it. -->
round: 2026-07-16-fix-wave
reviewer: chatgpt:gpt-5.6-sol
ingested: 2026-07-17
source: /tmp/review.md

---

model: gpt-5.6-pro
effort: high
review-target: 84ad6a799b38d74d95e490aebcd69fc8c1b8c41e

# 리뷰 결과

**판정: Changes requested**

* Critical: **0**
* Major: **6**

검토 범위는 요청서가 지정한 `c8ec816c..84ad6a7`입니다. 직전 리뷰의 두 Major에 대한 핵심 수정—호출자 파일을 직접 삭제하지 않는 release projection, verifier의 전 hook guard—은 코드상 닫혔습니다. 다만 요청서에 이미 기록된 잔여 Major 5건은 실제로 그 등급이 맞으며, `release-script-hardening`에 Minor로 적힌 checked-out-main 문제는 **Major로 승격**해야 합니다.

## Confirmed findings

### 1. Major — publication gate가 정확한 `HEAD` 경로와 바이트를 증명하지 않는다

**확인 위치:** `scripts/review.py::_committed_unchanged`, `verify_packet_publication`

Gate는 request와 sidecar를 **working tree에서 읽어 파싱**한 뒤, `_committed_unchanged`에서 다음만 확인합니다.

1. `path.resolve()`로 얻은 경로의 `git status`가 비어 있는가
2. 같은 경로 이름의 blob이 `HEAD`에 존재하는가

Working bytes와 `HEAD` blob의 바이트 비교는 하지 않습니다. 더욱이 `resolve()` 때문에 검사 대상이 원래 packet 경로가 아니라 symlink target으로 바뀝니다.

두 가지 독립 우회를 임시 Git 저장소에서 재현했습니다.

**Symlink 우회**

```text
HEAD:
  shared/request.md
  shared/binding.json

working tree:
  docs/reviews/r-request.md -> ../../shared/request.md
  docs/reviews/r-request.binding.json -> ../../shared/binding.json
```

두 `docs/reviews/...` 경로는 untracked이고 `HEAD`에는 존재하지 않았지만, `resolve()` 후 committed `shared/...` 파일을 검사하므로 helper가 성공했습니다. 최종 gate도 working symlink의 내용을 파싱하므로 remote에 packet 경로가 없어도 publication 성공이 가능합니다.

**`skip-worktree` 우회**

```text
HEAD request body: ORIGINAL
working request body: UNPUSHED
git status --porcelain -- <request>: 빈 출력
```

Tracked request와 sidecar에 `skip-worktree`를 설정하고 내용을 바꾸면 `git status`는 깨끗하게 보입니다. `cat-file -e`는 `HEAD`에 어떤 blob이 존재한다는 사실만 확인하므로, parser가 읽은 `UNPUSHED` 바이트가 remote의 `ORIGINAL`과 달라도 gate가 통과할 수 있습니다.

따라서 “미추적·부분 커밋 packet은 통과할 수 없다”는 Claim 3은 성립하지 않습니다. Gate가 성공한 뒤에도 reviewer에게 전달되는 local packet과 pushed packet이 다르거나, pushed packet 경로 자체가 없을 수 있습니다.

**필수 수정**

Working tree를 publication의 증거 소스로 사용하지 않아야 합니다.

* `git ls-tree`로 `HEAD` 안의 정확한 lexical path를 찾습니다.
* request와 sidecar를 `git show HEAD:<path>` 또는 blob API로 직접 읽어 파싱합니다.
* exact path가 regular blob인지 검증하고 symlink mode는 거부합니다.
* sidecar 후보도 filesystem `glob()`이 아니라 `HEAD` tree에서 열거합니다.
* working tree는 진단용으로만 비교하고, gate 판정에는 사용하지 않습니다.

현재 registry의 `fix/publication-gate-bypasses` **Major 판정은 적정**하며, 기존 5건에 `skip-worktree`/`assume-unchanged` 계열을 추가해야 합니다.

---

### 2. Major — `main`이 checkout된 worktree에서 release가 성공하면 index/worktree가 새 `HEAD`와 불일치한다

**확인 위치:** `release-to-main.sh`, `ReleaseToMainTests`

스크립트는 호출 branch를 제한하지 않고 `refs/heads/main`을 `git update-ref`로 직접 이동합니다. 호출자가 현재 `main`에 있거나, 같은 repository의 다른 linked worktree가 `main`을 checkout하고 있으면 그 worktree의 symbolic `HEAD`도 새 release commit으로 이동합니다. 그러나 index와 파일은 이전 main tree 그대로 남습니다.

동일한 `commit-tree` + `update-ref` 흐름으로 재현한 결과입니다.

```text
branch: main
HEAD: 새 release commit으로 이동
README.md bytes: 이전 main 내용
git status --porcelain: M  README.md
git diff --cached: release 변경의 역방향 diff
```

즉 명령은 성공을 보고하지만 worktree에는 release를 되돌리는 staged 변경이 생깁니다. 이후 평범한 `git commit`, branch 전환, 또는 다른 작업이 release를 역전하거나 사용자 변경과 섞을 수 있습니다. 호출자가 `dev`여도 다른 linked worktree가 `main`을 checkout하고 있으면 그 worktree가 같은 상태가 됩니다.

현재 회귀 테스트의 repository factory는 항상 `dev`를 checkout한 상태로 반환하므로 이 경로를 다루지 않습니다. 성공 테스트에서 branch, HEAD, status 불변을 검사하지만 전제 자체가 `dev`입니다.

**필수 수정**

`refs/heads/main`이 어느 worktree에서든 checkout되어 있으면 release 전에 fail-loud 해야 합니다.

* `git worktree list --porcelain`의 `branch refs/heads/main` 항목을 검사합니다.
* 발견 시 해당 worktree 경로를 출력하고 중단합니다.
* 현재 worktree가 `main`인 경우와 다른 linked worktree가 `main`인 경우를 각각 real-repo 테스트로 추가합니다.

Registry는 이 문제를 `chore/release-script-hardening`의 **Minor**로 두고 있지만, 성공 명령이 숨은 staged inverse diff를 만드는 것은 비파괴 계약 및 release provenance에 직접 영향을 주므로 **Major가 적정**합니다.

---

### 3. Major — Codex preflight probe 자체가 implementation patch를 오염시킬 수 있다

**확인 위치:** `scripts/delegate.py::_run_codex_sandbox_probe`, `_run_codex`

Preflight는 결정론적인 파일 쓰기 syscall이 아니라, task worktree에 `workspace-write` 권한을 가진 **별도 Codex agent turn**을 실행합니다. 성공 판정은 reserved probe 파일이 정확한 내용을 가졌는지만 확인하며, `finally`에서 그 파일 하나만 삭제합니다. 다른 tracked/untracked 변경은 검사하거나 되돌리지 않습니다. 그 직후 동일한 worktree에서 실제 implementer가 실행됩니다.

Fake Codex transport가 다음 두 파일을 쓰도록 한 fixture로 재현했습니다.

```text
.waystone-sandbox-write-probe-<id>  # 기대한 파일
UNRELATED_PROBE_EDIT.txt            # 추가 편집
```

Probe 함수는 성공했고 reserved 파일만 삭제했으며 `UNRELATED_PROBE_EDIT.txt`는 남았습니다. 이후 `_snapshot()`은 이 파일을 실제 implementer 결과와 함께 capture하므로 contract상 변경 출처가 “implementation runner”로 잘못 귀속됩니다.

현재 probe 테스트도 reserved probe가 남지 않는지만 확인하고, 다른 편집이 없었는지는 검사하지 않습니다.

**필수 수정**

가장 안전한 방법은 probe를 task worktree가 아닌, 같은 cache/filesystem 조건의 disposable sibling worktree에서 실행한 뒤 폐기하는 것입니다.

동일 worktree를 유지해야 한다면:

1. probe 전 tracked·untracked·ignored manifest를 capture
2. probe 후 reserved path를 제외한 모든 상태를 byte-level 비교
3. 추가 변경이 있으면 fail-loud
4. original state로 복구됐음을 다시 검증한 뒤에만 actual runner 실행

Registry의 `fix/preflight-probe-isolation` **Major 판정은 적정**합니다.

---

### 4. Major — `parked`가 direct execution과 lane gate에서 계속 새어 나온다

**확인 위치:** `scripts/delegate.py::_build_packet`, `scripts/lanes.py::verify`, round skill

`next_actionable()`은 dependency가 모두 `done`인 경우만 task를 반환하므로 자동 선택 경로는 올바릅니다.

하지만 `delegate run <child>`의 실제 entrypoint인 `_build_packet()`은 선택된 child 자신의 상태가 `pending|active`인지 검사할 뿐입니다. Dependency 상태는 packet에 문자열로 기록만 하고, 전부 `done`인지 요구하지 않습니다. 따라서 다음 상태가 실행 가능합니다.

```yaml
- id: feat/parent
  status: parked

- id: feat/child
  status: active
  deps: [feat/parent]
```

`feat/child`는 자동 선택에는 나오지 않지만 explicit `delegate run feat/child`로 실행됩니다. Claim 6의 “의존충족 어디서도 새지 않는다”가 execution boundary에서 깨집니다. `_claim_run`이 packet을 재구성해도 동일한 unsatisfied state를 다시 허용하므로 TOCTOU 재검증으로 보완되지 않습니다.

Lane 쪽도 `done|dropped`만 제외하므로 `parked` lane을 계속 “in-flight”로 검사합니다. Round skill은 lane을 사용했으면 round filter 없이 `waystone lanes verify .`를 실행하라고 지시합니다. 오래전에 parked된 lane의 branch가 삭제되면 무관한 이후 round close가 실패할 수 있습니다.

**필수 수정**

* `_build_packet()`에서 모든 dependency가 존재하고 `status == done`인지 강제합니다.
* prepare와 claim 양쪽이 동일 검사를 거치게 유지합니다.
* 실패 시 unsatisfied dependency ID와 상태를 모두 출력합니다.
* Lane selection에서 `parked`를 제외합니다.
* Round skill은 `waystone lanes verify . --round <round-id>`를 사용해야 합니다.

Registry의 `fix/execution-surface-dep-gating` **Major 판정은 적정**합니다.

---

### 5. Major — `codex-companion` verifier가 profile effort를 조용히 폐기한다

**확인 위치:** `scripts/delegate.py::_resolve_verifier_binding`, `verify_delegation`

Verifier binding은 `effort`를 보존하며, `ultra`만 companion에서 fail-loud로 거부합니다. 따라서 `high`이나 `xhigh` 같은 값은 `codex-companion` binding에서 유효하게 받아들여집니다.

`verify_delegation()`은 effort가 있으면 `runner_kwargs`를 만들지만:

* native Codex CLI에는 `model_reasoning_effort=...`가 전달됩니다.
* Claude CLI에는 `--effort ...`가 전달됩니다.
* companion branch의 argv에는 model만 있고 effort는 전혀 없습니다.

즉 `xhigh` profile이 정상적으로 검증을 통과하면서 실제 companion은 자신의 default effort로 실행됩니다.

생성되는 verify artifact도 backend와 profile fingerprint만 저장하고 실제 effective effort는 기록하지 않습니다. 이후에는 configured effort가 적용됐는지 사후 판별할 수도 없습니다.

**필수 수정**

* Companion이 effort 전달을 공식 지원한다면 raw argv 계약 테스트와 함께 명시적으로 전달합니다.
* 지원하지 않는다면 companion binding에서 `effort is not None`을 fail-loud로 거부합니다.
* Verify artifact에 `requested_effort`와 `effective_effort`를 기록해 silent fallback을 금지합니다.

Registry의 `fix/companion-verifier-effort-forwarding` **Major 판정은 적정**합니다.

---

### 6. Major — feedback reader가 editable Markdown에 저장된 결속 판정값을 권위로 신뢰한다

**확인 위치:** `scripts/review.py::read_feedback_reply_metadata`, `scripts/improve.py::_project_review_rows`

Ingest 시점의 `assess_review_reply()`는 실제 sidecar reviewers와 target을 사용하므로 최초 판정 자체는 타당합니다. 문제는 그 결과인 다음 파생 필드를 feedback Markdown header에 저장한다는 점입니다.

```json
{
  "review_target_matches": true,
  "reviewer_configured": true
}
```

Reader는 model, effort, review-target의 **문법만** 재검사합니다. 이후 `review_target_matches: true`와 `reviewer_configured: true`를 그대로 신뢰합니다. Reader API는 `path`만 받고 root, round binding, sidecar digest를 받지 않으므로 실제 결속을 재검증할 수도 없습니다.

따라서 feedback header를 다음 조건으로 수정하면, 실제 sidecar가 없거나 model/target이 해당 sidecar와 무관해도 `reviewer_configured=True`가 됩니다.

```text
metadata.model: 문법상 유효한 값
metadata.review-target: 문법상 유효한 12+ hex 값
review_target_matches: true
reviewer_configured: true
```

`improve`는 이 reader 결과를 그대로 review projection의 `reviewer`, `review_target_matches`, `reviewer_configured` 사실로 내보냅니다. 이 값이 longitudinal evidence와 향후 adaptive 판단에 들어가므로, mutable projection이 원 evidence보다 높은 권위를 갖게 됩니다.

Round ID를 재사용해 최신 sidecar가 바뀐 경우에도 과거 feedback의 stored `true`가 그대로 유지되어 서로 다른 binding이 한 row에서 결합될 수 있습니다.

**필수 수정**

Feedback에는 raw self-declaration만 저장하고 파생 boolean은 매번 다시 계산해야 합니다.

* Ingest가 소비한 exact sidecar path, sidecar digest, target/base/reviewers tuple을 기록합니다.
* Reader는 그 immutable binding snapshot 또는 digest를 검증한 뒤 `assess_review_reply()`를 다시 실행합니다.
* 검증할 binding이 없으면 `review_target_matches`와 `reviewer_configured`는 반드시 `null`이어야 합니다.
* 또는 immutable local ingest event를 projection authority로 삼고 Markdown header는 표시용으로만 취급합니다.

요청서가 지적한 “improve 저장값 무재검”은 가용성 문제가 아니라 evidence integrity 문제이므로 **Major 판정이 맞습니다**.

## Open domain questions

### Positive manifest의 미래 누락을 어떤 gate가 잡는가

현재 test suite는 **전체 dev tree**에서 먼저 실행되고, 그 뒤 `SHIP_PATHS` projection이 만들어집니다. 미래에 runtime이 새 파일을 도입했지만 manifest 등록을 잊으면 dev 테스트는 그 파일을 사용해 통과하고 main release만 누락될 수 있습니다. 현재 tree의 old/new zero-diff는 한 시점의 증거일 뿐 invariant는 아닙니다. Projected tree를 별도 worktree로 materialize해 install/smoke test하거나, product manifest와 실제 runtime dependency의 완전성을 검사하는 gate가 필요합니다.

### Companion broker cleanup 실패 시 hermeticity를 fail-closed 할 것인가

Verifier는 기존 broker를 정리하려 하지만 cleanup은 best-effort이며 “daemon may remain”을 반환해도 verification을 계속합니다. 기존 broker가 이전 RUN 환경을 보존하고 companion이 이를 재사용한다면 `WAYSTONE_VERIFIER_SESSION=1`의 수명 보장이 깨질 수 있습니다. 실제 companion 재사용 계약을 확인할 수 없는 환경이므로 confirmed finding으로 올리지는 않았지만, hermeticity를 절대 계약으로 둘 경우 pre-cleanup 실패는 verify 중단으로 처리하는 편이 일관됩니다.

## Residual risks and review limitations

* 설치된 Claude Code/Codex host에서의 실제 hook discovery, environment propagation, broker reuse는 이번 검토 환경에서 실행하지 않았습니다. 직접 hook entrypoint의 공용 guard와 record-local uv cache 배선은 코드상 적절합니다.
* 제출된 `600 tests` 전체 suite는 독립 재실행하지 않았습니다. 대신 정확한 target source를 검토하고 publication symlink/`skip-worktree`, checked-out-main `update-ref`, preflight extra-edit를 각각 독립 임시 Git/process fixture로 재현했습니다.
* 이 packet의 binding reviewer는 `chatgpt:gpt-5.6-sol`이지만 본 회신은 실제 모델을 `gpt-5.6-pro`로 선언했습니다. 현재 matcher는 이 둘을 alias로 추정하지 않으므로 ingest에서 `reviewer-not-configured`가 예상됩니다. 이는 현재 bounded matching 계약에 따른 정직한 불일치입니다.


---

## Findings (triage skeleton — verify each before registering)

_No `JW-GPT-NNN` finding blocks parsed — triage the verbatim reply directly._

| # | finding (요지) | verdict | type | evidence / reason | task-id |
|---|---|---|---|---|---|
| 1 | publication 게이트가 working tree를 증거 소스로 사용 — symlink resolve·skip-worktree 우회 재현 | REAL | correctness | 리뷰어 임시 repo 재현 2종 + 코드 대조(_committed_unchanged가 resolve()·cat-file -e만) — 기존 fix/publication-gate-bypasses 확정·보강(HEAD-blob 소스 전환 + skip-worktree 기준 추가) | fix/publication-gate-bypasses (major) |
| 2 | main checkout worktree에서 release 성공 시 역방향 staged diff 잔류 | REAL | correctness | 리뷰어 재현(M README.md + 역방향 cached diff); 테스트 factory가 dev 전제라 미커버 — minor에서 major 단독 task로 승격(리뷰어 권고 수용) | fix/release-checked-out-main (major, 신규) |
| 3 | preflight probe(모델 턴)가 reserved 외 편집을 남겨 patch 출처 오염 | REAL | verification | 리뷰어 fake-transport 재현(UNRELATED_PROBE_EDIT 잔류→snapshot 포착) — 기존 fix/preflight-probe-isolation 확정·sibling-worktree 접근 채택 | fix/preflight-probe-isolation (major) |
| 4 | parked가 delegate run(의존 미검사)·lanes verify(in-flight 취급)에서 누출 | REAL | correctness | 코드 대조(_build_packet 자기 상태만 검사) — 기존 fix/execution-surface-dep-gating 확정 + round skill --round 스코프 기준 추가 | fix/execution-surface-dep-gating (major) |
| 5 | companion verifier가 유효 effort를 침묵 폐기, effective effort 미기록 | REAL | verification | 코드 대조(companion argv에 effort 부재) — 기존 task 확정 + requested/effective effort 기록 기준 추가 | fix/companion-verifier-effort-forwarding (major) |
| 6 | feedback header의 저장 boolean을 reader가 무재검 신뢰 — evidence integrity | REAL | verification | 코드 대조(reader가 문법만 재검) — 기존 fix/reply-header-residuals 확정 + sidecar digest 스냅샷 재검증 기준 추가 | fix/reply-header-residuals (major) |
| 7 | (open) positive manifest의 미래 누락 게이트 부재 | REAL(설계 보강) | architecture | projected-tree materialize 스모크 제안 채택 방향으로 chore notes에 기록 | chore/release-script-hardening |
| 8 | (open) broker pre-cleanup 실패 시 verify 계속 — hermetic 절대 계약과 비일관 | REAL(계약 해석) | architecture | 기존 hermetic ruling의 일관 적용으로 fail-closed 기준 추가 | chore/verifier-guard-residuals-2 |

리뷰어 identity: 회신 자기선언 model gpt-5.6-pro / effort high / review-target 84ad6a79…(full) — binding(chatgpt:gpt-5.6-sol)과의 불일치는 리뷰어가 예고한 honest mismatch; profile reviewer backend를 실측 identity(chatgpt:gpt-5.6-pro)로 갱신함.
