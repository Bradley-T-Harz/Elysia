from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryClass(str, Enum):
    working = "working"
    conversation = "conversation"
    project = "project"
    research = "research"
    operational = "operational"
    preference = "preference"
    sealed_private = "sealed_private"
    audit = "audit"


class MemorySensitivity(str, Enum):
    public = "public"
    internal = "internal"
    private = "private"
    sealed = "sealed"


class MemoryMutability(str, Enum):
    live_editable = "live_editable"
    append_only = "append_only"
    review_required = "review_required"
    immutable = "immutable"
    not_yet_live = "not_yet_live"


class MemoryStatus(str, Enum):
    active = "active"
    archived = "archived"
    superseded = "superseded"
    provisional = "provisional"
    blocked = "blocked"


class MemorySourceKind(str, Enum):
    user_message = "user_message"
    assistant_inference = "assistant_inference"
    system_event = "system_event"
    project_update = "project_update"
    research_source = "research_source"
    imported_file = "imported_file"
    runtime_trace = "runtime_trace"
    manual_entry = "manual_entry"


class MemoryActorKind(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    service = "service"


class MemorySource(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_kind: MemorySourceKind
    source_ref: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Stable reference to the originating object, file, thread, or request.",
    )
    source_label: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Human-readable source label for UI display.",
    )
    captured_at_utc: datetime = Field(
        default_factory=utc_now,
        description="When the source was captured into memory consideration.",
    )


class MemoryContextLinks(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    conversation_id: Optional[str] = Field(default=None, max_length=128)
    project_id: Optional[str] = Field(default=None, max_length=128)
    request_id: Optional[str] = Field(default=None, max_length=128)
    parent_memory_id: Optional[str] = Field(default=None, max_length=128)


class MemoryRevisionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    revision: int = Field(
        default=1,
        ge=1,
        description="Monotonic revision counter for the memory item.",
    )
    supersedes_memory_id: Optional[str] = Field(default=None, max_length=128)
    superseded_by_memory_id: Optional[str] = Field(default=None, max_length=128)
    last_mutation_reason: Optional[str] = Field(default=None, max_length=240)


class MemoryFlags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pinned: bool = False
    user_declared: bool = False
    inferred: bool = False
    verified: bool = False
    stale: bool = False


class MemoryItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        use_enum_values=False,
    )

    memory_id: str = Field(
        default_factory=lambda: f"mem_{uuid4().hex}",
        min_length=8,
        max_length=128,
        description="Stable unique identifier for this memory item.",
    )
    memory_class: MemoryClass
    title: str = Field(
        ...,
        min_length=1,
        max_length=160,
        description="Short human-readable label for cards, lists, and summaries.",
    )
    body: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="Stored memory content or summary body.",
    )
    source: MemorySource
    context_links: MemoryContextLinks = Field(default_factory=MemoryContextLinks)
    why_stored: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Explicit rationale for why this memory was stored.",
    )
    sensitivity: MemorySensitivity = MemorySensitivity.internal
    mutability: MemoryMutability = MemoryMutability.not_yet_live
    status: MemoryStatus = MemoryStatus.active

    created_at_utc: datetime = Field(default_factory=utc_now)
    updated_at_utc: datetime = Field(default_factory=utc_now)

    created_by: MemoryActorKind = MemoryActorKind.system
    updated_by: MemoryActorKind = MemoryActorKind.system

    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Practical significance or salience, not emotional dominance.",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score, especially useful for research and inferred memory.",
    )

    revision_info: MemoryRevisionInfo = Field(default_factory=MemoryRevisionInfo)
    flags: MemoryFlags = Field(default_factory=MemoryFlags)

    @field_validator("memory_id")
    @classmethod
    def validate_memory_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("memory_id cannot be empty.")
        return value

    @field_validator("title", "body", "why_stored")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("required text fields cannot be empty or whitespace.")
        return value

    @model_validator(mode="after")
    def validate_memory_item(self) -> "MemoryItem":
        if self.updated_at_utc < self.created_at_utc:
            raise ValueError("updated_at_utc cannot be earlier than created_at_utc.")

        if (
            self.memory_class == MemoryClass.sealed_private
            and self.mutability == MemoryMutability.live_editable
        ):
            raise ValueError(
                "sealed_private memory cannot default to live_editable mutability."
            )

        if (
            self.memory_class == MemoryClass.audit
            and self.mutability
            not in {
                MemoryMutability.append_only,
                MemoryMutability.immutable,
                MemoryMutability.review_required,
            }
        ):
            raise ValueError(
                "audit memory must be append_only, immutable, or review_required."
            )

        if self.sensitivity == MemorySensitivity.sealed and self.memory_class != MemoryClass.sealed_private:
            raise ValueError(
                "sealed sensitivity is reserved for sealed_private memory items."
            )

        if self.status == MemoryStatus.superseded:
            if not (
                self.revision_info.superseded_by_memory_id
                or self.revision_info.last_mutation_reason
            ):
                raise ValueError(
                    "superseded memory should reference a successor or explain the mutation reason."
                )

        if self.status == MemoryStatus.provisional:
            if self.memory_class == MemoryClass.research and self.confidence is None:
                raise ValueError(
                    "provisional research memory should include a confidence score."
                )

        if (
            self.flags.user_declared
            and self.created_by not in {MemoryActorKind.user, MemoryActorKind.service}
        ):
            raise ValueError(
                "user_declared memory should be created by the user or a service acting on explicit user input."
            )

        if self.flags.verified and self.status == MemoryStatus.blocked:
            raise ValueError("blocked memory cannot simultaneously be marked verified.")

        return self
