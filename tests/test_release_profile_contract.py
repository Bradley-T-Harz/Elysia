from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROFILES_PATH = ROOT / "config" / "install" / "profiles.yaml"
CATALOG_PATH = ROOT / "config" / "install" / "dependency_catalog.yaml"
OVERRIDES_EXAMPLE_PATH = ROOT / "config" / "models" / "local_overrides.example.yaml"
PROFILE_OVERRIDE_EXAMPLE_PATH = ROOT / "config" / "install" / "local_profiles.example.yaml"
REQUIREMENTS_ROOT = ROOT / "requirements"


def _load_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_release_profiles_define_canonical_and_semantic_optional_profiles() -> None:
    payload = _load_yaml(PROFILES_PATH)
    assert payload["target_product_version"] == "1.0.0"
    assert payload["current_channel"] == "stable"
    assert set(payload["profiles"]) == {
        "core", "workstation", "creator", "developer", "semantic_local",
        "neurofabric_cpu", "neurofabric_cuda",
    }
    assert payload["profiles"]["core"]["default_enabled"] is True
    assert all(
        profile["default_enabled"] is False
        for key, profile in payload["profiles"].items()
        if key != "core"
    )


def test_profile_selection_cannot_grant_approval_or_weaken_safety_floor() -> None:
    doctrine = _load_yaml(PROFILES_PATH)["doctrine"]
    assert doctrine["profile_selection_grants_operation_approval"] is False
    assert doctrine["profiles_may_weaken_safety_floor"] is False
    assert doctrine["silent_cloud_fallback_allowed"] is False
    assert doctrine["private_data_export_allowed_by_default"] is False


def test_profile_dependency_groups_resolve_to_catalog_entries() -> None:
    profiles = _load_yaml(PROFILES_PATH)["profiles"]
    catalog = _load_yaml(CATALOG_PATH)
    groups = catalog["dependency_groups"]
    dependencies = catalog["dependencies"]

    for profile in profiles.values():
        for group_id in profile["dependency_groups"]:
            assert group_id in groups
            for dependency_id in groups[group_id]["dependencies"]:
                assert dependency_id in dependencies


def test_dependency_catalog_has_doctor_metadata_and_installs_nothing() -> None:
    catalog = _load_yaml(CATALOG_PATH)
    assert catalog["status"] == "declarative_only_installs_nothing"
    valid_kinds = {"python", "system", "node_rust", "model", "tool", "application"}

    for dependency_id, dependency in catalog["dependencies"].items():
        assert dependency["package_name"]
        assert dependency["profile"] in {
            "core", "workstation", "creator", "developer", "semantic_local",
            "neurofabric_cpu", "neurofabric_cuda",
        }
        assert dependency["kind"] in valid_kinds
        assert isinstance(dependency["required"], bool)
        assert isinstance(dependency["external_download_required"], bool)
        assert isinstance(dependency["allowed_in_core"], bool)
        assert dependency["purpose"]
        assert dependency["license_provenance_note"]
        assert any(
            key in dependency
            for key in ("import_check", "command_check", "doctor_check")
        ), dependency_id


def test_core_group_contains_no_non_core_dependency() -> None:
    catalog = _load_yaml(CATALOG_PATH)
    groups = catalog["dependency_groups"]
    dependencies = catalog["dependencies"]
    core_dependency_ids = {
        dependency_id
        for group_id in ("core_python_runtime", "core_desktop_runtime")
        for dependency_id in groups[group_id]["dependencies"]
    }
    assert core_dependency_ids
    assert all(dependencies[item]["allowed_in_core"] is True for item in core_dependency_ids)
    assert all(dependencies[item]["profile"] == "core" for item in core_dependency_ids)


def test_core_never_contains_creator_or_developer_python_stacks() -> None:
    core = (REQUIREMENTS_ROOT / "core.txt").read_text(encoding="utf-8").lower()
    forbidden = {
        "torch",
        "diffusers",
        "safetensors",
        "kokoro-onnx",
        "pytest",
        "httpx",
        "pandas",
        "pyarrow",
        "geopandas",
        "opencv-python",
    }
    assert not any(package in core for package in forbidden)


def test_profile_requirements_compose_without_redefining_core() -> None:
    workstation = (REQUIREMENTS_ROOT / "workstation.txt").read_text(encoding="utf-8")
    creator = (REQUIREMENTS_ROOT / "creator.txt").read_text(encoding="utf-8")
    developer = (REQUIREMENTS_ROOT / "developer.txt").read_text(encoding="utf-8")
    assert "-r core.txt" in workstation
    assert "-r workstation.txt" in creator
    assert "-r core.txt" in developer


