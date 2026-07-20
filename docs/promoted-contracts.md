# 0.12 승격 계약 목록 (confirmed v1)

- Status: **confirmed v1** — main 인수 2026-07-20 (PC-01~PC-30 전량; 행 단위 조정은 사용자 override로 가능)
- Basis: ADR-0014
- Inventory reviewed: `docs/porting-ledger.md` 85 classes / 828 methods

이 문서는 main이 2026-07-20 인수·확정한 계약 목록이다(v1 — 확정 기록은 ADR-0014 Amendment).
각 행은 legacy test 자체나 출력 등급이 아니라 새 시스템에 남길 **의미 계약** 하나를 확정한다.
각 계약 테스트 의무가 귀속되는 마일스톤은 ADR-0014 Amendment의 단계별 gate 원칙을 따른다. 원 테스트 클래스는
채굴 anchor일 뿐 port 지시가 아니다. 같은 클래스에서 아래 행이 명명하지 않은 assertion은
자동으로 승격되지 않는다.

근거 표시는 다음 순서로 적용했다.

| 표시 | 승격 근거 |
|---|---|
| ① | Git-tracked 프로젝트 기록의 형식·가독·연속성을 지킨다. |
| ② | 깨지면 조용한 프로젝트 데이터 훼손이나 delegation 산출물 오귀속으로 이어진다. |
| ③ | `docs/traceability-matrix.md`가 해당 legacy test를 invariant에 직접 결속한다. |

## 승격 후보

### Git-tracked 프로젝트 기록 연속성

