"""Exact Ubuntu prerequisite preview and explicitly authorized installation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
import yaml

from .component_graph_service import load_component_graph
from .dependency_disposition_service import external_prerequisite_guidance
from .hardware_service import detect_local_hardware
from .paths import ElysiaPaths, resolve_elysia_paths


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "config" / "install" / "system_prerequisites.yaml"
CONTRACT_VERSION = "elysia-system-prerequisites-1.0"
PREVIEW_TTL_SECONDS = 1800


class SystemPrerequisiteError(RuntimeError):
    """A prerequisite operation could not be proven safe."""


class SystemPrerequisitePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    component_ids: list[str] = Field(min_length=1, max_length=16)


class SystemPrerequisiteApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    preview_id: str = Field(pattern=r"^prereq_[a-f0-9]{24}$")
    approval_token: str = Field(min_length=32, max_length=256)
    operator_approved: bool


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_manifest() -> dict[str, Any]:
    try:
        payload = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SystemPrerequisiteError("The system-prerequisite manifest is unavailable.") from exc
    graph_dependencies = {
        item
        for component in load_component_graph()["components"].values()
        for item in component["system_dependencies"]
    }
    if (
        not isinstance(payload, dict)
        or payload.get("version") != 1
        or payload.get("contract_version") != CONTRACT_VERSION
        or set(payload.get("dependencies", {})) != graph_dependencies
        or payload.get("rules", {}).get("silent_sudo") is not False
        or payload.get("rules", {}).get("exact_package_version_preview") is not True
        or payload.get("rules", {}).get("full_setup_runs_as_root") is not False
        or payload.get("rules", {}).get("unlisted_package_operation_allowed") is not False
    ):
        raise SystemPrerequisiteError("The system-prerequisite manifest is incomplete or inconsistent.")
    return payload


def _private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=f".{path.name}-", suffix=".tmp", delete=False,
    ) as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    temporary.replace(path)


def _private_read(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
        raise SystemPrerequisiteError("The private prerequisite preview is unavailable or unsafe.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemPrerequisiteError("The private prerequisite preview is invalid.") from exc
    if not isinstance(payload, dict):
        raise SystemPrerequisiteError("The private prerequisite preview is invalid.")
    return payload


def _installed_version(package: str) -> str | None:
    dpkg = shutil.which("dpkg-query")
    if not dpkg:
        return None
    result = subprocess.run(
        [dpkg, "-W", "-f=${Status}\t${Version}\n", package],
        capture_output=True, text=True, timeout=8, check=False,
    )
    if result.returncode != 0:
        return None
    status, _, version = result.stdout.strip().partition("\t")
    return version if status == "install ok installed" and version else None


def _candidate_version(package: str) -> str | None:
    apt_cache = shutil.which("apt-cache")
    if not apt_cache:
        return None
    result = subprocess.run(
        [apt_cache, "policy", package], capture_output=True, text=True,
        timeout=10, check=False,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        label, separator, value = line.strip().partition(":")
        if label == "Candidate" and separator and value.strip() not in {"", "(none)"}:
            return value.strip()
    return None


class SystemPrerequisiteService:
    def __init__(self, paths: ElysiaPaths | None = None) -> None:
        self.paths = paths or resolve_elysia_paths()
        self.preview_root = self.paths.state_dir / "setup" / "prerequisite-previews"
        self.receipt_path = self.paths.state_dir / "setup" / "system-prerequisites.json"

    def inspect(self, component_ids: list[str]) -> dict[str, Any]:
        manifest = _load_manifest()
        graph = load_component_graph()
        if not component_ids or any(item not in graph["components"] for item in component_ids):
            raise SystemPrerequisiteError("The prerequisite request contains an unknown component.")
        dependency_ids = sorted({
            dependency
            for component_id in component_ids
            for dependency in graph["components"][component_id]["system_dependencies"]
        })
        hardware = detect_local_hardware()
        rows: list[dict[str, Any]] = []
        package_operations: dict[str, str] = {}
        external_missing: list[str] = []
        for dependency_id in dependency_ids:
            record = manifest["dependencies"][dependency_id]
            kind = str(record["kind"])
            packages = [str(item) for item in record.get("packages", [])]
            installed: dict[str, str] = {}
            missing_packages: list[str] = []
            for package in packages:
                version = _installed_version(package)
                if version:
                    installed[package] = version
                else:
                    missing_packages.append(package)
                    candidate = _candidate_version(package)
                    if not candidate:
                        external_missing.append(dependency_id)
                    else:
                        package_operations[package] = candidate
            present = not missing_packages
            if kind.startswith("external"):
                commands = [str(item) for item in record.get("commands", [])]
                if record.get("command"):
                    commands.append(str(record["command"]))
                present = any(shutil.which(command) for command in commands)
                if not present and kind == "external":
                    external_missing.append(dependency_id)
            elif kind == "hardware_optional":
                present = bool(hardware["gpu"]["cuda_variant_supported"])
            elif kind == "logical":
                present = hardware["cpu_only_supported"] is True
            rows.append({
                "dependency_id": dependency_id,
                "kind": kind,
                "purpose": record["purpose"],
                "present": present,
                "installed_package_versions": installed,
                "missing_packages": missing_packages,
                "optional": kind in {"external_optional", "hardware_optional"},
                "raw_paths_exposed": False,
            })
        exact_operations = [f"{package}={package_operations[package]}" for package in sorted(package_operations)]
        external_missing_ids = sorted(set(external_missing))
        return {
            "contract_version": CONTRACT_VERSION,
            "component_ids": component_ids,
            "dependency_rows": rows,
            "exact_package_operations": exact_operations,
            "package_manager_network_may_be_used": bool(exact_operations),
            "package_manager_privilege_required": bool(exact_operations),
            "authorization_mechanism": "graphical_polkit_pkexec" if exact_operations else "none",
            "silent_sudo": False,
            "full_setup_runs_as_root": False,
            "external_missing_dependency_ids": external_missing_ids,
            "external_missing_guidance": [
                guidance
                for dependency_id in external_missing_ids
                if (guidance := external_prerequisite_guidance(dependency_id))
                is not None
            ],
            "raw_paths_exposed": False,
        }

    def preview(self, request: SystemPrerequisitePreviewRequest) -> dict[str, Any]:
        public = self.inspect(request.component_ids)
        created = datetime.now(UTC).replace(microsecond=0)
        preview_id = f"prereq_{secrets.token_hex(12)}"
        token = secrets.token_urlsafe(32)
        _private_json(self.preview_root / f"{preview_id}.json", {
            "preview_id": preview_id,
            "approval_token_hash": sha256(token.encode()).hexdigest(),
            "created_at_utc": created.isoformat().replace("+00:00", "Z"),
            "expires_at_utc": (created + timedelta(seconds=PREVIEW_TTL_SECONDS)).isoformat().replace("+00:00", "Z"),
            "public": public,
        })
        return {**public, "preview_id": preview_id, "approval_token": token, "mutation_performed": False}

    def apply(self, request: SystemPrerequisiteApplyRequest) -> dict[str, Any]:
        if not request.operator_approved:
            raise SystemPrerequisiteError("System prerequisite installation requires exact operator approval.")
        path = self.preview_root / f"{request.preview_id}.json"
        preview = _private_read(path)
        if datetime.fromisoformat(str(preview["expires_at_utc"]).replace("Z", "+00:00")) < datetime.now(UTC):
            raise SystemPrerequisiteError("The system-prerequisite preview expired.")
        if not secrets.compare_digest(
            str(preview["approval_token_hash"]), sha256(request.approval_token.encode()).hexdigest()
        ):
            raise SystemPrerequisiteError("The system-prerequisite approval token is invalid.")
        operations = [str(item) for item in preview["public"]["exact_package_operations"]]
        if operations:
            pkexec = shutil.which("pkexec")
            apt_get = shutil.which("apt-get")
            if not pkexec or not apt_get:
                raise SystemPrerequisiteError("Graphical polkit and apt-get are required for the reviewed system-package operation.")
            result = subprocess.run(
                [pkexec, apt_get, "install", "--no-install-recommends", "--yes", *operations],
                capture_output=True, text=True, timeout=1800, check=False,
                env={key: value for key, value in os.environ.items() if key not in {"SUDO_ASKPASS", "LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONPATH"}},
            )
            if result.returncode != 0:
                raise SystemPrerequisiteError("The explicitly authorized system-package operation did not complete successfully.")
            for operation in operations:
                package, expected = operation.split("=", 1)
                if _installed_version(package) != expected:
                    raise SystemPrerequisiteError("A system package differs from the exact reviewed version after installation.")
        receipt = {
            "contract_version": CONTRACT_VERSION,
            "exact_package_operations": operations,
            "verified_after_apply": True,
            "operator_approved": True,
            "applied_at_utc": _utc_now(),
            "raw_paths_exposed": False,
        }
        _private_json(self.receipt_path, receipt)
        path.unlink(missing_ok=True)
        return {**self.inspect(preview["public"]["component_ids"]), "mutation_performed": bool(operations), "receipt_written": True}


__all__ = (
    "CONTRACT_VERSION", "SystemPrerequisiteApplyRequest",
    "SystemPrerequisiteError", "SystemPrerequisitePreviewRequest",
    "SystemPrerequisiteService",
)
