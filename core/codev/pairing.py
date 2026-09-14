"""Explicit native confirmation for metadata-only Online pairing.

The native app's bearer never leaves its API. Each pairing has a distinct RAM
P-256 key and a short-lived, single-purpose cloud confirmation secret. Browser
and local account identities are separate and bound to their exact login sessions.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import json
import re
import secrets
from threading import RLock
from urllib.request import Request, build_opener, ProxyHandler, HTTPSHandler, HTTPRedirectHandler
from urllib.error import URLError
from uuid import uuid4

from core.codev import broker_crypto as crypto
from core.codev.contracts import Actor, BrokerProof, PairingIntent, PairingSession
from core.codev.grants import GrantDenied, utc_now
from core.codev.installation import resolve_installation
from core.codev.sessions import require_native_session, _principal
from app.api.account_service import AccountServiceError

ORIGINS = ("https://elysiaecobotics.com", "https://www.elysiaecobotics.com")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise GrantDenied("codev_pairing_redirect_denied")


def _online(origin: str, route: str, payload: dict) -> dict:
    if origin not in ORIGINS or route not in {"claim", "native"}:
        raise GrantDenied("codev_pairing_destination_denied")
    request = Request(origin + "/api/codev/" + route, method="POST",
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json", "X-Codev-Native": "pairing-1", "Accept": "application/json",
                 "User-Agent": "Elysia-Codev/1.1.0 (codev-pairing-1; +https://github.com/Bradley-T-Harz/Elysia)"})
    try:
        # Do not inherit environment HTTP proxies or follow credential-bearing redirects.
        with build_opener(ProxyHandler({}), HTTPSHandler(), _NoRedirect()).open(request, timeout=5) as response:
            raw = response.read(8193)
            if len(raw) > 8192 or response.status != 200:
                raise GrantDenied("codev_online_pairing_unavailable")
            data = crypto.strict_json(raw.decode("utf-8"))
            if data.get("ok") is not True or not isinstance(data.get("pairing"), dict):
                raise GrantDenied("codev_online_pairing_unavailable")
            return data["pairing"]
    except (URLError, OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise GrantDenied("codev_online_pairing_unavailable") from exc


@dataclass
class NativePairing:
    intent: PairingIntent
    native_client_id: str
    local_profile_id: str
    local_session_id: str
    actor: Actor
    private_key: object
    native_secret: str
    revoked: bool = False
    nonces: dict[str, float] = field(default_factory=dict)
    requests: deque = field(default_factory=deque)
    lock: RLock = field(default_factory=RLock)


_PAIRS: dict[str, NativePairing] = {}
_LOCK = RLock()


def _expired(pair: NativePairing) -> bool:
    expiry = datetime.fromisoformat(pair.intent.expires_at.replace("Z", "+00:00"))
    return expiry.tzinfo is None or expiry <= utc_now()


def _validate_view(data: dict, *, expected_origin: str, key) -> PairingIntent:
    if set(data) != {"pairing_id", "native_public_key", "intent", "workspace_grants"} or data["workspace_grants"] != []:
        raise GrantDenied("codev_pairing_contract_mismatch")
    intent = PairingIntent.model_validate(data["intent"])
    if data["pairing_id"] != intent.intent_id or intent.origin != expected_origin or data["native_public_key"] != crypto.public_key(key).model_dump():
        raise GrantDenied("codev_pairing_identity_mismatch")
    crypto.load_public(intent.browser_public_key)
    expiry = datetime.fromisoformat(intent.expires_at.replace("Z", "+00:00"))
    if expiry.tzinfo is None or expiry <= utc_now() or (expiry - utc_now()).total_seconds() > 16 * 60:
        raise GrantDenied("codev_pairing_expired")
    return intent


def summary(pair: NativePairing) -> dict:
    return {"pairing_id": pair.intent.intent_id, "intent": pair.intent.model_dump(),
        "native_public_key": crypto.public_key(pair.private_key).model_dump(), "workspace_grants": [],
        "note": "Connected to local Codev. No workspace shared." if pair.intent.status == "paired" else "No workspace shared."}


def _revoke_local(pair: NativePairing) -> None:
    pair.revoked = True
    pair.intent = pair.intent.model_copy(update={"status": "revoked"})
    # Browser workspace authority is owned by the shared domain, never by transport.
    from core.codev import browser_workspaces
    browser_workspaces.revoke_actor(pair.actor)


def claim(client_id: str, code: str) -> dict:
    native = require_native_session(client_id)
    principal = _principal()
    if not re.fullmatch(r"EC1\.[AW]\.[A-Za-z0-9_-]{43}", code):
        raise GrantDenied("codev_pairing_code_invalid")
    crypto.decode64(code.split(".")[2], 32)
    with _LOCK:
        for key, old in list(_PAIRS.items()):
            if old.revoked or _expired(old):
                _revoke_local(old)
                del _PAIRS[key]
        if len(_PAIRS) >= 16:
            raise GrantDenied("codev_pairing_capacity_reached")
        origin = ORIGINS[0 if code.startswith("EC1.A.") else 1]
        key, secret = crypto.new_key(), secrets.token_urlsafe(32)
        data = _online(origin, "claim", {"code": code, "native_public_key": crypto.public_key(key).model_dump(), "native_secret": secret})
        intent = _validate_view(data, expected_origin=origin, key=key)
        if intent.status != "pending":
            raise GrantDenied("codev_pairing_already_claimed")
        require_native_session(client_id)
        if _principal() != principal:
            raise GrantDenied("codev_local_account_changed")
        actor = Actor(local_profile_id=native.local_profile_id, client_id=f"browser_{uuid4().hex}", client_kind="browser",
            online_account_id=intent.online_account_id, origin=intent.origin, surface=intent.surface)
        pair = NativePairing(intent, client_id, native.local_profile_id, principal["session_id"], actor, key, secret)
        _PAIRS[intent.intent_id] = pair
        return summary(pair)


def _local(pair: NativePairing, *, revocation_only=False) -> None:
    try:
        current = _principal()
        if (current["user_id"], current["session_id"]) != (pair.local_profile_id, pair.local_session_id):
            raise GrantDenied("codev_local_account_changed")
        if not revocation_only:
            require_native_session(pair.native_client_id)
            if pair.revoked or _expired(pair):
                raise GrantDenied("codev_pairing_expired_or_revoked")
    except (ValueError, OSError, AccountServiceError):
        _revoke_local(pair)
        raise GrantDenied("codev_local_authority_unavailable") from None


def native_action(client_id: str, pairing_id: str, action: str, *, explicitly_approved: bool = False) -> dict:
    native = require_native_session(client_id, revocation_only=action in {"deny", "revoke"})
    pair = get(pairing_id)
    with pair.lock:
        _local(pair, revocation_only=action in {"deny", "revoke"})
        if native.local_profile_id != pair.local_profile_id:
            raise GrantDenied("codev_pairing_owner_mismatch")
        if action in {"deny", "revoke"}:
            _revoke_local(pair)
            try:
                _online(pair.intent.origin, "native", {"pairing_id": pairing_id, "native_secret": pair.native_secret, "action": action})
                cloud_revoked = True
            except GrantDenied:
                cloud_revoked = False
            return {**summary(pair), "local_revoked": True, "cloud_revoked": cloud_revoked}
        if action != "confirm" or not explicitly_approved or pair.intent.status != "pending":
            raise GrantDenied("explicit_native_pairing_approval_required")
        from core.codev.broker import start_broker
        start_broker()
        data = _online(pair.intent.origin, "native", {"pairing_id": pairing_id, "native_secret": pair.native_secret, "action": "confirm"})
        _accept_lease(pair, data, {"native_approved"})
        _local(pair)
        return summary(pair)


def get(pairing_id: str) -> NativePairing:
    with _LOCK:
        pair = _PAIRS.get(pairing_id)
    if not pair:
        raise GrantDenied("codev_pairing_unavailable")
    return pair


def list_native(client_id: str) -> list[dict]:
    native = require_native_session(client_id, revocation_only=True)
    principal = _principal()
    with _LOCK:
        return [summary(pair) for pair in _PAIRS.values() if pair.local_profile_id == native.local_profile_id
                and pair.local_session_id == principal["session_id"] and not pair.revoked and not _expired(pair)]


def _accept_lease(pair: NativePairing, data: dict, statuses: set[str]) -> None:
    intent = _validate_view(data, expected_origin=pair.intent.origin, key=pair.private_key)
    stable = {"intent_id", "online_account_id", "account_label", "origin", "surface", "browser_session_id", "browser_public_key"}
    if intent.model_dump(include=stable) != pair.intent.model_dump(include=stable) or intent.status not in statuses:
        raise GrantDenied("codev_pairing_changed_or_revoked")
    pair.intent = intent


def require_live(pair: NativePairing, *, handshake: bool = False) -> None:
    with pair.lock:
        try:
            _local(pair)
            _accept_lease(pair, _online(pair.intent.origin, "native", {"pairing_id": pair.intent.intent_id,
                "native_secret": pair.native_secret, "action": "lease"}), {"native_approved", "paired"} if handshake else {"paired"})
            _local(pair)
        except (ValueError, OSError, AccountServiceError):
            _revoke_local(pair)
            raise GrantDenied("codev_pairing_no_longer_authorized") from None


def authenticate(origin: str, path: str, proof: BrokerProof, payload_json: str) -> NativePairing:
    pair = get(proof.pairing_id)
    with pair.lock:
        now = utc_now().timestamp()
        if (pair.revoked or _expired(pair) or pair.intent.status not in {"native_approved", "paired"}
            or origin != pair.intent.origin or proof.browser_session_id != pair.intent.browser_session_id
            or proof.online_account_id != pair.intent.online_account_id or abs(now * 1000 - proof.timestamp_ms) > 30000
            or not crypto.verify(pair.intent.browser_public_key, crypto.request_message(origin, path, proof, payload_json), proof.signature)):
            raise GrantDenied("codev_broker_authentication_failed")
        pair.nonces = {nonce: time for nonce, time in pair.nonces.items() if time > now - 61}
        while pair.requests and pair.requests[0] < now - 60:
            pair.requests.popleft()
        if proof.nonce in pair.nonces or len(pair.requests) >= 60 or len(pair.nonces) >= 128:
            raise GrantDenied("codev_broker_replay_or_rate_limit")
        pair.nonces[proof.nonce] = now
        pair.requests.append(now)
        _local(pair)
        return pair


def browser_status(pair: NativePairing) -> dict:
    require_live(pair, handshake=True)
    return {"session": PairingSession(pairing_id=pair.intent.intent_id, actor=pair.actor,
        browser_session_id=pair.intent.browser_session_id, browser_public_key=pair.intent.browser_public_key,
        native_public_key=crypto.public_key(pair.private_key), expires_at=pair.intent.expires_at,
        installation=resolve_installation()).model_dump(), "status": pair.intent.status}


def revoke_unavailable_pairs() -> None:
    with _LOCK:
        pairs = list(_PAIRS.values())
    for pair in pairs:
        with pair.lock:
            if pair.revoked:
                continue
            try:
                _local(pair)
            except GrantDenied:
                pass  # _local already cleared all browser grants and source.
