"""Terminal helpers for the sealed local account gate."""

from __future__ import annotations

import argparse
import getpass
import json
from typing import Sequence

from app.api import account_service
from app.api.schemas.account import (
    AccountCreateRequest,
    AccountLoginRequest,
    AccountProfileUpdateRequest,
)


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def _create_account(args: argparse.Namespace) -> int:
    password = args.password or getpass.getpass("Password: ")
    profile = account_service.create_account(
        AccountCreateRequest(
            username=args.username,
            password=password,
            interests=args.interests or "",
            bio=args.bio or "",
            birthdate=args.birthdate,
            emails=_split_list(args.emails or ""),
            phone_number=args.phone_number,
            social_media=_split_list(args.social_media or ""),
            github=args.github,
            city_state=args.city_state,
            profile_color_id=args.profile_color_id,
        )
    )
    _print_json(
        {
            "created": True,
            "state": account_service.get_account_state().to_payload(),
            "profile": profile.to_payload(),
            "credential_material_returned": False,
        }
    )
    return 0


def _login(args: argparse.Namespace) -> int:
    password = args.password or getpass.getpass("Password: ")
    state = account_service.login(
        AccountLoginRequest(username=args.username, password=password)
    )
    _print_json(
        {
            "logged_in": True,
            "state": state.to_payload(),
            "credential_material_returned": False,
        }
    )
    return 0


def _logout(_: argparse.Namespace) -> int:
    state = account_service.logout()
    _print_json({"logged_out": True, "state": state.to_payload(), "session_revoked": True})
    return 0


def _state(_: argparse.Namespace) -> int:
    _print_json(account_service.get_account_state().to_payload())
    return 0


def _profile(_: argparse.Namespace) -> int:
    _print_json(account_service.get_private_profile().to_payload())
    return 0


def _visible_profile(_: argparse.Namespace) -> int:
    profile = account_service.get_elysia_visible_profile()
    _print_json(profile.to_payload() if profile else {"profile": None})
    return 0


def _update_profile(args: argparse.Namespace) -> int:
    password = args.password
    if args.prompt_password:
        password = getpass.getpass("New password: ")
    profile, password_changed = account_service.update_profile(
        AccountProfileUpdateRequest(
            username=args.username,
            password=password,
            interests=args.interests,
            bio=args.bio,
            birthdate=args.birthdate,
            emails=_split_list(args.emails) if args.emails is not None else None,
            phone_number=args.phone_number,
            social_media=_split_list(args.social_media) if args.social_media is not None else None,
            github=args.github,
            city_state=args.city_state,
            profile_color_id=args.profile_color_id,
        )
    )
    _print_json(
        {
            "updated": True,
            "password_changed": password_changed,
            "profile": profile.to_payload(),
            "credential_material_returned": False,
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elysia-account",
        description="Manage the sealed local Elysia account from a terminal.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create the first local user.")
    create.add_argument("--username", required=True)
    create.add_argument("--password")
    create.add_argument("--interests", default="")
    create.add_argument("--bio", default="")
    create.add_argument("--birthdate")
    create.add_argument("--emails", default="")
    create.add_argument("--phone-number")
    create.add_argument("--social-media", default="")
    create.add_argument("--github")
    create.add_argument("--city-state")
    create.add_argument("--profile-color-id", default="meteor_rose")
    create.set_defaults(func=_create_account)

    login = subparsers.add_parser("login", help="Create a persistent local session.")
    login.add_argument("--username", required=True)
    login.add_argument("--password")
    login.set_defaults(func=_login)

    update = subparsers.add_parser("update-profile", help="Update the local profile.")
    update.add_argument("--username")
    update.add_argument("--password")
    update.add_argument("--prompt-password", action="store_true")
    update.add_argument("--interests")
    update.add_argument("--bio")
    update.add_argument("--birthdate")
    update.add_argument("--emails")
    update.add_argument("--phone-number")
    update.add_argument("--social-media")
    update.add_argument("--github")
    update.add_argument("--city-state")
    update.add_argument("--profile-color-id")
    update.set_defaults(func=_update_profile)

    subparsers.add_parser("logout", help="Revoke the current local session.").set_defaults(func=_logout)
    subparsers.add_parser("state", help="Show account gate state.").set_defaults(func=_state)
    subparsers.add_parser("profile", help="Show authenticated private profile.").set_defaults(func=_profile)
    subparsers.add_parser("visible-profile", help="Show Elysia-visible projection only.").set_defaults(func=_visible_profile)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except account_service.AccountServiceError as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
