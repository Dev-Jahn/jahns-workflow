<!-- waystone feedback: the body below is the reviewer reply VERBATIM (byte-exact copy via `waystone review ingest`) — do not edit it; a triage skeleton is appended beneath it. -->
round: 2026-07-18-generation-binding
reviewer: chatgpt:gpt-5.6-pro
ingested: 2026-07-18
source: /tmp/review.md

---

```text
model: gpt-5.6-pro
effort: xhigh
review-target: 44a4b77db4e614b23721bfd601ab5aa4b96f6c65
```

## 판정

**CHANGES REQUESTED — Critical 0 / Major 4**

`JW-GPT-005`의 reprepare crash ordering은 해소됐습니다. 그러나 generation receipt의 읽기 권위, PR cycle 결속, legacy capability anchor, probe runtime fingerprint에서 각각 fail-open 또는 provenance 과장 경로가 남아 있습니다.

## 직전 4건 상태

| 항목                                 | 판정               | 근거                                                                                                                           |
| ---------------------------------- | ---------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `JW-GPT-004` request-generation 결속 | **still-broken** | Packet receipt는 verbatim reply가 아니라 같은 파일의 가변 metadata cache를 신뢰합니다. PR cycle도 request digest를 기록하지 않습니다.                    |
| `JW-GPT-005` reprepare 원자성         | **resolved**     | 새 binding을 먼저 발행하고 request와 narrative를 뒤따라 갱신하며, pending은 두 projection을 최신 binding과 대조합니다.                                   |
| `JW-GPT-006` v1 downgrade          | **still-broken** | v2 자체는 필수 digest로 경화됐지만, legacy capability를 결정하는 “기존 과거 round” 집합을 mutable `PROGRESS.md`로 확장할 수 있습니다.                        |
| Q1 probe proof                     | **still-broken** | binary·host·mount 축은 추가됐지만 실행 사용자와 process security/config context가 빠져, shared checkout의 proof가 다른 runtime에서 그대로 적중할 수 있습니다. |

---

## Confirmed findings

### JW-GPT-007 — feedback metadata 한 줄 편집으로 A 회신을 B generation에 재귀속할 수 있음

* Severity: major

#### 실패 메커니즘

`ingest()`는 reviewer body에서 파싱한 선언과 resolved generation digest를 `reply-metadata-json`에 복제합니다. 이 metadata header와 verbatim reviewer body는 같은 `feedback.md` 파일에 저장됩니다.

그러나 읽기 경로인 `read_feedback_reply_metadata()`는 첫 separator 앞의 metadata header만 읽습니다. 다음 값은 모두 `reply-metadata-json`에서 직접 신뢰합니다.

* `metadata`의 model/review-target
* `narrative_digest`
* `rendered_request_digest`
* `rendered_request_coverage_reason`

Verbatim body에 실제로 적힌 `request-digest`는 다시 파싱하거나 metadata와 대조하지 않습니다.

따라서 다음 한 파일 편집으로 generation 결속을 우회할 수 있습니다.

1. Request A를 검토한 reply A를 ingest한다.
2. 같은 target으로 request B를 reprepare한다. A receipt는 정상적으로 pending이 된다.
3. `R-feedback.md`의 `reply-metadata-json` 한 줄에서:

   * `narrative_digest`를 B digest로,
   * `rendered_request_digest`를 B digest로,
   * coverage key가 존재하도록 수정한다.
4. Verbatim body는 여전히 A의 `request-digest`를 말하고 있어도 읽기 경로는 이를 보지 않는다.
5. Pending 계산은 수정된 receipt digests와 B binding 및 B projections가 일치한다는 이유로 round를 완료 처리한다.

이는 “stored assessment boolean은 재신뢰하지 않는다”는 원칙을 지키면서도, 그 boolean의 근거인 stored receipt 자체를 재신뢰하는 구조입니다. Request-digest echo가 실질적 증거가 아니라 ingest 시 만들어진 가변 cache의 원재료로만 쓰입니다.

#### 필수 수정

읽기 시점에 다음을 다시 파생해야 합니다.

