from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.memory.schemas.memory_item import (
    MemoryClass,
    MemoryItem,
    MemorySensitivity,
    MemorySourceKind,
)
from app.memory.schemas.memory_mutation import (
    MemoryMutationActor,
    MemoryMutationMode,
    MemoryMutationRequest,
    MemoryMutationType,
)
from app.memory.schemas.memory_policy import (
    MemoryActorPolicy,
    MemoryAutonomyPolicy,
    MemoryClassPolicy,
    MemoryMutationRule,
    MemoryPolicySet,
    MemoryPromotionRule,
    MemoryRetentionPolicy,
    MemorySensitivityPolicy,
    MemorySourcePolicy,
)


_SENSITIVITY_ORDER = {
    MemorySensitivity.public: 0,
    MemorySensitivity.internal: 1,
    MemorySensitivity.private: 2,
    MemorySensitivity.sealed: 3,
}


@dataclass(frozen=True)
class BoundaryRoomContext:
    room_name: str = "memory"
    summary_only: bool = False
    explicit_user_permission: bool = False
    allow_sealed_private: bool = False
    allow_cross_room_display: bool = False
    active_project_id: Optional[str] = None
    active_conversation_id: Optional[str] = None
    suppressed_classes: set[MemoryClass] = field(default_factory=set)


@dataclass(frozen=True)
class MemoryBoundaryDecision:
    allowed: bool
    blocked: bool
    review_required: bool
    provisional_only: bool
    redact_body: bool
    redact_source: bool
    reason: str
    policy_rule_id: Optional[str] = None
    explicit_user_permission_required: bool = False


