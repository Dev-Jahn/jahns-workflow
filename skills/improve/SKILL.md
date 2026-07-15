---
name: improve
description: This skill should be used when the user runs "/waystone:improve" in Claude Code or "$waystone:improve" in Codex, asks for workflow-improvement suggestions, wants to analyze their Claude Code or Codex 작업 이력 (work history), requests 개선 제안 grounded in past sessions, or asks "how can I work better / where am I wasting effort across my projects". It mines the user's existing host session logs plus round/review evidence into deterministic facts, then presents evidence-grounded, provenance-labeled recommendations for the user to accept or reject — recording each decision without applying anything automatically.
argument-hint: "[--source DIR] [--user-wide] (optional — defaults to the current project)"
---

# waystone: improve

## Host contract

- Claude Code: invoke `/waystone:improve`; assign `$CLAUDE_PLUGIN_ROOT` to
  `WAYSTONE_PLUGIN_ROOT`, then run command examples with `waystone` from `PATH`.
- Codex: invoke `$waystone:improve`; from this skill's directory walk up two parents, assign that
  absolute path to `WAYSTONE_PLUGIN_ROOT`, then run command examples with
  `$WAYSTONE_PLUGIN_ROOT/bin/waystone-codex`.
- Resolve plugin resources from `$WAYSTONE_PLUGIN_ROOT`. Ask required choices through the host's native
  user-interaction mechanism; never require a specifically named question tool.

Produce an **advisory** workflow-improvement report for the current project, grounded in the
user's actual host session history and review evidence. Record each accept/reject. For the small
finite set of mapped recommendations, separately offer an observation-only overlay; never
create one without a second explicit consent. Repository materialization is a later, separately
consented action.

By default, run inside an initialized project and keep the analysis in that project. Use
`--user-wide` only when the user explicitly asks for cross-project user-habit analysis; that mode
does not require the current directory to be an initialized project.

In project mode, before delegating any interpretive subtask, resolve the profile with
`waystone paths --root <project-root>` and follow the chosen role's `execution`/`backend`.
`clean-subagent`, `forked-subagent`, `deterministic-workflow`, and `main-session` are dispatched by
the host and retain their role attribution in the report. `waystone delegate run` is only an
`implementer`/`external-runner` surface; do not send a clerk or reviewer binding through it or invent
another runner. User-wide mode has no single project profile, so keep interpretation in the main
session unless a specific registered project's binding is explicitly selected. The deterministic
collection commands below remain script work, not a model role.

## Step 1 — Collect the evidence (deterministic)

Run exactly one host-specific trace, then the other four projections in order with
the current host's launcher. Project mode is the default: it filters the host logs to the current
project and writes every artifact to `{project_root}/.waystone/improve/`.

```bash
waystone improve trace                 # Claude Code
waystone improve trace --host codex    # Codex

# Then, on either host:
waystone improve reviews
waystone improve evidence
waystone improve audit
waystone improve metrics
```

For explicit cross-project user-habit analysis, pass `--user-wide` to **every** command above.
That mode scans its user-wide scope and writes to `~/.waystone/improve/` (or the equivalent under
`$WAYSTONE_HOME`). Do not mix project-mode and user-wide artifacts in one run.

- The default source is host-specific: Claude Code uses `$CLAUDE_CONFIG_DIR/projects`, else
  `~/.claude/projects`; Codex uses `$CODEX_HOME/sessions`, else `~/.codex/sessions`.
  When the user names log directories, pass each through as repeatable `--source <DIR>` values.
  `--project <SLUG>` is available only with `--user-wide`. In project mode, `reviews` and
  `evidence` use only the current project; in user-wide mode they scan the registered projects.
  `audit` reads the output residence for the selected mode.
- Trace, reviews, evidence, and audit are free, deterministic, and re-runnable. `metrics` is also
  deterministic over its inputs but intentionally appends a timestamped longitudinal snapshot to
  `metrics.jsonl`. Do **not** re-implement any parsing or aggregation in the model.
