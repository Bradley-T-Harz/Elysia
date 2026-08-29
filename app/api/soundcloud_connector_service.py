"""Optional SoundCloud OAuth 2.1/PKCE connector with local credential isolation."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field

from app.api.user_control_service import internet_master_enabled
from app.install.paths import resolve_elysia_paths
from app.ownership import current_user_id


AUTHORIZE_URL = "https://secure.soundcloud.com/authorize"
TOKEN_URL = "https://secure.soundcloud.com/oauth/token"
TOKEN_HOST = "secure.soundcloud.com"
SIGN_OUT_URL = "https://secure.soundcloud.com/sign-out"
API_ME_URL = "https://api.soundcloud.com/me"
API_HOST = "api.soundcloud.com"


class SoundCloudConnectorError(RuntimeError):
    """The optional connector could not complete a governed action."""


class SoundCloudCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    authorization_code: str = Field(min_length=8, max_length=4096)
    returned_state: str = Field(min_length=16, max_length=256)


def _now() -> datetime:
    return datetime.now(UTC)


def _owner() -> str:
    owner = current_user_id()
    if not owner:
        raise SoundCloudConnectorError("An authenticated local account is required.")
    return owner


def _owner_hash(owner: str) -> str:
    return hashlib.sha256(owner.encode("utf-8")).hexdigest()[:24]


def _root(owner: str) -> Path:
    root = resolve_elysia_paths().state_dir / "connectors" / "soundcloud" / _owner_hash(owner)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    return root


def _paths(owner: str) -> tuple[Path, Path, Path]:
    root = _root(owner)
    return root / "pending.json", root / "credential.key", root / "credential.enc"


def _write_private(path: Path, payload: bytes) -> None:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temp_path.replace(path)
        path.chmod(0o600)
    finally:
        temp_path.unlink(missing_ok=True)


def _configuration() -> tuple[str | None, str | None, str | None]:
    return (
        os.environ.get("ELYSIA_SOUNDCLOUD_CLIENT_ID"),
        os.environ.get("ELYSIA_SOUNDCLOUD_REDIRECT_URI"),
        os.environ.get("ELYSIA_SOUNDCLOUD_CLIENT_SECRET"),
    )


def _credential_state(owner: str) -> str:
    _, key_path, token_path = _paths(owner)
    if not key_path.is_file() or not token_path.is_file():
        return "not_connected"
    try:
        payload = json.loads(Fernet(key_path.read_bytes()).decrypt(token_path.read_bytes()))
    except (OSError, ValueError, InvalidToken, json.JSONDecodeError):
        return "credential_unreadable"
    expires_at = payload.get("expires_at_utc")
    if isinstance(expires_at, str):
        try:
            if datetime.fromisoformat(expires_at.replace("Z", "+00:00")) <= _now():
                return "token_expired"
        except ValueError:
            return "credential_unreadable"
    return "connected"


def _load_credential(owner: str) -> dict[str, Any]:
    _, key_path, token_path = _paths(owner)
    try:
        payload = json.loads(Fernet(key_path.read_bytes()).decrypt(token_path.read_bytes()))
    except (OSError, ValueError, InvalidToken, json.JSONDecodeError) as exc:
        raise SoundCloudConnectorError("The local SoundCloud credential is unavailable or unreadable.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
        raise SoundCloudConnectorError("The local SoundCloud credential is incomplete.")
    return payload


def _store_credential(owner: str, payload: dict[str, Any]) -> None:
    _, key_path, token_path = _paths(owner)
    key = key_path.read_bytes() if key_path.is_file() else Fernet.generate_key()
    _write_private(key_path, key)
    _write_private(token_path, Fernet(key).encrypt(json.dumps(payload).encode("utf-8")))


def status() -> dict[str, Any]:
    owner = _owner()
    client_id, redirect_uri, _ = _configuration()
    pending_path, _, _ = _paths(owner)
    return {
        "provider": "soundcloud",
        "optional": True,
        "configured": bool(client_id and redirect_uri),
        "credential_state": _credential_state(owner),
        "authorization_pending": pending_path.is_file(),
        "internet_master_enabled": internet_master_enabled(),
        "credential_storage": "account_scoped_local_encrypted_file",
        "network_boundary": "SoundCloud receives only explicitly authorized connector requests when Internet is ON.",
        "external_prerequisite": None if client_id and redirect_uri else "registered_soundcloud_application",
    }


def begin_authorization() -> dict[str, Any]:
    owner = _owner()
    if not internet_master_enabled():
        raise SoundCloudConnectorError("Internet is OFF in Settings; no SoundCloud authorization request was created.")
    client_id, redirect_uri, _ = _configuration()
    if not client_id or not redirect_uri:
        raise SoundCloudConnectorError(
            "A user-owned registered SoundCloud application is required. Configure the local client ID and redirect URI first."
        )
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    state = secrets.token_urlsafe(32)
    pending_path, _, _ = _paths(owner)
    pending = {
        "state": state,
        "code_verifier": verifier,
        "created_at_utc": _now().isoformat().replace("+00:00", "Z"),
        "expires_at_utc": (_now() + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
    }
    _write_private(pending_path, (json.dumps(pending, sort_keys=True) + "\n").encode("utf-8"))
    authorization_url = AUTHORIZE_URL + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    })
    return {
        "status": "authorization_required",
        "authorization_url": authorization_url,
        "expires_in_seconds": 600,
        "pkce": True,
        "state_required": True,
        "credentials_exposed": False,
    }


def _exchange(body: bytes) -> dict[str, Any]:
    request = Request(
        TOKEN_URL,
        method="POST",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - exact fixed HTTPS endpoint
            response_url = urlparse(response.geturl())
            if response_url.scheme != "https" or response_url.hostname != TOKEN_HOST:
                raise SoundCloudConnectorError("SoundCloud token exchange redirected outside the approved host.")
            raw = response.read(64 * 1024)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SoundCloudConnectorError("SoundCloud rejected or could not complete the token exchange.") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SoundCloudConnectorError("SoundCloud returned an invalid token response.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
        raise SoundCloudConnectorError("SoundCloud did not return an access token.")
    return payload


def _refresh_credential(owner: str, credential: dict[str, Any]) -> dict[str, Any]:
    refresh_token = credential.get("refresh_token")
    client_id, _, client_secret = _configuration()
    if not isinstance(refresh_token, str) or not refresh_token or not client_id:
        raise SoundCloudConnectorError("SoundCloud authorization expired; reconnect the optional account.")
    form = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }
    if client_secret:
        form["client_secret"] = client_secret
    token = _exchange(urlencode(form).encode("utf-8"))
    expires_in = int(token.get("expires_in") or 3600)
    refreshed = {
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token") or refresh_token,
        "token_type": token.get("token_type", "OAuth"),
        "scope": token.get("scope", credential.get("scope")),
        "expires_at_utc": (_now() + timedelta(seconds=max(60, min(expires_in, 86_400))))
        .isoformat()
        .replace("+00:00", "Z"),
    }
    _store_credential(owner, refreshed)
    return refreshed


def _usable_credential(owner: str) -> dict[str, Any]:
    credential = _load_credential(owner)
    expires_at = credential.get("expires_at_utc")
    try:
        expired = not isinstance(expires_at, str) or datetime.fromisoformat(
            expires_at.replace("Z", "+00:00")
        ) <= _now()
    except ValueError:
        expired = True
    return _refresh_credential(owner, credential) if expired else credential


def _read_json_request(request: Request, *, expected_host: str, error_message: str) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed provider endpoints only
            response_url = urlparse(response.geturl())
            if response_url.scheme != "https" or response_url.hostname != expected_host:
                raise SoundCloudConnectorError("SoundCloud redirected outside the approved provider host.")
            raw = response.read(64 * 1024)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SoundCloudConnectorError(error_message) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SoundCloudConnectorError("SoundCloud returned an invalid JSON response.") from exc
    if not isinstance(payload, dict):
        raise SoundCloudConnectorError("SoundCloud returned an unexpected response shape.")
    return payload


def verify_connected_account() -> dict[str, Any]:
    """Prove the optional credential works using SoundCloud's fixed ``GET /me`` endpoint."""

    owner = _owner()
    if not internet_master_enabled():
        raise SoundCloudConnectorError("Internet is OFF in Settings; no SoundCloud account request was sent.")
    credential = _usable_credential(owner)
    request = Request(
        API_ME_URL,
        method="GET",
        headers={
            "Accept": "application/json; charset=utf-8",
            "Authorization": f"OAuth {credential['access_token']}",
        },
    )
    payload = _read_json_request(
        request,
        expected_host=API_HOST,
        error_message="SoundCloud could not verify the connected account.",
    )
    return {
        "status": "verified",
        "provider": "soundcloud",
        "account_label": str(payload.get("username") or "Connected SoundCloud account")[:160],
        "account_urn": str(payload.get("urn") or "")[:240] or None,
        "permalink_url": str(payload.get("permalink_url") or "")[:1000] or None,
        "track_count": int(payload.get("track_count") or 0),
        "credentials_exposed": False,
        "request_boundary": "fixed_https_get_me",
    }


