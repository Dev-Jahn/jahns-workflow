"""Content-addressed runtime artifact storage with fail-loud integrity checks."""
from __future__ import annotations

import errno
import hashlib
import os
import re
import secrets
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from waystone.core import WorkflowError, _ensure_project_self_ignore


_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_ARTIFACT_DIRECTORY_MODE = 0o700
_STAGING_FILE_MODE = 0o600
_FINAL_ARTIFACT_MODE = 0o400
_MAX_STAGING_ATTEMPTS = 32
_MAX_VERIFY_ATTEMPTS = 16
_UNKNOWN_DIGEST = "sha256:" + "0" * 64


class _ArtifactIdentityChanged(Exception):
    """A cooperating publisher replaced one digest path during verification."""


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


class UnsafeArtifactPermissionsError(ArtifactIntegrityError):
    """An artifact root or leaf has unsafe or unprovable owner/mode."""

    code = "unsafe_artifact_permissions"


class ArtifactRootSymlinkError(ArtifactIntegrityError):
    """A component of the artifact root is a symlink."""

    code = "artifact_root_symlink"


class ArtifactRootEscapeError(ArtifactIntegrityError):
    """An artifact root component escapes the confirmed runtime root."""

    code = "artifact_root_escape"


class ArtifactRootTypeMismatchError(ArtifactIntegrityError):
    """An artifact root component is not a directory."""

    code = "artifact_root_type_mismatch"


class ArtifactPathSymlinkError(ArtifactIntegrityError):
    """An individual artifact leaf is a symlink."""

    code = "artifact_path_symlink"


class ArtifactPathEscapeError(ArtifactIntegrityError):
    """An individual artifact leaf escapes the confirmed artifact root."""

    code = "artifact_path_escape"


class ArtifactPathTypeMismatchError(ArtifactIntegrityError):
    """An individual artifact leaf is not a regular file."""

    code = "artifact_path_type_mismatch"


class EngineOwnedArtifactPathUnverifiableError(ArtifactIntegrityError):
    """The platform cannot prove no-follow artifact-path handling."""

    code = "engine_owned_path_unverifiable"


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


def _artifact_nofollow_flag(digest: str, path: Path) -> int:
    flag = getattr(os, "O_NOFOLLOW", None)
    if not isinstance(flag, int):
        raise EngineOwnedArtifactPathUnverifiableError(
            digest, path, "platform does not expose O_NOFOLLOW")
    return flag


def _artifact_effective_uid(digest: str, path: Path) -> int:
    getter = getattr(os, "geteuid", None)
    if not callable(getter):
        raise UnsafeArtifactPermissionsError(
            digest, path, "platform does not expose an effective POSIX owner")
    return int(getter())


def _validate_artifact_owner(digest: str, path: Path, info: os.stat_result) -> None:
    observed_owner = getattr(info, "st_uid", None)
    if not isinstance(observed_owner, int):
        raise UnsafeArtifactPermissionsError(
            digest, path, "filesystem owner is not observable")
    expected_owner = _artifact_effective_uid(digest, path)
    if observed_owner != expected_owner:
        raise UnsafeArtifactPermissionsError(
            digest, path,
            f"owner uid {observed_owner} does not match effective uid {expected_owner}")


def _validate_artifact_directory_mode(
        path: Path, info: os.stat_result, *, newly_created: bool) -> None:
    _validate_artifact_owner(_UNKNOWN_DIGEST, path, info)
    mode = stat.S_IMODE(info.st_mode)
    if newly_created and mode != _ARTIFACT_DIRECTORY_MODE:
        raise UnsafeArtifactPermissionsError(
            _UNKNOWN_DIGEST, path, f"new artifact directory mode {mode:#05o} is not 0700")
    required = stat.S_IWUSR | stat.S_IXUSR
    if mode & required != required or mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise UnsafeArtifactPermissionsError(
            _UNKNOWN_DIGEST, path,
            f"artifact directory mode {mode:#05o} lacks owner write/search "
            "or grants non-owner write")


def _validate_staging_file_mode(
        digest: str, path: Path, info: os.stat_result, *, newly_created: bool) -> None:
    _validate_artifact_owner(digest, path, info)
    mode = stat.S_IMODE(info.st_mode)
    if newly_created and mode != _STAGING_FILE_MODE:
        raise UnsafeArtifactPermissionsError(
            digest, path, f"new artifact staging mode {mode:#05o} is not 0600")
    required = stat.S_IRUSR | stat.S_IWUSR
    if mode & required != required or mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise UnsafeArtifactPermissionsError(
            digest, path,
            f"artifact staging mode {mode:#05o} lacks owner read/write "
            "or grants non-owner write")


