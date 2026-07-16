# Review Request — 2026-07-16-adopt-dogfooding

The reviewer has the repository via git. This is a domain/code review — 이 repo의 도메인은 Claude Code/Codex 플러그인 하네스 자체이므로, 아래 변경의 **코드·설계 타당성**을 본다 (이 요청 문서를 만든 워크플로 절차 자체는 out of scope).

- Project / Branch: waystone / dev
- Reviewing: 203580186fefc62cd23f2475c2c9bc1f8df49fc1   (diff against (root) — first round; 실질 변경분은 v0.10.0 릴리스 커밋 925acd5 이후 diff `git diff 925acd5..2035801`로 보는 것을 권장)

## What changed and why

waystone이 자기 자신의 개발을 관리하기 시작한 첫 라운드다 (dogfooding, ADR-0000). 세 묶음:

1. **자기채택 bootstrap** — 방향 문서 `SSOT.md` 신설, `.waystone.yml`(packet 리뷰, warn-allowed, delegation on), 프로젝트 부산물이 릴리스 브랜치(main)로 새지 않도록 `release-to-main.sh` EXCLUDES 확장.
2. **boundary hook 이전** (`fix/boundary-hook-cli-resolution`) — `waystone install hooks`가 `.claude/settings.json`에 심던 Stop hook이 hook 실행 환경에서 CLI를 못 찾는 실 장애(plugin bin PATH 주입은 Bash tool 한정이라는 CC 문서 확인)로, hook을 플러그인 소유 `hooks/hooks.json`으로 옮기고 `${CLAUDE_PLUGIN_ROOT}`로 해석. 프로젝트별 enable 마커(`.waystone/boundary-hooks-enabled`)로 게이트, install은 consent+마커 기록으로 재설계, 레거시 settings.json은 감지·안내만.
3. **verify 자기오염 수정** (`fix/verify-worktree-self-contamination`) — 독립 검증(verify)이 결정론적으로 실패하던 원인: verifier 서브프로세스(cwd=리뷰 worktree) 안에서 waystone 자신의 SessionStart/재진입 hook이 발화해 worktree를 프로젝트로 인식, lock·profile 시딩을 수행 → verify의 tree-mutation postcondition에 자기 부산물이 걸림. 수정: verify가 `WAYSTONE_VERIFIER_SESSION`을 verifier 세션에 전파하고 상태 기록 hook 2종이 그 세션에서 no-op.

두 fix 모두 격리 worktree 위임(codex)으로 구현했고, 1차 패치는 적대 리뷰 blocker(비차단 계약 위반)로 기각 후 finding을 인수 기준으로 편입해 2차에 반영했다.

## Read these first

1. `hooks/scripts/boundary_check.sh` — 새 Stop hook의 전체 로직 (게이팅·launcher 해석·비차단)
2. `hooks/hooks.json` — Stop hook 배선과 command 인용 방식
3. `scripts/delegate.py`의 verifier env 전파와 `_verify_worktree_state` postcondition 부근 — guard의 적용 지점과 오염 감지 로직
4. `scripts/waystone.py`의 `install hooks` 경로 — consent·마커·레거시 감지
5. `release-to-main.sh` — EXCLUDES 확장 (부산물 main 차단)
6. `SSOT.md` — 프로젝트 방향 문서 (north-star 고도 적정성)

## Claims to attack

1. **비차단 계약**: boundary Stop hook은 launcher가 어떤 종료 코드로 죽든(부재 포함) 자신은 exit 0으로 끝나고 stderr만 통과시킨다 — CC에서 Stop hook의 exit 2는 중단 차단 의미이므로 이 계약이 깨지면 사용자 작업이 막힌다.
2. **게이팅 무부작용**: `.waystone.yml`이 없거나 enable 마커가 없는 프로젝트에서 이 hook은 상태 파일을 만들지 않고 즉시 성공 종료한다.
3. **설치/롤백 대칭**: `waystone install hooks`는 사용자 설정 파일을 절대 수정하지 않으며(레거시 감지 시 안내만), 마커 삭제로 완전히 롤백된다.
4. **guard 범위**: `WAYSTONE_VERIFIER_SESSION`은 verifier 세션의 상태 기록 hook만 무력화하고, 일반 세션의 컨텍스트 주입·재진입 스냅샷 동작에는 어떤 영향도 없다 (과억제 없음).
5. **postcondition 비약화**: verifier가 실제로 worktree 파일을 생성·수정하면 verify는 여전히 아티팩트 기록을 거부한다.
6. **릴리스 격리**: EXCLUDES 확장 후 waystone 부산물(SSOT.md, tasks.yaml, docs/*, .claude/*)은 어떤 경로로도 main 릴리스 트리에 들어가지 않는다.

## Evidence already produced (mine — inspect, don't trust)

| Claim | Command / artifact | My reading | Where it lives |
|---|---|---|---|
| 1,2 | boundary_check.sh 픽스처 실측 (launcher exit 2·부재, 미채택 dir) | 모든 경우 exit 0, stderr 통과, 상태 생성 없음 | 인수 verdict agent_checks, `.waystone/delegations/20260716T014050Z-*/artifact/verdict-1.json` |
| 1-3 | 계약 테스트 6종 RED-first + 전체 561 tests | 구현 전 실패 확인 후 green | `scripts/tests/run_tests.py` (Boundary/Install 계약), 커밋 bb8484c |
| 4,5 | `DelegateVerifyTests` 19 tests (재현 fixture + 오염 거부 회귀) | 재현 조건(커밋된 config+레거시 시드)에서 verify 기록 성공, 진짜 오염은 거부 | 커밋 9076ec8, `.waystone/delegations/20260716T074509Z-*/artifact/verdict-1.json` |
| 6 | 임시 index로 `read-tree dev − EXCLUDES` tree-hash 계산 | 시뮬레이션 tree == 현 main tree (바이트 동일) | PROGRESS 2026-07-16 항목, 커밋 4f8ddbc 메시지 |
| 전체 | 전체 스위트 + ruff | 562 tests OK, F401/F841 clean | 각 커밋 직전 게이트 실행 |

## Known weak spots

- **실 호스트 라이프사이클 미검증**: hook 발화와 guard 전파는 subprocess 픽스처·계약 테스트 수준 — 설치본(릴리스)에 반영된 뒤에야 라이브로 확인 가능. 다음 릴리스 후 이 repo에서 dogfooding으로 검증 예정.
- **적대 리뷰가 남긴 edge 4건** (blocker 0 판정이지만 기록됨, `chore/verifier-session-guard-hardening`): 미가드 hook 표면(boundary_check·tasks_read_nudge)의 이론 경로, companion broker의 guard env 수명, RUN 단계 구현자 세션의 `.waystone` 시딩(무결성 무해하나 미처리).
- **SSOT.md는 방금 합성된 초판** — north-star 고도·falsifiability가 적정한지 외부 시각 환영.

## Domain lens

shell hook 안전성(비차단·경로 인용·stdin 처리), 상태 격리(리뷰 worktree ≠ 프로젝트), 설치·롤백 대칭성, 릴리스 브랜치 위생.

## Out of scope

`dev_docs/`(gitignored 로컬 설계 노트), v0.10.0 릴리스(925acd5) 이전의 이력, 이 라운드를 만든 워크플로 절차 자체.

## Response wanted

Major / critical issues only. For each: a concrete failure mechanism and where you confirmed it. Separate confirmed findings, open domain questions, and residual risks from unavailable environment (실 CC/Codex 호스트 발화 등).
