from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "docs" / "release"
DOCTRINE = RELEASE / "ADDON_DEVELOPER_FORGE_MARKETPLACE_DOCTRINE.md"
WARNINGS = RELEASE / "MARKETPLACE_ADDON_WARNINGS_AND_TERMS_DRAFT.md"
SUBMISSION = RELEASE / "DEVELOPER_ADDON_SUBMISSION_RULES_DRAFT.md"
CLEANUP = RELEASE / "MARKETPLACE_CLEANUP_TASK_CONTRACT.md"
PLAN = RELEASE / "ELYSIA_V1_IMPLEMENTATION_PASS_PLAN.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(path: Path) -> str:
    return " ".join(_text(path).split())


def test_pass7_canonical_doctrine_and_drafts_exist() -> None:
    for path in (DOCTRINE, WARNINGS, SUBMISSION, CLEANUP):
        assert path.is_file()
    assert "ADDON_DEVELOPER_FORGE_MARKETPLACE_DOCTRINE.md" in _text(PLAN)


def test_doctrine_preserves_governed_power_and_core_boundary() -> None:
    text = _flat(DOCTRINE).lower()
    for phrase in (
        "add-ons do not enter elysia's bloodstream",
        "blocked by default",
        "never build",
        "elysia core must not import arbitrary add-on modules directly",
        "no cloud or paid sandbox is required",
        "never fall back to direct host execution",
    ):
        assert phrase in text


def test_manifest_and_static_intake_contract_are_unambiguous() -> None:
    text = _flat(DOCTRINE).lower()
    assert "canonical manifest is `manifest.json`" in text
    assert "`.elysia-addon`" in text
    assert "does not execute uploaded code" in text
    for risk in (
        "path traversal",
        "symlinks",
        "`.env`",
        "secret",
        "private-path",
        "suspicious binary",
        "archive-depth",
        "license/provenance",
        "checksum",
    ):
        assert risk in text


def test_lifecycle_states_never_imply_authority() -> None:
    text = _flat(DOCTRINE).lower()
    for phrase in (
        "submitted does not mean approved",
        "approved does not mean installed",
        "installed does not mean enabled",
        "enabled does not mean unrestricted",
        "permission granted does not mean broad authority",
        "admin-reviewed does not mean guaranteed safe",
        "`installed_disabled`",
        "`enabled_limited`",
        "`revoked`",
    ):
        assert phrase in text


def test_external_submission_discloses_that_files_leave_the_machine() -> None:
    doctrine = _flat(DOCTRINE).lower()
    warnings = _flat(WARNINGS).lower()
    submission = _flat(SUBMISSION).lower()
    assert "files you select will leave your computer" in doctrine
    assert "files you select will leave your computer" in warnings
    assert "leave the local computer" in submission
    for text in (doctrine, submission):
        assert "does not silently connect" in text
        assert "data-flow" in text or "data flows" in text


def test_admin_review_and_marketplace_cleanup_fail_closed() -> None:
    text = _flat(DOCTRINE).lower()
    for phrase in (
        "exact package/repository hash",
        "reviewer/admin identity",
        "admin-reviewed does not mean guaranteed safe",
        "separate website task",
        "exact row IDs",
        "dry-run hide/delete plan",
        "release-owner/admin approval",
    ):
        assert phrase.lower() in text
    cleanup = _flat(CLEANUP).lower()
    for phrase in (
        "exact row ids",
        "dry-run",
        "release-owner/admin approval",
        "do not mutate unrelated",
        "official draft",
    ):
        assert phrase in cleanup


def test_codev_install_truth_requires_the_verified_developer_profile() -> None:
    text = _flat(DOCTRINE).lower()
    assert "codev is the first official add-on" in text
    assert "developer-profile installation path is real and verified" in text
    assert "only when the exact reviewed package" in text
    assert "never grants silent local installation authority" in text


def test_terms_and_submission_rules_require_review_without_enabling_features() -> None:
    warnings = _flat(WARNINGS).lower()
    submission = _flat(SUBMISSION).lower()
    for text in (warnings, submission):
        assert "attorney review is required" in text
        assert "must not execute" in text or "does not itself enable" in text
    assert "installed does not mean enabled" in warnings
    assert "new version or changed hash requires a new review" in submission


def test_doctrine_contains_no_machine_specific_home_or_repo_path() -> None:
    for path in (DOCTRINE, WARNINGS, SUBMISSION, CLEANUP):
        text = _text(path)
        assert "/home/" not in text
        private_workspace_marker = "MAIN" + "_Projects"
        assert private_workspace_marker not in text
