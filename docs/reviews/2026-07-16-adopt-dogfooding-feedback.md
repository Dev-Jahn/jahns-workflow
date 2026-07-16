<!-- waystone feedback: the body below is the reviewer reply VERBATIM (byte-exact copy via `waystone review ingest`) — do not edit it; a triage skeleton is appended beneath it. -->
round: 2026-07-16-adopt-dogfooding
reviewer: chatgpt:gpt-5.6-sol
reviewer-note: effort pro — ingest 시점에는 profile의 낡은 binding(chatgpt:gpt-5.5-pro)이 기록되어 사용자가 정정 (2026-07-16). 근본 해결은 feat/reviewer-self-declared-identity.
ingested: 2026-07-16
source: /tmp/review.md

---

# 리뷰 결과

검토 대상은 `waystone/dev`, 권장 범위 `925acd5..2035801`로 잡았습니다. 요청서가 지정한 boundary hook, verifier 격리, dogfooding release isolation, SSOT 적합성을 중심으로 확인했습니다.

**판정: Changes requested**

* Critical: **0**
* Major: **2**

## Confirmed findings

### 1. **Major — `release-to-main.sh`가 ignored 로컬 파일을 정상 실행 경로에서 삭제함**

**파일/구간:** `release-to-main.sh`의 release-tree 생성 및 `EXCLUDES` 제거 로직

스크립트는 현재 checkout이 clean인지 검사한 다음, 같은 worktree에서 `main`을 checkout하고 `dev` 트리를 덮어쓴 뒤, 제외 대상마다 `git rm --cached`와 `rm -rf`를 실행합니다. 새 제외 대상에는 `.claude` 전체가 포함됩니다.

Claude Code의 표준 프로젝트 로컬 설정은 `.claude/settings.local.json`이고, Claude Code가 생성한 경우 git에서 무시됩니다. 즉 이 파일은 `git status --porcelain`이 비어 있는 상태에서도 존재할 수 있습니다. ([Claude][1])

임시 저장소에서 다음 조건으로 정확히 재현했습니다.

```text
dev:
  tracked: .claude/agents/waystone-operator.md
  ignored: .claude/settings.local.json

release 전 git status --porcelain: 빈 출력
release 로직 실행 후: settings.local.json 삭제됨
dev 복귀 후 git status --porcelain: 여전히 빈 출력
```

따라서 성공한 release가 사용자별 permission, environment, hook 설정을 경고 없이 영구 삭제할 수 있습니다. `.claude` 외에도 디렉터리 단위로 제외되는 모든 경로 아래의 ignored 파일에 같은 문제가 적용됩니다. 이는 SSOT의 **Local-first, 비파괴** 원칙과 직접 충돌합니다.

또한 `restore()`가 `trap`으로 등록되어 있지 않아, `git read-tree` 이후 commit hook·서명·파일 제거 등 어느 단계에서든 실패하면 `main` checkout과 부분 변경이 그대로 남습니다.

**권고**

현재 checkout을 release staging area로 사용하지 않아야 합니다.

1. 임시 worktree 또는 임시 `GIT_INDEX_FILE`에서 `dev` 트리를 투영하고 제외 경로를 index에서만 제거합니다.
2. 생성된 tree로 release commit을 만든 뒤 `main` ref를 갱신합니다.
3. 현재 개발 worktree에는 checkout, `read-tree -u`, `rm -rf`를 실행하지 않습니다.
4. 최소 회귀 테스트로 아래 두 경로를 추가합니다.

   * ignored `.claude/settings.local.json`이 성공한 release 후 byte-identical하게 남는지
   * 의도적으로 commit 단계를 실패시켜도 시작 branch와 local 파일이 그대로인지

---

### 2. **Major — verifier contamination 수정이 `tasks_read_nudge` 경로를 놓쳐 독립 검증이 여전히 자기 오염으로 실패함**

**파일/구간:**

* `scripts/delegate.py::_verifier_env`
* `hooks/scripts/tasks_read_nudge.sh`
* `scripts/delegate.py::_verify_worktree_state`
* verifier lifecycle regression test

