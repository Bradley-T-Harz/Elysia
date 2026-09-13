"""Local identity binding shared by legacy and multi-surface Codev clients."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
import os
from pathlib import Path

_client_binding: ContextVar[str] = ContextVar("codev_client_binding", default="native-compatibility")
_workspace_root: ContextVar[Path | None] = ContextVar("codev_scoped_workspace", default=None)


def local_profile_id() -> str:
    from app.api.account_service import AccountAuthError, get_authenticated_principal
    try:
        return get_authenticated_principal()["user_id"]
    except AccountAuthError:
        # Source/test compatibility is not authentication for new clients.
        return f"signed-out-os-user-{os.getuid()}"


def approval_actor() -> str:
    from app.api.account_service import AccountAuthError, get_authenticated_principal
    try:
        principal = get_authenticated_principal()
        identity = f"{principal['user_id']}:{principal['session_id']}"
    except AccountAuthError:
        identity = f"signed-out-os-user-{os.getuid()}"
    return sha256(f"{identity}:{_client_binding.get()}".encode()).hexdigest()


@contextmanager
def bind_client(binding: str):
    """Internal adapter context, never a caller-supplied authorization header."""
    token = _client_binding.set(binding)
    try:
        yield
    finally:
        _client_binding.reset(token)


def current_workspace_root() -> Path | None:
    return _workspace_root.get()


@contextmanager
def bind_workspace(root: Path):
    """Internal grant adapter only; never persisted as a legacy repository grant."""
    token = _workspace_root.set(root)
    try:
        yield
    finally:
        _workspace_root.reset(token)
