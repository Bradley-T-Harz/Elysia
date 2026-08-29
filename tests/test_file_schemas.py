from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.schemas.files import (
    AttachedFile,
    FileContextChunkSummary,
    FileContextSummary,
    FileIngestResult,
    FileKind,
    FileMemoryPosture,
    FileProcessingState,
    FileProcessingStep,
    FileTrustZone,
)


def test_default_attached_file_is_safe_and_not_memory():
    attached_file = AttachedFile(
        file_id="file_test_001",
        display_name="field-notes.txt",
        original_name="field-notes.txt",
        file_kind=FileKind.TEXT,
    )

    assert attached_file.processing_state == FileProcessingState.ATTACHED
    assert attached_file.trust_zone == FileTrustZone.USER_SELECTED
    assert attached_file.memory_posture == FileMemoryPosture.NOT_MEMORY
    assert attached_file.user_selected is True
    assert attached_file.can_use_as_context is False
    assert attached_file.can_promote_to_memory is False
    assert attached_file.notes == []

    payload = attached_file.to_payload()

    assert payload["processing_state"] == "attached"
    assert payload["trust_zone"] == "user_selected"
    assert payload["memory_posture"] == "not_memory"
    assert payload["user_selected"] is True
    assert payload["can_use_as_context"] is False
    assert payload["can_promote_to_memory"] is False


def test_ready_attached_file_serializes_context_truth_without_memory_promotion():
    attached_file = AttachedFile(
        file_id="file_test_ready_001",
        display_name="source.md",
        original_name="source.md",
        file_kind=FileKind.MARKDOWN,
        mime_type="text/markdown",
        size_bytes=128,
        sha256="abc123",
        processing_state=FileProcessingState.READY,
        memory_posture=FileMemoryPosture.NOT_MEMORY,
        can_use_as_context=True,
    )

    payload = attached_file.to_payload()

    assert payload["file_kind"] == "markdown"
    assert payload["processing_state"] == "ready"
    assert payload["memory_posture"] == "not_memory"
    assert payload["can_use_as_context"] is True
    assert payload["can_promote_to_memory"] is False


def test_blocked_ingest_result_carries_errors_and_does_not_claim_ready():
    result = FileIngestResult(
        file_id="file_blocked_001",
        processing_state=FileProcessingState.BLOCKED,
        accepted=False,
        blocked=True,
        ready=False,
        errors=["File trust zone blocked."],
    )

    payload = result.to_payload()

    assert payload["file_id"] == "file_blocked_001"
    assert payload["processing_state"] == "blocked"
    assert payload["accepted"] is False
    assert payload["blocked"] is True
    assert payload["ready"] is False
    assert payload["errors"] == ["File trust zone blocked."]


def test_context_summary_can_be_usable_without_becoming_memory():
    chunk = FileContextChunkSummary(
        chunk_id="chunk_001",
        file_id="file_context_001",
        chunk_index=0,
        heading="Observations",
        char_start=0,
        char_end=120,
        token_estimate=32,
        excerpt="Sample field observation excerpt.",
    )

    summary = FileContextSummary(
        file_id="file_context_001",
        display_name="field-notes.txt",
        file_kind=FileKind.TEXT,
        processing_state=FileProcessingState.READY,
        memory_posture=FileMemoryPosture.NOT_MEMORY,
        usable_as_context=True,
        chunk_count=2,
        selected_chunk_count=1,
        chunks=[chunk],
        summary_note="One selected chunk is available for governed context use.",
    )

    payload = summary.to_payload()

    assert payload["memory_posture"] == "not_memory"
    assert payload["usable_as_context"] is True
    assert payload["chunk_count"] == 2
    assert payload["selected_chunk_count"] == 1
    assert payload["chunks"][0]["chunk_id"] == "chunk_001"
    assert payload["chunks"][0]["excerpt"] == "Sample field observation excerpt."


def test_processing_step_serializes_warnings_and_errors():
    step = FileProcessingStep(
        step_name="parsing",
        state=FileProcessingState.FAILED,
        started_at_utc="2026-05-04T09:00:00Z",
        completed_at_utc="2026-05-04T09:00:01Z",
        message="Parser failed safely.",
        warnings=["No context was produced."],
        errors=["Unsupported encoding."],
    )

    payload = step.to_payload()

    assert payload["step_name"] == "parsing"
    assert payload["state"] == "failed"
    assert payload["warnings"] == ["No context was produced."]
    assert payload["errors"] == ["Unsupported encoding."]


def test_attached_file_schema_rejects_unexpected_fields():
    with pytest.raises(ValidationError):
        AttachedFile(
            file_id="file_extra_001",
            display_name="extra.txt",
            random_extra_field=True,
        )
