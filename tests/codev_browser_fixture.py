"""Synthetic account/install/provider adapters around the real signed broker.

Only the disposable-XDG runner may start this fixture. Stdin/stdout contains
synthetic metadata and source; no operator account or production traffic.
"""
import json
import sys
from copy import deepcopy
from datetime import timedelta
import secrets
from uuid import uuid4

from scripts.assert_disposable_xdg import main as assert_disposable
assert_disposable()
from app.api import account_service, runtime_bridge
from core.codev import broker, pairing, sessions, browser_workspaces
from core.codev.contracts import Installation, BrowserPublicKey
from core.codev.grants import utc_now, GrantDenied
from core.codev.runtime_scope import current_context
from core.codev.installation import capability_manifest

principal = {"user_id": "synthetic-browser-local-profile", "session_id": "synthetic-browser-local-login"}
installation = Installation(state="installed_ready", installed=True, usable=True, version="1.0.0", capabilities=capability_manifest(usable=True), note="Synthetic browser qualification adapter.")
account_service.get_authenticated_principal = lambda: principal.copy()
sessions._principal = lambda: principal.copy()
pairing._principal = lambda: principal.copy()
sessions.resolve_installation = lambda: installation
pairing.resolve_installation = lambda: installation
states, codes, natives = {}, {}, {}
cloud_calls, model_contexts = [], []
proposed_edits = {}


def online(origin, route, payload):
    cloud_calls.append(route)
    pair_id = codes[payload["code"]] if route == "claim" else payload["pairing_id"]
    state = states[pair_id]
    assert origin == state["intent"]["origin"]
    if route == "claim":
        assert state["native_public_key"] is None
        state["native_public_key"] = payload["native_public_key"]
    elif payload["action"] == "confirm":
        state["intent"]["status"] = "native_approved"
        state["intent"]["expires_at"] = (utc_now()+timedelta(minutes=15)).isoformat()
    elif payload["action"] in {"deny", "revoke"}:
        state["intent"]["status"] = "revoked"
    return deepcopy(state)


def model_response(payload):
    context = current_context()
    model_contexts.append({"files": [item.path for item in context.files], "inventory": context.handoff, "edit_proposal": context.edit_proposal})
    if proposed_edits:
        response = json.dumps({"summary": "Synthetic provider proposes a focused improvement", "edits": proposed_edits})
    else:
        response = "Synthetic provider review: only selected development context was available. No tests or publication approval occurred."
    return {"data": {"invocation_status": "ok", "response_source": "live_invoker", "response_text": response,
                     "selected_model_runtime_tag": "synthetic-provider-for-browser-test"}}


pairing._online = online
runtime_bridge.send_chat_request = model_response
print(json.dumps({"fixture_ready": True}), flush=True)
try:
    for line in sys.stdin:
        command = json.loads(line)
        op = command["op"]
        if op in {"pair", "create"}:
            public_key = BrowserPublicKey.model_validate(command["key"])
            pair_id = str(uuid4())
            state = {"pairing_id": pair_id, "native_public_key": None, "workspace_grants": [], "intent": {
                "contract_version": "codev-pairing-1", "intent_id": pair_id, "online_account_id": command["account_id"],
                "account_label": "browser-fixture@example.invalid", "origin": "https://elysiaecobotics.com", "surface": command.get("surface", "forge"),
                "browser_session_id": command["browser_id"], "browser_public_key": public_key.model_dump(),
                "expires_at": (utc_now()+timedelta(minutes=5)).isoformat(), "status": "pending"}}
            states[pair_id] = state
            code = "EC1.A."+secrets.token_urlsafe(32)
            codes[code] = pair_id
            if op == "pair":
                native = sessions.open_native_session()
                natives[pair_id] = native.client_id
                pairing.claim(native.client_id, code)
                pairing.native_action(native.client_id, pair_id, "confirm", explicitly_approved=True)
                state["intent"]["status"] = "paired"
            print(json.dumps({"ok": True, "pairing": state, "manual_code": code}), flush=True)
        elif op == "approve":
            pair_id = codes[command["code"]]
            try:
                native = sessions.open_native_session()
                natives[pair_id] = native.client_id
                pairing.claim(native.client_id, command["code"])
                pairing.native_action(native.client_id, pair_id, "confirm", explicitly_approved=True)
                print(json.dumps({"ok": True, "pairing": states[pair_id]}), flush=True)
            except GrantDenied as error:
                print(json.dumps({"ok": False, "error": str(error)}), flush=True)
        elif op == "browser":
            state = states[command["pairing_id"]]
            assert state["intent"]["online_account_id"] == command["account_id"]
            assert state["intent"]["browser_session_id"] == command["browser_id"]
            action = command["action"]
            if action == "finish":
                assert state["intent"]["status"] in {"native_approved", "paired"}
                state["intent"]["status"] = "paired"
            elif action == "revoke":
                state["intent"]["status"] = "revoked"
            print(json.dumps({"ok": True, "pairing": state}), flush=True)
        elif op == "configure":
            if "installed" in command:
                value = command["installed"]
                installation = Installation(state="installed_ready" if value else "absent", installed=value, usable=value, version="1.0.0" if value else None, capabilities=capability_manifest(usable=value), note="Synthetic test installation state.")
            proposed_edits = command.get("edits", proposed_edits)
            print(json.dumps({"ok": True}), flush=True)
        elif op == "counts":
            print(json.dumps({"requests": len(broker._SERVER.requests) if broker._SERVER else 0, "cloud_calls": len(cloud_calls),
                "workspaces": [{"id": value.share.workspace_id, "files": [item.path for item in value.share.files if item.text is not None]} for value in browser_workspaces._WORKSPACES.values()],
                "model_contexts": model_contexts}), flush=True)
        elif op == "stop":
            break
        else:
            raise ValueError("unknown_fixture_command")
finally:
    broker.stop_broker()