def test_hard_prohibited_defaults_are_not_core_capabilities() -> None:
    tiers = _load_yaml(PROFILES_PATH)["capability_tiers"]
    core = set(tiers["core_v1_default"])
    hard_prohibited = set(tiers["hard_prohibited_by_default"])
    assert core.isdisjoint(hard_prohibited)
    assert "silent_cloud_fallback" in hard_prohibited
    assert "unconsented_voice_cloning_or_impersonation" in hard_prohibited
    assert "raw_private_logs_or_paths_in_ui" in hard_prohibited


def test_core_has_no_large_download_or_private_export_default() -> None:
    core = _load_yaml(PROFILES_PATH)["profiles"]["core"]
    assert core["large_downloads_may_occur"] is False
    assert core["private_data_leaves_machine_by_default"] is False
    assert core["network"]["runtime_default"] == "disabled"


def test_local_override_example_contains_no_operator_absolute_path() -> None:
    text = OVERRIDES_EXAMPLE_PATH.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "/home/" not in text
    assert "ojiji" not in lowered
    assert "test_operator" not in lowered
    payload = _load_yaml(OVERRIDES_EXAMPLE_PATH)
    assert payload["policy"]["allow_runtime_network"] is False
    assert payload["policy"]["allow_private_memory_mounts"] is False
    assert payload["policy"]["allow_host_docker_socket"] is False
    assert payload["policy"]["allow_physical_hardware"] is False


def test_local_profile_selection_example_is_core_only_and_untracked_at_runtime() -> None:
    text = PROFILE_OVERRIDE_EXAMPLE_PATH.read_text(encoding="utf-8")
    payload = _load_yaml(PROFILE_OVERRIDE_EXAMPLE_PATH)
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert payload["active_profile"] == "core"
    assert payload["additional_profiles"] == []
    assert "/home/" not in text
    assert "config/install/local_profiles.yaml" in gitignore


def test_semantic_profile_lifecycle_is_pinned_loopback_and_uninstall_aware() -> None:
    manager = (ROOT / "scripts" / "manage_qdrant.sh").read_text(encoding="utf-8")
    uninstall = (ROOT / "scripts" / "uninstall_core.sh").read_text(encoding="utf-8")
    assert "127.0.0.1" in manager
    assert "0.0.0.0" not in manager
    assert "telemetry_disabled: true" in manager
    assert "api_key:" in manager
    assert "--restart=no" in manager
    assert "--read-only" in manager
    assert "--cap-drop=ALL" in manager
    assert "--security-opt=no-new-privileges" in manager
    assert "verify_container_contract" in manager
    assert "sha256:a0e04fe623cb064502cd869cefc1dc7ce359d8edd481063b5bd351c0a0a2c91e" in manager
    assert '"$SEMANTIC_MANAGER" uninstall' in uninstall


def test_neurofabric_profiles_have_isolated_owned_lifecycle_contracts() -> None:
    manager = (ROOT / "scripts" / "manage_neurofabric.sh").read_text(encoding="utf-8")
    installer = (ROOT / "scripts" / "install_core.sh").read_text(encoding="utf-8")
    uninstall = (ROOT / "scripts" / "uninstall_core.sh").read_text(encoding="utf-8")
    cpu = (REQUIREMENTS_ROOT / "neurofabric-cpu.txt").read_text(encoding="utf-8")
    cuda = (REQUIREMENTS_ROOT / "neurofabric-cuda.txt").read_text(encoding="utf-8")

    assert "elysia_neurofabric" in manager
    assert "elysia-neurofabric-environment-ownership-v2" in manager
    assert "user_data_present" in manager
    assert "install-cpu|install-cuda" in manager
    assert "--expect" in manager
    assert "config/install/locks/neurofabric-cpu-py312.lock.txt" in manager
    assert "config/install/locks/neurofabric-cuda-py312.lock.txt" in manager
    assert "--require-hashes" in manager
    assert "python=3.11" not in manager
    assert "python3.12" in manager
    assert "prove_neurofabric_runtime.py" in installer
    assert '"$NEUROFABRIC_MANAGER" uninstall' in uninstall
    assert "torch==2.13.0+cpu" in cpu
    assert "torch==2.13.0+cu130" in cuda
    assert "ncps==1.0.1" in cpu and "ncps==1.0.1" in cuda
