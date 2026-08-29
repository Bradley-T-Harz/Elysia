"""Approval/result bookkeeping for coding bridge operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from hmac import compare_digest
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.api.coding_audit_service import utc_now_iso, write_coding_audit_record
from app.api.coding_path_guard_service import guard_workspace_path
from app.api.schemas.coding_operations import (
    CodingApprovalConsumption,
    CodingOperationApproval,
    CodingOperationApproveRequest,
    CodingOperationResult,
    CodingOperationResultRequest,
)


@dataclass
class _ApprovalRecord:
    approval: CodingOperationApproval
    token: str | None
    workspace_root: Path
    expires_at: datetime
    consumed_at: datetime | None = None


_APPROVALS: dict[str, _ApprovalRecord] = {}
_APPROVAL_LOCK = RLock()


def _expiry(seconds: int) -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=seconds)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _workspace_hash(root: Path) -> str:
    return sha256(str(root).encode("utf-8")).hexdigest()[:24]


def _approval_audit_fields(operation_kind: str, exact_files: list[str]) -> dict[str, object]:
    if operation_kind.startswith(("archive_", "database_", "binary_", "engineering_")) or operation_kind == "archive_extract":
        digest = sha256("\n".join(exact_files).encode("utf-8")).hexdigest()[:32]
        return {"exact_file_count": len(exact_files), "exact_files_digest": digest}
    return {"exact_files": exact_files}


def _normalize_exact_files(workspace_root: str, exact_files: list[str]) -> tuple[Path | None, list[str], str | None]:
    root_guard = guard_workspace_path(
        workspace_root=workspace_root,
        target_path=".",
        require_existing=True,
        allow_directory=True,
    )
    if not root_guard.allowed:
        return None, [], root_guard.reason or "workspace_root_not_approved"
    normalized: list[str] = []
    for file_path in exact_files:
        guarded = guard_workspace_path(
            workspace_root=workspace_root,
            target_path=file_path,
            require_existing=False,
            allow_directory=True,
        )
        if not guarded.allowed or not guarded.relative_path:
            return None, [], guarded.reason or "approval_file_not_allowed"
        normalized.append(guarded.relative_path)
    return root_guard.workspace_root, sorted(set(normalized)), None


def approve_operation(payload: CodingOperationApproveRequest) -> CodingOperationApproval:
    approval_id = f"approval_{uuid4().hex[:16]}"
    root, exact_files, normalization_error = _normalize_exact_files(payload.workspace_root, payload.exact_files)
    expires_at = _expiry(payload.expires_in_seconds if payload.operator_approved else 30)
    warnings = ["Approval is exact, expiring, and one-time; it does not execute the operation by itself."]
    exact_files_required = payload.allowed_mutation_class != "command_check"
    if normalization_error or (exact_files_required and not exact_files) or not payload.plan_hash or not payload.allowed_mutation_class:
        approval = CodingOperationApproval(
            status="denied",
            approval_id=approval_id,
            operation_kind=payload.operation_kind,
            operation_summary=payload.operation_summary,
            exact_files=exact_files,
            source_hash=payload.source_hash,
            plan_hash=payload.plan_hash,
            allowed_mutation_class=payload.allowed_mutation_class,
            expires_at_utc=_iso(expires_at),
            warnings=[normalization_error or "Exact files, plan hash, and mutation class are required."],
        )
        with _APPROVAL_LOCK:
            _APPROVALS[approval_id] = _ApprovalRecord(approval, None, root or Path("/"), expires_at)
        return approval
    if not payload.operator_approved:
        approval = CodingOperationApproval(
            status="approval_required",
            approval_id=approval_id,
            operation_kind=payload.operation_kind,
            operation_summary=payload.operation_summary,
            exact_files=exact_files,
            workspace_root_hash=_workspace_hash(root) if root else None,
            source_hash=payload.source_hash,
            plan_hash=payload.plan_hash,
            allowed_mutation_class=payload.allowed_mutation_class,
            expires_at_utc=_iso(expires_at),
            warnings=warnings,
        )
        with _APPROVAL_LOCK:
            _APPROVALS[approval_id] = _ApprovalRecord(approval, None, root or Path("/"), expires_at)
        return approval

    token = f"op_{uuid4().hex}"
    approval = CodingOperationApproval(
        status="approved",
        approval_id=approval_id,
        approval_token=token,
        operation_kind=payload.operation_kind,
        operation_summary=payload.operation_summary,
        exact_files=exact_files,
        workspace_root_hash=_workspace_hash(root),
        source_hash=payload.source_hash,
        plan_hash=payload.plan_hash,
        allowed_mutation_class=payload.allowed_mutation_class,
        expires_at_utc=_iso(expires_at),
        audit_written=True,
        warnings=warnings,
    )
    with _APPROVAL_LOCK:
        _APPROVALS[approval_id] = _ApprovalRecord(approval, token, root, expires_at)
    write_coding_audit_record(
        "approval",
        approval_id,
        {
            **({} if payload.operation_kind.startswith(("archive_", "database_", "binary_", "engineering_")) else {"session_id": payload.session_id}),
            "operation_kind": payload.operation_kind,
            "operation_summary": "Sensitive static/schema/engineering operation exact approval" if payload.operation_kind.startswith(("archive_", "database_", "binary_", "engineering_")) else payload.operation_summary,
            **_approval_audit_fields(payload.operation_kind, exact_files),
            "workspace_root_hash": approval.workspace_root_hash,
            "source_hash": payload.source_hash,
            "plan_hash": payload.plan_hash,
            "allowed_mutation_class": payload.allowed_mutation_class,
            "expires_at_utc": approval.expires_at_utc,
            "operator_approved": True,
            "approval_phrase_present": bool(payload.approval_phrase),
            "rollback_note": (
                "Disposable archive sandbox cleanup; source and project remain unchanged."
                if payload.operation_kind.startswith("archive_")
                else payload.rollback_note
            ),
        },
    )
    return approval


def _consume_operation_approval_locked(
    *,
    approval_id: str | None,
    approval_token: str | None,
    operation_kind: str,
    workspace_root: str,
    exact_files: list[str],
    source_hash: str | None,
    plan_hash: str,
    allowed_mutation_class: str,
) -> CodingApprovalConsumption:
    if not approval_id:
        return CodingApprovalConsumption(allowed=False, approval_id="", reason="approval_id_required")
    record = _APPROVALS.get(approval_id)
    if record is None or record.token is None:
        return CodingApprovalConsumption(allowed=False, approval_id=approval_id, reason="unknown_or_unapproved_approval_id")
    if not approval_token or not compare_digest(approval_token, record.token):
        return CodingApprovalConsumption(allowed=False, approval_id=approval_id, reason="approval_token_mismatch")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if now >= record.expires_at:
        return CodingApprovalConsumption(allowed=False, approval_id=approval_id, reason="approval_expired")
    if record.consumed_at is not None:
        return CodingApprovalConsumption(allowed=False, approval_id=approval_id, reason="approval_already_used")
    root, normalized_files, normalization_error = _normalize_exact_files(workspace_root, exact_files)
    approval = record.approval
    mismatch_reason = None
    if normalization_error or root != record.workspace_root:
        mismatch_reason = normalization_error or "approval_workspace_mismatch"
    elif approval.operation_kind != operation_kind:
        mismatch_reason = "approval_operation_kind_mismatch"
    elif approval.exact_files != normalized_files:
        mismatch_reason = "approval_exact_files_mismatch"
    elif approval.source_hash != source_hash:
        mismatch_reason = "approval_source_hash_mismatch"
    elif approval.plan_hash != plan_hash:
        mismatch_reason = "approval_plan_hash_mismatch"
    elif approval.allowed_mutation_class != allowed_mutation_class:
        mismatch_reason = "approval_mutation_class_mismatch"
    if mismatch_reason:
        return CodingApprovalConsumption(allowed=False, approval_id=approval_id, reason=mismatch_reason)

    record.consumed_at = now
    record.approval.consumed_at_utc = _iso(now)
    write_coding_audit_record(
        "approval_consumed",
        approval_id,
        {
            "operation_kind": operation_kind,
            "workspace_root_hash": approval.workspace_root_hash,
            **_approval_audit_fields(operation_kind, normalized_files),
            "source_hash": source_hash,
            "plan_hash": plan_hash,
            "allowed_mutation_class": allowed_mutation_class,
            "consumed_at_utc": _iso(now),
        },
    )
    return CodingApprovalConsumption(allowed=True, approval_id=approval_id, consumed_at_utc=_iso(now))


def consume_operation_approval(
    *,
    approval_id: str | None,
    approval_token: str | None,
    operation_kind: str,
    workspace_root: str,
    exact_files: list[str],
    source_hash: str | None,
    plan_hash: str,
    allowed_mutation_class: str,
) -> CodingApprovalConsumption:
    """Atomically validate and consume one exact approval token."""
    with _APPROVAL_LOCK:
        return _consume_operation_approval_locked(
            approval_id=approval_id,
            approval_token=approval_token,
            operation_kind=operation_kind,
            workspace_root=workspace_root,
            exact_files=exact_files,
            source_hash=source_hash,
            plan_hash=plan_hash,
            allowed_mutation_class=allowed_mutation_class,
        )


def record_operation_result(payload: CodingOperationResultRequest) -> CodingOperationResult:
    record = _APPROVALS.get(payload.approval_id)
    warnings: list[str] = []
    if record is None or record.token is None:
        return CodingOperationResult(
            status="denied",
            approval_id=payload.approval_id,
            result_summary="Unknown approval record.",
            warnings=["Result record rejected because the approval ID is unknown."],
        )
    if not payload.approval_token or not compare_digest(payload.approval_token, record.token):
        return CodingOperationResult(
            status="denied",
            approval_id=payload.approval_id,
            result_summary="Approval token did not match.",
            warnings=["Result record rejected because approval token did not match."],
        )
    if record.consumed_at is None:
        return CodingOperationResult(
            status="denied",
            approval_id=payload.approval_id,
            result_summary="Approval was not consumed by a governed executor.",
            warnings=["Result record rejected because no governed execution consumed the approval."],
        )
    if payload.execution_performed:
        warnings.append("Execution was reported by caller; Elysia did not perform shell/git/package execution here.")
    result = CodingOperationResult(
        status=payload.status,
        approval_id=payload.approval_id,
        result_summary=payload.result_summary,
        files_changed=payload.files_changed,
        execution_performed=payload.execution_performed,
        audit_written=True,
        warnings=warnings,
    )
    write_coding_audit_record(
        "result",
        payload.approval_id,
        {
            "status": payload.status,
            "result_summary": payload.result_summary,
            "files_changed": payload.files_changed,
            "execution_performed": payload.execution_performed,
            "recorded_at_utc": utc_now_iso(),
        },
    )
    return result


def clear_operation_state_for_tests() -> None:
    with _APPROVAL_LOCK:
        _APPROVALS.clear()


__all__ = (
    "approve_operation",
    "clear_operation_state_for_tests",
    "consume_operation_approval",
    "record_operation_result",
)
