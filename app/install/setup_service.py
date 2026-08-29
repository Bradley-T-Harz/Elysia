"""Transactional Elysia Setup preview/apply state over the authoritative graph."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
import yaml

from .component_graph_service import (
    ComponentGraphError,
    load_component_graph,
    resolve_profile_components,
)
from .acquisition_service import load_acquisition_manifests
from .component_install_service import ComponentInstallService
from .doctor_service import record_doctor_result, run_doctor
from .dependency_disposition_service import dependency_install_summary
from .hardware_service import detect_local_hardware
from .install_root_service import install_root_hash
from .paths import ElysiaPaths, resolve_elysia_paths
from .schemas import DependencyStatus
from .system_prerequisite_service import SystemPrerequisiteService


SETUP_CONTRACT_VERSION = "elysia-setup-1.0"
PREVIEW_TTL_SECONDS = 1800


class SetupError(RuntimeError):
    """A Setup plan or mutation failed closed."""


class SetupPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    profile_id: str
    distribution_form: str = Field(
        ...,
        pattern=r"^(deb|appimage|user_local_desktop|onefile_core|source)$",
    )
    install_root: str | None = Field(default=None, max_length=4096)
    custom_components: list[str] = Field(default_factory=list, max_length=16)
    internet_available: bool = False


class SetupApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    preview_id: str = Field(..., pattern=r"^setup_[a-f0-9]{24}$")
    approval_token: str = Field(..., min_length=32, max_length=256)
    operator_approved: bool


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _private_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}-", delete=False
    ) as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    temporary.replace(path)


def _private_read(path: Path) -> dict[str, Any]:
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_mode & 0o077
        or path.stat().st_uid != os.getuid()
    ):
        raise SetupError("The private Setup receipt is unavailable or unsafe.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SetupError("The private Setup receipt is invalid.") from exc
    if not isinstance(payload, dict):
        raise SetupError("The private Setup receipt is invalid.")
    return payload


def _nearest_existing(path: Path) -> Path:
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def _detected_distribution_form(paths: ElysiaPaths) -> str:
    configured = os.environ.get("ELYSIA_DISTRIBUTION_FORM", "").strip().lower()
    allowed = {"deb", "appimage", "user_local_desktop", "onefile_core", "source"}
    if configured in allowed:
        return configured
    return "onefile_core" if paths.mode.value == "packaged" else "source"


def _path_truth(request: SetupPreviewRequest) -> tuple[dict[str, Any], Path]:
    if request.distribution_form == "deb" and request.install_root:
        raise SetupError("A .deb uses conventional package-manager paths; Setup cannot pretend it has an arbitrary install root.")
    if request.install_root:
        root = Path(request.install_root).expanduser()
        if not root.is_absolute():
            raise SetupError("A custom install root must be absolute.")
    else:
        root = Path.home() / ".local" / "lib" / "elysia"
    resolved = root.resolve(strict=False)
    if resolved in {Path("/"), Path.home().resolve()}:
        raise SetupError("The install root is too broad.")
    ancestor = _nearest_existing(resolved)
    writable = ancestor.is_dir() and os.access(ancestor, os.W_OK)
    statvfs = os.statvfs(ancestor)
    read_only = bool(statvfs.f_flag & getattr(os, "ST_RDONLY", 1))
    noexec = bool(statvfs.f_flag & getattr(os, "ST_NOEXEC", 0))
    available = int(statvfs.f_bavail * statvfs.f_frsize)
    return {
        "selection": "custom_user_local" if request.install_root else "default_user_local",
        "distribution_location_truth": (
            "conventional_package_manager_paths"
            if request.distribution_form == "deb"
            else "relocatable_executable_with_stable_xdg_data"
            if request.distribution_form == "appimage"
            else "user_local_runtime_root_with_stable_xdg_data"
        ),
        "path_hash": hashlib.sha256(str(resolved).encode()).hexdigest(),
        "contains_spaces": " " in str(resolved),
        "contains_unicode": not str(resolved).isascii(),
        "length": len(str(resolved)),
        "writable": writable and not read_only,
        "owned_by_current_user": ancestor.stat().st_uid == os.getuid(),
        "read_only": read_only,
        "noexec": noexec,
        "available_bytes": available,
        "raw_path_exposed": False,
    }, resolved


class SetupService:
    def __init__(self, paths: ElysiaPaths | None = None) -> None:
        self.paths = paths or resolve_elysia_paths()
        self.setup_state_dir = self.paths.state_dir / "setup"
        self.preview_dir = self.setup_state_dir / "previews"
        self.receipt_path = self.setup_state_dir / "installation.json"
        self.doctor_receipt_path = self.setup_state_dir / "final-doctor.json"
        self.profile_override_path = self.paths.config_dir / "install" / "profiles.yaml"

    def state(self) -> dict[str, Any]:
        receipt: dict[str, Any] | None = None
        if self.receipt_path.is_file():
            try:
                receipt = _private_read(self.receipt_path)
            except SetupError:
                receipt = {"status": "invalid_receipt"}
        component_ids = receipt.get("component_ids", []) if receipt else []
        component_state = {
            item["component_id"]: item["status"]
            for item in ComponentInstallService(self.paths).state()["components"]
        }
        pending = [
            component_id for component_id in component_ids
            if component_state.get(component_id) not in {"package_bound", "ready", "ready_with_model_gates"}
        ]
        configured = bool(receipt and receipt.get("status") == "configured")
        doctor_receipt: dict[str, Any] | None = None
        if self.doctor_receipt_path.is_file():
            try:
                doctor_receipt = _private_read(self.doctor_receipt_path)
            except SetupError:
                doctor_receipt = None
        doctor_passed = bool(
            doctor_receipt
            and doctor_receipt.get("passed") is True
            and receipt
            and doctor_receipt.get("setup_plan_hash") == receipt.get("plan_hash")
        )
        machine_ready = configured and not pending and doctor_passed
        return {
            "contract_version": SETUP_CONTRACT_VERSION,
            "runtime_mode": self.paths.mode.value,
            "detected_distribution_form": _detected_distribution_form(self.paths),
            "distribution_form_locked": self.paths.mode.value == "packaged",
            "configured": configured,
            "machine_ready": machine_ready,
            "setup_required": self.paths.mode.value == "packaged" and not machine_ready,
            "status": (
                "ready" if machine_ready
                else "components_pending" if pending
                else "doctor_pending" if configured
                else "not_configured"
            ),
            "profile_id": receipt.get("profile_id") if receipt else None,
            "distribution_form": receipt.get("distribution_form") if receipt else None,
            "component_ids": component_ids,
            "pending_component_ids": pending,
            "component_status": component_state,
            "doctor_required": configured and not pending and not doctor_passed,
            "doctor_passed": doctor_passed,
            "doctor_classification": (
                doctor_receipt.get("classification") if doctor_receipt else None
            ),
            "doctor_degraded_check_ids": (
                doctor_receipt.get("degraded_check_ids", []) if doctor_receipt else []
            ),
            "machine_installation_separate_from_personal_onboarding": True,
            "profile_selection_grants_operation_approval": False,
            "raw_paths_exposed": False,
        }

    def preview(self, request: SetupPreviewRequest) -> dict[str, Any]:
        detected_form = _detected_distribution_form(self.paths)
        if self.paths.mode.value == "packaged" and request.distribution_form != detected_form:
            raise SetupError(
                "The selected distribution form does not match the running Elysia package."
            )
        try:
            graph = load_component_graph()
            components = resolve_profile_components(
                request.profile_id,
                custom_components=request.custom_components,
            )
        except ComponentGraphError as exc:
            raise SetupError(str(exc)) from exc
        path_truth, install_root = _path_truth(request)
        hardware = detect_local_hardware()
        dependency_dispositions = dependency_install_summary(
            components,
            scientific_variant=(
                "cuda" if hardware["gpu"]["cuda_variant_supported"] else "cpu"
            ),
        )
        projection = dict(graph["profiles"][request.profile_id]["runtime_projection"])
        if request.profile_id in {"scientific_engineering_mega", "complete_v1_mega"} and hardware["gpu"]["cuda_variant_supported"]:
            projection["additional_profiles"] = [
                "neurofabric_cuda" if item == "neurofabric_cpu" else item
                for item in projection["additional_profiles"]
            ]
        acquisitions = load_acquisition_manifests()["components"]
        prerequisites = SystemPrerequisiteService(self.paths).inspect(components)
        acquisition_components = [
            component_id
            for component_id in components
            if acquisitions[component_id]["method"] != "package_bound"
        ]
        estimated_download_bytes = sum(
            int(acquisitions[component_id]["estimated_download_bytes"])
            for component_id in acquisition_components
        )
        estimated_installed_bytes = sum(
            int(acquisitions[component_id]["estimated_installed_bytes"])
            for component_id in components
        )
        reserve_bytes = 2 * 1024**3
        warnings: list[str] = []
        blockers: list[str] = []
        if not hardware["supported_ubuntu"]:
            blockers.append("This release supports Ubuntu 24.04; the detected operating system is outside the qualified contract.")
        if not hardware["supported_architecture"]:
            blockers.append("This release supports the x86-64 architecture; the detected architecture is outside the qualified contract.")
        hardware_selected_python = sorted(
            {"creator_perception", "scientific_engineering"} & set(components)
        )
        if hardware_selected_python and not hardware["cpu_only_supported"]:
            missing = ", ".join(hardware["missing_cpu_features"]) or "the approved CPU baseline"
            blockers.append(
                "The selected hardware-sensitive runtime requires the approved CPU instruction baseline; "
                f"missing: {missing}. No incompatible Torch environment will be installed."
            )
        if not path_truth["writable"]:
            blockers.append("The selected target is not writable by the current user.")
        if not path_truth["owned_by_current_user"]:
            blockers.append("The selected user-local target is not owned by the current user.")
        if path_truth["noexec"] and (
            request.distribution_form in {"appimage", "user_local_desktop", "onefile_core", "source"}
            or acquisition_components
        ):
            blockers.append("The selected target is mounted noexec for an executable distribution form.")
        if acquisition_components:
            warnings.append("Selected external components require their own exact metadata/size preview and approval before transfer.")
        if prerequisites["exact_package_operations"]:
            warnings.append("Missing Ubuntu packages require a separate exact graphical polkit approval before component installation.")
        if prerequisites["external_missing_dependency_ids"]:
            warnings.append(
                "Separately governed external prerequisites are not currently present: "
                + ", ".join(prerequisites["external_missing_dependency_ids"])
                + "."
            )
        if path_truth["available_bytes"] < reserve_bytes:
            blockers.append(
                "The selected filesystem cannot preserve the mandatory lifecycle free-space reserve."
            )
        elif path_truth["available_bytes"] < estimated_installed_bytes + reserve_bytes:
            warnings.append(
                "The selected filesystem cannot currently hold the complete profile estimate plus lifecycle reserve; exact component/model previews will block oversized operations while still allowing smaller or model-free choices."
            )
        if request.profile_id in {"scientific_engineering_mega", "complete_v1_mega"} and not hardware["gpu"]["cuda_variant_supported"]:
            warnings.append("The CPU scientific variant will be used; unsupported CUDA was not selected.")
        plan = {
            "contract_version": SETUP_CONTRACT_VERSION,
            "profile_id": request.profile_id,
            "distribution_form": request.distribution_form,
            "component_ids": components,
            "runtime_projection": projection,
            "path_truth": path_truth,
            "hardware": hardware,
            "network_preview": {
                "internet_available": request.internet_available,
                "runtime_default": "disabled",
                "external_acquisition_requires_separate_exact_confirmation": True,
                "personal_data_egress": False,
            },
            "privilege_preview": {
                "silent_sudo": False,
                "package_manager_privilege_required": bool(
                    request.distribution_form == "deb"
                    or prerequisites["package_manager_privilege_required"]
                ),
                "exact_system_package_operations": prerequisites["exact_package_operations"],
                "authorization_mechanism": prerequisites["authorization_mechanism"],
                "full_setup_runs_as_root": False,
                "user_local_forms": ["appimage", "user_local_desktop", "onefile_core", "source"],
            },
            "system_prerequisites": prerequisites,
            "unresolved_acquisition_component_ids": acquisition_components,
            "acquisition_component_ids": acquisition_components,
            "estimated_download_bytes": estimated_download_bytes,
            "estimated_installed_bytes": estimated_installed_bytes,
            "lifecycle_reserve_bytes": reserve_bytes,
            "component_license_preview": [
                {
                    "component_id": component_id,
                    "license": acquisitions[component_id]["license"],
                    "redistribution": acquisitions[component_id]["redistribution"],
                }
                for component_id in components
            ],
            "dependency_install_dispositions": dependency_dispositions,
            "warnings": warnings,
            "blockers": blockers,
            "ready_to_apply": not blockers,
        }
        plan_hash = hashlib.sha256(
            json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        preview_id = f"setup_{secrets.token_hex(12)}"
        approval_token = secrets.token_urlsafe(32)
        _private_write(
            self.preview_dir / f"{preview_id}.json",
            {
                "preview_id": preview_id,
                "approval_token_hash": hashlib.sha256(approval_token.encode()).hexdigest(),
                "plan_hash": plan_hash,
                "plan": plan,
                "private": {
                    "install_root": str(install_root),
                    "install_root_sha256": install_root_hash(install_root),
                },
                "created_at_utc": _utc_now(),
            },
        )
        return {
            **plan,
            "preview_id": preview_id,
            "approval_token": approval_token,
            "plan_hash": plan_hash,
            "mutation_performed": False,
        }

    def apply(self, request: SetupApplyRequest) -> dict[str, Any]:
        if not request.operator_approved:
            raise SetupError("Setup apply requires exact operator approval.")
        preview_path = self.preview_dir / f"{request.preview_id}.json"
        preview = _private_read(preview_path)
        try:
            created = datetime.fromisoformat(
                str(preview["created_at_utc"]).replace("Z", "+00:00")
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SetupError("The exact Setup preview timestamp is invalid.") from exc
        if created.tzinfo is None or (
            datetime.now(UTC) - created.astimezone(UTC)
        ).total_seconds() > PREVIEW_TTL_SECONDS:
            raise SetupError("The exact Setup preview expired.")
        if not secrets.compare_digest(
            str(preview["approval_token_hash"]),
            hashlib.sha256(request.approval_token.encode()).hexdigest(),
        ):
            raise SetupError("The Setup approval token is invalid.")
        plan = preview["plan"]
        private = preview.get("private")
        if not isinstance(private, dict):
            raise SetupError("The exact Setup private install-root plan is unavailable.")
        install_root = Path(str(private.get("install_root") or ""))
        if (
            not install_root.is_absolute()
            or install_root_hash(install_root) != private.get("install_root_sha256")
            or install_root_hash(install_root) != plan["path_truth"]["path_hash"]
        ):
            raise SetupError("The exact Setup install-root plan failed integrity.")
        if not plan.get("ready_to_apply"):
            raise SetupError("Setup cannot apply while its preview contains blocking conditions.")
        ancestor = _nearest_existing(install_root)
        try:
            current_stat = os.statvfs(ancestor)
        except OSError as exc:
            raise SetupError("The approved Setup target is no longer available.") from exc
        if (
            not ancestor.is_dir()
            or ancestor.stat().st_uid != os.getuid()
            or not os.access(ancestor, os.W_OK)
            or bool(current_stat.f_flag & getattr(os, "ST_RDONLY", 1))
        ):
            raise SetupError("The approved Setup target is no longer safely writable by this user.")
        if (
            bool(current_stat.f_flag & getattr(os, "ST_NOEXEC", 0))
            and (
                plan["distribution_form"] in {"appimage", "user_local_desktop", "onefile_core", "source"}
                or plan["acquisition_component_ids"]
            )
        ):
            raise SetupError("The approved Setup target is now mounted noexec.")
        available_now = int(current_stat.f_bavail * current_stat.f_frsize)
        if available_now < int(plan["lifecycle_reserve_bytes"]):
            raise SetupError("The approved Setup target no longer preserves the lifecycle free-space reserve.")
        profile_payload = {
            "version": 1,
            "contract_version": "elysia-install-profile-override-1.0",
            "active_profile": plan["runtime_projection"]["active_profile"],
            "additional_profiles": plan["runtime_projection"]["additional_profiles"],
            "notes": "Written by Elysia Setup from the authoritative component graph.",
        }
        self.profile_override_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.profile_override_path.parent.chmod(0o700)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.profile_override_path.parent,
            prefix=".profiles-", suffix=".yaml", delete=False,
        ) as handle:
            yaml.safe_dump(profile_payload, handle, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        temporary.chmod(0o600)
        temporary.replace(self.profile_override_path)
        receipt = {
            "status": "configured",
            "contract_version": SETUP_CONTRACT_VERSION,
            "profile_id": plan["profile_id"],
            "distribution_form": plan["distribution_form"],
            "component_ids": plan["component_ids"],
            "custom_components": [
                component_id for component_id in plan["component_ids"]
                if component_id not in resolve_profile_components("core")
            ] if plan["profile_id"] == "custom" else [],
            "plan_hash": preview["plan_hash"],
            "install_root": str(install_root.resolve(strict=False)),
            "install_root_sha256": install_root_hash(install_root),
            "configured_at_utc": _utc_now(),
            "personal_onboarding_started": False,
            "raw_paths_exposed": False,
        }
        _private_write(self.receipt_path, receipt)
        preview_path.unlink(missing_ok=True)
        return {**self.state(), "mutation_performed": True, "doctor_required": True}

    def run_final_doctor(self) -> dict[str, Any]:
        """Run and record the exact post-component Doctor gate for Setup.

        A selected Creator profile may finish with explicitly unselected model
        powers gated, as the governing contract permits a narrow, visible
        optional degradation. Every other required missing, blocked, unknown,
        or degraded check remains a Setup blocker.
        """
        state = self.state()
        if not state["configured"] or state["pending_component_ids"]:
            raise SetupError(
                "Doctor cannot close Setup until every selected component operation has finished."
            )
        report = run_doctor(
            paths=self.paths,
            probe_local_services=True,
            profile_override_path=self.profile_override_path,
            model_override_path=self.paths.config_dir / "models" / "local_overrides.yaml",
        )
        permitted_degraded: list[str] = []
        blocking: list[str] = []
        for check in report.checks:
            status = DependencyStatus(check.status)
            if not check.required or status == DependencyStatus.PRESENT:
                continue
            if (
                check.check_id == "component_creator_perception"
                and status == DependencyStatus.DEGRADED
                and "unselected model-specific capabilities remain truthfully gated"
                in check.summary
            ):
                permitted_degraded.append(check.check_id)
                continue
            if status in {
                DependencyStatus.MISSING,
                DependencyStatus.BLOCKED,
                DependencyStatus.DEGRADED,
                DependencyStatus.UNKNOWN,
            }:
                blocking.append(check.check_id)
        passed = not blocking
        record_doctor_result(report, paths=self.paths)
        installation = _private_read(self.receipt_path)
        payload = {
            "contract_version": SETUP_CONTRACT_VERSION,
            "passed": passed,
            "classification": (
                "ready_with_explicit_optional_model_gates"
                if passed and permitted_degraded
                else "ready" if passed else "blocked"
            ),
            "setup_plan_hash": installation.get("plan_hash"),
            "doctor_version": report.doctor_version,
            "active_profile_id": report.active_profile_id,
            "blocking_check_ids": blocking,
            "degraded_check_ids": permitted_degraded,
            "recorded_at_utc": _utc_now(),
            "raw_paths_exposed": False,
        }
        _private_write(self.doctor_receipt_path, payload)
        if not passed:
            raise SetupError(
                "Setup Doctor found blocking selected-profile checks: "
                + ", ".join(blocking)
                + "."
            )
        return {**self.state(), "doctor_report_recorded": True, "mutation_performed": True}


__all__ = (
    "PREVIEW_TTL_SECONDS",
    "SETUP_CONTRACT_VERSION",
    "SetupApplyRequest",
    "SetupError",
    "SetupPreviewRequest",
    "SetupService",
)
