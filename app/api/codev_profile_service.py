"""Sanitized Developer-profile truth for the official Codev companion."""

from __future__ import annotations

from enum import Enum
import shutil
from typing import Any

from app.install.codev_service import (
    read_codev_install_status,
    read_codev_repo_approval_status,
)
from app.install.local_auth import build_local_api_auth_policy
from app.install.profile_service import resolve_install_profile_status


def build_codev_developer_profile_status() -> dict[str, Any]:
    profile, warnings = resolve_install_profile_status()
    developer = next(
        (item for item in profile.available_profiles if item.profile_id == "developer"),
        None,
    )
    auth = build_local_api_auth_policy(initialize=False).public_summary()
    codev = read_codev_install_status()
    repo_approval = read_codev_repo_approval_status()
    dependencies: dict[str, dict[str, Any]] = {}
    for item in profile.dependencies:
        if item.dependency_id not in {"vscode", "git", "codev_vsix"}:
            continue
        raw_status = item.status.value if isinstance(item.status, Enum) else str(item.status)
        version = item.version
        if item.dependency_id == "vscode" and any(
            shutil.which(command)
            for command in ("code", "code-insiders", "codium", "vscodium")
        ):
            raw_status = "present"
        elif item.dependency_id == "codev_vsix":
            raw_status = (
                "present"
                if codev["compatible"]
                else "degraded"
                if codev["installed"]
                else "missing"
            )
            version = codev["version"]
        dependencies[item.dependency_id] = {
            "status": raw_status,
            "required": item.required,
            "activation_state": item.activation_state,
            "version": version,
        }
    active = "developer" in profile.resolved_profile_ids
    base_readiness = (
        developer.readiness.value
        if developer and isinstance(developer.readiness, Enum)
        else str(developer.readiness)
        if developer
        else "unknown"
    )
    required_dependencies_ready = bool(dependencies) and all(
        not item["required"] or item["status"] == "present"
        for item in dependencies.values()
    )
    readiness = "ready" if active and required_dependencies_ready else base_readiness
    ready = bool(active and codev["compatible"] and developer and readiness == "ready")
    return {
        "status": "ready" if ready else "profile_gated" if not active else "degraded",
        "official_addon": True,
        "listing_state": "official_v1_release",
        "public_distribution_supported": True,
        "canonical_marketplace_url": "https://elysiaecobotics.com/marketplace/browse",
        "live_availability_source": "canonical_external_release_surfaces",
        "in_app_install_control_available": False,
        "active": active,
        "profile_id": "developer",
        "profile_label": developer.display_name if developer else "Developer / Codev",
        "profile_readiness": readiness,
        "codev_install": codev,
        "repo_approval": repo_approval,
        "dependencies": dependencies,
        "api_version": "1.0.0",
        "coding_contract_version": "vscode-coding-agent-contract-0.1",
        "local_auth": auth,
        "repo_approval_contract": "coding-repo-approval-1.0",
        "command_catalog_contract": "coding-command-catalog-1.0",
        "task_lab_contract": "coding-task-lab-1.0",
        "source_development_supported": True,
        "install_authority_available": False,
        "cloud_upload_allowed": False,
        "git_mutation_allowed": False,
        "arbitrary_shell_allowed": False,
        "raw_paths_exposed": False,
        "warnings": [
            *warnings,
            "Codev uses the authenticated local API for mutations; credential values are never returned.",
            "Public distribution is reported by the canonical external release surfaces; this local status never grants installation authority.",
        ],
    }


__all__ = ("build_codev_developer_profile_status",)
