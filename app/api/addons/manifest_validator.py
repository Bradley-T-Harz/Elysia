"""Strict, non-executing validator for untrusted ``.elysia-addon`` packages."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import BadZipFile, ZipFile

from app.api.addons.path_safety import (
    ARCHIVE_EXTENSIONS,
    MAX_COMPRESSION_RATIO,
    MAX_FILE_BYTES,
    MAX_FILE_COUNT,
    MAX_PACKAGE_BYTES,
    MAX_UNCOMPRESSED_BYTES,
    is_binary_entry,
    is_zip_special_file,
    is_zip_symlink,
    normalize_package_entry,
    validate_package_entry,
)
from app.api.addons.types import AddonInspection, AddonManifest, AddonPermission
from app.api.project_paths import config_path


ADDON_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){1,2}(?:[-+][A-Za-z0-9._-]+)?$")
PRIVATE_PATH_RE = re.compile(r"(?:/home/[^\s\"']+|/Users/[^\s\"']+|[A-Za-z]:\\Users\\[^\s\"']+)")
SECRET_VALUE_RE = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*[^\s,;]+)",
    re.IGNORECASE,
)
NETWORK_CODE_RE = re.compile(
    r"(?:https?://|\brequests\.(?:get|post|put|delete|patch)\b|\bfetch\s*\(|"
    r"\bsocket\.(?:socket|create_connection)\b|\burllib\.request\b)",
    re.IGNORECASE,
)

SUPPORTED_SCHEMA_VERSIONS = {"1.0", "1.1"}
CURRENT_ELYSIA_VERSION = "1.0.0"
SUPPORTED_ADDON_API_VERSIONS = {"1"}
VALID_PROFILES = {"core", "workstation", "creator", "developer", "semantic_local"}
VALID_BRIDGE_PROTOCOLS = {
    "none",
    "json_rpc_stdio",
    "authenticated_loopback_http",
    "unix_socket",
    "file_drop_job_result",
    "tauri_ui_metadata",
    "codev_vscode_client",
}
MAX_TEXT_SCAN_BYTES = MAX_FILE_BYTES
MAX_NESTED_ARCHIVE_PAYLOADS = 5
CODE_EXTENSIONS = {".c", ".cc", ".cpp", ".go", ".java", ".js", ".jsx", ".kt", ".py", ".rs", ".ts", ".tsx"}
TEXT_EXTENSIONS = CODE_EXTENSIONS | {
    ".cfg",
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".json",
    ".md",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


def _payload_signature_kind(data: bytes) -> str | None:
    if data.startswith(b"\x7fELF") or data.startswith(b"MZ") or data[:4] in {
        b"\xfe\xed\xfa\xce",
        b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe",
        b"\xce\xfa\xed\xfe",
    }:
        return "executable_binary"
    if data.startswith(b"#!"):
        return "script"
    if data.startswith(b"PK\x03\x04") or data.startswith(b"\x1f\x8b"):
        return "archive"
    return None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_package_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_permission_vocabulary() -> dict[str, Any]:
    path = config_path("addons", "permission_vocabulary.json")
    if not path.exists():
        raise FileNotFoundError(f"Missing add-on permission vocabulary: {path.name}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("permissions"), dict):
        raise ValueError("Add-on permission vocabulary must contain a permissions object.")
    valid_risks = {"low", "medium", "high", "critical"}
    for key, definition in payload["permissions"].items():
        if not ADDON_ID_RE.fullmatch(str(key)) or not isinstance(definition, dict):
            raise ValueError("Add-on permission vocabulary contains an invalid permission entry.")
        if definition.get("risk_level") not in valid_risks:
            raise ValueError(f"Add-on permission {key} has an invalid risk level.")
        if definition.get("default") not in {"deny", "blocked"}:
            raise ValueError(f"Add-on permission {key} must be deny-by-default or blocked.")
        profiles = definition.get("allowed_profiles")
        if not isinstance(profiles, list) or not set(map(str, profiles)) <= VALID_PROFILES:
            raise ValueError(f"Add-on permission {key} has invalid allowed profiles.")
        if not isinstance(definition.get("runtime_available"), bool):
            raise ValueError(f"Add-on permission {key} must declare runtime availability truth.")
    return payload


def _permission_risk(vocabulary: dict[str, Any], key: str) -> str:
    value = vocabulary.get("permissions", {}).get(key, {})
    return str(value.get("risk_level", "unknown"))


def _object(raw: dict[str, Any], key: str, errors: list[str], *, required: bool) -> dict[str, Any]:
    value = raw.get(key)
    if value is None and not required:
        return {}
    if not isinstance(value, dict):
        errors.append(f"Manifest {key} must be an object.")
        return {}
    return value


def _object_list(raw: dict[str, Any], key: str, errors: list[str], *, required: bool) -> list[dict[str, Any]]:
    value = raw.get(key)
    if value is None and not required:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        errors.append(f"Manifest {key} must be an array of objects.")
        return []
    return [dict(item) for item in value]


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", value)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))


def _compatibility_errors(compatibility: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    current = _version_tuple(CURRENT_ELYSIA_VERSION)
    minimum = _version_tuple(str(compatibility.get("min_elysia_version", "")))
    maximum_raw = str(compatibility.get("max_elysia_version", "")).strip()
    maximum = _version_tuple(maximum_raw) if maximum_raw else None
    addon_api = str(compatibility.get("addon_api_version", ""))
    if minimum is None:
        errors.append("Manifest compatibility.min_elysia_version must be a semantic version.")
    elif current is not None and current < minimum:
        errors.append("Package requires a newer Elysia version.")
    if maximum_raw and maximum is None:
        errors.append("Manifest compatibility.max_elysia_version must be a semantic version when present.")
    elif maximum is not None and current is not None and current > maximum:
        errors.append("Package is not compatible with this Elysia version.")
    if addon_api not in SUPPORTED_ADDON_API_VERSIONS:
        errors.append("Manifest compatibility.addon_api_version is unsupported.")
    return errors


def validate_manifest_payload(
    raw: dict[str, Any],
    vocabulary: dict[str, Any] | None = None,
) -> tuple[AddonManifest | None, list[str], list[str], list[str]]:
    """Validate manifest data without importing or loading any add-on code."""
    errors: list[str] = []
    warnings: list[str] = []
    risk_flags: list[str] = []
    vocabulary = vocabulary or load_permission_vocabulary()

    required_base = {
        "schema_version",
        "addon_id",
        "name",
        "version",
        "publisher",
        "compatibility",
        "entrypoints",
        "permissions",
        "sandbox",
        "checksums",
    }
    for field in sorted(required_base):
        if field not in raw:
            errors.append(f"Manifest missing required field: {field}")

    schema_version = str(raw.get("schema_version", ""))
    strict_v11 = schema_version == "1.1"
    if schema_version and schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"Unsupported schema_version: {schema_version}")

    addon_id = str(raw.get("addon_id", ""))
    version = str(raw.get("version", ""))
    name = str(raw.get("name", "")).strip()
    if addon_id and not ADDON_ID_RE.fullmatch(addon_id):
        errors.append(f"Invalid addon_id: {addon_id}")
    if version and not VERSION_RE.fullmatch(version):
        errors.append(f"Invalid version: {version}")
    if not name or len(name) > 160:
        errors.append("Manifest name must be between 1 and 160 characters.")

    publisher = _object(raw, "publisher", errors, required=True)
    if not str(publisher.get("name", "")).strip():
        errors.append("Manifest publisher.name is required.")

    compatibility = _object(raw, "compatibility", errors, required=True)
    errors.extend(_compatibility_errors(compatibility))

    required_profiles_raw = raw.get("required_profiles", [])
    if not isinstance(required_profiles_raw, list) or any(not isinstance(item, str) for item in required_profiles_raw):
        errors.append("Manifest required_profiles must be an array of profile IDs.")
        required_profiles: list[str] = []
    else:
        required_profiles = sorted(set(str(item).strip() for item in required_profiles_raw if str(item).strip()))
    unknown_profiles = sorted(set(required_profiles) - VALID_PROFILES)
    if unknown_profiles:
        errors.append(f"Manifest references unknown required profiles: {', '.join(unknown_profiles)}")

    entrypoints_raw = raw.get("entrypoints")
    if not isinstance(entrypoints_raw, dict) or not entrypoints_raw:
        errors.append("Manifest entrypoints must be a non-empty object.")
        entrypoints: dict[str, str] = {}
    else:
        entrypoints = {
            str(key).strip(): normalize_package_entry(str(value))
            for key, value in entrypoints_raw.items()
            if str(key).strip() and str(value).strip()
        }
        if not entrypoints:
            errors.append("Manifest entrypoints must contain at least one named path.")

    bridge = _object(raw, "bridge", errors, required=strict_v11)
    if not bridge:
        bridge = {"protocol": "none", "contract_version": "unavailable", "execution_enabled": False}
        warnings.append("Legacy 1.0 manifest has no bridge metadata; runtime bridge authority remains unavailable.")
    bridge_protocol = str(bridge.get("protocol", "none"))
    if bridge_protocol not in VALID_BRIDGE_PROTOCOLS:
        errors.append(f"Manifest bridge.protocol is unsupported: {bridge_protocol}")
    if strict_v11 and not str(bridge.get("contract_version", "")).strip():
        errors.append("Manifest bridge.contract_version is required for schema 1.1.")
    if bridge.get("execution_enabled") is True:
        errors.append("Manifest cannot self-enable add-on execution.")

    known_permissions = set(vocabulary.get("permissions", {}).keys())
    parsed_permissions: list[AddonPermission] = []
    permission_keys: set[str] = set()
    permissions = raw.get("permissions")
    if not isinstance(permissions, list):
        errors.append("Manifest permissions must be an array.")
        permissions = []
    for index, permission in enumerate(permissions):
        if not isinstance(permission, dict):
            errors.append(f"Permission at index {index} must be an object.")
            continue
        key = str(permission.get("key", "")).strip()
        if key in permission_keys:
            errors.append(f"Manifest declares duplicate permission: {key}")
            continue
        permission_keys.add(key)
        if key not in known_permissions:
            errors.append(f"Undeclared permission is not in vocabulary: {key}")
        reason = str(permission.get("reason", "")).strip()
        if not reason:
            errors.append(f"Permission {key or index} requires a human-readable reason.")
        risk_level = _permission_risk(vocabulary, key)
        if str(vocabulary.get("permissions", {}).get(key, {}).get("default")) == "blocked":
            risk_flags.append(f"{key} is hard-blocked by the current add-on permission policy.")
        parsed_permissions.append(AddonPermission(key, bool(permission.get("required", False)), reason, risk_level))
    if not parsed_permissions:
        warnings.append("Manifest declares no permissions; staging still requires exact local approval.")

    network_policy = _object(raw, "network_policy", errors, required=strict_v11)
    filesystem_policy = _object(raw, "filesystem_policy", errors, required=strict_v11)
    memory_policy = _object(raw, "memory_policy", errors, required=strict_v11)
    model_provider_policy = _object(raw, "model_provider_policy", errors, required=strict_v11)
    tool_worker_policy = _object(raw, "tool_worker_policy", errors, required=strict_v11)
    execution = _object(raw, "execution", errors, required=strict_v11)
    sandbox = _object(raw, "sandbox", errors, required=True)
    external_services = _object_list(raw, "external_services", errors, required=strict_v11)
    license_data = _object(raw, "license", errors, required=strict_v11)
    provenance = _object(raw, "provenance", errors, required=strict_v11)
    signing = _object(raw, "signing", errors, required=strict_v11)
    dependencies = _object_list(raw, "dependencies", errors, required=strict_v11)

    if not strict_v11:
        network_policy = network_policy or {"default": "deny", "declared_hosts": []}
        filesystem_policy = filesystem_policy or {"default": "deny", "mounts": []}
        memory_policy = memory_policy or {"default": "deny", "classes": []}
        model_provider_policy = model_provider_policy or {"default": "deny", "providers": []}
        tool_worker_policy = tool_worker_policy or {"default": "deny", "workers": []}
        execution = execution or {"requested": False}
        license_data = license_data or {"spdx": "NOASSERTION"}
        provenance = provenance or {"status": "unreviewed"}
        signing = signing or {"publisher_key_id": None, "signature": None}
        warnings.append("Legacy 1.0 manifest lacks one or more v1.1 governance fields; safe deny-by-default values were applied.")

    if str(network_policy.get("default", "deny")) not in {"deny", "deny_by_default", "disabled"}:
        errors.append("Manifest network_policy.default must be deny-by-default.")
    if str(filesystem_policy.get("default", "deny")) not in {"deny", "project_scoped"}:
        errors.append("Manifest filesystem_policy.default must deny or remain project-scoped.")
    if str(memory_policy.get("default", "deny")) != "deny":
        errors.append("Manifest memory_policy.default must deny access.")
    if execution.get("requested") is True:
        risk_flags.append("Package requests code execution; execution remains disabled until the full local sandbox gate is proven.")
    if sandbox.get("network") not in {"deny_by_default", "disabled", None}:
        errors.append("Manifest sandbox.network must be deny_by_default or disabled.")
    if permission_keys & {"network.fetch", "external_api.call"}:
        if str(network_policy.get("default", "deny")) == "disabled":
            errors.append("Network permission declarations conflict with a disabled network policy.")
    elif external_services:
        errors.append("Manifest declares external services without a network permission.")
    for service in external_services:
        if not str(service.get("id") or service.get("name") or "").strip():
            errors.append("Each external service declaration requires an id or name.")

    if strict_v11 and not str(license_data.get("spdx", "")).strip():
        errors.append("Manifest license.spdx is required for schema 1.1.")
    provenance_status = str(provenance.get("status", "")).strip()
    if strict_v11 and provenance_status not in {"self_declared", "reviewed", "verified", "unreviewed"}:
        errors.append("Manifest provenance.status must be self_declared, reviewed, verified, or unreviewed.")
    if signing.get("signature"):
        warnings.append("Manifest carries a declared signature, but signature verification infrastructure is not live; status is declared_unverified.")
    for dependency in dependencies:
        if not str(dependency.get("id") or dependency.get("name") or dependency.get("package_name") or "").strip():
            errors.append("Each dependency declaration requires an id, name, or package_name.")

    checksums = _object(raw, "checksums", errors, required=True)
    binaries_raw = raw.get("binaries", [])
    if not isinstance(binaries_raw, list) or any(not isinstance(item, str) for item in binaries_raw):
        errors.append("Manifest binaries must be an array of package-relative paths.")
        binaries: list[str] = []
    else:
        binaries = [normalize_package_entry(str(item)) for item in binaries_raw]
        if binaries:
            risk_flags.append(f"Package declares {len(binaries)} executable, script, or binary payload(s) for explicit review.")

    if errors:
        return None, errors, warnings, sorted(set(risk_flags))
    return (
        AddonManifest(
            schema_version=schema_version,
            addon_id=addon_id,
            name=name,
            version=version,
            publisher=publisher,
            compatibility=compatibility,
            required_profiles=required_profiles,
            entrypoints=entrypoints,
            bridge=bridge,
            permissions=parsed_permissions,
            network_policy=network_policy,
            filesystem_policy=filesystem_policy,
            memory_policy=memory_policy,
            model_provider_policy=model_provider_policy,
            tool_worker_policy=tool_worker_policy,
            execution=execution,
            sandbox=sandbox,
            external_services=external_services,
            license=license_data,
            provenance=provenance,
            signing=signing,
            dependencies=dependencies,
            checksums=checksums,
            binaries=binaries,
        ),
        [],
        warnings,
        sorted(set(risk_flags)),
    )


def _scan_text_entry(name: str, data: bytes, *, network_declared: bool) -> list[str]:
    errors: list[str] = []
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in TEXT_EXTENSIONS or len(data) > MAX_TEXT_SCAN_BYTES:
        return errors
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return errors
    if PRIVATE_PATH_RE.search(text):
        errors.append(f"Private absolute-path reference detected in package text: {name}")
    if SECRET_VALUE_RE.search(text):
        errors.append(f"Credential/secret-shaped value detected in package text: {name}")
    if suffix in CODE_EXTENSIONS and NETWORK_CODE_RE.search(text) and not network_declared:
        errors.append(f"Network behavior is present but undeclared in manifest permissions: {name}")
    return errors


def inspect_addon_package(package_path: str | Path) -> AddonInspection:
    """Inspect an untrusted package without creating directories or executing code."""
    path = Path(package_path).expanduser()
    errors: list[str] = []
    warnings: list[str] = []
    risk_flags: list[str] = []
    package_hash: str | None = None
    manifest_hash: str | None = None
    manifest: AddonManifest | None = None
    file_count = 0
    package_size = 0

    if not path.exists() or not path.is_file():
        return AddonInspection(False, str(path), None, None, None, ["Package file does not exist."], [], [], 0, 0, False)
    if path.is_symlink():
        return AddonInspection(False, str(path), None, None, None, ["Symlink package files are not accepted."], [], [], 0, 0, False)
    if path.suffix.lower() not in {".zip", ".elysia-addon"}:
        errors.append("Unsupported add-on package extension. Expected .elysia-addon or inspect-only .zip.")
    if path.suffix.lower() == ".zip":
        warnings.append("ZIP source bundles are inspect-only; rename is not enough to make an installable .elysia-addon.")
    package_size = path.stat().st_size
    if package_size > MAX_PACKAGE_BYTES:
        errors.append(f"Package exceeds maximum compressed size of {MAX_PACKAGE_BYTES} bytes.")
    package_hash = hash_package_file(path)

    try:
        with ZipFile(path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            file_count = len(infos)
            if file_count > MAX_FILE_COUNT:
                errors.append(f"Package exceeds maximum file count of {MAX_FILE_COUNT}.")
            total_uncompressed = sum(max(0, info.file_size) for info in infos)
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                errors.append(f"Package exceeds maximum uncompressed size of {MAX_UNCOMPRESSED_BYTES} bytes.")

            normalized_names: list[str] = []
            info_by_name: dict[str, Any] = {}
            nested_archives = 0
            for info in infos:
                normalized = normalize_package_entry(info.filename)
                normalized_names.append(normalized)
                info_by_name.setdefault(normalized, info)
                errors.extend(validate_package_entry(info.filename))
                if is_zip_symlink(info):
                    errors.append(f"Symlink entries are not allowed: {info.filename}")
                if is_zip_special_file(info):
                    errors.append(f"Special-file entries are not allowed: {info.filename}")
                if info.flag_bits & 0x1:
                    errors.append(f"Encrypted package entries are not allowed: {info.filename}")
                if info.file_size > MAX_FILE_BYTES:
                    errors.append(f"File exceeds maximum size: {info.filename}")
                if info.compress_size == 0 and info.file_size > 0:
                    errors.append(f"Suspicious compression ratio detected: {info.filename}")
                elif info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                    errors.append(f"Suspicious compression ratio detected: {info.filename}")
                if PurePosixPath(normalized).suffix.lower() in ARCHIVE_EXTENSIONS:
                    nested_archives += 1

            duplicate_names = sorted({name for name in normalized_names if normalized_names.count(name) > 1})
            for name in duplicate_names:
                errors.append(f"Duplicate normalized package entry is not allowed: {name}")
            if nested_archives > MAX_NESTED_ARCHIVE_PAYLOADS:
                errors.append("Package contains excessive nested archive payloads.")
            elif nested_archives:
                risk_flags.append(f"Package contains {nested_archives} nested archive payload(s) requiring explicit review.")

            manifest_count = normalized_names.count("manifest.json")
            if manifest_count == 0:
                errors.append("Package is missing manifest.json.")
            elif manifest_count > 1:
                errors.append("Package contains duplicate manifest.json entries.")
            else:
                manifest_info = info_by_name["manifest.json"]
                manifest_bytes = archive.read(manifest_info)
                manifest_hash = sha256_bytes(manifest_bytes)
                try:
                    raw_manifest = json.loads(manifest_bytes.decode("utf-8"))
                    if not isinstance(raw_manifest, dict):
                        errors.append("manifest.json must contain a JSON object.")
                        raw_manifest = {}
                except (UnicodeDecodeError, json.JSONDecodeError):
                    errors.append("manifest.json is not valid UTF-8 JSON.")
                    raw_manifest = {}
                manifest, parse_errors, parse_warnings, parse_risks = validate_manifest_payload(raw_manifest)
                errors.extend(parse_errors)
                warnings.extend(parse_warnings)
                risk_flags.extend(parse_risks)

                if manifest is not None:
                    network_declared = bool(
                        {permission.key for permission in manifest.permissions}
                        & {"network.fetch", "external_api.call"}
                    )
                    errors.extend(_scan_text_entry("manifest.json", manifest_bytes, network_declared=network_declared))
                    names = set(normalized_names)
                    for entrypoint in manifest.entrypoints.values():
                        if entrypoint not in names:
                            errors.append(f"Declared entrypoint is missing: {entrypoint}")
                    declared_binaries = set(manifest.binaries)
                    for binary in declared_binaries:
                        if binary not in names:
                            errors.append(f"Manifest declares a missing binary/script payload: {binary}")
                    for name in names:
                        if is_binary_entry(name) and name not in declared_binaries:
                            errors.append(f"Binary/script-like file is not declared in manifest.binaries: {name}")

                    file_checksums = manifest.checksums.get("files", {})
                    if not isinstance(file_checksums, dict) or not file_checksums:
                        errors.append("Manifest checksums.files must declare package file hashes.")
                        file_checksums = {}
                    normalized_checksums = {normalize_package_entry(str(name)): str(value) for name, value in file_checksums.items()}
                    payload_names = names - {"manifest.json"}
                    for missing in sorted(payload_names - set(normalized_checksums)):
                        errors.append(f"Payload file is missing a declared checksum: {missing}")
                    for extra in sorted(set(normalized_checksums) - payload_names):
                        errors.append(f"Checksum references missing or reserved file: {extra}")

                    for name in sorted(payload_names):
                        info = info_by_name[name]
                        data = archive.read(info)
                        signature_kind = _payload_signature_kind(data)
                        if signature_kind in {"executable_binary", "script"} and name not in declared_binaries:
                            errors.append(f"Executable/script payload signature is undeclared in manifest.binaries: {name}")
                        if signature_kind == "archive" and PurePosixPath(name).suffix.lower() not in ARCHIVE_EXTENSIONS:
                            errors.append(f"Archive payload signature conflicts with its declared file type: {name}")
                        expected = normalized_checksums.get(name)
                        if expected and not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
                            errors.append(f"Checksum is not a SHA-256 digest: {name}")
                        elif expected and sha256_bytes(data).lower() != expected.lower():
                            errors.append(f"Checksum mismatch for {name}.")
                        errors.extend(_scan_text_entry(name, data, network_declared=network_declared))
    except (BadZipFile, OSError, RuntimeError):
        errors.append("Package is not a readable ZIP/.elysia-addon archive.")

    unique_errors = list(dict.fromkeys(errors))
    valid = not unique_errors
    return AddonInspection(
        valid=valid,
        package_path=str(path),
        package_hash=package_hash,
        manifest_hash=manifest_hash,
        manifest=manifest,
        errors=unique_errors,
        warnings=list(dict.fromkeys(warnings)),
        risk_flags=list(dict.fromkeys(risk_flags)),
        file_count=file_count,
        package_size_bytes=package_size,
        installable=valid and manifest is not None and path.suffix.lower() == ".elysia-addon",
    )


__all__ = (
    "CURRENT_ELYSIA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "hash_package_file",
    "inspect_addon_package",
    "load_permission_vocabulary",
    "validate_manifest_payload",
)
