<!-- waystone feedback: the body below is the reviewer reply VERBATIM (byte-exact copy via `waystone review ingest`) — do not edit it; a triage skeleton is appended beneath it. -->
round: 2026-07-20-fleet-fix-wave
reviewer: codex:gpt-5.6-sol
reviewer-effort: ultra
review-target: 197b2cfa643f16188111e68a2c2f2255efd481c7
reply-metadata-json: {"metadata":{"effort":"ultra","model":"codex:gpt-5.6-sol","request-digest":"sha256:59648bf7f61dcf1abe669dcd42bb6168346dfb0082894b934f0279f81349d0cb","review-target":"197b2cfa643f16188111e68a2c2f2255efd481c7"},"narrative_digest":"sha256:09b6dce54bc54f25ccb75b16b247c0116c6837c0ad1de8b895342137427f0bae","rendered_request_coverage_reason":null,"rendered_request_digest":"sha256:59648bf7f61dcf1abe669dcd42bb6168346dfb0082894b934f0279f81349d0cb","rendered_request_digest_matches":true}
ingested: 2026-07-20
source: /tmp/review.md
verbatim-bytes: 13556

---

model: codex:gpt-5.6-sol
effort: ultra
review-target: 197b2cfa643f16188111e68a2c2f2255efd481c7
request-digest: sha256:59648bf7f61dcf1abe669dcd42bb6168346dfb0082894b934f0279f81349d0cb

# Verdict

REJECT — confirmed findings 5건: blocker 1, major 4.

전체 테스트 스위트의 rc=0은 재현했지만, 아래 결함들은 기존 green gate가 검사하지 않는
권위·이력·read-only 경계에 있다. 따라서 이 target의 수리·검증 주장을 그대로 승인할 수 없다.

# Confirmed findings

## WS-GPT-101 — 닫힌 test inventory를 누락된 characterization coverage로 오인해 CDX-2를 강등했다

- severity: blocker
- commit: 197b2cfa643f16188111e68a2c2f2255efd481c7
- confirmed at: docs/meta/agent-reports-2026-07-20/m0-exit-adjudication.md:16-20;
  docs/porting-ledger.md:3-18; docs/invariants.md:25,38-40;
  docs/traceability-matrix.md:25; dev_docs/0.12.0-refactor-plan.md:619-624

실패 메커니즘: adjudication은 SHA-pinned porting ledger와 run_tests.py의 inline fixture를
“닫힌 특성화 manifest”로 간주해 CDX-2를 blocker에서 minor로 내렸다. 그러나 ledger는 기존
828 test method의 보존/재작성 inventory일 뿐이고, I-10을 결속한 행은 한 건도 없다.
권위 matrix도 I-10의 세 검증 칸을 모두 TODO(M1)로 두고, 인접 test가 minimal worker prompt를
단언하지 않는다고 명시한다. docs/invariants.md:25는 I-10에 characterization을 요구하고
:38-40은 연결되지 않은 행을 이관 완료로 보지 않는다.

따라서 M1-A가 prompt adapter를 기계적으로 옮기는 과정에서 bookkeeping protocol을 모델
prompt에 노출해도 현재 pinned suite와 ledger는 계속 green일 수 있다. 별도 fixture directory가
필수인지와 무관하게, 필수 계약 하나가 실제로 관측되지 않는다는 반례다. 이는 M0-C exit의
“black-box observable contract/legacy fixture 실물 + 핵심 flow observable” 조건을 충족하지
못하므로 M1-A 진입을 막는 blocker다.

재현:

    rg -n 'I-10' docs/porting-ledger.md
    # observed: rc=1

    rg -n '^\s*- id: gate/characterization-baseline$' tasks.yaml
    # observed: rc=1

반면 docs/traceability-matrix.md:25에는 I-10이 명시적으로 gap으로 남아 있다. 전체 suite
rc=0은 이 공백을 반증하지 못한다.

