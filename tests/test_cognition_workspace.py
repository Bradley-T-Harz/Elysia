from __future__ import annotations

from pathlib import Path

from app.api import account_service
from app.api.account_service import AccountPaths, AccountStore
from app.api.schemas.account import AccountCreateRequest, AccountLoginRequest
from app.cognition.workspace import build_global_working_workspace
from app.cognition.sources import CognitionReadRequest, MemoryCognitionSource
from app.memory.canonical_models import MemoryCreateRequest, MemoryPrincipal, MemoryQuery
from app.memory.canonical_repository import MemoryRepository
from app.memory.fabric_service import MemoryFabricService


def _store(tmp_path: Path) -> AccountStore:
    identity = tmp_path / "profile" / "identity"
    return AccountStore(
        AccountPaths(
            identity_root=identity,
            database_path=identity / "elysia_identity.sqlite",
            profile_photo_dir=identity / "profile_photos",
            current_session_path=identity / "current_session.json",
        )
    )


def _memory(title: str, body: str, privacy: str) -> MemoryCreateRequest:
    return MemoryCreateRequest(
        title=title,
        body=body,
        why_stored="Synthetic cognition integration proof.",
        privacy=privacy,
        user_confirmed=True,
        importance=0.9,
    )


def _workspace(store: AccountStore, *, explicit_sealed: bool, request_id: str):
    principal = store.authenticated_principal()
    return build_global_working_workspace(
        message="Recall the synthetic cognition canary",
        owner_user_id=str(principal["user_id"]),
        conversation_id=None,
        project_id=None,
        request_id=request_id,
        mode="default",
        intent={"primary": "conversation"},
        model_runtime_tag="synthetic-model",
        model_context_window=8192,
        retrieval_breadth="broad",
        explicit_sealed_memory=explicit_sealed,
        paths=store.elysia_paths,
    )


def test_workspace_authorizes_before_ranking_and_sealed_use_is_one_request_only(
    tmp_path, monkeypatch
):
    store = _store(tmp_path)
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    password = "synthetic cognition account password"
    store.create_account(AccountCreateRequest(username="cognition-alpha", password=password))
    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    fabric = MemoryFabricService(repository=MemoryRepository(paths=store.elysia_paths))

    normal = fabric.create(
        principal,
        _memory("Normal cognition canary", "NORMAL_COGNITION_CANARY", "normal"),
    )
    private = fabric.create(
        principal,
        _memory("Private cognition canary", "PRIVATE_COGNITION_CANARY", "private"),
    )
    fabric.encryption.unlock_sealed(
        principal=principal,
        password=password,
        ttl_seconds=60,
    )
    sealed = fabric.create(
        principal,
        _memory("Sealed cognition canary", "SEALED_COGNITION_CANARY", "sealed"),
    )

    ordinary = _workspace(store, explicit_sealed=False, request_id="req_ordinary")
    ordinary_ids = {item.source_id for item in ordinary.admitted_candidates}
    assert normal.memory_id in ordinary_ids
    assert private.memory_id in ordinary_ids
    assert sealed.memory_id not in ordinary_ids
    assert any(
        item["candidate_id"] == f"memory:{sealed.memory_id}"
        for item in ordinary.receipt.excluded
    ) is False
    assert fabric.encryption.sealed_status(principal)["unlocked"] is True
    sealed_direct, sealed_total = fabric.list(
        principal,
        MemoryQuery(privacy="sealed", limit=20),
    )
    assert sealed_total == 1
    assert sealed_direct[0].body == "SEALED_COGNITION_CANARY"
    direct_candidates = MemoryCognitionSource(paths=store.elysia_paths).read(
        CognitionReadRequest(
            query="Recall the synthetic cognition canary",
            owner_user_id=principal.user_id,
            conversation_id=None,
            project_id=None,
            request_id="req_direct",
            mode="default",
            reasoning_gear="quick",
            model_runtime_tag="synthetic-model",
            recent_turn_limit=8,
            candidate_limit=80,
            profile_context={},
            authorized_space_ids=frozenset(),
            explicit_sealed_memory=True,
        )
    )
    assert sealed.memory_id in {item.source_id for item in direct_candidates}

    explicit = _workspace(store, explicit_sealed=True, request_id="req_explicit")
    sealed_candidates = [
        item for item in explicit.admitted_candidates if item.source_id == sealed.memory_id
    ]
    assert len(sealed_candidates) == 1, explicit.receipt.excluded
    assert sealed_candidates[0].privacy == "sealed"
    assert sealed_candidates[0].provenance["projection"] == "ephemeral_sealed_current_request"
    assert "SEALED_COGNITION_CANARY" in explicit.context_text
    assert "SEALED_COGNITION_CANARY" not in str(explicit.receipt.to_payload())

    fabric.encryption.relock(principal.user_id)
    relocked = _workspace(store, explicit_sealed=True, request_id="req_relocked")
    assert sealed.memory_id not in {item.source_id for item in relocked.admitted_candidates}

    projection_files = [
        store.elysia_paths.memory_fts_database_path,
        Path(str(store.elysia_paths.memory_fts_database_path) + "-wal"),
    ]
    projection_bytes = b"".join(path.read_bytes() for path in projection_files if path.exists())
    assert b"PRIVATE_COGNITION_CANARY" not in projection_bytes
    assert b"SEALED_COGNITION_CANARY" not in projection_bytes


