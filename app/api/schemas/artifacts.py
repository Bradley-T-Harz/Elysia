"""
Artifact schema models for Elysia local generated outputs.

Sprint 5B introduced saved data-summary artifacts produced from bounded local
data execution. Sprint 5D adds simple local SVG plot-image artifacts generated
from completed bounded data execution summaries.

These schemas do not imply notebook execution, arbitrary Python, shell access,
web access, source-file mutation, broad charting, local path fetching, or memory
promotion.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from .common import (
    ApprovalState,
    ElysiaSchemaModel,
    LocalityState,
)
from .execution import ExecutionToolKind


class ArtifactKind(str, Enum):
    """Known artifact kinds."""

    DATA_SUMMARY = "data_summary"
    TABLE_PREVIEW = "table_preview"
    PLOT_IMAGE = "plot_image"
    TEXT_REPORT = "text_report"
    TRANSCRIPT = "transcript"
    SPEECH_AUDIO = "speech_audio"
    GENERATED_IMAGE = "generated_image"
    GENERATED_VIDEO = "generated_video"


class ArtifactMemoryPosture(str, Enum):
    """Memory posture for generated artifacts."""

    NOT_MEMORY = "not_memory"
    MEMORY_CANDIDATE = "memory_candidate"
    PROMOTED_MEMORY = "promoted_memory"
    BLOCKED_FROM_MEMORY = "blocked_from_memory"
    UNKNOWN = "unknown"


class ArtifactSourceRef(ElysiaSchemaModel):
    """Source provenance for a generated artifact."""

    source_kind: str = Field(
        default="attached_file",
        description="Source kind that produced this artifact.",
    )
    source_file_id: str | None = Field(
        default=None,
        description="Attached file id when available.",
    )
    source_file_name: str | None = Field(
        default=None,
        description="Source file name safe for UI display.",
    )
    source_file_kind: str | None = Field(
        default=None,
        description="Source file kind such as csv.",
    )
    source_path: str | None = Field(
        default=None,
        description=(
            "Internal local source path. This belongs in the saved artifact "
            "record, not necessarily in compact UI summaries."
        ),
    )


class ArtifactBoundaryTruth(ElysiaSchemaModel):
    """Boundary facts attached to a generated artifact."""

    locality: LocalityState = Field(
        default=LocalityState.LOCAL,
        description="Artifact locality. Sprint 5B artifacts stay local.",
    )
    approval_state: ApprovalState = Field(
        default=ApprovalState.NOT_NEEDED,
        description="Approval posture for creating this artifact.",
    )
    memory_posture: ArtifactMemoryPosture = Field(
        default=ArtifactMemoryPosture.NOT_MEMORY,
        description="Artifacts are not memory by default.",
    )
    artifact_saved_locally: bool = Field(
        default=True,
        description="Whether the artifact record was saved locally.",
    )
    source_file_mutated: bool = Field(
        default=False,
        description="Whether the source file was changed. Must stay false.",
    )
    network_access_used: bool = Field(
        default=False,
        description="Whether network access was used. Must stay false.",
    )
    memory_promoted: bool = Field(
        default=False,
        description="Whether artifact/source content was promoted into memory.",
    )
    arbitrary_python_used: bool = Field(
        default=False,
        description="Whether arbitrary Python execution was used. Must stay false.",
    )
    shell_used: bool = Field(
        default=False,
        description="Whether shell execution was used. Must stay false.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Compact human-readable boundary notes.",
    )


class DataSummaryArtifactPayload(ElysiaSchemaModel):
    """Compact payload for a bounded local data-summary artifact."""

    row_count: int = Field(
        default=0,
        ge=0,
        description="Number of data rows summarized.",
    )
    column_count: int = Field(
        default=0,
        ge=0,
        description="Number of columns summarized.",
    )
    columns: list[str] = Field(
        default_factory=list,
        description="Column names in source order.",
    )
    numeric_columns: list[str] = Field(
        default_factory=list,
        description="Columns classified as numeric.",
    )
    text_columns: list[str] = Field(
        default_factory=list,
        description="Columns classified as text/categorical.",
    )
    missing_values_by_column: dict[str, int] = Field(
        default_factory=dict,
        description="Missing value counts by column.",
    )
    numeric_stats: dict[str, Any] = Field(
        default_factory=dict,
        description="Basic numeric stats by column.",
    )
    preview_rows: list[dict[str, str]] = Field(
        default_factory=list,
        description="Small preview of rows, never the full dataset.",
    )
    boundary_note: str = Field(
        default=(
            "Saved from bounded local data execution. This is not arbitrary "
            "Python, shell execution, web access, plotting, notebook behavior, "
            "source-file mutation, folder scanning, or memory promotion."
        ),
        description="Compact boundary note for the artifact payload.",
    )


class PlotArtifactPayload(ElysiaSchemaModel):
    """Compact payload for a simple local SVG plot artifact."""

    plot_kind: str = Field(
        default="numeric_summary_bar_svg",
        description="Plot kind produced by the bounded plot artifact builder.",
    )
    svg_text: str = Field(
        default="",
        description="Inline SVG text generated locally for immediate safe preview.",
    )
    svg_mime_type: str = Field(
        default="image/svg+xml",
        description="MIME type for the generated SVG preview.",
    )
    width: int = Field(
        default=720,
        ge=1,
        description="SVG width in pixels.",
    )
    height: int = Field(
        default=420,
        ge=1,
        description="SVG height in pixels.",
    )
    metric: str = Field(
        default="mean",
        description="Numeric metric plotted, such as mean, min, max, count, or missing.",
    )
    plotted_columns: list[str] = Field(
        default_factory=list,
        description="Numeric columns included in the v0 plot.",
    )
    row_count: int = Field(
        default=0,
        ge=0,
        description="Rows summarized in the source data execution result.",
    )
    column_count: int = Field(
        default=0,
        ge=0,
        description="Columns summarized in the source data execution result.",
    )
    boundary_note: str = Field(
        default=(
            "Saved from a completed bounded local data execution summary. This "
            "is a simple local SVG plot artifact, not notebook execution, "
            "arbitrary Python, shell execution, web access, source-file "
            "mutation, local path fetching, or memory promotion."
        ),
        description="Compact boundary note for the plot artifact payload.",
    )


class GeneratedMediaArtifactPayload(ElysiaSchemaModel):
    """Compact receipt for a generated speech/image/video artifact."""

    model_id: str
    worker_key: str
    mime_type: str
    output_path: str = Field(description="Internal local output path; never included in compact UI summaries.")
    output_sha256: str
    output_bytes: int = Field(default=0, ge=0)
    sidecar_path: str | None = Field(default=None, description="Internal local provenance-sidecar path.")
    sidecar_sha256: str | None = None
    synthetic_media: bool = False
    machine_generated_transcript: bool = False
    duration_seconds: float | None = Field(default=None, ge=0)
    language: str | None = None
    segment_count: int | None = Field(default=None, ge=0)
    sample_rate_hz: int | None = Field(default=None, ge=1)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    prompt_or_text_hash: str | None = None
    prompt_or_text_length: int | None = Field(default=None, ge=0)
    provenance_state: str = "local_unverified"
    boundary_note: str = "Generated locally by a governed worker; raw content is excluded from central trace."


class ArtifactSummary(ElysiaSchemaModel):
    """
    Compact UI-safe artifact summary.

    This summary intentionally avoids exposing the raw local source path.
    """

    artifact_id: str = Field(
        ...,
        min_length=1,
        description="Stable artifact identifier.",
    )
    kind: ArtifactKind = Field(
        ...,
        description="Artifact kind.",
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Short artifact title.",
    )
    summary: str = Field(
        default="",
        description="Compact artifact summary.",
    )
    created_at_utc: str = Field(
        ...,
        min_length=1,
        description="Creation timestamp in UTC.",
    )
    request_id: str | None = Field(
        default=None,
        description="Request id that produced this artifact when available.",
    )
    conversation_id: str | None = Field(
        default=None,
        description="Conversation id associated with this artifact when available.",
    )
    project_id: str | None = Field(
        default=None,
        description="Project id associated with this artifact when available.",
    )
    locality: LocalityState = Field(
        default=LocalityState.LOCAL,
        description="Artifact locality.",
    )
    memory_posture: ArtifactMemoryPosture = Field(
        default=ArtifactMemoryPosture.NOT_MEMORY,
        description="Artifact memory posture.",
    )
    producer_tool_kind: str = Field(
        default=ExecutionToolKind.DATA_EXECUTOR.value,
        description="Tool kind that produced the artifact.",
    )
    producer_operation: str = Field(
        default="summarize_csv",
        description="Operation that produced the artifact.",
    )
    source_file_id: str | None = Field(
        default=None,
        description="Source attached file id when available.",
    )
    source_file_name: str | None = Field(
        default=None,
        description="Source file name safe for display.",
    )
    source_file_kind: str | None = Field(
        default=None,
        description="Source file kind such as csv.",
    )
    row_count: int | None = Field(
        default=None,
        ge=0,
        description="Rows summarized when this is a data artifact.",
    )
    column_count: int | None = Field(
        default=None,
        ge=0,
        description="Columns summarized when this is a data artifact.",
    )
    plot_kind: str | None = Field(
        default=None,
        description="Plot kind when this summary represents a plot artifact.",
    )
    svg_text: str | None = Field(
        default=None,
        description=(
            "Optional compatibility field. Compact list summaries should not "
            "carry full inline SVG text; plot SVG belongs in "
            "ArtifactDetail.safe_preview."
        ),
    )
    svg_mime_type: str | None = Field(
        default=None,
        description="MIME type for inline plot preview when surfaced.",
    )
    width: int | None = Field(
        default=None,
        ge=1,
        description="SVG width when this is a plot artifact.",
    )
    height: int | None = Field(
        default=None,
        ge=1,
        description="SVG height when this is a plot artifact.",
    )
    metric: str | None = Field(
        default=None,
        description="Numeric metric plotted when this is a plot artifact.",
    )
    plotted_columns: list[str] = Field(
        default_factory=list,
        description="Columns plotted when this is a plot artifact.",
    )
    model_id: str | None = None
    mime_type: str | None = None
    output_sha256: str | None = None
    output_bytes: int | None = Field(default=None, ge=0)
    synthetic_media: bool = False
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal artifact warnings.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Artifact errors when relevant.",
    )
    memory_promotion: bool = Field(
        default=False,
        description="Whether artifact content was promoted into memory. Defaults false.",
    )
    private_context_sent: bool = Field(
        default=False,
        description="Whether private context was sent outward while producing this artifact. Defaults false.",
    )
    preview_available: bool = Field(
        default=False,
        description="Whether a bounded local preview is available.",
    )
    detail_available: bool = Field(
        default=True,
        description="Whether a safe artifact detail endpoint can describe this artifact.",
    )


class ArtifactDetail(ElysiaSchemaModel):
    """Safe detail payload for one local artifact."""

    summary: ArtifactSummary = Field(
        ...,
        description="Compact artifact summary without raw local paths.",
    )
    detail_kind: str = Field(
        default="artifact_detail",
        description="Type of safe detail payload.",
    )
    safe_preview: dict = Field(
        default_factory=dict,
        description="Bounded type-specific preview safe for UI display.",
    )
    provenance: list[dict] = Field(
        default_factory=list,
        description="Compact source/provenance records without raw paths.",
    )
    boundary_truth: dict = Field(
        default_factory=dict,
        description="Compact boundary truth for artifact production and display.",
    )


class ArtifactListResponse(ElysiaSchemaModel):
    """Response data for local artifact list routes."""

    artifacts: list[ArtifactSummary] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1)
    filters: dict = Field(default_factory=dict)


class ArtifactRecord(ElysiaSchemaModel):
    """Full local artifact record saved to disk."""

    artifact_id: str = Field(
        ...,
        min_length=1,
        description="Stable artifact identifier.",
    )
    owner_user_id: str | None = Field(
        default=None,
        description="Authenticated local account that owns this artifact; null only for legacy/test records.",
    )
    kind: ArtifactKind = Field(
        ...,
        description="Artifact kind.",
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Artifact title.",
    )
    summary: str = Field(
        default="",
        description="Compact artifact summary.",
    )
    created_at_utc: str = Field(
        ...,
        min_length=1,
        description="Creation timestamp in UTC.",
    )
    request_id: str | None = Field(
        default=None,
        description="Request id that produced the artifact.",
    )
    conversation_id: str | None = Field(
        default=None,
        description="Conversation id associated with the artifact.",
    )
    project_id: str | None = Field(
        default=None,
        description="Project id associated with the artifact.",
    )
    artifact_path: str = Field(
        ...,
        min_length=1,
        description="Local path where this artifact record is saved.",
    )
    object_id: str | None = Field(
        default=None,
        description="Stable governed object identifier for immutable artifact bytes.",
    )
    object_authority: str = Field(
        default="artifact_metadata_only",
        description="Whether immutable bytes are owned by the shared XDG object authority.",
    )
    producer_tool_kind: str = Field(
        default=ExecutionToolKind.DATA_EXECUTOR.value,
        description="Tool kind that produced the artifact.",
    )
    producer_operation: str = Field(
        default="summarize_csv",
        description="Operation that produced the artifact.",
    )
    source: ArtifactSourceRef = Field(
        default_factory=ArtifactSourceRef,
        description="Source provenance for this artifact.",
    )
    boundary: ArtifactBoundaryTruth = Field(
        default_factory=ArtifactBoundaryTruth,
        description="Boundary truth for this artifact.",
    )
    payload: DataSummaryArtifactPayload | PlotArtifactPayload | GeneratedMediaArtifactPayload = Field(
        default_factory=DataSummaryArtifactPayload,
        description="Artifact payload.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal artifact warnings.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Artifact errors when relevant.",
    )


__all__ = (
    "ArtifactBoundaryTruth",
    "ArtifactKind",
    "ArtifactMemoryPosture",
    "ArtifactRecord",
    "ArtifactSourceRef",
    "ArtifactDetail",
    "ArtifactListResponse",
    "ArtifactSummary",
    "DataSummaryArtifactPayload",
    "GeneratedMediaArtifactPayload",
    "PlotArtifactPayload",
)
