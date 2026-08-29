"""Governed Coder route module."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException
from pydantic import ValidationError

from app.api import code_service
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "phase1-ui-contract-1.0"

router = APIRouter(prefix="/code", tags=["code"])


def _new_route_request_id(prefix: str = "code_validation") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _require_mapping_payload(payload: Any, path: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise HTTPException(
            status_code=400,
            detail=f"Request body for {path} must be a JSON object.",
        )
    return dict(payload)


def _compact_validation_errors(exc: ValidationError) -> list[str]:
    """
    Convert Pydantic validation details into compact safe messages.

    Do not include raw input values here. Validation errors can be triggered
    by sensitive payloads, so only field locations, messages, and error types
    are surfaced.
    """
    messages: list[str] = []
    for item in exc.errors():
        loc_parts = [
            str(part)
            for part in item.get("loc", ())
            if str(part) not in {"body", "__root__"}
        ]
        loc = ".".join(loc_parts) or "payload"
        msg = str(item.get("msg") or "Invalid value")
        kind = str(item.get("type") or "validation_error")
        messages.append(f"{loc}: {msg} ({kind})")
    return messages or ["Request payload failed validation."]


def _validation_error_envelope(
    *,
    request_id: str,
    result_type: str,
    path: str,
    errors: list[str],
) -> dict[str, Any]:
    envelope = build_response_envelope(
        status=EnvelopeStatus.ERROR,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NEEDED,
        warnings=[],
        errors=errors,
        trace_summary=TraceSummary(
            route_used=f"code.{result_type}",
            log_written=False,
            journal_written=False,
        ),
        data={
            "validation_error": True,
            "path": path,
            "approval_required": True,
            "patch_applied": False,
            "command_executed": False,
            "mutated_files": False,
            "shell_used": False,
            "broad_shell_used": False,
            "git_mutation_used": False,
            "network_access_used": False,
            "private_context_sent": False,
        },
    )
    return envelope.to_payload()


def _envelope(
    *,
    request_id: str,
    result_type: str,
    data: Any,
    ok: bool,
    blocked: bool = False,
) -> dict[str, Any]:
    status = EnvelopeStatus.OK if ok else (EnvelopeStatus.BLOCKED if blocked else EnvelopeStatus.ERROR)
    approval_state = ApprovalState.APPROVED if ok else (ApprovalState.NEEDED if blocked else ApprovalState.DENIED)
    envelope = build_response_envelope(
        status=status,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=list(getattr(data, "warnings", []) or []),
        errors=list(getattr(data, "errors", []) or []),
        trace_summary=TraceSummary(
            route_used=f"code.{result_type}",
            log_written=False,
            journal_written=False,
        ),
        data=data,
    )
    return envelope.to_payload()


@router.post("/patch/apply")
async def apply_patch(payload: Any = Body(...)) -> dict[str, Any]:
    path = "/code/patch/apply"
    request_id = _new_route_request_id("patch_validation")

    try:
        mapping_payload = _require_mapping_payload(payload, path)
        data = code_service.apply_approved_patch(mapping_payload)
    except HTTPException as exc:
        return _validation_error_envelope(
            request_id=request_id,
            result_type="code_patch_apply_validation_error",
            path=path,
            errors=[str(exc.detail)],
        )
    except ValidationError as exc:
        return _validation_error_envelope(
            request_id=request_id,
            result_type="code_patch_apply_validation_error",
            path=path,
            errors=_compact_validation_errors(exc),
        )

    return _envelope(
        request_id=data.request_id,
        result_type="approved_patch_application",
        data=data,
        ok=data.status == "completed",
        blocked=data.status == "blocked",
    )


@router.post("/tests/run")
async def run_focused_test(payload: Any = Body(...)) -> dict[str, Any]:
    path = "/code/tests/run"
    request_id = _new_route_request_id("command_validation")

    try:
        mapping_payload = _require_mapping_payload(payload, path)
        data = code_service.run_approved_focused_command(mapping_payload)
    except HTTPException as exc:
        return _validation_error_envelope(
            request_id=request_id,
            result_type="focused_command_validation_error",
            path=path,
            errors=[str(exc.detail)],
        )
    except ValidationError as exc:
        return _validation_error_envelope(
            request_id=request_id,
            result_type="focused_command_validation_error",
            path=path,
            errors=_compact_validation_errors(exc),
        )

    return _envelope(
        request_id=data.request_id,
        result_type="approved_focused_command",
        data=data,
        ok=data.status == "completed" and data.exit_code == 0,
        blocked=data.status == "blocked",
    )


__all__ = ("router",)
