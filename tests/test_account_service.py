from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sqlite3

import httpx
import pytest

import app.api.account_service as account_service
from app.api.account_service import AccountAuthError, AccountBlockedError, AccountPaths, AccountServiceError, AccountStore
from app.api.main import create_app
from app.api.schemas.account import (
    AccountCreateRequest,
    AccountDeleteRequest,
    AccountLoginRequest,
    AccountProfileArchiveExportRequest,
    AccountProfileArchiveRestoreRequest,
    AccountProfileUpdateRequest,
)
from app.install.local_auth import LocalApiAuthPolicy
from app.install.paths import RuntimeMode


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


def create_request(**overrides):
    data = {
        "username": "the operator",
        "password": "correct horse battery staple",
        "interests": "ecology, robotics",
        "bio": "Local-first builder.",
        "birthdate": "PRIVATE-BIRTHDATE",
        "emails": ["private_email_canary@example.com"],
        "phone_number": "555-PRIVATE-CANARY",
        "social_media": ["private-social"],
        "github": "github_private_canary",
        "city_state": "SecretCityStateCanary",
        "profile_color_id": "meteor_rose",
    }
    data.update(overrides)
    return AccountCreateRequest(**data)


def test_account_store_creates_user_hashes_password_and_hides_private_projection(tmp_path):
    store = make_store(tmp_path)
    profile = store.create_account(create_request())

    assert profile.username == "the operator"
    assert profile.emails == ["private_email_canary@example.com"]
    assert store.state().is_authenticated is True

    with store._connect() as conn:  # intentionally checking local sealed store internals
        row = conn.execute("SELECT password_hash FROM users").fetchone()
    assert row is not None
    assert row["password_hash"] != "correct horse battery staple"
    assert "correct horse" not in row["password_hash"]

    visible = store.visible_profile()
    assert visible is not None
    payload = visible.to_payload()
    assert payload == {
        "name_or_username": "the operator",
        "interests": "ecology, robotics",
        "bio": "Local-first builder.",
        "profile_photo_available": False,
    }
    combined = repr(payload)
    assert "private_email_canary@example.com" not in combined
    assert "555-PRIVATE-CANARY" not in combined
    assert "SecretCityStateCanary" not in combined
    assert "github_private_canary" not in combined
    assert "PRIVATE-BIRTHDATE" not in combined


def test_multi_account_creation_and_idempotent_retry(tmp_path):
    store = make_store(tmp_path)
    store.create_account(create_request())
    first_user_id = store.state().active_user_id

    store.create_account(create_request())
    assert store.state().active_user_id == first_user_id
    assert store.account_count() == 1

    store.create_account(
        create_request(
            username="Someone Else",
            password="second local account password",
            requested_role="user",
            managed_profile=True,
        )
    )
    # Installation governance creates an isolated account without silently
    # switching the Owner's active chamber session.
    assert store.state().active_user_id == first_user_id
    assert store.account_count() == 2
    assert store.state().multiple_accounts_available is True
    with store._connect() as conn:
        second = conn.execute(
            "SELECT local_role, managed FROM users WHERE username = ?",
            ("Someone Else",),
        ).fetchone()
    assert second["local_role"] == "user"
    assert second["managed"] == 1


def test_login_logout_and_session_persistence(tmp_path):
    store = make_store(tmp_path)
    store.create_account(create_request())
    store.logout()

    assert store.state().account_status == "logged_out"
    assert store.current_session() is None

    state = store.login(
        AccountLoginRequest(username="the operator", password="correct horse battery staple")
    )
    assert state.is_authenticated is True
    assert store.current_session() is not None

    reloaded = make_store(tmp_path)
    assert reloaded.state().is_authenticated is True

    reloaded.logout()
    assert make_store(tmp_path).state().is_authenticated is False


