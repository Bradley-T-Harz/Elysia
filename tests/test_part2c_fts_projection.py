from __future__ import annotations

from pathlib import Path

from app.api import account_service
from app.api.account_service import AccountPaths, AccountStore
from app.api.schemas.account import AccountCreateRequest
from app.cognition.fts_projection import FtsMemoryProjection
from app.memory.canonical_models import (
    MemoryCorrectionRequest,
    MemoryCreateRequest,
    MemoryLifecycle,
    MemoryPrincipal,
    MemoryReasonRequest,
)
from app.memory.canonical_repository import MemoryRepository
from app.memory.fabric_service import MemoryFabricService


def _fabric(tmp_path: Path, monkeypatch):
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
    store.create_account(
        AccountCreateRequest(
            username="fts-synthetic",
            password="synthetic fts account password",
        )
    )
    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    repository = MemoryRepository(paths=store.elysia_paths)
    fabric = MemoryFabricService(repository=repository)
    projection = FtsMemoryProjection(
        paths=store.elysia_paths,
        repository=repository,
        fabric=fabric,
    )
    return store, principal, repository, fabric, projection


def _request(title: str, body: str, **extra):
    return MemoryCreateRequest(
        title=title,
        body=body,
        why_stored="Synthetic FTS lifecycle proof.",
        importance=0.8,
        **extra,
    )


def test_fts_phrase_prefix_temporal_pagination_and_mutation_queue(tmp_path, monkeypatch):
    _store, principal, _repository, fabric, projection = _fabric(tmp_path, monkeypatch)
    alpha = fabric.create(
        principal,
        _request("River lantern", "silver marsh restoration baseline"),
    )
    beta = fabric.create(
        principal,
        _request("River survey", "silver marsh restored reach evidence"),
    )
    future = fabric.create(
        principal,
        _request(
            "Future river note",
            "silver marsh future-only result",
            valid_from="2999-01-01T00:00:00Z",
        ),
    )

    phrase = projection.search(principal, '"silver marsh"', limit=20)
    phrase_ids = {row["candidate_id"] for row in phrase}
    assert {alpha.memory_id, beta.memory_id} <= phrase_ids
    assert future.memory_id not in phrase_ids
    assert projection.search(principal, "restor*", limit=20)

    first_page = projection.search(principal, "river", limit=1, offset=0)
    second_page = projection.search(principal, "river", limit=1, offset=1)
    assert first_page and second_page
    assert first_page[0]["candidate_id"] != second_page[0]["candidate_id"]

    fabric.correct(
        principal,
        alpha.memory_id,
        MemoryCorrectionRequest(
            body="CORRECTED_WATERSHED_CANARY",
            reason="Synthetic correction supersedes the old river wording.",
        ),
    )
    assert projection.search(principal, "CORRECTED_WATERSHED_CANARY")[0][
        "candidate_id"
    ] == alpha.memory_id
    assert alpha.memory_id not in {
        row["candidate_id"] for row in projection.search(principal, "baseline")
    }

    fabric.set_status(
        principal,
        beta.memory_id,
        MemoryLifecycle.ARCHIVED,
        MemoryReasonRequest(reason="Synthetic archive propagation."),
    )
    assert beta.memory_id not in {
        row["candidate_id"] for row in projection.search(principal, "restored")
    }
    fabric.set_status(
        principal,
        beta.memory_id,
        MemoryLifecycle.ACTIVE,
        MemoryReasonRequest(reason="Synthetic restore propagation."),
    )
    assert beta.memory_id in {
        row["candidate_id"] for row in projection.search(principal, "restored")
    }


def test_corrupt_derived_projection_repairs_without_canonical_loss(tmp_path, monkeypatch):
    store, principal, repository, fabric, projection = _fabric(tmp_path, monkeypatch)
    record = fabric.create(
        principal,
        _request("Repair canary", "REBUILD_FROM_CANONICAL_CANARY"),
    )
    assert projection.search(principal, "REBUILD_FROM_CANONICAL_CANARY")
    projection.database_path.write_bytes(b"synthetic corrupt derived cache")

    result = projection.repair_and_rebuild(principal)
    assert result["repair_performed"] is True
    assert result["canonical_memory_mutated"] is False
    assert fabric.get(principal, record.memory_id).body == "REBUILD_FROM_CANONICAL_CANARY"
    assert projection.search(principal, "REBUILD_FROM_CANONICAL_CANARY")
    assert any(store.elysia_paths.memory_fts_rebuild_dir.iterdir())
    assert repository.health()["state"] == "ready"


def test_fts_unicode_diacritics_punctuation_and_porter_stemming(tmp_path, monkeypatch):
    _store, principal, _repository, fabric, projection = _fabric(tmp_path, monkeypatch)
    record = fabric.create(
        principal,
        _request(
            "Café ecology notes",
            "Co-operating researchers restored the résumé archive near the wetland's edge.",
        ),
    )

    # The declared unicode61/remove_diacritics/Porter tokenizer contract must
    # survive realistic punctuation and must not require ASCII-only wording.
    assert projection.search(principal, "cafe")[0]["candidate_id"] == record.memory_id
    assert projection.search(principal, "resume")[0]["candidate_id"] == record.memory_id
    assert projection.search(principal, "restoring")[0]["candidate_id"] == record.memory_id
    assert projection.search(principal, "co-operating")[0]["candidate_id"] == record.memory_id
    assert projection.search(principal, "wetland's")[0]["candidate_id"] == record.memory_id
    assert projection.search(principal, "!!!—…") == []
