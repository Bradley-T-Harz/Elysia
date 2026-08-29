from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import yaml

from app.api.capability_service import get_capabilities_status
from app.api.main import create_app
from app.install.dependency_service import VALID_CATALOG_KINDS
from app.install.profile_service import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_PROFILES_PATH,
    resolve_install_profile_status,
)
from app.install.schemas import DependencyStatus


def _missing(tmp_path: Path, name: str) -> Path:
    return tmp_path / name


def _write_yaml(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_default_profile_resolution_is_deterministic_and_non_mutating(tmp_path: Path) -> None:
    first, first_warnings = resolve_install_profile_status(
        profile_override_path=_missing(tmp_path, "profiles.yaml"),
        model_override_path=_missing(tmp_path, "models.yaml"),
    )
    second, second_warnings = resolve_install_profile_status(
        profile_override_path=_missing(tmp_path, "profiles.yaml"),
        model_override_path=_missing(tmp_path, "models.yaml"),
    )

    assert first.active_profile_id == second.active_profile_id == "core"
    assert first.selected_profile_ids == second.selected_profile_ids == ["core"]
    assert first.resolved_profile_ids == second.resolved_profile_ids == ["core"]
    assert [item.profile_id for item in first.available_profiles] == [
        "core",
        "workstation",
        "creator",
        "developer",
        "semantic_local",
        "neurofabric_cpu",
        "neurofabric_cuda",
    ]
    assert first.profile_selection_grants_approval is False
    assert first.install_authority_available is False
    assert first.download_authority_available is False
    assert first.worker_start_authority_available is False
    assert first.doctor_executed is False
    assert not any(worker.enabled for worker in first.worker_summaries)
    assert first_warnings == second_warnings


def test_optional_profile_selection_resolves_inheritance_without_granting_authority(
    tmp_path: Path,
) -> None:
    override = _write_yaml(
        tmp_path / "local_profiles.yaml",
        {
            "version": 1,
            "contract_version": "elysia-local-profile-selection-1.0",
            "active_profile": "creator",
            "additional_profiles": ["developer"],
        },
    )
    data, _ = resolve_install_profile_status(
        profile_override_path=override,
        model_override_path=_missing(tmp_path, "models.yaml"),
    )

    assert data.active_profile_id == "creator"
    assert data.selected_profile_ids == ["creator", "developer"]
    assert data.resolved_profile_ids == ["core", "workstation", "creator", "developer"]
    assert data.local_overrides.selection_source == "gitignored_local_override"
    assert data.profile_selection_grants_approval is False
    assert data.install_authority_available is False
    assert data.worker_start_authority_available is False


def test_public_developer_profile_requires_runtime_not_source_test_dependencies(
    tmp_path: Path,
) -> None:
    override = _write_yaml(
        tmp_path / "local_profiles.yaml",
        {
            "version": 1,
            "contract_version": "elysia-local-profile-selection-1.0",
            "active_profile": "developer",
            "additional_profiles": [],
        },
    )
    data, _ = resolve_install_profile_status(
        profile_override_path=override,
        model_override_path=_missing(tmp_path, "models.yaml"),
    )

    dependency_ids = {item.dependency_id for item in data.dependencies}
    dependency_by_id = {item.dependency_id: item for item in data.dependencies}
    assert {"vscode", "git", "codev_vsix"} <= dependency_ids
    assert dependency_by_id["pytest"].required is False
    assert dependency_by_id["httpx"].required is False
    profile_contract = yaml.safe_load(DEFAULT_PROFILES_PATH.read_text(encoding="utf-8"))
    assert "developer_python_test" not in profile_contract["profiles"]["developer"]["dependency_groups"]
    assert all(worker.worker_id != "codev" for worker in data.worker_summaries)


def test_invalid_profile_override_fails_closed_to_core_without_path_leakage(
    tmp_path: Path,
) -> None:
    marker = "/home/private-operator/PROFILE_MARKER"
    override = _write_yaml(
        tmp_path / "local_profiles.yaml",
        {
            "version": 1,
            "active_profile": "creator",
            "unexpected_private_path": marker,
        },
    )
    data, warnings = resolve_install_profile_status(
        profile_override_path=override,
        model_override_path=_missing(tmp_path, "models.yaml"),
    )

    rendered = json.dumps(data.to_payload()) + json.dumps(warnings)
    assert data.active_profile_id == "core"
    assert data.resolution_state == "invalid"
    assert data.local_overrides.authority_granted is False
    assert marker not in rendered
    assert "/home/" not in rendered


def test_valid_model_override_surfaces_labels_only_and_never_values(tmp_path: Path) -> None:
    private_path = "/home/private-operator/MODEL_VAULT_MARKER"
    private_tag = "PRIVATE_MODEL_TAG_MARKER:7b"
    override = _write_yaml(
        tmp_path / "local_overrides.yaml",
        {
            "version": 1,
            "contract_version": "elysia-local-model-overrides-1.0",
            "local_only": True,
            "provider_overrides": {
                "ollama": {
                    "base_url": "http://127.0.0.1:11434",
                    "role_runtime_tags": {
                        "primary_general": private_tag,
                    },
                }
            },
            "model_vault": {
                "root": private_path,
                "permit_authenticated_download_state": False,
                "provenance_manifest": None,
            },
            "worker_overrides": {
                "imageforge": {"model_root": private_path},
            },
            "policy": {
                "allow_network_for_model_acquisition": False,
                "allow_runtime_network": False,
                "allow_private_memory_mounts": False,
                "allow_host_docker_socket": False,
                "allow_physical_hardware": False,
            },
        },
    )
    data, warnings = resolve_install_profile_status(
        profile_override_path=_missing(tmp_path, "profiles.yaml"),
        model_override_path=override,
    )

    rendered = json.dumps(data.to_payload()) + json.dumps(warnings)
    assert data.local_overrides.state == "loaded"
    assert data.local_overrides.raw_values_exposed is False
    assert data.local_overrides.authority_granted is False
    assert data.provider_summary.configured_role_ids == ["primary_general"]
    assert data.provider_summary.network_check_performed is False
    assert data.provider_summary.model_loaded is False
    assert private_path not in rendered
    assert private_tag not in rendered
    assert "/home/" not in rendered


def test_authority_bearing_model_override_is_rejected_and_ignored(tmp_path: Path) -> None:
    override = _write_yaml(
        tmp_path / "local_overrides.yaml",
        {
            "version": 1,
            "local_only": True,
            "provider_overrides": {},
            "model_vault": {"permit_authenticated_download_state": False},
            "worker_overrides": {},
            "policy": {"allow_runtime_network": True},
        },
    )
    data, warnings = resolve_install_profile_status(
        profile_override_path=_missing(tmp_path, "profiles.yaml"),
        model_override_path=override,
    )

    assert data.resolution_state == "invalid"
    assert data.local_overrides.state == "invalid_fail_closed"
    assert data.local_overrides.configured_count == 0
    assert data.local_overrides.authority_granted is False
    assert warnings


def test_dependency_catalog_runtime_vocabulary_and_core_boundaries(tmp_path: Path) -> None:
    catalog = yaml.safe_load(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))
    profiles = yaml.safe_load(DEFAULT_PROFILES_PATH.read_text(encoding="utf-8"))
    data, _ = resolve_install_profile_status(
        profile_override_path=_missing(tmp_path, "profiles.yaml"),
        model_override_path=_missing(tmp_path, "models.yaml"),
    )

    assert all(item["kind"] in VALID_CATALOG_KINDS for item in catalog["dependencies"].values())
    assert set(data.dependency_summary) == {status.value for status in DependencyStatus}
    assert all(
        dependency.status in {status.value for status in DependencyStatus}
        for dependency in data.dependencies
    )
    core_ids = {
        dependency_id
        for group_id in profiles["profiles"]["core"]["dependency_groups"]
        for dependency_id in catalog["dependency_groups"][group_id]["dependencies"]
    }
    forbidden = {"torch", "diffusers", "codev_vsix", "videoforge_model_assets"}
    assert core_ids.isdisjoint(forbidden)
    assert all(catalog["dependencies"][item]["allowed_in_core"] for item in core_ids)


