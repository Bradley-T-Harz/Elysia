"""
Request-summary and trace-inspection service organ for the Elysia local API bridge.

This module currently serves:
- GET /requests/{request_id}/summary

It now also owns a narrow in-memory request trace registry for live request
activity inspection.

Its job is still narrow:
- accept compact request-summary lookups
- find whatever governed request truth is currently available
- shape that into RequestSummaryData
- wrap it in the standard response envelope
- return structured dict payloads
- maintain a compact in-memory trace registry for request activity
- expose safe helper functions for starting, appending, updating, finalizing,
  fetching, and pruning live request traces

It must not:
- dump raw runtime logs
- dump raw journals
- expose secrets or raw internals
- fabricate a mature request database if one does not exist yet
- become a second approval engine
- become a general-purpose logging service
- become a second runtime
"""

from __future__ import annotations

import importlib
import logging
import threading
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from app.ids import new_id

from app.api.schemas.approval import ApprovalResolutionStatus
from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.api.schemas.requests import (
    RequestSummaryData,
    RequestSummaryLookup,
    RequestSummaryState,
)

LOGGER = logging.getLogger(__name__)

API_VERSION = "1.0.0"
CONTRACT_VERSION = "phase1-ui-contract-1.0"

_TRACE_STATUS_RUNNING = "running"
_TRACE_STATUS_COMPLETED = "completed"
_TRACE_STATUS_BLOCKED = "blocked"
_TRACE_STATUS_DEGRADED = "degraded"
_TRACE_STATUS_ERROR = "error"
_TRACE_STATUS_UNKNOWN = "unknown"

_TERMINAL_TRACE_STATUSES = {
    _TRACE_STATUS_COMPLETED,
    _TRACE_STATUS_BLOCKED,
    _TRACE_STATUS_DEGRADED,
    _TRACE_STATUS_ERROR,
}

_REQUEST_TRACE_LOCK = threading.RLock()
_REQUEST_TRACE_REGISTRY: dict[str, dict[str, Any]] = {}

_COMPACT_TRACE_LIST_LIMIT = 10
_COMPACT_TRACE_STRING_LIMIT = 240

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
    "warnings",
    "errors",
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
    "archive_type",
    "archive_hash",
    "manifest_hash",
    "member_count",
    "risk_total",
    "selected_member_count",
    "sandbox_hash",
    "extracted_file_count",
    "extracted_bytes",
    "blocked_member_count",
    "skipped_member_count",
    "policy_version",
    "sandbox_files_written",
    "project_files_mutated",
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

_COMPACT_BOOL_KEYS = {
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
    "memory_promotion_allowed",
    "outward_sharing_allowed",
    "memory_promotion",
    "preview_available",
    "detail_available",
    "synthetic_media",
    "audit_persisted",
    "cancel_requested",
    "sandbox_files_written",
    "project_files_mutated",
}
_COMPACT_COUNT_KEYS = {
    "input_count",
    "output_count",
    "chunks_created_count",
    "chunks_used_count",
    "member_count",
    "risk_total",
    "selected_member_count",
    "extracted_file_count",
    "extracted_bytes",
    "blocked_member_count",
    "skipped_member_count",
}
_COMPACT_LIST_KEYS = {"warnings", "errors", "relative_paths"}


def _new_request_id(prefix: str = "req") -> str:
    """
    Create a compact request identifier for envelope use.
    """
    return new_id(prefix)


def _utc_now_iso() -> str:
    """
    Return a compact UTC timestamp string with trailing Z.
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_string(value: Any, default: str = "") -> str:
    """
    Normalize one value into a clean string.
    """
    text = str(value or "").strip()
    return text if text else default


def _coerce_compact_string(value: Any, default: str = "") -> str:
    """
    Normalize a value into short UI-safe text for compact ledger summaries.
    """
    text = _coerce_string(value, default)
    if len(text) <= _COMPACT_TRACE_STRING_LIMIT:
        return text

    return f"{text[: _COMPACT_TRACE_STRING_LIMIT - 1].rstrip()}..."


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """
    Coerce a value into a boolean with light string handling.
    """
    if isinstance(value, bool):
        return value

    if value is None:
        return default

    if isinstance(value, str):
        lowered = value.strip().lower()

        if lowered in {"true", "1", "yes", "on"}:
            return True

        if lowered in {"false", "0", "no", "off"}:
            return False

    return bool(value)


def _coerce_nonnegative_int(value: Any) -> int:
    """
    Normalize one count-like value into a non-negative integer.
    """
    if isinstance(value, bool):
        return 0

    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _coerce_string_list(value: Any) -> list[str]:
    """
    Normalize a value into a compact list of strings.
    """
    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    for item in value:
        compact = _coerce_string(item, "")
        if compact:
            normalized.append(compact)

    return normalized


def _coerce_compact_string_list(value: Any, *, max_items: int = 10) -> list[str]:
    """
    Normalize a value into a short, bounded list of compact strings.
    """
    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    for item in value:
        compact = _coerce_compact_string(item, "")
        if compact:
            normalized.append(compact)

        if len(normalized) >= max_items:
            break

    return normalized


def _coerce_compact_dict_list(
    value: Any,
    allowed_keys: set[str],
    *,
    max_items: int = _COMPACT_TRACE_LIST_LIMIT,
) -> list[dict[str, Any]]:
    """
    Keep only whitelisted scalar fields from a compact list of dict summaries.
    """
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
            if key in _COMPACT_BOOL_KEYS:
                compact_item[key] = _coerce_bool(raw_value, False)
            elif key in _COMPACT_COUNT_KEYS:
                compact_item[key] = _coerce_nonnegative_int(raw_value)
            elif key in _COMPACT_LIST_KEYS:
                compact_item[key] = _coerce_compact_string_list(raw_value)
            elif isinstance(raw_value, (dict, list)):
                continue
            else:
                compact_text = _coerce_compact_string(raw_value, "")
                if compact_text:
                    compact_item[key] = compact_text

        if compact_item:
            normalized.append(compact_item)

        if len(normalized) >= max_items:
            break

    return normalized


def _coerce_file_summary_list(value: Any) -> list[dict[str, Any]]:
    return _coerce_compact_dict_list(value, FILE_SUMMARY_KEYS)


def _coerce_tool_ledger_list(value: Any) -> list[dict[str, Any]]:
    return [
        item
        for item in _coerce_compact_dict_list(value, TOOL_LEDGER_KEYS)
        if _coerce_string(item.get("tool_key"), "")
    ]


def _coerce_artifact_summary_list(value: Any) -> list[dict[str, Any]]:
    return _coerce_compact_dict_list(value, ARTIFACT_SUMMARY_KEYS)


def _import_optional(module_path: str) -> tuple[Any | None, str | None]:
    """
    Attempt to import one module without throwing.
    """
    try:
        return importlib.import_module(module_path), None
    except Exception as exc:
        return None, str(exc)


def _normalize_approval_state(value: Any) -> ApprovalState:
    """
    Normalize a value into the shared ApprovalState enum.
    """
    normalized = _coerce_string(value, "").lower()

    for candidate in ApprovalState:
        if normalized == candidate.value:
            return candidate

    return ApprovalState.UNKNOWN


def _normalize_locality_state(value: Any) -> LocalityState:
    """
    Normalize a value into the shared LocalityState enum.
    """
    normalized = _coerce_string(value, "").lower()

    for candidate in LocalityState:
        if normalized == candidate.value:
            return candidate

    return LocalityState.UNKNOWN


def _normalize_request_state(value: Any) -> RequestSummaryState:
    """
    Normalize a value into the request-summary request-state enum.
    """
    normalized = _coerce_string(value, "").lower()

    for candidate in RequestSummaryState:
        if normalized == candidate.value:
            return candidate

    return RequestSummaryState.UNKNOWN


def _normalize_trace_status(value: Any) -> str:
    """
    Normalize one request-trace status string.
    """
    normalized = _coerce_string(value, "").lower()

    if normalized in {
        _TRACE_STATUS_RUNNING,
        _TRACE_STATUS_COMPLETED,
        _TRACE_STATUS_BLOCKED,
        _TRACE_STATUS_DEGRADED,
        _TRACE_STATUS_ERROR,
    }:
        return normalized

    return _TRACE_STATUS_UNKNOWN


def _trace_status_to_request_state(trace_status: str) -> RequestSummaryState:
    """
    Map live trace status into the shared request-summary state family.
    """
    if trace_status == _TRACE_STATUS_RUNNING:
        return RequestSummaryState.PENDING

    if trace_status == _TRACE_STATUS_COMPLETED:
        return RequestSummaryState.COMPLETED

    if trace_status == _TRACE_STATUS_BLOCKED:
        return RequestSummaryState.BLOCKED

    if trace_status == _TRACE_STATUS_DEGRADED:
        return RequestSummaryState.COMPLETED

    return RequestSummaryState.UNKNOWN


def _trace_status_to_capability_state(trace_status: str) -> CapabilityState:
    """
    Map live trace status into broad capability truth.
    """
    if trace_status in {_TRACE_STATUS_RUNNING, _TRACE_STATUS_COMPLETED, _TRACE_STATUS_BLOCKED}:
        return CapabilityState.LIVE

    if trace_status == _TRACE_STATUS_DEGRADED:
        return CapabilityState.DEGRADED

    return CapabilityState.UNKNOWN


def _approval_state_from_request_state(
    request_state: RequestSummaryState,
) -> ApprovalState:
    """
    Map request state into the broad shared approval posture.
    """
    if request_state == RequestSummaryState.PENDING:
        return ApprovalState.NEEDED

    if request_state == RequestSummaryState.APPROVED:
        return ApprovalState.APPROVED

    if request_state == RequestSummaryState.DENIED:
        return ApprovalState.DENIED

    return ApprovalState.UNKNOWN


def _summary_text_for_request_state(
    request_state: RequestSummaryState,
    request_type: str | None,
) -> str:
    """
    Build compact summary text from request state and request type.
    """
    compact_type = request_type or "governed request"

    if request_state == RequestSummaryState.PENDING:
        return f"Pending {compact_type} awaiting a final governed outcome."

    if request_state == RequestSummaryState.APPROVED:
        return f"{compact_type.capitalize()} was approved and may proceed to its next governed step."

    if request_state == RequestSummaryState.DENIED:
        return f"{compact_type.capitalize()} was denied and remains blocked."

    if request_state == RequestSummaryState.CANCELLED:
        return f"{compact_type.capitalize()} was explicitly cancelled."

    if request_state == RequestSummaryState.COMPLETED:
        return f"{compact_type.capitalize()} completed its current governed path."

    if request_state == RequestSummaryState.BLOCKED:
        return f"{compact_type.capitalize()} remains blocked by current policy, boundary, or approval posture."

    if request_state == RequestSummaryState.EXPIRED:
        return f"{compact_type.capitalize()} is no longer actionable because it has expired."

    return f"{compact_type.capitalize()} exists, but its current state could not yet be confirmed."


def _base_trace_snapshot() -> dict[str, Any]:
    """
    Create the compact mutable snapshot for one request trace.
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
        "reasoning_gear": None,
        "governor_version": None,
        "effective_autonomy_level": None,
        "verification_depth": None,
        "governor_early_exit_eligible": False,
        "governor_escalations": [],
        "model_role_hint": None,
        "compute_decision": None,
        "selected_device": None,
        "workspace_version": None,
        "context_receipt_version": None,
        "retrieval_considered_count": 0,
        "retrieval_admitted_count": 0,
        "retrieval_excluded_count": 0,
        "retrieval_admitted_ids": [],
        "retrieval_exclusions": [],
        "retrieval_token_budget": {},
        "retrieval_projection_versions": {},
        "retrieval_contradiction_count": 0,
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
        "owner_user_id": None,
        "errors": [],
        "warnings": [],
    }


