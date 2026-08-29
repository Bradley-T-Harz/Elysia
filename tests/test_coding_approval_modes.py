from __future__ import annotations

from app.api.coding_approval_modes import approval_mode_policy, normalize_approval_mode
from app.api.coding_policy_service import coding_boundary_flags_for_mode


def test_approval_modes_normalize_known_and_legacy_names():
    assert normalize_approval_mode("read_only") == "read_only"
    assert normalize_approval_mode("path_preview") == "path_preview"
    assert normalize_approval_mode("patch_preview") == "apply_with_approval"
    assert normalize_approval_mode("ask_first") == "apply_with_approval"
    assert normalize_approval_mode("unknown") == "plan_only"


def test_approval_mode_capability_ladder():
    assert approval_mode_policy("read_only").can_propose_patch is False
    assert approval_mode_policy("plan_only").can_apply_patch is False
    assert approval_mode_policy("path_preview").can_inspect_paths is True
    assert approval_mode_policy("path_preview").can_apply_patch is False
    assert approval_mode_policy("apply_with_approval").can_apply_patch is True
    assert approval_mode_policy("apply_with_approval").can_run_tests is False
    assert approval_mode_policy("test_with_approval").can_run_tests is True


def test_mode_adjusted_boundaries_do_not_grant_global_power_by_default():
    plan_flags = coding_boundary_flags_for_mode("plan_only")
    test_flags = coding_boundary_flags_for_mode("test_with_approval")

    assert plan_flags.patch_proposal_allowed is False
    assert plan_flags.patch_apply_allowed is False
    assert plan_flags.command_execution_allowed is False
    assert test_flags.patch_apply_allowed is True
    assert test_flags.command_execution_allowed is True
    assert test_flags.git_mutation_allowed is False
    assert test_flags.package_manager_allowed is False
