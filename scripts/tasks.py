#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Compatibility adapter for the structured task-registry CLI."""
from __future__ import annotations

import sys
from pathlib import Path

_bootstrap_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _bootstrap_root)

_waystone_preloaded = "waystone" in sys.modules
import waystone.project.tasks_cli as _tasks_owner  # noqa: E402

from waystone.project.tasks_cli import (  # noqa: E402, F401
    __doc__,
    ACCEPT_REJECT_MSG,
    ARCHIVE_KEEP,
    ARCHIVE_NAME,
    ARCHIVE_THRESHOLD,
    SCOPE_REJECT_MSG,
    TERMINAL,
    WorkflowError,
    _FIELD_ORDER,
    _LIST_FIELDS,
    _MUTATION_SUBCOMMANDS,
    _READ_SUBCOMMANDS,
    _REPEAT_FLAGS,
    _SUB_OPTIONS,
    _VALUE_FLAGS,
    _canonical_read_root,
    _fmt,
    _git_checkout_context,
    _refuse_linked_worktree_mutation,
    _resolve_root,
    _split,
    _tasks,
    _write_validated,
    append_task_block,
    canonical_scope_prefixes,
    cmd_accept_add,
    cmd_add,
    cmd_archive,
    cmd_scope_add,
    cmd_set,
    find_project_root,
    hold_project_lock,
    load_tasks,
    main,
    migrate_project_state,
    normalize_scope_prefix,
    os,
    remove_task_blocks,
    render_list,
    render_show,
    require_initialized_root,
    round,
    select_for_archive,
    subprocess,
    validate,
    write_text_atomic,
    yaml,
)


class _TasksShim(type(sys)):
    """Keep legacy module-level monkeypatches bound to the moved module's globals.

    Legacy monkeypatch forwarding supports only setattr/delattr. Direct module
    ``__dict__`` mutation (for example, ``mock.patch.dict``) is not forwarded
    because the module dict cannot be replaced with an intercepting mapping.
    This non-conventional surface has no current consumers.
    """

    _routes = {
        name: (_tasks_owner,)
        for name, value in vars(sys.modules[__name__]).items()
        if name in vars(_tasks_owner) and vars(_tasks_owner)[name] is value
    }

    def __setattr__(self, name, value):
        for owner in self.__class__._routes.get(name, ()):
            setattr(owner, name, value)
        super().__setattr__(name, value)

    def __delattr__(self, name):
        for owner in self.__class__._routes.get(name, ()):
            delattr(owner, name)
        super().__delattr__(name)


sys.path.remove(_bootstrap_root)
if not _waystone_preloaded:
    del sys.modules["waystone"]
sys.modules[__name__].__class__ = _TasksShim
del _TasksShim, _tasks_owner, _waystone_preloaded, _bootstrap_root


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
