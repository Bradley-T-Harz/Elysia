from __future__ import annotations

from copy import deepcopy

import pytest

from app.install.component_graph_service import (
    COMPONENT_FIELDS,
    LOCAL_RELEASE_CAPABILITY_IDS,
    ComponentGraphError,
    load_component_graph,
    public_component_graph_summary,
    resolve_profile_components,
    validate_component_graph,
)


def test_authoritative_graph_has_every_profile_field_and_local_capability_owner() -> None:
    graph = load_component_graph()
    assert graph["authority"] == "authoritative"
    assert graph["release_target"] == "1.0.0"
    assert set(graph["profiles"]) == {
        "core",
        "workstation_research",
        "creator_perception",
        "developer_codev",
        "scientific_engineering_mega",
        "complete_v1_mega",
        "custom",
    }
    assert all(set(component) == COMPONENT_FIELDS for component in graph["components"].values())
    capabilities = {
        item
        for component in graph["components"].values()
        for item in component["capability_ids"]
    }
    assert capabilities == LOCAL_RELEASE_CAPABILITY_IDS


def test_profiles_resolve_through_one_graph_without_source_forks() -> None:
    core = resolve_profile_components("core")
    assert {"core_python_runtime", "desktop_shell", "identity_memory_fabric", "personal_onboarding"} <= set(core)
    developer = resolve_profile_components("developer_codev")
    assert set(core) <= set(developer)
    assert "codev_companion" in developer
    complete = resolve_profile_components("complete_v1_mega")
    assert {
        "creator_perception", "codev_companion", "scientific_engineering",
        "governed_research", "semantic_retrieval", "local_model_provider",
    } <= set(complete)
    summary = public_component_graph_summary()
    assert summary["source_forks"] is False
    assert summary["profile_selection_grants_operation_approval"] is False
    assert summary["raw_paths_exposed"] is False


def test_custom_rejects_unknown_components_and_cannot_remove_core() -> None:
    custom = resolve_profile_components("custom", custom_components=["codev_companion"])
    assert "identity_memory_fabric" in custom
    assert "codev_companion" in custom
    with pytest.raises(ComponentGraphError):
        resolve_profile_components("custom", custom_components=["arbitrary_shell"])


def test_graph_fails_closed_on_incomplete_component_or_capability_drift() -> None:
    graph = load_component_graph()
    incomplete = deepcopy(graph)
    incomplete["components"]["desktop_shell"].pop("uninstall_behavior")
    with pytest.raises(ComponentGraphError):
        validate_component_graph(incomplete)
    drift = deepcopy(graph)
    drift["components"]["core_python_runtime"]["capability_ids"].remove("ELY-INS-001")
    with pytest.raises(ComponentGraphError):
        validate_component_graph(drift)
