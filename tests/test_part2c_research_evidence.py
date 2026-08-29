from __future__ import annotations

from app.api import research_service
from app.api import account_service
from app.api.account_service import AccountPaths, AccountStore
from app.api.schemas.account import AccountCreateRequest
from app.api.research_service import (
    WebResearchPort,
    prepare_minimum_necessary_public_queries,
    source_authority_class,
)
from app.cognition.evidence_repository import EvidenceRepository
from app.cognition.workspace import build_global_working_workspace
from app.install.paths import resolve_elysia_paths
from app.memory.canonical_models import MemoryPrincipal
from app.memory.canonical_repository import MemoryRepository
from app.memory.fabric_service import MemoryFabricService
import pytest


def _paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    return resolve_elysia_paths()


def test_evidence_progress_survives_repository_restart(tmp_path, monkeypatch):
    paths = _paths(tmp_path, monkeypatch)
    repository = EvidenceRepository(paths=paths)
    session = repository.create_session(
        owner_user_id="user_synthetic",
        question="Synthetic source comparison",
        request_id="req_synthetic",
        project_id="project_synthetic",
        conversation_id="conversation_synthetic",
        reasoning_gear="deep",
        budget={"max_queries": 2},
    )
    repository.record_progress(
        owner_user_id="user_synthetic",
        session_id=session["session_id"],
        stage="search",
        state="ok",
        detail={"query_sequence": 1, "result_count": 3, "secret": "must-not-persist"},
    )

    reopened = EvidenceRepository(paths=paths).get_session(
        "user_synthetic", session["session_id"]
    )
    assert reopened["progress"][0]["stage"] == "search"
    assert reopened["progress"][0]["detail"] == {
        "query_sequence": 1,
        "result_count": 3,
    }
    assert repository.health()["schema_version"] == 4


def test_exact_egress_approval_is_actor_scope_hash_and_one_time_bound(tmp_path, monkeypatch):
    repository = EvidenceRepository(paths=_paths(tmp_path, monkeypatch))
    preview = repository.preview_egress(
        owner_user_id="user_alpha",
        operation="public_search",
        destination_class="public_search_engines_via_local_searxng",
        data_categories=["legal_strategy"],
        request_hash="request_hash_alpha",
        preview={"query_preview": "legal strategy public record"},
    )
    resolution = repository.resolve_egress(
        owner_user_id="user_alpha",
        approval_id=preview["approval_id"],
        approve=True,
    )
    token = resolution["approval_token"]
    assert token

    mismatch, reason = repository.consume_egress(
        owner_user_id="user_alpha",
        approval_id=preview["approval_id"],
        approval_token=token,
        operation="public_search",
        destination_class="public_search_engines_via_local_searxng",
        data_categories=["legal_strategy"],
        request_hash="tampered_hash",
    )
    assert mismatch is False
    assert reason == "approval_scope_mismatch"

    consumed, reason = repository.consume_egress(
        owner_user_id="user_alpha",
        approval_id=preview["approval_id"],
        approval_token=token,
        operation="public_search",
        destination_class="public_search_engines_via_local_searxng",
        data_categories=["legal_strategy"],
        request_hash="request_hash_alpha",
    )
    assert consumed is True
    assert reason == "consumed"
    reused, reason = repository.consume_egress(
        owner_user_id="user_alpha",
        approval_id=preview["approval_id"],
        approval_token=token,
        operation="public_search",
        destination_class="public_search_engines_via_local_searxng",
        data_categories=["legal_strategy"],
        request_hash="request_hash_alpha",
    )
    assert reused is False
    assert reason == "approval_not_approved"


def test_iterative_port_prefers_authority_and_domain_diversity(monkeypatch):
    monkeypatch.setattr(research_service, "internet_master_enabled", lambda: True)
    monkeypatch.setattr(research_service, "_research_controls", lambda: ("strict", "proactive"))
    searched: list[str] = []
    fetched: list[str] = []

    urls = (
        "https://agency.gov/report",
        "https://university.edu/paper",
        "https://example.org/analysis",
    )

    def search_runner(payload):
        index = len(searched)
        searched.extend(payload["queries"])
        url = urls[min(index, len(urls) - 1)]
        return {
            "status": "ok",
            "data": {
                "queries_sent": list(payload["queries"]),
                "network_access_used": True,
                "durable_research": {
                    "session_id": None,
                    "evidence_ids": [f"evidence_search_{index}"],
                },
                "evidence_packets": [{"source_url": url}],
            },
        }

    def fetch_runner(payload, **_kwargs):
        fetched.append(payload["url"])
        return {
            "status": "ok",
            "data": {
                "page_fetch_used": True,
                "network_access_used": True,
                "bytes_read": 100,
                "durable_research": {"evidence_ids": [f"evidence_fetch_{len(fetched)}"]},
            },
        }

    result = WebResearchPort().investigate(
        question="Compare synthetic wetland evidence",
        request_id="req_iterative",
        conversation_id=None,
        project_id=None,
        reasoning_gear="research_engineering",
        autonomy_level=5,
        search_runner=search_runner,
        fetch_runner=fetch_runner,
    )
    assert len(searched) == 3
    assert set(fetched) == set(urls)
    assert result["domain_count"] == 3
    assert result["authority_class_count"] == 3
    assert set(result["authority_classes"]) == {"government", "academic", "organization"}
    assert result["private_context_sent"] is False
    assert all(item["stage"] in {"search", "fetch"} for item in result["progress"])