1. `verbatim-bytes`를 이용해 exact reviewer body 범위를 찾는다.
2. 그 body에 `parse_review_reply_header()`를 다시 적용한다.
3. body가 선언한 `request-digest`를 immutable request sidecar generation에 resolve한다.
4. Stored metadata와 재파생 결과가 다르면 feedback을 corrupt/pending으로 처리한다.

`reply-metadata-json`은 cache나 진단 정보일 수는 있지만 receipt authority여서는 안 됩니다.

더 강하게 “임의의 로컬 단일-file tamper”까지 위협모델에 포함한다면, reviewer body와 receipt가 같은 가변 로컬 파일에 있는 한 그 보장은 성립하지 않습니다. 그 경우 receipt를 별도 append-only event나 원격 canonical store에 고정해야 합니다.

---

### JW-GPT-008 — PR review cycle이 request generation을 결속하지 않아 A cycle에 B digest가 귀속됨

* Severity: major

#### 실패 메커니즘

PR freeze의 로컬 sidecar에는 cycle/head/base/reviewers만 있고 narrative 또는 rendered-request digest가 없습니다.

GitHub에 게시되는 `waystone-review-cycle` marker도 마찬가지로 request digest를 포함하지 않습니다.

다음 정상 명령 순서에서 provenance가 잘못 결합됩니다.

1. PR mode에서 request A를 prepare한다.
2. Freeze cycle 1이 A를 GitHub comment로 게시한다.
3. Reviewer가 cycle 1/A를 완료한다.
4. 같은 HEAD에서 narrative B로 `review prepare`를 다시 실행한다.

   * 기존 sidecar와 비교하는 불변 조건은 target/base/reviewers/mode뿐이므로 B generation 발행이 허용됩니다.
5. 새 freeze는 실행하지 않는다. GitHub에서 완료된 review cycle은 여전히 A를 게시했던 cycle 1이다.
6. Improve projection은 최신 freeze cycle 1과 **최신 request sidecar B**를 target/reviewers만으로 결합하고, B의 narrative/rendered digests를 cycle 1의 request provenance로 출력합니다.

`ingest_round_binding()`의 PR 경로도 같은 방식으로 최신 freeze와 최신 request sidecar를 target/reviewers만으로 결합합니다.

Merge gate 자체는 cycle 번호 때문에 A의 완료를 B의 새 freeze에 재사용하지 않습니다. 문제는 durable evidence projection이 **게시되지도, cycle 1에서 검토되지도 않은 B generation을 cycle 1과 명시적으로 join**한다는 점입니다. 이는 domain lens의 provenance 과장입니다.

#### 필수 수정

PR publication 시점에 exact generation을 cycle evidence에 포함해야 합니다.

* `waystone-review-cycle` marker에 `rendered_request_digest`
* PR freeze sidecar에도 동일 digest
* 같은 cycle conflict 판정에도 digest 포함
* Improve와 `ingest_round_binding()`은 “latest request”가 아니라 cycle marker가 명명한 digest의 sidecar를 조회

Local freeze sidecar를 잃어도 GitHub marker만으로 exact generation을 복구할 수 있어야 합니다.

---

### JW-GPT-009 — mutable `PROGRESS.md` heading으로 임의의 과거 round를 새로 mint하여 v1 downgrade 가능

* Severity: major

#### 실패 메커니즘

V1 legacy 허용 여부는 round id 날짜가 `2026-07-18` 이전 또는 당일인지로 결정됩니다. 이후 날짜의 v1은 corrupt지만, cutoff 이전 날짜의 v1은 digest가 없어도 유효합니다.

요청서는 이를 “과거 round의 고정된 유한 집합”으로 설명합니다. 그러나 mint gate가 그 집합을 고정하지 않습니다.

`round close`는 날짜가 오늘이 아니어도 “기존 closeout”이면 허용하며, 기존 여부는 다음 둘 중 하나입니다.

1. round exposure가 존재함

2. mutable `PROGRESS.md`에 `## <round-id>` heading이 존재함