- In user-wide mode, registered projects that `reviews` cannot reach are listed in
  `reviews_coverage.json` (not silently dropped) — carry that into the report's coverage note.
- If a prior `decisions.jsonl` already exists in the out dir, read it now — Step 4 needs it.

The audit step writes `facts.json`. Its named lens vocabulary, selected by scope and input
availability, is `main_direct_work`, `verification_debt`, `retry_loops`, `context_heavy`,
`delegation_pattern`, `delegation_opportunity`, `worker_scope_drift`, `warn_friction`,
`adaptive_feedback`, `error_landscape`, `env_unpreparedness`, `review_association`,
`finding_concentration`, `coverage_caveats`, and `evidence_link`. `env_unpreparedness` is separate
from the general error landscape. `finding_concentration` includes role, session-kind, project-area,
recurrence, remediation-round, and reopen views. Each emitted lens carries a rule id, provenance,
per-project numbers, and ≤5 evidence pointers.

`metrics` appends the current snapshot to `metrics.jsonl` and adds bounded aggregate/pointer facts to
`facts.json`. Read only the latest row and, when its comparison points to one, the previous
same-scope row. `facts.json` plus those bounded metric rows are your **only** sources of claims. If
trace found no
sessions (empty corpus) or audit reports `skipped_lenses`, say so plainly rather than inventing
findings — an empty history is a finding in itself.

## Step 2 — Interpret (model) — grounded and provenance-labeled

