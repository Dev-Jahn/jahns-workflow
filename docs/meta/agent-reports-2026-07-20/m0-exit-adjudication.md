# M0 exit 적대 리뷰 — 판정 기록 (2026-07-20, fleet w0720)

리뷰어: codex(gpt-5.6-sol, ultra), read-only, 스냅샷 662f2e3. 원본: `m0-exit-review.md`.
검증: finding 11건 각각 독립 opus verifier 1기가 반증 시도(명시된 반증 조건 수색 + 인용 증거 대조).
판정: main(Fable). **최종 M0 exit 판정은 사용자 ruling 대기.**

## 요약

리뷰어 원판정 **blocker 3 / major 6 / minor 2** → 적대 검증 후 **blocker 2 / major 4 / minor 5**.
리뷰어의 산술·인벤토리 검증(828/828, 등급 합계, matrix 21/21, ADR 존재)은 전부 재확인 통과.
blocker 강등 1건(CDX-2)·major 강등 3건(CDX-7·9·10 절반)은 모두 "산출물이 실재하나 리뷰어가 다른
형태를 기대"였거나 "권위가 이미 다른 곳에 배치"인 경우다.

## finding별 판정표

| ID | 주장 | verifier 판정 | 최종 severity | 처분 (등록 task) |
|---|---|---|---|---|
| WS-CDX-1 | M0-B 필수 threat model 미완결 | CONFIRMED (공백 축소: env 전달·lease principal·permission/symlink fail-direction만 실공백; E-03·ADR-0011·ADR-0007이 부분 흡수) | **blocker** | fix/m0-threat-model-completion |
| WS-CDX-2 | characterization/fixture set 부재 | PARTIAL — 핵심 반증: porting-ledger가 SHA-pin된 닫힌 특성화 manifest(fixture는 run_tests.py 인라인, plan §2-5). 잔여: I-10/E-04/E-08 공백 명시·gate task id 미등록 | minor | docs/m0-exit-review-sync |
| WS-CDX-3 | M1-A 출력 등급 gate 실행 불가 | CONFIRMED (4세부 전부; ledger 판정규칙 :26 기준 내적 모순 추가 확인 — 동형 refusal이 타처선 diagnostic) | **blocker** | fix/porting-ledger-grade-gate-executability |
| WS-CDX-4 | JW-GPT-015 보상 구현 미등록 | CONFIRMED (지목 vehicle은 docs-only로 close; blocked 015 task는 폐기된 flat-file 패치 접근이라 대체 불가) | major | feat/review-runs-uuid-owner-directory |
| WS-CDX-5 | closeout manifest 계약 충돌 | CONFIRMED (세부1은 PARTIAL — ADR이 승인된 확정판일 수 있으나 deviation note 부재; 세부2·3·4는 ADR간 충돌이라 supersession으로 못 고침) | major | fix/adr-0006-closeout-manifest-gaps |
| WS-CDX-6 | canonical run id 이중화 | CONFIRMED (ADR-0005가 자기 권위원천 §5-2와 어긋난 상태까지) | major | fix/run-id-grammar-unification |
| WS-CDX-7 | authority matrix가 신설 권위 미흡수 | PARTIAL — 권위는 이미 확정·배치(projects.json=machine-tier F-06 done·profile 전이 권위=plan:448+F-01 M3), 반증 조건 기충족. 잔여: §5-2 back-reference | minor | docs/m0-exit-review-sync |
| WS-CDX-8 | ledger/matrix가 완료 ruling을 needs-ruling으로 유지 | CONFIRMED (forward-reference 규약 없음 — ledger 자체 정의상 stale) | major | docs/m0-exit-review-sync (성격이 doc-sync) |
| WS-CDX-9 | E-09 권위 원천과 확정 문구 충돌 | PARTIAL — ADR-0009가 이미 amend 경로로 supersede(계획의 관대한 E-09를 "현행 결함"으로 명명·수정). 잔여: plan §4 미역동기화 + invariants:4-5 stale 포인터(E-04식 precedence 절 부재) | minor | docs/m0-exit-review-sync |
| WS-CDX-10 | cross-reference 2곳 stale | PARTIAL — matrix "ADR-0003 §3-9" anchor만 생존(계획서 절 번호를 ADR anchor로 인용). ADR-0012 Tasks 필드는 반증(정당 연결) | minor | docs/m0-exit-review-sync |
| WS-CDX-11 | audit 상단 count 이중값 | PARTIAL — 구조 확인(상단 6건 현재형+미역동기화), 영향 과장(:186이 3-bucket 화해 명시). 리뷰어의 "6/2/1" 열거 자체도 부정확 | minor | docs/m0-exit-review-sync |

## main 판정안 (사용자 ruling 대상)

**M0 exit 보류 — blocker 2건 폐쇄 후 재심.** 근거:
- 두 blocker 모두 M1-A의 판정 절차 자체를 막는다(threat model은 M0-B exit 산출물 누락, 등급 gate는
  M1-A acceptance의 실행 불가).
- 단 둘 다 문서/계약 작업이다 — 구현 milestone을 여는 것이 아니라 M0-B/M0-C 산출물의 보완이므로,
  feature freeze와 충돌하지 않고 단기 폐쇄 가능하다.
- major 4건 중 CDX-4(015 보상 구현 등록)는 M1-B acceptance 재편입이 필수 조건 — M1 task 분해 전 처리.
  CDX-5·6은 M1 구현이 참조할 계약의 모순이므로 M1-A 착수 전 ADR amend 권장. CDX-8은 doc-sync.

## 이 wave가 M0 산출물에 만든 drift (재심 시 함께 처리)

- w0720 머지로 dev의 run_tests.py가 baseline(7cfecd3, sha bd781a…)에서 이탈: 828 → 833 tests
  (신규 +10, 구명 호환 삭제 -6, 기존 1 개정<probe hostname 계약> + colorenv env 수리).
  ledger는 baseline 특성화 문서로서 여전히 유효하나, M1-A 게이트 운용 시 "baseline 이후 dev에
  추가된 테스트"의 취급 규칙이 필요하다(ledger 증분 갱신 vs baseline re-pin — CDX-3 task에서 함께 판단 권장).
