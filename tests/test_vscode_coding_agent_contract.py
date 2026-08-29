from __future__ import annotations

from pathlib import Path

import yaml


POLICY_PATH = Path("config/policies/vscode_coding_agent.yaml")


def test_vscode_coding_agent_policy_contract_is_local_and_governed():
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))

    assert policy["contract_version"] == "vscode-coding-agent-contract-0.1"
    assert policy["local_only"] is True
    assert policy["marketplace_account_required"] is False
    assert policy["cloud_upload_allowed"] is False

    capabilities = policy["capabilities"]
    assert capabilities["status"] is True
    assert capabilities["session_start"] is True
    assert capabilities["chat"] is True
    assert capabilities["repo_inspect_preview"] is True
    for key in (
        "selected_file_read",
        "patch_proposal",
        "patch_apply",
        "command_execution",
        "test_execution",
        "generic_text_file_operations",
        "operation_approval_tokens",
        "operation_audit_read",
    ):
        assert capabilities[key] is True

    for key in (
        "git_mutation",
        "package_manager",
        "autonomous_loop",
    ):
        assert capabilities[key] is False


def test_vscode_coding_docs_claim_only_governed_execution_authority():
    docs = "\n".join(
        [
            Path("docs/api/vscode_coding_agent_contract.md").read_text(encoding="utf-8"),
            Path("docs/security/vscode_coding_agent_boundary.md").read_text(encoding="utf-8"),
        ]
    )

    lowered = docs.lower()
    assert "unapproved patch application is disabled" in lowered
    assert "unapproved or arbitrary command execution" in lowered
    assert "repository inspection preview returns metadata only" in lowered
    assert "exact, expiring, one-time approval" in lowered
