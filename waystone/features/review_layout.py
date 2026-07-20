"""Canonical and legacy addressing for Git-tracked review artifacts."""
from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from waystone.core import WorkflowError, write_bytes_atomic


REQUEST = "request"
REQUEST_BINDING = "request-binding"
FEEDBACK = "feedback"
PR_FREEZE = "pr-freeze"
PR_DEMOTION = "pr-demotion"

_FIXED_LEAVES = {
    REQUEST: "request.md",
    REQUEST_BINDING: "request.binding.json",
    FEEDBACK: "feedback.md",
}
_SIDECAR_DIRECTORIES = {
    PR_FREEZE: "pr-freeze",
    PR_DEMOTION: "pr-demotion",
}
_JSON_KINDS = frozenset((REQUEST_BINDING, PR_FREEZE, PR_DEMOTION))
_MARKDOWN_KINDS = frozenset((REQUEST, FEEDBACK))
_LOCAL_LOCATOR_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_MARKDOWN_IDENTITY_PREFIX = b"<!-- waystone-review-artifact:v1 "
_MARKDOWN_IDENTITY_SUFFIX = b" -->\n"
_MARKDOWN_IDENTITY_SCHEMA = "waystone-review-artifact-1"

_LEGACY_PATTERNS = (
    (REQUEST_BINDING, re.compile(
        r"(?P<round_id>.+)-request\.binding(?:-[1-9]\d*)?\.json")),
    (PR_FREEZE, re.compile(
        r"(?P<round_id>.+)-freeze-[1-9]\d*\.binding(?:-[1-9]\d*)?\.json")),
    (PR_DEMOTION, re.compile(
        r"(?P<round_id>.+)-freeze-[1-9]\d*\.demotion(?:-[1-9]\d*)?\.json")),
    (REQUEST, re.compile(r"(?P<round_id>.+)-request\.md")),
    (FEEDBACK, re.compile(r"(?P<round_id>.+)-feedback\.md")),
)


class ReviewLayoutError(WorkflowError):
    """Base class for typed canonical/legacy review-layout refusals."""


class IdentityConflict(ReviewLayoutError):
    """A canonical path owner and the artifact payload do not prove one identity."""

    code = "review-artifact-identity-conflict"


class InvalidRunId(IdentityConflict):
    """The purported canonical owner is not an RFC 9562 UUIDv7 string."""

    code = "invalid-review-run-id"


class ArtifactConflict(ReviewLayoutError):
    """A fixed canonical leaf already contains different bytes."""

    code = "review-artifact-publication-conflict"


def is_uuid7(value: object) -> bool:
    """Return whether ``value`` is canonical lowercase hyphenated RFC 9562 UUIDv7."""
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return False
    return (
        str(parsed) == value
        and parsed.version == 7
        and parsed.variant == uuid.RFC_4122
    )


def require_uuid7(value: object) -> str:
    if not is_uuid7(value):
        raise InvalidRunId(
            f"run_id must be canonical lowercase hyphenated RFC 9562 UUIDv7, got {value!r}")
    return str(value)


def new_run_id(*, unix_ms: int | None = None) -> str:
    """Mint a UUIDv7 with CSPRNG-provided random fields."""
    timestamp_ms = time.time_ns() // 1_000_000 if unix_ms is None else unix_ms
    if type(timestamp_ms) is not int or not 0 <= timestamp_ms < (1 << 48):
        raise InvalidRunId("UUIDv7 timestamp must be an unsigned 48-bit Unix millisecond value")
    random_bits = secrets.randbits(74)
    random_a = random_bits >> 62
    random_b = random_bits & ((1 << 62) - 1)
    value = (
        (timestamp_ms << 80)
        | (7 << 76)
        | (random_a << 64)
        | (0b10 << 62)
        | random_b
    )
    return str(uuid.UUID(int=value))


def canonical_run_directory(reviews_dir: Path, run_id: str) -> Path:
    return Path(reviews_dir) / "runs" / require_uuid7(run_id)


