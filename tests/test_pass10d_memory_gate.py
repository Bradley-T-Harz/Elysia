from __future__ import annotations

from pathlib import Path

import pytest

from app.api import account_service
from app.api.account_service import AccountPaths, AccountStore
from app.api.admin_service import AdminService
from app.api.schemas.account import AccountCreateRequest, AccountLoginRequest
from app.cognition.fts_projection import FtsMemoryProjection
from app.cognition.workspace import build_global_working_workspace
from app.memory.canonical_models import (
    CandidateDecisionRequest,
    MemoryCandidateCreateRequest,
    MemoryCreateRequest,
    MemoryPrincipal,
    MemoryQuery,
)
from app.memory.canonical_repository import MemoryRepository
from app.memory.fabric_service import MemoryFabricService
from app.memory.release_service import MemoryReleaseService


def _store(root: Path) -> AccountStore:
    identity = root / "profile" / "identity"
    return AccountStore(
        AccountPaths(
            identity_root=identity,
            database_path=identity / "elysia_identity.sqlite",
            profile_photo_dir=identity / "profile_photos",
            current_session_path=identity / "current_session.json",
        )
    )


def _candidate(index: int, *, kind: str = "personal_inference") -> MemoryCandidateCreateRequest:
    return MemoryCandidateCreateRequest(
        title=f"Synthetic candidate {index}",
        body=f"SYNTHETIC_CANDIDATE_BODY_{index}",
        why_stored="Synthetic Gate Zero candidate evidence.",
        candidate_kind=kind,
        proposed_wording=f"Synthetic proposed wording {index}",
        evidence_summary=f"Synthetic evidence summary {index}",
        confidence=0.75,
        source={
            "source_type": "conversation_inference" if kind == "personal_inference" else "onboarding_declaration",
            "source_id": f"synthetic-source-{index}",
            "source_authority": "inference_engine" if kind == "personal_inference" else "user",
            "provenance_status": "proposed" if kind == "personal_inference" else "declared",
        },
    )


def test_candidate_queue_all_user_outcomes_and_identity_separation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    password = "synthetic candidate owner password"
    store.create_account(AccountCreateRequest(username="candidate-owner", password=password))
    profile_before = store.private_profile().model_dump(mode="json")
    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    repository = MemoryRepository(paths=store.elysia_paths)
    fabric = MemoryFabricService(repository=repository)

    approved = fabric.create_candidate(principal, _candidate(1))
    approved = fabric.decide_candidate(
        principal,
        approved.memory_id,
        CandidateDecisionRequest(decision="approve", reason="Owner approved exact wording."),
    )
    assert approved.status.value == "active"
    assert approved.user_confirmed is True

    edited = fabric.create_candidate(principal, _candidate(2))
    edited = fabric.decide_candidate(
        principal,
        edited.memory_id,
        CandidateDecisionRequest(
            decision="approve",
            edited_title="User-edited declaration",
            edited_body="USER_APPROVED_EDITED_CANDIDATE",
            reason="Owner edited the machine proposal before approval.",
        ),
    )
    assert edited.title == "User-edited declaration"
    assert edited.body == "USER_APPROVED_EDITED_CANDIDATE"
    assert edited.revision_number == 2
    with repository.connect() as conn:
        candidate_row = conn.execute(
            "SELECT proposed_wording,evidence_summary,review_state FROM memory_candidates WHERE memory_id=?",
            (edited.memory_id,),
        ).fetchone()
        revision_actors = [
            str(row[0])
            for row in conn.execute(
                "SELECT created_by_actor FROM memory_revisions WHERE memory_id=? ORDER BY revision_number",
                (edited.memory_id,),
            ).fetchall()
        ]
    assert candidate_row["proposed_wording"] == "Synthetic proposed wording 2"
    assert candidate_row["evidence_summary"] == "Synthetic evidence summary 2"
    assert candidate_row["review_state"] == "approved"
    assert revision_actors == ["assistant_candidate", principal.user_id]

    rejected = fabric.create_candidate(principal, _candidate(3))
    rejected = fabric.decide_candidate(
        principal,
        rejected.memory_id,
        CandidateDecisionRequest(decision="reject", reason="Owner rejected the inference."),
    )
    assert rejected.status.value == "blocked"
    active, _ = fabric.list(principal, MemoryQuery(status="active", limit=100))
    assert rejected.memory_id not in {item.memory_id for item in active}

    deferred = fabric.create_candidate(principal, _candidate(4))
    deferred = fabric.decide_candidate(
        principal,
        deferred.memory_id,
        CandidateDecisionRequest(
            decision="defer",
            defer_until="2030-01-01T00:00:00Z",
            reason="Owner deferred review.",
        ),
    )
    assert deferred.status.value == "candidate"
    with repository.connect() as conn:
        assert conn.execute(
            "SELECT deferred_until,review_state FROM memory_candidates WHERE memory_id=?",
            (deferred.memory_id,),
        ).fetchone()[:] == ("2030-01-01T00:00:00Z", "pending")

    sealed = fabric.create_candidate(principal, _candidate(5))
    fabric.encryption.unlock_sealed(principal=principal, password=password, ttl_seconds=60)
    sealed = fabric.decide_candidate(
        principal,
        sealed.memory_id,
        CandidateDecisionRequest(decision="seal", reason="Owner chose the Sealed compartment."),
    )
    assert sealed.status.value == "active"
    assert sealed.privacy.value == "sealed"
    fabric.encryption.relock(principal.user_id)
    assert fabric.get(principal, sealed.memory_id).content_state == "sealed_locked"

    onboarding = fabric.create_candidate(
        principal,
        _candidate(6, kind="user_submitted_candidate"),
    )
    onboarding = fabric.decide_candidate(
        principal,
        onboarding.memory_id,
        CandidateDecisionRequest(
            decision="approve",
            reason="User explicitly approved an onboarding-style declaration.",
        ),
    )
    assert onboarding.owner_user_id == principal.user_id
    assert onboarding.sources[0]["source_authority"] == "user"
    assert store.private_profile().model_dump(mode="json") == profile_before


