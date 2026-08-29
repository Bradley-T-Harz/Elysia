from __future__ import annotations

from app.api.capability_service import get_capabilities_status


def test_chunks_1_through_8_have_explicit_bounded_capability_truth() -> None:
    payload = get_capabilities_status()
    capabilities = {
        entry["capability_key"]: entry
        for entry in payload["data"]["capabilities"]
    }

    expected = {
        "coding_file_stewardship": "/coding/file-types",
        "document_stewardship": "/coding/document-types",
        "science_data_stewardship": "/coding/data-types",
        "visual_stewardship": "/coding/visual-types",
        "media_stewardship": "/coding/media/inspect",
        "archiveforge_stewardship": "/coding/archive/inspect",
        "databaseforge_stewardship": "/coding/database/inspect",
        "binaryforge_stewardship": "/coding/binary/inspect",
        "engineeringforge_stewardship": "/coding/engineering/types",
    }

    assert expected.keys() <= capabilities.keys()
    for capability_key, endpoint in expected.items():
        entry = capabilities[capability_key]
        assert entry["state"] in {"live", "degraded"}
        assert entry["locality"] == "local"
        assert entry["approval_state"] == "needed"
        assert entry["supporting_endpoint"] == endpoint
        assert "capabilities_room" in entry["ui_surfaces"]
        assert "codev" in entry["ui_surfaces"]


def test_database_and_engineering_capability_truth_preserves_hard_boundaries() -> None:
    payload = get_capabilities_status()
    capabilities = {
        entry["capability_key"]: entry
        for entry in payload["data"]["capabilities"]
    }

    data_notes = " ".join(capabilities["science_data_stewardship"]["notes"])
    engineering_notes = " ".join(capabilities["engineeringforge_stewardship"]["notes"])

    assert "row preview, arbitrary SQL, export, repair, and mutation are unavailable" in data_notes
    assert "Heavy worker handoffs remain disabled" in engineering_notes
    assert "ParametricForge remains experimental" in engineering_notes
    assert "robot actuation" in engineering_notes
    assert "unavailable by design" in engineering_notes
