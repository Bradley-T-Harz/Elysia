from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.schemas.evidence import (
    EvidenceBoundaryState,
    EvidenceConfidence,
    EvidenceRetrievalMethod,
    EvidenceSourceType,
    ResearchEvidencePacket,
)
from app.api.schemas.research import (
    ResearchScope,
    ResearchTicket,
    ResearchTicketStatus,
)


def test_evidence_packet_defaults_are_contract_only_and_safe():
    packet = ResearchEvidencePacket(
        source_url="https://example.test/source",
        title="Local test source",
        retrieved_at_utc="2026-05-27T12:00:00Z",
        snippet="This local test snippet supports a bounded contract check.",
        claim="The research evidence contract remains local only.",
    )

    assert packet.confidence == EvidenceConfidence.UNKNOWN
    assert packet.source_type == EvidenceSourceType.UNKNOWN
    assert packet.retrieval_method == EvidenceRetrievalMethod.NOT_LIVE
    assert packet.outward_boundary_state == EvidenceBoundaryState.LOCAL_CONTRACT_ONLY
    assert packet.private_context_sent is False
    assert packet.network_access_used is False
    assert packet.page_fetch_used is False
    assert packet.live_web_research_used is False
    assert packet.contradiction_notes == []

    payload = packet.to_payload()

    assert payload["confidence"] == "unknown"
    assert payload["source_type"] == "unknown"
    assert payload["retrieval_method"] == "not_live"
    assert payload["outward_boundary_state"] == "local_contract_only"
    assert payload["private_context_sent"] is False
    assert payload["network_access_used"] is False
    assert payload["page_fetch_used"] is False
    assert payload["live_web_research_used"] is False


def test_evidence_packet_supports_searxng_search_method_without_changing_defaults():
    packet = ResearchEvidencePacket(
        source_url="https://example.test/source",
        title="Search result source",
        retrieved_at_utc="2026-05-27T12:00:00Z",
        snippet="Search result snippet returned by bounded SearXNG worker.",
        claim="Search result may be relevant to the public research question.",
        retrieval_method=EvidenceRetrievalMethod.SEARXNG_SEARCH,
        outward_boundary_state=EvidenceBoundaryState.EXTERNAL_BOUNDARY_CROSSED,
        network_access_used=True,
        live_web_research_used=True,
    )

    payload = packet.to_payload()

    assert payload["retrieval_method"] == "searxng_search"
    assert payload["outward_boundary_state"] == "external_boundary_crossed"


def test_evidence_packet_supports_public_page_fetch_method_without_changing_defaults():
    packet = ResearchEvidencePacket(
        source_url="https://example.test/source",
        title="Fetched public page",
        retrieved_at_utc="2026-05-31T12:00:00Z",
        snippet="Bounded public page fetch returned this short sanitized snippet.",
        claim="Fetched public page may be relevant to the approved URL.",
        retrieval_method=EvidenceRetrievalMethod.PUBLIC_PAGE_FETCH,
        outward_boundary_state=EvidenceBoundaryState.EXTERNAL_BOUNDARY_CROSSED,
        network_access_used=True,
        page_fetch_used=True,
        live_web_research_used=True,
    )

    payload = packet.to_payload()

    assert payload["retrieval_method"] == "public_page_fetch"
    assert payload["page_fetch_used"] is True


def test_research_ticket_defaults_are_not_live_research():
    ticket = ResearchTicket(
        ticket_id="research_ticket_001",
        question="What evidence contract should future research follow?",
    )

    assert ticket.status == ResearchTicketStatus.PLANNED
    assert ticket.research_scope == ResearchScope.UNKNOWN
    assert ticket.evidence_packets == []
    assert ticket.live_research_enabled is False
    assert ticket.query_execution_allowed is False
    assert ticket.retrieval_allowed is False
    assert ticket.private_context_allowed is False
    assert ticket.private_context_sent is False
    assert ticket.network_access_used is False
    assert ticket.page_fetch_used is False
    assert ticket.live_web_research_used is False

    payload = ticket.to_payload()

    assert payload["status"] == "planned"
    assert payload["research_scope"] == "unknown"
    assert payload["live_research_enabled"] is False
    assert payload["query_execution_allowed"] is False
    assert payload["retrieval_allowed"] is False


def test_completed_ticket_serializes_nested_evidence_packet():
    packet = ResearchEvidencePacket(
        source_url="https://example.test/report",
        title="Example report",
        retrieved_at_utc="2026-05-27T12:00:00Z",
        snippet="The report states that local-only verification is contract-bound.",
        claim="Local-only verification is contract-bound.",
        confidence=EvidenceConfidence.MEDIUM,
        source_type=EvidenceSourceType.PRIMARY,
    )
    ticket = ResearchTicket(
        ticket_id="research_ticket_002",
        question="Can a completed ticket carry evidence?",
        status=ResearchTicketStatus.COMPLETED,
        evidence_packets=[packet],
    )

    payload = ticket.to_payload()

    assert payload["status"] == "completed"
    assert payload["evidence_packets"][0]["source_type"] == "primary"
    assert payload["evidence_packets"][0]["confidence"] == "medium"
    assert payload["evidence_packets"][0]["network_access_used"] is False


def test_evidence_packet_rejects_unexpected_fields():
    with pytest.raises(ValidationError):
        ResearchEvidencePacket(
            source_url="https://example.test/source",
            title="Local test source",
            retrieved_at_utc="2026-05-27T12:00:00Z",
            snippet="A bounded snippet.",
            claim="A bounded claim.",
            random_extra_field=True,
        )


def test_research_ticket_rejects_unexpected_fields():
    with pytest.raises(ValidationError):
        ResearchTicket(
            ticket_id="research_ticket_extra_001",
            question="Will strict schemas reject extras?",
            random_extra_field=True,
        )


@pytest.mark.parametrize(
    "missing_field",
    ["source_url", "title", "retrieved_at_utc", "snippet", "claim"],
)
def test_evidence_packet_required_fields_are_enforced(missing_field):
    payload = {
        "source_url": "https://example.test/source",
        "title": "Local test source",
        "retrieved_at_utc": "2026-05-27T12:00:00Z",
        "snippet": "A bounded snippet.",
        "claim": "A bounded claim.",
    }
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        ResearchEvidencePacket(**payload)


@pytest.mark.parametrize("missing_field", ["ticket_id", "question"])
def test_research_ticket_required_fields_are_enforced(missing_field):
    payload = {
        "ticket_id": "research_ticket_required_001",
        "question": "Are ticket required fields enforced?",
    }
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        ResearchTicket(**payload)
