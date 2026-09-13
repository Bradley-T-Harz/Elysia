"""Read-only installation truth, independent of client processes and source trees.

The v1 receipt records a user-approved installation; it is not remote binary
attestation or proof that a VS Code process is running. This adapter is the
single replacement point for a future native multi-client installation receipt.
"""
from __future__ import annotations

import json
import os
import re
import stat

from app.install.codev_service import CODEV_CONTRACT_VERSION, CODEV_EXTENSION_ID, CODEV_VERSION, codev_receipt_path
from app.install.paths import ElysiaPaths
from core.codev.contracts import Capability, Installation, CLIENT_CONTRACT
from core.codev.filesystem import read_bytes


def _runtime_available() -> tuple[bool, str]:
    from app.api.account_service import AccountAuthError, get_authenticated_principal
    from app.api.user_control_service import managed_capability_allowed
    from app.install.profile_service import resolve_install_profile_status
    from app.cognition.emergency_control import emergency_active
    try:
        get_authenticated_principal()
    except AccountAuthError:
        return False, "Sign in to the local Elysia profile to use Codev."
    profile, _ = resolve_install_profile_status()
    if "developer" not in profile.resolved_profile_ids:
        return False, "The local Developer profile is not selected."
    if not managed_capability_allowed("coding_execution"):
        return False, "The installation policy does not permit coding operations."
    if emergency_active():
        return False, "Elysia emergency posture is active."
    return True, "Codev is installed. Every workspace and operation requires its own grant."


def capability_manifest(*, usable: bool) -> list[Capability]:
    live = {
        "workspace_read": ["workspace_grant", "selected_files"],
        "workspace_write_plan": ["workspace_grant"],
        "patch_propose": ["workspace_grant", "selected_files"],
        "patch_apply": ["workspace_write_grant", "exact_revision_approval"],
        "git_inspect": ["workspace_grant"],
        "command_catalog": [],
        "command_execute": ["command_grant", "exact_command_approval"],
    }
    unavailable = {
        "test_execute": "Repository scripts require a qualified isolated worker.",
        "build_execute": "Repository scripts require a qualified isolated worker.",
        "package_install": "Package installation is not exposed to Codev clients.",
        "network_public_docs": "Public network access is not granted.",
        "remote_repo_read": "Remote repository access is not granted.",
        "remote_repo_write": "Remote repository writes are not granted.",
        "forge_read": "Pairing and a separate Forge workspace grant are required.",
        "forge_write": "A revision-specific remote save requires separate approval.",
        "marketplace_workspace_read": "Pairing and an explicit browser workspace grant are required.",
        "marketplace_workspace_write": "A browser patch requires a revision-specific approval.",
        "cloud_model": "No external model authority is granted.",
    }
    return [Capability(id=key, available=usable, requires=required,
                       reason=None if usable else "Codev is unavailable in this local session.")
            for key, required in live.items()] + [Capability(id=key, available=False, reason=reason)
                                                  for key, reason in unavailable.items()]


def resolve_installation(paths: ElysiaPaths | None = None) -> Installation:
    target = codev_receipt_path(paths)
    try:
        info = target.lstat()
    except FileNotFoundError:
        return Installation(state="absent", note="Codev is not installed.")
    except OSError:
        return Installation(state="degraded", note="Installation evidence is unavailable.")
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o077:
        return Installation(state="degraded", note="Installation receipt ownership or permissions could not be verified.")
    try:
        payload = json.loads(read_bytes(target.parent, target.name, limit=16 * 1024))
        after = target.lstat()
        if (info.st_ino, info.st_dev, info.st_mtime_ns, info.st_ctime_ns) != (after.st_ino, after.st_dev, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("installation_receipt_changed")
    except (OSError, ValueError):
        return Installation(state="degraded", note="Installation receipt is unreadable or malformed.")
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or payload.get("extension_id") != CODEV_EXTENSION_ID or payload.get("install_state") != "installed_by_user":
        return Installation(state="degraded", note="Installation evidence is not a supported Codev receipt.")
    version = payload.get("version")
    contract = payload.get("contract_version")
    if version != CODEV_VERSION or contract != CODEV_CONTRACT_VERSION:
        return Installation(state="incompatible", installed=True, source="legacy_install_receipt",
                            version=version if isinstance(version, str) and re.fullmatch(r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}", version) else None,
                            note="The installed Codev version or compatibility contract is unsupported.")
    common = dict(installed=True, version=CODEV_VERSION, source="legacy_install_receipt",
                  contract_versions=[CLIENT_CONTRACT, CODEV_CONTRACT_VERSION])
    if not re.fullmatch(r"[a-f0-9]{64}", str(payload.get("package_sha256") or "")):
        return Installation(state="installed_unavailable", **common,
                            note="The legacy receipt lacks package evidence. Review installation through the existing installer.")
    try:
        usable, note = _runtime_available()
    except Exception:
        return Installation(state="degraded", **common, note="Local capability checks are unavailable.")
    return Installation(state="installed_ready" if usable else "installed_unavailable", usable=usable,
                        capabilities=capability_manifest(usable=usable), note=note, **common)
