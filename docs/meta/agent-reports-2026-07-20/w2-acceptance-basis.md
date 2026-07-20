# w2 acceptance basis 보고서

## 주장 ↔ anchor 대조

| acceptance 주장 | anchor | 판정 |
|---|---|---|
| 기준 전환: invariants + accepted ADR + main 확정 승격 목록 | `docs/adr/ADR-0014-m1a-acceptance-basis.md:24-31` | 일치 |
| legacy 828 suite retire-by-default, 승격 의미만 새 test로 재작성 | `docs/adr/ADR-0014-m1a-acceptance-basis.md:33-38` | 일치 |
| Git-tracked 연속성 보존, machine-local/internal 자유 | `docs/adr/ADR-0014-m1a-acceptance-basis.md:40-50` | 일치 |
| ledger는 채굴 체크리스트, 등급표는 gate 아님 | `docs/adr/ADR-0014-m1a-acceptance-basis.md:55-60` | 일치 |
| 구 M1-A exit supersede + 원문 보존 | ADR `:62-66`; plan `:632-646` | 일치 |
| 새 exit: 승격 test green + invariant 위반 0 + accepted ADR 모순/실패 0 | ADR `:68-72` | 일치 |
| 모든 승격 후보에 근거·원 class·재작성 방향 | `docs/promoted-contracts.md` PC-01~PC-30 | 30/30 |
| 명시적 비승격 클래스 군 | `docs/promoted-contracts.md:85-133` | 존재 |

대조 결과: 모순 0. 독립 ADR 감사와 ledger/matrix 재감사도 최종 PASS.

## 검증 명령과 결과

```sh
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; suite_rc=$?; echo "suite rc=$suite_rc"; exit "$suite_rc"
```

- 결과: `suite rc=0`
- `/tmp/suite.log`: `Ran 833 tests in 143.676s`, `OK`

```sh
ruby -rset -e '
ledger = File.readlines("docs/porting-ledger.md").map { |l| l[/^### (\S+) \(/, 1] }.compact.to_set
matrix = File.readlines("docs/traceability-matrix.md").select { |l| l.start_with?("|") }.flat_map { |l| l.scan(/`([A-Za-z0-9_]+Tests)\.[^`]+`/).flatten }.to_set
rows = File.readlines("docs/promoted-contracts.md").select { |l| l.start_with?("| PC-") }
ids = rows.map { |l| l.split("|")[1].strip }
expected = (1..30).map { |n| format("PC-%02d", n) }
abort("candidate ids mismatch") unless ids == expected
missing = []
unsupported = []
rows.each do |line|
  fields = line.split("|").map(&:strip)
  abort("bad columns") unless fields.size == 7
  abort("missing rationale") unless fields[3].match?(/[①②③]/)
  refs = fields[4].scan(/`([A-Za-z0-9_]+Tests)`/).flatten
  abort("missing class ref") if refs.empty?
  missing.concat(refs.reject { |ref| ledger.include?(ref) })
  unsupported << fields[1] if fields[3].include?("③") && refs.none? { |ref| matrix.include?(ref) }
  abort("missing rewrite") if fields[5].empty?
end
abort("missing ledger classes") unless missing.empty?
abort("unsupported criterion ③") unless unsupported.empty?
puts "candidate_rows=#{rows.size} ids=PC-01..PC-30 rationale_missing=0 class_ref_missing=0 rewrite_missing=0"
puts "source_classes_missing=0 criterion3_without_direct_matrix_class=0 ledger_classes=#{ledger.size}"
'
```

- 결과: `candidate_rows=30`, ID 연속, 근거/원 class/재작성 누락 0, ledger class 누락 0,
  ③의 matrix 직접 참조 누락 0, ledger class inventory 85.
- 초기 validator는 이 머신 Ruby에 `Array#filter_map`이 없어 rc=1이었고, 위의
  `map { ... }.compact` 호환 문법으로 동일 검사를 재실행해 rc=0을 확인했다.

```sh
git add dev_docs/0.12.0-refactor-plan.md docs/adr/ADR-0014-m1a-acceptance-basis.md docs/promoted-contracts.md
git diff --cached --check
git diff --cached --name-only
git status --short
```

- staged whitespace check rc=0; 대상은 지정 3파일뿐.
- commit 뒤 `git status --short` 출력 없음(clean).

## 복구 기록

초안 번호 재정렬에 사용한 local Ruby in-place 명령이 rc=1로 untracked
`docs/promoted-contracts.md`를 0바이트로 만들었다. 즉시 `apply_patch`로 감사 반영본을 복원한 뒤
`133 lines / 19,761 bytes`, PC-01~PC-30, 원 class/matrix 대조, 독립 ledger/matrix 재감사를 모두
다시 실행해 PASS를 확인했다. 커밋에는 복원·재검증된 파일만 포함된다.

VERDICT: PASS — ADR-0014, M1-A supersession note, 30개 승격 후보·명시적 비승격을 작성했고 full suite rc=0
COMMITS: 54596eacfa14c771d8a231874335b4b9d47b2a99
HOTFILES: dev_docs/0.12.0-refactor-plan.md M1-A :626-646 중 2줄 supersession note만 추가; review.py/common.py/run_tests.py 미접촉
VERIFIED: candidate 30/30 근거·class·rewrite 완전, ③ matrix 누락 0; git diff --cached --check rc=0; full suite 833 tests OK, rc=0
NOT-RUN: waystone CLI; 신규 test 작성; invariants/ledger/matrix 수정; push
