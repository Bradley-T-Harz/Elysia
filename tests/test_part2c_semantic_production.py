from __future__ import annotations

from io import BytesIO
import json
from types import SimpleNamespace

import pytest

from app.api import account_service
from app.api.account_service import AccountPaths, AccountStore
from app.api.schemas.account import AccountCreateRequest
from app.cognition.fts_projection import FtsMemoryProjection
from app.cognition.hybrid_retrieval import FUSION_VERSION, HybridMemoryRetriever
from app.cognition.semantic_projection import (
    SemanticMemoryProjection,
    SemanticProjectionConfig,
    SemanticProjectionError,
)
from app.memory.canonical_models import MemoryCreateRequest, MemoryPrincipal
from app.memory.canonical_repository import MemoryRepository
from app.memory.fabric_service import MemoryFabricService


def _fabric(tmp_path, monkeypatch):
    identity = tmp_path / "profile" / "identity"
    store = AccountStore(AccountPaths(
        identity_root=identity,
        database_path=identity / "elysia_identity.sqlite",
        profile_photo_dir=identity / "profile_photos",
        current_session_path=identity / "current_session.json",
    ))
    monkeypatch.setattr(account_service, "_default_store", lambda: store)
    store.create_account(AccountCreateRequest(
        username="semantic-synthetic",
        password="synthetic semantic account password",
    ))
    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    repository = MemoryRepository(paths=store.elysia_paths)
    fabric = MemoryFabricService(repository=repository)
    return store, principal, repository, fabric


def test_semantic_config_rejects_nonloopback_and_broad_key(tmp_path, monkeypatch):
    store, _principal, _repository, _fabric_service = _fabric(tmp_path, monkeypatch)
    config_dir = store.elysia_paths.memory_semantic_config_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    key = config_dir / "api-key"
    key.write_text("x" * 48, encoding="utf-8")
    key.chmod(0o600)
    client = config_dir / "client.json"
    client.write_text(json.dumps({
        "version": 1,
        "enabled": True,
        "qdrant_url": "http://0.0.0.0:6333",
        "api_key_file": "api-key",
        "ollama_url": "http://127.0.0.1:11434",
        "collection": "elysia_memory_semantic_v1",
        "embedding_model": "qwen3-embedding:0.6b",
    }), encoding="utf-8")
    client.chmod(0o600)
    with pytest.raises(SemanticProjectionError):
        SemanticProjectionConfig.load(store.elysia_paths)

    payload = json.loads(client.read_text(encoding="utf-8"))
    payload["qdrant_url"] = "http://localhost:6333"
    client.write_text(json.dumps(payload), encoding="utf-8")
    client.chmod(0o600)
    with pytest.raises(SemanticProjectionError):
        SemanticProjectionConfig.load(store.elysia_paths)

    payload["qdrant_url"] = "http://127.0.0.1:6333"
    payload["embedding_num_gpu"] = 1
    client.write_text(json.dumps(payload), encoding="utf-8")
    client.chmod(0o600)
    with pytest.raises(SemanticProjectionError):
        SemanticProjectionConfig.load(store.elysia_paths)

    payload["embedding_num_gpu"] = -1
    client.write_text(json.dumps(payload), encoding="utf-8")
    client.chmod(0o600)
    assert SemanticProjectionConfig.load(store.elysia_paths).embedding_num_gpu == -1

    payload["embedding_num_gpu"] = 0
    client.write_text(json.dumps(payload), encoding="utf-8")
    client.chmod(0o600)
    key.chmod(0o644)
    projection = SemanticMemoryProjection(paths=store.elysia_paths)
    with pytest.raises(SemanticProjectionError):
        projection._api_key()


def test_canonical_write_enqueues_separate_semantic_projection_job(tmp_path, monkeypatch):
    store, principal, repository, fabric = _fabric(tmp_path, monkeypatch)
    record = fabric.create(principal, MemoryCreateRequest(
        title="Canonical first", body="Synthetic semantic queue proof.",
        why_stored="Projection work follows canonical commit.",
    ))
    with repository.connect() as connection:
        jobs = connection.execute(
            "SELECT job_kind, state FROM memory_jobs WHERE job_kind LIKE 'semantic_%'"
        ).fetchall()
        canonical = connection.execute(
            "SELECT memory_id FROM memory_records WHERE memory_id = ?", (record.memory_id,)
        ).fetchone()
    assert canonical is not None
    assert [(row["job_kind"], row["state"]) for row in jobs] == [
        (f"semantic_upsert:{record.memory_id}", "pending")
    ]


