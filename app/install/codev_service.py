"""Read-only Codev installation receipt and compatibility truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.api.coding_repo_registry import list_approved_repo_roots

from .paths import ElysiaPaths, resolve_elysia_paths


CODEV_EXTENSION_ID = "ecosyneva-commons.elysia-codev"
CODEV_VERSION = "1.0.0"
CODEV_CONTRACT_VERSION = "vscode-coding-agent-contract-0.1"


def codev_receipt_path(paths: ElysiaPaths | None = None) -> Path:
    resolved = paths or resolve_elysia_paths()
    return resolved.data_dir / "developer" / "codev-install.json"


def read_codev_install_status(paths: ElysiaPaths | None = None) -> dict[str, Any]:
    target = codev_receipt_path(paths)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    valid = (
        isinstance(payload, dict)
        and payload.get("schema_version") == 1
        and payload.get("extension_id") == CODEV_EXTENSION_ID
        and payload.get("install_state") == "installed_by_user"
    )
    version = str(payload.get("version") or "") if valid else ""
    contract = str(payload.get("contract_version") or "") if valid else ""
    compatible = valid and version == CODEV_VERSION and contract == CODEV_CONTRACT_VERSION
    return {
        "state": "installed" if compatible else "incompatible" if valid else "missing",
        "installed": bool(valid),
        "compatible": bool(compatible),
        "version": version or None,
        "expected_version": CODEV_VERSION,
        "contract_version": contract or None,
        "expected_contract_version": CODEV_CONTRACT_VERSION,
        "extension_id": CODEV_EXTENSION_ID,
        "receipt_storage": "XDG user data",
        "raw_path_exposed": False,
    }


def read_codev_repo_approval_status(paths: ElysiaPaths | None = None) -> dict[str, Any]:
    """Return aggregate approval truth without exposing repository labels or paths."""
    resolved = paths or resolve_elysia_paths()
    registry = resolved.config_dir / "coding" / "approved-repos.json"
    approved_count = len(list_approved_repo_roots(registry))
    return {
        "state": "approved" if approved_count else "not_approved",
        "approved_repo_count": approved_count,
        "authority_scope": "exact_repository_roots",
        "shell_authority": False,
        "network_authority": False,
        "push_authority": False,
        "publish_authority": False,
        "raw_paths_exposed": False,
    }


__all__ = (
    "CODEV_CONTRACT_VERSION",
    "CODEV_EXTENSION_ID",
    "CODEV_VERSION",
    "codev_receipt_path",
    "read_codev_install_status",
    "read_codev_repo_approval_status",
)
