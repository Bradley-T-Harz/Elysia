from __future__ import annotations

import pytest

from app.api.schemas.evidence import (
    EvidenceBoundaryState,
    EvidenceConfidence,
    EvidenceRetrievalMethod,
    EvidenceSourceType,
    ResearchEvidencePacket,
)
from app.api.schemas.research import ResearchTicket, ResearchTicketStatus
from core.evidence_verifier import verify_research_ticket_payload
from core.verifier import verify_result


def valid_packet_payload(**overrides):
    payload = {
        "source_url": "https://example.test/source",
        "title": "Example source",
        "retrieved_at_utc": "2026-05-27T12:00:00Z",
        "snippet": (
            "The source says the research evidence contract remains local and "
            "requires structured evidence packets."
        ),
        "claim": "The research evidence contract remains local.",
        "confidence": "medium",
        "source_type": "primary",
        "contradiction_notes": [],
    }
    payload.update(overrides)
    return payload


def valid_ticket_payload(**overrides):
    payload = {
        "ticket_id": "research_ticket_001",
        "question": "What evidence contract should future research follow?",
        "status": "completed",
        "evidence_packets": [valid_packet_payload()],
    }
    payload.update(overrides)
    return payload


def test_valid_ticket_and_evidence_pass_verifier():
    result = verify_research_ticket_payload(valid_ticket_payload())

    assert result["verified"] is True
    assert "research_ticket_schema_valid" in result["checks_passed"]
    assert "research_ticket_completed_with_evidence" in result["checks_passed"]
    assert "research_packet_0_private_context_sent_false" in result["checks_passed"]
    assert "research_packet_0_retrieved_at_utc_parseable" in result["checks_passed"]
    assert result["issues"] == []


def test_valid_planned_ticket_without_evidence_passes_verifier():
    result = verify_research_ticket_payload(
        {
            "ticket_id": "research_ticket_planned_001",
            "question": "What future evidence should be gathered?",
            "status": "planned",
            "requires_live_research": True,
            "approval_required": True,
            "notes": ["Future live research is not enabled in Sprint 8."],
        }
    )

    assert result["verified"] is True
    assert "research_ticket_schema_valid" in result["checks_passed"]
    assert "research_ticket_live_research_enabled_false" in result["checks_passed"]
    assert result["issues"] == []


@pytest.mark.parametrize(
    ("field_name", "issue_text"),
    [
        ("private_context_sent", "must not send private context outward"),
        ("network_access_used", "must not use network access"),
        ("page_fetch_used", "must not fetch pages"),
        ("live_web_research_used", "must not use live web research"),
    ],
)
def test_risky_evidence_flags_fail_verifier(field_name, issue_text):
    packet = valid_packet_payload(**{field_name: True})
    result = verify_research_ticket_payload(
        valid_ticket_payload(evidence_packets=[packet])
    )

    assert result["verified"] is False
    assert any(issue_text in issue for issue in result["issues"])


def test_external_boundary_crossed_packet_fails_verifier():
    packet = valid_packet_payload(outward_boundary_state="external_boundary_crossed")
    result = verify_research_ticket_payload(
        valid_ticket_payload(evidence_packets=[packet])
    )

    assert result["verified"] is False
    assert "evidence packet 0 crossed an outward boundary" in result["issues"]


@pytest.mark.parametrize(
    ("field_name", "issue_text"),
    [
        ("live_research_enabled", "must not enable live research"),
        ("query_execution_allowed", "must not allow query execution"),
        ("retrieval_allowed", "must not allow retrieval"),
        ("private_context_allowed", "must not allow private context outward"),
        ("network_access_used", "must not use network access"),
        ("page_fetch_used", "must not use page fetching"),
        ("live_web_research_used", "must not use live web research"),
    ],
)
def test_risky_ticket_flags_fail_verifier(field_name, issue_text):
    result = verify_research_ticket_payload(valid_ticket_payload(**{field_name: True}))

    assert result["verified"] is False
    assert any(issue_text in issue for issue in result["issues"])