Verifier는 `WAYSTONE_VERIFIER_SESSION=1`을 설정하지만 동시에 `UV_CACHE_DIR`를 review worktree 내부의 `.waystone-uv-cache`로 지정합니다. 이 환경은 companion, Codex CLI, Claude CLI verifier 경로에 전달됩니다.

현재 guard를 확인하는 hook은 `session_context.sh`와 `resume_snapshot.sh`뿐입니다. `tasks_read_nudge.sh`는 guard가 없고, verifier가 canonical `tasks.yaml`을 Read하면 `uv run`을 실행합니다.

`uv`는 항상 cache directory를 필요로 하며, `UV_CACHE_DIR`가 지정되면 해당 경로를 cache로 사용합니다. ([Astral Docs][2]) Review postcondition은 일반 untracked 파일뿐 아니라 **ignored untracked 파일도 명시적으로 fingerprint**하고, before/after가 다르면 verify artifact를 기록하지 않습니다.

이 경로도 임시 저장소에서 실제 hook으로 재현했습니다.

```text
environment:
  WAYSTONE_VERIFIER_SESSION=1
  UV_CACHE_DIR=<review-worktree>/.waystone-uv-cache

event:
  PreToolUse Read(<review-worktree>/tasks.yaml)

hook result:
  rc=0
  permissionDecision=deny

git status --short:
  빈 출력

git ls-files --others --ignored --exclude-standard:
  .waystone-uv-cache/.gitignore
  .waystone-uv-cache/.lock
  .waystone-uv-cache/CACHEDIR.TAG
  .waystone-uv-cache/interpreter-v4/...msgpack
  .waystone-uv-cache/sdists-v9/.gitignore
```

즉 verifier의 정상적인 Read 시도만으로 ignored cache 파일이 생기고, postcondition이 이를 genuine mutation과 동일하게 판단하여 verification을 거부합니다. 기존 회귀 테스트는 두 lifecycle hook만 실행하므로 이 경로를 검증하지 않습니다.

Cache를 worktree 밖으로 옮기기만 해도 검증 품질 문제는 남습니다. `tasks_read_nudge.py`는 Read 자체를 deny하고 CLI 사용을 지시하는데, 독립 verifier의 제한된 tool policy에서는 그 대체 경로가 사용 불가능하거나 review 동작을 왜곡할 수 있습니다.

**권고**

1. `WAYSTONE_VERIFIER_SESSION=1`의 계약을 “state writer 두 개만 비활성화”가 아니라 **모든 Waystone host hook을 비활성화**하는 것으로 명문화합니다.
2. 최소한 `tasks_read_nudge.sh`, `boundary_check.sh`, `tasks_guard.sh`를 포함한 모든 hook entrypoint 최상단에 공통 guard를 적용합니다.
3. `UV_CACHE_DIR`를 review worktree 밖의 임시 디렉터리나 record-local runtime 디렉터리로 옮깁니다.
4. manifest에 등록된 모든 hook을 실제 subprocess로 실행하는 verifier hook-matrix 테스트를 추가합니다.

   * `tasks.yaml` Read가 출력·deny 없이 통과하는지
   * marker가 존재하는 Stop 이벤트도 worktree를 바꾸지 않는지
   * `_verify_worktree_state(before) == after`인지
5. 기존 genuine verifier mutation fail-loud 테스트는 그대로 유지합니다.

## Open domain questions

### Verifier session의 hook 격리 범위

`WAYSTONE_VERIFIER_SESSION`이 단순히 기록 hook만 차단하는지, 독립 verifier를 Waystone의 모든 host automation으로부터 hermetic하게 만드는지 명시적인 계약이 필요합니다. 현재 문제는 후자가 아니면 계속 재발합니다. 독립 검증의 관점에서는 **모든 Waystone hook no-op**이 더 일관된 경계입니다.

### Release projection 모델

