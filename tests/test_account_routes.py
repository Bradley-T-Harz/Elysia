from __future__ import annotations

import asyncio
from pathlib import Path

import app.api.account_service as account_service
from app.api.account_service import AccountPaths, AccountStore
from app.api.routes import account as account_routes
from app.api.schemas.account import AccountCreateRequest, AccountLoginRequest
from fastapi.responses import FileResponse


def run_async(coro):
    return asyncio.run(coro)


def make_store(tmp_path: Path) -> AccountStore:
    identity_root = tmp_path / "identity"
    return AccountStore(
        AccountPaths(
            identity_root=identity_root,
            database_path=identity_root / "elysia_identity.sqlite",
            profile_photo_dir=identity_root / "profile_photos",
            current_session_path=identity_root / "current_session.json",
        )
    )


def patch_store(tmp_path: Path, monkeypatch) -> AccountStore:
    store = make_store(tmp_path)
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    return store


def create_payload() -> AccountCreateRequest:
    return AccountCreateRequest(
        username="the operator",
        password="correct horse battery staple",
        interests="ecology",
        bio="builder",
        birthdate="PRIVATE-BIRTHDATE",
        emails=["private_email_canary@example.com"],
        phone_number="555-PRIVATE-CANARY",
        social_media=["private-social"],
        github="github_private_canary",
        city_state="SecretCityStateCanary",
        profile_color_id="meteor_rose",
    )


def test_account_state_create_visible_profile_and_logout_routes(tmp_path, monkeypatch):
    patch_store(tmp_path, monkeypatch)

    state = run_async(account_routes.get_account_state())
    assert state["data"]["has_user"] is False
    assert state["data"]["requires_user_creation"] is True

    created = run_async(account_routes.create_account(create_payload()))
    assert created["status"] == "ok"
    assert created["data"]["state"]["is_authenticated"] is True
    assert "password_hash" not in repr(created)

    profile = run_async(account_routes.get_profile())
    assert profile["status"] == "ok"
    assert profile["data"]["profile"]["emails"] == ["private_email_canary@example.com"]
    assert "password_hash" not in repr(profile)

    visible = run_async(account_routes.get_elysia_visible_profile())
    assert visible["status"] == "ok"
    visible_text = repr(visible["data"]["profile"])
    assert "the operator" in visible_text
    assert "private_email_canary@example.com" not in visible_text
    assert "555-PRIVATE-CANARY" not in visible_text
    assert "github_private_canary" not in visible_text
    assert "SecretCityStateCanary" not in visible_text

    logged_out = run_async(account_routes.logout())
    assert logged_out["status"] == "ok"
    assert logged_out["data"]["state"]["requires_login"] is True


def test_account_profile_requires_session_and_login_restores_it(tmp_path, monkeypatch):
    patch_store(tmp_path, monkeypatch)
    run_async(account_routes.create_account(create_payload()))
    run_async(account_routes.logout())

    blocked = run_async(account_routes.get_profile())
    assert blocked["status"] == "blocked"

    login = run_async(
        account_routes.login(
            AccountLoginRequest(
                username="the operator",
                password="correct horse battery staple",
            )
        )
    )
    assert login["status"] == "ok"
    assert login["data"]["state"]["is_authenticated"] is True

    profile = run_async(account_routes.get_profile())
    assert profile["status"] == "ok"


def test_account_color_and_privacy_routes(tmp_path, monkeypatch):
    patch_store(tmp_path, monkeypatch)

    colors = run_async(account_routes.get_account_colors())
    assert colors["status"] == "ok"
    assert len(colors["data"]["colors"]) == 10

    privacy = run_async(account_routes.get_account_privacy())
    assert privacy["status"] == "ok"
    assert "password_hash" in privacy["data"]["privacy"]["sealed_fields"]
    assert "bio" in privacy["data"]["privacy"]["elysia_visible_fields"]


def test_profile_photo_preview_route_returns_file_without_original_path(tmp_path, monkeypatch):
    store = patch_store(tmp_path, monkeypatch)
    run_async(account_routes.create_account(create_payload()))
    source = tmp_path / "profile.webp"
    source.write_bytes(b"fake-webp-content")

    selected = run_async(
        account_routes.select_profile_photo(
            account_routes.ProfilePhotoSelectRequest(source_path=str(source))
        )
    )
    asset_id = selected["data"]["profile_photo"]["asset_id"]

    response = run_async(account_routes.preview_profile_photo(asset_id))

    assert isinstance(response, FileResponse)
    assert response.media_type == "image/webp"
    assert asset_id in str(response.path)
    assert str(source) not in str(response.path)
    assert str(source) not in repr(selected)
