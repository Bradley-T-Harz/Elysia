from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.memory.schemas.memory_item import (
    MemoryClass,
    MemoryMutability,
    MemorySensitivity,
    MemorySourceKind,
    MemoryStatus,
)
from app.memory.schemas.memory_mutation import MemoryMutationActor


class MemoryStoreDecision(str, Enum):
    do_not_store = "do_not_store"
    working_only = "working_only"
    store = "store"
    store_provisional = "store_provisional"
    review_required = "review_required"


@dataclass(frozen=True)
class MemoryCandidate:
    body: str
    title: Optional[str] = None

    source_kind: MemorySourceKind = MemorySourceKind.manual_entry
    source_ref: Optional[str] = None
    source_label: Optional[str] = None

    conversation_id: Optional[str] = None
    project_id: Optional[str] = None

    actor: MemoryMutationActor = MemoryMutationActor.assistant

    explicit_user_declared: bool = False
    explicit_preference: bool = False
    explicit_private: bool = False
    explicit_sealed: bool = False
    review_hint: bool = False

    repetition_count: int = 1
    confidence: Optional[float] = None


@dataclass(frozen=True)
class MemoryClassificationResult:
    memory_class: MemoryClass
    sensitivity: MemorySensitivity
    mutability: MemoryMutability
    status: MemoryStatus

    importance: float
    durable: bool

    store_decision: MemoryStoreDecision
    review_required: bool

    why_stored: str
    reasoning_summary: str


