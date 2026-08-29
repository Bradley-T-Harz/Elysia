from __future__ import annotations

from app.api.coding_patch_service import propose_patch
from app.api.schemas.coding_patch import CodingPatchProposeRequest


def test_patch_proposal_is_preview_only_and_hashes_diff(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("print('old')\n", encoding="utf-8")

    result = propose_patch(
        CodingPatchProposeRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            target_files=["app.py"],
            change_summary="Update greeting",
            proposed_diff="-print('old')\n+print('new')\n",
        )
    )

    assert result.status == "preview_only"
    assert result.patch_hash
    assert result.allowed_target_files == ["app.py"]
    assert result.apply_allowed is True
    assert "No files were changed" in result.rollback_note


def test_patch_proposal_is_mode_blocked_in_plan_only(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("print('old')\n", encoding="utf-8")

    result = propose_patch(
        CodingPatchProposeRequest(
            approval_mode="plan_only",
            workspace_root=str(tmp_path),
            target_files=["app.py"],
            change_summary="Update greeting",
            proposed_diff="-print('old')\n+print('new')\n",
        )
    )

    assert result.status == "proposal_disabled"
    assert result.apply_allowed is False
    assert any("apply_with_approval" in warning for warning in result.warnings)


def test_patch_proposal_blocks_private_targets(tmp_path):
    result = propose_patch(
        CodingPatchProposeRequest(
            workspace_root=str(tmp_path),
            target_files=["../outside.py", ".env"],
            change_summary="Bad patch",
            proposed_diff="+secret\n",
        )
    )

    assert result.blocked_target_files
    assert result.apply_allowed is False
