"""
Local file-ingestion service organ for the Elysia API bridge.

This module provides the bounded local file-ingest path.

It should stay narrow:
- accept an explicit user-selected local file path
- support TXT/Markdown/JSON/saved HTML/PDF/DOCX as bounded text context when
  local parser dependencies are available
- support CSV/XLSX as bounded data-execution inputs and compact local summaries
- copy raw files into local ingest storage
- extract bounded context chunks for supported text-like file kinds
- return schema-backed file-ingest truth

It must not:
- expose routes
- scan folders
- read arbitrary paths recursively
- fake parser support when a local dependency is unavailable
- execute JavaScript or fetch linked resources from saved HTML
- call models or embeddings
- promote attached files into memory
- perform outward network actions
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.api.file_path_guard import guard_selected_file_path
from app.api.file_text_extractors import extract_file_text
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

from app.install.paths import resolve_elysia_paths

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INGEST_ROOT = resolve_elysia_paths().ingest_dir
DEFAULT_MAX_FILE_SIZE_BYTES = 2_000_000
DEFAULT_CHUNK_CHAR_LIMIT = 1_200
DEFAULT_ATTACHED_CONTEXT_MAX_FILES = 3
DEFAULT_ATTACHED_CONTEXT_MAX_CHUNKS_PER_FILE = 6
DEFAULT_ATTACHED_CONTEXT_MAX_TOTAL_EXCERPT_CHARS = 6_000

SUPPORTED_TEXT_FILE_KINDS = {
    FileKind.TEXT,
    FileKind.MARKDOWN,
    FileKind.JSON,
    FileKind.HTML,
    FileKind.PDF,
    FileKind.DOCX,
}

SUPPORTED_DATA_FILE_KINDS = {
    FileKind.CSV,
    FileKind.XLSX,
}

SUPPORTED_FILE_KINDS = SUPPORTED_TEXT_FILE_KINDS | SUPPORTED_DATA_FILE_KINDS


def _utc_now_iso() -> str:
    """
    Return a compact UTC timestamp string.
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_display_name(path: Path) -> str:
    """
    Return a compact display name without exposing more path than needed.
    """
    return path.name or "attached-file"


def _fallback_file_id(source_path: Path, *, prefix: str = "file_unresolved") -> str:
    """
    Build a deterministic fallback id from the path text when content hash is
    not available.
    """
    digest = hashlib.sha256(str(source_path).encode("utf-8", errors="replace")).hexdigest()
    return f"{prefix}_{digest[:16]}"


def _detect_file_kind(path: Path) -> FileKind:
    """
    Detect the v0 file kind from extension only.

    This intentionally does not imply parser support for every schema-level kind.
    """
    suffix = path.suffix.lower()

    if suffix == ".txt":
        return FileKind.TEXT

    if suffix in {".md", ".markdown"}:
        return FileKind.MARKDOWN

    if suffix == ".docx":
        return FileKind.DOCX

    if suffix == ".pdf":
        return FileKind.PDF

    if suffix == ".csv":
        return FileKind.CSV

    if suffix == ".xlsx":
        return FileKind.XLSX

    if suffix == ".json":
        return FileKind.JSON

    if suffix in {".html", ".htm"}:
        return FileKind.HTML

    return FileKind.UNSUPPORTED


def _is_supported_kind(file_kind: FileKind) -> bool:
    """
    Return whether this service v0 can process the detected file kind.
    """
    return file_kind in SUPPORTED_FILE_KINDS


def _is_text_context_kind(file_kind: FileKind) -> bool:
    """
    Return whether this file kind should be parsed into bounded text chunks.
    """
    return file_kind in SUPPORTED_TEXT_FILE_KINDS


def _is_data_execution_kind(file_kind: FileKind) -> bool:
    """
    Return whether this file kind should be registered for bounded data execution.
    """
    return file_kind in SUPPORTED_DATA_FILE_KINDS


def _compute_sha256(path: Path) -> str:
    """
    Compute a SHA-256 hash for a local file.
    """
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def _build_file_id(sha256: str) -> str:
    """
    Build a stable local file id from a content hash.
    """
    return f"file_{sha256[:16]}"


def _guess_mime_type(path: Path) -> str | None:
    """
    Guess MIME type using Python's local mimetypes table.
    """
    mime_type, _ = mimetypes.guess_type(path.name)
    return mime_type


