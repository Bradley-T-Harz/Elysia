from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .memory_item import (
    MemoryClass,
    MemoryMutability,
    MemorySensitivity,
    MemorySourceKind,
    MemoryStatus,
)


class MemoryTextSearchFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: Optional[str] = Field(default=None, min_length=1, max_length=240)
    title_only: bool = False
    body_only: bool = False
    case_sensitive: bool = False
    exact_phrase: bool = False

    @model_validator(mode="after")
    def validate_text_filter(self) -> "MemoryTextSearchFilter":
        if self.title_only and self.body_only:
            raise ValueError("title_only and body_only cannot both be true.")
        return self


class MemoryClassFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_classes: list[MemoryClass] = Field(default_factory=list)
    exclude_classes: list[MemoryClass] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_class_filter(self) -> "MemoryClassFilter":
        overlap = set(self.include_classes) & set(self.exclude_classes)
        if overlap:
            raise ValueError(
                f"Class filter cannot include and exclude the same classes: {sorted(value.value for value in overlap)}"
            )
        return self


class MemorySensitivityFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_sensitivities: list[MemorySensitivity] = Field(default_factory=list)
    exclude_sensitivities: list[MemorySensitivity] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_sensitivity_filter(self) -> "MemorySensitivityFilter":
        overlap = set(self.include_sensitivities) & set(self.exclude_sensitivities)
        if overlap:
            raise ValueError(
                f"Sensitivity filter cannot include and exclude the same sensitivities: {sorted(value.value for value in overlap)}"
            )
        return self


class MemoryStatusFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_statuses: list[MemoryStatus] = Field(default_factory=list)
    exclude_statuses: list[MemoryStatus] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_filter(self) -> "MemoryStatusFilter":
        overlap = set(self.include_statuses) & set(self.exclude_statuses)
        if overlap:
            raise ValueError(
                f"Status filter cannot include and exclude the same statuses: {sorted(value.value for value in overlap)}"
            )
        return self


class MemoryMutabilityFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_mutabilities: list[MemoryMutability] = Field(default_factory=list)
    exclude_mutabilities: list[MemoryMutability] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_mutability_filter(self) -> "MemoryMutabilityFilter":
        overlap = set(self.include_mutabilities) & set(self.exclude_mutabilities)
        if overlap:
            raise ValueError(
                f"Mutability filter cannot include and exclude the same mutabilities: {sorted(value.value for value in overlap)}"
            )
        return self


class MemorySourceFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    include_source_kinds: list[MemorySourceKind] = Field(default_factory=list)
    exclude_source_kinds: list[MemorySourceKind] = Field(default_factory=list)
    source_ref: Optional[str] = Field(default=None, max_length=256)
    source_label_query: Optional[str] = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_source_filter(self) -> "MemorySourceFilter":
        overlap = set(self.include_source_kinds) & set(self.exclude_source_kinds)
        if overlap:
            raise ValueError(
                f"Source filter cannot include and exclude the same source kinds: {sorted(value.value for value in overlap)}"
            )
        return self


class MemoryContextFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    conversation_id: Optional[str] = Field(default=None, max_length=128)
    project_id: Optional[str] = Field(default=None, max_length=128)
    request_id: Optional[str] = Field(default=None, max_length=128)
    parent_memory_id: Optional[str] = Field(default=None, max_length=128)


class MemoryDateRangeFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_after_utc: Optional[datetime] = None
    created_before_utc: Optional[datetime] = None
    updated_after_utc: Optional[datetime] = None
    updated_before_utc: Optional[datetime] = None
    captured_after_utc: Optional[datetime] = None
    captured_before_utc: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_date_ranges(self) -> "MemoryDateRangeFilter":
        if (
            self.created_after_utc is not None
            and self.created_before_utc is not None
            and self.created_after_utc > self.created_before_utc
        ):
            raise ValueError("created_after_utc cannot be later than created_before_utc.")

        if (
            self.updated_after_utc is not None
            and self.updated_before_utc is not None
            and self.updated_after_utc > self.updated_before_utc
        ):
            raise ValueError("updated_after_utc cannot be later than updated_before_utc.")

        if (
            self.captured_after_utc is not None
            and self.captured_before_utc is not None
            and self.captured_after_utc > self.captured_before_utc
        ):
            raise ValueError("captured_after_utc cannot be later than captured_before_utc.")

        return self


class MemoryScalarFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_scalar_ranges(self) -> "MemoryScalarFilter":
        if (
            self.min_importance is not None
            and self.max_importance is not None
            and self.min_importance > self.max_importance
        ):
            raise ValueError("min_importance cannot exceed max_importance.")

        if (
            self.min_confidence is not None
            and self.max_confidence is not None
            and self.min_confidence > self.max_confidence
        ):
            raise ValueError("min_confidence cannot exceed max_confidence.")

        return self


class MemoryFlagFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pinned_only: bool = False
    user_declared_only: bool = False
    inferred_only: bool = False
    verified_only: bool = False
    stale_only: bool = False


class MemorySortField(str, Enum):
    created_at_utc = "created_at_utc"
    updated_at_utc = "updated_at_utc"
    importance = "importance"
    confidence = "confidence"
    title = "title"


class MemorySortDirection(str, Enum):
    asc = "asc"
    desc = "desc"


class MemorySortOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sort_by: MemorySortField = MemorySortField.updated_at_utc
    sort_direction: MemorySortDirection = MemorySortDirection.desc


class MemoryPagination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class MemoryRetrievalMode(str, Enum):
    focused = "focused"
    balanced = "balanced"
    broad = "broad"


class MemoryRetrievalPosture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suppressed_classes: list[MemoryClass] = Field(default_factory=list)
    allow_sealed_private: bool = False
    retrieval_mode: MemoryRetrievalMode = MemoryRetrievalMode.balanced


class MemoryMutationReviewFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_required_only: bool = False
    blocked_mutations_only: bool = False
    pending_candidates_only: bool = False
    autonomous_writes_only: bool = False


class MemoryItemsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: MemoryTextSearchFilter = Field(default_factory=MemoryTextSearchFilter)
    classes: MemoryClassFilter = Field(default_factory=MemoryClassFilter)
    sensitivities: MemorySensitivityFilter = Field(default_factory=MemorySensitivityFilter)
    statuses: MemoryStatusFilter = Field(default_factory=MemoryStatusFilter)
    mutabilities: MemoryMutabilityFilter = Field(default_factory=MemoryMutabilityFilter)
    source: MemorySourceFilter = Field(default_factory=MemorySourceFilter)
    context: MemoryContextFilter = Field(default_factory=MemoryContextFilter)
    dates: MemoryDateRangeFilter = Field(default_factory=MemoryDateRangeFilter)
    scalars: MemoryScalarFilter = Field(default_factory=MemoryScalarFilter)
    flags: MemoryFlagFilter = Field(default_factory=MemoryFlagFilter)
    pagination: MemoryPagination = Field(default_factory=MemoryPagination)
    sort: MemorySortOptions = Field(default_factory=MemorySortOptions)
    retrieval: MemoryRetrievalPosture = Field(default_factory=MemoryRetrievalPosture)
    mutation_review: MemoryMutationReviewFilter = Field(default_factory=MemoryMutationReviewFilter)

    @model_validator(mode="after")
    def validate_query(self) -> "MemoryItemsQuery":
        include_classes = set(self.classes.include_classes)
        suppressed_classes = set(self.retrieval.suppressed_classes)

        if include_classes and (include_classes & suppressed_classes):
            raise ValueError(
                "A class cannot be both explicitly included and explicitly suppressed."
            )

        include_sensitivities = set(self.sensitivities.include_sensitivities)
        include_classes = set(self.classes.include_classes)

        requests_sealed_private = MemoryClass.sealed_private in include_classes
        requests_sealed_sensitivity = MemorySensitivity.sealed in include_sensitivities

        if (requests_sealed_private or requests_sealed_sensitivity) and not self.retrieval.allow_sealed_private:
            raise ValueError(
                "sealed_private / sealed memory cannot be queried unless allow_sealed_private is true."
            )

        return self
