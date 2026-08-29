"""Stable local-account ownership helpers shared by domain authorities."""

from __future__ import annotations


class DomainOwnershipError(PermissionError):
    """A domain object belongs to another authenticated local account."""


def current_user_id() -> str | None:
    """Resolve the active account without making domain stores own Identity."""
    try:
        from app.api.account_service import get_authenticated_principal

        return str(get_authenticated_principal()["user_id"])
    except Exception:
        return None


def assert_owner(owner_user_id: str | None) -> None:
    active = current_user_id()
    if active is not None and owner_user_id is not None and owner_user_id != active:
        raise DomainOwnershipError("The requested local object belongs to another account.")


__all__ = ("DomainOwnershipError", "assert_owner", "current_user_id")
