"""Routes for DatabaseForge stewardship."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_data_binary_artifact_service import get_data_binary_artifact
from app.api.coding_data_binary_policy_service import load_database_limits
from app.api.coding_database_service import inspect_database, preview_database_schema
from app.api.coding_database_type_registry import database_registry_payload
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.database_binary import DatabaseInspectRequest, DatabaseSchemaPreviewRequest
from app.api.schemas.envelope import TraceSummary, build_response_envelope


router = APIRouter(prefix="/coding/database", tags=["coding", "database"])


def _envelope(result_type: str, data: dict[str, Any], approval_state: ApprovalState, *, request_id: str | None = None, log_written: bool = False) -> dict[str, Any]:
    return build_response_envelope(status=EnvelopeStatus.OK, request_id=request_id or f"req_database_{uuid4().hex[:16]}", api_version="1.0.0", contract_version="databaseforge-0.1", result_type=result_type, capability_state=CapabilityState.LIVE, locality=LocalityState.LOCAL, approval_state=approval_state, warnings=["DatabaseForge is snapshot-first and fixed-introspection-only. Row preview, arbitrary SQL, extension loading, external access, export, and mutation are unavailable by design."], errors=[], trace_summary=TraceSummary(route_used=f"coding.database.{result_type}", log_written=log_written, journal_written=False), data=data).to_payload()


@router.get("/types")
async def get_database_types() -> dict[str, Any]:
    return _envelope("database_types", {"database_types": database_registry_payload(), "inspection_limits": load_database_limits()}, ApprovalState.NOT_NEEDED)


@router.post("/inspect")
def post_database_inspect(payload: DatabaseInspectRequest = Body(...)) -> dict[str, Any]:
    result = inspect_database(payload)
    state = ApprovalState.APPROVED if result.status == "completed" else ApprovalState.NEEDED if result.status == "approval_required" else ApprovalState.DENIED
    return _envelope("database_inspect", {"database": result.to_payload()}, state, request_id=result.request_id, log_written=result.audit_written)


@router.post("/schema/preview")
def post_database_schema_preview(payload: DatabaseSchemaPreviewRequest = Body(...)) -> dict[str, Any]:
    result = preview_database_schema(payload)
    state = ApprovalState.APPROVED if result.status == "completed" else ApprovalState.NEEDED if result.status == "approval_required" else ApprovalState.DENIED
    return _envelope("database_schema_preview", {"database_schema": result.to_payload()}, state, request_id=result.request_id, log_written=result.audit_written)


@router.get("/artifacts/{artifact_id}")
async def get_database_artifact(artifact_id: str) -> dict[str, Any]:
    artifact = get_data_binary_artifact("database", artifact_id)
    return _envelope("database_artifact", {"database_artifact": artifact, "found": artifact is not None}, ApprovalState.NOT_NEEDED)


__all__ = ("router",)
