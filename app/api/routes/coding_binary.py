"""Routes for BinaryForge static stewardship."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_binary_service import inspect_binary
from app.api.coding_binary_type_registry import binary_registry_payload
from app.api.coding_data_binary_artifact_service import get_data_binary_artifact
from app.api.coding_data_binary_policy_service import load_binary_limits
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.database_binary import BinaryInspectRequest
from app.api.schemas.envelope import TraceSummary, build_response_envelope


router = APIRouter(prefix="/coding/binary", tags=["coding", "binary"])


def _envelope(result_type: str, data: dict[str, Any], approval_state: ApprovalState, *, request_id: str | None = None, log_written: bool = False) -> dict[str, Any]:
    return build_response_envelope(status=EnvelopeStatus.OK, request_id=request_id or f"req_binary_{uuid4().hex[:16]}", api_version="1.0.0", contract_version="binaryforge-0.1", result_type=result_type, capability_state=CapabilityState.LIVE, locality=LocalityState.LOCAL, approval_state=approval_state, warnings=["BinaryForge performs bounded static inspection only. Execution, loading, import, installation, linking, mutation, patching, and trust are unavailable by design."], errors=[], trace_summary=TraceSummary(route_used=f"coding.binary.{result_type}", log_written=log_written, journal_written=False), data=data).to_payload()


@router.get("/types")
async def get_binary_types() -> dict[str, Any]:
    return _envelope("binary_types", {"binary_types": binary_registry_payload(), "inspection_limits": load_binary_limits()}, ApprovalState.NOT_NEEDED)


@router.post("/inspect")
def post_binary_inspect(payload: BinaryInspectRequest = Body(...)) -> dict[str, Any]:
    result = inspect_binary(payload)
    state = ApprovalState.APPROVED if result.status == "completed" else ApprovalState.NEEDED if result.status == "approval_required" else ApprovalState.DENIED
    return _envelope("binary_inspect", {"binary": result.to_payload()}, state, request_id=result.request_id, log_written=result.audit_written)


@router.get("/artifacts/{artifact_id}")
async def get_binary_artifact(artifact_id: str) -> dict[str, Any]:
    artifact = get_data_binary_artifact("binary", artifact_id)
    return _envelope("binary_artifact", {"binary_artifact": artifact, "found": artifact is not None}, ApprovalState.NOT_NEEDED)


__all__ = ("router",)
