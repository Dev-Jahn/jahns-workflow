"""Contract tests for ADR-0009 canonical review artifact addressing."""
from __future__ import annotations

import json
import subprocess

from support import *  # noqa: F401,F403

from waystone.features import review_layout


class ReviewRunsLayoutTests(unittest.TestCase):
    ROUND_ID = "2026-07-21-canonical-packet"
    NARRATIVE = "\n".join((
        "## What changed and why", "Canonical review owner wiring.",
        "## Read these first", "waystone/features/review_layout.py",
        "## Claims to attack", "The packet never writes a new flat artifact.",
        "## Evidence already produced (mine — inspect, don't trust)", "Contract tests.",
        "## Known weak spots", "Legacy evidence remains flat.",
        "## Domain lens", "Identity must be explicit.", "",
    ))

    def _prepared_packet(self, base: Path) -> tuple[Path, Path, dict]:
        root = base / "repo"
        root.mkdir()
        init_repo(root)
        (root / ".waystone.yml").write_text(
            "version: 1\nproject: canonical-test\nreviews_dir: docs/reviews\n"
            "review:\n  mode: packet\n  reviewers: [reviewer-x]\n")
        (root / "tasks.yaml").write_text(
            "version: 1\nproject: canonical-test\ntasks: []\n")
        narrative = root / "narrative.md"
        narrative.write_text(self.NARRATIVE)
        git(root, "add", "-A")
        git(root, "commit", "-qm", "packet inputs")
        head = git(root, "rev-parse", "HEAD").stdout.strip()
        exposure_dir = common.project_state_path(root) / "exposure"
        exposure_dir.mkdir(parents=True)
        (exposure_dir / f"round-{self.ROUND_ID}.json").write_text(json.dumps({
            "schema": "waystone-round-exposure-1",
            "round_id": self.ROUND_ID,
            "at": "2026-07-21T00:00:00+00:00",
            "head_sha": head,
            "base_sha": None,
            "review_mode": "packet",
            "reviewers": ["reviewer-x"],
            "project": {"name": "canonical-test", "branch": "main"},
        }) + "\n")
        self.assertEqual(review.prepare_review_request(root, self.ROUND_ID, narrative), 0)
        return root, narrative, review.packet_review_artifacts(root, self.ROUND_ID)

    def test_uuid7_generator_uses_canonical_rfc9562_shape(self):
        from unittest import mock

        with mock.patch.object(
                review_layout.secrets, "randbits", return_value=(1 << 74) - 1) as random_bits:
            run_id = review_layout.new_run_id(unix_ms=1_721_260_800_123)

        random_bits.assert_called_once_with(74)
        self.assertTrue(review_layout.is_uuid7(run_id))
        self.assertEqual(run_id, run_id.lower())
        self.assertEqual(run_id.count("-"), 4)

    def test_canonical_reader_requires_segment_and_payload_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            reviews = Path(directory) / "docs/reviews"
            owner = review_layout.new_run_id()
            other = review_layout.new_run_id()
            path = review_layout.canonical_artifact_path(
                reviews, owner, review_layout.REQUEST_BINDING)
            path.parent.mkdir(parents=True)

            path.write_text(json.dumps({"run_id": other, "round_id": "round-a"}) + "\n")
            with self.assertRaises(review_layout.IdentityConflict):
                review_layout.read_canonical_artifact(reviews, path)

            path.write_text(json.dumps({"round_id": "round-a"}) + "\n")
            with self.assertRaises(review_layout.IdentityConflict):
                review_layout.read_canonical_artifact(reviews, path)

            path.write_text(json.dumps({"run_id": owner, "round_id": "round-a"}) + "\n")
            artifact = review_layout.read_canonical_artifact(reviews, path)
            self.assertEqual(artifact["run_id"], owner)
            self.assertEqual(artifact["payload"]["run_id"], owner)

            invalid_segment = reviews / "runs/not-a-uuid/request.binding.json"
            invalid_segment.parent.mkdir(parents=True)
            invalid_segment.write_text(json.dumps({"run_id": owner}) + "\n")
            with self.assertRaises(review_layout.InvalidRunId):
                review_layout.read_canonical_artifact(reviews, invalid_segment)

    def test_canonical_identity_failure_never_falls_back_to_flat(self):
        with tempfile.TemporaryDirectory() as directory:
            reviews = Path(directory) / "docs/reviews"
            owner = review_layout.new_run_id()
            canonical = review_layout.canonical_artifact_path(
                reviews, owner, review_layout.REQUEST_BINDING)
            canonical.parent.mkdir(parents=True)
            canonical.write_text('{"round_id":"2026-07-21-flat"}\n')
            flat = reviews / "2026-07-21-flat-request.binding.json"
            flat.write_text('{"round_id":"2026-07-21-flat"}\n')

            with self.assertRaises(review_layout.IdentityConflict):
                review_layout.read_canonical_artifact(reviews, canonical)
            legacy = review_layout.read_legacy_artifact(reviews, flat)
            self.assertEqual(legacy["evidence"], "legacy")
            self.assertNotEqual(legacy["path"], canonical)

    def test_round_resolver_refuses_matching_rejected_owner_without_flat_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".waystone.yml").write_text(
                "version: 1\nproject: identity-test\nreviews_dir: docs/reviews\n")
            reviews = root / "docs/reviews"
            owner = review_layout.new_run_id()
            canonical = review_layout.canonical_artifact_path(
                reviews, owner, review_layout.REQUEST_BINDING)
            canonical.parent.mkdir(parents=True)
            canonical.write_text(json.dumps({"round_id": "2026-07-21-flat"}) + "\n")
            flat = reviews / "2026-07-21-flat-request.md"
            flat.write_text("# Historical flat request\n")

            with self.assertRaises(review_layout.IdentityConflict):
                review.packet_review_artifacts(root, "2026-07-21-flat")

    def test_every_canonical_binding_claim_blocks_same_round_flat_fallback(self):
        cases = (
            ("invalid-round", {"round_id": "invalid-round"}),
            ("2026-07-21-pr-owner", {
                "schema": review.ROUND_REQUEST_BINDING_SCHEMA,
                "round_id": "2026-07-21-pr-owner",
                "target_sha": "a" * 40,
                "base_sha": "b" * 40,
                "reviewers": ["reviewer-x"],
                "mode": "pr",
                "canonical_store": "github-pr-comment",
                "narrative_digest": TEST_NARRATIVE_DIGEST,
                "rendered_request_digest": TEST_RENDERED_REQUEST_DIGEST,
                "at": "2026-07-21T00:00:00+00:00",
            }),
        )
        for round_id, payload in cases:
            with self.subTest(round_id=round_id), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".waystone.yml").write_text(
                    "version: 1\nproject: claim-test\nreviews_dir: docs/reviews\n")
                reviews = root / "docs/reviews"
                owner = review_layout.new_run_id()
                review_layout.publish_json(
                    reviews, owner, review_layout.REQUEST_BINDING, payload)
                (reviews / f"{round_id}-request.md").write_text("# Flat decoy\n")

                with self.assertRaises(review_layout.IdentityConflict):
                    review.packet_review_artifacts(root, round_id)

    def test_legacy_adapter_refuses_symlink_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            reviews = Path(directory) / "docs/reviews"
            reviews.mkdir(parents=True)
            outside = Path(directory) / "outside.md"
            outside.write_text("# Outside\n")
            alias = reviews / "2026-07-21-alias-request.md"
            alias.symlink_to(outside)

            with self.assertRaises(review_layout.ReviewLayoutError):
                review_layout.read_legacy_artifact(reviews, alias)

    def test_legacy_binding_symlink_cannot_bypass_adapter_in_live_readers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            (root / ".waystone.yml").write_text(
                "version: 1\nproject: symlink-test\nreviews_dir: docs/reviews\n")
            reviews = root / "docs/reviews"
            reviews.mkdir(parents=True)
            round_id = "2026-07-21-symlink-binding"
            target, base_sha = "a" * 40, "b" * 40
            (reviews / f"{round_id}-request.md").write_text(
                f"# Request\n\n- Reviewing: {target}   (diff against {base_sha})\n")
            outside = root.parent / "outside-binding.json"
            outside.write_text(json.dumps({
                "schema": review.ROUND_REQUEST_BINDING_SCHEMA,
                "round_id": round_id,
                "target_sha": target,
                "base_sha": base_sha,
                "reviewers": ["reviewer-x"],
                "mode": "packet",
                "canonical_store": "local-packet",
                "narrative_digest": TEST_NARRATIVE_DIGEST,
                "rendered_request_digest": TEST_RENDERED_REQUEST_DIGEST,
                "at": "2026-07-21T00:00:00+00:00",
            }) + "\n")
            binding_alias = reviews / f"{round_id}-request.binding.json"
            binding_alias.symlink_to(outside)

            with self.assertRaises(review_layout.ReviewLayoutError):
                review.packet_review_artifacts(root, round_id)
            binding, reason = review.ingest_round_binding(
                root, round_id, common.load_config(root))
            pending = review.pending_reviews(root)

            self.assertIsNone(binding)
            self.assertEqual(reason, "corrupt-round-binding:ReviewLayoutError")
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["round_id"], round_id)
            self.assertEqual(
                pending[0]["reason"], "legacy-artifact-identity-conflict")
            self.assertIsNone(pending[0]["target_sha"])

    def test_foreign_rejected_binding_is_isolated_from_healthy_rounds(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _narrative, healthy = self._prepared_packet(Path(directory))
            reviews = root / "docs/reviews"
            foreign_owner = review_layout.new_run_id()
            foreign = review_layout.canonical_artifact_path(
                reviews, foreign_owner, review_layout.REQUEST_BINDING)
            foreign.parent.mkdir(parents=True)
            foreign.write_text(json.dumps({"round_id": "2026-07-21-foreign"}) + "\n")
            legacy = reviews / "2026-07-21-historical-request.md"
            legacy.write_text("# Historical request\n")

            resolved = review.packet_review_artifacts(root, self.ROUND_ID)
            historical = review.packet_review_artifacts(root, "2026-07-21-historical")
            pending = review.pending_reviews(root)

            self.assertEqual(resolved["run_id"], healthy["run_id"])
            self.assertEqual(historical["evidence"], "legacy")
            self.assertEqual(review.packet_review_round_ids(root), [
                self.ROUND_ID, "2026-07-21-historical",
            ])
            self.assertEqual(
                {row["round_id"] for row in pending}, {
                    self.ROUND_ID, "2026-07-21-foreign", "2026-07-21-historical",
                })
            self.assertEqual(
                next(row for row in pending
                     if row["round_id"] == "2026-07-21-foreign")["reason"],
                "canonical-artifact-identity-conflict")

    def test_rejected_foreign_binding_cannot_override_proven_healthy_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _narrative, healthy = self._prepared_packet(Path(directory))
            reviews = root / "docs/reviews"
            foreign_owner = review_layout.new_run_id()
            foreign = review_layout.canonical_artifact_path(
                reviews, foreign_owner, review_layout.REQUEST_BINDING)
            foreign.parent.mkdir(parents=True)
            foreign.write_text(json.dumps({"round_id": self.ROUND_ID}) + "\n")

            resolved = review.packet_review_artifacts(root, self.ROUND_ID)
            pending = review.pending_reviews(root)

            self.assertEqual(resolved["run_id"], healthy["run_id"])
            self.assertEqual([row["round_id"] for row in pending], [self.ROUND_ID])
            self.assertNotEqual(
                pending[0]["reason"], "canonical-artifact-identity-conflict")

    def test_canonical_reader_and_writer_reject_owner_directory_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            reviews = base / "docs/reviews"
            outside = base / "outside"
            outside.mkdir()
            owner = review_layout.new_run_id()
            owner_link = reviews / "runs" / owner
            owner_link.parent.mkdir(parents=True)
            owner_link.symlink_to(outside, target_is_directory=True)
            binding = outside / "request.binding.json"
            binding.write_text(json.dumps({"run_id": owner, "round_id": "round-a"}) + "\n")

            with self.assertRaises(review_layout.IdentityConflict):
                review_layout.read_canonical_artifact(
                    reviews, owner_link / "request.binding.json")
            with self.assertRaises(review_layout.IdentityConflict):
                review_layout.publish_markdown(
                    reviews, owner, review_layout.REQUEST, b"# Must not escape\n")
            self.assertFalse((outside / "request.md").exists())

    def test_broken_canonical_binding_symlink_is_a_recorded_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            reviews = Path(directory) / "docs/reviews"
            owner = review_layout.new_run_id()
            binding = review_layout.canonical_artifact_path(
                reviews, owner, review_layout.REQUEST_BINDING)
            binding.parent.mkdir(parents=True)
            binding.symlink_to("missing-binding.json")

            artifacts, rejected = review_layout.scan_canonical_request_bindings(reviews)

            self.assertEqual(artifacts, ())
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0][0], binding)
            self.assertIsInstance(rejected[0][1], review_layout.IdentityConflict)

    def test_broken_canonical_fixed_leaf_symlink_is_an_identity_conflict(self):
        for leaf in ("request", "feedback"):
            with self.subTest(leaf=leaf), tempfile.TemporaryDirectory() as directory:
                root, _narrative, artifacts = self._prepared_packet(Path(directory))
                path = artifacts[leaf]
                path.unlink(missing_ok=True)
                path.symlink_to(f"missing-{leaf}.md")

                with self.assertRaises(review_layout.IdentityConflict):
                    review.packet_review_artifacts(root, self.ROUND_ID)

    def test_canonical_and_flat_same_round_is_an_identity_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _narrative, _artifacts = self._prepared_packet(Path(directory))
            flat = root / "docs/reviews" / f"{self.ROUND_ID}-request.md"
            flat.write_text("# Conflicting flat request\n")

            with self.assertRaises(review_layout.IdentityConflict):
                review.packet_review_artifacts(root, self.ROUND_ID)

    def test_writer_round_trip_preserves_published_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            reviews = Path(directory) / "docs/reviews"
            owner = review_layout.new_run_id()
            request = review_layout.publish_markdown(
                reviews, owner, review_layout.REQUEST, b"# Review request\n")
            binding = review_layout.publish_json(
                reviews, owner, review_layout.REQUEST_BINDING,
                {"round_id": "2026-07-21-roundtrip"})
            before = {path: path.read_bytes() for path in (request, binding)}

            artifacts = {
                artifact["kind"]: artifact
                for artifact in review_layout.read_canonical_run(reviews, owner)
            }

            self.assertEqual(set(artifacts), {
                review_layout.REQUEST, review_layout.REQUEST_BINDING,
            })
            self.assertEqual(artifacts[review_layout.REQUEST]["bytes"], before[request])
            self.assertEqual(artifacts[review_layout.REQUEST_BINDING]["bytes"], before[binding])
            self.assertEqual(
                {path: path.read_bytes() for path in (request, binding)}, before)
            self.assertEqual(
                review_layout.publish_markdown(
                    reviews, owner, review_layout.REQUEST, b"# Review request\n"),
                request,
            )
            with self.assertRaises(review_layout.ArtifactConflict):
                review_layout.publish_markdown(
                    reviews, owner, review_layout.REQUEST, b"# Different request\n")

    def test_feedback_replace_refuses_corrupt_existing_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            reviews = Path(directory) / "docs/reviews"
            owner = review_layout.new_run_id()
            feedback = review_layout.publish_markdown(
                reviews, owner, review_layout.FEEDBACK, b"# Original\n")
            feedback.write_bytes(b"corrupt identity\n")
            before = feedback.read_bytes()

            with self.assertRaises(review_layout.IdentityConflict):
                review_layout.publish_markdown(
                    reviews, owner, review_layout.FEEDBACK,
                    b"# Replacement\n", replace=True)

            self.assertEqual(feedback.read_bytes(), before)

    def test_writer_maps_all_five_artifact_kinds_and_records_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            reviews = Path(directory) / "docs/reviews"
            owner = review_layout.new_run_id()
            paths = (
                review_layout.publish_markdown(
                    reviews, owner, review_layout.REQUEST, b"# Request\n"),
                review_layout.publish_json(
                    reviews, owner, review_layout.REQUEST_BINDING, {"round_id": "r"}),
                review_layout.publish_markdown(
                    reviews, owner, review_layout.FEEDBACK, b"# Feedback\n"),
                review_layout.publish_json(
                    reviews, owner, review_layout.PR_FREEZE, {"cycle": 1}, locator=1),
                review_layout.publish_json(
                    reviews, owner, review_layout.PR_DEMOTION,
                    {"observation_id": "obs-a"}, locator="obs-a"),
            )

            artifacts = [
                review_layout.read_canonical_artifact(reviews, path) for path in paths
            ]

            self.assertEqual(
                {artifact["kind"] for artifact in artifacts}, {
                    review_layout.REQUEST, review_layout.REQUEST_BINDING,
                    review_layout.FEEDBACK, review_layout.PR_FREEZE,
                    review_layout.PR_DEMOTION,
                })
            self.assertTrue(all(artifact["payload"]["run_id"] == owner
                                for artifact in artifacts))

    def test_live_packet_prepare_mints_uuid_owner_and_writes_no_flat_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _narrative, artifacts = self._prepared_packet(Path(directory))
            reviews = root / "docs/reviews"

            self.assertTrue(review_layout.is_uuid7(artifacts["run_id"]))
            self.assertNotEqual(artifacts["run_id"], self.ROUND_ID)
            self.assertEqual(artifacts["binding"]["run_id"], artifacts["run_id"])
            self.assertEqual(
                review_layout.read_canonical_artifact(
                    reviews, artifacts["request"])["run_id"], artifacts["run_id"])
            self.assertEqual(
                [path for path in reviews.iterdir() if path.is_file()], [])

    def test_ingest_without_request_or_binding_refuses_new_flat_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".waystone.yml").write_text(
                "version: 1\nproject: missing-owner\nreviews_dir: docs/reviews\n")
            reply = root / "reply.md"
            reply.write_text("model: reviewer-x\neffort: high\nreviewed\n")
            round_id = "2026-07-21-no-owner"

            self.assertEqual(review.ingest(root, round_id, src=reply), 1)

            self.assertTrue(reply.exists())
            self.assertFalse(
                (root / "docs/reviews" / f"{round_id}-feedback.md").exists())

    def test_jw_gpt_015_foreign_malformed_sidecar_does_not_block_live_ingest(self):
        """JW-GPT-015: foreign corruption cannot stop healthy owner ingest/pending."""
        with tempfile.TemporaryDirectory() as directory:
            root, _narrative, artifacts = self._prepared_packet(Path(directory))
            reviews = root / "docs/reviews"
            foreign = review_layout.new_run_id()
            malformed = review_layout.canonical_artifact_path(
                reviews, foreign, review_layout.PR_FREEZE, locator="broken")
            malformed.parent.mkdir(parents=True)
            malformed.write_bytes(b"{broken")
            binding = artifacts["binding"]
            reply = root / "reply.md"
            reply.write_text(
                "model: reviewer-x\neffort: high\n"
                f"review-target: {binding['target_sha']}\n"
                f"request-digest: {binding['rendered_request_digest']}\n\nreviewed\n")

            self.assertEqual(review.ingest(root, self.ROUND_ID, src=reply), 0)

            refreshed = review.packet_review_artifacts(root, self.ROUND_ID)
            feedback = review_layout.read_canonical_artifact(
                reviews, refreshed["feedback"])
            self.assertEqual(feedback["run_id"], artifacts["run_id"])
            self.assertFalse((reviews / f"{self.ROUND_ID}-feedback.md").exists())
            self.assertEqual(review.pending_reviews(root), [])

    def test_remote_verify_reads_canonical_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root, _narrative, artifacts = self._prepared_packet(base)
            remote = base / "remote.git"
            subprocess.run(
                ["git", "init", "--bare", "-q", str(remote)], check=True)
            git(root, "add", "-A")
            git(root, "commit", "-qm", "publish canonical packet")
            git(root, "remote", "add", "origin", str(remote))
            pushed = git(root, "push", "-qu", "origin", "main")
            self.assertEqual(pushed.returncode, 0, pushed.stderr)

            self.assertEqual(review.verify_packet_publication(root, self.ROUND_ID), 0)
            self.assertIn("/runs/", artifacts["request"].as_posix())

    def test_live_overlay_rule_reads_canonical_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".waystone.yml").write_text(
                "version: 1\nproject: overlay-test\nreviews_dir: docs/reviews\n"
                "review:\n  mode: packet\n")
            round_id = "2026-07-21-overlay"
            (root / "tasks.yaml").write_text(
                "version: 1\nproject: overlay-test\ntasks:\n"
                "  - id: fix/rejected\n"
                "    title: rejected review finding\n"
                "    status: active\n"
                "    severity: blocker\n"
                f"    origin: review-{round_id}\n")
            reviews = root / "docs/reviews"
            owner = review_layout.new_run_id()
            review_layout.publish_json(
                reviews, owner, review_layout.REQUEST_BINDING, {
                    "schema": review.ROUND_REQUEST_BINDING_SCHEMA,
                    "round_id": round_id,
                    "target_sha": "a" * 40,
                    "base_sha": "b" * 40,
                    "reviewers": ["reviewer-x"],
                    "mode": "packet",
                    "canonical_store": "local-packet",
                    "narrative_digest": TEST_NARRATIVE_DIGEST,
                    "rendered_request_digest": TEST_RENDERED_REQUEST_DIGEST,
                    "at": "2026-07-21T00:00:00+00:00",
                })
            review_layout.publish_markdown(
                reviews, owner, review_layout.FEEDBACK,
                b"meta\n\n## Findings (triage skeleton v1)\n"
                b"| Finding | Severity | Verdict | Evidence | Task |\n"
                b"| --- | --- | --- | --- | --- |\n"
                b"| WS-GPT-001 - rejected | `blocker` | REJECTED | ev | `fix/rejected` |\n")

            result = overlay.evaluate_rule2(
                root, common.load_config(root), ["blocker"], round_filter=round_id)

            self.assertEqual(result["fires"], [])
            self.assertEqual(result["evaluation_errors"], 0)

    def test_jw_gpt_015_foreign_malformed_sidecar_cannot_block_healthy_owner(self):
        """JW-GPT-015: a foreign malformed sidecar is outside the healthy owner read."""
        with tempfile.TemporaryDirectory() as directory:
            reviews = Path(directory) / "docs/reviews"
            healthy = review_layout.new_run_id()
            foreign = review_layout.new_run_id()
            review_layout.publish_markdown(
                reviews, healthy, review_layout.REQUEST, b"# Healthy\n")
            review_layout.publish_json(
                reviews, healthy, review_layout.REQUEST_BINDING,
                {"round_id": "2026-07-21-healthy"})
            malformed = review_layout.canonical_artifact_path(
                reviews, foreign, review_layout.PR_FREEZE, locator=1)
            malformed.parent.mkdir(parents=True)
            malformed.write_bytes(b"{broken")

            artifacts = review_layout.read_canonical_run(reviews, healthy)

            self.assertEqual(len(artifacts), 2)
            self.assertTrue(all(artifact["run_id"] == healthy for artifact in artifacts))
            with self.assertRaises(review_layout.IdentityConflict):
                review_layout.read_canonical_artifact(reviews, malformed)

    def test_pc14_historical_flat_evidence_stays_legacy_and_byte_unchanged(self):
        repository = Path(__file__).resolve().parents[2]
        names = (
            "2026-07-16-fix-wave-request.md",
            "2026-07-16-fix-wave-request.binding.json",
            "2026-07-16-fix-wave-request.binding-2.json",
            "2026-07-16-fix-wave-feedback.md",
        )
        historical = {
            name: (repository / "docs/reviews" / name).read_bytes()
            for name in names
        }
        with tempfile.TemporaryDirectory() as directory:
            reviews = Path(directory) / "docs/reviews"
            reviews.mkdir(parents=True)
            for name, content in historical.items():
                (reviews / name).write_bytes(content)
            settlement_source = (
                repository / "docs/reviews/legacy-settlements/2026-07-16-fix-wave.json")
            settlement = settlement_source.read_bytes()
            settlement_copy = reviews / "legacy-settlements/2026-07-16-fix-wave.json"
            settlement_copy.parent.mkdir()
            settlement_copy.write_bytes(settlement)

            legacy = [
                review_layout.read_legacy_artifact(reviews, reviews / name)
                for name in names
            ]
            before_names = {path.name for path in reviews.iterdir() if path.is_file()}
            owner = review_layout.new_run_id()
            review_layout.publish_markdown(
                reviews, owner, review_layout.REQUEST, b"# Canonical next request\n")
            review_layout.publish_json(
                reviews, owner, review_layout.REQUEST_BINDING,
                {"round_id": "2026-07-21-canonical-next"})

            self.assertTrue(all(artifact["evidence"] == "legacy" for artifact in legacy))
            self.assertEqual(
                {path.name for path in reviews.iterdir() if path.is_file()}, before_names)
            self.assertEqual(
                {name: (reviews / name).read_bytes() for name in names}, historical)
            self.assertEqual(settlement_copy.read_bytes(), settlement)
            self.assertTrue((reviews / "runs" / owner / "request.md").is_file())

    def test_pc14_legacy_packet_mutations_are_refused_and_bytes_unchanged(self):
        repository = Path(__file__).resolve().parents[2]
        round_id = "2026-07-16-fix-wave"
        names = (
            f"{round_id}-request.md",
            f"{round_id}-request.binding.json",
            f"{round_id}-request.binding-2.json",
            f"{round_id}-feedback.md",
        )
        historical = {
            name: (repository / "docs/reviews" / name).read_bytes()
            for name in names
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".waystone.yml").write_text(
                "version: 1\nproject: pc14-test\nreviews_dir: docs/reviews\n"
                "review:\n  mode: packet\n")
            reviews = root / "docs/reviews"
            reviews.mkdir(parents=True)
            for name, content in historical.items():
                (reviews / name).write_bytes(content)
            reply = root / "reply.md"
            reply.write_bytes(b"replacement review\n")
            triage = root / "triage.md"
            triage.write_bytes(b"replacement triage\n")

            self.assertEqual(review.ingest(root, round_id, src=reply), 1)
            self.assertEqual(review.ingest(root, round_id, src=reply, force=True), 1)
            with self.assertRaises(common.WorkflowError):
                review.triage(root, round_id, triage)

            (root / ".waystone.yml").write_text(
                "version: 1\nproject: pc14-test\nreviews_dir: docs/reviews\n"
                "review:\n  mode: pr\n")
            self.assertEqual(review.ingest(root, round_id, src=reply), 1)
            self.assertEqual(review.ingest(root, round_id, src=reply, force=True), 1)
            with self.assertRaises(common.WorkflowError):
                review.triage(root, round_id, triage)

            self.assertTrue(reply.exists())
            self.assertTrue(triage.exists())
            self.assertEqual(
                {name: (reviews / name).read_bytes() for name in names}, historical)
            self.assertFalse((reviews / "runs").exists())