def _create_trace_record(
    *,
    request_id: str,
    request_status: str,
    current_phase: str,
    current_phase_label: str,
    current_phase_detail: str | None,
) -> dict[str, Any]:
    """
    Create one new request trace record.
    """
    now = _utc_now_iso()

    return {
        "request_id": request_id,
        "request_status": request_status,
        "current_phase": current_phase,
        "current_phase_label": current_phase_label,
        "current_phase_detail": current_phase_detail,
        "created_at_utc": now,
        "updated_at_utc": now,
        "completed_at_utc": None,
        "trace_entries": [],
        "snapshot": _base_trace_snapshot(),
    }


def _touch_trace_record(record: dict[str, Any]) -> None:
    """
    Update the trace record's updated timestamp.
    """
    record["updated_at_utc"] = _utc_now_iso()


def _append_trace_entry(
    record: dict[str, Any],
    *,
    phase: str,
    label: str,
    detail: str | None = None,
    selected_mode: str | None = None,
    selected_role: str | None = None,
    selected_runtime: str | None = None,
    selected_model_runtime_tag: str | None = None,
    locality_state: str | None = None,
    approval_state: str | None = None,
    used_fallback: bool | None = None,
    memory_classes: list[str] | None = None,
    skill_name: str | None = None,
    tool_name: str | None = None,
    app_name: str | None = None,
    worker_name: str | None = None,
    execution_tool_kind: str | None = None,
    execution_status: str | None = None,
    execution_operation: str | None = None,
    execution_summary: str | None = None,
) -> dict[str, Any]:
    """
    Append one compact trace entry to a request record.
    """
    entry = {
        "entry_id": _new_request_id(prefix="trace"),
        "request_id": record["request_id"],
        "phase": _coerce_string(phase, "unknown"),
        "label": _coerce_string(label, "Request activity"),
        "detail": _coerce_string(detail, "") or None,
        "timestamp_utc": _utc_now_iso(),
        "selected_mode": _coerce_string(selected_mode, "") or None,
        "selected_role": _coerce_string(selected_role, "") or None,
        "selected_runtime": _coerce_string(selected_runtime, "") or None,
        "selected_model_runtime_tag": _coerce_string(
            selected_model_runtime_tag,
            "",
        )
        or None,
        "locality_state": _coerce_string(locality_state, "") or None,
        "approval_state": _coerce_string(approval_state, "") or None,
        "used_fallback": used_fallback if isinstance(used_fallback, bool) else None,
        "memory_classes": _coerce_string_list(memory_classes),
        "skill_name": _coerce_string(skill_name, "") or None,
        "tool_name": _coerce_string(tool_name, "") or None,
        "app_name": _coerce_string(app_name, "") or None,
        "worker_name": _coerce_string(worker_name, "") or None,
        "execution_tool_kind": _coerce_string(execution_tool_kind, "") or None,
        "execution_status": _coerce_string(execution_status, "") or None,
        "execution_operation": _coerce_string(execution_operation, "") or None,
        "execution_summary": _coerce_string(execution_summary, "") or None,
    }

    record["trace_entries"].append(entry)
    _touch_trace_record(record)
    return entry


