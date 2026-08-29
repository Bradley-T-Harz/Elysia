from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.memory.schemas.memory_filters import MemoryItemsQuery
from app.memory.schemas.memory_item import MemoryItem
from app.memory.schemas.memory_mutation import (
    MemoryMutationContext,
    MemoryMutationPatch,
    MemoryMutationRequest,
    MemoryMutationTarget,
    MemoryMutationType,
)
from app.memory.schemas.memory_policy import MemoryPolicySet
from app.memory.canonical_models import MemoryCreateRequest, MemoryPrincipal, MemoryQuery
from app.memory.canonical_repository import MemoryRepository
from app.memory.fabric_service import MemoryFabricService
from app.memory.services.memory_boundary_service import (
    BoundaryRoomContext,
    MemoryBoundaryDecision,
    MemoryBoundaryService,
)
from app.memory.services.memory_classification_service import (
    MemoryCandidate,
    MemoryClassificationResult,
    MemoryClassificationService,
    MemoryStoreDecision,
)
from app.memory.services.memory_consolidation_service import (
    ConsolidationExecutionResult,
    ConsolidationPlan,
    MemoryConsolidationService,
)
from app.memory.services.memory_item_service import MemoryItemService
from app.memory.services.memory_mutation_service import MemoryMutationService
from app.memory.services.memory_retrieval_service import (
    MemoryQueryResult,
    MemoryRetrievalService,
)
from app.memory.services.memory_salience_service import (
    MemorySalienceContext,
    MemorySalienceResult,
    MemorySalienceService,
)
from app.memory.services.memory_summary_service import MemorySummaryService


@dataclass(frozen=True)
class MemoryCandidateAnalysis:
    classification: MemoryClassificationResult
    salience: MemorySalienceResult


