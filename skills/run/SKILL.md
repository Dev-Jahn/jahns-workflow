---
name: run
description: Orchestrate the canonical one-task run lifecycle through WorkBrief, context transfer, execution, close, and report.
argument-hint: "<task-id>"
allowed-tools: ["Bash", "Read", "Write"]
---

# waystone: run

Thin orchestration only; the CLI and runtime store own authority.

1. Propose `explore`, `evaluate`, or `promote` from the request and current brief. Treat an
   ambiguous stage as an owner decision, not a silent downgrade.
2. Write a semantic YAML draft with `lifecycle_stage`, `objective_fact_id`, `desired_delta`,
   `why_now`, current state, decisions (`fixed`/`worker_may_choose`/`requires_escalation`),
   constraints, non-goals, known
   failures, evidence expectations (`criterion_id`/`kind`/`text`), relevant references
   (`path`/`anchor`/`purpose`), and open questions. Use explicit `[]` for an intentionally empty
   list. For evaluate, add `evaluation_spec_path`; for promote, add Git-tracked
   `promotion_records` paths (`regression_contract`/`supported_scope`/`accepted_risks`). Do not
   calculate ids, digests, bindings, or lineage.
3. Let the run ingress scaffold and validate the WorkBrief:

```bash
waystone run start <task-id> --work-brief-draft <file> [--stage <stage>]
```

4. If the run requests context, show it with `waystone run context show` and resume only after a
   typed response with `waystone run context provide`. Do not patch an existing attempt or reset
   its budget.
5. Write an outcome YAML draft containing only `kind`, `summary`, `evidence_refs`
   (`kind`/`reference_id`), `finding_refs`, and `rationale`; then close through the scaffold:

```bash
waystone run close <run-id> --outcome-draft <file>
```

Report the stage, evidence, OutcomeDelta, waiting context, and any refusal. Never turn a failed
promotion into explore success.
