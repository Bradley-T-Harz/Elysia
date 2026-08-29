"""
Local artifact service for Elysia.

This service writes compact local JSON records as receipts/results from bounded
local data execution and simple local SVG plot artifact building.

It does not mutate source files, run shell commands, touch the network, execute
arbitrary Python, use notebooks, scan folders, fetch local paths from the UI, or
promote content into memory.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from collections.abc import Mapping

from app.ids import new_id

from app.api.schemas.artifacts import (
    ArtifactBoundaryTruth,
    ArtifactDetail,
    ArtifactKind,
    ArtifactListResponse,
    ArtifactMemoryPosture,
    ArtifactRecord,
    ArtifactSourceRef,
    ArtifactSummary,
    DataSummaryArtifactPayload,
    GeneratedMediaArtifactPayload,
    PlotArtifactPayload,
)
from app.api.schemas.common import ApprovalState, LocalityState
from app.api.schemas.execution import ExecutionToolKind
from app.install.paths import resolve_elysia_paths
from app.ownership import current_user_id


DEFAULT_ARTIFACT_ROOT = resolve_elysia_paths().artifact_dir
DATA_SUMMARY_ARTIFACT_PREFIX = "artifact_data_summary"
PLOT_IMAGE_ARTIFACT_PREFIX = "artifact_plot_image"
GENERATED_MEDIA_ARTIFACT_PREFIX = "artifact_generated_media"
MAX_ARTIFACT_LIST_LIMIT = 200
MAX_SAFE_PREVIEW_ROWS = 20


class ArtifactCreationError(ValueError):
    """Raised when a requested artifact would be false or unsafe to create."""


def _validate_new_authority_links(
    *,
    request_id: str | None,
    conversation_id: str | None,
    project_id: str | None,
) -> None:
    """Reject new dangling artifact links in the production authority path."""
    from app.memory.source_adapters import (
        MemorySourceReferenceError,
        validate_source_reference,
    )

    try:
        for kind, stable_id in (
            ("request", request_id),
            ("conversation", conversation_id),
            ("project", project_id),
        ):
            if stable_id:
                validate_source_reference(kind, stable_id)
    except MemorySourceReferenceError as exc:
        raise ArtifactCreationError(str(exc)) from exc


def create_artifact_id(prefix: str = "artifact") -> str:
    """Create a stable time-sortable artifact identifier."""
    return new_id(prefix)


def utc_now_iso() -> str:
    """Return a compact UTC timestamp."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_artifact_root() -> Path:
    """Return the default local artifact root."""
    configured = os.environ.get("ELYSIA_ARTIFACT_ROOT", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_ARTIFACT_ROOT


def _resolve_artifact_root(artifact_root: str | Path | None = None) -> Path:
    """Resolve the local artifact root without accepting arbitrary UI paths."""
    if artifact_root is not None:
        return Path(artifact_root)
    owner = current_user_id()
    if not owner:
        return default_artifact_root()
    owner_namespace = hashlib.sha256(owner.encode("utf-8")).hexdigest()[:24]
    return default_artifact_root() / "accounts" / owner_namespace


def sanitize_artifact_filename(value: str) -> str:
    """
    Sanitize one value for local artifact filenames.

    This is for generated artifact records only, not source files.
    """
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.-]+", "_", text)
    text = text.strip("._-")

    return text or "artifact"


def _enum_value(value: Any) -> str:
    """Normalize enum-like values into strings."""
    return str(getattr(value, "value", value) or "")


def _get_field(value: Any, key: str, default: Any = None) -> Any:
    """Read a field from a mapping or object."""
    if isinstance(value, Mapping):
        return value.get(key, default)

    return getattr(value, key, default)


def _get_bool(value: Any, key: str, default: bool = False) -> bool:
    raw = _get_field(value, key, default)

    if isinstance(raw, bool):
        return raw

    if raw is None:
        return default

    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False

    return bool(raw)


def _get_int(value: Any, key: str, default: int = 0) -> int:
    raw = _get_field(value, key, default)

    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return default


def _get_str(value: Any, key: str, default: str = "") -> str:
    raw = _get_field(value, key, default)
    text = str(raw or "").strip()
    return text if text else default


def _get_optional_str(value: Any, key: str) -> str | None:
    text = _get_str(value, key, "")
    return text or None


def _get_list(value: Any, key: str) -> list[Any]:
    raw = _get_field(value, key, [])
    return list(raw or []) if isinstance(raw, list) else []


def _get_dict(value: Any, key: str) -> dict[str, Any]:
    raw = _get_field(value, key, {})
    return dict(raw or {}) if isinstance(raw, Mapping) else {}