따라서 현재 날짜가 cutoff 이후여도 다음 경로가 가능합니다.

1. `PROGRESS.md`에 아직 존재하지 않는 `## 2026-07-18-arbitrary` heading 하나를 추가한다.
2. `round close --round 2026-07-18-arbitrary`를 실행한다.
3. Date gate는 이를 기존 round로 간주하고 현재 HEAD의 새 exposure를 발행한다.
4. Request를 v2로 prepare한 뒤 sidecar를 v1로 바꾸고 두 digest를 제거한다.
5. Round id가 cutoff 당일이므로 reader는 이를 genuine legacy v1으로 받아들인다.
6. Echo 없는 reply는 legacy fallback을 다시 사용할 수 있다.

즉 legacy-eligible round 집합은 고정되어 있지 않습니다. 한 tracked documentation edit로 임의의 과거-dated review generation을 새로 mint할 수 있습니다. 이는 Known weak spot의 단순 재발견이 아니라, 그 잔여가 “유한”이라는 전제를 무효화하는 새 진입 경로입니다.

#### 필수 수정

`_round_has_existing_closeout()`에서 `PROGRESS.md` heading을 capability 증거로 사용하면 안 됩니다.

안전한 선택지는 다음 중 하나입니다.

* 유효한 immutable round exposure만 기존 round로 인정
* Pre-exposure 역사 round는 migration 시점에 생성된 명시적 allowlist/manifest로 고정
* Allowlist를 특정 repository commit 또는 migration event에 결속

자유 편집 문서는 digest capability 경계를 결정하는 trust anchor가 될 수 없습니다.

---

### JW-GPT-010 — probe fingerprint가 실행 principal과 process security context를 누락함

* Severity: major

#### 실패 메커니즘

새 fingerprint는 다음 축을 포함합니다.

* resolved Codex path, size, mtime, version
* hostname과 machine-id/IOPlatformUUID
* OS/kernel
* sandbox invocation contract
* Linux LSM inventory
* filesystem device/fsid/readonly

그러나 Linux LSM 관측 함수 자체도 “future Codex process에 적용되는 전체 policy를 설명하지 않는다”고 명시합니다.  전체 fingerprint 필드에도 실행 사용자와 process-local security/config context는 없습니다.

누락된 주요 축은 다음과 같습니다.

* effective UID/GID 및 supplementary groups
* `HOME`/`CODEX_HOME`과 실제 Codex configuration identity
* user namespace / mount namespace
* seccomp mode
* 현재 AppArmor/SELinux process label
* Linux capabilities 및 no-new-privileges 상태

Marker는 project-local `.waystone/codex-runner-verified`에 있고, 현재 fingerprint와 JSON exact-match하면 proof가 인정됩니다.

따라서 공유 checkout에서 다음이 가능합니다.

1. User/container A가 probe를 성공시키고 marker를 기록한다.
2. User/container B가 같은 host machine-id, hostname, kernel, system-wide Codex binary와 같은 filesystem mount를 사용한다.
3. B의 UID, groups, seccomp/AppArmor context 또는 Codex user configuration은 A와 다르다.
4. 현재 fingerprint의 모든 기록 필드는 동일하므로 marker가 적중한다.
5. `_run_codex()`는 probe를 생략하고 runner를 직접 실행한다.

이는 직전 Q1의 NFS/shared-checkout 경로를 machine-id만 추가해서 완전히 닫은 것이 아닙니다. Checkout-local은 machine-local이나 user/runtime-local과 동의어가 아닙니다.

#### 필수 수정

Proof를 최소한 다음에 결속해야 합니다.

* effective UID/GID/groups
* relevant Codex config root와 config fingerprint
* process security context와 namespace identity
* probe가 실행된 worktree owner/permission context

또는 marker를 project checkout이 아니라 user-machine state에 두고 project/mount/runtime fingerprint로 keying해야 합니다. 필요한 context를 신뢰성 있게 측정할 수 없는 환경에서는 marker를 재사용하지 않고 매번 probe하는 것이 fail-closed 방향입니다.

---

## Open domain questions

