"""Real signatures and local sockets; cloud login behavior is separately tested in PostgreSQL."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from http.client import HTTPConnection
import json
import secrets
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import account_service
from core.codev import broker, broker_crypto as crypto, pairing, sessions, browser_workspaces as browser
from core.codev.contracts import BrokerProof, Installation, WorkspaceFile
from core.codev.grants import GRANTS, GrantDenied, utc_now
from core.codev.revisions import workspace_hash


@pytest.fixture
def fixture(monkeypatch):
    principal = {"user_id": "synthetic-local-account", "session_id": "local-login-a"}
    install = Installation(state="installed_ready", installed=True, usable=True, version="1.0.0", note="Synthetic installed adapter.")
    monkeypatch.setattr(sessions, "_principal", lambda: principal.copy())
    monkeypatch.setattr(pairing, "_principal", lambda: principal.copy())
    monkeypatch.setattr(account_service, "get_authenticated_principal", lambda: principal.copy())
    monkeypatch.setattr(sessions, "resolve_installation", lambda: install)
    monkeypatch.setattr(pairing, "resolve_installation", lambda: install)
    native = sessions.open_native_session()
    browser_key = crypto.new_key()
    data = {"pairing_id": str(uuid4()), "native_public_key": None, "workspace_grants": [], "intent": {
        "contract_version": "codev-pairing-1", "intent_id": "", "online_account_id": str(uuid4()), "account_label": "fixture@example.invalid",
        "origin": pairing.ORIGINS[0], "surface": "forge", "browser_session_id": secrets.token_urlsafe(32),
        "browser_public_key": crypto.public_key(browser_key).model_dump(), "expires_at": (utc_now()+timedelta(minutes=5)).isoformat(), "status": "pending"}}
    data["intent"]["intent_id"] = data["pairing_id"]
    calls = []
    active = [True]
    def online(origin, route, payload):
        calls.append((origin, route, set(payload)))
        assert origin == data["intent"]["origin"]
        if not active[0]:
            raise GrantDenied("fixture_cloud_account_revoked")
        if route == "claim":
            assert data["native_public_key"] is None
            data["native_public_key"] = payload["native_public_key"]
        elif payload["action"] == "confirm":
            assert data["intent"]["status"] == "pending"
            data["intent"]["status"] = "native_approved"
        elif payload["action"] in {"revoke", "deny"}:
            data["intent"]["status"] = "revoked"
        return deepcopy(data)
    monkeypatch.setattr(pairing, "_online", online)
    broker.stop_broker(); pairing._PAIRS.clear()
    code = "EC1.A." + secrets.token_urlsafe(32)
    state = SimpleNamespace(principal=principal, install=install, native=native, browser_key=browser_key,
        data=data, calls=calls, active=active, code=code)
    yield state
    broker.stop_broker()
    for pair in list(pairing._PAIRS.values()): pairing._revoke_local(pair)
    pairing._PAIRS.clear()


def connect(state):
    claimed = pairing.claim(state.native.client_id, state.code)
    pairing.native_action(state.native.client_id, claimed["pairing_id"], "confirm", explicitly_approved=True)
    state.data["intent"]["status"] = "paired"
    return pairing.get(claimed["pairing_id"])


def envelope(state, pair, path, payload, *, origin=None, nonce=None, timestamp=None, key=None):
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    proof = BrokerProof(pairing_id=pair.intent.intent_id, browser_session_id=pair.intent.browser_session_id,
        online_account_id=pair.intent.online_account_id, nonce=nonce or secrets.token_urlsafe(32),
        timestamp_ms=timestamp or int(utc_now().timestamp()*1000), signature="a"*86)
    proof.signature = crypto.sign(key or state.browser_key, crypto.request_message(origin or pair.intent.origin, path, proof, body))
    return {"proof": proof.model_dump(), "payload_json": body}


def http_call(path, value=None, *, method="POST", headers=None):
    connection = HTTPConnection("127.0.0.1", 47321, timeout=8)
    raw = json.dumps(value).encode() if value is not None else None
    connection.request(method, path, body=raw, headers={"Origin": pairing.ORIGINS[0], "Content-Type": "application/json", **(headers or {})})
    response = connection.getresponse()
    result = (response.status, dict(response.getheaders()), response.read())
    connection.close()
    return result


def shared(state, pair, *, scopes=None):
    source = "answer = 42\n"
    files = [WorkspaceFile(path="main.py", size_bytes=len(source), content_hash=sha256(source.encode()).hexdigest(),
        text=source, availability="text", provenance="editor"),
        WorkspaceFile(path="binary.bin", size_bytes=10, content_hash=sha256(b"0123456789").hexdigest(), availability="metadata_only", provenance="intake")]
    value = {"workspace_id": "workspace_"+uuid4().hex, "surface": "forge", "draft_id": str(uuid4()), "label": "Synthetic browser draft",
        "base_revision": 0, "current_revision": 3, "content_hash": workspace_hash(files), "files": [item.model_dump() for item in files],
        "scopes": scopes or ["read", "propose"], "expected_epoch": 0, "explicitly_approved": True}
    return value, browser.dispatch(pair, "/codev/workspace/share", value)


def test_installation_then_separate_native_confirmation_and_zero_workspace_grants(fixture):
    state = fixture
    state.install.usable = False
    with pytest.raises(GrantDenied): pairing.claim(state.native.client_id, state.code)
    assert not state.calls
    state.install.usable = True
    claimed = pairing.claim(state.native.client_id, state.code)
    pair = pairing.get(claimed["pairing_id"])
    assert claimed["workspace_grants"] == [] and not browser._WORKSPACES
    assert claimed["intent"]["status"] == "pending" and broker._SERVER is None
    with pytest.raises(GrantDenied): pairing.native_action(state.native.client_id, pair.intent.intent_id, "confirm")
    assert broker._SERVER is None
    pairing.native_action(state.native.client_id, pair.intent.intent_id, "confirm", explicitly_approved=True)
    assert pairing.browser_status(pair)["status"] == "native_approved"
    assert not browser._WORKSPACES and not any(grant.actor == pair.actor for grant in GRANTS._grants.values())
    with pytest.raises(GrantDenied): shared(state, pair)
    assert pair.revoked  # Consequential work before browser finish fails closed.


def test_real_http_signed_status_replay_and_impostor_refusal(fixture):
    state = fixture; pair = connect(state); path = "/codev/status"
    request = envelope(state, pair, path, {})
    status, headers, raw = http_call(path, request)
    assert status == 200 and headers["Access-Control-Allow-Origin"] == pair.intent.origin
    response = json.loads(raw)
    assert crypto.verify(crypto.public_key(pair.private_key), crypto.response_message(pair.intent.origin, path,
        BrokerProof.model_validate(request["proof"]), request["payload_json"], response["payload_json"]), response["signature"])
    data = json.loads(response["payload_json"])
    assert data["data"]["session"]["workspace_grants"] == []
    assert pair.native_secret not in raw.decode()
    assert http_call(path, request)[0] == 403
    assert http_call(path, envelope(state, pair, path, {}, key=crypto.new_key()))[0] == 403
    assert http_call(path, envelope(state, pair, path, {}, timestamp=int((utc_now()-timedelta(minutes=2)).timestamp()*1000)))[0] == 403
    modified = envelope(state, pair, path, {}); modified["payload_json"] = '{"workspace_id":"forged"}'
    assert http_call(path, modified)[0] == 403
    assert http_call("/codev/revoke", envelope(state, pair, path, {}))[0] == 403


@pytest.mark.parametrize("headers", [{"Host":"localhost:47321"}, {"Host":"attacker.invalid:47321"}, {"Origin":"null"},
    {"Origin":"https://attacker.invalid"}, {"Origin":"https://elysiaecobotics.com.attacker.invalid"},
    {"Authorization":"Bearer native-credential"}, {"Cookie":"native=credential"}, {"Content-Type":"text/plain"}])
def test_transport_refuses_unapproved_boundaries_without_cloud_contact(fixture, headers):
    state = fixture; pair = connect(state); before = len(state.calls)
    assert http_call("/codev/status", envelope(state, pair, "/codev/status", {}), headers=headers)[0] == 403
    assert len(state.calls) == before


def test_preflight_is_narrow_no_install_probe_and_no_native_api_proxy(fixture):
    state = fixture; connect(state); before = len(state.calls)
    status, headers, raw = http_call("/codev/status", method="OPTIONS", headers={"Access-Control-Request-Method":"POST", "Access-Control-Request-Headers":"content-type", "Access-Control-Request-Private-Network":"true"})
    assert status == 204 and not raw and headers["Access-Control-Allow-Private-Network"] == "true"
    assert len(state.calls) == before
    for path in ["/coding", "/codev/status?token=x", "/api/account", "/codev/commands/start", "http://attacker.invalid/codev/status"]:
        assert http_call(path, {})[0] == 403
    assert http_call("/codev/status", method="GET")[0] == 501
    assert http_call("/codev/status", method="OPTIONS", headers={"Access-Control-Request-Method":"POST", "Access-Control-Request-Headers":"authorization"})[0] == 403


def test_browser_share_revision_grants_and_exact_single_use_patch(fixture):
    state = fixture; pair = connect(state)
    source, shared_state = shared(state, pair)
    assert shared_state["shared_files"] == ["main.py"]
    assert not shared_state["native_filesystem_granted"] and not shared_state["commands_granted"] and not shared_state["network_granted"]
    revision = {"workspace_id": source["workspace_id"], "revision": source["current_revision"], "content_hash":source["content_hash"], "grant_epoch":shared_state["grant"]["epoch"]}
    with pytest.raises(GrantDenied): browser.dispatch(pair, "/codev/patch/plan", {**revision, "summary":"Forbidden", "edits":{"binary.bin":"guessed"}})
    with pytest.raises(GrantDenied): browser.dispatch(pair, "/codev/patch/plan", {**revision, "revision":2, "summary":"Stale", "edits":{"main.py":"answer = 43\n"}})
    plan = browser.dispatch(pair, "/codev/patch/plan", {**revision, "summary":"Exact example", "edits":{"main.py":"answer = 43\n"}})["plan"]
    approval = {**revision,"plan_id":plan["plan_id"],"plan_hash":plan["plan_hash"],"explicitly_approved":True}
    with pytest.raises(GrantDenied): browser.dispatch(pair, "/codev/patch/authorize", {**approval,"explicitly_approved":False})
    result = browser.dispatch(pair, "/codev/patch/authorize", approval)
    assert result["approval"]["consumed"] and result["approval"]["operation"] == "browser_patch"
    assert result["receipt"]["status"] == "approved" and result["receipt"]["files_changed"] == []
    assert browser._workspace(pair.actor, source["workspace_id"]).share.files[0].text == "answer = 42\n"
    with pytest.raises(GrantDenied): browser.dispatch(pair, "/codev/patch/authorize", approval)
    browser.dispatch(pair, "/codev/workspace/revoke", {"workspace_id":source["workspace_id"]})
    assert GRANTS.get(pair.actor, source["workspace_id"]).revoked
    with pytest.raises(GrantDenied): browser.dispatch(pair, "/codev/workspace/status", {"workspace_id":source["workspace_id"]})


@pytest.mark.parametrize("response_kind", ["conversation", "edit_proposal"])
@pytest.mark.parametrize("change", ["logout", "uninstall", "cloud_revoke"])
def test_revocation_withholds_inflight_cognition_and_clears_shared_source(fixture, monkeypatch, change, response_kind):
    from app.api import runtime_bridge
    from core.codev.runtime_scope import current_context
    state = fixture; pair = connect(state); source, shared_state = shared(state, pair)
    def respond(payload):
        assert current_context().files[0].text == "answer = 42\n"
        assert len(current_context().files) == 1 and "browser file inventory" in current_context().handoff
        if change == "logout": state.principal["session_id"] = "replacement-login"
        elif change == "uninstall": state.install.usable = False
        else: state.active[0] = False
        return {"data":{"invocation_status":"ok", "response_source":"live_invoker", "response_text":"WITHHELD_CANARY"}}
    monkeypatch.setattr(runtime_bridge, "send_chat_request", respond)
    with pytest.raises(GrantDenied): browser.dispatch(pair, "/codev/chat", {"workspace_id":source["workspace_id"], "revision":3,
        "content_hash":source["content_hash"], "grant_epoch":shared_state["grant"]["epoch"], "message":"Explain",
        "response_kind":response_kind, "request_id":"codev_"+uuid4().hex})
    pairing.revoke_unavailable_pairs()
    assert not any(value.actor == pair.actor for value in browser._WORKSPACES.values())


@pytest.mark.parametrize("output", [
    {"summary": "Exact edit", "edits": {"main.py": "answer = 43\n"}},
    {"summary": {}, "edits": {"main.py": "answer = 43\n"}},
    {"summary": "Wrong scope", "edits": {"unselected.py": "DO_NOT_RETURN"}},
])
def test_structured_proposal_validates_model_output_without_authorizing_mutation(fixture, monkeypatch, output):
    from app.api import runtime_bridge
    from core.codev.runtime_scope import current_context
    state = fixture; pair = connect(state); source, shared_state = shared(state, pair)
    selected_path = source["files"][0]["path"]
    if "main.py" in output["edits"]:
        output = {**output, "edits": {selected_path: output["edits"]["main.py"]}}
    def respond(payload):
        assert current_context().edit_proposal
        return {"data": {"invocation_status": "ok", "response_source": "live_invoker", "response_text": json.dumps(output)}}
    monkeypatch.setattr(runtime_bridge, "send_chat_request", respond)
    result = browser.dispatch(pair, "/codev/chat", {"workspace_id":source["workspace_id"], "revision":3,
        "content_hash":source["content_hash"], "grant_epoch":shared_state["grant"]["epoch"], "message":"Propose",
        "response_kind":"edit_proposal", "request_id":"codev_"+uuid4().hex})
    valid = isinstance(output["summary"], str) and set(output["edits"]) == {selected_path}
    assert result["receipt"]["status"] == ("completed" if valid else "blocked")
    assert "DO_NOT_RETURN" not in result["response_text"]
    assert browser._workspace(pair.actor, source["workspace_id"]).share.files[0].text == "answer = 42\n"


def test_structured_proposal_requires_propose_grant_before_model_access(fixture, monkeypatch):
    from app.api import runtime_bridge
    state = fixture; pair = connect(state); source, shared_state = shared(state, pair, scopes=["read"])
    monkeypatch.setattr(runtime_bridge, "send_chat_request", lambda *_: pytest.fail("Read-only grant accessed proposal model path"))
    with pytest.raises(GrantDenied):
        browser.dispatch(pair, "/codev/chat", {"workspace_id":source["workspace_id"], "revision":3,
            "content_hash":source["content_hash"], "grant_epoch":shared_state["grant"]["epoch"], "message":"Propose",
            "response_kind":"edit_proposal", "request_id":"codev_"+uuid4().hex})


def test_native_revoke_succeeds_even_when_cloud_is_down(fixture):
    state = fixture; pair = connect(state); shared(state, pair); state.active[0] = False
    result = pairing.native_action(state.native.client_id, pair.intent.intent_id, "revoke")
    assert result["local_revoked"] and not result["cloud_revoked"] and pair.revoked
    assert not any(value.actor == pair.actor for value in browser._WORKSPACES.values())


def test_port_is_exclusive_and_request_rate_is_bounded(fixture):
    state = fixture; pair = connect(state)
    with pytest.raises(OSError): broker._Server()
    for _ in range(60):
        request = envelope(state, pair, "/codev/status", {})
        pairing.authenticate(pair.intent.origin, "/codev/status", BrokerProof.model_validate(request["proof"]), request["payload_json"])
    request = envelope(state, pair, "/codev/status", {})
    with pytest.raises(GrantDenied, match="rate_limit"):
        pairing.authenticate(pair.intent.origin, "/codev/status", BrokerProof.model_validate(request["proof"]), request["payload_json"])


def test_duplicate_headers_oversize_and_duplicate_json_fail_before_cloud(fixture):
    state = fixture; pair = connect(state); before = len(state.calls)
    connection = HTTPConnection("127.0.0.1", 47321, timeout=8)
    connection.putrequest("POST", "/codev/status")
    connection.putheader("Origin", pairing.ORIGINS[0]); connection.putheader("Origin", pairing.ORIGINS[0])
    connection.putheader("Content-Type", "application/json"); connection.putheader("Content-Length", "2")
    connection.endheaders(b"{}")
    response = connection.getresponse(); assert response.status == 403; response.read(); connection.close()
    assert http_call("/codev/status", {}, headers={"Content-Length":str(broker.POLICY.max_body_bytes+1)})[0] == 403
    request = envelope(state, pair, "/codev/status", {})
    request["payload_json"] = '{"same":1,"same":2}'
    assert http_call("/codev/status", request)[0] == 403
    assert len(state.calls) == before


def test_refresh_reset_revokes_source_but_preserves_epoch_tombstones(fixture):
    state = fixture; pair = connect(state); source, shared_state = shared(state, pair)
    revision = {"workspace_id":source["workspace_id"],"revision":3,"content_hash":source["content_hash"],"grant_epoch":shared_state["grant"]["epoch"]}
    plan = browser.dispatch(pair,"/codev/patch/plan",{**revision,"summary":"Pending old plan","edits":{"main.py":"answer = 43\n"}})["plan"]
    reset = browser.dispatch(pair,"/codev/workspace/reset",{})
    assert reset["workspace_grants"] == [] and reset["grant_epochs"][source["workspace_id"]] == 2
    assert not any(value.actor == pair.actor for value in browser._WORKSPACES.values())
    with pytest.raises(GrantDenied): browser.dispatch(pair,"/codev/workspace/share",source)
    renewed = browser.dispatch(pair,"/codev/workspace/share",{**source,"expected_epoch":2})
    assert renewed["grant"]["epoch"] == 3
    with pytest.raises(GrantDenied):
        browser.dispatch(pair,"/codev/patch/authorize",{**revision,"grant_epoch":3,"plan_id":plan["plan_id"],"plan_hash":plan["plan_hash"],"explicitly_approved":True})
