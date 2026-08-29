from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from app.memory.schemas.memory_filters import (
    MemoryItemsQuery,
    MemorySortDirection,
    MemorySortField,
)
from app.memory.schemas.memory_item import (
    MemoryClass,
    MemoryItem,
    MemorySensitivity,
)
from app.memory.services.memory_item_service import MemoryItemService


@dataclass(frozen=True)
class MemoryQueryResult:
    items: list[MemoryItem]
    total_matches: int
    limit: int
    offset: int


class MemoryRetrievalService:
    """Safe recall/query engine for memory items.

    Responsibilities:
    - accept a typed MemoryItemsQuery
    - load candidate items from MemoryItemService
    - apply retrieval posture and structured filters
    - sort deterministically
    - paginate results
    - return a bounded result set

    Non-responsibilities:
    - mutation
    - classification
    - promotion/demotion
    - summary aggregation
    - policy execution beyond safe default posture
    """

    def __init__(
        self,
        item_service: Optional[MemoryItemService] = None,
    ) -> None:
        self._item_service = item_service or MemoryItemService()

    @property
    def item_service(self) -> MemoryItemService:
        return self._item_service

    def query_items(self, query: Optional[MemoryItemsQuery] = None) -> MemoryQueryResult:
        query = query or MemoryItemsQuery()

        items = self._item_service.list_items()

        items = self._apply_retrieval_posture(items, query)
        items = self._apply_class_filter(items, query)
        items = self._apply_sensitivity_filter(items, query)
        items = self._apply_status_filter(items, query)
        items = self._apply_mutability_filter(items, query)
        items = self._apply_source_filter(items, query)
        items = self._apply_context_filter(items, query)
        items = self._apply_date_filter(items, query)
        items = self._apply_scalar_filter(items, query)
        items = self._apply_flag_filter(items, query)
        items = self._apply_mutation_review_filter(items, query)
        items = self._apply_text_filter(items, query)

        items = self._sort_items(items, query)
        total_matches = len(items)
        items = self._paginate_items(items, query)

        return MemoryQueryResult(
            items=items,
            total_matches=total_matches,
            limit=query.pagination.limit,
            offset=query.pagination.offset,
        )

    def _apply_retrieval_posture(
        self,
        items: list[MemoryItem],
        query: MemoryItemsQuery,
    ) -> list[MemoryItem]:
        suppressed = set(query.retrieval.suppressed_classes)

        filtered: list[MemoryItem] = []
        for item in items:
            if item.memory_class in suppressed:
                continue

            if (
                not query.retrieval.allow_sealed_private
                and (
                    item.memory_class == MemoryClass.sealed_private
                    or item.sensitivity == MemorySensitivity.sealed
                )
            ):
                continue

            filtered.append(item)

        return filtered

    def _apply_class_filter(
        self,
        items: list[MemoryItem],
        query: MemoryItemsQuery,
    ) -> list[MemoryItem]:
        include = set(query.classes.include_classes)
        exclude = set(query.classes.exclude_classes)

        filtered = items
        if include:
            filtered = [item for item in filtered if item.memory_class in include]
        if exclude:
            filtered = [item for item in filtered if item.memory_class not in exclude]

        return filtered

    def _apply_sensitivity_filter(
        self,
        items: list[MemoryItem],
        query: MemoryItemsQuery,
    ) -> list[MemoryItem]:
        include = set(query.sensitivities.include_sensitivities)
        exclude = set(query.sensitivities.exclude_sensitivities)

        filtered = items
        if include:
            filtered = [item for item in filtered if item.sensitivity in include]
        if exclude:
            filtered = [item for item in filtered if item.sensitivity not in exclude]

        return filtered

    def _apply_status_filter(
        self,
        items: list[MemoryItem],
        query: MemoryItemsQuery,
    ) -> list[MemoryItem]:
        include = set(query.statuses.include_statuses)
        exclude = set(query.statuses.exclude_statuses)

        filtered = items
        if include:
            filtered = [item for item in filtered if item.status in include]
        if exclude:
            filtered = [item for item in filtered if item.status not in exclude]

        return filtered

    def _apply_mutability_filter(
        self,
        items: list[MemoryItem],
        query: MemoryItemsQuery,
    ) -> list[MemoryItem]:
        include = set(query.mutabilities.include_mutabilities)
        exclude = set(query.mutabilities.exclude_mutabilities)

        filtered = items
        if include:
            filtered = [item for item in filtered if item.mutability in include]
        if exclude:
            filtered = [item for item in filtered if item.mutability not in exclude]

        return filtered

    def _apply_source_filter(
        self,
        items: list[MemoryItem],
        query: MemoryItemsQuery,
    ) -> list[MemoryItem]:
        include = set(query.source.include_source_kinds)
        exclude = set(query.source.exclude_source_kinds)
        source_ref = query.source.source_ref
        source_label_query = query.source.source_label_query

        filtered = items
        if include:
            filtered = [item for item in filtered if item.source.source_kind in include]
        if exclude:
            filtered = [item for item in filtered if item.source.source_kind not in exclude]
        if source_ref:
            filtered = [
                item for item in filtered
                if item.source.source_ref == source_ref
            ]
        if source_label_query:
            needle = source_label_query.casefold()
            filtered = [
                item for item in filtered
                if item.source.source_label and needle in item.source.source_label.casefold()
            ]

        return filtered

    def _apply_context_filter(
        self,
        items: list[MemoryItem],
        query: MemoryItemsQuery,
    ) -> list[MemoryItem]:
        context = query.context

        filtered = items
        if context.project_id:
            filtered = [
                item for item in filtered
                if item.context_links.project_id == context.project_id
            ]
        if context.conversation_id:
            filtered = [
                item for item in filtered
                if item.context_links.conversation_id == context.conversation_id
            ]
        if context.request_id:
            filtered = [
                item for item in filtered
                if item.context_links.request_id == context.request_id
            ]
        if context.parent_memory_id:
            filtered = [
                item for item in filtered
                if item.context_links.parent_memory_id == context.parent_memory_id
            ]

        return filtered

    def _apply_date_filter(
        self,
        items: list[MemoryItem],
        query: MemoryItemsQuery,
    ) -> list[MemoryItem]:
        dates = query.dates

        filtered = items

        if dates.created_after_utc is not None:
            filtered = [
                item for item in filtered
                if item.created_at_utc >= dates.created_after_utc
            ]
        if dates.created_before_utc is not None:
            filtered = [
                item for item in filtered
                if item.created_at_utc <= dates.created_before_utc
            ]
        if dates.updated_after_utc is not None:
            filtered = [
                item for item in filtered
                if item.updated_at_utc >= dates.updated_after_utc
            ]
        if dates.updated_before_utc is not None:
            filtered = [
                item for item in filtered
                if item.updated_at_utc <= dates.updated_before_utc
            ]
        if dates.captured_after_utc is not None:
            filtered = [
                item for item in filtered
                if item.source.captured_at_utc >= dates.captured_after_utc
            ]
        if dates.captured_before_utc is not None:
            filtered = [
                item for item in filtered
                if item.source.captured_at_utc <= dates.captured_before_utc
            ]

        return filtered

    def _apply_scalar_filter(
        self,
        items: list[MemoryItem],
        query: MemoryItemsQuery,
    ) -> list[MemoryItem]:
        scalars = query.scalars

        filtered = items

        if scalars.min_importance is not None:
            filtered = [
                item for item in filtered
                if item.importance >= scalars.min_importance
            ]
        if scalars.max_importance is not None:
            filtered = [
                item for item in filtered
                if item.importance <= scalars.max_importance
            ]
        if scalars.min_confidence is not None:
            filtered = [
                item for item in filtered
                if item.confidence is not None and item.confidence >= scalars.min_confidence
            ]
        if scalars.max_confidence is not None:
            filtered = [
                item for item in filtered
                if item.confidence is not None and item.confidence <= scalars.max_confidence
            ]

        return filtered

    def _apply_flag_filter(
        self,
        items: list[MemoryItem],
        query: MemoryItemsQuery,
    ) -> list[MemoryItem]:
        flags = query.flags

        filtered = items

        if flags.pinned_only:
            filtered = [item for item in filtered if item.flags.pinned]
        if flags.user_declared_only:
            filtered = [item for item in filtered if item.flags.user_declared]
        if flags.inferred_only:
            filtered = [item for item in filtered if item.flags.inferred]
        if flags.verified_only:
            filtered = [item for item in filtered if item.flags.verified]
        if flags.stale_only:
            filtered = [item for item in filtered if item.flags.stale]

        return filtered

    def _apply_mutation_review_filter(
        self,
        items: list[MemoryItem],
        query: MemoryItemsQuery,
    ) -> list[MemoryItem]:
        review = query.mutation_review

        filtered = items

        if review.review_required_only:
            filtered = [
                item for item in filtered
                if item.mutability.name == "review_required"
            ]

        if review.blocked_mutations_only:
            filtered = [
                item for item in filtered
                if item.status.name == "blocked"
            ]

        if review.pending_candidates_only:
            filtered = [
                item for item in filtered
                if item.status.name == "provisional"
            ]

        if review.autonomous_writes_only:
            filtered = [
                item for item in filtered
                if item.created_by.name in {"assistant", "service"}
            ]

        return filtered

    def _apply_text_filter(
        self,
        items: list[MemoryItem],
        query: MemoryItemsQuery,
    ) -> list[MemoryItem]:
        text = query.text
        if not text.query:
            return items

        needle = text.query if text.case_sensitive else text.query.casefold()

        def contains(value: str) -> bool:
            haystack = value if text.case_sensitive else value.casefold()
            if text.exact_phrase:
                return needle in haystack
            return needle in haystack

        filtered: list[MemoryItem] = []

        for item in items:
            title_match = contains(item.title)
            body_match = contains(item.body)

            if text.title_only and title_match:
                filtered.append(item)
                continue

            if text.body_only and body_match:
                filtered.append(item)
                continue

            if not text.title_only and not text.body_only and (title_match or body_match):
                filtered.append(item)

        return filtered

    def _sort_items(
        self,
        items: list[MemoryItem],
        query: MemoryItemsQuery,
    ) -> list[MemoryItem]:
        reverse = query.sort.sort_direction == MemorySortDirection.desc
        sort_by = query.sort.sort_by

        def sort_key(item: MemoryItem):
            if sort_by == MemorySortField.created_at_utc:
                return (item.created_at_utc, item.memory_id)
            if sort_by == MemorySortField.updated_at_utc:
                return (item.updated_at_utc, item.memory_id)
            if sort_by == MemorySortField.importance:
                return (item.importance, item.updated_at_utc, item.memory_id)
            if sort_by == MemorySortField.confidence:
                confidence = item.confidence if item.confidence is not None else -1.0
                return (confidence, item.updated_at_utc, item.memory_id)
            if sort_by == MemorySortField.title:
                return (item.title.casefold(), item.memory_id)
            return (item.updated_at_utc, item.memory_id)

        return sorted(items, key=sort_key, reverse=reverse)

    def _paginate_items(
        self,
        items: list[MemoryItem],
        query: MemoryItemsQuery,
    ) -> list[MemoryItem]:
        offset = query.pagination.offset
        limit = query.pagination.limit
        return items[offset: offset + limit]
