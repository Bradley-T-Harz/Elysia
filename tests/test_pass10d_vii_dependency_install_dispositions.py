from __future__ import annotations

import yaml

from app.install.component_graph_service import resolve_profile_components
from app.install.dependency_service import validate_dependency_catalog
from app.install.dependency_disposition_service import (
    CATALOG_PATH,
    complete_dependency_install_summary,
    dependency_install_summary,
    external_prerequisite_guidance,
    load_dependency_install_dispositions,
)


def test_every_release_dependency_has_exactly_one_install_disposition() -> None:
    summary = complete_dependency_install_summary()
    payload = load_dependency_install_dispositions()
    catalog = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    validate_dependency_catalog(catalog)
    assert summary["contract_version"] == (
        "elysia-dependency-install-dispositions-1.0"
    )
    assert summary["system_dependency_count"] == 20
    assert summary["system_category_counts"] == {
        "A": 0,
        "B": 0,
        "C": 16,
        "D": 1,
        "E": 3,
    }
    assert summary["category_counts"] == {
        "A": 16,
        "B": 39,
        "C": 5,
        "D": 4,
        "E": 4,
    }
    assert summary["dependency_count"] == len(summary["dependencies"])
    assert sum(summary["category_counts"].values()) == summary["dependency_count"]
    assert {row["setup_category"] for row in summary["dependencies"]} <= {
        "A", "B", "C", "D", "E"
    }
    assert summary["system_only_guidance"]["optional_supported_nvidia_driver"][
        "category"
    ] == "E"
    assert payload["contributor_only_dependency_ids"] == [
        "pytest", "httpx", "nodejs_npm", "rust_cargo",
    ]
    mapped = {
        dependency_id
        for values in payload["component_dependency_ids"].values()
        for dependency_id in values
    }
    assert mapped == set(catalog["dependencies"]) - set(
        payload["contributor_only_dependency_ids"]
    )


def test_complete_profile_owns_every_runtime_dependency_and_selects_one_science_variant() -> None:
    components = resolve_profile_components("complete_v1_mega")
    cpu = dependency_install_summary(components, scientific_variant="cpu")
    cuda = dependency_install_summary(components, scientific_variant="cuda")
    cpu_ids = {row["dependency_id"] for row in cpu["dependencies"]}
    cuda_ids = {row["dependency_id"] for row in cuda["dependencies"]}
    assert "searxng_loopback_service" in cpu_ids
    assert "codev_vsix" in cpu_ids
    assert "ollama_local_provider" in cpu_ids
    assert "neurofabric_torch_cpu" in cpu_ids
    assert "neurofabric_torch_cuda" not in cpu_ids
    assert "neurofabric_torch_cuda" in cuda_ids
    assert "neurofabric_torch_cpu" not in cuda_ids
    assert cpu["category_e_actions"] == []
    assert {
        row["dependency_id"]
        for row in cpu["dependencies"]
        if row["setup_category"] == "D"
    } == {"ollama_local_provider", "vscode", "codev_core", "codev_vsix"}
    action_groups = {
        row["dependency_id"]: row
        for row in cpu["system_category_e_actions"]
    }
    assert set(action_groups) == {
        "ollama_local_provider",
        "optional_supported_nvidia_driver",
    }
    assert action_groups["ollama_local_provider"]["dependency_ids"] == [
        "ollama", "ollama_optional",
    ]


def test_core_stays_small_and_has_no_category_e_manual_requirement() -> None:
    summary = dependency_install_summary(resolve_profile_components("core"))
    assert summary["category_counts"] == {
        "A": 16,
        "B": 0,
        "C": 0,
        "D": 0,
        "E": 0,
    }
    assert summary["category_e_actions"] == []
    bundled = {row["dependency_id"] for row in summary["dependencies"]}
    # Symbolic math and dimensional validation are existing Core capabilities;
    # optional native domain engines must not enter the bundled Core implicitly.
    assert {"sympy", "pint"} <= bundled
    assert not {"scipy", "rdkit", "cantera", "highspy", "ortools"} & bundled


def test_external_prerequisites_have_complete_public_guidance() -> None:
    for dependency_id in ("ollama", "ollama_optional"):
        guidance = external_prerequisite_guidance(dependency_id)
        assert guidance is not None
        assert guidance["setup_category"] == "E"
        assert guidance["official_source"].startswith("https://")
        assert guidance["supported_steps"]
        assert guidance["doctor_detection"]
        assert guidance["retry_repair"]
    assert external_prerequisite_guidance("vscode") is None
    assert load_dependency_install_dispositions()["category_e_guidance"]["vscode"]["supported_steps"]