def _build_attached_file(
    *,
    file_id: str,
    source_path: Path,
    file_kind: FileKind,
    processing_state: FileProcessingState,
    size_bytes: int | None = None,
    sha256: str | None = None,
    conversation_id: str | None = None,
    project_id: str | None = None,
    can_use_as_context: bool = False,
    parser_used: str | None = None,
    chunks_created_count: int = 0,
    chunks_used_count: int = 0,
    blocked_reason: str | None = None,
    notes: list[str] | None = None,
) -> AttachedFile:
    """
    Build compact attached-file metadata while keeping memory disabled by default.
    """
    return AttachedFile(
        file_id=file_id,
        display_name=_safe_display_name(source_path),
        original_name=_safe_display_name(source_path),
        file_kind=file_kind,
        mime_type=_guess_mime_type(source_path),
        size_bytes=size_bytes,
        sha256=sha256,
        trust_zone=FileTrustZone.USER_SELECTED,
        processing_state=processing_state,
        memory_posture=FileMemoryPosture.NOT_MEMORY,
        attached_at_utc=_utc_now_iso(),
        source_conversation_id=conversation_id,
        source_project_id=project_id,
        user_selected=True,
        can_use_as_context=can_use_as_context,
        can_promote_to_memory=False,
        parser_used=parser_used,
        chunks_created_count=chunks_created_count,
        chunks_used_count=chunks_used_count,
        memory_promotion_allowed=False,
        outward_sharing_allowed=False,
        blocked_reason=blocked_reason,
        notes=notes or [],
    )


