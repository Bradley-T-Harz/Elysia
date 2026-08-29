from __future__ import annotations

from pathlib import Path

import pytest

from app.api.account_service import AccountPaths, AccountStore
from app.api.marketplace_link_service import (
    MarketplaceLinkAuthError,
    MarketplaceLinkPaths,
    MarketplaceLinkStore,
)
from app.api.schemas.account import AccountCreateRequest
from app.api.schemas.marketplace import MarketplaceLinkRequest


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


def make_link_store(tmp_path: Path, account_store: AccountStore) -> MarketplaceLinkStore:
    identity_root = tmp_path / "identity"
    return MarketplaceLinkStore(
        MarketplaceLinkPaths(
            identity_root=identity_root,
            link_path=identity_root / "marketplace_link.json",
        ),
        account_store=account_store,
    )


def create_local_account(account_store: AccountStore) -> None:
    account_store.create_account(
        AccountCreateRequest(
            username="the operator",
            password="local-password-canary",
            interests="ecology",
            bio="local bio",
            birthdate="PRIVATE-BIRTHDATE",
            emails=["private@example.com"],
            phone_number="555-PRIVATE",
            social_media=["private-social"],
            github="private-github",
            city_state="Private City",
        )
    )


def test_marketplace_link_requires_local_auth(tmp_path):
    account_store = make_account_store(tmp_path)
    link_store = make_link_store(tmp_path, account_store)

    with pytest.raises(MarketplaceLinkAuthError):
        link_store.status()


def test_marketplace_link_stores_only_redacted_metadata(tmp_path):
    account_store = make_account_store(tmp_path)
    create_local_account(account_store)
    link_store = make_link_store(tmp_path, account_store)

    status = link_store.link(
        MarketplaceLinkRequest(
            marketplace_user_id="market-user-123",
            marketplace_email="builder@example.com",
            marketplace_username="market-builder",
            sync_enabled_fields=[
                "username",
                "bio",
                "birthdate",
                "supabase_access_token",
                "profile_photo_asset_reference",
            ],
        )
    )

    assert status.linked is True
    assert status.marketplace_email == "builder@example.com"
    assert status.sync_enabled_fields == []
    assert status.password_stored is False
    assert status.token_stored is False
    assert status.local_private_profile_shared is False
    assert status.runtime_access_allowed is False

    stored = (tmp_path / "identity" / "marketplace_link.json").read_text(encoding="utf-8")
    assert "market-user-123" in stored
    assert "builder@example.com" in stored
    assert "local-password-canary" not in stored
    assert "PRIVATE-BIRTHDATE" not in stored
    assert "private@example.com" not in stored
    assert "555-PRIVATE" not in stored
    assert "private-github" not in stored
    assert "supabase_access_token" not in stored


def test_marketplace_unlink_removes_local_metadata(tmp_path):
    account_store = make_account_store(tmp_path)
    create_local_account(account_store)
    link_store = make_link_store(tmp_path, account_store)
    link_store.link(
        MarketplaceLinkRequest(
            marketplace_user_id="market-user-123",
            marketplace_email="builder@example.com",
            marketplace_username="market-builder",
        )
    )

    status = link_store.unlink()

    assert status.linked is False
    assert not (tmp_path / "identity" / "marketplace_link.json").exists()