class MemoryClassificationService:
    """Rule-first intake-and-placement organ for memory candidates.

    This service does not write memory or enforce final policy. It classifies a
    candidate into a recommended memory posture so later mutation/boundary logic
    can decide whether to commit it.
    """

    PERSONAL_SENSITIVE_KEYWORDS = {
        "trauma",
        "abuse",
        "diagnosis",
        "medical",
        "therapy",
        "ptsd",
        "depression",
        "anxiety",
        "ssn",
        "social security",
        "bank account",
        "password",
        "secret",
        "private",
        "confidential",
        "suicidal",
        "self harm",
        "self-harm",
        "address",
        "phone number",
        "email password",
    }

    PREFERENCE_KEYWORDS = {
        "i prefer",
        "prefer",
        "i like",
        "i don't like",
        "i do not like",
        "remember that i",
        "from now on",
        "please remember",
        "always use",
        "never use",
    }

    PROJECT_KEYWORDS = {
        "blocker",
        "milestone",
        "deadline",
        "decision",
        "constraint",
        "scope",
        "phase",
        "stage",
        "roadmap",
        "project",
        "task",
        "todo",
        "to-do",
    }

    CONVERSATION_KEYWORDS = {
        "unresolved",
        "follow up",
        "follow-up",
        "thread",
        "summary",
        "asked",
        "question",
        "next step",
        "next steps",
    }

    OPERATIONAL_KEYWORDS = {
        "command",
        "cli",
        "shell",
        "path",
        "environment",
        "env",
        "setup",
        "install",
        "configure",
        "config",
        "service",
        "port",
        "host",
        "loopback",
    }

    def __init__(
        self,
        *,
        low_confidence_threshold: float = 0.65,
        review_preference_threshold: int = 2,
        durable_working_max_length: int = 40,
    ) -> None:
        self._low_confidence_threshold = low_confidence_threshold
        self._review_preference_threshold = review_preference_threshold
        self._durable_working_max_length = durable_working_max_length

    def classify_candidate(self, candidate: MemoryCandidate) -> MemoryClassificationResult:
        body = candidate.body.strip()
        if not body:
            raise ValueError("Memory candidate body cannot be empty.")

        memory_class = self._classify_memory_class(candidate)
        sensitivity = self._classify_sensitivity(candidate, memory_class)
        status = self._classify_status(candidate, memory_class)
        mutability = self._classify_mutability(candidate, memory_class, status)
        importance = self._classify_importance(candidate, memory_class, status)
        durable = self._classify_durability(candidate, memory_class, status)
        review_required = self._requires_review(candidate, memory_class, sensitivity, status)
        store_decision = self._classify_store_decision(
            candidate=candidate,
            memory_class=memory_class,
            status=status,
            review_required=review_required,
            durable=durable,
        )
        why_stored = self._build_why_stored(
            candidate=candidate,
            memory_class=memory_class,
            status=status,
            review_required=review_required,
            durable=durable,
        )
        reasoning_summary = self._build_reasoning_summary(
            candidate=candidate,
            memory_class=memory_class,
            sensitivity=sensitivity,
            status=status,
            store_decision=store_decision,
            review_required=review_required,
        )

        return MemoryClassificationResult(
            memory_class=memory_class,
            sensitivity=sensitivity,
            mutability=mutability,
            status=status,
            importance=importance,
            durable=durable,
            store_decision=store_decision,
            review_required=review_required,
            why_stored=why_stored,
            reasoning_summary=reasoning_summary,
        )

    def _classify_memory_class(self, candidate: MemoryCandidate) -> MemoryClass:
        body = candidate.body.casefold()
        title = (candidate.title or "").casefold()

        if candidate.explicit_sealed or candidate.explicit_private:
            return MemoryClass.sealed_private

        if candidate.source_kind == MemorySourceKind.runtime_trace:
            if self._contains_any(body, self.OPERATIONAL_KEYWORDS) or self._contains_any(title, self.OPERATIONAL_KEYWORDS):
                return MemoryClass.operational
            return MemoryClass.audit

        if candidate.source_kind == MemorySourceKind.research_source:
            return MemoryClass.research

        if candidate.explicit_preference or (
            candidate.explicit_user_declared and self._contains_any(body, self.PREFERENCE_KEYWORDS)
        ):
            return MemoryClass.preference

        if candidate.project_id and (
            self._contains_any(body, self.PROJECT_KEYWORDS)
            or self._contains_any(title, self.PROJECT_KEYWORDS)
        ):
            return MemoryClass.project

        if candidate.project_id and candidate.source_kind in {
            MemorySourceKind.project_update,
            MemorySourceKind.imported_file,
        }:
            return MemoryClass.project

        if candidate.source_kind == MemorySourceKind.imported_file:
            return MemoryClass.research if not candidate.project_id else MemoryClass.project

        if candidate.conversation_id and (
            self._contains_any(body, self.CONVERSATION_KEYWORDS)
            or self._contains_any(title, self.CONVERSATION_KEYWORDS)
        ):
            return MemoryClass.conversation

        if candidate.explicit_user_declared and candidate.conversation_id:
            return MemoryClass.conversation

        return MemoryClass.working

    def _classify_sensitivity(
        self,
        candidate: MemoryCandidate,
        memory_class: MemoryClass,
    ) -> MemorySensitivity:
        body = candidate.body.casefold()

        if candidate.explicit_sealed or memory_class == MemoryClass.sealed_private:
            return MemorySensitivity.sealed

        if candidate.explicit_private or self._contains_any(body, self.PERSONAL_SENSITIVE_KEYWORDS):
            return MemorySensitivity.private

        if memory_class == MemoryClass.audit:
            return MemorySensitivity.internal

        if memory_class == MemoryClass.research and candidate.source_kind == MemorySourceKind.research_source:
            return MemorySensitivity.public

        return MemorySensitivity.internal

    def _classify_status(
        self,
        candidate: MemoryCandidate,
        memory_class: MemoryClass,
    ) -> MemoryStatus:
        if candidate.review_hint:
            return MemoryStatus.provisional

        if memory_class == MemoryClass.preference and not candidate.explicit_user_declared:
            return MemoryStatus.provisional

        if memory_class == MemoryClass.research:
            if candidate.confidence is None or candidate.confidence < self._low_confidence_threshold:
                return MemoryStatus.provisional

        if candidate.source_kind == MemorySourceKind.assistant_inference:
            return MemoryStatus.provisional

        return MemoryStatus.active

    def _classify_mutability(
        self,
        candidate: MemoryCandidate,
        memory_class: MemoryClass,
        status: MemoryStatus,
    ) -> MemoryMutability:
        if memory_class == MemoryClass.audit:
            return MemoryMutability.append_only

        if memory_class == MemoryClass.sealed_private:
            return MemoryMutability.review_required

        if memory_class == MemoryClass.research:
            return (
                MemoryMutability.review_required
                if status == MemoryStatus.provisional
                else MemoryMutability.append_only
            )

        if memory_class == MemoryClass.preference and not candidate.explicit_user_declared:
            return MemoryMutability.review_required

        if status == MemoryStatus.provisional:
            return MemoryMutability.review_required

        return MemoryMutability.live_editable

    def _classify_importance(
        self,
        candidate: MemoryCandidate,
        memory_class: MemoryClass,
        status: MemoryStatus,
    ) -> float:
        base_by_class = {
            MemoryClass.working: 0.25,
            MemoryClass.conversation: 0.45,
            MemoryClass.project: 0.75,
            MemoryClass.research: 0.65,
            MemoryClass.operational: 0.55,
            MemoryClass.preference: 0.70,
            MemoryClass.sealed_private: 0.70,
            MemoryClass.audit: 0.50,
        }

        importance = base_by_class[memory_class]

        if candidate.explicit_user_declared:
            importance += 0.10
        if candidate.explicit_preference:
            importance += 0.08
        if candidate.project_id and memory_class == MemoryClass.project:
            importance += 0.05
        if candidate.repetition_count > 1:
            importance += min(0.12, 0.03 * (candidate.repetition_count - 1))
        if status == MemoryStatus.provisional:
            importance -= 0.08
        if candidate.confidence is not None:
            importance += (candidate.confidence - 0.5) * 0.15

        return max(0.0, min(1.0, round(importance, 3)))

    def _classify_durability(
        self,
        candidate: MemoryCandidate,
        memory_class: MemoryClass,
        status: MemoryStatus,
    ) -> bool:
        if memory_class in {
            MemoryClass.project,
            MemoryClass.research,
            MemoryClass.operational,
            MemoryClass.preference,
            MemoryClass.sealed_private,
            MemoryClass.audit,
        }:
            return True

        if memory_class == MemoryClass.conversation:
            return True

        if memory_class == MemoryClass.working:
            if candidate.explicit_user_declared:
                return True
            if len(candidate.body.strip()) >= self._durable_working_max_length:
                return True
            if status == MemoryStatus.provisional:
                return False

        return False

    def _requires_review(
        self,
        candidate: MemoryCandidate,
        memory_class: MemoryClass,
        sensitivity: MemorySensitivity,
        status: MemoryStatus,
    ) -> bool:
        if candidate.review_hint:
            return True

        if sensitivity in {MemorySensitivity.private, MemorySensitivity.sealed}:
            return True

        if memory_class == MemoryClass.preference and not candidate.explicit_user_declared:
            return True

        if candidate.source_kind == MemorySourceKind.assistant_inference and memory_class in {
            MemoryClass.preference,
            MemoryClass.sealed_private,
        }:
            return True

        if (
            candidate.source_kind == MemorySourceKind.assistant_inference
            and candidate.repetition_count < self._review_preference_threshold
        ):
            return True

        if status == MemoryStatus.provisional and candidate.actor == MemoryMutationActor.assistant:
            return True

        return False

    def _classify_store_decision(
        self,
        *,
        candidate: MemoryCandidate,
        memory_class: MemoryClass,
        status: MemoryStatus,
        review_required: bool,
        durable: bool,
    ) -> MemoryStoreDecision:
        body = candidate.body.strip()

        if len(body) < 8 and not candidate.explicit_user_declared and memory_class == MemoryClass.working:
            return MemoryStoreDecision.do_not_store

        if review_required:
            return MemoryStoreDecision.review_required

        if memory_class == MemoryClass.working and not durable:
            return MemoryStoreDecision.working_only

        if status == MemoryStatus.provisional:
            return MemoryStoreDecision.store_provisional

        return MemoryStoreDecision.store

    def _build_why_stored(
        self,
        *,
        candidate: MemoryCandidate,
        memory_class: MemoryClass,
        status: MemoryStatus,
        review_required: bool,
        durable: bool,
    ) -> str:
        if memory_class == MemoryClass.preference:
            if candidate.explicit_user_declared:
                return "User explicitly stated a stable preference worth preserving."
            return "Possible preference candidate detected and kept provisionally for review."

        if memory_class == MemoryClass.project:
            return "Project-scoped information was captured to preserve continuity, decisions, or blockers."

        if memory_class == MemoryClass.research:
            if status == MemoryStatus.provisional:
                return "Research-related information was captured provisionally pending stronger confidence or review."
            return "Research-related information was captured for durable evidence continuity."

        if memory_class == MemoryClass.operational:
            return "Operational truth or environment procedure was captured for repeatable system continuity."

        if memory_class == MemoryClass.audit:
            return "Audit-worthy system or runtime trace was captured for accountability."

        if memory_class == MemoryClass.sealed_private:
            return "Sensitive private material was classified into sealed memory for stronger protection."

        if memory_class == MemoryClass.conversation:
            return "Conversation continuity information was captured to preserve unresolved context and follow-through."

        if durable:
            return "Working context was preserved because it appeared important enough to outlast the immediate moment."

        if review_required:
            return "Candidate memory was retained cautiously for review rather than fully trusted."

        return "Working context was retained for near-term continuity."

    def _build_reasoning_summary(
        self,
        *,
        candidate: MemoryCandidate,
        memory_class: MemoryClass,
        sensitivity: MemorySensitivity,
        status: MemoryStatus,
        store_decision: MemoryStoreDecision,
        review_required: bool,
    ) -> str:
        parts = [
            f"class={memory_class.value}",
            f"sensitivity={sensitivity.value}",
            f"status={status.value}",
            f"store_decision={store_decision.value}",
        ]

        if candidate.project_id:
            parts.append("project-scoped")
        if candidate.conversation_id:
            parts.append("conversation-linked")
        if candidate.explicit_user_declared:
            parts.append("user-declared")
        if candidate.source_kind == MemorySourceKind.assistant_inference:
            parts.append("assistant-inferred")
        if review_required:
            parts.append("review-required")

        return "; ".join(parts)

    def _contains_any(self, text: str, phrases: set[str]) -> bool:
        return any(phrase in text for phrase in phrases)
