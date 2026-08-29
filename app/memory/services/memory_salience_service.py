from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.memory.schemas.memory_item import (
    MemoryClass,
    MemoryItem,
    MemorySensitivity,
    MemorySourceKind,
    MemoryStatus,
)
from app.memory.services.memory_classification_service import (
    MemoryCandidate,
    MemoryClassificationResult,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class MemorySalienceContext:
    recurrence_count: int = 1
    current_task_active: bool = False
    deadline_near: bool = False
    explicit_user_emphasis: bool = False
    current_project_id: Optional[str] = None
    current_conversation_id: Optional[str] = None


@dataclass(frozen=True)
class MemorySalienceResult:
    salience_score: float
    recurrence_score: float
    consequence_score: float
    urgency_score: float
    durability_score: float
    source_trust_adjustment: float

    resurface_recommended: bool
    pin_recommended: bool
    promotion_recommended: bool
    archive_recommended: bool

    reasoning_summary: str


class MemorySalienceService:
    """Priority-and-significance organ for memory.

    This service does not mutate memory or define policy. It scores how much a
    memory item or classified candidate should matter right now, and whether it
    likely deserves pinning, resurfacing, promotion, or archiving attention.
    """

    CONSEQUENCE_KEYWORDS = {
        "blocker",
        "critical",
        "urgent",
        "deadline",
        "milestone",
        "decision",
        "constraint",
        "security",
        "privacy",
        "safety",
        "architecture",
        "deployment",
        "failure",
        "broken",
        "must",
        "required",
    }

    URGENCY_KEYWORDS = {
        "today",
        "tomorrow",
        "asap",
        "urgent",
        "soon",
        "immediately",
        "now",
        "deadline",
        "blocked",
        "waiting on",
    }

    EMPHASIS_KEYWORDS = {
        "remember this",
        "important",
        "do not forget",
        "don't forget",
        "from now on",
        "must remember",
        "critical",
    }

    CLASS_DURABILITY_BASE = {
        MemoryClass.working: 0.22,
        MemoryClass.conversation: 0.48,
        MemoryClass.project: 0.82,
        MemoryClass.research: 0.72,
        MemoryClass.operational: 0.66,
        MemoryClass.preference: 0.78,
        MemoryClass.sealed_private: 0.62,
        MemoryClass.audit: 0.55,
    }

    SOURCE_TRUST_BASE = {
        MemorySourceKind.user_message: 0.90,
        MemorySourceKind.manual_entry: 0.88,
        MemorySourceKind.project_update: 0.82,
        MemorySourceKind.research_source: 0.80,
        MemorySourceKind.imported_file: 0.74,
        MemorySourceKind.runtime_trace: 0.78,
        MemorySourceKind.system_event: 0.72,
        MemorySourceKind.assistant_inference: 0.48,
    }

    def __init__(
        self,
        *,
        recurrence_weight: float = 0.22,
        consequence_weight: float = 0.28,
        urgency_weight: float = 0.20,
        durability_weight: float = 0.20,
        trust_weight: float = 0.10,
    ) -> None:
        total = (
            recurrence_weight
            + consequence_weight
            + urgency_weight
            + durability_weight
            + trust_weight
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError("Salience weights must sum to 1.0.")

        self._recurrence_weight = recurrence_weight
        self._consequence_weight = consequence_weight
        self._urgency_weight = urgency_weight
        self._durability_weight = durability_weight
        self._trust_weight = trust_weight

    def score_item(
        self,
        item: MemoryItem,
        *,
        context: Optional[MemorySalienceContext] = None,
    ) -> MemorySalienceResult:
        context = context or MemorySalienceContext()

        recurrence_score = self._score_recurrence(
            recurrence_count=context.recurrence_count,
            explicit_user_emphasis=context.explicit_user_emphasis or item.flags.user_declared,
        )
        consequence_score = self._score_consequence_for_item(item=item)
        urgency_score = self._score_urgency_for_item(item=item, context=context)
        durability_score = self._score_durability_for_item(item=item, context=context)
        source_trust_adjustment = self._score_source_trust_adjustment(item.source.source_kind)

        baseline_importance = clamp(item.importance)
        raw_salience = (
            (recurrence_score * self._recurrence_weight)
            + (consequence_score * self._consequence_weight)
            + (urgency_score * self._urgency_weight)
            + (durability_score * self._durability_weight)
            + (source_trust_adjustment * self._trust_weight)
        )

        salience_score = clamp((raw_salience * 0.7) + (baseline_importance * 0.3))
        salience_score = self._apply_sensitivity_and_status_adjustments(
            salience_score=salience_score,
            sensitivity=item.sensitivity,
            status=item.status,
        )

        pin_recommended = self._recommend_pin_for_item(item=item, salience_score=salience_score)
        promotion_recommended = self._recommend_promotion_for_item(
            item=item,
            salience_score=salience_score,
            recurrence_score=recurrence_score,
            durability_score=durability_score,
        )
        archive_recommended = self._recommend_archive_for_item(
            item=item,
            salience_score=salience_score,
            urgency_score=urgency_score,
            recurrence_score=recurrence_score,
        )
        resurface_recommended = self._recommend_resurface_for_item(
            item=item,
            salience_score=salience_score,
            urgency_score=urgency_score,
            recurrence_score=recurrence_score,
        )

        reasoning_summary = self._build_reasoning_summary(
            salience_score=salience_score,
            recurrence_score=recurrence_score,
            consequence_score=consequence_score,
            urgency_score=urgency_score,
            durability_score=durability_score,
            source_trust_adjustment=source_trust_adjustment,
            pin_recommended=pin_recommended,
            promotion_recommended=promotion_recommended,
            archive_recommended=archive_recommended,
            resurface_recommended=resurface_recommended,
            memory_class=item.memory_class,
            sensitivity=item.sensitivity,
        )

        return MemorySalienceResult(
            salience_score=round(salience_score, 3),
            recurrence_score=round(recurrence_score, 3),
            consequence_score=round(consequence_score, 3),
            urgency_score=round(urgency_score, 3),
            durability_score=round(durability_score, 3),
            source_trust_adjustment=round(source_trust_adjustment, 3),
            resurface_recommended=resurface_recommended,
            pin_recommended=pin_recommended,
            promotion_recommended=promotion_recommended,
            archive_recommended=archive_recommended,
            reasoning_summary=reasoning_summary,
        )

    def score_candidate(
        self,
        candidate: MemoryCandidate,
        classification: MemoryClassificationResult,
        *,
        context: Optional[MemorySalienceContext] = None,
    ) -> MemorySalienceResult:
        context = context or MemorySalienceContext()

        recurrence_score = self._score_recurrence(
            recurrence_count=max(candidate.repetition_count, context.recurrence_count),
            explicit_user_emphasis=context.explicit_user_emphasis or candidate.explicit_user_declared,
        )
        consequence_score = self._score_consequence_for_candidate(
            candidate=candidate,
            classification=classification,
        )
        urgency_score = self._score_urgency_for_candidate(candidate=candidate, context=context)
        durability_score = self._score_durability_for_candidate(
            candidate=candidate,
            classification=classification,
        )
        source_trust_adjustment = self._score_source_trust_adjustment(candidate.source_kind)

        raw_salience = (
            (recurrence_score * self._recurrence_weight)
            + (consequence_score * self._consequence_weight)
            + (urgency_score * self._urgency_weight)
            + (durability_score * self._durability_weight)
            + (source_trust_adjustment * self._trust_weight)
        )

        salience_score = clamp((raw_salience * 0.7) + (classification.importance * 0.3))
        salience_score = self._apply_sensitivity_and_status_adjustments(
            salience_score=salience_score,
            sensitivity=classification.sensitivity,
            status=classification.status,
        )

        pin_recommended = (
            salience_score >= 0.82
            and classification.memory_class in {MemoryClass.project, MemoryClass.preference}
            and classification.sensitivity not in {MemorySensitivity.private, MemorySensitivity.sealed}
        )
        promotion_recommended = (
            salience_score >= 0.70
            and classification.memory_class in {MemoryClass.working, MemoryClass.conversation}
            and classification.durable
        )
        archive_recommended = (
            salience_score <= 0.28
            and classification.memory_class == MemoryClass.working
            and not classification.review_required
        )
        resurface_recommended = (
            salience_score >= 0.68
            and recurrence_score >= 0.55
            and classification.sensitivity not in {MemorySensitivity.private, MemorySensitivity.sealed}
        )

        reasoning_summary = self._build_reasoning_summary(
            salience_score=salience_score,
            recurrence_score=recurrence_score,
            consequence_score=consequence_score,
            urgency_score=urgency_score,
            durability_score=durability_score,
            source_trust_adjustment=source_trust_adjustment,
            pin_recommended=pin_recommended,
            promotion_recommended=promotion_recommended,
            archive_recommended=archive_recommended,
            resurface_recommended=resurface_recommended,
            memory_class=classification.memory_class,
            sensitivity=classification.sensitivity,
        )

        return MemorySalienceResult(
            salience_score=round(salience_score, 3),
            recurrence_score=round(recurrence_score, 3),
            consequence_score=round(consequence_score, 3),
            urgency_score=round(urgency_score, 3),
            durability_score=round(durability_score, 3),
            source_trust_adjustment=round(source_trust_adjustment, 3),
            resurface_recommended=resurface_recommended,
            pin_recommended=pin_recommended,
            promotion_recommended=promotion_recommended,
            archive_recommended=archive_recommended,
            reasoning_summary=reasoning_summary,
        )

    def _score_recurrence(
        self,
        *,
        recurrence_count: int,
        explicit_user_emphasis: bool,
    ) -> float:
        recurrence = min(max(recurrence_count, 1), 8)
        score = 0.18 + ((recurrence - 1) * 0.10)
        if explicit_user_emphasis:
            score += 0.12
        return clamp(score)

    def _score_consequence_for_item(self, *, item: MemoryItem) -> float:
        text = " ".join((item.title, item.body, item.why_stored)).casefold()
        score = 0.20

        if item.memory_class == MemoryClass.project:
            score += 0.28
        elif item.memory_class == MemoryClass.preference:
            score += 0.18
        elif item.memory_class == MemoryClass.research:
            score += 0.16
        elif item.memory_class == MemoryClass.operational:
            score += 0.18

        if self._contains_any(text, self.CONSEQUENCE_KEYWORDS):
            score += 0.20
        if item.flags.user_declared:
            score += 0.08
        if item.flags.verified:
            score += 0.05

        return clamp(score)

    def _score_consequence_for_candidate(
        self,
        *,
        candidate: MemoryCandidate,
        classification: MemoryClassificationResult,
    ) -> float:
        text = " ".join(filter(None, [candidate.title, candidate.body])).casefold()
        score = 0.18

        if classification.memory_class == MemoryClass.project:
            score += 0.28
        elif classification.memory_class == MemoryClass.preference:
            score += 0.18
        elif classification.memory_class == MemoryClass.research:
            score += 0.16
        elif classification.memory_class == MemoryClass.operational:
            score += 0.18

        if self._contains_any(text, self.CONSEQUENCE_KEYWORDS):
            score += 0.20
        if candidate.explicit_user_declared:
            score += 0.08

        return clamp(score)

    def _score_urgency_for_item(
        self,
        *,
        item: MemoryItem,
        context: MemorySalienceContext,
    ) -> float:
        text = " ".join((item.title, item.body, item.why_stored)).casefold()
        score = 0.08

        if self._contains_any(text, self.URGENCY_KEYWORDS):
            score += 0.30
        if context.current_task_active:
            score += 0.18
        if context.deadline_near:
            score += 0.18

        age_days = max((utc_now() - item.updated_at_utc).total_seconds() / 86400.0, 0.0)
        if age_days <= 2:
            score += 0.12
        elif age_days > 14:
            score -= 0.08

        return clamp(score)

    def _score_urgency_for_candidate(
        self,
        *,
        candidate: MemoryCandidate,
        context: MemorySalienceContext,
    ) -> float:
        text = " ".join(filter(None, [candidate.title, candidate.body])).casefold()
        score = 0.10

        if self._contains_any(text, self.URGENCY_KEYWORDS):
            score += 0.30
        if context.current_task_active:
            score += 0.18
        if context.deadline_near:
            score += 0.18

        return clamp(score)

    def _score_durability_for_item(
        self,
        *,
        item: MemoryItem,
        context: MemorySalienceContext,
    ) -> float:
        score = self.CLASS_DURABILITY_BASE[item.memory_class]

        if item.flags.user_declared:
            score += 0.10
        if item.flags.verified:
            score += 0.05
        if context.current_project_id and item.context_links.project_id == context.current_project_id:
            score += 0.06
        if context.current_conversation_id and item.context_links.conversation_id == context.current_conversation_id:
            score += 0.04
        if item.status == MemoryStatus.provisional:
            score -= 0.12
        if item.status == MemoryStatus.archived:
            score -= 0.22
        if item.status == MemoryStatus.superseded:
            score -= 0.28

        return clamp(score)

    def _score_durability_for_candidate(
        self,
        *,
        candidate: MemoryCandidate,
        classification: MemoryClassificationResult,
    ) -> float:
        score = self.CLASS_DURABILITY_BASE[classification.memory_class]

        if candidate.explicit_user_declared:
            score += 0.10
        if classification.status == MemoryStatus.provisional:
            score -= 0.12
        if candidate.repetition_count > 1:
            score += min(0.12, 0.03 * (candidate.repetition_count - 1))

        return clamp(score)

    def _score_source_trust_adjustment(self, source_kind: MemorySourceKind) -> float:
        return self.SOURCE_TRUST_BASE.get(source_kind, 0.5)

    def _apply_sensitivity_and_status_adjustments(
        self,
        *,
        salience_score: float,
        sensitivity: MemorySensitivity,
        status: MemoryStatus,
    ) -> float:
        adjusted = salience_score

        if sensitivity == MemorySensitivity.private:
            adjusted -= 0.05
        elif sensitivity == MemorySensitivity.sealed:
            adjusted -= 0.10

        if status == MemoryStatus.provisional:
            adjusted -= 0.05
        elif status == MemoryStatus.archived:
            adjusted -= 0.15
        elif status == MemoryStatus.superseded:
            adjusted -= 0.20
        elif status == MemoryStatus.blocked:
            adjusted -= 0.12

        return clamp(adjusted)

    def _recommend_pin_for_item(
        self,
        *,
        item: MemoryItem,
        salience_score: float,
    ) -> bool:
        if item.sensitivity in {MemorySensitivity.private, MemorySensitivity.sealed}:
            return False
        if item.flags.pinned:
            return False
        return (
            salience_score >= 0.82
            and item.memory_class in {MemoryClass.project, MemoryClass.preference}
        )

    def _recommend_promotion_for_item(
        self,
        *,
        item: MemoryItem,
        salience_score: float,
        recurrence_score: float,
        durability_score: float,
    ) -> bool:
        if item.memory_class not in {MemoryClass.working, MemoryClass.conversation}:
            return False
        if item.sensitivity == MemorySensitivity.sealed:
            return False
        return (
            salience_score >= 0.70
            and recurrence_score >= 0.55
            and durability_score >= 0.55
        )

    def _recommend_archive_for_item(
        self,
        *,
        item: MemoryItem,
        salience_score: float,
        urgency_score: float,
        recurrence_score: float,
    ) -> bool:
        if item.memory_class not in {MemoryClass.working, MemoryClass.conversation}:
            return False
        if item.status in {MemoryStatus.archived, MemoryStatus.superseded}:
            return False
        if item.flags.pinned:
            return False
        return (
            salience_score <= 0.28
            and urgency_score <= 0.22
            and recurrence_score <= 0.22
        )

    def _recommend_resurface_for_item(
        self,
        *,
        item: MemoryItem,
        salience_score: float,
        urgency_score: float,
        recurrence_score: float,
    ) -> bool:
        if item.sensitivity in {MemorySensitivity.private, MemorySensitivity.sealed}:
            return False
        if item.status in {MemoryStatus.archived, MemoryStatus.superseded, MemoryStatus.blocked}:
            return False
        return (
            salience_score >= 0.68
            and (urgency_score >= 0.50 or recurrence_score >= 0.60)
        )

    def _build_reasoning_summary(
        self,
        *,
        salience_score: float,
        recurrence_score: float,
        consequence_score: float,
        urgency_score: float,
        durability_score: float,
        source_trust_adjustment: float,
        pin_recommended: bool,
        promotion_recommended: bool,
        archive_recommended: bool,
        resurface_recommended: bool,
        memory_class: MemoryClass,
        sensitivity: MemorySensitivity,
    ) -> str:
        parts = [
            f"class={memory_class.value}",
            f"sensitivity={sensitivity.value}",
            f"salience={salience_score:.3f}",
            f"recurrence={recurrence_score:.3f}",
            f"consequence={consequence_score:.3f}",
            f"urgency={urgency_score:.3f}",
            f"durability={durability_score:.3f}",
            f"trust={source_trust_adjustment:.3f}",
        ]

        recommendations = []
        if pin_recommended:
            recommendations.append("pin")
        if promotion_recommended:
            recommendations.append("promote")
        if archive_recommended:
            recommendations.append("archive")
        if resurface_recommended:
            recommendations.append("resurface")

        if recommendations:
            parts.append("recommend=" + ",".join(recommendations))
        else:
            parts.append("recommend=none")

        return "; ".join(parts)

    def _contains_any(self, text: str, phrases: set[str]) -> bool:
        return any(phrase in text for phrase in phrases)
