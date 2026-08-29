"""Shared types for governed local add-on package handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Literal


_PRIVATE_PATH_RE = re.compile(r"(?:/home/|/Users/|[A-Za-z]:\\Users\\)[^\s,;\"']+")
_SECRET_RE = re.compile(r"\b(token|secret|password|api[_ -]?key|credential)\s*[:=]\s*[^\s,;]+", re.IGNORECASE)


def sanitize_public_text(value: object) -> str:
    text = str(value).replace("\n", " ")[:500]
    text = _PRIVATE_PATH_RE.sub("[local path hidden]", text)
    return _SECRET_RE.sub(r"\1=[private value hidden]", text)


AddonLifecycleState = Literal[
    "draft",
    "packaged",
    "submitted",
    "pending_review",
    "approved",
    "rejected",
    "installed_disabled",
    "enabled_limited",
    "disabled",
    "revoked",
    "removed",
]
AddonStatus = AddonLifecycleState


@dataclass(frozen=True)
class AddonPermission:
    key: str
    required: bool
    reason: str
    risk_level: str


@dataclass(frozen=True)
class AddonManifest:
    schema_version: str
    addon_id: str
    name: str
    version: str
    publisher: dict[str, Any]
    compatibility: dict[str, Any]
    required_profiles: list[str]
    entrypoints: dict[str, str]
    bridge: dict[str, Any]
    permissions: list[AddonPermission]
    network_policy: dict[str, Any]
    filesystem_policy: dict[str, Any]
    memory_policy: dict[str, Any]
    model_provider_policy: dict[str, Any]
    tool_worker_policy: dict[str, Any]
    execution: dict[str, Any]
    sandbox: dict[str, Any]
    external_services: list[dict[str, Any]]
    license: dict[str, Any]
    provenance: dict[str, Any]
    signing: dict[str, Any]
    dependencies: list[dict[str, Any]]
    checksums: dict[str, Any]
    binaries: list[str] = field(default_factory=list)


@dataclass
class AddonInspection:
    valid: bool
    package_path: str
    package_hash: str | None
    manifest_hash: str | None
    manifest: AddonManifest | None
    errors: list[str]
    warnings: list[str]
    risk_flags: list[str]
    file_count: int
    package_size_bytes: int
    installable: bool

    def to_payload(self) -> dict[str, Any]:
        """Return an allowlisted public payload with no raw local path."""
        return {
            "valid": self.valid,
            "package_label": sanitize_public_text(Path(self.package_path).name),
            "raw_paths_exposed": False,
            "package_hash": self.package_hash,
            "manifest_hash": self.manifest_hash,
            "manifest": manifest_to_payload(self.manifest),
            "errors": [sanitize_public_text(item) for item in self.errors],
            "warnings": [sanitize_public_text(item) for item in self.warnings],
            "risk_flags": [sanitize_public_text(item) for item in self.risk_flags],
            "file_count": self.file_count,
            "package_size_bytes": self.package_size_bytes,
            "installable": self.installable,
            "inspection_mode": "static_only",
            "executed_code": False,
        }


@dataclass
class RegistryEntry:
    addon_id: str
    version: str
    name: str
    publisher: dict[str, Any]
    storage_key: str
    status: AddonStatus
    permissions_requested: list[dict[str, Any]]
    permissions_approved: list[str]
    permissions_effective: list[str]
    permissions_granted: list[str]
    permissions_denied: list[str]
    package_hash: str
    manifest_hash: str
    installed_at: str | None
    enabled_at: str | None
    disabled_at: str | None
    removed_at: str | None
    source: str
    rollback_snapshot: str | None
    revocation_status: str
    last_verified_at: str | None
    execution_enabled: bool = False
    bridge_authority_active: bool = False
    files_retained: bool = True
    state_version: int = 1
    registry_revision: str = ""

    def key(self) -> str:
        return f"{self.addon_id}@{self.version}"

    def to_payload(self) -> dict[str, Any]:
        """Return registry truth without the internal storage key."""
        payload = self.to_storage_payload()
        payload.pop("storage_key", None)
        payload["publisher"] = {"name": sanitize_public_text(self.publisher.get("name", "undeclared"))}
        payload["permissions_requested"] = [
            {
                "key": str(item.get("key", "")),
                "required": bool(item.get("required", False)),
                "risk_level": str(item.get("risk_level", "unknown")),
            }
            for item in self.permissions_requested
            if isinstance(item, dict)
        ]
        payload["storage_label"] = "XDG user add-on data"
        payload["raw_paths_exposed"] = False
        return payload

    def to_storage_payload(self) -> dict[str, Any]:
        return self.__dict__.copy()


def manifest_to_payload(manifest: AddonManifest | None) -> dict[str, Any] | None:
    """Return bounded manifest truth, never the untrusted raw manifest payload."""
    if manifest is None:
        return None
    publisher_name = sanitize_public_text(manifest.publisher.get("name", "undeclared"))[:160]
    compatibility = {
        "min_elysia_version": manifest.compatibility.get("min_elysia_version"),
        "max_elysia_version": manifest.compatibility.get("max_elysia_version"),
        "addon_api_version": manifest.compatibility.get("addon_api_version"),
    }
    return {
        "schema_version": manifest.schema_version,
        "addon_id": manifest.addon_id,
        "name": sanitize_public_text(manifest.name),
        "version": manifest.version,
        "publisher": {"name": publisher_name},
        "compatibility": compatibility,
        "required_profiles": manifest.required_profiles,
        "entrypoint_kinds": sorted(manifest.entrypoints),
        "bridge": {
            "protocol": manifest.bridge.get("protocol", "none"),
            "contract_version": manifest.bridge.get("contract_version"),
            "execution_enabled": False,
        },
        "permissions": [
            {"key": permission.key, "required": permission.required, "risk_level": permission.risk_level}
            for permission in manifest.permissions
        ],
        "policy_summary": {
            "network": manifest.network_policy.get("default", "deny"),
            "filesystem": manifest.filesystem_policy.get("default", "deny"),
            "memory": manifest.memory_policy.get("default", "deny"),
            "model_provider": manifest.model_provider_policy.get("default", "deny"),
            "tool_worker": manifest.tool_worker_policy.get("default", "deny"),
        },
        "execution_requested": bool(manifest.execution.get("requested", False)),
        "sandbox_required": bool(manifest.sandbox.get("required", False)),
        "external_service_count": len(manifest.external_services),
        "license": {"spdx": manifest.license.get("spdx", "NOASSERTION")},
        "provenance_status": manifest.provenance.get("status", "unreviewed"),
        "signature_status": "unsigned" if not manifest.signing.get("signature") else "declared_unverified",
        "dependency_count": len(manifest.dependencies),
        "checksum_file_count": len(manifest.checksums.get("files", {})) if isinstance(manifest.checksums.get("files"), dict) else 0,
        "binary_count": len(manifest.binaries),
        "raw_manifest_exposed": False,
    }


__all__ = (
    "AddonInspection",
    "AddonLifecycleState",
    "AddonManifest",
    "AddonPermission",
    "AddonStatus",
    "RegistryEntry",
    "manifest_to_payload",
    "sanitize_public_text",
)
