"""
Chat route module for the Elysia local API bridge.

This module owns POST /chat/send.

It should stay thin:
- accept the request body
- validate it against the shared chat request schema
- ensure conversation continuity exists locally
- call the runtime bridge
- persist the resulting exchange locally
- lightly synchronize final request-trace snapshot truth when needed
- return the structured envelope produced downstream

It must not become a second runtime, second router, second governance layer,
or a request-trace controller.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from starlette.concurrency import run_in_threadpool

from app.api.conversation_service import (
    ConversationServiceError,
    ensure_conversation,
    record_chat_exchange_from_bridge_result,
)
from app.api.schemas.chat import ChatSendRequest
from app.cognition.emergency_control import bind_request_owner, release_request
from app.ids import new_id

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)


def _require_mapping_payload(payload: Any) -> dict[str, Any]:
    """
    Require that the incoming request body is a JSON object / mapping.
    """
    if not isinstance(payload, Mapping):
        raise HTTPException(
            status_code=400,
            detail="Request body for /chat/send must be a JSON object.",
        )

    return dict(payload)


def _model_to_payload(model: Any) -> dict[str, Any]:
    """
    Serialize a pydantic model in a way that tolerates v1/v2 differences.
    """
    dump_method = getattr(model, "model_dump", None)
    if callable(dump_method):
        return dump_method(mode="json")

    dict_method = getattr(model, "dict", None)
    if callable(dict_method):
        return dict_method()

    if isinstance(model, dict):
        return dict(model)

    raise HTTPException(
        status_code=500,
        detail="Chat route could not serialize the validated request payload.",
    )


def _clean_optional_string(value: Any) -> str | None:
    """
    Normalize one optional string-like value into None or stripped text.
    """
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _extract_optional_request_id(payload: dict[str, Any]) -> str | None:
    """
    Extract one optional client-supplied request_id from the raw request payload.
    """
    return _clean_optional_string(payload.get("request_id"))


def _parse_chat_request(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Validate the incoming request against the shared chat-send schema.
    """
    optional_request_id = _extract_optional_request_id(payload)

    try:
        request_model = ChatSendRequest(**payload)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Request body for /chat/send failed schema validation: {exc}",
        ) from exc

    normalized_payload = _model_to_payload(request_model)

    if optional_request_id and not _clean_optional_string(
        normalized_payload.get("request_id")
    ):
        normalized_payload["request_id"] = optional_request_id
    if not _clean_optional_string(normalized_payload.get("request_id")):
        normalized_payload["request_id"] = new_id("request")

    _require_message_field(normalized_payload)
    return normalized_payload


def _require_message_field(payload: dict[str, Any]) -> None:
    """
    Require a non-empty string message field.
    """
    message = payload.get("message", "")

    if not isinstance(message, str) or not message.strip():
        raise HTTPException(
            status_code=400,
            detail="Field 'message' is required and must be a non-empty string.",
        )


def _ensure_conversation_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """
    Ensure the request has a real local conversation container before runtime send.
    """
    try:
        metadata = ensure_conversation(
            conversation_id=payload.get("conversation_id"),
            project_id=payload.get("project_id"),
            requested_mode=payload.get("requested_mode"),
            requested_role=payload.get("requested_role"),
        )
    except ConversationServiceError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Conversation service is not available yet: {exc}",
        ) from exc

    normalized_payload = dict(payload)
    normalized_payload["conversation_id"] = metadata.conversation_id
    return normalized_payload, metadata.conversation_id


def _load_runtime_bridge() -> Any:
    """
    Import the runtime bridge lazily so this route module can exist before every
    downstream organ is finished.
    """
    try:
        return importlib.import_module("app.api.runtime_bridge")
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Runtime bridge is not available yet: {exc}",
        ) from exc


def _load_request_trace_service_optional() -> Any | None:
    """
    Import the request-trace service opportunistically.

    The chat route uses this only for light final snapshot synchronization.
    If the trace service is unavailable, chat/send should still work.
    """
    try:
        return importlib.import_module("app.api.request_trace_service")
    except Exception:
        return None


def _ensure_result_dict(result: Any) -> dict[str, Any]:
    """
    Require that the runtime bridge returns a structured dictionary envelope.
    """
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=500,
            detail="Runtime bridge returned a non-dictionary response.",
        )

    return result