def _model_to_jsonable(value: Any) -> Any:
    """
    Convert Pydantic/dataclass-ish values into JSON-safe values.
    """
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")

    if hasattr(value, "dict"):
        return value.dict()

    if isinstance(value, Mapping):
        return {str(key): _model_to_jsonable(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_model_to_jsonable(item) for item in value]

    if isinstance(value, tuple):
        return [_model_to_jsonable(item) for item in value]

    if hasattr(value, "value"):
        return value.value

    return value


def _model_validate_artifact_record(payload: Mapping[str, Any]) -> ArtifactRecord:
    """Validate one saved artifact JSON payload across Pydantic versions."""
    validate_method = getattr(ArtifactRecord, "model_validate", None)
    if callable(validate_method):
        return validate_method(dict(payload))

    return ArtifactRecord(**dict(payload))


def _artifact_record_paths(artifact_root: str | Path | None = None) -> list[Path]:
    """Return candidate artifact record paths under the local artifact root."""
    root = _resolve_artifact_root(artifact_root)
    if not root.exists():
        return []

    return sorted(
        (path for path in root.glob("*.json") if path.is_file()),
        key=lambda path: path.name,
    )


def _load_artifact_record(path: Path) -> ArtifactRecord | None:
    """Load one artifact record from the known artifact store."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, Mapping):
        return None

    try:
        return _model_validate_artifact_record(payload)
    except Exception:
        return None


def _all_artifact_records(
    artifact_root: str | Path | None = None,
) -> list[ArtifactRecord]:
    """Load all readable artifact records from the local artifact root."""
    records = [
        record
        for path in _artifact_record_paths(artifact_root)
        if (record := _load_artifact_record(path)) is not None
    ]
    records.sort(
        key=lambda record: (record.created_at_utc or "", record.artifact_id),
        reverse=True,
    )
    return records


def _is_completed_data_execution(data_execution: Any) -> bool:
    """
    Determine whether one data execution payload is safe to artifact.

    Runtime payloads may be dicts with used/status and schema objects may carry
    ok/status. We accept completed used/ok summaries and reject failures/skips.
    """
    status = _enum_value(_get_field(data_execution, "status", "")).lower()
    used = _get_field(data_execution, "used", None)
    ok = _get_field(data_execution, "ok", None)

    if status != "completed":
        return False

    if used is False:
        return False

    if ok is False:
        return False

    return True


def _artifact_prefix_for_kind(kind: ArtifactKind) -> str:
    """Return the local filename prefix for one artifact kind."""
    if kind == ArtifactKind.PLOT_IMAGE:
        return PLOT_IMAGE_ARTIFACT_PREFIX

    if kind in {
        ArtifactKind.TRANSCRIPT,
        ArtifactKind.SPEECH_AUDIO,
        ArtifactKind.GENERATED_IMAGE,
        ArtifactKind.GENERATED_VIDEO,
    }:
        return GENERATED_MEDIA_ARTIFACT_PREFIX

    return DATA_SUMMARY_ARTIFACT_PREFIX


def _artifact_file_path(
    *,
    artifact_root: Path,
    artifact_id: str,
    kind: ArtifactKind,
) -> Path:
    prefix = _artifact_prefix_for_kind(kind)
    filename = sanitize_artifact_filename(f"{prefix}_{artifact_id}")
    return artifact_root / f"{filename}_{kind.value}.json"


def _build_payload(data_execution: Any) -> DataSummaryArtifactPayload:
    return DataSummaryArtifactPayload(
        row_count=_get_int(data_execution, "row_count", 0),
        column_count=_get_int(data_execution, "column_count", 0),
        columns=[str(value) for value in _get_list(data_execution, "columns")],
        numeric_columns=[
            str(value) for value in _get_list(data_execution, "numeric_columns")
        ],
        text_columns=[str(value) for value in _get_list(data_execution, "text_columns")],
        missing_values_by_column={
            str(column): int(count or 0)
            for column, count in _get_dict(
                data_execution,
                "missing_values_by_column",
            ).items()
        },
        numeric_stats=_model_to_jsonable(_get_dict(data_execution, "numeric_stats")),
        preview_rows=[
            {str(column): str(cell) for column, cell in row.items()}
            for row in _get_list(data_execution, "preview_rows")
            if isinstance(row, Mapping)
        ],
    )


def _build_summary_text(
    *,
    source_file_name: str | None,
    row_count: int,
    column_count: int,
) -> str:
    name = source_file_name or "attached data file"
    return f"Saved bounded local data summary for {name}: {row_count} rows, {column_count} columns."


def build_data_summary_artifact_record(
    data_execution: Any,
    *,
    request_id: str | None = None,
    conversation_id: str | None = None,
    project_id: str | None = None,
    artifact_root: str | Path | None = None,
    artifact_id: str | None = None,
    created_at_utc: str | None = None,
) -> ArtifactRecord:
    """
    Build one unsaved local data-summary artifact record.

    Raises ArtifactCreationError if the data execution was not completed
    successfully. This prevents fake success artifacts.
    """
    if not _is_completed_data_execution(data_execution):
        status = _enum_value(_get_field(data_execution, "status", "unknown"))
        raise ArtifactCreationError(
            "Data summary artifacts require completed bounded data execution. "
            f"Received status={status!r}."
        )

    root = _resolve_artifact_root(artifact_root)
    artifact_kind = ArtifactKind.DATA_SUMMARY
    resolved_artifact_id = artifact_id or create_artifact_id("artifact")
    artifact_path = _artifact_file_path(
        artifact_root=root,
        artifact_id=resolved_artifact_id,
        kind=artifact_kind,
    )

    payload = _build_payload(data_execution)
    source_file_name = _get_optional_str(data_execution, "file_name")
    source_file_id = (
        _get_optional_str(data_execution, "file_id")
        or _get_optional_str(data_execution, "source_file_id")
    )
    source_file_kind = _get_optional_str(data_execution, "file_kind")
    source_kind = _get_str(data_execution, "source_kind", "attached_file")
    producer_operation = _get_str(data_execution, "operation", "summarize_csv")

    title = f"Data summary: {source_file_name or 'attached data file'}"
    summary = _build_summary_text(
        source_file_name=source_file_name,
        row_count=payload.row_count,
        column_count=payload.column_count,
    )

    boundary_notes = [
        "Saved from bounded local data execution.",
        "Source file was not mutated.",
        "Artifact is local and not memory.",
        "No network, shell, arbitrary Python, plotting, notebook behavior, folder scanning, or memory promotion was used.",
    ]

    return ArtifactRecord(
        artifact_id=resolved_artifact_id,
        owner_user_id=current_user_id(),
        kind=artifact_kind,
        title=title,
        summary=summary,
        created_at_utc=created_at_utc or utc_now_iso(),
        request_id=request_id,
        conversation_id=conversation_id,
        project_id=project_id,
        artifact_path=str(artifact_path),
        producer_tool_kind=(
            _enum_value(
                _get_field(
                    data_execution,
                    "tool_kind",
                    ExecutionToolKind.DATA_EXECUTOR.value,
                )
            )
            or ExecutionToolKind.DATA_EXECUTOR.value
        ),
        producer_operation=producer_operation,
        source=ArtifactSourceRef(
            source_kind=source_kind,
            source_file_id=source_file_id,
            source_file_name=source_file_name,
            source_file_kind=source_file_kind,
            source_path=_get_optional_str(data_execution, "source_path"),
        ),
        boundary=ArtifactBoundaryTruth(
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            memory_posture=ArtifactMemoryPosture.NOT_MEMORY,
            artifact_saved_locally=True,
            source_file_mutated=False,
            network_access_used=_get_bool(data_execution, "network_access_used", False),
            memory_promoted=False,
            arbitrary_python_used=False,
            shell_used=False,
            notes=boundary_notes,
        ),
        payload=payload,
        warnings=[str(value) for value in _get_list(data_execution, "warnings")],
        errors=[str(value) for value in _get_list(data_execution, "errors")],
    )


def _is_completed_plot_build(plot_build_result: Any) -> bool:
    """
    Determine whether one plot build result is safe to save as a plot artifact.
    """
    status = _enum_value(_get_field(plot_build_result, "status", "")).lower()
    ok = _get_field(plot_build_result, "ok", None)
    artifact_kind = _get_str(
        plot_build_result,
        "artifact_kind",
        ArtifactKind.PLOT_IMAGE.value,
    )
    svg_text = _get_str(plot_build_result, "svg_text", "")

    if status != "completed":
        return False

    if ok is False:
        return False

    if artifact_kind != ArtifactKind.PLOT_IMAGE.value:
        return False

    if not svg_text.lstrip().startswith("<svg"):
        return False

    return True


def _build_plot_payload(plot_build_result: Any) -> PlotArtifactPayload:
    """Build a compact plot artifact payload from a completed plot build."""
    return PlotArtifactPayload(
        plot_kind=_get_str(
            plot_build_result,
            "plot_kind",
            "numeric_summary_bar_svg",
        ),
        svg_text=_get_str(plot_build_result, "svg_text", ""),
        svg_mime_type=_get_str(
            plot_build_result,
            "svg_mime_type",
            "image/svg+xml",
        ),
        width=max(1, _get_int(plot_build_result, "width", 720)),
        height=max(1, _get_int(plot_build_result, "height", 420)),
        metric=_get_str(plot_build_result, "metric", "mean"),
        plotted_columns=[
            str(value) for value in _get_list(plot_build_result, "plotted_columns")
        ],
        row_count=_get_int(plot_build_result, "row_count", 0),
        column_count=_get_int(plot_build_result, "column_count", 0),
    )


def build_plot_image_artifact_record(
    plot_build_result: Any,
    *,
    request_id: str | None = None,
    conversation_id: str | None = None,
    project_id: str | None = None,
    artifact_root: str | Path | None = None,
    artifact_id: str | None = None,
    created_at_utc: str | None = None,
) -> ArtifactRecord:
    """
    Build one unsaved local plot-image artifact record.

    Raises ArtifactCreationError if the plot build result was not completed
    successfully. This prevents fake plot artifacts.
    """
    if not _is_completed_plot_build(plot_build_result):
        status = _enum_value(_get_field(plot_build_result, "status", "unknown"))
        raise ArtifactCreationError(
            "Plot image artifacts require a completed bounded local plot build. "
            f"Received status={status!r}."
        )

    root = _resolve_artifact_root(artifact_root)
    artifact_kind = ArtifactKind.PLOT_IMAGE
    resolved_artifact_id = artifact_id or create_artifact_id("artifact")
    artifact_path = _artifact_file_path(
        artifact_root=root,
        artifact_id=resolved_artifact_id,
        kind=artifact_kind,
    )


    payload = _build_plot_payload(plot_build_result)
    source_file_name = _get_optional_str(plot_build_result, "source_file_name")
    source_file_kind = _get_optional_str(plot_build_result, "source_file_kind")
    title = _get_str(
        plot_build_result,
        "title",
        f"Plot artifact: {source_file_name or 'data summary'}",
    )
    summary = _get_str(
        plot_build_result,
        "summary",
        "Saved local SVG plot artifact from completed bounded data execution.",
    )

    boundary_notes = [
        "Saved from completed bounded local data execution summary.",
        "Generated as a simple local SVG plot artifact.",
        "Source file was not mutated.",
        "Artifact is local and not memory.",
        "No network, shell, arbitrary Python, notebook behavior, folder scanning, local path fetching, or memory promotion was used.",
    ]

    return ArtifactRecord(
        artifact_id=resolved_artifact_id,
        owner_user_id=current_user_id(),
        kind=artifact_kind,
        title=title,
        summary=summary,
        created_at_utc=created_at_utc or utc_now_iso(),
        request_id=request_id,
        conversation_id=conversation_id,
        project_id=project_id,
        artifact_path=str(artifact_path),
        producer_tool_kind=_get_str(
            plot_build_result,
            "tool_kind",
            "plot_artifact_builder",
        ),
        producer_operation=_get_str(
            plot_build_result,
            "operation",
            "build_numeric_summary_bar_svg",
        ),
        source=ArtifactSourceRef(
            source_kind=_get_str(plot_build_result, "source_kind", "data_execution_summary"),
            source_file_id=_get_optional_str(plot_build_result, "source_file_id"),
            source_file_name=source_file_name,
            source_file_kind=source_file_kind,
            source_path=None,
        ),
        boundary=ArtifactBoundaryTruth(
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.NOT_NEEDED,
            memory_posture=ArtifactMemoryPosture.NOT_MEMORY,
            artifact_saved_locally=True,
            source_file_mutated=False,
            network_access_used=_get_bool(
                plot_build_result,
                "network_access_used",
                False,
            ),
            memory_promoted=False,
            arbitrary_python_used=_get_bool(
                plot_build_result,
                "arbitrary_python_used",
                False,
            ),
            shell_used=_get_bool(plot_build_result, "shell_used", False),
            notes=boundary_notes,
        ),
        payload=payload,
        warnings=[str(value) for value in _get_list(plot_build_result, "warnings")],
        errors=[str(value) for value in _get_list(plot_build_result, "errors")],
    )


def build_generated_media_artifact_record(
    media_result: Any,
    *,
    request_id: str | None = None,
    conversation_id: str | None = None,
    project_id: str | None = None,
    artifact_root: str | Path | None = None,
    artifact_id: str | None = None,
    created_at_utc: str | None = None,
) -> ArtifactRecord:
    """Build a compact receipt for a completed governed media-worker output."""
    status = _get_str(media_result, "status", "")
    kind_text = _get_str(media_result, "artifact_kind", "")
    try:
        artifact_kind = ArtifactKind(kind_text)
    except ValueError as exc:
        raise ArtifactCreationError(f"Unsupported generated media artifact kind: {kind_text}") from exc
    if status != "completed" or artifact_kind not in {
        ArtifactKind.TRANSCRIPT,
        ArtifactKind.SPEECH_AUDIO,
        ArtifactKind.GENERATED_IMAGE,
        ArtifactKind.GENERATED_VIDEO,
    }:
        raise ArtifactCreationError("Generated media artifacts require a completed governed worker result.")
    output_path = Path(_get_str(media_result, "output_path", ""))
    output_sha256 = _get_str(media_result, "output_sha256", "")
    if not output_path.is_file() or not output_sha256:
        raise ArtifactCreationError("Generated media output and SHA-256 receipt are required.")

    root = _resolve_artifact_root(artifact_root)
    resolved_artifact_id = artifact_id or create_artifact_id("artifact")
    receipt_path = _artifact_file_path(artifact_root=root, artifact_id=resolved_artifact_id, kind=artifact_kind)
    payload = GeneratedMediaArtifactPayload(
        model_id=_get_str(media_result, "model_id", "unknown_local_model"),
        worker_key=_get_str(media_result, "worker_key", "media_worker"),
        mime_type=_get_str(media_result, "mime_type", "application/octet-stream"),
        output_path=str(output_path),
        output_sha256=output_sha256,
        output_bytes=_get_int(media_result, "output_bytes", output_path.stat().st_size),
        sidecar_path=_get_optional_str(media_result, "sidecar_path"),
        sidecar_sha256=_get_optional_str(media_result, "sidecar_sha256"),
        synthetic_media=_get_bool(media_result, "synthetic_media", False),
        machine_generated_transcript=_get_bool(media_result, "machine_generated_transcript", False),
        duration_seconds=_get_field(media_result, "duration_seconds", None),
        language=_get_optional_str(media_result, "language"),
        segment_count=_get_field(media_result, "segment_count", None),
        sample_rate_hz=_get_field(media_result, "sample_rate_hz", None),
        width=_get_field(media_result, "width", None),
        height=_get_field(media_result, "height", None),
        prompt_or_text_hash=_get_optional_str(media_result, "prompt_or_text_hash"),
        prompt_or_text_length=_get_field(media_result, "prompt_or_text_length", None),
        provenance_state=_get_str(media_result, "provenance_state", "local_unverified"),
    )
    return ArtifactRecord(
        artifact_id=resolved_artifact_id,
        owner_user_id=current_user_id(),
        kind=artifact_kind,
        title=_get_str(media_result, "title", f"Local {artifact_kind.value} artifact"),
        summary=_get_str(media_result, "summary", "Saved governed local media-worker output."),
        created_at_utc=created_at_utc or utc_now_iso(),
        request_id=request_id,
        conversation_id=conversation_id,
        project_id=project_id,
        artifact_path=str(receipt_path),
        producer_tool_kind="governed_media_worker",
        producer_operation=_get_str(media_result, "operation", artifact_kind.value),
        source=ArtifactSourceRef(
            source_kind=_get_str(media_result, "source_kind", "local_worker_request"),
            source_file_id=None,
            source_file_name=_get_optional_str(media_result, "source_file_name"),
            source_file_kind=_get_optional_str(media_result, "source_file_kind"),
            source_path=_get_optional_str(media_result, "source_path"),
        ),
        boundary=ArtifactBoundaryTruth(
            locality=LocalityState.LOCAL,
            approval_state=ApprovalState.APPROVED,
            memory_posture=ArtifactMemoryPosture.NOT_MEMORY,
            artifact_saved_locally=True,
            source_file_mutated=False,
            network_access_used=False,
            memory_promoted=False,
            arbitrary_python_used=False,
            shell_used=False,
            notes=[
                "Generated by an isolated local worker after exact approval.",
                "Raw transcript, text, prompt, and media bytes are excluded from central trace.",
                "Artifact is local and is not memory by default.",
            ],
        ),
        payload=payload,
        warnings=[str(value) for value in _get_list(media_result, "warnings")],
        errors=[],
    )


def save_artifact_record(record: ArtifactRecord) -> ArtifactRecord:
    """
    Save one artifact record and adopt eligible immutable generated bytes.

    Source outputs remain intact for established artifact workflows. The
    content-addressed object reference is rolled back if the artifact metadata
    cannot be committed, so neither authority retains a dangling half-write.
    """
    adopted_objects = None
    adopted_reference_id: str | None = None
    if isinstance(record.payload, GeneratedMediaArtifactPayload) and record.owner_user_id:
        from app.api.account_service import AccountStore
        from app.memory.canonical_models import MemoryPrincipal, MemoryPrivacy
        from app.memory.object_store import MemoryObjectStore

        try:
            principal = MemoryPrincipal.model_validate(
                AccountStore().authenticated_principal()
            )
            if principal.user_id != record.owner_user_id:
                raise ArtifactCreationError("Artifact ownership changed before byte adoption.")
            source_path = Path(record.payload.output_path)
            if not source_path.is_file() or source_path.is_symlink():
                raise ArtifactCreationError("Generated artifact bytes failed their file-boundary check.")
            raw = source_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != record.payload.output_sha256:
                raise ArtifactCreationError("Generated artifact bytes failed their signed digest.")
            objects = MemoryObjectStore()
            managed = objects.put(
                principal=principal,
                raw=raw,
                privacy=MemoryPrivacy.NORMAL,
                space_id=None,
                ref_type="artifact",
                ref_id=record.artifact_id,
                purpose="authoritative_generated_bytes",
                media_type=record.payload.mime_type,
                compress=False,
            )
            adopted_objects = objects
            adopted_reference_id = str(managed["object_ref_id"])
            managed_path = objects.internal_managed_path(
                principal=principal, object_id=str(managed["object_id"])
            )
            record = record.model_copy(
                update={
                    "payload": record.payload.model_copy(
                        update={
                            "output_path": str(managed_path),
                            "provenance_state": "governed_object_verified",
                        }
                    ),
                    "object_id": str(managed["object_id"]),
                    "object_authority": "xdg_content_addressed_objects_v1",
                }
            )
        except ArtifactCreationError:
            if adopted_objects is not None and adopted_reference_id is not None:
                adopted_objects.purge_reference_ids([adopted_reference_id])
            raise
        except Exception as exc:
            if adopted_objects is not None and adopted_reference_id is not None:
                adopted_objects.purge_reference_ids([adopted_reference_id])
            raise ArtifactCreationError(
                "Generated artifact bytes could not enter the governed object authority."
            ) from exc

    artifact_path = Path(record.artifact_path)
    payload = _model_to_jsonable(record)
    temporary: Path | None = None
    try:
        artifact_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        artifact_path.parent.chmod(0o700)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".artifact-", dir=artifact_path.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, artifact_path)
        temporary = None
        artifact_path.chmod(0o600)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if adopted_objects is not None and adopted_reference_id is not None:
            adopted_objects.purge_reference_ids([adopted_reference_id])
        raise

    return record


def artifact_summary_from_record(record: ArtifactRecord) -> ArtifactSummary:
    """
    Build a compact UI-safe summary from a saved artifact record.

    This intentionally does not include raw source_path, raw artifact_path, or
    full inline plot payloads. Plot SVG text belongs in ArtifactDetail.safe_preview
    for a selected artifact, not in list/catalog summaries.
    """
    payload = record.payload

    return ArtifactSummary(
        artifact_id=record.artifact_id,
        kind=record.kind,
        title=record.title,
        summary=record.summary,
        created_at_utc=record.created_at_utc,
        request_id=record.request_id,
        conversation_id=record.conversation_id,
        project_id=record.project_id,
        locality=record.boundary.locality,
        memory_posture=record.boundary.memory_posture,
        producer_tool_kind=record.producer_tool_kind,
        producer_operation=record.producer_operation,
        source_file_id=record.source.source_file_id,
        source_file_name=record.source.source_file_name,
        source_file_kind=record.source.source_file_kind,
        row_count=getattr(payload, "row_count", None),
        column_count=getattr(payload, "column_count", None),
        plot_kind=getattr(payload, "plot_kind", None),
        svg_text=None,
        svg_mime_type=getattr(payload, "svg_mime_type", None),
        width=getattr(payload, "width", None),
        height=getattr(payload, "height", None),
        metric=getattr(payload, "metric", None),
        plotted_columns=list(getattr(payload, "plotted_columns", []) or []),
        model_id=getattr(payload, "model_id", None),
        mime_type=getattr(payload, "mime_type", None),
        output_sha256=getattr(payload, "output_sha256", None),
        output_bytes=getattr(payload, "output_bytes", None),
        synthetic_media=bool(getattr(payload, "synthetic_media", False)),
        warnings=list(record.warnings),
        errors=list(record.errors),
        memory_promotion=bool(record.boundary.memory_promoted),
        private_context_sent=False,
        preview_available=record.kind
        in {
            ArtifactKind.DATA_SUMMARY,
            ArtifactKind.PLOT_IMAGE,
            ArtifactKind.TRANSCRIPT,
            ArtifactKind.SPEECH_AUDIO,
            ArtifactKind.GENERATED_IMAGE,
            ArtifactKind.GENERATED_VIDEO,
        },
        detail_available=True,
    )


def _safe_preview_from_record(record: ArtifactRecord) -> dict[str, Any]:
    """Build a bounded type-specific preview without raw paths."""
    payload = record.payload

    if record.kind == ArtifactKind.DATA_SUMMARY:
        preview_rows = list(getattr(payload, "preview_rows", []) or [])[
            :MAX_SAFE_PREVIEW_ROWS
        ]
        return {
            "row_count": getattr(payload, "row_count", 0),
            "column_count": getattr(payload, "column_count", 0),
            "columns": list(getattr(payload, "columns", []) or []),
            "numeric_columns": list(getattr(payload, "numeric_columns", []) or []),
            "text_columns": list(getattr(payload, "text_columns", []) or []),
            "missing_values_by_column": dict(
                getattr(payload, "missing_values_by_column", {}) or {}
            ),
            "numeric_stats": dict(getattr(payload, "numeric_stats", {}) or {}),
            "preview_rows": preview_rows,
            "preview_truncated": len(preview_rows)
            < len(list(getattr(payload, "preview_rows", []) or [])),
        }

    if record.kind == ArtifactKind.PLOT_IMAGE:
        return {
            "plot_kind": getattr(payload, "plot_kind", None),
            "svg_text": getattr(payload, "svg_text", None),
            "svg_mime_type": getattr(payload, "svg_mime_type", None),
            "width": getattr(payload, "width", None),
            "height": getattr(payload, "height", None),
            "metric": getattr(payload, "metric", None),
            "plotted_columns": list(getattr(payload, "plotted_columns", []) or []),
            "row_count": getattr(payload, "row_count", None),
            "column_count": getattr(payload, "column_count", None),
            "generated_local": True,
        }

    if record.kind in {
        ArtifactKind.TRANSCRIPT,
        ArtifactKind.SPEECH_AUDIO,
        ArtifactKind.GENERATED_IMAGE,
        ArtifactKind.GENERATED_VIDEO,
    }:
        return {
            "model_id": getattr(payload, "model_id", None),
            "worker_key": getattr(payload, "worker_key", None),
            "mime_type": getattr(payload, "mime_type", None),
            "output_sha256": getattr(payload, "output_sha256", None),
            "output_bytes": getattr(payload, "output_bytes", None),
            "synthetic_media": bool(getattr(payload, "synthetic_media", False)),
            "machine_generated_transcript": bool(getattr(payload, "machine_generated_transcript", False)),
            "duration_seconds": getattr(payload, "duration_seconds", None),
            "language": getattr(payload, "language", None),
            "segment_count": getattr(payload, "segment_count", None),
            "sample_rate_hz": getattr(payload, "sample_rate_hz", None),
            "width": getattr(payload, "width", None),
            "height": getattr(payload, "height", None),
            "provenance_state": getattr(payload, "provenance_state", None),
            "raw_content_included": False,
        }

    return {
        "summary": record.summary,
        "preview_available": False,
    }


def artifact_detail_from_record(record: ArtifactRecord) -> ArtifactDetail:
    """Build safe detail for one saved artifact record."""
    summary = artifact_summary_from_record(record)
    source_ref = {
        "source_kind": record.source.source_kind,
        "source_file_id": record.source.source_file_id,
        "source_file_name": record.source.source_file_name,
        "source_file_kind": record.source.source_file_kind,
    }
    boundary = {
        "locality": _enum_value(record.boundary.locality),
        "approval_state": _enum_value(record.boundary.approval_state),
        "memory_posture": _enum_value(record.boundary.memory_posture),
        "artifact_saved_locally": bool(record.boundary.artifact_saved_locally),
        "source_file_mutated": bool(record.boundary.source_file_mutated),
        "network_access_used": bool(record.boundary.network_access_used),
        "memory_promotion": bool(record.boundary.memory_promoted),
        "private_context_sent": False,
        "arbitrary_python_used": bool(record.boundary.arbitrary_python_used),
        "shell_used": bool(record.boundary.shell_used),
        "notes": list(record.boundary.notes),
    }
    return ArtifactDetail(
        summary=summary,
        detail_kind=f"{_enum_value(record.kind)}_detail",
        safe_preview=_safe_preview_from_record(record),
        provenance=[source_ref],
        boundary_truth=boundary,
    )


def list_artifacts(
    *,
    project_id: str | None = None,
    request_id: str | None = None,
    conversation_id: str | None = None,
    artifact_type: str | None = None,
    limit: int = 50,
    artifact_root: str | Path | None = None,
) -> ArtifactListResponse:
    """List safe summaries for local artifacts from the known artifact store."""
    effective_limit = max(1, min(int(limit or 50), MAX_ARTIFACT_LIST_LIMIT))
    artifact_type_text = str(artifact_type or "").strip()
    records = _all_artifact_records(artifact_root)

    filtered: list[ArtifactRecord] = []
    for record in records:
        if project_id and record.project_id != project_id:
            continue
        if request_id and record.request_id != request_id:
            continue
        if conversation_id and record.conversation_id != conversation_id:
            continue
        if artifact_type_text and _enum_value(record.kind) != artifact_type_text:
            continue
        filtered.append(record)

    limited = filtered[:effective_limit]
    return ArtifactListResponse(
        artifacts=[artifact_summary_from_record(record) for record in limited],
        total=len(filtered),
        limit=effective_limit,
        filters={
            "project_id": project_id,
            "request_id": request_id,
            "conversation_id": conversation_id,
            "artifact_type": artifact_type_text or None,
        },
    )


def get_artifact_detail(
    artifact_id: str,
    *,
    artifact_root: str | Path | None = None,
) -> ArtifactDetail | None:
    """Return safe detail for one known artifact id."""
    target_id = str(artifact_id or "").strip()
    if not target_id:
        return None

    for record in _all_artifact_records(artifact_root):
        if record.artifact_id == target_id:
            return artifact_detail_from_record(record)

    return None


def create_data_summary_artifact(
    data_execution: Any,
    *,
    request_id: str | None = None,
    conversation_id: str | None = None,
    project_id: str | None = None,
    artifact_root: str | Path | None = None,
) -> ArtifactRecord:
    """
    Build and save one local data-summary artifact from completed data execution.
    """
    if artifact_root is None:
        _validate_new_authority_links(
            request_id=request_id,
            conversation_id=conversation_id,
            project_id=project_id,
        )
    record = build_data_summary_artifact_record(
        data_execution,
        request_id=request_id,
        conversation_id=conversation_id,
        project_id=project_id,
        artifact_root=artifact_root,
    )

    return save_artifact_record(record)


def create_plot_image_artifact(
    plot_build_result: Any,
    *,
    request_id: str | None = None,
    conversation_id: str | None = None,
    project_id: str | None = None,
    artifact_root: str | Path | None = None,
) -> ArtifactRecord:
    """
    Build and save one local plot-image artifact from a completed plot build.
    """
    if artifact_root is None:
        _validate_new_authority_links(
            request_id=request_id,
            conversation_id=conversation_id,
            project_id=project_id,
        )
    record = build_plot_image_artifact_record(
        plot_build_result,
        request_id=request_id,
        conversation_id=conversation_id,
        project_id=project_id,
        artifact_root=artifact_root,
    )

    return save_artifact_record(record)


def create_generated_media_artifact(
    media_result: Any,
    *,
    request_id: str | None = None,
    conversation_id: str | None = None,
    project_id: str | None = None,
    artifact_root: str | Path | None = None,
) -> ArtifactRecord:
    if artifact_root is None:
        _validate_new_authority_links(
            request_id=request_id,
            conversation_id=conversation_id,
            project_id=project_id,
        )
    record = build_generated_media_artifact_record(
        media_result,
        request_id=request_id,
        conversation_id=conversation_id,
        project_id=project_id,
        artifact_root=artifact_root,
    )
    return save_artifact_record(record)


__all__ = (
    "ArtifactCreationError",
    "artifact_detail_from_record",
    "artifact_summary_from_record",
    "build_data_summary_artifact_record",
    "build_plot_image_artifact_record",
    "build_generated_media_artifact_record",
    "create_artifact_id",
    "create_data_summary_artifact",
    "create_plot_image_artifact",
    "create_generated_media_artifact",
    "default_artifact_root",
    "get_artifact_detail",
    "list_artifacts",
    "sanitize_artifact_filename",
    "save_artifact_record",
    "utc_now_iso",
)
