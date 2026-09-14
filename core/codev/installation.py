"""Canonical installed Core truth. Editors, workspaces and pairing are independent."""
from __future__ import annotations

import os

from app.install.codev_service import CODEV_CONTRACT_VERSION
from app.install.codev_core import inspect_core, CORE_CONTRACT, PRODUCT_VERSION
from app.install.paths import ElysiaPaths
from core.codev.contracts import Capability, Installation, CLIENT_CONTRACT


def _runtime_available() -> tuple[bool, str]:
    from app.api.account_service import AccountAuthError, get_authenticated_principal
    from app.api.user_control_service import managed_capability_allowed
    from app.cognition.emergency_control import emergency_active
    try:
        get_authenticated_principal()
    except AccountAuthError:
        return False, "Sign in to the local Elysia profile to use Codev."
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
        "structured_edit_proposal": ["workspace_propose_grant", "selected_files", "local_compute_admission"],
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


def resolve_installation(paths: ElysiaPaths | None = None, *, runtime_ready: bool = True) -> Installation:
    identity = inspect_core(paths)
    if not identity.installed:
        return Installation(state="absent", note=identity.note)
    common = dict(installed=True, version=identity.version, source="installed_core_manifest",
                  installation_state="incompatible" if identity.state == "incompatible" else "installed",
                  runtime_instance_id=os.environ.get("ELYSIA_RUNTIME_INSTANCE_ID"),
                  installation_id=identity.installation_id,
                  contract_versions=[CLIENT_CONTRACT, CORE_CONTRACT, CODEV_CONTRACT_VERSION])
    if not identity.compatible:
        return Installation(state="incompatible" if identity.state == "incompatible" else "degraded",
                            runtime_state="degraded", note=identity.note, **common)
    try:
        session_ready, note = _runtime_available()
    except Exception:
        session_ready, note = False, "Local session policy is temporarily unavailable."
    usable = runtime_ready and session_ready
    return Installation(state="installed_ready" if runtime_ready else "installed_unavailable",
                        runtime_state="ready" if runtime_ready else "disconnected",
                        session_state="ready" if session_ready else "approval_needed",
                        usable=usable, capabilities=capability_manifest(usable=usable),
                        note=note if runtime_ready else "Codev Core is installed; its local service is unavailable.",
                        **common)
