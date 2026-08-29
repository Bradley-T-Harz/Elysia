"""Referential adapters from Memory links to existing domain authorities.

These adapters validate stable identifiers without copying authoritative
conversation, project, request, or artifact content into the Memory database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class MemorySourceReferenceError(ValueError):
    """A requested cross-authority reference is dangling or inconsistent."""


class SourceAuthorityAdapter(Protocol):
    target_type: str

    def validate(self, target_id: str, *, context_id: str | None = None) -> None: ...


@dataclass(frozen=True)
class ConversationSourceAdapter:
    target_type: str = "conversation"

    def validate(self, target_id: str, *, context_id: str | None = None) -> None:
        from app.api.conversation_service import get_conversation_metadata

        try:
            get_conversation_metadata(target_id)
        except Exception as exc:
            raise MemorySourceReferenceError("The linked conversation does not exist.") from exc


@dataclass(frozen=True)
class MessageSourceAdapter:
    target_type: str = "message"

    def validate(self, target_id: str, *, context_id: str | None = None) -> None:
        from app.api.conversation_service import get_conversation_thread

        if not context_id:
            raise MemorySourceReferenceError(
                "A linked message requires its stable conversation identifier."
            )
        try:
            thread = get_conversation_thread(context_id)
        except Exception as exc:
            raise MemorySourceReferenceError("The linked conversation does not exist.") from exc
        if not any(str(message.get("message_id")) == target_id for message in thread["messages"]):
            raise MemorySourceReferenceError(
                "The linked message does not belong to the linked conversation."
            )


@dataclass(frozen=True)
class ProjectSourceAdapter:
    target_type: str = "project"

    def validate(self, target_id: str, *, context_id: str | None = None) -> None:
        from app.api.project_service import get_project_metadata

        try:
            get_project_metadata(target_id)
        except Exception as exc:
            raise MemorySourceReferenceError("The linked project does not exist.") from exc


@dataclass(frozen=True)
class RequestSourceAdapter:
    target_type: str = "request"

    def validate(self, target_id: str, *, context_id: str | None = None) -> None:
        from app.api.request_trace_service import get_request_trace_record

        if get_request_trace_record(target_id) is not None:
            return
        # Live request traces are deliberately bounded in-memory. Part 2C's
        # durable, content-free context receipt is the restart-safe authority
        # for a request link once its live trace has aged out.
        from app.cognition.evidence_repository import EvidenceRepository
        from app.ownership import current_user_id

        owner = current_user_id()
        if owner is not None and EvidenceRepository().get_context_receipt(owner, target_id):
            return
        raise MemorySourceReferenceError("The linked request trace or durable context receipt does not exist.")


@dataclass(frozen=True)
class ArtifactSourceAdapter:
    target_type: str = "artifact"

    def validate(self, target_id: str, *, context_id: str | None = None) -> None:
        from app.api.artifact_service import get_artifact_detail

        if get_artifact_detail(target_id) is None:
            raise MemorySourceReferenceError("The linked artifact does not exist.")


@dataclass(frozen=True)
class EvidenceSourceAdapter:
    target_type: str = "evidence"

    def validate(self, target_id: str, *, context_id: str | None = None) -> None:
        from app.cognition.evidence_repository import EvidenceRepository
        from app.ownership import current_user_id

        owner = current_user_id()
        if owner is None:
            raise MemorySourceReferenceError("Evidence linkage requires an authenticated account.")
        try:
            EvidenceRepository().get_evidence(owner, target_id)
        except Exception as exc:
            raise MemorySourceReferenceError("The linked evidence does not exist.") from exc


ADAPTERS: dict[str, SourceAuthorityAdapter] = {
    adapter.target_type: adapter
    for adapter in (
        ConversationSourceAdapter(),
        MessageSourceAdapter(),
        ProjectSourceAdapter(),
        RequestSourceAdapter(),
        ArtifactSourceAdapter(),
        EvidenceSourceAdapter(),
    )
}


def validate_source_reference(
    target_type: str,
    target_id: str,
    *,
    context_id: str | None = None,
) -> None:
    """Validate a reference when its owning domain offers a live lookup."""

    adapter = ADAPTERS.get(target_type)
    if adapter is not None:
        adapter.validate(target_id, context_id=context_id)


__all__ = (
    "ADAPTERS",
    "MemorySourceReferenceError",
    "SourceAuthorityAdapter",
    "validate_source_reference",
)