없습니다. 위 네 항목은 코드 경로로 확인되는 correctness/provenance 문제입니다.

문서화된 stderr-only static shim 잔여 자체는 재지적하지 않았습니다. 이번 Q1은 별개의 execution-principal/process-context 누락입니다.

## Residual risks from unavailable environment

Target commit에 연결된 GitHub Actions workflow run은 확인되지 않았습니다.  따라서 요청서가 보고한 777-test green 및 ruff 결과를 CI evidence로 독립 확인하지 못했습니다.

또한 다음 환경 동작은 실행하지 못했습니다.

* 실제 Linux/macOS에서 runtime fingerprint 수집
* shared checkout의 cross-user/container marker reuse
* GitHub PR comment → cycle marker → improve projection 전체 roundtrip
* 강제 종료를 주입한 reprepare integration

정적 코드 계약상 `JW-GPT-005` 수정은 타당하지만, 위 Major 4건 때문에 `44a4b77db4e614b23721bfd601ab5aa4b96f6c65`는 아직 release 승인 대상이 아닙니다.


---

## Findings (triage skeleton — verify each before registering)

| finding | severity | type | verdict (REAL/REJECTED/NEEDS-RULING) | evidence | task id |
|---|---|---|---|---|---|
| JW-GPT-007 — feedback metadata 한 줄 편집으로 A 회신을 B generation에 재귀속할 수 있음 | major | verification | REAL | 코드 확증: `read_feedback_reply_metadata`(review.py:640)는 separator 앞 헤더 prefix만 읽고 verbatim body의 request-digest를 재파싱하지 않음 — "선언은 as-is 투영" docstring 그대로. receipt 권위가 같은 파일의 가변 cache에 있음. 수정 방향은 확립된 projection 재계산 원칙(triage-discipline ruling)의 연장: 읽기 시점 body 재파생 + 불변 sidecar resolve + 불일치 corrupt. append-only/원격 store 변형은 decision/trust-threat-model-boundary에 위양. | fix/receipt-read-time-rederive |
| JW-GPT-008 — PR review cycle이 request generation을 결속하지 않아 A cycle에 B digest가 귀속됨 | major | reporting | REAL | 코드 확증: review-cycle marker(review.py:1926)는 round_id/cycle/target/base/reviewers/fingerprint만 — digest 부재. improve·ingest_round_binding PR 경로가 latest freeze와 latest request sidecar를 target/reviewers로만 join. merge gate 자체는 cycle 번호로 보호되나 durable evidence projection이 미게시 generation을 cycle에 귀속 — provenance 과장. | fix/pr-cycle-generation-binding |
| JW-GPT-009 — mutable `PROGRESS.md` heading으로 임의의 과거 round를 새로 mint하여 v1 downgrade 가능 | major | correctness | REAL | 코드 확증: `_round_has_existing_closeout`(round.py:212)이 exposure 부재 시 mutable PROGRESS.md의 `## <round-id>` regex를 기존성 증거로 수용 — 한 줄 문서 편집으로 과거-dated round 신규 mint 가능, '유한 전환일 잔여' 전제 무효화. 정당 흐름(익일 확장)은 exposure가 항상 존재하므로 exposure-only 앵커로 좁혀도 비파괴. | fix/round-mint-anchor-immutable |
| JW-GPT-010 — probe fingerprint가 실행 principal과 process security context를 누락함 | major | architecture | REAL | 코드 확증(직전 라운드 패치 정독): fingerprint 축에 euid/gid/groups·codex config root·process context 부재 — checkout-local은 user/runtime-local과 동의어가 아님(공유 checkout의 타 사용자 적중). 처방은 principal 축 추가 + Linux best-effort process context, 관측 불가 시 fail-toward-probe. 컨테이너/namespace 심층 축의 비례성은 decision/trust-threat-model-boundary에서 판정. | fix/probe-proof-principal-binding |

**추가 등록**: decision/trust-threat-model-boundary — 3회전 연속 위협모델 확장(로컬 적대→다중 사용자→프로세스 컨텍스트)에 대한 수용 경계 ruling (사용자).
