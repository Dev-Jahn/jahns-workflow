# Review request — round {round-id}

> Paste this whole packet to the external reviewer (e.g. web ChatGPT).
> Ingest the reply with `/jahns-workflow:review {round-id}`.

## Scope

- Project: {project} @ {branch}, commits {first}..{last} ({n} commits, {diffstat})
- Round goal: {one paragraph}
- Tasks shipped: {id — title, one per line}
- SSOT sections touched: {§-anchors, or "none"}

## What changed

{Concise narrative of the changes, written for a reviewer who has not seen the repo today.
Include key diffs/pseudocode inline where the reviewer needs them — the reviewer cannot
browse the repo.}

## Claims to verify (please attack these)

{Numbered list of the round's load-bearing claims, each stated falsifiably, e.g.
"1. The chunked path is numerically equivalent to the full path within fp32 tolerance for
nonzero initial state (gate/chunk-equivalence passed with max rel err 3e-7)."}

## Known weak spots

{Where the implementer is least confident. Blind spots of the current test ladder.}

## Questions

{Specific questions for the reviewer, numbered.}
