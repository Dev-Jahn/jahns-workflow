"""Codex rollout-log adapter for the canonical trace rows consumed by improve.py.

Codex documents its transcript path to hooks but not the JSONL schema. This parser is therefore
versioned independently from the Claude parser, reports unknown records, and only treats explicit
exit/status fields as failure evidence.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from cclog import RESULT_TEXT_CAP, compact_json, stable_id, tool_category, truncate_text

PARSER_VERSION = "waystone-codex-trace-1"
SKIP_DIRS = {".git", "__pycache__"}

_ROLLOUT_ID_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$"
)
_PATCH_PATH_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)
_DIRECT_TRACE_RE = re.compile(
    r"(?:^|[;&|]\s*)(?:\S*/)?waystone(?:-codex)?\s+improve\s+trace(?:\s|$)"
)
_WRAPPED_TRACE_RE = re.compile(
    r"cmd\s*:\s*['\"][^'\"]*(?:waystone-codex|bin/waystone)[^'\"]*"
    r"\s+improve\s+trace(?:\s|$)"
)


def rollout_id(path: Path) -> str | None:
    match = _ROLLOUT_ID_RE.search(path.name)
    return match.group(1) if match else None


def discover(sources: list[Path]) -> list[tuple[Path, tuple[str, ...]]]:
    found: list[tuple[Path, tuple[str, ...]]] = []
    for source in sources:
        if not source.is_dir():
            continue
        for path in sorted(source.rglob("*.jsonl")):
            rel = path.relative_to(source).parts
            if any(part in SKIP_DIRS for part in rel):
                continue
            found.append((path, rel))
    return found


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        item.get("text", "") for item in content
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    )


def _decode_arguments(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _explicit_exit(value: Any) -> bool | None:
    """Return explicit failure state, never infer it from human-readable output prose."""
    if isinstance(value, dict):
        if type(value.get("is_error")) is bool:
            return value["is_error"]
        for key in ("exit_code", "returncode", "return_code"):
            if type(value.get(key)) is int:
                return value[key] != 0
        status = value.get("status")
        if status in ("failed", "error"):
            return True
        if status in ("completed", "success", "succeeded"):
            return False
        for child in value.values():
            found = _explicit_exit(child)
            if found is not None:
                return found
        return None
    if isinstance(value, list):
        for child in value:
            found = _explicit_exit(child)
            if found is not None:
                return found
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped[0] not in "[{":
            return None
        try:
            return _explicit_exit(json.loads(stripped))
        except json.JSONDecodeError:
            return None
    return None


def _agent_result_fields(value: Any) -> dict[str, Any]:
    found = {"agent_id": None, "resolved_model": None, "status": None, "is_async": None}

    def visit(item: Any) -> None:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped[:1] in "[{":
                try:
                    visit(json.loads(stripped))
                except json.JSONDecodeError:
                    pass
            return
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if not isinstance(item, dict):
            return
        aliases = {
            "agent_id": ("agent_id", "agentId"),
            "resolved_model": ("resolved_model", "resolvedModel"),
            "status": ("status",),
            "is_async": ("is_async", "isAsync"),
        }
        for target, keys in aliases.items():
            for key in keys:
                if key in item and found[target] is None:
                    found[target] = item[key]
        for child in item.values():
            visit(child)

    visit(value)
    return found


def _canonical_tool(payload: dict) -> tuple[str, dict, dict]:
    raw_name = payload.get("name") if isinstance(payload.get("name"), str) else "unknown"
    namespace = payload.get("namespace") if isinstance(payload.get("namespace"), str) else None
    args = _decode_arguments(payload.get("arguments"))
    custom_input = payload.get("input") if isinstance(payload.get("input"), str) else None
    full_name = f"{namespace}.{raw_name}" if namespace else raw_name

    command = description = prompt = file_path = subagent_type = model_requested = None
    canonical = full_name
    if raw_name == "exec" and custom_input is not None:
        if "tools.apply_patch(" in custom_input:
            canonical = "Write"
            command = custom_input
            match = _PATCH_PATH_RE.search(command)
            file_path = match.group(1).strip() if match else None
        elif "tools.web__run(" in custom_input:
            canonical = "WebSearch"
        elif "tools.update_plan(" in custom_input:
            canonical = "TodoWrite"
        elif "tools.exec_command(" in custom_input:
            canonical = "Bash"
            command = custom_input
        else:
            canonical = "functions.exec"
    elif raw_name == "exec_command" or full_name == "functions.exec_command":
        canonical = "Bash"
        command = args.get("cmd") if isinstance(args.get("cmd"), str) else None
    elif raw_name == "write_stdin":
        canonical = "BashOutput"
        command = args.get("chars") if isinstance(args.get("chars"), str) else None
    elif raw_name == "apply_patch":
        canonical = "Write"
        command = custom_input or (args.get("command") if isinstance(args.get("command"), str) else None)
        if command:
            match = _PATCH_PATH_RE.search(command)
            file_path = match.group(1).strip() if match else None
    elif raw_name in ("spawn_agent", "create_agent") or full_name.endswith(".spawn_agent"):
        canonical = "Task"
        prompt = args.get("message") if isinstance(args.get("message"), str) else None
        description = prompt
        subagent_type = args.get("task_name") if isinstance(args.get("task_name"), str) else None
        model_requested = args.get("model") if isinstance(args.get("model"), str) else None
    elif raw_name in ("update_plan",):
        canonical = "TodoWrite"
    elif raw_name in ("web__run", "web_search") or (namespace and "web" in namespace):
        canonical = "WebSearch"
    elif raw_name.startswith("mcp__"):
        canonical = raw_name

    tool_input = args or ({"command": custom_input} if custom_input is not None else {})
    fields = {
        "command": command,
        "description": description,
        "prompt": prompt,
        "file_path": file_path,
        "subagent_type": subagent_type,
        "model_requested": model_requested,
    }
    return canonical, tool_input, fields


def _trace_invocation(payload: dict) -> bool:
    if payload.get("type") == "function_call":
        args = _decode_arguments(payload.get("arguments"))
        command = args.get("cmd")
        return isinstance(command, str) and bool(_DIRECT_TRACE_RE.search(command))
    if payload.get("type") == "custom_tool_call" and isinstance(payload.get("input"), str):
        return bool(_WRAPPED_TRACE_RE.search(payload["input"]))
    return False


def self_session_anchor(path: Path) -> tuple[int | None, int]:
    anchor = None
    total = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for line_no, raw in enumerate(stream, start=1):
                total = line_no
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if (isinstance(record, dict) and record.get("type") == "response_item"
                        and isinstance(record.get("payload"), dict)
                        and _trace_invocation(record["payload"])):
                    anchor = line_no
    except OSError:
        return None, 0
    return anchor, total - anchor + 1 if anchor is not None else 0


def parse_transcript_file(path: Path, *, file_id: str,
                          stop_before_line: int | None = None) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    expected_id = rollout_id(path)
    session_id = expected_id
    project = agent_id = parent_id = agent_path = agent_nickname = None
    cwd = model = cli_version = None
    session_kind = "main"
    turn_index = 0
    partial_tail_lines = 0
    latest_usage: tuple[int, str | None, dict] | None = None

    def event(line_no: int, timestamp: str | None, **fields) -> dict[str, Any]:
        event_id = stable_id("evt", file_id, str(line_no))
        return {
            "event_id": event_id, "file_id": file_id, "line_no": line_no,
            "ordinal": line_no, "server": None, "project": project,
            "session_id": session_id, "agent_id": agent_id, "workflow_id": None,
            "parse_status": "ok", "raw_type": fields.pop("raw_type", None),
            "actor": fields.pop("actor", "system"),
            "event_type": fields.pop("event_type", "unknown_raw"),
            "event_subtype": fields.pop("event_subtype", None),
            "text": fields.pop("text", None), "uuid": None, "parent_uuid": None,
            "timestamp": timestamp, "is_meta": False,
            "is_sidechain": session_kind != "main", "cwd": cwd, "git_branch": None,
            "request_id": None, "message_id": fields.pop("message_id", None),
            "model_raw": model, "model_norm": model, "stop_reason": None,
            "content_types": fields.pop("content_types", None), "turn_index": turn_index,
            "extras_json": compact_json(fields.pop("extras", None)),
            "usage_json": compact_json(fields.pop("usage", None)),
        } | fields

    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line_no, raw in enumerate(stream, start=1):
            if stop_before_line is not None and line_no >= stop_before_line:
                break
            had_newline = raw.endswith("\n")
            try:
                record = json.loads(raw)
                if not isinstance(record, dict):
                    raise ValueError("record is not an object")
            except (json.JSONDecodeError, ValueError) as exc:
                if not had_newline:
                    partial_tail_lines += 1
                    continue
                row = event(
                    line_no, None, raw_type="parse_error", event_type="unknown_raw",
                    event_subtype="parse_error", parse_status=f"error:{exc}"[:200],
                )
                events.append(row)
                continue

            record_type = record.get("type")
            payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
            timestamp = record.get("timestamp") if isinstance(record.get("timestamp"), str) else None

            if record_type == "session_meta":
                candidate = payload.get("id")
                if candidate == expected_id or (expected_id is None and session_id is None):
                    session_id = candidate if isinstance(candidate, str) else session_id
                    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else cwd
                    project = Path(cwd).name if cwd else project
                    cli_version = (payload.get("cli_version")
                                   if isinstance(payload.get("cli_version"), str) else cli_version)
                    parent_id = (payload.get("parent_thread_id")
                                 if isinstance(payload.get("parent_thread_id"), str) else None)
                    agent_path = payload.get("agent_path") if isinstance(payload.get("agent_path"), str) else None
                    agent_nickname = (payload.get("agent_nickname")
                                      if isinstance(payload.get("agent_nickname"), str) else None)
                    if parent_id or payload.get("thread_source") == "subagent":
                        session_kind = "subagent"
                        agent_id = session_id
                events.append(event(
                    line_no, timestamp, raw_type="session_meta", event_type="session_state",
                    event_subtype="session_meta", extras={"cli_version": cli_version},
                ))
                continue

            if record_type == "turn_context":
                turn_index += 1
                cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else cwd
                model = payload.get("model") if isinstance(payload.get("model"), str) else model
                events.append(event(
                    line_no, timestamp, raw_type="turn_context", event_type="session_state",
                    event_subtype="turn_context",
                ))
                continue

            if record_type == "response_item":
                item_type = payload.get("type")
                if item_type == "message":
                    role = payload.get("role")
                    text = _content_text(payload.get("content"))
                    message_id = payload.get("id") if isinstance(payload.get("id"), str) else None
                    if role == "user":
                        events.append(event(
                            line_no, timestamp, raw_type="response_item", actor="user",
                            event_type="user_instruction", event_subtype="natural_language",
                            text=truncate_text(text or None, 32_768)[0], message_id=message_id,
                        ))
                    elif role == "assistant":
                        events.append(event(
                            line_no, timestamp, raw_type="response_item", actor="assistant",
                            event_type="assistant_fragment", event_subtype="text",
                            text=truncate_text(text or None, 32_768)[0], message_id=message_id,
                            content_types="text",
                        ))
                    else:
                        events.append(event(
                            line_no, timestamp, raw_type="response_item", actor="harness",
                            event_type="context_injection", event_subtype=str(role or "message"),
                        ))
                    continue

                if item_type == "reasoning":
                    events.append(event(
                        line_no, timestamp, raw_type="response_item", actor="assistant",
                        event_type="assistant_fragment", event_subtype="thinking_marker",
                        message_id=payload.get("id"), content_types="thinking_marker",
                    ))
                    continue

                if item_type in ("function_call", "custom_tool_call"):
                    call_id = payload.get("call_id") or payload.get("id")
                    row = event(
                        line_no, timestamp, raw_type="response_item", actor="assistant",
                        event_type="assistant_fragment", event_subtype="tool_use",
                        message_id=str(call_id) if call_id else None, content_types="tool_use",
                    )
                    events.append(row)
                    canonical, tool_input, fields = _canonical_tool(payload)
                    prompt = fields.pop("prompt")
                    tool_calls.append({
                        "tool_call_id": call_id, "event_id": row["event_id"], "file_id": file_id,
                        "server": None, "project": project, "session_id": session_id,
                        "agent_id": agent_id, "workflow_id": None, "ordinal": line_no,
                        "timestamp": timestamp, "turn_index": turn_index,
                        "is_sidechain": session_kind != "main", "message_id": row["message_id"],
                        "model_norm": model, "tool_name_raw": canonical,
                        "tool_category": tool_category(canonical, tool_input),
                        "command": fields["command"], "description": fields["description"],
                        "subagent_type": fields["subagent_type"],
                        "model_requested": fields["model_requested"],
                        "prompt_head": truncate_text(prompt, 2000)[0] if prompt else None,
                        "file_path": fields["file_path"], "input_json": compact_json(tool_input, 8192),
                    })
                    continue

                if item_type in ("function_call_output", "custom_tool_call_output"):
                    call_id = payload.get("call_id")
                    output = payload.get("output")
                    text = _content_text(output) if isinstance(output, list) else (output or "")
                    text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
                    text_trunc, text_len = truncate_text(text or None, RESULT_TEXT_CAP)
                    row = event(
                        line_no, timestamp, raw_type="response_item", actor="tool",
                        event_type="tool_result", event_subtype="output",
                        text=truncate_text(text or None, 32_768)[0],
                    )
                    events.append(row)
                    agent_fields = _agent_result_fields(output)
                    tool_results.append({
                        "tool_use_id": call_id, "event_id": row["event_id"], "file_id": file_id,
                        "server": None, "project": project, "session_id": session_id,
                        "agent_id": agent_id, "workflow_id": None, "ordinal": line_no,
                        "timestamp": timestamp, "turn_index": turn_index,
                        "is_sidechain": session_kind != "main", "is_error": _explicit_exit(output),
                        "interrupted": None, "is_image": None, "content_text": text_trunc,
                        "content_len": text_len, "content_bytes": len(text.encode("utf-8")),
                        "stdout_len": None, "stderr_len": None, "stderr_head": None,
                        "source_tool_assistant_uuid": None,
                        "tur_agent_id": agent_fields["agent_id"],
                        "tur_resolved_model": agent_fields["resolved_model"],
                        "tur_status": agent_fields["status"],
                        "tur_is_async": agent_fields["is_async"],
                    })
                    continue

                events.append(event(
                    line_no, timestamp, raw_type="response_item", event_type="unknown_raw",
                    event_subtype=f"response_item:{item_type or 'unknown'}",
                ))
                continue

            if record_type == "event_msg":
                subtype = payload.get("type")
                if subtype == "token_count" and isinstance(payload.get("info"), dict):
                    usage = payload["info"].get("total_token_usage")
                    if isinstance(usage, dict):
                        latest_usage = (line_no, timestamp, {
                            "input_tokens": usage.get("input_tokens"),
                            "output_tokens": usage.get("output_tokens"),
                            "cache_read_input_tokens": usage.get("cached_input_tokens"),
                            "cache_creation_input_tokens": 0,
                        })
                    events.append(event(
                        line_no, timestamp, raw_type="event_msg", event_type="system_event",
                        event_subtype="token_count",
                    ))
                else:
                    events.append(event(
                        line_no, timestamp, raw_type="event_msg", event_type="system_event",
                        event_subtype=str(subtype or "unknown"),
                    ))
                continue

            if record_type in ("compacted", "world_state", "inter_agent_communication_metadata"):
                events.append(event(
                    line_no, timestamp, raw_type=str(record_type), event_type="session_state",
                    event_subtype=str(record_type),
                ))
                continue

            events.append(event(
                line_no, timestamp, raw_type=str(record_type) if record_type else None,
                event_type="unknown_raw", event_subtype=str(record_type or "no_type"),
            ))

    if latest_usage is not None:
        usage_line, usage_timestamp, usage = latest_usage
        usage_event = event(
            usage_line, usage_timestamp, raw_type="event_msg", actor="assistant",
            event_type="assistant_fragment", event_subtype="usage",
            message_id="usage:total", content_types="usage", usage=usage,
        )
        usage_event["event_id"] = stable_id("evt", file_id, str(usage_line), "usage-total")
        events.append(usage_event)

    scope = {"project": project, "session_id": session_id, "agent_id": agent_id,
             "workflow_id": None}
    agent_meta = None
    if session_kind == "subagent":
        agent_meta = {"agentType": "codex-subagent", "description": agent_path,
                      "spawnDepth": None, "nickname": agent_nickname,
                      "parentSessionId": parent_id}
    return {
        "events": events, "tool_calls": tool_calls, "tool_results": tool_results,
        "replayed_skipped": 0, "partial_tail_lines": partial_tail_lines,
        "scope": scope, "session_kind": session_kind, "agent_meta": agent_meta,
        "parser_version": PARSER_VERSION,
    }
