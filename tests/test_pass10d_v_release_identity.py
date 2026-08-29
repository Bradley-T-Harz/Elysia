from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
CODEV_VSIX_SHA256 = "5cbb9298e0d9f56797b95854e4cf07db84fe2d7fc00deb7bc3364d503451f6ff"


def test_release_identity_is_qualified_without_mutable_publication_state() -> None:
    identity = json.loads(
        (ROOT / "config/release/release_identity.json").read_text(encoding="utf-8")
    )
    assert identity["version"] == VERSION
    assert identity["semantic_tag"] == "v1.0.0"
    assert identity["channel"] == "stable"
    assert identity["qualification_state"] == "pass_10d_vi_qualified"
    assert identity["artifact_role"] == "official_v1_release_payload"
    assert identity["publication_state"] == {
        "live_state_source": "canonical_external_release_surfaces",
        "mutable_external_state_not_embedded": True,
        "owner_authorization_required_for_external_mutation": True,
        "canonical_release_url": "https://github.com/Bradley-T-Harz/Elysia/releases/tag/v1.0.0",
        "canonical_archive_url": "https://elysiaecobotics.com/archive",
    }
    assert "public_release" not in identity
    assert "tag_created" not in identity
    assert identity["source_repository"] == {
        "owner": "Bradley-T-Harz",
        "name": "Elysia",
        "url": "https://github.com/Bradley-T-Harz/Elysia",
        "issues_url": "https://github.com/Bradley-T-Harz/Elysia/issues",
    }
    assert identity["official_codev"]["version"] == VERSION
    assert identity["official_codev"]["vsix_sha256"] == CODEV_VSIX_SHA256
    assert identity["official_codev"]["vsix_size_bytes"] == 162207
    assert identity["official_codev"]["vsix_url"] == (
        "https://github.com/Bradley-T-Harz/elysia-codev/releases/download/"
        "v1.0.0/elysia-codev-1.0.0.vsix"
    )


def test_release_bearing_manifests_share_v1_identity() -> None:
    public = yaml.safe_load(
        (ROOT / "packaging/public_manifest.yaml").read_text(encoding="utf-8")
    )
    profiles = yaml.safe_load(
        (ROOT / "config/install/profiles.yaml").read_text(encoding="utf-8")
    )
    desktop = json.loads(
        (ROOT / "apps/elysia-desktop/package.json").read_text(encoding="utf-8")
    )
    tauri = json.loads(
        (ROOT / "apps/elysia-desktop/src-tauri/tauri.conf.json").read_text(
            encoding="utf-8"
        )
    )
    codev = json.loads(
        (ROOT / "config/addons/official_candidates.json").read_text(encoding="utf-8")
    )["candidates"][0]

    assert public["target_release"] == VERSION
    assert public["current_channel"] == "stable"
    assert public["publication"] == {
        "release_role": "qualified_public_release_payload",
        "live_state_source": "canonical_external_release_surfaces",
        "mutable_external_state_not_embedded": True,
        "owner_authorization_required_for_external_mutation": True,
        "canonical_release_url": "https://github.com/Bradley-T-Harz/Elysia/releases/tag/v1.0.0",
        "canonical_archive_url": "https://elysiaecobotics.com/archive",
    }
    assert profiles["target_product_version"] == VERSION
    assert profiles["current_channel"] == "stable"
    assert desktop["version"] == VERSION
    assert tauri["version"] == VERSION
    assert codev["version"] == VERSION
    assert codev["version_channel"] == "stable"
    assert codev["listing_state"] == "official_v1_release"
    assert codev["public_distribution_supported"] is True
    assert codev["in_app_install_control_live"] is False


def test_exact_codev_release_is_bound_into_install_manifests() -> None:
    graph = (ROOT / "config/install/component_graph.yaml").read_text(encoding="utf-8")
    acquisitions = (ROOT / "config/install/acquisition_manifests.yaml").read_text(
        encoding="utf-8"
    )
    assert CODEV_VSIX_SHA256 in graph
    assert CODEV_VSIX_SHA256 in acquisitions
    assert "ecosyneva-commons.elysia-codev@1.0.0" in acquisitions
    assert "exact_selected_vsix_digest_required" not in acquisitions


def test_package_bound_acquisitions_describe_release_payloads_not_candidates() -> None:
    acquisitions = yaml.safe_load(
        (ROOT / "config/install/acquisition_manifests.yaml").read_text(
            encoding="utf-8"
        )
    )
    package_bound = [
        item
        for item in acquisitions["components"].values()
        if item["method"] == "package_bound"
    ]
    assert package_bound
    for item in package_bound:
        assert item["source"] == "exact Elysia v1.0.0 release package"
        assert "candidate" not in item["digest"]
        assert "candidate" not in item["size_state"]
        assert "candidate" not in item["redistribution"]


def test_release_docs_keep_qualification_and_external_state_boundaries_explicit() -> None:
    release_notes = (ROOT / "docs/release/RELEASE_NOTES_v1.0.0.md").read_text(
        encoding="utf-8"
    )
    known = (ROOT / "docs/release/KNOWN_ISSUES_v1.0.0.md").read_text(
        encoding="utf-8"
    )
    assert "qualified stable Elysia v1.0.0 release" in release_notes
    assert "canonical GitHub Release and Elysia Archive" in release_notes
    assert "three distinct encrypted offline destinations" in known
    assert "Pond5 item 168538192 / U8" in known
    assert "absent from Elysia and Codev" in known
    for relative in (
        "docs/release/INSTALLER_DOCTOR_RUNTIME.md",
        "docs/release/INSTALL_UPDATE_ROLLBACK_UNINSTALL_v1.0.0.md",
        "docs/release/SYSTEM_REQUIREMENTS_v1.0.0.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "candidate manifest" not in text
        assert "candidate component/profile" not in text
        assert "Pass-IV artifacts remain unpublished" not in text