def test_workspace_does_not_cross_account_boundary(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    store.create_account(
        AccountCreateRequest(username="cognition-owner", password="owner cognition password")
    )
    owner_principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    fabric = MemoryFabricService(repository=MemoryRepository(paths=store.elysia_paths))
    owner_record = fabric.create(
        owner_principal,
        _memory("Owner cognition canary", "OWNER_ONLY_COGNITION_CANARY", "normal"),
    )

    store.create_account(
        AccountCreateRequest(username="cognition-reader", password="reader cognition password")
    )
    # Creating an additional local profile must never silently switch the
    # Installation Owner's active session. Enter the reader profile explicitly.
    store.logout()
    store.login(
        AccountLoginRequest(username="cognition-reader", password="reader cognition password")
    )
    reader = _workspace(store, explicit_sealed=False, request_id="req_reader")
    assert owner_record.memory_id not in {item.source_id for item in reader.admitted_candidates}
    assert "OWNER_ONLY_COGNITION_CANARY" not in reader.context_text


def test_account_memory_remains_available_inside_a_new_conversation(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    store.create_account(
        AccountCreateRequest(username="cognition-continuity", password="continuity password")
    )
    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    fabric = MemoryFabricService(repository=MemoryRepository(paths=store.elysia_paths))
    record = fabric.create(
        principal,
        _memory(
            "Account continuity canary",
            "ACCOUNT_MEMORY_AVAILABLE_IN_NEW_CONVERSATION",
            "normal",
        ),
    )

    workspace = build_global_working_workspace(
        message="Recall the account continuity canary",
        owner_user_id=principal.user_id,
        conversation_id="conv_synthetic_new_thread",
        project_id=None,
        request_id="req_account_memory_new_thread",
        mode="default",
        intent={"primary": "conversation"},
        model_runtime_tag="synthetic-model",
        model_context_window=8192,
        retrieval_breadth="broad",
        paths=store.elysia_paths,
    )

    assert record.memory_id in {item.source_id for item in workspace.admitted_candidates}
    assert "ACCOUNT_MEMORY_AVAILABLE_IN_NEW_CONVERSATION" in workspace.context_text


def test_reasoning_gear_caps_retrieval_against_concrete_model_window(tmp_path):
    workspace = build_global_working_workspace(
        message="hello",
        owner_user_id=None,
        conversation_id=None,
        project_id=None,
        request_id="req_budget",
        mode="default",
        intent={"primary": "conversation"},
        model_runtime_tag="small-local-model",
        model_context_window=4096,
        retrieval_breadth="broad",
        paths=_store(tmp_path).elysia_paths,
    )
    assert workspace.reasoning_gear == "quick"
    assert workspace.receipt.retrieval_share <= 0.10
    assert workspace.receipt.uncertainty["retrieval_insufficient"] is False
    budget = workspace.receipt.token_budget
    assert sum(
        budget[key]
        for key in (
            "constitutional_policy_reserve",
            "current_instruction_reserve",
            "tool_research_evidence_reserve",
            "output_reserve",
            "retrieval_capacity",
        )
    ) <= budget["model_window"]
