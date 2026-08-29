from __future__ import annotations

from pathlib import Path

import pytest

from app.api import account_service, conversation_service, project_service
from app.api.account_service import AccountPaths, AccountStore
from app.api.schemas.account import AccountCreateRequest
from app.cognition.conversation_cognition import build_conversation_hierarchy
from app.cognition.evidence_repository import EvidenceRepository
from app.cognition.workspace import build_global_working_workspace
from app.install.paths import resolve_elysia_paths
from app.memory.canonical_models import MemoryCreateRequest, MemoryPrincipal
from app.memory.canonical_repository import MemoryRepository
from app.memory.fabric_service import MemoryFabricService


def _environment(tmp_path: Path, monkeypatch):
    for key, leaf in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_RUNTIME_DIR", "runtime"),
    ):
        target = tmp_path / leaf
        target.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(key, str(target))
    paths = resolve_elysia_paths()
    identity = paths.data_dir / "identity"
    store = AccountStore(
        AccountPaths(
            identity_root=identity,
            database_path=identity / "elysia_identity.sqlite",
            profile_photo_dir=identity / "profile_photos",
            current_session_path=identity / "current_session.json",
            elysia_paths=paths,
        )
    )
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    monkeypatch.setattr(conversation_service, "CONVERSATIONS_DIR", paths.conversation_dir)
    monkeypatch.setattr(project_service, "PROJECTS_DIR", paths.project_dir)
    monkeypatch.setattr(
        project_service,
        "ACTIVE_PROJECT_PATH",
        paths.project_dir / "_active_project.json",
    )
    store.create_account(
        AccountCreateRequest(
            username="continuity-synthetic",
            password="synthetic continuity account password",
        )
    )
    return store, paths


def test_conversation_and_project_reopen_feed_complete_packet_to_workspace(
    tmp_path, monkeypatch
):
    store, paths = _environment(tmp_path, monkeypatch)
    project = project_service.create_project(name="Synthetic river project")
    project_id = str(project["project_id"])
    project_service.update_project_metadata(
        project_id,
        current_state="The field comparison is complete.",
        latest_chunk="Calculated the synthetic marsh recovery score.",
        project_notes="CANARY_CONSTRAINT: use only paired public observations.",
        decisions=[{"label": "CANARY_DECISION: choose the north transect"}],
        milestones=[{"label": "Baseline survey complete"}],
        blockers=[{"label": "Awaiting rainfall series"}],
        next_actions=[{"label": "Compare the restored reach"}],
        unresolved_questions=[{"label": "Does season alter detectability?"}],
        corrections=[{"label": "Supersede 2024 area with corrected 2025 area"}],
    )
    conversation = conversation_service.ensure_conversation(project_id=project_id)
    for index in range(15):
        user = (
            "We decided CANARY_DECISION must remain the north transect."
            if index == 0
            else f"Synthetic continuity turn {index}."
        )
        conversation_service.record_chat_exchange(
            conversation_id=conversation.conversation_id,
            user_message=user,
            response_text=f"Recorded synthetic response {index}.",
            request_id=f"req_continuity_{index}",
            project_id=project_id,
            selected_model_runtime_tag="synthetic-model",
            invocation_status="ok",
            response_source="live_invoker",
        )

    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    fabric = MemoryFabricService(repository=MemoryRepository(paths=paths))
    linked_memory = fabric.create(
        principal,
        MemoryCreateRequest(
            title="Synthetic project method",
            body="Use paired observation windows for the river comparison.",
            why_stored="Synthetic project continuity proof.",
            scope="project",
            form="procedural",
            project_id=project_id,
        ),
    )
    evidence_repository = EvidenceRepository(paths=paths)
    session = evidence_repository.create_session(
        owner_user_id=principal.user_id,
        question="Synthetic river evidence",
        request_id="req_research_continuity",
        project_id=project_id,
        conversation_id=conversation.conversation_id,
        reasoning_gear="deep",
        budget={"max_queries": 1},
    )
    evidence_id = evidence_repository.record_evidence(
        owner_user_id=principal.user_id,
        packet={
            "source_url": "https://example.test/synthetic-source",
            "title": "Synthetic river source",
            "snippet": "UNTRUSTED_SYNTHETIC_EVIDENCE",
            "claim": "Synthetic public evidence claim",
            "retrieval_method": "fixture",
            "source_type": "organization",
            "network_access_used": True,
        },
        session_id=str(session["session_id"]),
        request_id="req_research_continuity",
        project_id=project_id,
        conversation_id=conversation.conversation_id,
    )

    thread = conversation_service.get_conversation_thread(conversation.conversation_id)
    hierarchy = build_conversation_hierarchy(
        thread,
        owner_user_id=principal.user_id,
        generator_model="synthetic-model",
        paths=paths,
    )
    assert hierarchy["derived"] is True
    assert hierarchy["approved_semantic_memory"] is False
    assert hierarchy["segments"][0]["message_ids"]
    assert "CANARY_DECISION" in hierarchy["segments"][0]["summary"]

    def reopen(request_id: str):
        return build_global_working_workspace(
            message="Continue where we left off after CANARY_DECISION.",
            owner_user_id=principal.user_id,
            conversation_id=conversation.conversation_id,
            project_id=project_id,
            request_id=request_id,
            mode="default",
            intent={"primary": "conversation"},
            model_runtime_tag="synthetic-model",
            model_context_window=16384,
            retrieval_breadth="broad",
            paths=paths,
        )

    first = reopen("req_reopen_first")
    second = reopen("req_reopen_after_restart")
    for workspace in (first, second):
        text = workspace.context_text
        assert "CANARY_DECISION" in text
        assert "CANARY_CONSTRAINT" in text
        assert "Awaiting rainfall series" in text
        assert "Does season alter detectability?" in text
        assert "Supersede 2024 area" in text
        assert linked_memory.memory_id in text
        assert evidence_id in text
        assert any(
            item.source_type == "project"
            for item in workspace.admitted_candidates
        )
        assert all(
            "UNTRUSTED_SYNTHETIC_EVIDENCE" not in str(item)
            for item in workspace.receipt.admitted
        )
        assert workspace.receipt.model_runtime_tag == "synthetic-model"


def test_new_conversation_project_links_fail_closed(tmp_path, monkeypatch):
    _store, _paths = _environment(tmp_path, monkeypatch)
    with pytest.raises(conversation_service.ConversationServiceError, match="project"):
        conversation_service.ensure_conversation(project_id="project_missing_synthetic")