Read `facts.json` and derive recommendations. HARD rules (invariant #11):

- **No claim that isn't in facts.json or the bounded metric snapshot rows.** Every recommendation
  cites its lens, the numbers, and an evidence pointer (file + line). If the facts don't support it,
  don't say it.
- **Label evidence strength.** A recommendation built on an `inferred` lens is stated as
  "패턴상 추정(<rule-id>)"; one built on an `explicit` lens may be stated directly. Never present an
  inferred pattern as a certainty — that distinction is the user-facing form of invariant #11.
- **State report-confidence limits.** When `coverage_caveats` is non-trivial (parse errors, skipped
  files, partial tails, unknown record types), say so up front — the report is only as complete as
  the coverage allows.
- **Open with the machine-reported maturity framing in project mode.** Read
  `facts.json.maturity.stage` and
  `recommendation_strength`: Bootstrap and Calibrate are `soft`; Tune is `tuned`. The permissive
  `recommendation_tier: always-allowed` means maturity is an evidence-strength label, never a gate
  that suppresses supported recommendations. Do not manufacture personalization the data can't
  support. Tune does not promote a delta; the CLI still requires replay before warning. If maturity
  is degraded, report its `degraded_inputs` and do not imply a state transition occurred. User-wide
  mode has no single project maturity stage; do not manufacture one.
- **Report metrics without causal interpretation.** Cite the snapshot line, metric group/name,
  value, numerator/denominator, provenance, coverage, and `first_measured_version`. A comparison is
  only previous/current/delta, never proof that a policy caused the change. When provenance is
  `unavailable`, show its `unavailable_reason` and relevant coverage honestly; never turn null into
  zero or silently omit it.
- **Context discipline.** Read `facts.json`, the two small coverage jsons, and at most the latest and
  referenced previous same-scope `metrics.jsonl` rows ONLY. Never open
  `sessions.jsonl`/`delegations.jsonl` (multi-MB aggregates, not model input) and never open the raw
  transcripts behind evidence pointers — cite pointers as-is; the user inspects them on demand. If a
  fact seems to need more detail than facts.json carries, that is a lens-improvement finding to
  report, not a license to read the lake.

## Step 3 — Present and record (approval = RECORDING only)

For each recommendation, use the host-native interaction mechanism to get an explicit
accept/reject — one question per recommendation, never a generic wizard and never a batched
"apply this plan". Then record the decision deterministically:

```bash
waystone improve decide <rec-id> accept|reject [--title "..."] [--note "..."]
```

**Approval is recording.** It does not itself materialize or apply anything. When the user accepts a
recommendation, explain the concrete action. Then apply Step 3.5 only when the recommendation matches
the finite mapping below.

## Step 3.5 — Separately offer an observation-only overlay

For each accepted recommendation that matches this table, ask a separate host-native question:
"Store this as an overlay delta? It starts in observing (records only, no warning)." Ask once per
recommendation. A no does nothing; the Step 3 decision is already recorded.

| recommendation lens | overlay rule |
|---|---|
| `verification_debt/*` | `delegation-verification-evidence-v1` |
| `review_association/*` only for an unresolved severe-finding pattern | `round-close-open-findings-v1` |

This mapping is exhaustive. HARD: never map another lens or infer a new rule. On yes, fill every
flag from facts already read and use the CLI only:

```bash
waystone overlay add <rec-id> --rule <mapped-rule> \
  --summary "<observed numbers>" --pointers "<evidence pointer>" --from-rec <rec-id> \
  --expected-effect "<bounded expectation>" --risk "<known friction>" \
  --candidate-scope <project_candidate|user_candidate|unresolved>
```

Never write delta JSON directly. After creation, explain that the delta can be considered for warning
only after `waystone overlay replay <rec-id>` and then `waystone overlay promote <rec-id>`; do not run promotion
as part of improve.

For a `user_candidate`, user-wide promotion is a further, separate proposal. Ask first; on yes run:

```bash
waystone overlay promote-user <rec-id> --root <project-root>
```

The CLI derives observations from registered canonical projects; there is no `--observed-in` input.
If the evidence gate refuses promotion, show the refusal reason to the user and leave the project
delta intact. Never fabricate evidence, hand-edit a user delta, or weaken the candidate scope to get
past the gate.

Committed project policy is a different, consent-gated action. Only after replay and a separate user
decision to share the sanitized policy with the repository, record consent and materialize:

```bash
waystone consent record materialize accept \
  --context origin_delta_id=<rec-id> --root <project-root>
waystone overlay materialize <rec-id> --root <project-root>
```

`docs/waystone-policy.yaml` is left uncommitted. Show the resulting diff and commit it only after the
user reviews and approves that commit; behavioral evidence and local paths must never enter it.

When citing replay, report only that it "would have fired" and the estimated nuisance rate (which is
null while unlabeled). Never use the quality-claim words **prevented**, **improved**, or **benefit**.

## Step 4 — Suppress re-nagging (stable rec ids)

Mint each `rec_id` as `<lens>/<kebab-gist>` so the same recommendation keeps the same id across
cycles (e.g. `main_direct_work/heavy-solo-implementation`). Reuse the same gist for the same
underlying pattern — that stability is what makes the decision log meaningful. A recommendation the
user previously **rejected** (per `decisions.jsonl`) is re-surfaced only when the evidence is
*materially* new — new sessions, a higher rate, a newly affected project — not merely because you
re-ran the audit.

## Step 5 — Report

Report in the user's configured language. In project mode, lead with that project's maturity
framing; in user-wide mode, identify the report as a cross-project user-habit analysis. Then list
recommendations ordered by evidence strength and impact — each with its lens, numbers, evidence
pointer, and strength label — and note any coverage caveats. Include the current metric snapshot,
factual same-scope changes, and unavailable reasons. Close by summarizing what was accepted vs
rejected, which observation-only deltas, user promotions, or committed policy files (if any) were
separately created, and where the decision
log lives (`{project_root}/.waystone/improve/decisions.jsonl` by default or
`~/.waystone/improve/decisions.jsonl` with `--user-wide`).

End with the **next-step reminder**:

> Recommendations were recorded, not applied. Any separately accepted overlay starts in observing
> (records only, no warning); replay is required before warning promotion. Re-run
> `/waystone:improve` in Claude Code or `$waystone:improve` in Codex after a few more rounds;
> decisions are remembered, so the next report focuses on what's new.
