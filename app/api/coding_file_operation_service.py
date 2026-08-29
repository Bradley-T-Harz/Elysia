"""Non-mutating file operation planner for Elysia Codev."""

from __future__ import annotations

from hashlib import sha256
from uuid import uuid4

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_backup_service import create_coding_backup, hash_file_bytes
from app.api.coding_approval_modes import approval_mode_policy, mode_required_message
from app.api.coding_file_adapter_service import validate_patch_for_descriptor
from app.api.coding_file_type_service import is_supported_file_operation, normalize_file_operation_kind
from app.api.coding_file_type_registry import detect_file_type
from app.api.coding_path_guard_service import guard_workspace_path
from app.api.coding_operation_service import consume_operation_approval
from app.api.coding_risk_service import summarize_file_risk
from app.api.coding_secret_scan_service import scan_preview_for_secrets
from app.api.schemas.coding_file_operations import (
    CodingFileOperationExecuteRequest,
    CodingFileOperationExecuteResult,
    CodingFileOperationPlan,
    CodingFileOperationPlanRequest,
)


def plan_file_operation(payload: CodingFileOperationPlanRequest) -> CodingFileOperationPlan:
    operation_kind = normalize_file_operation_kind(payload.operation_kind)
    if not is_supported_file_operation(operation_kind):
        return CodingFileOperationPlan(
            status="unsupported_operation_kind",
            operation_kind=operation_kind,
            blocked_reason="unsupported_operation_kind",
            warnings=["No file mutation was performed."],
        )

    require_existing = operation_kind in {"edit", "delete", "rename", "move", "replace"}
    target = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=payload.target_path,
        require_existing=require_existing,
        allow_directory=False,
    )
    if not target.allowed:
        return CodingFileOperationPlan(
            status="blocked",
            operation_kind=operation_kind,
            target_relative_path=target.relative_path,
            blocked_reason=target.reason,
            warnings=["No file mutation was performed."],
        )
    if operation_kind == "create" and target.target_path.exists():
        return CodingFileOperationPlan(
            status="blocked",
            operation_kind=operation_kind,
            target_relative_path=target.relative_path,
            blocked_reason="target_exists",
            warnings=["Create never overwrites an existing file. Use an exact-hash edit or replace plan."],
        )
    raw = None
    if target.target_path.exists() and target.target_path.is_file():
        with target.target_path.open("rb") as stream:
            raw = stream.read(4096)
    descriptor = detect_file_type(target.target_path, raw)
    capability_allowed = {
        "create": descriptor.creatable,
        "edit": descriptor.writable and descriptor.patchable,
        "replace": descriptor.writable and descriptor.patchable,
        "delete": descriptor.deletable,
        "rename": descriptor.renameable,
        "move": descriptor.renameable,
    }.get(operation_kind, False)
    if not capability_allowed or descriptor.adapter == "blocked":
        return CodingFileOperationPlan(
            status="blocked",
            operation_kind=operation_kind,
            target_relative_path=target.relative_path,
            blocked_reason="file_type_operation_not_allowed",
            risk_labels=summarize_file_risk(target.relative_path or payload.target_path),
            warnings=["No file mutation was performed.", *descriptor.notes],
        )

    destination_relative: str | None = None
    if operation_kind in {"rename", "move"}:
        if not payload.destination_path:
            return CodingFileOperationPlan(
                status="blocked",
                operation_kind=operation_kind,
                target_relative_path=target.relative_path,
                blocked_reason="destination_required",
                warnings=["No file mutation was performed."],
            )
        destination = guard_workspace_path(
            workspace_root=payload.workspace_root,
            target_path=payload.destination_path,
            require_existing=False,
            allow_directory=False,
        )
        if not destination.allowed:
            return CodingFileOperationPlan(
                status="blocked",
                operation_kind=operation_kind,
                target_relative_path=target.relative_path,
                destination_relative_path=destination.relative_path,
                blocked_reason=destination.reason,
                warnings=["No file mutation was performed."],
            )
        if destination.target_path.exists():
            return CodingFileOperationPlan(
                status="blocked",
                operation_kind=operation_kind,
                target_relative_path=target.relative_path,
                destination_relative_path=destination.relative_path,
                blocked_reason="destination_exists",
                warnings=["No file mutation was performed. Destination already exists."],
            )
        destination_descriptor = detect_file_type(destination.target_path)
        if destination_descriptor.adapter == "blocked" or not destination_descriptor.creatable:
            return CodingFileOperationPlan(
                status="blocked",
                operation_kind=operation_kind,
                target_relative_path=target.relative_path,
                destination_relative_path=destination.relative_path,
                blocked_reason="destination_file_type_not_allowed",
                warnings=["No file mutation was performed.", *destination_descriptor.notes],
            )
        if destination_descriptor.type_id != descriptor.type_id:
            return CodingFileOperationPlan(
                status="blocked",
                operation_kind=operation_kind,
                target_relative_path=target.relative_path,
                destination_relative_path=destination.relative_path,
                blocked_reason="type_changing_move_not_allowed",
                warnings=["Rename/move must preserve the governed file type."],
            )
        destination_relative = destination.relative_path

    source_hash = hash_file_bytes(target.target_path) if require_existing else None
    plan_material = "\n".join(
        [
            operation_kind,
            target.relative_path or "",
            destination_relative or "",
            source_hash or "",
            sha256((payload.new_text or "").encode("utf-8")).hexdigest() if payload.new_text is not None else "",
        ]
    )

    steps = [
        f"Review requested {operation_kind} plan for {target.relative_path}.",
        "Show exact file path(s), intended content/diff, and rollback note to the operator.",
        "Require explicit local approval before any future mutation path runs.",
    ]
    if destination_relative:
        steps.insert(1, f"Destination would be {destination_relative}.")

    return CodingFileOperationPlan(
        status="preview_only",
        operation_kind=operation_kind,
        target_relative_path=target.relative_path,
        destination_relative_path=destination_relative,
        mutation_performed=False,
        approval_required=True,
        source_hash=source_hash,
        plan_hash=sha256(plan_material.encode("utf-8")).hexdigest()[:32],
        plan_steps=steps,
        risk_labels=summarize_file_risk(target.relative_path or payload.target_path),
        warnings=["File operation planning is preview-only. No file mutation was performed.", *descriptor.notes],
    )


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def execute_file_operation(payload: CodingFileOperationExecuteRequest) -> CodingFileOperationExecuteResult:
    mode_policy = approval_mode_policy(payload.approval_mode)
    if not mode_policy.can_apply_patch:
        return CodingFileOperationExecuteResult(
            status="blocked_by_approval_mode",
            operation_kind=normalize_file_operation_kind(payload.operation_kind),
            rollback_note="No files were changed.",
            blocked_reason=f"{mode_policy.mode}_does_not_allow_file_mutation",
            warnings=[mode_required_message("apply_with_approval")],
        )

    if not payload.operator_approved:
        return CodingFileOperationExecuteResult(
            status="approval_required",
            operation_kind=normalize_file_operation_kind(payload.operation_kind),
            rollback_note="No files were changed.",
            blocked_reason="operator_approval_required",
            warnings=["File operation execution requires explicit operator approval."],
        )

    plan = plan_file_operation(payload)
    if plan.status not in {"preview_only"}:
        return CodingFileOperationExecuteResult(
            status="blocked",
            operation_kind=plan.operation_kind,
            target_relative_path=plan.target_relative_path,
            destination_relative_path=plan.destination_relative_path,
            rollback_note="No files were changed.",
            blocked_reason=plan.blocked_reason or plan.status,
            warnings=plan.warnings,
        )

    kind = plan.operation_kind
    target = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=payload.target_path,
        require_existing=kind in {"edit", "delete", "rename", "move", "replace"},
        allow_directory=False,
    )
    previous_hash: str | None = None
    new_hash: str | None = None
    descriptor = None
    if target.target_path.exists() and target.target_path.is_file():
        previous_hash = hash_file_bytes(target.target_path)
        if not payload.expected_content_hash:
            return CodingFileOperationExecuteResult(
                status="blocked",
                operation_kind=kind,
                target_relative_path=target.relative_path,
                previous_content_hash=previous_hash,
                rollback_note="No files were changed. Re-plan with the exact source hash.",
                blocked_reason="expected_content_hash_required",
            )
        if previous_hash != payload.expected_content_hash:
            return CodingFileOperationExecuteResult(
                status="blocked",
                operation_kind=kind,
                target_relative_path=target.relative_path,
                previous_content_hash=previous_hash,
                rollback_note="No files were changed. Refresh preview before retrying.",
                blocked_reason="current_content_hash_mismatch",
            )

    destination_relative = plan.destination_relative_path
    backup = None
    if kind in {"create", "edit", "replace"}:
        if payload.new_text is None:
            return CodingFileOperationExecuteResult(
                status="blocked",
                operation_kind=kind,
                target_relative_path=target.relative_path,
                previous_content_hash=previous_hash,
                rollback_note="No files were changed.",
                blocked_reason="new_text_required",
            )
        raw_sample = None
        if target.target_path.exists() and target.target_path.is_file():
            with target.target_path.open("rb") as stream:
                raw_sample = stream.read(4096)
        candidate_descriptor = detect_file_type(target.target_path, raw_sample)
        descriptor_ok, descriptor_reason = validate_patch_for_descriptor(candidate_descriptor, new_text=payload.new_text)
        if not descriptor_ok:
            return CodingFileOperationExecuteResult(
                status="blocked",
                operation_kind=kind,
                target_relative_path=target.relative_path,
                previous_content_hash=previous_hash,
                rollback_note="No files were changed.",
                blocked_reason=descriptor_reason,
                warnings=list(candidate_descriptor.notes),
            )
        secret_findings = scan_preview_for_secrets(payload.new_text)
        if secret_findings:
            return CodingFileOperationExecuteResult(
                status="blocked",
                operation_kind=kind,
                target_relative_path=target.relative_path,
                previous_content_hash=previous_hash,
                rollback_note="No files were changed.",
                blocked_reason="proposed_content_contains_possible_secret",
                warnings=["Proposed content was refused by the secret scanner.", *sorted(secret_findings)],
            )

    exact_files = [payload.target_path]
    if kind in {"rename", "move"} and payload.destination_path:
        exact_files.append(payload.destination_path)
    approval = consume_operation_approval(
        approval_id=payload.approval_id,
        approval_token=payload.approval_token,
        operation_kind=f"file_operation:{kind}",
        workspace_root=payload.workspace_root,
        exact_files=exact_files,
        source_hash=previous_hash,
        plan_hash=plan.plan_hash or "",
        allowed_mutation_class=f"file_{kind}",
    )
    if not approval.allowed:
        return CodingFileOperationExecuteResult(
            status="approval_required",
            operation_kind=kind,
            target_relative_path=target.relative_path,
            destination_relative_path=destination_relative,
            previous_content_hash=previous_hash,
            rollback_note="No files were changed.",
            blocked_reason=approval.reason,
            warnings=["A matching, unexpired, one-time approval record is required."],
        )

    if kind in {"create", "edit", "replace"}:
        raw = None
        if target.target_path.exists() and target.target_path.is_file():
            with target.target_path.open("rb") as stream:
                raw = stream.read(4096)
        descriptor = detect_file_type(target.target_path, raw)
        descriptor_ok, descriptor_reason = validate_patch_for_descriptor(descriptor, new_text=payload.new_text)
        if not descriptor_ok:
            return CodingFileOperationExecuteResult(
                status="blocked",
                operation_kind=kind,
                target_relative_path=target.relative_path,
                previous_content_hash=previous_hash,
                rollback_note="No files were changed.",
                blocked_reason=descriptor_reason,
                warnings=list(descriptor.notes),
            )
        if kind in {"edit", "replace"}:
            backup = create_coding_backup(
                workspace_root=target.workspace_root,
                source_path=target.target_path,
                source_relative_path=target.relative_path or target.target_path.name,
                operation_kind=kind,
                session_id=payload.session_id,
            )
        target.target_path.parent.mkdir(parents=True, exist_ok=True)
        target.target_path.write_text(payload.new_text, encoding="utf-8")
        new_hash = _hash_text(payload.new_text)
    elif kind == "delete":
        backup = create_coding_backup(
            workspace_root=target.workspace_root,
            source_path=target.target_path,
            source_relative_path=target.relative_path or target.target_path.name,
            operation_kind=kind,
            session_id=payload.session_id,
        )
        target.target_path.unlink()
    elif kind in {"rename", "move"}:
        if not payload.destination_path:
            return CodingFileOperationExecuteResult(
                status="blocked",
                operation_kind=kind,
                target_relative_path=target.relative_path,
                rollback_note="No files were changed.",
                blocked_reason="destination_required",
            )
        destination = guard_workspace_path(
            workspace_root=payload.workspace_root,
            target_path=payload.destination_path,
            require_existing=False,
            allow_directory=False,
        )
        if not destination.allowed:
            return CodingFileOperationExecuteResult(
                status="blocked",
                operation_kind=kind,
                target_relative_path=target.relative_path,
                destination_relative_path=destination.relative_path,
                rollback_note="No files were changed.",
                blocked_reason=destination.reason,
            )
        source_descriptor = detect_file_type(target.target_path)
        destination_descriptor = detect_file_type(destination.target_path)
        if destination_descriptor.type_id != source_descriptor.type_id:
            return CodingFileOperationExecuteResult(
                status="blocked",
                operation_kind=kind,
                target_relative_path=target.relative_path,
                destination_relative_path=destination.relative_path,
                rollback_note="No files were changed.",
                blocked_reason="type_changing_move_not_allowed",
            )
        backup = create_coding_backup(
            workspace_root=target.workspace_root,
            source_path=target.target_path,
            source_relative_path=target.relative_path or target.target_path.name,
            operation_kind=kind,
            session_id=payload.session_id,
        )
        destination.target_path.parent.mkdir(parents=True, exist_ok=True)
        target.target_path.rename(destination.target_path)
        destination_relative = destination.relative_path
    else:
        return CodingFileOperationExecuteResult(
            status="unsupported_operation_kind",
            operation_kind=kind,
            target_relative_path=target.relative_path,
            rollback_note="No files were changed.",
            blocked_reason="unsupported_operation_kind",
        )

    audit_written = write_coding_audit_record(
        "file_operation",
        f"{uuid4().hex[:16]}",
        {
            "session_id": payload.session_id,
            "operation_kind": kind,
            "target_relative_path": target.relative_path,
            "destination_relative_path": destination_relative,
            "file_type": descriptor.type_id if descriptor is not None else detect_file_type(payload.destination_path or payload.target_path).type_id,
            "previous_content_hash": previous_hash,
            "new_content_hash": new_hash,
            "operator_approved": True,
            "approval_phrase_present": bool(payload.approval_phrase),
            "approval_id": payload.approval_id,
            "backup_relative_path": backup.backup_relative_path if backup else None,
            "rollback_receipt_id": backup.receipt_id if backup else None,
        },
    )
    return CodingFileOperationExecuteResult(
        status="applied",
        operation_kind=kind,
        target_relative_path=target.relative_path,
        destination_relative_path=destination_relative,
        previous_content_hash=previous_hash,
        new_content_hash=new_hash,
        backup_relative_path=backup.backup_relative_path if backup else None,
        rollback_receipt_id=backup.receipt_id if backup else None,
        mutation_performed=True,
        audit_written=audit_written,
        rollback_note=(
            f"Restore from {backup.backup_relative_path} using receipt {backup.receipt_id}."
            if backup
            else "Created file can be rolled back by deleting the exact approved target."
        ),
        warnings=["File operation used Python filesystem APIs only; no shell, git, or package manager was used."],
    )


__all__ = ("execute_file_operation", "plan_file_operation")
