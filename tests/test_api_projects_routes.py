from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
import app.api.conversation_service as conversation_service
import app.api.project_service as project_service
from app.api.main import create_app
from app.api.routes.conversations import patch_one_conversation
from app.api.routes.projects import get_one_project
from app.api.schemas.conversation_mutation import ConversationUpdateRequest
from tests.asgi_test_client import ASGITestClient


def _patch_local_stores(monkeypatch, tmp_path) -> None:
    projects_dir = tmp_path / "projects"
    monkeypatch.setattr(
        conversation_service,
        "CONVERSATIONS_DIR",
        tmp_path / "conversations",
    )
    monkeypatch.setattr(project_service, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(
        project_service,
        "ACTIVE_PROJECT_PATH",
        projects_dir / "_active_project.json",
    )


def _client_with_project_store(monkeypatch, tmp_path) -> ASGITestClient:
    _patch_local_stores(monkeypatch, tmp_path)
    return ASGITestClient(create_app())


def test_project_continuity_route_returns_hybrid_summary(monkeypatch, tmp_path):
    client = _client_with_project_store(monkeypatch, tmp_path)

    create_response = client.post(
        "/projects",
        json={"name": "Chunk 3", "description": "Continuity test"},
    )
    assert create_response.status_code == 200
    project_id = create_response.json()["data"]["project_id"]

    patch_response = client.patch(
        f"/projects/{project_id}",
        json={
            "current_state": "Phase 7 is being tested.",
            "latest_chunk": "Finishline Chunk 3",
            "milestones": [{"label": "Project continuity route exists"}],
            "blockers": [{"label": "No blocker in this test"}],
            "next_actions": [{"label": "Run focused tests"}],
        },
    )
    assert patch_response.status_code == 200

    response = client.get(f"/projects/{project_id}/continuity")
    assert response.status_code == 200
    payload = response.json()

    assert payload["result_type"] == "project_continuity"
    continuity = payload["data"]["continuity_summary"]
    assert continuity["project_id"] == project_id
    assert continuity["current_state"] == "Phase 7 is being tested."
    assert continuity["latest_chunk"] == "Finishline Chunk 3"
    assert continuity["recent_milestones"][0]["label"] == "Project continuity route exists"
    assert continuity["attached_files_are_memory"] is False
    assert continuity["artifacts_are_memory"] is False


def test_moving_conversation_persists_linkage_and_surfaces_in_project_detail(
    monkeypatch,
    tmp_path,
):
    _patch_local_stores(monkeypatch, tmp_path)
    conversation_id = "conv_project_link_test"
    conversation_service.ensure_conversation(
        conversation_id,
        title="Project linkage conversation",
    )

    project = project_service.create_project(
        name="Test",
        description="Conversation linkage target",
    )
    project_id = project["project_id"]

    move_payload = asyncio.run(
        patch_one_conversation(
            conversation_id,
            ConversationUpdateRequest(project_id=project_id),
        )
    )
    assert move_payload["data"]["metadata"]["project_id"] == project_id
    assert (
        conversation_service.get_conversation_metadata(conversation_id).project_id
        == project_id
    )

    detail_payload = asyncio.run(
        get_one_project(
            project_id,
            include_archived_conversations=False,
            conversation_limit=None,
        )
    )
    detail = detail_payload["data"]
    assert detail["conversation_count"] == 1
    assert detail["metadata"]["conversation_count"] == 1
    assert [
        conversation["conversation_id"]
        for conversation in detail["related_conversations"]
    ] == [conversation_id]


def test_moving_conversation_rejects_unknown_project_without_changing_linkage(
    monkeypatch,
    tmp_path,
):
    _patch_local_stores(monkeypatch, tmp_path)
    conversation_id = "conv_missing_project_test"
    conversation_service.ensure_conversation(conversation_id, title="Still unassigned")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            patch_one_conversation(
                conversation_id,
                ConversationUpdateRequest(project_id="proj_does_not_exist"),
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Project 'proj_does_not_exist' was not found."
    assert conversation_service.get_conversation_metadata(conversation_id).project_id is None