def test_invalid_login_is_rejected(tmp_path):
    store = make_store(tmp_path)
    store.create_account(create_request())
    store.logout()

    with pytest.raises(AccountAuthError):
        store.login(AccountLoginRequest(username="the operator", password="wrong"))
    with store._connect() as conn:
        event = conn.execute(
            "SELECT event_type, safe_details_json FROM account_events "
            "WHERE event_type = 'authentication_failed' ORDER BY created_at_utc DESC LIMIT 1"
        ).fetchone()
    assert event is not None
    assert json.loads(event["safe_details_json"]) == {
        "account_disabled": False,
        "credential_material_recorded": False,
        "known_local_profile": True,
    }


def test_profile_update_can_change_private_fields_without_leaking_projection(tmp_path):
    store = make_store(tmp_path)
    store.create_account(create_request())

    profile, password_changed = store.update_profile(
        AccountProfileUpdateRequest(
            bio="Updated safe bio",
            emails=["new_private_email@example.com"],
            phone_number="555-NEW-PRIVATE",
            github="new_private_github",
            city_state="New Secret City",
            current_password="correct horse battery staple",
            password="new secret password",
        )
    )

    assert password_changed is True
    assert profile.bio == "Updated safe bio"
    assert profile.emails == ["new_private_email@example.com"]
    visible = store.visible_profile()
    assert visible is not None
    combined = repr(visible.to_payload())
    assert "Updated safe bio" in combined
    assert "new_private_email@example.com" not in combined
    assert "555-NEW-PRIVATE" not in combined
    assert "new_private_github" not in combined
    assert "New Secret City" not in combined


def test_profile_photo_is_copied_to_identity_store_without_original_path(tmp_path):
    store = make_store(tmp_path)
    store.create_account(create_request())
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"\xff\xd8fake-jpg-content")

    asset = store.copy_profile_photo(source)

    assert asset.asset_id.startswith("profile_photo_")
    assert asset.extension == "jpg"
    assert (store.paths.profile_photo_dir / f"{asset.asset_id}.jpg").exists()
    assert str(source) not in repr(asset.to_payload())
    visible = store.visible_profile()
    assert visible is not None
    assert visible.profile_photo_asset_id == asset.asset_id
    assert visible.profile_photo_available is True

    preview_path, preview_mime_type = store.profile_photo_preview(asset.asset_id)
    assert preview_path == store.paths.profile_photo_dir / f"{asset.asset_id}.jpg"
    assert preview_path.exists()
    assert preview_mime_type == asset.mime_type
    assert str(source) not in str(preview_path)


def test_profile_photo_rejects_pdf_for_v1(tmp_path):
    store = make_store(tmp_path)
    store.create_account(create_request())
    source = tmp_path / "photo.pdf"
    source.write_bytes(b"%PDF private")

    with pytest.raises(AccountBlockedError):
        store.copy_profile_photo(source)


def test_profile_photo_preview_requires_current_asset_owner(tmp_path):
    store = make_store(tmp_path)
    store.create_account(create_request())
    source = tmp_path / "photo.png"
    source.write_bytes(b"fake-png-content")
    asset = store.copy_profile_photo(source)
    store.logout()

    with pytest.raises(AccountAuthError):
        store.profile_photo_preview(asset.asset_id)


def test_encrypted_profile_export_and_recovery_preserves_identity_boundary(tmp_path):
    store = make_store(tmp_path)
    store.create_account(create_request())
    source = tmp_path / "identity.png"
    source.write_bytes(b"synthetic-private-profile-photo")
    original_asset = store.copy_profile_photo(source)
    password = "correct horse battery staple"
    recovery = "synthetic archive recovery material"
    exported = store.export_profile_archive(AccountProfileArchiveExportRequest(
        current_password=password,
        recovery_material=recovery,
    ))
    assert exported["encrypted"] is True
    assert exported["memory_included"] is False
    assert exported["role_or_admin_authority_included"] is False
    assert "private_email_canary@example.com" not in exported["archive_base64"]

    store.update_profile(AccountProfileUpdateRequest(
        interests="changed",
        bio="changed",
        emails=["changed@example.test"],
    ))
    store.delete_profile_photo()
    with pytest.raises(AccountAuthError):
        store.restore_profile_archive(AccountProfileArchiveRestoreRequest(
            current_password=password,
            recovery_material="wrong recovery material",
            archive_base64=exported["archive_base64"],
            operator_confirmed=True,
        ))
    restored = store.restore_profile_archive(AccountProfileArchiveRestoreRequest(
        current_password=password,
        recovery_material=recovery,
        archive_base64=exported["archive_base64"],
        operator_confirmed=True,
    ))
    assert restored["restored"] is True
    assert restored["username_changed"] is False
    assert restored["password_changed"] is False
    assert restored["role_or_admin_authority_changed"] is False
    assert restored["memory_restored"] is False
    profile = store.private_profile()
    assert profile.interests == "ecology, robotics"
    assert profile.emails == ["private_email_canary@example.com"]
    assert profile.profile_photo_available is True
    assert profile.profile_photo is not None
    assert profile.profile_photo.sha256 == original_asset.sha256