def complete_authorization(payload: SoundCloudCompleteRequest) -> dict[str, Any]:
    owner = _owner()
    if not internet_master_enabled():
        raise SoundCloudConnectorError("Internet is OFF in Settings; no token exchange was attempted.")
    client_id, redirect_uri, client_secret = _configuration()
    if not client_id or not redirect_uri:
        raise SoundCloudConnectorError("The local SoundCloud application configuration is incomplete.")
    pending_path, _, _ = _paths(owner)
    try:
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        expires = datetime.fromisoformat(str(pending["expires_at_utc"]).replace("Z", "+00:00"))
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise SoundCloudConnectorError("No valid SoundCloud authorization attempt is pending.") from exc
    if expires <= _now() or not secrets.compare_digest(str(pending.get("state", "")), payload.returned_state):
        raise SoundCloudConnectorError("The SoundCloud authorization state is invalid or expired.")
    form = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_verifier": str(pending["code_verifier"]),
        "code": payload.authorization_code,
    }
    if client_secret:
        form["client_secret"] = client_secret
    token = _exchange(urlencode(form).encode("utf-8"))
    expires_in = int(token.get("expires_in") or 3600)
    encrypted_payload = {
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token"),
        "token_type": token.get("token_type", "Bearer"),
        "scope": token.get("scope"),
        "expires_at_utc": (_now() + timedelta(seconds=max(60, min(expires_in, 86_400)))).isoformat().replace("+00:00", "Z"),
    }
    _store_credential(owner, encrypted_payload)
    pending_path.unlink(missing_ok=True)
    return {
        "status": "connected",
        "provider": "soundcloud",
        "credentials_exposed": False,
        "internet_master_enabled": True,
    }


