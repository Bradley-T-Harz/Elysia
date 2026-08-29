from __future__ import annotations

from app.api.routes import coding as coding_routes
from app.api.schemas.coding import CodingChatRequest, CodingSessionStartRequest, RepoInspectPreviewRequest


def test_coding_routes_are_registered_on_local_bridge():
    from app.api.main import create_app

    app = create_app()
    paths = set(app.openapi()["paths"])

    assert "/coding/status" in paths
    assert "/coding/file-types" in paths
    assert "/coding/file/inspect-type" in paths
    assert "/coding/session/start" in paths
    assert "/coding/chat" in paths
    assert "/coding/repo/inspect-preview" in paths
    assert "/coding/file/read-preview" in paths
    assert "/coding/patch/propose" in paths
    assert "/coding/file/operation-plan" in paths
    assert "/coding/operation/approve" in paths
    assert "/coding/command/plan" in paths
    assert "/coding/git/preview" in paths
    assert "/coding/task/plan" in paths


async def _await_payload(coro):
    return await coro


def test_coding_status_route_exposes_disabled_dangerous_capabilities():
    import asyncio

    payload = asyncio.run(_await_payload(coding_routes.get_coding_status()))
    bridge = payload["data"]["coding_bridge"]

    assert payload["status"] == "ok"
    assert bridge["boundaries"]["local_only"] is True
    assert bridge["boundaries"]["selected_file_read_allowed"] is True
    assert bridge["boundaries"]["patch_proposal_allowed"] is True
    assert bridge["boundaries"]["patch_apply_allowed"] is True
    assert bridge["boundaries"]["command_execution_allowed"] is True
    assert "git_mutation" in bridge["disabled_capabilities"]


def test_coding_session_and_chat_routes_are_planning_only():
    import asyncio

    session_payload = asyncio.run(
        _await_payload(
            coding_routes.post_coding_session_start(
                CodingSessionStartRequest(workspace_label="Workspace", approval_mode="plan_only")
            )
        )
    )
    session = session_payload["data"]["session"]
    chat_payload = asyncio.run(
        _await_payload(
            coding_routes.post_coding_chat(
                CodingChatRequest(session_id=session["session_id"], message="Help me inspect this code.")
            )
        )
    )
    chat = chat_payload["data"]["coding_chat"]

    assert chat["session_id"] == session["session_id"]
    assert "will not mutate files" in chat["assistant_text"]
    assert "does not yet have a general coding-reasoning model" in chat["assistant_text"]
    assert "command_execution" in chat["refused_capabilities"]
    assert chat["boundaries"]["source_contents_included"] is False


def test_repo_inspect_preview_ignores_private_generated_paths(tmp_path):
    import asyncio

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("SECRET_SOURCE = True\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "identity").mkdir()

    payload = asyncio.run(
        _await_payload(
            coding_routes.post_repo_inspect_preview(
                RepoInspectPreviewRequest(workspace_root=str(tmp_path), max_depth=3, max_entries=50)
            )
        )
    )
    preview = payload["data"]["repo_preview"]
    paths = {entry["relative_path"] for entry in preview["preview_entries"]}

    assert "src" in paths
    assert "src/app.py" in paths
    assert ".git" not in paths
    assert "node_modules" not in paths
    assert ".env" not in paths
    assert "data/identity" not in paths
    assert preview["source_contents_included"] is False
    assert preview["files_read"] == []
    assert "SECRET_SOURCE" not in repr(preview)