class MemoryService:
    """Front-door orchestration facade for the memory subsystem.

    This class wires the memory services together and exposes a smaller,
    stable API for the rest of Elysia. It should coordinate the organs,
    not replace them.
    """

    def __init__(
        self,
        *,
        policy_set: MemoryPolicySet,
        store_root: Optional[Path] = None,
        recent_window_days: int = 7,
        autonomous_updates_enabled: bool = False,
        stale_working_days: int = 7,
        archive_salience_threshold: float = 0.30,
        promote_salience_threshold: float = 0.72,
        recurrence_threshold: int = 2,
        allow_merge_apply: bool = False,
        canonical_repository: MemoryRepository | None = None,
    ) -> None:
        self._policy_set = policy_set
        self._canonical_repository = canonical_repository
        self._canonical_fabric: MemoryFabricService | None = None

        self._item_service = MemoryItemService(store_root=store_root)
        self._classification_service = MemoryClassificationService()
        self._salience_service = MemorySalienceService()
        self._summary_service = MemorySummaryService(
            item_service=self._item_service,
            recent_window_days=recent_window_days,
            autonomous_updates_enabled=autonomous_updates_enabled,
        )
        self._retrieval_service = MemoryRetrievalService(
            item_service=self._item_service,
        )
        self._boundary_service = MemoryBoundaryService(policy_set=policy_set)
        self._mutation_service = MemoryMutationService(
            item_service=self._item_service,
            boundary_service=self._boundary_service,
        )
        self._consolidation_service = MemoryConsolidationService(
            item_service=self._item_service,
            retrieval_service=self._retrieval_service,
            salience_service=self._salience_service,
            mutation_service=self._mutation_service,
            classification_service=self._classification_service,
            stale_working_days=stale_working_days,
            archive_salience_threshold=archive_salience_threshold,
            promote_salience_threshold=promote_salience_threshold,
            recurrence_threshold=recurrence_threshold,
            allow_merge_apply=allow_merge_apply,
        )

    @property
    def policy_set(self) -> MemoryPolicySet:
        return self._policy_set

    @property
    def canonical_fabric(self) -> MemoryFabricService:
        """Return the one active XDG-SQLite writer for all new memory."""
        if self._canonical_fabric is None:
            self._canonical_fabric = MemoryFabricService(
                repository=self._canonical_repository
            )
        return self._canonical_fabric

    def create_memory(
        self, principal: MemoryPrincipal, request: MemoryCreateRequest
    ):
        return self.canonical_fabric.create(principal, request)

    def query_memory(
        self, principal: MemoryPrincipal, query: MemoryQuery | None = None
    ):
        return self.canonical_fabric.list(principal, query or MemoryQuery())

    def get_memory(self, principal: MemoryPrincipal, memory_id: str):
        return self.canonical_fabric.get(principal, memory_id)

    @property
    def item_service(self) -> MemoryItemService:
        return self._item_service

    @property
    def summary_service(self) -> MemorySummaryService:
        return self._summary_service

    @property
    def retrieval_service(self) -> MemoryRetrievalService:
        return self._retrieval_service

    @property
    def boundary_service(self) -> MemoryBoundaryService:
        return self._boundary_service

    @property
    def mutation_service(self) -> MemoryMutationService:
        return self._mutation_service

    @property
    def classification_service(self) -> MemoryClassificationService:
        return self._classification_service

    @property
    def salience_service(self) -> MemorySalienceService:
        return self._salience_service

    @property
    def consolidation_service(self) -> MemoryConsolidationService:
        return self._consolidation_service

    def get_summary(
        self,
        *,
        project_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ):
        return self._summary_service.get_summary(
            project_id=project_id,
            conversation_id=conversation_id,
        )

    def query_items(self, query: Optional[MemoryItemsQuery] = None) -> MemoryQueryResult:
        return self._retrieval_service.query_items(query)

    def get_item(self, memory_id: str) -> MemoryItem:
        return self._item_service.get_item(memory_id)

    def list_items(
        self,
        *,
        memory_class=None,
        project_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        include_statuses=None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[MemoryItem]:
        return self._item_service.list_items(
            memory_class=memory_class,
            project_id=project_id,
            conversation_id=conversation_id,
            include_statuses=include_statuses,
            limit=limit,
            offset=offset,
        )

    def classify_candidate(
        self,
        candidate: MemoryCandidate,
    ) -> MemoryClassificationResult:
        return self._classification_service.classify_candidate(candidate)

    def score_item(
        self,
        item: MemoryItem,
        *,
        context: Optional[MemorySalienceContext] = None,
    ) -> MemorySalienceResult:
        return self._salience_service.score_item(item, context=context)

    def score_candidate(
        self,
        candidate: MemoryCandidate,
        classification: MemoryClassificationResult,
        *,
        context: Optional[MemorySalienceContext] = None,
    ) -> MemorySalienceResult:
        return self._salience_service.score_candidate(
            candidate,
            classification,
            context=context,
        )

    def classify_and_score_candidate(
        self,
        candidate: MemoryCandidate,
        *,
        context: Optional[MemorySalienceContext] = None,
    ) -> MemoryCandidateAnalysis:
        classification = self.classify_candidate(candidate)
        salience = self.score_candidate(
            candidate,
            classification,
            context=context,
        )
        return MemoryCandidateAnalysis(
            classification=classification,
            salience=salience,
        )

    def build_candidate_create_mutation(
        self,
        candidate: MemoryCandidate,
        *,
        context: Optional[MemorySalienceContext] = None,
        dry_run: bool = True,
    ) -> tuple[MemoryMutationRequest, MemoryCandidateAnalysis]:
        analysis = self.classify_and_score_candidate(candidate, context=context)
        classification = analysis.classification

        if classification.store_decision == MemoryStoreDecision.do_not_store:
            raise ValueError("Candidate classification recommends do_not_store.")

        trigger_event = "memory_service_candidate_ingest"
        patch = MemoryMutationPatch(
            title=(candidate.title or "Untitled memory").strip(),
            body=candidate.body.strip(),
            why_stored=classification.why_stored,
            memory_class=classification.memory_class,
            sensitivity=classification.sensitivity,
            mutability=classification.mutability,
            status=classification.status,
            importance=classification.importance,
            confidence=candidate.confidence,
        )

        request = MemoryMutationRequest(
            mutation_type=MemoryMutationType.create,
            actor=candidate.actor,
            mode=(
                self._select_candidate_mutation_mode(candidate, classification)
            ),
            target=MemoryMutationTarget(
                memory_class=classification.memory_class,
                project_id=candidate.project_id,
                conversation_id=candidate.conversation_id,
            ),
            patch=patch,
            context=MemoryMutationContext(
                reason=classification.why_stored,
                source_kind=candidate.source_kind,
                source_ref=candidate.source_ref,
                trigger_event=trigger_event,
                notes=classification.reasoning_summary,
            ),
            dry_run=dry_run,
        )
        return request, analysis

    def ingest_candidate_preview(
        self,
        candidate: MemoryCandidate,
        *,
        context: Optional[MemorySalienceContext] = None,
    ):
        request, analysis = self.build_candidate_create_mutation(
            candidate,
            context=context,
            dry_run=True,
        )
        record = self.preview_mutation(request)
        return {
            "analysis": analysis,
            "mutation_request": request,
            "mutation_record": record,
        }

    def apply_mutation(self, request: MemoryMutationRequest):
        return self._mutation_service.apply_mutation(request)

    def preview_mutation(self, request: MemoryMutationRequest):
        return self._mutation_service.preview_mutation(request)

    def evaluate_retrieval_boundary(
        self,
        item: MemoryItem,
        *,
        actor,
        room_context: Optional[BoundaryRoomContext] = None,
    ) -> MemoryBoundaryDecision:
        return self._boundary_service.evaluate_retrieval(
            item,
            actor=actor,
            room_context=room_context,
        )

    def evaluate_summary_exposure(
        self,
        item: MemoryItem,
        *,
        actor,
        room_context: Optional[BoundaryRoomContext] = None,
    ) -> MemoryBoundaryDecision:
        return self._boundary_service.evaluate_summary_exposure(
            item,
            actor=actor,
            room_context=room_context,
        )

    def sanitize_item_for_exposure(
        self,
        item: MemoryItem,
        decision: MemoryBoundaryDecision,
    ) -> Optional[MemoryItem]:
        return self._boundary_service.sanitize_item_for_exposure(item, decision)

    def evaluate_mutation_boundary(
        self,
        request: MemoryMutationRequest,
        *,
        existing_item: Optional[MemoryItem] = None,
    ) -> MemoryBoundaryDecision:
        return self._boundary_service.evaluate_mutation(
            request,
            existing_item=existing_item,
        )

    def evaluate_promotion_boundary(
        self,
        *,
        from_class,
        to_class,
        actor,
        source_kind,
        confidence: Optional[float] = None,
        repetition_count: int = 1,
        mode,
    ) -> MemoryBoundaryDecision:
        return self._boundary_service.evaluate_promotion(
            from_class=from_class,
            to_class=to_class,
            actor=actor,
            source_kind=source_kind,
            confidence=confidence,
            repetition_count=repetition_count,
            mode=mode,
        )

    def build_consolidation_plan(
        self,
        *,
        project_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> ConsolidationPlan:
        return self._consolidation_service.build_consolidation_plan(
            project_id=project_id,
            conversation_id=conversation_id,
        )

    def run_consolidation(
        self,
        *,
        plan: Optional[ConsolidationPlan] = None,
        project_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> ConsolidationExecutionResult:
        return self._consolidation_service.run_consolidation(
            plan=plan,
            project_id=project_id,
            conversation_id=conversation_id,
            dry_run=dry_run,
        )

    def _select_candidate_mutation_mode(
        self,
        candidate: MemoryCandidate,
        classification: MemoryClassificationResult,
    ):
        if candidate.actor.value == "assistant":
            if classification.store_decision in {
                MemoryStoreDecision.review_required,
                MemoryStoreDecision.store_provisional,
            }:
                return "autonomous"
            return "autonomous"
        return "assisted"