def _update_trace_snapshot(
    record: dict[str, Any],
    *,
    route_used: str | None = None,
    ui_surface: str | None = None,
    selected_mode: str | None = None,
    selected_role: str | None = None,
    selected_runtime: str | None = None,
    selected_model_runtime_tag: str | None = None,
    locality_state: str | None = None,
    approval_state: str | None = None,
    approval_needed: bool | None = None,
    used_fallback: bool | None = None,
    mode_profile_key: str | None = None,
    mode_profile_label: str | None = None,
    mode_profile_used: bool | None = None,
    mode_profile_effects: list[str] | None = None,
    mode_profile_warnings: list[str] | None = None,
    authority_granted_by_mode: bool | None = None,
    memory_classes: list[str] | None = None,
    skill_name: str | None = None,
    tool_name: str | None = None,
    app_name: str | None = None,
    worker_name: str | None = None,
    execution_tool_kind: str | None = None,
    execution_status: str | None = None,
    execution_operation: str | None = None,
    execution_summary: str | None = None,
    related_conversation_id: str | None = None,
    related_project_id: str | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> None:
    """
    Update the compact snapshot for one trace record.
    """
    snapshot = record["snapshot"]

    if route_used is not None:
        snapshot["route_used"] = _coerce_string(route_used, "") or None
    if ui_surface is not None:
        snapshot["ui_surface"] = _coerce_string(ui_surface, "") or None
    if selected_mode is not None:
        snapshot["selected_mode"] = _coerce_string(selected_mode, "") or None
    if selected_role is not None:
        snapshot["selected_role"] = _coerce_string(selected_role, "") or None
    if selected_runtime is not None:
        snapshot["selected_runtime"] = _coerce_string(selected_runtime, "") or None
    if selected_model_runtime_tag is not None:
        snapshot["selected_model_runtime_tag"] = _coerce_string(
            selected_model_runtime_tag,
            "",
        ) or None
    if locality_state is not None:
        snapshot["locality_state"] = _coerce_string(locality_state, "") or None
    if approval_state is not None:
        snapshot["approval_state"] = _coerce_string(approval_state, "") or None
    if approval_needed is not None:
        snapshot["approval_needed"] = bool(approval_needed)
    if used_fallback is not None:
        snapshot["used_fallback"] = bool(used_fallback)
    if mode_profile_key is not None:
        snapshot["mode_profile_key"] = _coerce_string(mode_profile_key, "") or None
    if mode_profile_label is not None:
        snapshot["mode_profile_label"] = _coerce_string(mode_profile_label, "") or None
    if mode_profile_used is not None:
        snapshot["mode_profile_used"] = bool(mode_profile_used)
    if mode_profile_effects is not None:
        snapshot["mode_profile_effects"] = _coerce_compact_string_list(mode_profile_effects)
    if mode_profile_warnings is not None:
        snapshot["mode_profile_warnings"] = _coerce_compact_string_list(mode_profile_warnings)
    if authority_granted_by_mode is not None:
        snapshot["authority_granted_by_mode"] = False
    if memory_classes is not None:
        snapshot["memory_classes"] = _coerce_string_list(memory_classes)
    if skill_name is not None:
        snapshot["skill_name"] = _coerce_string(skill_name, "") or None
    if tool_name is not None:
        snapshot["tool_name"] = _coerce_string(tool_name, "") or None
    if app_name is not None:
        snapshot["app_name"] = _coerce_string(app_name, "") or None
    if worker_name is not None:
        snapshot["worker_name"] = _coerce_string(worker_name, "") or None
    if execution_tool_kind is not None:
        snapshot["execution_tool_kind"] = _coerce_string(execution_tool_kind, "") or None
    if execution_status is not None:
        snapshot["execution_status"] = _coerce_string(execution_status, "") or None
    if execution_operation is not None:
        snapshot["execution_operation"] = _coerce_string(execution_operation, "") or None
    if execution_summary is not None:
        snapshot["execution_summary"] = _coerce_string(execution_summary, "") or None
    if related_conversation_id is not None:
        snapshot["related_conversation_id"] = (
            _coerce_string(related_conversation_id, "") or None
        )
    if related_project_id is not None:
        snapshot["related_project_id"] = _coerce_string(related_project_id, "") or None
    if errors is not None:
        snapshot["errors"] = _coerce_string_list(errors)
    if warnings is not None:
        snapshot["warnings"] = _coerce_string_list(warnings)

    _touch_trace_record(record)


def _get_or_create_trace_record(request_id: str) -> dict[str, Any]:
    """
    Return an existing trace record or create a modest unknown/running one.
    """
    record = _REQUEST_TRACE_REGISTRY.get(request_id)
    if isinstance(record, dict):
        return record

    record = _create_trace_record(
        request_id=request_id,
        request_status=_TRACE_STATUS_RUNNING,
        current_phase="preparing_request",
        current_phase_label="Preparing governed request",
        current_phase_detail="Request trace has started.",
    )
    _REQUEST_TRACE_REGISTRY[request_id] = record
    return record


def start_request_trace(
    *,
    request_id: str,
    route_used: str | None = None,
    selected_mode: str | None = None,
    related_conversation_id: str | None = None,
    related_project_id: str | None = None,
    ui_surface: str | None = None,
    phase: str = "preparing_request",
    label: str = "Preparing governed request",
    detail: str | None = "Creating a compact live trace for this governed request.",
) -> dict[str, Any]:
    """
    Start or re-open a compact in-memory request trace record.
    """
    with _REQUEST_TRACE_LOCK:
        record = _REQUEST_TRACE_REGISTRY.get(request_id)
        if not isinstance(record, dict):
            record = _create_trace_record(
                request_id=request_id,
                request_status=_TRACE_STATUS_RUNNING,
                current_phase=_coerce_string(phase, "preparing_request"),
                current_phase_label=_coerce_string(label, "Preparing governed request"),
                current_phase_detail=_coerce_string(detail, "") or None,
            )
            _REQUEST_TRACE_REGISTRY[request_id] = record
        else:
            record["request_status"] = _TRACE_STATUS_RUNNING
            record["current_phase"] = _coerce_string(phase, "preparing_request")
            record["current_phase_label"] = _coerce_string(
                label,
                "Preparing governed request",
            )
            record["current_phase_detail"] = _coerce_string(detail, "") or None
        try:
            from app.ownership import current_user_id

            record["snapshot"]["owner_user_id"] = current_user_id()
        except Exception:
            record["snapshot"]["owner_user_id"] = None
            _touch_trace_record(record)

        _update_trace_snapshot(
            record,
            route_used=route_used,
            ui_surface=ui_surface,
            selected_mode=selected_mode,
            related_conversation_id=related_conversation_id,
            related_project_id=related_project_id,
        )

        if not record["trace_entries"]:
            _append_trace_entry(
                record,
                phase=phase,
                label=label,
                detail=detail,
                selected_mode=selected_mode,
            )

        return deepcopy(record)


def append_request_trace_event(
    *,
    request_id: str,
    phase: str,
    label: str,
    detail: str | None = None,
    selected_mode: str | None = None,
    selected_role: str | None = None,
    selected_runtime: str | None = None,
    selected_model_runtime_tag: str | None = None,
    locality_state: str | None = None,
    approval_state: str | None = None,
    used_fallback: bool | None = None,
    memory_classes: list[str] | None = None,
    skill_name: str | None = None,
    tool_name: str | None = None,
    app_name: str | None = None,
    worker_name: str | None = None,
    execution_tool_kind: str | None = None,
    execution_status: str | None = None,
    execution_operation: str | None = None,
    execution_summary: str | None = None,
) -> dict[str, Any]:
    """
    Append one safe compact trace event to a request trace record.
    """
    with _REQUEST_TRACE_LOCK:
        record = _get_or_create_trace_record(request_id)
        record["current_phase"] = _coerce_string(phase, "unknown")
        record["current_phase_label"] = _coerce_string(label, "Request activity")
        record["current_phase_detail"] = _coerce_string(detail, "") or None

        entry = _append_trace_entry(
            record,
            phase=phase,
            label=label,
            detail=detail,
            selected_mode=selected_mode,
            selected_role=selected_role,
            selected_runtime=selected_runtime,
            selected_model_runtime_tag=selected_model_runtime_tag,
            locality_state=locality_state,
            approval_state=approval_state,
            used_fallback=used_fallback,
            memory_classes=memory_classes,
            skill_name=skill_name,
            tool_name=tool_name,
            app_name=app_name,
            worker_name=worker_name,
            execution_tool_kind=execution_tool_kind,
            execution_status=execution_status,
            execution_operation=execution_operation,
            execution_summary=execution_summary,
        )

        _update_trace_snapshot(
            record,
            selected_mode=selected_mode,
            selected_role=selected_role,
            selected_runtime=selected_runtime,
            selected_model_runtime_tag=selected_model_runtime_tag,
            locality_state=locality_state,
            approval_state=approval_state,
            used_fallback=used_fallback,
            memory_classes=memory_classes,
            skill_name=skill_name,
            tool_name=tool_name,
            app_name=app_name,
            worker_name=worker_name,
            execution_tool_kind=execution_tool_kind,
            execution_status=execution_status,
            execution_operation=execution_operation,
            execution_summary=execution_summary,
        )

        return deepcopy(entry)


def update_request_trace_snapshot(
    *,
    request_id: str,
    route_used: str | None = None,
    ui_surface: str | None = None,
    selected_mode: str | None = None,
    selected_role: str | None = None,
    selected_runtime: str | None = None,
    selected_model_runtime_tag: str | None = None,
    locality_state: str | None = None,
    approval_state: str | None = None,
    approval_needed: bool | None = None,
    used_fallback: bool | None = None,
    mode_profile_key: str | None = None,
    mode_profile_label: str | None = None,
    mode_profile_used: bool | None = None,
    mode_profile_effects: list[str] | None = None,
    mode_profile_warnings: list[str] | None = None,
    authority_granted_by_mode: bool | None = None,
    memory_classes: list[str] | None = None,
    skill_name: str | None = None,
    tool_name: str | None = None,
    app_name: str | None = None,
    worker_name: str | None = None,
    execution_tool_kind: str | None = None,
    execution_status: str | None = None,
    execution_operation: str | None = None,
    execution_summary: str | None = None,
    related_conversation_id: str | None = None,
    related_project_id: str | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """
    Update the compact snapshot for one request trace without appending a new event.
    """
    with _REQUEST_TRACE_LOCK:
        record = _get_or_create_trace_record(request_id)
        _update_trace_snapshot(
            record,
            route_used=route_used,
            ui_surface=ui_surface,
            selected_mode=selected_mode,
            selected_role=selected_role,
            selected_runtime=selected_runtime,
            selected_model_runtime_tag=selected_model_runtime_tag,
            locality_state=locality_state,
            approval_state=approval_state,
            approval_needed=approval_needed,
            used_fallback=used_fallback,
            mode_profile_key=mode_profile_key,
            mode_profile_label=mode_profile_label,
            mode_profile_used=mode_profile_used,
            mode_profile_effects=mode_profile_effects,
            mode_profile_warnings=mode_profile_warnings,
            authority_granted_by_mode=authority_granted_by_mode,
            memory_classes=memory_classes,
            skill_name=skill_name,
            tool_name=tool_name,
            app_name=app_name,
            worker_name=worker_name,
            execution_tool_kind=execution_tool_kind,
            execution_status=execution_status,
            execution_operation=execution_operation,
            execution_summary=execution_summary,
            related_conversation_id=related_conversation_id,
            related_project_id=related_project_id,
            errors=errors,
            warnings=warnings,
        )
        return deepcopy(record)


def update_request_trace_research_snapshot(
    *,
    request_id: str,
    research_ticket_id: str | None = None,
    research_worker_name: str | None = None,
    research_status: str | None = None,
    research_query_count: int | None = None,
    research_queries_sent: list[str] | None = None,
    research_query_hashes: list[str] | None = None,
    blocked_query_preview: str | None = None,
    evidence_packet_count: int | None = None,
    outward_boundary_state: str | None = None,
    private_context_sent: bool | None = None,
    network_access_used: bool | None = None,
    page_fetch_used: bool | None = None,
    cloud_search_used: bool | None = None,
    cloud_model_used: bool | None = None,
) -> dict[str, Any]:
    """
    Update UI-safe bounded research trace fields without raw private context.
    """
    with _REQUEST_TRACE_LOCK:
        record = _get_or_create_trace_record(request_id)
        snapshot = record["snapshot"]

        if research_ticket_id is not None:
            snapshot["research_ticket_id"] = _coerce_string(research_ticket_id, "") or None
        if research_worker_name is not None:
            snapshot["research_worker_name"] = _coerce_string(research_worker_name, "") or None
            snapshot["worker_name"] = _coerce_string(research_worker_name, "") or None
        if research_status is not None:
            snapshot["research_status"] = _coerce_string(research_status, "") or None
        if research_query_count is not None:
            snapshot["research_query_count"] = max(0, int(research_query_count))
        if research_queries_sent is not None:
            snapshot["research_queries_sent"] = _coerce_string_list(research_queries_sent)
        if research_query_hashes is not None:
            snapshot["research_query_hashes"] = _coerce_string_list(research_query_hashes)
        if blocked_query_preview is not None:
            snapshot["blocked_query_preview"] = _coerce_string(blocked_query_preview, "") or None
        if evidence_packet_count is not None:
            snapshot["evidence_packet_count"] = max(0, int(evidence_packet_count))
        if outward_boundary_state is not None:
            snapshot["outward_boundary_state"] = _coerce_string(outward_boundary_state, "") or None
        if private_context_sent is not None:
            snapshot["private_context_sent"] = bool(private_context_sent)
        if network_access_used is not None:
            snapshot["network_access_used"] = bool(network_access_used)
        if page_fetch_used is not None:
            snapshot["page_fetch_used"] = bool(page_fetch_used)
        if cloud_search_used is not None:
            snapshot["cloud_search_used"] = bool(cloud_search_used)
        if cloud_model_used is not None:
            snapshot["cloud_model_used"] = bool(cloud_model_used)

        _touch_trace_record(record)
        return deepcopy(record)


def update_request_trace_cognition_snapshot(
    *,
    request_id: str,
    workspace: dict[str, Any] | None = None,
    context_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach content-free retrieval/admission truth to the live request trace."""
    safe_workspace = workspace if isinstance(workspace, dict) else {}
    receipt = context_receipt if isinstance(context_receipt, dict) else {}
    admitted = [item for item in receipt.get("admitted", []) if isinstance(item, dict)]
    excluded = [item for item in receipt.get("excluded", []) if isinstance(item, dict)]
    considered = [item for item in receipt.get("considered", []) if isinstance(item, dict)]
    contradictions = [
        item for item in receipt.get("contradiction_handling", []) if isinstance(item, dict)
    ]
    governor = receipt.get("governor") if isinstance(receipt.get("governor"), dict) else {}
    compute = receipt.get("compute") if isinstance(receipt.get("compute"), dict) else {}
    with _REQUEST_TRACE_LOCK:
        record = _get_or_create_trace_record(request_id)
        snapshot = record["snapshot"]
        snapshot["reasoning_gear"] = _coerce_string(
            receipt.get("reasoning_gear") or safe_workspace.get("reasoning_gear"), ""
        ) or None
        snapshot["governor_version"] = _coerce_string(governor.get("version"), "") or None
        try:
            snapshot["effective_autonomy_level"] = max(
                1, min(5, int(governor.get("effective_autonomy_level") or 1))
            )
        except (TypeError, ValueError):
            snapshot["effective_autonomy_level"] = None
        snapshot["verification_depth"] = _coerce_string(
            governor.get("verification_depth"), ""
        ) or None
        snapshot["governor_early_exit_eligible"] = bool(
            governor.get("early_exit_eligible", False)
        )
        snapshot["governor_escalations"] = _coerce_compact_string_list(
            governor.get("escalation_conditions") or []
        )
        snapshot["model_role_hint"] = _coerce_string(
            governor.get("model_role_hint"), ""
        ) or None
        snapshot["compute_decision"] = _coerce_string(
            compute.get("decision"), ""
        ) or None
        snapshot["selected_device"] = _coerce_string(
            compute.get("selected_device"), ""
        ) or None
        snapshot["workspace_version"] = _coerce_string(
            safe_workspace.get("workspace_version"), ""
        ) or None
        snapshot["context_receipt_version"] = _coerce_string(
            receipt.get("receipt_version"), ""
        ) or None
        snapshot["retrieval_considered_count"] = len(considered)
        snapshot["retrieval_admitted_count"] = len(admitted)
        snapshot["retrieval_excluded_count"] = len(excluded)
        snapshot["retrieval_admitted_ids"] = _coerce_compact_string_list(
            [str(item.get("candidate_id") or "") for item in admitted]
        )
        snapshot["retrieval_exclusions"] = [
            {
                "candidate_id": _coerce_string(item.get("candidate_id"), ""),
                "source_type": _coerce_string(item.get("source_type"), ""),
                "reason": _coerce_string(item.get("reason"), ""),
            }
            for item in excluded[:100]
        ]
        token_budget = receipt.get("token_budget")
        snapshot["retrieval_token_budget"] = (
            {str(key): int(value) for key, value in token_budget.items() if isinstance(value, (int, float))}
            if isinstance(token_budget, dict)
            else {}
        )
        versions = receipt.get("projection_versions")
        snapshot["retrieval_projection_versions"] = (
            {str(key): _coerce_string(value, "") for key, value in versions.items()}
            if isinstance(versions, dict)
            else {}
        )
        snapshot["retrieval_contradiction_count"] = len(contradictions)
        _touch_trace_record(record)
        return deepcopy(record)


def update_request_trace_ledger_snapshot(
    *,
    request_id: str,
    files_attached: list[dict[str, Any]] | None = None,
    files_used_count: int | None = None,
    file_chunks_used_count: int | None = None,
    file_parsers_used: list[str] | None = None,
    file_memory_promotion: bool | None = None,
    file_outward_sharing: bool | None = None,
    tools_available: list[dict[str, Any]] | None = None,
    tools_used: list[dict[str, Any]] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    repo_context_status: str | None = None,
    repo_context_files: list[str] | None = None,
    patch_plan_status: str | None = None,
    patch_plan_files: list[str] | None = None,
    patch_id: str | None = None,
    patch_hash: str | None = None,
    patch_diff_preview: str | None = None,
    patch_preview_truncated: bool | None = None,
    rollback_note: str | None = None,
    command_key: str | None = None,
    command_argv: list[str] | None = None,
    command_exit_code: int | None = None,
    command_duration_ms: int | None = None,
    command_output_preview: str | None = None,
    command_output_truncated: bool | None = None,
    mutated_files: bool | None = None,
    shell_used: bool | None = None,
    git_mutation_used: bool | None = None,
    external_worker_used: bool | None = None,
) -> dict[str, Any]:
    """
    Update UI-safe request/evidence/tool ledger fields.

    This helper records compact inspectability truth only. It does not execute
    tools, authorize tools, read files, or expose raw internal payloads.
    """
    with _REQUEST_TRACE_LOCK:
        record = _get_or_create_trace_record(request_id)
        snapshot = record["snapshot"]

        if files_attached is not None:
            compact_files = _coerce_file_summary_list(files_attached)
            snapshot["files_attached"] = compact_files
            snapshot["files_attached_count"] = len(compact_files)

        if files_used_count is not None:
            snapshot["files_used_count"] = _coerce_nonnegative_int(files_used_count)
        if file_chunks_used_count is not None:
            snapshot["file_chunks_used_count"] = _coerce_nonnegative_int(file_chunks_used_count)
        if file_parsers_used is not None:
            snapshot["file_parsers_used"] = _coerce_compact_string_list(file_parsers_used)
        if file_memory_promotion is not None:
            snapshot["file_memory_promotion"] = bool(file_memory_promotion)
        if file_outward_sharing is not None:
            snapshot["file_outward_sharing"] = bool(file_outward_sharing)

        if tools_available is not None:
            compact_tools_available = _coerce_tool_ledger_list(tools_available)
            snapshot["tools_available"] = compact_tools_available
            snapshot["tools_available_count"] = len(compact_tools_available)

        if tools_used is not None:
            compact_tools_used = _coerce_tool_ledger_list(tools_used)
            snapshot["tools_used"] = compact_tools_used
            snapshot["tools_used_count"] = len(compact_tools_used)

        if artifacts is not None:
            compact_artifacts = _coerce_artifact_summary_list(artifacts)
            snapshot["artifacts"] = compact_artifacts
            snapshot["artifact_count"] = len(compact_artifacts)

        if repo_context_status is not None:
            snapshot["repo_context_status"] = (
                _coerce_compact_string(repo_context_status, "") or None
            )

        if repo_context_files is not None:
            compact_repo_files = _coerce_compact_string_list(
                repo_context_files,
                max_items=_COMPACT_TRACE_LIST_LIMIT,
            )
            snapshot["repo_context_files"] = compact_repo_files
            snapshot["repo_context_file_count"] = len(compact_repo_files)

        if patch_plan_status is not None:
            snapshot["patch_plan_status"] = (
                _coerce_compact_string(patch_plan_status, "") or None
            )

        if patch_plan_files is not None:
            compact_patch_files = _coerce_compact_string_list(
                patch_plan_files,
                max_items=_COMPACT_TRACE_LIST_LIMIT,
            )
            snapshot["patch_plan_files"] = compact_patch_files
            snapshot["patch_plan_file_count"] = len(compact_patch_files)

        if patch_id is not None:
            snapshot["patch_id"] = _coerce_compact_string(patch_id, "") or None
        if patch_hash is not None:
            snapshot["patch_hash"] = _coerce_compact_string(patch_hash, "") or None
        if patch_diff_preview is not None:
            snapshot["patch_diff_preview"] = _coerce_compact_string(patch_diff_preview, "")[:4000] or None
        if patch_preview_truncated is not None:
            snapshot["patch_preview_truncated"] = bool(patch_preview_truncated)
        if rollback_note is not None:
            snapshot["rollback_note"] = _coerce_compact_string(rollback_note, "") or None
        if command_key is not None:
            snapshot["command_key"] = _coerce_compact_string(command_key, "") or None
        if command_argv is not None:
            snapshot["command_argv"] = _coerce_compact_string_list(command_argv, max_items=12)
        if command_exit_code is not None:
            snapshot["command_exit_code"] = int(command_exit_code)
        if command_duration_ms is not None:
            snapshot["command_duration_ms"] = _coerce_nonnegative_int(command_duration_ms)
        if command_output_preview is not None:
            snapshot["command_output_preview"] = _coerce_compact_string(command_output_preview, "")[:4000] or None
        if command_output_truncated is not None:
            snapshot["command_output_truncated"] = bool(command_output_truncated)

        if mutated_files is not None:
            snapshot["mutated_files"] = bool(mutated_files)
        if shell_used is not None:
            snapshot["shell_used"] = bool(shell_used)
        if git_mutation_used is not None:
            snapshot["git_mutation_used"] = bool(git_mutation_used)
        if external_worker_used is not None:
            snapshot["external_worker_used"] = bool(external_worker_used)

        _touch_trace_record(record)
        return deepcopy(record)


def _mark_request_trace_status(
    *,
    request_id: str,
    request_status: str,
    phase: str,
    label: str,
    detail: str | None = None,
    selected_mode: str | None = None,
    selected_role: str | None = None,
    selected_runtime: str | None = None,
    selected_model_runtime_tag: str | None = None,
    locality_state: str | None = None,
    approval_state: str | None = None,
    approval_needed: bool | None = None,
    used_fallback: bool | None = None,
    memory_classes: list[str] | None = None,
    skill_name: str | None = None,
    tool_name: str | None = None,
    app_name: str | None = None,
    worker_name: str | None = None,
    execution_tool_kind: str | None = None,
    execution_status: str | None = None,
    execution_operation: str | None = None,
    execution_summary: str | None = None,
    related_conversation_id: str | None = None,
    related_project_id: str | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """
    Internal helper for terminal/live request-status transitions.
    """
    normalized_status = _normalize_trace_status(request_status)

    with _REQUEST_TRACE_LOCK:
        record = _get_or_create_trace_record(request_id)
        record["request_status"] = normalized_status
        record["current_phase"] = _coerce_string(phase, "unknown")
        record["current_phase_label"] = _coerce_string(label, "Request activity")
        record["current_phase_detail"] = _coerce_string(detail, "") or None

        _append_trace_entry(
            record,
            phase=phase,
            label=label,
            detail=detail,
            selected_mode=selected_mode,
            selected_role=selected_role,
            selected_runtime=selected_runtime,
            selected_model_runtime_tag=selected_model_runtime_tag,
            locality_state=locality_state,
            approval_state=approval_state,
            used_fallback=used_fallback,
            memory_classes=memory_classes,
            skill_name=skill_name,
            tool_name=tool_name,
            app_name=app_name,
            worker_name=worker_name,
            execution_tool_kind=execution_tool_kind,
            execution_status=execution_status,
            execution_operation=execution_operation,
            execution_summary=execution_summary,
        )

        _update_trace_snapshot(
            record,
            selected_mode=selected_mode,
            selected_role=selected_role,
            selected_runtime=selected_runtime,
            selected_model_runtime_tag=selected_model_runtime_tag,
            locality_state=locality_state,
            approval_state=approval_state,
            approval_needed=approval_needed,
            used_fallback=used_fallback,
            memory_classes=memory_classes,
            skill_name=skill_name,
            tool_name=tool_name,
            app_name=app_name,
            worker_name=worker_name,
            execution_tool_kind=execution_tool_kind,
            execution_status=execution_status,
            execution_operation=execution_operation,
            execution_summary=execution_summary,
            related_conversation_id=related_conversation_id,
            related_project_id=related_project_id,
            errors=errors,
            warnings=warnings,
        )

        if normalized_status in _TERMINAL_TRACE_STATUSES:
            record["completed_at_utc"] = _utc_now_iso()

        return deepcopy(record)


def mark_request_trace_completed(
    *,
    request_id: str,
    phase: str = "completed",
    label: str = "Completed",
    detail: str | None = "The governed request completed its current bridge-visible path.",
    selected_mode: str | None = None,
    selected_role: str | None = None,
    selected_runtime: str | None = None,
    selected_model_runtime_tag: str | None = None,
    locality_state: str | None = None,
    approval_state: str | None = None,
    approval_needed: bool | None = None,
    used_fallback: bool | None = None,
    memory_classes: list[str] | None = None,
    skill_name: str | None = None,
    tool_name: str | None = None,
    app_name: str | None = None,
    worker_name: str | None = None,
    execution_tool_kind: str | None = None,
    execution_status: str | None = None,
    execution_operation: str | None = None,
    execution_summary: str | None = None,
    related_conversation_id: str | None = None,
    related_project_id: str | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """
    Mark one request trace as completed.
    """
    return _mark_request_trace_status(
        request_id=request_id,
        request_status=_TRACE_STATUS_COMPLETED,
        phase=phase,
        label=label,
        detail=detail,
        selected_mode=selected_mode,
        selected_role=selected_role,
        selected_runtime=selected_runtime,
        selected_model_runtime_tag=selected_model_runtime_tag,
        locality_state=locality_state,
        approval_state=approval_state,
        approval_needed=approval_needed,
        used_fallback=used_fallback,
        memory_classes=memory_classes,
        skill_name=skill_name,
        tool_name=tool_name,
        app_name=app_name,
        worker_name=worker_name,
        execution_tool_kind=execution_tool_kind,
        execution_status=execution_status,
        execution_operation=execution_operation,
        execution_summary=execution_summary,
        related_conversation_id=related_conversation_id,
        related_project_id=related_project_id,
        errors=errors,
        warnings=warnings,
    )


def mark_request_trace_blocked(
    *,
    request_id: str,
    phase: str = "blocked",
    label: str = "Blocked",
    detail: str | None = "The governed request was blocked by current boundary or approval posture.",
    selected_mode: str | None = None,
    selected_role: str | None = None,
    selected_runtime: str | None = None,
    selected_model_runtime_tag: str | None = None,
    locality_state: str | None = None,
    approval_state: str | None = None,
    approval_needed: bool | None = None,
    used_fallback: bool | None = None,
    memory_classes: list[str] | None = None,
    skill_name: str | None = None,
    tool_name: str | None = None,
    app_name: str | None = None,
    worker_name: str | None = None,
    execution_tool_kind: str | None = None,
    execution_status: str | None = None,
    execution_operation: str | None = None,
    execution_summary: str | None = None,
    related_conversation_id: str | None = None,
    related_project_id: str | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """
    Mark one request trace as blocked.
    """
    return _mark_request_trace_status(
        request_id=request_id,
        request_status=_TRACE_STATUS_BLOCKED,
        phase=phase,
        label=label,
        detail=detail,
        selected_mode=selected_mode,
        selected_role=selected_role,
        selected_runtime=selected_runtime,
        selected_model_runtime_tag=selected_model_runtime_tag,
        locality_state=locality_state,
        approval_state=approval_state,
        approval_needed=approval_needed,
        used_fallback=used_fallback,
        memory_classes=memory_classes,
        skill_name=skill_name,
        tool_name=tool_name,
        app_name=app_name,
        worker_name=worker_name,
        execution_tool_kind=execution_tool_kind,
        execution_status=execution_status,
        execution_operation=execution_operation,
        execution_summary=execution_summary,
        related_conversation_id=related_conversation_id,
        related_project_id=related_project_id,
        errors=errors,
        warnings=warnings,
    )


def mark_request_trace_degraded(
    *,
    request_id: str,
    phase: str = "degraded",
    label: str = "Degraded",
    detail: str | None = "The governed request completed in a degraded path.",
    selected_mode: str | None = None,
    selected_role: str | None = None,
    selected_runtime: str | None = None,
    selected_model_runtime_tag: str | None = None,
    locality_state: str | None = None,
    approval_state: str | None = None,
    approval_needed: bool | None = None,
    used_fallback: bool | None = None,
    memory_classes: list[str] | None = None,
    skill_name: str | None = None,
    tool_name: str | None = None,
    app_name: str | None = None,
    worker_name: str | None = None,
    execution_tool_kind: str | None = None,
    execution_status: str | None = None,
    execution_operation: str | None = None,
    execution_summary: str | None = None,
    related_conversation_id: str | None = None,
    related_project_id: str | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """
    Mark one request trace as degraded.
    """
    return _mark_request_trace_status(
        request_id=request_id,
        request_status=_TRACE_STATUS_DEGRADED,
        phase=phase,
        label=label,
        detail=detail,
        selected_mode=selected_mode,
        selected_role=selected_role,
        selected_runtime=selected_runtime,
        selected_model_runtime_tag=selected_model_runtime_tag,
        locality_state=locality_state,
        approval_state=approval_state,
        approval_needed=approval_needed,
        used_fallback=used_fallback,
        memory_classes=memory_classes,
        skill_name=skill_name,
        tool_name=tool_name,
        app_name=app_name,
        worker_name=worker_name,
        execution_tool_kind=execution_tool_kind,
        execution_status=execution_status,
        execution_operation=execution_operation,
        execution_summary=execution_summary,
        related_conversation_id=related_conversation_id,
        related_project_id=related_project_id,
        errors=errors,
        warnings=warnings,
    )


def mark_request_trace_error(
    *,
    request_id: str,
    phase: str = "error",
    label: str = "Error",
    detail: str | None = "The governed request encountered an unexpected bridge-visible error.",
    selected_mode: str | None = None,
    selected_role: str | None = None,
    selected_runtime: str | None = None,
    selected_model_runtime_tag: str | None = None,
    locality_state: str | None = None,
    approval_state: str | None = None,
    approval_needed: bool | None = None,
    used_fallback: bool | None = None,
    memory_classes: list[str] | None = None,
    skill_name: str | None = None,
    tool_name: str | None = None,
    app_name: str | None = None,
    worker_name: str | None = None,
    execution_tool_kind: str | None = None,
    execution_status: str | None = None,
    execution_operation: str | None = None,
    execution_summary: str | None = None,
    related_conversation_id: str | None = None,
    related_project_id: str | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """
    Mark one request trace as errored.
    """
    return _mark_request_trace_status(
        request_id=request_id,
        request_status=_TRACE_STATUS_ERROR,
        phase=phase,
        label=label,
        detail=detail,
        selected_mode=selected_mode,
        selected_role=selected_role,
        selected_runtime=selected_runtime,
        selected_model_runtime_tag=selected_model_runtime_tag,
        locality_state=locality_state,
        approval_state=approval_state,
        approval_needed=approval_needed,
        used_fallback=used_fallback,
        memory_classes=memory_classes,
        skill_name=skill_name,
        tool_name=tool_name,
        app_name=app_name,
        worker_name=worker_name,
        execution_tool_kind=execution_tool_kind,
        execution_status=execution_status,
        execution_operation=execution_operation,
        execution_summary=execution_summary,
        related_conversation_id=related_conversation_id,
        related_project_id=related_project_id,
        errors=errors,
        warnings=warnings,
    )


def get_request_trace_record(request_id: str) -> dict[str, Any] | None:
    """
    Fetch one safe deep-copied request trace record by request_id.
    """
    with _REQUEST_TRACE_LOCK:
        record = _REQUEST_TRACE_REGISTRY.get(request_id)
        if not isinstance(record, dict):
            return None

        return deepcopy(record)


def list_request_trace_summaries(
    *,
    project_id: str | None = None,
    conversation_id: str | None = None,
    owner_user_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Return compact retained request-trace summaries for continuity surfaces.

    The trace registry is in-memory, so this is a recent-request view rather
    than durable memory. It never exposes raw logs, prompts, journals, or nested
    runtime payloads.
    """
    effective_limit = max(1, min(int(limit or 50), 200))
    summaries: list[dict[str, Any]] = []

    with _REQUEST_TRACE_LOCK:
        records = [record for record in _REQUEST_TRACE_REGISTRY.values() if isinstance(record, dict)]

    records.sort(
        key=lambda record: str(
            record.get("updated_at_utc") or record.get("created_at_utc") or ""
        ),
        reverse=True,
    )

    for record in records:
        snapshot = record.get("snapshot", {})
        if not isinstance(snapshot, dict):
            continue

        related_project_id = _coerce_string(snapshot.get("related_project_id"), "") or None
        related_conversation_id = (
            _coerce_string(snapshot.get("related_conversation_id"), "") or None
        )
        if owner_user_id is not None and snapshot.get("owner_user_id") != owner_user_id:
            continue
        if project_id and related_project_id != project_id:
            continue
        if conversation_id and related_conversation_id != conversation_id:
            continue

        summaries.append(
            {
                "request_id": _coerce_string(record.get("request_id"), ""),
                "request_status": _coerce_string(record.get("request_status"), ""),
                "current_phase": _coerce_string(record.get("current_phase"), ""),
                "updated_at_utc": _coerce_string(record.get("updated_at_utc"), ""),
                "selected_mode": _coerce_string(snapshot.get("selected_mode"), ""),
                "route_used": _coerce_string(snapshot.get("route_used"), ""),
                "locality_state": _coerce_string(snapshot.get("locality_state"), ""),
                "approval_state": _coerce_string(snapshot.get("approval_state"), ""),
                "artifact_count": int(snapshot.get("artifact_count") or 0),
                "evidence_packet_count": int(snapshot.get("evidence_packet_count") or 0),
                "related_project_id": related_project_id,
                "related_conversation_id": related_conversation_id,
            }
        )
        if len(summaries) >= effective_limit:
            break

    return summaries


def prune_request_traces(*, max_age_seconds: int = 3600) -> int:
    """
    Prune old terminal request traces from the in-memory registry.

    This stays intentionally modest: only terminal traces older than the threshold
    are removed.
    """
    now = datetime.now(UTC)
    threshold = now - timedelta(seconds=max(1, int(max_age_seconds)))
    removed = 0

    with _REQUEST_TRACE_LOCK:
        stale_ids: list[str] = []

        for request_id, record in _REQUEST_TRACE_REGISTRY.items():
            if not isinstance(record, dict):
                stale_ids.append(request_id)
                continue

            request_status = _normalize_trace_status(record.get("request_status"))
            if request_status not in _TERMINAL_TRACE_STATUSES:
                continue

            completed_at_text = _coerce_string(record.get("completed_at_utc"), "")
            if not completed_at_text:
                continue

            try:
                completed_at = datetime.fromisoformat(
                    completed_at_text.replace("Z", "+00:00")
                ).astimezone(UTC)
            except ValueError:
                stale_ids.append(request_id)
                continue

            if completed_at < threshold:
                stale_ids.append(request_id)

        for request_id in stale_ids:
            _REQUEST_TRACE_REGISTRY.pop(request_id, None)
            removed += 1

    return removed


def _load_approval_ledger() -> dict[str, Any]:
    """
    Load the narrow in-memory approval ledger from governance_service when available.

    This is intentionally modest and current-phase only.
    """
    governance_service, _ = _import_optional("app.api.governance_service")
    if governance_service is None:
        return {}

    ledger = getattr(governance_service, "_APPROVAL_LEDGER", None)
    if isinstance(ledger, dict):
        return ledger

    return {}


def _lookup_ledger_record(request_id: str) -> dict[str, Any] | None:
    """
    Look up a request record in the narrow in-memory approval ledger.
    """
    ledger = _load_approval_ledger()
    record = ledger.get(request_id)

    if isinstance(record, dict):
        return dict(record)

    return None


def _lookup_runtime_bridge_envelope(request_id: str) -> dict[str, Any] | None:
    """
    Try to discover a last-known runtime bridge envelope for the request_id.

    This does not require the runtime bridge to expose such snapshots yet, but it
    supports them if they appear later.
    """
    runtime_bridge, _ = _import_optional("app.api.runtime_bridge")
    if runtime_bridge is None:
        return None

    candidate_names = (
        "LAST_CHAT_ENVELOPE",
        "LAST_CHAT_RESPONSE_ENVELOPE",
        "LAST_REQUEST_ENVELOPE",
        "LAST_RUNTIME_PACKET",
        "LAST_CHAT_RUNTIME_PACKET",
        "LAST_RUNTIME_RESULT",
        "LAST_CHAT_RESULT",
    )

    for candidate_name in candidate_names:
        candidate = getattr(runtime_bridge, candidate_name, None)
        if not isinstance(candidate, dict):
            continue

        candidate_request_id = _coerce_string(candidate.get("request_id"), "")
        if candidate_request_id == request_id:
            return dict(candidate)

    return None


def _build_summary_from_ledger_record(
    request_id: str,
    record: dict[str, Any],
) -> RequestSummaryData:
    """
    Build a compact request summary from the governance approval ledger.
    """
    request_state = _normalize_request_state(record.get("request_state"))
    approval_state = _approval_state_from_request_state(request_state)

    decision = _coerce_string(record.get("decision"), "").lower()
    if decision in {
        ApprovalResolutionStatus.ACCEPTED.value,
        ApprovalResolutionStatus.REJECTED.value,
        ApprovalResolutionStatus.IGNORED.value,
        ApprovalResolutionStatus.ERROR.value,
    }:
        resolution_status = ApprovalResolutionStatus(decision)
    elif decision in {"approved", "denied", "cancelled"}:
        resolution_status = ApprovalResolutionStatus.ACCEPTED
    else:
        resolution_status = None

    request_type = "approval_bound_action"
    notes: list[str] = []

    if request_state == RequestSummaryState.APPROVED:
        notes.append("Approval was accepted.")
        notes.append("Later execution may still fail independently of approval.")
    elif request_state == RequestSummaryState.DENIED:
        notes.append("Request was explicitly denied.")
    elif request_state == RequestSummaryState.CANCELLED:
        notes.append("Request was explicitly cancelled.")
    else:
        notes.append("Request summary comes from the current bridge-phase approval ledger.")

    return RequestSummaryData(
        request_id=request_id,
        request_state=request_state,
        request_type=request_type,
        summary_text=_summary_text_for_request_state(request_state, request_type),
        created_at_utc=None,
        updated_at_utc=None,
        approval_required=True,
        approval_state=approval_state,
        locality=LocalityState.LOCAL,
        selected_role=_coerce_string(record.get("selected_role"), "") or None,
        selected_runtime=_coerce_string(record.get("selected_runtime"), "") or None,
        selected_model_runtime_tag=_coerce_string(
            record.get("selected_model_runtime_tag"),
            "",
        )
        or None,
        used_fallback=_coerce_bool(record.get("used_fallback"), False),
        resolution_status=resolution_status,
        can_proceed=request_state in {
            RequestSummaryState.APPROVED,
            RequestSummaryState.COMPLETED,
        },
        related_conversation_id=_coerce_string(
            record.get("related_conversation_id"),
            "",
        )
        or None,
        related_project_id=_coerce_string(record.get("related_project_id"), "") or None,
        notes=notes,
    )


def _build_summary_from_trace_record(
    request_id: str,
    record: dict[str, Any],
) -> RequestSummaryData:
    """
    Build a compact request summary from the live in-memory request trace registry.
    """
    request_status = _normalize_trace_status(record.get("request_status"))
    request_state = _trace_status_to_request_state(request_status)
    snapshot = record.get("snapshot", {})
    if not isinstance(snapshot, dict):
        snapshot = {}

    approval_state = _normalize_approval_state(snapshot.get("approval_state"))
    locality = _normalize_locality_state(snapshot.get("locality_state"))
    approval_required = _coerce_bool(snapshot.get("approval_needed"), False)

    request_type = "live_runtime_request"

    notes: list[str] = []
    current_phase_label = _coerce_string(record.get("current_phase_label"), "")
    current_phase_detail = _coerce_string(record.get("current_phase_detail"), "")

    if current_phase_label:
        notes.append(f"Current phase: {current_phase_label}.")
    if current_phase_detail:
        notes.append(current_phase_detail)

    memory_classes = _coerce_string_list(snapshot.get("memory_classes"))
    if memory_classes:
        notes.append(f"Memory classes: {', '.join(memory_classes)}.")

    skill_name = _coerce_string(snapshot.get("skill_name"), "")
    if skill_name:
        notes.append(f"Skill: {skill_name}.")

    tool_name = _coerce_string(snapshot.get("tool_name"), "")
    if tool_name:
        notes.append(f"Tool: {tool_name}.")

    app_name = _coerce_string(snapshot.get("app_name"), "")
    if app_name:
        notes.append(f"App: {app_name}.")

    worker_name = _coerce_string(snapshot.get("worker_name"), "")
    if worker_name:
        notes.append(f"Worker: {worker_name}.")

    mode_profile_label = _coerce_string(snapshot.get("mode_profile_label"), "")
    mode_profile_key = _coerce_string(snapshot.get("mode_profile_key"), "")
    mode_profile_effects = _coerce_compact_string_list(
        snapshot.get("mode_profile_effects"),
        max_items=6,
    )
    mode_profile_warnings = _coerce_compact_string_list(
        snapshot.get("mode_profile_warnings"),
        max_items=3,
    )
    if mode_profile_label or mode_profile_key:
        notes.append(
            f"Mode profile: {mode_profile_label or mode_profile_key}; authority granted by mode: false."
        )

    execution_tool_kind = _coerce_string(snapshot.get("execution_tool_kind"), "")
    execution_status = _coerce_string(snapshot.get("execution_status"), "")
    execution_operation = _coerce_string(snapshot.get("execution_operation"), "")
    execution_summary = _coerce_string(snapshot.get("execution_summary"), "")

    if execution_tool_kind:
        notes.append(f"Execution tool: {execution_tool_kind}.")
    if execution_status:
        notes.append(f"Execution status: {execution_status}.")
    if execution_operation:
        notes.append(f"Execution operation: {execution_operation}.")
    if execution_summary:
        notes.append(f"Execution summary: {execution_summary}")

    research_ticket_id = _coerce_string(snapshot.get("research_ticket_id"), "")
    research_status = _coerce_string(snapshot.get("research_status"), "")
    research_worker_name = _coerce_string(snapshot.get("research_worker_name"), "")
    evidence_packet_count = snapshot.get("evidence_packet_count")
    if research_ticket_id:
        notes.append(f"Research ticket: {research_ticket_id}.")
    if research_worker_name:
        notes.append(f"Research worker: {research_worker_name}.")
    if research_status:
        notes.append(f"Research status: {research_status}.")
    if isinstance(evidence_packet_count, int):
        notes.append(f"Evidence packets: {evidence_packet_count}.")

    files_attached_count = _coerce_nonnegative_int(
        snapshot.get("files_attached_count"),
    )
    files_used_count = _coerce_nonnegative_int(snapshot.get("files_used_count"))
    file_chunks_used_count = _coerce_nonnegative_int(
        snapshot.get("file_chunks_used_count")
    )
    file_parsers_used = _coerce_compact_string_list(
        snapshot.get("file_parsers_used"),
        max_items=_COMPACT_TRACE_LIST_LIMIT,
    )
    file_memory_promotion = _coerce_bool(
        snapshot.get("file_memory_promotion"),
        False,
    )
    file_outward_sharing = _coerce_bool(
        snapshot.get("file_outward_sharing"),
        False,
    )
    tools_available = _coerce_tool_ledger_list(snapshot.get("tools_available"))
    tools_used = _coerce_tool_ledger_list(snapshot.get("tools_used"))
    tools_available_count = _coerce_nonnegative_int(
        snapshot.get("tools_available_count"),
    )
    tools_used_count = _coerce_nonnegative_int(snapshot.get("tools_used_count"))
    artifact_count = _coerce_nonnegative_int(snapshot.get("artifact_count"))
    repo_context_status = _coerce_string(snapshot.get("repo_context_status"), "")
    repo_context_files = _coerce_compact_string_list(
        snapshot.get("repo_context_files"),
        max_items=_COMPACT_TRACE_LIST_LIMIT,
    )
    patch_plan_status = _coerce_string(snapshot.get("patch_plan_status"), "")
    patch_plan_files = _coerce_compact_string_list(
        snapshot.get("patch_plan_files"),
        max_items=_COMPACT_TRACE_LIST_LIMIT,
    )
    patch_id = _coerce_string(snapshot.get("patch_id"), "")
    patch_hash = _coerce_string(snapshot.get("patch_hash"), "")
    command_key = _coerce_string(snapshot.get("command_key"), "")
    command_exit_code = (
        _coerce_nonnegative_int(snapshot.get("command_exit_code"))
        if snapshot.get("command_exit_code") is not None
        else None
    )
    mutated_files = _coerce_bool(snapshot.get("mutated_files"), False)
    shell_used = _coerce_bool(snapshot.get("shell_used"), False)
    git_mutation_used = _coerce_bool(snapshot.get("git_mutation_used"), False)
    external_worker_used = _coerce_bool(snapshot.get("external_worker_used"), False)

    if files_attached_count:
        notes.append(f"Files attached: {files_attached_count}.")
    if files_used_count:
        notes.append(
            f"Files used: {files_used_count}; chunks used: {file_chunks_used_count}."
        )
    if file_parsers_used:
        notes.append(f"File parsers: {', '.join(file_parsers_used[:4])}.")
    if file_memory_promotion or file_outward_sharing:
        notes.append(
            f"File memory promotion: {file_memory_promotion}; file outward sharing: {file_outward_sharing}."
        )
    if tools_used:
        used_tool_keys = [
            _coerce_string(tool.get("tool_key"), "")
            for tool in tools_used[:3]
            if _coerce_string(tool.get("tool_key"), "")
        ]
        if used_tool_keys:
            notes.append(f"Tools used: {', '.join(used_tool_keys)}.")
    elif tools_used_count:
        notes.append(f"Tools used: {tools_used_count}.")
    if tools_available_count and not tools_used_count:
        notes.append(f"Tools available: {tools_available_count}.")
    if artifact_count:
        notes.append(f"Artifacts: {artifact_count}.")
    if repo_context_status:
        notes.append(
            f"Repo context: {repo_context_status}, {len(repo_context_files)} files."
        )
    if patch_plan_status:
        notes.append(f"Patch plan: {patch_plan_status}, {len(patch_plan_files)} files.")
    if patch_hash:
        notes.append(f"Patch hash: {patch_hash[:16]}.")
    if command_key:
        notes.append(f"Command: {command_key}.")
    if command_exit_code is not None:
        notes.append(f"Command exit code: {command_exit_code}.")
    if mutated_files:
        notes.append("Mutation: true.")
    if shell_used:
        notes.append("Shell: true.")
    if git_mutation_used:
        notes.append("Git mutation: true.")
    if external_worker_used:
        notes.append("External worker: true.")

    warnings = _coerce_string_list(snapshot.get("warnings"))
    for warning in warnings[:3]:
        notes.append(f"Warning: {warning}")

    errors = _coerce_string_list(snapshot.get("errors"))
    for error in errors[:3]:
        notes.append(f"Error: {error}")

    if not notes:
        notes.append(
            "Request summary comes from the live in-memory request trace registry."
        )

    can_proceed = request_status == _TRACE_STATUS_COMPLETED

    return RequestSummaryData(
        request_id=request_id,
        request_state=request_state,
        request_type=request_type,
        summary_text=_summary_text_for_request_state(request_state, request_type),
        created_at_utc=_coerce_string(record.get("created_at_utc"), "") or None,
        updated_at_utc=_coerce_string(record.get("updated_at_utc"), "") or None,
        approval_required=approval_required,
        approval_state=approval_state,
        locality=locality,
        selected_role=_coerce_string(snapshot.get("selected_role"), "") or None,
        selected_runtime=_coerce_string(snapshot.get("selected_runtime"), "") or None,
        selected_model_runtime_tag=_coerce_string(
            snapshot.get("selected_model_runtime_tag"),
            "",
        )
        or None,
        used_fallback=_coerce_bool(snapshot.get("used_fallback"), False),
        mode_profile_key=mode_profile_key or None,
        mode_profile_label=mode_profile_label or None,
        mode_profile_used=_coerce_bool(snapshot.get("mode_profile_used"), False),
        mode_profile_effects=mode_profile_effects,
        mode_profile_warnings=mode_profile_warnings,
        authority_granted_by_mode=False,
        execution_tool_kind=_coerce_string(snapshot.get("execution_tool_kind"), "") or None,
        execution_status=_coerce_string(snapshot.get("execution_status"), "") or None,
        execution_operation=_coerce_string(snapshot.get("execution_operation"), "") or None,
        execution_summary=_coerce_string(snapshot.get("execution_summary"), "") or None,
        research_ticket_id=_coerce_string(snapshot.get("research_ticket_id"), "") or None,
        research_status=_coerce_string(snapshot.get("research_status"), "") or None,
        research_worker_name=_coerce_string(snapshot.get("research_worker_name"), "") or None,
        research_query_count=int(snapshot.get("research_query_count") or 0),
        evidence_packet_count=int(snapshot.get("evidence_packet_count") or 0),
        outward_boundary_state=_coerce_string(snapshot.get("outward_boundary_state"), "") or None,
        private_context_sent=_coerce_bool(snapshot.get("private_context_sent"), False),
        network_access_used=_coerce_bool(snapshot.get("network_access_used"), False),
        page_fetch_used=_coerce_bool(snapshot.get("page_fetch_used"), False),
        cloud_search_used=_coerce_bool(snapshot.get("cloud_search_used"), False),
        cloud_model_used=_coerce_bool(snapshot.get("cloud_model_used"), False),
        files_attached_count=files_attached_count,
        files_attached=_coerce_file_summary_list(snapshot.get("files_attached")),
        files_used_count=files_used_count,
        file_chunks_used_count=file_chunks_used_count,
        file_parsers_used=file_parsers_used,
        file_memory_promotion=file_memory_promotion,
        file_outward_sharing=file_outward_sharing,
        tools_available_count=tools_available_count,
        tools_used_count=tools_used_count,
        tools_available=tools_available,
        tools_used=tools_used,
        artifact_count=artifact_count,
        artifacts=_coerce_artifact_summary_list(snapshot.get("artifacts")),
        repo_context_status=repo_context_status or None,
        repo_context_file_count=len(repo_context_files),
        repo_context_files=repo_context_files,
        patch_plan_status=patch_plan_status or None,
        patch_plan_file_count=len(patch_plan_files),
        patch_plan_files=patch_plan_files,
        patch_id=patch_id or None,
        patch_hash=patch_hash or None,
        patch_diff_preview=_coerce_string(snapshot.get("patch_diff_preview"), "") or None,
        patch_preview_truncated=_coerce_bool(
            snapshot.get("patch_preview_truncated"),
            False,
        ),
        rollback_note=_coerce_string(snapshot.get("rollback_note"), "") or None,
        command_key=command_key or None,
        command_argv=_coerce_compact_string_list(snapshot.get("command_argv"), max_items=12),
        command_exit_code=command_exit_code,
        command_duration_ms=_coerce_nonnegative_int(
            snapshot.get("command_duration_ms")
        ),
        command_output_preview=_coerce_string(
            snapshot.get("command_output_preview"),
            "",
        )
        or None,
        command_output_truncated=_coerce_bool(
            snapshot.get("command_output_truncated"),
            False,
        ),
        mutated_files=mutated_files,
        shell_used=shell_used,
        git_mutation_used=git_mutation_used,
        external_worker_used=external_worker_used,
        resolution_status=None,
        can_proceed=can_proceed,
        related_conversation_id=_coerce_string(
            snapshot.get("related_conversation_id"),
            "",
        )
        or None,
        related_project_id=_coerce_string(snapshot.get("related_project_id"), "") or None,
        notes=notes,
    )


def _build_summary_from_runtime_bridge_envelope(
    request_id: str,
    envelope: dict[str, Any],
) -> RequestSummaryData:
    """
    Build a compact request summary from a last-known runtime bridge envelope.

    This is intentionally modest and partial. It uses only UI-safe compact truth
    already exposed through the bridge, never raw logs.
    """
    envelope_status = _coerce_string(envelope.get("status"), "").lower()
    data = envelope.get("data", {})
    trace_summary = envelope.get("trace_summary", {})

    if not isinstance(data, dict):
        data = {}

    if not isinstance(trace_summary, dict):
        trace_summary = {}

    approval_needed = _coerce_bool(data.get("approval_needed"), False)
    approval_state = _normalize_approval_state(envelope.get("approval_state"))
    locality = _normalize_locality_state(envelope.get("locality"))

    if envelope_status == EnvelopeStatus.BLOCKED.value:
        request_state = RequestSummaryState.BLOCKED
    elif envelope_status in {
        EnvelopeStatus.OK.value,
        EnvelopeStatus.DEGRADED.value,
    }:
        request_state = RequestSummaryState.COMPLETED
    elif approval_needed:
        request_state = RequestSummaryState.PENDING
    else:
        request_state = RequestSummaryState.UNKNOWN

    notes: list[str] = []
    caveats = data.get("caveats", [])
    if isinstance(caveats, list):
        notes.extend(str(item) for item in caveats[:3] if str(item).strip())

    if not notes:
        notes.append(
            "Request summary comes from a last-known runtime bridge envelope and may be partial."
        )

    if request_state == RequestSummaryState.COMPLETED and approval_needed:
        notes.append(
            "This response completed successfully, but broader downstream actions remain approval-bound."
        )

    math_execution = data.get("math_execution")
    if not isinstance(math_execution, dict):
        response_payload = data.get("response", {})
        if isinstance(response_payload, dict):
            math_execution = response_payload.get("math_execution")

    if not isinstance(math_execution, dict):
        math_execution = {}

    execution_tool_kind = _coerce_string(math_execution.get("tool_kind"), "")
    execution_status = _coerce_string(math_execution.get("status"), "")
    execution_operation = _coerce_string(math_execution.get("operation"), "")
    execution_result = _coerce_string(math_execution.get("result"), "")
    execution_numeric_result = math_execution.get("numeric_result")

    execution_summary_parts: list[str] = []
    if execution_result:
        execution_summary_parts.append(f"result {execution_result}")
    if execution_numeric_result is not None:
        execution_summary_parts.append(f"numeric result {execution_numeric_result}")

    execution_summary = "; ".join(execution_summary_parts)

    if execution_tool_kind:
        notes.append(f"Execution tool: {execution_tool_kind}.")
    if execution_status:
        notes.append(f"Execution status: {execution_status}.")
    if execution_operation:
        notes.append(f"Execution operation: {execution_operation}.")
    if execution_summary:
        notes.append(f"Execution summary: {execution_summary}")

    return RequestSummaryData(
        request_id=request_id,
        request_state=request_state,
        request_type="local_runtime_request",
        summary_text=_summary_text_for_request_state(
            request_state,
            "local runtime request",
        ),
        created_at_utc=_coerce_string(envelope.get("timestamp_utc"), "") or None,
        updated_at_utc=_coerce_string(envelope.get("timestamp_utc"), "") or None,
        approval_required=approval_needed,
        approval_state=approval_state,
        locality=locality,
        selected_role=_coerce_string(trace_summary.get("selected_role"), "")
        or _coerce_string(data.get("selected_model_role"), "")
        or None,
        selected_runtime=_coerce_string(trace_summary.get("selected_runtime"), "")
        or _coerce_string(data.get("selected_runtime"), "")
        or None,
        selected_model_runtime_tag=_coerce_string(
            trace_summary.get("selected_model_runtime_tag"),
            "",
        )
        or _coerce_string(data.get("selected_model_runtime_tag"), "")
        or None,
        used_fallback=_coerce_bool(
            data.get("used_fallback"),
            _coerce_bool(trace_summary.get("used_fallback"), False),
        ),
        execution_tool_kind=execution_tool_kind or None,
        execution_status=execution_status or None,
        execution_operation=execution_operation or None,
        execution_summary=execution_summary or None,
        resolution_status=None,
        can_proceed=request_state == RequestSummaryState.COMPLETED,
        related_conversation_id=_coerce_string(data.get("conversation_id"), "") or None,
        related_project_id=_coerce_string(data.get("project_id"), "") or None,
        notes=notes,
    )


def _build_unknown_request_summary(
    request_id: str,
) -> RequestSummaryData:
    """
    Build the compact response payload for an unknown request_id.
    """
    return RequestSummaryData(
        request_id=request_id,
        request_state=RequestSummaryState.UNKNOWN,
        request_type="unknown",
        summary_text="Requested summary could not be produced because the request_id is not valid or not currently known.",
        created_at_utc=None,
        updated_at_utc=None,
        approval_required=False,
        approval_state=ApprovalState.UNKNOWN,
        locality=LocalityState.UNKNOWN,
        selected_role=None,
        selected_runtime=None,
        selected_model_runtime_tag=None,
        used_fallback=False,
        resolution_status=None,
        can_proceed=False,
        related_conversation_id=None,
        related_project_id=None,
        notes=[
            "No real governed request exists for this request_id.",
            "Current bridge-phase request tracking is intentionally modest.",
        ],
    )


def _lookup_known_request_summary(
    request_model: RequestSummaryLookup,
) -> tuple[RequestSummaryData | None, CapabilityState, list[str], TraceSummary]:
    """
    Look up the best currently available compact summary for a request_id.

    Source order:
    1. narrow approval ledger
    2. live in-memory request trace registry
    3. last-known runtime bridge envelope
    """
    ledger_record = _lookup_ledger_record(request_model.request_id)
    if ledger_record is not None:
        summary = _build_summary_from_ledger_record(
            request_model.request_id,
            ledger_record,
        )
        trace_summary = TraceSummary(
            route_used="requests.summary",
            selected_role=summary.selected_role,
            selected_runtime=summary.selected_runtime,
            selected_model_runtime_tag=summary.selected_model_runtime_tag,
            used_fallback=summary.used_fallback,
            log_written=False,
            journal_written=False,
        )
        return summary, CapabilityState.LIVE, [], trace_summary

    trace_record = get_request_trace_record(request_model.request_id)
    if trace_record is not None:
        summary = _build_summary_from_trace_record(
            request_model.request_id,
            trace_record,
        )
        snapshot = trace_record.get("snapshot", {})
        if not isinstance(snapshot, dict):
            snapshot = {}

        trace_summary = TraceSummary(
            route_used=_coerce_string(snapshot.get("route_used"), "") or "request_trace",
            selected_role=summary.selected_role,
            selected_runtime=summary.selected_runtime,
            selected_model_runtime_tag=summary.selected_model_runtime_tag,
            used_fallback=summary.used_fallback,
            log_written=False,
            journal_written=False,
        )
        capability_state = _trace_status_to_capability_state(
            _normalize_trace_status(trace_record.get("request_status"))
        )
        return summary, capability_state, [], trace_summary

    runtime_envelope = _lookup_runtime_bridge_envelope(request_model.request_id)
    if runtime_envelope is not None:
        summary = _build_summary_from_runtime_bridge_envelope(
            request_model.request_id,
            runtime_envelope,
        )
        trace_summary = TraceSummary(
            route_used="requests.summary",
            selected_role=summary.selected_role,
            selected_runtime=summary.selected_runtime,
            selected_model_runtime_tag=summary.selected_model_runtime_tag,
            used_fallback=summary.used_fallback,
            log_written=False,
            journal_written=False,
        )
        warnings = [
            "Request summary is based on last-known runtime bridge output and may be partial.",
        ]
        return summary, CapabilityState.DEGRADED, warnings, trace_summary

    trace_summary = TraceSummary(
        route_used="requests.summary",
        log_written=False,
        journal_written=False,
    )
    return None, CapabilityState.LIVE, [], trace_summary


def get_request_summary(request_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Return a structured envelope payload for GET /requests/{request_id}/summary.

    This function is intentionally modest and honest:
    - it summarizes only the governed request truth currently available
    - it does not expose raw logs
    - it does not pretend a mature request database already exists
    """
    envelope_request_id = _new_request_id()

    try:
        request_model = RequestSummaryLookup(**request_payload)
    except ValidationError as exc:
        envelope = build_response_envelope(
            status=EnvelopeStatus.ERROR,
            request_id=envelope_request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="request_summary",
            capability_state=CapabilityState.UNKNOWN,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.UNKNOWN,
            warnings=[],
            errors=[f"Request summary lookup validation failed: {exc}"],
            trace_summary=TraceSummary(
                route_used="requests.summary",
                log_written=False,
                journal_written=False,
            ),
            data={},
        )
        return envelope.to_payload()

    try:
        summary_data, capability_state, warnings, trace_summary = _lookup_known_request_summary(
            request_model
        )

        if summary_data is None:
            summary_data = _build_unknown_request_summary(request_model.request_id)

            envelope = build_response_envelope(
                status=EnvelopeStatus.BLOCKED,
                request_id=envelope_request_id,
                api_version=API_VERSION,
                contract_version=CONTRACT_VERSION,
                result_type="request_summary",
                capability_state=CapabilityState.LIVE,
                locality=LocalityState.UNKNOWN,
                approval_state=ApprovalState.UNKNOWN,
                warnings=[],
                errors=["No real governed request exists for this request_id."],
                trace_summary=trace_summary,
                data=summary_data,
            )
            return envelope.to_payload()

        envelope = build_response_envelope(
            status=EnvelopeStatus.OK,
            request_id=envelope_request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="request_summary",
            capability_state=capability_state,
            locality=summary_data.locality,
            approval_state=summary_data.approval_state,
            warnings=warnings,
            errors=[],
            trace_summary=trace_summary,
            data=summary_data,
        )
        return envelope.to_payload()

    except Exception as exc:
        LOGGER.exception("Request summary lookup failed unexpectedly", exc_info=exc)

        envelope = build_response_envelope(
            status=EnvelopeStatus.ERROR,
            request_id=envelope_request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="request_summary",
            capability_state=CapabilityState.UNKNOWN,
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.UNKNOWN,
            warnings=[],
            errors=[f"Request summary lookup failed unexpectedly: {exc}"],
            trace_summary=TraceSummary(
                route_used="requests.summary",
                log_written=False,
                journal_written=False,
            ),
            data={},
        )
        return envelope.to_payload()


__all__ = (
    "append_request_trace_event",
    "get_request_summary",
    "get_request_trace_record",
    "list_request_trace_summaries",
    "mark_request_trace_blocked",
    "mark_request_trace_completed",
    "mark_request_trace_degraded",
    "mark_request_trace_error",
    "prune_request_traces",
    "start_request_trace",
    "update_request_trace_ledger_snapshot",
    "update_request_trace_research_snapshot",
    "update_request_trace_cognition_snapshot",
    "update_request_trace_snapshot",
)
