from __future__ import annotations

import difflib
from hashlib import sha256

from app.api.coding_patch_service import apply_patch_with_approval, patch_hash_for_diff
from app.api.coding_operation_service import approve_operation
from app.api.schemas.coding_operations import CodingOperationApproveRequest
from app.api.schemas.coding_patch import CodingPatchApplyRequest


def _diff(old: str, new: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="a/fibonacci_bug.py",
            tofile="b/fibonacci_bug.py",
        )
    )


def _approve_patch(tmp_path, source_name: str, source_hash: str, patch_hash: str):
    return approve_operation(
        CodingOperationApproveRequest(
            operation_kind="patch_apply",
            operation_summary="Apply exact test patch",
            workspace_root=str(tmp_path),
            exact_files=[source_name],
            source_hash=source_hash,
            plan_hash=patch_hash,
            allowed_mutation_class="text_patch",
            operator_approved=True,
            approval_phrase="approve exact patch",
            rollback_note="Use governed backup receipt.",
        )
    )


def test_patch_apply_requires_approval(tmp_path):
    source = tmp_path / "fibonacci_bug.py"
    old = "a = b\nb = a + b\n"
    new = "a, b = b, a + b\n"
    source.write_text(old, encoding="utf-8")
    diff = _diff(old, new)
    source_hash = sha256(old.encode("utf-8")).hexdigest()
    patch_hash = patch_hash_for_diff(diff)
    approval = _approve_patch(tmp_path, "fibonacci_bug.py", source_hash, patch_hash)

    result = apply_patch_with_approval(
        CodingPatchApplyRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            target_file="fibonacci_bug.py",
            proposed_diff=diff,
            expected_content_hash=source_hash,
            patch_hash=patch_hash,
            approval_id=approval.approval_id,
            approval_token=approval.approval_token,
        )
    )

    assert result.status == "approval_required"
    assert result.mutation_performed is False
    assert source.read_text(encoding="utf-8") == old


def test_patch_apply_applies_unified_diff_with_hash_guard(tmp_path):
    source = tmp_path / "fibonacci_bug.py"
    old = "a = b\nb = a + b\n"
    new = "a, b = b, a + b\n"
    source.write_text(old, encoding="utf-8")
    diff = _diff(old, new)
    source_hash = sha256(old.encode("utf-8")).hexdigest()
    patch_hash = patch_hash_for_diff(diff)
    approval = _approve_patch(tmp_path, "fibonacci_bug.py", source_hash, patch_hash)

    result = apply_patch_with_approval(
        CodingPatchApplyRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            target_file="fibonacci_bug.py",
            proposed_diff=diff,
            expected_content_hash=source_hash,
            patch_hash=patch_hash,
            approval_id=approval.approval_id,
            approval_token=approval.approval_token,
            operator_approved=True,
            approval_phrase="Apply approved patch",
        )
    )

    assert result.status == "applied"
    assert result.mutation_performed is True
    assert source.read_text(encoding="utf-8") == new
    assert result.backup_relative_path
    assert (tmp_path / result.backup_relative_path).read_text(encoding="utf-8") == old


def test_patch_apply_blocks_stale_content(tmp_path):
    source = tmp_path / "fibonacci_bug.py"
    old = "a = b\nb = a + b\n"
    source.write_text("changed\n", encoding="utf-8")
    diff = _diff(old, "a, b = b, a + b\n")

    result = apply_patch_with_approval(
        CodingPatchApplyRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            target_file="fibonacci_bug.py",
            proposed_diff=diff,
            expected_content_hash=sha256(old.encode("utf-8")).hexdigest(),
            patch_hash=patch_hash_for_diff(diff),
            operator_approved=True,
        )
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "current_content_hash_mismatch"


def test_patch_apply_blocks_in_plan_only_even_with_operator_approval(tmp_path):
    source = tmp_path / "fibonacci_bug.py"
    old = "a = b\nb = a + b\n"
    new = "a, b = b, a + b\n"
    source.write_text(old, encoding="utf-8")
    diff = _diff(old, new)

    result = apply_patch_with_approval(
        CodingPatchApplyRequest(
            approval_mode="plan_only",
            workspace_root=str(tmp_path),
            target_file="fibonacci_bug.py",
            proposed_diff=diff,
            expected_content_hash=sha256(old.encode("utf-8")).hexdigest(),
            patch_hash=patch_hash_for_diff(diff),
            operator_approved=True,
        )
    )

    assert result.status == "blocked_by_approval_mode"
    assert result.mutation_performed is False
    assert source.read_text(encoding="utf-8") == old
