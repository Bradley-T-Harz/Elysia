from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .memory_item import (
    MemoryClass,
    MemoryMutability,
    MemorySensitivity,
    MemoryStatus,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryClassSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_class: MemoryClass
    total_count: int = Field(default=0, ge=0)
    active_count: int = Field(default=0, ge=0)
    archived_count: int = Field(default=0, ge=0)
    provisional_count: int = Field(default=0, ge=0)
    blocked_count: int = Field(default=0, ge=0)
    superseded_count: int = Field(default=0, ge=0)
    pinned_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> "MemoryClassSummary":
        component_total = (
            self.active_count
            + self.archived_count
            + self.provisional_count
            + self.blocked_count
            + self.superseded_count
        )
        if component_total > self.total_count:
            raise ValueError(
                "Class lifecycle counts cannot exceed total_count."
            )

        if self.pinned_count > self.total_count:
            raise ValueError("pinned_count cannot exceed total_count.")

        return self


class MemorySensitivitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sensitivity: MemorySensitivity
    count: int = Field(default=0, ge=0)


class MemoryMutabilitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mutability: MemoryMutability
    count: int = Field(default=0, ge=0)


class MemoryStatusSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: MemoryStatus
    count: int = Field(default=0, ge=0)


class MemoryRecentActivitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recent_created_count: int = Field(default=0, ge=0)
    recent_updated_count: int = Field(default=0, ge=0)
    recent_archived_count: int = Field(default=0, ge=0)

    last_created_at_utc: Optional[datetime] = None
    last_updated_at_utc: Optional[datetime] = None
    last_archived_at_utc: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_recent_activity(self) -> "MemoryRecentActivitySummary":
        if self.recent_created_count == 0 and self.last_created_at_utc is not None:
            raise ValueError(
                "last_created_at_utc should be omitted when recent_created_count is 0."
            )

        if self.recent_updated_count == 0 and self.last_updated_at_utc is not None:
            raise ValueError(
                "last_updated_at_utc should be omitted when recent_updated_count is 0."
            )

        if self.recent_archived_count == 0 and self.last_archived_at_utc is not None:
            raise ValueError(
                "last_archived_at_utc should be omitted when recent_archived_count is 0."
            )

        return self


class MemoryMutationPostureSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    autonomous_updates_enabled: bool = False
    review_required_count: int = Field(default=0, ge=0)
    blocked_mutation_count: int = Field(default=0, ge=0)
    pending_candidate_count: int = Field(default=0, ge=0)

    last_autonomous_write_at_utc: Optional[datetime] = None
    last_review_required_at_utc: Optional[datetime] = None
    last_blocked_mutation_at_utc: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_mutation_posture(self) -> "MemoryMutationPostureSummary":
        if not self.autonomous_updates_enabled and self.last_autonomous_write_at_utc is not None:
            raise ValueError(
                "last_autonomous_write_at_utc should be omitted when autonomous updates are disabled."
            )

        if self.review_required_count == 0 and self.last_review_required_at_utc is not None:
            raise ValueError(
                "last_review_required_at_utc should be omitted when review_required_count is 0."
            )

        if self.blocked_mutation_count == 0 and self.last_blocked_mutation_at_utc is not None:
            raise ValueError(
                "last_blocked_mutation_at_utc should be omitted when blocked_mutation_count is 0."
            )

        return self


class MemorySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_items: int = Field(default=0, ge=0)

    class_summaries: list[MemoryClassSummary] = Field(default_factory=list)
    sensitivity_summaries: list[MemorySensitivitySummary] = Field(default_factory=list)
    mutability_summaries: list[MemoryMutabilitySummary] = Field(default_factory=list)
    status_summaries: list[MemoryStatusSummary] = Field(default_factory=list)

    recent_activity: MemoryRecentActivitySummary = Field(
        default_factory=MemoryRecentActivitySummary
    )
    mutation_posture: MemoryMutationPostureSummary = Field(
        default_factory=MemoryMutationPostureSummary
    )

    generated_at_utc: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_summary(self) -> "MemorySummary":
        class_total = sum(item.total_count for item in self.class_summaries)
        if self.class_summaries and class_total != self.total_items:
            raise ValueError(
                "total_items must equal the sum of class_summaries total_count values."
            )

        sensitivity_total = sum(item.count for item in self.sensitivity_summaries)
        if self.sensitivity_summaries and sensitivity_total != self.total_items:
            raise ValueError(
                "Sensitivity summary counts must add up to total_items."
            )

        mutability_total = sum(item.count for item in self.mutability_summaries)
        if self.mutability_summaries and mutability_total != self.total_items:
            raise ValueError(
                "Mutability summary counts must add up to total_items."
            )

        status_total = sum(item.count for item in self.status_summaries)
        if self.status_summaries and status_total != self.total_items:
            raise ValueError(
                "Status summary counts must add up to total_items."
            )

        return self