def test_private_and_sealed_records_never_enter_persistent_semantic_batch(tmp_path, monkeypatch):
    store, principal, repository, fabric = _fabric(tmp_path, monkeypatch)
    private = fabric.create(principal, MemoryCreateRequest(
        title="Private synthetic", body="PRIVATE_VECTOR_CANARY",
        why_stored="Synthetic privacy proof.", privacy="private",
    ))
    fabric.encryption.unlock_sealed(
        principal=principal,
        password="synthetic semantic account password",
        ttl_seconds=60,
    )
    sealed = fabric.create(principal, MemoryCreateRequest(
        title="Sealed synthetic", body="SEALED_VECTOR_CANARY",
        why_stored="Synthetic sealed proof.", privacy="sealed",
    ))
    projection = SemanticMemoryProjection(
        paths=store.elysia_paths, repository=repository, fabric=fabric,
        config=SemanticProjectionConfig(
            enabled=True,
            qdrant_url="http://127.0.0.1:6333",
            api_key_path=tmp_path / "unused",
            ollama_url="http://127.0.0.1:11434",
        ),
    )
    deleted = []
    monkeypatch.setattr(projection, "_delete", lambda memory_id: deleted.append(memory_id))
    monkeypatch.setattr(
        projection, "_ollama",
        lambda _texts, **_kwargs: pytest.fail("Private/Sealed text reached the embedding model."),
    )
    assert projection._upsert_batch([private, sealed], principal) == 0
    assert set(deleted) == {private.memory_id, sealed.memory_id}


def test_semantic_filter_rejects_forged_space_and_owner_acl_bypass(tmp_path, monkeypatch):
    store, principal, repository, fabric = _fabric(tmp_path, monkeypatch)
    projection = SemanticMemoryProjection(
        paths=store.elysia_paths,
        repository=repository,
        fabric=fabric,
        config=SemanticProjectionConfig(
            enabled=True,
            qdrant_url="http://127.0.0.1:6333",
            api_key_path=tmp_path / "unused",
            ollama_url="http://127.0.0.1:11434",
        ),
    )
    monkeypatch.setattr(projection, "ensure_ready", lambda _principal: {"state": "ready"})
    monkeypatch.setattr(projection, "_ollama", lambda *_args, **_kwargs: [[0.0] * 1024])
    captured = {}

    def fake_qdrant(_method, _path, payload=None, **_kwargs):
        captured["filter"] = payload["filter"]
        return {
            "result": {
                "points": [
                    {
                        "id": "synthetic",
                        "score": 0.9,
                        "payload": {
                            "memory_id": "memory_forged",
                            "owner_user_id": principal.user_id,
                            "space_id": "space_forged",
                            "privacy": "normal",
                        },
                    }
                ]
            }
        }

    monkeypatch.setattr(projection, "_qdrant", fake_qdrant)
    with pytest.raises(SemanticProjectionError, match="hard authorization filter"):
        projection.search(
            principal,
            "synthetic",
            authorized_space_ids=["space_forged"],
        )
    assert captured["filter"]["should"] == [
        {
            "must": [
                {"key": "owner_user_id", "match": {"value": principal.user_id}},
                {"is_empty": {"key": "space_id"}},
            ]
        }
    ]


