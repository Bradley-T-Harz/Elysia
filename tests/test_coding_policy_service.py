from __future__ import annotations

from app.api.coding_policy_service import build_coding_status, coding_boundary_flags, load_coding_policy


def test_coding_policy_loads_and_builds_status():
    policy = load_coding_policy()
    status = build_coding_status()

    assert policy["contract_version"] == status.contract_version
    assert "/coding/status" in status.enabled_endpoints
    assert "/coding/repo/inspect-preview" in status.enabled_endpoints
    assert "/coding/file/read-preview" in status.enabled_endpoints
    assert "/coding/patch/propose" in status.enabled_endpoints
    assert "git_mutation" in status.disabled_capabilities
    assert "package_manager" in status.disabled_capabilities


def test_coding_boundary_flags_do_not_grant_dangerous_authority():
    flags = coding_boundary_flags()

    assert flags.local_only is True
    assert flags.marketplace_account_required is False
    assert flags.cloud_upload_allowed is False
    assert flags.selected_file_read_allowed is True
    assert flags.patch_proposal_allowed is True
    assert flags.patch_apply_allowed is True
    assert flags.command_execution_allowed is True
    assert flags.test_execution_allowed is True
    assert flags.git_mutation_allowed is False
    assert flags.package_manager_allowed is False
    assert flags.autonomous_loop_allowed is False
    assert flags.source_contents_included is False