| ID | 계약명 | 근거 | 원 테스트 클래스 참조 | 새 시스템 재작성 방향 |
|---|---|---|---|---|
| PC-01 | 기존 `tasks.yaml`의 지원 필드·주석·newline/CRLF를 읽고, 한 task를 수정한 뒤에도 유효하고 사람이 읽을 수 있는 registry로 남긴다. | ①, ② | `TextSurgeryTests`, `TaskCliTests`, `TaskRegressionTests`, `AcceptFieldTests` | 역사 fixture를 legacy reader로 읽고 canonical task store를 거쳐 한 항목을 수정한 뒤 의미·주석·비대상 bytes 보존을 검증한다. |
| PC-02 | task ID·status·dependency·acceptance의 schema를 검증하며 malformed·duplicate·invalid mutation은 원본을 바꾸지 않는다. | ①, ② | `AcceptFieldTests`, `FrozenAcceptanceTests`, `TasksGateTests`, `ParkedTaskContractTests` | task domain validation과 compare-before-commit fault test로 재작성한다. owner provenance·dependency drift는 PC-15에서 검증하고 CLI argv·문구는 고정하지 않는다. |
| PC-03 | 동시 task mutation은 project lock 아래 원자적으로 commit되고 timeout·replace failure·symlink target에서는 외부나 원본에 쓰지 않는다. | ①, ② | `LockWiringTests`, `TaskCliTests`, `TaskRegressionTests` | task-store transaction에 lock contention, atomic-replace crash, symlink fault를 주입해 no-write를 검증한다. |
| PC-04 | actionability·dependency·parked 의미를 보존하고, archive는 오래된 terminal task만 누적 이동하며 남은 task가 직접·전이 의존하는 항목은 보존한다. | ①, ② | `NextActionableTests`, `TaskArchiveTests`, `TaskRegressionTests`, `ParkedTaskContractTests` | task domain property와 기존 `tasks.yaml`+archive transaction을 함께 검증해 무손실·dependency closure·재실행을 확인한다. |
| PC-05 | run close는 task 완료와 tracked projection 갱신 전체를 한 transaction으로 취급하며 어느 render/write 검사가 실패해도 부분 갱신을 남기지 않는다. | ①, ② | `RoundCloseTests` | task store와 projection writer 사이의 prepare/commit fault-injection test로 재작성한다. |
| PC-06 | `ROADMAP.md`와 generated SSOT view는 task 상태에서 결정적으로 재생성되고 stale·missing·extra view를 success로 보지 않으며 terminal/parked 구분을 잃지 않는다. | ①, ② | `RoundCloseTests`, `ParkedTaskContractTests`, `FrozenAcceptanceTests`, `CodexHookTests` | hook argv가 아니라 projection effect와 실패 시 기존 view 보존을 검증한다. |
| PC-07 | 기존 `PROGRESS.md` round heading·work log·archive pointer를 계속 읽고 역사 뒤에 새 close 기록을 append/archive할 수 있다. | ① | `RoundCloseTests` | 실제 역사 `PROGRESS.md`/archive fixture로 read→append→archive continuity를 새로 검증한다. ledger에는 backdated-heading 거부 외의 양성 생성 coverage가 없음을 전제로 새 fixture를 만든다. |
| PC-08 | close/reclose exposure publication은 기존 evidence를 덮어쓰지 않고 publication 실패가 tracked task mutation을 부분 commit하게 두지 않는다. | ② | `RoundExposureTests`, `RoundCloseTests` | non-overwrite와 transaction fault 의미만 새 projection 경계에서 검증한다. host-local path/schema/payload는 보존하지 않으며 cross-machine authority와 run ID·manifest 계약은 legacy에서 승격하거나 여기서 재결정하지 않는다. |
| PC-09 | review request는 round·target·narrative·resolved reviewer를 사람이 읽을 수 있게 render하고, 실제 rendered bytes의 digest와 회신이 명명할 exact generation에 결속된다. | ①, ②, ③(E-01) | `PacketPublicationTests`, `MarkerTests`, `BasePolicyTests` | ordinary Markdown round-trip과 protocol-lookalike 거부를 포함한 render→canonicalize→digest→publish contract test로 만들고 exact template bytes는 고정하지 않는다. |
| PC-10 | review binding은 완전한 sidecar로 원자적·배타적으로 추가되고 latest sequence만 판정 후보이며 corrupt latest를 건너뛰어 과거 binding을 승격하지 않는다. | ①, ②, ③(E-01, E-02) | `PacketPublicationTests`, `PendingReviewTests` | immutable generation store에 collision/crash/corrupt-latest fault를 주입하고 결과가 pending/unknown인지 검증한다. |
| PC-11 | feedback receipt는 원문 bytes와 bounded envelope를 보존하고, 완료는 body가 에코한 request digest에서 재파생하며 cache edit·file existence·실패한 reingest가 귀속이나 archive bytes를 바꾸지 못한다. | ①, ②, ③(E-01, E-02) | `IngestTests`, `PacketPublicationTests`, `PendingReviewTests` | anchored verbatim-body parser, cache tamper, reingest/event-correction rollback fault test로 receipt authority와 transaction을 검증한다. |
| PC-12 | pending projection은 exact latest request/binding/feedback 결속만 완료로 보고 손상·불일치는 해당 run만 `unknown`으로 격리한다. | ①, ②, ③(E-02) | `PendingReviewTests`, `IngestTests`, `PacketPublicationTests` | 여러 healthy/corrupt run fixture를 함께 읽어 stale fallback 0, healthy projection 중단 0을 검증한다. |
| PC-13 | PR review cycle/freeze evidence는 exact rendered digest generation에 결속되고 v1 legacy·v2 혼재, 동률·충돌·손상은 stale evidence를 새 evidence로 승격하지 않는다. | ①, ②, ③(E-01) | `MarkerTests`, `PacketPublicationTests`, `L3GapClosureAcceptanceTests` | canonical review reader와 legacy adapter를 분리해 version-skew·digest conflict·cross-owner corruption fixture로 재작성한다. |
| PC-14 | 기존 flat `docs/reviews/` request·binding·feedback·sidecar archive는 rename 없이 legacy evidence로 계속 읽히고, 새 writer가 그 bytes를 소급 수정하지 않는다. | ① | `MarkerTests`, `PacketPublicationTests`, `IngestTests`, `L3GapClosureAcceptanceTests` | ADR-0009의 legacy-adapter 경계에서 실제 역사 fixture read와 canonical next-write를 검증하되 filename 분해를 신규 identity 규칙으로 복제하지 않는다. |

### Registry mutation·delegation 산출물 안전

