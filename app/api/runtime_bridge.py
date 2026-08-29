"""
Runtime bridge for the Elysia local API bridge.

This module is the narrow adapter between the HTTP/API layer and Elysia's
actual governed body path.

Its job is deliberately narrow:
- accept already-validated API-side chat input
- normalize/build the minimal runtime session input
- call the real core.runtime entrypoint
- translate runtime output into Stage 3 schema shapes
- return a structured response envelope payload
- emit coarse-grained bridge-visible request trace events

It must not:
- decide routing from scratch
- decide policy from scratch
- call Ollama directly
- bypass verification, logging, or journaling
- duplicate runtime logic
- become a dumping ground for API conveniences
- become the request-trace store
- become the trace route layer
"""

from __future__ import annotations

import importlib
import inspect
import logging
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from core.plot_artifact_builder import build_numeric_summary_bar_svg

from app.api import account_service
from app.api.artifact_service import (
    ArtifactCreationError,
    artifact_summary_from_record,
    create_data_summary_artifact,
    create_plot_image_artifact,
)
from app.api.file_ingest_service import build_attached_file_context_packet
from app.api.request_trace_service import (
    append_request_trace_event,
    mark_request_trace_blocked,
    mark_request_trace_completed,
    mark_request_trace_degraded,
    mark_request_trace_error,
    start_request_trace,
    update_request_trace_ledger_snapshot,
    update_request_trace_cognition_snapshot,
    update_request_trace_snapshot,
)
from app.api.schemas.artifacts import ArtifactSummary
from app.api.schemas.chat import (
    ChatInvocationStatus,
    ChatResponseSource,
    ChatSendRequest,
    ChatSendResponseData,
)
from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.api.user_control_service import autonomy_level as authoritative_autonomy_level
from app.ids import new_id

LOGGER = logging.getLogger(__name__)

API_VERSION = "1.0.0"
CONTRACT_VERSION = "phase1-ui-contract-1.0"

DEFAULT_ACTIVE_MODE = "default"
DEFAULT_AUTONOMY_LEVEL = 1
DEFAULT_MEMORY_LAYERS = ["working", "conversation", "project", "preferences"]
QUICK_INVOKE_MEMORY_LAYERS = ["working", "conversation"]

LAST_RUNTIME_PACKET: dict[str, Any] = {}
LAST_CHAT_RUNTIME_PACKET: dict[str, Any] = {}
LAST_RUNTIME_RESULT: dict[str, Any] = {}
LAST_CHAT_RESULT: dict[str, Any] = {}
LAST_CHAT_ENVELOPE: dict[str, Any] = {}
LAST_CHAT_RESPONSE_ENVELOPE: dict[str, Any] = {}


def _new_request_id(prefix: str = "req") -> str:
    """
    Create a compact request identifier for API-envelope use.
    """
    return new_id(prefix)


def _resolve_request_id(payload_dict: dict[str, Any]) -> str:
    """
    Resolve a request_id from the incoming payload when supplied, otherwise create one.

    This lets the frontend know the request_id before completion for live polling,
    without requiring the bridge to stop working when no request_id is provided yet.
    """
    candidate = _coerce_string(payload_dict.get("request_id"), "")
    return candidate or _new_request_id()


def _as_mapping(value: Any) -> dict[str, Any]:
    """
    Return a shallow copied mapping or an empty dict.
    """
    if not isinstance(value, Mapping):
        return {}

    return dict(value)


def _coerce_string(value: Any, default: str = "") -> str:
    """
    Normalize one value into a clean string.
    """
    text = str(value or "").strip()
    return text if text else default


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


def _coerce_string_list(value: Any) -> list[str]:
    """
    Normalize one optional list-like value into a compact string list.
    """
    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    for item in value:
        text = _coerce_string(item, "")
        if text:
            normalized.append(text)

    return normalized


def _dedupe_string_list(values: list[str]) -> list[str]:
    """
    Preserve order while removing duplicates and empty entries.
    """
    seen: set[str] = set()
    deduped: list[str] = []

    for value in values:
        text = _coerce_string(value, "")
        if not text or text in seen:
            continue

        seen.add(text)
        deduped.append(text)

    return deduped


def _is_quick_invoke_surface(ui_surface_hint: str | None) -> bool:
    """
    Determine whether the current request came from Quick Invoke.
    """
    return _coerce_string(ui_surface_hint, "").lower() == "quick_invoke"


def _build_memory_layers_for_surface(
    *,
    is_quick_invoke: bool,
    has_project_context: bool,
) -> list[str]:
    """
    Build the governed memory-layer posture for the current surface.

    Quick Invoke keeps the same governed path, but narrows context weight.
    """
    if not is_quick_invoke:
        return list(DEFAULT_MEMORY_LAYERS)

    memory_layers = list(QUICK_INVOKE_MEMORY_LAYERS)
    if has_project_context:
        memory_layers.append("project")

    return _dedupe_string_list(memory_layers)


