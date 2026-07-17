# ADR-0001: `deterministic-workflow`의 carrier·귀속 의미론을 확정한다

- Status: accepted
- Date: 2026-07-17
- Round: —
- SSOT sections affected: 없음 — §8.3은 `dev_docs/waystone-0.7-0.9-design.md`의 절 번호(deterministic-workflow 실행 모드)이며, `SSOT.md`에는 §8이 존재하지 않는다 (2026-07-18 staleness 감사에서 좌표 정정)
- Tasks: decision/deterministic-workflow-carrier-semantics
- Provenance: 통합 설계안(`.claude/plans/waystone-plugin-harness-delegate-atomic-sunbeam.md` §3) 외부 리뷰 판정 **"Architecture approved, implementation changes requested"** 반영

## Context

waystone에는 `deterministic-workflow` 실행 모드가 profile 스키마·라우팅 정책(reasoning/independent-perspective/bounded-scope/independent-verification prefer)·설계 문서(`dev_docs/waystone-0.7-0.9-design.md` §8.3)에 이미 선언돼 있으나, **구체 캐리어가 명명되지 않은 공백**이 있었다. delegate가 CC 네이티브 Workflow(ultracode)를 모른 채 개발돼 역할이 겹쳤다. 이 결정은 conventions 문구 이상(backend 의미·fallback provenance 재정의)이므로 ADR로 확정한다.

확정 아키텍처는 3축 분리다:

| 축 | 정의 | 값 예 |
|---|---|---|
| **Role execution** | waystone상 작업 수행 형태. `deterministic-workflow`는 호스트 도구명이 아니라 "고정된 plan manifest를 입력으로 받아 정해진 순서·동시성·집계 규칙을 수행하는 orchestration procedure" | `deterministic-workflow` |
| **Host carrier** | 그 procedure를 실제로 실행하는 호스트 엔진 | `claude-workflow` (v1 유일) |
| **Leaf runner** | 실제 구현을 수행하는 transport·model·effort | `codex:gpt-5.6-sol` + effort `ultra` |

중심 명제(리뷰 승인): Workflow는 waystone delegate를 대체하지 않는다. main이 이미 결정한 여러 delegate leg를 운반·집계하며, 모든 구현 결과는 기존 evidence/verdict gate로 돌아온다.

## Decision

1. execution `deterministic-workflow` = **manifest 기반 orchestration procedure**로 정의한다(호스트 불문; 위 3축 표). 호스트 도구명이 아니다.
2. **carrier 축을 신설**한다. 귀속에 `carrier`(enum, v1 `claude-workflow`)와 `carrier_instance_id`(main/CLI 사전 생성 correlation ID)를 기록한다. 실제 host workflow run ID는 사후 개선 루프(cclog)에서 correlation ID와 조인하며, immutable packet에 사전 미지 값을 넣지 않는다.
3. **carrier 부재 호스트(Codex)에서 이 binding은 fail-loud**다. 산문 지시 기반 순차 실행을 deterministic-workflow로 기록하면 provenance 과장이므로 금지하고, 그 role을 명시적으로 rebind해 실제 binding대로 기록한다. `round close --route-note` 정확일치 게이트는 완화하지 않는다.
4. **backend 의미**: orchestrator의 deterministic-workflow binding backend = 절차를 소유·판단하는 세션 모델(현행 `claude:fable-5`). workflow 내부 기계 agent(leaf 조종)는 **clerk binding의 backend·effort를 차용**하며 별도 route-note 없이 절차의 일부로 orchestrator에 귀속된다. implementer leg는 자기 binding(external-runner)대로 packet에 독립 기록된다.
5. deterministic-workflow binding은 **effort 명시가 필수**다(모델·effort 추측 금지 원칙). `waystone delegate plan`이 fail-loud로 집행한다.
6. **effort 매핑**(waystone enum → CC Workflow `agent()`): `none|minimal|low → low`, `medium → medium`, `high → high`, `xhigh → xhigh`. `ultra`는 Claude carrier가 거부(fail-loud, 대체 금지 — CONVENTIONS의 기존 `ultra` 패턴과 동일)한다. CC `max`는 어떤 binding 값에도 대응하지 않으며 main 자체 분석 전용이다.

## Consequences

- carrier report는 non-authoritative pointer surface다. nontrivial 구현은 반드시 implementer(external-runner) → `waystone delegate run` → verdict 게이트를 경유하고, main은 디스크 record(`.waystone/delegations/<did>/`)에서 사실을 재파생한다.
- carrier/carrier_instance_id가 packet에 기록되므로 improve/cclog가 correlation 조인 키를 이미 보유한다. exposure.json 스키마 확장은 불필요하다.
- binding > 세션 실행 모드가 유지된다: ultracode ON은 캐리어 가용성일 뿐 rebinding이 아니며, `agent()` model/effort는 manifest(=profile binding 파생)에서만 도출된다.

## Alternatives considered

- **Codex 폴백을 "순차 host dispatch를 deterministic-workflow로 기록"** — provenance 과장이라 철회. carrier 부재 호스트는 fail-loud + 명시 rebind로 대체.
- **routing-note에 workflow run ID 기록** — 실행 전 알 수 없으므로 철회. 사전 생성 correlation ID + `--carrier`/`--carrier-instance` 필드로 대체.
- **effort `xhigh → max` 매핑**(리뷰 권고) — Workflow `agent()` effort enum에 `xhigh`가 실재하므로 enum 오인으로 판단, `xhigh → xhigh`로 확정. `max`는 main 자체 분석 전용.
