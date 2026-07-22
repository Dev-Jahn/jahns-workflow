"""Reserved worker-result control file and context-request adaptation."""
from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml

from waystone.core import WorkflowError
from waystone.runs.artifacts import ArtifactStore, StoredArtifact, validate_sha256_digest
from waystone.runs.spec import BaseSnapshot, _capture_snapshot


WORKER_RESULT_SCHEMA = "waystone-worker-result-1"
CONTEXT_REQUEST_SCHEMA = "waystone-context-request-1"
CONTEXT_RESPONSE_SCHEMA = "waystone-context-response-1"
RUNNER_COMPLETION_SCHEMA = "waystone-runner-completion-2"
RESULT_CONTROL_FILE = "WAYSTONE_RESULT.yaml"


class WorkerResultError(WorkflowError):
    code = "worker_result_error"

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(f"{self.code}: {detail}")


class WorkerResultMissing(WorkerResultError):
    code = "worker_result_missing"


class WorkerResultSchemaRefusal(WorkerResultError):
    code = "worker_result_schema_refusal"


class WorkerResultBindingMismatch(WorkerResultError):
    code = "worker_result_binding_mismatch"


class ContextRequestWithChanges(WorkerResultError):
    code = "context_request_with_changes"


class ContextResponseBindingMismatch(WorkerResultError):
    code = "context_response_binding_mismatch"


class RunnerCompletionMarkerRefusal(WorkerResultError):
    code = "runner_completion_marker_refusal"


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False,
) -> dict:
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                f"found duplicate key {key!r}", key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkerResultSchemaRefusal(f"{field} must be a non-empty string")
    return value


@dataclass(frozen=True)
class EvidenceRef:
    reference_id: str
    digest: str

    def to_dict(self) -> dict[str, str]:
        return {"reference_id": self.reference_id, "digest": self.digest}


@dataclass(frozen=True)
class CompletedWorkerResult:
    run_spec_digest: str
    attempt_id: str
    result_summary: str
    evidence_refs: tuple[EvidenceRef, ...]
    status: str = "completed"


@dataclass(frozen=True)
class ContextRequestedWorkerResult:
    run_spec_digest: str
    attempt_id: str
    question: str
    blocked_decision: str
    why_required: str
    status: str = "context-requested"


WorkerResult = CompletedWorkerResult | ContextRequestedWorkerResult


@dataclass(frozen=True)
class ResultSnapshot:
    digest: str
    size: int
    snapshot: BaseSnapshot


@dataclass(frozen=True)
class ContextRequest:
    run_id: str
    job_id: str
    attempt_id: str
    run_spec_digest: str
    work_brief_digest: str
    question: str
    blocked_decision: str
    why_required: str
    observed_result_digest: str

    def canonical_bytes(self) -> bytes:
        return _canonical_json({
            "schema": CONTEXT_REQUEST_SCHEMA,
            "run_id": self.run_id,
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "run_spec_digest": self.run_spec_digest,
            "work_brief_digest": self.work_brief_digest,
            "question": self.question,
            "blocked_decision": self.blocked_decision,
            "why_required": self.why_required,
            "observed_result_digest": self.observed_result_digest,
        })


@dataclass(frozen=True)
class ContextResponse:
    request_digest: str
    answer_text: str
    answer_provenance: str
    answer_source: Mapping[str, object]
    binding_digest: str

    def canonical_bytes(self) -> bytes:
        return _canonical_json({
            "schema": CONTEXT_RESPONSE_SCHEMA,
            "request_digest": self.request_digest,
            "answer": {
                "text": self.answer_text,
                "provenance": self.answer_provenance,
                "source": dict(self.answer_source),
            },
            "issued_by": {
                "role": "coordinator",
                "binding_digest": self.binding_digest,
                "principal": None,
            },
        })


@dataclass(frozen=True)
class AdaptedWorkerResult:
    result: WorkerResult
    worker_result_artifact: StoredArtifact
    result_snapshot: ResultSnapshot
    context_request: ContextRequest | None
    context_request_artifact: StoredArtifact | None


