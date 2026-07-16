# PROGRESS

round 단위 작업 이력이 이 파일에 축적된다. 활성 task와 의존성은 `tasks.yaml`(CLI: `waystone task`)과 생성 파일 `ROADMAP.md` 참조.

## 2026-07-16-adopt-dogfooding

- **Goal**: waystone이 자기 자신의 개발 하네스가 되는 첫 사이클 — 채택 bootstrap + 첫 dogfooding finding 2건의 위임 수정.
- **Shipped**:
  - docs/adopt-waystone-harness — 자기채택 bootstrap: SSOT.md(ideate 합성), init(packet 리뷰·warn-allowed·delegation on), ADR-0000, 부산물 release EXCLUDES, 3축 profile 6-role binding (done; main-session)
  - fix/boundary-hook-cli-resolution — boundary hook을 plugin hooks.json으로 이동(마커 게이트·비차단·레거시 감지) (done; implementer=external-runner/codex:gpt-5.6-sol, 1차 discard 후 2차 apply)
  - fix/verify-worktree-self-contamination — verifier 세션에서 waystone session hook이 worktree에 상태를 시딩하던 결함을 WAYSTONE_VERIFIER_SESSION guard로 차단 (done; implementer=external-runner/codex:gpt-5.6-sol, 네트워크 실패 1회 discard 후 apply)
- **Gates**: 전체 테스트 558→562 OK + ruff F401,F841 clean (인수 verdict의 agent_checks; 커밋 bb8484c·9076ec8). main 누출 0 — release EXCLUDES tree-hash 시뮬레이션으로 증명 (4f8ddbc).
- **SSOT**: 신규 작성 (§1-§7) + ADR-0000 ratified.
- **Decisions pending**: none.
- **Review**: requested (docs/reviews/2026-07-16-adopt-dogfooding-request.md).
- **Adaptive rules**: unevaluable (활성 overlay 규칙 0개 — bootstrap 단계).
- **Next**: 릴리스로 고친 hook·guard를 설치본에 반영 → verifier binding 복원 + boundary hook enable로 라이브 검증. chore/verifier-session-guard-hardening 처리. 이후 Adapt & Enforce arc.

## waystone 채택 이전 이력 (요약, 2026-06-11 ~ 2026-07-16)

waystone 채택(ADR-0000) 이전의 개발은 round 구조 없이 진행됐다. 상세는 `dev` 브랜치 git log와 `dev_docs/` 설계·구현 노트(gitignored) 참조.

- **v0.1–v0.2 (2026-06):** 플러그인 생성(당시 이름 jahns-workflow). SHA-bound 리뷰 사이클, 결정론적 merge gate 등 correctness kernel을 7차례 외부 GPT 리뷰로 경화.
- **v0.3–v0.6 (2026-06 하순~07초):** 리뷰 번들 도입 후 단일 markdown 요청으로 단순화(v0.4.1), task registry CLI + archive(v0.5), ideate 스킬 + SSOT.md 표준화(v0.6). dev/main 분리, `release-to-main.sh`, marketplace CI 자동 sync 확립.
- **v0.7 Observe & Advise (2026-07-13):** 세션 로그 trace + audit 렌즈 + evidence 기반 improve 권고.
- **v0.8 Delegate & Verify (2026-07-14):** 격리 worktree delegation primitive, artifact contract, overlay/replay/warn, 독립 verify. v0.8.1에서 waystone으로 개명, v0.8.3 Codex 호스트 지원.
- **v0.9 Unify & Automate (2026-07-15):** cross-host 저장 통합(`{root}/.waystone` + `~/.waystone`), flock locking, delegate 자율화(verdict 게이트).
- **v0.10 Bind & Compose (2026-07-16):** 설계 완전성 arc — 213요소 전수 감사 후 role 3축 소비 완성, policy 4층 합성, guard 4규칙, longitudinal metrics, verdict digest 체인. 558 tests. 최종 인수 합격 후 릴리스.