def test_research_port_cancels_before_network(monkeypatch):
    monkeypatch.setattr(research_service, "internet_master_enabled", lambda: True)
    calls: list[object] = []
    result = WebResearchPort().investigate(
        question="Synthetic cancelled investigation",
        request_id="req_cancel",
        conversation_id=None,
        project_id=None,
        reasoning_gear="deep",
        autonomy_level=3,
        cancel_check=lambda: True,
        search_runner=lambda payload: calls.append(payload),
    )
    assert result["state"] == "cancelled"
    assert result["network_access_used"] is False
    assert calls == []


def test_source_authority_classification_is_deterministic():
    assert source_authority_class("https://www.epa.gov/report") == "government"
    assert source_authority_class("https://lab.example.edu/paper") == "academic"
    assert source_authority_class("https://docs.example.com/api") == "primary_documentation"
    assert source_authority_class("https://forum.example.com/thread") == "community"


def test_automatic_query_preparation_removes_unnecessary_local_personal_context():
    queries, receipt = prepare_minimum_necessary_public_queries(
        "Research wetland recovery using my private project file /home/synthetic/secret.txt; "
        "my email is person@example.test and my account id is account-123",
        limit=3,
    )
    outbound = " ".join(queries)
    assert "person@example.test" not in outbound
    assert "/home/" not in outbound
    assert "account-123" not in outbound
    assert "private project file" not in outbound
    assert "wetland recovery" in outbound
    assert receipt["local_context_included"] is False
    assert set(receipt["removed_categories"]) >= {
        "email_address",
        "local_path",
        "account_identifier",
    }


def test_evidence_correction_supersedes_old_claim_without_averaging(tmp_path, monkeypatch):
    paths = _paths(tmp_path, monkeypatch)
    repository = EvidenceRepository(paths=paths)
    original = repository.record_evidence(
        owner_user_id="user_synthetic",
        packet={
            "source_url": "https://example.test/changing-fact",
            "title": "Synthetic changing fact",
            "snippet": "The synthetic count was eleven.",
            "claim": "CHANGING_FACT_CANARY equals eleven",
            "retrieval_method": "public_search",
            "source_type": "organization",
        },
    )
    replacement = repository.correct_evidence(
        "user_synthetic",
        original,
        claim="CHANGING_FACT_CANARY equals twelve",
        excerpt="The corrected synthetic count is twelve.",
        reason="A later primary record corrected the count.",
    )
    workspace = build_global_working_workspace(
        message="What changed for CHANGING_FACT_CANARY?",
        owner_user_id="user_synthetic",
        conversation_id=None,
        project_id=None,
        request_id="req_changing_fact",
        mode="default",
        intent={"primary": "conversation"},
        model_runtime_tag="synthetic-model",
        model_context_window=8192,
        paths=paths,
    )
    assert "equals twelve" in workspace.context_text
    assert "equals eleven" not in workspace.context_text
    assert any(section["label"] == "Corrections" for section in workspace.context_sections)
    assert any(
        item["candidate_id"] == f"evidence:{original}"
        and item["reason"] == "inactive_or_superseded"
        for item in workspace.receipt.excluded
    )
    assert any(
        item["candidate_id"] == f"evidence:{replacement['evidence_id']}"
        for item in workspace.receipt.contradiction_handling
    )


def test_verified_high_stakes_evidence_enters_memory_as_review_candidate_only(
    tmp_path, monkeypatch
):
    paths = _paths(tmp_path, monkeypatch)
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
    store.create_account(
        AccountCreateRequest(
            username="evidence-candidate",
            password="synthetic evidence account password",
        )
    )
    principal = MemoryPrincipal.model_validate(store.authenticated_principal())
    repository = EvidenceRepository(paths=paths)
    evidence_id = repository.record_evidence(
        owner_user_id=principal.user_id,
        packet={
            "source_url": "https://agency.gov/synthetic-medical",
            "title": "Synthetic high-stakes source",
            "snippet": "Synthetic evidence excerpt.",
            "claim": "Synthetic medical claim requiring review.",
            "retrieval_method": "public_search",
            "source_type": "government",
            "high_stakes": True,
        },
    )
    with pytest.raises(Exception, match="verified"):
        repository.promote_to_memory_candidate(principal.user_id, evidence_id)
    repository.set_verification(
        principal.user_id,
        evidence_id,
        verification_status="verified",
    )
    promotion = repository.promote_to_memory_candidate(principal.user_id, evidence_id)
    fabric = MemoryFabricService(repository=MemoryRepository(paths=paths))
    candidate = fabric.get(principal, promotion["memory_id"])
    assert promotion["requires_user_review"] is True
    assert promotion["high_stakes"] is True
    assert candidate.status.value == "candidate"
    assert candidate.user_confirmed is False
    assert candidate.candidate_kind == "high_stakes_research_claim"
