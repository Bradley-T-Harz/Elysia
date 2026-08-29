"""
Conversation route module for the Elysia local API bridge.

This module owns:
- GET /conversations
- GET /conversations/{conversation_id}
- PATCH /conversations/{conversation_id}
- DELETE /conversations/{conversation_id}

It should stay thin:
- accept only modest route/query/body input
- call the local conversation service organ
- validate transport payloads through the route schemas
- return structured envelopes

It must not become:
- a storage layer
- a runtime bridge
- a governance layer
- a capability catalog
- a dumping ground for thread business logic
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from app.ids import new_id

from app.api.conversation_service import (
    ConversationNotFoundError,
    ConversationServiceError,
    ConversationStoreCorruptError,
    delete_conversation,
    get_conversation_thread,
    list_conversations,
    update_conversation_metadata,
)
from app.api.project_service import (
    ProjectNotFoundError,
    ProjectServiceError,
    ProjectStoreCorruptError,
    get_project_metadata,
)
from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.conversation_history import (
    ConversationListItem,
    ConversationListResponseData,
    ConversationThreadResponseData,
)
from app.api.schemas.conversation_mutation import (
    ConversationUpdateRequest,
    ConversationUpdateResponseData,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope

LOGGER = logging.getLogger(__name__)

API_VERSION = "1.0.0"
CONTRACT_VERSION = "phase1-ui-contract-1.0"
MAX_ROUTE_LIST_LIMIT = 500

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
)


def _new_request_id(prefix: str = "req") -> str:
    """
    Create a compact request identifier for route-level envelope use.
    """
    return new_id(prefix)


def _model_to_payload(model: Any) -> dict[str, Any]:
    """
    Serialize a pydantic model in a way that tolerates v1/v2 differences.

    The route should validate with models but still return plain envelope payload
    dictionaries to FastAPI.
    """
    dump_method = getattr(model, "model_dump", None)
    if callable(dump_method):
        return dump_method(mode="json")

    dict_method = getattr(model, "dict", None)
    if callable(dict_method):
        return dict_method()

    if isinstance(model, dict):
        return dict(model)

    raise TypeError("Unable to serialize route model into dictionary form.")


def _build_trace_summary(route_used: str) -> TraceSummary:
    """Create a modest route-level trace summary for read-only surfaces."""
    return TraceSummary(
        route_used=route_used,
        log_written=False,
        journal_written=False,
    )


def _build_list_item(metadata: Any) -> ConversationListItem:
    """
    Build one validated conversation list item.

    For Stage 8 we derive last_message_role conservatively from the stored thread.
    If that derivation fails for a specific conversation, we keep the summary row
    but leave last_message_role unset rather than failing the whole list surface.
    """
    metadata_payload = _model_to_payload(metadata)
    conversation_id = str(metadata_payload.get("conversation_id", "")).strip()

    last_message_role: str | None = None
    if conversation_id:
        try:
            thread_payload = get_conversation_thread(conversation_id)
            raw_last_role = thread_payload.get("last_message_role")
            if isinstance(raw_last_role, str) and raw_last_role.strip():
                last_message_role = raw_last_role.strip()
        except ConversationServiceError as exc:
            LOGGER.warning(
                "Unable to derive last_message_role for conversation '%s': %s",
                conversation_id,
                exc,
            )

    return ConversationListItem(
        **metadata_payload,
        last_message_role=last_message_role,
    )


@router.get("")
@router.get("/", include_in_schema=False)
async def get_conversations(
    include_archived: bool = Query(
        default=False,
        description="Whether archived conversations should be included.",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=MAX_ROUTE_LIST_LIMIT,
        description="Optional maximum number of conversations to return.",
    ),
) -> dict[str, Any]:
    """
    Return the local conversation list for the Conversations room.

    This route is intentionally modest:
    - no mutation
    - no search grammar yet
    - no fake remote paging story
    """
    request_id = _new_request_id()

    try:
        metadata_items = list_conversations(
            include_archived=include_archived,
            limit=limit,
        )
    except ConversationStoreCorruptError as exc:
        LOGGER.exception("Conversation list store is corrupt", exc_info=exc)
        raise HTTPException(
            status_code=500,
            detail=f"Conversation store is corrupt: {exc}",
        ) from exc
    except ConversationServiceError as exc:
        LOGGER.exception("Conversation list route failed", exc_info=exc)
        raise HTTPException(
            status_code=500,
            detail=f"Conversation list is not available: {exc}",
        ) from exc

    list_items = [_build_list_item(metadata) for metadata in metadata_items]
    active_conversation_id = list_items[0].conversation_id if list_items else None

    data_model = ConversationListResponseData(
        conversations=list_items,
        total=len(list_items),
        active_conversation_id=active_conversation_id,
    )

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="conversation_list",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[],
        errors=[],
        trace_summary=_build_trace_summary("get_conversations"),
        data=_model_to_payload(data_model),
    )
    return envelope.to_payload()


@router.get("/{conversation_id}")
async def get_one_conversation(conversation_id: str) -> dict[str, Any]:
    """
    Return one persisted local conversation thread.

    This route exposes the stored thread shape for the Conversations room while
    remaining downstream of the local conversation service organ.
    """
    request_id = _new_request_id()

    try:
        thread_payload = get_conversation_thread(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation '{conversation_id}' was not found.",
        ) from exc
    except ConversationStoreCorruptError as exc:
        LOGGER.exception(
            "Conversation thread '%s' is corrupt",
            conversation_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Conversation '{conversation_id}' is corrupt: {exc}",
        ) from exc
    except ConversationServiceError as exc:
        LOGGER.exception(
            "Conversation thread '%s' could not be loaded",
            conversation_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Conversation '{conversation_id}' is not available: {exc}",
        ) from exc

    try:
        data_model = ConversationThreadResponseData(**thread_payload)
    except Exception as exc:
        LOGGER.exception(
            "Conversation thread '%s' failed route-level validation",
            conversation_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=(
                f"Conversation '{conversation_id}' failed route-level validation: {exc}"
            ),
        ) from exc

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="conversation_thread",
        capability_state=data_model.metadata.capability_state,
        locality=data_model.metadata.locality,
        approval_state=data_model.metadata.approval_state,
        warnings=[],
        errors=[],
        trace_summary=_build_trace_summary("get_one_conversation"),
        data=_model_to_payload(data_model),
    )
    return envelope.to_payload()


@router.patch("/{conversation_id}")
async def patch_one_conversation(
    conversation_id: str,
    payload: ConversationUpdateRequest = Body(...),
) -> dict[str, Any]:
    """
    Update one persisted local conversation's compact metadata surface.

    This route stays thin:
    - validate through the shared mutation schema
    - call the conversation service organ
    - return structured envelope truth
    """
    request_id = _new_request_id()
    payload_dict = _model_to_payload(payload)
    updated_fields = sorted(
        key for key, value in payload_dict.items() if value is not None
    )

    if payload.project_id is not None:
        try:
            get_project_metadata(payload.project_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Project '{payload.project_id}' was not found.",
            ) from exc
        except ProjectStoreCorruptError as exc:
            LOGGER.exception(
                "Conversation '%s' could not be moved because project '%s' is corrupt",
                conversation_id,
                payload.project_id,
                exc_info=exc,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Project '{payload.project_id}' is corrupt: {exc}",
            ) from exc
        except ProjectServiceError as exc:
            LOGGER.exception(
                "Conversation '%s' could not validate project '%s'",
                conversation_id,
                payload.project_id,
                exc_info=exc,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Project '{payload.project_id}' is not available: {exc}",
            ) from exc

    try:
        updated_metadata = update_conversation_metadata(
            conversation_id,
            title=payload.title,
            project_id=payload.project_id,
            pinned=payload.pinned,
            archived=payload.archived,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation '{conversation_id}' was not found.",
        ) from exc
    except ConversationStoreCorruptError as exc:
        LOGGER.exception(
            "Conversation '%s' could not be updated because the store is corrupt",
            conversation_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Conversation '{conversation_id}' is corrupt: {exc}",
        ) from exc
    except ConversationServiceError as exc:
        LOGGER.exception(
            "Conversation '%s' could not be updated",
            conversation_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Conversation '{conversation_id}' could not be updated: {exc}",
        ) from exc

    data_model = ConversationUpdateResponseData(
        conversation_id=updated_metadata.conversation_id,
        metadata=updated_metadata,
        updated_fields=updated_fields,
    )

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="conversation_update",
        capability_state=updated_metadata.capability_state,
        locality=updated_metadata.locality,
        approval_state=updated_metadata.approval_state,
        warnings=[],
        errors=[],
        trace_summary=_build_trace_summary("patch_one_conversation"),
        data=_model_to_payload(data_model),
    )
    return envelope.to_payload()


@router.delete("/{conversation_id}")
async def delete_one_conversation(conversation_id: str) -> dict[str, Any]:
    """
    Delete one persisted local conversation container.

    This route stays downstream of the conversation service organ:
    it does not touch the filesystem directly and does not own any frontend
    reselection behavior.
    """
    request_id = _new_request_id()

    try:
        delete_result = delete_conversation(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation '{conversation_id}' was not found.",
        ) from exc
    except ConversationStoreCorruptError as exc:
        LOGGER.exception(
            "Conversation '%s' could not be deleted because the store is corrupt",
            conversation_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Conversation '{conversation_id}' is corrupt: {exc}",
        ) from exc
    except ConversationServiceError as exc:
        LOGGER.exception(
            "Conversation '%s' could not be deleted",
            conversation_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Conversation '{conversation_id}' could not be deleted: {exc}",
        ) from exc

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="conversation_delete",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[],
        errors=[],
        trace_summary=_build_trace_summary("delete_one_conversation"),
        data={
            "conversation_id": delete_result.get("conversation_id"),
            "deleted": bool(delete_result.get("deleted")),
        },
    )
    return envelope.to_payload()
