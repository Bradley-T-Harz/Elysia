from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "config" / "release" / "protected_desktop_surfaces.json"
CAPABILITY_INVENTORY_PATH = (
    ROOT / "config" / "release" / "protected_desktop_capabilities.json"
)


def _inventory() -> list[dict[str, str]]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    assert payload["contract_version"] == 1
    return payload["surfaces"]


def test_protected_desktop_surface_inventory_is_complete_and_unique() -> None:
    surfaces = _inventory()
    ids = [surface["id"] for surface in surfaces]
    labels = [surface["label"] for surface in surfaces]

    assert len(surfaces) == 12
    assert len(ids) == len(set(ids))
    assert len(labels) == len(set(labels))
    assert set(ids) == {
        "home",
        "conversations",
        "projects",
        "artifacts",
        "requests",
        "memory",
        "user_profile",
        "governance",
        "capabilities",
        "addons",
        "health",
        "admin",
    }


def test_every_protected_surface_remains_navigable_and_rendered() -> None:
    preferences = (
        ROOT / "apps" / "elysia-desktop" / "src" / "desktopPreferences.ts"
    ).read_text(encoding="utf-8")
    rail = (ROOT / "apps" / "elysia-desktop" / "src" / "LeftRail.tsx").read_text(
        encoding="utf-8"
    )
    shell = (ROOT / "apps" / "elysia-desktop" / "src" / "AppShell.tsx").read_text(
        encoding="utf-8"
    )

    for surface in _inventory():
        room_id = surface["id"]
        label = surface["label"]
        component = surface["component"]

        if room_id != "admin":
            assert f'{{ id: "{room_id}", label: "{label}" }}' in preferences
        else:
            # Installation governance is intentionally role-gated and is not
            # a valid unauthenticated/default startup room.
            assert surface["visibility"] == "installation_owner_or_admin_only"
        assert f'room: "{room_id}"' in rail
        assert f'label: "{label}"' in rail
        assert component in shell
        if room_id != "home":
            assert f'activeRoom === "{room_id}"' in shell


def test_preservation_law_is_durable_release_documentation() -> None:
    contract = (
        ROOT / "docs" / "release" / "DESKTOP_SURFACE_PRESERVATION_CONTRACT.md"
    ).read_text(encoding="utf-8")

    assert "the operator's explicit approval **by surface name**" in contract
    assert "does not authorize hiding its room" in contract
    assert "protected_desktop_surfaces.json" in contract
    assert "protected_desktop_capabilities.json" in contract
    assert "real capability" in contract


def test_settings_inventory_and_established_capabilities_cannot_silently_disappear() -> None:
    payload = json.loads(CAPABILITY_INVENTORY_PATH.read_text(encoding="utf-8"))
    assert payload["contract_version"] == 1

    settings_source = (
        ROOT / "apps" / "elysia-desktop" / "src" / "SettingsPanel.tsx"
    ).read_text(encoding="utf-8")
    conversations_source = (
        ROOT / "apps" / "elysia-desktop" / "src" / "ConversationsPage.tsx"
    ).read_text(encoding="utf-8")
    bridge_source = (
        ROOT / "apps" / "elysia-desktop" / "src" / "api" / "bridgeClient.ts"
    ).read_text(encoding="utf-8")
    account_routes = (ROOT / "app" / "api" / "routes" / "account.py").read_text(
        encoding="utf-8"
    )
    research_routes = (ROOT / "app" / "api" / "routes" / "research.py").read_text(
        encoding="utf-8"
    )
    media_routes = (
        ROOT / "app" / "api" / "routes" / "media_workers.py"
    ).read_text(encoding="utf-8")
    project_workbench = (
        ROOT / "apps" / "elysia-desktop" / "src" / "ProjectWorkbenchPanel.tsx"
    ).read_text(encoding="utf-8")
    developer_profile_tests = (
        ROOT / "tests" / "test_codev_developer_profile.py"
    ).read_text(encoding="utf-8")
    cognition_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "app" / "cognition" / "governor.py",
            ROOT / "app" / "cognition" / "compute_governor.py",
            ROOT / "app" / "api" / "routes" / "cognition.py",
            ROOT / "apps" / "elysia-desktop" / "src" / "HealthPage.tsx",
            ROOT / "apps" / "elysia-desktop" / "src" / "AdminPage.tsx",
            ROOT / "apps" / "elysia-desktop" / "src" / "TopBar.tsx",
            ROOT / "config" / "install" / "dependency_catalog.yaml",
        )
    )

    labels = [item["label"] for item in payload["settings_surfaces"]]
    assert len(labels) == len(set(labels))
    active_setting_labels = {
        "Appearance",
        "Density",
        "Startup room",
        "Left-rail behavior",
        "Reduced motion",
        "Autonomy level",
        "Memory write preferences",
        "Memory recording",
        "Storage profile",
        "Default privacy",
        "Candidate behavior",
        "Internet master",
        "Reasoning effort",
        "Domain ceilings",
        "Compute preference",
        "Resource ceilings",
        "Background cognition",
    }
    for item in payload["settings_surfaces"]:
        if item["label"] in active_setting_labels:
            assert item["token"] in settings_source

    sources = "\n".join(
        [
            conversations_source,
            bridge_source,
            account_routes,
            research_routes,
            media_routes,
            project_workbench,
            developer_profile_tests,
            cognition_sources,
        ]
    )
    for capability in payload["established_capabilities"]:
        assert capability["backend_token"] in sources
        assert "removed_because_unfinished" not in capability["state"]
        assert "hidden_because_unfinished" not in capability["state"]

    prototype = payload["historical_ui_prototypes"][0]
    assert prototype["first_known_commit"].startswith("2b2e1cce")
    assert prototype["classification"] == (
        "prototype_controls_forward_ported_to_real_capabilities"
    )
    assert "real Project workbench workflows" in prototype["preservation_rule"]

    forbidden = set(payload["forbidden_final_states"])
    assert forbidden == {
        "removed_because_unfinished",
        "hidden_because_unfinished",
        "disabled_because_unfinished",
        "fake_live",
    }
