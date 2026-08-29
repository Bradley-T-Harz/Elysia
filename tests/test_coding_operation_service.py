from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.api import coding_operation_service
from app.api.coding_operation_service import approve_operation, clear_operation_state_for_tests, consume_operation_approval, record_operation_result
from app.api.schemas.coding_operations import CodingOperationApproveRequest, CodingOperationResultRequest


def test_operation_approval_requires_operator_approval(tmp_path):
    clear_operation_state_for_tests()
    result = approve_operation(
        CodingOperationApproveRequest(
            operation_kind="patch_apply",
            operation_summary="Apply proposed patch",
            workspace_root=str(tmp_path),
            exact_files=["app.py"],
            plan_hash="patch-hash",
            allowed_mutation_class="text_patch",
            rollback_note="Restore previous file from diff.",
        )
    )

    assert result.status == "approval_required"
    assert result.approval_token is None


def test_operation_result_rejects_wrong_token(tmp_path, monkeypatch):
    from app.api import coding_audit_service

    monkeypatch.setattr(coding_audit_service, "AUDIT_ROOT", tmp_path / "audit")
    clear_operation_state_for_tests()
    approval = approve_operation(
        CodingOperationApproveRequest(
            operation_kind="patch_apply",
            operation_summary="Apply proposed patch",
            workspace_root=str(tmp_path),
            exact_files=["app.py"],
            plan_hash="patch-hash",
            allowed_mutation_class="text_patch",
            operator_approved=True,
            approval_phrase="approve exact files",
            rollback_note="Restore previous file from diff.",
        )
    )

    result = record_operation_result(
        CodingOperationResultRequest(
            approval_id=approval.approval_id,
            approval_token="wrong",
            status="complete",
            result_summary="done",
        )
    )

    assert result.status == "denied"
    assert result.execution_performed is False


def test_operation_result_rejects_unknown_approval_id():
    result = record_operation_result(
        CodingOperationResultRequest(
            approval_id="missing",
            approval_token="anything",
            status="complete",
            result_summary="must be denied",
        )
    )

    assert result.status == "denied"
    assert "unknown" in result.result_summary.lower()


def _exact_patch_approval(tmp_path):
    return approve_operation(
        CodingOperationApproveRequest(
            operation_kind="patch_apply",
            operation_summary="Apply exact patch",
            workspace_root=str(tmp_path),
            exact_files=["app.py"],
            source_hash="source-hash",
            plan_hash="patch-hash",
            allowed_mutation_class="text_patch",
            operator_approved=True,
            rollback_note="Restore the governed backup.",
        )
    )


def _consume_exact(tmp_path, approval):
    return consume_operation_approval(
        approval_id=approval.approval_id,
        approval_token=approval.approval_token,
        operation_kind="patch_apply",
        workspace_root=str(tmp_path),
        exact_files=["app.py"],
        source_hash="source-hash",
        plan_hash="patch-hash",
        allowed_mutation_class="text_patch",
    )


def test_approval_is_one_time_and_exact(tmp_path):
    approval = _exact_patch_approval(tmp_path)

    first = _consume_exact(tmp_path, approval)
    second = _consume_exact(tmp_path, approval)

    assert first.allowed is True
    assert second.allowed is False
    assert second.reason == "approval_already_used"


def test_approval_rejects_hash_mismatch_without_consuming(tmp_path):
    approval = _exact_patch_approval(tmp_path)
    mismatch = consume_operation_approval(
        approval_id=approval.approval_id,
        approval_token=approval.approval_token,
        operation_kind="patch_apply",
        workspace_root=str(tmp_path),
        exact_files=["app.py"],
        source_hash="different",
        plan_hash="patch-hash",
        allowed_mutation_class="text_patch",
    )

    assert mismatch.allowed is False
    assert mismatch.reason == "approval_source_hash_mismatch"
    assert _consume_exact(tmp_path, approval).allowed is True


def test_expired_approval_is_rejected(tmp_path):
    approval = _exact_patch_approval(tmp_path)
    coding_operation_service._APPROVALS[approval.approval_id].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    result = _consume_exact(tmp_path, approval)

    assert result.allowed is False
    assert result.reason == "approval_expired"