def _build_runtime_request_context(
    *,
    is_quick_invoke: bool,
    ui_surface_hint: str | None,
    inbound_request_context: dict[str, Any] | None = None,
    attached_context_packet: dict[str, Any] | None = None,
    profile_context: dict[str, Any] | None = None,
    request_id: str | None = None,
    conversation_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Build one optional compact runtime hint payload.

    This does not weaken governance. It carries UI hints and attached-file
    context truth when present, while keeping attached files as context only,
    never memory.
    """
    context: dict[str, Any] = {}

    if inbound_request_context:
        context.update(dict(inbound_request_context))

    if is_quick_invoke:
        context.update(
            {
                "ui_surface": _coerce_string(ui_surface_hint, "quick_invoke"),
                "response_style": "compact",
                "response_length_preference": "short",
                "compact_surface": True,
                "note": "Compact governed entry surface. Prefer concise direct answers unless safety or boundary truth requires more detail.",
            }
        )

    if attached_context_packet is not None:
        data_files = [
            dict(file)
            for file in attached_context_packet.get("data_files", [])
            if isinstance(file, Mapping)
        ]
        context["attached_context"] = attached_context_packet
        context["attached_data_files"] = data_files
        context["attached_files_are_memory"] = False
        context["attached_files_source"] = "user_selected_local_files"

    if profile_context is not None:
        context["profile_context"] = dict(profile_context)
        context["profile_context_source"] = "sealed_identity_visible_projection"
        context["profile_private_fields_included"] = False
        context["profile_memory_import_allowed"] = False

    # These identifiers have already passed the typed chat contract. Assign
    # them after inbound hints so arbitrary request_context cannot override the
    # canonical conversation/project/request linkage.
    context["request_id"] = request_id
    context["conversation_id"] = conversation_id
    context["project_id"] = project_id
    try:
        from app.api.user_control_service import current_user_controls

        snapshot = current_user_controls()
        context["retrieval_breadth"] = snapshot.retrieval_breadth
        context["research_initiative"] = snapshot.research_initiative
        context["safe_search_level"] = snapshot.safe_search_level
        context["internet_master_enabled"] = snapshot.internet_master_enabled
        context["preferred_reasoning_gear"] = snapshot.preferred_reasoning_gear
        context["autonomy_domain_overrides"] = dict(snapshot.autonomy_domain_overrides)
        context["compute_preference"] = snapshot.compute_preference
        context["model_performance_preference"] = snapshot.model_performance_preference
        context["background_cognition_enabled"] = snapshot.background_cognition_enabled
        context["cpu_percent_ceiling"] = snapshot.cpu_percent_ceiling
        context["ram_mb_ceiling"] = snapshot.ram_mb_ceiling
        context["vram_mb_ceiling"] = snapshot.vram_mb_ceiling
        context["max_background_jobs"] = snapshot.max_background_jobs
        context["managed_profile"] = snapshot.managed_profile
        context["managed_policy_version"] = snapshot.managed_policy_version
    except Exception:
        # No authenticated account means fail-closed network behavior and
        # default bounded local retrieval; account-required sources stay empty.
        context.setdefault("retrieval_breadth", "focused")
        context.setdefault("research_initiative", "manual")
        context.setdefault("safe_search_level", "strict")
        context.setdefault("internet_master_enabled", False)

    return context or None


def _load_visible_profile_context() -> dict[str, Any] | None:
    """
    Return only the Elysia-visible profile projection.

    This function must never read or return private profile fields. If account
    state is absent, logged out, or unavailable, the runtime simply receives no
    profile context.
    """
    try:
        profile = account_service.get_elysia_visible_profile()
    except Exception as exc:
        LOGGER.info("Visible profile projection unavailable: %s", exc)
        return None

    if profile is None:
        return None

    payload = profile.to_payload()
    allowed = {
        "name_or_username",
        "interests",
        "bio",
        "profile_photo_asset_id",
        "profile_photo_available",
    }
    return {key: payload[key] for key in allowed if key in payload}


def _extract_attached_file_ids(request_context: dict[str, Any] | None) -> list[str]:
    """
    Extract attached file ids from a compact request_context mapping.
    """
    if not isinstance(request_context, Mapping):
        return []

    raw_ids = request_context.get("attached_file_ids")
    if raw_ids is None:
        raw_ids = request_context.get("attached_files")

    if isinstance(raw_ids, str):
        return _dedupe_string_list([raw_ids])

    if isinstance(raw_ids, list):
        return _dedupe_string_list([
            _coerce_string(value, "")
            for value in raw_ids
        ])

    return []


def _build_attached_context_summary(
    packet: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """
    Build a compact response-visible truth summary for attached file context.
    """
    if not packet:
        return None

    files = [
        file
        for file in packet.get("files", [])
        if isinstance(file, Mapping)
    ]
    data_files = [
        file
        for file in packet.get("data_files", [])
        if isinstance(file, Mapping)
    ]

    text_file_names = [
        _coerce_string(file.get("display_name"), file.get("file_id", "attached-file"))
        for file in files
    ]
    data_file_names = [
        _coerce_string(file.get("display_name"), file.get("file_id", "attached-data-file"))
        for file in data_files
    ]

    has_any_file = bool(files or data_files)
    compact_files: list[dict[str, Any]] = []
    compact_data_files: list[dict[str, Any]] = []
    for file in files:
        compact_files.append(
            {
                "file_id": _coerce_string(file.get("file_id"), ""),
                "display_name": _coerce_string(file.get("display_name"), "attached-file"),
                "file_kind": _coerce_string(file.get("file_kind"), "unknown"),
                "processing_state": _coerce_string(file.get("processing_state"), "ready"),
                "parser_used": _coerce_string(file.get("parser_used"), ""),
                "memory_posture": _coerce_string(file.get("memory_posture"), "not_memory"),
                "memory_promotion_allowed": False,
                "outward_sharing_allowed": False,
                "chunk_count": _coerce_int(file.get("chunk_count"), 0),
                "selected_chunk_count": _coerce_int(file.get("selected_chunk_count"), 0),
                "retrieval_method": _coerce_string(file.get("retrieval_method"), "bounded_selection"),
            }
        )
    for file in data_files:
        compact_data_files.append(
            {
                "file_id": _coerce_string(file.get("file_id"), ""),
                "display_name": _coerce_string(file.get("display_name"), "attached-data-file"),
                "file_name": _coerce_string(file.get("file_name"), "attached-data-file"),
                "file_kind": _coerce_string(file.get("file_kind"), "unknown"),
                "processing_state": _coerce_string(file.get("processing_state"), "ready"),
                "parser_used": _coerce_string(file.get("parser_used"), "data_file_registration"),
                "memory_posture": _coerce_string(file.get("memory_posture"), "not_memory"),
                "memory_promotion_allowed": False,
                "outward_sharing_allowed": False,
                "chunk_count": _coerce_int(file.get("chunk_count"), 0),
                "selected_chunk_count": _coerce_int(file.get("selected_chunk_count"), 0),
                "retrieval_method": "bounded_data_file_registration",
            }
        )

    return {
        "active_project_id": None,
        "active_project_name": None,
        "files_in_use": text_file_names + data_file_names,
        "text_files_in_use": text_file_names,
        "data_files_in_use": data_file_names,
        "attached_file_ids": list(packet.get("used_file_ids", []) or []),
        "attached_text_file_ids": list(packet.get("used_text_file_ids", []) or []),
        "attached_data_file_ids": list(packet.get("used_data_file_ids", []) or []),
        "attached_files_are_memory": False,
        "attached_files_source": packet.get("source", "user_selected_local_files"),
        "file_count": packet.get("file_count", len(files) + len(data_files)),
        "text_file_count": packet.get("text_file_count", len(files)),
        "data_file_count": packet.get("data_file_count", len(data_files)),
        "files": compact_files,
        "data_files": compact_data_files,
        "files_used_count": len(compact_files) + len(compact_data_files),
        "file_chunks_used_count": sum(
            _coerce_int(file.get("selected_chunk_count"), 0)
            for file in compact_files + compact_data_files
        ),
        "file_parsers_used": _dedupe_string_list([
            _coerce_string(file.get("parser_used"), "")
            for file in compact_files + compact_data_files
        ]),
        "file_memory_promotion": False,
        "file_outward_sharing": False,
        "bounded": True,
        "warnings": list(packet.get("warnings", []) or []),
        "errors": list(packet.get("errors", []) or []),
        "active_context_note": (
            "Attached local files were included for this request. TXT/Markdown files may be used as bounded text context; CSV/XLSX files may be used as bounded local data-execution inputs. They were not promoted into memory."
        )
        if has_any_file
        else "No attached local file context or data file was included in this request.",
    }


def _build_attached_context_block(packet: dict[str, Any] | None) -> str:
    """
    Build a bounded model-facing attached-file context block.
    """
    if not packet or not packet.get("files"):
        return ""

    lines: list[str] = [
        "Attached local file context:",
        "These files were explicitly selected by the user in the local desktop chamber.",
        "They are context only. They are not memory.",
        "Use only the excerpts below when answering questions about the attached files.",
        "",
    ]

    for file_index, file_packet in enumerate(packet.get("files", []) or [], start=1):
        if not isinstance(file_packet, Mapping):
            continue

        display_name = _coerce_string(
            file_packet.get("display_name"),
            f"attached-file-{file_index}",
        )
        file_id = _coerce_string(file_packet.get("file_id"), "")
        file_kind = _coerce_string(file_packet.get("file_kind"), "unknown")
        memory_posture = _coerce_string(
            file_packet.get("memory_posture"),
            "not_memory",
        )

        lines.extend(
            [
                f"File {file_index}: {display_name}",
                f"File ID: {file_id}",
                f"Kind: {file_kind}",
                f"Memory posture: {memory_posture}",
                "",
            ]
        )

        chunks = file_packet.get("chunks")
        if not isinstance(chunks, list):
            continue

        for chunk in chunks:
            if not isinstance(chunk, Mapping):
                continue

            chunk_index = chunk.get("chunk_index")
            excerpt = _coerce_string(chunk.get("excerpt"), "")
            if not excerpt:
                continue

            lines.extend(
                [
                    f"Chunk {chunk_index}:",
                    excerpt,
                    "",
                ]
            )

    return "\n".join(lines).strip()


def _build_effective_runtime_message(
    *,
    user_message: str,
    attached_context_packet: dict[str, Any] | None,
) -> str:
    """
    Add bounded attached-file context to the model-facing message when available.
    """
    context_block = _build_attached_context_block(attached_context_packet)
    if not context_block:
        return user_message

    return f"{context_block}\n\nUser request:\n{user_message}"


def _safe_trace_call(action_name: str, func: Any, **kwargs: Any) -> None:
    """
    Call one request-trace helper without letting trace failures break the bridge.
    """
    try:
        func(**kwargs)
    except Exception as exc:
        LOGGER.warning(
            "Request trace update failed during %s: %s",
            action_name,
            exc,
        )


def _normalize_chat_response_source(value: Any) -> ChatResponseSource:
    """
    Normalize runtime response_source into the chat schema enum.
    """
    normalized = _coerce_string(value, "").lower()

    if normalized == ChatResponseSource.LIVE_INVOKER.value:
        return ChatResponseSource.LIVE_INVOKER

    return ChatResponseSource.SCAFFOLD_FALLBACK


def _normalize_chat_invocation_status(value: Any) -> ChatInvocationStatus:
    """
    Normalize runtime invocation_status into the chat schema enum.
    """
    normalized = _coerce_string(value, "").lower()

    for candidate in ChatInvocationStatus:
        if normalized == candidate.value:
            return candidate

    return ChatInvocationStatus.UNKNOWN


def _load_runtime_module() -> Any:
    """
    Import the real governed runtime organ lazily.

    The bridge must call the real body path, not duplicate it.
    """
    return importlib.import_module("core.runtime")


def _build_session_state(
    runtime_module: Any,
    *,
    active_mode: str | None = None,
    autonomy_level: int | None = None,
    memory_layers: list[str] | None = None,
) -> Any:
    """
    Build a minimal SessionState object for the current bridge phase.

    The API bridge does not invent new runtime policy here. It only supplies
    a modest default session shell so the existing body can run.
    """
    session_state_cls = getattr(runtime_module, "SessionState", None)
    if session_state_cls is None:
        raise RuntimeError("core.runtime does not expose SessionState.")

    defaults: dict[str, Any] = {
        "active_mode": active_mode or DEFAULT_ACTIVE_MODE,
        "autonomy_level": (
            DEFAULT_AUTONOMY_LEVEL if autonomy_level is None else autonomy_level
        ),
        "memory_layers": list(memory_layers or DEFAULT_MEMORY_LAYERS),
    }

    try:
        signature = inspect.signature(session_state_cls)
    except (TypeError, ValueError):
        signature = None

    candidate_kwargs: dict[str, Any] = {}

    if signature is not None:
        for name in signature.parameters:
            if name == "self":
                continue

            if name in defaults:
                candidate_kwargs[name] = defaults[name]

    try:
        session_state = session_state_cls(**candidate_kwargs)
    except TypeError:
        session_state = session_state_cls()

    for field_name, field_value in defaults.items():
        if hasattr(session_state, field_name):
            current_value = getattr(session_state, field_name)
            if current_value in (None, "", []):
                setattr(session_state, field_name, field_value)

    return session_state


def _extract_session_mode(session_state: Any, fallback_mode: str | None) -> str | None:
    """
    Read one compact active-mode value from session state when available.
    """
    return _coerce_string(getattr(session_state, "active_mode", ""), "") or fallback_mode


def _extract_session_memory_classes(session_state: Any) -> list[str]:
    """
    Read one compact memory-class list from session state when available.
    """
    return _coerce_string_list(getattr(session_state, "memory_layers", []) or [])


def _invoke_runtime_handle_user_message(
    runtime_module: Any,
    *,
    message: str,
    session_state: Any,
    request_context: dict[str, Any] | None,
) -> Any:
    """
    Invoke the governed runtime while only passing optional compact-hint metadata
    when the runtime signature explicitly supports it.
    """
    handle_user_message = getattr(runtime_module, "handle_user_message", None)
    if not callable(handle_user_message):
        raise RuntimeError("core.runtime does not expose callable handle_user_message.")

    if not request_context:
        return handle_user_message(message, session_state)

    try:
        signature = inspect.signature(handle_user_message)
    except (TypeError, ValueError):
        signature = None

    if signature is None:
        return handle_user_message(message, session_state)

    parameters = signature.parameters
    if "request_context" in parameters:
        return handle_user_message(
            message,
            session_state,
            request_context=request_context,
        )

    if "request_metadata" in parameters:
        return handle_user_message(
            message,
            session_state,
            request_metadata=request_context,
        )

    if "ui_surface" in parameters:
        return handle_user_message(
            message,
            session_state,
            ui_surface=request_context.get("ui_surface"),
        )

    return handle_user_message(message, session_state)


def _determine_locality(
    runtime_packet: dict[str, Any],
) -> LocalityState:
    """
    Determine locality from runtime/model-routing truth.
    """
    internal_result = _as_mapping(runtime_packet.get("internal_result", {}))
    model_routing = _as_mapping(runtime_packet.get("model_routing", {}))

    if _coerce_bool(internal_result.get("stayed_local"), False):
        return LocalityState.LOCAL

    if _coerce_bool(model_routing.get("stayed_local"), False):
        return LocalityState.LOCAL

    if internal_result or model_routing:
        return LocalityState.CROSSED_BOUNDARY

    return LocalityState.UNKNOWN


def _determine_approval_state(
    runtime_packet: dict[str, Any],
) -> tuple[ApprovalState, bool]:
    """
    Determine broad approval posture for the chat response.
    """
    policy_review = _as_mapping(runtime_packet.get("policy_review", {}))
    research = _as_mapping(runtime_packet.get("research", {}))

    if _coerce_string(research.get("state"), "") == "approval_required":
        return ApprovalState.NEEDED, True

    if "approval_required" in policy_review:
        approval_needed = _coerce_bool(policy_review.get("approval_required"), False)
        return (
            ApprovalState.NEEDED if approval_needed else ApprovalState.NOT_NEEDED,
            approval_needed,
        )

    return ApprovalState.UNKNOWN, False


def _build_trace_summary(runtime_packet: dict[str, Any]) -> TraceSummary:
    """
    Build compact trace data safe for UI inspection.
    """
    response = _as_mapping(runtime_packet.get("response", {}))
    log_status = _as_mapping(runtime_packet.get("log_status", {}))
    journal_status = _as_mapping(runtime_packet.get("journal_status", {}))

    log_written = bool(_coerce_string(log_status.get("path"), ""))
    journal_written = bool(_coerce_string(journal_status.get("path"), "")) and _coerce_bool(
        journal_status.get("journal_write_allowed"),
        False,
    )

    selected_role = _coerce_string(response.get("selected_model_role"), "")
    selected_runtime = _coerce_string(response.get("selected_runtime"), "")
    selected_model_runtime_tag = _coerce_string(
        response.get("selected_model_runtime_tag"),
        "",
    )

    route_used = selected_role or "chat_send"

    return TraceSummary(
        route_used=route_used,
        selected_role=selected_role or None,
        selected_runtime=selected_runtime or None,
        selected_model_runtime_tag=selected_model_runtime_tag or None,
        used_fallback=_coerce_bool(response.get("used_fallback"), False),
        log_written=log_written,
        journal_written=journal_written,
    )



def _message_requests_plot_artifact(message: str) -> bool:
    """
    Decide whether a user explicitly requested a simple plot artifact.

    This intentionally stays conservative. Data execution can create a saved
    data-summary artifact by default, but plot artifacts are created only when
    the user asks for a plot/chart/graph/visualization/figure.
    """
    lowered = _coerce_string(message, "").lower()
    trigger_terms = (
        "plot",
        "chart",
        "graph",
        "visualize",
        "visualise",
        "visualization",
        "visualisation",
        "bar chart",
        "make a figure",
        "show me a figure",
        "simple figure",
    )

    return any(term in lowered for term in trigger_terms)


def _build_artifact_summaries_for_chat_response(
    *,
    request_model: ChatSendRequest,
    runtime_packet: dict[str, Any],
) -> tuple[list[ArtifactSummary], list[str]]:
    """
    Build compact local artifact summaries for a chat response.

    Completed bounded local data execution can create a saved data_summary
    artifact. When the user explicitly asks for a plot/chart/graph/visualization,
    the bridge may also create one simple local SVG plot_image artifact from the
    completed numeric summary. These are local output receipts, not memory, not
    notebook execution, not arbitrary Python, not shell, not web, and not
    source-file mutation.
    """
    response = _as_mapping(runtime_packet.get("response", {}))
    data_execution = (
        _as_mapping(runtime_packet.get("data_execution", {}))
        or _as_mapping(response.get("data_execution", {}))
    )

    if not data_execution:
        return [], []

    if not _coerce_bool(data_execution.get("used"), False):
        return [], []

    status = _coerce_string(data_execution.get("status"), "").lower()
    if status != "completed":
        return [], []

    tool_kind = _coerce_string(data_execution.get("tool_kind"), "").lower()
    if tool_kind != "data_executor":
        return [], []

    operation = _coerce_string(data_execution.get("operation"), "").lower()
    if operation != "summarize_csv":
        return [], []

    artifact_summaries: list[ArtifactSummary] = []
    artifact_warnings: list[str] = []

    try:
        data_summary_record = create_data_summary_artifact(
            data_execution,
            request_id=request_model.request_id,
            conversation_id=request_model.conversation_id,
            project_id=request_model.project_id,
        )
        artifact_summaries.append(artifact_summary_from_record(data_summary_record))
    except ArtifactCreationError as exc:
        artifact_warnings.append(
            "Data execution completed, but local data-summary artifact saving was skipped: "
            f"{exc}"
        )
    except Exception as exc:
        LOGGER.exception("Data summary artifact creation failed", exc_info=exc)
        artifact_warnings.append(
            "Data execution completed, but local data-summary artifact saving failed: "
            f"{exc}"
        )

    if not _message_requests_plot_artifact(request_model.message):
        return artifact_summaries, artifact_warnings

    try:
        plot_build_result = build_numeric_summary_bar_svg(data_execution)

        if not getattr(plot_build_result, "ok", False):
            errors = list(getattr(plot_build_result, "errors", []) or [])
            reason = "; ".join(str(error) for error in errors if str(error).strip())
            artifact_warnings.append(
                "Data execution completed, but plot artifact creation was skipped: "
                + (reason or "plot builder did not return a completed result")
            )
            return artifact_summaries, artifact_warnings

        plot_record = create_plot_image_artifact(
            plot_build_result,
            request_id=request_model.request_id,
            conversation_id=request_model.conversation_id,
            project_id=request_model.project_id,
        )
        artifact_summaries.append(artifact_summary_from_record(plot_record))
    except ArtifactCreationError as exc:
        artifact_warnings.append(
            "Data execution completed, but local plot artifact saving was skipped: "
            f"{exc}"
        )
    except Exception as exc:
        LOGGER.exception("Plot artifact creation failed", exc_info=exc)
        artifact_warnings.append(
            "Data execution completed, but local plot artifact saving failed: "
            f"{exc}"
        )

    return artifact_summaries, artifact_warnings


def _translate_runtime_packet_to_chat_data(
    request_model: ChatSendRequest,
    runtime_packet: dict[str, Any],
) -> ChatSendResponseData:
    """
    Translate the governed runtime packet into ChatSendResponseData.

    This is translation only. It must not invent new runtime logic.
    """
    response = _as_mapping(runtime_packet.get("response", {}))
    artifact_summaries, artifact_warnings = _build_artifact_summaries_for_chat_response(
        request_model=request_model,
        runtime_packet=runtime_packet,
    )

    return ChatSendResponseData(
        user_message=request_model.message,
        response_text=_coerce_string(response.get("response_text"), ""),
        response_source=_normalize_chat_response_source(
            response.get("response_source"),
        ),
        invocation_status=_normalize_chat_invocation_status(
            response.get("invocation_status"),
        ),
        selected_model_role=_coerce_string(response.get("selected_model_role"), "") or None,
        selected_runtime=_coerce_string(response.get("selected_runtime"), "") or None,
        selected_model_runtime_tag=_coerce_string(
            response.get("selected_model_runtime_tag"),
            "",
        )
        or None,
        used_fallback=_coerce_bool(response.get("used_fallback"), False),
        fallback_from=_coerce_string(response.get("fallback_from"), "") or None,
        fallback_to=_coerce_string(response.get("fallback_to"), "") or None,
        caveats=list(response.get("caveats", []) or []) + artifact_warnings,
        approval_needed=False,
        approval_token=None,
        conversation_id=request_model.conversation_id,
        project_id=request_model.project_id,
        attached_context_summary=_build_attached_context_summary(
            runtime_packet.get("attached_context_packet")
            if isinstance(runtime_packet.get("attached_context_packet"), dict)
            else None
        ),
        mode_profile=(
            _as_mapping(runtime_packet.get("mode_profile", {}))
            or _as_mapping(response.get("mode_profile", {}))
            or None
        ),
        continuity={
            "conversation_id": request_model.conversation_id,
            "project_id": request_model.project_id,
            "restored_source_ids": list(
                _as_mapping(runtime_packet.get("context_receipt", {})).get("retrieved_ids", [])
            ),
            "admitted_source_ids": [
                str(item.get("candidate_id"))
                for item in _as_mapping(runtime_packet.get("context_receipt", {})).get("admitted", [])
                if isinstance(item, Mapping) and item.get("candidate_id")
            ],
        },
        workspace=_as_mapping(runtime_packet.get("global_workspace", {})) or None,
        context_receipt=_as_mapping(runtime_packet.get("context_receipt", {})) or None,
        research=_as_mapping(runtime_packet.get("research", {})) or None,
        governor=_as_mapping(runtime_packet.get("governor", {})) or None,
        compute=_as_mapping(runtime_packet.get("compute", {})) or None,
        operational_self_model=(
            _as_mapping(runtime_packet.get("operational_self_model", {})) or None
        ),
        data_execution=(
            _as_mapping(runtime_packet.get("data_execution", {}))
            or _as_mapping(response.get("data_execution", {}))
            or None
        ),
        math_execution=(
            _as_mapping(runtime_packet.get("math_execution", {}))
            or _as_mapping(response.get("math_execution", {}))
            or None
        ),
        repo_context=(
            _as_mapping(runtime_packet.get("repo_context", {}))
            or _as_mapping(response.get("repo_context", {}))
            or None
        ),
        code_patch_plan=(
            _as_mapping(runtime_packet.get("code_patch_plan", {}))
            or _as_mapping(response.get("code_patch_plan", {}))
            or None
        ),
        aider_worker=(
            _as_mapping(runtime_packet.get("aider_worker", {}))
            or _as_mapping(response.get("aider_worker", {}))
            or None
        ),
        artifacts=artifact_summaries,
    )


def _schema_payload(value: Any) -> dict[str, Any]:
    """
    Convert a schema object or mapping into JSON-safe compact payload.
    """
    if isinstance(value, Mapping):
        return dict(value)

    dump_method = getattr(value, "model_dump", None)
    if callable(dump_method):
        return dump_method(mode="json")

    dict_method = getattr(value, "dict", None)
    if callable(dict_method):
        return dict_method()

    return {}


def _build_tool_ledger_from_chat_data(
    chat_data: ChatSendResponseData,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Build compact tool-ledger truth from already-produced chat data.

    This only surfaces existing runtime truth. It does not execute tools,
    authorize tools, or expand capability.
    """
    tools_used: list[dict[str, Any]] = []
    extra: dict[str, Any] = {
        "files_attached": [],
        "files_used_count": 0,
        "file_chunks_used_count": 0,
        "file_parsers_used": [],
        "file_memory_promotion": False,
        "file_outward_sharing": False,
        "repo_context_status": None,
        "repo_context_files": [],
        "patch_plan_status": None,
        "patch_plan_files": [],
        "mutated_files": False,
        "shell_used": False,
        "git_mutation_used": False,
        "external_worker_used": False,
    }

    attached_summary = _as_mapping(chat_data.attached_context_summary)
    text_files = [
        item for item in attached_summary.get("files", []) or []
        if isinstance(item, Mapping)
    ]
    data_files = [
        item for item in attached_summary.get("data_files", []) or []
        if isinstance(item, Mapping)
    ]
    file_summaries: list[dict[str, Any]] = []
    parsers: list[str] = []
    chunks_used = 0
    for file_record in text_files + data_files:
        parser_used = _coerce_string(file_record.get("parser_used"), "")
        if parser_used:
            parsers.append(parser_used)
        selected_chunks = _coerce_int(file_record.get("selected_chunk_count"), 0)
        chunks_used += selected_chunks
        file_summaries.append(
            {
                "file_id": _coerce_string(file_record.get("file_id"), ""),
                "file_name": _coerce_string(
                    file_record.get("display_name") or file_record.get("file_name"),
                    "attached-file",
                ),
                "file_kind": _coerce_string(file_record.get("file_kind"), "unknown"),
                "status": _coerce_string(file_record.get("processing_state"), "ready"),
                "summary": "Attached local file context; contents are not dumped in trace.",
                "parser_used": parser_used,
                "chunks_created_count": _coerce_int(file_record.get("chunk_count"), 0),
                "chunks_used_count": selected_chunks,
                "memory_promotion_allowed": False,
                "outward_sharing_allowed": False,
                "trust_zone": "user_selected_local_file",
                "blocked_reason": "",
            }
        )
    extra["files_attached"] = file_summaries
    extra["files_used_count"] = len(file_summaries)
    extra["file_chunks_used_count"] = chunks_used
    extra["file_parsers_used"] = _dedupe_string_list(parsers)

    data_execution = _as_mapping(chat_data.data_execution)
    if _coerce_bool(data_execution.get("used"), False):
        tools_used.append(
            {
                "tool_key": "bounded_data_execution",
                "tool_label": "Bounded data execution",
                "tool_kind": _coerce_string(data_execution.get("tool_kind"), "data_executor"),
                "state": _coerce_string(data_execution.get("status"), "unknown"),
                "available": True,
                "used": True,
                "locality": "local",
                "boundary_kind": "local_selected_file",
                "operation": _coerce_string(data_execution.get("operation"), ""),
                "summary": "Read-only local data execution truth from chat response.",
                "input_count": _coerce_int(data_execution.get("row_count"), 0),
                "output_count": _coerce_int(data_execution.get("column_count"), 0),
                "mutated_files": False,
                "network_access_used": False,
                "private_context_sent": False,
                "shell_used": False,
                "git_mutation_used": False,
                "cloud_used": False,
                "warnings": list(data_execution.get("warnings", []) or []),
                "errors": list(data_execution.get("errors", []) or []),
            }
        )

    math_execution = _as_mapping(chat_data.math_execution)
    if _coerce_bool(math_execution.get("used"), False):
        tools_used.append(
            {
                "tool_key": "bounded_math_execution",
                "tool_label": "Bounded math execution",
                "tool_kind": _coerce_string(math_execution.get("tool_kind"), "math_executor"),
                "state": _coerce_string(math_execution.get("status"), "unknown"),
                "available": True,
                "used": True,
                "approval_required": _coerce_bool(math_execution.get("approval_required"), False),
                "approval_state": "not_needed",
                "locality": "local",
                "boundary_kind": "local",
                "operation": _coerce_string(math_execution.get("operation"), ""),
                "summary": "Bounded local math execution truth from chat response.",
                "input_count": 1,
                "output_count": 1 if _coerce_string(math_execution.get("result"), "") else 0,
                "mutated_files": False,
                "network_access_used": False,
                "private_context_sent": False,
                "shell_used": False,
                "git_mutation_used": False,
                "cloud_used": False,
                "warnings": list(math_execution.get("warnings", []) or []),
                "errors": list(math_execution.get("errors", []) or []),
            }
        )

    repo_context = _as_mapping(chat_data.repo_context)
    if _coerce_bool(repo_context.get("used"), False):
        repo_status = _coerce_string(repo_context.get("status"), "unknown")
        repo_files = [
            _coerce_string(value, "")
            for value in list(repo_context.get("safe_tree_entries", []) or [])[:10]
            if _coerce_string(value, "")
        ]
        extra["repo_context_status"] = repo_status
        extra["repo_context_files"] = repo_files
        tools_used.append(
            {
                "tool_key": "repo_context",
                "tool_label": "Repo context",
                "tool_kind": _coerce_string(repo_context.get("tool_kind"), "repo_context_gatherer"),
                "state": repo_status,
                "available": True,
                "used": True,
                "approval_required": _coerce_bool(repo_context.get("approval_required"), False),
                "locality": "local",
                "boundary_kind": "local_selected_repo",
                "operation": _coerce_string(repo_context.get("operation"), "gather_repo_context"),
                "summary": "Read-only selected-repo context was surfaced.",
                "input_count": len(repo_files),
                "output_count": len(repo_files),
                "mutated_files": False,
                "network_access_used": _coerce_bool(repo_context.get("network_access_used"), False),
                "private_context_sent": False,
                "shell_used": _coerce_bool(repo_context.get("shell_used"), False),
                "git_mutation_used": False,
                "cloud_used": False,
                "warnings": list(repo_context.get("warnings", []) or []),
                "errors": list(repo_context.get("errors", []) or []),
            }
        )

    code_patch_plan = _as_mapping(chat_data.code_patch_plan)
    if _coerce_bool(code_patch_plan.get("used"), False):
        patch_status = _coerce_string(code_patch_plan.get("status"), "unknown")
        patch_files = [
            _coerce_string(value, "")
            for value in list(code_patch_plan.get("files_to_touch", []) or [])[:10]
            if _coerce_string(value, "")
        ]
        extra["patch_plan_status"] = patch_status
        extra["patch_plan_files"] = patch_files
        tools_used.append(
            {
                "tool_key": "code_patch_plan",
                "tool_label": "Code patch plan",
                "tool_kind": _coerce_string(code_patch_plan.get("tool_kind"), "code_patch_formatter"),
                "state": patch_status,
                "available": True,
                "used": True,
                "approval_required": _coerce_bool(code_patch_plan.get("approval_needed"), True),
                "approval_state": "needed",
                "locality": "local",
                "boundary_kind": "local_selected_repo",
                "operation": _coerce_string(code_patch_plan.get("operation"), "format_code_patch_plan"),
                "summary": _coerce_string(code_patch_plan.get("summary"), "Proposal-only patch plan."),
                "input_count": len(patch_files),
                "output_count": len(patch_files),
                "mutated_files": False,
                "network_access_used": False,
                "private_context_sent": False,
                "shell_used": False,
                "git_mutation_used": False,
                "cloud_used": False,
                "warnings": list(code_patch_plan.get("warnings", []) or []),
                "errors": list(code_patch_plan.get("errors", []) or []),
            }
        )

    aider_worker = _as_mapping(chat_data.aider_worker)
    if _coerce_bool(aider_worker.get("used"), False):
        tools_used.append(
            {
                "tool_key": "aider_worker_dry_run",
                "tool_label": "Aider worker dry-run",
                "tool_kind": "aider_worker",
                "state": _coerce_string(aider_worker.get("status"), "unknown"),
                "available": True,
                "used": True,
                "approval_required": _coerce_bool(aider_worker.get("approval_required"), True),
                "approval_state": "needed",
                "locality": "local",
                "boundary_kind": "local_selected_repo",
                "worker_name": "aider_worker",
                "operation": "dry_run_validation",
                "summary": "Aider worker skeleton validation surfaced without invoking Aider.",
                "input_count": len(list(aider_worker.get("files_considered", []) or [])),
                "output_count": len(list(aider_worker.get("files_proposed", []) or [])),
                "mutated_files": False,
                "network_access_used": False,
                "private_context_sent": False,
                "shell_used": False,
                "git_mutation_used": False,
                "cloud_used": False,
                "warnings": list(aider_worker.get("warnings", []) or []),
                "errors": list(aider_worker.get("errors", []) or []),
            }
        )

    return tools_used, extra


def _coerce_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _update_request_ledger_from_chat_data(
    *,
    request_id: str,
    chat_data: ChatSendResponseData,
) -> None:
    tools_used, extra = _build_tool_ledger_from_chat_data(chat_data)
    artifacts = [_schema_payload(artifact) for artifact in chat_data.artifacts]
    math_execution = _as_mapping(chat_data.math_execution)
    math_used = _coerce_bool(math_execution.get("used"), False)

    _safe_trace_call(
        "update_request_trace_ledger_snapshot.chat_data",
        update_request_trace_ledger_snapshot,
        request_id=request_id,
        tools_used=tools_used,
        files_attached=extra["files_attached"],
        artifacts=artifacts,
        files_used_count=extra["files_used_count"],
        file_chunks_used_count=extra["file_chunks_used_count"],
        file_parsers_used=extra["file_parsers_used"],
        file_memory_promotion=extra["file_memory_promotion"],
        file_outward_sharing=extra["file_outward_sharing"],
        repo_context_status=extra["repo_context_status"],
        repo_context_files=extra["repo_context_files"],
        patch_plan_status=extra["patch_plan_status"],
        patch_plan_files=extra["patch_plan_files"],
        mutated_files=extra["mutated_files"],
        shell_used=extra["shell_used"],
        git_mutation_used=extra["git_mutation_used"],
        external_worker_used=extra["external_worker_used"],
    )

    if math_used:
        _safe_trace_call(
            "update_request_trace_snapshot.math_execution",
            update_request_trace_snapshot,
            request_id=request_id,
            execution_tool_kind=_coerce_string(
                math_execution.get("tool_kind"),
                "math_executor",
            ),
            execution_status=_coerce_string(math_execution.get("status"), "unknown"),
            execution_operation=_coerce_string(math_execution.get("operation"), ""),
            execution_summary="Bounded local math execution was used.",
        )


def _determine_envelope_status(
    runtime_packet: dict[str, Any],
    chat_data: ChatSendResponseData,
) -> EnvelopeStatus:
    """
    Determine the envelope request-outcome status for /chat/send.
    """
    runtime_status = _coerce_string(runtime_packet.get("status"), "")
    invocation_status = chat_data.invocation_status
    response_source = chat_data.response_source

    if invocation_status == ChatInvocationStatus.BLOCKED:
        return EnvelopeStatus.BLOCKED

    if runtime_status != "ok_local_runtime":
        return EnvelopeStatus.ERROR

    if chat_data.used_fallback:
        return EnvelopeStatus.DEGRADED

    if response_source == ChatResponseSource.SCAFFOLD_FALLBACK:
        return EnvelopeStatus.DEGRADED

    return EnvelopeStatus.OK


def _determine_capability_state(envelope_status: EnvelopeStatus) -> CapabilityState:
    """
    Determine capability truth for the chat/send path based on bridge/runtime outcome.
    """
    if envelope_status == EnvelopeStatus.OK:
        return CapabilityState.LIVE

    if envelope_status == EnvelopeStatus.BLOCKED:
        return CapabilityState.LIVE

    if envelope_status == EnvelopeStatus.DEGRADED:
        return CapabilityState.DEGRADED

    if envelope_status == EnvelopeStatus.UNAVAILABLE:
        return CapabilityState.UNAVAILABLE

    return CapabilityState.UNKNOWN


def _build_error_envelope(
    *,
    request_id: str,
    status: EnvelopeStatus,
    detail: str,
    capability_state: CapabilityState,
    locality: LocalityState = LocalityState.LOCAL,
) -> dict[str, Any]:
    """
    Build a structured error/unavailable envelope for bridge-layer failures.
    """
    envelope = build_response_envelope(
        status=status,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="chat_response",
        capability_state=capability_state,
        locality=locality,
        approval_state=ApprovalState.UNKNOWN,
        warnings=[],
        errors=[detail],
        trace_summary=TraceSummary(
            route_used="runtime_bridge.send_chat_request",
            log_written=False,
            journal_written=False,
        ),
        data={},
    )
    return envelope.to_payload()


def _cache_runtime_bridge_state(
    *,
    request_id: str,
    runtime_packet: dict[str, Any],
    envelope_payload: dict[str, Any],
) -> None:
    """
    Cache the last-known runtime packet and chat envelope for status/trace surfaces.
    """
    global LAST_RUNTIME_PACKET
    global LAST_CHAT_RUNTIME_PACKET
    global LAST_RUNTIME_RESULT
    global LAST_CHAT_RESULT
    global LAST_CHAT_ENVELOPE
    global LAST_CHAT_RESPONSE_ENVELOPE

    runtime_snapshot = deepcopy(runtime_packet)
    runtime_snapshot["request_id"] = request_id
    runtime_snapshot["timestamp_utc"] = _coerce_string(
        envelope_payload.get("timestamp_utc"),
        "",
    )

    LAST_RUNTIME_PACKET = runtime_snapshot
    LAST_CHAT_RUNTIME_PACKET = deepcopy(runtime_snapshot)
    LAST_RUNTIME_RESULT = deepcopy(runtime_snapshot)
    LAST_CHAT_RESULT = deepcopy(runtime_snapshot)
    LAST_CHAT_ENVELOPE = deepcopy(envelope_payload)
    LAST_CHAT_RESPONSE_ENVELOPE = deepcopy(envelope_payload)


def _build_bridge_error_runtime_packet(
    *,
    request_id: str,
    status: str,
    detail: str,
) -> dict[str, Any]:
    """
    Build one compact bridge-visible runtime packet for early error caching.

    This is not a fake runtime success packet. It is only a modest snapshot so
    later inspection surfaces do not lose the final bridge-visible failure truth.
    """
    return {
        "status": status,
        "request_id": request_id,
        "internal_result": {
            "error": detail,
        },
        "response": {
            "response_text": "",
            "response_source": ChatResponseSource.SCAFFOLD_FALLBACK.value,
            "invocation_status": ChatInvocationStatus.ERROR.value,
            "selected_model_role": "",
            "selected_runtime": "",
            "selected_model_runtime_tag": "",
            "used_fallback": False,
            "fallback_from": "",
            "fallback_to": "",
            "caveats": [],
        },
        "policy_review": {},
        "log_status": {},
        "journal_status": {},
    }


def _finalize_bridge_error(
    *,
    request_id: str,
    status: EnvelopeStatus,
    detail: str,
    capability_state: CapabilityState,
    locality: LocalityState = LocalityState.LOCAL,
) -> dict[str, Any]:
    """
    Build and cache one final bridge-visible error envelope.
    """
    envelope_payload = _build_error_envelope(
        request_id=request_id,
        status=status,
        detail=detail,
        capability_state=capability_state,
        locality=locality,
    )

    _cache_runtime_bridge_state(
        request_id=request_id,
        runtime_packet=_build_bridge_error_runtime_packet(
            request_id=request_id,
            status=status.value,
            detail=detail,
        ),
        envelope_payload=envelope_payload,
    )

    return envelope_payload


def send_chat_request(payload_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Accept one /chat/send request payload, call the real governed runtime, and
    return a structured response-envelope payload.

    This bridge is an adapter, not a second runtime.
    """
    normalized_payload = dict(payload_dict)
    request_id = _resolve_request_id(normalized_payload)
    normalized_payload["request_id"] = request_id

    selected_mode_hint = (
        _coerce_string(normalized_payload.get("requested_mode"), "")
        or _coerce_string(normalized_payload.get("mode_requested"), "")
        or None
    )
    related_conversation_id_hint = _coerce_string(
        normalized_payload.get("conversation_id"),
        "",
    ) or None
    related_project_id_hint = _coerce_string(normalized_payload.get("project_id"), "") or None
    ui_surface_hint = _coerce_string(normalized_payload.get("ui_surface"), "") or None
    is_quick_invoke = _is_quick_invoke_surface(ui_surface_hint)

    _safe_trace_call(
        "start_request_trace",
        start_request_trace,
        request_id=request_id,
        route_used="runtime_bridge.send_chat_request",
        selected_mode=selected_mode_hint,
        related_conversation_id=related_conversation_id_hint,
        related_project_id=related_project_id_hint,
        ui_surface=ui_surface_hint,
        phase="preparing_request",
        label="Preparing governed request",
        detail="The bridge is preparing a governed local request trace.",
    )

    _safe_trace_call(
        "update_request_trace_snapshot.initial_request_context",
        update_request_trace_snapshot,
        request_id=request_id,
        route_used="runtime_bridge.send_chat_request",
        ui_surface=ui_surface_hint,
        selected_mode=selected_mode_hint,
        related_conversation_id=related_conversation_id_hint,
        related_project_id=related_project_id_hint,
        warnings=[],
        errors=[],
    )

    _safe_trace_call(
        "append_request_trace_event.validate_request",
        append_request_trace_event,
        request_id=request_id,
        phase="validating_request",
        label="Validating request payload",
        detail="The bridge is validating and normalizing the incoming chat request.",
        selected_mode=selected_mode_hint,
    )

    try:
        request_model = ChatSendRequest(**normalized_payload)
    except ValidationError as exc:
        detail = f"Chat request validation failed: {exc}"
        _safe_trace_call(
            "mark_request_trace_error.validation",
            mark_request_trace_error,
            request_id=request_id,
            phase="validation_failed",
            label="Validation failed",
            detail=detail,
            selected_mode=selected_mode_hint,
            related_conversation_id=related_conversation_id_hint,
            related_project_id=related_project_id_hint,
            errors=[detail],
        )
        return _finalize_bridge_error(
            request_id=request_id,
            status=EnvelopeStatus.ERROR,
            detail=detail,
            capability_state=CapabilityState.UNKNOWN,
        )

    selected_mode_hint = (
        _coerce_string(request_model.requested_mode, "")
        or _coerce_string(request_model.mode_requested, "")
        or None
    )

    _safe_trace_call(
        "update_request_trace_snapshot.validated_request",
        update_request_trace_snapshot,
        request_id=request_id,
        route_used="runtime_bridge.send_chat_request",
        ui_surface=ui_surface_hint,
        selected_mode=selected_mode_hint,
        related_conversation_id=request_model.conversation_id,
        related_project_id=request_model.project_id,
    )

    try:
        runtime_module = _load_runtime_module()
    except Exception as exc:
        LOGGER.exception("Failed to import core.runtime", exc_info=exc)
        detail = f"Local runtime path is unavailable: {exc}"
        _safe_trace_call(
            "mark_request_trace_error.runtime_import",
            mark_request_trace_error,
            request_id=request_id,
            phase="runtime_unavailable",
            label="Local runtime unavailable",
            detail=detail,
            selected_mode=selected_mode_hint,
            related_conversation_id=request_model.conversation_id,
            related_project_id=request_model.project_id,
            errors=[detail],
        )
        return _finalize_bridge_error(
            request_id=request_id,
            status=EnvelopeStatus.UNAVAILABLE,
            detail=detail,
            capability_state=CapabilityState.UNAVAILABLE,
        )

    try:
        memory_layers = _build_memory_layers_for_surface(
            is_quick_invoke=is_quick_invoke,
            has_project_context=bool(request_model.project_id),
        )
        inbound_request_context = _as_mapping(request_model.request_context)
        if request_model.mode_requested and "mode_requested" not in inbound_request_context:
            inbound_request_context["mode_requested"] = request_model.mode_requested
        attached_file_ids = _extract_attached_file_ids(inbound_request_context)
        attached_context_packet = (
            build_attached_file_context_packet(attached_file_ids)
            if attached_file_ids
            else None
        )
        profile_context = _load_visible_profile_context()
        runtime_request_context = _build_runtime_request_context(
            is_quick_invoke=is_quick_invoke,
            ui_surface_hint=ui_surface_hint,
            inbound_request_context=inbound_request_context,
            attached_context_packet=attached_context_packet,
            profile_context=profile_context,
            request_id=request_id,
            conversation_id=request_model.conversation_id,
            project_id=request_model.project_id,
        )
        if runtime_request_context is None:
            runtime_request_context = {}
        runtime_request_context["requested_gear"] = request_model.requested_gear or "automatic"
        effective_message = _build_effective_runtime_message(
            user_message=request_model.message,
            attached_context_packet=attached_context_packet,
        )
        session_build_detail = (
            "The bridge is preparing a compact governed session shell for Quick Invoke."
            if is_quick_invoke
            else "The bridge is preparing the minimal session shell for the governed runtime."
        )

        _safe_trace_call(
            "append_request_trace_event.build_session_state",
            append_request_trace_event,
            request_id=request_id,
            phase="building_session_state",
            label="Building session state",
            detail=session_build_detail,
            selected_mode=selected_mode_hint,
            memory_classes=memory_layers,
        )

        session_state = _build_session_state(
            runtime_module,
            active_mode=selected_mode_hint or DEFAULT_ACTIVE_MODE,
            autonomy_level=authoritative_autonomy_level(default=1),
            memory_layers=memory_layers,
        )
        active_mode = _extract_session_mode(session_state, selected_mode_hint)
        memory_classes = _extract_session_memory_classes(session_state)

        _safe_trace_call(
            "update_request_trace_snapshot.session_state_ready",
            update_request_trace_snapshot,
            request_id=request_id,
            selected_mode=active_mode,
            related_conversation_id=request_model.conversation_id,
            related_project_id=request_model.project_id,
            memory_classes=memory_classes,
        )

        _safe_trace_call(
            "append_request_trace_event.checking_policy_posture",
            append_request_trace_event,
            request_id=request_id,
            phase="checking_policy_posture",
            label="Checking broad policy posture",
            detail=(
                "The bridge is entering the governed runtime path with a compact Quick Invoke session posture."
                if is_quick_invoke
                else "The bridge is entering the governed runtime path with current default session posture."
            ),
            selected_mode=active_mode,
            memory_classes=memory_classes,
        )

        _safe_trace_call(
            "append_request_trace_event.invoking_runtime",
            append_request_trace_event,
            request_id=request_id,
            phase="invoking_runtime",
            label="Invoking governed runtime",
            detail=(
                "The request is now inside the local runtime path with compact Quick Invoke hints."
                if is_quick_invoke
                else "The request is now inside the local runtime path."
            ),
            selected_mode=active_mode,
            memory_classes=memory_classes,
        )

        runtime_result = _invoke_runtime_handle_user_message(
            runtime_module,
            message=effective_message,
            session_state=session_state,
            request_context=runtime_request_context,
        )

        if attached_context_packet is not None:
            runtime_result["attached_context_packet"] = attached_context_packet

    except Exception as exc:
        LOGGER.exception("Runtime bridge failed while calling core.runtime", exc_info=exc)
        detail = f"Local runtime bridge encountered an unexpected error: {exc}"
        _safe_trace_call(
            "mark_request_trace_error.runtime_call",
            mark_request_trace_error,
            request_id=request_id,
            phase="runtime_error",
            label="Runtime call failed",
            detail=detail,
            selected_mode=selected_mode_hint,
            memory_classes=locals().get("memory_classes", []),
            related_conversation_id=request_model.conversation_id,
            related_project_id=request_model.project_id,
            errors=[detail],
        )
        return _finalize_bridge_error(
            request_id=request_id,
            status=EnvelopeStatus.ERROR,
            detail=detail,
            capability_state=CapabilityState.UNKNOWN,
        )

    if not isinstance(runtime_result, dict):
        detail = "Local runtime returned a non-dictionary result."
        _safe_trace_call(
            "mark_request_trace_error.runtime_non_mapping",
            mark_request_trace_error,
            request_id=request_id,
            phase="runtime_result_invalid",
            label="Runtime output invalid",
            detail=detail,
            selected_mode=selected_mode_hint,
            related_conversation_id=request_model.conversation_id,
            related_project_id=request_model.project_id,
            errors=[detail],
        )
        return _finalize_bridge_error(
            request_id=request_id,
            status=EnvelopeStatus.ERROR,
            detail=detail,
            capability_state=CapabilityState.UNKNOWN,
        )

    _safe_trace_call(
        "append_request_trace_event.runtime_returned",
        append_request_trace_event,
        request_id=request_id,
        phase="runtime_returned",
        label="Runtime returned packet",
        detail="The governed runtime returned a packet to the bridge.",
        selected_mode=locals().get("active_mode", selected_mode_hint),
        memory_classes=locals().get("memory_classes", []),
    )

    try:
        _safe_trace_call(
            "append_request_trace_event.translating_runtime_packet",
            append_request_trace_event,
            request_id=request_id,
            phase="translating_runtime_packet",
            label="Translating runtime packet",
            detail=(
                "The bridge is translating the compact Quick Invoke runtime packet into the chat response schema."
                if is_quick_invoke
                else "The bridge is translating the runtime packet into the chat response schema."
            ),
            selected_mode=locals().get("active_mode", selected_mode_hint),
            memory_classes=locals().get("memory_classes", []),
        )

        chat_data = _translate_runtime_packet_to_chat_data(
            request_model,
            runtime_result,
        )
        profile_context_truth = _as_mapping(runtime_result.get("profile_context", {}))
        if profile_context_truth:
            chat_data.profile_context = {
                "used": True,
                "source": "sealed_identity_visible_projection",
                "fields": [
                    key for key in (
                        "name_or_username",
                        "interests",
                        "bio",
                        "profile_photo_asset_id",
                        "profile_photo_available",
                    )
                    if key in profile_context_truth
                ],
                "private_fields_included": False,
                "memory_import_allowed": False,
            }

        approval_state, approval_needed = _determine_approval_state(runtime_result)
        chat_data.approval_needed = approval_needed

        envelope_status = _determine_envelope_status(runtime_result, chat_data)
        capability_state = _determine_capability_state(envelope_status)
        locality = _determine_locality(runtime_result)
        trace_summary = _build_trace_summary(runtime_result)

        internal_result = _as_mapping(runtime_result.get("internal_result", {}))

        warnings = list(chat_data.caveats)
        attached_summary = chat_data.attached_context_summary or {}
        attached_warnings = attached_summary.get("warnings") if isinstance(attached_summary, dict) else []
        if isinstance(attached_warnings, list):
            warnings.extend(
                _coerce_string(warning, "")
                for warning in attached_warnings
                if _coerce_string(warning, "")
            )
        errors: list[str] = []

        internal_error = _coerce_string(internal_result.get("error"), "")
        if internal_error:
            errors.append(internal_error)

        if envelope_status == EnvelopeStatus.BLOCKED and not errors:
            errors.append("Request was blocked by current governed boundary rules.")

        _safe_trace_call(
            "update_request_trace_snapshot.translated_result",
            update_request_trace_snapshot,
            request_id=request_id,
            route_used="runtime_bridge.send_chat_request",
            ui_surface=ui_surface_hint,
            selected_mode=locals().get("active_mode", selected_mode_hint),
            selected_role=chat_data.selected_model_role,
            selected_runtime=chat_data.selected_runtime,
            selected_model_runtime_tag=chat_data.selected_model_runtime_tag,
            locality_state=locality.value,
            approval_state=approval_state.value,
            approval_needed=approval_needed,
            used_fallback=chat_data.used_fallback,
            mode_profile_key=_coerce_string(
                _as_mapping(chat_data.mode_profile).get("key"),
                "",
            )
            or None,
            mode_profile_label=_coerce_string(
                _as_mapping(chat_data.mode_profile).get("label"),
                "",
            )
            or None,
            mode_profile_used=_coerce_bool(
                _as_mapping(chat_data.mode_profile).get("used"),
                bool(chat_data.mode_profile),
            ),
            mode_profile_effects=_coerce_string_list(
                _as_mapping(chat_data.mode_profile).get("effects", [])
            ),
            mode_profile_warnings=_coerce_string_list(
                _as_mapping(chat_data.mode_profile).get("warnings", [])
            ),
            authority_granted_by_mode=False,
            memory_classes=locals().get("memory_classes", []),
            related_conversation_id=chat_data.conversation_id,
            related_project_id=chat_data.project_id,
            warnings=warnings,
            errors=errors,
        )

        _safe_trace_call(
            "update_request_trace_cognition_snapshot.translated_result",
            update_request_trace_cognition_snapshot,
            request_id=request_id,
            workspace=_as_mapping(chat_data.workspace),
            context_receipt=_as_mapping(chat_data.context_receipt),
        )

        _update_request_ledger_from_chat_data(
            request_id=request_id,
            chat_data=chat_data,
        )

        _safe_trace_call(
            "append_request_trace_event.finalizing_envelope",
            append_request_trace_event,
            request_id=request_id,
            phase="finalizing_envelope",
            label="Finalizing response envelope",
            detail="The bridge is preparing the final response payload for the API surface.",
            selected_mode=locals().get("active_mode", selected_mode_hint),
            selected_role=chat_data.selected_model_role,
            selected_runtime=chat_data.selected_runtime,
            selected_model_runtime_tag=chat_data.selected_model_runtime_tag,
            locality_state=locality.value,
            approval_state=approval_state.value,
            used_fallback=chat_data.used_fallback,
            memory_classes=locals().get("memory_classes", []),
        )

        envelope = build_response_envelope(
            status=envelope_status,
            request_id=request_id,
            api_version=API_VERSION,
            contract_version=CONTRACT_VERSION,
            result_type="chat_response",
            capability_state=capability_state,
            locality=locality,
            approval_state=approval_state,
            warnings=warnings,
            errors=errors,
            trace_summary=trace_summary,
            data=chat_data,
        )
        envelope_payload = envelope.to_payload()

        _safe_trace_call(
            "append_request_trace_event.caching_bridge_state",
            append_request_trace_event,
            request_id=request_id,
            phase="caching_bridge_state",
            label="Caching final bridge state",
            detail="The bridge is caching its final visible request state for later inspection surfaces.",
            selected_mode=locals().get("active_mode", selected_mode_hint),
            selected_role=chat_data.selected_model_role,
            selected_runtime=chat_data.selected_runtime,
            selected_model_runtime_tag=chat_data.selected_model_runtime_tag,
            locality_state=locality.value,
            approval_state=approval_state.value,
            used_fallback=chat_data.used_fallback,
        )

        _cache_runtime_bridge_state(
            request_id=request_id,
            runtime_packet=runtime_result,
            envelope_payload=envelope_payload,
        )

        if envelope_status == EnvelopeStatus.BLOCKED:
            _safe_trace_call(
                "mark_request_trace_blocked",
                mark_request_trace_blocked,
                request_id=request_id,
                phase="blocked",
                label="Blocked",
                detail="The governed request was blocked by current boundary or approval posture.",
                selected_mode=locals().get("active_mode", selected_mode_hint),
                selected_role=chat_data.selected_model_role,
                selected_runtime=chat_data.selected_runtime,
                selected_model_runtime_tag=chat_data.selected_model_runtime_tag,
                locality_state=locality.value,
                approval_state=approval_state.value,
                approval_needed=approval_needed,
                used_fallback=chat_data.used_fallback,
                memory_classes=locals().get("memory_classes", []),
                related_conversation_id=chat_data.conversation_id,
                related_project_id=chat_data.project_id,
                errors=errors,
                warnings=warnings,
            )
        elif envelope_status == EnvelopeStatus.DEGRADED:
            _safe_trace_call(
                "mark_request_trace_degraded",
                mark_request_trace_degraded,
                request_id=request_id,
                phase="completed_degraded",
                label="Completed in degraded path",
                detail="The governed request completed, but the visible path was degraded.",
                selected_mode=locals().get("active_mode", selected_mode_hint),
                selected_role=chat_data.selected_model_role,
                selected_runtime=chat_data.selected_runtime,
                selected_model_runtime_tag=chat_data.selected_model_runtime_tag,
                locality_state=locality.value,
                approval_state=approval_state.value,
                approval_needed=approval_needed,
                used_fallback=chat_data.used_fallback,
                memory_classes=locals().get("memory_classes", []),
                related_conversation_id=chat_data.conversation_id,
                related_project_id=chat_data.project_id,
                errors=errors,
                warnings=warnings,
            )
        elif envelope_status == EnvelopeStatus.OK:
            _safe_trace_call(
                "mark_request_trace_completed",
                mark_request_trace_completed,
                request_id=request_id,
                phase="completed",
                label="Completed",
                detail="The governed request completed its current bridge-visible path.",
                selected_mode=locals().get("active_mode", selected_mode_hint),
                selected_role=chat_data.selected_model_role,
                selected_runtime=chat_data.selected_runtime,
                selected_model_runtime_tag=chat_data.selected_model_runtime_tag,
                locality_state=locality.value,
                approval_state=approval_state.value,
                approval_needed=approval_needed,
                used_fallback=chat_data.used_fallback,
                memory_classes=locals().get("memory_classes", []),
                related_conversation_id=chat_data.conversation_id,
                related_project_id=chat_data.project_id,
                errors=errors,
                warnings=warnings,
            )
        else:
            _safe_trace_call(
                "mark_request_trace_error.unexpected_status",
                mark_request_trace_error,
                request_id=request_id,
                phase="unexpected_status",
                label="Unexpected bridge outcome",
                detail="The bridge produced an unexpected terminal status.",
                selected_mode=locals().get("active_mode", selected_mode_hint),
                selected_role=chat_data.selected_model_role,
                selected_runtime=chat_data.selected_runtime,
                selected_model_runtime_tag=chat_data.selected_model_runtime_tag,
                locality_state=locality.value,
                approval_state=approval_state.value,
                approval_needed=approval_needed,
                used_fallback=chat_data.used_fallback,
                memory_classes=locals().get("memory_classes", []),
                related_conversation_id=chat_data.conversation_id,
                related_project_id=chat_data.project_id,
                errors=errors or ["Unexpected bridge status."],
                warnings=warnings,
            )

        return envelope_payload

    except Exception as exc:
        LOGGER.exception("Runtime result translation failed", exc_info=exc)
        detail = f"Runtime bridge could not translate runtime output cleanly: {exc}"
        _safe_trace_call(
            "mark_request_trace_error.translation",
            mark_request_trace_error,
            request_id=request_id,
            phase="translation_error",
            label="Translation failed",
            detail=detail,
            selected_mode=locals().get("active_mode", selected_mode_hint),
            memory_classes=locals().get("memory_classes", []),
            related_conversation_id=request_model.conversation_id,
            related_project_id=request_model.project_id,
            errors=[detail],
        )
        return _finalize_bridge_error(
            request_id=request_id,
            status=EnvelopeStatus.ERROR,
            detail=detail,
            capability_state=CapabilityState.UNKNOWN,
        )


__all__ = ("send_chat_request",)
