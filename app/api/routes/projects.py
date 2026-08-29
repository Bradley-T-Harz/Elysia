"""
Projects route module for the Elysia local API bridge.

This module owns:
- GET /projects
- POST /projects
- GET /projects/{project_id}
- POST /projects/select
- PATCH /projects/{project_id}
- DELETE /projects/{project_id}

It should stay thin:
- accept only modest route/query/body input
- call the local project service organ
- validate transport payloads through route-level schemas
- return structured envelopes

It must not become:
- a storage layer
- a runtime bridge
- a governance layer
- a capability catalog
- a dumping ground for project business logic
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from app.ids import new_id

from app.api.project_service import (
    ProjectNotFoundError,
    ProjectServiceError,
    ProjectStoreCorruptError,
    build_project_continuity_summary,
    create_project,
    delete_project,
    get_active_project_selection,
    get_project_detail,
    get_project_metadata,
    list_projects,
    select_active_project,
    update_project_metadata,
)
from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope

LOGGER = logging.getLogger(__name__)

API_VERSION = "1.0.0"
CONTRACT_VERSION = "phase1-ui-contract-1.0"
MAX_ROUTE_LIST_LIMIT = 500
MAX_ROUTE_CONVERSATION_LIMIT = 500

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
)


class ProjectSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_id: str
    owner_user_id: str | None = None
    name: str | None = None
    description: str | None = None
    created_at_utc: str | None = None
    updated_at_utc: str | None = None
    status: str | None = None
    conversation_count: int | None = 0
    notes_summary: str | None = None
    state_summary: str | None = None
    current_state: str | None = None
    latest_chunk: str | None = None
    project_notes: str | None = None
    milestones: list[dict[str, Any]] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    next_actions: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_questions: list[dict[str, Any]] = Field(default_factory=list)
    corrections: list[dict[str, Any]] = Field(default_factory=list)
    source_count: int | None = 0
    archived: bool | None = False

class ProjectConversationSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    conversation_id: str
    owner_user_id: str | None = None
    title: str | None = None
    created_at_utc: str | None = None
    updated_at_utc: str | None = None
    last_message_preview: str | None = None
    message_count: int | None = None
    current_mode: str | None = None
    current_role: str | None = None
    capability_state: str | None = None
    locality: str | None = None
    approval_state: str | None = None
    project_id: str | None = None
    archived: bool = False
    pinned: bool = False
    conversation_state: str | None = None

class ProjectListResponseData(BaseModel):
    projects: list[ProjectSummary]
    total: int
    active_project_id: str | None = None


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=280)


class ProjectCreateResponseData(BaseModel):
    project_id: str
    project: ProjectSummary
    active_project_id: str | None = None
    selected_at_utc: str | None = None
    created: bool = True


class ProjectDetailResponseData(BaseModel):
    project_id: str
    metadata: ProjectSummary
    related_conversations: list[ProjectConversationSummary]
    conversation_count: int
    notes_summary: str | None = None
    state_summary: str | None = None
    continuity_summary: dict[str, Any] = Field(default_factory=dict)
    source_count: int = 0
    active_project_id: str | None = None


class ProjectContinuityResponseData(BaseModel):
    project_id: str
    continuity_summary: dict[str, Any]
    active_project_id: str | None = None


class ProjectSelectionRequest(BaseModel):
    project_id: str | None = None


class ProjectSelectionResponseData(BaseModel):
    active_project_id: str | None = None
    selected_at_utc: str | None = None
    project: ProjectSummary | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=280)
    status: str | None = None
    notes_summary: str | None = Field(default=None, max_length=220)
    state_summary: str | None = Field(default=None, max_length=220)
    current_state: str | None = Field(default=None, max_length=280)
    latest_chunk: str | None = Field(default=None, max_length=120)
    project_notes: str | None = Field(default=None, max_length=280)
    milestones: list[dict[str, Any]] | None = None
    decisions: list[dict[str, Any]] | None = None
    blockers: list[dict[str, Any]] | None = None
    next_actions: list[dict[str, Any]] | None = None
    unresolved_questions: list[dict[str, Any]] | None = None
    corrections: list[dict[str, Any]] | None = None
    source_count: int | None = Field(default=None, ge=0)
    archived: bool | None = None


class ProjectUpdateResponseData(BaseModel):
    project_id: str
    project: ProjectSummary
    updated_fields: list[str]


class ProjectDeleteResponseData(BaseModel):
    project_id: str
    deleted: bool
    active_project_id: str | None = None


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


def _build_project_summary(payload: dict[str, Any]) -> ProjectSummary:
    """Validate one compact project summary payload."""
    return ProjectSummary(**payload)


def _build_project_conversation_summary(
    payload: dict[str, Any],
) -> ProjectConversationSummary:
    """Validate one related-conversation summary payload."""
    return ProjectConversationSummary(**payload)


@router.get("")
@router.get("/", include_in_schema=False)
async def get_projects(
    include_archived: bool = Query(
        default=False,
        description="Whether archived projects should be included.",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=MAX_ROUTE_LIST_LIMIT,
        description="Optional maximum number of projects to return.",
    ),
) -> dict[str, Any]:
    """
    Return the local project list for the Projects room.

    This route is intentionally modest:
    - no search grammar yet
    - no fake paging story
    - current active project selection included for room state
    """
    request_id = _new_request_id()

    try:
        project_rows = list_projects(
            include_archived=include_archived,
            limit=limit,
        )
        active_selection = get_active_project_selection()
    except ProjectStoreCorruptError as exc:
        LOGGER.exception("Project list store is corrupt", exc_info=exc)
        raise HTTPException(
            status_code=500,
            detail=f"Project store is corrupt: {exc}",
        ) from exc
    except ProjectServiceError as exc:
        LOGGER.exception("Project list route failed", exc_info=exc)
        raise HTTPException(
            status_code=500,
            detail=f"Project list is not available: {exc}",
        ) from exc

    project_models = [_build_project_summary(row) for row in project_rows]

    data_model = ProjectListResponseData(
        projects=project_models,
        total=len(project_models),
        active_project_id=active_selection.get("active_project_id"),
    )

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="project_list",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[],
        errors=[],
        trace_summary=_build_trace_summary("get_projects"),
        data=_model_to_payload(data_model),
    )
    return envelope.to_payload()


@router.post("")
@router.post("/", include_in_schema=False)
async def create_one_project(
    payload: ProjectCreateRequest = Body(...),
) -> dict[str, Any]:
    """
    Create one local project container and select it as the active project.

    This route stays thin:
    - validate a modest create payload
    - call the project service organ
    - return structured envelope truth
    """
    request_id = _new_request_id()

    try:
        created_project = create_project(
            name=payload.name,
            description=payload.description,
        )
        selection = select_active_project(created_project["project_id"])
    except ProjectStoreCorruptError as exc:
        LOGGER.exception("Project create store is corrupt", exc_info=exc)
        raise HTTPException(
            status_code=500,
            detail=f"Project store is corrupt: {exc}",
        ) from exc
    except ProjectServiceError as exc:
        LOGGER.exception("Project create route failed", exc_info=exc)
        raise HTTPException(
            status_code=500,
            detail=f"Project could not be created: {exc}",
        ) from exc

    project_model = _build_project_summary(created_project)

    data_model = ProjectCreateResponseData(
        project_id=project_model.project_id,
        project=project_model,
        active_project_id=selection.get("active_project_id"),
        selected_at_utc=selection.get("selected_at_utc"),
        created=True,
    )

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="project_create",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[],
        errors=[],
        trace_summary=_build_trace_summary("create_one_project"),
        data=_model_to_payload(data_model),
    )
    return envelope.to_payload()


@router.get("/{project_id}")
async def get_one_project(
    project_id: str = Path(..., description="The local project identifier."),
    include_archived_conversations: bool = Query(
        default=False,
        description="Whether archived project conversations should be included.",
    ),
    conversation_limit: int | None = Query(
        default=None,
        ge=1,
        le=MAX_ROUTE_CONVERSATION_LIMIT,
        description="Optional maximum number of related conversations to return.",
    ),
) -> dict[str, Any]:
    """
    Return one local project detail payload.

    This is the backend truth surface for the future project detail room.
    """
    request_id = _new_request_id()

    try:
        detail_payload = get_project_detail(
            project_id,
            include_archived_conversations=include_archived_conversations,
            conversation_limit=conversation_limit,
        )
        active_selection = get_active_project_selection()
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' was not found.",
        ) from exc
    except ProjectStoreCorruptError as exc:
        LOGGER.exception(
            "Project '%s' is corrupt",
            project_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Project '{project_id}' is corrupt: {exc}",
        ) from exc
    except ProjectServiceError as exc:
        LOGGER.exception(
            "Project '%s' could not be loaded",
            project_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Project '{project_id}' is not available: {exc}",
        ) from exc

    try:
        metadata_model = _build_project_summary(detail_payload.get("metadata", {}))
        related_conversation_models = [
            _build_project_conversation_summary(item)
            for item in detail_payload.get("related_conversations", [])
        ]
        data_model = ProjectDetailResponseData(
            project_id=str(detail_payload.get("project_id") or project_id),
            metadata=metadata_model,
            related_conversations=related_conversation_models,
            conversation_count=int(detail_payload.get("conversation_count", 0) or 0),
            notes_summary=detail_payload.get("notes_summary"),
            state_summary=detail_payload.get("state_summary"),
            continuity_summary=detail_payload.get("continuity_summary") or {},
            source_count=int(detail_payload.get("source_count", 0) or 0),
            active_project_id=active_selection.get("active_project_id"),
        )
    except Exception as exc:
        LOGGER.exception(
            "Project '%s' failed route-level validation",
            project_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Project '{project_id}' failed route-level validation: {exc}",
        ) from exc

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="project_detail",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[],
        errors=[],
        trace_summary=_build_trace_summary("get_one_project"),
        data=_model_to_payload(data_model),
    )
    return envelope.to_payload()


@router.get("/{project_id}/continuity")
async def get_project_continuity(
    project_id: str = Path(..., description="The local project identifier."),
) -> dict[str, Any]:
    """Return compact project continuity truth for one local project."""
    request_id = _new_request_id()

    try:
        continuity = build_project_continuity_summary(project_id)
        active_selection = get_active_project_selection()
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' was not found.",
        ) from exc
    except ProjectServiceError as exc:
        LOGGER.exception("Project continuity route failed", exc_info=exc)
        raise HTTPException(
            status_code=500,
            detail=f"Project continuity is not available: {exc}",
        ) from exc

    data_model = ProjectContinuityResponseData(
        project_id=project_id,
        continuity_summary=continuity,
        active_project_id=active_selection.get("active_project_id"),
    )

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="project_continuity",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[],
        errors=[],
        trace_summary=_build_trace_summary("get_project_continuity"),
        data=_model_to_payload(data_model),
    )
    return envelope.to_payload()


@router.post("/select")
async def select_one_project(
    payload: ProjectSelectionRequest = Body(...),
) -> dict[str, Any]:
    """
    Persist the active-project selection locally.

    Passing null clears the active-project selection.
    """
    request_id = _new_request_id()

    try:
        selection = select_active_project(payload.project_id)
        selected_project_payload = (
            get_project_metadata(payload.project_id)
            if payload.project_id is not None
            else None
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{payload.project_id}' was not found.",
        ) from exc
    except ProjectStoreCorruptError as exc:
        LOGGER.exception("Project select store is corrupt", exc_info=exc)
        raise HTTPException(
            status_code=500,
            detail=f"Project store is corrupt: {exc}",
        ) from exc
    except ProjectServiceError as exc:
        LOGGER.exception("Project select route failed", exc_info=exc)
        raise HTTPException(
            status_code=500,
            detail=f"Project selection could not be updated: {exc}",
        ) from exc

    project_model = (
        _build_project_summary(selected_project_payload)
        if isinstance(selected_project_payload, dict)
        else None
    )

    data_model = ProjectSelectionResponseData(
        active_project_id=selection.get("active_project_id"),
        selected_at_utc=selection.get("selected_at_utc"),
        project=project_model,
    )

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="project_selection",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[],
        errors=[],
        trace_summary=_build_trace_summary("select_one_project"),
        data=_model_to_payload(data_model),
    )
    return envelope.to_payload()


@router.patch("/{project_id}")
async def patch_one_project(
    project_id: str,
    payload: ProjectUpdateRequest = Body(...),
) -> dict[str, Any]:
    """
    Update one persisted local project's compact metadata surface.

    This route stays thin:
    - validate through a modest mutation schema
    - call the project service organ
    - return structured envelope truth
    """
    request_id = _new_request_id()
    payload_dict = _model_to_payload(payload)
    updated_fields = sorted(
        key for key, value in payload_dict.items() if value is not None
    )

    try:
        updated_metadata = update_project_metadata(
            project_id,
            name=payload.name,
            description=payload.description,
            status=payload.status,
            notes_summary=payload.notes_summary,
            state_summary=payload.state_summary,
            current_state=payload.current_state,
            latest_chunk=payload.latest_chunk,
            project_notes=payload.project_notes,
            milestones=payload.milestones,
            decisions=payload.decisions,
            blockers=payload.blockers,
            next_actions=payload.next_actions,
            unresolved_questions=payload.unresolved_questions,
            corrections=payload.corrections,
            source_count=payload.source_count,
            archived=payload.archived,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' was not found.",
        ) from exc
    except ProjectStoreCorruptError as exc:
        LOGGER.exception(
            "Project '%s' could not be updated because the store is corrupt",
            project_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Project '{project_id}' is corrupt: {exc}",
        ) from exc
    except ProjectServiceError as exc:
        LOGGER.exception(
            "Project '%s' could not be updated",
            project_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Project '{project_id}' could not be updated: {exc}",
        ) from exc

    data_model = ProjectUpdateResponseData(
        project_id=str(updated_metadata.get("project_id") or project_id),
        project=_build_project_summary(updated_metadata),
        updated_fields=updated_fields,
    )

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="project_update",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[],
        errors=[],
        trace_summary=_build_trace_summary("patch_one_project"),
        data=_model_to_payload(data_model),
    )
    return envelope.to_payload()


@router.delete("/{project_id}")
async def delete_one_project(project_id: str) -> dict[str, Any]:
    """
    Delete one persisted local project container.

    This route stays downstream of the project service organ:
    it does not touch the filesystem directly and does not own frontend
    reselection behavior.
    """
    request_id = _new_request_id()

    try:
        delete_result = delete_project(project_id)
        active_selection = get_active_project_selection()
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' was not found.",
        ) from exc
    except ProjectStoreCorruptError as exc:
        LOGGER.exception(
            "Project '%s' could not be deleted because the store is corrupt",
            project_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Project '{project_id}' is corrupt: {exc}",
        ) from exc
    except ProjectServiceError as exc:
        LOGGER.exception(
            "Project '%s' could not be deleted",
            project_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Project '{project_id}' could not be deleted: {exc}",
        ) from exc

    data_model = ProjectDeleteResponseData(
        project_id=str(delete_result.get("project_id") or project_id),
        deleted=bool(delete_result.get("deleted")),
        active_project_id=active_selection.get("active_project_id"),
    )

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="project_delete",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[],
        errors=[],
        trace_summary=_build_trace_summary("delete_one_project"),
        data=_model_to_payload(data_model),
    )
    return envelope.to_payload()
