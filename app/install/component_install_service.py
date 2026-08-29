"""Approved, cancellable, transactional installation of optional components."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import signal
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable, Literal
from urllib.request import Request, urlopen
import zipfile
import yaml

from packaging.utils import canonicalize_name
from pydantic import BaseModel, ConfigDict, Field

from .acquisition_service import load_acquisition_manifests
from .codev_installer import CodevInstallError, inspect_codev_vsix
from .component_graph_service import load_component_graph
from .hardware_service import detect_local_hardware
from .install_root_service import install_root_hash, resolve_component_runtime_root
from .model_acquisition_service import (
    CREATOR_MODEL_IDS,
    ModelAcquisitionError,
    acquire_creator_models,
    creator_model_plan,
)
from .paths import ElysiaPaths, resolve_elysia_paths
from .python_artifact_resolver import (
    PythonArtifactResolutionError,
    resolve_hash_locked_wheels,
)
from .python_lock_service import compare_environment_to_lock


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_VERSION = "elysia-component-install-1.0"
PREVIEW_TTL_SECONDS = 1800

_PYTHON_COMPONENTS = {
    "workstation_adapters": ("elysia_workstation", "workstation-py312.lock.txt"),
    # Creator is hardware-selected during preview; this value is only the
    # conservative CPU default used by lifecycle iteration.
    "creator_perception": ("elysia_creator", "creator-cpu-py312.lock.txt"),
}
_CONTAINER_COMPONENTS = {
    "governed_research": ("scripts/manage_searxng.sh", "install", "uninstall"),
    "semantic_retrieval": ("scripts/manage_qdrant.sh", "install", "uninstall"),
}
_PACKAGE_BOUND = {
    "core_python_runtime", "desktop_shell", "identity_memory_fabric",
    "personal_onboarding", "local_connectors",
}

_JOBS: dict[str, tuple[threading.Thread, threading.Event]] = {}
_JOBS_LOCK = threading.Lock()


class ComponentInstallError(RuntimeError):
    """A component operation failed closed."""


class ComponentPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    component_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    operation: Literal["install", "repair", "remove"]
    metadata_network_approved: bool = False
    local_artifact_path: str | None = Field(default=None, max_length=4096)
    selected_model_ids: list[str] = Field(default_factory=list, max_length=3)
    local_model_root: str | None = Field(default=None, max_length=4096)
    model_terms_accepted: bool = False


class ComponentApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    preview_id: str = Field(pattern=r"^component_[a-f0-9]{24}$")
    approval_token: str = Field(min_length=32, max_length=256)
    operator_approved: bool


class ComponentCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    job_id: str = Field(pattern=r"^component_job_[a-f0-9]{24}$")
    operator_approved: bool


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ComponentInstallError("The component preview timestamp is invalid.") from exc
    if parsed.tzinfo is None:
        raise ComponentInstallError("The component preview timestamp has no UTC authority.")
    return parsed.astimezone(UTC)


def _private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
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


def _safe_payload(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
        raise ComponentInstallError("The exact private component record is unavailable or unsafe.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComponentInstallError("The exact private component record is invalid.") from exc
    if not isinstance(payload, dict):
        raise ComponentInstallError("The exact private component record is invalid.")
    return payload


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sanitized_environment() -> dict[str, str]:
    blocked = {
        "PYTHONPATH", "LD_LIBRARY_PATH", "CONDA_PREFIX", "CONDA_DEFAULT_ENV",
        "VIRTUAL_ENV", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL",
    }
    return {key: value for key, value in os.environ.items() if key not in blocked}


def _registry_plan(image: str) -> dict[str, Any]:
    runtime = shutil.which("podman")
    inspector = shutil.which("skopeo")
    if not runtime or not inspector:
        raise ComponentInstallError(
            "Rootless Podman and Skopeo are required to resolve the exact container transfer plan."
        )

    def inspect_raw(reference: str) -> tuple[dict[str, Any], bytes]:
        result = subprocess.run(
            [inspector, "inspect", "--raw", f"docker://{reference}"],
            capture_output=True,
            timeout=90,
            check=False,
            env=_sanitized_environment(),
        )
        if result.returncode != 0:
            raise ComponentInstallError(
                "The approved registry image manifest could not be resolved without pulling it."
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ComponentInstallError(
                "The approved registry returned an invalid image manifest."
            ) from exc
        if not isinstance(payload, dict):
            raise ComponentInstallError(
                "The approved registry returned an invalid image manifest."
            )
        return payload, result.stdout

    payload, raw_manifest = inspect_raw(image)
    requested_digest = image.rpartition("@")[2]
    resolved_digest = "sha256:" + sha256(raw_manifest).hexdigest()
    if not requested_digest.startswith("sha256:") or resolved_digest != requested_digest:
        raise ComponentInstallError(
            "The registry response does not match the exact approved image digest."
        )

    platform_digest = requested_digest
    manifests = payload.get("manifests")
    if isinstance(manifests, list):
        matches = [
            item
            for item in manifests
            if isinstance(item, dict)
            and item.get("platform", {}).get("os") == "linux"
            and item.get("platform", {}).get("architecture") == "amd64"
            and item.get("platform", {}).get("variant") in {None, ""}
        ]
        if len(matches) != 1:
            raise ComponentInstallError(
                "The exact image index does not identify one supported Linux/amd64 manifest."
            )
        platform_digest = str(matches[0].get("digest") or "")
        if not platform_digest.startswith("sha256:"):
            raise ComponentInstallError(
                "The exact Linux/amd64 image descriptor has no valid digest."
            )
        repository, separator, _ = image.rpartition("@")
        if not separator:
            raise ComponentInstallError("The approved container identity is not digest-pinned.")
        payload, raw_manifest = inspect_raw(f"{repository}@{platform_digest}")
        if "sha256:" + sha256(raw_manifest).hexdigest() != platform_digest:
            raise ComponentInstallError(
                "The Linux/amd64 image manifest does not match its exact index descriptor."
            )

    layers = payload.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ComponentInstallError("The exact platform image manifest did not expose layer sizes.")
    config = payload.get("config")
    if not isinstance(config, dict):
        raise ComponentInstallError("The exact platform image manifest has no config descriptor.")
    descriptors = [config, *layers]
    sizes = [int(item.get("size") or 0) for item in descriptors if isinstance(item, dict)]
    digests = [str(item.get("digest") or "") for item in descriptors if isinstance(item, dict)]
    if (
        len(sizes) != len(descriptors)
        or any(size <= 0 for size in sizes)
        or len(digests) != len(descriptors)
        or any(not digest.startswith("sha256:") for digest in digests)
    ):
        raise ComponentInstallError("The exact container layer transfer sizes are incomplete.")
    return {
        "artifact_count": len(descriptors),
        "exact_download_bytes": sum(sizes),
        "image": image,
        "image_index_digest": requested_digest,
        "platform_manifest_digest": platform_digest,
        "platform": {"os": "linux", "architecture": "amd64"},
        "config_digest": digests[0],
        "layer_digests": [str(item.get("digest") or "") for item in layers],
        "metadata_network_used": True,
        "container_bytes_pulled": False,
    }


def _codev_plan(
    path_text: str | None,
    *,
    metadata_network_approved: bool,
    release_identity_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    identity_path = release_identity_path or (
        ROOT / "config" / "release" / "release_identity.json"
    )
    try:
        release = json.loads(identity_path.read_text(encoding="utf-8"))
        codev = release["official_codev"]
        version = str(codev["version"])
        repository_url = str(codev["repository_url"]).rstrip("/")
        expected_sha256 = str(codev["vsix_sha256"])
        expected_size = int(codev["vsix_size_bytes"])
        canonical_url = str(codev["vsix_url"])
        expected_url = (
            f"{repository_url}/releases/download/v{version}/"
            f"elysia-codev-{version}.vsix"
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ComponentInstallError(
            "The exact first-party Codev release identity is unavailable."
        ) from exc
    if (
        release.get("version") != "1.0.0"
        or version != "1.0.0"
        or repository_url != "https://github.com/Bradley-T-Harz/elysia-codev"
        or len(expected_sha256) != 64
        or expected_size <= 0
        or canonical_url != expected_url
    ):
        raise ComponentInstallError(
            "The exact first-party Codev release identity is invalid."
        )
    if not path_text:
        if not metadata_network_approved:
            raise ComponentInstallError(
                "The exact Codev v1.0.0 release download requires explicit network approval."
            )
        return {
            "artifact_count": 1,
            "exact_download_bytes": expected_size,
            "exact_installed_input_bytes": expected_size,
            "artifact_sha256": expected_sha256,
            "package_identity": "ecosyneva-commons.elysia-codev@1.0.0",
            "third_party_notices_required": True,
            "network_used": True,
            "canonical_release_url": canonical_url,
            "automatic_acquisition": True,
        }, {
            "remote_artifact": {
                "url": canonical_url,
                "filename": "elysia-codev-1.0.0.vsix",
                "sha256": expected_sha256,
                "size_bytes": expected_size,
            },
            "artifact_sha256": expected_sha256,
            "artifact_size_bytes": expected_size,
        }
    path = Path(path_text).expanduser().resolve(strict=True)
    if not path.is_file() or path.is_symlink() or path.suffix.lower() != ".vsix":
        raise ComponentInstallError("The selected Codev artifact is not a safe local VSIX.")
    try:
        inspection = inspect_codev_vsix(path)
        with zipfile.ZipFile(path) as archive:
            notices = archive.getinfo("extension/THIRD_PARTY_NOTICES.txt")
    except (CodevInstallError, KeyError, zipfile.BadZipFile, OSError) as exc:
        raise ComponentInstallError("The selected Codev VSIX is missing its package identity or notices.") from exc
    if inspection.sha256 != expected_sha256 or path.stat().st_size != expected_size:
        raise ComponentInstallError(
            "The selected local Codev VSIX is not the exact qualified v1.0.0 release payload."
        )
    public = {
        "artifact_count": 1,
        "exact_download_bytes": 0,
        "exact_installed_input_bytes": path.stat().st_size,
        "artifact_sha256": inspection.sha256,
        "package_identity": "ecosyneva-commons.elysia-codev@1.0.0",
        "third_party_notices_present": notices.file_size > 0,
        "network_used": False,
        "canonical_release_url": canonical_url,
        "automatic_acquisition": False,
    }
    return public, {
        "local_artifact_path": str(path),
        "artifact_sha256": inspection.sha256,
        "artifact_size_bytes": path.stat().st_size,
    }


def _model_acquisition(model_id: str) -> dict[str, Any]:
    path = ROOT / "config" / "install" / "model_acquisitions.yaml"
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        record = payload["models"][model_id]
    except Exception as exc:
        raise ComponentInstallError("The exact model acquisition manifest is unavailable.") from exc
    if (
        payload.get("version") != 1
        or payload.get("contract_version") != "elysia-model-acquisitions-1.0"
        or not isinstance(record, dict)
        or int(record.get("exact_download_bytes") or 0) <= 0
        or sum(int(item.get("size_bytes") or 0) for item in record.get("layers", []))
        != int(record["exact_download_bytes"])
    ):
        raise ComponentInstallError("The exact model acquisition manifest is invalid.")
    return record


class ComponentInstallService:
    def __init__(
        self,
        paths: ElysiaPaths | None = None,
        *,
        wheel_resolver: Callable[[Path], dict[str, Any]] | None = None,
        registry_resolver: Callable[[str], dict[str, Any]] | None = None,
        command_runner: Callable[[list[str], threading.Event, Path], str | None] | None = None,
        release_identity_path: Path | None = None,
    ) -> None:
        self.paths = paths or resolve_elysia_paths()
        self.root = self.paths.state_dir / "install" / "component-jobs"
        self.preview_root = self.root / "previews"
        self.job_root = self.root / "jobs"
        self.receipt_root = self.paths.state_dir / "install" / "components"
        self.component_root = resolve_component_runtime_root(self.paths)
        self.recovery_root = self.paths.state_dir / "recoverable-components"
        self.wheel_resolver = wheel_resolver or resolve_hash_locked_wheels
        self.registry_resolver = registry_resolver or _registry_plan
        self.command_runner = command_runner
        self.release_identity_path = release_identity_path

    def _receipt(self, component_id: str) -> dict[str, Any] | None:
        try:
            return _safe_payload(self.receipt_root / f"{component_id}.json")
        except ComponentInstallError:
            return None

    def state(self) -> dict[str, Any]:
        graph = load_component_graph()
        components = []
        for component_id in graph["components"]:
            receipt = self._receipt(component_id)
            root_matches = bool(
                receipt
                and receipt.get("component_root_sha256") in {
                    None,
                    install_root_hash(self.component_root),
                }
            )
            status = str(receipt.get("status")) if receipt else (
                "package_bound" if component_id in _PACKAGE_BOUND else "not_installed"
            )
            if receipt and not root_matches and status not in {"removed", "not_installed"}:
                status = "blocked_root_mismatch"
            components.append({
                "component_id": component_id,
                "status": status,
                "managed_by_elysia": bool(receipt and receipt.get("managed_by_elysia") is True),
                "raw_paths_exposed": False,
            })
        return {
            "contract_version": CONTRACT_VERSION,
            "components": components,
            "running_job_count": sum(
                1 for thread, _ in _JOBS.values() if thread.is_alive()
            ),
            "profile_selection_grants_acquisition_approval": False,
            "raw_paths_exposed": False,
        }

    def _root_receipt_fields(self) -> dict[str, Any]:
        return {
            "component_root_sha256": install_root_hash(self.component_root),
            "component_root_source": "private_setup_receipt",
        }

    def preview(self, request: ComponentPreviewRequest) -> dict[str, Any]:
        graph = load_component_graph()
        acquisitions = load_acquisition_manifests()["components"]
        if request.component_id not in graph["components"]:
            raise ComponentInstallError("The component is not present in the authoritative graph.")
        if request.component_id != "creator_perception" and (
            request.selected_model_ids or request.local_model_root or request.model_terms_accepted
        ):
            raise ComponentInstallError("Creator model selections apply only to the Creator / Perception component.")
        if request.component_id in _PACKAGE_BOUND:
            raise ComponentInstallError("Package-bound Core components are changed only through signed application lifecycle operations.")
        receipt = self._receipt(request.component_id)
        if request.operation == "remove" and not receipt:
            raise ComponentInstallError("The component has no Elysia ownership receipt and cannot be removed by Setup.")
        manifest = acquisitions[request.component_id]
        public: dict[str, Any] = {
            "contract_version": CONTRACT_VERSION,
            "component_id": request.component_id,
            "operation": request.operation,
            "source": manifest["source"],
            "publisher": manifest["publisher"],
            "identity": manifest["identity"],
            "digest": manifest["digest"],
            "license": manifest["license"],
            "redistribution": manifest["redistribution"],
            "network": manifest["network"],
            "privilege": manifest["privilege"],
            "removal": manifest["removal"],
            "estimated_installed_bytes": int(manifest["estimated_installed_bytes"]),
            "private_data_egress": False,
            "silent_privilege": False,
            "raw_paths_exposed": False,
        }
        private: dict[str, Any] = {}
        if request.operation == "remove":
            public.update({
                "exact_download_bytes": 0,
                "network_used": False,
                "recoverable_removal": True,
                "user_content_removed": False,
            })
        elif request.component_id in _PYTHON_COMPONENTS or request.component_id == "scientific_engineering":
            if not request.metadata_network_approved:
                raise ComponentInstallError("Exact public wheel metadata resolution requires explicit network approval.")
            if request.component_id in {"creator_perception", "scientific_engineering"}:
                hardware = detect_local_hardware()
                if not hardware["cpu_only_supported"]:
                    missing = ", ".join(hardware["missing_cpu_features"]) or "the approved CPU baseline"
                    raise ComponentInstallError(
                        f"The {request.component_id.replace('_', ' ').title()} runtime is incompatible with this CPU; "
                        f"missing required instruction features: {missing}."
                    )
                variant = "cuda" if hardware["gpu"]["cuda_variant_supported"] else "cpu"
                if request.component_id == "scientific_engineering":
                    environment_id = "elysia_neurofabric"
                    lock_name = f"neurofabric-{variant}-py312.lock.txt"
                else:
                    environment_id = "elysia_creator"
                    lock_name = f"creator-{variant}-py312.lock.txt"
                public["hardware_variant"] = variant
                public["hardware"] = hardware
            else:
                environment_id, lock_name = _PYTHON_COMPONENTS[request.component_id]
            lock_path = ROOT / "config" / "install" / "locks" / lock_name
            try:
                wheel_plan = self.wheel_resolver(lock_path)
            except PythonArtifactResolutionError as exc:
                raise ComponentInstallError(
                    f"The exact {request.component_id.replace('_', ' ')} acquisition plan is invalid: {exc}"
                ) from exc
            public.update({
                key: value for key, value in wheel_plan.items()
                if key != "artifacts"
            })
            public["artifact_identities"] = [
                {
                    "package": item["package"], "version": item["version"],
                    "filename": item["filename"], "sha256": item["sha256"],
                    "size_bytes": item["size_bytes"],
                    "artifact_type": item["artifact_type"],
                }
                for item in wheel_plan["artifacts"]
            ]
            public["build_tool_identities"] = [
                {
                    "package": item["package"], "version": item["version"],
                    "filename": item["filename"], "sha256": item["sha256"],
                    "size_bytes": item["size_bytes"],
                }
                for item in wheel_plan["build_tools"]
            ]
            private.update({
                "environment_id": environment_id,
                "lock_name": lock_name,
                "wheel_plan": wheel_plan,
            })
            if request.component_id == "creator_perception":
                if request.selected_model_ids and not request.model_terms_accepted:
                    raise ComponentInstallError(
                        "Creator model acquisition requires explicit review and acceptance of each displayed license and use boundary."
                    )
                try:
                    model_public, model_private = creator_model_plan(
                        request.selected_model_ids, request.local_model_root,
                    )
                except ModelAcquisitionError as exc:
                    raise ComponentInstallError(str(exc)) from exc
                public["python_exact_download_bytes"] = int(public["exact_download_bytes"])
                public["python_artifact_count"] = int(public["artifact_count"])
                public["model_plan"] = model_public
                public["model_selection_complete"] = set(request.selected_model_ids) == set(CREATOR_MODEL_IDS)
                public["model_gates_after_install"] = sorted(
                    set(CREATOR_MODEL_IDS) - set(request.selected_model_ids)
                )
                public["exact_download_bytes"] = (
                    int(public["exact_download_bytes"])
                    + int(model_public["model_exact_download_bytes"])
                )
                public["artifact_count"] = (
                    int(public["artifact_count"])
                    + int(model_public["model_artifact_count"])
                )
                public["estimated_installed_bytes"] = (
                    max(int(public["python_exact_download_bytes"]) * 3, 1_500_000_000)
                    + int(model_public["model_exact_download_bytes"])
                )
                private["creator_model_plan"] = model_private
        elif request.component_id in _CONTAINER_COMPONENTS:
            if not request.metadata_network_approved:
                raise ComponentInstallError("Exact registry manifest resolution requires explicit network approval.")
            image = str(manifest["identity"]).split(" plus ", 1)[0]
            container_plan = self.registry_resolver(image)
            public.update(container_plan)
            private["manager"] = _CONTAINER_COMPONENTS[request.component_id]
            if request.component_id == "semantic_retrieval":
                model = _model_acquisition("qwen3_embedding_0_6b")
                public["container_download_bytes"] = int(container_plan["exact_download_bytes"])
                public["model_download_bytes"] = int(model["exact_download_bytes"])
                public["exact_download_bytes"] = (
                    int(container_plan["exact_download_bytes"])
                    + int(model["exact_download_bytes"])
                )
                public["artifact_count"] = int(container_plan["artifact_count"]) + len(model["layers"])
                public["model_identity"] = {
                    "model": model["model"],
                    "publisher": model["publisher"],
                    "manifest_digest": model["registry_manifest_digest"],
                    "layers": model["layers"],
                    "license": model["license"],
                    "redistribution": model["redistribution"],
                }
                private["model_acquisition"] = model
        elif request.component_id == "codev_companion":
            codev_public, codev_private = _codev_plan(
                request.local_artifact_path,
                metadata_network_approved=request.metadata_network_approved,
                release_identity_path=self.release_identity_path,
            )
            if self.release_identity_path is None and (
                str(manifest["source"]) != codev_public["canonical_release_url"]
                or str(manifest["digest"])
                != f"sha256:{codev_public['artifact_sha256']}"
                or int(manifest["estimated_download_bytes"])
                != int(codev_public["exact_installed_input_bytes"])
            ):
                raise ComponentInstallError(
                    "The Codev acquisition and release-identity manifests disagree."
                )
            public.update(codev_public)
            private.update(codev_private)
        elif request.component_id == "local_model_provider":
            executable = shutil.which("ollama")
            if not executable:
                raise ComponentInstallError("No approved local Ollama provider is installed; provider installation is a separate operator action.")
            public.update({
                "exact_download_bytes": 0,
                "network_used": False,
                "provider_adoption_only": True,
            })
            private["provider_executable"] = executable
        else:
            raise ComponentInstallError("The selected component has no bounded installation adapter.")
        if request.operation != "remove":
            disk_root = self.component_root
            while not disk_root.exists() and disk_root != disk_root.parent:
                disk_root = disk_root.parent
            available = shutil.disk_usage(disk_root).free
            lifecycle_reserve = 2 * 1024**3
            required_capacity = (
                int(public.get("exact_download_bytes") or 0)
                + int(public.get("estimated_installed_bytes") or 0)
                + lifecycle_reserve
            )
            public["disk_preview"] = {
                "available_bytes": available,
                "required_capacity_bytes": required_capacity,
                "lifecycle_reserve_bytes": lifecycle_reserve,
                "sufficient": available >= required_capacity,
                "raw_path_exposed": False,
            }
            if available < required_capacity:
                raise ComponentInstallError(
                    "The exact component operation exceeds available storage after preserving the lifecycle reserve."
                )
        created = datetime.now(UTC).replace(microsecond=0)
        preview_id = f"component_{secrets.token_hex(12)}"
        token = secrets.token_urlsafe(32)
        _private_json(self.preview_root / f"{preview_id}.json", {
            "preview_id": preview_id,
            "approval_token_hash": sha256(token.encode()).hexdigest(),
            "created_at_utc": created.isoformat().replace("+00:00", "Z"),
            "expires_at_utc": (created + timedelta(seconds=PREVIEW_TTL_SECONDS)).isoformat().replace("+00:00", "Z"),
            "public": public,
            "private": private,
        })
        return {**public, "preview_id": preview_id, "approval_token": token, "mutation_performed": False}

    def _load_preview(self, request: ComponentApplyRequest) -> tuple[Path, dict[str, Any]]:
        if not request.operator_approved:
            raise ComponentInstallError("Component apply requires exact operator approval.")
        path = self.preview_root / f"{request.preview_id}.json"
        payload = _safe_payload(path)
        if _parse_utc(str(payload["expires_at_utc"])) < datetime.now(UTC):
            raise ComponentInstallError("The component preview expired.")
        if not secrets.compare_digest(
            str(payload["approval_token_hash"]), sha256(request.approval_token.encode()).hexdigest()
        ):
            raise ComponentInstallError("The component approval token is invalid.")
        return path, payload

    def apply(self, request: ComponentApplyRequest) -> dict[str, Any]:
        preview_path, preview = self._load_preview(request)
        component_id = str(preview["public"]["component_id"])
        with _JOBS_LOCK:
            if any(thread.is_alive() for thread, _ in _JOBS.values()):
                raise ComponentInstallError("Another component operation is already active.")
            job_id = f"component_job_{secrets.token_hex(12)}"
            cancel = threading.Event()
            _private_json(self.job_root / f"{job_id}.json", {
                "contract_version": CONTRACT_VERSION,
                "job_id": job_id,
                "component_id": component_id,
                "operation": preview["public"]["operation"],
                "status": "queued",
                "cancel_requested": False,
                "created_at_utc": _utc_now(),
                "updated_at_utc": _utc_now(),
                "raw_paths_exposed": False,
            })
            thread = threading.Thread(
                target=self._execute_job,
                args=(job_id, preview, cancel),
                name=f"elysia-{component_id}", daemon=True,
            )
            _JOBS[job_id] = (thread, cancel)
            thread.start()
        preview_path.unlink(missing_ok=True)
        return {
            "job_id": job_id,
            "component_id": component_id,
            "status": "queued",
            "cancellable": True,
            "mutation_performed": True,
            "raw_paths_exposed": False,
        }

    def _job_update(self, job_id: str, **updates: Any) -> None:
        path = self.job_root / f"{job_id}.json"
        payload = _safe_payload(path)
        payload.update(updates)
        payload["updated_at_utc"] = _utc_now()
        _private_json(path, payload)

    def job(self, job_id: str) -> dict[str, Any]:
        if not job_id.startswith("component_job_"):
            raise ComponentInstallError("The component job identity is invalid.")
        payload = _safe_payload(self.job_root / f"{job_id}.json")
        with _JOBS_LOCK:
            running = _JOBS.get(job_id)
        if payload.get("status") in {"queued", "running"} and not (running and running[0].is_alive()):
            payload["status"] = "interrupted"
            payload["recoverable"] = True
            payload["updated_at_utc"] = _utc_now()
            _private_json(self.job_root / f"{job_id}.json", payload)
        return {key: value for key, value in payload.items() if key not in {"error_private"}}

    def cancel(self, request: ComponentCancelRequest) -> dict[str, Any]:
        if not request.operator_approved:
            raise ComponentInstallError("Component cancellation requires exact operator approval.")
        with _JOBS_LOCK:
            active = _JOBS.get(request.job_id)
        if not active or not active[0].is_alive():
            state = self.job(request.job_id)
            return {**state, "cancellation_accepted": False}
        active[1].set()
        self._job_update(request.job_id, cancel_requested=True)
        return {**self.job(request.job_id), "cancellation_accepted": True}

    def _run_command(
        self,
        command: list[str],
        cancel: threading.Event,
        working: Path,
        *,
        environment_overrides: dict[str, str] | None = None,
        child_umask: int = -1,
    ) -> str:
        if self.command_runner is not None:
            return self.command_runner(command, cancel, working) or ""
        environment = _sanitized_environment()
        environment.update(environment_overrides or {})
        # Do not leave child output attached to unread PIPEs. Acquisition tools
        # such as Ollama emit enough progress data to fill a pipe before exit;
        # waiting for process completion before communicate() then deadlocks a
        # successfully completed transfer. Anonymous private temporary files
        # continuously drain both streams without exposing them in receipts.
        with tempfile.TemporaryFile(mode="w+b") as stdout_file, tempfile.TemporaryFile(mode="w+b") as stderr_file:
            process = subprocess.Popen(
                command, cwd=working, stdout=stdout_file, stderr=stderr_file,
                env=environment, start_new_session=True,
                umask=child_umask,
            )
            while process.poll() is None:
                if cancel.is_set():
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                    raise ComponentInstallError("The component operation was cancelled and its private staging is being cleaned.")
                time.sleep(0.1)

            def bounded_output(handle: Any) -> str:
                handle.flush()
                size = os.fstat(handle.fileno()).st_size
                handle.seek(max(0, size - 2 * 1024 * 1024))
                return handle.read().decode("utf-8", errors="replace")

            stdout = bounded_output(stdout_file)
            stderr = bounded_output(stderr_file)
        if process.returncode:
            safe = " ".join((stderr or stdout).strip().split())[:500]
            raise ComponentInstallError(f"The bounded component command failed: {safe or 'no safe diagnostic'}")
        return stdout

    def _download(self, artifact: dict[str, Any], destination: Path, cancel: threading.Event) -> None:
        request = Request(str(artifact["url"]), headers={"User-Agent": "Elysia-Setup/1.0"})
        digest = sha256()
        size = 0
        with urlopen(request, timeout=60) as response, destination.open("wb") as handle:
            while True:
                if cancel.is_set():
                    raise ComponentInstallError("The component download was cancelled.")
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if size != int(artifact["size_bytes"]) or digest.hexdigest() != artifact["sha256"]:
            raise ComponentInstallError("A downloaded artifact differs from the exact approved size or SHA-256.")

    def _python_install(self, component_id: str, private: dict[str, Any], cancel: threading.Event, job_id: str) -> None:
        environment_id = str(private["environment_id"])
        lock_name = str(private["lock_name"])
        target = self.component_root / environment_id
        if target.parent != self.component_root or target == self.component_root:
            raise ComponentInstallError("The component environment target is unsafe.")
        working = self.root / "staging" / job_id
        wheelhouse = working / "wheelhouse"
        sourcehouse = working / "sourcehouse"
        buildtoolhouse = working / "buildtoolhouse"
        environment = working / "environment"
        wheelhouse.mkdir(mode=0o700, parents=True, exist_ok=False)
        sourcehouse.mkdir(mode=0o700)
        buildtoolhouse.mkdir(mode=0o700)
        self._job_update(job_id, phase="download")
        downloaded: dict[str, Path] = {}
        for artifact in private["wheel_plan"]["artifacts"]:
            destination_root = sourcehouse if artifact["artifact_type"] == "sdist" else wheelhouse
            destination = destination_root / str(artifact["filename"])
            self._download(artifact, destination, cancel)
            downloaded[str(artifact["sha256"])] = destination
        for tool in private["wheel_plan"]["build_tools"]:
            digest = str(tool["sha256"])
            if digest in downloaded:
                continue
            destination = buildtoolhouse / str(tool["filename"])
            self._download(tool, destination, cancel)
            downloaded[digest] = destination
        source_build_receipts: list[dict[str, Any]] = []
        source_artifacts = [
            item for item in private["wheel_plan"]["artifacts"]
            if item["artifact_type"] == "sdist"
        ]
        if source_artifacts:
            self._job_update(job_id, phase="source_build_toolchain")
            builder = working / "builder"
            python = shutil.which("python3.12")
            if not python:
                raise ComponentInstallError("A supported Python 3.12 interpreter is unavailable.")
            self._run_command([python, "-m", "venv", str(builder)], cancel, working)
            tool_lock = working / "build-tools.lock"
            tool_lock.write_text("".join(
                f"{item['package']}=={item['version']} --hash=sha256:{item['sha256']}\n"
                for item in private["wheel_plan"]["build_tools"]
            ), encoding="utf-8")
            self._run_command([
                str(builder / "bin" / "python"), "-m", "pip", "install",
                "--disable-pip-version-check", "--no-index",
                "--find-links", str(wheelhouse), "--find-links", str(buildtoolhouse),
                "--require-hashes", "--requirement", str(tool_lock),
            ], cancel, working)
            for source in source_artifacts:
                policy = source["build_policy"]
                expected = policy["output"]
                build = policy["build"]
                self._job_update(job_id, phase=f"source_build:{source['package']}")
                self._run_command([
                    str(builder / "bin" / "python"), "-m", "pip", "wheel",
                    "--disable-pip-version-check", "--no-index", "--no-deps",
                    "--no-build-isolation", "--wheel-dir", str(wheelhouse),
                    str(sourcehouse / str(source["filename"])),
                ], cancel, working, environment_overrides={
                    "SOURCE_DATE_EPOCH": str(build["source_date_epoch"]),
                    "PYTHONHASHSEED": str(build["python_hash_seed"]),
                    "TZ": str(build["timezone"]),
                    "LC_ALL": str(build["locale"]),
                    "LANG": str(build["locale"]),
                }, child_umask=int(str(build["umask"]), 8))
                output = wheelhouse / str(expected["filename"])
                if not output.is_file() or _file_sha256(output) != str(expected["sha256"]):
                    raise ComponentInstallError(
                        f"The deterministic source build for {source['package']} did not match its approved wheel identity."
                    )
                source_build_receipts.append({
                    "package": source["package"],
                    "version": source["version"],
                    "source_filename": source["filename"],
                    "source_sha256": source["sha256"],
                    "output_filename": expected["filename"],
                    "output_sha256": expected["sha256"],
                    "build_backend": build["backend"],
                    "build_umask": str(build["umask"]),
                    "build_tools": [
                        {key: item[key] for key in ("package", "version", "sha256")}
                        for item in private["wheel_plan"]["build_tools"]
                    ],
                    "network_during_build": False,
                })
        self._job_update(job_id, phase="environment_creation")
        python = shutil.which("python3.12")
        if not python:
            raise ComponentInstallError("A supported Python 3.12 interpreter is unavailable.")
        self._run_command([python, "-m", "venv", str(environment)], cancel, working)
        self._job_update(job_id, phase="component_installation")
        lock_path = ROOT / "config" / "install" / "locks" / lock_name
        self._run_command([
            str(environment / "bin" / "python"), "-m", "pip", "install",
            "--disable-pip-version-check", "--no-index", "--find-links", str(wheelhouse),
            "--require-hashes", "--requirement", str(lock_path),
        ], cancel, working)
        probe = subprocess.run(
            [str(environment / "bin" / "python"), "-c", "import importlib.metadata,json;print(json.dumps({d.metadata['Name']:d.version for d in importlib.metadata.distributions() if d.metadata.get('Name')}))"],
            capture_output=True, text=True, timeout=60, check=False,
            env=_sanitized_environment(),
        )
        try:
            installed = json.loads(probe.stdout.strip().splitlines()[-1])
        except Exception as exc:
            raise ComponentInstallError("The installed component package inventory could not be verified.") from exc
        comparison = compare_environment_to_lock(
            lock_path,
            installed={canonicalize_name(str(key)): str(value) for key, value in installed.items()},
        )
        if not comparison["matches"]:
            raise ComponentInstallError("The installed component environment differs from its exact release lock.")
        model_receipt: dict[str, Any] | None = None
        component_status = "ready"
        if component_id == "creator_perception":
            model_plan = private.get("creator_model_plan")
            if not isinstance(model_plan, dict):
                raise ComponentInstallError("The Creator model plan is missing from the exact approved operation.")
            selected_model_ids = [str(item) for item in model_plan.get("selected_model_ids", [])]
            if selected_model_ids:
                self._job_update(job_id, phase="creator_model_acquisition")
                try:
                    model_receipt = acquire_creator_models(
                        self.paths,
                        selected_model_ids,
                        str(model_plan["local_model_root"]) if model_plan.get("local_model_root") else None,
                        working,
                        cancel,
                        lambda artifact: self._job_update(
                            job_id, phase="creator_model_acquisition", current_artifact=artifact,
                        ),
                    )
                except ModelAcquisitionError as exc:
                    raise ComponentInstallError(str(exc)) from exc
            missing_models = sorted(set(CREATOR_MODEL_IDS) - set(selected_model_ids))
            if missing_models:
                component_status = "ready_with_model_gates"
                model_receipt = model_receipt or {
                    "contract_version": "elysia-model-acquisitions-1.0",
                    "status": "not_selected",
                    "selected_model_ids": [],
                    "authenticated_state_persisted": False,
                    "redistributed_by_elysia": False,
                    "raw_paths_exposed": False,
                }
                model_receipt["gated_model_ids"] = missing_models
        self.component_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.exists():
            recovery = self.recovery_root / f"{environment_id}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
            recovery.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            target.replace(recovery)
        environment.replace(target)
        _private_json(self.receipt_root / f"{component_id}.json", {
            "contract_version": CONTRACT_VERSION,
            "component_id": component_id,
            "environment_id": environment_id,
            "status": component_status,
            "managed_by_elysia": True,
            "lock_name": lock_name,
            "lock_sha256": _file_sha256(lock_path),
            "artifact_count": int(private["wheel_plan"]["artifact_count"]),
            "exact_download_bytes": int(private["wheel_plan"]["exact_download_bytes"]),
            "source_builds": source_build_receipts,
            "model_receipt": model_receipt,
            "user_data_present": False,
            "installed_at_utc": _utc_now(),
            "raw_paths_exposed": False,
            **self._root_receipt_fields(),
        })
        shutil.rmtree(working)

    def _remove(self, component_id: str) -> None:
        receipt = _safe_payload(self.receipt_root / f"{component_id}.json")
        if receipt.get("managed_by_elysia") is not True or receipt.get("user_data_present") is not False:
            raise ComponentInstallError("The component ownership receipt does not authorize removal.")
        if receipt.get("component_root_sha256") not in {
            None,
            install_root_hash(self.component_root),
        }:
            raise ComponentInstallError(
                "The component receipt belongs to a different private Setup root; removal stopped."
            )
        environment_id = receipt.get("environment_id")
        if environment_id:
            target = self.component_root / str(environment_id)
            if target.parent != self.component_root:
                raise ComponentInstallError("The component removal target is unsafe.")
            if target.exists():
                recovery = self.recovery_root / f"{environment_id}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
                recovery.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                target.replace(recovery)
        receipt.update({"status": "removed", "removed_at_utc": _utc_now(), "recoverable": True})
        _private_json(self.receipt_root / f"{component_id}.json", receipt)

    def uninstall_managed_optional_components(self) -> dict[str, Any]:
        """Remove only Elysia-owned optional runtimes during app uninstall.

        External providers, model vaults, user artifacts, Codev/editor state, and
        all account data remain outside this bounded removal authority.
        """
        removed: list[str] = []
        for component_id in (*_PYTHON_COMPONENTS, "scientific_engineering"):
            receipt = self._receipt(component_id)
            if receipt and receipt.get("status") not in {"removed", "not_installed"}:
                self._remove(component_id)
                removed.append(component_id)
        bash = shutil.which("bash")
        for component_id, (script_name, _, uninstall_action) in _CONTAINER_COMPONENTS.items():
            receipt = self._receipt(component_id)
            if not receipt or receipt.get("status") in {"removed", "not_installed"}:
                continue
            script = ROOT / script_name
            if not bash or not script.is_file() or script.is_symlink():
                raise ComponentInstallError(
                    "An Elysia-owned optional service cannot be removed without its bounded lifecycle manager."
                )
            result = subprocess.run(
                [bash, str(script), uninstall_action], capture_output=True, text=True,
                timeout=180, check=False, env=_sanitized_environment(),
            )
            if result.returncode:
                raise ComponentInstallError(
                    "An Elysia-owned optional service could not be removed; application uninstall stopped to avoid an orphan."
                )
            receipt.update({"status": "removed", "removed_at_utc": _utc_now(), "recoverable": True})
            _private_json(self.receipt_root / f"{component_id}.json", receipt)
            removed.append(component_id)
        return {
            "removed_component_ids": removed,
            "external_provider_removed": False,
            "model_vault_removed": False,
            "user_data_removed": False,
            "raw_paths_exposed": False,
        }

    def _container_install(self, component_id: str, private: dict[str, Any], cancel: threading.Event, job_id: str) -> None:
        relative_script, install_action, _ = private["manager"]
        script = ROOT / relative_script
        bash = shutil.which("bash")
        if not bash or not script.is_file() or script.is_symlink():
            raise ComponentInstallError("The bounded component lifecycle manager is unavailable.")
        operation_started = False
        model_receipt: dict[str, Any] | None = None
        try:
            self._job_update(job_id, phase="component_installation")
            operation_started = True
            self._run_command([bash, str(script), str(install_action)], cancel, ROOT)
            if component_id == "semantic_retrieval":
                model = private.get("model_acquisition")
                ollama = shutil.which("ollama")
                if not isinstance(model, dict) or not ollama:
                    raise ComponentInstallError("Semantic retrieval requires the approved local Ollama model acquisition adapter.")
                self._job_update(job_id, phase="model_acquisition")
                self._run_command([ollama, "pull", str(model["model"])], cancel, ROOT)
                proof = subprocess.run(
                    [ollama, "show", str(model["model"]), "--modelfile"],
                    capture_output=True, text=True, timeout=60, check=False,
                    env=_sanitized_environment(),
                )
                expected_layers = {str(item["sha256"]) for item in model["layers"]}
                if proof.returncode or not all(digest in proof.stdout for digest in expected_layers):
                    raise ComponentInstallError("The acquired embedding model does not expose every exact approved layer identity.")
                model_receipt = {
                    "model": model["model"],
                    "registry_manifest_digest": model["registry_manifest_digest"],
                    "layer_sha256": sorted(expected_layers),
                    "exact_download_bytes": int(model["exact_download_bytes"]),
                    "license": model["license"],
                    "redistributed_by_elysia": False,
                }
        except Exception:
            if operation_started:
                cleanup = subprocess.run(
                    [bash, str(script), str(private["manager"][2])],
                    capture_output=True, text=True, timeout=120, check=False,
                    env=_sanitized_environment(),
                )
                if cleanup.returncode != 0:
                    raise ComponentInstallError(
                        "The component operation failed and its Elysia-owned service cleanup also failed; manual bounded recovery is required."
                    )
            raise
        _private_json(self.receipt_root / f"{component_id}.json", {
            "contract_version": CONTRACT_VERSION,
            "component_id": component_id,
            "status": "ready",
            "managed_by_elysia": True,
            "user_data_present": False,
            "installed_at_utc": _utc_now(),
            "model_receipt": model_receipt,
            "raw_paths_exposed": False,
            **self._root_receipt_fields(),
        })

    def _codev_install(self, component_id: str, private: dict[str, Any], cancel: threading.Event, job_id: str) -> None:
        editor = shutil.which("code") or shutil.which("codium")
        if not editor:
            raise ComponentInstallError("A supported VS Code-family host is unavailable.")
        staging: Path | None = None
        remote_artifact = private.get("remote_artifact")
        try:
            if isinstance(remote_artifact, dict):
                staging = self.root / "staging" / job_id
                staging.mkdir(mode=0o700, parents=True, exist_ok=False)
                artifact = staging / "elysia-codev-1.0.0.vsix"
                self._job_update(job_id, phase="download")
                self._download(remote_artifact, artifact, cancel)
            else:
                artifact = Path(str(private["local_artifact_path"]))
            try:
                inspection = inspect_codev_vsix(artifact)
            except CodevInstallError as exc:
                raise ComponentInstallError(
                    "The approved Codev VSIX changed or became invalid before installation."
                ) from exc
            if (
                inspection.sha256 != str(private.get("artifact_sha256") or "")
                or artifact.stat().st_size != int(private.get("artifact_size_bytes") or -1)
            ):
                raise ComponentInstallError(
                    "The approved Codev VSIX changed after preview; installation stopped."
                )
            self._job_update(job_id, phase="component_installation")
            self._run_command([editor, "--install-extension", str(artifact), "--force"], cancel, ROOT)
            installed = self._run_command(
                [editor, "--list-extensions", "--show-versions"], cancel, ROOT,
            )
            if "ecosyneva-commons.elysia-codev@1.0.0" not in {
                line.strip().lower() for line in installed.splitlines()
            }:
                raise ComponentInstallError(
                    "VS Code did not report the exact Codev extension after installation."
                )
            receipt = self.paths.data_dir / "developer" / "codev-install.json"
            _private_json(receipt, {
                "schema_version": 1,
                "extension_id": "ecosyneva-commons.elysia-codev",
                "version": "1.0.0",
                "contract_version": "vscode-coding-agent-contract-0.1",
                "install_state": "installed_by_user",
                "package_sha256": inspection.sha256,
                "raw_paths_exposed": False,
            })
            _private_json(self.receipt_root / f"{component_id}.json", {
                "contract_version": CONTRACT_VERSION,
                "component_id": component_id,
                "status": "ready",
                "managed_by_elysia": True,
                "user_data_present": False,
                "package_sha256": inspection.sha256,
                "installed_at_utc": _utc_now(),
                "raw_paths_exposed": False,
                **self._root_receipt_fields(),
            })
        finally:
            if staging is not None and staging.is_dir():
                shutil.rmtree(staging)

    def _codev_remove(self, component_id: str, cancel: threading.Event, job_id: str) -> None:
        receipt = _safe_payload(self.receipt_root / f"{component_id}.json")
        if receipt.get("managed_by_elysia") is not True or receipt.get("user_data_present") is not False:
            raise ComponentInstallError("The component ownership receipt does not authorize removal.")
        if receipt.get("component_root_sha256") not in {None, install_root_hash(self.component_root)}:
            raise ComponentInstallError(
                "The Codev receipt belongs to a different private Setup root; removal stopped."
            )
        editor = shutil.which("code") or shutil.which("codium")
        if not editor:
            raise ComponentInstallError("A supported VS Code-family host is unavailable.")
        self._job_update(job_id, phase="component_removal")
        self._run_command(
            [editor, "--uninstall-extension", "ecosyneva-commons.elysia-codev"],
            cancel,
            ROOT,
        )
        installed = self._run_command(
            [editor, "--list-extensions", "--show-versions"], cancel, ROOT,
        )
        if any(
            line.strip().lower().startswith("ecosyneva-commons.elysia-codev@")
            for line in installed.splitlines()
        ):
            raise ComponentInstallError("VS Code still reports Codev after removal.")
        codev_receipt = self.paths.data_dir / "developer" / "codev-install.json"
        codev_payload = _safe_payload(codev_receipt)
        if codev_payload:
            codev_payload.update({
                "install_state": "removed_by_user",
                "removed_at_utc": _utc_now(),
                "raw_paths_exposed": False,
            })
            _private_json(codev_receipt, codev_payload)
        receipt.update({
            "status": "removed",
            "removed_at_utc": _utc_now(),
            "recoverable": False,
            "workspace_and_repository_data_preserved": True,
        })
        _private_json(self.receipt_root / f"{component_id}.json", receipt)

    def _execute_job(self, job_id: str, preview: dict[str, Any], cancel: threading.Event) -> None:
        public = preview["public"]
        private = preview["private"]
        component_id = str(public["component_id"])
        operation = str(public["operation"])
        self._job_update(job_id, status="running", phase="starting")
        try:
            if operation == "remove":
                if component_id in _CONTAINER_COMPONENTS:
                    script, _, uninstall_action = _CONTAINER_COMPONENTS[component_id]
                    bash = shutil.which("bash")
                    if not bash:
                        raise ComponentInstallError("Bash is unavailable for the bounded component lifecycle manager.")
                    self._run_command([bash, str(ROOT / script), uninstall_action], cancel, ROOT)
                    receipt = _safe_payload(self.receipt_root / f"{component_id}.json")
                    receipt.update({"status": "removed", "removed_at_utc": _utc_now(), "recoverable": True})
                    _private_json(self.receipt_root / f"{component_id}.json", receipt)
                elif component_id == "codev_companion":
                    self._codev_remove(component_id, cancel, job_id)
                else:
                    self._remove(component_id)
            elif component_id in _PYTHON_COMPONENTS or component_id == "scientific_engineering":
                self._python_install(component_id, private, cancel, job_id)
            elif component_id in _CONTAINER_COMPONENTS:
                self._container_install(component_id, private, cancel, job_id)
            elif component_id == "codev_companion":
                self._codev_install(component_id, private, cancel, job_id)
            elif component_id == "local_model_provider":
                _private_json(self.receipt_root / f"{component_id}.json", {
                    "contract_version": CONTRACT_VERSION, "component_id": component_id,
                    "status": "ready", "managed_by_elysia": False,
                    "user_data_present": False, "adopted_external_loopback_provider": True,
                    "installed_at_utc": _utc_now(), "raw_paths_exposed": False,
                    **self._root_receipt_fields(),
                })
            else:
                raise ComponentInstallError("The approved component operation has no bounded adapter.")
            self._job_update(
                job_id,
                status="succeeded",
                phase="complete",
                cleanup_complete=True,
                receipt_written=True,
                cancellation_too_late=cancel.is_set(),
            )
        except Exception as exc:
            staging = self.root / "staging" / job_id
            if cancel.is_set() and staging.is_dir() and staging.parent == self.root / "staging":
                shutil.rmtree(staging)
            recoverable = staging.exists()
            self._job_update(
                job_id,
                status="cancelled" if cancel.is_set() else "failed",
                phase="cancelled" if cancel.is_set() else "failed",
                recoverable=recoverable,
                cleanup_complete=not staging.exists(),
                error_summary=" ".join(str(exc).split())[:500],
            )


__all__ = (
    "CONTRACT_VERSION",
    "ComponentApplyRequest",
    "ComponentCancelRequest",
    "ComponentInstallError",
    "ComponentInstallService",
    "ComponentPreviewRequest",
)