def test_external_boundary_crossed_ticket_fails_verifier():
    result = verify_research_ticket_payload(
        valid_ticket_payload(outward_boundary_state="external_boundary_crossed")
    )

    assert result["verified"] is False
    assert "Research ticket must not cross an outward boundary" in result["issues"]


def test_completed_ticket_with_no_evidence_fails_verifier():
    result = verify_research_ticket_payload(
        valid_ticket_payload(evidence_packets=[])
    )

    assert result["verified"] is False
    assert "completed research ticket is missing evidence packets" in result["issues"]


def test_unparseable_retrieved_at_utc_fails_verifier():
    packet = valid_packet_payload(retrieved_at_utc="not-a-timestamp")

    result = verify_research_ticket_payload(
        valid_ticket_payload(evidence_packets=[packet])
    )

    assert result["verified"] is False
    assert "evidence packet 0 has unparseable retrieved_at_utc" in result["issues"]


@pytest.mark.parametrize("status", ["blocked", "failed"])
def test_blocked_or_failed_ticket_with_no_errors_fails_verifier(status):
    result = verify_research_ticket_payload(
        {
            "ticket_id": "research_ticket_blocked_001",
            "question": "Why was research blocked?",
            "status": status,
            "errors": [],
        }
    )

    assert result["verified"] is False
    assert "blocked or failed research ticket is missing errors" in result["issues"]


@pytest.mark.parametrize("status", ["blocked", "failed"])
def test_blocked_or_failed_ticket_with_errors_passes_verifier(status):
    result = verify_research_ticket_payload(
        {
            "ticket_id": "research_ticket_blocked_002",
            "question": "Why was research blocked?",
            "status": status,
            "errors": ["Research worker is not live in Sprint 8."],
        }
    )

    assert result["verified"] is True
    assert "research_ticket_failure_has_errors" in result["checks_passed"]


def test_high_confidence_packet_with_weak_support_warns_without_network():
    packet = valid_packet_payload(
        snippet="Too short.",
        confidence="high",
        source_type="unknown",
    )

    result = verify_research_ticket_payload(
        valid_ticket_payload(evidence_packets=[packet])
    )

    assert result["verified"] is True
    assert result["warnings"]
    assert "high confidence with weak source or snippet support" in result[
        "warnings"
    ][0]


def test_contradiction_without_notes_is_flagged():
    result = verify_research_ticket_payload(
        valid_ticket_payload(
            evidence_packets=[
                valid_packet_payload(
                    claim="The river restoration plan reduces nitrate levels."
                ),
                valid_packet_payload(
                    source_url="https://example.test/source-2",
                    title="Second source",
                    claim=(
                        "The river restoration plan does not reduce nitrate levels."
                    ),
                ),
            ]
        )
    )

    assert result["verified"] is False
    assert "likely negation conflict lacks contradiction_notes" in result["issues"]
    assert result["contradiction_scan"]["conflicts"][0]["conflict_type"] == "negation"


def test_contradiction_with_notes_records_safely():
    result = verify_research_ticket_payload(
        valid_ticket_payload(
            evidence_packets=[
                valid_packet_payload(
                    claim="The field trial measured 42 wetland acres restored.",
                    contradiction_notes=[
                        "Another source gives a different acreage; do not resolve automatically."
                    ],
                ),
                valid_packet_payload(
                    source_url="https://example.test/source-2",
                    title="Second source",
                    claim="The field trial measured 35 wetland acres restored.",
                ),
            ]
        )
    )

    assert result["verified"] is True
    assert result["contradiction_scan"]["conflicts"][0]["conflict_type"] == (
        "numeric_or_date"
    )
    assert "research_contradiction_notes_present_for_possible_conflicts" in result[
        "checks_passed"
    ]


