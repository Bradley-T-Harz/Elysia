"""One development facade, retaining the v1 compatibility adapters.

Existing coding adapters implement format-specific work. New clients use this
facade and an additional actor/workspace grant boundary. A legacy boolean is
never translated into a one-time operation approval.
"""

from __future__ import annotations

from uuid import uuid4
from app.api.schemas.coding_patch import CodingPatchProposeRequest, CodingPatchProposeResult, CodingPatchApplyRequest, CodingPatchApplyResult
from app.api.schemas.coding_commands import CodingCommandRunApprovedRequest, CodingCommandRunResult


def propose_patch(payload: CodingPatchProposeRequest) -> CodingPatchProposeResult:
    from app.api.coding_patch_service import propose_patch as execute
    return execute(payload)


def apply_patch_with_approval(payload: CodingPatchApplyRequest) -> CodingPatchApplyResult:
    from app.api.coding_patch_service import apply_patch_with_approval as execute
    return execute(payload)


def run_approved_command(payload: CodingCommandRunApprovedRequest) -> CodingCommandRunResult:
    from app.api.coding_process_service import run_approved_command as execute
    return execute(payload)


def refuse_legacy_execution(operation: str, request_id: str | None) -> tuple[str, str]:
    from app.api.coding_audit_service import write_coding_audit_record
    request_id = request_id or f"codev_{uuid4().hex}"
    reason = "Exact, expiring operation approval is required. Review this operation through the governed coding workflow."
    write_coding_audit_record("legacy_execution_blocked", request_id, {
        "operation_kind": operation, "status": "blocked",
        "mutation_performed": False, "execution_performed": False,
        "reason": "legacy_boolean_is_not_exact_approval",
    })
    return request_id, reason