def _validate_final_artifact_mode(
        digest: str, path: Path, info: os.stat_result, *, newly_published: bool) -> None:
    _validate_artifact_owner(digest, path, info)
    mode = stat.S_IMODE(info.st_mode)
    if newly_published and mode != _FINAL_ARTIFACT_MODE:
        raise UnsafeArtifactPermissionsError(
            digest, path, f"new finalized artifact mode {mode:#05o} is not 0400")
    if not mode & stat.S_IRUSR or mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
        raise UnsafeArtifactPermissionsError(
            digest, path,
            f"finalized artifact mode {mode:#05o} lacks owner read or grants write")


def _require_artifact_root_containment(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ArtifactRootEscapeError(
            _UNKNOWN_DIGEST, path, f"path is outside confirmed artifact root {root}") from error


def _require_artifact_leaf_containment(digest: str, path: Path, root: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ArtifactPathEscapeError(
            digest, path, f"path is outside confirmed artifact root {root}") from error
    if len(relative.parts) != 1:
        raise ArtifactPathEscapeError(
            digest, path, "artifact leaf must be a direct child of the confirmed artifact root")


def _verify_artifact_directory(
        path: Path, root: Path, *, newly_created: bool) -> None:
    _require_artifact_root_containment(path, root)
    try:
        path_info = path.lstat()
    except FileNotFoundError as error:
        raise EngineOwnedArtifactPathUnverifiableError(
            _UNKNOWN_DIGEST, path, "artifact directory disappeared during verification") from error
    except OSError as error:
        raise EngineOwnedArtifactPathUnverifiableError(
            _UNKNOWN_DIGEST, path, f"cannot inspect artifact directory: {error}") from error
    if stat.S_ISLNK(path_info.st_mode):
        raise ArtifactRootSymlinkError(
            _UNKNOWN_DIGEST, path, "artifact root component must not be a symlink")
    if not stat.S_ISDIR(path_info.st_mode):
        raise ArtifactRootTypeMismatchError(
            _UNKNOWN_DIGEST, path, "artifact root component must be a directory")
    _validate_artifact_directory_mode(path, path_info, newly_created=newly_created)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if not isinstance(directory_flag, int):
        raise EngineOwnedArtifactPathUnverifiableError(
            _UNKNOWN_DIGEST, path, "platform does not expose O_DIRECTORY")
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path, os.O_RDONLY | directory_flag | _artifact_nofollow_flag(_UNKNOWN_DIGEST, path))
        handle_info = os.fstat(descriptor)
    except OSError as error:
        if error.errno == getattr(errno, "ELOOP", None):
            raise ArtifactRootSymlinkError(
                _UNKNOWN_DIGEST, path, "artifact root component became a symlink") from error
        if error.errno == getattr(errno, "ENOTDIR", None):
            raise ArtifactRootTypeMismatchError(
                _UNKNOWN_DIGEST, path, "artifact root component is not a directory") from error
        raise EngineOwnedArtifactPathUnverifiableError(
            _UNKNOWN_DIGEST, path,
            f"cannot open artifact directory without following links: {error}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not stat.S_ISDIR(handle_info.st_mode):
        raise ArtifactRootTypeMismatchError(
            _UNKNOWN_DIGEST, path, "artifact root component is not a directory")
    if (path_info.st_dev, path_info.st_ino) != (handle_info.st_dev, handle_info.st_ino):
        raise EngineOwnedArtifactPathUnverifiableError(
            _UNKNOWN_DIGEST, path, "artifact directory identity changed during verification")
    _validate_artifact_directory_mode(path, handle_info, newly_created=newly_created)


def _ensure_artifact_directory(path: Path, root: Path) -> None:
    _require_artifact_root_containment(path, root)
    newly_created = False
    try:
        path.lstat()
    except FileNotFoundError:
        try:
            os.mkdir(path, _ARTIFACT_DIRECTORY_MODE)
            newly_created = True
        except FileExistsError:
            pass
        except OSError as error:
            raise EngineOwnedArtifactPathUnverifiableError(
                _UNKNOWN_DIGEST, path, f"cannot create artifact directory: {error}") from error
    except OSError as error:
        raise EngineOwnedArtifactPathUnverifiableError(
            _UNKNOWN_DIGEST, path, f"cannot inspect artifact directory: {error}") from error
    _verify_artifact_directory(path, root, newly_created=newly_created)


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
        _ensure_artifact_directory(state_directory, self.project_root)
        _ensure_artifact_directory(self.directory, state_directory)
        try:
            _ensure_project_self_ignore(state_directory)
        except (OSError, WorkflowError) as error:
            raise ArtifactIntegrityError(
                _UNKNOWN_DIGEST, state_directory / ".gitignore",
                f"cannot establish project-state self-ignore: {error}") from error

    def _verify_existing_directory_tree(self) -> None:
        state_directory = self.directory.parent
        try:
            state_directory.lstat()
        except FileNotFoundError:
            return
        except OSError as error:
            raise EngineOwnedArtifactPathUnverifiableError(
                _UNKNOWN_DIGEST, state_directory,
                f"cannot inspect artifact state directory: {error}") from error
        _verify_artifact_directory(
            state_directory, self.project_root, newly_created=False)
        try:
            self.directory.lstat()
        except FileNotFoundError:
            return
        except OSError as error:
            raise EngineOwnedArtifactPathUnverifiableError(
                _UNKNOWN_DIGEST, self.directory,
                f"cannot inspect artifact directory: {error}") from error
        _verify_artifact_directory(
            self.directory, state_directory, newly_created=False)

    def _verified_file_info(
            self, digest: str, path: Path, *, finalized: bool) -> tuple[os.stat_result, int]:
        _require_artifact_leaf_containment(digest, path, self.directory)
        try:
            path_info = path.lstat()
        except FileNotFoundError as error:
            raise ArtifactNotFoundError(digest, path) from error
        except OSError as error:
            raise ArtifactIntegrityError(digest, path, f"cannot inspect bytes: {error}") from error
        if stat.S_ISLNK(path_info.st_mode):
            raise ArtifactPathSymlinkError(
                digest, path, "artifact leaf must not be a symlink")
        if not stat.S_ISREG(path_info.st_mode):
            raise ArtifactPathTypeMismatchError(
                digest, path, "artifact leaf must be a regular file")
        if finalized:
            _validate_final_artifact_mode(
                digest, path, path_info, newly_published=False)
        else:
            _validate_staging_file_mode(
                digest, path, path_info, newly_created=False)
        try:
            descriptor = os.open(
                path, os.O_RDONLY | _artifact_nofollow_flag(digest, path))
        except OSError as error:
            if error.errno == getattr(errno, "ELOOP", None):
                raise ArtifactPathSymlinkError(
                    digest, path, "artifact leaf became a symlink") from error
            if error.errno in {getattr(errno, "EISDIR", None), getattr(errno, "ENOTDIR", None)}:
                raise ArtifactPathTypeMismatchError(
                    digest, path, "artifact leaf is not a regular file") from error
            raise EngineOwnedArtifactPathUnverifiableError(
                digest, path,
                f"cannot open artifact leaf without following links: {error}") from error
        try:
            handle_info = os.fstat(descriptor)
            if not stat.S_ISREG(handle_info.st_mode):
                raise ArtifactPathTypeMismatchError(
                    digest, path, "artifact leaf is not a regular file")
            if (path_info.st_dev, path_info.st_ino) != (
                    handle_info.st_dev, handle_info.st_ino):
                raise _ArtifactIdentityChanged
            if finalized:
                _validate_final_artifact_mode(
                    digest, path, handle_info, newly_published=False)
            else:
                _validate_staging_file_mode(
                    digest, path, handle_info, newly_created=False)
        except BaseException:
            os.close(descriptor)
            raise
        return handle_info, descriptor

    def _verified_bytes(self, digest: str, path: Path, *, finalized: bool = True) -> bytes:
        for _ in range(_MAX_VERIFY_ATTEMPTS):
            try:
                verified_info, descriptor = self._verified_file_info(
                    digest, path, finalized=finalized)
            except _ArtifactIdentityChanged:
                continue
            try:
                with os.fdopen(descriptor, "rb") as stream:
                    payload = stream.read()
            except OSError as error:
                raise ArtifactIntegrityError(
                    digest, path, f"bytes are unreadable: {error}") from error
            actual = _sha256(payload)
            if actual != digest:
                raise ArtifactIntegrityError(
                    digest, path, f"content digest mismatch (observed {actual})")
            try:
                final_info = path.lstat()
            except OSError as error:
                raise EngineOwnedArtifactPathUnverifiableError(
                    digest, path, f"cannot confirm artifact after read: {error}") from error
            if stat.S_ISLNK(final_info.st_mode):
                raise ArtifactPathSymlinkError(
                    digest, path, "artifact leaf became a symlink during read")
            if (verified_info.st_dev, verified_info.st_ino) == (
                    final_info.st_dev, final_info.st_ino):
                return payload
        raise EngineOwnedArtifactPathUnverifiableError(
            digest, path,
            f"artifact leaf kept changing across {_MAX_VERIFY_ATTEMPTS} verified reads")

    def _create_staging_file(self, digest: str) -> tuple[Path, int]:
        flags = (
            os.O_RDWR | os.O_CREAT | os.O_EXCL
            | _artifact_nofollow_flag(digest, self.directory))
        for _ in range(_MAX_STAGING_ATTEMPTS):
            path = self.directory / f".artifact-{secrets.token_hex(16)}.tmp"
            _require_artifact_leaf_containment(digest, path, self.directory)
            try:
                descriptor = os.open(path, flags, _STAGING_FILE_MODE)
            except FileExistsError:
                continue
            except OSError as error:
                raise EngineOwnedArtifactPathUnverifiableError(
                    digest, path,
                    f"cannot create artifact staging file without following links: {error}") from error
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode):
                    raise ArtifactPathTypeMismatchError(
                        digest, path, "artifact staging leaf is not a regular file")
                _validate_staging_file_mode(
                    digest, path, info, newly_created=True)
            except BaseException:
                os.close(descriptor)
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                raise
            return path, descriptor
        raise ArtifactIntegrityError(
            digest, self.directory,
            f"could not allocate a unique staging file after {_MAX_STAGING_ATTEMPTS} attempts")

    def _sync_directory(self, digest: str) -> None:
        directory_flag = getattr(os, "O_DIRECTORY", None)
        if not isinstance(directory_flag, int):
            raise EngineOwnedArtifactPathUnverifiableError(
                digest, self.directory, "platform does not expose O_DIRECTORY")
        try:
            descriptor = os.open(
                self.directory,
                os.O_RDONLY | directory_flag
                | _artifact_nofollow_flag(digest, self.directory),
            )
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISDIR(info.st_mode):
                    raise ArtifactRootTypeMismatchError(
                        digest, self.directory, "artifact root is not a directory")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except ArtifactError:
            raise
        except OSError as error:
            raise ArtifactIntegrityError(
                digest, self.directory,
                f"cannot durably sync artifact directory: {error}") from error

    def write(self, content: bytes) -> StoredArtifact:
        """Atomically publish bytes and verify both the temporary and final content."""
        if not isinstance(content, bytes):
            raise TypeError("artifact content must be bytes")
        digest = _sha256(content)
        target = self.path_for(digest)
        self._ensure_directory()
        try:
            existing = self._verified_bytes(digest, target)
        except ArtifactNotFoundError:
            existing = None
        if existing is not None:
            return StoredArtifact(digest=digest, size=len(existing), path=target)

        temporary_path: Path | None = None
        staging_descriptor: int | None = None
        try:
            temporary_path, staging_descriptor = self._create_staging_file(digest)
            with os.fdopen(os.dup(staging_descriptor), "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                temporary_bytes = self._verified_bytes(
                    digest, temporary_path, finalized=False)
            except ArtifactNotFoundError as error:
                raise ArtifactIntegrityError(
                    digest, temporary_path, "temporary bytes disappeared before publication") from error
            if len(temporary_bytes) != len(content):
                raise ArtifactIntegrityError(digest, temporary_path, "temporary size changed")
            os.fchmod(staging_descriptor, _FINAL_ARTIFACT_MODE)
            finalized_info = os.fstat(staging_descriptor)
            _validate_final_artifact_mode(
                digest, temporary_path, finalized_info, newly_published=True)

            try:
                existing = self._verified_bytes(digest, target)
            except ArtifactNotFoundError:
                existing = None
            if existing is not None:
                return StoredArtifact(digest=digest, size=len(existing), path=target)

            os.replace(temporary_path, target)
            temporary_path = None
            try:
                published = self._verified_bytes(digest, target)
            except ArtifactNotFoundError as error:
                raise ArtifactIntegrityError(
                    digest, target, "published bytes disappeared after atomic rename") from error
            if len(published) != len(content):
                raise ArtifactIntegrityError(digest, target, "published size changed")
            self._sync_directory(digest)
            return StoredArtifact(digest=digest, size=len(published), path=target)
        except ArtifactError:
            raise
        except OSError as error:
            raise ArtifactIntegrityError(digest, target, f"atomic write failed: {error}") from error
        finally:
            if staging_descriptor is not None:
                os.close(staging_descriptor)
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass

    def read(self, digest: str) -> bytes:
        """Read and rehash raw digest-addressed bytes; missing remains distinct from corruption."""
        canonical = validate_sha256_digest(digest)
        self._verify_existing_directory_tree()
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