def canonical_artifact_path(
        reviews_dir: Path, run_id: str, kind: str, *, locator: str | int | None = None,
) -> Path:
    directory = canonical_run_directory(reviews_dir, run_id)
    if kind in _FIXED_LEAVES:
        if locator is not None:
            raise ReviewLayoutError(f"{kind} does not accept a local locator")
        return directory / _FIXED_LEAVES[kind]
    sidecar_directory = _SIDECAR_DIRECTORIES.get(kind)
    local = str(locator) if locator is not None else ""
    if sidecar_directory is None or _LOCAL_LOCATOR_RE.fullmatch(local) is None:
        raise ReviewLayoutError(f"{kind} requires one safe local locator segment")
    return directory / sidecar_directory / f"{local}.json"


def bind_markdown_run_id(content: bytes, run_id: str) -> bytes:
    """Return Markdown carrying one strict, first-line canonical identity payload."""
    owner = require_uuid7(run_id)
    if not isinstance(content, bytes):
        raise TypeError("canonical Markdown content must be bytes")
    if content.startswith(_MARKDOWN_IDENTITY_PREFIX):
        payload = _markdown_identity(content, Path("<memory>"))
        _require_payload_owner(payload, owner, Path("<memory>"))
        return content
    payload = json.dumps(
        {"run_id": owner, "schema": _MARKDOWN_IDENTITY_SCHEMA},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return _MARKDOWN_IDENTITY_PREFIX + payload + _MARKDOWN_IDENTITY_SUFFIX + content


def publish_markdown(
        reviews_dir: Path, run_id: str, kind: str, content: bytes, *, replace: bool = False,
) -> Path:
    if kind not in _MARKDOWN_KINDS:
        raise ReviewLayoutError(f"{kind} is not a canonical Markdown artifact")
    if replace and kind != FEEDBACK:
        raise ReviewLayoutError("only canonical feedback supports explicit replacement")
    path = canonical_artifact_path(reviews_dir, run_id, kind)
    _publish(Path(reviews_dir), path, bind_markdown_run_id(content, run_id), replace=replace)
    return path


def publish_json(
        reviews_dir: Path, run_id: str, kind: str, payload: Mapping[str, Any], *,
        locator: str | int | None = None,
) -> Path:
    if kind not in _JSON_KINDS:
        raise ReviewLayoutError(f"{kind} is not a canonical JSON artifact")
    owner = require_uuid7(run_id)
    if not isinstance(payload, Mapping):
        raise ReviewLayoutError("canonical JSON payload must be a mapping")
    if "run_id" in payload and payload["run_id"] != owner:
        raise IdentityConflict(
            f"writer payload run_id {payload['run_id']!r} does not match owner {owner!r}")
    row = dict(payload)
    row["run_id"] = owner
    try:
        content = (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ReviewLayoutError(f"canonical JSON payload is not serializable: {error}") from error
    path = canonical_artifact_path(reviews_dir, owner, kind, locator=locator)
    _publish(Path(reviews_dir), path, content, replace=False)
    return path


def read_canonical_artifact(reviews_dir: Path, path: Path) -> dict[str, Any]:
    """Read one canonical artifact only after path and payload owner checks both pass."""
    artifact_path = Path(path)
    run_id, kind, locator = _canonical_address(Path(reviews_dir), artifact_path)
    _require_safe_canonical_path(Path(reviews_dir), artifact_path)
    try:
        content = artifact_path.read_bytes()
    except OSError as error:
        raise ReviewLayoutError(f"canonical review artifact unavailable {artifact_path}: {error}") \
            from error
    if kind in _JSON_KINDS:
        payload = _json_object(content, artifact_path)
    else:
        payload = _markdown_identity(content, artifact_path)
    _require_payload_owner(payload, run_id, artifact_path)
    return {
        "run_id": run_id,
        "kind": kind,
        "path": artifact_path,
        "bytes": content,
        "payload": payload,
        "locator": locator,
        "evidence": "canonical",
    }


def read_canonical_run(reviews_dir: Path, run_id: str) -> tuple[dict[str, Any], ...]:
    """Read one owner directory without enumerating or parsing any adjacent owner."""
    directory = canonical_run_directory(reviews_dir, run_id)
    if directory.is_symlink() or not directory.is_dir():
        raise ReviewLayoutError(f"canonical review owner directory is missing: {directory}")
    paths = [
        directory / leaf for leaf in _FIXED_LEAVES.values()
        if (directory / leaf).exists() or (directory / leaf).is_symlink()
    ]
    for sidecar_dir in _SIDECAR_DIRECTORIES.values():
        parent = directory / sidecar_dir
        if parent.is_symlink():
            raise IdentityConflict(f"canonical review sidecar directory is a symlink: {parent}")
        if parent.is_dir():
            paths.extend(sorted(parent.glob("*.json")))
    return tuple(read_canonical_artifact(reviews_dir, path) for path in sorted(paths))


def scan_canonical_request_bindings(
        reviews_dir: Path,
) -> tuple[tuple[dict[str, Any], ...], tuple[tuple[Path, ReviewLayoutError], ...]]:
    """Return valid canonical owner bindings and explicit per-owner rejections separately."""
    runs = Path(reviews_dir) / "runs"
    if runs.is_symlink():
        raise IdentityConflict(f"canonical reviews runs directory is a symlink: {runs}")
    if not runs.is_dir():
        return (), ()
    artifacts: list[dict[str, Any]] = []
    rejected: list[tuple[Path, ReviewLayoutError]] = []
    for owner_directory in sorted(runs.iterdir()):
        path = owner_directory / _FIXED_LEAVES[REQUEST_BINDING]
        if owner_directory.is_symlink():
            rejected.append((path, IdentityConflict(
                f"canonical review owner directory is a symlink: {owner_directory}")))
            continue
        if not owner_directory.is_dir():
            continue
        if not path.exists() and not path.is_symlink():
            continue
        try:
            artifacts.append(read_canonical_artifact(reviews_dir, path))
        except ReviewLayoutError as error:
            rejected.append((path, error))
    return tuple(artifacts), tuple(rejected)


def rejected_binding_round_claim(reviews_dir: Path, path: Path) -> str | None:
    """Return only a bounded, untrusted round claim used to isolate one rejected owner."""
    artifact_path = Path(path)
    try:
        _require_safe_canonical_path(Path(reviews_dir), artifact_path)
        payload = _json_object(artifact_path.read_bytes(), artifact_path)
    except (OSError, ReviewLayoutError):
        return None
    claim = payload.get("round_id")
    return claim if isinstance(claim, str) else None


def read_legacy_artifact(reviews_dir: Path, path: Path) -> dict[str, Any]:
    """Read one direct-child flat artifact using only the historical filename grammar."""
    directory = Path(reviews_dir)
    artifact_path = Path(path)
    if artifact_path.parent != directory:
        raise ReviewLayoutError(
            f"legacy review artifact must be a direct child of {directory}: {artifact_path}")
    if artifact_path.is_symlink() or not artifact_path.is_file():
        raise ReviewLayoutError(
            f"legacy review artifact must be a regular non-symlink file: {artifact_path}")
    for kind, pattern in _LEGACY_PATTERNS:
        match = pattern.fullmatch(artifact_path.name)
        if match is None:
            continue
        try:
            content = artifact_path.read_bytes()
        except OSError as error:
            raise ReviewLayoutError(
                f"legacy review artifact unavailable {artifact_path}: {error}") from error
        return {
            "round_id": match.group("round_id"),
            "kind": kind,
            "path": artifact_path,
            "bytes": content,
            "evidence": "legacy",
        }
    raise ReviewLayoutError(f"unrecognized legacy review artifact: {artifact_path}")


def _canonical_address(reviews_dir: Path, path: Path) -> tuple[str, str, str | None]:
    try:
        relative = path.relative_to(reviews_dir / "runs")
    except ValueError as error:
        raise IdentityConflict(f"artifact is outside the canonical runs tree: {path}") from error
    parts = relative.parts
    if len(parts) == 2:
        run_id = require_uuid7(parts[0])
        kinds = {leaf: kind for kind, leaf in _FIXED_LEAVES.items()}
        kind = kinds.get(parts[1])
        if kind is None:
            raise IdentityConflict(f"unknown canonical review leaf: {path}")
        return run_id, kind, None
    if len(parts) == 3 and parts[2].endswith(".json"):
        run_id = require_uuid7(parts[0])
        kinds = {directory: kind for kind, directory in _SIDECAR_DIRECTORIES.items()}
        kind = kinds.get(parts[1])
        locator = parts[2].removesuffix(".json")
        if kind is not None and _LOCAL_LOCATOR_RE.fullmatch(locator):
            return run_id, kind, locator
    raise IdentityConflict(f"invalid canonical review artifact address: {path}")


def _require_safe_canonical_path(reviews_dir: Path, path: Path) -> None:
    if reviews_dir.is_symlink():
        raise IdentityConflict(f"canonical reviews directory is a symlink: {reviews_dir}")
    runs = reviews_dir / "runs"
    try:
        relative = path.relative_to(runs)
    except ValueError as error:
        raise IdentityConflict(f"artifact is outside the canonical runs tree: {path}") from error
    current = reviews_dir
    for part in ("runs", *relative.parts):
        current = current / part
        if current.is_symlink():
            raise IdentityConflict(f"canonical review path contains a symlink: {current}")
    try:
        path.resolve(strict=False).relative_to(runs.resolve(strict=False))
    except ValueError as error:
        raise IdentityConflict(f"canonical review path escapes the runs tree: {path}") from error


def _require_payload_owner(payload: Mapping[str, Any], run_id: str, path: Path) -> None:
    payload_owner = payload.get("run_id")
    if not is_uuid7(payload_owner):
        raise IdentityConflict(f"canonical review artifact has no valid payload run_id: {path}")
    if payload_owner != run_id:
        raise IdentityConflict(
            f"canonical review artifact payload run_id {payload_owner!r} does not match "
            f"directory owner {run_id!r}: {path}")


def _json_object(content: bytes, path: Path) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        row: dict[str, Any] = {}
        for key, value in pairs:
            if key in row:
                raise ValueError(f"duplicate field {key!r}")
            row[key] = value
        return row

    try:
        payload = json.loads(content.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise IdentityConflict(f"canonical review JSON payload is invalid {path}: {error}") \
            from error
    if not isinstance(payload, dict):
        raise IdentityConflict(f"canonical review JSON payload must be an object: {path}")
    return payload


def _markdown_identity(content: bytes, path: Path) -> Mapping[str, Any]:
    first_line, separator, _body = content.partition(b"\n")
    if not separator or not first_line.startswith(_MARKDOWN_IDENTITY_PREFIX) \
            or not first_line.endswith(b" -->"):
        raise IdentityConflict(f"canonical review Markdown payload run_id is missing: {path}")
    raw = first_line[len(_MARKDOWN_IDENTITY_PREFIX):-len(b" -->")]
    payload = _json_object(raw, path)
    if payload.get("schema") != _MARKDOWN_IDENTITY_SCHEMA:
        raise IdentityConflict(f"canonical review Markdown identity schema is invalid: {path}")
    return payload


def _publish(reviews_dir: Path, path: Path, content: bytes, *, replace: bool) -> None:
    _require_safe_canonical_path(reviews_dir, path)
    if replace:
        if path.exists() or path.is_symlink():
            read_canonical_artifact(reviews_dir, path)
        write_bytes_atomic(path, content)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _require_safe_canonical_path(reviews_dir, path)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
                "wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp",
                delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            if path.is_symlink():
                raise ArtifactConflict(
                    f"canonical review leaf is a symlink: {path}") from error
            try:
                existing = path.read_bytes()
            except OSError as read_error:
                raise ArtifactConflict(
                    f"canonical review leaf exists but cannot be compared: {path}: {read_error}") \
                    from read_error
            if existing != content:
                raise ArtifactConflict(
                    f"canonical review leaf already contains different bytes: {path}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
