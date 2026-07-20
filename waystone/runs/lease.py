"""Lease principals, fencing, and short single-machine advisory locks."""
from __future__ import annotations

import errno
import fcntl
import math
import os
import secrets
import sqlite3
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator, TypeVar

from waystone.core import WorkflowError
from waystone.runs.store import (
    EngineOwnedPathUnverifiableError,
    EntityKind,
    RunStore,
    StatePathSymlinkError,
    StatePathTypeMismatchError,
    StoreError,
    _open_mutable_state_file,
    _require_contained_state_path,
    _verify_state_directory,
)


_MAX_FENCING_EPOCH = (1 << 63) - 1
_TOKEN_BYTES = 32
_T = TypeVar("_T")


class LeaseError(WorkflowError):
    """Base class for typed lease and fencing failures."""

    code = "lease_error"

    def __init__(self, message: str):
        super().__init__(f"{self.code}: {message}")


class LeasePrincipalMismatch(LeaseError):
    """A readable current principal does not match the supplied tuple."""

    code = "lease_principal_mismatch"

    def __init__(self, action_id: str, operation: str):
        self.action_id = action_id
        self.operation = operation
        super().__init__(
            f"action {action_id!r} is owned by a different current principal during {operation}")


class LeasePrincipalUnknown(LeaseError):
    """The current principal cannot be read as one coherent DB fact."""

    code = "lease_principal_unknown"

    def __init__(self, action_id: str, operation: str, detail: str):
        self.action_id = action_id
        self.operation = operation
        self.detail = detail
        super().__init__(
            f"cannot establish the current principal for action {action_id!r} "
            f"during {operation}: {detail}")


class LeaseAlreadyClaimed(LeaseError):
    """A claim exists and expiry is not authority to replace it."""

    code = "lease_already_claimed"

    def __init__(self, action_id: str):
        self.action_id = action_id
        super().__init__(
            f"action {action_id!r} already has a current principal; use proven reclaim")


class LeaseReclaimRefused(LeaseError):
    """Positive quiescence and effect-absence evidence was not established."""

    code = "lease_reclaim_refused"

    def __init__(self, action_id: str, evidence: str):
        self.action_id = action_id
        self.evidence = evidence
        super().__init__(
            f"action {action_id!r} cannot be reclaimed without positive {evidence} evidence")


class FencingEpochExhausted(LeaseError):
    """The durable fencing counter cannot advance without reuse or overflow."""

    code = "fencing_epoch_exhausted"

    def __init__(self, action_id: str):
        self.action_id = action_id
        super().__init__(f"action {action_id!r} fencing epoch cannot advance")


class LeaseStateError(LeaseError):
    """A lease transaction failed without being reported as successful."""

    code = "lease_state_error"

    def __init__(self, operation: str, detail: str):
        self.operation = operation
        self.detail = detail
        super().__init__(f"{operation}: {detail}")


class LockBusy(LeaseError):
    """The requested non-blocking advisory lock is held elsewhere."""

    code = "lock_busy"

    def __init__(self, path: Path):
        self.path = Path(path)
        super().__init__(f"advisory lock {path} is busy")


class LockPrincipalUnknown(LeaseError):
    """An actual live advisory lock handle could not be established."""

    code = "lock_principal_unknown"

    def __init__(self, path: Path, detail: str):
        self.path = Path(path)
        self.detail = detail
        super().__init__(f"cannot establish advisory lock principal for {path}: {detail}")


class GuardPoint(str, Enum):
    """Every ADR-0013 principal guard entry point owned by this layer."""

    HEARTBEAT_RENEW = "heartbeat-renew"
    EFFECT_START = "effect-start"
    SUBMIT = "submit"
    COMPLETION = "completion"
    APPLY = "apply"
    CLEANUP = "cleanup"


