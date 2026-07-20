"""Content-addressed runtime artifact storage with fail-loud integrity checks."""
from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from waystone.core import WorkflowError, _ensure_project_self_ignore


_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


class ArtifactError(WorkflowError):
    """Base class for typed artifact-store failures."""

    code = "artifact_error"

    def __init__(self, message: str):
        super().__init__(f"{self.code}: {message}")


class ArtifactIntegrityError(ArtifactError):
    """Artifact bytes or their storage path cannot prove the expected digest."""

    code = "artifact_integrity_error"

    def __init__(self, digest: str, path: Path, detail: str):
        self.digest = digest
        self.path = Path(path)
        self.detail = detail
        super().__init__(f"{digest} at {path}: {detail}")


class ArtifactNotFoundError(ArtifactError):
    """No bytes exist for a raw, not-yet-reference-qualified digest lookup."""

    code = "artifact_not_found"

    def __init__(self, digest: str, path: Path):
        self.digest = digest
        self.path = Path(path)
        super().__init__(f"no bytes for {digest} at {path}")


class DanglingArtifactReferenceError(ArtifactError):
    """A durable reference exists, but its content-addressed bytes do not."""

    code = "dangling_artifact_reference"

    def __init__(self, reference_id: str, digest: str, path: Path):
        self.reference_id = reference_id
        self.digest = digest
        self.path = Path(path)
        super().__init__(f"reference {reference_id} names missing {digest} at {path}")


class UninitializedArtifactProjectError(ArtifactError):
    """Artifact state cannot be created outside an initialized project."""

    code = "uninitialized_project"

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        super().__init__(
            f"{project_root} has no regular .waystone.yml; refusing artifact state creation")


class ArtifactReferenceKind(str, Enum):
    """Immutable artifact-reference roles owned by the store-kernel slice."""

    ATTEMPT = "attempt"
    EVIDENCE = "evidence"
    DECISION = "decision"


def validate_sha256_digest(digest: str) -> str:
    """Return one canonical SHA-256 identity or reject it without normalization."""
    if not isinstance(digest, str) or _DIGEST_PATTERN.fullmatch(digest) is None:
        raise ValueError("digest must be canonical sha256:<64 lowercase hex>")
    return digest


@dataclass(frozen=True)
class ArtifactReference:
    """Immutable metadata attached to one state transition by reference identity."""

    reference_id: str
    kind: ArtifactReferenceKind
    digest: str
    size: int

    def __post_init__(self) -> None:
        if not isinstance(self.reference_id, str) or not self.reference_id.strip():
            raise ValueError("reference_id must be a non-empty string")
        try:
            kind = ArtifactReferenceKind(self.kind)
        except (TypeError, ValueError) as error:
            raise ValueError("artifact reference kind is not supported by schema v1") from error
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0:
            raise ValueError("artifact reference size must be a non-negative integer")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "digest", validate_sha256_digest(self.digest))


