"""ArchiveForge orchestration: path guard, artifacts, approvals, audit, and jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from app.api.coding_archive_artifact_service import create_archive_artifact
from app.api.coding_archive_extraction_service import apply_extraction_plan, build_extraction_plan
from app.api.coding_archive_inspection_service import inspect_archive_path
from app.api.coding_archive_job_service import finish_archive_job, start_archive_job
from app.api.coding_archive_policy_service import load_archive_limits
from app.api.coding_archive_type_registry import archive_type_from_extension, descriptor_for_type
from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.coding_trace_service import coding_request_id
from app.api.schemas.archive import (
    ArchiveExtractionApplyRequest,
    ArchiveExtractionPlan,
    ArchiveExtractionPlanRequest,
    ArchiveExtractionResult,
    ArchiveInspectRequest,
    ArchiveInspectResponse,
)


def _operation_id(kind: str) -> str:
    return f"archive_{kind}_{uuid4().hex[:16]}"


def _compact_audit(
    *,
    payload: Any,
    operation_kind: str,
    status: str,
    operation_id: str,
    inspection: dict[str, Any] | None = None,
    plan: ArchiveExtractionPlan | None = None,
    result: ArchiveExtractionResult | None = None,
    artifact_id: str | None = None,
) -> bool:
    compact: dict[str, Any] = {
        "operation_kind": operation_kind,
        "status": status,
        "workspace_root_hash": hash_path(getattr(payload, "workspace_root", "")),
        "path_hash": hash_path(getattr(payload, "archive_path", "")),
        "archive_type": inspection.get("detected_type") if inspection else plan.archive_type if plan else result.archive_type if result else None,
        "archive_hash": inspection.get("archive_sha256") if inspection else plan.archive_sha256 if plan else result.archive_sha256 if result else None,
        "size_bytes": inspection.get("archive_size_bytes") if inspection else plan.archive_size_bytes if plan else None,
        "member_count": inspection.get("member_count") if inspection else None,
        "risk_total": sum((inspection.get("risk_counts") or {}).values()) if inspection else None,
        "manifest_hash": inspection.get("manifest_digest") if inspection else plan.manifest_digest if plan else result.manifest_digest if result else None,
        "plan_hash": plan.plan_hash if plan else result.plan_hash if result else None,
        "selected_member_count": plan.selected_file_count if plan else None,
        "sandbox_hash": plan.sandbox_destination_hash if plan else result.sandbox_destination_hash if result else None,
        "approval_id": result.approval_id if result else getattr(payload, "approval_id", None),
        "artifact_id": artifact_id,
        "policy_version": inspection.get("policy_version") if inspection else plan.policy_version if plan else load_archive_limits()["version"],
        "tool_used": inspection.get("tool_used") if inspection else None,
        "extracted_file_count": result.extracted_file_count if result else None,
        "extracted_bytes": result.extracted_bytes if result else None,
        "blocked_member_count": result.blocked_member_count if result else None,
        "skipped_member_count": result.skipped_member_count if result else None,
        "operator_approved": bool(getattr(payload, "operator_approved", False)),
        "approval_required": operation_kind == "archive_extract_apply",
        "mutation_performed": bool(result and result.mutation_performed),
        "network": False,
        "shell": False,
        "raw_content_logged": False,
    }
    return write_coding_audit_record(operation_kind, operation_id, {key: value for key, value in compact.items() if value is not None})


def inspect_archive(payload: ArchiveInspectRequest) -> ArchiveInspectResponse:
    operation_id = _operation_id("inspect")
    request_id = coding_request_id(operation_id)
    guarded = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=payload.archive_path,
        require_existing=True,
        allow_directory=False,
    )
    extension_type = archive_type_from_extension(guarded.target_path)
    descriptor = descriptor_for_type(extension_type)
    start_archive_job(operation_id, "archive_inspect")
    if not guarded.allowed or not payload.approval_granted:
        reason = guarded.reason if not guarded.allowed else "explicit_inspection_approval_required"
        status = "blocked" if not guarded.allowed else "approval_required"
        audit = _compact_audit(
            payload=payload,
            operation_kind="archive_inspect",
            status=status,
            operation_id=operation_id,
        )
        finish_archive_job(operation_id, status=status, compact_summary={"blocked_reason": reason})
        return ArchiveInspectResponse(
            status=status,
            operation_id=operation_id,
            request_id=request_id,
            file_label=guarded.target_path.name or "selected archive",
            relative_path=guarded.relative_path,
            path_hash=hash_path(guarded.target_path),
            extension_type=extension_type,
            detected_type="unknown",
            descriptor=descriptor,
            policy_version=load_archive_limits()["version"],
            blocked_reason=reason,
            audit_written=audit,
            warnings=["Archive inspection is user-initiated, local, path-guarded, and read-only."],
        )
    inspection = inspect_archive_path(guarded.target_path)
    manifest_artifact = create_archive_artifact("manifest", inspection["manifest_payload"])
    risk_artifact = create_archive_artifact(
        "risk_report",
        {
            "archive_sha256": inspection["archive_sha256"],
            "manifest_digest": inspection["manifest_digest"],
            "risk_flags": [risk.to_payload() for risk in inspection["risk_flags"]],
            "risk_counts": inspection["risk_counts"],
            "package_metadata": inspection["package_metadata"].to_payload() if inspection["package_metadata"] else None,
            "policy_version": inspection["policy_version"],
        },
    )
    limit = load_archive_limits()["limits"]["max_manifest_members_in_response"]
    audit = _compact_audit(
        payload=payload,
        operation_kind="archive_inspect",
        status=inspection["status"],
        operation_id=operation_id,
        inspection=inspection,
        artifact_id=manifest_artifact.artifact_id,
    )
    finish_archive_job(
        operation_id,
        status=inspection["status"],
        artifact_id=manifest_artifact.artifact_id,
        compact_summary={
            "archive_type": inspection["detected_type"],
            "member_count": inspection["member_count"],
            "risk_total": sum(inspection["risk_counts"].values()),
        },
    )
    return ArchiveInspectResponse(
        status=inspection["status"],
        operation_id=operation_id,
        request_id=request_id,
        file_label=guarded.target_path.name,
        relative_path=guarded.relative_path,
        path_hash=hash_path(guarded.target_path),
        archive_sha256=inspection["archive_sha256"],
        archive_size_bytes=inspection["archive_size_bytes"],
        extension_type=inspection["extension_type"],
        detected_type=inspection["detected_type"],
        extension_content_match=inspection["extension_content_match"],
        descriptor=inspection["descriptor"],
        member_count=inspection["member_count"],
        directory_count=inspection["directory_count"],
        projected_uncompressed_bytes=inspection["projected_uncompressed_bytes"],
        largest_member_bytes=inspection["largest_member_bytes"],
        nested_archive_count=inspection["nested_archive_count"],
        compression_ratio=inspection["compression_ratio"],
        encrypted=inspection["encrypted"],
        members=inspection["members"][:limit],
        member_list_truncated=bool(inspection.get("manifest_truncated")) or len(inspection["members"]) > limit,
        risk_flags=inspection["risk_flags"],
        risk_counts=inspection["risk_counts"],
        package_metadata=inspection["package_metadata"],
        manifest_digest=inspection["manifest_digest"],
        artifacts=[manifest_artifact, risk_artifact],
        policy_version=inspection["policy_version"],
        tool_used=inspection["tool_used"],
        blocked_reason=inspection["blocked_reason"],
        audit_written=audit,
        warnings=inspection["warnings"],
    )


def plan_archive_extraction(payload: ArchiveExtractionPlanRequest) -> ArchiveExtractionPlan:
    operation_id = _operation_id("plan")
    start_archive_job(operation_id, "archive_extract_plan")
    guarded = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=payload.archive_path,
        require_existing=True,
        allow_directory=False,
    )
    if not guarded.allowed:
        empty_inspection = {
            "archive_sha256": "unavailable",
            "archive_size_bytes": 0,
            "manifest_digest": "unavailable",
            "detected_type": archive_type_from_extension(payload.archive_path),
            "descriptor": descriptor_for_type(archive_type_from_extension(payload.archive_path)),
            "members": [],
            "risk_flags": [],
        }
        plan = build_extraction_plan(payload, guarded=guarded, inspection=empty_inspection, operation_id=operation_id)
        plan.status = "blocked"
        plan.blocked_reason = guarded.reason
    else:
        inspection = inspect_archive_path(guarded.target_path)
        plan = build_extraction_plan(payload, guarded=guarded, inspection=inspection, operation_id=operation_id)
    plan.request_id = coding_request_id(operation_id)
    audit = _compact_audit(
        payload=payload,
        operation_kind="archive_extract_plan",
        status=plan.status,
        operation_id=operation_id,
        plan=plan,
        artifact_id=plan.artifact.artifact_id if plan.artifact else None,
    )
    del audit
    finish_archive_job(
        operation_id,
        status=plan.status,
        artifact_id=plan.artifact.artifact_id if plan.artifact else None,
        compact_summary={"selected_member_count": plan.selected_file_count, "sandbox_hash": plan.sandbox_destination_hash},
    )
    return plan


def apply_archive_extraction(payload: ArchiveExtractionApplyRequest) -> ArchiveExtractionResult:
    operation_id = payload.operation_id
    start_archive_job(operation_id, "archive_extract_apply")
    guarded = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=payload.archive_path,
        require_existing=True,
        allow_directory=False,
    )
    if not guarded.allowed:
        result = ArchiveExtractionResult(
            status="blocked",
            operation_id=operation_id,
            request_id=coding_request_id(operation_id),
            approval_id=payload.approval_id,
            archive_type=archive_type_from_extension(payload.archive_path),
            archive_sha256=payload.expected_archive_sha256,
            manifest_digest=payload.expected_manifest_digest,
            plan_hash=payload.expected_plan_hash,
            sandbox_id=payload.sandbox_id or "invalid_sandbox",
            sandbox_destination_hash="unavailable",
            blocked_reason=guarded.reason,
            warnings=["No sandbox was created."],
        )
        result.audit_written = _compact_audit(
            payload=payload,
            operation_kind="archive_extract_apply",
            status=result.status,
            operation_id=operation_id,
            result=result,
        )
        finish_archive_job(operation_id, status="blocked", approval_id=payload.approval_id)
        return result
    inspection = inspect_archive_path(guarded.target_path)
    plan = build_extraction_plan(
        payload,
        guarded=guarded,
        inspection=inspection,
        operation_id=operation_id,
        check_destination_exists=False,
    )
    result = apply_extraction_plan(payload, guarded=guarded, inspection=inspection, plan=plan, operation_id=operation_id)
    result.request_id = coding_request_id(operation_id, payload.approval_id)
    audit = _compact_audit(
        payload=payload,
        operation_kind="archive_extract_apply",
        status=result.status,
        operation_id=operation_id,
        inspection=inspection,
        plan=plan,
        result=result,
        artifact_id=result.artifact.artifact_id if result.artifact else None,
    )
    result.audit_written = audit
    finish_archive_job(
        operation_id,
        status=result.status,
        approval_id=payload.approval_id,
        artifact_id=result.artifact.artifact_id if result.artifact else None,
        compact_summary={
            "extracted_file_count": result.extracted_file_count,
            "extracted_bytes": result.extracted_bytes,
            "sandbox_hash": result.sandbox_destination_hash,
        },
    )
    return result


__all__ = ("apply_archive_extraction", "inspect_archive", "plan_archive_extraction")