@dataclass(frozen=True)
class LeasePrincipal:
    """One engine-owned action claim incarnation and its liveness-only deadline."""

    run_id: str
    action_id: str
    owner_token: str
    fencing_epoch: int
    entity_version: int
    monotonic_deadline: float

    @property
    def cas_tuple(self) -> tuple[str, int, int]:
        """Return the exact tuple checked at every guarded entry point."""
        return (self.owner_token, self.fencing_epoch, self.entity_version)

    def is_expired_hint(self, *, monotonic_now: float | None = None) -> bool:
        """Return a liveness hint; callers must not use it as mutation authority."""
        now = time.monotonic() if monotonic_now is None else monotonic_now
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
            raise ValueError("monotonic_now must be a finite number")
        return float(now) >= self.monotonic_deadline


@dataclass(frozen=True)
class AdvisoryLockHandle:
    """Proof object whose descriptor remains open for the context lifetime."""

    path: Path
    _descriptor: int

    def fileno(self) -> int:
        return self._descriptor


def _nonempty(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _validate_entity_version(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("expected_entity_version must be a non-negative integer")
    return value


def _lease_times(ttl_seconds: float) -> tuple[str, float]:
    if (isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float))
            or not math.isfinite(ttl_seconds) or ttl_seconds <= 0):
        raise ValueError("ttl_seconds must be a positive finite number")
    try:
        wall_expiry = datetime.now(timezone.utc) + timedelta(seconds=float(ttl_seconds))
    except (OverflowError, ValueError) as error:
        raise ValueError("ttl_seconds is outside the supported datetime range") from error
    return (
        wall_expiry.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        time.monotonic() + float(ttl_seconds),
    )


def _observed_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _new_owner_token(previous: str | None = None) -> str:
    for _ in range(4):
        token = secrets.token_urlsafe(_TOKEN_BYTES)
        if isinstance(token, str) and token and token != previous:
            return token
    raise LeaseStateError("generate owner token", "CSPRNG did not produce a fresh opaque token")