def test_semantic_embedding_uses_measured_governor_workload_and_full_gpu_offload(
    tmp_path, monkeypatch
):
    store, principal, repository, fabric = _fabric(tmp_path, monkeypatch)
    projection = SemanticMemoryProjection(
        paths=store.elysia_paths,
        repository=repository,
        fabric=fabric,
        config=SemanticProjectionConfig(
            enabled=True,
            qdrant_url="http://127.0.0.1:6333",
            api_key_path=tmp_path / "unused",
            ollama_url="http://127.0.0.1:11434",
            embedding_num_gpu=-1,
        ),
    )
    monkeypatch.setattr(
        "app.cognition.semantic_projection.ModelRegistry.snapshot",
        lambda _self: {
            "models": [{
                "runtime_tag": "qwen3-embedding:0.6b",
                "size_bytes": 640_000_000,
                "size_vram_bytes": 0,
                "loaded": False,
                "digest": "sha256:synthetic",
            }]
        },
    )
    captured = {}
    monkeypatch.setattr(
        "app.api.user_control_service.current_user_controls",
        lambda: SimpleNamespace(
            compute_preference="gpu",
            cpu_percent_ceiling=40,
            ram_mb_ceiling=2048,
            vram_mb_ceiling=1024,
            max_background_jobs=0,
        ),
    )

    def fake_decide(workload, **kwargs):
        captured["workload"] = workload
        captured["compute_kwargs"] = kwargs
        return SimpleNamespace(
            decision="hybrid",
            selected_device="cuda:0",
            lease_id=None,
            reservation_id=None,
        )

    def fake_urlopen(request, timeout):
        del timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return BytesIO(json.dumps({"embeddings": [[0.0] * 1024]}).encode("utf-8"))

    monkeypatch.setattr("app.cognition.semantic_projection.decide_compute", fake_decide)
    monkeypatch.setattr("app.cognition.semantic_projection.urlopen", fake_urlopen)

    vectors = projection._ollama(["synthetic normal-memory query"], principal=principal)

    workload = captured["workload"]
    assert len(vectors[0]) == 1024
    assert captured["payload"]["options"]["num_gpu"] == -1
    assert workload.required_model == "qwen3-embedding:0.6b"
    assert workload.required_resources == ("local_ollama_embedding",)
    assert workload.incremental_vram_mb == workload.estimated_vram_mb
    assert workload.hard_vram_limit_mb == 1024
    assert workload.estimate_source == "ollama_installed_artifact_plus_runtime_allowance"
    assert captured["compute_kwargs"]["preference"] == "gpu"
    assert captured["compute_kwargs"]["cpu_percent_ceiling"] == 40
    assert captured["compute_kwargs"]["ram_mb_ceiling"] == 2048
    assert captured["compute_kwargs"]["vram_mb_ceiling"] == 1024
    assert captured["compute_kwargs"]["max_background_jobs"] == 0


def test_hybrid_rrf_adds_semantic_only_canonical_candidate_and_falls_back(tmp_path, monkeypatch):
    store, principal, repository, fabric = _fabric(tmp_path, monkeypatch)
    lexical_record = fabric.create(principal, MemoryCreateRequest(
        title="Exact wetland cue", body="silver marsh baseline",
        why_stored="Synthetic fusion proof.",
    ))
    semantic_record = fabric.create(principal, MemoryCreateRequest(
        title="Ecological continuity", body="restore water retention across the habitat",
        why_stored="Synthetic fusion proof.",
    ))
    lexical = FtsMemoryProjection(paths=store.elysia_paths, repository=repository, fabric=fabric)

    class SemanticReady:
        configured = True

        def search(self, *_args, **_kwargs):
            return [{"candidate_id": semantic_record.memory_id, "semantic_score": 0.93, "record": semantic_record}]

    result = HybridMemoryRetriever(lexical=lexical, semantic=SemanticReady()).search_normal(
        principal, "silver marsh", limit=20
    )
    by_id = {row["candidate_id"]: row for row in result.rows}
    assert lexical_record.memory_id in by_id
    assert semantic_record.memory_id in by_id
    assert by_id[semantic_record.memory_id]["semantic_rank"] == 1
    assert by_id[semantic_record.memory_id]["fusion_version"] == FUSION_VERSION

    class SemanticBroken:
        configured = True

        def search(self, *_args, **_kwargs):
            raise RuntimeError("synthetic derived outage")

    fallback = HybridMemoryRetriever(lexical=lexical, semantic=SemanticBroken()).search_normal(
        principal, "silver marsh", limit=20
    )
    assert fallback.semantic_state == "degraded_fts_fallback"
    assert lexical_record.memory_id in {row["candidate_id"] for row in fallback.rows}


def test_invalid_optional_semantic_config_cannot_break_mandatory_fts(tmp_path, monkeypatch):
    store, principal, repository, fabric = _fabric(tmp_path, monkeypatch)
    record = fabric.create(principal, MemoryCreateRequest(
        title="Lexical safety floor", body="silver marsh survives bad optional config",
        why_stored="Synthetic fail-open retrieval and fail-closed mutation split.",
    ))
    config_dir = store.elysia_paths.memory_semantic_config_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    config = config_dir / "client.json"
    config.write_text("{invalid", encoding="utf-8")
    config.chmod(0o600)
    lexical = FtsMemoryProjection(paths=store.elysia_paths, repository=repository, fabric=fabric)
    result = HybridMemoryRetriever(lexical=lexical).search_normal(
        principal, "silver marsh", limit=20
    )
    assert result.semantic_state == "degraded_fts_fallback"
    assert record.memory_id in {row["candidate_id"] for row in result.rows}
