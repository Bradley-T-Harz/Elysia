"""
Standard response envelope schema for the Elysia local API bridge.

This module is the Python-side implementation shape for the Stage 2 standard
response envelope. It should keep all routes and services aligned around one
shared outer response structure so the bridge does not drift into loose strings
or ad hoc dictionaries.

This file should stay narrow:
- shared trace-summary model
- shared response-envelope model
- small helper for envelope construction

It should not contain:
- service logic
- runtime logic
- governance logic
- endpoint-specific business rules
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field

from .common import (
    ApprovalState,
    CapabilityState,
    ElysiaSchemaModel,
    EnvelopeStatus,
    LocalityState,
)


def _utc_now_iso() -> str:
    """
    Return a compact UTC ISO-8601 timestamp suitable for envelope use.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


class TraceSummary(ElysiaSchemaModel):
    """
    Compact trace information safe for UI inspection.

    This is not raw logging. It is only the small structured subset the bridge
    may safely surface in envelopes.
    """

    route_used: str | None = None
    selected_role: str | None = None
    selected_runtime: str | None = None
    selected_model_runtime_tag: str | None = None
    used_fallback: bool | None = None
    log_written: bool | None = None
    journal_written: bool | None = None


class ResponseEnvelope(ElysiaSchemaModel):
    """
    Standard outer response wrapper for all Phase 1 local API endpoints.
    """

    status: EnvelopeStatus
    request_id: str = Field(
        ...,
        description="Unique request identifier for this API response.",
    )
    api_version: str = Field(
        ...,
        description="Version of the local API layer.",
    )
    contract_version: str = Field(
        ...,
        description="Version of the governing UI/API contract.",
    )
    timestamp_utc: str = Field(
        ...,
        description="UTC timestamp for when the response envelope was produced.",
    )
    result_type: str = Field(
        ...,
        description="Declares what kind of payload is inside data.",
    )
    capability_state: CapabilityState = Field(
        ...,
        description="Capability truth for the relevant feature/path referenced by this response.",
    )
    locality: LocalityState = Field(
        ...,
        description="Whether the relevant request/path stayed local or crossed a boundary.",
    )
    approval_state: ApprovalState = Field(
        ...,
        description="Approval posture relevant to this response.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal cautions or degradations.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Fatal or blocking issues associated with the request.",
    )
    trace_summary: TraceSummary | None = Field(
        default=None,
        description="Compact structured trace data safe for UI inspection.",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Endpoint-specific payload. Always present, even if empty.",
    )


def _normalize_data_payload(data: Any) -> dict[str, Any]:
    """
    Normalize endpoint-specific payloads into a plain mapping.

    Accepts:
    - plain dictionaries
    - ElysiaSchemaModel instances
    - None

    This helper is intentionally narrow so the envelope remains predictable.
    """
    if data is None:
        return {}

    if isinstance(data, ElysiaSchemaModel):
        return data.to_payload()

    if isinstance(data, dict):
        return data

    raise TypeError(
        "Envelope data must be a dict, an ElysiaSchemaModel instance, or None."
    )


def build_response_envelope(
    *,
    status: EnvelopeStatus,
    request_id: str,
    api_version: str,
    contract_version: str,
    result_type: str,
    capability_state: CapabilityState,
    locality: LocalityState,
    approval_state: ApprovalState,
    data: Any | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    trace_summary: TraceSummary | dict[str, Any] | None = None,
    timestamp_utc: str | None = None,
) -> ResponseEnvelope:
    """
    Build a ResponseEnvelope in one place so routes and services can stay aligned.

    This is a schema-construction helper, not a business-logic helper.
    """
    normalized_trace_summary: TraceSummary | None = None
    if isinstance(trace_summary, TraceSummary):
        normalized_trace_summary = trace_summary
    elif isinstance(trace_summary, dict):
        normalized_trace_summary = TraceSummary(**trace_summary)

    return ResponseEnvelope(
        status=status,
        request_id=request_id,
        api_version=api_version,
        contract_version=contract_version,
        timestamp_utc=timestamp_utc or _utc_now_iso(),
        result_type=result_type,
        capability_state=capability_state,
        locality=locality,
        approval_state=approval_state,
        warnings=warnings or [],
        errors=errors or [],
        trace_summary=normalized_trace_summary,
        data=_normalize_data_payload(data),
    )


__all__ = (
    "ResponseEnvelope",
    "TraceSummary",
    "build_response_envelope",
)