class MemoryBoundaryService:
    """Constitutional gatekeeper for memory retrieval, mutation, and promotion.

    This service interprets a validated MemoryPolicySet and applies it to real
    situations. It does not mutate memory itself. It answers whether something
    is allowed, blocked, review-required, provisional-only, or must be redacted.
    """

    def __init__(self, policy_set: MemoryPolicySet) -> None:
        self._policy_set = policy_set

        self._class_policy_map = {
            policy.memory_class: policy for policy in policy_set.class_policies
        }
        self._sensitivity_policy_map = {
            policy.sensitivity: policy for policy in policy_set.sensitivity_policies
        }
        self._source_policy_map = {
            policy.source_kind: policy for policy in policy_set.source_policies
        }
        self._actor_policy_map = {
            policy.actor: policy for policy in policy_set.actor_policies
        }
        self._mutation_rule_map = {
            rule.mutation_type: rule for rule in policy_set.mutation_rules
        }
        self._promotion_rule_map = {
            (rule.from_class, rule.to_class): rule for rule in policy_set.promotion_rules
        }
        self._retention_policy_map = {
            policy.memory_class: policy for policy in policy_set.retention_policies
        }

    @property
    def policy_set(self) -> MemoryPolicySet:
        return self._policy_set

    def evaluate_retrieval(
        self,
        item: MemoryItem,
        *,
        actor: MemoryMutationActor,
        room_context: Optional[BoundaryRoomContext] = None,
    ) -> MemoryBoundaryDecision:
        room_context = room_context or BoundaryRoomContext()

        class_policy = self._get_class_policy(item.memory_class)
        sensitivity_policy = self._get_sensitivity_policy(item.sensitivity)
        actor_policy = self._get_actor_policy(actor)

        if item.memory_class in room_context.suppressed_classes:
            return self._blocked_decision(
                reason=f"{item.memory_class.value} is suppressed in this retrieval posture."
            )

        if item.memory_class in actor_policy.blocked_classes:
            return self._blocked_decision(
                reason=f"{actor.value} is blocked from {item.memory_class.value} memory."
            )

        if actor_policy.allowed_classes and item.memory_class not in actor_policy.allowed_classes:
            return self._blocked_decision(
                reason=f"{actor.value} is not allowed to access {item.memory_class.value} memory."
            )

        if sensitivity_policy.allowed_actors and actor not in sensitivity_policy.allowed_actors:
            return self._blocked_decision(
                reason=f"{actor.value} is not allowed for {item.sensitivity.value} sensitivity."
            )

        if self._sensitivity_exceeds(actor_policy.max_sensitivity, item.sensitivity):
            return self._blocked_decision(
                reason=(
                    f"{actor.value} exceeds its sensitivity ceiling "
                    f"for {item.sensitivity.value} memory."
                )
            )

        if (
            item.memory_class == MemoryClass.sealed_private
            or item.sensitivity == MemorySensitivity.sealed
        ):
            if not room_context.explicit_user_permission and not room_context.allow_sealed_private:
                return self._blocked_decision(
                    reason="sealed/private memory requires explicit permission for retrieval.",
                    explicit_user_permission_required=True,
                )

        if room_context.summary_only and not sensitivity_policy.allow_summary_exposure:
            return self._blocked_decision(
                reason=f"{item.sensitivity.value} memory cannot be exposed in summaries."
            )

        if (
            room_context.room_name != "memory"
            and not sensitivity_policy.allow_cross_room_display
            and not self._is_same_scope(item, room_context)
        ):
            return self._blocked_decision(
                reason=(
                    f"{item.sensitivity.value} memory cannot be displayed cross-room "
                    "outside its originating scope."
                )
            )

        review_required = sensitivity_policy.requires_review and actor != MemoryMutationActor.user
        redact_body = room_context.summary_only or item.sensitivity in {
            MemorySensitivity.private,
            MemorySensitivity.sealed,
        }
        redact_source = room_context.summary_only or item.sensitivity in {
            MemorySensitivity.private,
            MemorySensitivity.sealed,
        }

        return MemoryBoundaryDecision(
            allowed=True,
            blocked=False,
            review_required=review_required,
            provisional_only=(class_policy.default_status.value == "provisional"),
            redact_body=redact_body,
            redact_source=redact_source,
            reason="Retrieval allowed under current memory boundaries.",
            policy_rule_id=f"sensitivity:{item.sensitivity.value}",
            explicit_user_permission_required=False,
        )

    def evaluate_summary_exposure(
        self,
        item: MemoryItem,
        *,
        actor: MemoryMutationActor,
        room_context: Optional[BoundaryRoomContext] = None,
    ) -> MemoryBoundaryDecision:
        summary_context = room_context or BoundaryRoomContext()
        summary_context = BoundaryRoomContext(
            room_name=summary_context.room_name,
            summary_only=True,
            explicit_user_permission=summary_context.explicit_user_permission,
            allow_sealed_private=summary_context.allow_sealed_private,
            allow_cross_room_display=summary_context.allow_cross_room_display,
            active_project_id=summary_context.active_project_id,
            active_conversation_id=summary_context.active_conversation_id,
            suppressed_classes=set(summary_context.suppressed_classes),
        )
        return self.evaluate_retrieval(
            item,
            actor=actor,
            room_context=summary_context,
        )

    def sanitize_item_for_exposure(
        self,
        item: MemoryItem,
        decision: MemoryBoundaryDecision,
    ) -> Optional[MemoryItem]:
        if decision.blocked:
            return None

        sanitized = item.model_copy(deep=True)

        if decision.redact_body:
            sanitized.body = "[REDACTED]"
            sanitized.why_stored = "[REDACTED]"

        if decision.redact_source:
            sanitized.source.source_ref = None
            sanitized.source.source_label = None

        return sanitized

    def evaluate_mutation(
        self,
        request: MemoryMutationRequest,
        *,
        existing_item: Optional[MemoryItem] = None,
    ) -> MemoryBoundaryDecision:
        actor_policy = self._get_actor_policy(request.actor)
        mutation_rule = self._get_mutation_rule(request.mutation_type)
        autonomy_policy = self._policy_set.autonomy_policy

        target_class = self._resolve_target_class(request, existing_item)
        if target_class is None:
            return self._blocked_decision(
                reason="Target memory_class could not be determined for mutation."
            )

        class_policy = self._get_class_policy(target_class)
        target_sensitivity = self._resolve_target_sensitivity(
            request=request,
            existing_item=existing_item,
            class_policy=class_policy,
        )
        sensitivity_policy = self._get_sensitivity_policy(target_sensitivity)

        source_policy = None
        if request.context.source_kind is not None:
            source_policy = self._get_source_policy(request.context.source_kind)

        if target_class in actor_policy.blocked_classes:
            return self._blocked_decision(
                reason=f"{request.actor.value} is blocked from mutating {target_class.value} memory."
            )

        if actor_policy.allowed_classes and target_class not in actor_policy.allowed_classes:
            return self._blocked_decision(
                reason=f"{request.actor.value} is not allowed to mutate {target_class.value} memory."
            )

        if request.mutation_type in actor_policy.blocked_mutations:
            return self._blocked_decision(
                reason=f"{request.actor.value} is blocked from {request.mutation_type.value} mutations."
            )

        if actor_policy.allowed_mutations and request.mutation_type not in actor_policy.allowed_mutations:
            return self._blocked_decision(
                reason=f"{request.actor.value} is not allowed to perform {request.mutation_type.value}."
            )

        if request.mutation_type in class_policy.blocked_mutations:
            return self._blocked_decision(
                reason=f"{request.mutation_type.value} is blocked for {target_class.value} memory."
            )

        if class_policy.allowed_mutations and request.mutation_type not in class_policy.allowed_mutations:
            return self._blocked_decision(
                reason=f"{request.mutation_type.value} is not allowed for {target_class.value} memory."
            )

        if target_class in mutation_rule.blocked_classes:
            return self._blocked_decision(
                reason=f"{request.mutation_type.value} is blocked for {target_class.value} by mutation rule."
            )

        if mutation_rule.allowed_classes and target_class not in mutation_rule.allowed_classes:
            return self._blocked_decision(
                reason=f"{request.mutation_type.value} is not allowed for {target_class.value} by mutation rule."
            )

        if self._sensitivity_exceeds(actor_policy.max_sensitivity, target_sensitivity):
            return self._blocked_decision(
                reason=(
                    f"{request.actor.value} exceeds its sensitivity ceiling "
                    f"for {target_sensitivity.value} mutation."
                )
            )

        if sensitivity_policy.allowed_actors and request.actor not in sensitivity_policy.allowed_actors:
            return self._blocked_decision(
                reason=f"{request.actor.value} is not allowed for {target_sensitivity.value} mutation."
            )

        if target_sensitivity == MemorySensitivity.sealed and request.actor != MemoryMutationActor.user:
            return self._blocked_decision(
                reason="sealed memory mutation requires explicit user action.",
                explicit_user_permission_required=True,
            )

        if request.review.sensitivity_conflict and autonomy_policy.blocked_when_sensitive_conflict:
            return self._blocked_decision(
                reason="Mutation blocked because a sensitivity conflict was detected."
            )

        if request.mode == MemoryMutationMode.autonomous:
            autonomous_decision = self._evaluate_autonomous_mutation(
                request=request,
                target_class=target_class,
                class_policy=class_policy,
                actor_policy=actor_policy,
                mutation_rule=mutation_rule,
                autonomy_policy=autonomy_policy,
                target_sensitivity=target_sensitivity,
            )
            if autonomous_decision is not None:
                return autonomous_decision

        provisional_only = False
        review_required = False
        reasons: list[str] = []

        if request.mutation_type in class_policy.review_required_mutations:
            review_required = True
            reasons.append("Class policy requires review for this mutation.")

        if request.mutation_type in actor_policy.requires_review_for:
            review_required = True
            reasons.append("Actor policy requires review for this mutation.")

        if mutation_rule.review_required:
            review_required = True
            reasons.append("Mutation rule requires review.")

        if sensitivity_policy.requires_review and request.actor != MemoryMutationActor.user:
            review_required = True
            reasons.append("Sensitivity policy requires review.")

        if request.review.review_required:
            review_required = True
            reasons.append(request.review.review_reason or "Request review flag is set.")

        if source_policy is not None:
            source_decision = self._evaluate_source_constraints(
                request=request,
                target_class=target_class,
                source_policy=source_policy,
            )
            if source_decision is not None and source_decision.blocked:
                return source_decision

            if source_decision is not None and source_decision.review_required:
                review_required = True
                reasons.append(source_decision.reason)

            if (
                target_class in source_policy.provisional_only_classes
                or class_policy.default_status.value == "provisional"
            ):
                provisional_only = True
                reasons.append("Source/class policy limits this mutation to provisional posture.")

        if request.mutation_type == MemoryMutationType.forget_request:
            review_required = True
            reasons.append("forget_request is governed and requires review.")

        if review_required:
            return MemoryBoundaryDecision(
                allowed=False,
                blocked=False,
                review_required=True,
                provisional_only=provisional_only,
                redact_body=False,
                redact_source=False,
                reason=" ".join(reasons) or "Mutation requires review.",
                policy_rule_id=f"mutation:{request.mutation_type.value}",
                explicit_user_permission_required=False,
            )

        return MemoryBoundaryDecision(
            allowed=True,
            blocked=False,
            review_required=False,
            provisional_only=provisional_only,
            redact_body=False,
            redact_source=False,
            reason="Mutation allowed under current memory boundaries.",
            policy_rule_id=f"mutation:{request.mutation_type.value}",
            explicit_user_permission_required=False,
        )

    def evaluate_promotion(
        self,
        *,
        from_class: MemoryClass,
        to_class: MemoryClass,
        actor: MemoryMutationActor,
        source_kind: Optional[MemorySourceKind],
        confidence: Optional[float] = None,
        repetition_count: int = 1,
        mode: MemoryMutationMode = MemoryMutationMode.assisted,
    ) -> MemoryBoundaryDecision:
        promotion_rule = self._get_promotion_rule(from_class, to_class)
        actor_policy = self._get_actor_policy(actor)
        source_policy = self._get_source_policy(source_kind) if source_kind is not None else None

        if not promotion_rule.allowed:
            return self._blocked_decision(
                reason=f"Promotion from {from_class.value} to {to_class.value} is blocked by policy."
            )

        if actor_policy.blocked_classes and to_class in actor_policy.blocked_classes:
            return self._blocked_decision(
                reason=f"{actor.value} is blocked from promoting into {to_class.value} memory."
            )

        if actor_policy.allowed_classes and to_class not in actor_policy.allowed_classes:
            return self._blocked_decision(
                reason=f"{actor.value} is not allowed to promote into {to_class.value} memory."
            )

        if promotion_rule.minimum_confidence is not None:
            if confidence is None or confidence < promotion_rule.minimum_confidence:
                return self._blocked_decision(
                    reason=(
                        f"Promotion requires confidence >= {promotion_rule.minimum_confidence:.2f}."
                    )
                )

        if repetition_count < promotion_rule.minimum_repetition_count:
            return self._blocked_decision(
                reason=(
                    f"Promotion requires repetition_count >= "
                    f"{promotion_rule.minimum_repetition_count}."
                )
            )

        if promotion_rule.required_source_kinds:
            if source_kind is None or source_kind not in promotion_rule.required_source_kinds:
                return self._blocked_decision(
                    reason="Promotion source kind does not satisfy rule requirements."
                )

        if mode == MemoryMutationMode.autonomous and not promotion_rule.autonomous_allowed:
            return self._blocked_decision(
                reason="Autonomous promotion is not allowed for this class transition."
            )

        review_required = promotion_rule.review_required
        provisional_only = promotion_rule.provisional_first
        reason_parts: list[str] = []

        if promotion_rule.review_required:
            reason_parts.append("Promotion rule requires review.")

        if source_policy is not None and to_class in source_policy.requires_review_for:
            review_required = True
            reason_parts.append("Source policy requires review for this destination class.")

        if source_policy is not None and to_class == MemoryClass.preference:
            if not source_policy.allow_preference_creation:
                return self._blocked_decision(
                    reason=f"{source_policy.source_kind.value} cannot directly create preference memory."
                )

        if review_required:
            return MemoryBoundaryDecision(
                allowed=False,
                blocked=False,
                review_required=True,
                provisional_only=provisional_only,
                redact_body=False,
                redact_source=False,
                reason=" ".join(reason_parts) or "Promotion requires review.",
                policy_rule_id=f"promotion:{from_class.value}->{to_class.value}",
                explicit_user_permission_required=False,
            )

        return MemoryBoundaryDecision(
            allowed=True,
            blocked=False,
            review_required=False,
            provisional_only=provisional_only,
            redact_body=False,
            redact_source=False,
            reason=f"Promotion from {from_class.value} to {to_class.value} is allowed.",
            policy_rule_id=f"promotion:{from_class.value}->{to_class.value}",
            explicit_user_permission_required=False,
        )

    def get_retention_policy(self, memory_class: MemoryClass) -> MemoryRetentionPolicy:
        return self._get_retention_policy(memory_class)

    def _evaluate_autonomous_mutation(
        self,
        *,
        request: MemoryMutationRequest,
        target_class: MemoryClass,
        class_policy: MemoryClassPolicy,
        actor_policy: MemoryActorPolicy,
        mutation_rule: MemoryMutationRule,
        autonomy_policy: MemoryAutonomyPolicy,
        target_sensitivity: MemorySensitivity,
    ) -> Optional[MemoryBoundaryDecision]:
        if request.actor != MemoryMutationActor.assistant:
            return self._blocked_decision(
                reason="Autonomous mutation is reserved for assistant actor."
            )

        if not autonomy_policy.allow_assistant_self_maintenance:
            return self._blocked_decision(
                reason="Autonomous mutation is disabled by autonomy policy."
            )

        if MemoryMutationMode.autonomous not in actor_policy.autonomous_modes_allowed:
            return self._blocked_decision(
                reason="Assistant actor policy does not allow autonomous mode."
            )

        if target_sensitivity in {MemorySensitivity.private, MemorySensitivity.sealed}:
            return self._blocked_decision(
                reason="Autonomous mutation is blocked for private/sealed sensitivity.",
                explicit_user_permission_required=(target_sensitivity == MemorySensitivity.sealed),
            )

        if request.mutation_type == MemoryMutationType.create and not class_policy.autonomous_create_allowed:
            return self._blocked_decision(
                reason=f"{target_class.value} memory does not allow autonomous create."
            )

        if request.mutation_type in {
            MemoryMutationType.revise,
            MemoryMutationType.append_note,
            MemoryMutationType.supersede,
            MemoryMutationType.pin,
            MemoryMutationType.unpin,
            MemoryMutationType.reclassify,
            MemoryMutationType.change_sensitivity,
            MemoryMutationType.change_mutability,
            MemoryMutationType.promote,
            MemoryMutationType.demote,
            MemoryMutationType.merge,
            MemoryMutationType.block,
            MemoryMutationType.unblock,
            MemoryMutationType.restore,
        } and not class_policy.autonomous_update_allowed:
            return self._blocked_decision(
                reason=f"{target_class.value} memory does not allow autonomous update."
            )

        if request.mutation_type == MemoryMutationType.archive and not class_policy.autonomous_archive_allowed:
            return self._blocked_decision(
                reason=f"{target_class.value} memory does not allow autonomous archive."
            )

        if request.mutation_type == MemoryMutationType.forget_request and not class_policy.autonomous_forget_allowed:
            return self._blocked_decision(
                reason=f"{target_class.value} memory does not allow autonomous forget."
            )

        if not mutation_rule.autonomous_allowed:
            return self._blocked_decision(
                reason=f"{request.mutation_type.value} is not allowed in autonomous mode."
            )

        return None

    def _evaluate_source_constraints(
        self,
        *,
        request: MemoryMutationRequest,
        target_class: MemoryClass,
        source_policy: MemorySourcePolicy,
    ) -> Optional[MemoryBoundaryDecision]:
        if request.mutation_type == MemoryMutationType.create:
            if (
                source_policy.durable_classes_allowed
                and target_class not in source_policy.durable_classes_allowed
                and target_class not in source_policy.provisional_only_classes
            ):
                return self._blocked_decision(
                    reason=(
                        f"{source_policy.source_kind.value} cannot create durable "
                        f"{target_class.value} memory."
                    )
                )

            if target_class == MemoryClass.preference and not source_policy.allow_preference_creation:
                return self._blocked_decision(
                    reason=(
                        f"{source_policy.source_kind.value} cannot directly create "
                        "preference memory."
                    )
                )

        if request.mutation_type in {
            MemoryMutationType.revise,
            MemoryMutationType.promote,
            MemoryMutationType.demote,
        } and target_class == MemoryClass.preference:
            if not source_policy.allow_preference_update:
                return self._blocked_decision(
                    reason=(
                        f"{source_policy.source_kind.value} cannot directly update "
                        "preference memory."
                    )
                )

        if source_policy.requires_confidence and request.patch.confidence is None:
            return MemoryBoundaryDecision(
                allowed=False,
                blocked=False,
                review_required=True,
                provisional_only=True,
                redact_body=False,
                redact_source=False,
                reason=(
                    f"{source_policy.source_kind.value} requires confidence for this memory operation."
                ),
                policy_rule_id=f"source:{source_policy.source_kind.value}",
                explicit_user_permission_required=False,
            )

        if target_class in source_policy.requires_review_for:
            return MemoryBoundaryDecision(
                allowed=False,
                blocked=False,
                review_required=True,
                provisional_only=(target_class in source_policy.provisional_only_classes),
                redact_body=False,
                redact_source=False,
                reason=(
                    f"{source_policy.source_kind.value} requires review for "
                    f"{target_class.value} memory."
                ),
                policy_rule_id=f"source:{source_policy.source_kind.value}",
                explicit_user_permission_required=False,
            )

        return None

    def _resolve_target_class(
        self,
        request: MemoryMutationRequest,
        existing_item: Optional[MemoryItem],
    ) -> Optional[MemoryClass]:
        return (
            request.patch.memory_class
            or request.target.memory_class
            or (existing_item.memory_class if existing_item is not None else None)
        )

    def _resolve_target_sensitivity(
        self,
        *,
        request: MemoryMutationRequest,
        existing_item: Optional[MemoryItem],
        class_policy: MemoryClassPolicy,
    ) -> MemorySensitivity:
        return (
            request.patch.sensitivity
            or (existing_item.sensitivity if existing_item is not None else None)
            or class_policy.default_sensitivity
        )

    def _is_same_scope(
        self,
        item: MemoryItem,
        room_context: BoundaryRoomContext,
    ) -> bool:
        if (
            room_context.active_project_id
            and item.context_links.project_id == room_context.active_project_id
        ):
            return True

        if (
            room_context.active_conversation_id
            and item.context_links.conversation_id == room_context.active_conversation_id
        ):
            return True

        return False

    def _sensitivity_exceeds(
        self,
        allowed: MemorySensitivity,
        actual: MemorySensitivity,
    ) -> bool:
        return _SENSITIVITY_ORDER[actual] > _SENSITIVITY_ORDER[allowed]

    def _get_class_policy(self, memory_class: MemoryClass) -> MemoryClassPolicy:
        return self._class_policy_map[memory_class]

    def _get_sensitivity_policy(
        self,
        sensitivity: MemorySensitivity,
    ) -> MemorySensitivityPolicy:
        return self._sensitivity_policy_map[sensitivity]

    def _get_source_policy(
        self,
        source_kind: MemorySourceKind,
    ) -> MemorySourcePolicy:
        return self._source_policy_map[source_kind]

    def _get_actor_policy(
        self,
        actor: MemoryMutationActor,
    ) -> MemoryActorPolicy:
        return self._actor_policy_map[actor]

    def _get_mutation_rule(
        self,
        mutation_type: MemoryMutationType,
    ) -> MemoryMutationRule:
        return self._mutation_rule_map[mutation_type]

    def _get_promotion_rule(
        self,
        from_class: MemoryClass,
        to_class: MemoryClass,
    ) -> MemoryPromotionRule:
        try:
            return self._promotion_rule_map[(from_class, to_class)]
        except KeyError as exc:
            raise KeyError(
                f"No promotion rule defined for {from_class.value} -> {to_class.value}."
            ) from exc

    def _get_retention_policy(
        self,
        memory_class: MemoryClass,
    ) -> MemoryRetentionPolicy:
        return self._retention_policy_map[memory_class]

    def _blocked_decision(
        self,
        *,
        reason: str,
        explicit_user_permission_required: bool = False,
    ) -> MemoryBoundaryDecision:
        return MemoryBoundaryDecision(
            allowed=False,
            blocked=True,
            review_required=False,
            provisional_only=False,
            redact_body=False,
            redact_source=False,
            reason=reason,
            policy_rule_id=None,
            explicit_user_permission_required=explicit_user_permission_required,
        )
