"""Atomic XDG-local add-on registry, staging, and sanitized receipt storage."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from zipfile import ZipFile

from app.api.addons.manifest_validator import hash_package_file, inspect_addon_package
from app.api.addons.path_safety import (
    addons_root,
    ensure_addons_tree,
    ensure_within_directory,
    normalize_package_entry,
    safe_install_leaf,
)
from app.api.addons.permission_resolver import current_disabled_resolution
from app.api.addons.types import AddonInspection, RegistryEntry


_PRIVATE_PATH_RE = re.compile(r"(?:/home/|/Users/|[A-Za-z]:\\Users\\)[^\s,;\"']+")
_SECRET_RE = re.compile(r"\b(token|secret|password|api[_ -]?key|credential)\s*[:=]\s*[^\s,;]+", re.IGNORECASE)
_AUDIT_DETAIL_KEYS = {
    "action",
    "actor",
    "approved_permission_count",
    "current_state",
    "effective_permission_count",
    "error_codes",
    "execution_enabled",
    "file_count",
    "files_retained",
    "manifest_hash",
    "package_hash",
    "plan_hash",
    "proposed_state",
    "reason_code",
    "requested_permission_count",
    "source",
    "state_version",
}


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sanitize_text(value: object) -> str:
    text = str(value).replace("\n", " ")[:500]
    text = _PRIVATE_PATH_RE.sub("[local path hidden]", text)
    return _SECRET_RE.sub(r"\1=[private value hidden]", text)


def _sanitize_details(details: dict[str, Any] | None) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in (details or {}).items():
        if key not in _AUDIT_DETAIL_KEYS:
            continue
        if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            sanitized[key] = value
        elif isinstance(value, list):
            sanitized[key] = [_sanitize_text(item) for item in value[:25]]
        else:
            sanitized[key] = _sanitize_text(value)
    return sanitized


def registry_path() -> Path:
    return addons_root() / "manifests" / "installed_registry.json"


def audit_path() -> Path:
    return addons_root() / "audit" / "addon_audit.jsonl"


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_registry() -> dict[str, Any]:
    path = registry_path()
    if not path.exists():
        return {"schema_version": 2, "revision": _canonical_hash({}), "entries": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "schema_version": 2,
            "revision": _canonical_hash({}),
            "entries": {},
            "warnings": ["Registry state is unreadable; add-on mutation is blocked pending manual review."],
        }
    if not isinstance(payload, dict) or not isinstance(payload.get("entries", {}), dict):
        return {
            "schema_version": 2,
            "revision": _canonical_hash({}),
            "entries": {},
            "warnings": ["Registry shape is invalid; add-on mutation is blocked pending manual review."],
        }
    payload.setdefault("schema_version", 2)
    payload.setdefault("entries", {})
    payload["revision"] = _canonical_hash(payload["entries"])
    return payload


def save_registry(registry: dict[str, Any]) -> str:
    path = registry_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    registry = {
        "schema_version": 2,
        "revision": _canonical_hash(registry.get("entries", {})),
        "entries": registry.get("entries", {}),
    }
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return str(registry["revision"])


def append_audit(
    action: str,
    result: str,
    *,
    addon_id: str | None = None,
    version: str | None = None,
    request_id: str | None = None,
    operation_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    path = audit_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    record = {
        "timestamp_utc": now_utc(),
        "action": _sanitize_text(action),
        "addon_id": _sanitize_text(addon_id) if addon_id else None,
        "version": _sanitize_text(version) if version else None,
        "request_id": _sanitize_text(request_id) if request_id else None,
        "operation_id": _sanitize_text(operation_id) if operation_id else None,
        "result": _sanitize_text(result),
        "details": _sanitize_details(details),
        "raw_paths_exposed": False,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def read_audit(limit: int = 100) -> list[dict[str, Any]]:
    path = audit_path()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-max(1, min(limit, 500)) :]
    except OSError:
        return [{"timestamp_utc": None, "action": "audit_read_error", "result": "error", "raw_paths_exposed": False}]
    records: list[dict[str, Any]] = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            record = {"timestamp_utc": None, "action": "audit_parse_error", "result": "error"}
        details = _sanitize_details(record.get("details") if isinstance(record.get("details"), dict) else None)
        records.append(
            {
                "timestamp_utc": record.get("timestamp_utc"),
                "action": _sanitize_text(record.get("action", "unknown")),
                "addon_id": _sanitize_text(record.get("addon_id")) if record.get("addon_id") else None,
                "version": _sanitize_text(record.get("version")) if record.get("version") else None,
                "request_id": _sanitize_text(record.get("request_id")) if record.get("request_id") else None,
                "operation_id": _sanitize_text(record.get("operation_id")) if record.get("operation_id") else None,
                "result": _sanitize_text(record.get("result", "unknown")),
                "reason_code": details.get("reason_code"),
                "planned_action": details.get("action"),
                "current_state": details.get("current_state"),
                "proposed_state": details.get("proposed_state"),
                "package_hash": details.get("package_hash"),
                "plan_hash": details.get("plan_hash"),
                "execution_enabled": details.get("execution_enabled", False),
                "raw_paths_exposed": False,
            }
        )
    return records


def _public_entry(entry: dict[str, Any]) -> dict[str, Any]:
    status = "enabled_limited" if entry.get("status") == "enabled" else str(entry.get("status", "installed_disabled"))
    requested_raw = entry.get("permissions_requested", []) if isinstance(entry.get("permissions_requested", []), list) else []
    requested = [
        {
            "key": str(item.get("key", "")),
            "required": bool(item.get("required", False)),
            "risk_level": str(item.get("risk_level", "unknown")),
        }
        for item in requested_raw
        if isinstance(item, dict)
    ]
    approved = [str(item) for item in entry.get("permissions_approved", []) if str(item)]
    effective = [str(item) for item in entry.get("permissions_effective", []) if str(item)]
    return {
        "addon_id": str(entry.get("addon_id", "")),
        "version": str(entry.get("version", "")),
        "name": str(entry.get("name", entry.get("addon_id", "Add-on"))),
        "publisher": {"name": _sanitize_text((entry.get("publisher") or {}).get("name", "undeclared"))}
        if isinstance(entry.get("publisher"), dict)
        else {"name": "undeclared"},
        "status": status,
        "permissions_requested": requested,
        "permissions_approved": approved,
        "permissions_effective": effective,
        "permissions_granted": effective,
        "permissions_denied": [str(item) for item in entry.get("permissions_denied", [])],
        "package_hash": str(entry.get("package_hash", "")),
        "manifest_hash": str(entry.get("manifest_hash", "")),
        "installed_at": entry.get("installed_at"),
        "enabled_at": entry.get("enabled_at"),
        "disabled_at": entry.get("disabled_at"),
        "removed_at": entry.get("removed_at"),
        "source": str(entry.get("source", "local")),
        "revocation_status": str(entry.get("revocation_status", "not_revoked")),
        "last_verified_at": entry.get("last_verified_at"),
        "execution_enabled": False,
        "bridge_authority_active": False,
        "files_retained": bool(entry.get("files_retained", True)),
        "state_version": int(entry.get("state_version", 1)),
        "storage_label": "XDG user add-on data",
        "raw_paths_exposed": False,
    }


def list_installed() -> list[dict[str, Any]]:
    entries = load_registry().get("entries", {})
    return [_public_entry(entry) for _, entry in sorted(entries.items()) if isinstance(entry, dict)]


def get_storage_entry(addon_id: str, version: str) -> dict[str, Any] | None:
    entry = load_registry().get("entries", {}).get(f"{addon_id}@{version}")
    return dict(entry) if isinstance(entry, dict) else None


def registry_revision() -> str:
    return str(load_registry().get("revision", ""))


def _extract_package(inspection: AddonInspection, destination: Path) -> None:
    root = addons_root()
    ensure_within_directory(destination, root)
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    with ZipFile(inspection.package_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            relative = Path(normalize_package_entry(info.filename))
            target = destination / relative
            ensure_within_directory(target, destination)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            try:
                target.chmod(0o600)
            except OSError:
                pass


def stage_validated_package(
    inspection: AddonInspection,
    *,
    source: str,
    approved_permissions: list[str],
    request_id: str,
    operation_id: str,
) -> dict[str, Any]:
    """Atomically stage an already validated exact package, always disabled."""
    if not inspection.installable or inspection.manifest is None or not inspection.package_hash:
        return {"ok": False, "installed": False, "reason_code": "package_not_installable", "errors": inspection.errors}
    manifest = inspection.manifest
    if hash_package_file(inspection.package_path) != inspection.package_hash:
        return {"ok": False, "installed": False, "reason_code": "package_hash_changed", "errors": ["Package changed after validation."]}

    paths = ensure_addons_tree()
    destination = paths["installed"] / safe_install_leaf(manifest.addon_id) / safe_install_leaf(manifest.version)
    ensure_within_directory(destination, paths["root"])
    if destination.exists():
        return {
            "ok": False,
            "installed": False,
            "already_installed": True,
            "reason_code": "version_already_staged",
            "entry": _public_entry(get_storage_entry(manifest.addon_id, manifest.version) or {}),
            "errors": ["This exact add-on version is already staged locally."],
        }

    stage_parent = paths["staged"]
    stage_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".addon-stage-", dir=stage_parent))
    try:
        _extract_package(inspection, temporary / "payload")
        if hash_package_file(inspection.package_path) != inspection.package_hash:
            return {"ok": False, "installed": False, "reason_code": "package_hash_changed", "errors": ["Package changed during staging."]}
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.replace(temporary / "payload", destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    permission_resolution = current_disabled_resolution(
        manifest.permissions,
        approved_permissions=approved_permissions,
        active_profiles=manifest.required_profiles or ("core",),
    )
    timestamp = now_utc()
    storage_key = str(destination.relative_to(paths["root"]))
    entry = RegistryEntry(
        addon_id=manifest.addon_id,
        version=manifest.version,
        name=manifest.name,
        publisher=manifest.publisher,
        storage_key=storage_key,
        status="installed_disabled",
        permissions_requested=[permission.__dict__.copy() for permission in manifest.permissions],
        permissions_approved=list(permission_resolution.approved),
        permissions_effective=[],
        permissions_granted=[],
        permissions_denied=list(permission_resolution.denied),
        package_hash=inspection.package_hash,
        manifest_hash=inspection.manifest_hash or "",
        installed_at=timestamp,
        enabled_at=None,
        disabled_at=timestamp,
        removed_at=None,
        source=source,
        rollback_snapshot=None,
        revocation_status="not_revoked",
        last_verified_at=timestamp,
        execution_enabled=False,
        bridge_authority_active=False,
        files_retained=True,
    )
    registry = load_registry()
    registry.setdefault("entries", {})[entry.key()] = entry.to_storage_payload()
    revision = save_registry(registry)
    public = entry.to_payload()
    public["registry_revision"] = revision
    append_audit(
        "install_disabled",
        "applied",
        addon_id=manifest.addon_id,
        version=manifest.version,
        request_id=request_id,
        operation_id=operation_id,
        details={
            "package_hash": inspection.package_hash,
            "manifest_hash": inspection.manifest_hash,
            "proposed_state": "installed_disabled",
            "requested_permission_count": len(permission_resolution.requested),
            "approved_permission_count": len(permission_resolution.approved),
            "effective_permission_count": 0,
            "execution_enabled": False,
            "source": source,
        },
    )
    return {
        "ok": True,
        "installed": True,
        "entry": public,
        "inspection": inspection.to_payload(),
        "permission_resolution": permission_resolution.to_payload(),
        "files_retained": True,
        "execution_enabled": False,
    }


def apply_registry_state(
    addon_id: str,
    version: str,
    target_state: str,
    *,
    approved_permissions: list[str],
    expected_state: str,
    expected_package_hash: str,
    request_id: str,
    operation_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    registry = load_registry()
    key = f"{addon_id}@{version}"
    entry = registry.setdefault("entries", {}).get(key)
    if not isinstance(entry, dict):
        return {"ok": False, "reason_code": "addon_not_found", "error": "Add-on version is not installed."}
    current_state = "enabled_limited" if entry.get("status") == "enabled" else str(entry.get("status"))
    if current_state != expected_state:
        return {"ok": False, "reason_code": "stale_state", "error": "Add-on state changed after planning."}
    if str(entry.get("package_hash")) != expected_package_hash:
        return {"ok": False, "reason_code": "package_hash_changed", "error": "Installed package hash no longer matches the approved plan."}

    requested = entry.get("permissions_requested", []) if isinstance(entry.get("permissions_requested"), list) else []
    revoked = target_state == "revoked"
    resolution = current_disabled_resolution(
        requested,
        approved_permissions=approved_permissions,
        active_profiles=("core", "workstation", "creator", "developer"),
        revoked=revoked,
    )
    timestamp = now_utc()
    entry["status"] = target_state
    entry["permissions_approved"] = list(resolution.approved) if target_state == "enabled_limited" else []
    entry["permissions_effective"] = []
    entry["permissions_granted"] = []
    entry["permissions_denied"] = list(resolution.denied)
    entry["execution_enabled"] = False
    entry["bridge_authority_active"] = False
    entry["last_verified_at"] = timestamp
    entry["state_version"] = int(entry.get("state_version", 1)) + 1
    entry["files_retained"] = True
    if target_state == "enabled_limited":
        entry["enabled_at"] = timestamp
    if target_state == "disabled":
        entry["disabled_at"] = timestamp
    if target_state == "revoked":
        entry["revocation_status"] = "revoked"
        entry["disabled_at"] = timestamp
    if target_state == "removed":
        entry["removed_at"] = timestamp
    revision = save_registry(registry)
    entry["registry_revision"] = revision
    append_audit(
        f"transition_{target_state}",
        "applied",
        addon_id=addon_id,
        version=version,
        request_id=request_id,
        operation_id=operation_id,
        details={
            "current_state": current_state,
            "proposed_state": target_state,
            "package_hash": expected_package_hash,
            "approved_permission_count": len(resolution.approved),
            "effective_permission_count": 0,
            "execution_enabled": False,
            "files_retained": True,
            "reason_code": reason or "explicit_local_transition",
            "state_version": entry["state_version"],
        },
    )
    return {
        "ok": True,
        "entry": _public_entry(entry),
        "permission_resolution": resolution.to_payload(),
        "execution_enabled": False,
        "files_retained": True,
        "removal_semantics": "registry_marked_removed_files_retained" if target_state == "removed" else None,
        "revocation_semantics": "trust_withdrawn_no_runtime_was_active" if target_state == "revoked" else None,
    }


def rollback(addon_id: str, version: str) -> dict[str, Any]:
    entry = get_storage_entry(addon_id, version)
    if not entry:
        append_audit("rollback", "not_found", addon_id=addon_id, version=version)
        return {"ok": False, "error": "No staged add-on version to roll back."}
    append_audit("rollback", "blocked", addon_id=addon_id, version=version, details={"reason_code": "no_snapshot"})
    return {
        "ok": False,
        "blocked": True,
        "reason": "No exact rollback snapshot exists. Disable or revoke instead; staged files remain local.",
        "entry": _public_entry(entry),
        "files_retained": True,
        "execution_enabled": False,
    }


def validation_only_sandbox(package_path: str | Path) -> dict[str, Any]:
    inspection = inspect_addon_package(package_path)
    append_audit(
        "validation_only",
        "passed" if inspection.valid else "blocked",
        addon_id=inspection.manifest.addon_id if inspection.manifest else None,
        version=inspection.manifest.version if inspection.manifest else None,
        details={"error_codes": ["validation_failed"] if inspection.errors else [], "file_count": inspection.file_count},
    )
    return {
        "sandbox_mode": "validation_only",
        "local_only": True,
        "cloud_sandbox_required": False,
        "host_docker_socket_allowed": False,
        "executed_code": False,
        "network_allowed": False,
        "shell_allowed": False,
        "package_manager_allowed": False,
        "hardware_allowed": False,
        "private_memory_allowed": False,
        "doctor_proof_required": True,
        "result": "passed" if inspection.valid else "blocked",
        "inspection": inspection.to_payload(),
    }


def status_payload() -> dict[str, Any]:
    entries = list_installed()
    registry_exists = registry_path().exists()
    return {
        "storage_label": "XDG user add-on data",
        "registry_initialized": registry_exists,
        "raw_paths_exposed": False,
        "installed_count": len(entries),
        "enabled_limited_count": sum(1 for entry in entries if entry.get("status") == "enabled_limited"),
        "enabled_count": sum(1 for entry in entries if entry.get("status") == "enabled_limited"),
        "revoked_count": sum(1 for entry in entries if entry.get("status") == "revoked"),
        "website_can_install": False,
        "install_requires_local_approval": True,
        "state_changes_require_exact_one_time_approval": True,
        "sandbox_mode": "validation_only",
        "sandbox_local_only": True,
        "cloud_sandbox_required": False,
        "execution_enabled": False,
        "bridge_authority_active": False,
        "network_allowed": False,
        "shell_allowed": False,
        "package_manager_allowed": False,
        "private_memory_allowed": False,
        "host_docker_socket_allowed": False,
        "deep_link_status": "invitation_parser_only_no_install_authority",
    }


def create_install_plan(package_path: str | Path, *, source: str = "manual_file") -> dict[str, Any]:
    """Compatibility read path; exact state-changing plans live in lifecycle_service."""
    inspection = inspect_addon_package(package_path)
    return {
        "plan_state": "exact_transition_plan_required" if inspection.installable else "blocked_by_validation",
        "source": source,
        "inspection": inspection.to_payload(),
        "recommended_action": "Create exact install-disabled transition plan" if inspection.installable else "Do not install",
        "storage_label": "XDG user add-on data",
        "execution_enabled": False,
        "enable_requires_separate_approval": True,
        "sandbox_mode": "validation_only",
        "website_control_allowed": False,
        "private_core_access_allowed": False,
    }


def install_disabled(package_path: str | Path, *, source: str = "manual_file") -> dict[str, Any]:
    """Block legacy unapproved mutation; use lifecycle plan/approve/apply."""
    inspection = inspect_addon_package(package_path)
    append_audit("install_disabled", "blocked", details={"reason_code": "exact_transition_plan_required", "source": source})
    return {
        "ok": False,
        "installed": False,
        "reason_code": "exact_transition_plan_required",
        "errors": ["An exact, unexpired, one-time approved install-disabled plan is required."],
        "inspection": inspection.to_payload(),
    }


def update_status(addon_id: str, version: str, status: str, *, reason: str | None = None) -> dict[str, Any]:
    """Block legacy direct status mutation; use lifecycle plan/approve/apply."""
    append_audit(
        "status_update",
        "blocked",
        addon_id=addon_id,
        version=version,
        details={"proposed_state": status, "reason_code": "exact_transition_plan_required"},
    )
    return {"ok": False, "reason_code": "exact_transition_plan_required", "error": "Exact approved transition plan required."}


__all__ = (
    "append_audit",
    "apply_registry_state",
    "audit_path",
    "create_install_plan",
    "get_storage_entry",
    "install_disabled",
    "list_installed",
    "load_registry",
    "read_audit",
    "registry_path",
    "registry_revision",
    "rollback",
    "save_registry",
    "stage_validated_package",
    "status_payload",
    "update_status",
    "validation_only_sandbox",
)
