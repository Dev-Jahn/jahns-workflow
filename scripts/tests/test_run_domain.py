"""Mechanically split tests loaded by run_tests.py."""
from __future__ import annotations

from support import *  # noqa: F401,F403

import json

import waystone.jobs.domain as domain
import waystone.jobs.profile_v1 as profile_v1
from waystone.jobs.domain import ExecutionCategory, ExecutorKind, Role, RoleBinding
from waystone.jobs.profile_v1 import (
    LegacySurfaceKind,
    ProfileV1,
    ProfileV1Refusal,
    ProfileV1RefusalCode,
)


class RunDomainTests(unittest.TestCase):
    @staticmethod
    def _profile_path(directory: str, body: str) -> Path:
        root = Path(directory) / "repo"
        path = root / ".waystone" / "profile.yml"
        path.parent.mkdir(parents=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_domain_enums_are_closed(self):
        self.assertEqual(
            [role.value for role in Role],
            ["coordinator", "worker", "verifier", "reviewer"],
        )
        self.assertEqual(
            [kind.value for kind in ExecutorKind],
            ["engine", "carrier", "user"],
        )
        self.assertEqual(
            [category.value for category in ExecutionCategory],
            ["in-session", "subagent", "external"],
        )

        for enum_type, unsupported in (
                (Role, "main"),
                (Role, "orchestrator"),
                (ExecutorKind, "worker"),
                (ExecutionCategory, "deterministic-workflow")):
            with self.subTest(enum=enum_type.__name__, value=unsupported):
                with self.assertRaises(ValueError):
                    enum_type(unsupported)

    def test_implementer_maps_to_worker_with_legacy_provenance_without_reissue(self):
        body = (
            "schema: waystone-profile-1\n"
            "bindings:\n"
            "  implementer: {execution: external-runner, backend: 'codex:gpt-test'}\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = self._profile_path(directory, body)
            original = path.read_bytes()

            result = profile_v1.read_profile_v1(path)

            self.assertIsInstance(result, ProfileV1)
            adapted = result.role_bindings[0]
            self.assertEqual(
                adapted.binding,
                RoleBinding(Role.WORKER, ExecutionCategory.EXTERNAL, "codex:gpt-test"),
            )
            self.assertEqual(adapted.provenance.legacy_role, "implementer")
            self.assertEqual(adapted.provenance.legacy_execution, "external-runner")
            self.assertEqual(path.read_bytes(), original)

        self.assertFalse(hasattr(profile_v1, "write_profile_v1"))
        self.assertFalse(hasattr(profile_v1, "dump_profile_v1"))

    def test_unsupported_binding_returns_typed_refusal(self):
        bodies = {
            "non-category execution": (
                "schema: waystone-profile-1\n"
                "bindings:\n"
                "  implementer: {execution: deterministic-workflow, "
                "backend: 'claude:opus'}\n"
            ),
            "unknown verifier entry": (
                "schema: waystone-profile-1\n"
                "bindings:\n"
                "  implementer: {execution: external-runner, backend: 'codex:gpt-test'}\n"
                "  verifier: {execution: external-runner, backend: 'codex:gpt-test', "
                "entry: unknown-review}\n"
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            for index, (case, body) in enumerate(bodies.items()):
                with self.subTest(case=case):
                    path = self._profile_path(f"{directory}/{index}", body)
                    result = profile_v1.read_profile_v1(path)
                    self.assertIsInstance(result, ProfileV1Refusal)
                    self.assertEqual(
                        result.code, ProfileV1RefusalCode.UNSUPPORTED_BINDING)
                    self.assertTrue(result.reason)
                    self.assertIsNotNone(result.legacy_role)

    def test_parse_failures_return_typed_refusal_without_last_value_wins(self):
        duplicate = (
            "schema: waystone-profile-1\n"
            "bindings:\n"
            "  implementer: {execution: deterministic-workflow, backend: 'claude:opus'}\n"
            "  implementer: {execution: external-runner, backend: 'codex:gpt-test'}\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = self._profile_path(directory, duplicate)
            result = profile_v1.read_profile_v1(path)
        self.assertIsInstance(result, ProfileV1Refusal)
        self.assertEqual(result.code, ProfileV1RefusalCode.INVALID_PROFILE)
        self.assertIn("duplicate", result.reason)

        unreadable = profile_v1.read_profile_v1("profile\0.yml")
        self.assertIsInstance(unreadable, ProfileV1Refusal)
        self.assertEqual(unreadable.code, ProfileV1RefusalCode.UNREADABLE)

    def test_profile_schema_fixture_read_round_trip_preserves_all_dispositions(self):
        body = (
            "schema: waystone-profile-1\n"
            "bindings:\n"
            "  main: {execution: main-session, backend: 'claude:opus'}\n"
            "  orchestrator: {execution: deterministic-workflow, backend: 'claude:opus'}\n"
            "  implementer: {execution: external-runner, backend: 'codex:gpt'}\n"
            "  clerk: {execution: forked-subagent, backend: 'local-runner:small'}\n"
            "  verifier: {backend: 'gemini:pro'}\n"
            "  reviewer: {execution: clean-subagent, backend: 'future.runner:model'}\n"
        )
        schema = json.loads(
            (SCRIPTS.parent / "templates" / "profile-schema.json").read_text(encoding="utf-8"))
        fixture = yaml.safe_load(body)
        self.assertEqual(
            set(fixture["bindings"]),
            set(schema["properties"]["bindings"]["properties"]),
        )

        with tempfile.TemporaryDirectory() as directory:
            path = self._profile_path(directory, body)
            original = path.read_bytes()
            result = profile_v1.read_profile_v1(path)

            self.assertIsInstance(result, ProfileV1)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(
                [adapted.binding.role for adapted in result.role_bindings],
                [Role.WORKER, Role.VERIFIER, Role.REVIEWER],
            )
            self.assertEqual(
                [adapted.binding.execution_category for adapted in result.role_bindings],
                [ExecutionCategory.EXTERNAL, ExecutionCategory.EXTERNAL,
                 ExecutionCategory.SUBAGENT],
            )
            self.assertEqual(
                [step.provenance.legacy_role for step in result.deterministic_steps],
                ["clerk"],
            )
            self.assertEqual(
                [surface.kind for surface in result.non_role_bindings],
                [LegacySurfaceKind.EXECUTION_LOCATION,
                 LegacySurfaceKind.ENGINE_ORCHESTRATION],
            )
            self.assertNotIn(
                Role.COORDINATOR,
                [adapted.binding.role for adapted in result.role_bindings],
            )

    def test_role_and_executor_kind_have_no_inference_api(self):
        self.assertEqual(
            list(RoleBinding.__dataclass_fields__),
            ["role", "execution_category", "backend"],
        )
        for name in (
                "executor_kind_for_role",
                "role_for_executor_kind",
                "role_to_executor_kind",
                "executor_kind_to_role"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(domain, name))