def _processing_step(
    *,
    step_name: str,
    state: FileProcessingState,
    message: str | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> FileProcessingStep:
    """
    Build one completed processing step for v0's simple synchronous path.
    """
    timestamp = _utc_now_iso()

    return FileProcessingStep(
        step_name=step_name,
        state=state,
        started_at_utc=timestamp,
        completed_at_utc=timestamp,
        message=message,
        warnings=warnings or [],
        errors=errors or [],
    )


def _failed_result(
    *,
    source_path: Path,
    error: str,
    file_kind: FileKind = FileKind.UNKNOWN,
    file_id: str | None = None,
    size_bytes: int | None = None,
    sha256: str | None = None,
    conversation_id: str | None = None,
    project_id: str | None = None,
) -> FileIngestResult:
    """
    Build a failed ingest result.

    Failed means the path or operation failed. It does not necessarily mean a
    policy/support boundary blocked the file.
    """
    resolved_file_id = file_id or _fallback_file_id(source_path, prefix="file_failed")
    attached_file = _build_attached_file(
        file_id=resolved_file_id,
        source_path=source_path,
        file_kind=file_kind,
        processing_state=FileProcessingState.FAILED,
        size_bytes=size_bytes,
        sha256=sha256,
        conversation_id=conversation_id,
        project_id=project_id,
        can_use_as_context=False,
        notes=["File ingest failed safely."],
        blocked_reason=error,
    )

    return FileIngestResult(
        file_id=resolved_file_id,
        processing_state=FileProcessingState.FAILED,
        accepted=False,
        blocked=False,
        ready=False,
        file=attached_file,
        steps=[
            _processing_step(
                step_name="failed",
                state=FileProcessingState.FAILED,
                message="File ingest failed safely.",
                errors=[error],
            )
        ],
        errors=[error],
    )


def _blocked_result(
    *,
    source_path: Path,
    error: str,
    file_kind: FileKind,
    file_id: str | None = None,
    size_bytes: int | None = None,
    sha256: str | None = None,
    conversation_id: str | None = None,
    project_id: str | None = None,
) -> FileIngestResult:
    """
    Build a blocked ingest result.

    Blocked means policy, support limits, trust posture, or size boundaries
    refused ingestion.
    """
    resolved_file_id = file_id or _fallback_file_id(source_path, prefix="file_blocked")
    attached_file = _build_attached_file(
        file_id=resolved_file_id,
        source_path=source_path,
        file_kind=file_kind,
        processing_state=FileProcessingState.BLOCKED,
        size_bytes=size_bytes,
        sha256=sha256,
        conversation_id=conversation_id,
        project_id=project_id,
        can_use_as_context=False,
        notes=["File ingest was blocked before context use."],
        blocked_reason=error,
    )

    return FileIngestResult(
        file_id=resolved_file_id,
        processing_state=FileProcessingState.BLOCKED,
        accepted=False,
        blocked=True,
        ready=False,
        file=attached_file,
        steps=[
            _processing_step(
                step_name="blocked",
                state=FileProcessingState.BLOCKED,
                message="File ingest was blocked before context use.",
                errors=[error],
            )
        ],
        errors=[error],
    )


def _chunk_text(
    *,
    file_id: str,
    text: str,
    chunk_char_limit: int,
) -> list[FileContextChunkSummary]:
    """
    Create simple character-window chunks for v0.

    This is intentionally modest. Semantic chunking and embeddings come later.
    """
    normalized_limit = max(1, int(chunk_char_limit))
    chunks: list[FileContextChunkSummary] = []

    if not text:
        return chunks

    for chunk_index, char_start in enumerate(range(0, len(text), normalized_limit)):
        char_end = min(char_start + normalized_limit, len(text))
        excerpt = text[char_start:char_end].strip()

        chunks.append(
            FileContextChunkSummary(
                chunk_id=f"{file_id}_chunk_{chunk_index:04d}",
                file_id=file_id,
                chunk_index=chunk_index,
                heading=None,
                char_start=char_start,
                char_end=char_end,
                token_estimate=max(1, len(excerpt) // 4) if excerpt else 0,
                excerpt=excerpt[:420] if excerpt else None,
            )
        )

    return chunks


def _file_summary_note(file_kind: FileKind, parser_used: str) -> str:
    if file_kind == FileKind.JSON:
        return "JSON was parsed locally into a bounded structure summary and text context."
    if file_kind == FileKind.HTML:
        return "Saved HTML was parsed locally as text. Scripts, styles, links, and external resources were not executed or fetched."
    if file_kind == FileKind.PDF:
        return "PDF text was extracted locally. OCR/rendering was not used."
    if file_kind == FileKind.DOCX:
        return "DOCX text was extracted locally. Macros and external links were not executed or followed."
    return f"Local ingest produced simple text chunks with {parser_used}."


def _ensure_ingest_dirs(
    *,
    ingest_root: Path,
    file_id: str,
) -> tuple[Path, Path]:
    """
    Ensure raw and extracted directories exist for one file id.
    """
    raw_dir = ingest_root / "raw" / file_id
    extracted_dir = ingest_root / "extracted" / file_id

    raw_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)

    return raw_dir, extracted_dir


def _write_chunks_json(
    *,
    chunks_path: Path,
    file_id: str,
    display_name: str,
    chunks: list[FileContextChunkSummary],
) -> None:
    """
    Write compact chunk summaries to local extracted storage.
    """
    payload: dict[str, Any] = {
        "file_id": file_id,
        "display_name": display_name,
        "chunk_count": len(chunks),
        "chunks": [chunk.to_payload() for chunk in chunks],
    }

    chunks_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _ingest_result_path(
    *,
    ingest_root: Path,
    file_id: str,
) -> Path:
    """
    Return the local registry path for one file ingest result.
    """
    return ingest_root / "extracted" / file_id / "ingest_result.json"


def _chunks_path(
    *,
    ingest_root: Path,
    file_id: str,
) -> Path:
    """
    Return the local extracted chunks path for one file ingest result.
    """
    return ingest_root / "extracted" / file_id / "chunks.json"


def _write_ingest_result_json(
    *,
    result_path: Path,
    result: FileIngestResult,
) -> None:
    """
    Persist the schema-backed ingest result for later status/context lookup.
    """
    result_path.write_text(
        json.dumps(result.to_payload(), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _load_json_payload(path: Path) -> dict[str, Any] | None:
    """
    Load one local JSON payload safely.

    Missing, unreadable, malformed, or non-object payloads return None so the
    route layer can report an honest not-found/degraded envelope.
    """
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    return payload



def _build_data_file_ingest_result(
    *,
    source: Path,
    ingest_base: Path,
    file_id: str,
    file_kind: FileKind,
    size_bytes: int,
    sha256: str,
    conversation_id: str | None,
    project_id: str | None,
) -> FileIngestResult:
    """
    Register a CSV/XLSX file as a bounded local data-execution input.

    This copies the raw data file into local ingest storage and records metadata.
    It intentionally does not parse table rows, create prompt chunks, call models,
    promote memory, write artifacts, or run the data executor. Runtime decides
    later whether the user request should trigger bounded table inspection.
    """
    try:
        raw_dir, _ = _ensure_ingest_dirs(
            ingest_root=ingest_base,
            file_id=file_id,
        )

        raw_copy_path = raw_dir / source.name
        shutil.copy2(source, raw_copy_path)
    except OSError as exc:
        return _failed_result(
            source_path=source,
            error=f"Could not persist local data-file ingest artifact: {exc}",
            file_kind=file_kind,
            file_id=file_id,
            size_bytes=size_bytes,
            sha256=sha256,
            conversation_id=conversation_id,
            project_id=project_id,
        )

    attached_file = _build_attached_file(
        file_id=file_id,
        source_path=source,
        file_kind=file_kind,
        processing_state=FileProcessingState.READY,
        size_bytes=size_bytes,
        sha256=sha256,
        conversation_id=conversation_id,
        project_id=project_id,
        can_use_as_context=True,
        parser_used="data_file_registration",
        chunks_created_count=0,
        chunks_used_count=0,
        notes=[
            "Data file was copied into local ingest storage.",
            "Data file is ready for bounded local data execution and compact local metadata truth.",
            "Attached data file remains separate from memory.",
        ],
    )

    context_summary = FileContextSummary(
        file_id=file_id,
        display_name=_safe_display_name(source),
        file_kind=file_kind,
        processing_state=FileProcessingState.READY,
        memory_posture=FileMemoryPosture.NOT_MEMORY,
        usable_as_context=True,
        chunk_count=0,
        selected_chunk_count=0,
        chunks=[],
        summary_note=(
            f"{file_kind.value.upper()} is ready for bounded local data execution. "
            "It was copied locally and not promoted into memory."
        ),
        parser_used="data_file_registration",
        memory_promotion_allowed=False,
        outward_sharing_allowed=False,
        retrieval_method="bounded_data_file_registration",
        warnings=[],
        errors=[],
    )

    result = FileIngestResult(
        file_id=file_id,
        processing_state=FileProcessingState.READY,
        accepted=True,
        blocked=False,
        ready=True,
        file=attached_file,
        steps=[
            _processing_step(
                step_name="detecting_type",
                state=FileProcessingState.DETECTING_TYPE,
                message=f"Detected file kind: {file_kind.value}.",
            ),
            _processing_step(
                step_name="registering_data_file",
                state=FileProcessingState.INDEXED,
                message="Registered data file for bounded local data execution without text chunking.",
            ),
            _processing_step(
                step_name="ready",
                state=FileProcessingState.READY,
                message="Data file is ready for governed bounded data-execution use.",
            ),
        ],
        warnings=[],
        errors=[],
        context_summary=context_summary,
    )

    try:
        _write_ingest_result_json(
            result_path=_ingest_result_path(
                ingest_root=ingest_base,
                file_id=file_id,
            ),
            result=result,
        )
    except OSError as exc:
        return _failed_result(
            source_path=source,
            error=f"Could not persist local data-file ingest result registry: {exc}",
            file_kind=file_kind,
            file_id=file_id,
            size_bytes=size_bytes,
            sha256=sha256,
            conversation_id=conversation_id,
            project_id=project_id,
        )

    return result


def attach_file(
    source_path: str | Path,
    *,
    conversation_id: str | None = None,
    project_id: str | None = None,
    ingest_root: str | Path | None = None,
    max_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    chunk_char_limit: int = DEFAULT_CHUNK_CHAR_LIMIT,
) -> FileIngestResult:
    """
    Attach and ingest one explicit user-selected local file.

    V0 supports TXT/Markdown as bounded text context and CSV/XLSX as bounded
    data-execution inputs. Successful ingestion makes the file usable for the
    correct governed lane, but does not promote it into memory.
    """
    source = Path(source_path).expanduser()
    ingest_base = Path(ingest_root) if ingest_root is not None else DEFAULT_INGEST_ROOT

    guard = guard_selected_file_path(source_path, max_size_bytes=max_size_bytes)
    if not guard.allowed:
        return _blocked_result(
            source_path=source,
            error=guard.reason,
            file_kind=_detect_file_kind(source),
            conversation_id=conversation_id,
            project_id=project_id,
        )

    if not source.exists():
        return _failed_result(
            source_path=source,
            error=f"Source file does not exist: {source}",
            conversation_id=conversation_id,
            project_id=project_id,
        )

    if not source.is_file():
        return _failed_result(
            source_path=source,
            error=f"Source path is not a file: {source}",
            conversation_id=conversation_id,
            project_id=project_id,
        )

    file_kind = _detect_file_kind(source)

    try:
        size_bytes = source.stat().st_size
    except OSError as exc:
        return _failed_result(
            source_path=source,
            error=f"Could not inspect source file size: {exc}",
            file_kind=file_kind,
            conversation_id=conversation_id,
            project_id=project_id,
        )

    if size_bytes > max_size_bytes:
        return _blocked_result(
            source_path=source,
            error=(
                f"File is too large for v0 ingest: {size_bytes} bytes "
                f"exceeds limit of {max_size_bytes} bytes."
            ),
            file_kind=file_kind,
            size_bytes=size_bytes,
            conversation_id=conversation_id,
            project_id=project_id,
        )

    if not _is_supported_kind(file_kind):
        sha256: str | None = None
        file_id: str | None = None

        try:
            sha256 = _compute_sha256(source)
            file_id = _build_file_id(sha256)
        except OSError:
            pass

        return _blocked_result(
            source_path=source,
            error=(
                f"Unsupported file kind for v0 ingest: {file_kind.value}. "
                "Supported local ingest kinds are TXT, Markdown, CSV, XLSX, JSON, saved HTML, PDF, and DOCX. "
                "PDF/DOCX support depends on local parser packages."
            ),
            file_kind=FileKind.UNSUPPORTED,
            file_id=file_id,
            size_bytes=size_bytes,
            sha256=sha256,
            conversation_id=conversation_id,
            project_id=project_id,
        )

    try:
        sha256 = _compute_sha256(source)
    except OSError as exc:
        return _failed_result(
            source_path=source,
            error=f"Could not hash source file: {exc}",
            file_kind=file_kind,
            size_bytes=size_bytes,
            conversation_id=conversation_id,
            project_id=project_id,
        )

    file_id = _build_file_id(sha256)

    if _is_data_execution_kind(file_kind):
        return _build_data_file_ingest_result(
            source=source,
            ingest_base=ingest_base,
            file_id=file_id,
            file_kind=file_kind,
            size_bytes=size_bytes,
            sha256=sha256,
            conversation_id=conversation_id,
            project_id=project_id,
        )

    try:
        extraction = extract_file_text(source, file_kind)
    except Exception as exc:
        return _failed_result(
            source_path=source,
            error=f"Could not parse source file locally: {exc}",
            file_kind=file_kind,
            file_id=file_id,
            size_bytes=size_bytes,
            sha256=sha256,
            conversation_id=conversation_id,
            project_id=project_id,
        )

    if not extraction.ok:
        return _blocked_result(
            source_path=source,
            error="; ".join(extraction.errors) or "Local parser could not extract usable text.",
            file_kind=file_kind,
            file_id=file_id,
            size_bytes=size_bytes,
            sha256=sha256,
            conversation_id=conversation_id,
            project_id=project_id,
        )

    try:
        raw_dir, extracted_dir = _ensure_ingest_dirs(
            ingest_root=ingest_base,
            file_id=file_id,
        )

        raw_copy_path = raw_dir / source.name
        shutil.copy2(source, raw_copy_path)

        chunks = _chunk_text(
            file_id=file_id,
            text=extraction.text,
            chunk_char_limit=chunk_char_limit,
        )

        chunks_path = extracted_dir / "chunks.json"
        _write_chunks_json(
            chunks_path=chunks_path,
            file_id=file_id,
            display_name=_safe_display_name(source),
            chunks=chunks,
        )
    except OSError as exc:
        return _failed_result(
            source_path=source,
            error=f"Could not persist local ingest artifacts: {exc}",
            file_kind=file_kind,
            file_id=file_id,
            size_bytes=size_bytes,
            sha256=sha256,
            conversation_id=conversation_id,
            project_id=project_id,
        )

    attached_file = _build_attached_file(
        file_id=file_id,
        source_path=source,
        file_kind=file_kind,
        processing_state=FileProcessingState.READY,
        size_bytes=size_bytes,
        sha256=sha256,
        conversation_id=conversation_id,
        project_id=project_id,
        can_use_as_context=True,
        parser_used=extraction.parser_used,
        chunks_created_count=len(chunks),
        chunks_used_count=len(chunks),
        notes=[
            "File was copied into local ingest storage.",
            "File is usable as attached context but has not been promoted into memory.",
            f"Local parser used: {extraction.parser_used}.",
        ],
    )

    context_summary = FileContextSummary(
        file_id=file_id,
        display_name=_safe_display_name(source),
        file_kind=file_kind,
        processing_state=FileProcessingState.READY,
        memory_posture=FileMemoryPosture.NOT_MEMORY,
        usable_as_context=True,
        chunk_count=len(chunks),
        selected_chunk_count=len(chunks),
        chunks=chunks,
        summary_note=_file_summary_note(file_kind, extraction.parser_used),
        parser_used=extraction.parser_used,
        memory_promotion_allowed=False,
        outward_sharing_allowed=False,
        retrieval_method="bounded_selection",
        warnings=list(extraction.warnings),
        errors=[],
    )

    result = FileIngestResult(
        file_id=file_id,
        processing_state=FileProcessingState.READY,
        accepted=True,
        blocked=False,
        ready=True,
        file=attached_file,
        steps=[
            _processing_step(
                step_name="detecting_type",
                state=FileProcessingState.DETECTING_TYPE,
                message=f"Detected file kind: {file_kind.value}.",
            ),
            _processing_step(
                step_name="parsing",
                state=FileProcessingState.PARSING,
                message="Read supported text content as UTF-8.",
            ),
            _processing_step(
                step_name="indexing",
                state=FileProcessingState.INDEXED,
                message="Wrote simple local chunk summaries.",
            ),
            _processing_step(
                step_name="ready",
                state=FileProcessingState.READY,
                message="File is ready for governed attached-context use.",
            ),
        ],
        warnings=list(extraction.warnings),
        errors=[],
        context_summary=context_summary,
    )

    try:
        _write_ingest_result_json(
            result_path=_ingest_result_path(
                ingest_root=ingest_base,
                file_id=file_id,
            ),
            result=result,
        )
    except OSError as exc:
        return _failed_result(
            source_path=source,
            error=f"Could not persist local ingest result registry: {exc}",
            file_kind=file_kind,
            file_id=file_id,
            size_bytes=size_bytes,
            sha256=sha256,
            conversation_id=conversation_id,
            project_id=project_id,
        )

    return result



def get_file_status(
    file_id: str,
    *,
    ingest_root: str | Path | None = None,
) -> FileIngestResult | None:
    """
    Return a previously persisted file-ingest result by file id.

    This is a local filesystem registry lookup. It does not scan folders, call
    models, promote memory, or parse files.
    """
    clean_file_id = str(file_id).strip()

    if not clean_file_id:
        return None

    ingest_base = Path(ingest_root) if ingest_root is not None else DEFAULT_INGEST_ROOT
    result_path = _ingest_result_path(
        ingest_root=ingest_base,
        file_id=clean_file_id,
    )
    payload = _load_json_payload(result_path)

    if payload is None:
        return None

    try:
        return FileIngestResult(**payload)
    except (TypeError, ValueError):
        return None


def get_file_context_summary(
    file_id: str,
    *,
    ingest_root: str | Path | None = None,
) -> FileContextSummary | None:
    """
    Return the context summary for a previously persisted file-ingest result.
    """
    result = get_file_status(
        file_id,
        ingest_root=ingest_root,
    )

    if result is None:
        return None

    return result.context_summary


def _enum_payload_value(value: Any) -> Any:
    """
    Return enum values as strings while leaving plain values unchanged.
    """
    return getattr(value, "value", value)


def _normalize_attached_file_ids(file_ids: list[str] | tuple[str, ...] | None) -> list[str]:
    """
    Normalize and deduplicate requested attached-file ids while preserving order.
    """
    if not file_ids:
        return []

    seen: set[str] = set()
    normalized: list[str] = []

    for file_id in file_ids:
        text = str(file_id or "").strip()
        if not text or text in seen:
            continue

        seen.add(text)
        normalized.append(text)

    return normalized


def _load_chunks_for_file(
    *,
    ingest_root: Path,
    file_id: str,
) -> list[dict[str, Any]]:
    """
    Load persisted chunk summaries for one file id.
    """
    payload = _load_json_payload(
        _chunks_path(
            ingest_root=ingest_root,
            file_id=file_id,
        )
    )

    if payload is None:
        return []

    chunks = payload.get("chunks")
    if not isinstance(chunks, list):
        return []

    return [
        dict(chunk)
        for chunk in chunks
        if isinstance(chunk, dict)
    ]


def build_attached_file_context_packet(
    file_ids: list[str] | tuple[str, ...] | None,
    *,
    ingest_root: str | Path | None = None,
    max_files: int = DEFAULT_ATTACHED_CONTEXT_MAX_FILES,
    max_chunks_per_file: int = DEFAULT_ATTACHED_CONTEXT_MAX_CHUNKS_PER_FILE,
    max_total_excerpt_chars: int = DEFAULT_ATTACHED_CONTEXT_MAX_TOTAL_EXCERPT_CHARS,
) -> dict[str, Any]:
    """
    Build a bounded local context packet for user-selected attached files.

    TXT/Markdown files become bounded text-context excerpts. CSV/XLSX files become
    bounded data-execution inputs and are not injected into the prompt as raw
    rows. This does not call models, promote memory, perform retrieval, or parse
    table data.
    """
    ingest_base = Path(ingest_root) if ingest_root is not None else DEFAULT_INGEST_ROOT
    requested_ids = _normalize_attached_file_ids(file_ids)
    selected_ids = requested_ids[: max(0, int(max_files))]

    warnings: list[str] = []
    errors: list[str] = []
    files: list[dict[str, Any]] = []
    data_files: list[dict[str, Any]] = []
    total_excerpt_chars = 0
    total_excerpt_limit = max(0, int(max_total_excerpt_chars))
    per_file_chunk_limit = max(0, int(max_chunks_per_file))

    if len(requested_ids) > len(selected_ids):
        warnings.append(
            f"Attached file context was limited to {len(selected_ids)} file(s) for v0."
        )

    for file_id in selected_ids:
        status = get_file_status(
            file_id,
            ingest_root=ingest_base,
        )

        if status is None:
            warnings.append(f"No local ingest record was found for attached file id: {file_id}")
            continue

        context_summary = status.context_summary
        attached_file = status.file
        file_kind = _enum_payload_value(
            getattr(attached_file, "file_kind", None)
            or getattr(context_summary, "file_kind", None)
        )
        file_kind_text = str(file_kind or "").strip().lower()

        if (
            not status.ready
            or status.blocked
            or context_summary is None
            or not context_summary.usable_as_context
        ):
            warnings.append(
                f"Attached file is not ready for context use and was skipped: {file_id}"
            )
            continue

        display_name = (
            getattr(attached_file, "display_name", None)
            or context_summary.display_name
            or file_id
        )

        if file_kind_text in {FileKind.CSV.value, FileKind.XLSX.value}:
            raw_copy_path = ingest_base / "raw" / file_id / str(display_name)
            if not raw_copy_path.exists():
                warnings.append(
                    f"Attached data-file raw copy was missing and was skipped: {file_id}"
                )
                continue

            data_files.append(
                {
                    "file_id": file_id,
                    "display_name": str(display_name),
                    "file_name": str(display_name),
                    "name": str(display_name),
                    "file_kind": file_kind_text or FileKind.UNKNOWN.value,
                    "source_kind": "attached_file",
                    "source_path": str(raw_copy_path),
                    "local_path": str(raw_copy_path),
                    "processing_state": _enum_payload_value(
                        getattr(attached_file, "processing_state", None)
                        or context_summary.processing_state
                    ),
                    "parser_used": str(
                        getattr(attached_file, "parser_used", None)
                        or getattr(context_summary, "parser_used", None)
                        or "data_file_registration"
                    ),
                    "memory_posture": _enum_payload_value(
                        getattr(attached_file, "memory_posture", None)
                        or context_summary.memory_posture
                        or FileMemoryPosture.NOT_MEMORY
                    ),
                    "memory_promotion_allowed": False,
                    "outward_sharing_allowed": False,
                    "ready": True,
                    "usable_as_context": True,
                    "blocked": False,
                    "chunk_count": 0,
                    "selected_chunk_count": 0,
                    "notes": list(getattr(attached_file, "notes", []) or []),
                }
            )
            continue

        chunk_payloads = _load_chunks_for_file(
            ingest_root=ingest_base,
            file_id=file_id,
        )

        selected_chunks: list[dict[str, Any]] = []
        for chunk in chunk_payloads:
            if len(selected_chunks) >= per_file_chunk_limit:
                break

            excerpt = str(chunk.get("excerpt") or "").strip()
            if not excerpt:
                continue

            remaining_chars = total_excerpt_limit - total_excerpt_chars
            if remaining_chars <= 0:
                break

            bounded_excerpt = excerpt[:remaining_chars]
            total_excerpt_chars += len(bounded_excerpt)

            selected_chunks.append(
                {
                    "chunk_id": str(chunk.get("chunk_id") or ""),
                    "file_id": file_id,
                    "chunk_index": chunk.get("chunk_index"),
                    "heading": chunk.get("heading"),
                    "char_start": chunk.get("char_start"),
                    "char_end": chunk.get("char_end"),
                    "token_estimate": chunk.get("token_estimate"),
                    "excerpt": bounded_excerpt,
                }
            )

        if chunk_payloads and len(selected_chunks) < len(chunk_payloads):
            warnings.append(
                f"Attached file context for {file_id} was bounded to "
                f"{len(selected_chunks)} chunk(s) for v0."
            )

        if not selected_chunks:
            warnings.append(
                f"No usable local chunk excerpts were available for attached file id: {file_id}"
            )
            continue

        files.append(
            {
                "file_id": file_id,
                "display_name": str(display_name),
                "file_kind": file_kind_text or FileKind.UNKNOWN.value,
                "processing_state": _enum_payload_value(
                    getattr(attached_file, "processing_state", None)
                    or context_summary.processing_state
                ),
                "parser_used": str(
                    getattr(attached_file, "parser_used", None)
                    or getattr(context_summary, "parser_used", None)
                    or ""
                ),
                "memory_posture": _enum_payload_value(
                    getattr(attached_file, "memory_posture", None)
                    or context_summary.memory_posture
                    or FileMemoryPosture.NOT_MEMORY
                ),
                "memory_promotion_allowed": False,
                "outward_sharing_allowed": False,
                "usable_as_context": True,
                "chunk_count": context_summary.chunk_count,
                "selected_chunk_count": len(selected_chunks),
                "retrieval_method": (
                    getattr(context_summary, "retrieval_method", None)
                    or "bounded_selection"
                ),
                "chunks": selected_chunks,
            }
        )

    used_text_file_ids = [file["file_id"] for file in files]
    used_data_file_ids = [file["file_id"] for file in data_files]

    return {
        "attached_files_are_memory": False,
        "source": "user_selected_local_files",
        "locality": "local",
        "bounded": True,
        "requested_file_ids": requested_ids,
        "used_file_ids": used_text_file_ids + used_data_file_ids,
        "used_text_file_ids": used_text_file_ids,
        "used_data_file_ids": used_data_file_ids,
        "requested_file_count": len(requested_ids),
        "file_count": len(files) + len(data_files),
        "text_file_count": len(files),
        "data_file_count": len(data_files),
        "files": files,
        "data_files": data_files,
        "warnings": warnings,
        "errors": errors,
    }


__all__ = (
    "DEFAULT_CHUNK_CHAR_LIMIT",
    "DEFAULT_ATTACHED_CONTEXT_MAX_TOTAL_EXCERPT_CHARS",
    "DEFAULT_ATTACHED_CONTEXT_MAX_FILES",
    "DEFAULT_ATTACHED_CONTEXT_MAX_CHUNKS_PER_FILE",
    "DEFAULT_INGEST_ROOT",
    "DEFAULT_MAX_FILE_SIZE_BYTES",
    "attach_file",
    "build_attached_file_context_packet",
    "get_file_context_summary",
    "get_file_status",
)
