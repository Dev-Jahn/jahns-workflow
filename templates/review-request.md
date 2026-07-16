# Review Request — {round-id}

The reviewer has the repository via git. This is a domain/code review, not a workflow audit —
keep the waystone harness out of scope unless asked.

- Project / Branch: {project} / {branch}
- Reviewing: {40-lowercase-hex-closeout-sha}   (diff against {40-lowercase-hex-base-sha-or-(root)})

<!-- Keep the Reviewing field on exactly one line with the literal spacing shown above. -->

## What changed and why

{Not a file list — the intent. What problem this round attacked, what structure you chose, and
why you believe it is right.}

## Read these first

1. `{path}` — {why it is load-bearing}
2. `{path}` — {why}

## Claims to attack

{Numbered, falsifiable. What you assert is true and want the reviewer to try to break — the
math / model / kernel / physics invariant, the thing a passing test could still get wrong.}

## Evidence already produced (mine — inspect, don't trust)

| Claim | Command / artifact | My reading | Where it lives |
|---|---|---|---|
| {claim} | `{command}` | {your interpretation} | `{path/to/log or PROGRESS §}` |

## Known weak spots

{Where you are least confident — the proof gap, the GPU-only race, the dynamics you are unsure
you read right, the boundary condition you hand-waved.}

## Domain lens

{The angle that matters most this round. See `docs/review-profile.md` for the project's standing
review priorities, if present.}

## Out of scope

{What not to review this round.}

## Response wanted

Start the reply with this block (replace values; key case/order/spacing and a Markdown fence are
optional; extra keys are preserved). Echo the `Reviewing` target, alone or as a 12–40 hex
`base-target` range; missing/damaged values stay unknown, and no model/target means ordinary prose:
```text
model: gpt-5.6-sol
effort: high
review-target: a1b2c3d4e5f6-a2b3c4d5e6f7
```

Major / critical issues only. For each: a concrete failure mechanism and where you confirmed it.
Separate confirmed findings, open domain questions, and residual risks from unavailable
GPU / data / environment.
