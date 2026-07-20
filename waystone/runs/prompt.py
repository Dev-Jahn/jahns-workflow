"""Minimal worker prompt rendering from one frozen RunSpec."""
from __future__ import annotations

from waystone.runs.spec import RunSpec


_REPORT_STANZA = """## Report (required)

Before you finish, write a report to `WAYSTONE_REPORT.yaml` at the worktree root with this shape:

```yaml
verification:            # commands you actually ran to check your work
  - {cmd: "<command>", rc: <exit code>, summary: "<what it showed>"}
limitations:             # what you could not verify or complete
  - "<limitation>"
risks:                   # anything a reviewer should double-check
  - "<risk>"
escalations:             # out-of-scope problems you noticed but did not touch
  - "<escalation>"
```

Report only what you actually did. Do not invent verification you did not run — the harness carries
this report through labeled as your claim, and an independent verifier checks it."""


def render_worker_prompt(spec: RunSpec) -> str:
    """Render only frozen worker intent and the allowed reporting contract."""
    job_input = spec.job_input
    blocks = (
        f"## Goal\n\n{job_input.title}",
        "## Bounds\n\n" + "\n".join(f"- {item}" for item in job_input.scope),
        "## Acceptance criteria\n\n" + "\n".join(
            f"{index}. {criterion}"
            for index, criterion in enumerate(job_input.acceptance_criteria, 1)
        ),
        _REPORT_STANZA,
    )
    return "\n\n".join(blocks) + "\n"


__all__ = ["render_worker_prompt"]
