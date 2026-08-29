"""Bounded conflict and uncertainty signals for governed cognition."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from app.cognition.models import CognitionCandidate, ExcludedCandidate


@dataclass(frozen=True)
class UncertaintyAssessment:
    score: float
    band: str
    conflict_count: int
    low_confidence_count: int
    stale_or_invalid_count: int
    source_failure_count: int
    retrieval_insufficient: bool
    escalation_recommended: bool
    reasons: tuple[str, ...]
    low_retrieval_agreement: bool = False
    model_disagreement: bool = False
    tool_mismatch: bool = False
    low_evidence_quality: bool = False
    ambiguous_intent: bool = False
    verifier_failure: bool = False
    content_free: bool = True

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


def assess_uncertainty(
    admitted: Iterable[CognitionCandidate],
    excluded: Iterable[ExcludedCandidate],
    *,
    query_present: bool,
) -> UncertaintyAssessment:
    items = list(admitted)
    rejected = list(excluded)
    conflicts = sum(
        1
        for item in items
        if item.provenance.get("contradiction")
        or item.provenance.get("contradiction_notes")
    )
    low_confidence = sum(
        1 for item in items if item.confidence is not None and item.confidence < 0.55
    )
    stale_reasons = {"not_yet_valid", "no_longer_valid", "inactive_or_superseded"}
    stale = sum(1 for item in rejected if item.reason in stale_reasons)
    source_failures = sum(1 for item in rejected if item.reason == "source_unavailable")
    insufficient = bool(query_present and not items)
    low_agreement = bool(
        len(items) >= 2 and low_confidence >= max(1, (len(items) + 1) // 2)
    )
    score = min(
        1.0,
        (0.40 if insufficient else 0.0)
        + (0.20 if low_agreement else 0.0)
        + min(0.35, conflicts * 0.20)
        + min(0.20, low_confidence * 0.07)
        + min(0.15, source_failures * 0.05)
        + min(0.10, stale * 0.025),
    )
    reasons: list[str] = []
    if conflicts:
        reasons.append("authorized_sources_conflict")
    if low_confidence:
        reasons.append("low_confidence_sources")
    if stale:
        reasons.append("stale_or_invalid_sources_excluded")
    if source_failures:
        reasons.append("cognition_source_degraded")
    if insufficient:
        reasons.append("authorized_retrieval_insufficient")
    if low_agreement:
        reasons.append("low_retrieval_agreement")
    band = "high" if score >= 0.65 else "moderate" if score >= 0.30 else "low"
    return UncertaintyAssessment(
        score=round(score, 4),
        band=band,
        conflict_count=conflicts,
        low_confidence_count=low_confidence,
        stale_or_invalid_count=stale,
        source_failure_count=source_failures,
        retrieval_insufficient=insufficient,
        escalation_recommended=bool(conflicts or low_agreement or score >= 0.65),
        reasons=tuple(reasons),
        low_retrieval_agreement=low_agreement,
    )


def extend_uncertainty(
    assessment: UncertaintyAssessment | Mapping[str, Any],
    *,
    model_disagreement: bool = False,
    tool_mismatch: bool = False,
    low_evidence_quality: bool = False,
    ambiguity_score: float = 0.0,
    verifier_failure: bool = False,
) -> UncertaintyAssessment:
    """Merge post-retrieval runtime signals into one content-free assessment."""
    if isinstance(assessment, Mapping):
        base = UncertaintyAssessment(
            score=float(assessment.get("score") or 0.0),
            band=str(assessment.get("band") or "low"),
            conflict_count=int(assessment.get("conflict_count") or 0),
            low_confidence_count=int(assessment.get("low_confidence_count") or 0),
            stale_or_invalid_count=int(assessment.get("stale_or_invalid_count") or 0),
            source_failure_count=int(assessment.get("source_failure_count") or 0),
            retrieval_insufficient=bool(assessment.get("retrieval_insufficient")),
            escalation_recommended=bool(assessment.get("escalation_recommended")),
            reasons=tuple(str(item) for item in assessment.get("reasons", []) or []),
            low_retrieval_agreement=bool(assessment.get("low_retrieval_agreement")),
            model_disagreement=bool(assessment.get("model_disagreement")),
            tool_mismatch=bool(assessment.get("tool_mismatch")),
            low_evidence_quality=bool(assessment.get("low_evidence_quality")),
            ambiguous_intent=bool(assessment.get("ambiguous_intent")),
            verifier_failure=bool(assessment.get("verifier_failure")),
        )
    else:
        base = assessment
    ambiguous = bool(base.ambiguous_intent or float(ambiguity_score) >= 0.65)
    signals = {
        "model_disagreement": bool(base.model_disagreement or model_disagreement),
        "tool_mismatch": bool(base.tool_mismatch or tool_mismatch),
        "low_evidence_quality": bool(base.low_evidence_quality or low_evidence_quality),
        "ambiguous_user_intent": ambiguous,
        "verifier_failure": bool(base.verifier_failure or verifier_failure),
    }
    reasons = list(base.reasons)
    reasons.extend(name for name, active in signals.items() if active)
    score = min(
        1.0,
        float(base.score)
        + (0.25 if signals["model_disagreement"] else 0.0)
        + (0.20 if signals["tool_mismatch"] else 0.0)
        + (0.25 if signals["low_evidence_quality"] else 0.0)
        + (0.20 if signals["ambiguous_user_intent"] else 0.0)
        + (0.35 if signals["verifier_failure"] else 0.0),
    )
    band = "high" if score >= 0.65 else "moderate" if score >= 0.30 else "low"
    return UncertaintyAssessment(
        score=round(score, 4),
        band=band,
        conflict_count=base.conflict_count,
        low_confidence_count=base.low_confidence_count,
        stale_or_invalid_count=base.stale_or_invalid_count,
        source_failure_count=base.source_failure_count,
        retrieval_insufficient=base.retrieval_insufficient,
        escalation_recommended=bool(base.escalation_recommended or any(signals.values())),
        reasons=tuple(dict.fromkeys(reasons)),
        low_retrieval_agreement=base.low_retrieval_agreement,
        model_disagreement=signals["model_disagreement"],
        tool_mismatch=signals["tool_mismatch"],
        low_evidence_quality=signals["low_evidence_quality"],
        ambiguous_intent=signals["ambiguous_user_intent"],
        verifier_failure=signals["verifier_failure"],
    )


def operational_self_model(
    *,
    selected_gear: str,
    selected_model: str,
    selected_device: str,
    autonomy_level: int,
    internet_enabled: bool,
    stop_active: bool,
    assessment: UncertaintyAssessment | Mapping[str, Any],
    pending_work_count: int = 0,
    active_memory_banks: Iterable[str] = (),
    active_projections: Iterable[str] = (),
    resource_state: Mapping[str, Any] | None = None,
    current_constraints: Iterable[str] = (),
    recent_failures: Iterable[str] = (),
    benchmarked_weaknesses: Iterable[str] = (),
) -> dict[str, object]:
    """Objective operational truth only; no anthropomorphic or hidden reasoning claims."""
    if isinstance(assessment, Mapping):
        assessment = UncertaintyAssessment(
            score=float(assessment.get("score") or 0.0),
            band=str(assessment.get("band") or "low"),
            conflict_count=int(assessment.get("conflict_count") or 0),
            low_confidence_count=int(assessment.get("low_confidence_count") or 0),
            stale_or_invalid_count=int(assessment.get("stale_or_invalid_count") or 0),
            source_failure_count=int(assessment.get("source_failure_count") or 0),
            retrieval_insufficient=bool(assessment.get("retrieval_insufficient")),
            escalation_recommended=bool(assessment.get("escalation_recommended")),
            reasons=tuple(str(item) for item in assessment.get("reasons", []) or []),
            low_retrieval_agreement=bool(assessment.get("low_retrieval_agreement")),
            model_disagreement=bool(assessment.get("model_disagreement")),
            tool_mismatch=bool(assessment.get("tool_mismatch")),
            low_evidence_quality=bool(assessment.get("low_evidence_quality")),
            ambiguous_intent=bool(assessment.get("ambiguous_intent")),
            verifier_failure=bool(assessment.get("verifier_failure")),
        )
    recovery = []
    if stop_active:
        recovery.append("operator_reset_required")
    if assessment.source_failure_count:
        recovery.append("retry_degraded_source_or_continue_with_caveat")
    if assessment.retrieval_insufficient:
        recovery.append("request_clarification_or_authorized_retrieval")
    if assessment.ambiguous_intent:
        recovery.append("request_intent_clarification")
    if assessment.tool_mismatch:
        recovery.append("retry_or_use_authorized_alternative_tool")
    if assessment.verifier_failure or assessment.model_disagreement:
        recovery.append("increase_verification_or_return_provisional_result")
    raw_resources = dict(resource_state or {})
    system = dict(raw_resources.get("system") or {})
    gpu = dict(raw_resources.get("gpu") or {})
    resource_summary = {
        "cpu_percent": system.get("cpu_percent"),
        "ram_available_mb": system.get("ram_available_mb"),
        "process_rss_mb": system.get("process_rss_mb"),
        "gpu_available": bool(gpu.get("available")),
        "gpu_device_count": len(list(gpu.get("devices") or [])),
        "compute_queue_depth": int(
            dict(raw_resources.get("compute_queue") or {}).get("active_job_count") or 0
        ),
    }
    return {
        "contract": "bounded-operational-self-model-v1",
        "selected_gear": selected_gear,
        "selected_model": selected_model,
        "selected_device": selected_device,
        "effective_autonomy_level": autonomy_level,
        "internet_enabled": internet_enabled,
        "emergency_stop_active": stop_active,
        "uncertainty_band": assessment.band,
        "uncertainty_reasons": list(assessment.reasons),
        "pending_work_count": max(0, int(pending_work_count)),
        "active_memory_banks": sorted({str(item) for item in active_memory_banks if str(item)}),
        "active_projections": sorted({str(item) for item in active_projections if str(item)}),
        "resource_state": resource_summary,
        "current_constraints": list(dict.fromkeys(str(item) for item in current_constraints if str(item))),
        "recent_tool_model_failures": list(dict.fromkeys(str(item) for item in recent_failures if str(item))),
        "benchmarked_weaknesses": list(dict.fromkeys(str(item) for item in benchmarked_weaknesses if str(item))),
        "safe_recovery_options": recovery,
        "consciousness_claimed": False,
        "hidden_reasoning_exposed": False,
        "private_content_included": False,
    }


__all__ = (
    "UncertaintyAssessment",
    "assess_uncertainty",
    "extend_uncertainty",
    "operational_self_model",
)