@dataclass(frozen=True)
class RunnerCompletionMarkerV2:
    run_id: str
    job_id: str
    action_id: str
    fencing_epoch: int
    launch_token: str
    process_identity: str
    started_at: str
    finished_at: str
    returncode: int | None
    signal: int | None
    stdout_artifact_digest: str
    stderr_artifact_digest: str
    worker_result_digest: str

    def __post_init__(self) -> None:
        for field in (
                "run_id", "job_id", "action_id", "launch_token", "process_identity",
                "started_at", "finished_at"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string")
        if (isinstance(self.fencing_epoch, bool)
                or not isinstance(self.fencing_epoch, int) or self.fencing_epoch < 1):
            raise ValueError("fencing_epoch must be positive")
        if sum(value is not None for value in (self.returncode, self.signal)) != 1:
            raise ValueError("marker requires exactly one of returncode or signal")
        for value in (self.returncode, self.signal):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError("returncode/signal must be integers or null")
        for field in (
                "stdout_artifact_digest", "stderr_artifact_digest", "worker_result_digest"):
            object.__setattr__(self, field, validate_sha256_digest(getattr(self, field)))

    def canonical_bytes(self) -> bytes:
        return _canonical_json({
            "schema": RUNNER_COMPLETION_SCHEMA,
            "run_id": self.run_id,
            "job_id": self.job_id,
            "action_id": self.action_id,
            "fencing_epoch": self.fencing_epoch,
            "launch_token": self.launch_token,
            "process_identity": self.process_identity,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "returncode": self.returncode,
            "signal": self.signal,
            "stdout_artifact_digest": self.stdout_artifact_digest,
            "stderr_artifact_digest": self.stderr_artifact_digest,
            "worker_result_digest": self.worker_result_digest,
        })


def parse_runner_completion_marker_v2_bytes(content: bytes) -> RunnerCompletionMarkerV2:
    if not isinstance(content, bytes):
        raise TypeError("runner completion marker content must be bytes")
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RunnerCompletionMarkerRefusal(f"marker must be canonical JSON: {error}") from error
    fields = {
        "schema", "run_id", "job_id", "action_id", "fencing_epoch", "launch_token",
        "process_identity", "started_at", "finished_at", "returncode", "signal",
        "stdout_artifact_digest", "stderr_artifact_digest", "worker_result_digest",
    }
    if not isinstance(payload, dict) or set(payload) != fields:
        raise RunnerCompletionMarkerRefusal("marker v2 fields are not canonical")
    if payload["schema"] != RUNNER_COMPLETION_SCHEMA or _canonical_json(payload) != content:
        raise RunnerCompletionMarkerRefusal("marker v2 schema or encoding is invalid")
    try:
        return RunnerCompletionMarkerV2(**{
            key: value for key, value in payload.items() if key != "schema"
        })
    except (TypeError, ValueError) as error:
        raise RunnerCompletionMarkerRefusal(str(error)) from error


def parse_worker_result_bytes(
    content: bytes, *, expected_run_spec_digest: str | None = None,
    expected_attempt_id: str | None = None,
) -> WorkerResult:
    if not isinstance(content, bytes):
        raise TypeError("worker result content must be bytes")
    try:
        document = yaml.load(content.decode("utf-8"), Loader=_UniqueKeyLoader)
    except (UnicodeDecodeError, yaml.YAMLError, TypeError) as error:
        raise WorkerResultSchemaRefusal(f"worker result must be UTF-8 YAML: {error}") from error
    if not isinstance(document, Mapping):
        raise WorkerResultSchemaRefusal("worker result must contain one mapping")
    common = {"schema", "status", "run_spec_digest", "attempt_id"}
    status = document.get("status")
    if document.get("schema") != WORKER_RESULT_SCHEMA:
        raise WorkerResultSchemaRefusal(f"schema must be {WORKER_RESULT_SCHEMA}")
    try:
        run_spec_digest = validate_sha256_digest(document.get("run_spec_digest"))
    except ValueError as error:
        raise WorkerResultSchemaRefusal(str(error)) from error
    attempt_id = _nonempty(document.get("attempt_id"), "attempt_id")
    if expected_run_spec_digest is not None and run_spec_digest != validate_sha256_digest(
            expected_run_spec_digest):
        raise WorkerResultBindingMismatch("run_spec_digest differs from the launched attempt")
    if expected_attempt_id is not None and attempt_id != expected_attempt_id:
        raise WorkerResultBindingMismatch("attempt_id differs from the launched attempt")

    if status == "completed":
        if set(document) != common | {"result_summary", "evidence_refs"}:
            raise WorkerResultSchemaRefusal("completed worker result fields are not canonical")
        raw_refs = document["evidence_refs"]
        if not isinstance(raw_refs, list):
            raise WorkerResultSchemaRefusal("evidence_refs must be a list")
        references = []
        for index, value in enumerate(raw_refs):
            if not isinstance(value, Mapping) or set(value) != {"reference_id", "digest"}:
                raise WorkerResultSchemaRefusal(f"evidence_refs[{index}] is invalid")
            try:
                digest = validate_sha256_digest(value["digest"])
            except ValueError as error:
                raise WorkerResultSchemaRefusal(f"evidence_refs[{index}]: {error}") from error
            references.append(EvidenceRef(
                _nonempty(value["reference_id"], f"evidence_refs[{index}].reference_id"),
                digest,
            ))
        return CompletedWorkerResult(
            run_spec_digest, attempt_id,
            _nonempty(document["result_summary"], "result_summary"),
            tuple(references),
        )
    if status == "context-requested":
        if set(document) != common | {"context_request"}:
            raise WorkerResultSchemaRefusal(
                "context-requested worker result fields are not canonical")
        request = document["context_request"]
        if not isinstance(request, Mapping) or set(request) != {
                "question", "blocked_decision", "why_required"}:
            raise WorkerResultSchemaRefusal("context_request fields are not canonical")
        return ContextRequestedWorkerResult(
            run_spec_digest,
            attempt_id,
            _nonempty(request["question"], "context_request.question"),
            _nonempty(request["blocked_decision"], "context_request.blocked_decision"),
            _nonempty(request["why_required"], "context_request.why_required"),
        )
    raise WorkerResultSchemaRefusal("status must be completed or context-requested")


def _canonical_backend_projection_bytes(content: bytes) -> bytes:
    """Remove only the inactive null branch required by Codex structured output."""
    try:
        document = yaml.load(content.decode("utf-8"), Loader=_UniqueKeyLoader)
    except (UnicodeDecodeError, yaml.YAMLError, TypeError) as error:
        raise WorkerResultSchemaRefusal(
            f"worker result must be UTF-8 YAML: {error}") from error
    if not isinstance(document, Mapping):
        raise WorkerResultSchemaRefusal("worker result must contain one mapping")
    projected_fields = {
        "schema", "status", "run_spec_digest", "attempt_id",
        "result_summary", "evidence_refs", "context_request",
    }
    if set(document) != projected_fields:
        return content
    status = document.get("status")
    if status == "completed":
        if document["context_request"] is not None:
            raise WorkerResultSchemaRefusal(
                "completed worker result cannot include context_request")
        return _canonical_json({
            key: value for key, value in document.items() if key != "context_request"
        })
    if status == "context-requested":
        if document["result_summary"] is not None or document["evidence_refs"] is not None:
            raise WorkerResultSchemaRefusal(
                "context-requested worker result cannot include completed fields")
        return _canonical_json({
            key: value for key, value in document.items()
            if key not in {"result_summary", "evidence_refs"}
        })
    return content


def parse_context_response_bytes(
    content: bytes, *, expected_request_digest: str | None = None,
    expected_binding_digest: str | None = None,
) -> ContextResponse:
    if not isinstance(content, bytes):
        raise TypeError("context response content must be bytes")
    try:
        document = yaml.load(content.decode("utf-8"), Loader=_UniqueKeyLoader)
    except (UnicodeDecodeError, yaml.YAMLError, TypeError) as error:
        raise WorkerResultSchemaRefusal(f"context response must be UTF-8 YAML: {error}") from error
    if not isinstance(document, Mapping) or set(document) != {
            "schema", "request_digest", "answer", "issued_by"}:
        raise WorkerResultSchemaRefusal("context response fields are not canonical")
    if document["schema"] != CONTEXT_RESPONSE_SCHEMA:
        raise WorkerResultSchemaRefusal(f"schema must be {CONTEXT_RESPONSE_SCHEMA}")
    try:
        request_digest = validate_sha256_digest(document["request_digest"])
    except ValueError as error:
        raise WorkerResultSchemaRefusal(f"request_digest: {error}") from error
    answer = document["answer"]
    if not isinstance(answer, Mapping) or set(answer) != {"text", "provenance", "source"}:
        raise WorkerResultSchemaRefusal("context response answer fields are not canonical")
    provenance = answer["provenance"]
    if provenance not in ("owner-source", "harness-observation", "coordinator-summary"):
        raise WorkerResultSchemaRefusal("answer provenance is invalid")
    source = answer["source"]
    if not isinstance(source, Mapping) or not isinstance(source.get("kind"), str):
        raise WorkerResultSchemaRefusal("answer source must be a typed mapping")
    source_digest = source.get("digest") or source.get("fact_digest") or source.get("item_digest")
    try:
        validate_sha256_digest(source_digest)
    except ValueError as error:
        raise WorkerResultSchemaRefusal(f"answer source: {error}") from error
    actor = document["issued_by"]
    if not isinstance(actor, Mapping) or set(actor) != {
            "role", "binding_digest", "principal"}:
        raise WorkerResultSchemaRefusal("issued_by fields are not canonical")
    if actor["role"] != "coordinator" or actor["principal"] is not None:
        raise WorkerResultSchemaRefusal(
            "issued_by must be coordinator with unauthenticated principal: null")
    try:
        binding_digest = validate_sha256_digest(actor["binding_digest"])
    except ValueError as error:
        raise WorkerResultSchemaRefusal(f"issued_by.binding_digest: {error}") from error
    if (expected_request_digest is not None
            and request_digest != validate_sha256_digest(expected_request_digest)):
        raise ContextResponseBindingMismatch("response does not bind the current request")
    if (expected_binding_digest is not None
            and binding_digest != validate_sha256_digest(expected_binding_digest)):
        raise ContextResponseBindingMismatch("coordinator binding_digest is stale")
    return ContextResponse(
        request_digest=request_digest,
        answer_text=_nonempty(answer["text"], "answer.text"),
        answer_provenance=provenance,
        answer_source=dict(source),
        binding_digest=binding_digest,
    )


def revise_work_brief_for_response(
    previous_content: bytes,
    response: ContextResponse,
) -> bytes:
    """Derive the one mechanical WorkBrief lineage update represented by a response."""
    if not isinstance(previous_content, bytes):
        raise TypeError("previous WorkBrief content must be bytes")
    if not isinstance(response, ContextResponse):
        raise TypeError("response must be a ContextResponse")
    try:
        previous = json.loads(previous_content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkerResultSchemaRefusal(
            f"previous WorkBrief is not canonical JSON: {error}") from error
    if not isinstance(previous, dict) or _canonical_json(previous) != previous_content:
        raise WorkerResultSchemaRefusal("previous WorkBrief bytes are not canonical JSON")
    revision = previous.get("revision")
    current_state = previous.get("current_state")
    if type(revision) is not int or revision < 1 or not isinstance(current_state, list):
        raise WorkerResultSchemaRefusal("previous WorkBrief revision/current_state is invalid")
    revised = dict(previous)
    revised["revision"] = revision + 1
    revised["supersedes_digest"] = _digest(previous_content)
    revised["resolves_context_request_digest"] = response.request_digest
    revised["current_state"] = [
        *current_state,
        {
            "text": response.answer_text,
            "provenance": response.answer_provenance,
            "source": dict(response.answer_source),
        },
    ]
    return _canonical_json(revised)


def capture_result_snapshot(root: Path) -> ResultSnapshot:
    """Capture the existing Git snapshot format while excluding the reserved control file."""
    snapshot = _capture_snapshot(Path(root))
    filtered = BaseSnapshot(
        snapshot.head,
        tuple(entry for entry in snapshot.entries if entry.path != RESULT_CONTROL_FILE.encode()),
    )
    content = filtered.canonical_bytes()
    return ResultSnapshot(_digest(content), len(content), filtered)


class WorkerResultAdapter:
    def __init__(self, root: Path, artifact_store: ArtifactStore | None = None):
        self.root = Path(root)
        self.artifact_store = artifact_store or ArtifactStore(self.root)

    def adapt(
        self, *, run_id: str, job_id: str, attempt_id: str,
        run_spec_digest: str, work_brief_digest: str, base_snapshot_digest: str,
    ) -> AdaptedWorkerResult:
        """Read the control file once, publish it, then snapshot without that control file."""
        path = self.root / RESULT_CONTROL_FILE
        try:
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise WorkerResultMissing("reserved worker result must be a regular file")
            content = path.read_bytes()
        except WorkerResultError:
            raise
        except OSError as error:
            raise WorkerResultMissing(f"cannot read reserved worker result: {error}") from error
        return self._adapt_content(
            content,
            run_id=run_id, job_id=job_id, attempt_id=attempt_id,
            run_spec_digest=run_spec_digest, work_brief_digest=work_brief_digest,
            base_snapshot_digest=base_snapshot_digest,
        )

    def adapt_published(
        self, worker_result_digest: str, *, run_id: str, job_id: str, attempt_id: str,
        run_spec_digest: str, work_brief_digest: str, base_snapshot_digest: str,
    ) -> AdaptedWorkerResult:
        """Observe supervisor-adapted CAS bytes without rereading the worker control file."""
        content = self.artifact_store.read(validate_sha256_digest(worker_result_digest))
        return self._adapt_content(
            content,
            run_id=run_id, job_id=job_id, attempt_id=attempt_id,
            run_spec_digest=run_spec_digest, work_brief_digest=work_brief_digest,
            base_snapshot_digest=base_snapshot_digest,
        )

    def _adapt_content(
        self, content: bytes, *, run_id: str, job_id: str, attempt_id: str,
        run_spec_digest: str, work_brief_digest: str, base_snapshot_digest: str,
    ) -> AdaptedWorkerResult:
        canonical_content = _canonical_backend_projection_bytes(content)
        result = parse_worker_result_bytes(
            canonical_content,
            expected_run_spec_digest=run_spec_digest,
            expected_attempt_id=attempt_id,
        )
        result_artifact = self.artifact_store.write(canonical_content)
        snapshot = capture_result_snapshot(self.root)
        context_request = None
        context_artifact = None
        if isinstance(result, ContextRequestedWorkerResult):
            expected_base = validate_sha256_digest(base_snapshot_digest)
            if snapshot.digest != expected_base:
                raise ContextRequestWithChanges(
                    f"result snapshot {snapshot.digest} differs from frozen base {expected_base}")
            context_request = ContextRequest(
                run_id=_nonempty(run_id, "run_id"),
                job_id=_nonempty(job_id, "job_id"),
                attempt_id=attempt_id,
                run_spec_digest=result.run_spec_digest,
                work_brief_digest=validate_sha256_digest(work_brief_digest),
                question=result.question,
                blocked_decision=result.blocked_decision,
                why_required=result.why_required,
                observed_result_digest=snapshot.digest,
            )
            context_artifact = self.artifact_store.write(context_request.canonical_bytes())
        return AdaptedWorkerResult(
            result, result_artifact, snapshot, context_request, context_artifact)


__all__ = [
    "AdaptedWorkerResult",
    "CompletedWorkerResult",
    "ContextRequest",
    "ContextResponse",
    "ContextResponseBindingMismatch",
    "ContextRequestedWorkerResult",
    "ContextRequestWithChanges",
    "RESULT_CONTROL_FILE",
    "RUNNER_COMPLETION_SCHEMA",
    "ResultSnapshot",
    "RunnerCompletionMarkerRefusal",
    "RunnerCompletionMarkerV2",
    "WorkerResultAdapter",
    "WorkerResultBindingMismatch",
    "WorkerResultError",
    "WorkerResultMissing",
    "WorkerResultSchemaRefusal",
    "capture_result_snapshot",
    "parse_context_response_bytes",
    "parse_runner_completion_marker_v2_bytes",
    "parse_worker_result_bytes",
    "revise_work_brief_for_response",
]