class LeaseManager:
    """Compose lease primitives over one project's existing runtime store."""

    def __init__(self, store: RunStore):
        if not isinstance(store, RunStore):
            raise TypeError("store must be a RunStore")
        self._store = store

    @contextmanager
    def _transaction(
            self, action_id: str, operation: str, *, principal_required: bool) -> Iterator[None]:
        connection = self._store._connection  # noqa: SLF001 - package-internal composition boundary
        with self._store._connection_lock:  # noqa: SLF001 - serialize one shared connection
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.DatabaseError as error:
                if principal_required:
                    raise LeasePrincipalUnknown(
                        action_id, operation, f"cannot begin principal read: {error}") from error
                raise LeaseStateError(operation, f"cannot begin lease transaction: {error}") from error
            try:
                yield
            except BaseException as operation_error:
                try:
                    if connection.in_transaction:
                        connection.rollback()
                except sqlite3.DatabaseError as rollback_error:
                    raise LeaseStateError(
                        operation, f"rollback failed after guarded error: {rollback_error}"
                    ) from operation_error
                raise
            try:
                connection.commit()
            except sqlite3.DatabaseError as error:
                try:
                    if connection.in_transaction:
                        connection.rollback()
                except sqlite3.DatabaseError as rollback_error:
                    raise LeaseStateError(
                        operation,
                        f"commit failed ({error}); rollback also failed ({rollback_error})",
                    ) from error
                raise LeaseStateError(operation, f"cannot commit lease transaction: {error}") from error

    def _load_action_locked(self, action_id: str, operation: str):
        try:
            return self._store._load_record(  # noqa: SLF001 - validate within the same transaction
                EntityKind.ACTION, action_id)
        except (StoreError, sqlite3.DatabaseError) as error:
            raise LeasePrincipalUnknown(action_id, operation, str(error)) from error

    def _lease_rows_locked(self, action_id: str, operation: str):
        try:
            return self._store._connection.execute(  # noqa: SLF001
                "SELECT lease_id, run_id, entity_kind, entity_id, entity_version, "
                "owner_token, fencing_epoch, expires_at, observed_at FROM leases "
                "WHERE lease_id = ? OR (entity_kind = ? AND entity_id = ?)",
                (action_id, EntityKind.ACTION.value, action_id),
            ).fetchall()
        except sqlite3.DatabaseError as error:
            raise LeasePrincipalUnknown(action_id, operation, f"cannot read lease row: {error}") from error

    @staticmethod
    def _valid_epoch(value: object, *, allow_zero: bool = False) -> bool:
        minimum = 0 if allow_zero else 1
        return (not isinstance(value, bool) and isinstance(value, int)
                and minimum <= value <= _MAX_FENCING_EPOCH)

    def _read_current_locked(self, principal: LeasePrincipal, operation: str):
        if not isinstance(principal, LeasePrincipal):
            raise TypeError("principal must be a LeasePrincipal")
        action_id = _nonempty(principal.action_id, "principal.action_id")
        action = self._load_action_locked(action_id, operation)
        rows = self._lease_rows_locked(action_id, operation)
        if len(rows) != 1:
            raise LeasePrincipalUnknown(
                action_id, operation,
                "current action lease row is missing or has ambiguous duplicates")
        row = rows[0]
        owner_token = row["owner_token"]
        epoch = row["fencing_epoch"]
        lease_version = row["entity_version"]
        if (row["lease_id"] != action_id
                or row["entity_kind"] != EntityKind.ACTION.value
                or row["entity_id"] != action_id
                or row["run_id"] != action.run_id
                or not isinstance(owner_token, str) or not owner_token
                or not self._valid_epoch(epoch)
                or isinstance(lease_version, bool) or not isinstance(lease_version, int)
                or lease_version < 0
                or lease_version != action.version):
            raise LeasePrincipalUnknown(
                action_id, operation, "lease/action binding or current tuple is incoherent")
        current_identity = (
            action.run_id, action_id, owner_token, epoch, lease_version)
        expected_identity = (
            principal.run_id, principal.action_id, principal.owner_token,
            principal.fencing_epoch, principal.entity_version)
        if current_identity != expected_identity:
            raise LeasePrincipalMismatch(action_id, operation)
        return action, row

    def _cas_current_locked(self, principal: LeasePrincipal, operation: str) -> None:
        try:
            result = self._store._connection.execute(  # noqa: SLF001
                "UPDATE leases SET observed_at = observed_at "
                "WHERE lease_id = ? AND run_id = ? AND entity_kind = ? AND entity_id = ? "
                "AND owner_token = ? AND fencing_epoch = ? AND entity_version = ? "
                "AND EXISTS (SELECT 1 FROM actions WHERE action_id = ? AND run_id = ? "
                "AND version = ?)",
                (principal.action_id, principal.run_id, EntityKind.ACTION.value,
                 principal.action_id, principal.owner_token, principal.fencing_epoch,
                 principal.entity_version, principal.action_id, principal.run_id,
                 principal.entity_version),
            )
        except sqlite3.DatabaseError as error:
            raise LeasePrincipalUnknown(
                principal.action_id, operation, f"principal CAS unavailable: {error}") from error
        if result.rowcount != 1:
            self._read_current_locked(principal, operation)
            raise LeasePrincipalUnknown(
                principal.action_id, operation, "principal CAS did not select one current row")

    def claim(
            self, action_id: str, *, expected_entity_version: int,
            ttl_seconds: float) -> LeasePrincipal:
        """Claim an unowned action without treating an expired timestamp as authority."""
        identity = _nonempty(action_id, "action_id")
        expected = _validate_entity_version(expected_entity_version)
        expires_at, deadline = _lease_times(ttl_seconds)
        owner_token = _new_owner_token()
        operation = "claim"
        with self._transaction(identity, operation, principal_required=False):
            action = self._load_action_locked(identity, operation)
            if action.version != expected:
                raise LeasePrincipalMismatch(identity, operation)
            rows = self._lease_rows_locked(identity, operation)
            observed = _observed_at()
            if not rows:
                epoch = 1
                try:
                    self._store._connection.execute(  # noqa: SLF001
                        "INSERT INTO leases(lease_id, run_id, entity_kind, entity_id, "
                        "entity_version, owner_token, fencing_epoch, expires_at, observed_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (identity, action.run_id, EntityKind.ACTION.value, identity, expected,
                         owner_token, epoch, expires_at, observed),
                    )
                except sqlite3.DatabaseError as error:
                    raise LeaseStateError(operation, str(error)) from error
            elif len(rows) == 1:
                row = rows[0]
                lease_version = row["entity_version"]
                if (row["lease_id"] != identity
                        or row["entity_kind"] != EntityKind.ACTION.value
                        or row["entity_id"] != identity
                        or row["run_id"] != action.run_id
                        or not self._valid_epoch(row["fencing_epoch"], allow_zero=True)
                        or isinstance(lease_version, bool)
                        or not isinstance(lease_version, int)
                        or lease_version < 0):
                    raise LeasePrincipalUnknown(
                        identity, operation, "stored lease identity or epoch is incoherent")
                if row["owner_token"] is not None:
                    if not isinstance(row["owner_token"], str) or not row["owner_token"]:
                        raise LeasePrincipalUnknown(
                            identity, operation, "stored owner token is malformed")
                    if (not self._valid_epoch(row["fencing_epoch"])
                            or lease_version != action.version):
                        raise LeasePrincipalUnknown(
                            identity, operation, "active lease/entity version is incoherent")
                    raise LeaseAlreadyClaimed(identity)
                if row["fencing_epoch"] >= _MAX_FENCING_EPOCH:
                    raise FencingEpochExhausted(identity)
                epoch = row["fencing_epoch"] + 1
                try:
                    result = self._store._connection.execute(  # noqa: SLF001
                        "UPDATE leases SET entity_version = ?, owner_token = ?, "
                        "fencing_epoch = ?, expires_at = ?, observed_at = ? "
                        "WHERE lease_id = ? AND run_id = ? AND entity_kind = ? AND entity_id = ? "
                        "AND owner_token IS NULL AND fencing_epoch = ? "
                        "AND EXISTS (SELECT 1 FROM actions WHERE action_id = ? AND run_id = ? "
                        "AND version = ?)",
                        (expected, owner_token, epoch, expires_at, observed, identity,
                         action.run_id, EntityKind.ACTION.value, identity,
                         row["fencing_epoch"], identity, action.run_id, expected),
                    )
                except sqlite3.DatabaseError as error:
                    raise LeaseStateError(operation, str(error)) from error
                if result.rowcount != 1:
                    raise LeasePrincipalMismatch(identity, operation)
            else:
                raise LeasePrincipalUnknown(
                    identity, operation, "current action lease has ambiguous duplicates")
        return LeasePrincipal(
            action.run_id, identity, owner_token, epoch, expected, deadline)

    def renew(self, principal: LeasePrincipal, *, ttl_seconds: float) -> LeasePrincipal:
        """Renew heartbeat telemetry only for the exact current principal."""
        expires_at, deadline = _lease_times(ttl_seconds)
        operation = GuardPoint.HEARTBEAT_RENEW.value
        with self._transaction(principal.action_id, operation, principal_required=True):
            self._read_current_locked(principal, operation)
            observed = _observed_at()
            try:
                result = self._store._connection.execute(  # noqa: SLF001
                    "UPDATE leases SET expires_at = ?, observed_at = ? "
                    "WHERE lease_id = ? AND run_id = ? AND owner_token = ? "
                    "AND fencing_epoch = ? AND entity_version = ?",
                    (expires_at, observed, principal.action_id, principal.run_id,
                     principal.owner_token, principal.fencing_epoch, principal.entity_version),
                )
                if result.rowcount == 1:
                    self._store._connection.execute(  # noqa: SLF001
                        "INSERT INTO action_runtime(action_id, entity_version, phase, "
                        "heartbeat_at, observed_at) VALUES (?, ?, NULL, ?, ?) "
                        "ON CONFLICT(action_id) DO UPDATE SET "
                        "entity_version = excluded.entity_version, "
                        "heartbeat_at = excluded.heartbeat_at, "
                        "observed_at = excluded.observed_at",
                        (principal.action_id, principal.entity_version, observed, observed),
                    )
            except sqlite3.DatabaseError as error:
                raise LeasePrincipalUnknown(
                    principal.action_id, operation, f"heartbeat CAS unavailable: {error}") from error
            if result.rowcount != 1:
                self._read_current_locked(principal, operation)
                raise LeasePrincipalUnknown(
                    principal.action_id, operation,
                    "heartbeat CAS did not select one current row")
        return replace(principal, monotonic_deadline=deadline)

    def release(self, principal: LeasePrincipal) -> None:
        """Release an exact principal while preserving its durable fencing epoch."""
        operation = "release"
        with self._transaction(principal.action_id, operation, principal_required=True):
            self._read_current_locked(principal, operation)
            try:
                result = self._store._connection.execute(  # noqa: SLF001
                    "UPDATE leases SET owner_token = NULL, expires_at = NULL, observed_at = ? "
                    "WHERE lease_id = ? AND run_id = ? AND owner_token = ? "
                    "AND fencing_epoch = ? AND entity_version = ?",
                    (_observed_at(), principal.action_id, principal.run_id,
                     principal.owner_token, principal.fencing_epoch, principal.entity_version),
                )
            except sqlite3.DatabaseError as error:
                raise LeasePrincipalUnknown(
                    principal.action_id, operation, f"release CAS unavailable: {error}") from error
            if result.rowcount != 1:
                self._read_current_locked(principal, operation)
                raise LeasePrincipalUnknown(
                    principal.action_id, operation,
                    "release CAS did not select one current row")

    def reclaim(
            self, principal: LeasePrincipal, *, quiescence_probe: Callable[[], bool],
            effect_absence_probe: Callable[[], bool], ttl_seconds: float) -> LeasePrincipal:
        """Reclaim only after fresh positive quiescence and effect-absence observations."""
        if not callable(quiescence_probe) or not callable(effect_absence_probe):
            raise TypeError("reclaim probes must be callable")
        expires_at, deadline = _lease_times(ttl_seconds)
        owner_token = _new_owner_token(principal.owner_token)
        operation = "reclaim"
        with self._transaction(principal.action_id, operation, principal_required=True):
            action, row = self._read_current_locked(principal, operation)
            try:
                quiescent = quiescence_probe()
            except Exception as error:
                raise LeaseReclaimRefused(principal.action_id, "quiescence (observation failed)") from error
            if quiescent is not True:
                raise LeaseReclaimRefused(principal.action_id, "quiescence")
            try:
                effect_absent = effect_absence_probe()
            except Exception as error:
                raise LeaseReclaimRefused(
                    principal.action_id, "effect absence (observation failed)") from error
            if effect_absent is not True:
                raise LeaseReclaimRefused(principal.action_id, "effect absence")

            self._read_current_locked(principal, operation)
            if row["fencing_epoch"] >= _MAX_FENCING_EPOCH:
                raise FencingEpochExhausted(principal.action_id)
            next_epoch = row["fencing_epoch"] + 1
            try:
                result = self._store._connection.execute(  # noqa: SLF001
                    "UPDATE leases SET owner_token = ?, fencing_epoch = ?, expires_at = ?, "
                    "observed_at = ? WHERE lease_id = ? AND run_id = ? AND owner_token = ? "
                    "AND fencing_epoch = ? AND entity_version = ? "
                    "AND EXISTS (SELECT 1 FROM actions WHERE action_id = ? AND run_id = ? "
                    "AND version = ?)",
                    (owner_token, next_epoch, expires_at, _observed_at(), principal.action_id,
                     principal.run_id, principal.owner_token, principal.fencing_epoch,
                     principal.entity_version, principal.action_id, principal.run_id,
                     principal.entity_version),
                )
            except sqlite3.DatabaseError as error:
                raise LeasePrincipalUnknown(
                    principal.action_id, operation, f"reclaim CAS unavailable: {error}") from error
            if result.rowcount != 1:
                self._read_current_locked(principal, operation)
                raise LeasePrincipalUnknown(
                    principal.action_id, operation,
                    "reclaim CAS did not select one current row")
        return LeasePrincipal(
            action.run_id, principal.action_id, owner_token, next_epoch,
            principal.entity_version, deadline)

    def _guard_operation(
            self, principal: LeasePrincipal, operation: str,
            callback: Callable[[], _T]) -> _T:
        """Commit one short entry mutation under the already-open lease transaction.

        The callback is the guarded DB/telemetry entry mutation, not the long-running
        external effect. It must not open another RunStore transaction.
        """
        if not callable(callback):
            raise TypeError("guard callback must be callable")
        with self._transaction(principal.action_id, operation, principal_required=True):
            self._read_current_locked(principal, operation)
            self._cas_current_locked(principal, operation)
            return callback()

    def _guard(
            self, principal: LeasePrincipal, point: GuardPoint,
            callback: Callable[[], _T]) -> _T:
        return self._guard_operation(principal, point.value, callback)

    def guard_heartbeat_renew(
            self, principal: LeasePrincipal, callback: Callable[[], _T]) -> _T:
        return self._guard(principal, GuardPoint.HEARTBEAT_RENEW, callback)

    def guard_effect_start(
            self, principal: LeasePrincipal, callback: Callable[[], _T]) -> _T:
        return self._guard(principal, GuardPoint.EFFECT_START, callback)

    def guard_submit(self, principal: LeasePrincipal, callback: Callable[[], _T]) -> _T:
        return self._guard(principal, GuardPoint.SUBMIT, callback)

    def guard_completion(self, principal: LeasePrincipal, callback: Callable[[], _T]) -> _T:
        return self._guard(principal, GuardPoint.COMPLETION, callback)

    def guard_apply(self, principal: LeasePrincipal, callback: Callable[[], _T]) -> _T:
        return self._guard(principal, GuardPoint.APPLY, callback)

    def guard_cleanup(self, principal: LeasePrincipal, callback: Callable[[], _T]) -> _T:
        return self._guard(principal, GuardPoint.CLEANUP, callback)

    @contextmanager
    def advisory_lock(
            self, path: Path, principal: LeasePrincipal, *,
            blocking: bool = True) -> Iterator[AdvisoryLockHandle]:
        """Hold a real fcntl handle, then recheck the DB tuple before entry."""
        supplied_lock_path = Path(path)
        state_directory = self._store.database_path.parent
        current_parent = supplied_lock_path.parent
        while True:
            try:
                parent_info = current_parent.lstat()
            except OSError as error:
                raise EngineOwnedPathUnverifiableError(
                    supplied_lock_path,
                    f"cannot inspect lock directory traversal: {error}") from error
            if stat.S_ISLNK(parent_info.st_mode):
                raise StatePathSymlinkError(current_parent)
            if not stat.S_ISDIR(parent_info.st_mode):
                raise StatePathTypeMismatchError(current_parent, "directory")
            try:
                if os.path.samefile(current_parent, state_directory):
                    break
            except OSError as error:
                raise EngineOwnedPathUnverifiableError(
                    supplied_lock_path,
                    f"cannot establish lock directory containment: {error}") from error
            parent = current_parent.parent
            if parent == current_parent:
                _require_contained_state_path(supplied_lock_path, state_directory)
            current_parent = parent
        try:
            canonical_parent = supplied_lock_path.parent.resolve(strict=True)
        except OSError as error:
            raise EngineOwnedPathUnverifiableError(
                supplied_lock_path, f"cannot resolve lock parent: {error}") from error
        lock_path = canonical_parent / supplied_lock_path.name
        _require_contained_state_path(lock_path, state_directory)
        _verify_state_directory(
            state_directory, self._store.project_root, newly_created=False)
        relative_lock = lock_path.relative_to(state_directory)
        current_directory = state_directory
        for component in relative_lock.parts[:-1]:
            current_directory /= component
            _verify_state_directory(
                current_directory, state_directory, newly_created=False)

        descriptor: int | None = None
        acquired = False
        try:
            descriptor = _open_mutable_state_file(
                lock_path, state_directory, create=True)
            operation = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            try:
                fcntl.flock(descriptor, operation)
            except OSError as error:
                if not blocking and error.errno in {errno.EACCES, errno.EAGAIN}:
                    raise LockBusy(lock_path) from error
                raise LockPrincipalUnknown(lock_path, str(error)) from error
            acquired = True

            self._guard_operation(principal, "os-lock-entry", lambda: None)
            yield AdvisoryLockHandle(lock_path, descriptor)
        finally:
            if descriptor is not None:
                if acquired:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                    finally:
                        os.close(descriptor)
                else:
                    os.close(descriptor)
