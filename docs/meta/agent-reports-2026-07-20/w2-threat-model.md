# w2 threat model — ADR-0013 completion report

## Outcome

M0-B가 요구한 최소 operational threat model을 accepted ADR-0013으로 완결했다. 마스터 경계,
ADR-0007의 DB 배치, ADR-0011의 same-machine linked-worktree identity, E-03의 config fingerprint 범위는
재결정하지 않고 흡수했다. 실공백이던 DB/artifact permission·symlink fail direction, delegated child
environment allowlist, lease/lock principal을 우발 손상 방어의 연장선으로 확정했다.

변경 파일은 다음 둘뿐이다.

- `docs/adr/ADR-0013-operational-threat-model.md` 신규
- `dev_docs/0.12.0-refactor-plan.md` M0-B Exit 한 줄의 ADR-0013 pointer

## 자체 대조표 — 계획서 :602-604 전 축

| # | 계획 축 | ADR-0013 결정/흡수 anchor | 보호·비보호·fail direction | 판정 |
|---|---|---|---|---|
| 1 | 보호 대상 / 의도적 비보호 대상 | `보호 경계` :23-33, 흡수 표 :39, 축별 표 :48 | 우발 손상 보호; 의도적 local tampering·multi-user·namespace 비보호; typed refusal/unknown을 success로 축약 금지 | PASS |
| 2 | DB permission | 축별 표 :49, 상세 :59-71 | 생성 mode와 owner/write 의미 검사; `unsafe_state_permissions`; auto chmod/chown/relocation 금지 | PASS |
| 3 | artifact permission | 축별 표 :50, 상세 :59-71 | staging/finalized 권한 분리; `unsafe_artifact_permissions`; leaf 결함은 E-06에 따라 해당 run 격리 | PASS |
| 4 | shared checkout | 흡수 표 :41, 축별 표 :51 | ADR-0011 project/checkout identity와 refusal을 그대로 흡수; multi-user shared checkout은 비보호 | PASS |
| 5 | symlink | 축별 표 :52, 상세 :73-91 | engine-owned subtree만 no-follow/containment; DB/root/leaf별 typed code; follow·unlink·replace·fallback 금지 | PASS |
| 6 | config fingerprint 범위 | 흡수 표 :42, 축별 표 :53 | E-03 exact-match와 not-observed 동등을 재결정하지 않음; 재probe 불가는 `runner_probe_unavailable` | PASS |
| 7 | env 전달 | 축별 표 :54, 상세 :93-116 | empty map + closed allowlist; undeclared ambient env 차단; `child_env_required_missing`/`child_env_not_allowed` | PASS |
| 8 | lease/lock principal | 축별 표 :55, 상세 :118-144 | engine-owned claim incarnation과 live OS lock handle; mismatch/unknown/busy typed refusal; expiry·PID·lockfile 추정 금지 | PASS |

Inventory 결과: **8/8**. DB와 artifact permission을 별도 행으로 세어 계획서 열거를 빠짐없이 대조했다.

## 기존 권위와의 정합성

| 권위 | 대조 결과 |
|---|---|
| plan §9 ruling 2 (:838-842) | :23-33에서 동일 보호/비보호 경계를 흡수하고 signature·seal·hardened namespace를 명시적으로 기각했다. 모순 0. |
| ADR-0007 | DB 위치·unsupported filesystem·명시 relocation 제안·silent fallback/journal 강등 금지를 :40에서 유지했다. permission/symlink refusal이 auto relocation을 유발하지 않는다. 모순 0. |
| ADR-0011 | canonical project DB와 linked checkout identity, mapping/mutation refusal을 :41/:51/:73-77에서 유지했다. user checkout 전체 symlink 금지를 만들지 않았다. 모순 0. |
| E-03 | :42/:53은 exact-match 재사용 범위와 not-observed 상태 동등을 그대로 인용한다. E-03의 `principal` 의미를 lease principal로 재정의하지 않는다(:120-123). 모순 0. |
| E-06 | artifact root 결함과 individual leaf 결함을 분리해 leaf logical damage는 해당 run으로 격리한다(:50/:82-86). 모순 0. |
| ADR-0002·ADR-0003 / E-08·E-09 | owner token+fence+CAS, supervisor telemetry, lease expiry 비증명, ambient PID/hostname/cwd 비소유권을 유지한다(:118-144). 모순 0. |

초안 독립 감사가 E-03 principal 과잉 해석과 일부 typed reason 공백 2건을 지적했다. 둘 다 수정한 뒤
재감사 결과는 `PASS — 남은 필수 이슈 없음`이었다. 새 invariant 제안은 필요하지 않다. ADR-0013은
I-09와 E-06/E-08/E-09의 기존 fail-toward-verification을 operationalize한다.

## Verification evidence

축 inventory:

```bash
adr=docs/adr/ADR-0013-operational-threat-model.md; count=0; for term in '보호 대상' 'DB permission' 'Artifact permission' 'Shared checkout' 'Symlink' 'Config fingerprint' 'Delegated child env' 'Lease·lock principal'; do rg -F "$term" "$adr" >/dev/null || exit 1; count=$((count + 1)); done; echo "axis inventory=$count/8"
```

결과: `axis inventory=8/8`, rc=0.

변경 범위와 whitespace:

```bash
git diff --check 8392d5afe440b5073afd0adb7fcde1a958f9a7bc 3087f6a5a35d91645223245b893a39dc95b5125d
git diff --name-only 8392d5afe440b5073afd0adb7fcde1a958f9a7bc 3087f6a5a35d91645223245b893a39dc95b5125d
git diff --numstat 8392d5afe440b5073afd0adb7fcde1a958f9a7bc 3087f6a5a35d91645223245b893a39dc95b5125d
git status --porcelain
```

결과: rc=0; 두 허용 파일만 존재; plan `1 insertion / 1 deletion`, ADR `163 insertions`; worktree clean.

Full suite (지시 원문, pipeline 없이 rc 직접 캡처):

```bash
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite.log 2>&1; echo "suite rc=$?"
```

결과: `Ran 833 tests in 139.882s`, `OK`, `suite rc=0`.

VERDICT: PASS — ADR-0013이 M0-B threat-model 8축을 완결했고 기존 권위와 모순 0, full suite green
COMMITS: 3087f6a5a35d91645223245b893a39dc95b5125d
HOTFILES: dev_docs/0.12.0-refactor-plan.md M0-B Exit(:613) 한 줄만; review.py/common.py/run_tests.py 미접촉
VERIFIED: axis inventory 8/8 rc=0; independent contract reaudit PASS; git diff --check rc=0; full suite 833 tests OK rc=0; worktree clean
NOT-RUN: waystone CLI (명시 금지); code RED-first/targeted code tests (docs-only, 해당 없음); push (명시 금지)