## WS-GPT-102 — Ruff gate가 artifact가 아니라 ambient index의 version 문자열에 결속돼 false-green과 host-side code execution을 허용한다

- severity: major
- commit: ca20c62eaa420c52924802152416fedcdd4f2182
- confirmed at: .waystone.yml:18-20; scripts/tests/run_tests.py.lock:5-12;
  scripts/delegate.py:703-714,740-751,2147-2152;
  scripts/tests/run_tests.py:17158-17176,17188-17193,17211-17217;
  docs/adr/ADR-0012-verification-capability-preflight.md:48-59

실패 메커니즘: PyYAML은 URL/hash가 있는 lock에 결속되지만 Ruff는
uv tool run ruff@0.15.22 --version 한 줄뿐이다. _implementer_env()는 os.environ 전체를
복사하므로 UV_DEFAULT_INDEX 등 ambient UV source 설정을 그대로 신뢰한다. _run_env_prep()은
그 source가 준 console entry point를 runner sandbox 전에 host-side로 실행하고, 영속 기록에는
command와 rc만 남겨 source/artifact digest를 남기지 않는다.

이 라운드가 추가한 regression fixture 자체가 경로를 입증한다. test는 임의 Python 코드를
ruff 0.15.22 wheel로 포장하고, --version에는 올바른 문자열을, lint에는 실제 분석 없이
All checks passed를 반환하게 한다. 이를 UV_DEFAULT_INDEX로 주입한 뒤 offline suite와 lint를
성공으로 인정한다. 즉 잘못되거나 공격받은 ambient index는 같은 version의 임의 wheel을
prep 단계에서 실행하고, 그 bytes를 cache에 심어 이후 offline lint까지 false-green으로
만들 수 있다. “prepared cache 이후 offline”은 availability만 보장할 뿐 gate semantics나
artifact authenticity를 보장하지 않는다. 이는 ADR-0012:58-59의 declared input,
preparation/result digest, ambient cache/network 비의존 계약과 충돌한다.

재현:

    env -u FORCE_COLOR -u CLICOLOR_FORCE PYTHONDONTWRITEBYTECODE=1 \
      uv run scripts/tests/run_tests.py \
      UvCacheTests.test_declared_env_prep_warms_runner_cache_for_offline_suite_and_lint

관측값:

    Ran 1 test
    OK
    rc=0

여기서 OK가 바로 반례다. 위 line 17158-17176의 non-Ruff stub wheel이 실제 Ruff gate로
수용됐는데도 test가 성공했다.

## WS-GPT-103 — linked worktree의 list/show가 guard 없이 destructive lazy migration을 실행한다

- severity: major
- commit: 0c4ac61171141545cfe648a393ea083246fda174
- confirmed at: scripts/tasks.py:365-374,478-495,506-526;
  scripts/common.py:246-251,296-338,973-1018,1310-1399;
  docs/adr/ADR-0011-project-context.md:13-20,68-87

실패 메커니즘: 새 guard의 집합은 add/set/drop/archive뿐이다. list와 show도 공용
need_root()를 통과하지만 linked-worktree refusal은 호출하지 않고, project lock을 잡은 뒤
migrate_project_state(root)를 항상 호출한다. lock 획득 자체가 해당 checkout에
.waystone/.gitignore와 .waystone/lock을 만들고 쓴다. legacy state가 있으면
_migrate_file()은 destination으로 복사하면서 remove_source=True로 원본을 제거하고,
동일 loser도 unlink한다. 즉 nominal read가 linked checkout에 새 authority를 만들고
host legacy state를 이동/삭제한다.

ADR-0011:16-20은 linked cwd에서 registry 변경과 pre-0.9 migration이 실제로 두 번 발생한
원 사고라고 명시하고, :85-87은 linked read가 migration/repair 대신 typed refusal을
반환해야 한다고 규정한다. mutation-only guard는 tasks.yaml 오염 한 경로만 닫았을 뿐,
동일 사고의 migration 경로를 list/show에 남겼다.