“향후 생성되는 dogfooding artifact도 main에 절대 들어가지 않는다”가 hard invariant라면, 현재의 `dev tree - path denylist` 방식은 미래 경로를 증명하지 못합니다. 현재 알려진 artifact 경로의 누락은 확인하지 못했지만, 장기적으로는 다음 중 하나가 필요합니다.

* ship 대상의 positive manifest
* dogfood artifact의 단일 machine-readable manifest
* dev/main tree 비교 시 허용된 product path만 검증하는 contract test

## Residual risks

* 요청서 자체가 실제 Claude Code/Codex host invocation을 실행하지 못했고, 설치된 release에도 아직 변경이 없다고 명시합니다. 따라서 hook discovery, trust UI, stdout/stderr 표시와 같은 live behavior는 잔여 리스크입니다.
* Claude Code 측의 `hooks/hooks.json` 및 `${CLAUDE_PLUGIN_ROOT}` 사용은 공식 계약과 일치합니다. ([Claude][3]) Codex 공개 문서에서는 plugin hook 존재와 trust 요구는 확인되지만, 이 변경이 의존하는 `CLAUDE_PLUGIN_ROOT` compatibility alias의 구체 계약은 확인되지 않았습니다. ([OpenAI 개발자][4])
* 제출된 `562 tests passed` 전체 suite는 이 환경에서 독립 재실행하지 않았습니다. 대신 위 두 Major는 각각 최소 저장소에서 실제 Git·shell·uv 동작으로 재현했습니다.

[1]: https://code.claude.com/docs/en/settings "https://code.claude.com/docs/en/settings"
[2]: https://docs.astral.sh/uv/concepts/cache/ "https://docs.astral.sh/uv/concepts/cache/"
[3]: https://code.claude.com/docs/en/hooks "Hooks reference - Claude Code Docs"
[4]: https://developers.openai.com/codex/plugins "
  Plugins | ChatGPT Learn
"


---

## Findings (triage skeleton — verify each before registering)

_No `JW-GPT-NNN` finding blocks parsed — triage the verbatim reply directly._

| # | finding (요지) | verdict | type | evidence / reason | task-id |
|---|---|---|---|---|---|
| 1 | release-to-main.sh가 현 워킹트리 staging으로 EXCLUDES의 ignored 로컬 파일을 rm -rf 삭제 + restore trap 부재 | REAL | correctness | 리뷰어 임시 repo 재현(무증상 settings.local.json 삭제) + main-session 코드 검증 일치(checkout main→read-tree -u→rm -rf); SSOT §원칙 Local-first·비파괴 위반 | fix/release-staging-isolation (major) |
| 2 | tasks_read_nudge 미가드 + worktree 내 UV_CACHE_DIR로 verifier의 정상 Read만으로 postcondition 실패 | REAL | verification | 리뷰어 실 hook+uv 재현; tasks_read_nudge.sh:9 `uv run` 확인; 직전 적대 리뷰의 '미재현 edge' 하향 판정 정정. deny가 verifier Read를 왜곡하는 문제 포함 | fix/verifier-hook-hermeticity (major, deps: decision/verifier-hook-isolation-contract) |
| 3 | (open question) WAYSTONE_VERIFIER_SESSION 계약 범위 — 기록 hook만 vs 전 hook hermetic | NEEDS-RULING | architecture | SSOT 해석 사안(독립 검증의 경계 정의) — 리뷰어는 hermetic 권고 | decision/verifier-hook-isolation-contract |
| 4 | (open question) release 배포 모델 — denylist는 미래 artifact 경로를 증명 못함 | NEEDS-RULING | architecture | 현행 알려진 경로 누락은 미확인(리뷰어 확인); 장기 invariant 증명 방식의 선택 사안 | decision/release-ship-manifest |

Residual risks (task 미등록, 기존 계획으로 커버): 실 CC/Codex 호스트 발화·trust UI는 다음 릴리스 후 dogfooding 라이브 검증 예정(start-here 참조); Codex 측 CLAUDE_PLUGIN_ROOT compatibility alias 계약은 공개 문서 미확인 — 라이브 검증 항목에 포함.