def test_verifier_branch_uses_contract_only_evidence_verifier():
    plan = {
        "intent": "research",
        "mode": "researcher",
        "retrieved_memory_count": 0,
        "uses_memory_context": False,
        "memory_context_source": "",
        "memory_class_declared": False,
        "memory_class": "",
        "primary_memory_class": "",
        "memory_class_source": "",
        "forced_memory_class": "",
        "memory_class_boundary_sensitive": False,
        "memory_class_requires_boundary_check": False,
        "reads_private_memory": False,
        "research_ticket_candidate": True,
    }
    internal_result = {
        "status": "ok_scaffold",
        "note": "Internal scaffold result created before final response composition.",
        "research_ticket": valid_ticket_payload(),
    }

    result = verify_result(plan, internal_result)

    assert result["verified"] is True
    assert "research_ticket_summary_present" in result["checks_passed"]
    assert "research_ticket_schema_valid" in result["checks_passed"]


def test_verifier_branch_fails_when_research_ticket_missing():
    plan = {
        "intent": "research",
        "mode": "researcher",
        "retrieved_memory_count": 0,
        "uses_memory_context": False,
        "memory_context_source": "",
        "research_ticket_candidate": True,
    }
    internal_result = {
        "status": "ok_scaffold",
        "note": "Internal scaffold result created before final response composition.",
    }

    result = verify_result(plan, internal_result)

    assert result["verified"] is False
    assert "plan requested research ticket but result is missing" in result["issues"]


def test_verifier_branch_marks_research_ticket_not_required_by_default():
    result = verify_result(
        {
            "intent": "conversation",
            "mode": "companion",
            "retrieved_memory_count": 0,
            "uses_memory_context": False,
            "memory_context_source": "",
        },
        {
            "status": "ok_scaffold",
            "note": "Internal scaffold result created before final response composition.",
        },
    )

    assert result["verified"] is True
    assert "research_ticket_not_required" in result["checks_passed"]


def test_verifier_accepts_schema_instances():
    packet = ResearchEvidencePacket(
        source_url="https://example.test/source",
        title="Example source",
        retrieved_at_utc="2026-05-27T12:00:00Z",
        snippet="The source states the evidence verifier validates local contract payloads.",
        claim="The evidence verifier validates local contract payloads.",
        confidence=EvidenceConfidence.MEDIUM,
        source_type=EvidenceSourceType.PRIMARY,
        outward_boundary_state=EvidenceBoundaryState.LOCAL_CONTRACT_ONLY,
    )
    ticket = ResearchTicket(
        ticket_id="research_ticket_instance_001",
        question="Can verifier accept schema instances?",
        status=ResearchTicketStatus.COMPLETED,
        evidence_packets=[packet],
    )

    result = verify_research_ticket_payload(ticket)

    assert result["verified"] is True
    assert result["issues"] == []


def test_verifier_accepts_bounded_searxng_ticket_truth():
    packet = valid_packet_payload(
        retrieval_method="searxng_search",
        outward_boundary_state="external_boundary_crossed",
        network_access_used=True,
        live_web_research_used=True,
    )
    result = verify_research_ticket_payload(
        valid_ticket_payload(
            worker_key="searxng_research_worker",
            worker_used=True,
            queries_requested=["wetland nitrate removal"],
            queries_sent=["wetland nitrate removal"],
            query_hashes=["abc123"],
            query_count=1,
            result_count=1,
            evidence_packet_count=1,
            live_research_enabled=True,
            query_execution_allowed=True,
            retrieval_allowed=False,
            network_access_used=True,
            live_web_research_used=True,
            outward_boundary_state="external_boundary_crossed",
            evidence_packets=[packet],
        )
    )

    assert result["verified"] is True
    assert "research_ticket_outward_boundary_crossed_for_searxng" in result["checks_passed"]
    assert "research_packet_0_retrieval_method_searxng_search" in result["checks_passed"]


def test_verifier_rejects_searxng_evidence_without_worker_truth():
    packet = valid_packet_payload(
        retrieval_method=EvidenceRetrievalMethod.SEARXNG_SEARCH,
        outward_boundary_state="external_boundary_crossed",
        network_access_used=True,
        live_web_research_used=True,
    )
    result = verify_research_ticket_payload(valid_ticket_payload(evidence_packets=[packet]))

    assert result["verified"] is False
    assert any("non-SearXNG ticket" in issue or "outside a bounded SearXNG ticket" in issue for issue in result["issues"])