현재 target의 control flow 재현:

    env PYTHONDONTWRITEBYTECODE=1 uv run --with pyyaml python - <<'PY'
    import contextlib, sys
    from pathlib import Path
    from unittest import mock
    sys.path.insert(0, 'scripts')
    import tasks
    with mock.patch.object(tasks, '_resolve_root', return_value=Path('/linked')), \
         mock.patch.object(tasks, '_refuse_linked_worktree_mutation') as guard, \
         mock.patch.object(tasks, 'hold_project_lock',
                           return_value=contextlib.nullcontext()), \
         mock.patch.object(tasks, 'migrate_project_state') as migrate, \
         mock.patch.object(tasks, 'load_tasks', return_value={}), \
         mock.patch.object(tasks, 'render_list', return_value=[]):
        rc = tasks.main(['list'])
    print('rc', rc, 'guard_calls', guard.call_count,
          'migration_calls', migrate.call_count)
    PY

관측값:

    rc 0 guard_calls 0 migration_calls 1

별도 temporary linked checkout 통합 재현에서도 list rc=0 뒤 linked checkout에
.waystone/.gitignore, .waystone/lock, .waystone/resume.md가 생겼고 legacy resume source는
없어졌다. 기존 mutation 표적 test는 이 read path를 검사하지 않는다.

## WS-GPT-104 — WS-only historical reader가 보존된 JW triage 21건을 투영과 live policy에서 소거한다

- severity: major
- commit: f8d873200cce00ee16bac782a874ef75412a7908
- confirmed at: scripts/improve.py:749-759,783-810,1260-1300,1744-1758;
  scripts/overlay.py:134-178; scripts/tests/run_tests.py:7740-7768,7817-7845;
  tasks.yaml:486-492; docs/reviews/2026-07-18-carrier-lanes-feedback.md:150-157

실패 메커니즘: rename commit은 improve의 historical triage reader regex까지
JW-GPT-\d+에서 WS-GPT-\d+ 전용으로 바꿨다. 그러나 task scope는 verbatim review history와
JW-GPT provenance를 보존하고 “신규 라운드부터” 새 prefix를 쓴다고 명시한다. target에
의도적으로 보존된 feedback 6개의 마지막 canonical triage table에는 기존 reader가 읽던
JW finding 21건이 있다. target reader는 이를 전부 조용히 건너뛴다.

그 결과 _project_review_rows()는 REAL/REJECTED verdict, taxonomy type, evidence pointer와
finding ID를 잃고 task-origin fallback만 남긴다. recurrence 계산은 REAL canonical type만
세므로 과거 recurrence가 사라진다. overlay rule 2도 같은 parser로 REJECTED task를 제외하므로,
old-prefix REJECTED finding의 open-major warning이 거짓으로 fire할 수 있다. tests는 dual-read
case를 추가하지 않고 historical fixture의 prefix 자체를 WS로 기계 변경해 회귀를 숨겼다.
새 writer/ingest를 WS-only로 바꾸는 것과 immutable historical reader를 WS-only로 만드는 것은
다른 호환 경계다.

base reader와 target reader의 동일 보존 corpus 비교:

    env PYTHONDONTWRITEBYTECODE=1 uv run --with pyyaml python - <<'PY'
    import subprocess, sys
    from pathlib import Path
    sys.path.insert(0, 'scripts')
    src = subprocess.run(
        ['git', 'show', 'f8d8732^:scripts/improve.py'],
        text=True, capture_output=True, check=True).stdout
    ns = {'__file__': str(Path('scripts/improve.py').resolve()),
          '__name__': 'before'}
    exec(compile(src, 'f8d8732^:scripts/improve.py', 'exec'), ns)
    import improve
    rows = []
    for path in Path('docs/reviews').glob('*-feedback.md'):
        text = path.read_text(encoding='utf-8', errors='replace')
        old = ns['_parse_triage'](text)
        if old:
            rows.append((len(old), len(improve._parse_triage(text))))
    print('files', len(rows), 'before_f8', sum(a for a, _ in rows),
          'at_target', sum(b for _, b in rows))
    PY