def disconnect() -> dict[str, Any]:
    owner = _owner()
    pending_path, key_path, token_path = _paths(owner)
    provider_sign_out = "not_attempted"
    if internet_master_enabled() and key_path.is_file() and token_path.is_file():
        try:
            credential = _usable_credential(owner)
            request = Request(
                SIGN_OUT_URL,
                method="POST",
                data=json.dumps({"access_token": credential["access_token"]}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            try:
                with urlopen(request, timeout=15) as response:  # noqa: S310 - exact fixed HTTPS endpoint
                    response_url = urlparse(response.geturl())
                    if response_url.scheme != "https" or response_url.hostname != TOKEN_HOST:
                        raise SoundCloudConnectorError("SoundCloud sign-out redirected outside the approved host.")
                    response.read(64 * 1024)
                provider_sign_out = "completed"
            except (HTTPError, URLError, TimeoutError, SoundCloudConnectorError):
                provider_sign_out = "failed_local_credential_removed"
        except SoundCloudConnectorError:
            provider_sign_out = "failed_local_credential_removed"
    pending_path.unlink(missing_ok=True)
    token_path.unlink(missing_ok=True)
    key_path.unlink(missing_ok=True)
    return {
        "status": "disconnected",
        "provider": "soundcloud",
        "credential_state": "not_connected",
        "provider_sign_out": provider_sign_out,
    }


def close_pending_authorizations_for_emergency() -> int:
    """Invalidate resumable OAuth handshakes without deleting linked accounts.

    Internet OFF blocks every provider call. Removing only account-scoped PKCE
    pending files also prevents an authorization browser flow that was already
    open from being resumed after the system-wide stop. Encrypted durable
    connector credentials remain owned by the user for explicit later resume
    or disconnect.
    """
    connector_root = resolve_elysia_paths().state_dir / "connectors" / "soundcloud"
    removed = 0
    try:
        pending_paths = list(connector_root.glob("*/pending.json"))
    except OSError:
        return 0
    for pending_path in pending_paths:
        try:
            pending_path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            continue
    return removed


__all__ = (
    "SoundCloudCompleteRequest",
    "SoundCloudConnectorError",
    "begin_authorization",
    "complete_authorization",
    "close_pending_authorizations_for_emergency",
    "disconnect",
    "status",
    "verify_connected_account",
)
