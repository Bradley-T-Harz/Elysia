"""
Request-trace route module for the Elysia local API bridge.

This module owns:
- GET /request-trace/{request_id}

Its job is narrow:
- accept one request_id from the path
- ask request_trace_service for the safe live trace record
- shape that into a bounded response envelope
- return only UI-safe trace truth

It must not:
- mutate trace state
- manage trace phases
- call the runtime bridge
- expose raw logs, journals, hidden reasoning, or secret internals
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from app.api.request_trace_service import get_request_trace_record, list_request_trace_summaries
from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope

router = APIRouter(
    prefix="/request-trace",
    tags=["request-trace"],
)

API_VERSION = "1.0.0"
CONTRACT_VERSION = "phase1-ui-contract-1.0"
COMPACT_ROUTE_LIST_LIMIT = 10
COMPACT_ROUTE_STRING_LIMIT = 240

FILE_SUMMARY_KEYS = {
    "file_id",
    "file_name",
    "file_kind",
    "status",
    "summary",
    "parser_used",
    "chunks_created_count",
    "chunks_used_count",
    "memory_promotion_allowed",
    "outward_sharing_allowed",
    "trust_zone",
    "blocked_reason",
}
TOOL_LEDGER_KEYS = {
    "tool_key",
    "tool_label",
    "tool_kind",
    "state",
    "available",
    "used",
    "approval_required",
    "approval_state",
    "locality",
    "boundary_kind",
    "boundary_state",
    "worker_name",
    "operation",
    "summary",
    "input_count",
    "output_count",
    "mutated_files",
    "network_access_used",
    "private_context_sent",
    "shell_used",
    "git_mutation_used",
    "cloud_used",
    "session_id",
    "operation_id",
    "approval_id",
    "workspace_root_hash",
    "relative_paths",
    "source_hash",
    "plan_hash",
    "result_hash",
    "mutation_class",
    "backup_summary",
    "audit_persisted",
    "artifact_id",
    "model_id",
    "synthetic_media",
    "raw_content_logged",
    "runtime_seconds",
    "peak_gpu_memory_mib",
    "cancel_requested",
    "warnings",
    "errors",
}
ARTIFACT_SUMMARY_KEYS = {
    "artifact_id",
    "kind",
    "title",
    "summary",
    "request_id",
    "conversation_id",
    "project_id",
    "created_at_utc",
    "locality",
    "memory_posture",
    "memory_promotion",
    "private_context_sent",
    "preview_available",
    "detail_available",
    "producer_tool_kind",
    "producer_operation",
    "source_file_id",
    "source_file_name",
    "source_file_kind",
    "model_id",
    "mime_type",
    "output_sha256",
    "output_bytes",
    "synthetic_media",
    "warnings",
    "errors",
}

COMPACT_BOOL_KEYS = {
    "available",
    "used",
    "approval_required",
    "mutated_files",
    "network_access_used",
    "private_context_sent",
    "shell_used",
    "git_mutation_used",
    "cloud_used",
    "synthetic_media",
    "raw_content_logged",
    "cancel_requested",
    "memory_promotion_allowed",
    "outward_sharing_allowed",
    "memory_promotion",
    "preview_available",
    "detail_available",
    "synthetic_media",
}
COMPACT_COUNT_KEYS = {
    "input_count",
    "output_count",
    "chunks_created_count",
    "chunks_used_count",
}
COMPACT_LIST_KEYS = {"warnings", "errors", "relative_paths"}


def _new_request_id(prefix: str = "req") -> str:
    """
    Create a compact request identifier for route-envelope use.
    """
    return f"{prefix}_{uuid4().hex[:16]}"


def _clean_request_id(request_id: str) -> str:
    """
    Normalize one request_id path parameter and reject empty values.
    """
    normalized = str(request_id or "").strip()
    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="request_id path parameter must not be empty.",
        )

    return normalized


def _clean_optional_string(value: Any) -> str | None:
    """
    Normalize one optional value into stripped text or None.
    """
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _clean_compact_string(value: Any) -> str | None:
    text = _clean_optional_string(value)
    if text is None:
        return None

    if len(text) <= COMPACT_ROUTE_STRING_LIMIT:
        return text

    return f"{text[: COMPACT_ROUTE_STRING_LIMIT - 1].rstrip()}..."


def _clean_optional_bool(value: Any) -> bool | None:
    """
    Normalize one optional boolean-like value into bool or None.
    """
    if isinstance(value, bool):
        return value

    return None


def _clean_nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0

    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _clean_string_list(value: Any) -> list[str]:
    """
    Normalize one optional list into a compact list of strings.
    """
    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    for item in value:
        text = _clean_compact_string(item)
        if text:
            normalized.append(text)

        if len(normalized) >= COMPACT_ROUTE_LIST_LIMIT:
            break

    return normalized


def _clean_compact_dict_list(
    value: Any,
    allowed_keys: set[str],
    *,
    max_items: int = COMPACT_ROUTE_LIST_LIMIT,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        compact_item: dict[str, Any] = {}
        for key in allowed_keys:
            if key not in item:
                continue

            raw_value = item.get(key)
            if key in COMPACT_BOOL_KEYS:
                compact_item[key] = bool(raw_value) if isinstance(raw_value, bool) else False
            elif key in COMPACT_COUNT_KEYS:
                compact_item[key] = _clean_nonnegative_int(raw_value)
            elif key in COMPACT_LIST_KEYS:
                compact_item[key] = _clean_string_list(raw_value)
            elif isinstance(raw_value, (dict, list)):
                continue
            else:
                text = _clean_compact_string(raw_value)
                if text:
                    compact_item[key] = text

        if compact_item:
            normalized.append(compact_item)

        if len(normalized) >= max_items:
            break

    return normalized


def _clean_file_summaries(value: Any) -> list[dict[str, Any]]:
    return _clean_compact_dict_list(value, FILE_SUMMARY_KEYS)


def _clean_tool_entries(value: Any) -> list[dict[str, Any]]:
    return [
        item
        for item in _clean_compact_dict_list(value, TOOL_LEDGER_KEYS)
        if _clean_optional_string(item.get("tool_key"))
    ]


def _clean_artifact_summaries(value: Any) -> list[dict[str, Any]]:
    return _clean_compact_dict_list(value, ARTIFACT_SUMMARY_KEYS)


def _normalize_capability_state(value: Any) -> CapabilityState:
    """
    Normalize one value into CapabilityState.
    """
    normalized = _clean_optional_string(value)
    if normalized:
        lowered = normalized.lower()
        for candidate in CapabilityState:
            if lowered == candidate.value:
                return candidate

    return CapabilityState.UNKNOWN


def _normalize_locality_state(value: Any) -> LocalityState:
    """
    Normalize one value into LocalityState.
    """
    normalized = _clean_optional_string(value)
    if normalized:
        lowered = normalized.lower()
        for candidate in LocalityState:
            if lowered == candidate.value:
                return candidate

    return LocalityState.UNKNOWN


def _normalize_approval_state(value: Any) -> ApprovalState:
    """
    Normalize one value into ApprovalState.
    """
    normalized = _clean_optional_string(value)
    if normalized:
        lowered = normalized.lower()
        for candidate in ApprovalState:
            if lowered == candidate.value:
                return candidate

    return ApprovalState.UNKNOWN


def _looks_like_bridge_request_id(request_id: str) -> bool:
    """
    Heuristically decide whether a request_id looks like one generated by the bridge/client.

    This is not a security check. It only helps the polling route distinguish
    "possibly just not started yet" from "probably not a real request id".
    """
    if not request_id.startswith("req_"):
        return False

    suffix = request_id[4:]
    if len(suffix) < 8:
        return False

    return all(character.isalnum() for character in suffix)


def _base_empty_snapshot() -> dict[str, Any]:
    """
    Build the compact empty snapshot shape used by fallback payloads.
    """
    return {
        "route_used": None,
        "ui_surface": None,
        "selected_mode": None,
        "selected_role": None,
        "selected_runtime": None,
        "selected_model_runtime_tag": None,
        "locality_state": None,
        "approval_state": None,
        "approval_needed": None,
        "used_fallback": None,
        "mode_profile_key": None,
        "mode_profile_label": None,
        "mode_profile_used": False,
        "mode_profile_effects": [],
        "mode_profile_warnings": [],
        "authority_granted_by_mode": False,
        "memory_classes": [],
        "skill_name": None,
        "tool_name": None,
        "app_name": None,
        "worker_name": None,
        "execution_tool_kind": None,
        "execution_status": None,
        "execution_operation": None,
        "execution_summary": None,
        "research_ticket_id": None,
        "research_worker_name": None,
        "research_status": None,
        "research_query_count": 0,
        "research_queries_sent": [],
        "research_query_hashes": [],
        "blocked_query_preview": None,
        "evidence_packet_count": 0,
        "outward_boundary_state": None,
        "private_context_sent": False,
        "network_access_used": False,
        "page_fetch_used": False,
        "cloud_search_used": False,
        "cloud_model_used": False,
        "files_attached_count": 0,
        "files_attached": [],
        "files_used_count": 0,
        "file_chunks_used_count": 0,
        "file_parsers_used": [],
        "file_memory_promotion": False,
        "file_outward_sharing": False,
        "tools_available_count": 0,
        "tools_used_count": 0,
        "tools_available": [],
        "tools_used": [],
        "artifact_count": 0,
        "artifacts": [],
        "repo_context_status": None,
        "repo_context_file_count": 0,
        "repo_context_files": [],
        "patch_plan_status": None,
        "patch_plan_file_count": 0,
        "patch_plan_files": [],
        "patch_id": None,
        "patch_hash": None,
        "patch_diff_preview": None,
        "patch_preview_truncated": False,
        "rollback_note": None,
        "command_key": None,
        "command_argv": [],
        "command_exit_code": None,
        "command_duration_ms": 0,
        "command_output_preview": None,
        "command_output_truncated": False,
        "mutated_files": False,
        "shell_used": False,
        "git_mutation_used": False,
        "external_worker_used": False,
        "related_conversation_id": None,
        "related_project_id": None,
        "errors": [],
        "warnings": [],
    }


def _build_pending_startup_trace_payload(request_id: str) -> dict[str, Any]:
    """
    Build a polling-safe payload for a request_id that looks valid but whose
    trace record has not appeared yet.
    """
    return {
        "request_id": request_id,
        "request_status": "pending_startup",
        "current_phase": "waiting_for_trace_startup",
        "current_phase_label": "Waiting for trace startup",
        "current_phase_detail": (
            "This request_id looks valid, but no live trace record has appeared yet. "
            "The governed request may still be starting."
        ),
        "created_at_utc": None,
        "updated_at_utc": None,
        "completed_at_utc": None,
        "trace_entries": [],
        "snapshot": _base_empty_snapshot(),
    }


def _build_unknown_trace_payload(request_id: str) -> dict[str, Any]:
    """
    Build a polling-safe payload for a request_id that is not currently known
    and does not look like a likely active bridge request.
    """
    return {
        "request_id": request_id,
        "request_status": "unknown",
        "current_phase": "unknown_request_id",
        "current_phase_label": "Unknown request id",
        "current_phase_detail": "No live request trace is currently known for this request_id.",
        "created_at_utc": None,
        "updated_at_utc": None,
        "completed_at_utc": None,
        "trace_entries": [],
        "snapshot": _base_empty_snapshot(),
    }


def _sanitize_trace_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """
    Return one bounded safe trace entry for UI inspection.
    """
    return {
        "entry_id": _clean_optional_string(entry.get("entry_id")),
        "request_id": _clean_optional_string(entry.get("request_id")),
        "phase": _clean_optional_string(entry.get("phase")),
        "label": _clean_optional_string(entry.get("label")),
        "detail": _clean_optional_string(entry.get("detail")),
        "timestamp_utc": _clean_optional_string(entry.get("timestamp_utc")),
        "selected_mode": _clean_optional_string(entry.get("selected_mode")),
        "selected_role": _clean_optional_string(entry.get("selected_role")),
        "selected_runtime": _clean_optional_string(entry.get("selected_runtime")),
        "selected_model_runtime_tag": _clean_optional_string(
            entry.get("selected_model_runtime_tag")
        ),
        "locality_state": _clean_optional_string(entry.get("locality_state")),
        "approval_state": _clean_optional_string(entry.get("approval_state")),
        "used_fallback": _clean_optional_bool(entry.get("used_fallback")),
        "memory_classes": _clean_string_list(entry.get("memory_classes")),
        "skill_name": _clean_optional_string(entry.get("skill_name")),
        "tool_name": _clean_optional_string(entry.get("tool_name")),
        "app_name": _clean_optional_string(entry.get("app_name")),
        "worker_name": _clean_optional_string(entry.get("worker_name")),
        "execution_tool_kind": _clean_optional_string(
            entry.get("execution_tool_kind")
        ),
        "execution_status": _clean_optional_string(entry.get("execution_status")),
        "execution_operation": _clean_optional_string(
            entry.get("execution_operation")
        ),
        "execution_summary": _clean_optional_string(entry.get("execution_summary")),
    }


def _sanitize_trace_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    Return one bounded safe trace snapshot for UI inspection.
    """
    files_attached = _clean_file_summaries(snapshot.get("files_attached"))
    tools_available = _clean_tool_entries(snapshot.get("tools_available"))
    tools_used = _clean_tool_entries(snapshot.get("tools_used"))
    artifacts = _clean_artifact_summaries(snapshot.get("artifacts"))
    repo_context_files = _clean_string_list(snapshot.get("repo_context_files"))
    patch_plan_files = _clean_string_list(snapshot.get("patch_plan_files"))

    return {
        "route_used": _clean_optional_string(snapshot.get("route_used")),
        "ui_surface": _clean_optional_string(snapshot.get("ui_surface")),
        "selected_mode": _clean_optional_string(snapshot.get("selected_mode")),
        "selected_role": _clean_optional_string(snapshot.get("selected_role")),
        "selected_runtime": _clean_optional_string(snapshot.get("selected_runtime")),
        "selected_model_runtime_tag": _clean_optional_string(
            snapshot.get("selected_model_runtime_tag")
        ),
        "locality_state": _clean_optional_string(snapshot.get("locality_state")),
        "approval_state": _clean_optional_string(snapshot.get("approval_state")),
        "approval_needed": _clean_optional_bool(snapshot.get("approval_needed")),
        "used_fallback": _clean_optional_bool(snapshot.get("used_fallback")),
        "mode_profile_key": _clean_optional_string(snapshot.get("mode_profile_key")),
        "mode_profile_label": _clean_optional_string(snapshot.get("mode_profile_label")),
        "mode_profile_used": _clean_optional_bool(snapshot.get("mode_profile_used")) or False,
        "mode_profile_effects": _clean_string_list(snapshot.get("mode_profile_effects")),
        "mode_profile_warnings": _clean_string_list(snapshot.get("mode_profile_warnings")),
        "authority_granted_by_mode": False,
        "memory_classes": _clean_string_list(snapshot.get("memory_classes")),
        "skill_name": _clean_optional_string(snapshot.get("skill_name")),
        "tool_name": _clean_optional_string(snapshot.get("tool_name")),
        "app_name": _clean_optional_string(snapshot.get("app_name")),
        "worker_name": _clean_optional_string(snapshot.get("worker_name")),
        "execution_tool_kind": _clean_optional_string(
            snapshot.get("execution_tool_kind")
        ),
        "execution_status": _clean_optional_string(snapshot.get("execution_status")),
        "execution_operation": _clean_optional_string(
            snapshot.get("execution_operation")
        ),
        "execution_summary": _clean_optional_string(snapshot.get("execution_summary")),
        "research_ticket_id": _clean_optional_string(snapshot.get("research_ticket_id")),
        "research_worker_name": _clean_optional_string(snapshot.get("research_worker_name")),
        "research_status": _clean_optional_string(snapshot.get("research_status")),
        "research_query_count": _clean_nonnegative_int(snapshot.get("research_query_count")),
        "research_queries_sent": _clean_string_list(snapshot.get("research_queries_sent")),
        "research_query_hashes": _clean_string_list(snapshot.get("research_query_hashes")),
        "blocked_query_preview": _clean_optional_string(snapshot.get("blocked_query_preview")),
        "evidence_packet_count": _clean_nonnegative_int(snapshot.get("evidence_packet_count")),
        "outward_boundary_state": _clean_optional_string(snapshot.get("outward_boundary_state")),
        "private_context_sent": _clean_optional_bool(snapshot.get("private_context_sent")) or False,
        "network_access_used": _clean_optional_bool(snapshot.get("network_access_used")) or False,
        "page_fetch_used": _clean_optional_bool(snapshot.get("page_fetch_used")) or False,
        "cloud_search_used": _clean_optional_bool(snapshot.get("cloud_search_used")) or False,
        "cloud_model_used": _clean_optional_bool(snapshot.get("cloud_model_used")) or False,
        "reasoning_gear": _clean_optional_string(snapshot.get("reasoning_gear")),
        "governor_version": _clean_optional_string(snapshot.get("governor_version")),
        "effective_autonomy_level": (
            max(1, min(5, _clean_nonnegative_int(snapshot.get("effective_autonomy_level"))))
            if snapshot.get("effective_autonomy_level") is not None else None
        ),
        "verification_depth": _clean_optional_string(snapshot.get("verification_depth")),
        "governor_early_exit_eligible": _clean_optional_bool(
            snapshot.get("governor_early_exit_eligible")
        ) or False,
        "governor_escalations": _clean_string_list(snapshot.get("governor_escalations")),
        "model_role_hint": _clean_optional_string(snapshot.get("model_role_hint")),
        "compute_decision": _clean_optional_string(snapshot.get("compute_decision")),
        "selected_device": _clean_optional_string(snapshot.get("selected_device")),
        "files_attached_count": len(files_attached),
        "files_attached": files_attached,
        "files_used_count": _clean_nonnegative_int(snapshot.get("files_used_count")),
        "file_chunks_used_count": _clean_nonnegative_int(
            snapshot.get("file_chunks_used_count")
        ),
        "file_parsers_used": _clean_string_list(snapshot.get("file_parsers_used")),
        "file_memory_promotion": _clean_optional_bool(
            snapshot.get("file_memory_promotion")
        )
        or False,
        "file_outward_sharing": _clean_optional_bool(
            snapshot.get("file_outward_sharing")
        )
        or False,
        "tools_available_count": len(tools_available),
        "tools_used_count": len(tools_used),
        "tools_available": tools_available,
        "tools_used": tools_used,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "repo_context_status": _clean_optional_string(
            snapshot.get("repo_context_status")
        ),
        "repo_context_file_count": len(repo_context_files),
        "repo_context_files": repo_context_files,
        "patch_plan_status": _clean_optional_string(snapshot.get("patch_plan_status")),
        "patch_plan_file_count": len(patch_plan_files),
        "patch_plan_files": patch_plan_files,
        "patch_id": _clean_optional_string(snapshot.get("patch_id")),
        "patch_hash": _clean_optional_string(snapshot.get("patch_hash")),
        "patch_diff_preview": _clean_optional_string(
            snapshot.get("patch_diff_preview")
        ),
        "patch_preview_truncated": _clean_optional_bool(
            snapshot.get("patch_preview_truncated")
        )
        or False,
        "rollback_note": _clean_optional_string(snapshot.get("rollback_note")),
        "command_key": _clean_optional_string(snapshot.get("command_key")),
        "command_argv": _clean_string_list(snapshot.get("command_argv")),
        "command_exit_code": _clean_nonnegative_int(
            snapshot.get("command_exit_code")
        )
        if snapshot.get("command_exit_code") is not None
        else None,
        "command_duration_ms": _clean_nonnegative_int(
            snapshot.get("command_duration_ms")
        ),
        "command_output_preview": _clean_optional_string(
            snapshot.get("command_output_preview")
        ),
        "command_output_truncated": _clean_optional_bool(
            snapshot.get("command_output_truncated")
        )
        or False,
        "mutated_files": _clean_optional_bool(snapshot.get("mutated_files")) or False,
        "shell_used": _clean_optional_bool(snapshot.get("shell_used")) or False,
        "git_mutation_used": _clean_optional_bool(snapshot.get("git_mutation_used"))
        or False,
        "external_worker_used": _clean_optional_bool(
            snapshot.get("external_worker_used")
        )
        or False,
        "related_conversation_id": _clean_optional_string(
            snapshot.get("related_conversation_id")
        ),
        "related_project_id": _clean_optional_string(snapshot.get("related_project_id")),
        "errors": _clean_string_list(snapshot.get("errors")),
        "warnings": _clean_string_list(snapshot.get("warnings")),
    }