def _ensure_result_data_mapping(result: dict[str, Any]) -> dict[str, Any]:
    """
    Ensure the result envelope has a mutable mapping data payload.
    """
    raw_data = result.get("data")
    if isinstance(raw_data, Mapping):
        data = dict(raw_data)
    else:
        data = {}

    result["data"] = data
    return data


def _ensure_result_request_id(
    result: dict[str, Any],
    request_payload: dict[str, Any],
) -> None:
    """
    Make sure the final route-visible envelope still carries the validated request_id.
    """
    existing_request_id = _clean_optional_string(result.get("request_id"))
    if existing_request_id:
        return

    request_id = _extract_optional_request_id(request_payload)
    if request_id:
        result["request_id"] = request_id


def _ensure_result_request_context(
    result: dict[str, Any],
    *,
    conversation_id: str,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Make sure response data retains the minimum request-linked truth the UI and
    persistence path depend on.
    """
    data = _ensure_result_data_mapping(result)

    if not data.get("conversation_id"):
        data["conversation_id"] = conversation_id

    request_project_id = _clean_optional_string(request_payload.get("project_id"))
    if request_project_id and not _clean_optional_string(data.get("project_id")):
        data["project_id"] = request_project_id

    return data


def _append_unique_warning(result: dict[str, Any], warning: str) -> None:
    """
    Append one warning to the envelope without duplicating it.
    """
    raw_warnings = result.get("warnings")
    warnings = list(raw_warnings) if isinstance(raw_warnings, list) else []

    if warning not in warnings:
        warnings.append(warning)

    result["warnings"] = warnings


def _mark_persistence_issue(
    result: dict[str, Any],
    *,
    conversation_id: str,
    warning: str,
) -> dict[str, Any]:
    """
    Surface a post-response persistence failure honestly without discarding a
    successful governed runtime response.
    """
    data = _ensure_result_data_mapping(result)
    if not data.get("conversation_id"):
        data["conversation_id"] = conversation_id

    _append_unique_warning(result, warning)

    status = str(result.get("status", "")).strip().lower()
    if status == "ok":
        result["status"] = "degraded"

    capability_state = str(result.get("capability_state", "")).strip().lower()
    if capability_state in {"", "live", "ok"}:
        result["capability_state"] = "degraded"

    return result


def _sync_request_trace_success(
    *,
    result: dict[str, Any],
    conversation_id: str,
    request_payload: dict[str, Any],
) -> None:
    """
    Lightly synchronize the final request trace snapshot after successful
    persistence.
    """
    request_trace_service = _load_request_trace_service_optional()
    if request_trace_service is None:
        return

    request_id = _clean_optional_string(result.get("request_id"))
    if not request_id:
        return

    data = _ensure_result_data_mapping(result)
    update_snapshot = getattr(request_trace_service, "update_request_trace_snapshot", None)
    if not callable(update_snapshot):
        return

    warnings = result.get("warnings")
    errors = result.get("errors")

    update_snapshot(
        request_id=request_id,
        selected_mode=_clean_optional_string(request_payload.get("requested_mode")),
        selected_role=_clean_optional_string(data.get("selected_model_role")),
        selected_runtime=_clean_optional_string(data.get("selected_runtime")),
        selected_model_runtime_tag=_clean_optional_string(
            data.get("selected_model_runtime_tag")
        ),
        locality_state=_clean_optional_string(result.get("locality")),
        approval_state=_clean_optional_string(result.get("approval_state")),
        approval_needed=bool(data.get("approval_needed"))
        if data.get("approval_needed") is not None
        else None,
        used_fallback=bool(data.get("used_fallback"))
        if data.get("used_fallback") is not None
        else None,
        related_conversation_id=conversation_id,
        related_project_id=_clean_optional_string(data.get("project_id")),
        warnings=list(warnings) if isinstance(warnings, list) else None,
        errors=list(errors) if isinstance(errors, list) else None,
    )


def _sync_request_trace_persistence_issue(
    *,
    result: dict[str, Any],
    conversation_id: str,
    warning: str,
    request_payload: dict[str, Any],
) -> None:
    """
    Lightly synchronize a persistence-caused degraded outcome into the request
    trace after the runtime bridge has already returned.
    """
    request_trace_service = _load_request_trace_service_optional()
    if request_trace_service is None:
        return

    request_id = _clean_optional_string(result.get("request_id"))
    if not request_id:
        return

    data = _ensure_result_data_mapping(result)
    mark_degraded = getattr(request_trace_service, "mark_request_trace_degraded", None)
    if not callable(mark_degraded):
        return

    warnings = result.get("warnings")
    errors = result.get("errors")

    mark_degraded(
        request_id=request_id,
        phase="persistence_degraded",
        label="Conversation persistence degraded",
        detail=warning,
        selected_mode=_clean_optional_string(request_payload.get("requested_mode")),
        selected_role=_clean_optional_string(data.get("selected_model_role")),
        selected_runtime=_clean_optional_string(data.get("selected_runtime")),
        selected_model_runtime_tag=_clean_optional_string(
            data.get("selected_model_runtime_tag")
        ),
        locality_state=_clean_optional_string(result.get("locality")),
        approval_state=_clean_optional_string(result.get("approval_state")),
        approval_needed=bool(data.get("approval_needed"))
        if data.get("approval_needed") is not None
        else None,
        used_fallback=bool(data.get("used_fallback"))
        if data.get("used_fallback") is not None
        else None,
        related_conversation_id=conversation_id,
        related_project_id=_clean_optional_string(data.get("project_id")),
        errors=list(errors) if isinstance(errors, list) else None,
        warnings=list(warnings) if isinstance(warnings, list) else [warning],
    )


@router.post("/send")
async def send_chat(payload: Any = Body(...)) -> dict[str, Any]:
    """
    Submit one governed chat request into the local runtime bridge.

    This route does not decide routing, policy, verification, logging,
    journaling, or capability truth. It validates the request, ensures the
    conversation container exists, forwards the normalized payload into the
    body-facing bridge, and then records the resulting exchange into the local
    conversation store when possible.
    """
    payload_dict = _require_mapping_payload(payload)
    normalized_payload = _parse_chat_request(payload_dict)
    normalized_payload, conversation_id = _ensure_conversation_payload(normalized_payload)

    runtime_bridge = _load_runtime_bridge()

    try:
        from app.api.account_service import get_authenticated_principal

        bind_request_owner(
            str(normalized_payload["request_id"]),
            str(get_authenticated_principal()["user_id"]),
        )
    except Exception:
        # The owning runtime/account boundary still rejects unauthenticated
        # work. Never fabricate an owner binding on failure.
        pass

    bridge_fn = getattr(runtime_bridge, "send_chat_request", None)
    if bridge_fn is None:
        raise HTTPException(
            status_code=503,
            detail="Runtime bridge does not expose send_chat_request yet.",
        )

    try:
        if inspect.iscoroutinefunction(bridge_fn):
            result = await bridge_fn(normalized_payload)
        else:
            # Model/research/tool work is synchronous today. Keep it off the event
            # loop so /emergency/stop remains responsive during an active request.
            result = await run_in_threadpool(bridge_fn, normalized_payload)
            if inspect.isawaitable(result):
                result = await result
    finally:
        # Idempotent on the success path (Core also releases). This closes the
        # cancellation registry when a provider/adapter raises unexpectedly.
        release_request(str(normalized_payload["request_id"]))

    result_dict = _ensure_result_dict(result)
    _ensure_result_request_id(result_dict, normalized_payload)
    result_data = _ensure_result_request_context(
        result_dict,
        conversation_id=conversation_id,
        request_payload=normalized_payload,
    )

    try:
        research = result_data.get("research")
        if isinstance(research, Mapping) and research.get("state") == "approval_required":
            # Approval interruption is request/governance truth, not a
            # conversation turn. Persist only after the exact approval has
            # been consumed and the real answer exists.
            persistence_result = {
                "conversation_id": conversation_id,
                "persistence_skipped": "research_egress_approval_pending",
            }
        else:
            persistence_result = record_chat_exchange_from_bridge_result(
                request_payload=normalized_payload,
                bridge_result=result_dict,
            )
        persisted_conversation_id = persistence_result.get("conversation_id")
        if isinstance(persisted_conversation_id, str) and persisted_conversation_id.strip():
            result_data["conversation_id"] = persisted_conversation_id

        _sync_request_trace_success(
            result=result_dict,
            conversation_id=result_data["conversation_id"],
            request_payload=normalized_payload,
        )

    except ConversationServiceError as exc:
        warning = (
            "Conversation exchange was returned, but local conversation persistence "
            f"did not complete: {exc}"
        )
        result_dict = _mark_persistence_issue(
            result_dict,
            conversation_id=conversation_id,
            warning=warning,
        )

        _sync_request_trace_persistence_issue(
            result=result_dict,
            conversation_id=result_data.get("conversation_id", conversation_id),
            warning=warning,
            request_payload=normalized_payload,
        )

    return result_dict
