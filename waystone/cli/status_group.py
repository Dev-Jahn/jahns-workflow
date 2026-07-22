"""Objective-first `waystone status` CLI core."""
from __future__ import annotations

import json
from pathlib import Path

from waystone.core import WorkflowError
from waystone.project.context import resolve_project_context
from waystone.runs.engine import ReadOnlyStoreUnavailable, open_read_only_store
from waystone.runs.observe import (
    project_status_json,
    project_status_projection,
    render_project_status,
)
from waystone.runs.transport import ActionPlanRefusal, encode_envelope, failure_envelope


def _arguments(argv: list[str]) -> tuple[Path, bool]:
    project = Path.cwd()
    as_json = False
    index = 0
    seen = set()
    while index < len(argv):
        option = argv[index]
        if option == "--json":
            if option in seen:
                raise ActionPlanRefusal("--json may be passed only once")
            seen.add(option)
            as_json = True
            index += 1
            continue
        if option == "--project":
            if option in seen or index + 1 >= len(argv):
                raise ActionPlanRefusal("--project requires exactly one value")
            seen.add(option)
            project = Path(argv[index + 1])
            index += 2
            continue
        raise ActionPlanRefusal(f"unexpected status argument {option!r}")
    return project, as_json


def _failure(error: BaseException) -> int:
    if isinstance(error, WorkflowError):
        code = getattr(error, "code", type(error).__name__)
        error = ActionPlanRefusal(f"{code}: {error}")
    exit_code, envelope = failure_envelope(error)
    print(encode_envelope(envelope).decode("utf-8"))
    return int(exit_code)


def main(argv: list[str]) -> int:
    """Render project direction first and operational counts only under Audit."""
    try:
        project, as_json = _arguments(argv)
        context = resolve_project_context(project)
        try:
            with open_read_only_store(context.canonical_root) as store:
                status = project_status_projection(context.canonical_root, store)
        except ReadOnlyStoreUnavailable as error:
            if (context.canonical_root / ".waystone" / "state.db").exists():
                raise error
            status = project_status_projection(context.canonical_root)
        if as_json:
            print(json.dumps(
                project_status_json(status), ensure_ascii=False,
                sort_keys=True, separators=(",", ":")))
        else:
            print(render_project_status(status))
        return 0
    except (WorkflowError, OSError, ValueError, TypeError) as error:
        return _failure(error)


__all__ = ["main"]
