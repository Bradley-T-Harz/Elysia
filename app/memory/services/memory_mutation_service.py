from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.memory.schemas.memory_item import (
    MemoryActorKind,
    MemoryClass,
    MemoryContextLinks,
    MemoryFlags,
    MemoryItem,
    MemoryMutability,
    MemoryRevisionInfo,
    MemorySensitivity,
    MemorySource,
    MemorySourceKind,
    MemoryStatus,
)
from app.memory.schemas.memory_mutation import (
    MemoryFlagsPatch,
    MemoryMutationActor,
    MemoryMutationDecision,
    MemoryMutationPatch,
    MemoryMutationRecord,
    MemoryMutationRequest,
    MemoryMutationType,
)
from app.memory.services.memory_boundary_service import (
    MemoryBoundaryDecision,
    MemoryBoundaryService,
)
from app.memory.services.memory_item_service import (
    MemoryItemAlreadyExistsError,
    MemoryItemNotFoundError,
    MemoryItemRevisionMismatchError,
    MemoryItemService,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryMutationService:
    """Governed executor for memory changes.

    Responsibilities:
    - accept a typed mutation request
    - resolve current target state
    - ask MemoryBoundaryService for a decision
    - apply allowed item-level changes through MemoryItemService
    - always return a MemoryMutationRecord

    Non-responsibilities:
    - invent policy
    - raw filesystem writes
    - broad retrieval
    - summary aggregation
    """

    def __init__(
        self,
        item_service: MemoryItemService,
        boundary_service: MemoryBoundaryService,
    ) -> None:
        self._item_service = item_service
        self._boundary_service = boundary_service

    @property
    def item_service(self) -> MemoryItemService:
        return self._item_service

    @property
    def boundary_service(self) -> MemoryBoundaryService:
        return self._boundary_service

    def apply_mutation(self, request: MemoryMutationRequest) -> MemoryMutationRecord:
        try:
            existing_item = self._load_single_target(request)
            existing_items = self._load_multi_target(request)

            boundary_decision = self._evaluate_boundary(
                request=request,
                existing_item=existing_item,
            )

            if boundary_decision.blocked:
                return self._record_blocked(request, boundary_decision)

            if boundary_decision.review_required:
                return self._record_review_required(request, boundary_decision)

            if request.dry_run:
                return self._record_allowed_preview(request, boundary_decision)

            handler = self._get_handler(request.mutation_type)
            return handler(
                request=request,
                decision=boundary_decision,
                existing_item=existing_item,
                existing_items=existing_items,
            )

        except Exception as exc:
            return self._record_failed(
                request=request,
                reason="Memory mutation failed during execution.",
                error_message=str(exc),
            )

    def preview_mutation(self, request: MemoryMutationRequest) -> MemoryMutationRecord:
        preview_request = request.model_copy(deep=True)
        preview_request.dry_run = True
        return self.apply_mutation(preview_request)

    def _evaluate_boundary(
        self,
        *,
        request: MemoryMutationRequest,
        existing_item: Optional[MemoryItem],
    ) -> MemoryBoundaryDecision:
        if request.mutation_type in {
            MemoryMutationType.promote,
            MemoryMutationType.demote,
        }:
            from_class = (
                existing_item.memory_class
                if existing_item is not None
                else request.target.memory_class
            )
            to_class = request.patch.memory_class
            if from_class is None or to_class is None:
                return MemoryBoundaryDecision(
                    allowed=False,
                    blocked=True,
                    review_required=False,
                    provisional_only=False,
                    redact_body=False,
                    redact_source=False,
                    reason="Promotion/demotion requires both from_class and to_class.",
                    policy_rule_id=None,
                    explicit_user_permission_required=False,
                )

            return self._boundary_service.evaluate_promotion(
                from_class=from_class,
                to_class=to_class,
                actor=request.actor,
                source_kind=request.context.source_kind,
                confidence=request.patch.confidence,
                repetition_count=1,
                mode=request.mode,
            )

        return self._boundary_service.evaluate_mutation(
            request,
            existing_item=existing_item,
        )

    def _load_single_target(
        self,
        request: MemoryMutationRequest,
    ) -> Optional[MemoryItem]:
        if not request.target.memory_id:
            return None
        return self._item_service.get_item(request.target.memory_id)

    def _load_multi_target(
        self,
        request: MemoryMutationRequest,
    ) -> list[MemoryItem]:
        if not request.target.memory_ids:
            return []
        return [self._item_service.get_item(memory_id) for memory_id in request.target.memory_ids]

    def _get_handler(self, mutation_type: MemoryMutationType):
        handlers = {
            MemoryMutationType.create: self._handle_create,
            MemoryMutationType.revise: self._handle_revise,
            MemoryMutationType.append_note: self._handle_append_note,
            MemoryMutationType.supersede: self._handle_supersede,
            MemoryMutationType.archive: self._handle_archive,
            MemoryMutationType.restore: self._handle_restore,
            MemoryMutationType.pin: self._handle_pin,
            MemoryMutationType.unpin: self._handle_unpin,
            MemoryMutationType.reclassify: self._handle_reclassify,
            MemoryMutationType.change_sensitivity: self._handle_change_sensitivity,
            MemoryMutationType.change_mutability: self._handle_change_mutability,
            MemoryMutationType.promote: self._handle_promote,
            MemoryMutationType.demote: self._handle_demote,
            MemoryMutationType.merge: self._handle_merge,
            MemoryMutationType.forget_request: self._handle_forget_request,
            MemoryMutationType.block: self._handle_block,
            MemoryMutationType.unblock: self._handle_unblock,
        }
        return handlers[mutation_type]

    def _handle_create(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_item, existing_items
        item = self._build_created_item(request=request, decision=decision)
        self._item_service.create_item(item)
        stored_item = self._item_service.get_item(item.memory_id)
        return self._record_applied(
            request=request,
            reason=decision.reason,
            resulting_memory_id=stored_item.memory_id,
        )

    def _handle_revise(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("revise requires an existing target item.")

        revised_item = self._apply_patch_to_item(
            existing_item=existing_item,
            patch=request.patch,
            request=request,
            decision=decision,
        )

        if self._items_equivalent(existing_item, revised_item):
            return self._record_no_op(
                request=request,
                reason="Revision produced no effective change."
            )

        self._item_service.replace_item(
            revised_item,
            expected_revision=request.target.expected_revision,
        )
        stored_item = self._item_service.get_item(revised_item.memory_id)
        return self._record_applied(
            request=request,
            reason=decision.reason,
            resulting_memory_id=stored_item.memory_id,
        )

    def _handle_append_note(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("append_note requires an existing target item.")

        note_body = request.patch.note_body or ""
        appended_body = (
            f"{existing_item.body}\n\n[Appended note]\n{note_body}"
            if existing_item.body
            else f"[Appended note]\n{note_body}"
        )

        patch = request.patch.model_copy(deep=True)
        patch.body = appended_body

        updated_item = self._apply_patch_to_item(
            existing_item=existing_item,
            patch=patch,
            request=request,
            decision=decision,
        )

        self._item_service.replace_item(
            updated_item,
            expected_revision=request.target.expected_revision,
        )
        return self._record_applied(
            request=request,
            reason=decision.reason,
            resulting_memory_id=updated_item.memory_id,
        )

    def _handle_supersede(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("supersede requires an existing target item.")

        successor_id = request.patch.successor_memory_id
        if successor_id:
            self._item_service.supersede_item(
                existing_item.memory_id,
                successor_memory_id=successor_id,
                reason=request.context.reason,
                updated_by=self._actor_to_item_actor(request.actor),
                expected_revision=request.target.expected_revision,
            )
            return self._record_applied(
                request=request,
                reason=decision.reason,
                resulting_memory_id=successor_id,
                superseded_memory_id=existing_item.memory_id,
            )

        successor_item = self._build_successor_from_existing(
            existing_item=existing_item,
            request=request,
            decision=decision,
        )
        self._item_service.create_item(successor_item)
        self._item_service.supersede_item(
            existing_item.memory_id,
            successor_memory_id=successor_item.memory_id,
            reason=request.context.reason,
            updated_by=self._actor_to_item_actor(request.actor),
            expected_revision=request.target.expected_revision,
        )
        return self._record_applied(
            request=request,
            reason=decision.reason,
            resulting_memory_id=successor_item.memory_id,
            superseded_memory_id=existing_item.memory_id,
        )

    def _handle_archive(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("archive requires an existing target item.")

        if existing_item.status == MemoryStatus.archived:
            return self._record_no_op(
                request=request,
                reason="Target item is already archived."
            )

        archived_item = self._item_service.archive_item(
            existing_item.memory_id,
            reason=request.context.reason,
            updated_by=self._actor_to_item_actor(request.actor),
            expected_revision=request.target.expected_revision,
        )
        return self._record_applied(
            request=request,
            reason=decision.reason,
            resulting_memory_id=archived_item.memory_id,
        )

    def _handle_restore(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("restore requires an existing target item.")

        if existing_item.status != MemoryStatus.archived:
            return self._record_no_op(
                request=request,
                reason="Target item is not archived."
            )

        restored_item = existing_item.model_copy(deep=True)
        restored_item.status = MemoryStatus.active
        restored_item.updated_by = self._actor_to_item_actor(request.actor)
        restored_item.updated_at_utc = utc_now()
        restored_item.revision_info.last_mutation_reason = request.context.reason

        self._item_service.replace_item(
            restored_item,
            expected_revision=request.target.expected_revision,
        )
        return self._record_applied(
            request=request,
            reason=decision.reason,
            resulting_memory_id=restored_item.memory_id,
        )

    def _handle_pin(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("pin requires an existing target item.")

        if existing_item.flags.pinned:
            return self._record_no_op(
                request=request,
                reason="Target item is already pinned."
            )

        updated_item = existing_item.model_copy(deep=True)
        updated_item.flags.pinned = True
        updated_item.updated_by = self._actor_to_item_actor(request.actor)
        updated_item.updated_at_utc = utc_now()
        updated_item.revision_info.last_mutation_reason = request.context.reason

        self._item_service.replace_item(
            updated_item,
            expected_revision=request.target.expected_revision,
        )
        return self._record_applied(
            request=request,
            reason=decision.reason,
            resulting_memory_id=updated_item.memory_id,
        )

    def _handle_unpin(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("unpin requires an existing target item.")

        if not existing_item.flags.pinned:
            return self._record_no_op(
                request=request,
                reason="Target item is already unpinned."
            )

        updated_item = existing_item.model_copy(deep=True)
        updated_item.flags.pinned = False
        updated_item.updated_by = self._actor_to_item_actor(request.actor)
        updated_item.updated_at_utc = utc_now()
        updated_item.revision_info.last_mutation_reason = request.context.reason

        self._item_service.replace_item(
            updated_item,
            expected_revision=request.target.expected_revision,
        )
        return self._record_applied(
            request=request,
            reason=decision.reason,
            resulting_memory_id=updated_item.memory_id,
        )

    def _handle_reclassify(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("reclassify requires an existing target item.")

        updated_item = self._apply_patch_to_item(
            existing_item=existing_item,
            patch=request.patch,
            request=request,
            decision=decision,
        )

        if updated_item.memory_class == existing_item.memory_class:
            return self._record_no_op(
                request=request,
                reason="Reclassification produced no class change."
            )

        self._item_service.replace_item(
            updated_item,
            expected_revision=request.target.expected_revision,
        )
        return self._record_applied(
            request=request,
            reason=decision.reason,
            resulting_memory_id=updated_item.memory_id,
        )

    def _handle_change_sensitivity(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("change_sensitivity requires an existing target item.")

        updated_item = self._apply_patch_to_item(
            existing_item=existing_item,
            patch=request.patch,
            request=request,
            decision=decision,
        )

        if updated_item.sensitivity == existing_item.sensitivity:
            return self._record_no_op(
                request=request,
                reason="Sensitivity change produced no effective change."
            )

        self._item_service.replace_item(
            updated_item,
            expected_revision=request.target.expected_revision,
        )
        return self._record_applied(
            request=request,
            reason=decision.reason,
            resulting_memory_id=updated_item.memory_id,
        )

    def _handle_change_mutability(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("change_mutability requires an existing target item.")

        updated_item = self._apply_patch_to_item(
            existing_item=existing_item,
            patch=request.patch,
            request=request,
            decision=decision,
        )

        if updated_item.mutability == existing_item.mutability:
            return self._record_no_op(
                request=request,
                reason="Mutability change produced no effective change."
            )

        self._item_service.replace_item(
            updated_item,
            expected_revision=request.target.expected_revision,
        )
        return self._record_applied(
            request=request,
            reason=decision.reason,
            resulting_memory_id=updated_item.memory_id,
        )

    def _handle_promote(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("promote requires an existing target item.")
        return self._handle_reclassify(
            request=request,
            decision=decision,
            existing_item=existing_item,
            existing_items=[],
        )

    def _handle_demote(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("demote requires an existing target item.")
        return self._handle_reclassify(
            request=request,
            decision=decision,
            existing_item=existing_item,
            existing_items=[],
        )

    def _handle_merge(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_item
        if len(existing_items) < 2:
            raise ValueError("merge requires multiple existing target items.")

        merged_item = self._merge_items_into_successor(
            source_items=existing_items,
            request=request,
            decision=decision,
        )
        self._item_service.create_item(merged_item)

        for item in existing_items:
            self._item_service.supersede_item(
                item.memory_id,
                successor_memory_id=merged_item.memory_id,
                reason=request.context.reason,
                updated_by=self._actor_to_item_actor(request.actor),
                expected_revision=None,
            )

        return self._record_applied(
            request=request,
            reason=decision.reason,
            resulting_memory_id=merged_item.memory_id,
            superseded_memory_id=",".join(item.memory_id for item in existing_items),
        )

    def _handle_forget_request(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("forget_request requires an existing target item.")

        if existing_item.status == MemoryStatus.archived:
            return self._record_no_op(
                request=request,
                reason="Forget request target is already archived."
            )

        archived_item = self._item_service.archive_item(
            existing_item.memory_id,
            reason=f"Forget requested: {request.context.reason}",
            updated_by=self._actor_to_item_actor(request.actor),
            expected_revision=request.target.expected_revision,
        )
        return self._record_applied(
            request=request,
            reason="Forget request recorded as governed archive, not hard deletion.",
            resulting_memory_id=archived_item.memory_id,
        )

    def _handle_block(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("block requires an existing target item.")

        updated_item = existing_item.model_copy(deep=True)
        updated_item.status = MemoryStatus.blocked
        updated_item.updated_by = self._actor_to_item_actor(request.actor)
        updated_item.updated_at_utc = utc_now()
        updated_item.revision_info.last_mutation_reason = request.context.reason

        self._item_service.replace_item(
            updated_item,
            expected_revision=request.target.expected_revision,
        )
        return self._record_applied(
            request=request,
            reason=decision.reason,
            resulting_memory_id=updated_item.memory_id,
        )

    def _handle_unblock(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        existing_item: Optional[MemoryItem],
        existing_items: list[MemoryItem],
    ) -> MemoryMutationRecord:
        del existing_items
        if existing_item is None:
            raise MemoryItemNotFoundError("unblock requires an existing target item.")

        if existing_item.status != MemoryStatus.blocked:
            return self._record_no_op(
                request=request,
                reason="Target item is not blocked."
            )

        updated_item = existing_item.model_copy(deep=True)
        updated_item.status = MemoryStatus.active
        if decision.provisional_only:
            updated_item.status = MemoryStatus.provisional
        updated_item.updated_by = self._actor_to_item_actor(request.actor)
        updated_item.updated_at_utc = utc_now()
        updated_item.revision_info.last_mutation_reason = request.context.reason

        self._item_service.replace_item(
            updated_item,
            expected_revision=request.target.expected_revision,
        )
        return self._record_applied(
            request=request,
            reason=decision.reason,
            resulting_memory_id=updated_item.memory_id,
        )

    def _build_created_item(
        self,
        *,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
    ) -> MemoryItem:
        target_class = self._resolve_target_class(request=request, existing_item=None)
        class_policy = self._get_class_policy(target_class)

        sensitivity = (
            request.patch.sensitivity
            or class_policy.default_sensitivity
        )
        mutability = (
            request.patch.mutability
            or class_policy.default_mutability
        )
        status = request.patch.status or class_policy.default_status
        if decision.provisional_only:
            status = MemoryStatus.provisional

        return MemoryItem(
            memory_class=target_class,
            title=request.patch.title or "Untitled memory",
            body=request.patch.body or "",
            why_stored=request.patch.why_stored or request.context.reason,
            source=self._build_source(request),
            context_links=self._build_context_links(request=request, existing_item=None),
            sensitivity=sensitivity,
            mutability=mutability,
            status=status,
            created_by=self._actor_to_item_actor(request.actor),
            updated_by=self._actor_to_item_actor(request.actor),
            importance=request.patch.importance if request.patch.importance is not None else 0.5,
            confidence=request.patch.confidence,
            flags=self._build_flags_from_patch(request.patch.flags, existing_flags=None),
            revision_info=MemoryRevisionInfo(
                revision=1,
                last_mutation_reason=request.context.reason,
            ),
        )

    def _build_successor_from_existing(
        self,
        *,
        existing_item: MemoryItem,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
    ) -> MemoryItem:
        successor = existing_item.model_copy(deep=True)
        successor.memory_id = MemoryItem().memory_id
        successor.created_at_utc = utc_now()
        successor.updated_at_utc = successor.created_at_utc
        successor.created_by = self._actor_to_item_actor(request.actor)
        successor.updated_by = self._actor_to_item_actor(request.actor)
        successor.revision_info = MemoryRevisionInfo(
            revision=1,
            supersedes_memory_id=existing_item.memory_id,
            last_mutation_reason=request.context.reason,
        )

        successor = self._apply_patch_to_item(
            existing_item=successor,
            patch=request.patch,
            request=request,
            decision=decision,
            increment_revision=False,
        )
        return successor

    def _merge_items_into_successor(
        self,
        *,
        source_items: list[MemoryItem],
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
    ) -> MemoryItem:
        primary = source_items[0]
        target_class = self._resolve_target_class(request=request, existing_item=primary)
        class_policy = self._get_class_policy(target_class)

        merged_title = request.patch.title or "Merged memory"
        merged_body = request.patch.body or "\n\n".join(
            f"[{item.title}]\n{item.body}" for item in source_items
        )
        merged_why = request.patch.why_stored or request.context.reason

        merged_item = MemoryItem(
            memory_class=target_class,
            title=merged_title,
            body=merged_body,
            why_stored=merged_why,
            source=self._build_source(request),
            context_links=self._build_context_links(request=request, existing_item=primary),
            sensitivity=request.patch.sensitivity or class_policy.default_sensitivity,
            mutability=request.patch.mutability or class_policy.default_mutability,
            status=(
                MemoryStatus.provisional
                if decision.provisional_only
                else (request.patch.status or class_policy.default_status)
            ),
            created_by=self._actor_to_item_actor(request.actor),
            updated_by=self._actor_to_item_actor(request.actor),
            importance=request.patch.importance if request.patch.importance is not None else max(
                item.importance for item in source_items
            ),
            confidence=request.patch.confidence,
            flags=self._build_flags_from_patch(request.patch.flags, existing_flags=None),
            revision_info=MemoryRevisionInfo(
                revision=1,
                last_mutation_reason=request.context.reason,
            ),
        )
        return merged_item

    def _apply_patch_to_item(
        self,
        *,
        existing_item: MemoryItem,
        patch: MemoryMutationPatch,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
        increment_revision: bool = True,
    ) -> MemoryItem:
        updated = existing_item.model_copy(deep=True)

        if patch.title is not None:
            updated.title = patch.title
        if patch.body is not None:
            updated.body = patch.body
        if patch.why_stored is not None:
            updated.why_stored = patch.why_stored
        if patch.memory_class is not None:
            updated.memory_class = patch.memory_class
        if patch.sensitivity is not None:
            updated.sensitivity = patch.sensitivity
        if patch.mutability is not None:
            updated.mutability = patch.mutability
        if patch.status is not None:
            updated.status = patch.status
        if decision.provisional_only:
            updated.status = MemoryStatus.provisional
        if patch.importance is not None:
            updated.importance = patch.importance
        if patch.confidence is not None:
            updated.confidence = patch.confidence
        if patch.flags is not None:
            updated.flags = self._build_flags_from_patch(
                patch.flags,
                existing_flags=updated.flags,
            )

        updated.updated_at_utc = utc_now()
        updated.updated_by = self._actor_to_item_actor(request.actor)
        if increment_revision:
            updated.revision_info.revision += 1
        updated.revision_info.last_mutation_reason = request.context.reason

        if patch.successor_memory_id is not None:
            updated.revision_info.superseded_by_memory_id = patch.successor_memory_id
        if patch.revision_note is not None:
            updated.revision_info.last_mutation_reason = patch.revision_note

        return updated

    def _build_source(self, request: MemoryMutationRequest) -> MemorySource:
        source_kind = request.context.source_kind or MemorySourceKind.manual_entry
        source_label = request.context.trigger_event or request.context.source_ref
        return MemorySource(
            source_kind=source_kind,
            source_ref=request.context.source_ref,
            source_label=source_label,
        )

    def _build_context_links(
        self,
        *,
        request: MemoryMutationRequest,
        existing_item: Optional[MemoryItem],
    ) -> MemoryContextLinks:
        existing_links = (
            existing_item.context_links.model_copy(deep=True)
            if existing_item is not None
            else MemoryContextLinks()
        )

        if request.target.project_id is not None:
            existing_links.project_id = request.target.project_id
        if request.target.conversation_id is not None:
            existing_links.conversation_id = request.target.conversation_id

        return existing_links

    def _build_flags_from_patch(
        self,
        patch_flags: Optional[MemoryFlagsPatch],
        *,
        existing_flags: Optional[MemoryFlags],
    ) -> MemoryFlags:
        flags = existing_flags.model_copy(deep=True) if existing_flags is not None else MemoryFlags()

        if patch_flags is None:
            return flags

        if patch_flags.pinned is not None:
            flags.pinned = patch_flags.pinned
        if patch_flags.user_declared is not None:
            flags.user_declared = patch_flags.user_declared
        if patch_flags.inferred is not None:
            flags.inferred = patch_flags.inferred
        if patch_flags.verified is not None:
            flags.verified = patch_flags.verified
        if patch_flags.stale is not None:
            flags.stale = patch_flags.stale

        return flags

    def _resolve_target_class(
        self,
        *,
        request: MemoryMutationRequest,
        existing_item: Optional[MemoryItem],
    ) -> MemoryClass:
        target_class = (
            request.patch.memory_class
            or request.target.memory_class
            or (existing_item.memory_class if existing_item is not None else None)
        )
        if target_class is None:
            raise ValueError("Target memory_class could not be resolved.")
        return target_class

    def _get_class_policy(self, memory_class: MemoryClass):
        for policy in self._boundary_service.policy_set.class_policies:
            if policy.memory_class == memory_class:
                return policy
        raise KeyError(f"No class policy found for {memory_class.value}.")

    def _actor_to_item_actor(self, actor: MemoryMutationActor) -> MemoryActorKind:
        mapping = {
            MemoryMutationActor.user: MemoryActorKind.user,
            MemoryMutationActor.assistant: MemoryActorKind.assistant,
            MemoryMutationActor.system: MemoryActorKind.system,
            MemoryMutationActor.service: MemoryActorKind.service,
        }
        return mapping[actor]

    def _items_equivalent(self, left: MemoryItem, right: MemoryItem) -> bool:
        left_dump = left.model_dump(mode="python")
        right_dump = right.model_dump(mode="python")

        for payload in (left_dump, right_dump):
            payload.pop("updated_at_utc", None)
            payload.pop("updated_by", None)
            revision_info = payload.get("revision_info") or {}
            revision_info.pop("revision", None)
            payload["revision_info"] = revision_info

        return left_dump == right_dump

    def _record_allowed_preview(
        self,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
    ) -> MemoryMutationRecord:
        return MemoryMutationRecord(
            **request.model_dump(mode="python"),
            decision=MemoryMutationDecision.allowed,
            decision_reason=f"Dry run: {decision.reason}",
            evaluated_at_utc=utc_now(),
            applied_at_utc=None,
            resulting_memory_id=None,
            superseded_memory_id=None,
            error_message=None,
        )

    def _record_blocked(
        self,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
    ) -> MemoryMutationRecord:
        return MemoryMutationRecord(
            **request.model_dump(mode="python"),
            decision=MemoryMutationDecision.blocked,
            decision_reason=decision.reason,
            evaluated_at_utc=utc_now(),
            applied_at_utc=None,
            resulting_memory_id=None,
            superseded_memory_id=None,
            error_message=None,
        )

    def _record_review_required(
        self,
        request: MemoryMutationRequest,
        decision: MemoryBoundaryDecision,
    ) -> MemoryMutationRecord:
        return MemoryMutationRecord(
            **request.model_dump(mode="python"),
            decision=MemoryMutationDecision.review_required,
            decision_reason=decision.reason,
            evaluated_at_utc=utc_now(),
            applied_at_utc=None,
            resulting_memory_id=None,
            superseded_memory_id=None,
            error_message=None,
        )

    def _record_applied(
        self,
        *,
        request: MemoryMutationRequest,
        reason: str,
        resulting_memory_id: Optional[str],
        superseded_memory_id: Optional[str] = None,
    ) -> MemoryMutationRecord:
        now = utc_now()
        return MemoryMutationRecord(
            **request.model_dump(mode="python"),
            decision=MemoryMutationDecision.applied,
            decision_reason=reason,
            evaluated_at_utc=now,
            applied_at_utc=now,
            resulting_memory_id=resulting_memory_id,
            superseded_memory_id=superseded_memory_id,
            error_message=None,
        )

    def _record_no_op(
        self,
        *,
        request: MemoryMutationRequest,
        reason: str,
    ) -> MemoryMutationRecord:
        return MemoryMutationRecord(
            **request.model_dump(mode="python"),
            decision=MemoryMutationDecision.no_op,
            decision_reason=reason,
            evaluated_at_utc=utc_now(),
            applied_at_utc=None,
            resulting_memory_id=request.target.memory_id,
            superseded_memory_id=None,
            error_message=None,
        )

    def _record_failed(
        self,
        *,
        request: MemoryMutationRequest,
        reason: str,
        error_message: str,
    ) -> MemoryMutationRecord:
        return MemoryMutationRecord(
            **request.model_dump(mode="python"),
            decision=MemoryMutationDecision.failed,
            decision_reason=reason,
            evaluated_at_utc=utc_now(),
            applied_at_utc=None,
            resulting_memory_id=None,
            superseded_memory_id=None,
            error_message=error_message,
        )
