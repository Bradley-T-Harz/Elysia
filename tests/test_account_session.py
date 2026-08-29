from __future__ import annotations

from pathlib import Path

from app.api.account_service import AccountPaths, AccountStore
from app.api.schemas.account import AccountCreateRequest


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


def test_current_session_file_controls_persistent_local_login(tmp_path):
    store = make_store(tmp_path)
    store.create_account(
        AccountCreateRequest(
            username="the operator",
            password="safe local password",
            interests="privacy",
            bio="local-first",
        )
    )

    assert store.paths.current_session_path.exists()
    assert make_store(tmp_path).state().is_authenticated is True

    store.paths.current_session_path.unlink()
    assert make_store(tmp_path).state().is_authenticated is False


def test_logout_revokes_stored_session_token(tmp_path):
    store = make_store(tmp_path)
    store.create_account(
        AccountCreateRequest(
            username="the operator",
            password="safe local password",
            interests="privacy",
            bio="local-first",
        )
    )
    session = store.current_session()
    assert session is not None

    store.logout()

    assert store.current_session() is None
    with store._connect() as conn:
        row = conn.execute(
            "SELECT revoked_at_utc, revocation_reason FROM sessions WHERE id = ?",
            (session["session_id"],),
        ).fetchone()
    assert row is not None
    assert row["revoked_at_utc"]
    assert row["revocation_reason"] == "user_logout"
