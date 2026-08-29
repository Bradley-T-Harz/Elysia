from __future__ import annotations

from typing import Any

from app.api.coding_operation_service import approve_operation
from app.api.schemas.coding_operations import CodingOperationApproveRequest


def approval_fields_for_plan(
    *,
    workspace_root: str,
    operation_kind: str,
    mutation_class: str,
    source_file: str,
    plan: Any,
) -> dict[str, str | None]:
    exact_files = [source_file]
    target = getattr(plan, "target_relative_path", None)
    relative = getattr(plan, "relative_path", None)
    if target and target != relative:
        exact_files.append(target)
    approval = approve_operation(
        CodingOperationApproveRequest(
            operation_kind=operation_kind,
            operation_summary=f"Approve exact {operation_kind} test operation",
            workspace_root=workspace_root,
            exact_files=exact_files,
            source_hash=getattr(plan, "source_hash", None),
            plan_hash=getattr(plan, "plan_hash", None) or "",
            allowed_mutation_class=mutation_class,
            operator_approved=True,
            approval_phrase="approve exact planned operation",
            rollback_note="Use the governed backup or derived-output receipt.",
        )
    )
    return {"approval_id": approval.approval_id, "approval_token": approval.approval_token}
