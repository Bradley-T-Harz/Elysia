from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = ROOT / "docs" / "release" / "PUBLIC_PRIVATE_BOUNDARY.md"
UPGRADE = ROOT / "docs" / "release" / "UPGRADE_UNINSTALL.md"
GITIGNORE = ROOT / ".gitignore"


def test_public_private_boundary_names_required_exclusions() -> None:
    text = BOUNDARY.read_text(encoding="utf-8")
    for phrase in (
        "private memory",
        "personal journals",
        ".env",
        "keys, tokens, credentials",
        "vault contents",
        "identity databases",
        "local runtime databases",
        "machine-specific config",
        "local absolute paths",
        "downloaded model weights",
    ):
        assert phrase in text


def test_public_private_boundary_defines_xdg_roots_and_sanitized_ui() -> None:
    text = BOUNDARY.read_text(encoding="utf-8")
    for variable in (
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "XDG_RUNTIME_DIR",
    ):
        assert variable in text
    assert "Normal UI must not expose raw private paths" in text
    assert "gitignored local configuration" in text
    assert "source checkout is not a production data directory" in text


def test_repo_local_override_names_are_ignored_while_example_is_tracked() -> None:
    gitignore = GITIGNORE.read_text(encoding="utf-8")
    assert "config/models/local_overrides.yaml" in gitignore
    assert "config/install/local_profiles.yaml" in gitignore
    assert "local_overrides.example.yaml" not in gitignore


def test_upgrade_and_uninstall_preserve_user_data_by_default() -> None:
    text = UPGRADE.read_text(encoding="utf-8")
    assert "Upgrades preserve local config and data by default" in text
    assert "User data remains by default" in text
    assert "separate explicit action" in text
    assert "never deleted by uninstall" in text
    assert "must not silently delete local user data" in text