def test_profile_status_route_and_capability_truth_are_live() -> None:
    async def exercise_route() -> tuple[int, dict]:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://elysia.local",
        ) as client:
            response = await client.get("/status/profiles")
            return response.status_code, response.json()

    status_code, payload = asyncio.run(exercise_route())
    capabilities = {
        entry["capability_key"]: entry
        for entry in get_capabilities_status()["data"]["capabilities"]
    }

    assert status_code == 200
    assert payload["status"] in {"ok", "degraded"}
    assert payload["result_type"] == "install_profile_status"
    assert payload["locality"] == "local"
    assert payload["approval_state"] == "not_needed"
    assert payload["data"]["active_profile_id"] == "core"
    assert payload["data"]["install_authority_available"] is False
    assert payload["data"]["doctor_executed"] is False
    assert capabilities["install_profile_manifests"]["state"] == "live"
    assert capabilities["install_profile_manifests"]["supporting_endpoint"] == "/status/profiles"


def test_status_profile_api_contract_matches_the_live_read_only_route() -> None:
    contract_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "api"
        / "status_profiles_schema.yaml"
    )
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))[
        "status_profiles_schema"
    ]

    assert contract["route"] == "/status/profiles"
    assert contract["method"] == "GET"
    rules = " ".join(contract["governing_rules"])
    assert "installs, downloads, starts, enables, or mutates nothing" in rules
    assert "Raw local paths" in rules
    fields = contract["response"]["data_payload"]["fields"]
    assert fields["install_authority_available"]["must_be"] is False
    assert fields["download_authority_available"]["must_be"] is False
    assert fields["worker_start_authority_available"]["must_be"] is False
    assert fields["doctor_executed"]["must_be"] is False
