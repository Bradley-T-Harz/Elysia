"""Interactive terminal bootstrap for the sealed local Elysia user."""

from __future__ import annotations

import getpass

from app.api import account_service
from app.api.schemas.account import AccountCreateRequest


def ensure_account_ready_for_terminal() -> dict:
    """
    Create a local account interactively when no user exists.

    This helper is intentionally small and local-only. It does not write normal
    Memory, does not return session tokens, and does not expose password hashes.
    """
    state = account_service.get_account_state()
    if not state.requires_user_creation:
        return {
            "created": False,
            "state": state.to_payload(),
            "credential_material_returned": False,
        }

    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    interests = input("Interests: ").strip()
    bio = input("Bio: ").strip()

    account_service.create_account(
        AccountCreateRequest(
            username=username,
            password=password,
            interests=interests,
            bio=bio,
        )
    )
    return {
        "created": True,
        "state": account_service.get_account_state().to_payload(),
        "credential_material_returned": False,
    }


def main() -> int:
    result = ensure_account_ready_for_terminal()
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
