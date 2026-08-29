from __future__ import annotations

from app.api.coding_policy_service import build_coding_status


def test_patch_policy_exposes_proposal_and_approved_apply_only():
    status = build_coding_status()

    assert "/coding/patch/propose" in status.enabled_endpoints
    assert status.boundaries.patch_proposal_allowed is True
    assert status.boundaries.patch_apply_allowed is True
    assert "git_mutation" in status.disabled_capabilities
