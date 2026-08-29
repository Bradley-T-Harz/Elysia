from __future__ import annotations

from pathlib import Path

import app.api.account_service as account_service
from app.api.account_service import AccountPaths, AccountStore
from app.cli import account_commands


def _make_store(tmp_path: Path) -> AccountStore:
    identity_root = tmp_path / "identity"
    return AccountStore(
        AccountPaths(
            identity_root=identity_root,
            database_path=identity_root / "elysia_identity.sqlite",
            profile_photo_dir=identity_root / "profile_photos",
            current_session_path=identity_root / "current_session.json",
        )
    )


def test_account_cli_create_visible_profile_and_logout(tmp_path, monkeypatch, capsys):
    store = _make_store(tmp_path)
    monkeypatch.setattr(account_service, "_default_store", lambda: store)

    assert account_commands.main(
        [
            "create",
            "--username",
            "the operator",
            "--password",
            "safe local password",
            "--interests",
            "ecology",
            "--bio",
            "local-first",
            "--emails",
            "private_email_canary@example.com",
            "--phone-number",
            "555-PRIVATE-CANARY",
            "--github",
            "github_private_canary",
            "--city-state",
            "SecretCityStateCanary",
        ]
    ) == 0
    create_output = capsys.readouterr().out
    assert "password_hash" not in create_output
    assert "safe local password" not in create_output

    assert account_commands.main(["visible-profile"]) == 0
    visible_output = capsys.readouterr().out
    assert "the operator" in visible_output
    assert "ecology" in visible_output
    assert "private_email_canary@example.com" not in visible_output
    assert "555-PRIVATE-CANARY" not in visible_output
    assert "github_private_canary" not in visible_output
    assert "SecretCityStateCanary" not in visible_output

    assert account_commands.main(["logout"]) == 0
    logout_output = capsys.readouterr().out
    assert "session_token" not in logout_output
    assert "password_hash" not in logout_output
