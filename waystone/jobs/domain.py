"""Canonical job roles and execution axes. This module performs no I/O."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    COORDINATOR = "coordinator"
    WORKER = "worker"
    VERIFIER = "verifier"
    REVIEWER = "reviewer"


class ExecutorKind(str, Enum):
    ENGINE = "engine"
    CARRIER = "carrier"
    USER = "user"


class ExecutionCategory(str, Enum):
    IN_SESSION = "in-session"
    SUBAGENT = "subagent"
    EXTERNAL = "external"


@dataclass(frozen=True)
class RoleBinding:
    role: Role
    execution_category: ExecutionCategory
    backend: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, Role):
            raise TypeError("role must be a Role")
        if not isinstance(self.execution_category, ExecutionCategory):
            raise TypeError("execution_category must be an ExecutionCategory")
        if not isinstance(self.backend, str) or not self.backend.strip():
            raise ValueError("backend must be a non-empty identifier")


__all__ = ["ExecutionCategory", "ExecutorKind", "Role", "RoleBinding"]
