"""Policy helpers for the VS Code coding bridge MVP."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.api.coding_approval_modes import approval_mode_policy, normalize_approval_mode
from app.api.project_paths import policy_path
from app.api.schemas.coding import CodingBoundaryFlags, CodingBridgeStatus


POLICY_PATH = policy_path("vscode_coding_agent.yaml")

DANGEROUS_CAPABILITIES = (
    "patch_apply",
    "command_execution",
    "test_execution",
    "git_mutation",
    "package_manager",
    "autonomous_loop",
)


def load_coding_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("VS Code coding agent policy must be a mapping.")
    return data


def coding_boundary_flags(policy: dict[str, Any] | None = None) -> CodingBoundaryFlags:
    loaded = policy or load_coding_policy()
    capabilities = loaded.get("capabilities") or {}
    return CodingBoundaryFlags(
        local_only=bool(loaded.get("local_only", True)),
        marketplace_account_required=bool(loaded.get("marketplace_account_required", False)),
        cloud_upload_allowed=bool(loaded.get("cloud_upload_allowed", False)),
        selected_file_read_allowed=bool(capabilities.get("selected_file_read", False)),
        patch_proposal_allowed=bool(capabilities.get("patch_proposal", False)),
        patch_apply_allowed=bool(capabilities.get("patch_apply", False)),
        command_execution_allowed=bool(capabilities.get("command_execution", False)),
        test_execution_allowed=bool(capabilities.get("test_execution", False)),
        git_mutation_allowed=bool(capabilities.get("git_mutation", False)),
        package_manager_allowed=bool(capabilities.get("package_manager", False)),
        autonomous_loop_allowed=bool(capabilities.get("autonomous_loop", False)),
        source_contents_included=False,
    )


def coding_boundary_flags_for_mode(raw_mode: str | None, policy: dict[str, Any] | None = None) -> CodingBoundaryFlags:
    flags = coding_boundary_flags(policy)
    mode_policy = approval_mode_policy(raw_mode)
    flags.patch_proposal_allowed = flags.patch_proposal_allowed and mode_policy.can_propose_patch
    flags.patch_apply_allowed = flags.patch_apply_allowed and mode_policy.can_apply_patch
    flags.command_execution_allowed = flags.command_execution_allowed and mode_policy.can_run_tests
    flags.test_execution_allowed = flags.test_execution_allowed and mode_policy.can_run_tests
    return flags


def build_coding_status() -> CodingBridgeStatus:
    policy = load_coding_policy()
    capabilities = policy.get("capabilities") or {}
    enabled_endpoints = [
        "/coding/status",
        "/coding/session/start",
        "/coding/chat",
        "/coding/repo/inspect-preview",
    ]
    if capabilities.get("selected_file_read", False):
        enabled_endpoints.append("/coding/file/read-preview")
    if capabilities.get("patch_proposal", False):
        enabled_endpoints.append("/coding/patch/propose")
    if capabilities.get("patch_apply", False):
        enabled_endpoints.append("/coding/patch/apply-approved")
    enabled_endpoints.extend(
        [
            "/coding/file-types",
            "/coding/file/inspect-type",
            "/coding/file/operation-plan",
            "/coding/file/operation-execute-approved",
            "/coding/operation/approve",
            "/coding/operation/result",
            "/coding/operation/audit",
            "/coding/document/inspect",
            "/coding/document/extract-preview",
            "/coding/document/export-plan",
            "/coding/document/export-approved",
            "/coding/document/edit-plan",
            "/coding/document/apply-approved",
            "/coding/data/inspect",
            "/coding/data/preview",
            "/coding/data/export-plan",
            "/coding/data/export-approved",
            "/coding/data/mutation-plan",
            "/coding/data/apply-mutation-approved",
            "/coding/visual/inspect",
            "/coding/visual/preview",
            "/coding/visual/ocr",
            "/coding/visual/analysis",
            "/coding/visual/export-plan",
            "/coding/visual/export-approved",
            "/coding/visual/edit-plan",
            "/coding/visual/apply-approved",
            "/coding/archive/types",
            "/coding/archive/inspect",
            "/coding/archive/extract/plan",
            "/coding/archive/extract/apply",
            "/coding/archive/jobs/{operation_id}",
            "/coding/archive/jobs/{operation_id}/cancel",
            "/coding/archive/artifacts/{artifact_id}",
            "/coding/database/types",
            "/coding/database/inspect",
            "/coding/database/schema/preview",
            "/coding/database/artifacts/{artifact_id}",
            "/coding/binary/types",
            "/coding/binary/inspect",
            "/coding/binary/artifacts/{artifact_id}",
            "/coding/command/plan",
            "/coding/command/run-approved",
            "/coding/command/status/{run_id}",
            "/coding/command/cancel",
            "/coding/git/preview",
            "/coding/task/plan",
        ]
    )
    disabled = [key for key in DANGEROUS_CAPABILITIES if not capabilities.get(key, False)]
    disabled.extend(
        [
            "archive_install",
            "archive_execute",
            "archive_import",
            "archive_auto_open",
            "archive_extract_to_project",
            "archive_autonomous_extraction",
            "database_row_preview",
            "database_arbitrary_sql",
            "database_export",
            "database_mutation",
            "database_extension_install_load",
            "binary_execute",
            "binary_load",
            "binary_import",
            "binary_install",
            "binary_link",
            "binary_mutation",
            "binary_patch",
            "binary_disassemble",
            "binary_decompile",
        ]
    )
    return CodingBridgeStatus(
        contract_version=str(policy.get("contract_version", "vscode-coding-agent-contract-0.1")),
        boundaries=coding_boundary_flags(policy),
        enabled_endpoints=enabled_endpoints,
        disabled_capabilities=disabled,
        notes=list(policy.get("notes") or []),
    )


def preview_limits(policy: dict[str, Any] | None = None) -> tuple[int, int]:
    loaded = policy or load_coding_policy()
    limits = loaded.get("limits") or {}
    max_depth = int(limits.get("max_preview_depth", 3))
    max_entries = int(limits.get("max_preview_entries", 100))
    return max_depth, max_entries


def file_preview_limits(policy: dict[str, Any] | None = None) -> tuple[int, int]:
    loaded = policy or load_coding_policy()
    limits = loaded.get("limits") or {}
    max_bytes = int(limits.get("max_file_preview_bytes", 12000))
    max_lines = int(limits.get("max_file_preview_lines", 240))
    return max_bytes, max_lines


def patch_preview_limit(policy: dict[str, Any] | None = None) -> int:
    loaded = policy or load_coding_policy()
    limits = loaded.get("limits") or {}
    return int(limits.get("max_patch_preview_bytes", 20000))


__all__ = (
    "DANGEROUS_CAPABILITIES",
    "POLICY_PATH",
    "build_coding_status",
    "coding_boundary_flags",
    "coding_boundary_flags_for_mode",
    "load_coding_policy",
    "file_preview_limits",
    "patch_preview_limit",
    "normalize_approval_mode",
    "preview_limits",
)
