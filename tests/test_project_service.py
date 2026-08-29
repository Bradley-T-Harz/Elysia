from __future__ import annotations

import app.api.artifact_service as artifact_service
import app.api.account_service as account_service
import app.api.conversation_service as conversation_service
import app.api.project_service as project_service
import pytest
from app.api.account_service import AccountPaths, AccountStore
from app.api.schemas.account import AccountCreateRequest, AccountLoginRequest
from app.memory.canonical_models import MemoryCreateRequest, MemoryPrincipal
from app.memory.canonical_repository import MemoryRepository
from app.memory.fabric_service import MemoryFabricService
from app.api.artifact_service import create_data_summary_artifact
from tests.test_artifact_service import completed_data_execution_payload, write_file


def _patch_project_store(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setattr(project_service, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(
        project_service,
        "ACTIVE_PROJECT_PATH",
        projects_dir / "_active_project.json",
    )
    monkeypatch.setattr(conversation_service, "CONVERSATIONS_DIR", tmp_path / "conversations")


def test_project_continuity_summary_includes_manual_fields_and_artifacts(
    monkeypatch,
    tmp_path,
):
    _patch_project_store(monkeypatch, tmp_path)
    artifact_root = tmp_path / "artifacts"
    monkeypatch.setattr(artifact_service, "DEFAULT_ARTIFACT_ROOT", artifact_root)

    project = project_service.create_project(
        name="Chunk 3",
        description="Finishline Chunk 3 continuity work.",
    )
    project_id = project["project_id"]
    project_service.update_project_metadata(
        project_id,
        current_state="Chunk 3 implementation is underway.",
        latest_chunk="Finishline Chunk 3",
        milestones=[{"label": "Chunk 2 completed", "status": "complete"}],
        blockers=[{"label": "Live SearXNG may be unavailable"}],
        next_actions=[{"label": "Wire artifact plane"}],
    )

    source_csv = write_file(tmp_path / "sites.csv", "site,value\nA,1\n")
    artifact = create_data_summary_artifact(
        completed_data_execution_payload(source_csv),
        request_id="req_project_artifact",
        project_id=project_id,
        artifact_root=artifact_root,
    )

    continuity = project_service.build_project_continuity_summary(project_id)

    assert continuity["project_id"] == project_id
    assert continuity["current_state"] == "Chunk 3 implementation is underway."
    assert continuity["latest_chunk"] == "Finishline Chunk 3"
    assert continuity["recent_milestones"][0]["label"] == "Chunk 2 completed"
    assert continuity["open_blockers"][0]["label"] == "Live SearXNG may be unavailable"
    assert continuity["next_suggested_actions"][0]["label"] == "Wire artifact plane"
    assert artifact.artifact_id in continuity["linked_artifact_ids"]
    assert continuity["artifacts_are_memory"] is False
    assert continuity["sealed_private_memory_used"] is False


def test_conversation_project_and_active_selection_are_account_isolated(
    monkeypatch, tmp_path
):
    identity = tmp_path / "profile" / "identity"
    store = AccountStore(
        AccountPaths(
            identity_root=identity,
            database_path=identity / "elysia_identity.sqlite",
            profile_photo_dir=identity / "profile_photos",
            current_session_path=identity / "current_session.json",
        )
    )
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    projects_dir = store.elysia_paths.project_dir
    monkeypatch.setattr(project_service, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(
        project_service, "ACTIVE_PROJECT_PATH", projects_dir / "_active_project.json"
    )
    monkeypatch.setattr(
        conversation_service,
        "CONVERSATIONS_DIR",
        store.elysia_paths.conversation_dir,
    )

    store.create_account(
        AccountCreateRequest(username="alpha-domain", password="alpha domain password")
    )
    alpha_project = project_service.create_project(name="Alpha project")
    alpha_conversation = conversation_service.ensure_conversation(
        title="Alpha conversation", project_id=alpha_project["project_id"]
    )
    project_service.select_active_project(alpha_project["project_id"])
    alpha_id = store.state().active_user_id
    assert alpha_project["owner_user_id"] == alpha_id
    assert alpha_conversation.owner_user_id == alpha_id

    store.create_account(
        AccountCreateRequest(username="beta-domain", password="beta domain password")
    )
    # Additional local profile creation is not an implicit session switch.
    store.login(
        AccountLoginRequest(username="beta-domain", password="beta domain password")
    )
    assert project_service.list_projects() == []
    assert conversation_service.list_conversations() == []
    assert project_service.get_active_project_selection()["active_project_id"] is None
    with pytest.raises(project_service.ProjectNotFoundError):
        project_service.get_project_metadata(alpha_project["project_id"])
    with pytest.raises(conversation_service.ConversationNotFoundError):
        conversation_service.get_conversation_metadata(
            alpha_conversation.conversation_id
        )

    beta_project = project_service.create_project(name="Beta project")
    assert beta_project["owner_user_id"] == store.state().active_user_id
    store.logout()
    store.login(
        AccountLoginRequest(username="alpha-domain", password="alpha domain password")
    )
    assert [item["project_id"] for item in project_service.list_projects()] == [
        alpha_project["project_id"]
    ]
    assert project_service.get_active_project_selection()["active_project_id"] == alpha_project[
        "project_id"
    ]


def test_memory_links_existing_project_and_conversation_by_stable_id(monkeypatch, tmp_path):
    identity = tmp_path / "profile" / "identity"
    store = AccountStore(
        AccountPaths(
            identity_root=identity,
            database_path=identity / "elysia_identity.sqlite",
            profile_photo_dir=identity / "profile_photos",
            current_session_path=identity / "current_session.json",
        )
    )
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    monkeypatch.setattr(project_service, "PROJECTS_DIR", store.elysia_paths.project_dir)
    monkeypatch.setattr(
        project_service,
        "ACTIVE_PROJECT_PATH",
        store.elysia_paths.project_dir / "_active_project.json",
    )
    monkeypatch.setattr(
        conversation_service,
        "CONVERSATIONS_DIR",
        store.elysia_paths.conversation_dir,
    )
    store.create_account(
        AccountCreateRequest(username="link-owner", password="link owner password")
    )
    project = project_service.create_project(name="Authority project")
    conversation = conversation_service.ensure_conversation(
        title="Authority conversation", project_id=project["project_id"]
    )
    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    fabric = MemoryFabricService(
        repository=MemoryRepository(paths=store.elysia_paths)
    )
    record = fabric.create(
        principal,
        MemoryCreateRequest(
            title="Continuity pointer",
            body="A compact user-declared continuity fact.",
            why_stored="Link authority objects without copying them.",
            scope="project",
            project_id=project["project_id"],
            conversation_id=conversation.conversation_id,
        ),
    )
    targets = {(relation["target_type"], relation["target_id"]) for relation in record.relations}
    assert targets == {
        ("project", project["project_id"]),
        ("conversation", conversation.conversation_id),
    }
    with fabric.repository.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_relations").fetchone()[0] == 2
    assert "Authority conversation" not in fabric.repository.database_path.read_text(
        encoding="utf-8", errors="ignore"
    )
