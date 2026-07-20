#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Contract tests for the I-10 minimal worker prompt."""
from __future__ import annotations

from support import *  # noqa: F401,F403

from waystone.runs.prompt import render_worker_prompt
from waystone.runs.spec import (
    DEFAULT_RETRY_POLICY,
    BaseSnapshotReference,
    FrozenJobInput,
    RunSpec,
)


REPORT_STANZA = """## Report (required)

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


class RunPromptTests(unittest.TestCase):
    @staticmethod
    def spec() -> RunSpec:
        return RunSpec(
            run_id="019b1f7e-7a00-7000-8000-000000000001",
            job_id="019b1f7e-7a00-7000-8000-000000000001:job",
            revision=1,
            readiness="frozen-ready",
            critic_disposition="critic-not-required",
            job_input=FrozenJobInput(
                task_id="fix/prompt-surface",
                title="Render the frozen worker intent",
                acceptance_criteria=(
                    "The goal and bounds remain verbatim.",
                    "No internal bookkeeping surface is projected.",
                ),
                scope=(
                    "waystone/runs/prompt.py",
                    "scripts/tests/test_run_prompt.py",
                ),
                dependencies=("DEBT-DEPENDENCY-ID-SENTINEL",),
                input_digest="sha256:" + "1" * 64,
            ),
            base_snapshot=BaseSnapshotReference(
                head="a" * 40,
                reference_id="base-snapshot:fixture",
                digest="sha256:" + "2" * 64,
                size=1,
            ),
            retry=DEFAULT_RETRY_POLICY,
            review_decision=None,
            run_spec_digest="sha256:" + "3" * 64,
        )

    def test_renders_the_four_allowed_components_from_frozen_input(self):
        spec = self.spec()

        prompt = render_worker_prompt(spec)

        self.assertIn("## Goal\n\nRender the frozen worker intent", prompt)
        self.assertIn(
            "## Bounds\n\n"
            "- waystone/runs/prompt.py\n"
            "- scripts/tests/test_run_prompt.py",
            prompt,
        )
        self.assertIn(
            "## Acceptance criteria\n\n"
            "1. The goal and bounds remain verbatim.\n"
            "2. No internal bookkeeping surface is projected.",
            prompt,
        )
        self.assertIn(REPORT_STANZA, prompt)

    def test_full_text_contains_only_the_four_allowed_blocks(self):
        spec = self.spec()
        allowed_blocks = (
            "## Goal\n\nRender the frozen worker intent",
            "## Bounds\n\n"
            "- waystone/runs/prompt.py\n"
            "- scripts/tests/test_run_prompt.py",
            "## Acceptance criteria\n\n"
            "1. The goal and bounds remain verbatim.\n"
            "2. No internal bookkeeping surface is projected.",
            REPORT_STANZA,
        )
        expected = """## Goal

Render the frozen worker intent

## Bounds

- waystone/runs/prompt.py
- scripts/tests/test_run_prompt.py

## Acceptance criteria

1. The goal and bounds remain verbatim.
2. No internal bookkeeping surface is projected.

## Report (required)

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
this report through labeled as your claim, and an independent verifier checks it.
"""

        prompt = render_worker_prompt(spec)

        self.assertEqual(prompt, expected)
        remainder = prompt
        for block in allowed_blocks:
            self.assertEqual(prompt.count(block), 1)
            remainder = remainder.replace(block, "", 1)
        self.assertEqual(remainder.strip(), "")

    def test_omits_debt_fields_dependency_status_and_internal_surfaces(self):
        spec = self.spec()
        # Frozen RunSpec has dependency IDs but no legacy debt fields or dependency statuses.
        # Attach adversarial extras deliberately: the renderer must not mine undeclared attrs.
        debt_values = {
            "status": "STATUS-DEBT-SENTINEL",
            "milestone": "MILESTONE-DEBT-SENTINEL",
            "round": "ROUND-DEBT-SENTINEL",
            "anchor": "ANCHOR-DEBT-SENTINEL",
            "routing_note": "ROUTING-NOTE-VALUE-SENTINEL",
            "dependency_statuses": {
                "DEBT-DEPENDENCY-ID-SENTINEL": "DEPENDENCY-STATUS-SENTINEL",
            },
            "internal_bookkeeping": (
                "tasks.yaml",
                "ROADMAP",
                "PROGRESS",
                ".waystone/",
                "round close",
                "exposure",
                "overlay",
                "registry command",
            ),
        }
        for name, value in debt_values.items():
            object.__setattr__(spec, name, value)

        prompt = render_worker_prompt(spec)
        normalized = prompt.casefold()

        for debt_surface in ("status", "milestone", "round", "anchor", "routing_note"):
            with self.subTest(debt_surface=debt_surface):
                self.assertNotIn(debt_surface, normalized)
        for sentinel in (
                "STATUS-DEBT-SENTINEL",
                "MILESTONE-DEBT-SENTINEL",
                "ROUND-DEBT-SENTINEL",
                "ANCHOR-DEBT-SENTINEL",
                "ROUTING-NOTE-VALUE-SENTINEL",
                "DEBT-DEPENDENCY-ID-SENTINEL",
                "DEPENDENCY-STATUS-SENTINEL"):
            with self.subTest(sentinel=sentinel):
                self.assertNotIn(sentinel, prompt)
        for internal_surface in (
                "tasks.yaml", "roadmap", "progress", ".waystone/", "round close",
                "exposure", "overlay", "registry"):
            with self.subTest(internal_surface=internal_surface):
                self.assertNotIn(internal_surface, normalized)

    def test_routing_note_value_channel_is_not_projected(self):
        spec = self.spec()
        sentinel = "ROUTING-NOTE-UNIQUE-VALUE-7B98E2"
        object.__setattr__(spec, "routing_note", sentinel)

        self.assertNotIn(sentinel, render_worker_prompt(spec))

    def test_rendering_is_byte_identical_for_the_same_run_spec(self):
        spec = self.spec()

        first = render_worker_prompt(spec).encode("utf-8")
        second = render_worker_prompt(spec).encode("utf-8")

        self.assertEqual(first, second)
