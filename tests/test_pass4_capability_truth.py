from __future__ import annotations

import asyncio

import httpx

from app.api.capability_service import get_capabilities_status
from app.api.main import create_app


def _capabilities() -> dict[str, dict[str, object]]:
    payload = get_capabilities_status()
    return {
        entry["capability_key"]: entry
        for entry in payload["data"]["capabilities"]
    }


def test_pass_1_through_4_surfaces_have_explicit_capability_truth() -> None:
    capabilities = _capabilities()

    expected_states = {
        "desktop_settings_preferences": "live",
        "governance_mutation_contract": "live",
        "install_profile_manifests": "live",
        "installer_doctor_readiness": "live",
        "addon_registry_management": "live",
        "addon_package_validation": "live",
        "addon_permission_resolution": "live",
        "developer_addon_package_preparation": "degraded",
        "marketplace_submission_review_contract": "degraded",
        "codev_official_addon_candidate": "live",
        "marketplace_catalog": "inactive",
        "local_sandbox_readiness": "planned",
        "external_boundary_governance": "live",
        "publish_queue_profile": "planned",
        "codev_developer_profile": "degraded",
        "parametricforge_lab": "inactive",
    }

    assert expected_states.keys() <= capabilities.keys()
    for capability_key, expected_state in expected_states.items():
        assert capabilities[capability_key]["state"] == expected_state
        assert capabilities[capability_key]["summary"]
        assert capabilities[capability_key]["ui_surfaces"]


def test_capability_truth_does_not_promote_profile_or_lab_authority() -> None:
    capabilities = _capabilities()

    profiles = capabilities["install_profile_manifests"]
    doctor = capabilities["installer_doctor_readiness"]
    sandbox = capabilities["local_sandbox_readiness"]
    publish = capabilities["publish_queue_profile"]
    parametric = capabilities["parametricforge_lab"]

    assert profiles["read_only"] is True
    assert profiles.get("supporting_endpoint") == "/status/profiles"
    assert doctor["read_only"] is True
    assert doctor.get("supporting_endpoint") == "/status/doctor"
    assert sandbox["read_only"] is True
    assert sandbox.get("supporting_endpoint") is None
    assert publish.get("supporting_endpoint") is None
    assert parametric["state"] == "inactive"

    combined_notes = " ".join(
        note
        for key in (
            "installer_doctor_readiness",
            "local_sandbox_readiness",
            "external_boundary_governance",
            "publish_queue_profile",
            "codev_developer_profile",
            "parametricforge_lab",
        )
        for note in capabilities[key]["notes"]
    )
    assert "No cloud sandbox is required" in combined_notes
    assert "No silent send or post is authorized" in combined_notes
    assert "arbitrary shell" in combined_notes.lower()
    assert "physical actuation authority" in combined_notes


def test_addon_capability_truth_matches_governed_nonexecuting_semantics() -> None:
    capabilities = _capabilities()
    addon = capabilities["addon_registry_management"]
    notes = " ".join(addon["notes"])

    assert addon["state"] == "live"
    assert addon["supporting_endpoint"] == "/addons/status"
    assert "does not execute add-on code" in notes
    assert "retains staged files" in notes

    permissions = capabilities["addon_permission_resolution"]
    assert permissions["state"] == "live"
    assert permissions["read_only"] is True
    assert "fail-closed intersection" in permissions["summary"]

    review = capabilities["marketplace_submission_review_contract"]
    assert review["state"] == "degraded"
    assert "Non-uploading" in review["summary"]

    codev = capabilities["codev_official_addon_candidate"]
    assert codev["state"] == "live"
    assert "canonical Elysia Ecobotics Marketplace distribution" in codev["summary"]
    assert "No silent shell" in " ".join(codev["notes"])


def test_capability_route_serves_pass4_truth_through_async_asgi() -> None:
    async def exercise_route() -> tuple[int, dict[str, object]]:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://elysia.local",
        ) as client:
            response = await client.get("/status/capabilities")
            return response.status_code, response.json()

    status_code, payload = asyncio.run(exercise_route())
    capabilities = {
        entry["capability_key"]: entry
        for entry in payload["data"]["capabilities"]
    }

    assert status_code == 200
    assert payload["status"] == "ok"
    assert capabilities["desktop_settings_preferences"]["state"] == "live"
    assert capabilities["publish_queue_profile"]["state"] == "planned"