def test_governed_account_deletion_removes_empty_identity_authority_and_photo(tmp_path):
    store = make_store(tmp_path)
    store.create_account(create_request())
    source = tmp_path / "photo.png"
    source.write_bytes(b"synthetic-photo")
    asset = store.copy_profile_photo(source)
    stored_photo = store.paths.profile_photo_dir / f"{asset.asset_id}.png"

    state, inventory, sessions_removed, assets_removed = store.delete_current_account(
        AccountDeleteRequest(
            current_password="correct horse battery staple",
            confirmation_username="the operator",
        )
    )

    assert inventory.blocking_owned_records == 0
    assert inventory.profile_photo_assets == 1
    assert sessions_removed == 1
    assert assets_removed == 1
    assert not stored_photo.exists()
    assert state.requires_user_creation is True
    assert state.account_count == 0
    assert store.current_session() is None
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    with sqlite3.connect(store.elysia_paths.memory_database_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_keys").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM memory_settings").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM memory_session_keys").fetchone()[0] == 0


def test_governed_account_deletion_requires_fresh_password_exact_name_and_empty_owned_state(tmp_path):
    store = make_store(tmp_path)
    store.create_account(create_request())

    with pytest.raises(AccountAuthError):
        store.delete_current_account(
            AccountDeleteRequest(
                current_password="wrong password",
                confirmation_username="the operator",
            )
        )
    with pytest.raises(AccountBlockedError, match="username exactly"):
        store.delete_current_account(
            AccountDeleteRequest(
                current_password="correct horse battery staple",
                confirmation_username="not the operator",
            )
        )

    owner = store.state().active_user_id
    assert owner
    store.elysia_paths.project_dir.mkdir(parents=True, exist_ok=True)
    (store.elysia_paths.project_dir / "owned.json").write_text(
        json.dumps({"owner_user_id": owner, "synthetic": True}), encoding="utf-8"
    )
    with pytest.raises(AccountBlockedError, match="still owns"):
        store.delete_current_account(
            AccountDeleteRequest(
                current_password="correct horse battery staple",
                confirmation_username="the operator",
            )
        )
    assert store.account_count() == 1


def test_operator_reset_requires_verified_preservation_and_refuses_owned_records(tmp_path):
    store = make_store(tmp_path)
    store.create_account(create_request())

    with pytest.raises(AccountBlockedError, match="preservation"):
        store.reset_all_accounts_after_verified_preservation(
            confirmation=account_service.OPERATOR_RESET_CONFIRMATION,
            preservation_verified=False,
        )
    with pytest.raises(AccountBlockedError, match="exact local reset"):
        store.reset_all_accounts_after_verified_preservation(
            confirmation="RESET SOME ACCOUNTS",
            preservation_verified=True,
        )

    result = store.reset_all_accounts_after_verified_preservation(
        confirmation=account_service.OPERATOR_RESET_CONFIRMATION,
        preservation_verified=True,
    )
    assert result == {
        "users_removed": 1,
        "sessions_removed": 1,
        "profile_assets_removed": 0,
    }
    assert store.state().requires_user_creation is True


