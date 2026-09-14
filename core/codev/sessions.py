"""Native client sessions, bound to the authenticated local account session."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock
from uuid import uuid4

from core.codev.contracts import Actor
from core.codev.grants import GrantDenied, utc_now
from core.codev.installation import resolve_installation


@dataclass
class _Session:
    actor: Actor
    local_session_id: str
    expires_at: datetime
    installation_id: str | None = None


_SESSIONS: dict[str, _Session] = {}
_LOCK = RLock()


def _principal():
    from app.api.account_service import get_authenticated_principal
    return get_authenticated_principal()


def ensure_available() -> None:
    if not resolve_installation().usable:
        raise GrantDenied("codev_installation_unavailable")


def open_native_session() -> Actor:
    ensure_available()
    principal = _principal()
    actor = Actor(local_profile_id=principal["user_id"], client_id=f"native_{uuid4().hex}",
                  client_kind="native", surface="local")
    with _LOCK:
        for key in list(_SESSIONS):
            if _SESSIONS[key].expires_at <= utc_now():
                del _SESSIONS[key]
        if len(_SESSIONS) >= 32:
            raise GrantDenied("native_session_capacity_reached")
        _SESSIONS[actor.client_id] = _Session(actor, principal["session_id"], utc_now() + timedelta(hours=8),
                                             resolve_installation().installation_id)
    return actor


def require_native_session(client_id: str, *, revocation_only: bool = False) -> Actor:
    principal = _principal()
    if not revocation_only:
        ensure_available()
    with _LOCK:
        session = _SESSIONS.get(client_id)
        if (not session or session.expires_at <= utc_now() or session.actor.local_profile_id != principal["user_id"]
                or session.local_session_id != principal["session_id"]):
            raise GrantDenied("native_session_missing_expired_or_account_changed")
        if not revocation_only and session.installation_id != resolve_installation().installation_id:
            raise GrantDenied("native_session_installation_changed")
        return session.actor