def _sanitize_trace_payload(request_id: str, record: dict[str, Any]) -> dict[str, Any]:
    """
    Return one bounded safe trace payload from a trace service record.
    """
    snapshot = record.get("snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}

    trace_entries = record.get("trace_entries")
    if not isinstance(trace_entries, list):
        trace_entries = []

    sanitized_entries = [
        _sanitize_trace_entry(entry)
        for entry in trace_entries
        if isinstance(entry, dict)
    ]

    request_status = _clean_optional_string(record.get("request_status")) or "unknown"
    current_phase = _clean_optional_string(record.get("current_phase"))
    current_phase_label = _clean_optional_string(record.get("current_phase_label"))
    current_phase_detail = _clean_optional_string(record.get("current_phase_detail"))

    if request_status == "running" and len(sanitized_entries) == 0:
        current_phase = current_phase or "trace_record_created"
        current_phase_label = current_phase_label or "Trace record created"
        current_phase_detail = current_phase_detail or (
            "A live trace record exists for this request, but no phase entries have been appended yet."
        )

    return {
        "request_id": _clean_optional_string(record.get("request_id")) or request_id,
        "request_status": request_status,
        "current_phase": current_phase,
        "current_phase_label": current_phase_label,
        "current_phase_detail": current_phase_detail,
        "created_at_utc": _clean_optional_string(record.get("created_at_utc")),
        "updated_at_utc": _clean_optional_string(record.get("updated_at_utc")),
        "completed_at_utc": _clean_optional_string(record.get("completed_at_utc")),
        "trace_entries": sanitized_entries,
        "snapshot": _sanitize_trace_snapshot(snapshot),
    }


def _build_fallback_trace_payload(request_id: str) -> dict[str, Any]:
    """
    Return the best polling-safe fallback payload when no trace record exists yet.
    """
    if _looks_like_bridge_request_id(request_id):
        return _build_pending_startup_trace_payload(request_id)

    return _build_unknown_trace_payload(request_id)


def _determine_envelope_status(request_status: str) -> EnvelopeStatus:
    """
    Map trace request_status into the route envelope status.
    """
    if request_status == "degraded":
        return EnvelopeStatus.DEGRADED

    if request_status == "blocked":
        return EnvelopeStatus.BLOCKED

    if request_status == "error":
        return EnvelopeStatus.ERROR

    return EnvelopeStatus.OK


def _determine_capability_state(request_status: str) -> CapabilityState:
    """
    Map trace request_status into broad capability truth for the route envelope.
    """
    if request_status == "degraded":
        return CapabilityState.DEGRADED

    if request_status in {"pending_startup", "running", "completed", "blocked"}:
        return CapabilityState.LIVE

    return CapabilityState.UNKNOWN


def _determine_route_warnings(request_status: str) -> list[str]:
    """
    Return modest route-level warnings for polling-safe fallback states.
    """
    if request_status == "pending_startup":
        return [
            "Live trace record has not appeared yet. Polling may still be correct while the governed request starts.",
        ]

    if request_status == "unknown":
        return [
            "No live request trace is currently known for this request_id.",
        ]

    if request_status == "running_no_entries":
        return [
            "A live trace record exists, but no phase entries have been appended yet.",
        ]

    return []


@router.get("")
async def get_recent_request_traces(
    project_id: str | None = Query(default=None),
    conversation_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Return bounded in-memory request summaries, including coding operations."""
    summaries = list_request_trace_summaries(
        project_id=project_id,
        conversation_id=conversation_id,
        limit=limit,
    )
    return build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id(),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="request_trace_list",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=["Recent request history is in-memory continuity truth, not a durable raw-log browser."],
        errors=[],
        trace_summary=TraceSummary(
            route_used="request_trace.get_recent_request_traces",
            log_written=False,
            journal_written=False,
        ),
        data={"request_traces": summaries, "count": len(summaries)},
    ).to_payload()


@router.get("/{request_id}")
async def get_request_trace(request_id: str) -> dict[str, Any]:
    """
    Return one bounded live request trace payload.

    This route is polling-safe: if a trace is not yet known, it returns a stable
    fallback payload rather than a hard 404.
    """
    normalized_request_id = _clean_request_id(request_id)
    envelope_request_id = _new_request_id()

    try:
        trace_record = get_request_trace_record(normalized_request_id)
        if trace_record is None:
            payload = _build_fallback_trace_payload(normalized_request_id)
        else:
            payload = _sanitize_trace_payload(normalized_request_id, trace_record)

        snapshot = payload.get("snapshot", {})
        if not isinstance(snapshot, dict):
            snapshot = {}

        request_status = _clean_optional_string(payload.get("request_status")) or "unknown"

        derived_warning_state = request_status
        if request_status == "running" and not payload.get("trace_entries"):
            derived_warning_state = "running_no_entries"

        trace_summary = TraceSummary(
            route_used="request_trace.get_request_trace",
            selected_role=_clean_optional_string(snapshot.get("selected_role")),
            selected_runtime=_clean_optional_string(snapshot.get("selected_runtime")),
            selected_model_runtime_tag=_clean_optional_string(
                snapshot.get("selected_model_runtime_tag")
            ),
            used_fallback=bool(snapshot.get("used_fallback"))
            if snapshot.get("used_fallback") is not None
            else False,
            log_written=False,
            journal_written=False,
        )

        envelope = build_response_envelope(
            status=_determine_envelope_status(request_status),
            request_id=envelope_request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="request_trace",
            capability_state=_determine_capability_state(request_status),
            locality=_normalize_locality_state(snapshot.get("locality_state")),
            approval_state=_normalize_approval_state(snapshot.get("approval_state")),
            warnings=_determine_route_warnings(derived_warning_state),
            errors=[],
            trace_summary=trace_summary,
            data=payload,
        )
        return envelope.to_payload()

    except HTTPException:
        raise
    except Exception as exc:
        envelope = build_response_envelope(
            status=EnvelopeStatus.ERROR,
            request_id=envelope_request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="request_trace",
            capability_state=CapabilityState.UNKNOWN,
            locality=LocalityState.UNKNOWN,
            approval_state=ApprovalState.UNKNOWN,
            warnings=[],
            errors=[f"Request trace lookup failed unexpectedly: {exc}"],
            trace_summary=TraceSummary(
                route_used="request_trace.get_request_trace",
                log_written=False,
                journal_written=False,
            ),
            data={},
        )
        return envelope.to_payload()


__all__ = ("router",)