| ID | 계약명 | 근거 | 원 테스트 클래스 참조 | 새 시스템 재작성 방향 |
|---|---|---|---|---|
| PC-15 | worker job input은 owner의 task intent·acceptance·dependency를 고정하고 worker claim이나 준비 뒤 drift가 이를 바꾸지 못한다. | ②, ③(I-01, E-05) | `AcceptFieldTests`, `DelegatePacketTests`, `DelegatePacketDigestTests`, `DelegateVerdictTests`, `DelegateExpectAndCarrierTests` | accepted ADR의 job-input 경계에 owner fields와 digest를 결속하고 drift/worker-override refusal을 검증한다. schema·파일명은 재결정하지 않는다. |
| PC-16 | changed files, patch bytes, base/result SHA와 digest는 harness가 Git에서 계산하며 binary·non-UTF-8도 보존하고 post-verdict 교체는 거부한다. | ②, ③(I-03, E-07) | `DelegateRunTests`, `DelegateVerifyTests`, `L3GapClosureAcceptanceTests` | Git adapter property test와 patch tamper fault test로 `(base, patch bytes) → result` 결속을 검증한다. |
| PC-17 | snapshot·job 실행은 live worktree와 index를 바꾸지 않으며 apply는 unrelated user dirt를 보존하고 drift에서는 원자적으로 no-write한다. | ②, ③(I-05) | `DelegateSnapshotTests`, `DelegateApplyTests` | clean/dirty/staged/untracked fixture와 integration drift를 조합해 stash·silent commit·silent 3-way apply가 없음을 검증한다. |
| PC-18 | attempt, verifier evidence와 integration decision은 append-only이고 같은 시각·번호 충돌이나 retry가 기존 artifact를 덮어쓰지 않는다. | ②, ③(I-06, E-05) | `DelegateRunTests`, `DelegateVerdictTests`, `DelegateVerifyTests` | store의 unique identity와 append API에 collision/concurrent writer를 주입해 기존 bytes와 이력을 검증한다. |
| PC-19 | corrupt job record는 success로 해석되지 않고 해당 run에 격리되며 healthy run의 조회·projection을 중단시키지 않는다. | ②, ③(I-09, E-06) | `DelegateCorruptRecordTests`, `DelegateStatusJsonTests` | logical record corruption을 주입해 typed corrupt/unknown과 healthy isolation을 검증한다. artifact-reference 복구와 digest 재검증은 legacy가 덮지 않는 신규 E-06 의무다. |
| PC-20 | verifier는 worker·integration actor와 분리되고 검토 worktree를 수정하지 않으며 invalid/empty/failed output에는 verifier artifact를 발행하지 않는다. | ②, ③(I-02, I-04, E-07) | `DelegateVerifyTests`, `DelegateVerdictTests` | read-only verifier adapter와 artifact commit 경계에 mutation, timeout, malformed output fault를 주입한다. |
| PC-21 | integration decision은 owner criterion의 exact set과 해당 result digest의 verifier evidence에 결속되고 worker self-acceptance나 근거 없는 blocker override를 허용하지 않는다. | ②, ③(I-01, I-02, I-04, E-05, E-07) | `DelegateVerdictTests`, `DelegateApplyTests`, `L3GapClosureAcceptanceTests` | decision domain test에서 missing/extra criterion, wrong digest, wrong actor, unsupported override를 각각 typed refusal로 검증한다. |
| PC-22 | accept/apply는 실행 시점에 contract·decision·verifier digest와 base+patch 결과를 다시 검증하고 mismatch나 concurrent drift에서 project bytes를 바꾸지 않는다. | ②, ③(I-03, I-05, E-07) | `DelegateApplyTests`, `DelegateVerifyTests`, `L3GapClosureAcceptanceTests` | integration transaction 직전 tamper/CAS race를 주입해 atomic refusal과 unrelated user work 보존을 검증한다. |

### Invariant가 직접 결속한 추가 의미 계약

