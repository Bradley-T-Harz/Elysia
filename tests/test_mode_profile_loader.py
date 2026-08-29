from __future__ import annotations

from pathlib import Path

from core.mode_profile_loader import (
    EXPECTED_MODE_KEYS,
    load_mode_profiles,
    resolve_mode_profile,
)


def test_loads_expected_mode_profiles_from_config():
    profiles = load_mode_profiles()

    assert tuple(profiles.keys()) == EXPECTED_MODE_KEYS
    assert profiles["tutor"].label == "Tutor"
    assert profiles["tutor"].math_execution_preference == "high"
    assert profiles["researcher"].citation_strictness == "mandatory_for_web"
    assert profiles["coder"].repo_context_preference == "high"


def test_mode_profiles_never_grant_authority():
    profiles = load_mode_profiles()

    for profile in profiles.values():
        payload = profile.to_payload()
        assert profile.authority_granted_by_mode is False
        assert payload["authority_granted_by_mode"] is False
        assert "shell_execution_allowed" not in payload
        assert "patch_application_allowed" not in payload


def test_unknown_mode_falls_back_to_default_with_warning():
    profile = resolve_mode_profile("time_lord")

    assert profile.key == "default"
    assert profile.authority_granted_by_mode is False
    assert any("Unknown mode profile" in warning for warning in profile.warnings)


def test_missing_optional_fields_use_safe_defaults(tmp_path: Path):
    config = tmp_path / "mode_profiles.yaml"
    config.write_text(
        """
version: 1
modes:
  default:
    label: Default
  tutor:
    label: Tutor
  researcher:
    label: Researcher
  writer:
    label: Writer
  coder:
    label: Coder
""",
        encoding="utf-8",
    )

    profiles = load_mode_profiles(config)

    assert profiles["default"].response_style == "balanced"
    assert profiles["default"].web_research_preference == "explicit_only"
    assert profiles["coder"].authority_granted_by_mode is False


def test_malformed_config_does_not_crash(tmp_path: Path):
    config = tmp_path / "mode_profiles.yaml"
    config.write_text("modes: [not, a, mapping]", encoding="utf-8")

    profiles = load_mode_profiles(config)

    assert profiles["default"].key == "default"
    assert profiles["default"].authority_granted_by_mode is False
