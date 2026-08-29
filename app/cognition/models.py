"""Typed, bounded contracts for Elysia's one governed cognition path."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Privacy = Literal["normal", "private", "sealed"]


@dataclass(frozen=True)
class CognitionCandidate:
    candidate_id: str
    source_type: str
    source_id: str
    owner_user_id: str | None
    space_id: str | None
    privacy: Privacy
    form: str
    scope: str
    content_excerpt_or_pointer: str
    observed_at: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    confidence: float | None = None
    source_authority: str = "derived"
    provenance: dict[str, Any] = field(default_factory=dict)
    estimated_tokens: int = 0
    project_id: str | None = None
    conversation_id: str | None = None
    status: str = "active"
    user_confirmed: bool = False
    importance: float = 0.5
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    rank_score: float = 0.0
    rank_reasons: tuple[str, ...] = ()
    untrusted: bool = False

    def to_payload(self, *, include_content: bool = False) -> dict[str, Any]:
        payload = asdict(self)
        if not include_content:
            payload.pop("content_excerpt_or_pointer", None)
        return payload


@dataclass(frozen=True)
class ExcludedCandidate:
    candidate_id: str
    source_type: str
    reason: str

    def to_payload(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class ContextReceipt:
    receipt_version: str
    request_id: str
    model_runtime_tag: str
    model_context_window: int
    reasoning_gear: str
    retrieval_share: float
    token_budget: dict[str, int]
    considered: list[dict[str, str]] = field(default_factory=list)
    retrieved_ids: list[str] = field(default_factory=list)
    admitted: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[dict[str, str]] = field(default_factory=list)
    privacy_scopes: list[str] = field(default_factory=list)
    projection_versions: dict[str, str] = field(default_factory=dict)
    contradiction_handling: list[dict[str, str]] = field(default_factory=list)
    research: dict[str, Any] = field(default_factory=dict)
    governor: dict[str, Any] = field(default_factory=dict)
    admission_actions: list[dict[str, str]] = field(default_factory=list)
    uncertainty: dict[str, Any] = field(default_factory=dict)
    compute: dict[str, Any] = field(default_factory=dict)
    generated_at_utc: str = ""

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GlobalWorkingWorkspace:
    workspace_version: str
    request_id: str
    reasoning_gear: str
    model_runtime_tag: str
    model_context_window: int
    admitted_candidates: list[CognitionCandidate]
    context_sections: list[dict[str, Any]]
    context_text: str
    receipt: ContextReceipt
    assembly_latency_ms: float

    def to_payload(self, *, include_content: bool = False) -> dict[str, Any]:
        return {
            "workspace_version": self.workspace_version,
            "request_id": self.request_id,
            "reasoning_gear": self.reasoning_gear,
            "model_runtime_tag": self.model_runtime_tag,
            "model_context_window": self.model_context_window,
            "admitted_candidates": [
                item.to_payload(include_content=include_content)
                for item in self.admitted_candidates
            ],
            "context_sections": self.context_sections if include_content else [
                {
                    key: value
                    for key, value in section.items()
                    if key not in {"content", "items"}
                }
                for section in self.context_sections
            ],
            "receipt": self.receipt.to_payload(),
            "assembly_latency_ms": self.assembly_latency_ms,
        }


def estimate_tokens(text: str) -> int:
    """Conservative local estimate; avoids adding a tokenizer dependency to Core."""
    compact = str(text or "").strip()
    if not compact:
        return 0
    return max(1, (len(compact.encode("utf-8")) + 3) // 4)


__all__ = (
    "CognitionCandidate",
    "ContextReceipt",
    "ExcludedCandidate",
    "GlobalWorkingWorkspace",
    "estimate_tokens",
)