관측값:

    files 6 before_f8 21 at_target 0

## WS-GPT-105 — CDX-9 강등 후에도 E-09의 두 권위 원천이 상반된 구현을 허용한다

- severity: major
- commit: 197b2cfa643f16188111e68a2c2f2255efd481c7
- confirmed at: docs/meta/agent-reports-2026-07-20/m0-exit-adjudication.md:24-27;
  docs/invariants.md:3-6,36; dev_docs/0.12.0-refactor-plan.md:427-434,973-974;
  docs/adr/ADR-0009-review-artifact-addressing.md:69-91

실패 메커니즘: adjudication은 ADR-0009가 plan의 E-09를 supersede했다고 주장하면서도,
같은 행에서 plan §4 미동기화와 precedence 부재를 인정한 뒤 minor로 내린다. 실제 권위
문서는 그 supersession을 표현하지 않는다. docs/invariants.md:4-6은 E-01~E-09 문구의
권위 원천을 plan §4로 지목하고, plan:973-974는 자신을 구현 기준으로 선언한다. 그 plan의
E-09(:433)는 신뢰·귀속 판정의 근거로 파일명을 허용한다. 반면 accepted ADR-0009:69-91과
docs/invariants.md:36은 filename delimiter 분해를 legacy adapter 밖 owner identity 추론에
쓸 수 없고, 검증된 intrinsic identity의 주소/kind에만 쓸 수 있다고 제한한다.

따라서 M1 implementer가 명시된 구현 기준인 plan을 따르면 filename-derived owner
attribution을 다시 도입할 수 있고, ADR을 따르면 이를 거부한다. 이는 문구 정리 수준이 아니라
동일 입력에 상반된 attribution 결과를 허용하는 contract/authority split이다. 명시적
amend 또는 precedence가 권위 문서에 반영되기 전에는 major다.

재현용 대조 명령:

    nl -ba docs/invariants.md | sed -n '3,6p;36p'
    nl -ba dev_docs/0.12.0-refactor-plan.md | sed -n '433p;973,974p'
    nl -ba docs/adr/ADR-0009-review-artifact-addressing.md | sed -n '69,91p'

# Open domain questions

없음. Ruff artifact trust를 hash-lock, vendoring, 또는 명시적 source+digest 중 무엇으로 닫을지와
historical prefix dual-read의 sunset 시점은 구현 선택이지만, 현재 target의 결함 성립에는
영향을 주지 않는다.

# Claims not refuted at major severity

- probe proof v2→v3: schema mismatch가 exact comparison 전에 보존돼 v2는 한 번 재프로브되고,
  성공 후 v3로 교체된다. CodexRunnerVerificationGateTests 30건 rc=0이었으며 accepted
  threat model 밖의 의도적 local marker 위조 외 새 우회는 확인하지 못했다.
- reclose: .waystone.yml:22의 watermark는 f0f6f23add0c71adad2d2cb64d8bd6149db08e14이고,
  scripts/round.py:271-274가 generation 1의 base_sha를 우선한다.
  RoundExposureTests.test_same_round_reclose_preserves_original_previous_round_diff_base는 rc=0이었다.
- WAYSTONE_REPORT rename과 old config/home compatibility 삭제 자체에서는 별도 major를 찾지
  못했다. WS-GPT-104는 새 ingress가 아니라 보존된 historical evidence의 live reader 문제다.

# Verification and residual risks

- 허용된 전체 명령을 파이프 없이 직접 실행했다:

      env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py

  결과는 rc=0이었다. 위 findings는 green suite가 해당 경계를 검증하지 않는 이유를 각각
  구체적으로 제시한다.
