<!-- waystone feedback: the body below is the reviewer reply VERBATIM (byte-exact copy via `waystone review ingest`) — do not edit it; a triage skeleton is appended beneath it. -->
round: 2026-07-19-evidence-authority
reviewer: codex:gpt-5.6-sol
ingested: 2026-07-19
source: /tmp/review.md

---

```text
model: gpt-5.6-sol
effort: xhigh
review-target: 2e0f1fbe9a9d0c2cdc52d4da919f617c148d9d06
```

## 직전 4건 상태

| 항목 | 판정 | 근거 |
|---|---|---|
| JW-GPT-007 | resolved | Body header를 다시 파싱하고 sidecar를 digest로 resolve하며, cache 불일치는 pending 처리된다(`scripts/review.py:757-853`). |
| JW-GPT-008 | new-concern | 순수 v2의 latest-request 오결합은 차단됐지만, 더 늦은 v1 same-cycle marker가 있어도 이전 v2 digest를 권위로 유지하는 혼합-version 오귀속 경로가 생겼다. |
| JW-GPT-009 | resolved | 과거 round 기존성은 검증된 exposure만 사용하며 `PROGRESS.md` heading 경로가 제거됐다(`scripts/round.py:212-218,243-248`). |
| JW-GPT-010 | still-broken | UID/GID와 process context는 결속됐지만 Codex config는 root directory의 stat만 기록하여 실제 config content 변경을 감지하지 못한다(`scripts/delegate.py:1127-1167`). |

## Confirmed findings

### JW-GPT-011 — 더 늦은 v1 marker가 게시한 generation을 이전 v2 digest로 오귀속함

- Severity: major

#### 실패 메커니즘

1. v2 호스트가 cycle N에서 request A를 게시한다.
2. `44a4b77` 호스트는 v2 marker를 파싱하지 못한다(`44a4b77`의 `scripts/review.py:118`)는 이유로 같은 cycle N을 다시 선택하고, re-prepare된 request B를 더 늦은 v1 marker로 게시할 수 있다.
3. 현재 classifier는 같은 cycle의 v1/v2를 conflict로 보지 않고, timestamp와 무관하게 v2 marker에서 `lc`를 고른다. 반면 review freshness 기준인 `freeze_at`은 더 늦은 v1 timestamp를 사용한다(`scripts/review.py:1625-1637`).
4. 따라서 B 게시 이후의 result·approval은 정상적으로 인정되지만, durable fact의 `rendered_request_digest`는 A의 digest다(`scripts/review.py:1652-1715`). `completed_pr_feedback_event()`와 merge gate도 `cycle_version_skew`를 차단 조건으로 사용하지 않는다(`scripts/review.py:1721-1738`, `scripts/merge.py:46-82`).
5. 현재 테스트도 더 늦은 v1과 더 이른 v2를 배치한 뒤 v2 digest가 유지되어야 한다고 명시한다(`scripts/tests/run_tests.py:908-922`).

결과적으로 reviewer는 B를 보고 완료했지만 evidence projection과 복구 sidecar는 A를 exact generation으로 주장한다. 이는 혼합-version 상태에서의 정직한 version-skew가 아니다.

#### 필수 수정

같은 cycle에서 최신 trusted marker가 v1이면 exact generation을 unknown으로 처리하고 새 cycle의 v2 re-freeze를 요구해야 한다. 더 최신 v2가 존재할 때만 그 digest를 권위로 사용할 수 있다. 이 ordering 규칙을 `classify()`, `ingest_round_binding()`, `improve._review_binding()`에 동일하게 적용해야 한다.

### JW-GPT-012 — 손상된 최신 PR freeze가 제거되어 오래된 cycle이 explicit evidence로 승격됨

- Severity: major

#### 실패 메커니즘

1. round에 유효한 cycle 1/A freeze sidecar와 더 최신인 cycle 2/B sidecar가 존재한다.
2. cycle 2 파일이 truncated JSON 등으로 손상되면 `_round_review_sidecars()`는 warning만 출력하고 그 파일을 projection 입력에서 완전히 제외한다(`scripts/improve.py:1131-1138`).
3. `_review_binding()`은 남은 유효 행의 최대 cycle을 계산하므로 cycle 1을 latest로 선택하고 `review_binding_provenance: explicit`으로 반환한다(`scripts/improve.py:975-1045`).
4. 최종 review row도 그 stale binding을 그대로 내보낸다(`scripts/improve.py:1177-1188,1227-1250`).

따라서 한 최신 파일의 손상이 해당 round를 honest-unknown으로 격리하지 않고, 게시 순서상 폐기됐어야 할 A cycle을 현재 durable evidence로 되살린다.

#### 필수 수정

Freeze filename에서 round/cycle identity를 엄격히 파생하고, 파싱 실패도 해당 identity의 corrupt sentinel로 보존해야 한다. 최고 cycle 후보가 손상됐으면 그 round만 unknown으로 투영하되, 이전 유효 cycle로 fallback해서는 안 된다. Content의 round/cycle도 filename identity와 대조해야 한다.

### JW-GPT-013 — Codex config content 변경 후에도 기존 probe proof가 재사용됨

- Severity: major

