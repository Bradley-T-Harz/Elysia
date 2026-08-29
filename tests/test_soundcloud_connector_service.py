from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

import pytest

from app.api import soundcloud_connector_service as service


def _prepare(monkeypatch, tmp_path: Path, *, internet: bool = True, configured: bool = True) -> Path:
    state_dir = tmp_path / "state"
    monkeypatch.setattr(service, "current_user_id", lambda: "soundcloud_test_user")
    monkeypatch.setattr(service, "resolve_elysia_paths", lambda: SimpleNamespace(state_dir=state_dir))
    monkeypatch.setattr(service, "internet_master_enabled", lambda: internet)
    if configured:
        monkeypatch.setenv("ELYSIA_SOUNDCLOUD_CLIENT_ID", "public-test-client")
        monkeypatch.setenv("ELYSIA_SOUNDCLOUD_REDIRECT_URI", "http://127.0.0.1:43119/soundcloud/callback")
    else:
        monkeypatch.delenv("ELYSIA_SOUNDCLOUD_CLIENT_ID", raising=False)
        monkeypatch.delenv("ELYSIA_SOUNDCLOUD_REDIRECT_URI", raising=False)
    monkeypatch.delenv("ELYSIA_SOUNDCLOUD_CLIENT_SECRET", raising=False)
    return state_dir


def test_connector_is_optional_and_reports_external_registration(monkeypatch, tmp_path: Path):
    _prepare(monkeypatch, tmp_path, configured=False)
    result = service.status()
    assert result["optional"] is True
    assert result["configured"] is False
    assert result["external_prerequisite"] == "registered_soundcloud_application"
    assert result["credential_state"] == "not_connected"


def test_internet_off_fails_closed_before_creating_pkce_state(monkeypatch, tmp_path: Path):
    state_dir = _prepare(monkeypatch, tmp_path, internet=False)
    with pytest.raises(service.SoundCloudConnectorError, match="Internet is OFF"):
        service.begin_authorization()
    assert not list(state_dir.rglob("pending.json"))


def test_pkce_authorization_state_is_private_and_verifier_never_enters_url(monkeypatch, tmp_path: Path):
    state_dir = _prepare(monkeypatch, tmp_path)
    result = service.begin_authorization()
    query = parse_qs(urlparse(result["authorization_url"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert "code_verifier" not in query
    assert "client_secret" not in query
    assert result["credentials_exposed"] is False
    pending_path = next(state_dir.rglob("pending.json"))
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    assert pending_path.stat().st_mode & 0o777 == 0o600
    assert pending["code_verifier"]
    assert pending["state"] == query["state"][0]


def test_completion_encrypts_credential_and_disconnect_revokes_it(monkeypatch, tmp_path: Path):
    state_dir = _prepare(monkeypatch, tmp_path)
    begin = service.begin_authorization()
    returned_state = parse_qs(urlparse(begin["authorization_url"]).query)["state"][0]
    monkeypatch.setattr(
        service,
        "_exchange",
        lambda _body: {
            "access_token": "synthetic-access-token",
            "refresh_token": "synthetic-refresh-token",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    result = service.complete_authorization(
        service.SoundCloudCompleteRequest(
            authorization_code="synthetic-code-value",
            returned_state=returned_state,
        )
    )
    assert result == {
        "status": "connected",
        "provider": "soundcloud",
        "credentials_exposed": False,
        "internet_master_enabled": True,
    }
    token_path = next(state_dir.rglob("credential.enc"))
    key_path = next(state_dir.rglob("credential.key"))
    assert token_path.stat().st_mode & 0o777 == 0o600
    assert key_path.stat().st_mode & 0o777 == 0o600
    assert b"synthetic-access-token" not in token_path.read_bytes()
    assert service.status()["credential_state"] == "connected"

    monkeypatch.setattr(service, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")))
    disconnected = service.disconnect()
    assert disconnected["credential_state"] == "not_connected"
    assert disconnected["provider_sign_out"] == "failed_local_credential_removed"
    assert not token_path.exists()
    assert not key_path.exists()


def test_completion_rejects_wrong_state_without_network(monkeypatch, tmp_path: Path):
    _prepare(monkeypatch, tmp_path)
    service.begin_authorization()
    called = False

    def fail_exchange(_body: bytes):
        nonlocal called
        called = True
        raise AssertionError("network must not be reached")

    monkeypatch.setattr(service, "_exchange", fail_exchange)
    with pytest.raises(service.SoundCloudConnectorError, match="invalid or expired"):
        service.complete_authorization(
            service.SoundCloudCompleteRequest(
                authorization_code="synthetic-code-value",
                returned_state="wrong-state-value-long-enough",
            )
        )
    assert called is False


def test_connected_account_verification_uses_fixed_me_endpoint_and_never_returns_token(monkeypatch, tmp_path: Path):
    _prepare(monkeypatch, tmp_path)
    begin = service.begin_authorization()
    returned_state = parse_qs(urlparse(begin["authorization_url"]).query)["state"][0]
    monkeypatch.setattr(
        service,
        "_exchange",
        lambda _body: {
            "access_token": "synthetic-access-token",
            "refresh_token": "synthetic-refresh-token",
            "expires_in": 3600,
        },
    )
    service.complete_authorization(
        service.SoundCloudCompleteRequest(
            authorization_code="synthetic-code-value",
            returned_state=returned_state,
        )
    )
    captured: dict[str, str] = {}

    def fake_read(request, *, expected_host: str, error_message: str):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization") or ""
        captured["expected_host"] = expected_host
        captured["error_message"] = error_message
        return {
            "username": "Synthetic listener",
            "urn": "soundcloud:users:123",
            "permalink_url": "https://soundcloud.com/synthetic-listener",
            "track_count": 2,
        }

    monkeypatch.setattr(service, "_read_json_request", fake_read)
    result = service.verify_connected_account()
    assert captured["url"] == service.API_ME_URL
    assert captured["expected_host"] == service.API_HOST
    assert captured["authorization"] == "OAuth synthetic-access-token"
    assert result["status"] == "verified"
    assert result["account_label"] == "Synthetic listener"
    assert result["track_count"] == 2
    assert result["credentials_exposed"] is False
    assert "token" not in result


def test_expired_connected_account_refreshes_before_fixed_me_request(monkeypatch, tmp_path: Path):
    state_dir = _prepare(monkeypatch, tmp_path)
    owner = "soundcloud_test_user"
    root = state_dir / "connectors" / "soundcloud" / service._owner_hash(owner)
    root.mkdir(parents=True)
    service._store_credential(
        owner,
        {
            "access_token": "expired-token",
            "refresh_token": "single-use-refresh",
            "expires_at_utc": "2000-01-01T00:00:00Z",
        },
    )
    monkeypatch.setattr(
        service,
        "_exchange",
        lambda body: {
            "access_token": "refreshed-token",
            "refresh_token": "rotated-refresh-token",
            "expires_in": 3600,
            "request": body.decode("utf-8"),
        },
    )
    monkeypatch.setattr(
        service,
        "_read_json_request",
        lambda request, **_kwargs: {"username": "Refreshed listener", "track_count": 0}
        if request.get_header("Authorization") == "OAuth refreshed-token"
        else (_ for _ in ()).throw(AssertionError("stale access token used")),
    )
    result = service.verify_connected_account()
    assert result["account_label"] == "Refreshed listener"
    encrypted = (root / "credential.enc").read_bytes()
    assert b"refreshed-token" not in encrypted
