"""
Contract-only verification for research evidence tickets.

Sprint 8D validates structure and boundary truth before any live research path
exists. It does not search, fetch pages, use the network, or send private
context outward.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ValidationError

from app.api.schemas.evidence import (
    EvidenceBoundaryState,
    EvidenceConfidence,
    EvidenceRetrievalMethod,
    EvidenceSourceType,
    ResearchEvidencePacket,
)
from app.api.schemas.research import ResearchTicket, ResearchTicketStatus

from .contradiction_scan import scan_contradictions


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _as_ticket(payload: Any) -> ResearchTicket:
    if isinstance(payload, ResearchTicket):
        return payload

    if hasattr(ResearchTicket, "model_validate"):
        return ResearchTicket.model_validate(payload)

    return ResearchTicket(**payload)


def _is_parseable_timestamp(value: str) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _packet_source_support_is_weak(packet: ResearchEvidencePacket) -> bool:
    if packet.source_type == EvidenceSourceType.UNKNOWN:
        return True

    if len(packet.snippet.strip()) < 40:
        return True

    claim_terms = {
        part.lower()
        for part in packet.claim.replace(".", " ").replace(",", " ").split()
        if len(part) >= 4
    }
    snippet_text = packet.snippet.lower()
    if claim_terms:
        matching_terms = {term for term in claim_terms if term in snippet_text}
        return len(matching_terms) < min(2, len(claim_terms))

    return False


def _verify_packet(
    packet: ResearchEvidencePacket,
    *,
    index: int,
    bounded_searxng_ticket: bool,
    bounded_fetch_ticket: bool,
    checks_passed: list[str],
    issues: list[str],
    warnings: list[str],
) -> None:
    prefix = f"evidence packet {index}"

    required_text_fields = {
        "source_url": packet.source_url,
        "title": packet.title,
        "retrieved_at_utc": packet.retrieved_at_utc,
        "snippet": packet.snippet,
        "claim": packet.claim,
    }
    for field_name, value in required_text_fields.items():
        if str(value or "").strip():
            checks_passed.append(f"research_packet_{index}_{field_name}_present")
        else:
            issues.append(f"{prefix} is missing {field_name}")

    if _is_parseable_timestamp(packet.retrieved_at_utc):
        checks_passed.append(f"research_packet_{index}_retrieved_at_utc_parseable")
    else:
        issues.append(f"{prefix} has unparseable retrieved_at_utc")

    if packet.private_context_sent is False:
        checks_passed.append(f"research_packet_{index}_private_context_sent_false")
    else:
        issues.append(f"{prefix} must not send private context outward")

    if bounded_fetch_ticket:
        if packet.page_fetch_used is True:
            checks_passed.append(f"research_packet_{index}_page_fetch_used_true_for_fetch")
        else:
            issues.append(f"{prefix} must truthfully mark page_fetch_used true")
    else:
        if packet.page_fetch_used is False:
            checks_passed.append(f"research_packet_{index}_page_fetch_used_false")
        else:
            issues.append(f"{prefix} must not fetch pages")

    if bounded_searxng_ticket or bounded_fetch_ticket:
        if packet.network_access_used is True:
            checks_passed.append(f"research_packet_{index}_network_access_used_true")
        else:
            issues.append(f"{prefix} must truthfully mark network_access_used true")

        if packet.live_web_research_used is True:
            checks_passed.append(f"research_packet_{index}_live_web_research_used_true")
        else:
            issues.append(f"{prefix} must truthfully mark live_web_research_used true")

        if _enum_value(packet.outward_boundary_state) == EvidenceBoundaryState.EXTERNAL_BOUNDARY_CROSSED.value:
            checks_passed.append(f"research_packet_{index}_outward_boundary_crossed")
        else:
            issues.append(f"{prefix} must mark external_boundary_crossed")

        expected_method = (
            EvidenceRetrievalMethod.PUBLIC_PAGE_FETCH.value
            if bounded_fetch_ticket
            else EvidenceRetrievalMethod.SEARXNG_SEARCH.value
        )
        if _enum_value(packet.retrieval_method) == expected_method:
            checks_passed.append(f"research_packet_{index}_retrieval_method_searxng_search")
        else:
            issues.append(f"{prefix} must use retrieval_method {expected_method}")
    else:
        dangerous_false_fields = {
            "network_access_used": "must not use network access",
            "live_web_research_used": "must not use live web research",
        }
        for field_name, issue_text in dangerous_false_fields.items():
            if getattr(packet, field_name) is False:
                checks_passed.append(f"research_packet_{index}_{field_name}_false")
            else:
                issues.append(f"{prefix} {issue_text}")

        if _enum_value(packet.outward_boundary_state) == EvidenceBoundaryState.EXTERNAL_BOUNDARY_CROSSED.value:
            issues.append(f"{prefix} crossed an outward boundary")
        else:
            checks_passed.append(f"research_packet_{index}_outward_boundary_not_crossed")

        if _enum_value(packet.retrieval_method) == EvidenceRetrievalMethod.SEARXNG_SEARCH.value:
            issues.append(f"{prefix} uses searxng_search outside a bounded SearXNG ticket")
        if _enum_value(packet.retrieval_method) == EvidenceRetrievalMethod.PUBLIC_PAGE_FETCH.value:
            issues.append(f"{prefix} uses public_page_fetch outside a bounded fetch ticket")

    if _enum_value(packet.retrieval_method) in {
        EvidenceRetrievalMethod.FUTURE_SEARCH.value,
        EvidenceRetrievalMethod.FUTURE_FETCH.value,
    }:
        warnings.append(
            f"{prefix} names a future retrieval method; Sprint 8 remains contract-only"
        )
    elif not (bounded_searxng_ticket or bounded_fetch_ticket):
        checks_passed.append(f"research_packet_{index}_retrieval_method_contract_safe")

    if packet.confidence == EvidenceConfidence.HIGH and _packet_source_support_is_weak(
        packet
    ):
        warnings.append(
            f"{prefix} has high confidence with weak source or snippet support"
        )
    else:
        checks_passed.append(f"research_packet_{index}_confidence_support_checked")


def verify_research_ticket_payload(payload: Any) -> dict[str, Any]:
    """
    Verify a ResearchTicket payload without performing research.
    """
    checks_passed: list[str] = []
    issues: list[str] = []
    warnings: list[str] = []

    try:
        ticket = _as_ticket(payload)
    except (TypeError, ValueError, ValidationError) as exc:
        return {
            "verified": False,
            "checks_passed": [],
            "issues": [f"research ticket schema validation failed: {exc}"],
            "warnings": [],
            "contradiction_scan": None,
        }

    checks_passed.append("research_ticket_schema_valid")
    bounded_searxng_ticket = (
        getattr(ticket, "worker_key", None) == "searxng_research_worker"
        and getattr(ticket, "worker_used", False) is True
    )
    bounded_fetch_ticket = (
        getattr(ticket, "worker_key", None) == "bounded_fetch_worker"
        and getattr(ticket, "worker_used", False) is True
    )

    status = _enum_value(ticket.status)
    if status in {item.value for item in ResearchTicketStatus}:
        checks_passed.append("research_ticket_status_allowed")
    else:
        issues.append(f"research ticket has unsupported status: {status}")

    if ticket.ticket_id.strip():
        checks_passed.append("research_ticket_id_present")
    else:
        issues.append("research ticket is missing ticket_id")

    if ticket.question.strip():
        checks_passed.append("research_ticket_question_present")
    else:
        issues.append("research ticket is missing question")

    always_false_fields = {
        "private_context_allowed": "Research ticket must not allow private context outward",
        "private_context_sent": "Research ticket must not send private context outward",
        "cloud_search_used": "Research ticket must not use cloud search",
        "cloud_model_used": "Research ticket must not use cloud models",
    }
    for field_name, issue_text in always_false_fields.items():
        if getattr(ticket, field_name, False) is False:
            checks_passed.append(f"research_ticket_{field_name}_false")
        else:
            issues.append(issue_text)

    if bounded_fetch_ticket:
        if ticket.live_research_enabled is True:
            checks_passed.append("research_ticket_live_research_enabled_true_for_fetch")
        else:
            issues.append("Bounded fetch ticket must truthfully enable live research")

        if ticket.query_execution_allowed is False:
            checks_passed.append("research_ticket_query_execution_allowed_false_for_fetch")
        else:
            issues.append("Bounded fetch ticket must not mark query execution")

        if ticket.retrieval_allowed is True and ticket.page_fetch_allowed is True:
            checks_passed.append("research_ticket_retrieval_allowed_true_for_fetch")
        else:
            issues.append("Bounded fetch ticket must truthfully allow approved retrieval")

        if ticket.page_fetch_used is True:
            checks_passed.append("research_ticket_page_fetch_used_true_for_fetch")
        else:
            issues.append("Bounded fetch ticket must truthfully mark page_fetch_used true")

        if ticket.network_access_used is True and ticket.live_web_research_used is True:
            checks_passed.append("research_ticket_network_access_used_true_for_fetch")
        else:
            issues.append("Bounded fetch ticket must truthfully mark network/live use")

        if _enum_value(ticket.outward_boundary_state) == EvidenceBoundaryState.EXTERNAL_BOUNDARY_CROSSED.value:
            checks_passed.append("research_ticket_outward_boundary_crossed_for_fetch")
        else:
            issues.append("Bounded fetch ticket must mark external_boundary_crossed")

        if ticket.evidence_packets:
            checks_passed.append("research_ticket_fetch_has_evidence_packets")
        else:
            issues.append("Bounded fetch ticket is missing evidence packets")
    elif bounded_searxng_ticket:
        if ticket.live_research_enabled is True:
            checks_passed.append("research_ticket_live_research_enabled_true_for_searxng")
        else:
            issues.append("Bounded SearXNG ticket must truthfully enable live research")

        if ticket.query_execution_allowed is True:
            checks_passed.append("research_ticket_query_execution_allowed_true_for_searxng")
        else:
            issues.append("Bounded SearXNG ticket must truthfully allow query execution")

        if ticket.retrieval_allowed is False:
            checks_passed.append("research_ticket_retrieval_allowed_false_for_search_only")
        else:
            issues.append("Bounded SearXNG ticket must not allow page/source retrieval")

        if ticket.network_access_used is True:
            checks_passed.append("research_ticket_network_access_used_true_for_searxng")
        else:
            issues.append("Bounded SearXNG ticket must truthfully mark network_access_used true")

        if ticket.live_web_research_used is True:
            checks_passed.append("research_ticket_live_web_research_used_true_for_searxng")
        else:
            issues.append("Bounded SearXNG ticket must truthfully mark live_web_research_used true")

        if _enum_value(ticket.outward_boundary_state) == EvidenceBoundaryState.EXTERNAL_BOUNDARY_CROSSED.value:
            checks_passed.append("research_ticket_outward_boundary_crossed_for_searxng")
        else:
            issues.append("Bounded SearXNG ticket must mark external_boundary_crossed")

        if getattr(ticket, "queries_sent", []):
            checks_passed.append("research_ticket_queries_sent_present_for_searxng")
        else:
            issues.append("Bounded SearXNG ticket crossed boundary without queries_sent")

        if ticket.evidence_packets:
            checks_passed.append("research_ticket_searxng_has_evidence_packets")
        else:
            issues.append("Bounded SearXNG ticket is missing evidence packets")
    else:
        dangerous_false_fields = {
            "live_research_enabled": "Research ticket must not enable live research",
            "query_execution_allowed": "Research ticket must not allow query execution",
            "retrieval_allowed": "Research ticket must not allow retrieval",
            "page_fetch_allowed": "Research ticket must not allow page fetching",
            "page_fetch_used": "Research ticket must not use page fetching",
            "network_access_used": "Research ticket must not use network access",
            "live_web_research_used": "Research ticket must not use live web research",
        }
        for field_name, issue_text in dangerous_false_fields.items():
            if getattr(ticket, field_name) is False:
                checks_passed.append(f"research_ticket_{field_name}_false")
            else:
                issues.append(issue_text)

        if _enum_value(ticket.outward_boundary_state) == EvidenceBoundaryState.EXTERNAL_BOUNDARY_CROSSED.value:
            issues.append("Research ticket must not cross an outward boundary")
        elif ticket.live_web_research_used or ticket.network_access_used:
            issues.append("Live web research or network use requires bounded SearXNG worker truth")
        else:
            checks_passed.append("research_ticket_outward_boundary_not_crossed")

        if any(
            _enum_value(packet.retrieval_method) == EvidenceRetrievalMethod.SEARXNG_SEARCH.value
            for packet in ticket.evidence_packets
        ):
            issues.append("searxng_search evidence appears on a non-SearXNG ticket")
        if any(
            _enum_value(packet.retrieval_method) == EvidenceRetrievalMethod.PUBLIC_PAGE_FETCH.value
            for packet in ticket.evidence_packets
        ):
            issues.append("public_page_fetch evidence appears on a non-fetch ticket")

    if ticket.status == ResearchTicketStatus.COMPLETED:
        if ticket.evidence_packets:
            checks_passed.append("research_ticket_completed_with_evidence")
        else:
            issues.append("completed research ticket is missing evidence packets")

    if ticket.status in {
        ResearchTicketStatus.BLOCKED,
        ResearchTicketStatus.FAILED,
    }:
        if ticket.errors:
            checks_passed.append("research_ticket_failure_has_errors")
        else:
            issues.append("blocked or failed research ticket is missing errors")

    for index, packet in enumerate(ticket.evidence_packets):
        _verify_packet(
            packet,
            index=index,
            bounded_searxng_ticket=bounded_searxng_ticket,
            bounded_fetch_ticket=bounded_fetch_ticket,
            checks_passed=checks_passed,
            issues=issues,
            warnings=warnings,
        )

    contradiction_scan = None
    if len(ticket.evidence_packets) >= 2:
        contradiction_scan = scan_contradictions(ticket.evidence_packets)
        checks_passed.extend(
            f"research_{check_name}"
            for check_name in contradiction_scan["checks_passed"]
        )
        issues.extend(contradiction_scan["issues"])
        warnings.extend(contradiction_scan.get("warnings", []))

    return {
        "verified": not issues,
        "checks_passed": checks_passed,
        "issues": issues,
        "warnings": warnings,
        "contradiction_scan": contradiction_scan,
    }


__all__ = ("verify_research_ticket_payload",)