| ID | 계약명 | 근거 | 원 테스트 클래스 참조 | 새 시스템 재작성 방향 |
|---|---|---|---|---|
| PC-23 | 기존 `.waystone.yml`의 지원 설정은 계속 읽고 invalid 값은 쓰기 전에 거부하며, owner policy는 frozen base에서 읽어 head/local mutation이 CI·review requirement를 약화하지 못한다. | ①, ③(I-01) | `ConfigTests`, `BasePolicyTests` | legacy config adapter의 typed result와 planner의 base-policy authority를 검증하고 normalized dict·오류 문구는 고정하지 않는다. |
| PC-24 | 기존 프로젝트 도입·migration은 비파괴·멱등이고 atomic replace 직후 crash와 symlink에서도 loss·duplicate·외부 write 없이 재개한다. | ③(I-07) | `MigrationV2Phase2Tests` | legacy phase/path/schema는 버리고 `core/migrations`의 second-run no-op, crash-resume, symlink refusal property test로 재작성한다. previewable 동작은 legacy가 덮지 않는 신규 I-07 의무다. |
| PC-25 | 새 policy는 observing에서 시작하고 replay/evidence 없이 warning 또는 더 강한 단계로 승격되지 않는다. | ③(I-08) | `OverlayStoreTests`, `L2DPolicyMachineTests` | 새 policy state machine에서 transition guard를 검증하고 legacy JSON path·정확 threshold는 고정하지 않는다. |
| PC-26 | policy materialization은 명시적 consent와 audit 결속 전에는 일어나지 않으며 손상·권위 부재 입력은 transition이나 state bytes 변경을 만들지 않는다. | ③(I-08, I-09) | `L2DPolicyMachineTests`, `L2DAdversarialFindingTests` | consent store와 projection을 분리하고 degraded-input fault-injection으로 non-transition을 검증한다. |
| PC-27 | 지원하지 않는 execution·verifier entry·sandbox capability는 다른 실행 형태로 가장하지 않고 worker 시작 전에 typed refusal한다. | ③(I-11) | `DelegateProfileTests`, `DelegateVerifyTests`, `DelegateRunTests` | executor capability/preflight test에서 no-launch와 typed reason을 검증하고 legacy `failed-env` JSON·문구는 고정하지 않는다. |
| PC-28 | runner proof의 bounded 관측축과 config content가 같은 경우에만 기존 proof가 재사용되며 observed/unobserved 상태 변화는 재검증한다. | ③(E-03) | `CodexRunnerVerificationGateTests` | state-equivalent not-observed, config-content change, observed/unobserved transition fixture를 새 probe table에 둔다. checkout·machine·principal mismatch refusal은 legacy가 직접 덮지 않아 신규 E-03 fixture로 추가하며 local marker path/schema는 보존하지 않는다. |
| PC-29 | packet digest는 worktree relocation에 안정적이고, directory stat이 같아도 config content 변화는 runner proof를 무효화한다. | ②, ③(E-09) | `DelegatePacketDigestTests`, `CodexRunnerVerificationGateTests` | relocation-stable digest와 unchanged-stat/content-change test를 새 attribution adapter에 작성한다. 다른 incidental ambient 값의 authority 금지는 legacy가 덮지 않는 신규 E-09 의무다. |
| PC-30 | public handoff·report는 bounded하며 concrete backend나 내부 delta ID를 알아야만 다음 행동을 할 필요가 없다. | ③(I-12) | `ContractInjectTests`, `M2DocsTests` | semantic UX test로 필요한 public facts와 내부 용어 비노출을 검증하고 legacy 12행·1300자·정확 문구는 승격하지 않는다. |

## Legacy reference가 없는 신규 계약 의무

다음은 승격 후보가 아니라 invariant/accepted ADR에서 직접 새 테스트를 만들어야 하는 의무다.
비승격 또는 legacy ref 부재가 이 계약을 면제하지 않는다.

- I-10: minimal worker prompt와 bookkeeping protocol 비전달
- I-07 잔여: migration/adoption의 previewable 동작
- E-03 잔여: checkout·machine·principal 축 mismatch의 proof reuse 거부
- E-04: Git-tracked closeout authority와 cross-machine conflict 방향
- E-06 잔여: artifact-reference 판독 복구와 content digest 재검증
- E-08: positive liveness/exit evidence, 사유 있는 `unknown`, unknown에서 destructive resolution 금지
- E-09 잔여: hostname·cwd·mtime/inode·열거 순서와 filename 분해를 durable authority로 쓰지 않음
- ADR-0003 '취소, quiescence, cleanup 안전 계약' 절(계획 §3-9 유래): cancellation·quiescence·cleanup의 독립 fault 계약

`docs/traceability-matrix.md`가 I-10의 근접 증거로 언급한
`ImproveL2BAdversarialTests.test_f12_scope_is_structured_and_packet_text_is_never_mined`는 characterization
coverage가 아니므로 승격 근거로 세지 않는다.

## 명시적 비승격

아래는 빠뜨린 항목이 아니라 의도적으로 버리는 legacy 클래스 군/관측면이다. 승격 후보에 일부
클래스가 등장하더라도 그 클래스 전체가 아니라 위에서 이름 붙인 의미만 승격된다.

- **출력 comparator 전부:** human CLI의 정확 문구·help/diagnostic/traceback path, JSON field 순서와
  legacy schema 전체, timestamp·temporary path normalization 등 구 M1-A의 generic 출력 등급.
  단, PC-01의 tracked registry bytes, PC-09/PC-11의 digest-bound/verbatim bytes, PC-18의
  append-only artifact bytes처럼 계약 자체가 명시한 byte 보존은 남는다.
- **release·remote·배포 구현:** `ReleaseToMainTests`, `RemoteTests`, `IntegrationSmokeTests`,
  `CodexPluginContractTests`의 release script text, manifest 열거, remote pagination/argv와 smoke wiring.
