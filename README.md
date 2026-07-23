# Waystone

Waystone is an intent control plane for agent-assisted development. It preserves the difference
between committed direction, working hypotheses, open questions, staged execution evidence, and
accepted objective progress.

## Canonical surfaces

- `PROJECT_BRIEF.md` is the project-frame authority; `.waystone.yml` uses `brief:`.
- `waystone brief check|show|adopt` checks, reads, or owner-adopts the frame.
- `waystone run start`, `waystone run resume`, and `waystone run close` operate one typed WorkBrief
  through an `explore`, `evaluate`, or `promote` stage.
- `waystone run context show|provide` makes additional context an explicit, typed exchange.
- `waystone run status`, `waystone run watch`, and `waystone run cancel` expose or control one run;
  `waystone run actions next|submit` is the carrier/user action transport.
- `waystone review ingest|validate|disposition|materialize` keeps review claims separate from
  validation, disposition, and selected work. `waystone review attach` binds ingested reviewer
  evidence to an exact promotion lineage.
- `waystone status` projects objective, active stage, waiting context, OutcomeDelta, advisory, and
  audit counts in that order; it accepts `--project` and `--json`.

The `run` skill writes semantic YAML rather than protocol identifiers. With
`waystone run start --work-brief-draft`, deterministic code binds that draft to current project,
profile, lineage, and verification authority before dispatch. The corresponding
`waystone run close --outcome-draft` path binds a semantic outcome draft to the run. Models supply
meaning; scripts assemble and validate the canonical protocol.

`ideate` is one skill with two modes: framing when no brief exists and realignment when one exists.
Its output is always provisional. Adoption requires the typed `waystone brief adopt` gate. The
other installed workflow skills are `improve`, `init`, `review`, `run`, and `status`.

## v1 execution scope

Waystone v1 staged execution supports external Codex workers and evaluators only. The profile schema
declares `in-session`, `subagent`, and `external` execution categories, but the staged engine does
not yet implement in-session or subagent carriers. Canonical routing based on context-transfer cost
is also not implemented, so the declared categories must not be read as three supported runtimes.

## Authority boundaries

The worker receives semantic context and provenance, not harness bookkeeping. A worker result is a
proposal. Independent evidence is required for evaluate/promote claims. Review findings are claims,
not automatic tasks or progress. Only a confirmed validation and an explicit disposition may
materialize selected work.

The current trust boundary is one solo developer on a local machine. Claude Code and Codex may use
the same canonical project records, while active runtime authority and locally addressed evidence
remain within that project and machine. Multi-machine evidence sharing is a future extension, not a
current execution guarantee.

The following transitions are never automatic: hypothesis → requirement, confirmed finding → task,
probe → permanent test, and coordinator summary → owner authority.

## Assurance and trust kernel

External evaluation and promotion verification run from the exact candidate materialization. Their
launch records bind the candidate OID, root fingerprint, and frozen run specification, and the
materialization is checked around execution.

Promotion authority exists only in published store/CAS artifacts. Apply reloads the published
verifier, review, and decision evidence instead of treating an in-memory return value as authority.
A semantic verifier rejection is terminal for that candidate; retry requires a new candidate or an
explicit owner ruling.

Review disposition revalidates its objective against the current committed brief, including fact
digest and binding, and refuses superseded authority as `objective-superseded`. Public run failures
use an envelope with a typed code and safe, non-empty detail. The code/detail boundary distinguishes
preflight failure, expected authority or contract refusal, and unclassified internal failure; the
last is sanitized to avoid exposing paths, stack traces, or secret-bearing exception text.

## Status

The 0.13 intent-control-plane redesign is in final development and release preparation after
external architecture review cycles. `PROGRESS.md` is the live implementation record, and
`ROADMAP.md` is the current task and sequencing view.

## Installation

Install the plugin for the host you use, then invoke the matching skill (`/waystone:init` or
`$waystone:init`). The CLI launcher is available as `bin/waystone` and `bin/waystone-codex`.

## Verification

```bash
uv run scripts/tests/run_tests.py
```

The suite intentionally contains the preserved trust kernel and focused 0.13 control-plane tests;
retired delegate/round/SSOT compatibility tests are not part of the suite.