def test_async_packaged_account_route_first_run_auth_cors_and_restart(monkeypatch, tmp_path):
    store = make_store(tmp_path)
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    local_credential = "synthetic-local-bridge-credential-000000000000"
    policy = LocalApiAuthPolicy(
        required=True,
        credential_path=tmp_path / "runtime-credential",
        runtime_mode=RuntimeMode.PACKAGED,
        source="packaged_test",
        expected_credential=local_credential,
    )
    app = create_app(auth_policy=policy)

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testclient",
        ) as client:
            preflight = await client.options(
                "/account/create",
                headers={
                    "Origin": "http://tauri.localhost",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization,content-type",
                },
            )
            denied = await client.post(
                "/account/create",
                json={"username": "packaged operator", "password": "packaged account password"},
            )
            created = await client.post(
                "/account/create",
                headers={"Authorization": f"Bearer {local_credential}"},
                json={"username": "packaged operator", "password": "packaged account password"},
            )
            retried = await client.post(
                "/account/create",
                headers={"Authorization": f"Bearer {local_credential}"},
                json={"username": "packaged operator", "password": "packaged account password"},
            )
            managed = await client.post(
                "/account/create",
                headers={"Authorization": f"Bearer {local_credential}"},
                json={
                    "username": "managed packaged user",
                    "password": "managed packaged account password",
                    "requested_role": "user",
                    "managed_profile": True,
                },
            )
            invalid = await client.post(
                "/account/create",
                headers={"Authorization": f"Bearer {local_credential}"},
                json={"username": "", "password": "short"},
            )
        return preflight, denied, created, retried, managed, invalid

    preflight, denied, created, retried, managed, invalid = asyncio.run(exercise())
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://tauri.localhost"
    assert denied.status_code == 401
    assert created.status_code == 200
    assert created.json()["status"] == "ok"
    assert created.json()["data"]["state"]["is_authenticated"] is True
    assert retried.status_code == 200
    assert managed.status_code == 200
    assert managed.json()["status"] == "ok"
    assert managed.json()["data"]["state"]["active_username"] == "packaged operator"
    assert store.account_count() == 2
    with store._connect() as conn:
        managed_row = conn.execute(
            "SELECT local_role, managed FROM users WHERE username = ?",
            ("managed packaged user",),
        ).fetchone()
    assert managed_row["local_role"] == "user"
    assert managed_row["managed"] == 1
    assert invalid.status_code == 422
    assert local_credential not in json.dumps(created.json())
    assert store.elysia_paths.memory_database_path.is_file()
    assert make_store(tmp_path).state().is_authenticated is True


def test_session_filesystem_failure_rolls_back_identity_and_memory_keys(monkeypatch, tmp_path):
    store = make_store(tmp_path)

    def fail_session(*_args, **_kwargs):
        raise AccountServiceError(
            "The private local account session could not be established."
        )

    monkeypatch.setattr(store, "_write_current_session", fail_session)
    with pytest.raises(AccountServiceError, match="could not be established"):
        store.create_account(
            AccountCreateRequest(
                username="permission proof",
                password="permission failure account password",
            )
        )
    assert store.account_count() == 0
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    with sqlite3.connect(store.elysia_paths.memory_database_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_keys").fetchone()[0] == 0


def test_memory_key_permission_failure_is_sanitized_and_leaves_no_partial_account(
    monkeypatch, tmp_path
):
    from app.memory.encryption_service import MemoryEncryptionService

    store = make_store(tmp_path)

    def fail_key_write(*_args, **_kwargs):
        raise PermissionError("SYNTHETIC_SECRET_KEY_PATH_SHOULD_NOT_ESCAPE")

    monkeypatch.setattr(MemoryEncryptionService, "provision_account", fail_key_write)
    with pytest.raises(AccountServiceError) as captured:
        store.create_account(
            AccountCreateRequest(
                username="key permission proof",
                password="key permission failure password",
            )
        )
    assert "private memory key could not be prepared" in str(captured.value)
    assert "SYNTHETIC_SECRET_KEY_PATH" not in str(captured.value)
    assert store.account_count() == 0
    assert store.current_session() is None
