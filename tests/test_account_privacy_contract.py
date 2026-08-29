from __future__ import annotations

from pathlib import Path

import pytest


yaml = pytest.importorskip("yaml")


PRIVACY_CONFIG = Path("config/policies/account_privacy.yaml")
COLOR_CONFIG = Path("config/ui/account_colors.yaml")
REQUIREMENTS = Path("requirements.txt")

EXPECTED_VISIBLE_FIELDS = {
    "name_or_username",
    "interests",
    "bio",
    "profile_photo_asset_id",
    "profile_photo_available",
}

EXPECTED_SEALED_FIELDS = {
    "password",
    "password_hash",
    "birthdate",
    "emails",
    "phone_number",
    "social_media",
    "github",
    "city_state",
    "session_token",
    "session_token_hash",
    "original_profile_photo_path",
}

EXPECTED_COLOR_LABELS = {
    "Meteor Rose",
    "Aurora Teal",
    "Volcanic Coral",
    "Stellar Indigo",
    "Vapor Mint",
    "Laser Lemon",
    "Blue Flame",
    "Magenta Comet",
    "Prismatic Amber",
    "Bioelectric Green",
}


def _load_yaml(path: Path) -> dict:
    assert path.exists(), f"Missing expected config file: {path}"
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert isinstance(data, dict)
    return data


def test_account_privacy_contract_loads_and_declares_explicit_field_sets():
    data = _load_yaml(PRIVACY_CONFIG)

    visible_fields = set(data.get("elysia_visible_fields") or [])
    sealed_fields = set(data.get("sealed_fields") or [])

    assert data["version"] == 1
    assert EXPECTED_VISIBLE_FIELDS.issubset(visible_fields)
    assert EXPECTED_SEALED_FIELDS.issubset(sealed_fields)
    assert visible_fields.isdisjoint(sealed_fields)


def test_account_privacy_contract_blocks_private_profile_from_runtime_tools_workers_and_memory():
    data = _load_yaml(PRIVACY_CONFIG)

    assert data["identity_store"]["normal_memory_store"] is False
    assert data["runtime_access"]["private_profile_allowed"] is False
    assert data["runtime_access"]["visible_projection_allowed"] is True
    assert data["tools_access"]["private_profile_allowed"] is False
    assert data["tools_access"]["visible_projection_allowed"] is False
    assert data["workers_access"]["private_profile_allowed"] is False
    assert data["workers_access"]["visible_projection_allowed"] is False
    assert data["memory_import"]["private_profile_allowed"] is False
    assert data["memory_import"]["visible_projection_allowed"] is False
    assert data["memory_import"]["automatic_memory_promotion_allowed"] is False


def test_account_privacy_projection_does_not_include_sealed_private_fields():
    data = _load_yaml(PRIVACY_CONFIG)
    projection = data["profile_projection"]["projected_fields"]

    assert set(projection) == set(data["elysia_visible_fields"])
    assert EXPECTED_SEALED_FIELDS.isdisjoint(set(projection))


def test_account_photo_and_password_rules_are_safe_by_default():
    data = _load_yaml(PRIVACY_CONFIG)

    assert data["passwords"]["plaintext_storage_allowed"] is False
    assert data["passwords"]["required_hashing_algorithm"] == "Argon2id"
    assert data["passwords"]["preferred_python_library"] == "pwdlib[argon2]"
    assert data["profile_photo"]["pdf_as_profile_photo_allowed"] is False
    assert data["profile_photo"]["store_original_path"] is False
    assert data["profile_photo"]["expose_original_path_to_runtime"] is False
    assert set(data["profile_photo"]["allowed_extensions"]) == {
        "jpg",
        "jpeg",
        "png",
        "webp",
    }


def test_account_colors_load_with_exactly_ten_allowed_choices():
    data = _load_yaml(COLOR_CONFIG)

    colors = data.get("colors")
    assert isinstance(colors, list)
    assert len(colors) == 10
    assert {color["label"] for color in colors} == EXPECTED_COLOR_LABELS
    assert len({color["id"] for color in colors}) == 10
    assert len({color["hex"] for color in colors}) == 10
    assert all(str(color["hex"]).startswith("#") for color in colors)
    assert data["rules"]["mutate_global_theme_tokens"] is False
    assert data["rules"]["page_local_only"] is True


def test_password_hashing_dependency_declares_argon2_pwdlib_support():
    assert REQUIREMENTS.exists()
    requirements = REQUIREMENTS.read_text(encoding="utf-8").splitlines()

    assert "pwdlib[argon2]" in {line.strip() for line in requirements}
