"""Non-mutating dependency catalog validation and safe presence checks."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import re
import shutil
from typing import Any

from .schemas import DependencyCategory, DependencyStatus, DependencyStatusEntry


VALID_CATALOG_KINDS = {
    "python",
    "system",
    "node_rust",
    "model",
    "tool",
    "application",
}
LAB_DEPENDENCY_IDS = {
    "videoforge_model_assets",
    "bubblewrap",
    "rootless_container_engine",
}
PRIVATE_DATA_DEPENDENCY_IDS = {
    "speechforge_model_assets",
    "imageforge_model_assets",
    "videoforge_model_assets",
}


class DependencyCatalogError(ValueError):
    """Raised when a tracked dependency contract is invalid."""


def validate_dependency_catalog(catalog: dict[str, Any]) -> None:
    if catalog.get("version") != 1:
        raise DependencyCatalogError("Unsupported dependency catalog version.")
    if catalog.get("status") != "declarative_only_installs_nothing":
        raise DependencyCatalogError("Dependency catalog must remain non-installing.")

    groups = catalog.get("dependency_groups")
    dependencies = catalog.get("dependencies")
    if not isinstance(groups, dict) or not isinstance(dependencies, dict):
        raise DependencyCatalogError("Dependency groups and entries are required.")

    for dependency_id, dependency in dependencies.items():
        if not isinstance(dependency_id, str) or not isinstance(dependency, dict):
            raise DependencyCatalogError("Dependency entries must be named mappings.")
        if dependency.get("profile") not in {
            "core",
            "workstation",
            "creator",
            "developer",
            "semantic_local",
            "neurofabric_cpu",
            "neurofabric_cuda",
        }:
            raise DependencyCatalogError("Dependency references an invalid profile.")
        if dependency.get("kind") not in VALID_CATALOG_KINDS:
            raise DependencyCatalogError("Dependency references an invalid category.")
        if not isinstance(dependency.get("required"), bool):
            raise DependencyCatalogError("Dependency required flags must be boolean.")
        if not isinstance(dependency.get("allowed_in_core"), bool):
            raise DependencyCatalogError("Dependency Core flags must be boolean.")
        checks = [
            key
            for key in ("import_check", "command_check", "doctor_check")
            if key in dependency
        ]
        if len(checks) != 1:
            raise DependencyCatalogError(
                "Every dependency must declare exactly one safe check contract."
            )

    for group in groups.values():
        if not isinstance(group, dict) or not isinstance(group.get("dependencies"), list):
            raise DependencyCatalogError("Dependency groups must contain lists.")
        if any(item not in dependencies for item in group["dependencies"]):
            raise DependencyCatalogError("Dependency group references an unknown entry.")


def _category(dependency_id: str, catalog_kind: str) -> DependencyCategory:
    if catalog_kind == "python":
        return DependencyCategory.PYTHON
    if catalog_kind == "system":
        return DependencyCategory.SYSTEM
    if catalog_kind == "model":
        return DependencyCategory.MODEL
    if catalog_kind == "node_rust":
        return (
            DependencyCategory.RUST
            if dependency_id == "rust_cargo"
            else DependencyCategory.NODE
        )
    if "worker" in dependency_id:
        return DependencyCategory.WORKER
    return DependencyCategory.EXTERNAL


def _distribution_name(package_name: str) -> str:
    match = re.match(r"[A-Za-z0-9_.-]+", package_name)
    return match.group(0) if match else package_name


def _python_status(dependency: dict[str, Any]) -> tuple[DependencyStatus, str | None]:
    module_name = dependency["import_check"]
    try:
        found = importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return DependencyStatus.UNKNOWN, None

    if not found:
        return (
            DependencyStatus.MISSING
            if dependency["required"]
            else DependencyStatus.OPTIONAL_MISSING,
            None,
        )

    try:
        version = importlib.metadata.version(_distribution_name(dependency["package_name"]))
    except importlib.metadata.PackageNotFoundError:
        version = None
    return DependencyStatus.PRESENT, version


def _command_status(dependency: dict[str, Any]) -> DependencyStatus:
    commands = [dependency["command_check"]]
    companion = dependency.get("companion_command_check")
    if companion:
        commands.append(companion)

    valid = all(
        isinstance(command, list)
        and bool(command)
        and isinstance(command[0], str)
        and shutil.which(command[0]) is not None
        for command in commands
    )
    if valid:
        return DependencyStatus.PRESENT
    return (
        DependencyStatus.MISSING
        if dependency["required"]
        else DependencyStatus.OPTIONAL_MISSING
    )


def _doctor_only_status(
    dependency_id: str,
    dependency: dict[str, Any],
    selected_profile_ids: set[str],
) -> DependencyStatus:
    if dependency_id in LAB_DEPENDENCY_IDS or dependency.get("kind") == "model":
        return DependencyStatus.LAB_GATED
    if dependency["profile"] not in selected_profile_ids:
        return DependencyStatus.PROFILE_GATED
    return DependencyStatus.UNKNOWN


def inspect_dependency(
    dependency_id: str,
    dependency: dict[str, Any],
    *,
    selected_profile_ids: set[str],
) -> DependencyStatusEntry:
    """Inspect one dependency without importing it, executing it, or using network."""
    version: str | None = None
    if "import_check" in dependency:
        status, version = _python_status(dependency)
        check_method = "module_metadata"
    elif "command_check" in dependency:
        status = _command_status(dependency)
        check_method = "executable_lookup"
    else:
        status = _doctor_only_status(
            dependency_id,
            dependency,
            selected_profile_ids,
        )
        check_method = "doctor_required"

    profile_id = dependency["profile"]
    if dependency_id in LAB_DEPENDENCY_IDS or dependency.get("kind") == "model":
        activation_state = "lab_gated"
    elif profile_id not in selected_profile_ids:
        activation_state = "profile_gated"
    else:
        activation_state = "active_profile_truth_only"

    warning: str | None = None
    if status == DependencyStatus.UNKNOWN:
        warning = "Pass 6 doctor proof is required; no executable or worker was started."
    elif status == DependencyStatus.PROFILE_GATED:
        warning = "The owning optional profile is not selected; nothing was activated."
    elif status == DependencyStatus.LAB_GATED:
        warning = "Lab and isolation proof is required; nothing was activated."
    elif status in {DependencyStatus.MISSING, DependencyStatus.OPTIONAL_MISSING}:
        warning = "Dependency was not found by the bounded local presence check."

    return DependencyStatusEntry(
        dependency_id=dependency_id,
        label=str(dependency["package_name"]),
        profile_id=profile_id,
        category=_category(dependency_id, dependency["kind"]),
        catalog_kind=dependency["kind"],
        required=dependency["required"],
        purpose=dependency["purpose"],
        status=status,
        activation_state=activation_state,
        check_method=check_method,
        version=version,
        warning=warning,
        external_download_required=bool(dependency.get("external_download_required")),
        private_data_may_be_involved=dependency_id in PRIVATE_DATA_DEPENDENCY_IDS,
        allowed_in_core=dependency["allowed_in_core"],
    )


def inspect_dependency_catalog(
    catalog: dict[str, Any],
    *,
    selected_profile_ids: set[str],
) -> list[DependencyStatusEntry]:
    validate_dependency_catalog(catalog)
    return [
        inspect_dependency(
            dependency_id,
            dependency,
            selected_profile_ids=selected_profile_ids,
        )
        for dependency_id, dependency in sorted(catalog["dependencies"].items())
    ]


__all__ = (
    "DependencyCatalogError",
    "VALID_CATALOG_KINDS",
    "inspect_dependency",
    "inspect_dependency_catalog",
    "validate_dependency_catalog",
)
