# ADR-0014: M1-A acceptance basis를 invariants·accepted ADR·승격 계약으로 전환한다

- Status: accepted
- Date: 2026-07-20
- Round: —
- SSOT sections affected: 없음 — 0.12 재설계의 milestone acceptance authority를 확정한다
- Tasks: docs/adr-m1a-acceptance-basis

## Context

0.12는 legacy 구조를 보존하는 리팩터가 아니라 재설계다. 종전 계획서 §2-5와 M1-A exit는
828개 legacy test를 출력 등급에 배정하고 old/new 결과를 비교하는 방식으로 silent contract drop을
막으려 했다. 그러나 M0 exit 리뷰의 WS-CDX-3는 등급 배정과 normalization이 실제 comparator
계약으로 실행될 수 없음을 확인했다. 등급 gate를 수리하면 828개 legacy 출력이 새 설계의 목적함수가
되어 재설계가 옛 구현을 test-by-test로 모사하는 작업으로 바뀐다.

2026-07-20 사용자 ruling은 이 전제를 교체했다. 새 시스템이 보존해야 할 것은 옛 코드와 출력의
동형성이 아니라 확정된 안전·권위 계약과 Git-tracked 프로젝트 기록의 연속성이다.

## Decision

### Acceptance authority

M1-A와 이후 0.12 재구축의 합격 기준은 다음 세 계약 집합의 합집합이다.

1. `docs/invariants.md`의 I-01~I-12·E-01~E-09
2. 판정 시점에 `accepted`인 ADR의 적용 가능한 계약
3. main이 확정한 승격 계약 목록

legacy 출력 동등성, legacy 828 suite의 green, porting ledger의 등급 합계나 행별 처분은 이
합격 기준의 필요조건도 충분조건도 아니다.

### Legacy suite는 retire-by-default다

legacy 828 test는 기본 폐기한다. 전수 이식이나 import/fixture path만 바꾸는 기계적 port를 하지
않는다. main이 명시적으로 승격한 의미 계약만 새 시스템 경계의 새 계약 테스트로 다시 작성한다.
새 테스트는 옛 코드 구조, 내부 파일 배치, CLI 내부 동작이나 출력 문구를 복제하지 않고 승격된
계약의 성공·거부·fault 방향을 검증한다. legacy test의 물리 삭제 시점과 작업은 이 ADR 범위 밖이다.

### 승격 경계

Git-tracked 프로젝트 기록의 연속성은 기본 승격 대상이다. `.waystone.yml`, `tasks.yaml`과
archive, 기존 `docs/reviews/` request·binding·feedback 아카이브, `PROGRESS.md`, `ROADMAP.md` 등은
새 시스템이 계속 읽고 유효한 다음 기록을 이어쓸 수 있어야 한다. 역사 기록을 일괄 rename하거나
새 runtime store의 값으로 대체하지 않는다. 새 writer의 canonical layout과 schema는 accepted
ADR을 따르며, 이 ADR은 run ID나 manifest 계약을 다시 결정하지 않는다.

machine-local 상태와 그 저장 형식, 코드 내부 구조, CLI 내부 동작은 continuity 대상이 아니므로
자유롭게 폐기할 수 있다. 다만 해당 동작이 invariant, accepted ADR 또는 승격 계약을 구현하는
유일한 수단이었다는 이유로 그 상위 계약까지 폐기할 수는 없다.

`docs/promoted-contracts.md`는 main이 인수·확정할 후보 초안이다. 초안 행은 스스로 gate를
확장하지 않으며, main이 확정한 행만 위 세 번째 계약 집합에 들어간다.

### Porting ledger는 채굴 체크리스트다

`docs/porting-ledger.md`는 legacy 828 test에서 역사적 observable을 찾기 위한 characterization
기록과 채굴 체크리스트로만 사용한다. 출력 등급표와 `port`/`rewrite` 처분은 참고 정보이며,
comparator gate, coverage denominator 또는 M1-A exit 판정으로 사용하지 않는다. ledger 파일
자체는 이 결정에서 변경하지 않는다.

### 종전 M1-A exit를 supersede한다

이 ADR은 계획서 M1-A의 r3 출력 등급별 동일성 exit 전체, 즉 결정 당시 `:632-643`의 등급표와
ledger 배정 문단을 명시적으로 supersede한다. 계획서 원문은 역사적 맥락으로 보존하고, M1-A의
구현 범위 설명은 이 ADR에서 다시 결정하지 않는다.

새 M1-A exit는 다음을 모두 만족할 때다.

1. main이 확정한 승격 목록의 각 계약에 새 시스템 계약 테스트가 존재하고 모두 green이다.
2. I-01~I-12·E-01~E-09 위반이 0이다.
3. 적용 가능한 accepted ADR 계약과 알려진 모순 또는 실패한 계약 검사가 0이다.

따라서 WS-CDX-3는 comparator를 수리해서 닫는 blocker가 아니다. 실행 불가능한 comparator gate를
폐기하고 위 acceptance authority로 대체함으로써 소멸한다.

## Consequences

- legacy test count와 출력 등급 일치는 0.12 진척률이나 합격 증거가 아니다.
- 승격된 의미는 새 architecture 경계에서 다시 검증하므로 legacy test 자체는 새 시스템의
  verification evidence가 아니다.
- Git-tracked 역사와 사용자가 읽는 프로젝트 기록은 이어지지만 machine-local/internal
  compatibility 부담은 제거된다.
- 의도적 비승격은 승격 목록의 비승격 절에 클래스 군 단위로 남겨 누락과 구분한다.
- legacy coverage가 없는 invariant와 accepted ADR 계약은 legacy에서 승격할 항목이 아니라 새
  계약 테스트로 직접 구현해야 한다.

## Alternatives considered

- **(A) 출력 등급 gate를 수리한다.** 828개 test를 실제 관측 표면에 다시 배정하고, 동적 field의
  normal form과 executable old/new comparator를 만든다. WS-CDX-3가 현 gate의 실행 불가성과
  내적 불일치를 확인했고, 이 수리는 828개 legacy output을 새 설계의 목적함수로 만들어 전수 이식
  수렁을 낳는다. “새 계약을 지키는가” 대신 “옛 구현을 흉내 내는가”를 묻게 되어 재설계와
  싸우므로 기각한다.
- **Git-tracked 기록까지 전부 폐기한다.** 기존 프로젝트가 task·review·progress 역사를 읽거나
  이어쓸 수 없어 사용자 데이터 연속성을 파괴하므로 기각한다.