- **machine-local 저장 배치:** `LockPrimitiveTests`, `StoragePathTests`, `DashboardLockingTests`,
  `WaystoneStorageCliTests`, `UvCacheTests`의 lock-marker JSON, directory 이름, cache path, host override와
  CLI rendering, 그리고 `ConfigTests`의 normalized dict/default rendering. PC-03·PC-29의 상위 safety와
  PC-23의 Git-tracked v1 config 의미만 남긴다.
- **CLI·dispatcher 내부 동작:** `TextSurgeryTests`, `NextActionableTests`, `LaneTests`,
  `ResumeStartHereTests`, `StatuslineTests`, `TaskReadNudgeTests`, `DelegateCliTests`,
  `DelegateJsonEventsTests`, `DelegateStatusJsonTests`, `DelegateFanoutTemplateLintTests`,
  `DelegateMainContractTests`의 argv parsing, exact exit/rendering, dispatch table, template source 검사.
  PC-01·PC-04가 명명한 task mutation/actionability 의미는 별도 새 test가 맡는다.
- **improve/analytics projection 형식:** `CclogParseTests`, `CclogLayoutTests`, `ImproveDiscoveryTests`,
  `ImproveTraceTests`, `ImproveSelfSessionTests`, `ImproveReviewsTests`, `ImproveAuditTests`,
  `ImproveDecideTests`, `ImproveMetricsTests`, `ImproveScopeTests`, `ImproveM1DefectTests`,
  `EvidenceTests`, `ImproveL2BTests`, `ImproveL2BAdversarialTests`의 local corpus layout, metric JSON,
  heuristics와 byte-stable report. 직접 승격된 invariant 의미는 별도 새 test가 맡는다.
- **legacy delegation mechanics:** `DelegateSnapshotTests`부터 `DelegateVerifyTests`까지의 DID/slug,
  `packet.yaml`·`contract.yaml`, record directory, branch/ref 이름, runner argv, fan-out template,
  JSON event/status schema와 exact state labels. PC-15~PC-22만 semantic rewrite한다.
- **unsafe discard·cleanup characterization:** `DelegateApplyTests`의 running/orphan discard,
  `DelegateCorruptRecordTests`의 corrupt-record discard, `DelegateRunTests`의 claim-only discard 경로는
  positive quiescence/effect reconciliation을 증명하지 않으므로 승격하지 않는다. E-08과
  ADR-0003 '취소, quiescence, cleanup 안전 계약' 절의 새 fault test로 대체한다.
- **host-local round exposure payload:** `RoundExposureTests`의 path/JSON과 session·policy/profile
  payload는 portability 계약으로 승격하지 않는다. PC-08의 non-overwrite·tracked rollback 의미만
  남기고 cross-machine authority는 신규 E-04 계약에서 직접 검증한다.
- **overlay·policy의 legacy 저장/임계값:** `OverlayStoreTests`, `OverlayRuleTests`,
  `BoundaryWarnTests`, `DelegateExposureOverlayTests`, `ReplayTests`, `L2DPolicyMachineTests`,
  `L2DAdversarialFindingTests`의 local delta schema/path, rule ID, 정확 threshold와 report 문구.
  PC-25·PC-26의 state/consent 의미만 남긴다.
- **migration mechanics:** `MigrationV2Phase1Tests`, `MigrationV2Phase2Tests`, `MigrationV2HookTests`,
  `MigrationTests`의 phase 번호, source/destination path, legacy profile/start-here schema, hook 설치와
  worktree 이동 방식. PC-24의 비파괴·멱등·crash/symlink 안전 성질만 새 kernel로 옮긴다.
- **hook·static-doc wiring과 과거 gap harness:** `M2DocsTests`, `CodexHookTests`, `CodexTraceTests`,
  `CodexVerifierTests`, `L2CGuardTests`, `L2CImproveFeedbackTests`, `L2CAdversarialFixTests`,
  `L3GapClosureAcceptanceTests`의 exact SKILL/AGENTS text, hook argv·manifest, legacy acceptance harness.
  각 PC 행에서 이 클래스 군을 근거로 명명한 의미만 새 경계에서 다시 쓴다.
- **review transport 세부:** `MarkerTests`, `MergeGateTests`, `PacketPublicationTests`, `IngestTests`,
  `PendingReviewTests`, `FrozenAcceptanceTests`의 GitHub REST pagination, bot regex, exact warning/CLI
  text와 flat filename parsing 구현. PC-09~PC-14의 digest·receipt·history 계약만 남긴다.
