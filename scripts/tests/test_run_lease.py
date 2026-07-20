#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Contract tests for the M1-B lease, fencing, and advisory-lock layer."""
from __future__ import annotations

import errno
import fcntl
import os
import sqlite3
import stat
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
_WAYSTONE_PRELOADED = "waystone" in sys.modules
sys.path.insert(0, str(ROOT))
try:
    from waystone.runs import lease as lease_module  # noqa: E402
    from waystone.runs import store as store_module  # noqa: E402
    from waystone.runs.lease import (  # noqa: E402
        FencingEpochExhausted,
        LeaseAlreadyClaimed,
        LeaseManager,
        LeasePrincipalMismatch,
        LeasePrincipalUnknown,
        LeaseReclaimRefused,
        LeaseStateError,
        LockBusy,
        LockPrincipalUnknown,
    )
    from waystone.runs.store import (  # noqa: E402
        EntityKind,
        FilesystemInfo,
        RunStore,
        StatePathSymlinkError,
        TransitionReason,
    )
finally:
    sys.path.pop(0)
    if not _WAYSTONE_PRELOADED:
        sys.modules.pop("waystone", None)
del _WAYSTONE_PRELOADED


class RunLeaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name) / "project"
        self.root.mkdir()
        (self.root / ".waystone.yml").write_text(
            "version: 1\nproject: lease-fixture\n", encoding="utf-8")
        with mock.patch.object(
                store_module, "_probe_state_filesystem",
                return_value=FilesystemInfo(
                    filesystem="apfs", mount_point=Path("/"), writable=True)):
            self.store = RunStore.open(self.root)
        self.addCleanup(self.store.close)
        self.manager = LeaseManager(self.store)
        self._action_number = 0

    def action(self):
        self._action_number += 1
        suffix = str(self._action_number)
        run = self.store.create_run()
        self.store.create_job(run.entity_id, f"job-{suffix}")
        self.store.create_attempt(
            run.entity_id, f"job-{suffix}", f"attempt-{suffix}")
        action = self.store.create_action(
            run.entity_id, f"job-{suffix}", f"attempt-{suffix}", f"action-{suffix}")
        return action

    def second_store(self) -> RunStore:
        with mock.patch.object(
                store_module, "_probe_state_filesystem",
                return_value=FilesystemInfo(
                    filesystem="apfs", mount_point=Path("/"), writable=True)):
            opened = RunStore.open(self.root)
        self.addCleanup(opened.close)
        return opened

    def snapshot(self):
        result = {}
        for table, order in (
                ("actions", "action_id"),
                ("leases", "lease_id"),
                ("action_runtime", "action_id"),
                ("transitions", "transition_id")):
            result[table] = [
                tuple(row) for row in self.store._connection.execute(  # noqa: SLF001
                    f"SELECT * FROM {table} ORDER BY {order}").fetchall()
            ]
        return result

    @staticmethod
    def guards(manager: LeaseManager):
        return (
            manager.guard_heartbeat_renew,
            manager.guard_effect_start,
            manager.guard_submit,
            manager.guard_completion,
            manager.guard_apply,
            manager.guard_cleanup,
        )

    def test_claim_renew_release_use_csprng_and_never_reuse_fencing_epoch(self):
        action = self.action()
        ambient = {
            "WAYSTONE_OWNER_TOKEN": "ambient-owner-token",
            "OWNER_TOKEN": "ambient-owner-token",
            "HOSTNAME": "ambient-host",
        }
        with mock.patch.dict(os.environ, ambient, clear=False), mock.patch.object(
                lease_module.secrets, "token_urlsafe",
                side_effect=("csprng-owner-one", "csprng-owner-two")) as token_urlsafe:
            first = self.manager.claim(
                action.entity_id, expected_entity_version=0, ttl_seconds=30)
            renewed = self.manager.renew(first, ttl_seconds=60)
            self.manager.release(renewed)
            second = self.manager.claim(
                action.entity_id, expected_entity_version=0, ttl_seconds=30)

        self.assertEqual(first.owner_token, "csprng-owner-one")
        self.assertNotIn(first.owner_token, ambient.values())
        self.assertEqual(first.fencing_epoch, 1)
        self.assertEqual(renewed.cas_tuple, first.cas_tuple)
        self.assertGreater(renewed.monotonic_deadline, first.monotonic_deadline)
        self.assertEqual(second.owner_token, "csprng-owner-two")
        self.assertEqual(second.fencing_epoch, 2)
        self.assertEqual(token_urlsafe.call_args_list, [mock.call(32), mock.call(32)])
        self.assertFalse(first.is_expired_hint(
            monotonic_now=first.monotonic_deadline - 0.001))
        self.assertTrue(first.is_expired_hint(
            monotonic_now=first.monotonic_deadline))

        row = self.store._connection.execute(  # noqa: SLF001
            "SELECT owner_token, fencing_epoch, entity_version FROM leases "
            "WHERE lease_id = ?", (action.entity_id,)).fetchone()
        self.assertEqual(tuple(row), (second.owner_token, 2, 0))
        runtime = self.store._connection.execute(  # noqa: SLF001
            "SELECT entity_version, heartbeat_at FROM action_runtime WHERE action_id = ?",
            (action.entity_id,),
        ).fetchone()
        self.assertEqual(runtime[0], 0)
        self.assertTrue(runtime[1])

    def test_expiry_is_only_a_hint_and_never_authorizes_claim_or_stale_write(self):
        action = self.action()
        first = self.manager.claim(
            action.entity_id, expected_entity_version=0, ttl_seconds=30)
        expired = replace(first, monotonic_deadline=0.0)
        self.store._connection.execute(  # noqa: SLF001 - stored wall value is deliberately stale
            "UPDATE leases SET expires_at = '1970-01-01T00:00:00Z' WHERE lease_id = ?",
            (action.entity_id,),
        )
        self.assertTrue(expired.is_expired_hint(monotonic_now=1.0))

        with self.assertRaises(LeaseAlreadyClaimed) as claimed:
            self.manager.claim(
                action.entity_id, expected_entity_version=0, ttl_seconds=30)
        self.assertEqual(claimed.exception.code, "lease_already_claimed")

        current = self.manager.reclaim(
            first,
            quiescence_probe=lambda: True,
            effect_absence_probe=lambda: True,
            ttl_seconds=30,
        )
        effects = []
        with self.assertRaises(LeasePrincipalMismatch) as stale:
            self.manager.guard_effect_start(expired, lambda: effects.append("stale"))
        self.assertEqual(stale.exception.code, "lease_principal_mismatch")
        self.assertEqual(effects, [])
        self.assertEqual(current.fencing_epoch, first.fencing_epoch + 1)

    def test_fixture_6_all_guard_entries_fail_typed_before_callback(self):
        """M1-B exit fixture 6: stale/unknown principals cause mutation and effect count 0."""
        action = self.action()
        current = self.manager.claim(
            action.entity_id, expected_entity_version=0, ttl_seconds=30)

        for guard in self.guards(self.manager):
            with self.subTest(guard=guard.__name__, principal="mismatch"):
                calls = []
                before = self.snapshot()
                stale = replace(current, owner_token=f"stale-{guard.__name__}")
                with self.assertRaises(LeasePrincipalMismatch) as raised:
                    guard(stale, lambda: calls.append("called"))
                self.assertEqual(raised.exception.code, "lease_principal_mismatch")
                self.assertEqual(calls, [])
                self.assertEqual(self.snapshot(), before)

            with self.subTest(guard=guard.__name__, principal="unknown"):
                self.store._connection.execute(  # noqa: SLF001 - corrupt-principal fixture
                    "UPDATE leases SET owner_token = NULL WHERE lease_id = ?",
                    (action.entity_id,),
                )
                calls = []
                before = self.snapshot()
                with self.assertRaises(LeasePrincipalUnknown) as raised:
                    guard(current, lambda: calls.append("called"))
                self.assertEqual(raised.exception.code, "lease_principal_unknown")
                self.assertEqual(calls, [])
                self.assertEqual(self.snapshot(), before)
                self.store._connection.execute(  # noqa: SLF001 - restore isolated fixture
                    "UPDATE leases SET owner_token = ? WHERE lease_id = ?",
                    (current.owner_token, action.entity_id),
                )

        stale = replace(current, owner_token="stale-heartbeat-owner")
        before = self.snapshot()
        with self.assertRaises(LeasePrincipalMismatch):
            self.manager.renew(stale, ttl_seconds=30)
        with self.assertRaises(LeasePrincipalMismatch):
            self.manager.release(stale)
        self.assertEqual(self.snapshot(), before)
        self.store._connection.execute(  # noqa: SLF001 - unreadable heartbeat fixture
            "UPDATE leases SET owner_token = NULL WHERE lease_id = ?",
            (action.entity_id,),
        )
        before = self.snapshot()
        with self.assertRaises(LeasePrincipalUnknown):
            self.manager.renew(current, ttl_seconds=30)
        self.assertEqual(self.snapshot(), before)
        self.store._connection.execute(  # noqa: SLF001 - restore isolated fixture
            "UPDATE leases SET owner_token = ? WHERE lease_id = ?",
            (current.owner_token, action.entity_id),
        )

        calls = []
        for guard in self.guards(self.manager):
            self.assertEqual(
                guard(current, lambda name=guard.__name__: calls.append(name)), None)
        self.assertEqual(calls, [guard.__name__ for guard in self.guards(self.manager)])

    def test_principal_classification_covers_each_tuple_axis_and_incoherent_authority(self):
        action = self.action()
        current = self.manager.claim(
            action.entity_id, expected_entity_version=0, ttl_seconds=30)
        for stale in (
                replace(current, owner_token="wrong-token"),
                replace(current, fencing_epoch=current.fencing_epoch + 1),
                replace(current, entity_version=current.entity_version + 1)):
            with self.subTest(tuple=stale.cas_tuple):
                with self.assertRaises(LeasePrincipalMismatch):
                    self.manager.guard_submit(stale, lambda: self.fail("callback ran"))

        self.store._connection.execute(  # noqa: SLF001 - duplicate authority fixture
            "INSERT INTO leases(lease_id, run_id, entity_kind, entity_id, entity_version, "
            "owner_token, fencing_epoch) VALUES (?, ?, 'action', ?, 0, 'duplicate', 1)",
            ("foreign-lease", action.run_id, action.entity_id),
        )
        with self.assertRaises(LeasePrincipalUnknown):
            self.manager.guard_submit(current, lambda: self.fail("callback ran"))
        self.store._connection.execute(  # noqa: SLF001
            "DELETE FROM leases WHERE lease_id = 'foreign-lease'")

        self.store.record_transition(
            EntityKind.ACTION,
            action.entity_id,
            expected_version=0,
            next_state="process-started",
            reason=TransitionReason.PROCESS_STARTED,
        )
        with self.assertRaises(LeasePrincipalUnknown):
            self.manager.guard_submit(current, lambda: self.fail("callback ran"))
        with self.assertRaises(LeasePrincipalUnknown):
            self.manager.claim(
                action.entity_id, expected_entity_version=1, ttl_seconds=30)

        epoch_action = self.action()
        epoch_principal = self.manager.claim(
            epoch_action.entity_id, expected_entity_version=0, ttl_seconds=30)
        self.store._connection.execute(  # noqa: SLF001 - incoherent active epoch fixture
            "UPDATE leases SET fencing_epoch = 0 WHERE lease_id = ?",
            (epoch_action.entity_id,),
        )
        with self.assertRaises(LeasePrincipalUnknown):
            self.manager.claim(
                epoch_action.entity_id, expected_entity_version=0, ttl_seconds=30)
        with self.assertRaises(LeasePrincipalUnknown):
            self.manager.guard_submit(
                epoch_principal, lambda: self.fail("callback ran"))

    def test_guarded_entry_commits_db_marker_and_rolls_back_failed_marker(self):
        action = self.action()
        principal = self.manager.claim(
            action.entity_id, expected_entity_version=0, ttl_seconds=30)

        def record_marker(phase: str) -> None:
            self.store._connection.execute(  # noqa: SLF001 - transaction-bound marker fixture
                "INSERT INTO action_runtime(action_id, entity_version, phase) VALUES (?, 0, ?) "
                "ON CONFLICT(action_id) DO UPDATE SET phase = excluded.phase",
                (action.entity_id, phase),
            )

        self.manager.guard_effect_start(
            principal, lambda: record_marker("effect-start-authorized"))
        row = self.store._connection.execute(  # noqa: SLF001
            "SELECT phase FROM action_runtime WHERE action_id = ?", (action.entity_id,)
        ).fetchone()
        self.assertEqual(row[0], "effect-start-authorized")

        def fail_after_marker() -> None:
            record_marker("must-rollback")
            raise RuntimeError("injected guarded mutation failure")

        with self.assertRaisesRegex(RuntimeError, "injected guarded mutation failure"):
            self.manager.guard_submit(principal, fail_after_marker)
        row = self.store._connection.execute(  # noqa: SLF001
            "SELECT phase FROM action_runtime WHERE action_id = ?", (action.entity_id,)
        ).fetchone()
        self.assertEqual(row[0], "effect-start-authorized")

    def test_commit_and_rollback_faults_remain_typed(self):
        action = self.action()
        principal = self.manager.claim(
            action.entity_id, expected_entity_version=0, ttl_seconds=30)
        connection = self.store._connection  # noqa: SLF001

        class FaultConnection:
            def execute(self, *args, **kwargs):
                return connection.execute(*args, **kwargs)

            @property
            def in_transaction(self):
                return connection.in_transaction

            @staticmethod
            def commit():
                raise sqlite3.OperationalError("commit-fault")

            @staticmethod
            def rollback():
                raise sqlite3.OperationalError("rollback-fault")

        self.store._connection = FaultConnection()  # noqa: SLF001 - transaction fault fixture
        try:
            with self.assertRaises(LeaseStateError) as raised:
                self.manager.guard_submit(principal, lambda: None)
            self.assertEqual(raised.exception.code, "lease_state_error")
            self.assertIn("rollback also failed", str(raised.exception))
        finally:
            self.store._connection = connection  # noqa: SLF001
            if connection.in_transaction:
                connection.rollback()

    def test_fixture_7_lock_waiter_rechecks_db_tuple_after_actual_handle_acquisition(self):
        """M1-B exit fixture 7: post-acquire DB recheck blocks a stale critical section."""
        action = self.action()
        first = self.manager.claim(
            action.entity_id, expected_entity_version=0, ttl_seconds=30)
        lock_path = self.root / ".waystone" / "fixture-7.lock"
        holder = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(lambda: os.close(holder))
        real_flock = fcntl.flock
        real_flock(holder, fcntl.LOCK_EX)
        waiting = threading.Event()
        entered = []
        failures = []

        def observed_flock(descriptor: int, operation: int):
            if descriptor != holder and operation & fcntl.LOCK_EX:
                waiting.set()
            return real_flock(descriptor, operation)

        def contender() -> None:
            try:
                with self.manager.advisory_lock(lock_path, first):
                    entered.append("critical")
            except BaseException as error:
                failures.append(error)

        with mock.patch.object(lease_module.fcntl, "flock", side_effect=observed_flock):
            thread = threading.Thread(target=contender)
            thread.start()
            self.assertTrue(waiting.wait(timeout=5), "contender did not reach actual flock")
            current = self.manager.reclaim(
                first,
                quiescence_probe=lambda: True,
                effect_absence_probe=lambda: True,
                ttl_seconds=30,
            )
            real_flock(holder, fcntl.LOCK_UN)
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

        self.assertEqual(entered, [])
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], LeasePrincipalMismatch)
        self.assertEqual(failures[0].code, "lease_principal_mismatch")
        self.assertEqual(failures[0].operation, "os-lock-entry")

        with self.manager.advisory_lock(lock_path, current, blocking=False) as handle:
            self.assertGreaterEqual(handle.fileno(), 0)
            with self.assertRaises(LockBusy):
                with self.manager.advisory_lock(lock_path, current, blocking=False):
                    self.fail("second critical section entered")

    def test_lock_contention_and_unprovable_handle_are_typed(self):
        action = self.action()
        principal = self.manager.claim(
            action.entity_id, expected_entity_version=0, ttl_seconds=30)
        lock_path = self.root / ".waystone" / "typed-lock.lock"
        holder = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        real_flock = fcntl.flock
        try:
            real_flock(holder, fcntl.LOCK_EX)
            with self.assertRaises(LockBusy) as busy:
                with self.manager.advisory_lock(lock_path, principal, blocking=False):
                    self.fail("busy lock entered")
            self.assertEqual(busy.exception.code, "lock_busy")
        finally:
            real_flock(holder, fcntl.LOCK_UN)
            os.close(holder)

        with mock.patch.object(
                lease_module.fcntl, "flock",
                side_effect=OSError(errno.EIO, "injected handle failure")):
            with self.assertRaises(LockPrincipalUnknown) as unknown:
                with self.manager.advisory_lock(lock_path, principal):
                    self.fail("unknown lock entered")
        self.assertEqual(unknown.exception.code, "lock_principal_unknown")

    def test_advisory_lock_creation_is_0600_and_nofollow(self):
        action = self.action()
        principal = self.manager.claim(
            action.entity_id, expected_entity_version=0, ttl_seconds=30)
        lock_path = self.root / ".waystone" / "permission.lock"
        real_open = os.open
        observations: list[tuple[int, int, int]] = []

        def inspect_open(path, flags, mode=0o777, *, dir_fd=None):
            descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
            if Path(path).name == lock_path.name and flags & os.O_CREAT:
                observations.append((
                    flags,
                    mode,
                    stat.S_IMODE(os.fstat(descriptor).st_mode),
                ))
            return descriptor

        previous_umask = os.umask(0)
        try:
            with mock.patch.object(
                    lease_module.os, "open", side_effect=inspect_open):
                with self.manager.advisory_lock(lock_path, principal) as handle:
                    self.assertEqual(stat.S_IMODE(os.fstat(handle.fileno()).st_mode), 0o600)
        finally:
            os.umask(previous_umask)

        self.assertEqual(stat.S_IMODE(lock_path.lstat().st_mode), 0o600)
        self.assertEqual(len(observations), 1)
        flags, requested_mode, created_mode = observations[0]
        self.assertTrue(flags & os.O_NOFOLLOW)
        self.assertEqual(requested_mode, 0o600)
        self.assertEqual(created_mode, 0o600)

    def test_advisory_lock_symlink_is_refused_at_open_before_flock(self):
        action = self.action()
        principal = self.manager.claim(
            action.entity_id, expected_entity_version=0, ttl_seconds=30)
        target = self.root / "regular-lock-target"
        target.write_bytes(b"target remains unchanged")
        target.chmod(0o600)
        lock_path = self.root / ".waystone" / "symlink.lock"
        lock_path.symlink_to(target)
        real_open = os.open
        observed_flags: list[int] = []

        def inspect_open(path, flags, mode=0o777, *, dir_fd=None):
            if Path(path).name == lock_path.name:
                observed_flags.append(flags)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch.object(
                lease_module.os, "open", side_effect=inspect_open), \
                mock.patch.object(lease_module.fcntl, "flock") as flock:
            with self.assertRaises(StatePathSymlinkError) as raised:
                with self.manager.advisory_lock(lock_path, principal):
                    self.fail("symlinked lock entered")

        self.assertEqual(raised.exception.code, "state_path_symlink")
        self.assertTrue(observed_flags)
        self.assertTrue(all(flags & os.O_NOFOLLOW for flags in observed_flags))
        flock.assert_not_called()
        self.assertTrue(lock_path.is_symlink())
        self.assertEqual(target.read_bytes(), b"target remains unchanged")

    def test_reclaim_requires_fresh_positive_quiescence_and_effect_absence(self):
        action = self.action()
        principal = self.manager.claim(
            action.entity_id, expected_entity_version=0, ttl_seconds=30)
        original = self.snapshot()
        cases = (
            (lambda: False, lambda: True, "quiescence"),
            (lambda: True, lambda: False, "effect absence"),
            (lambda: None, lambda: True, "quiescence unknown"),
            (lambda: True, lambda: None, "effect absence unknown"),
        )
        for quiescence, absence, case in cases:
            with self.subTest(case=case):
                with self.assertRaises(LeaseReclaimRefused) as refused:
                    self.manager.reclaim(
                        principal,
                        quiescence_probe=quiescence,
                        effect_absence_probe=absence,
                        ttl_seconds=30,
                    )
                self.assertEqual(refused.exception.code, "lease_reclaim_refused")
                self.assertEqual(self.snapshot(), original)

        def unavailable():
            raise OSError("observation unavailable")

        with self.assertRaises(LeaseReclaimRefused):
            self.manager.reclaim(
                principal,
                quiescence_probe=unavailable,
                effect_absence_probe=lambda: True,
                ttl_seconds=30,
            )
        self.assertEqual(self.snapshot(), original)

    def test_fixture_8_reclaim_wins_cas_and_rejects_every_old_owner_path(self):
        """M1-B exit fixture 8: reclaim race has one principal and zero stale duplicates."""
        action = self.action()
        old = self.manager.claim(
            action.entity_id, expected_entity_version=0, ttl_seconds=30)
        competing_manager = LeaseManager(self.second_store())
        probe_entered = threading.Event()
        allow_reclaim = threading.Event()
        stale_effects = []

        def quiescence_probe() -> bool:
            probe_entered.set()
            self.assertTrue(allow_reclaim.wait(timeout=5))
            return True

        with ThreadPoolExecutor(max_workers=2) as executor:
            reclaim_future = executor.submit(
                self.manager.reclaim,
                old,
                quiescence_probe=quiescence_probe,
                effect_absence_probe=lambda: True,
                ttl_seconds=30,
            )
            self.assertTrue(probe_entered.wait(timeout=5))
            old_effect = executor.submit(
                competing_manager.guard_effect_start,
                old,
                lambda: stale_effects.append("old-effect"),
            )
            allow_reclaim.set()
            current = reclaim_future.result(timeout=5)
            with self.assertRaises(LeasePrincipalMismatch):
                old_effect.result(timeout=5)

        stale_callbacks = []
        old_paths = (
            lambda: self.manager.renew(old, ttl_seconds=30),
            lambda: self.manager.guard_effect_start(
                old, lambda: stale_callbacks.append("effect")),
            lambda: self.manager.guard_submit(
                old, lambda: stale_callbacks.append("submit")),
            lambda: self.manager.reclaim(
                old,
                quiescence_probe=lambda: True,
                effect_absence_probe=lambda: True,
                ttl_seconds=30,
            ),
            lambda: self.manager.guard_cleanup(
                old, lambda: stale_callbacks.append("cleanup")),
        )
        for path in old_paths:
            with self.subTest(path=path):
                with self.assertRaises(LeasePrincipalMismatch):
                    path()
        self.assertEqual(stale_effects, [])
        self.assertEqual(stale_callbacks, [])

        self.store._connection.execute(  # noqa: SLF001 - mock effect expected state
            "INSERT INTO action_runtime(action_id, entity_version, phase) VALUES (?, 0, NULL)",
            (action.entity_id,),
        )
        current_effects = []

        def cas_phase(expected, next_phase: str, effect: str) -> None:
            result = self.store._connection.execute(  # noqa: SLF001
                "UPDATE action_runtime SET phase = ? WHERE action_id = ? AND phase IS ?",
                (next_phase, action.entity_id, expected),
            )
            if result.rowcount != 1:
                raise RuntimeError("mock effect expected-state CAS lost")
            current_effects.append(effect)

        self.manager.guard_effect_start(
            current, lambda: cas_phase(None, "effect-started", "effect"))
        with self.assertRaisesRegex(RuntimeError, "expected-state CAS lost"):
            self.manager.guard_effect_start(
                current, lambda: cas_phase(None, "effect-started", "effect"))
        self.manager.guard_cleanup(
            current, lambda: cas_phase("effect-started", "cleaned", "cleanup"))
        with self.assertRaisesRegex(RuntimeError, "expected-state CAS lost"):
            self.manager.guard_cleanup(
                current, lambda: cas_phase("effect-started", "cleaned", "cleanup"))
        self.assertEqual(current_effects, ["effect", "cleanup"])

    def test_fixture_8_old_guarded_start_invalidates_stale_reclaim_evidence(self):
        """M1-B exit fixture 8 reverse schedule: observed effect blocks reclaim commit."""
        action = self.action()
        old = self.manager.claim(
            action.entity_id, expected_entity_version=0, ttl_seconds=30)
        competing_manager = LeaseManager(self.second_store())
        self.store._connection.execute(  # noqa: SLF001 - mock effect expected state
            "INSERT INTO action_runtime(action_id, entity_version, phase) VALUES (?, 0, NULL)",
            (action.entity_id,),
        )
        effect_entered = threading.Event()
        allow_effect_commit = threading.Event()
        effects = []

        def start_effect() -> None:
            result = self.store._connection.execute(  # noqa: SLF001
                "UPDATE action_runtime SET phase = 'effect-started' "
                "WHERE action_id = ? AND phase IS NULL",
                (action.entity_id,),
            )
            self.assertEqual(result.rowcount, 1)
            effects.append("effect")
            effect_entered.set()
            self.assertTrue(allow_effect_commit.wait(timeout=5))

        with ThreadPoolExecutor(max_workers=2) as executor:
            old_future = executor.submit(
                self.manager.guard_effect_start, old, start_effect)
            self.assertTrue(effect_entered.wait(timeout=5))
            reclaim_future = executor.submit(
                competing_manager.reclaim,
                old,
                quiescence_probe=lambda: True,
                effect_absence_probe=lambda: (
                    competing_manager._store._connection.execute(  # noqa: SLF001
                        "SELECT phase FROM action_runtime WHERE action_id = ?",
                        (action.entity_id,),
                    ).fetchone()[0] is None),
                ttl_seconds=30,
            )
            allow_effect_commit.set()
            old_future.result(timeout=5)
            with self.assertRaises(LeaseReclaimRefused):
                reclaim_future.result(timeout=5)

        self.assertEqual(effects, ["effect"])
        row = self.store._connection.execute(  # noqa: SLF001
            "SELECT owner_token, fencing_epoch FROM leases WHERE lease_id = ?",
            (action.entity_id,),
        ).fetchone()
        self.assertEqual(tuple(row), (old.owner_token, old.fencing_epoch))

    def test_concurrent_reclaimable_claim_has_one_winner_and_epoch_overflow_never_wraps(self):
        action = self.action()
        first = self.manager.claim(
            action.entity_id, expected_entity_version=0, ttl_seconds=30)
        self.manager.release(first)
        other_manager = LeaseManager(self.second_store())
        barrier = threading.Barrier(2)

        def compete(manager: LeaseManager):
            barrier.wait()
            try:
                return manager.claim(
                    action.entity_id, expected_entity_version=0, ttl_seconds=30)
            except LeaseAlreadyClaimed as error:
                return error

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(compete, (self.manager, other_manager)))
        winners = [result for result in results if not isinstance(result, LeaseAlreadyClaimed)]
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].fencing_epoch, first.fencing_epoch + 1)
        self.manager.release(winners[0])

        self.store._connection.execute(  # noqa: SLF001 - overflow boundary fixture
            "UPDATE leases SET fencing_epoch = ? WHERE lease_id = ?",
            ((1 << 63) - 1, action.entity_id),
        )
        with self.assertRaises(FencingEpochExhausted) as exhausted:
            self.manager.claim(
                action.entity_id, expected_entity_version=0, ttl_seconds=30)
        self.assertEqual(exhausted.exception.code, "fencing_epoch_exhausted")
        row = self.store._connection.execute(  # noqa: SLF001
            "SELECT owner_token, fencing_epoch FROM leases WHERE lease_id = ?",
            (action.entity_id,),
        ).fetchone()
        self.assertEqual(tuple(row), (None, (1 << 63) - 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