- target HEAD는 197b2cfa643f16188111e68a2c2f2255efd481c7로 재확인했고 worktree는 clean이다.
- 금지된 waystone CLI는 실행하지 않았다. 실제 external Codex/Claude worker dispatch와
  물리적으로 network가 끊긴 cold machine은 실행하지 않았다. WS-GPT-102는 test의 temporary
  HTTP index와 임의 wheel로 동일 source-substitution 경로를 재현했다. GPU나 별도 data는
  이 리뷰에 필요하지 않았다.
- target에는 “독립 opus verifier 11/11”의 개별 회신이 없고 main이 작성한 adjudication
  표만 있다. 따라서 각 verifier의 독립성·반증 과정을 저장소 증거로 재감사할 수 없다.
  이는 별도 code finding으로 세지 않았지만 강등 판정의 residual evidence risk다.


---

<!-- waystone triage: BEGIN -->
## Finding triage (main 판정, 2026-07-20 — finding당 독립 opus verifier 반증 후 확정)

| finding | verdict | type | evidence / 처분 | task |
|---|---|---|---|---|
| WS-GPT-101 | REAL (blocker 유지) | verification | verifier 재확증: ledger I-10 행 0건·matrix 3열 TODO·prompt 최소성 단언 테스트 0건. 폐쇄 = 특성화 테스트 1개 + bookkeeping 경계(ADR-0014 Amendment 2 §5가 확정: WAYSTONE_REPORT stanza만 허용) | fix/i10-prompt-minimality-characterization |
| WS-GPT-102 | REAL (major→minor 강등) | verification | 메커니즘 재현(위조 ruff wheel이 offline gate rc=0). 단 동일 gap이 fix/delegate-env-prep-uv-cache 결과에 "비-범위"로 명시 이월돼 있고, ADR-0012 digest 결속은 M1 target이며, 잔여 공격은 coordinator ambient env 장악 필요 = 마스터 경계(의도적 로컬 조작) 밖. ruff 단독 hash-lock이 아니라 M1 VerificationPlan digest 결속에 편입 | fix/env-prep-toolchain-digest-binding |
| WS-GPT-103 | PARTIAL (major→minor 강등) | correctness | 파괴적 절반(legacy state 이동/삭제)은 이후 migration sunset이 해소 — remove_source/이동 코드 소멸 확인. 잔여 재현: 순수 read(list)가 linked checkout에 .waystone/{.gitignore,lock}을 생성하며 pre-0.9 거부보다 잔재 생성이 먼저 | fix/linked-read-lock-litter |
| WS-GPT-104 | REAL (major 유지, low-end) | correctness | 21→0 재현 확정(보존 feedback 6파일), fixture prefix 개서로 회귀 은폐 확인. 현 blast radius = improve 진단 표면 + overlay rule 2 휴면 경로(역사 REJECTED 0건이라 현재 미발화). 수리 정제: dual-prefix는 improve._FINDING_ID_RE만, review.FINDING_RE는 WS 유지, 실제 보존 파일 대상 회귀 테스트 | fix/improve-dual-prefix-archive-reader |
| WS-GPT-105 | REAL — 현 HEAD 기해소 | correctness | 대상 시점(197b2cf)에 실재. 이후 라운드(2026-07-20-ruling-execution)의 doc-sync가 정확히 이 지점을 수리: invariants:4-6 precedence 절 신설 + plan §4 E-09를 확정 문구와 문자 단위 일치(760 chars 비교 재검증) + ADR-0009 supersession note. 신규 task 불요 | — |

리뷰어 residual note(독립 verifier 회신이 repo에 없음)는 수용 — 이번 라운드부터 verifier 판정 요지를 triage에 병기하고 원 회신은 agent-reports 아카이브에 남긴다.
<!-- waystone triage: END -->
