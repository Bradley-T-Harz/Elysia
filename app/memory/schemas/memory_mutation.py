from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .memory_item import (
    MemoryClass,
    MemoryMutability,
    MemorySensitivity,
    MemorySourceKind,
    MemoryStatus,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryMutationType(str, Enum):
    create = "create"
    revise = "revise"
    append_note = "append_note"
    supersede = "supersede"
    archive = "archive"
    restore = "restore"
    pin = "pin"
    unpin = "unpin"
    reclassify = "reclassify"
    change_sensitivity = "change_sensitivity"
    change_mutability = "change_mutability"
    promote = "promote"
    demote = "demote"
    merge = "merge"
    forget_request = "forget_request"
    block = "block"
    unblock = "unblock"


class MemoryMutationActor(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    service = "service"


class MemoryMutationMode(str, Enum):
    manual = "manual"
    assisted = "assisted"
    autonomous = "autonomous"
    review_queue = "review_queue"
    system_maintenance = "system_maintenance"


class MemoryMutationDecision(str, Enum):
    allowed = "allowed"
    applied = "applied"
    blocked = "blocked"
    review_required = "review_required"
    deferred = "deferred"
    no_op = "no_op"
    failed = "failed"


class MemoryMutationRiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class MemoryFlagsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pinned: Optional[bool] = None
    user_declared: Optional[bool] = None
    inferred: Optional[bool] = None
    verified: Optional[bool] = None
    stale: Optional[bool] = None

    def has_changes(self) -> bool:
        return any(
            value is not None
            for value in (
                self.pinned,
                self.user_declared,
                self.inferred,
                self.verified,
                self.stale,
            )
        )


class MemoryMutationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    memory_id: Optional[str] = Field(default=None, max_length=128)
    memory_ids: list[str] = Field(default_factory=list)
    expected_revision: Optional[int] = Field(default=None, ge=1)
    memory_class: Optional[MemoryClass] = None
    project_id: Optional[str] = Field(default=None, max_length=128)
    conversation_id: Optional[str] = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_target(self) -> "MemoryMutationTarget":
        if self.memory_id and self.memory_ids:
            raise ValueError("Use either memory_id or memory_ids, not both.")

        if self.memory_ids:
            normalized = [value.strip() for value in self.memory_ids if value.strip()]
            if len(normalized) != len(self.memory_ids):
                raise ValueError("memory_ids cannot contain empty values.")
            if len(set(normalized)) != len(normalized):
                raise ValueError("memory_ids cannot contain duplicates.")
            self.memory_ids = normalized

        return self

    def has_single_target(self) -> bool:
        return bool(self.memory_id) and not self.memory_ids

    def has_multi_target(self) -> bool:
        return len(self.memory_ids) > 0 and not self.memory_id


class MemoryMutationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Optional[str] = Field(default=None, min_length=1, max_length=160)
    body: Optional[str] = Field(default=None, min_length=1, max_length=8000)
    why_stored: Optional[str] = Field(default=None, min_length=1, max_length=500)

    memory_class: Optional[MemoryClass] = None
    sensitivity: Optional[MemorySensitivity] = None
    mutability: Optional[MemoryMutability] = None
    status: Optional[MemoryStatus] = None

    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    flags: Optional[MemoryFlagsPatch] = None

    note_body: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    successor_memory_id: Optional[str] = Field(default=None, max_length=128)
    revision_note: Optional[str] = Field(default=None, max_length=240)

    def has_substantive_changes(self) -> bool:
        return any(
            value is not None
            for value in (
                self.title,
                self.body,
                self.why_stored,
                self.memory_class,
                self.sensitivity,
                self.mutability,
                self.status,
                self.importance,
                self.confidence,
                self.note_body,
                self.successor_memory_id,
            )
        ) or (self.flags is not None and self.flags.has_changes())

    def has_core_content_changes(self) -> bool:
        return any(value is not None for value in (self.title, self.body, self.why_stored))


class MemoryMutationContext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(..., min_length=1, max_length=500)
    source_kind: Optional[MemorySourceKind] = None
    source_ref: Optional[str] = Field(default=None, max_length=256)
    trigger_event: Optional[str] = Field(default=None, max_length=160)
    notes: Optional[str] = Field(default=None, max_length=1000)


class MemoryMutationReviewInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    risk_level: MemoryMutationRiskLevel = MemoryMutationRiskLevel.medium
    review_required: bool = False
    review_reason: Optional[str] = Field(default=None, max_length=240)
    policy_rule_id: Optional[str] = Field(default=None, max_length=128)
    sensitivity_conflict: bool = False
    autonomous_allowed: bool = False

    @model_validator(mode="after")
    def validate_review_info(self) -> "MemoryMutationReviewInfo":
        if self.review_required and not self.review_reason:
            raise ValueError("review_reason is required when review_required is true.")
        return self


class MemoryMutationRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        use_enum_values=False,
    )

    mutation_id: str = Field(
        default_factory=lambda: f"mmut_{uuid4().hex}",
        min_length=8,
        max_length=128,
    )
    mutation_type: MemoryMutationType
    actor: MemoryMutationActor
    mode: MemoryMutationMode

    target: MemoryMutationTarget = Field(default_factory=MemoryMutationTarget)
    patch: MemoryMutationPatch = Field(default_factory=MemoryMutationPatch)
    context: MemoryMutationContext

    requested_at_utc: datetime = Field(default_factory=utc_now)

    review: MemoryMutationReviewInfo = Field(default_factory=MemoryMutationReviewInfo)

    requested_by: Optional[str] = Field(default=None, max_length=128)
    dry_run: bool = False

    @model_validator(mode="after")
    def validate_request(self) -> "MemoryMutationRequest":
        single_target_required = {
            MemoryMutationType.revise,
            MemoryMutationType.append_note,
            MemoryMutationType.supersede,
            MemoryMutationType.archive,
            MemoryMutationType.restore,
            MemoryMutationType.pin,
            MemoryMutationType.unpin,
            MemoryMutationType.reclassify,
            MemoryMutationType.change_sensitivity,
            MemoryMutationType.change_mutability,
            MemoryMutationType.promote,
            MemoryMutationType.demote,
            MemoryMutationType.block,
            MemoryMutationType.unblock,
        }

        multi_target_required = {
            MemoryMutationType.merge,
        }

        target_optional = {
            MemoryMutationType.create,
        }

        if self.mutation_type in single_target_required and not self.target.has_single_target():
            raise ValueError(f"{self.mutation_type.value} requires exactly one target memory_id.")

        if self.mutation_type in multi_target_required and not self.target.has_multi_target():
            raise ValueError(f"{self.mutation_type.value} requires multiple target memory_ids.")

        if self.mutation_type not in target_optional and self.mutation_type != MemoryMutationType.forget_request:
            if not self.target.has_single_target() and not self.target.has_multi_target():
                raise ValueError(f"{self.mutation_type.value} requires a target.")

        if self.mutation_type == MemoryMutationType.create:
            if self.target.has_single_target() or self.target.has_multi_target():
                raise ValueError("create should not target an existing memory_id or memory_ids.")
            if not self.patch.title or not self.patch.body or not self.patch.why_stored:
                raise ValueError(
                    "create requires title, body, and why_stored in the patch."
                )
            if self.patch.memory_class is None and self.target.memory_class is None:
                raise ValueError(
                    "create requires a target memory_class or patch memory_class."
                )

        if self.mutation_type == MemoryMutationType.revise:
            if not self.patch.has_substantive_changes():
                raise ValueError("revise requires a non-empty substantive patch.")

        if self.mutation_type == MemoryMutationType.append_note:
            if not self.patch.note_body:
                raise ValueError("append_note requires note_body.")
            if self.patch.has_core_content_changes():
                raise ValueError("append_note should not replace core title/body/why content.")

        if self.mutation_type == MemoryMutationType.supersede:
            if not (self.patch.successor_memory_id or self.patch.has_core_content_changes()):
                raise ValueError(
                    "supersede requires successor_memory_id or replacement content."
                )

        if self.mutation_type in {MemoryMutationType.archive, MemoryMutationType.restore}:
            if any(
                value is not None
                for value in (
                    self.patch.title,
                    self.patch.body,
                    self.patch.why_stored,
                    self.patch.memory_class,
                    self.patch.sensitivity,
                    self.patch.mutability,
                    self.patch.importance,
                    self.patch.confidence,
                    self.patch.note_body,
                    self.patch.successor_memory_id,
                )
            ) or (self.patch.flags is not None and self.patch.flags.has_changes()):
                raise ValueError(
                    f"{self.mutation_type.value} should not rewrite core memory content."
                )

        if self.mutation_type == MemoryMutationType.pin:
            if self.patch.flags and self.patch.flags.pinned is False:
                raise ValueError("pin cannot explicitly set pinned to false.")
            if self.patch.flags is None:
                self.patch.flags = MemoryFlagsPatch(pinned=True)
            elif self.patch.flags.pinned is None:
                self.patch.flags.pinned = True

        if self.mutation_type == MemoryMutationType.unpin:
            if self.patch.flags and self.patch.flags.pinned is True:
                raise ValueError("unpin cannot explicitly set pinned to true.")
            if self.patch.flags is None:
                self.patch.flags = MemoryFlagsPatch(pinned=False)
            elif self.patch.flags.pinned is None:
                self.patch.flags.pinned = False

        if self.mutation_type == MemoryMutationType.reclassify and self.patch.memory_class is None:
            raise ValueError("reclassify requires patch.memory_class.")

        if self.mutation_type == MemoryMutationType.change_sensitivity and self.patch.sensitivity is None:
            raise ValueError("change_sensitivity requires patch.sensitivity.")

        if self.mutation_type == MemoryMutationType.change_mutability and self.patch.mutability is None:
            raise ValueError("change_mutability requires patch.mutability.")

        if self.mutation_type in {MemoryMutationType.promote, MemoryMutationType.demote}:
            if self.patch.memory_class is None:
                raise ValueError(f"{self.mutation_type.value} requires patch.memory_class.")
            if self.target.memory_class is not None and self.target.memory_class == self.patch.memory_class:
                raise ValueError(
                    f"{self.mutation_type.value} requires a different destination memory_class."
                )

        if self.mutation_type == MemoryMutationType.merge:
            if len(self.target.memory_ids) < 2:
                raise ValueError("merge requires at least two source memory_ids.")
            if not (self.patch.successor_memory_id or self.patch.has_substantive_changes()):
                raise ValueError(
                    "merge requires successor_memory_id or a substantive patch for the merged result."
                )

        if self.mutation_type == MemoryMutationType.forget_request:
            if not self.target.has_single_target() and not self.target.has_multi_target():
                raise ValueError("forget_request requires a target memory_id or memory_ids.")
            if self.patch.has_substantive_changes():
                raise ValueError(
                    "forget_request should not directly mutate memory content; it represents a governed request."
                )

        if self.mutation_type in {MemoryMutationType.block, MemoryMutationType.unblock}:
            if self.patch.has_core_content_changes():
                raise ValueError(
                    f"{self.mutation_type.value} should not rewrite core memory content."
                )

        if self.mode == MemoryMutationMode.autonomous and self.actor != MemoryMutationActor.assistant:
            raise ValueError("autonomous mode is reserved for assistant-driven mutation requests.")

        return self


class MemoryMutationRecord(MemoryMutationRequest):
    decision: MemoryMutationDecision
    decision_reason: str = Field(..., min_length=1, max_length=500)

    evaluated_at_utc: datetime = Field(default_factory=utc_now)
    applied_at_utc: Optional[datetime] = None

    resulting_memory_id: Optional[str] = Field(default=None, max_length=128)
    superseded_memory_id: Optional[str] = Field(default=None, max_length=128)

    error_message: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_record(self) -> "MemoryMutationRecord":
        if self.evaluated_at_utc < self.requested_at_utc:
            raise ValueError("evaluated_at_utc cannot be earlier than requested_at_utc.")

        if self.applied_at_utc is not None and self.applied_at_utc < self.requested_at_utc:
            raise ValueError("applied_at_utc cannot be earlier than requested_at_utc.")

        if self.decision == MemoryMutationDecision.applied and self.applied_at_utc is None:
            raise ValueError("applied_at_utc is required when decision is applied.")

        if self.decision in {
            MemoryMutationDecision.blocked,
            MemoryMutationDecision.review_required,
            MemoryMutationDecision.deferred,
        } and self.applied_at_utc is not None:
            raise ValueError(
                f"applied_at_utc should be omitted when decision is {self.decision.value}."
            )

        if self.decision == MemoryMutationDecision.failed and not self.error_message:
            raise ValueError("error_message is required when decision is failed.")

        if self.decision != MemoryMutationDecision.failed and self.error_message:
            raise ValueError("error_message should only be present when decision is failed.")

        return self
