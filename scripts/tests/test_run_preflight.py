#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Contract tests for frozen VerificationPlan and dispatch capability preflight."""
from __future__ import annotations

from support import *  # noqa: F401,F403

import hashlib
import inspect
import json
import shutil
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
from unittest import mock

import waystone.runs.preflight as preflight_module
from waystone.jobs.domain import ExecutionCategory, ExecutorKind, Role, RoleBinding
from waystone.jobs.profile_v1 import ProfileV1RefusalCode
from waystone.runs.artifacts import ArtifactStore
from waystone.runs.preflight import (
    CapabilitySet,
    CheckPhase,
    CheckCapabilityProbe,
    CheckDefinition,
    ChildEnvironmentNormalization,
    ChildEnvironmentNotAllowedError,
    ChildEnvironmentRequiredMissingError,
    ChildEnvironmentSource,
    DependencyConstraint,
    EnvironmentInput,
    EnvironmentPreparationUnavailableError,
    EnvironmentPreparationReceipt,
    EnvironmentPreparationStep,
    MaterializedToolchain,
    NetworkCacheRequirements,
    NonAuthoritativeCheckResultError,
    ObservationStatus,
    PreflightEvidenceArtifactError,
    ProbeTarget,
    ProfilePreflightRefusal,
    RequiredCheckUnexecutableError,
    RedFirstEvidenceUnavailableError,
    RedFirstProbe,
    RoleCapability,
    RunnerCapabilities,
    RunnerContext,
    RunnerProofRevalidationRequired,
    RuntimeObservation,
    SandboxContract,
    ToolchainDigestMismatchError,
    ToolchainObservation,
    ToolchainRequirement,
    ToolchainUnavailableError,
    UnsupportedBindingError,
    UnsupportedExecutionCategoryError,
    UnsupportedSandboxError,
    VerificationPlanDefinition,
    VerificationPlanIncompleteError,
    VerificationPlanMissingError,
    VerificationPlanStateError,
    VerifierCapabilityUnavailableError,
    WorkerCheckReport,
    WorkingDirectoryRule,
    freeze_verification_plan,
    load_dispatch_ready,
    load_runner_proof,
    load_verification_plan,
    preflight_for_dispatch,
    record_runner_proof,
    reject_worker_check_result,
    require_reusable_runner_proof,
    runner_probe_unavailable,
)
from waystone.runs.spec import plan_one_task_run
from waystone.runs.store import FilesystemInfo, RecordNotFoundError, RunStore


def sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


class RunPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.base = Path(self._temporary_directory.name)
        self._project_number = 0
        self.check_sandbox = SandboxContract(
            "isolated-worktree-write", "process-exec", "network-denied")
        self.verifier_sandbox = SandboxContract(
            "read-only", "process-exec", "network-denied")

    @contextmanager
    def supported_filesystem(self):
        with mock.patch(
                "waystone.runs.store._probe_state_filesystem",
                return_value=FilesystemInfo(
                    filesystem="apfs", mount_point=Path("/"), writable=True)):
            yield

    def project(
            self, *, profile: str | None = None,
            toolchain_bytes: bytes = b"ruff-wheel-v1") -> tuple[Path, Path]:
        self._project_number += 1
        root = self.base / f"repo-{self._project_number}"
        root.mkdir()
        init_repo(root)
        (root / ".waystone.yml").write_text(
            "version: 1\nproject: fixture\n", encoding="utf-8")
        (root / "tasks.yaml").write_text(
            "version: 1\n"
            "project: fixture\n"
            "tasks:\n"
            "  - id: feat/example\n"
            "    title: verify one task\n"
            "    status: pending\n"
            "    accept:\n"
            "      - deterministic check is engine owned\n",
            encoding="utf-8",
        )
        (root / ".gitignore").write_text(
            ".waystone/\n.toolchains/\n", encoding="utf-8")
        (root / "tracked.txt").write_text("base\n", encoding="utf-8")
        git(root, "add", "-A")
        self.assertEqual(git(root, "commit", "-qm", "fixture").returncode, 0)

        state = root / ".waystone"
        state.mkdir()
        (state / "profile.yml").write_text(
            profile or (
                "schema: waystone-profile-1\n"
                "bindings:\n"
                "  implementer: {execution: external-runner, backend: 'codex:gpt-test'}\n"
                "  verifier: {backend: 'codex:gpt-verify', entry: adversarial-review}\n"
            ),
            encoding="utf-8",
        )
        toolchain = root / ".toolchains" / "ruff.whl"
        toolchain.parent.mkdir()
        toolchain.write_bytes(toolchain_bytes)
        return root, toolchain

    def run_spec(self, root: Path):
        with self.supported_filesystem():
            return plan_one_task_run("feat/example", start=root)

    def definition(self, toolchain_bytes: bytes = b"ruff-wheel-v1"):
        source = "lock:ruff@https://packages.example/ruff.whl"
        toolchain = ToolchainRequirement(
            toolchain_id="ruff-wheel",
            executable="ruff",
            runtime="python>=3.10",
            source_id=source,
            content_digest=sha256(toolchain_bytes),
            size=len(toolchain_bytes),
            dependencies=(DependencyConstraint("ruff", "==0.15.2"),),
        )
        check = CheckDefinition(
            check_id="lint",
            phase=CheckPhase.VERIFICATION,
            command=("uv", "run", "ruff", "check", "."),
            working_directory=WorkingDirectoryRule.INTEGRATION_ROOT,
            expected_exit_codes=(0,),
            expected_evidence_kinds=("stderr", "stdout"),
            environment=(EnvironmentInput(
                name="UV_OFFLINE",
                source=ChildEnvironmentSource.FROZEN_ACTION,
                normalization=ChildEnvironmentNormalization.BOOLEAN_01,
                value_digest=sha256(b"1"),
            ),),
            fixture_digests=(sha256(b"lint-fixture"),),
            required_toolchain_ids=("ruff-wheel",),
            sandbox=self.check_sandbox,
            worker_execution_required=True,
        )
        return VerificationPlanDefinition(
            required_checks=(check,),
            required_toolchains=(toolchain,),
            environment_preparation=(EnvironmentPreparationStep(
                sequence=0,
                step_id="materialize-ruff",
                command=("uv", "sync", "--offline"),
                input_toolchain_ids=("ruff-wheel",),
            ),),
            network_cache_requirements=NetworkCacheRequirements(
                network_required=False,
                allowed_sources=(source,),
                cache_namespace="uv-lock-fixture",
                offline_capable=True,
            ),
            verifier_sandbox=self.verifier_sandbox,
        )

    def red_definition(self, toolchain_bytes: bytes = b"ruff-wheel-v1"):
        definition = self.definition(toolchain_bytes)
        check = definition.required_checks[0]
        return replace(definition, required_checks=(replace(
            check,
            phase=CheckPhase.RED_FIRST,
            red_expected_exit_codes=(1,),
        ),))

    def freeze(self, root: Path, run_id: str, definition=None):
        with self.supported_filesystem():
            return freeze_verification_plan(
                run_id, definition or self.definition(), start=root)

    def load(self, root: Path, run_id: str):
        with self.supported_filesystem():
            return load_verification_plan(run_id, start=root)

    @staticmethod
    def observations(*overrides: RuntimeObservation) -> tuple[RuntimeObservation, ...]:
        observations = {
            "cache-boundary": RuntimeObservation(
                "cache-boundary", "engine:cache-boundary", ObservationStatus.OBSERVED,
                sha256(b"cache-boundary-v1")),
            "platform-kernel": RuntimeObservation(
                "platform-kernel", "engine:platform-kernel", ObservationStatus.OBSERVED,
                sha256(b"platform-kernel-v1")),
            "process-security": RuntimeObservation(
                "process-security", "engine:process-security",
                ObservationStatus.NOT_OBSERVED),
            "runner-binary": RuntimeObservation(
                "runner-binary", "runner-adapter:binary", ObservationStatus.OBSERVED,
                sha256(b"runner-binary-v1")),
            "runner-config-content": RuntimeObservation(
                "runner-config-content", "runner-adapter:config",
                ObservationStatus.NOT_OBSERVED),
            "runner-version": RuntimeObservation(
                "runner-version", "runner-adapter:version", ObservationStatus.OBSERVED,
                sha256(b"runner-version-v1")),
            "sandbox-contract": RuntimeObservation(
                "sandbox-contract", "engine:sandbox-contract",
                ObservationStatus.OBSERVED, sha256(b"sandbox-contract-v1")),
        }
        observations.update((item.axis, item) for item in overrides)
        return tuple(observations.values())

    @staticmethod
    def context(
            root: Path, *, checkout: str = "checkout-1", machine: str = "machine-1",
            principal: str = "principal-1", observations=None) -> RunnerContext:
        return RunnerContext(
            checkout_identity=sha256(checkout.encode("utf-8")),
            machine_identity=sha256(machine.encode("utf-8")),
            principal_identity=sha256(principal.encode("utf-8")),
            project_config_digest=sha256((root / ".waystone.yml").read_bytes()),
            profile_config_digest=sha256(
                (root / ".waystone" / "profile.yml").read_bytes()),
            runtime_observations=(RunPreflightTests.observations()
                                  if observations is None else observations),
        )

    def capabilities(
            self, plan, *, categories=None, worker_binding=None,
            worker_sandbox=None, engine_sandbox=None, verifier_binding=None,
            verifier_sandbox=None, verifier_result=True, verifier_artifact=True,
            verifier_base=True, verifier_patch=True, probe_ready=True,
            probe_structured=True, probe_exit=0, red_probe_exit=None) -> CapabilitySet:
        worker = worker_binding or plan.binding_for(Role.WORKER).binding
        verifier = verifier_binding or plan.binding_for(Role.VERIFIER).binding
        runner = RunnerCapabilities(
            execution_categories=categories or (ExecutionCategory.EXTERNAL,),
            engine_sandboxes=(engine_sandbox or self.check_sandbox,),
            role_capabilities=(
                RoleCapability(
                    binding=worker,
                    sandbox=worker_sandbox or self.check_sandbox,
                    accepts_frozen_base=False,
                    accepts_patch_bytes=False,
                    accepts_result_digest=False,
                    emits_artifacts=False,
                ),
                RoleCapability(
                    binding=verifier,
                    sandbox=verifier_sandbox or self.verifier_sandbox,
                    accepts_frozen_base=verifier_base,
                    accepts_patch_bytes=verifier_patch,
                    accepts_result_digest=verifier_result,
                    emits_artifacts=verifier_artifact,
                ),
            ),
        )
        toolchain_observations = tuple(ToolchainObservation(
            toolchain_id=item.toolchain_id,
            source_id=item.source_id,
            content_digest=item.content_digest,
            size=item.size,
        ) for item in plan.required_toolchains)
        preparation_receipt = EnvironmentPreparationReceipt(
            environment_preparation_digest=plan.environment_preparation_digest,
            network_cache_requirements=plan.network_cache_requirements,
            toolchain_observations=toolchain_observations,
        )
        probes = tuple(CheckCapabilityProbe(
            check_id=check.check_id,
            target=target,
            command=check.command,
            command_input_digest=check.command_input_digest,
            environment_preparation_artifact_digest=(
                preparation_receipt.artifact_digest),
            child_environment=check.environment,
            entrypoint_ready=probe_ready,
            structured_result=probe_structured,
            exit_code=probe_exit,
        ) for check in plan.required_checks for target in ProbeTarget)
        red_probes = tuple(RedFirstProbe(
            check_id=check.check_id,
            base_snapshot_digest=plan.base_snapshot_digest,
            command=check.command,
            command_input_digest=check.command_input_digest,
            environment_preparation_artifact_digest=(
                preparation_receipt.artifact_digest),
            child_environment=check.environment,
            structured_result=probe_structured,
            exit_code=(check.red_expected_exit_codes[0]
                       if red_probe_exit is None else red_probe_exit),
        ) for check in plan.required_checks if check.phase is CheckPhase.RED_FIRST)
        return CapabilitySet(
            runner=runner,
            environment_preparation_receipts=(preparation_receipt,),
            check_probes=probes,
            red_first_probes=red_probes,
        )

    def ready_inputs(self, root: Path, plan, toolchain: Path, **capability_kwargs):
        capabilities = self.capabilities(plan, **capability_kwargs)
        context = self.context(root)
        proof = record_runner_proof(context, capabilities.runner)
        materialized = (MaterializedToolchain(
            "ruff-wheel",
            "lock:ruff@https://packages.example/ruff.whl",
            toolchain,
        ),)
        return capabilities, context, proof, materialized

    def preflight(self, root: Path, plan, toolchain: Path, **capability_kwargs):
        capabilities, context, proof, materialized = self.ready_inputs(
            root, plan, toolchain, **capability_kwargs)
        with self.supported_filesystem():
            return preflight_for_dispatch(
                plan.run_id,
                capabilities=capabilities,
                materialized_toolchains=materialized,
                current_runner_context=context,
                reusable_runner_proof=proof,
                start=root,
            )

    def open_store(self, root: Path) -> RunStore:
        with self.supported_filesystem():
            store = RunStore.open(root)
        self.addCleanup(store.close)
        return store

    def test_freeze_plan_persists_canonical_artifact_reference_and_profile_bindings(self):
        root, _toolchain = self.project()
        spec = self.run_spec(root)

        plan = self.freeze(root, spec.run_id)
        loaded = self.load(root, spec.run_id)

        self.assertEqual(loaded, plan)
        self.assertEqual(plan.run_id, spec.run_id)
        self.assertEqual(plan.job_id, spec.job_id)
        self.assertEqual(plan.run_spec_digest, spec.run_spec_digest)
        self.assertEqual(plan.base_snapshot_digest, spec.base_snapshot.digest)
        self.assertEqual(
            [item.binding.role for item in plan.role_bindings],
            [Role.WORKER, Role.VERIFIER],
        )
        self.assertEqual(
            plan.binding_for(Role.WORKER).binding,
            RoleBinding(Role.WORKER, ExecutionCategory.EXTERNAL, "codex:gpt-test"),
        )
        self.assertEqual(plan.binding_for(Role.WORKER).legacy_role, "implementer")
        self.assertEqual(
            plan.binding_for(Role.VERIFIER).binding.backend, "codex:gpt-verify")
        self.assertEqual(plan.required_checks[0].authoritative_executor, ExecutorKind.ENGINE)
        self.assertRegex(
            plan.required_checks[0].command_input_digest, r"^sha256:[0-9a-f]{64}$")
        self.assertNotIn(str(root), plan.canonical_bytes().decode("utf-8"))

        store = self.open_store(root)
        reference = store.get_artifact_reference(f"verification-plan:{spec.run_id}")
        artifact = ArtifactStore(root).read_reference(reference)
        self.assertEqual(artifact, plan.canonical_bytes())
        self.assertEqual(reference.digest, plan.verification_plan_digest)
        self.assertEqual(
            artifact,
            json.dumps(
                json.loads(artifact), ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        self.assertEqual(store.get_run(spec.run_id).state, "verification-plan-frozen")

    def test_command_input_digest_binds_command_environment_base_fixture_and_toolchain(self):
        root, _toolchain = self.project()
        spec = self.run_spec(root)
        definition = self.definition()
        frozen = self.freeze(root, spec.run_id, definition)
        profile_bytes = (root / ".waystone" / "profile.yml").read_bytes()

        def digest_for(candidate):
            plan = preflight_module._new_plan(  # noqa: SLF001 - deterministic contract fixture
                spec, candidate, profile_bytes, frozen.role_bindings)
            return plan.required_checks[0].command_input_digest

        base_digest = digest_for(definition)
        check = definition.required_checks[0]
        toolchain = definition.required_toolchains[0]
        changed_source = replace(toolchain, source_id="lock:ruff@https://mirror.example/ruff.whl")
        variants = (
            replace(definition, required_checks=(replace(
                check, command=("uv", "run", "ruff", "format", "--check", ".")),)),
            replace(definition, required_checks=(replace(
                check, environment=(EnvironmentInput(
                    name="UV_OFFLINE",
                    source=ChildEnvironmentSource.FROZEN_ACTION,
                    normalization=ChildEnvironmentNormalization.BOOLEAN_01,
                    value_digest=sha256(b"0"),
                ),)),)),
            replace(definition, required_checks=(replace(
                check, fixture_digests=(sha256(b"changed-fixture"),)),)),
            replace(definition, required_toolchains=(replace(
                toolchain, content_digest=sha256(b"other-ruff-wheel-v1"),
                size=len(b"other-ruff-wheel-v1")),)),
            replace(
                definition,
                required_toolchains=(changed_source,),
                network_cache_requirements=replace(
                    definition.network_cache_requirements,
                    allowed_sources=(changed_source.source_id,)),
            ),
            replace(
                definition,
                network_cache_requirements=replace(
                    definition.network_cache_requirements,
                    cache_namespace="different-frozen-cache",
                ),
            ),
        )

        for candidate in variants:
            with self.subTest(candidate=candidate):
                self.assertNotEqual(digest_for(candidate), base_digest)
        changed_base_spec = replace(
            spec,
            base_snapshot=replace(
                spec.base_snapshot, digest=sha256(b"different-base-snapshot")),
        )
        changed_base_plan = preflight_module._new_plan(  # noqa: SLF001
            changed_base_spec, definition, profile_bytes, frozen.role_bindings)
        self.assertNotEqual(
            changed_base_plan.required_checks[0].command_input_digest, base_digest)

    def test_incomplete_or_missing_plan_cannot_satisfy_dispatch_precondition(self):
        root, _toolchain = self.project()
        spec = self.run_spec(root)

        with self.assertRaises(VerificationPlanMissingError) as raised:
            self.load(root, spec.run_id)
        self.assertEqual(raised.exception.code, "verification_plan_missing")
        with self.assertRaises(VerificationPlanIncompleteError):
            VerificationPlanDefinition(
                required_checks=(),
                required_toolchains=self.definition().required_toolchains,
                environment_preparation=self.definition().environment_preparation,
                network_cache_requirements=self.definition().network_cache_requirements,
                verifier_sandbox=self.verifier_sandbox,
            )
        store = self.open_store(root)
        self.assertEqual(store.get_run(spec.run_id).state, "frozen-ready")
        with self.assertRaises(RecordNotFoundError):
            store.get_artifact_reference(f"verification-preflight:{spec.run_id}")

    def test_frozen_plan_cannot_be_mutated_rebuilt_from_live_profile_or_overwritten(self):
        root, _toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        artifact_before = plan.canonical_bytes()

        with self.assertRaises(FrozenInstanceError):
            plan.task_id = "worker-override"  # type: ignore[misc]
        profile = root / ".waystone" / "profile.yml"
        profile.write_text(
            profile.read_text().replace("codex:gpt-test", "codex:changed"),
            encoding="utf-8",
        )
        self.assertEqual(self.load(root, spec.run_id).canonical_bytes(), artifact_before)
        with self.assertRaises(VerificationPlanStateError) as raised:
            self.freeze(root, spec.run_id)
        self.assertEqual(raised.exception.state, "verification-plan-frozen")
        self.assertEqual(self.load(root, spec.run_id).canonical_bytes(), artifact_before)

    def test_profile_v1_refusal_is_wrapped_without_losing_original_fields(self):
        root, _toolchain = self.project(profile=(
            "schema: waystone-profile-1\n"
            "bindings:\n"
            "  implementer: {execution: deterministic-workflow, backend: 'claude:opus'}\n"
            "  verifier: {backend: 'codex:gpt-verify'}\n"
        ))
        spec = self.run_spec(root)

        with self.assertRaises(ProfilePreflightRefusal) as raised:
            self.freeze(root, spec.run_id)

        refusal = raised.exception.refusal
        self.assertEqual(raised.exception.code, "verification_profile_refused")
        self.assertEqual(refusal.code, ProfileV1RefusalCode.UNSUPPORTED_BINDING)
        self.assertEqual(raised.exception.profile_code, refusal.code)
        self.assertEqual(raised.exception.profile_reason, refusal.reason)
        self.assertEqual(raised.exception.legacy_role, refusal.legacy_role)
        self.assertEqual(raised.exception.legacy_execution, refusal.legacy_execution)
        store = self.open_store(root)
        self.assertEqual(store.get_run(spec.run_id).state, "frozen-ready")

        root, _toolchain = self.project(profile=(
            "schema: waystone-profile-1\n"
            "bindings:\n"
            "  implementer: {execution: external-runner, backend: 'codex:gpt-test'}\n"
            "  verifier: {backend: 'codex:gpt-verify', entry: cooperative-review}\n"
        ))
        spec = self.run_spec(root)
        with self.assertRaises(ProfilePreflightRefusal) as verifier_refusal:
            self.freeze(root, spec.run_id)
        self.assertEqual(verifier_refusal.exception.code, "verification_profile_refused")
        self.assertEqual(verifier_refusal.exception.legacy_role, "verifier")
        self.assertEqual(self.open_store(root).get_run(spec.run_id).state, "frozen-ready")

    def test_missing_worker_or_verifier_binding_is_incomplete_without_reference(self):
        for role, profile in (
                ("worker", (
                    "schema: waystone-profile-1\n"
                    "bindings:\n"
                    "  verifier: {backend: 'codex:gpt-verify'}\n"
                )),
                ("verifier", (
                    "schema: waystone-profile-1\n"
                    "bindings:\n"
                    "  implementer: {execution: external-runner, backend: 'codex:gpt-test'}\n"
                ))):
            with self.subTest(missing=role):
                root, _toolchain = self.project(profile=profile)
                spec = self.run_spec(root)
                with self.assertRaises(VerificationPlanIncompleteError):
                    self.freeze(root, spec.run_id)
                store = self.open_store(root)
                self.assertEqual(store.get_run(spec.run_id).state, "frozen-ready")
                with self.assertRaises(RecordNotFoundError):
                    store.get_artifact_reference(f"verification-plan:{spec.run_id}")

    def test_profile_role_binding_is_parsed_from_the_exact_digested_snapshot(self):
        root, _toolchain = self.project()
        spec = self.run_spec(root)

        with mock.patch.object(
                preflight_module,
                "read_profile_v1",
                side_effect=AssertionError("path-based second read must not occur"),
        ) as path_reader:
            plan = self.freeze(root, spec.run_id)

        path_reader.assert_not_called()
        profile_bytes = (root / ".waystone" / "profile.yml").read_bytes()
        self.assertEqual(plan.profile_content_digest, sha256(profile_bytes))
        self.assertEqual(plan.binding_for(Role.WORKER).binding.backend, "codex:gpt-test")

    def test_absolute_worktree_path_is_rejected_anywhere_in_plan_authority(self):
        root, _toolchain = self.project()
        spec = self.run_spec(root)
        definition = self.definition()
        candidates = (
            replace(
                definition,
                network_cache_requirements=replace(
                    definition.network_cache_requirements,
                    cache_namespace=str(root),
                ),
            ),
            replace(definition, required_checks=(replace(
                definition.required_checks[0],
                command=("uv", "run", "ruff", f"--root={root}"),
            ),)),
        )

        for candidate in candidates:
            with self.subTest(candidate=candidate), self.assertRaises(
                    VerificationPlanIncompleteError):
                self.freeze(root, spec.run_id, candidate)
        store = self.open_store(root)
        self.assertEqual(store.get_run(spec.run_id).state, "frozen-ready")
        with self.assertRaises(RecordNotFoundError):
            store.get_artifact_reference(f"verification-plan:{spec.run_id}")

    def test_duplicate_environment_receipts_fail_validation_without_sort_type_error(self):
        root, _toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        capabilities = self.capabilities(plan)
        receipt = capabilities.environment_preparation_receipts[0]
        duplicate = replace(
            receipt,
            network_cache_requirements=replace(
                receipt.network_cache_requirements,
                cache_namespace="different-cache",
            ),
        )

        with self.assertRaisesRegex(ValueError, "receipt digests must be unique"):
            replace(
                capabilities,
                environment_preparation_receipts=(receipt, duplicate),
            )

        requirement = plan.required_toolchains[0]
        with self.assertRaisesRegex(ValueError, "size must be a non-negative integer"):
            ToolchainObservation(
                requirement.toolchain_id,
                requirement.source_id,
                requirement.content_digest,
                True,
            )
        self.assertEqual(self.open_store(root).get_run(plan.run_id).state,
                         "verification-plan-frozen")

    def test_unsupported_execution_binding_and_sandbox_each_refuse_before_dispatch(self):
        root, toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)

        cases = (
            (UnsupportedExecutionCategoryError, {
                "categories": (ExecutionCategory.SUBAGENT,),
            }),
            (UnsupportedBindingError, {
                "worker_binding": RoleBinding(
                    Role.WORKER, ExecutionCategory.EXTERNAL, "codex:other"),
            }),
            (UnsupportedBindingError, {
                "verifier_binding": RoleBinding(
                    Role.VERIFIER, ExecutionCategory.EXTERNAL, "codex:other"),
            }),
            (UnsupportedSandboxError, {
                "engine_sandbox": SandboxContract(
                    "read-only", "process-exec", "network-denied"),
            }),
            (UnsupportedSandboxError, {
                "worker_sandbox": SandboxContract(
                    "read-only", "process-exec", "network-denied"),
            }),
            (UnsupportedSandboxError, {
                "verifier_sandbox": SandboxContract(
                    "isolated-worktree-write", "process-exec", "network-denied"),
            }),
        )
        for error, kwargs in cases:
            with self.subTest(error=error.__name__):
                capabilities, context, proof, materialized = self.ready_inputs(
                    root, plan, toolchain, **kwargs)
                with self.supported_filesystem(), self.assertRaises(error):
                    preflight_for_dispatch(
                        plan.run_id,
                        capabilities=capabilities,
                        materialized_toolchains=materialized,
                        current_runner_context=context,
                        reusable_runner_proof=proof,
                        start=root,
                    )
                store = self.open_store(root)
                self.assertEqual(store.get_run(plan.run_id).state, "verification-plan-frozen")
                with self.assertRaises(RecordNotFoundError):
                    store.get_artifact_reference(f"verification-preflight:{plan.run_id}")

    def test_verifier_requires_frozen_base_patch_result_and_artifact_capabilities(self):
        root, toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        cases = (
            {"verifier_base": False},
            {"verifier_patch": False},
            {"verifier_result": False},
            {"verifier_artifact": False},
        )

        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                capabilities, context, proof, materialized = self.ready_inputs(
                    root, plan, toolchain, **kwargs)
                with self.supported_filesystem(), self.assertRaises(
                        VerifierCapabilityUnavailableError):
                    preflight_for_dispatch(
                        plan.run_id,
                        capabilities=capabilities,
                        materialized_toolchains=materialized,
                        current_runner_context=context,
                        reusable_runner_proof=proof,
                        start=root,
                    )
        self.assertEqual(self.open_store(root).get_run(plan.run_id).state,
                         "verification-plan-frozen")

    def test_unexecutable_probe_refuses_but_structured_nonzero_result_is_capable(self):
        root, toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        capabilities, context, proof, materialized = self.ready_inputs(
            root, plan, toolchain, probe_ready=False)

        with self.supported_filesystem(), self.assertRaises(
                RequiredCheckUnexecutableError) as raised:
            preflight_for_dispatch(
                plan.run_id,
                capabilities=capabilities,
                materialized_toolchains=materialized,
                current_runner_context=context,
                reusable_runner_proof=proof,
                start=root,
            )
        self.assertEqual(raised.exception.code, "required_check_unexecutable")

        capable = self.capabilities(plan, probe_exit=1)
        proof = record_runner_proof(context, capable.runner)
        with self.supported_filesystem():
            ready = preflight_for_dispatch(
                plan.run_id,
                capabilities=capable,
                materialized_toolchains=materialized,
                current_runner_context=context,
                reusable_runner_proof=proof,
                start=root,
            )
        self.assertEqual(ready.engine_actions[0].executor_kind, ExecutorKind.ENGINE)

    def test_network_cache_receipt_must_exactly_match_frozen_environment(self):
        root, toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        capabilities, context, _proof, materialized = self.ready_inputs(
            root, plan, toolchain)
        receipt = capabilities.environment_preparation_receipts[0]
        mismatched = replace(
            receipt,
            network_cache_requirements=replace(
                receipt.network_cache_requirements,
                cache_namespace="ambient-index-cache",
            ),
        )
        capabilities = replace(
            capabilities, environment_preparation_receipts=(mismatched,))
        proof = record_runner_proof(context, capabilities.runner)

        with self.supported_filesystem(), self.assertRaises(
                EnvironmentPreparationUnavailableError):
            preflight_for_dispatch(
                plan.run_id,
                capabilities=capabilities,
                materialized_toolchains=materialized,
                current_runner_context=context,
                reusable_runner_proof=proof,
                start=root,
            )

    def test_probes_and_actions_bind_selected_preparation_and_closed_child_environment(self):
        root, toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        capabilities, context, _proof, materialized = self.ready_inputs(
            root, plan, toolchain)

        extra_probe = replace(
            capabilities.check_probes[0], check_id="ambient-extra")
        extra_probe_set = replace(
            capabilities,
            check_probes=(*capabilities.check_probes, extra_probe),
        )
        with self.supported_filesystem(), self.assertRaises(
                RequiredCheckUnexecutableError):
            preflight_for_dispatch(
                plan.run_id,
                capabilities=extra_probe_set,
                materialized_toolchains=materialized,
                current_runner_context=context,
                reusable_runner_proof=record_runner_proof(
                    context, extra_probe_set.runner),
                start=root,
            )
        self.assertEqual(self.open_store(root).get_run(plan.run_id).state,
                         "verification-plan-frozen")

        stale_probes = tuple(replace(
            probe,
            environment_preparation_artifact_digest=sha256(b"stale-preparation"),
        ) for probe in capabilities.check_probes)
        stale = replace(capabilities, check_probes=stale_probes)
        with self.supported_filesystem(), self.assertRaises(
                RequiredCheckUnexecutableError):
            preflight_for_dispatch(
                plan.run_id,
                capabilities=stale,
                materialized_toolchains=materialized,
                current_runner_context=context,
                reusable_runner_proof=record_runner_proof(context, stale.runner),
                start=root,
            )

        missing = replace(capabilities, check_probes=tuple(replace(
            probe, child_environment=()) for probe in capabilities.check_probes))
        with self.supported_filesystem(), self.assertRaises(
                ChildEnvironmentRequiredMissingError) as raised:
            preflight_for_dispatch(
                plan.run_id,
                capabilities=missing,
                materialized_toolchains=materialized,
                current_runner_context=context,
                reusable_runner_proof=record_runner_proof(context, missing.runner),
                start=root,
            )
        self.assertEqual(raised.exception.code, "child_env_required_missing")

        extra_input = EnvironmentInput(
            name="LANG",
            source=ChildEnvironmentSource.ENGINE_RUNTIME,
            normalization=ChildEnvironmentNormalization.UTF8_EXACT,
            value_digest=sha256(b"C.UTF-8"),
        )
        extra = replace(capabilities, check_probes=tuple(replace(
            probe,
            child_environment=(*probe.child_environment, extra_input),
        ) for probe in capabilities.check_probes))
        with self.supported_filesystem(), self.assertRaises(
                ChildEnvironmentNotAllowedError) as raised:
            preflight_for_dispatch(
                plan.run_id,
                capabilities=extra,
                materialized_toolchains=materialized,
                current_runner_context=context,
                reusable_runner_proof=record_runner_proof(context, extra.runner),
                start=root,
            )
        self.assertEqual(raised.exception.code, "child_env_not_allowed")

        with self.assertRaises(ChildEnvironmentNotAllowedError):
            EnvironmentInput(
                name="WAYSTONE_OWNER_TOKEN",
                source=ChildEnvironmentSource.ENGINE_RUNTIME,
                normalization=ChildEnvironmentNormalization.UTF8_EXACT,
                value_digest=sha256(b"ambient-token"),
            )
        with self.assertRaises(ChildEnvironmentNotAllowedError):
            EnvironmentInput(
                name="AWS_SECRET_ACCESS_KEY",
                source=ChildEnvironmentSource.FROZEN_ACTION,
                normalization=ChildEnvironmentNormalization.UTF8_EXACT,
                value_digest=sha256(b"ambient-secret"),
            )

        ready = self.preflight(root, plan, toolchain)
        receipt = capabilities.environment_preparation_receipts[0]
        for action in ready.engine_actions:
            self.assertEqual(
                action.environment_preparation_artifact_digest,
                receipt.artifact_digest,
            )
            matching_probe = next(
                probe for probe in capabilities.check_probes
                if probe.check_id == action.check_id)
            self.assertEqual(action.prepared_input_digest,
                             matching_probe.prepared_input_digest)

    def test_red_first_expected_failure_is_base_bound_and_persisted(self):
        root, toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id, self.red_definition())
        capabilities = self.capabilities(plan)

        ready = self.preflight(root, plan, toolchain)

        self.assertEqual(ready.engine_actions[0].phase, CheckPhase.RED_FIRST)
        self.assertEqual(ready.engine_actions[0].red_expected_exit_codes, (1,))
        probe = capabilities.red_first_probes[0]
        store = self.open_store(root)
        reference = store.get_artifact_reference(
            f"preflight-receipt:{plan.run_id}:"
            f"{probe.artifact_digest.removeprefix('sha256:')}")
        self.assertEqual(ArtifactStore(root).read_reference(reference),
                         probe.canonical_receipt_bytes())

    def test_red_first_snapshot_or_exit_mismatch_refuses_before_dispatch(self):
        root, toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id, self.red_definition())
        capabilities, context, _proof, materialized = self.ready_inputs(
            root, plan, toolchain)
        probe = capabilities.red_first_probes[0]
        variants = (
            replace(probe, base_snapshot_digest=sha256(b"other-base")),
            replace(probe, exit_code=0),
        )

        for variant in variants:
            with self.subTest(variant=variant):
                candidate = replace(capabilities, red_first_probes=(variant,))
                with self.supported_filesystem(), self.assertRaises(
                        RedFirstEvidenceUnavailableError):
                    preflight_for_dispatch(
                        plan.run_id,
                        capabilities=candidate,
                        materialized_toolchains=materialized,
                        current_runner_context=context,
                        reusable_runner_proof=record_runner_proof(
                            context, candidate.runner),
                        start=root,
                    )
        self.assertEqual(self.open_store(root).get_run(plan.run_id).state,
                         "verification-plan-frozen")

    def test_successful_preflight_is_capability_only_and_worker_result_is_not_authority(self):
        root, toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)

        ready = self.preflight(root, plan, toolchain)

        self.assertEqual(ready.verification_plan_digest, plan.verification_plan_digest)
        self.assertRegex(ready.preflight_evidence_digest, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(len(ready.engine_actions), 1)
        action = ready.engine_actions[0]
        self.assertEqual(action.executor_kind, ExecutorKind.ENGINE)
        store = self.open_store(root)
        self.assertEqual(store.get_run(plan.run_id).state, "dispatch-ready")
        reference = store.get_artifact_reference(
            f"verification-preflight:{plan.run_id}")
        payload = json.loads(ArtifactStore(root).read_reference(reference))
        self.assertEqual(payload["authority_scope"], "dispatch-capability-only")
        self.assertEqual(payload["verification_plan_digest"], plan.verification_plan_digest)
        self.assertEqual(
            {item["target"] for item in payload["capability_probes"]},
            {target.value for target in ProbeTarget},
        )
        self.assertEqual(load_dispatch_ready(plan.run_id, start=root), ready)
        for digest in payload["receipt_artifact_digests"]:
            receipt_reference = store.get_artifact_reference(
                f"preflight-receipt:{plan.run_id}:"
                f"{digest.removeprefix('sha256:')}")
            receipt_bytes = ArtifactStore(root).read_reference(receipt_reference)
            self.assertEqual(sha256(receipt_bytes), digest)

        worker_report = WorkerCheckReport(
            check_id=action.check_id,
            command_input_digest=action.command_input_digest,
            exit_code=0,
            evidence_digests=(("stdout", sha256(b"ok")),
                              ("stderr", sha256(b""))),
        )
        with self.assertRaises(NonAuthoritativeCheckResultError) as raised:
            reject_worker_check_result(action, worker_report)
        self.assertEqual(raised.exception.code, "worker_check_not_authoritative")

    def test_post_commit_reload_recovers_dispatch_after_return_path_crash(self):
        root, toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        capabilities, context, proof, materialized = self.ready_inputs(
            root, plan, toolchain)

        with mock.patch.object(
                preflight_module,
                "load_dispatch_ready",
                side_effect=RuntimeError("crash after commit"),
        ), self.supported_filesystem(), self.assertRaisesRegex(
                RuntimeError, "crash after commit"):
            preflight_for_dispatch(
                plan.run_id,
                capabilities=capabilities,
                materialized_toolchains=materialized,
                current_runner_context=context,
                reusable_runner_proof=proof,
                start=root,
            )

        self.assertEqual(self.open_store(root).get_run(plan.run_id).state,
                         "dispatch-ready")
        recovered = load_dispatch_ready(plan.run_id, start=root)
        self.assertEqual(recovered.run_id, plan.run_id)
        self.assertEqual(recovered.engine_actions[0].check_id, "lint")
        self.assertEqual(load_runner_proof(plan.run_id, start=root), proof)

    def test_dispatch_reload_refuses_dangling_receipt(self):
        root, toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        ready = self.preflight(root, plan, toolchain)
        store = self.open_store(root)
        evidence_reference = store.get_artifact_reference(
            f"verification-preflight:{plan.run_id}")
        evidence = json.loads(ArtifactStore(root).read_reference(evidence_reference))
        digest = evidence["receipt_artifact_digests"][0]
        ArtifactStore(root).path_for(digest).unlink()

        with self.assertRaises(PreflightEvidenceArtifactError) as raised:
            load_dispatch_ready(plan.run_id, start=root)
        self.assertEqual(raised.exception.code, "preflight_evidence_artifact_invalid")
        self.assertEqual(ready.run_id, plan.run_id)

    def test_state_equivalent_not_observed_runner_proof_is_reusable(self):
        root, _toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        capabilities = self.capabilities(plan).runner
        recorded = self.context(root, observations=self.observations())
        current = self.context(root, observations=self.observations())
        proof = record_runner_proof(recorded, capabilities)

        self.assertIs(
            require_reusable_runner_proof(proof, current, capabilities), proof)

    def test_runner_proof_observer_is_engine_owned_and_unavailable_probe_is_typed(self):
        root, _toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        capabilities = self.capabilities(plan).runner
        context = self.context(root)

        with self.assertRaises(NonAuthoritativeCheckResultError):
            record_runner_proof(
                context, capabilities, observed_by=ExecutorKind.CARRIER)
        with self.assertRaisesRegex(
                preflight_module.RunnerProbeUnavailableError,
                "security label cannot be observed",
        ) as raised:
            runner_probe_unavailable("security label cannot be observed")
        self.assertEqual(raised.exception.code, "runner_probe_unavailable")

        with self.assertRaisesRegex(ValueError, "not in the bounded schema"):
            RuntimeObservation(
                "hostname", "socket.gethostname", ObservationStatus.OBSERVED,
                sha256(b"Mac.local"),
            )
        with self.assertRaises(preflight_module.RunnerProbeUnavailableError):
            self.context(root, observations=())

    def test_observed_unobserved_runner_axis_transitions_require_reprobe(self):
        root, _toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        capabilities = self.capabilities(plan).runner
        observed = RuntimeObservation(
            "process-security", "engine:process-security", ObservationStatus.OBSERVED,
            sha256(b"2"))
        unobserved = RuntimeObservation(
            "process-security", "engine:process-security",
            ObservationStatus.NOT_OBSERVED)

        for before, after in ((observed, unobserved), (unobserved, observed)):
            with self.subTest(before=before.status.value, after=after.status.value):
                proof = record_runner_proof(
                    self.context(root, observations=self.observations(before)),
                    capabilities)
                with self.assertRaises(RunnerProofRevalidationRequired) as raised:
                    require_reusable_runner_proof(
                        proof,
                        self.context(root, observations=self.observations(after)),
                        capabilities,
                    )
                self.assertIn("runtime-observations", raised.exception.mismatched_axes)

    def test_config_content_change_with_unchanged_directory_stat_requires_reprobe(self):
        root, _toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        capabilities = self.capabilities(plan).runner
        before = self.context(root)
        proof = record_runner_proof(before, capabilities)
        config = root / ".waystone.yml"
        original = config.read_bytes()
        directory_stat = root.stat()
        replacement = original.replace(b"fixture", b"changed")
        self.assertEqual(len(replacement), len(original))
        config.write_bytes(replacement)
        os.utime(root, ns=(directory_stat.st_atime_ns, directory_stat.st_mtime_ns))
        after_stat = root.stat()
        self.assertEqual(after_stat.st_ino, directory_stat.st_ino)
        self.assertEqual(after_stat.st_mtime_ns, directory_stat.st_mtime_ns)
        current = self.context(root)

        with self.assertRaises(RunnerProofRevalidationRequired) as raised:
            require_reusable_runner_proof(proof, current, capabilities)
        self.assertIn("project-config-content", raised.exception.mismatched_axes)

    def _assert_identity_axis_reprobes(self, axis: str):
        root, _toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        capabilities = self.capabilities(plan).runner
        proof = record_runner_proof(self.context(root), capabilities)
        kwargs = {"checkout": "checkout-1", "machine": "machine-1", "principal": "principal-1"}
        kwargs[axis] = f"{axis}-2"

        with self.assertRaises(RunnerProofRevalidationRequired) as raised:
            require_reusable_runner_proof(
                proof, self.context(root, **kwargs), capabilities)
        self.assertIn(axis, raised.exception.mismatched_axes)

    def test_checkout_identity_mismatch_requires_fresh_probe(self):
        self._assert_identity_axis_reprobes("checkout")

    def test_machine_identity_mismatch_requires_fresh_probe(self):
        self._assert_identity_axis_reprobes("machine")

    def test_principal_identity_mismatch_requires_fresh_probe(self):
        self._assert_identity_axis_reprobes("principal")

    def test_plan_and_runner_proof_digests_are_relocation_and_ambient_order_stable(self):
        root, _toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        capabilities = self.capabilities(plan).runner
        context = self.context(root)
        proof = record_runner_proof(context, capabilities)
        reversed_capabilities = RunnerCapabilities(
            execution_categories=tuple(reversed(capabilities.execution_categories)),
            engine_sandboxes=tuple(reversed(capabilities.engine_sandboxes)),
            role_capabilities=tuple(reversed(capabilities.role_capabilities)),
        )
        reversed_context = replace(
            context,
            runtime_observations=tuple(reversed(context.runtime_observations)),
        )
        self.assertEqual(
            record_runner_proof(reversed_context, reversed_capabilities).proof_digest,
            proof.proof_digest,
        )

        relocated = self.base / "relocated-project"
        shutil.move(root, relocated)
        os.utime(relocated, None)
        loaded = self.load(relocated, plan.run_id)
        relocated_context = self.context(relocated)

        self.assertEqual(loaded.verification_plan_digest, plan.verification_plan_digest)
        self.assertEqual(loaded.canonical_bytes(), plan.canonical_bytes())
        self.assertEqual(
            record_runner_proof(relocated_context, reversed_capabilities).proof_digest,
            proof.proof_digest,
        )
        authority_bytes = plan.canonical_bytes() + proof.canonical_bytes()
        self.assertNotIn(str(root).encode(), authority_bytes)
        self.assertNotIn(str(relocated).encode(), authority_bytes)
        self.assertNotIn(b"hostname", authority_bytes)
        self.assertNotIn(b"mtime", authority_bytes)
        self.assertNotIn(b"inode", authority_bytes)

    def test_ws_gpt_102_forged_toolchain_bytes_refuse_before_offline_gate(self):
        original = b"ruff-version=0.15.2;payload=original"
        forged = b"ruff-version=0.15.2;payload=forged!!"
        self.assertEqual(len(original), len(forged))
        root, toolchain = self.project(toolchain_bytes=original)
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id, self.definition(original))
        before = toolchain.stat()
        toolchain.write_bytes(forged)
        os.utime(toolchain, ns=(before.st_atime_ns, before.st_mtime_ns))
        after = toolchain.stat()
        self.assertEqual(after.st_ino, before.st_ino)
        self.assertEqual(after.st_size, before.st_size)
        self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)
        capabilities, context, proof, materialized = self.ready_inputs(
            root, plan, toolchain)

        with self.supported_filesystem(), self.assertRaises(
                ToolchainDigestMismatchError) as raised:
            preflight_for_dispatch(
                plan.run_id,
                capabilities=capabilities,
                materialized_toolchains=materialized,
                current_runner_context=context,
                reusable_runner_proof=proof,
                start=root,
            )

        self.assertEqual(raised.exception.code, "toolchain_digest_mismatch")
        store = self.open_store(root)
        self.assertEqual(store.get_run(plan.run_id).state, "verification-plan-frozen")
        with self.assertRaises(RecordNotFoundError):
            store.get_artifact_reference(f"verification-preflight:{plan.run_id}")

    def test_toolchain_source_substitution_refuses_even_when_bytes_match(self):
        root, toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)
        capabilities = self.capabilities(plan)
        context = self.context(root)
        proof = record_runner_proof(context, capabilities.runner)

        with self.supported_filesystem(), self.assertRaises(
                ToolchainUnavailableError) as raised:
            preflight_for_dispatch(
                plan.run_id,
                capabilities=capabilities,
                materialized_toolchains=(MaterializedToolchain(
                    "ruff-wheel", "ambient:UV_DEFAULT_INDEX", toolchain),),
                current_runner_context=context,
                reusable_runner_proof=proof,
                start=root,
            )
        self.assertEqual(raised.exception.code, "toolchain_unavailable")

    def test_relative_toolchain_path_cannot_select_bytes_through_ambient_cwd(self):
        root, _toolchain = self.project()
        spec = self.run_spec(root)
        plan = self.freeze(root, spec.run_id)

        with self.assertRaises(ToolchainUnavailableError) as raised:
            MaterializedToolchain(
                "ruff-wheel",
                plan.required_toolchains[0].source_id,
                Path(".toolchains/ruff.whl"),
            )
        self.assertIn("ambient cwd", str(raised.exception))
        self.assertEqual(self.open_store(root).get_run(plan.run_id).state,
                         "verification-plan-frozen")

    def test_ambient_parent_environment_never_enters_plan_or_preflight_authority(self):
        root, toolchain = self.project()
        spec = self.run_spec(root)
        with mock.patch.dict(os.environ, {
            "AWS_SECRET_ACCESS_KEY": "ambient-secret",
            "WAYSTONE_OWNER_TOKEN": "ambient-owner",
        }, clear=False):
            plan = self.freeze(root, spec.run_id)
            ready = self.preflight(root, plan, toolchain)

        store = self.open_store(root)
        evidence = ArtifactStore(root).read_reference(
            store.get_artifact_reference(
                f"verification-preflight:{plan.run_id}"))
        authority = plan.canonical_bytes() + evidence
        self.assertNotIn(b"AWS_SECRET_ACCESS_KEY", authority)
        self.assertNotIn(b"ambient-secret", authority)
        self.assertNotIn(b"WAYSTONE_OWNER_TOKEN", authority)
        self.assertNotIn(b"ambient-owner", authority)
        self.assertEqual(ready.engine_actions[0].child_environment,
                         plan.required_checks[0].environment)

    def test_public_dispatch_precondition_has_no_optional_plan_or_worker_launcher(self):
        parameters = inspect.signature(preflight_for_dispatch).parameters
        self.assertEqual(parameters["run_id"].default, inspect.Parameter.empty)
        self.assertNotIn("plan", parameters)
        self.assertNotIn("launcher", parameters)


if __name__ == "__main__":
    unittest.main(verbosity=2)
