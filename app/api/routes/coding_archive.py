"""Routes for ArchiveForge archive/container stewardship."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

from app.api.coding_archive_artifact_service import get_archive_artifact
from app.api.coding_archive_job_service import cancel_archive_job, get_archive_job
from app.api.coding_archive_policy_service import public_archive_limits
from app.api.coding_archive_service import apply_archive_extraction, inspect_archive, plan_archive_extraction
from app.api.coding_archive_type_registry import archive_registry_payload
from app.api.schemas.archive import ArchiveExtractionApplyRequest, ArchiveExtractionPlanRequest, ArchiveInspectRequest
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope


API_VERSION = "1.0.0"
CONTRACT_VERSION = "archiveforge-0.1"

router = APIRouter(prefix="/coding/archive", tags=["coding", "archive"])


def _request_id(prefix: str) -> str:
    return f"req_{prefix}_{uuid4().hex[:16]}"


def _envelope(
    *,
    result_type: str,
    data: dict[str, Any],
    approval_state: ApprovalState,
    log_written: bool = False,
    request_id: str | None = None,
) -> dict[str, Any]:
    return build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id or _request_id("archive"),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=[
            "ArchiveForge is local, path-guarded, policy-bound, and never installs, executes, imports, trusts, auto-opens, or merges container contents.",
            "Extraction is selected-file only, sandbox only, and requires a fresh exact one-time approval.",
        ],
        errors=[],
        trace_summary=TraceSummary(route_used=f"coding.archive.{result_type}", log_written=log_written, journal_written=False),
        data=data,
    ).to_payload()


@router.get("/types")
async def get_archive_types() -> dict[str, Any]:
    return _envelope(
        result_type="archive_types",
        data={"archive_types": archive_registry_payload(), "extraction_limits": public_archive_limits()},
        approval_state=ApprovalState.NOT_NEEDED,
    )


@router.post("/inspect")
def post_archive_inspect(payload: ArchiveInspectRequest = Body(...)) -> dict[str, Any]:
    result = inspect_archive(payload)
    state = ApprovalState.APPROVED if result.status in {"completed", "blocked"} and payload.approval_granted else ApprovalState.NEEDED
    return _envelope(
        result_type="archive_inspect",
        data={"archive": result.to_payload()},
        approval_state=state,
        log_written=result.audit_written,
        request_id=result.request_id,
    )


@router.post("/extract/plan")
def post_archive_extract_plan(payload: ArchiveExtractionPlanRequest = Body(...)) -> dict[str, Any]:
    result = plan_archive_extraction(payload)
    return _envelope(
        result_type="archive_extraction_plan",
        data={"archive_extraction_plan": result.to_payload()},
        approval_state=ApprovalState.NEEDED,
        log_written=True,
        request_id=result.request_id,
    )


@router.post("/extract/apply")
def post_archive_extract_apply(payload: ArchiveExtractionApplyRequest = Body(...)) -> dict[str, Any]:
    result = apply_archive_extraction(payload)
    state = ApprovalState.APPROVED if result.status == "completed" else ApprovalState.NEEDED if result.status == "approval_required" else ApprovalState.DENIED
    return _envelope(
        result_type="archive_extraction_result",
        data={"archive_extraction_result": result.to_payload()},
        approval_state=state,
        log_written=result.audit_written,
        request_id=result.request_id,
    )


@router.get("/jobs/{operation_id}")
async def get_archive_job_state(operation_id: str) -> dict[str, Any]:
    job = get_archive_job(operation_id)
    return _envelope(
        result_type="archive_job",
        data={"archive_job": job.to_payload() if job else None, "found": job is not None},
        approval_state=ApprovalState.NOT_NEEDED,
    )


@router.post("/jobs/{operation_id}/cancel")
async def post_archive_job_cancel(operation_id: str) -> dict[str, Any]:
    job = cancel_archive_job(operation_id)
    return _envelope(
        result_type="archive_job_cancel",
        data={"archive_job": job.to_payload() if job else None, "found": job is not None},
        approval_state=ApprovalState.APPROVED if job else ApprovalState.UNKNOWN,
    )


@router.get("/artifacts/{artifact_id}")
async def get_archive_artifact_detail(artifact_id: str) -> dict[str, Any]:
    artifact = get_archive_artifact(artifact_id)
    return _envelope(
        result_type="archive_artifact",
        data={"archive_artifact": artifact, "found": artifact is not None},
        approval_state=ApprovalState.NOT_NEEDED,
    )


__all__ = ("router",)
