"""Frozen child environments for candidate-bound runner processes."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


_INHERITED_NAMES = frozenset({
    "HOME",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "LANG",
    "NO_PROXY",
    "PATH",
    "SHELL",
    "TERM",
    "TMPDIR",
    "USER",
    "UV_CACHE_DIR",
    "http_proxy",
    "https_proxy",
    "no_proxy",
})


@dataclass(frozen=True)
class RunnerEnvironment:
    """One immutable, deterministically digested child environment."""

    values: Mapping[str, str]

    def __post_init__(self) -> None:
        normalized: dict[str, str] = {}
        for name, value in self.values.items():
            if (not isinstance(name, str) or not name or "=" in name or "\0" in name
                    or not isinstance(value, str) or "\0" in value):
                raise ValueError("runner environment entries must be valid strings")
            normalized[name] = value
        object.__setattr__(
            self,
            "values",
            MappingProxyType(dict(sorted(normalized.items()))),
        )

    @property
    def digest(self) -> str:
        content = "\0".join(
            f"{name}={value}" for name, value in self.values.items()
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(content).hexdigest()

    def as_dict(self) -> dict[str, str]:
        return dict(self.values)


def build_runner_environment(
        source: Mapping[str, str] | None = None) -> RunnerEnvironment:
    """Select the complete child environment from an explicit allowlist."""
    ambient = os.environ if source is None else source
    if not isinstance(ambient, Mapping):
        raise TypeError("runner environment source must be a mapping")
    return RunnerEnvironment({
        name: value
        for name, value in ambient.items()
        if name in _INHERITED_NAMES or name.startswith("LC_")
    })


__all__ = ["RunnerEnvironment", "build_runner_environment"]
