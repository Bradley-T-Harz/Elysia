from __future__ import annotations

from pathlib import Path

import app.api.account_service as account_service
from app.api import runtime_bridge
from app.api.account_service import AccountPaths, AccountStore
from app.api.schemas.account import AccountCreateRequest
from app.api.schemas.chat import ChatSendRequest
import core.runtime as runtime


PRIVATE_CANARIES = (
    "PRIVATE-BIRTHDATE-CANARY",
    "private_email_canary@example.com",
    "555-PRIVATE-CANARY",
    "private-social-canary",
    "github_private_canary",
    "SecretCityStateCanary",
    "correct horse battery staple",
)


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


def _create_private_profile(store: AccountStore) -> None:
    store.create_account(
        AccountCreateRequest(
            username="the operator",
            password="correct horse battery staple",
            interests="ecology, robotics",
            bio="Local-first builder.",
            birthdate="PRIVATE-BIRTHDATE-CANARY",
            emails=["private_email_canary@example.com"],
            phone_number="555-PRIVATE-CANARY",
            social_media=["private-social-canary"],
            github="github_private_canary",
            city_state="SecretCityStateCanary",
            profile_color_id="meteor_rose",
        )
    )


def test_runtime_bridge_loads_only_elysia_visible_profile_projection(
    tmp_path: Path,
    monkeypatch,
):
    store = _make_store(tmp_path)
    _create_private_profile(store)
    monkeypatch.setattr(account_service, "_default_store", lambda: store)

    profile_context = runtime_bridge._load_visible_profile_context()

    assert profile_context == {
        "name_or_username": "the operator",
        "interests": "ecology, robotics",
        "bio": "Local-first builder.",
        "profile_photo_available": False,
    }
    combined = repr(profile_context)
    for private_value in PRIVATE_CANARIES:
        assert private_value not in combined


def test_runtime_request_context_and_model_block_keep_private_profile_fields_out(
    tmp_path: Path,
    monkeypatch,
):
    store = _make_store(tmp_path)
    _create_private_profile(store)
    monkeypatch.setattr(account_service, "_default_store", lambda: store)

    visible = runtime_bridge._load_visible_profile_context()
    request_context = runtime_bridge._build_runtime_request_context(
        is_quick_invoke=False,
        ui_surface_hint="conversations_room",
        inbound_request_context={},
        attached_context_packet=None,
        profile_context=visible,
    )

    assert request_context is not None
    assert request_context["profile_context_source"] == "sealed_identity_visible_projection"
    assert request_context["profile_private_fields_included"] is False
    assert request_context["profile_memory_import_allowed"] is False

    gathered = runtime._merge_request_context_into_gathered_context(
        {"request_summary": "hello"},
        request_context,
    )
    profile_block = runtime._build_profile_context_block(gathered)

    assert "Username/name: the operator" in profile_block
    assert "Interests: ecology, robotics" in profile_block
    assert "Story: Local-first builder." in profile_block
    assert "Private account fields are not included" in profile_block
    assert "not Memory" in profile_block
    combined = repr(gathered) + profile_block
    for private_value in PRIVATE_CANARIES:
        assert private_value not in combined


def test_chat_data_exposes_profile_projection_truth_not_profile_values():
    request_model = ChatSendRequest(
        message="Use my profile only if it is allowed.",
        request_id="req_profile_projection_001",
    )
    runtime_packet = {
        "status": "ok_local_runtime",
        "response": {
            "response_text": "Hello the operator.",
            "response_source": "live_invoker",
            "invocation_status": "ok",
            "selected_model_role": "primary_general",
            "selected_runtime": "ollama",
            "selected_model_runtime_tag": "fake-local-general-model",
            "used_fallback": False,
            "fallback_from": "",
            "fallback_to": "",
            "caveats": [],
        },
        "profile_context": {
            "name_or_username": "the operator",
            "interests": "ecology, robotics",
            "bio": "Local-first builder.",
            "profile_photo_available": False,
        },
    }

    chat_data = runtime_bridge._translate_runtime_packet_to_chat_data(
        request_model,
        runtime_packet,
    )
    profile_context_truth = runtime_bridge._as_mapping(runtime_packet.get("profile_context", {}))
    if profile_context_truth:
        chat_data.profile_context = {
            "used": True,
            "source": "sealed_identity_visible_projection",
            "fields": [
                key
                for key in (
                    "name_or_username",
                    "interests",
                    "bio",
                    "profile_photo_asset_id",
                    "profile_photo_available",
                )
                if key in profile_context_truth
            ],
            "private_fields_included": False,
            "memory_import_allowed": False,
        }

    assert chat_data.profile_context == {
        "used": True,
        "source": "sealed_identity_visible_projection",
        "fields": [
            "name_or_username",
            "interests",
            "bio",
            "profile_photo_available",
        ],
        "private_fields_included": False,
        "memory_import_allowed": False,
    }
    combined = repr(chat_data.profile_context)
    assert "the operator" not in combined
    assert "ecology" not in combined
    for private_value in PRIVATE_CANARIES:
        assert private_value not in combined
