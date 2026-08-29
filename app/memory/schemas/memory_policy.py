from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .memory_item import (
    MemoryClass,
    MemoryMutability,
    MemorySensitivity,
    MemorySourceKind,
    MemoryStatus,
)
from .memory_mutation import (
    MemoryMutationActor,
    MemoryMutationMode,
    MemoryMutationRiskLevel,
    MemoryMutationType,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


_SENSITIVITY_ORDER = {
    MemorySensitivity.public: 0,
    MemorySensitivity.internal: 1,
    MemorySensitivity.private: 2,
    MemorySensitivity.sealed: 3,
}


class MemoryClassPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_class: MemoryClass
    default_sensitivity: MemorySensitivity
    default_mutability: MemoryMutability
    default_status: MemoryStatus = MemoryStatus.active

    allowed_mutations: list[MemoryMutationType] = Field(default_factory=list)
    blocked_mutations: list[MemoryMutationType] = Field(default_factory=list)
    review_required_mutations: list[MemoryMutationType] = Field(default_factory=list)

    autonomous_create_allowed: bool = False
    autonomous_update_allowed: bool = False
    autonomous_archive_allowed: bool = False
    autonomous_forget_allowed: bool = False

    append_only_default: bool = False
    immutable_default: bool = False
    durable_by_default: bool = True
    allow_direct_user_edit: bool = True

    @model_validator(mode="after")
    def validate_class_policy(self) -> "MemoryClassPolicy":
        allowed = set(self.allowed_mutations)
        blocked = set(self.blocked_mutations)
        review_required = set(self.review_required_mutations)

        overlap = allowed & blocked
        if overlap:
            raise ValueError(
                f"Class policy cannot both allow and block the same mutations: {sorted(value.value for value in overlap)}"
            )

        if review_required - allowed:
            raise ValueError(
                "review_required_mutations must also appear in allowed_mutations."
            )

        if self.append_only_default and self.immutable_default:
            raise ValueError(
                "append_only_default and immutable_default cannot both be true."
            )

        if self.memory_class == MemoryClass.sealed_private:
            if self.default_sensitivity != MemorySensitivity.sealed:
                raise ValueError(
                    "sealed_private must default to sealed sensitivity."
                )
            if self.default_mutability == MemoryMutability.live_editable:
                raise ValueError(
                    "sealed_private cannot default to live_editable mutability."
                )
            if self.autonomous_update_allowed or self.autonomous_forget_allowed:
                raise ValueError(
                    "sealed_private cannot allow autonomous update or autonomous forget by default."
                )

        if self.memory_class == MemoryClass.audit:
            if self.default_mutability not in {
                MemoryMutability.append_only,
                MemoryMutability.immutable,
                MemoryMutability.review_required,
            }:
                raise ValueError(
                    "audit must default to append_only, immutable, or review_required mutability."
                )
            if self.autonomous_forget_allowed:
                raise ValueError(
                    "audit cannot allow autonomous forget."
                )

        if self.immutable_default and self.autonomous_update_allowed:
            raise ValueError(
                "immutable_default classes cannot also allow autonomous_update_allowed."
            )

        return self


class MemorySensitivityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sensitivity: MemorySensitivity
    allowed_actors: list[MemoryMutationActor] = Field(default_factory=list)

    autonomous_access_allowed: bool = False
    autonomous_mutation_allowed: bool = False

    requires_review: bool = False
    requires_explicit_user_permission: bool = False

    default_retrieval_allowed: bool = True
    allow_cross_room_display: bool = True
    allow_summary_exposure: bool = True

    @model_validator(mode="after")
    def validate_sensitivity_policy(self) -> "MemorySensitivityPolicy":
        if self.sensitivity == MemorySensitivity.sealed:
            if self.autonomous_mutation_allowed:
                raise ValueError("sealed sensitivity cannot allow autonomous mutation.")
            if self.default_retrieval_allowed:
                raise ValueError("sealed sensitivity cannot allow default retrieval.")
            if self.allow_cross_room_display:
                raise ValueError("sealed sensitivity cannot allow cross-room display.")
            if self.allow_summary_exposure:
                raise ValueError("sealed sensitivity cannot allow summary exposure.")
            if not self.requires_explicit_user_permission:
                raise ValueError(
                    "sealed sensitivity must require explicit user permission."
                )

        return self


class MemorySourcePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: MemorySourceKind
    durable_classes_allowed: list[MemoryClass] = Field(default_factory=list)
    provisional_only_classes: list[MemoryClass] = Field(default_factory=list)

    requires_confidence: bool = False
    requires_review_for: list[MemoryClass] = Field(default_factory=list)

    autonomous_promotion_allowed: bool = False
    trust_weight: float = Field(default=0.5, ge=0.0, le=1.0)

    allow_preference_creation: bool = False
    allow_preference_update: bool = False

    @model_validator(mode="after")
    def validate_source_policy(self) -> "MemorySourcePolicy":
        durable = set(self.durable_classes_allowed)
        provisional_only = set(self.provisional_only_classes)

        overlap = durable & provisional_only
        if overlap:
            raise ValueError(
                f"Source policy cannot mark the same classes as both durable and provisional-only: {sorted(value.value for value in overlap)}"
            )

        if self.source_kind == MemorySourceKind.assistant_inference:
            if self.allow_preference_creation or self.allow_preference_update:
                raise ValueError(
                    "assistant_inference cannot directly allow durable preference creation or update."
                )

        if self.source_kind == MemorySourceKind.runtime_trace:
            if self.allow_preference_creation or self.allow_preference_update:
                raise ValueError(
                    "runtime_trace cannot create or update preference memory."
                )

        return self


class MemoryActorPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: MemoryMutationActor
    allowed_classes: list[MemoryClass] = Field(default_factory=list)
    blocked_classes: list[MemoryClass] = Field(default_factory=list)

    allowed_mutations: list[MemoryMutationType] = Field(default_factory=list)
    blocked_mutations: list[MemoryMutationType] = Field(default_factory=list)
    requires_review_for: list[MemoryMutationType] = Field(default_factory=list)

    max_sensitivity: MemorySensitivity = MemorySensitivity.internal
    autonomous_modes_allowed: list[MemoryMutationMode] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_actor_policy(self) -> "MemoryActorPolicy":
        class_overlap = set(self.allowed_classes) & set(self.blocked_classes)
        if class_overlap:
            raise ValueError(
                f"Actor policy cannot both allow and block the same classes: {sorted(value.value for value in class_overlap)}"
            )

        mutation_overlap = set(self.allowed_mutations) & set(self.blocked_mutations)
        if mutation_overlap:
            raise ValueError(
                f"Actor policy cannot both allow and block the same mutations: {sorted(value.value for value in mutation_overlap)}"
            )

        if set(self.requires_review_for) - set(self.allowed_mutations):
            raise ValueError(
                "requires_review_for must be a subset of allowed_mutations."
            )

        if (
            self.actor != MemoryMutationActor.assistant
            and MemoryMutationMode.autonomous in self.autonomous_modes_allowed
        ):
            raise ValueError(
                "autonomous mode is reserved for assistant actor policy."
            )

        return self


class MemoryMutationRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mutation_type: MemoryMutationType
    allowed_classes: list[MemoryClass] = Field(default_factory=list)
    blocked_classes: list[MemoryClass] = Field(default_factory=list)

    autonomous_allowed: bool = False
    review_required: bool = False

    requires_reason: bool = True
    requires_target: bool = True
    requires_expected_revision: bool = False
    requires_provenance: bool = False

    allow_multi_target: bool = False
    allow_sealed_private: bool = False
    allow_direct_apply: bool = True

    @model_validator(mode="after")
    def validate_mutation_rule(self) -> "MemoryMutationRule":
        overlap = set(self.allowed_classes) & set(self.blocked_classes)
        if overlap:
            raise ValueError(
                f"Mutation rule cannot both allow and block the same classes: {sorted(value.value for value in overlap)}"
            )

        if self.mutation_type == MemoryMutationType.create and self.requires_target:
            raise ValueError("create should not require an existing target.")

        if self.mutation_type == MemoryMutationType.merge and not self.allow_multi_target:
            raise ValueError("merge must allow multi-target mutation.")

        if self.mutation_type == MemoryMutationType.forget_request and self.allow_direct_apply:
            raise ValueError(
                "forget_request cannot allow direct apply."
            )

        if self.allow_sealed_private and not self.review_required:
            raise ValueError(
                "sealed/private mutation access should require review."
            )

        return self


class MemoryPromotionRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_class: MemoryClass
    to_class: MemoryClass

    allowed: bool = True
    review_required: bool = False

    minimum_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    minimum_repetition_count: int = Field(default=1, ge=1)

    required_source_kinds: list[MemorySourceKind] = Field(default_factory=list)

    autonomous_allowed: bool = False
    provisional_first: bool = False
    reason_required: bool = True

    @model_validator(mode="after")
    def validate_promotion_rule(self) -> "MemoryPromotionRule":
        if self.from_class == self.to_class:
            raise ValueError("from_class and to_class must differ.")

        if not self.allowed and self.autonomous_allowed:
            raise ValueError("autonomous_allowed cannot be true when the promotion is not allowed.")

        if self.to_class == MemoryClass.preference and self.autonomous_allowed and not self.review_required:
            raise ValueError(
                "Autonomous promotion into preference memory must require review."
            )

        return self


class MemoryRetentionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_class: MemoryClass

    archive_before_forget: bool = True
    hard_delete_allowed: bool = False
    hard_delete_requires_user: bool = True

    stale_after_days: Optional[int] = Field(default=None, ge=1)
    auto_archive_after_days: Optional[int] = Field(default=None, ge=1)
    auto_forget_after_days: Optional[int] = Field(default=None, ge=1)

    retain_superseded_history: bool = True
    sealed_retention_override: bool = False

    @model_validator(mode="after")
    def validate_retention_policy(self) -> "MemoryRetentionPolicy":
        if (
            self.stale_after_days is not None
            and self.auto_archive_after_days is not None
            and self.auto_archive_after_days < self.stale_after_days
        ):
            raise ValueError(
                "auto_archive_after_days cannot be earlier than stale_after_days."
            )

        if self.auto_forget_after_days is not None:
            if not self.hard_delete_allowed:
                raise ValueError(
                    "auto_forget_after_days cannot be set when hard_delete_allowed is false."
                )
            if self.archive_before_forget and self.auto_archive_after_days is None:
                raise ValueError(
                    "archive_before_forget requires auto_archive_after_days before auto_forget_after_days."
                )
            if (
                self.auto_archive_after_days is not None
                and self.auto_forget_after_days < self.auto_archive_after_days
            ):
                raise ValueError(
                    "auto_forget_after_days cannot be earlier than auto_archive_after_days."
                )

        if self.memory_class == MemoryClass.audit:
            if self.hard_delete_allowed:
                raise ValueError("audit retention cannot allow hard delete.")
            if not self.retain_superseded_history:
                raise ValueError(
                    "audit retention must preserve superseded history."
                )

        if self.memory_class == MemoryClass.sealed_private and self.auto_forget_after_days is not None:
            raise ValueError(
                "sealed_private retention should not auto-forget by default."
            )

        return self


class MemoryAutonomyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_queue_enabled: bool = True
    auto_apply_low_risk: bool = False
    auto_apply_as_provisional: bool = True
    blocked_when_sensitive_conflict: bool = True

    review_threshold: MemoryMutationRiskLevel = MemoryMutationRiskLevel.medium

    allow_assistant_self_maintenance: bool = False
    audit_required_for_all_autonomous_writes: bool = True
    require_policy_trace: bool = True

    @model_validator(mode="after")
    def validate_autonomy_policy(self) -> "MemoryAutonomyPolicy":
        if (
            self.auto_apply_low_risk or self.auto_apply_as_provisional
        ) and not self.audit_required_for_all_autonomous_writes:
            raise ValueError(
                "Autonomous auto-apply paths require audit_required_for_all_autonomous_writes."
            )

        if not self.allow_assistant_self_maintenance and self.auto_apply_low_risk:
            raise ValueError(
                "auto_apply_low_risk requires allow_assistant_self_maintenance."
            )

        return self


class MemoryPolicySet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str = Field(default="1.0", min_length=1, max_length=64)
    generated_at_utc: datetime = Field(default_factory=utc_now)

    class_policies: list[MemoryClassPolicy] = Field(default_factory=list)
    sensitivity_policies: list[MemorySensitivityPolicy] = Field(default_factory=list)
    source_policies: list[MemorySourcePolicy] = Field(default_factory=list)
    actor_policies: list[MemoryActorPolicy] = Field(default_factory=list)
    mutation_rules: list[MemoryMutationRule] = Field(default_factory=list)
    promotion_rules: list[MemoryPromotionRule] = Field(default_factory=list)
    retention_policies: list[MemoryRetentionPolicy] = Field(default_factory=list)
    autonomy_policy: MemoryAutonomyPolicy = Field(default_factory=MemoryAutonomyPolicy)

    @model_validator(mode="after")
    def validate_policy_set(self) -> "MemoryPolicySet":
        class_keys = [policy.memory_class for policy in self.class_policies]
        if len(class_keys) != len(set(class_keys)):
            raise ValueError("class_policies cannot contain duplicate memory classes.")

        sensitivity_keys = [policy.sensitivity for policy in self.sensitivity_policies]
        if len(sensitivity_keys) != len(set(sensitivity_keys)):
            raise ValueError("sensitivity_policies cannot contain duplicate sensitivities.")

        source_keys = [policy.source_kind for policy in self.source_policies]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("source_policies cannot contain duplicate source kinds.")

        actor_keys = [policy.actor for policy in self.actor_policies]
        if len(actor_keys) != len(set(actor_keys)):
            raise ValueError("actor_policies cannot contain duplicate actors.")

        mutation_keys = [rule.mutation_type for rule in self.mutation_rules]
        if len(mutation_keys) != len(set(mutation_keys)):
            raise ValueError("mutation_rules cannot contain duplicate mutation types.")

        retention_keys = [policy.memory_class for policy in self.retention_policies]
        if len(retention_keys) != len(set(retention_keys)):
            raise ValueError("retention_policies cannot contain duplicate memory classes.")

        promotion_pairs = [(rule.from_class, rule.to_class) for rule in self.promotion_rules]
        if len(promotion_pairs) != len(set(promotion_pairs)):
            raise ValueError("promotion_rules cannot contain duplicate from/to class pairs.")

        if set(class_keys) != set(MemoryClass):
            raise ValueError("class_policies must cover every MemoryClass exactly once.")

        if set(sensitivity_keys) != set(MemorySensitivity):
            raise ValueError(
                "sensitivity_policies must cover every MemorySensitivity exactly once."
            )

        if set(source_keys) != set(MemorySourceKind):
            raise ValueError("source_policies must cover every MemorySourceKind exactly once.")

        if set(actor_keys) != set(MemoryMutationActor):
            raise ValueError("actor_policies must cover every MemoryMutationActor exactly once.")

        if set(mutation_keys) != set(MemoryMutationType):
            raise ValueError("mutation_rules must cover every MemoryMutationType exactly once.")

        if set(retention_keys) != set(MemoryClass):
            raise ValueError("retention_policies must cover every MemoryClass exactly once.")

        sensitivity_map = {policy.sensitivity: policy for policy in self.sensitivity_policies}
        sealed_policy = sensitivity_map[MemorySensitivity.sealed]
        private_policy = sensitivity_map[MemorySensitivity.private]
        internal_policy = sensitivity_map[MemorySensitivity.internal]

        if sealed_policy.default_retrieval_allowed:
            raise ValueError("sealed sensitivity cannot allow default retrieval.")
        if sealed_policy.allow_summary_exposure:
            raise ValueError("sealed sensitivity cannot allow summary exposure.")
        if sealed_policy.allow_cross_room_display:
            raise ValueError("sealed sensitivity cannot allow cross-room display.")
        if not sealed_policy.requires_explicit_user_permission:
            raise ValueError(
                "sealed sensitivity must require explicit user permission."
            )

        actor_map = {policy.actor: policy for policy in self.actor_policies}
        assistant_policy = actor_map[MemoryMutationActor.assistant]
        if (
            not self.autonomy_policy.allow_assistant_self_maintenance
            and MemoryMutationMode.autonomous in assistant_policy.autonomous_modes_allowed
        ):
            raise ValueError(
                "Assistant autonomous modes require allow_assistant_self_maintenance."
            )

        source_map = {policy.source_kind: policy for policy in self.source_policies}
        assistant_inference_policy = source_map[MemorySourceKind.assistant_inference]
        if (
            assistant_inference_policy.allow_preference_creation
            or assistant_inference_policy.allow_preference_update
        ):
            raise ValueError(
                "assistant_inference source policy cannot directly allow preference creation or update."
            )

        return self
