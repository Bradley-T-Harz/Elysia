from types import SimpleNamespace
from uuid import uuid4
from time import monotonic, sleep

import pytest

from core.codev import actions, sessions, workspaces
from core.codev.approvals import PLANS
from core.codev.grants import GrantDenied
from core.codev.runtime_scope import current_context
from tests.test_codev_native_workspace import fixture, share


def authenticated(monkeypatch, actor=None):
    from app.api import account_service
    principal = {"user_id": actor.local_profile_id if actor else "native-fixture", "session_id": "fixture-session"}
    monkeypatch.setattr(sessions, "_principal", lambda: principal.copy())
    monkeypatch.setattr(account_service, "get_authenticated_principal", lambda: principal.copy())
    monkeypatch.setattr(sessions, "resolve_installation", lambda: SimpleNamespace(usable=True, installation_id="a" * 64))
    return principal


def test_native_sessions_require_installation_and_exact_login_session(monkeypatch):
    principal = authenticated(monkeypatch)
    actor = sessions.open_native_session()
    assert sessions.require_native_session(actor.client_id) == actor
    principal["session_id"] = "replacement-session"
    with pytest.raises(GrantDenied, match="account_changed"):
        sessions.require_native_session(actor.client_id)
    principal["session_id"] = "fixture-session"
    monkeypatch.setattr(sessions, "resolve_installation", lambda: SimpleNamespace(usable=False))
    with pytest.raises(GrantDenied, match="installation"):
        sessions.open_native_session()
    with pytest.raises(GrantDenied, match="installation"):
        sessions.require_native_session(actor.client_id)
    assert sessions.require_native_session(actor.client_id, revocation_only=True) == actor


def test_chat_uses_only_selected_context_and_whitelists_response(tmp_path, monkeypatch):
    from app.api import runtime_bridge
    root, actor, workspace_id = fixture(tmp_path)
    authenticated(monkeypatch, actor)
    share(actor, workspace_id)
    begin = monotonic()
    def respond(payload):
        assert payload["requested_mode"] == "coder"
        assert [item.path for item in current_context().files] == ["main.py"]
        assert current_context().handoff == "Explicit context"
        assert begin < current_context().deadline_monotonic <= monotonic() + actions.CHAT_BUDGET_SECONDS
        return {"data": {"invocation_status": "ok", "response_source": "live_invoker", "response_text": "Answer",
                         "personal_canary": "PRIVATE", "selected_model_runtime_tag": "fixture-local"}}
    monkeypatch.setattr(runtime_bridge, "send_chat_request", respond)
    result = actions.chat(actor, workspace_id=workspace_id, message="Explain", request_id="codev_" + uuid4().hex,
                          handoff="Explicit context")
    assert result["response_text"] == "Answer" and "PRIVATE" not in str(result)
    assert result["receipt"]["files_inspected"] == ["main.py"]
    assert not result["receipt"]["network_used"] and result["receipt"]["tests_run"] == []
    assert current_context() is None


def test_completed_provider_content_is_withheld_after_whole_request_deadline(tmp_path, monkeypatch):
    from app.api import runtime_bridge
    root, actor, workspace_id = fixture(tmp_path)
    authenticated(monkeypatch, actor)
    share(actor, workspace_id)
    now = [100.0]
    monkeypatch.setattr(actions, "monotonic", lambda: now[0])
    def respond(payload):
        assert current_context().deadline_monotonic == 310.0
        now[0] = 311.0
        return {"data": {"invocation_status": "ok", "response_source": "live_invoker", "response_text": "LATE"}}
    monkeypatch.setattr(runtime_bridge, "send_chat_request", respond)
    result = actions.chat(actor, workspace_id=workspace_id, message="Explain", request_id="codev_" + uuid4().hex)
    assert result["receipt"]["status"] == "blocked"
    assert "LATE" not in str(result)
    assert not actions._CHAT_OWNERS


