from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from app.memory.schemas.memory_item import (
    MemoryClass,
    MemoryItem,
    MemorySensitivity,
    MemoryStatus,
)
from app.memory.schemas.memory_mutation import (
    MemoryMutationActor,
    MemoryMutationContext,
    MemoryMutationMode,
    MemoryMutationPatch,
    MemoryMutationRequest,
    MemoryMutationTarget,
    MemoryMutationType,
)
from app.memory.services.memory_classification_service import MemoryClassificationService
from app.memory.services.memory_item_service import MemoryItemService
from app.memory.services.memory_mutation_service import MemoryMutationService
from app.memory.services.memory_retrieval_service import MemoryRetrievalService
from app.memory.services.memory_salience_service import (
    MemorySalienceContext,
    MemorySalienceResult,
    MemorySalienceService,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConsolidationAction(str, Enum):
    archive = "archive"
    promote = "promote"
    merge = "merge"
    summarize = "summarize"
    defer = "defer"
    leave_as_is = "leave_as_is"


@dataclass(frozen=True)
class ConsolidationCandidate:
    action: ConsolidationAction
    target_memory_ids: list[str]
    from_class: Optional[MemoryClass]
    to_class: Optional[MemoryClass]
    salience_score: float
    recurrence_count: int
    reason: str
    auto_applicable: bool
    review_likely: bool
    proposed_title: Optional[str] = None
    proposed_body: Optional[str] = None


@dataclass(frozen=True)
class ConsolidationPlan:
    generated_at_utc: datetime
    candidates: list[ConsolidationCandidate] = field(default_factory=list)


@dataclass(frozen=True)
class ConsolidationExecutionResult:
    plan: ConsolidationPlan
    mutation_records: list = field(default_factory=list)
    skipped_candidates: list[ConsolidationCandidate] = field(default_factory=list)


class MemoryConsolidationService:
    """Plan-first, conservative long-horizon organizer for memory.

    This service identifies candidates for archive/promote/merge-style
    consolidation and optionally applies the safe subset through the mutation
    service. It does not write directly to storage.
    """

    def __init__(
        self,
        *,
        item_service: Optional[MemoryItemService] = None,
        retrieval_service: Optional[MemoryRetrievalService] = None,
        salience_service: Optional[MemorySalienceService] = None,
        mutation_service: Optional[MemoryMutationService] = None,
        classification_service: Optional[MemoryClassificationService] = None,
        stale_working_days: int = 7,
        archive_salience_threshold: float = 0.30,
        promote_salience_threshold: float = 0.72,
        recurrence_threshold: int = 2,
        allow_merge_apply: bool = False,
        mutation_actor: MemoryMutationActor = MemoryMutationActor.service,
        mutation_mode: MemoryMutationMode = MemoryMutationMode.system_maintenance,
    ) -> None:
        base_item_service = item_service or MemoryItemService()
        self._item_service = base_item_service
        self._retrieval_service = retrieval_service or MemoryRetrievalService(base_item_service)
        self._salience_service = salience_service or MemorySalienceService()
        self._mutation_service = mutation_service
        self._classification_service = classification_service or MemoryClassificationService()

        self._stale_working_days = stale_working_days
        self._archive_salience_threshold = archive_salience_threshold
        self._promote_salience_threshold = promote_salience_threshold
        self._recurrence_threshold = recurrence_threshold
        self._allow_merge_apply = allow_merge_apply
        self._mutation_actor = mutation_actor
        self._mutation_mode = mutation_mode

    @property
    def item_service(self) -> MemoryItemService:
        return self._item_service

    @property
    def retrieval_service(self) -> MemoryRetrievalService:
        return self._retrieval_service

    @property
    def salience_service(self) -> MemorySalienceService:
        return self._salience_service

    @property
    def mutation_service(self) -> Optional[MemoryMutationService]:
        return self._mutation_service

    @property
    def classification_service(self) -> MemoryClassificationService:
        return self._classification_service

    def build_consolidation_plan(
        self,
        *,
        project_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> ConsolidationPlan:
        items = self._item_service.list_items(
            project_id=project_id,
            conversation_id=conversation_id,
        )

        if not items:
            return ConsolidationPlan(generated_at_utc=utc_now(), candidates=[])

        recurrence_map = self._build_recurrence_map(items)
        salience_map = self._build_salience_map(
            items=items,
            recurrence_map=recurrence_map,
            current_project_id=project_id,
            current_conversation_id=conversation_id,
        )

        candidates: list[ConsolidationCandidate] = []
        candidates.extend(self._find_stale_working_archive_candidates(items, recurrence_map, salience_map))
        candidates.extend(self._find_working_promotion_candidates(items, recurrence_map, salience_map))
        candidates.extend(self._find_conversation_project_promotion_candidates(items, recurrence_map, salience_map))
        candidates.extend(self._find_merge_candidates(items, recurrence_map, salience_map))

        candidates = self._deduplicate_candidates(candidates)

        return ConsolidationPlan(
            generated_at_utc=utc_now(),
            candidates=candidates,
        )

    def run_consolidation(
        self,
        *,
        plan: Optional[ConsolidationPlan] = None,
        project_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> ConsolidationExecutionResult:
        if self._mutation_service is None:
            raise RuntimeError(
                "MemoryConsolidationService requires a MemoryMutationService to run consolidation."
            )

        plan = plan or self.build_consolidation_plan(
            project_id=project_id,
            conversation_id=conversation_id,
        )

        mutation_records = []
        skipped_candidates: list[ConsolidationCandidate] = []

        for candidate in plan.candidates:
            if not candidate.auto_applicable:
                skipped_candidates.append(candidate)
                continue

            record = self._apply_candidate(candidate, dry_run=dry_run)
            mutation_records.append(record)

        return ConsolidationExecutionResult(
            plan=plan,
            mutation_records=mutation_records,
            skipped_candidates=skipped_candidates,
        )

    def _find_stale_working_archive_candidates(
        self,
        items: list[MemoryItem],
        recurrence_map: dict[str, int],
        salience_map: dict[str, MemorySalienceResult],
    ) -> list[ConsolidationCandidate]:
        candidates: list[ConsolidationCandidate] = []
        now = utc_now()

        for item in items:
            if item.memory_class != MemoryClass.working:
                continue
            if item.status not in {MemoryStatus.active, MemoryStatus.provisional}:
                continue
            if item.flags.pinned:
                continue
            if item.sensitivity in {MemorySensitivity.private, MemorySensitivity.sealed}:
                continue

            age_days = (now - item.updated_at_utc).total_seconds() / 86400.0
            salience = salience_map[item.memory_id]
            recurrence = recurrence_map.get(self._signature(item), 1)

            if (
                age_days >= self._stale_working_days
                and salience.salience_score <= self._archive_salience_threshold
                and recurrence <= 1
            ):
                candidates.append(
                    ConsolidationCandidate(
                        action=ConsolidationAction.archive,
                        target_memory_ids=[item.memory_id],
                        from_class=item.memory_class,
                        to_class=None,
                        salience_score=salience.salience_score,
                        recurrence_count=recurrence,
                        reason=(
                            "Low-salience working memory appears stale and is a good archive candidate."
                        ),
                        auto_applicable=True,
                        review_likely=False,
                    )
                )

        return candidates

    def _find_working_promotion_candidates(
        self,
        items: list[MemoryItem],
        recurrence_map: dict[str, int],
        salience_map: dict[str, MemorySalienceResult],
    ) -> list[ConsolidationCandidate]:
        candidates: list[ConsolidationCandidate] = []

        for item in items:
            if item.memory_class != MemoryClass.working:
                continue
            if item.status in {MemoryStatus.archived, MemoryStatus.superseded, MemoryStatus.blocked}:
                continue
            if item.sensitivity in {MemorySensitivity.private, MemorySensitivity.sealed}:
                continue

            recurrence = recurrence_map.get(self._signature(item), 1)
            salience = salience_map[item.memory_id]

            target_class: Optional[MemoryClass] = None
            if (
                item.context_links.project_id
                and salience.salience_score >= self._promote_salience_threshold
                and recurrence >= self._recurrence_threshold
            ):
                target_class = MemoryClass.project
            elif (
                item.context_links.conversation_id
                and salience.salience_score >= self._promote_salience_threshold
                and recurrence >= self._recurrence_threshold
            ):
                target_class = MemoryClass.conversation

            if target_class is None:
                continue

            candidates.append(
                ConsolidationCandidate(
                    action=ConsolidationAction.promote,
                    target_memory_ids=[item.memory_id],
                    from_class=item.memory_class,
                    to_class=target_class,
                    salience_score=salience.salience_score,
                    recurrence_count=recurrence,
                    reason=(
                        f"Repeated working memory appears durable enough to promote into {target_class.value}."
                    ),
                    auto_applicable=True,
                    review_likely=item.status == MemoryStatus.provisional,
                )
            )

        return candidates

    def _find_conversation_project_promotion_candidates(
        self,
        items: list[MemoryItem],
        recurrence_map: dict[str, int],
        salience_map: dict[str, MemorySalienceResult],
    ) -> list[ConsolidationCandidate]:
        candidates: list[ConsolidationCandidate] = []

        for item in items:
            if item.memory_class != MemoryClass.conversation:
                continue
            if item.status in {MemoryStatus.archived, MemoryStatus.superseded, MemoryStatus.blocked}:
                continue
            if not item.context_links.project_id:
                continue
            if item.sensitivity in {MemorySensitivity.private, MemorySensitivity.sealed}:
                continue

            recurrence = recurrence_map.get(self._signature(item), 1)
            salience = salience_map[item.memory_id]

            if (
                salience.salience_score >= self._promote_salience_threshold
                and recurrence >= self._recurrence_threshold
            ):
                candidates.append(
                    ConsolidationCandidate(
                        action=ConsolidationAction.promote,
                        target_memory_ids=[item.memory_id],
                        from_class=item.memory_class,
                        to_class=MemoryClass.project,
                        salience_score=salience.salience_score,
                        recurrence_count=recurrence,
                        reason="Conversation memory has repeated project significance and is a good project promotion candidate.",
                        auto_applicable=True,
                        review_likely=item.status == MemoryStatus.provisional,
                    )
                )

        return candidates

    def _find_merge_candidates(
        self,
        items: list[MemoryItem],
        recurrence_map: dict[str, int],
        salience_map: dict[str, MemorySalienceResult],
    ) -> list[ConsolidationCandidate]:
        candidates: list[ConsolidationCandidate] = []
        groups = self._group_related_items(items)

        for grouped_items in groups.values():
            if len(grouped_items) < 2:
                continue

            first = grouped_items[0]
            if first.memory_class not in {MemoryClass.working, MemoryClass.conversation}:
                continue
            if any(item.sensitivity in {MemorySensitivity.private, MemorySensitivity.sealed} for item in grouped_items):
                continue
            if any(item.status in {MemoryStatus.archived, MemoryStatus.superseded, MemoryStatus.blocked} for item in grouped_items):
                continue

            average_salience = sum(
                salience_map[item.memory_id].salience_score for item in grouped_items
            ) / len(grouped_items)
            recurrence = recurrence_map.get(self._signature(first), len(grouped_items))

            if recurrence < self._recurrence_threshold:
                continue

            proposed_title = first.title or "Merged memory"
            proposed_body = self._build_merge_body(grouped_items)

            candidates.append(
                ConsolidationCandidate(
                    action=ConsolidationAction.merge,
                    target_memory_ids=[item.memory_id for item in grouped_items],
                    from_class=first.memory_class,
                    to_class=first.memory_class,
                    salience_score=round(average_salience, 3),
                    recurrence_count=recurrence,
                    reason="Multiple overlapping low-level memories appear suitable for cautious merge/compaction.",
                    auto_applicable=self._allow_merge_apply,
                    review_likely=not self._allow_merge_apply,
                    proposed_title=proposed_title,
                    proposed_body=proposed_body,
                )
            )

        return candidates

    def _apply_candidate(
        self,
        candidate: ConsolidationCandidate,
        *,
        dry_run: bool,
    ):
        assert self._mutation_service is not None

        if candidate.action == ConsolidationAction.archive:
            request = MemoryMutationRequest(
                mutation_type=MemoryMutationType.archive,
                actor=self._mutation_actor,
                mode=self._mutation_mode,
                target=MemoryMutationTarget(memory_id=candidate.target_memory_ids[0]),
                patch=MemoryMutationPatch(),
                context=MemoryMutationContext(
                    reason=candidate.reason,
                    source_kind=None,
                    source_ref=None,
                    trigger_event="memory_consolidation",
                    notes="Generated by consolidation service.",
                ),
                dry_run=dry_run,
            )
            return self._mutation_service.apply_mutation(request)

        if candidate.action == ConsolidationAction.promote:
            request = MemoryMutationRequest(
                mutation_type=MemoryMutationType.promote,
                actor=self._mutation_actor,
                mode=self._mutation_mode,
                target=MemoryMutationTarget(
                    memory_id=candidate.target_memory_ids[0],
                    memory_class=candidate.from_class,
                ),
                patch=MemoryMutationPatch(memory_class=candidate.to_class),
                context=MemoryMutationContext(
                    reason=candidate.reason,
                    source_kind=None,
                    source_ref=None,
                    trigger_event="memory_consolidation",
                    notes="Generated by consolidation service.",
                ),
                dry_run=dry_run,
            )
            return self._mutation_service.apply_mutation(request)

        if candidate.action == ConsolidationAction.merge:
            request = MemoryMutationRequest(
                mutation_type=MemoryMutationType.merge,
                actor=self._mutation_actor,
                mode=self._mutation_mode,
                target=MemoryMutationTarget(
                    memory_ids=candidate.target_memory_ids,
                    memory_class=candidate.from_class,
                ),
                patch=MemoryMutationPatch(
                    title=candidate.proposed_title,
                    body=candidate.proposed_body,
                    memory_class=candidate.to_class or candidate.from_class,
                ),
                context=MemoryMutationContext(
                    reason=candidate.reason,
                    source_kind=None,
                    source_ref=None,
                    trigger_event="memory_consolidation",
                    notes="Generated by consolidation service.",
                ),
                dry_run=dry_run,
            )
            return self._mutation_service.apply_mutation(request)

        raise ValueError(f"Unsupported consolidation action for apply: {candidate.action.value}")

    def _build_recurrence_map(self, items: list[MemoryItem]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            key = self._signature(item)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _build_salience_map(
        self,
        *,
        items: list[MemoryItem],
        recurrence_map: dict[str, int],
        current_project_id: Optional[str],
        current_conversation_id: Optional[str],
    ) -> dict[str, MemorySalienceResult]:
        result: dict[str, MemorySalienceResult] = {}

        for item in items:
            recurrence = recurrence_map.get(self._signature(item), 1)
            context = MemorySalienceContext(
                recurrence_count=recurrence,
                current_task_active=False,
                deadline_near=False,
                explicit_user_emphasis=item.flags.user_declared,
                current_project_id=current_project_id,
                current_conversation_id=current_conversation_id,
            )
            result[item.memory_id] = self._salience_service.score_item(
                item,
                context=context,
            )

        return result

    def _group_related_items(self, items: list[MemoryItem]) -> dict[tuple, list[MemoryItem]]:
        groups: dict[tuple, list[MemoryItem]] = {}

        for item in items:
            key = (
                item.memory_class,
                item.context_links.project_id,
                item.context_links.conversation_id,
                self._signature(item),
            )
            groups.setdefault(key, []).append(item)

        return groups

    def _signature(self, item: MemoryItem) -> str:
        title = (item.title or "").strip().casefold()
        if title:
            return title

        words = item.body.strip().casefold().split()
        return " ".join(words[:12])

    def _build_merge_body(self, items: list[MemoryItem]) -> str:
        sections = []
        for item in items:
            header = item.title or item.memory_id
            sections.append(f"[{header}]\n{item.body}")
        return "\n\n".join(sections)

    def _deduplicate_candidates(
        self,
        candidates: list[ConsolidationCandidate],
    ) -> list[ConsolidationCandidate]:
        seen: set[tuple] = set()
        deduped: list[ConsolidationCandidate] = []

        for candidate in candidates:
            key = (
                candidate.action,
                tuple(candidate.target_memory_ids),
                candidate.to_class,
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)

        return deduped
