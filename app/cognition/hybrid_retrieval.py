"""Transparent reciprocal-rank fusion for canonical normal Memory.

FTS5 is mandatory.  The semantic projection contributes only when the
explicit local profile is healthy.  Candidate identifiers returned by Qdrant
have already been re-read from canonical Memory and re-authorized.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.cognition.fts_projection import FtsMemoryProjection, PROJECTION_VERSION
from app.cognition.semantic_projection import (
    SEMANTIC_ABSTRACTION_VERSION,
    SemanticMemoryProjection,
    SemanticProjectionError,
)


FUSION_VERSION = "weighted-rrf-lexical040-semantic060-k60-v1"
RRF_K = 60.0
LEXICAL_WEIGHT = 0.40
SEMANTIC_WEIGHT = 0.60
MAX_RRF = (LEXICAL_WEIGHT + SEMANTIC_WEIGHT) / (RRF_K + 1.0)


@dataclass(frozen=True)
class HybridRetrievalResult:
    rows: list[dict[str, Any]]
    semantic_state: str
    projection_versions: dict[str, str]


def _linked_id(record: Any, target_type: str) -> str | None:
    for relation in list(getattr(record, "relations", []) or []):
        if str(relation.get("target_type")) == target_type:
            return str(relation.get("target_id") or "") or None
    return None


def _record_row(record: Any) -> dict[str, Any]:
    return {
        "candidate_id": str(record.memory_id),
        "owner_user_id": str(record.owner_user_id),
        "space_id": str(record.space_id) if record.space_id else None,
        "scope": str(getattr(record.scope, "value", record.scope)),
        "form": str(getattr(record.form, "value", record.form)),
        "privacy": str(getattr(record.privacy, "value", record.privacy)),
        "status": str(getattr(record.status, "value", record.status)),
        "source_type": "memory",
        "source_id": str(record.memory_id),
        "project_id": _linked_id(record, "project"),
        "conversation_id": _linked_id(record, "conversation"),
        "observed_at": record.observed_at,
        "valid_from": record.valid_from,
        "valid_until": record.valid_until,
        "importance": float(record.importance),
        "pinned": bool(record.pinned),
        "confidence": record.confidence,
        "user_confirmed": int(record.user_confirmed),
        "updated_at": str(record.updated_at),
        "title": str(record.title or ""),
        "body": str(record.body or ""),
        "why_stored": str(record.why_stored or ""),
    }


class HybridMemoryRetriever:
    def __init__(
        self,
        *,
        lexical: FtsMemoryProjection,
        semantic: SemanticMemoryProjection | None = None,
    ) -> None:
        self.lexical = lexical
        self.semantic_config_error = False
        if semantic is not None:
            self.semantic = semantic
        else:
            try:
                self.semantic = SemanticMemoryProjection(
                    paths=lexical.paths,
                    repository=lexical.repository,
                    fabric=lexical.fabric,
                )
            except SemanticProjectionError:
                self.semantic = None
                self.semantic_config_error = True

    def search_normal(
        self,
        principal: Any,
        text: str,
        *,
        scope: str | None = None,
        form: str | None = None,
        status: str | None = None,
        space_id: str | None = None,
        project_id: str | None = None,
        conversation_id: str | None = None,
        space_ids: list[str] | None = None,
        limit: int = 40,
        offset: int = 0,
    ) -> HybridRetrievalResult:
        requested = max(1, min(500, int(limit) + max(0, int(offset))))
        lexical_rows = self.lexical.search(
            principal,
            text,
            scope=scope,
            form=form,
            status=status,
            space_id=space_id,
            project_id=project_id,
            conversation_id=conversation_id,
            space_ids=space_ids,
            limit=requested,
        )
        semantic_rows: list[dict[str, Any]] = []
        semantic_state = (
            "degraded_fts_fallback" if self.semantic_config_error
            else "optional_not_installed"
        )
        if self.semantic is not None and self.semantic.configured:
            try:
                semantic_rows = self.semantic.search(
                    principal,
                    text,
                    authorized_space_ids=space_ids or [],
                    scope=scope,
                    form=form,
                    status=status,
                    space_id=space_id,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    limit=requested,
                )
                semantic_state = "ready"
            except Exception:
                # FTS remains production-capable when the derived profile is
                # stopped, absent, corrupt, rebuilding, or resource-limited.
                semantic_state = "degraded_fts_fallback"

        rows = {str(row["candidate_id"]): dict(row) for row in lexical_rows}
        lexical_ranks = {
            str(row["candidate_id"]): rank
            for rank, row in enumerate(lexical_rows, start=1)
        }
        semantic_ranks: dict[str, int] = {}
        semantic_scores: dict[str, float] = {}
        for rank, item in enumerate(semantic_rows, start=1):
            memory_id = str(item["candidate_id"])
            semantic_ranks[memory_id] = rank
            semantic_scores[memory_id] = float(item["semantic_score"])
            rows.setdefault(memory_id, _record_row(item["record"]))

        fused: list[dict[str, Any]] = []
        for memory_id, row in rows.items():
            lexical_rank = lexical_ranks.get(memory_id)
            semantic_rank = semantic_ranks.get(memory_id)
            rrf = 0.0
            if lexical_rank is not None:
                rrf += LEXICAL_WEIGHT / (RRF_K + lexical_rank)
            if semantic_rank is not None:
                rrf += SEMANTIC_WEIGHT / (RRF_K + semantic_rank)
            fused_score = max(0.0, min(1.0, rrf / MAX_RRF))
            item = dict(row)
            item.update({
                "raw_rank": -fused_score,
                "lexical_rank": lexical_rank,
                "semantic_rank": semantic_rank,
                "semantic_score": semantic_scores.get(memory_id, 0.0),
                "fusion_score": fused_score,
                "retrieval_method": (
                    "fts5_qwen_qdrant_hybrid"
                    if lexical_rank is not None and semantic_rank is not None
                    else "qwen_qdrant_semantic"
                    if semantic_rank is not None
                    else "sqlite_fts5_bm25"
                ),
                "fusion_version": FUSION_VERSION,
            })
            fused.append(item)
        fused.sort(key=lambda row: (
            -float(row["fusion_score"]),
            -float(row.get("importance") or 0.0),
            str(row["candidate_id"]),
        ))
        bounded_offset = max(0, int(offset))
        bounded_limit = max(1, min(500, int(limit)))
        return HybridRetrievalResult(
            rows=fused[bounded_offset : bounded_offset + bounded_limit],
            semantic_state=semantic_state,
            projection_versions={
                "lexical": PROJECTION_VERSION,
                "semantic": SEMANTIC_ABSTRACTION_VERSION,
                "fusion": FUSION_VERSION,
            },
        )


__all__ = (
    "FUSION_VERSION", "HybridMemoryRetriever", "HybridRetrievalResult",
    "LEXICAL_WEIGHT", "RRF_K", "SEMANTIC_WEIGHT",
)
