"""
File-ingestion routes for the Elysia local API bridge.

This route module exposes the first narrow HTTP surface for local file ingest.

It should stay thin:
- accept a JSON object
- validate modest request fields
- call file_ingest_service.attach_file
- wrap the schema-backed result in the standard response envelope

It must not:
- parse files itself
- scan folders
- promote files into memory
- call models or embeddings
- perform outward network actions
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.ids import new_id

from app.api import file_ingest_service
from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.api.schemas.files import (
    FileContextSummary,
    FileIngestResult,
    FileProcessingState,
)

API_VERSION = "1.0.0"
CONTRACT_VERSION = "phase1-ui-contract-1.0"

router = APIRouter(
    prefix="/files",
    tags=["files"],
)


def _new_request_id(prefix: str = "file") -> str:
    """
    Create a compact request identifier for file-route responses.
    """
    return new_id(prefix)


def _require_mapping_payload(payload: Any) -> dict[str, Any]:
    """
    Require that the incoming request body is a JSON object / mapping.
    """
    if not isinstance(payload, Mapping):
        raise HTTPException(
            status_code=400,
            detail="Request body for /files/attach must be a JSON object.",
        )

    return dict(payload)


def _clean_optional_string(value: Any) -> str | None:
    """
    Normalize one optional string-like value into None or stripped text.
    """
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _require_source_path(payload: dict[str, Any]) -> str:
    """
    Require a non-empty source_path field.
    """
    source_path = _clean_optional_string(payload.get("source_path"))

    if source_path is None:
        raise HTTPException(
            status_code=400,
            detail="Field 'source_path' is required and must be a non-empty string.",
        )

    return source_path


def _parse_positive_int(
    payload: dict[str, Any],
    key: str,
) -> int | None:
    """
    Parse one optional positive integer route parameter.
    """
    value = payload.get(key)

    if value is None:
        return None

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Field '{key}' must be a positive integer when provided.",
        ) from exc

    if parsed <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"Field '{key}' must be a positive integer when provided.",
        )

    return parsed


def _result_to_envelope_status(result: FileIngestResult) -> EnvelopeStatus:
    """
    Map a file-ingest result into the standard envelope status family.
    """
    if result.blocked or result.processing_state == FileProcessingState.BLOCKED:
        return EnvelopeStatus.BLOCKED

    if result.ready and result.processing_state == FileProcessingState.READY:
        return EnvelopeStatus.OK

    return EnvelopeStatus.ERROR


def _result_to_capability_state(result: FileIngestResult) -> CapabilityState:
    """
    Map file-ingest request outcome into broad capability truth.
    """
    if result.processing_state == FileProcessingState.FAILED:
        return CapabilityState.DEGRADED

    return CapabilityState.LIVE


def _result_to_approval_state(result: FileIngestResult) -> ApprovalState:
    """
    Map file-ingest request outcome into broad approval posture.
    """
    if result.blocked or result.processing_state == FileProcessingState.BLOCKED:
        return ApprovalState.DENIED

    return ApprovalState.NOT_NEEDED


def _build_file_ingest_envelope(result: FileIngestResult) -> dict[str, Any]:
    """
    Wrap a FileIngestResult in the standard local API response envelope.
    """
    envelope_status = _result_to_envelope_status(result)
    capability_state = _result_to_capability_state(result)
    approval_state = _result_to_approval_state(result)

    envelope = build_response_envelope(
        status=envelope_status,
        request_id=_new_request_id("fileattach"),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="file_ingest_result",
        capability_state=capability_state,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=list(result.warnings),
        errors=list(result.errors),
        trace_summary=TraceSummary(
            route_used="files.attach",
            log_written=False,
            journal_written=False,
        ),
        data=result.to_payload(),
    )
    return envelope.to_payload()


def _build_file_lookup_missing_envelope(
    *,
    file_id: str,
    result_type: str,
    route_used: str,
    error: str,
) -> dict[str, Any]:
    """
    Build an honest local lookup envelope for a missing file registry record.
    """
    envelope = build_response_envelope(
        status=EnvelopeStatus.ERROR,
        request_id=_new_request_id("filelookup"),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.DEGRADED,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[],
        errors=[error],
        trace_summary=TraceSummary(
            route_used=route_used,
            log_written=False,
            journal_written=False,
        ),
        data={
            "file_id": file_id,
            "found": False,
        },
    )
    return envelope.to_payload()


def _build_file_status_envelope(
    *,
    file_id: str,
    result: FileIngestResult | None,
) -> dict[str, Any]:
    """
    Wrap a file status lookup result in the standard local API envelope.
    """
    if result is None:
        return _build_file_lookup_missing_envelope(
            file_id=file_id,
            result_type="file_status",
            route_used="files.status",
            error=f"No file ingest record was found for file_id: {file_id}",
        )

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id("filestatus"),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="file_status",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=list(result.warnings),
        errors=list(result.errors),
        trace_summary=TraceSummary(
            route_used="files.status",
            log_written=False,
            journal_written=False,
        ),
        data=result.to_payload(),
    )
    return envelope.to_payload()


def _build_file_context_summary_envelope(
    *,
    file_id: str,
    summary: FileContextSummary | None,
) -> dict[str, Any]:
    """
    Wrap a file context-summary lookup result in the standard local API envelope.
    """
    if summary is None:
        return _build_file_lookup_missing_envelope(
            file_id=file_id,
            result_type="file_context_summary",
            route_used="files.context_summary",
            error=f"No file context summary was found for file_id: {file_id}",
        )

    envelope = build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_new_request_id("filecontext"),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="file_context_summary",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=list(summary.warnings),
        errors=list(summary.errors),
        trace_summary=TraceSummary(
            route_used="files.context_summary",
            log_written=False,
            journal_written=False,
        ),
        data=summary.to_payload(),
    )
    return envelope.to_payload()


@router.post("/attach")
async def attach_file_route(payload: Any = Body(...)) -> dict[str, Any]:
    """
    Attach and ingest one explicit user-selected local file.

    V0 delegates all file handling to file_ingest_service and only exposes the
    structured route/envelope surface.
    """
    payload_dict = _require_mapping_payload(payload)

    source_path = _require_source_path(payload_dict)
    conversation_id = _clean_optional_string(payload_dict.get("conversation_id"))
    project_id = _clean_optional_string(payload_dict.get("project_id"))
    max_size_bytes = _parse_positive_int(payload_dict, "max_size_bytes")
    chunk_char_limit = _parse_positive_int(payload_dict, "chunk_char_limit")

    kwargs: dict[str, Any] = {
        "conversation_id": conversation_id,
        "project_id": project_id,
    }

    if max_size_bytes is not None:
        kwargs["max_size_bytes"] = max_size_bytes

    if chunk_char_limit is not None:
        kwargs["chunk_char_limit"] = chunk_char_limit

    result = file_ingest_service.attach_file(
        source_path,
        **kwargs,
    )

    return _build_file_ingest_envelope(result)


@router.get("/{file_id}/status")
async def get_file_status_route(file_id: str) -> dict[str, Any]:
    """
    Return persisted local file-ingest status by file id.
    """
    clean_file_id = str(file_id).strip()
    result = file_ingest_service.get_file_status(clean_file_id)

    return _build_file_status_envelope(
        file_id=clean_file_id,
        result=result,
    )


@router.get("/{file_id}/context-summary")
async def get_file_context_summary_route(file_id: str) -> dict[str, Any]:
    """
    Return persisted local file-context summary by file id.
    """
    clean_file_id = str(file_id).strip()
    summary = file_ingest_service.get_file_context_summary(clean_file_id)

    return _build_file_context_summary_envelope(
        file_id=clean_file_id,
        summary=summary,
    )
