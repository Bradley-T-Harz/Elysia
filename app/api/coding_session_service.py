"""In-memory governed coding sessions for the VS Code bridge MVP."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.api.coding_policy_service import coding_boundary_flags_for_mode, normalize_approval_mode
from app.api.schemas.coding import CodingSession, CodingSessionStartRequest


_SESSIONS: dict[str, CodingSession] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash_workspace_root(workspace_root: str | None) -> str | None:
    if not workspace_root:
        return None
    resolved = str(Path(workspace_root).expanduser())
    return sha256(resolved.encode("utf-8")).hexdigest()[:24]


def start_coding_session(payload: CodingSessionStartRequest) -> CodingSession:
    now = _utc_now_iso()
    workspace_label = payload.workspace_label or "VS Code workspace"
    session = CodingSession(
        session_id=f"coding_{uuid4().hex[:16]}",
        workspace_label=workspace_label,
        workspace_root_hash=_hash_workspace_root(payload.workspace_root),
        approval_mode=normalize_approval_mode(payload.approval_mode),
        source=payload.source or "vscode",
        created_at_utc=now,
        updated_at_utc=now,
        boundaries=coding_boundary_flags_for_mode(payload.approval_mode),
    )
    _SESSIONS[session.session_id] = session
    return session


def get_coding_session(session_id: str | None) -> CodingSession | None:
    if not session_id:
        return None
    return _SESSIONS.get(session_id)


def clear_coding_sessions_for_tests() -> None:
    _SESSIONS.clear()


__all__ = (
    "clear_coding_sessions_for_tests",
    "get_coding_session",
    "start_coding_session",
)
