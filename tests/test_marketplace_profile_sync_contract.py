from __future__ import annotations

import json
from pathlib import Path

from app.api.account_service import AccountPaths, AccountStore
from app.api.marketplace_link_service import MarketplaceLinkPaths, MarketplaceLinkStore
from app.api.schemas.account import AccountCreateRequest
from app.api.schemas.marketplace import MarketplaceLinkRequest, MarketplaceProfileSyncRecordRequest


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
            interests="ecosystems",
            bio="local public bio",
            birthdate="PRIVATE-BIRTHDATE",
            emails=["private@example.com"],
            phone_number="555-PRIVATE",
            social_media=["private-social"],
            github="private-github",
            city_state="Private City",
        )
    )


def test_marketplace_profile_sync_record_stores_field_names_only(tmp_path):
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

    record = link_store.record_profile_sync(
        MarketplaceProfileSyncRecordRequest(
            direction="local_to_marketplace",
            fields_synced=[
                "username",
                "bio",
                "interests",
                "birthdate",
                "supabase_access_token",
            ],
        )
    )

    assert record.recorded is True
    assert record.fields_synced == []
    assert record.raw_values_stored is False
    assert record.marketplace_token_received is False
    assert record.marketplace_password_received is False
    assert record.local_private_fields_synced is False

    stored = (tmp_path / "identity" / "marketplace_link.json").read_text(encoding="utf-8")
    payload = json.loads(stored)
    assert payload["sync_enabled_fields"] == []
    assert payload["marketplace_username"] == "market-builder"
    for forbidden_key in ("username", "bio", "interests", "birthdate", "supabase_access_token"):
        assert forbidden_key not in payload
    for forbidden_value in (
        "local public bio",
        "PRIVATE-BIRTHDATE",
        "private@example.com",
        "local-password-canary",
    ):
        assert forbidden_value not in stored
