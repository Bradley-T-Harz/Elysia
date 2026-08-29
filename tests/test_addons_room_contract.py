from __future__ import annotations

from pathlib import Path

import yaml


CONTRACT_PATH = Path("config/ui/addons_room_contract.yaml")


def load_contract() -> dict:
    data = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_addons_room_contract_loads_and_is_operator_only():
    contract = load_contract()

    room = contract["room"]
    assert room["operator_only"] is True
    assert room["model_accessible"] is False
    assert room["chat_accessible"] is False
    assert room["memory_promotion_allowed"] is False


def test_addons_room_requires_marketplace_link_gate():
    contract = load_contract()

    gate = contract["gate"]
    assert gate["requires_marketplace_frontend_session"] is True
    assert gate["requires_local_marketplace_link"] is True
    assert gate["requires_session_user_id_matches_local_link"] is True
    messages = gate["locked_messages"]
    assert messages["no_marketplace_session"] == "Sign in to Marketplace in Personal Identity to use Add-ons."
    assert messages["signed_in_not_linked"] == "Marketplace is signed in, but this local Elysia chamber is not linked yet."
    assert messages["account_mismatch"] == (
        "You are signed into a different Marketplace account than the one linked to this local Elysia chamber."
    )


def test_addons_room_local_actions_use_exact_nonexecuting_transitions():
    actions = load_contract()["actions"]

    for action_key in ("install", "enable", "disable", "revoke"):
      assert actions[action_key]["live"] is True
      assert actions[action_key]["exact_plan_approval_apply"] is True
    assert actions["install"]["execution"] is False
    assert actions["enable"]["execution"] is False
    assert actions["uninstall"]["files_deleted"] is False
    assert actions["uninstall"]["files_retained"] is True


def test_addons_room_grants_no_local_execution_authority():
    local_execution = load_contract()["local_execution"]

    assert local_execution["command_execution_allowed"] is False
    assert local_execution["package_install_allowed"] is False
    assert local_execution["package_uninstall_allowed"] is False
    assert local_execution["shell_allowed"] is False
    assert local_execution["subprocess_allowed"] is False
    assert local_execution["file_mutation_allowed"] is False
    assert local_execution["package_staging_file_mutation_allowed"] is True
    assert local_execution["arbitrary_core_import_allowed"] is False


def test_addons_room_upload_and_review_truth_is_fail_closed():
    contract = load_contract()
    assert contract["gate"]["local_package_manager_requires_marketplace_session"] is False
    assert contract["submission"]["upload_live"] is False
    assert contract["submission"]["website_upload_is_local_only"] is False
    assert contract["submission"]["ordinary_intake_executes_code"] is False
    assert contract["review"]["admin_review_guarantees_safety"] is False
    assert contract["official_candidates"]["codev"]["local_vsix_install_action_live"] is True
    assert contract["official_candidates"]["codev"]["public_distribution_supported"] is True
    assert contract["official_candidates"]["codev"]["in_app_marketplace_install_action_live"] is False


def test_addons_room_forbids_private_uploads_and_service_role_language():
    contract = load_contract()
    forbidden_uploads = set(contract["forbidden_uploads"])

    assert "local_elysia_password" in forbidden_uploads
    assert "local_files" in forbidden_uploads
    assert "memory" in forbidden_uploads
    assert "request_traces" in forbidden_uploads
    assert "dependency_inventory" in forbidden_uploads
    assert "local_paths" in forbidden_uploads
    assert "private_profile_fields" in forbidden_uploads
    assert "service_role" not in repr(contract).lower()
