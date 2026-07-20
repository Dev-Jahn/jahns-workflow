# COMMON — w0720 wave 전 기 공통 계약 (waystone repo)

이 파일 + 뒤에 이어지는 개별 브리프가 너의 전체 지시다. 브리프가 이 계약과 충돌하면 브리프가 우선한다.

## 프로젝트 배경 (전 기 공통)
- repo: waystone — Claude Code + Codex 워크플로 하네스 플러그인 (Python, uv 기반, 테스트 828건).
- 현재 0.12 전면 리팩터의 M0(characterization) 완료 직후. baseline branch `baseline/0.12-refactor` 동결,
  **feature freeze 중 — 이 wave는 결함 수리·정리·리뷰만 한다. 새 기능 추가 금지.**
- 핵심 문서: SSOT.md(전체 재독 금지 — `docs/ssot/INDEX.md`로 필요한 절만 라우팅),
  `docs/invariants.md`(I-01~12·E-01~09), `docs/adr/ADR-*.md`, `dev_docs/0.12.0-refactor-plan.md`.

## 금지
- 네 작업 디렉터리(codex 시작 cwd = 네 worktree) 밖 파일 쓰기 금지. 유일한 예외: 아래 `$REPORTS` 하위의
  지정 보고서 파일. main tree(`/Users/jahn/workspace/waystone`)·타 worktree 수정 금지.
- **`waystone` CLI 실행 금지** — registry root 오해석 결함이 바로 이 wave의 수리 대상이다(오염 방지).
  tasks.yaml·ROADMAP.md·PROGRESS.md·docs/adr/·docs/reviews/ 수정 금지 — main 세션이 처리한다.
- `git add -A` 금지 — 커밋할 파일을 명시 add. 5MiB 초과 산출물 커밋 금지. **push 금지** — 네 로컬
  branch에 커밋만 남긴다, 머지는 main이 한다.
- 예측된 테스트 통과를 위한 threshold 완화·silent fallback·기존 테스트 임의 삭제 금지. 계약을 지킬 수
  없으면 우회 구현 대신 **NO-GO 보고**. 기존 테스트가 브리프의 계약과 모순되면 — 몰래 완화하지 말고
  보고서에 근거를 명시하고 개정한다.

## 환경/호출 표준
```bash
export REPORTS="/private/tmp/claude-501/-Users-jahn-workspace-waystone/9c45406a-2fef-4660-b072-4824b6fcaede/scratchpad/fleet/reports"
# Python 실행은 이 repo 표준인 `uv run` (worktree마다 자체 .venv가 생긴다 — 정상, 네트워크 사용 가능).
# 전체 테스트 게이트 — rc를 직접 캡처, 출력 tail만 믿지 말 것:
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py; echo "suite rc=$?"
```
- 이 머신 세션은 FORCE_COLOR=3이 설정돼 있을 수 있다 — 스위트 및 출력 파싱이 걸린 subprocess 실행은
  항상 위처럼 색상 강제 변수를 중화한다.
- GPU 없음(이 wave 전체 CPU-only).
- base 커밋: **네 worktree의 시작 HEAD가 base다.** 외부 SHA와의 불일치를 조사하는 데 시간 쓰지 말 것.

## hot-file 규약 (머지 충돌 1순위 — 반드시 준수)
- `scripts/tests/run_tests.py`(21k줄 단일 테스트 파일): 전 기가 동시에 만진다. 신규 테스트는 **관련
  기존 테스트 클러스터 인접 위치에 새 함수로만** 추가. 파일 말미 일괄 append 금지(전 기 공통 anchor가
  되어 전부 충돌한다). 무관 구역 리포맷 금지.
- `scripts/common.py`·`scripts/delegate.py`: 브리프가 지정한 anchor 구획만 접촉. 다른 구획은 병행 기
  소유다.
- footprint 최소화 — 신규 로직이 커지면 새 모듈 파일로 분리.

## 검증 규범
- acceptance 기준은 브리프에 pre-register돼 있다. 결과를 본 뒤 완화 금지 — 미달이면 fail-closed로
  FAIL/NO-GO를 보고한다.
- 구현 기: 최종 보고 전 **전체 스위트 1회 rc=0** 필수(위 게이트 명령 그대로). 개발 중에는 표적 재현
  스크립트로 빠르게 돌고, full suite는 마지막에 1회.
- 재현/반증 도구·명령은 음성 판정이어도 산출물로 남긴다(보고서에 명령 원문).
- 결과 JSON을 만드는 도구는 strict-finite(NaN/Inf → 즉시 fail)·fail-closed.

## 보고서 (필수 — 저장: `$REPORTS/<브리프가 지정한 파일명>` + stdout 말미에 동일 요약)
고정 헤더로 시작한다:
```
VERDICT: <PASS/FAIL/NO-GO/DONE + 핵심 한 줄>
COMMITS: <sha 목록 (없으면 none)>
HOTFILES: <run_tests.py/common.py/delegate.py 접촉 여부와 구획>
VERIFIED: <실행한 검증 명령 + rc/수치>
NOT-RUN: <안 한 것 — '도구만 구축'과 '실행 완료'를 구분>
```
이후 자유 서술: 구현 무엇/왜 → 검증 증거 → 리스크 → 머지 주의.
read-only 기(분석·리뷰)는 COMMITS: none 고정 — 아무 것도 커밋하지 않는다.

---