#### 실패 메커니즘

1. config A에서 sandbox probe가 통과해 marker가 기록된다.
2. 이후 동일한 `CODEX_HOME/config.toml`의 내용을 in-place로 config B로 변경한다. Directory entry가 추가·삭제되지 않았으므로 config root directory의 inode·size·mtime·ctime은 그대로일 수 있다.
3. `_codex_config_root_identity()`는 root directory만 `stat()`하며 내부 파일이나 effective config content를 읽지 않는다(`scripts/delegate.py:1127-1167`).
4. 이 값은 그대로 fingerprint에 들어가고(`scripts/delegate.py:1267-1282`), comparison은 JSON equality만 수행하며 reuse blocker도 root 상태가 `present`인지 여부만 확인한다(`scripts/delegate.py:1315-1358`).
5. Marker가 일치하면 `_run_codex()`는 probe를 생략하고 변경된 config B로 task runner를 실행한다(`scripts/delegate.py:1431-1453,1483-1487,1557-1567`).

즉 proof는 config A에서 생성됐지만 config B의 runtime에 재사용된다. JW-GPT-010이 요구한 실제 Codex configuration identity 결속이 아직 성립하지 않는다.

#### 필수 수정

Directory stat이 아니라 Codex가 실제로 읽는 sandbox/runner 관련 config 입력의 canonical content digest를 fingerprint에 포함해야 한다. 관련 config를 확정적으로 읽거나 열거할 수 없으면 proof 재사용을 차단해야 한다.

## Open domain questions

없음.

## Residual risks from unavailable environment

- `unverified-static`: 지시에 따라 테스트 스위트를 실행하지 않았다.
- `unverified-static`: JW-GPT-011의 실제 구·신 버전 호스트 간 GitHub comment roundtrip은 실행하지 않았으며, marker selection과 gate 경로를 정적으로 추적했다.
- `unverified-static`: JW-GPT-012의 실제 파일 손상 projection과 JW-GPT-013의 실제 Codex config mutation 후 probe reuse는 실행하지 않았다.

---

## Findings (triage skeleton — verify each before registering)

| finding | severity | type | verdict (REAL/REJECTED/NEEDS-RULING) | evidence | task id |
|---|---|---|---|---|---|
| JW-GPT-011 — 더 늦은 v1 marker가 게시한 generation을 이전 v2 digest로 오귀속함 | major | correctness | REAL | `classify()`의 `lc = max(v2_cycles or same_cycle, key=at)`(review.py:1634)가 더 늦은 v1이 있어도 v2 digest를 권위로 유지, `freeze_at`은 늦은 v1 시각(review.py:1636) — 완료 인정은 B 기준, digest 귀속은 A. `cycle_version_skew`는 facts에만 있고 `completed_pr_feedback_event`·`merge_gate`가 차단 조건으로 소비하지 않음(merge.py:46-82 확인). 구버전 호스트 전제도 성립: 44a4b77의 `MARKER_RE`는 `:v1`만 매치(구 review.py:118) → v2 cycle-N marker 불가시 → same-cycle v1 재freeze 가능. `test_cycle_v1_v2_mix_...`(run_tests.py:908)가 이 오귀속을 명시적으로 고정 중. improve `_review_binding`도 동일 선택식(improve.py:995). | 미등록 (사용자 지시: ingest만) |
| JW-GPT-012 — 손상된 최신 PR freeze가 제거되어 오래된 cycle이 explicit evidence로 승격됨 | major | correctness | REAL | `_round_review_sidecars`의 비대칭 확인: request sidecar는 corrupt sentinel 행 보존(improve.py:1122-1127), freeze sidecar는 warning 후 `continue`로 완전 제외(improve.py:1131-1138) → `_review_binding`이 잔여 유효 행의 `max(cycle)`로 이전 cycle을 `request_provenance: explicit`로 승격(improve.py:983,1045). E-계열 손상-격리 원칙(한 파일 손상이 honest-unknown이 아닌 fallback 증거를 만들지 않음) 위반. | 미등록 (사용자 지시: ingest만) |
| JW-GPT-013 — Codex config content 변경 후에도 기존 probe proof가 재사용됨 | major | verification | REAL | `_codex_config_root_identity`는 config root **디렉터리**의 stat만 기록(delegate.py:1127-1167) — `config.toml` in-place 내용 변경은 디렉터리 inode/size/mtime을 바꾸지 않으므로 fingerprint 불변 → marker 일치 시 probe 생략(delegate.py:1483-1487). sandbox 동작을 지배하는 config 내용이 바뀌어도 구 config에서 측정된 proof가 재사용됨 — 위협모델 확장이 아니라 정당한 자기 config 변경(honest drift)에서도 재현되는 결함. | 미등록 (사용자 지시: ingest만) |

triage 요약 (2026-07-19, main session): REAL 3 / REJECTED 0 / NEEDS-RULING 0 — 전건 major.
직전 4건 판정 검증: 007 resolved·009 resolved 동의, 008은 신규 011로 재개, 010은 013으로 still-broken.
task 등록은 사용자 지시("ingest만, 추가 task 생성 금지")로 보류 — 등록·수정 착수는 사용자 결정 대기.