def test_local_admin_governs_counts_but_cannot_read_another_profile_life(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    owner_password = "synthetic installation owner password"
    user_password = "synthetic ordinary profile password"
    store.create_account(AccountCreateRequest(username="installation-owner", password=owner_password))
    store.create_account(AccountCreateRequest(username="ordinary-profile", password=user_password))
    store.logout()
    store.login(AccountLoginRequest(username="ordinary-profile", password=user_password))
    ordinary = MemoryPrincipal.model_validate(store.authenticated_principal())
    repository = MemoryRepository(paths=store.elysia_paths)
    fabric = MemoryFabricService(repository=repository)
    normal = fabric.create(
        ordinary,
        MemoryCreateRequest(
            title="Ordinary private-life normal",
            body="ORDINARY_NORMAL_LIFE_CANARY",
            why_stored="Synthetic Admin non-reader proof.",
        ),
    )
    private = fabric.create(
        ordinary,
        MemoryCreateRequest(
            title="Ordinary private-life private",
            body="ORDINARY_PRIVATE_LIFE_CANARY",
            why_stored="Synthetic Admin non-reader proof.",
            privacy="private",
        ),
    )
    fabric.encryption.unlock_sealed(principal=ordinary, password=user_password, ttl_seconds=60)
    sealed = fabric.create(
        ordinary,
        MemoryCreateRequest(
            title="Ordinary private-life sealed",
            body="ORDINARY_SEALED_LIFE_CANARY",
            why_stored="Synthetic Admin non-reader proof.",
            privacy="sealed",
        ),
    )
    fabric.encryption.relock(ordinary.user_id)

    store.logout()
    store.login(AccountLoginRequest(username="installation-owner", password=owner_password))
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    owner = MemoryPrincipal.model_validate(store.authenticated_principal())
    summary = AdminService(store).summary()
    ordinary_storage = next(
        item for item in summary["memory_storage_by_profile"] if item["user_id"] == ordinary.user_id
    )
    assert ordinary_storage["record_count"] == 3
    assert ordinary_storage["content_included"] is False
    for canary in (
        "ORDINARY_NORMAL_LIFE_CANARY",
        "ORDINARY_PRIVATE_LIFE_CANARY",
        "ORDINARY_SEALED_LIFE_CANARY",
    ):
        assert canary not in repr(summary)

    for record in (normal, private, sealed):
        with pytest.raises(Exception):
            fabric.get(owner, record.memory_id)
    records, count = fabric.list(owner, MemoryQuery(limit=100))
    assert records == []
    assert count == 0
    projection = FtsMemoryProjection(
        paths=store.elysia_paths,
        repository=repository,
        fabric=fabric,
    )
    assert projection.search(owner, "ORDINARY_NORMAL_LIFE_CANARY") == []
    assert MemoryReleaseService(fabric=fabric)._logical_export(owner, "full_account")["records"] == []
    workspace = build_global_working_workspace(
        message="Recall the ordinary profile canary",
        owner_user_id=owner.user_id,
        conversation_id=None,
        project_id=None,
        request_id="pass10d-admin-nonreader",
        mode="default",
        intent={"primary": "conversation"},
        model_runtime_tag="synthetic-model",
        model_context_window=8192,
        retrieval_breadth="broad",
        paths=store.elysia_paths,
    )
    assert "ORDINARY_" not in workspace.context_text
    assert not workspace.admitted_candidates
