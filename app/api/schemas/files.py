"""
File-ingestion schema models for the Elysia local API bridge.

This module defines the Python-side schema vocabulary for future local-first
file attachment, processing, and context-summary surfaces.

It should stay narrow:
- file ingestion enums
- attached-file metadata models
- processing-state models
- file context summary models

It should not contain:
- route logic
- service logic
- parser logic
- indexing logic
- memory promotion logic
- filesystem side effects
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import ElysiaSchemaModel


class FileProcessingState(str, Enum):
    """
    Canonical file-processing states for local file ingestion.

    Meanings:
    - attached: user selected/attached a file, but ingest has not started
    - queued: accepted for processing but not currently processing
    - detecting_type: identifying MIME/file kind
    - parsing: extracting usable text/metadata
    - indexed: chunks/index records exist
    - ready: usable as attached context
    - failed: processing failed
    - blocked: policy/trust rules refused processing
    """

    ATTACHED = "attached"
    QUEUED = "queued"
    DETECTING_TYPE = "detecting_type"
    PARSING = "parsing"
    INDEXED = "indexed"
    READY = "ready"
    FAILED = "failed"
    BLOCKED = "blocked"


class FileKind(str, Enum):
    """
    Compact file-kind labels for local file ingestion.

    Naming a kind here does not mean parsing support is live. It only means the
    bridge can truthfully represent that kind when encountered.
    """

    TEXT = "text"
    MARKDOWN = "markdown"
    DOCX = "docx"
    PDF = "pdf"
    CSV = "csv"
    XLSX = "xlsx"
    JSON = "json"
    HTML = "html"
    IMAGE = "image"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


class FileTrustZone(str, Enum):
    """
    Trust-zone posture for an attached or ingested file.
    """

    USER_SELECTED = "user_selected"
    PROJECT_LOCAL = "project_local"
    SANDBOXED = "sandboxed"
    EXTERNAL_IMPORT = "external_import"
    SEALED = "sealed"
    UNKNOWN = "unknown"


class FileMemoryPosture(str, Enum):
    """
    Memory relationship for an attached file.

    Default posture must remain not_memory. Attached files are not memory unless
    a future explicit promotion policy stores them.
    """

    NOT_MEMORY = "not_memory"
    MEMORY_CANDIDATE = "memory_candidate"
    PROMOTED_MEMORY = "promoted_memory"
    BLOCKED_FROM_MEMORY = "blocked_from_memory"
    UNKNOWN = "unknown"


class AttachedFile(ElysiaSchemaModel):
    """
    Compact metadata for one user-attached file.

    This model intentionally separates file attachment from file readiness and
    memory promotion. A file can be attached without being usable as context, and
    usable as context without becoming memory.
    """

    file_id: str = Field(
        ...,
        min_length=1,
        description="Stable local identifier for the attached file.",
    )
    display_name: str = Field(
        ...,
        min_length=1,
        description="Human-facing file name for UI display.",
    )
    original_name: str | None = Field(
        default=None,
        description="Original file name as supplied by the user or local picker.",
    )
    file_kind: FileKind = Field(
        default=FileKind.UNKNOWN,
        description="Compact detected or declared file kind.",
    )
    mime_type: str | None = Field(
        default=None,
        description="Detected or declared MIME type when known.",
    )
    size_bytes: int | None = Field(
        default=None,
        ge=0,
        description="File size in bytes when known.",
    )
    sha256: str | None = Field(
        default=None,
        description="Local file content hash when computed.",
    )
    trust_zone: FileTrustZone = Field(
        default=FileTrustZone.USER_SELECTED,
        description="Trust-zone posture for this file.",
    )
    processing_state: FileProcessingState = Field(
        default=FileProcessingState.ATTACHED,
        description="Current processing state for this file.",
    )
    memory_posture: FileMemoryPosture = Field(
        default=FileMemoryPosture.NOT_MEMORY,
        description="Whether this file is memory, a memory candidate, or not memory.",
    )
    attached_at_utc: str | None = Field(
        default=None,
        description="UTC timestamp for when the file was attached.",
    )
    source_conversation_id: str | None = Field(
        default=None,
        description="Conversation id associated with this attachment when known.",
    )
    source_project_id: str | None = Field(
        default=None,
        description="Project id associated with this attachment when known.",
    )
    user_selected: bool = Field(
        default=True,
        description="Whether the file was explicitly selected by the user.",
    )
    can_use_as_context: bool = Field(
        default=False,
        description="Whether parsed file content is currently usable as context.",
    )
    can_promote_to_memory: bool = Field(
        default=False,
        description="Whether current policy allows this file to be promoted into memory.",
    )
    parser_used: str | None = Field(
        default=None,
        description="Local parser or registration path used for this file, when known.",
    )
    chunks_created_count: int = Field(
        default=0,
        ge=0,
        description="Number of local chunks created for context use.",
    )
    chunks_used_count: int = Field(
        default=0,
        ge=0,
        description="Number of local chunks selected for this request or context summary.",
    )
    memory_promotion_allowed: bool = Field(
        default=False,
        description="Whether this attached file may be promoted into memory in the current path.",
    )
    outward_sharing_allowed: bool = Field(
        default=False,
        description="Whether this attached file content may be shared outward in the current path.",
    )
    blocked_reason: str | None = Field(
        default=None,
        description="Compact blocked reason when file ingest is refused.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Compact UI-safe notes about this file.",
    )


class FileProcessingStep(ElysiaSchemaModel):
    """
    Compact trace step for file processing progress.
    """

    step_name: str = Field(
        ...,
        min_length=1,
        description="Machine-readable processing step name.",
    )
    state: FileProcessingState = Field(
        ...,
        description="State associated with this processing step.",
    )
    started_at_utc: str | None = Field(
        default=None,
        description="UTC timestamp when this step started.",
    )
    completed_at_utc: str | None = Field(
        default=None,
        description="UTC timestamp when this step completed.",
    )
    message: str | None = Field(
        default=None,
        description="Compact UI-safe processing message.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Compact warning strings from this step.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Compact error strings from this step.",
    )


class FileContextChunkSummary(ElysiaSchemaModel):
    """
    Safe compact summary for one file-context chunk.

    This should not become a raw full-file body dump.
    """

    chunk_id: str = Field(
        ...,
        min_length=1,
        description="Stable local identifier for this chunk.",
    )
    file_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the file this chunk belongs to.",
    )
    chunk_index: int = Field(
        ...,
        ge=0,
        description="Zero-based chunk index inside the file.",
    )
    heading: str | None = Field(
        default=None,
        description="Nearby heading or section label when available.",
    )
    char_start: int | None = Field(
        default=None,
        ge=0,
        description="Start character offset when known.",
    )
    char_end: int | None = Field(
        default=None,
        ge=0,
        description="End character offset when known.",
    )
    token_estimate: int | None = Field(
        default=None,
        ge=0,
        description="Estimated token count for this chunk when known.",
    )
    excerpt: str | None = Field(
        default=None,
        description="Small UI-safe excerpt or preview when appropriate.",
    )


class FileContextSummary(ElysiaSchemaModel):
    """
    Compact context summary for one attached file.

    This is suitable for future right-drawer, request-trace, and files-in-use
    surfaces without implying memory promotion.
    """

    file_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the summarized file.",
    )
    display_name: str = Field(
        ...,
        min_length=1,
        description="Human-facing file name for UI display.",
    )
    file_kind: FileKind = Field(
        default=FileKind.UNKNOWN,
        description="Compact detected or declared file kind.",
    )
    processing_state: FileProcessingState = Field(
        default=FileProcessingState.ATTACHED,
        description="Current processing state for this file context.",
    )
    memory_posture: FileMemoryPosture = Field(
        default=FileMemoryPosture.NOT_MEMORY,
        description="Memory relationship for this file context.",
    )
    usable_as_context: bool = Field(
        default=False,
        description="Whether this file can currently be used as context.",
    )
    chunk_count: int = Field(
        default=0,
        ge=0,
        description="Total number of known chunks for this file.",
    )
    selected_chunk_count: int = Field(
        default=0,
        ge=0,
        description="Number of chunks selected for the current context window.",
    )
    chunks: list[FileContextChunkSummary] = Field(
        default_factory=list,
        description="Compact summaries of selected or relevant chunks.",
    )
    summary_note: str | None = Field(
        default=None,
        description="Compact UI-safe file-context note.",
    )
    parser_used: str | None = Field(
        default=None,
        description="Local parser or registration path used for this file, when known.",
    )
    memory_promotion_allowed: bool = Field(
        default=False,
        description="Whether this context summary can promote file contents into memory.",
    )
    outward_sharing_allowed: bool = Field(
        default=False,
        description="Whether this context summary can share file contents outward.",
    )
    retrieval_method: str | None = Field(
        default=None,
        description="Bounded local retrieval method used for chunk selection.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Compact warnings for this context summary.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Compact errors for this context summary.",
    )


class FileIngestResult(ElysiaSchemaModel):
    """
    Result shape for a future local file-ingest attempt.
    """

    file_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the file being ingested.",
    )
    processing_state: FileProcessingState = Field(
        default=FileProcessingState.ATTACHED,
        description="Final or current processing state for this ingest result.",
    )
    accepted: bool = Field(
        default=False,
        description="Whether the file was accepted into the ingest path.",
    )
    blocked: bool = Field(
        default=False,
        description="Whether ingest was blocked by policy or trust posture.",
    )
    ready: bool = Field(
        default=False,
        description="Whether the file is ready for governed context use.",
    )
    file: AttachedFile | None = Field(
        default=None,
        description="Attached-file metadata when available.",
    )
    steps: list[FileProcessingStep] = Field(
        default_factory=list,
        description="Compact processing steps for this ingest attempt.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Compact warning strings from the ingest attempt.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Compact error strings from the ingest attempt.",
    )
    context_summary: FileContextSummary | None = Field(
        default=None,
        description="Context summary when parsing/indexing produced usable context.",
    )


__all__ = (
    "AttachedFile",
    "FileContextChunkSummary",
    "FileContextSummary",
    "FileIngestResult",
    "FileKind",
    "FileMemoryPosture",
    "FileProcessingState",
    "FileProcessingStep",
    "FileTrustZone",
)
