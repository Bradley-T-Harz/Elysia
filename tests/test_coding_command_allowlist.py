from __future__ import annotations

from app.api.coding_command_allowlist_service import find_allowlist_match, load_command_allowlist
from app.api.coding_command_plan_service import plan_command
from app.api.schemas.coding_commands import CodingCommandPlanRequest


SAFE_GIT_DIFF = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "credential.helper=", "diff", "--no-ext-diff", "--no-textconv", "--check"]


def test_command_allowlist_matches_exact_frontend_typecheck():
    policy = load_command_allowlist()
    match = find_allowlist_match(
        ["npm", "--prefix", "apps/elysia-desktop", "run", "typecheck"],
        policy,
    )

    assert match is not None
    assert match["id"] == "frontend_typecheck"


def test_command_plan_blocks_package_install(tmp_path):
    result = plan_command(
        CodingCommandPlanRequest(
            workspace_root=str(tmp_path),
            command=["npm", "install"],
            purpose="install package",
        )
    )

    assert result.status == "blocked"
    assert result.execution_enabled is False
    assert result.blocked_reason.startswith("blocked_term")


def test_command_plan_enables_safe_exact_allowlisted_command_after_approval(tmp_path):
    result = plan_command(
        CodingCommandPlanRequest(
            approval_mode="test_with_approval",
            workspace_root=str(tmp_path),
            command=SAFE_GIT_DIFF,
            purpose="diff whitespace check",
        )
    )

    assert result.allowlist_match is True
    assert result.execution_enabled is True
    assert result.blocked_reason is None


def test_command_plan_blocks_allowlisted_command_outside_test_mode(tmp_path):
    result = plan_command(
        CodingCommandPlanRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            command=SAFE_GIT_DIFF,
            purpose="diff whitespace check",
        )
    )

    assert result.allowlist_match is True
    assert result.execution_enabled is False
    assert result.blocked_reason == "approval_mode_does_not_allow_command_execution"


def test_command_plan_gates_workspace_controlled_build_scripts(tmp_path):
    result = plan_command(
        CodingCommandPlanRequest(
            approval_mode="test_with_approval",
            workspace_root=str(tmp_path),
            command=["npm", "--prefix", "apps/elysia-desktop", "run", "build"],
            purpose="frontend build",
        )
    )

    assert result.allowlist_match is True
    assert result.execution_enabled is False
    assert result.blocked_reason == "command_disabled_by_policy"
    assert any("ambient" in warning.lower() for warning in result.warnings)