@dataclass(frozen=True)
class StoredArtifact:
    """A verified content-addressed artifact."""

    digest: str
    size: int
    path: Path


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _regular_nonsymlink(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    return stat.S_ISREG(mode) and not stat.S_ISLNK(mode)


class ArtifactStore:
    """Store immutable bytes at ``.waystone/artifacts/sha256-<hex>``."""

    def __init__(self, project_root: Path):
        supplied_root = Path(project_root)
        marker = supplied_root / ".waystone.yml"
        if not _regular_nonsymlink(marker):
            raise UninitializedArtifactProjectError(supplied_root)
        try:
            self.project_root = supplied_root.resolve(strict=True)
        except OSError as error:
            raise UninitializedArtifactProjectError(supplied_root) from error
        self.directory = self.project_root / ".waystone" / "artifacts"

    def path_for(self, digest: str) -> Path:
        canonical = validate_sha256_digest(digest)
        return self.directory / canonical.replace(":", "-", 1)

    def _ensure_directory(self) -> None:
        state_directory = self.directory.parent
        for directory in (state_directory, self.directory):
            try:
                directory.mkdir(exist_ok=True)
                info = directory.lstat()
            except OSError as error:
                raise ArtifactIntegrityError(
                    "sha256:" + "0" * 64, directory,
                    f"cannot inspect artifact directory: {error}") from error
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise ArtifactIntegrityError(
                    "sha256:" + "0" * 64, directory,
                    "artifact directory must be a real directory")
        try:
            _ensure_project_self_ignore(state_directory)
        except (OSError, WorkflowError) as error:
            raise ArtifactIntegrityError(
                "sha256:" + "0" * 64, state_directory / ".gitignore",
                f"cannot establish project-state self-ignore: {error}") from error

    def _verified_bytes(self, digest: str, path: Path) -> bytes:
        try:
            info = path.lstat()
        except FileNotFoundError as error:
            raise ArtifactNotFoundError(digest, path) from error
        except OSError as error:
            raise ArtifactIntegrityError(digest, path, f"cannot inspect bytes: {error}") from error
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ArtifactIntegrityError(digest, path, "artifact path is not a regular file")
        try:
            payload = path.read_bytes()
        except FileNotFoundError as error:
            raise ArtifactIntegrityError(
                digest, path, "bytes disappeared during verified read") from error
        except OSError as error:
            raise ArtifactIntegrityError(digest, path, f"bytes are unreadable: {error}") from error
        actual = _sha256(payload)
        if actual != digest:
            raise ArtifactIntegrityError(
                digest, path, f"content digest mismatch (observed {actual})")
        return payload

    def write(self, content: bytes) -> StoredArtifact:
        """Atomically publish bytes and verify both the temporary and final content."""
        if not isinstance(content, bytes):
            raise TypeError("artifact content must be bytes")
        digest = _sha256(content)
        target = self.path_for(digest)
        try:
            existing = self._verified_bytes(digest, target)
        except ArtifactNotFoundError:
            existing = None
        if existing is not None:
            return StoredArtifact(digest=digest, size=len(existing), path=target)

        self._ensure_directory()
        try:
            existing = self._verified_bytes(digest, target)
        except ArtifactNotFoundError:
            existing = None
        if existing is not None:
            return StoredArtifact(digest=digest, size=len(existing), path=target)

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                    "wb", dir=self.directory, prefix=".artifact-", suffix=".tmp",
                    delete=False) as stream:
                temporary_path = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                temporary_bytes = self._verified_bytes(digest, temporary_path)
            except ArtifactNotFoundError as error:
                raise ArtifactIntegrityError(
                    digest, temporary_path, "temporary bytes disappeared before publication") from error
            if len(temporary_bytes) != len(content):
                raise ArtifactIntegrityError(digest, temporary_path, "temporary size changed")
            os.replace(temporary_path, target)
            temporary_path = None
            try:
                published = self._verified_bytes(digest, target)
            except ArtifactNotFoundError as error:
                raise ArtifactIntegrityError(
                    digest, target, "published bytes disappeared after atomic rename") from error
            if len(published) != len(content):
                raise ArtifactIntegrityError(digest, target, "published size changed")
            try:
                directory_descriptor = os.open(self.directory, os.O_RDONLY)
                try:
                    os.fsync(directory_descriptor)
                finally:
                    os.close(directory_descriptor)
            except OSError as error:
                raise ArtifactIntegrityError(
                    digest, target, f"cannot durably sync artifact directory: {error}") from error
            return StoredArtifact(digest=digest, size=len(published), path=target)
        except ArtifactError:
            raise
        except OSError as error:
            raise ArtifactIntegrityError(digest, target, f"atomic write failed: {error}") from error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass

    def read(self, digest: str) -> bytes:
        """Read and rehash raw digest-addressed bytes; missing remains distinct from corruption."""
        canonical = validate_sha256_digest(digest)
        return self._verified_bytes(canonical, self.path_for(canonical))

    def read_reference(self, reference: ArtifactReference) -> bytes:
        """Read a durable reference, promoting missing bytes to a typed dangling finding."""
        if not isinstance(reference, ArtifactReference):
            raise TypeError("reference must be an ArtifactReference")
        try:
            payload = self.read(reference.digest)
        except ArtifactNotFoundError as error:
            raise DanglingArtifactReferenceError(
                reference.reference_id, reference.digest, error.path) from error
        if len(payload) != reference.size:
            raise ArtifactIntegrityError(
                reference.digest, self.path_for(reference.digest),
                f"reference size {reference.size} does not match verified bytes {len(payload)}")
        return payload