@pytest.mark.parametrize("change", ["logout", "revoke"])
def test_response_is_withheld_after_session_change_or_grant_revocation(tmp_path, monkeypatch, change):
    from app.api import runtime_bridge
    root, actor, workspace_id = fixture(tmp_path)
    principal = authenticated(monkeypatch, actor)
    share(actor, workspace_id)
    def respond(payload):
        if change == "logout":
            principal["session_id"] = "new-login-same-user"
        else:
            workspaces.revoke_workspace(actor, workspace_id)
        return {"data": {"invocation_status": "ok", "response_source": "live_invoker", "response_text": "WITHHELD"}}
    monkeypatch.setattr(runtime_bridge, "send_chat_request", respond)
    with pytest.raises(GrantDenied):
        actions.chat(actor, workspace_id=workspace_id, message="Explain", request_id="codev_" + uuid4().hex)
    assert not actions._CHAT_OWNERS


def test_cancellation_is_owned_and_never_reports_completed_answer(tmp_path, monkeypatch):
    from app.api import runtime_bridge
    root, actor, workspace_id = fixture(tmp_path)
    authenticated(monkeypatch, actor)
    share(actor, workspace_id)
    request_id = "codev_" + uuid4().hex
    other = actor.model_copy(update={"client_id": "native_" + uuid4().hex})
    def respond(payload):
        with pytest.raises(GrantDenied):
            actions.cancel_chat(other, request_id)
        assert actions.cancel_chat(actor, request_id)["cancellation_requested"]
        return {"data": {"invocation_status": "ok", "response_source": "live_invoker", "response_text": "WITHHELD"}}
    monkeypatch.setattr(runtime_bridge, "send_chat_request", respond)
    result = actions.chat(actor, workspace_id=workspace_id, message="Explain", request_id=request_id)
    assert result["receipt"]["status"] == "cancelled"
    assert "WITHHELD" not in str(result)


def test_native_command_uses_exact_grant_and_real_process(tmp_path, monkeypatch):
    import subprocess
    root, actor, workspace_id = fixture(tmp_path)
    authenticated(monkeypatch, actor)
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    workspaces.grant_workspace(actor, workspace_id, scopes=["metadata", "read", "command"], files=["main.py"],
        command_ids=["git_diff_check"], expected_epoch=0, explicitly_approved=True)
    plan = actions.plan_command(actor, workspace_id, "git_diff_check")
    assert plan.command_argv[-4:] == ["diff", "--no-ext-diff", "--no-textconv", "--check"]
    assert "core.fsmonitor=false" in plan.command_argv
    approval, token = PLANS.approve(actor, plan.plan_id, plan.plan_hash, explicitly_approved=True)
    started = actions.start_command(actor, workspace_id, plan_id=plan.plan_id, approval_id=approval.approval_id, approval_token=token)
    deadline = monotonic() + 5
    while monotonic() < deadline:
        state = actions.command_status(actor, workspace_id, started["run_id"])
        if state["result"]:
            break
        sleep(0.02)
    assert state["receipt"]["status"] == "completed", state
    assert state["receipt"]["commands_run"] == [plan.command_argv]
    assert state["receipt"]["tests_run"] == []
    root.rename(tmp_path / "moved")
    assert actions.command_status(actor, workspace_id, started["run_id"])["receipt"]
    actions.cancel_command(actor, workspace_id, started["run_id"])
    assert workspaces.receipts(actor, workspace_id)


def test_native_transport_cannot_be_used_without_the_desktop_credential(tmp_path, monkeypatch):
    import asyncio
    import httpx
    from app.api.main import create_app
    from app.install.local_auth import LocalApiAuthPolicy
    from app.install.paths import RuntimeMode
    policy = LocalApiAuthPolicy(required=True, credential_path=tmp_path / "credential", runtime_mode=RuntimeMode.TEST,
                                source="test", expected_credential="synthetic-fixture-credential-" + "x" * 40)
    async def exercise():
        transport = httpx.ASGITransport(app=create_app(auth_policy=policy))
        async with httpx.AsyncClient(transport=transport, base_url="http://testclient") as client:
            for endpoint in ["session", "workspaces/select", "workspaces/snapshot", "grants/issue", "patches/apply", "chat", "chat/cancel", "commands/status", "receipts", "pairing/claim", "pairing/action", "pairing/list", "pairing/revoke"]:
                response = await client.post("/codev/" + endpoint, json={})
                assert response.status_code == 401, endpoint
                assert not response.json()["data"]["credential_exposed"]
    asyncio.run(exercise())
