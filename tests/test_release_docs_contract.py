from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = ROOT / "docs" / "release"

REQUIRED_DOCS = {
    "ELYSIA_V1_IMPLEMENTATION_PASS_PLAN.md",
    "ELYSIA_V1_PUBLIC_RELEASE_SCOPE.md",
    "INSTALL_PROFILES.md",
    "PUBLIC_PRIVATE_BOUNDARY.md",
    "CAPABILITY_RISK_TIERS.md",
    "LOCAL_SANDBOX_DOCTRINE.md",
    "V1_RELEASE_GATE.md",
    "UPGRADE_UNINSTALL.md",
    "RELEASE_NOTES_v1.0.0.md",
    "SYSTEM_REQUIREMENTS_v1.0.0.md",
    "INSTALL_UPDATE_ROLLBACK_UNINSTALL_v1.0.0.md",
    "KNOWN_ISSUES_v1.0.0.md",
}


def _text(name: str) -> str:
    return (RELEASE_ROOT / name).read_text(encoding="utf-8")


def test_required_release_documents_exist() -> None:
    assert REQUIRED_DOCS <= {path.name for path in RELEASE_ROOT.glob("*.md")}


def test_durable_pass_plan_covers_all_passes_and_future_reminder() -> None:
    text = _text("ELYSIA_V1_IMPLEMENTATION_PASS_PLAN.md")
    for pass_number in range(1, 11):
        assert f"Pass {pass_number}" in text
    assert "Read this file completely" in text
    assert "blocked by default" in text
    assert "never build" in text
    assert "Elysia and Codev commits separate" in text


def test_official_codev_sibling_path_is_canonical_and_consistent() -> None:
    canonical_path = "Add-ons/Official_Addons/elysia-codev"
    pass_plan = _text("ELYSIA_V1_IMPLEMENTATION_PASS_PLAN.md")
    approved_repos = (ROOT / "config" / "coder" / "approved_repos.yaml").read_text(
        encoding="utf-8"
    )

    assert canonical_path in pass_plan
    assert f"../{canonical_path}" in approved_repos
    legacy_codev_path = "Add-ons/" + "elysia-codev"
    assert legacy_codev_path not in pass_plan
    assert f"../{legacy_codev_path}" not in approved_repos


def test_public_scope_has_truthful_version_and_product_framing() -> None:
    text = _text("ELYSIA_V1_PUBLIC_RELEASE_SCOPE.md")
    assert "Target version: `1.0.0`" in text
    assert "Current channel: `stable`" in text
    assert "Qualification state: `Pass 10D VI qualified`" in text
    assert "mutable external state is not embedded" in text
    for phrase in (
        "local-first",
        "privacy-first",
        "governed",
        "installable",
        "auditable",
        "developer-friendly",
        "profile-aware",
        "add-on-capable",
        "not a ChatGPT clone",
        "not a Codex clone",
    ):
        assert phrase in text


def test_profile_document_names_every_profile_and_boundary() -> None:
    text = _text("INSTALL_PROFILES.md")
    for profile in (
        "Elysia Core",
        "Recommended Workstation",
        "Creator / AI Media",
        "Developer / Codev",
    ):
        assert profile in text
    assert "Core must not require" in text
    assert "Large downloads may occur only" in text
    assert "arbitrary shell" in text


def test_risk_tiers_preserve_governed_power_without_silent_defaults() -> None:
    text = _text("CAPABILITY_RISK_TIERS.md")
    for tier in (
        "Core v1 default",
        "Optional v1 profile",
        "v1 Lab / Developer-gated",
        "Hard-prohibited by default",
    ):
        assert tier in text
    for capability in (
        "Pursue Goal",
        "Heavy EngineeringForge",
        "ImageForge",
        "VideoForge",
        "Publish queue",
        "Add-on code execution",
        "Silent cloud fallback",
    ):
        assert capability in text


def test_local_sandbox_contract_is_local_and_deny_by_default() -> None:
    text = _text("LOCAL_SANDBOX_DOCTRINE.md")
    for phrase in (
        "No cloud sandbox is required",
        "No host Docker socket",
        "No private memory",
        "No network",
        "No physical hardware access",
        "explicit allowlisted",
        "operation/request receipt",
        "doctor must prove",
    ):
        assert phrase in text


def test_release_gate_requires_all_major_product_checks() -> None:
    text = _text("V1_RELEASE_GATE.md")
    for phrase in (
        "Broad safe backend regression",
        "TypeScript check",
        "Tauri `.deb` and AppImage",
        "Codev unit tests and full compile",
        "Extension Host review",
        "Local API authentication",
        "XDG config/data/cache/state/runtime",
        "Manual screenshots",
        "No push",
    ):
        assert phrase in text


def test_root_license_is_apache_2() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "Copyright 2026 EcoSyneva Commons LLC" in license_text
