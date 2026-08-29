from __future__ import annotations

from app.api.addon_action_plan_service import build_addon_action_plan
from app.api.schemas.addon_actions import (
    AddonActionManifest,
    AddonActionPlanRequest,
    AddonDependencySummary,
)


def test_addon_action_plan_is_preview_only_and_non_executing():
    plan = build_addon_action_plan(
        AddonActionPlanRequest(
            addon_id="advanced-pdf-parser",
            addon_name="Advanced PDF Parser",
            publisher="EcoSyneva Commons",
            trust_tier="official",
            local_only=True,
            network_access=False,
            dependencies=[
                AddonDependencySummary(
                    ecosystem="python",
                    package_name="pdfplumber",
                    source="pypi",
                    version_constraint=">=0.11",
                    required=True,
                )
            ],
            action=AddonActionManifest(
                action_key="prepare_install",
                action_label="Prepare install plan",
                action_kind="python_package_install",
                allowed=True,
                risk_level="moderate",
                requires_local_operator_password=True,
                network_access=False,
            ),
        )
    )

    assert plan.plan_state == "execution_not_implemented"
    assert plan.execution_enabled is False
    assert plan.mutation_allowed is False
    assert plan.command_execution_allowed is False
    assert plan.package_manager_allowed is False
    assert plan.shell_allowed is False
    assert plan.subprocess_allowed is False
    assert plan.requires_local_operator_password is True
    assert plan.dependency_count == 1
    assert "python:pdfplumber >=0.11 from pypi" in plan.dependency_summary
    assert plan.local_files_sent is False
    assert plan.memory_sent is False
    assert plan.request_traces_sent is False
    assert plan.dependency_inventory_sent is False


def test_addon_action_plan_blocks_manifest_disallowed_action():
    plan = build_addon_action_plan(
        AddonActionPlanRequest(
            addon_id="blocked-addon",
            addon_name="Blocked Add-on",
            action=AddonActionManifest(
                action_key="install",
                action_label="Install",
                action_kind="setup_script",
                allowed=False,
                risk_level="high",
            ),
        )
    )

    assert plan.plan_state == "blocked_by_manifest"
    assert plan.execution_enabled is False
    assert "not allowed" in plan.refusal_reason


def test_addon_action_plan_refuses_missing_developer_action():
    plan = build_addon_action_plan(
        AddonActionPlanRequest(
            addon_id="manual-only",
            addon_name="Manual Only Add-on",
            action=AddonActionManifest(
                action_key="developer_action_missing",
                action_label="Install action not declared by developer",
                action_kind="developer_action_missing",
                allowed=False,
                risk_level="unknown",
            ),
        )
    )

    assert plan.plan_state == "developer_action_missing"
    assert plan.execution_enabled is False
    assert plan.mutation_allowed is False
    assert "does not declare this action" in plan.refusal_reason


def test_addons_page_does_not_claim_local_installation():
    source = __import__("pathlib").Path("apps/elysia-desktop/src/AddonsPage.tsx").read_text(encoding="utf-8")

    assert "Installed locally" not in source
    assert "Enabled locally" not in source
    assert "Uninstalled locally" not in source
    assert "Install now" not in source
