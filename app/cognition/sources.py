"""Read-only bounded adapters around Elysia's existing domain authorities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.cognition.conversation_cognition import build_conversation_hierarchy
from app.cognition.evidence_repository import EvidenceRepository
from app.cognition.fts_projection import FtsMemoryProjection, PROJECTION_VERSION
from app.cognition.hybrid_retrieval import HybridMemoryRetriever
from app.cognition.models import CognitionCandidate, estimate_tokens
from app.install.paths import ElysiaPaths, resolve_elysia_paths


@dataclass(frozen=True)
class CognitionReadRequest:
    query: str
    owner_user_id: str | None
    conversation_id: str | None
    project_id: str | None
    request_id: str
    mode: str
    reasoning_gear: str
    model_runtime_tag: str
    recent_turn_limit: int
    candidate_limit: int
    profile_context: dict[str, Any]
    authorized_space_ids: frozenset[str]
    explicit_sealed_memory: bool = False


class CognitionSource(ABC):
    source_type: str

    @abstractmethod
    def read(self, request: CognitionReadRequest) -> list[CognitionCandidate]: ...


def _candidate(
    *,
    candidate_id: str,
    source_type: str,
    source_id: str,
    content: str,
    owner_user_id: str | None,
    space_id: str | None = None,
    privacy: str = "normal",
    form: str = "episodic",
    scope: str = "user",
    source_authority: str = "canonical",
    project_id: str | None = None,
    conversation_id: str | None = None,
    observed_at: str | None = None,
    valid_from: str | None = None,
    valid_until: str | None = None,
    confidence: float | None = None,
    importance: float = 0.5,
    user_confirmed: bool = False,
    provenance: dict[str, Any] | None = None,
    status: str = "active",
    lexical_score: float = 0.0,
    semantic_score: float = 0.0,
    untrusted: bool = False,
) -> CognitionCandidate:
    bounded = str(content or "")[:12000]
    return CognitionCandidate(
        candidate_id=candidate_id,
        source_type=source_type,
        source_id=source_id,
        owner_user_id=owner_user_id,
        space_id=space_id,
        privacy=privacy if privacy in {"normal", "private", "sealed"} else "normal",  # type: ignore[arg-type]
        form=form,
        scope=scope,
        content_excerpt_or_pointer=bounded,
        observed_at=observed_at,
        valid_from=valid_from,
        valid_until=valid_until,
        confidence=confidence,
        source_authority=source_authority,
        provenance=dict(provenance or {}),
        estimated_tokens=estimate_tokens(bounded),
        project_id=project_id,
        conversation_id=conversation_id,
        status=status,
        user_confirmed=user_confirmed,
        importance=importance,
        lexical_score=lexical_score,
        semantic_score=semantic_score,
        untrusted=untrusted,
    )


class ConversationCognitionSource(CognitionSource):
    source_type = "conversation"

    def __init__(self, *, paths: ElysiaPaths | None = None) -> None:
        self.paths = paths or resolve_elysia_paths()

    def read(self, request: CognitionReadRequest) -> list[CognitionCandidate]:
        if not request.conversation_id:
            return []
        from app.api.conversation_service import get_conversation_thread

        try:
            thread = get_conversation_thread(request.conversation_id)
        except Exception:
            return []
        metadata = dict(thread.get("metadata") or {})
        owner = metadata.get("owner_user_id")
        hierarchy = build_conversation_hierarchy(
            thread,
            owner_user_id=str(owner) if owner else request.owner_user_id,
            generator_model=request.model_runtime_tag,
            paths=self.paths,
        )
        messages = [item for item in thread.get("messages", []) if isinstance(item, dict)]
        recent = messages[-max(2, request.recent_turn_limit) :]
        candidates: list[CognitionCandidate] = []
        for message in recent:
            message_id = str(message.get("message_id") or "")
            content = str(message.get("content") or "")
            if not message_id or not content:
                continue
            candidates.append(
                _candidate(
                    candidate_id=f"conversation:{message_id}",
                    source_type=self.source_type,
                    source_id=message_id,
                    content=f"{str(message.get('role') or 'unknown').title()}: {content}",
                    owner_user_id=str(owner) if owner else request.owner_user_id,
                    form="episodic",
                    scope="conversation",
                    project_id=metadata.get("project_id"),
                    conversation_id=request.conversation_id,
                    observed_at=message.get("created_at_utc"),
                    confidence=1.0,
                    importance=0.9,
                    user_confirmed=str(message.get("role")) == "user",
                    provenance={
                        "authority": "conversation_json",
                        "conversation_id": request.conversation_id,
                        "message_id": message_id,
                        "exact_turn": True,
                    },
                )
            )
        recent_ids = {str(item.get("message_id")) for item in recent}
        for segment in hierarchy.get("segments", []):
            message_ids = [str(value) for value in segment.get("message_ids", [])]
            if any(value in recent_ids for value in message_ids):
                continue
            summary = str(segment.get("summary") or "")
            if summary:
                candidates.append(
                    _candidate(
                        candidate_id=f"conversation_summary:{segment['segment_id']}",
                        source_type="conversation_summary",
                        source_id=str(segment["segment_id"]),
                        content=summary,
                        owner_user_id=str(owner) if owner else request.owner_user_id,
                        form="episodic",
                        scope="conversation",
                        project_id=metadata.get("project_id"),
                        conversation_id=request.conversation_id,
                        observed_at=segment.get("ends_at"),
                        confidence=0.85,
                        importance=0.72,
                        provenance={
                            "authority": "derived_conversation_summary",
                            "message_ids": message_ids,
                            "summary_schema_version": hierarchy.get("schema_version"),
                            "generator": hierarchy.get("generator"),
                            "derived": True,
                            "summary_digest": segment.get("summary_digest"),
                            "generated_at_utc": segment.get("generated_at_utc"),
                        },
                    )
                )
        overview = str(hierarchy.get("overview") or "")
        if overview and len(hierarchy.get("segments", [])) > 1:
            candidates.append(
                _candidate(
                    candidate_id=f"conversation_summary:{request.conversation_id}:overview",
                    source_type="conversation_summary",
                    source_id=f"{request.conversation_id}:overview",
                    content=overview,
                    owner_user_id=str(owner) if owner else request.owner_user_id,
                    form="episodic",
                    scope="conversation",
                    project_id=metadata.get("project_id"),
                    conversation_id=request.conversation_id,
                    observed_at=hierarchy.get("generated_at_utc"),
                    confidence=0.78,
                    importance=0.66,
                    provenance={
                        "authority": "derived_conversation_overview",
                        "message_ids": [
                            value
                            for segment in hierarchy.get("segments", [])
                            for value in segment.get("message_ids", [])
                        ],
                        "summary_schema_version": hierarchy.get("schema_version"),
                        "generator": hierarchy.get("generator"),
                        "summary_digest": hierarchy.get("overview_digest"),
                        "generated_at_utc": hierarchy.get("generated_at_utc"),
                        "derived": True,
                    },
                )
            )
        return candidates


class ProjectCognitionSource(CognitionSource):
    source_type = "project"

    def read(self, request: CognitionReadRequest) -> list[CognitionCandidate]:
        if not request.project_id:
            return []
        from app.api.project_service import get_project_detail
        from app.api.project_capability_service import get_workbench

        try:
            detail = get_project_detail(request.project_id)
        except Exception:
            return []
        metadata = dict(detail.get("metadata") or {})
        continuity = dict(detail.get("continuity_summary") or {})
        linked_conversation_summaries = [
            {
                "conversation_id": item.get("conversation_id"),
                "title": item.get("title"),
                "last_message_preview": item.get("last_message_preview"),
                "updated_at_utc": item.get("updated_at_utc"),
            }
            for item in list(detail.get("related_conversations") or [])[:20]
            if isinstance(item, dict)
        ]
        linked_artifact_summaries = [
            {
                "artifact_id": item.get("artifact_id"),
                "kind": item.get("kind"),
                "title": item.get("title"),
                "summary": item.get("summary"),
            }
            for item in list(continuity.get("linked_artifacts") or [])[:20]
            if isinstance(item, dict)
        ]
        try:
            workbench = get_workbench(request.project_id)
        except Exception:
            workbench = {}
        linked_memories: list[str] = []
        try:
            from app.memory.canonical_models import MemoryPrivacy, MemoryQuery

            projection = FtsMemoryProjection()
            principal = projection.fabric.current_principal()
            memory_rows, _ = projection.fabric.list(
                principal,
                MemoryQuery(
                    privacy=MemoryPrivacy.NORMAL,
                    project_id=request.project_id,
                    limit=40,
                ),
            )
            linked_memories = [
                f"{item.memory_id}: {item.title}" for item in memory_rows
            ]
        except Exception:
            linked_memories = []
        durable_research: list[str] = []
        if request.owner_user_id:
            try:
                evidence_repository = EvidenceRepository()
                sessions = evidence_repository.list_sessions(
                    request.owner_user_id, project_id=request.project_id, limit=20
                )
                evidence = evidence_repository.list_evidence(
                    request.owner_user_id, project_id=request.project_id, limit=40
                )
                durable_research = [
                    f"sessions={','.join(str(item.get('session_id')) for item in sessions if item.get('session_id')) or 'none'}",
                    "evidence=" + (
                        "; ".join(
                            f"{item.get('evidence_id')}[{item.get('verification_status')}:{item.get('record_status')}]"
                            for item in evidence
                            if item.get("evidence_id")
                        )
                        or "none"
                    ),
                ]
            except Exception:
                durable_research = []
        sections = [
            ("Name", metadata.get("name")),
            ("Current state", continuity.get("current_state")),
            ("Latest work", continuity.get("latest_chunk")),
            ("Project notes", continuity.get("project_notes")),
            ("Milestones", continuity.get("recent_milestones")),
            ("Blockers", continuity.get("open_blockers")),
            ("Next actions", continuity.get("next_suggested_actions")),
            ("Decisions", continuity.get("decisions")),
            ("Unresolved questions", continuity.get("unresolved_questions")),
            ("Corrections and supersessions", continuity.get("corrections")),
            ("Linked conversation summaries", linked_conversation_summaries),
            ("Linked artifacts", linked_artifact_summaries),
            ("Memory links", linked_memories),
            ("Durable research links", durable_research),
            ("Sources", workbench.get("sources")),
            ("Research", workbench.get("research_investigations")),
            ("Goals", workbench.get("goals")),
        ]
        lines = [f"{label}: {value}" for label, value in sections if value not in (None, "", [])]
        if not lines:
            return []
        owner = metadata.get("owner_user_id")
        return [
            _candidate(
                candidate_id=f"project:{request.project_id}:active_packet",
                source_type=self.source_type,
                source_id=request.project_id,
                content="\n".join(lines),
                owner_user_id=str(owner) if owner else request.owner_user_id,
                form="prospective",
                scope="project",
                project_id=request.project_id,
                observed_at=metadata.get("updated_at_utc"),
                confidence=1.0,
                importance=0.95,
                user_confirmed=True,
                provenance={
                    "authority": "project_json",
                    "project_id": request.project_id,
                    "linked_conversation_ids": continuity.get("linked_conversation_ids", []),
                    "linked_artifact_ids": continuity.get("linked_artifact_ids", []),
                    "linked_evidence_packet_ids": continuity.get("linked_evidence_packet_ids", []),
                    "packet_fields": [label for label, value in sections if value not in (None, "", [])],
                    "unresolved_commitment": bool(
                        continuity.get("open_blockers")
                        or continuity.get("next_suggested_actions")
                        or continuity.get("unresolved_questions")
                    ),
                    "stakes": 0.8,
                },
            )
        ]


class MemoryCognitionSource(CognitionSource):
    source_type = "memory"

    def __init__(self, *, paths: ElysiaPaths | None = None) -> None:
        self.paths = paths or resolve_elysia_paths()

    def read(self, request: CognitionReadRequest) -> list[CognitionCandidate]:
        if not request.owner_user_id:
            return []
        try:
            projection = FtsMemoryProjection(paths=self.paths)
            principal = projection.fabric.current_principal()
            hybrid = HybridMemoryRetriever(lexical=projection).search_normal(
                principal,
                request.query,
                space_ids=sorted(request.authorized_space_ids),
                limit=request.candidate_limit,
            )
            rows = list(hybrid.rows)
            rows += projection.search_private_ephemeral(
                principal,
                request.query,
                limit=max(5, request.candidate_limit // 2),
            )
            # Sealed records never enter a durable index.  They may be read
            # into this one process-local workspace only when the user chose
            # the explicit per-request control and the current session's
            # password-unlocked vault is still within its bounded TTL.
            if request.explicit_sealed_memory:
                from app.memory.canonical_models import MemoryPrivacy, MemoryQuery

                if projection.fabric.encryption.sealed_status(principal).get("unlocked"):
                    sealed_rows, _ = projection.fabric.list(
                        principal,
                        MemoryQuery(
                            privacy=MemoryPrivacy.SEALED,
                            include_archived=False,
                            limit=min(200, request.candidate_limit),
                        ),
                    )
                    query_terms = {
                        term.casefold()
                        for term in request.query.split()
                        if len(term.strip()) > 1
                    }
                    for item in sealed_rows:
                        searchable = "\n".join(
                            value
                            for value in (item.title, item.body or "", item.why_stored or "")
                            if value
                        )
                        content_terms = {term.casefold() for term in searchable.split()}
                        overlap = len(query_terms & content_terms)
                        if query_terms and overlap == 0:
                            continue
                        rows.append(
                            {
                                "candidate_id": item.memory_id,
                                "source_id": item.memory_id,
                                "owner_user_id": item.owner_user_id,
                                "space_id": item.space_id,
                                "privacy": item.privacy.value,
                                "form": item.form.value,
                                "scope": item.scope.value,
                                "title": item.title,
                                "body": item.body,
                                "why_stored": item.why_stored,
                                "project_id": next(
                                    (
                                        relation.get("target_id")
                                        for relation in item.relations
                                        if relation.get("target_type") == "project"
                                    ),
                                    None,
                                ),
                                "conversation_id": next(
                                    (
                                        relation.get("target_id")
                                        for relation in item.relations
                                        if relation.get("target_type") == "conversation"
                                    ),
                                    None,
                                ),
                                "observed_at": item.observed_at,
                                "valid_from": item.valid_from,
                                "valid_until": item.valid_until,
                                "confidence": item.confidence,
                                "importance": item.importance,
                                "pinned": item.pinned,
                                "user_confirmed": item.user_confirmed,
                                "status": item.status.value,
                                "raw_rank": -float(overlap),
                                "ephemeral_sealed": True,
                            }
                        )
        except Exception:
            return []
        # Canonical Memory remains authoritative for mutable salience fields
        # such as pinning. The derived lexical/semantic rows may rank broadly,
        # but workspace admission re-reads this content-free metadata before
        # final scoring.
        authorized_rows: list[dict[str, Any]] = []
        for row in rows:
            try:
                canonical_record = projection.fabric.get(
                    principal, str(row["candidate_id"])
                )
            except Exception:
                continue
            if (
                bool(canonical_record.automatic_recall_suppressed)
                or canonical_record.form.value == "audit"
                or canonical_record.activation_tier.value in {"cold", "archived"}
                or (
                    canonical_record.form.value == "prospective"
                    and str(canonical_record.form_data.get("state") or "pending")
                    != "pending"
                )
            ):
                continue
            row["pinned"] = bool(canonical_record.pinned)
            authorized_rows.append(row)
        rows = authorized_rows
        candidates = []
        for rank_position, row in enumerate(rows, start=1):
            raw_rank = float(row.get("raw_rank") or 0.0)
            lexical = max(0.02, 1.0 / float(rank_position))
            content = "\n".join(
                value for value in (str(row.get("title") or ""), str(row.get("body") or ""), str(row.get("why_stored") or "")) if value
            )
            candidates.append(
                _candidate(
                    candidate_id=f"memory:{row['candidate_id']}",
                    source_type=self.source_type,
                    source_id=str(row["source_id"]),
                    content=content,
                    owner_user_id=str(row.get("owner_user_id") or request.owner_user_id),
                    space_id=str(row.get("space_id")) if row.get("space_id") else None,
                    privacy=str(row["privacy"]),
                    form=str(row["form"]),
                    scope=str(row["scope"]),
                    project_id=row.get("project_id"),
                    conversation_id=row.get("conversation_id"),
                    observed_at=row.get("observed_at"),
                    valid_from=row.get("valid_from"),
                    valid_until=row.get("valid_until"),
                    confidence=row.get("confidence"),
                    importance=float(row.get("importance") or 0.5),
                    user_confirmed=bool(row.get("user_confirmed")),
                    status=str(row.get("status") or "active"),
                    lexical_score=lexical,
                    semantic_score=float(row.get("semantic_score") or 0.0),
                    provenance={
                        "authority": "canonical_memory_fabric",
                        "projection": (
                            "ephemeral_sealed_current_request"
                            if row.get("ephemeral_sealed")
                            else "ephemeral_private"
                            if row.get("ephemeral_private")
                            else str(row.get("fusion_version") or PROJECTION_VERSION)
                        ),
                        "memory_id": row["candidate_id"],
                        "space_id": row.get("space_id"),
                        "raw_rank": raw_rank,
                        "retrieval_method": row.get("retrieval_method"),
                        "lexical_rank": row.get("lexical_rank"),
                        "semantic_rank": row.get("semantic_rank"),
                        "fusion_score": row.get("fusion_score"),
                        "fusion_version": row.get("fusion_version"),
                        "pinned": bool(row.get("pinned")),
                        "user_emphasis": bool(row.get("user_confirmed")),
                        "unresolved_commitment": str(row.get("form")) == "prospective",
                        "stakes": float(row.get("importance") or 0.0),
                    },
                )
            )
        return candidates


class EvidenceCognitionSource(CognitionSource):
    source_type = "evidence"

    def __init__(self, *, paths: ElysiaPaths | None = None) -> None:
        self.repository = EvidenceRepository(paths=paths or resolve_elysia_paths())

    def read(self, request: CognitionReadRequest) -> list[CognitionCandidate]:
        if not request.owner_user_id:
            return []
        try:
            rows = self.repository.list_evidence(
                request.owner_user_id,
                project_id=request.project_id,
                conversation_id=request.conversation_id,
                limit=request.candidate_limit,
            )
        except Exception:
            return []
        return [
            _candidate(
                candidate_id=f"evidence:{row['evidence_id']}",
                source_type=self.source_type,
                source_id=str(row["evidence_id"]),
                content=f"Claim: {row.get('claim')}\nSource: {row.get('title')}\nExcerpt: {row.get('excerpt')}",
                owner_user_id=request.owner_user_id,
                form=(
                    "corrective"
                    if row.get("retrieval_method") == "user_correction"
                    else "semantic"
                ),
                scope="research",
                source_authority="verified_evidence" if row.get("verification_status") == "verified" else "evidence_candidate",
                project_id=row.get("project_id"),
                conversation_id=row.get("conversation_id"),
                observed_at=row.get("retrieved_at"),
                confidence=0.75 if row.get("verification_status") == "verified" else 0.45,
                importance=0.75,
                status=(
                    "rejected"
                    if row.get("verification_status") == "rejected"
                    else str(row.get("record_status") or "active")
                ),
                provenance={
                    "authority": "research_evidence_sqlite",
                    "source_url_hash": row.get("source_url_hash"),
                    "retrieval_method": row.get("retrieval_method"),
                    "verification_status": row.get("verification_status"),
                    "citation": row.get("citation"),
                    "quarantine_state": row.get("quarantine_state"),
                    "contradiction_notes": list((row.get("contradiction") or {}).get("notes") or []),
                    "supersedes_evidence_id": row.get("supersedes_evidence_id"),
                    "superseded_by_evidence_id": row.get("superseded_by_evidence_id"),
                    "recorded_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                },
                untrusted=str(row.get("quarantine_state")) == "untrusted_web_evidence",
            )
            for row in rows
        ]


class ArtifactCognitionSource(CognitionSource):
    source_type = "artifact"

    def read(self, request: CognitionReadRequest) -> list[CognitionCandidate]:
        try:
            from app.api.artifact_service import list_artifacts
            result = list_artifacts(
                project_id=request.project_id,
                conversation_id=request.conversation_id,
                limit=request.candidate_limit,
            )
        except Exception:
            return []
        candidates = []
        for item in result.artifacts:
            payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else item.dict()
            content = f"{payload.get('title') or 'Artifact'}: {payload.get('summary') or ''}"
            candidates.append(
                _candidate(
                    candidate_id=f"artifact:{payload.get('artifact_id')}",
                    source_type=self.source_type,
                    source_id=str(payload.get("artifact_id")),
                    content=content,
                    owner_user_id=request.owner_user_id,
                    form="episodic",
                    scope="project" if payload.get("project_id") else "conversation",
                    project_id=payload.get("project_id"),
                    conversation_id=payload.get("conversation_id"),
                    observed_at=payload.get("created_at_utc"),
                    confidence=1.0,
                    importance=0.55,
                    provenance={"authority": "artifact_store", "artifact_kind": payload.get("kind")},
                )
            )
        return candidates


class IdentityProjectionSource(CognitionSource):
    source_type = "identity_projection"

    def read(self, request: CognitionReadRequest) -> list[CognitionCandidate]:
        allowed = {
            key: request.profile_context[key]
            for key in ("name_or_username", "interests", "bio")
            if request.profile_context.get(key)
        }
        if not allowed:
            return []
        content = "\n".join(f"{key.replace('_', ' ').title()}: {value}" for key, value in allowed.items())
        return [
            _candidate(
                candidate_id=f"identity:{request.owner_user_id}:visible",
                source_type=self.source_type,
                source_id=str(request.owner_user_id or "visible-profile"),
                content=content,
                owner_user_id=request.owner_user_id,
                privacy="private",
                form="relational",
                scope="user",
                source_authority="explicit_identity_projection",
                confidence=1.0,
                importance=0.85,
                user_confirmed=True,
                provenance={"authority": "identity_sqlite_visible_projection", "fields": sorted(allowed)},
            )
        ]


class OperationalTraceSource(CognitionSource):
    source_type = "operational_trace"

    def read(self, request: CognitionReadRequest) -> list[CognitionCandidate]:
        if request.owner_user_id is None:
            return []
        try:
            from app.api.request_trace_service import list_request_trace_summaries
            rows = list_request_trace_summaries(
                project_id=request.project_id,
                owner_user_id=request.owner_user_id,
                limit=8,
            )
        except Exception:
            return []
        candidates = []
        for row in rows:
            trace_id = str(row.get("request_id") or "")
            if not trace_id or trace_id == request.request_id:
                continue
            content = f"Request status: {row.get('request_status')}; phase: {row.get('current_phase')}; evidence packets: {row.get('evidence_packet_count', 0)}; route: {row.get('route_used') or 'none'}"
            candidates.append(
                _candidate(
                    candidate_id=f"operational:{trace_id}",
                    source_type=self.source_type,
                    source_id=trace_id,
                    content=content,
                    owner_user_id=request.owner_user_id,
                    form="audit",
                    scope="operational",
                    project_id=row.get("related_project_id"),
                    conversation_id=row.get("related_conversation_id"),
                    observed_at=row.get("updated_at_utc"),
                    confidence=1.0,
                    importance=0.3,
                    provenance={"authority": "request_trace_registry", "sanitized": True},
                )
            )
        return candidates


DEFAULT_SOURCES: tuple[type[CognitionSource], ...] = (
    ConversationCognitionSource,
    ProjectCognitionSource,
    MemoryCognitionSource,
    EvidenceCognitionSource,
    ArtifactCognitionSource,
    IdentityProjectionSource,
    OperationalTraceSource,
)


__all__ = (
    "ArtifactCognitionSource",
    "CognitionReadRequest",
    "CognitionSource",
    "ConversationCognitionSource",
    "DEFAULT_SOURCES",
    "EvidenceCognitionSource",
    "IdentityProjectionSource",
    "MemoryCognitionSource",
    "OperationalTraceSource",
    "ProjectCognitionSource",
)
