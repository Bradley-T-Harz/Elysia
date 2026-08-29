from __future__ import annotations

import asyncio
from pathlib import Path

import app.api.account_service as account_service
import app.api.marketplace_link_service as marketplace_link_service
from app.api.account_service import AccountPaths, AccountStore
from app.api.marketplace_link_service import MarketplaceLinkPaths, MarketplaceLinkStore
from app.api.routes import account as account_routes
from app.api.routes import marketplace as marketplace_routes
from app.api.schemas.account import AccountCreateRequest
from app.api.schemas.marketplace import MarketplaceLinkRequest, MarketplaceProfileSyncRecordRequest


def run_async(coro):
    return asyncio.run(coro)


def make_account_store(tmp_path: Path) -> AccountStore:
    identity_root = tmp_path / "identity"
    return AccountStore(
        AccountPaths(
            identity_root=identity_root,
            database_path=identity_root / "elysia_identity.sqlite",
            profile_photo_dir=identity_root / "profile_photos",
            current_session_path=identity_root / "current_session.json",
        )
    )


def patch_stores(tmp_path: Path, monkeypatch) -> None:
    account_store = make_account_store(tmp_path)
    link_store = MarketplaceLinkStore(
        MarketplaceLinkPaths(
            identity_root=tmp_path / "identity",
            link_path=tmp_path / "identity" / "marketplace_link.json",
        ),
        account_store=account_store,
    )
    monkeypatch.setattr(account_service, "_default_store", lambda: account_store)
    monkeypatch.setattr(marketplace_link_service, "_default_store", lambda: link_store)


def create_payload() -> AccountCreateRequest:
    return AccountCreateRequest(
        username="the operator",
        password="local-password-canary",
        interests="ecology",
        bio="builder",
        birthdate="PRIVATE-BIRTHDATE",
        emails=["private@example.com"],
        phone_number="555-PRIVATE",
        social_media=["private-social"],
        github="private-github",
        city_state="Private City",
    )


def test_marketplace_routes_require_local_account_session(tmp_path, monkeypatch):
    patch_stores(tmp_path, monkeypatch)

    response = run_async(marketplace_routes.get_marketplace_link_status())

    assert response["status"] == "blocked"
    assert response["data"]["marketplace_password_received"] is False
    assert response["data"]["marketplace_tokens_received"] is False


def test_marketplace_link_routes_return_redacted_status(tmp_path, monkeypatch):
    patch_stores(tmp_path, monkeypatch)
    run_async(account_routes.create_account(create_payload()))

    linked = run_async(
        marketplace_routes.link_marketplace_account(
            MarketplaceLinkRequest(
                marketplace_user_id="market-user-123",
                marketplace_email="builder@example.com",
                marketplace_username="market-builder",
                sync_enabled_fields=["username", "bio", "birthdate"],
            )
        )
    )

    assert linked["status"] == "ok"
    status = linked["data"]["marketplace_link"]
    assert status["linked"] is True
    assert status["marketplace_email"] == "builder@example.com"
    assert status["sync_enabled_fields"] == []
    assert status["password_stored"] is False
    assert status["token_stored"] is False
    assert status["local_private_profile_shared"] is False
    assert status["runtime_access_allowed"] is False

    serialized = repr(linked)
    assert "local-password-canary" not in serialized
    assert "PRIVATE-BIRTHDATE" not in serialized
    assert "private@example.com" not in serialized
    assert "555-PRIVATE" not in serialized
    assert "private-github" not in serialized
    assert "builder@example.com" in serialized

    visible = run_async(account_routes.get_elysia_visible_profile())
    assert visible["status"] == "ok"
    visible_text = repr(visible["data"]["profile"])
    assert "builder@example.com" not in visible_text
    assert "market-builder" not in visible_text
    assert "market-user-123" not in visible_text

    unlinked = run_async(marketplace_routes.unlink_marketplace_account())
    assert unlinked["status"] == "ok"
    assert unlinked["data"]["marketplace_link"]["linked"] is False


def test_marketplace_profile_sync_route_records_field_names_only(tmp_path, monkeypatch):
    patch_stores(tmp_path, monkeypatch)
    run_async(account_routes.create_account(create_payload()))
    run_async(
        marketplace_routes.link_marketplace_account(
            MarketplaceLinkRequest(
                marketplace_user_id="market-user-123",
                marketplace_email="builder@example.com",
                marketplace_username="market-builder",
            )
        )
    )

    response = run_async(
        marketplace_routes.record_marketplace_profile_sync(
            MarketplaceProfileSyncRecordRequest(
                fields_synced=[
                    "username",
                    "display_name",
                    "bio",
                    "interests",
                    "birthdate",
                    "supabase_access_token",
                ],
            )
        )
    )

    assert response["status"] == "ok"
    record = response["data"]["profile_sync"]
    assert record["fields_synced"] == []
    assert record["raw_values_stored"] is False
    assert record["marketplace_token_received"] is False
    assert record["marketplace_password_received"] is False
    assert record["local_private_fields_synced"] is False
    serialized = repr(response)
    assert "PRIVATE-BIRTHDATE" not in serialized
    assert "local-password-canary" not in serialized
    assert "supabase_access_token" not in serialized
