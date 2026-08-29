"""
Project storage/service organ for the Elysia local API bridge.

This module is the local persistence and retrieval layer for Stage 11 project
index/detail support.

It should stay in this lane:
- create and normalize local project containers
- persist compact project metadata locally
- list projects for route/UI surfaces
- load one project detail payload
- manage the active project selection locally
- derive related conversation summaries from the existing conversation store
- mutate compact project metadata locally when explicitly requested
- delete one stored project container locally when explicitly requested

It should not become:
- a route module
- a response-envelope builder
- a runtime/invoker layer
- a governance layer
- a capability-reporting layer
- a second conversation store
- a full database abstraction fantasy

Current storage posture:
- local filesystem only
- one JSON file per project
- atomic writes
- modest schema discipline
- robust enough for Stage 11, without pretending to be the final store
"""

from __future__ import annotations

import json
from hashlib import sha256
import logging
import re
import tempfile
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NotRequired, TypedDict
from app.ids import new_id
from app.ownership import DomainOwnershipError, assert_owner as assert_domain_owner, current_user_id

from app.api.conversation_service import (
    ConversationServiceError,
    get_conversation_thread,
    list_conversations,
)
from app.install.paths import resolve_elysia_paths

LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECTS_DIR = resolve_elysia_paths().project_dir
ACTIVE_PROJECT_PATH = PROJECTS_DIR / "_active_project.json"

STORAGE_VERSION = 1
PROJECT_ID_PREFIX = "proj"

MAX_NAME_LENGTH = 80
MAX_DESCRIPTION_LENGTH = 280
MAX_SUMMARY_LENGTH = 220
MAX_CONTINUITY_TEXT_LENGTH = 280
MAX_CONTINUITY_ITEMS = 20
MAX_LIST_LIMIT = 500

_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_SLUG_PART_PATTERN = re.compile(r"[^a-z0-9]+")
_STORE_LOCK = threading.RLock()


class ProjectServiceError(Exception):
    """Base exception for project service failures."""


class ProjectNotFoundError(ProjectServiceError):
    """Raised when a requested project container does not exist."""


class ProjectStoreCorruptError(ProjectServiceError):
    """Raised when a stored project record cannot be interpreted safely."""


def _assert_record_owner(owner_user_id: str | None) -> None:
    try:
        assert_domain_owner(owner_user_id)
    except DomainOwnershipError as exc:
        raise ProjectNotFoundError("The project is unavailable to this account.") from exc


class ProjectMetadataRecord(TypedDict):
    project_id: str
    owner_user_id: NotRequired[str | None]
    slug: str
    name: str
    created_at_utc: str
    updated_at_utc: str
    status: str
    description: NotRequired[str | None]
    notes_summary: NotRequired[str | None]
    state_summary: NotRequired[str | None]
    current_state: NotRequired[str | None]
    latest_chunk: NotRequired[str | None]
    project_notes: NotRequired[str | None]
    milestones: NotRequired[list[dict[str, Any]]]
    decisions: NotRequired[list[dict[str, Any]]]
    blockers: NotRequired[list[dict[str, Any]]]
    next_actions: NotRequired[list[dict[str, Any]]]
    unresolved_questions: NotRequired[list[dict[str, Any]]]
    corrections: NotRequired[list[dict[str, Any]]]
    source_count: NotRequired[int]
    archived: NotRequired[bool]


class ProjectRecord(TypedDict):
    storage_version: int
    metadata: dict[str, Any]


class ActiveProjectSelectionRecord(TypedDict):
    active_project_id: str | None
    selected_at_utc: str | None


def _utc_now_iso() -> str:
    """Return a compact UTC timestamp string with trailing Z."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_store_dir() -> None:
    """Ensure the project storage directory exists."""
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def _new_compact_id(prefix: str) -> str:
    """Create a sortable UUIDv7 identifier for local storage surfaces."""
    return new_id(prefix)


def new_project_id() -> str:
    """Create a new project identifier."""
    return _new_compact_id(PROJECT_ID_PREFIX)


def _validate_project_id(project_id: str) -> str:
    """
    Validate and normalize one project identifier.

    This stays intentionally modest: the service rejects obviously unsafe
    identifiers without pretending to solve every future identity question.
    """
    normalized = project_id.strip()
    if not normalized:
        raise ProjectServiceError("Project identifier must not be empty.")

    if not _PROJECT_ID_PATTERN.fullmatch(normalized):
        raise ProjectServiceError(
            "Project identifier contains unsupported characters."
        )

    return normalized


def _project_path(project_id: str) -> Path:
    """Return the local JSON storage path for one project."""
    safe_id = _validate_project_id(project_id)
    return PROJECTS_DIR / f"{safe_id}.json"


def _compact_text(value: str | None) -> str:
    """Collapse whitespace and strip surrounding noise for display-oriented fields."""
    if value is None:
        return ""

    return " ".join(str(value).strip().split())


def _truncate_text(value: str | None, limit: int) -> str:
    """Trim text to a display-safe length with ellipsis when needed."""
    compacted = _compact_text(value)
    if len(compacted) <= limit:
        return compacted

    return f"{compacted[: max(1, limit - 1)].rstrip()}…"


def _safe_string(value: Any) -> str | None:
    """Return a stripped string or None."""
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _safe_bool(value: Any, default: bool = False) -> bool:
    """Defensively coerce broad truthy/falsy values into bool."""
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False

    return default


def _safe_int(value: Any, default: int = 0) -> int:
    """Defensively coerce a value into a non-negative integer."""
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default

    return max(0, normalized)


def _derive_project_name(name: str | None) -> str:
    """Build a modest display-safe project name."""
    derived = _truncate_text(name, MAX_NAME_LENGTH)
    return derived or "New project"


def _derive_description(value: str | None) -> str | None:
    """Build a modest display-safe project description."""
    description = _truncate_text(value, MAX_DESCRIPTION_LENGTH)
    return description or None


def _derive_summary(value: str | None) -> str | None:
    """Build a modest display-safe summary field."""
    summary = _truncate_text(value, MAX_SUMMARY_LENGTH)
    return summary or None


def _derive_continuity_text(value: Any) -> str | None:
    """Build display-safe text for project continuity fields."""
    text = _truncate_text(_safe_string(value), MAX_CONTINUITY_TEXT_LENGTH)
    return text or None


def _normalize_status_label(value: Any, default: str = "planned") -> str:
    """Normalize compact continuity status labels."""
    text = _compact_text(_safe_string(value)).lower().replace(" ", "_")
    if text in {"complete", "completed", "done"}:
        return "complete"
    if text in {"partial", "in_progress", "active"}:
        return "partial"
    if text in {"blocked", "paused"}:
        return "blocked"
    if text in {"planned", "next"}:
        return "planned"
    return default


def _normalize_continuity_items(
    value: Any,
    *,
    default_status: str = "planned",
) -> list[dict[str, Any]]:
    """Normalize manual milestone/blocker/action lists into compact records."""
    if not isinstance(value, list):
        return []

    items: list[dict[str, Any]] = []
    for raw_item in value[:MAX_CONTINUITY_ITEMS]:
        if isinstance(raw_item, Mapping):
            label = _derive_continuity_text(raw_item.get("label") or raw_item.get("title"))
            summary = _derive_continuity_text(raw_item.get("summary"))
            status = _normalize_status_label(raw_item.get("status"), default_status)
            source_kind = _derive_continuity_text(raw_item.get("source_kind")) or "manual"
            source_id = _derive_continuity_text(raw_item.get("source_id"))
            updated_at_utc = _derive_continuity_text(raw_item.get("updated_at_utc"))
        else:
            label = _derive_continuity_text(raw_item)
            summary = None
            status = default_status
            source_kind = "manual"
            source_id = None
            updated_at_utc = None

        if not label:
            continue

        item = {
            "label": label,
            "status": status,
            "source_kind": source_kind,
            "source_id": source_id,
            "updated_at_utc": updated_at_utc,
        }
        if summary:
            item["summary"] = summary
        items.append(item)

    return items


def _slugify_name(name: str | None) -> str:
    """Create a modest slug from the current project name."""
    base = _compact_text(name).lower()
    slug = _SLUG_PART_PATTERN.sub("-", base).strip("-")
    return slug[:64] or "project"


def _normalize_status(raw_status: str | None, *, archived: bool = False) -> str:
    """Normalize project status into a modest canonical string."""
    normalized = _compact_text(raw_status).lower().replace(" ", "_")
    if archived:
        return "archived"

    return normalized or "active"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write one JSON record atomically to reduce corruption risk."""
    _ensure_store_dir()

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.stem}_",
        suffix=".tmp",
        delete=False,
    ) as temp_file:
        temp_path = Path(temp_file.name)
        json.dump(payload, temp_file, indent=2, ensure_ascii=False, sort_keys=True)
        temp_file.write("\n")

    temp_path.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    """Read one JSON file into a mapping."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError as exc:
        raise ProjectNotFoundError(f"Project '{path.stem}' does not exist.") from exc
    except json.JSONDecodeError as exc:
        raise ProjectStoreCorruptError(
            f"Project record '{path.name}' is not valid JSON: {exc}"
        ) from exc
    except OSError as exc:
        raise ProjectServiceError(
            f"Unable to read project record '{path.name}': {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise ProjectStoreCorruptError(
            f"Project record '{path.name}' is not a JSON object."
        )

    return payload


def _build_metadata_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one project metadata payload."""
    project_id = _safe_string(data.get("project_id"))
    if not project_id:
        raise ProjectStoreCorruptError("Project metadata is missing project_id.")

    normalized_project_id = _validate_project_id(project_id)
    name = _derive_project_name(_safe_string(data.get("name")))
    archived = _safe_bool(data.get("archived"))
    status = _normalize_status(_safe_string(data.get("status")), archived=archived)

    created_at_utc = _safe_string(data.get("created_at_utc")) or _utc_now_iso()
    updated_at_utc = _safe_string(data.get("updated_at_utc")) or created_at_utc

    metadata: ProjectMetadataRecord = {
        "project_id": normalized_project_id,
        "owner_user_id": _safe_string(data.get("owner_user_id")),
        "slug": _safe_string(data.get("slug")) or _slugify_name(name),
        "name": name,
        "created_at_utc": created_at_utc,
        "updated_at_utc": updated_at_utc,
        "status": status,
        "archived": archived,
    }

    description = _derive_description(_safe_string(data.get("description")))
    if description is not None:
        metadata["description"] = description

    notes_summary = _derive_summary(_safe_string(data.get("notes_summary")))
    if notes_summary is not None:
        metadata["notes_summary"] = notes_summary

    state_summary = _derive_summary(_safe_string(data.get("state_summary")))
    if state_summary is not None:
        metadata["state_summary"] = state_summary

    current_state = _derive_continuity_text(data.get("current_state"))
    if current_state is not None:
        metadata["current_state"] = current_state

    latest_chunk = _derive_continuity_text(data.get("latest_chunk"))
    if latest_chunk is not None:
        metadata["latest_chunk"] = latest_chunk

    project_notes = _derive_continuity_text(data.get("project_notes"))
    if project_notes is not None:
        metadata["project_notes"] = project_notes

    metadata["milestones"] = _normalize_continuity_items(
        data.get("milestones"),
        default_status="complete",
    )
    metadata["decisions"] = _normalize_continuity_items(
        data.get("decisions"),
        default_status="decided",
    )
    metadata["blockers"] = _normalize_continuity_items(
        data.get("blockers"),
        default_status="blocked",
    )
    metadata["next_actions"] = _normalize_continuity_items(
        data.get("next_actions"),
        default_status="planned",
    )
    metadata["unresolved_questions"] = _normalize_continuity_items(
        data.get("unresolved_questions"),
        default_status="open",
    )
    metadata["corrections"] = _normalize_continuity_items(
        data.get("corrections"),
        default_status="corrective",
    )

    metadata["source_count"] = _safe_int(data.get("source_count"), default=0)

    return dict(metadata)


def _empty_record(
    project_id: str,
    *,
    name: str,
    description: str | None = None,
    status: str | None = None,
    notes_summary: str | None = None,
    state_summary: str | None = None,
) -> ProjectRecord:
    """Create an empty project record with valid compact metadata."""
    now = _utc_now_iso()

    metadata = _build_metadata_dict(
        {
            "project_id": project_id,
            "owner_user_id": current_user_id(),
            "slug": _slugify_name(name),
            "name": name,
            "description": description,
            "created_at_utc": now,
            "updated_at_utc": now,
            "status": status or "active",
            "notes_summary": notes_summary,
            "state_summary": state_summary,
            "current_state": state_summary,
            "latest_chunk": None,
            "project_notes": notes_summary,
            "milestones": [],
            "blockers": [],
            "next_actions": [],
            "source_count": 0,
            "archived": False,
        }
    )

    return {
        "storage_version": STORAGE_VERSION,
        "metadata": metadata,
    }


def _normalize_loaded_record(project_id: str, payload: dict[str, Any]) -> ProjectRecord:
    """
    Normalize a loaded on-disk record into the service's internal shape.

    This accepts the intended nested shape and one modest migration fallback where
    metadata fields were stored top-level.
    """
    storage_version = int(payload.get("storage_version", STORAGE_VERSION))
    raw_metadata = payload.get("metadata")

    if isinstance(raw_metadata, Mapping):
        metadata_payload = dict(raw_metadata)
    else:
        metadata_payload = {
            key: payload.get(key)
            for key in (
                "project_id",
                "owner_user_id",
                "slug",
                "name",
                "description",
                "created_at_utc",
                "updated_at_utc",
                "status",
                "notes_summary",
                "state_summary",
                "source_count",
                "archived",
            )
            if key in payload
        }

    metadata_payload["project_id"] = project_id
    normalized_metadata = _build_metadata_dict(metadata_payload)

    return {
        "storage_version": storage_version,
        "metadata": normalized_metadata,
    }


def _load_record(project_id: str) -> ProjectRecord:
    """Load and normalize one project record from local storage."""
    path = _project_path(project_id)
    payload = _read_json(path)
    return _normalize_loaded_record(project_id, payload)


def _save_record(record: ProjectRecord) -> None:
    """Persist one normalized project record."""
    metadata = record.get("metadata", {})
    project_id = _safe_string(metadata.get("project_id"))
    if not project_id:
        raise ProjectServiceError("Cannot save project record without project_id.")

    path = _project_path(project_id)
    _write_json_atomic(path, record)


def _sorted_project_paths() -> list[Path]:
    """Return all stored project paths in a stable local order."""
    _ensure_store_dir()
    return sorted(
        (
            path
            for path in PROJECTS_DIR.glob("*.json")
            if not path.name.startswith("_")
        ),
        key=lambda path: path.name.lower(),
    )


def _normalize_selection_payload(payload: dict[str, Any]) -> ActiveProjectSelectionRecord:
    """Normalize one active-project selection payload."""
    active_project_id = _safe_string(payload.get("active_project_id"))
    if active_project_id is not None:
        active_project_id = _validate_project_id(active_project_id)

    selected_at_utc = _safe_string(payload.get("selected_at_utc"))

    return {
        "active_project_id": active_project_id,
        "selected_at_utc": selected_at_utc,
    }


def _read_active_selection() -> ActiveProjectSelectionRecord:
    """Read the local active-project selection state."""
    _ensure_store_dir()

    selection_path = _active_selection_path()
    if not selection_path.exists():
        return {
            "active_project_id": None,
            "selected_at_utc": None,
        }

    payload = _read_json(selection_path)
    return _normalize_selection_payload(payload)


def _write_active_selection(active_project_id: str | None) -> ActiveProjectSelectionRecord:
    """Persist the active-project selection state atomically."""
    normalized_active_project_id = (
        _validate_project_id(active_project_id) if active_project_id else None
    )

    payload: ActiveProjectSelectionRecord = {
        "active_project_id": normalized_active_project_id,
        "selected_at_utc": _utc_now_iso() if normalized_active_project_id else None,
    }
    _write_json_atomic(_active_selection_path(), dict(payload))
    return payload


def _active_selection_path() -> Path:
    owner = current_user_id()
    if owner is None:
        return ACTIVE_PROJECT_PATH
    owner_digest = sha256(owner.encode("utf-8")).hexdigest()[:20]
    return PROJECTS_DIR / f"_active_project_{owner_digest}.json"


def _conversation_metadata_to_summary(metadata: Any) -> dict[str, Any]:
    """Convert one conversation metadata model into a modest summary dictionary."""
    return {
        "conversation_id": _safe_string(getattr(metadata, "conversation_id", None)) or "",
        "title": _safe_string(getattr(metadata, "title", None)),
        "created_at_utc": _safe_string(getattr(metadata, "created_at_utc", None)),
        "updated_at_utc": _safe_string(getattr(metadata, "updated_at_utc", None)),
        "last_message_preview": _safe_string(
            getattr(metadata, "last_message_preview", None)
        ),
        "message_count": getattr(metadata, "message_count", None),
        "current_mode": _safe_string(getattr(metadata, "current_mode", None)),
        "current_role": _safe_string(getattr(metadata, "current_role", None)),
        "capability_state": _safe_string(
            getattr(metadata, "capability_state", None)
        ),
        "locality": _safe_string(getattr(metadata, "locality", None)),
        "approval_state": _safe_string(getattr(metadata, "approval_state", None)),
        "project_id": _safe_string(getattr(metadata, "project_id", None)),
        "archived": bool(getattr(metadata, "archived", False)),
        "pinned": bool(getattr(metadata, "pinned", False)),
        "conversation_state": _safe_string(
            getattr(metadata, "conversation_state", None)
        ),
    }


def list_project_conversations(
    project_id: str,
    *,
    include_archived: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    List conversations currently linked to one project.

    This intentionally derives project membership from the existing conversation
    store's project_id field rather than introducing a second membership map that
    could drift out of sync.
    """
    normalized_project_id = _validate_project_id(project_id)

    if limit is not None and limit < 0:
        raise ProjectServiceError("Project conversation list limit must not be negative.")

    effective_limit = None
    if limit is not None:
        effective_limit = min(limit, MAX_LIST_LIMIT)

    try:
        conversation_metadata_items = list_conversations(
            include_archived=include_archived,
            limit=None,
        )
    except ConversationServiceError as exc:
        raise ProjectServiceError(
            f"Project conversations are not available: {exc}"
        ) from exc

    related_items = [
        _conversation_metadata_to_summary(metadata)
        for metadata in conversation_metadata_items
        if _safe_string(getattr(metadata, "project_id", None)) == normalized_project_id
    ]

    if effective_limit is not None:
        related_items = related_items[:effective_limit]

    return related_items


def _conversation_counts_by_project(*, include_archived: bool = True) -> dict[str, int]:
    """Build a compact conversation-count map keyed by project_id."""
    counts: dict[str, int] = {}

    try:
        conversation_metadata_items = list_conversations(
            include_archived=include_archived,
            limit=None,
        )
    except ConversationServiceError as exc:
        LOGGER.warning("Unable to derive project conversation counts: %s", exc)
        return counts

    for metadata in conversation_metadata_items:
        project_id = _safe_string(getattr(metadata, "project_id", None))
        if not project_id:
            continue

        counts[project_id] = counts.get(project_id, 0) + 1

    return counts


def create_project(
    *,
    name: str,
    description: str | None = None,
    status: str | None = None,
    notes_summary: str | None = None,
    state_summary: str | None = None,
) -> dict[str, Any]:
    """Create one new local project container and return its compact metadata."""
    compact_name = _derive_project_name(name)
    if not compact_name:
        raise ProjectServiceError("Project name must not be empty.")

    with _STORE_LOCK:
        project_id = new_project_id()
        record = _empty_record(
            project_id,
            name=compact_name,
            description=description,
            status=status,
            notes_summary=notes_summary,
            state_summary=state_summary,
        )
        _save_record(record)
        return dict(record["metadata"])


def get_project_metadata(project_id: str) -> dict[str, Any]:
    """Return validated compact metadata for one project container."""
    with _STORE_LOCK:
        record = _load_record(project_id)
        metadata = dict(record["metadata"])
        _assert_record_owner(_safe_string(metadata.get("owner_user_id")))
        return metadata


def list_projects(
    *,
    include_archived: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    List stored project metadata records in UI-friendly order.

    Current sort order:
    - active first
    - then most recently updated
    """
    if limit is not None and limit < 0:
        raise ProjectServiceError("Project list limit must not be negative.")

    effective_limit = None
    if limit is not None:
        effective_limit = min(limit, MAX_LIST_LIMIT)

    conversation_counts = _conversation_counts_by_project(include_archived=True)
    metadata_items: list[dict[str, Any]] = []

    with _STORE_LOCK:
        for path in _sorted_project_paths():
            try:
                record = _normalize_loaded_record(path.stem, _read_json(path))
            except ProjectServiceError as exc:
                LOGGER.warning("Skipping unreadable project record %s: %s", path.name, exc)
                continue

            metadata = dict(record["metadata"])
            active_owner = current_user_id()
            if active_owner is not None and _safe_string(metadata.get("owner_user_id")) != active_owner:
                continue
            if _safe_bool(metadata.get("archived")) and not include_archived:
                continue

            metadata["conversation_count"] = conversation_counts.get(
                str(metadata["project_id"]),
                0,
            )
            metadata_items.append(metadata)

    metadata_items.sort(
        key=lambda item: (
            _normalize_status(_safe_string(item.get("status"))) != "active",
            item.get("updated_at_utc") or "",
            item.get("created_at_utc") or "",
            item.get("project_id") or "",
        ),
        reverse=False,
    )

    metadata_items.reverse()

    if effective_limit is not None:
        metadata_items = metadata_items[:effective_limit]

    return metadata_items


def get_project_detail(
    project_id: str,
    *,
    include_archived_conversations: bool = False,
    conversation_limit: int | None = None,
) -> dict[str, Any]:
    """
    Return one project detail payload for future route/schema use.

    This keeps project detail modest for Phase 1:
    - compact metadata
    - related conversations derived from the existing conversation store
    - notes/state summaries from the project record
    """
    normalized_project_id = _validate_project_id(project_id)

    with _STORE_LOCK:
        metadata = get_project_metadata(normalized_project_id)
        related_conversations = list_project_conversations(
            normalized_project_id,
            include_archived=include_archived_conversations,
            limit=conversation_limit,
        )
        metadata["conversation_count"] = len(related_conversations)

        return {
            "project_id": normalized_project_id,
            "metadata": metadata,
            "related_conversations": related_conversations,
            "conversation_count": len(related_conversations),
            "notes_summary": metadata.get("notes_summary"),
            "state_summary": metadata.get("state_summary"),
            "continuity_summary": build_project_continuity_summary(
                normalized_project_id,
                metadata=metadata,
                related_conversations=related_conversations,
            ),
            "source_count": _safe_int(metadata.get("source_count"), default=0),
        }


def _linked_request_ids_from_conversations(
    related_conversations: list[dict[str, Any]],
) -> list[str]:
    """Collect request IDs from related conversation messages."""
    request_ids: list[str] = []
    seen: set[str] = set()

    for conversation in related_conversations:
        conversation_id = _safe_string(conversation.get("conversation_id"))
        if not conversation_id:
            continue
        try:
            thread = get_conversation_thread(conversation_id)
        except ConversationServiceError:
            continue

        messages = thread.get("messages", [])
        if not isinstance(messages, list):
            continue

        for message in messages:
            if not isinstance(message, Mapping):
                continue
            request_id = _safe_string(message.get("request_id"))
            if request_id and request_id not in seen:
                request_ids.append(request_id)
                seen.add(request_id)

    return request_ids[:MAX_CONTINUITY_ITEMS]


def _linked_artifact_summaries(project_id: str) -> list[dict[str, Any]]:
    """Collect compact artifact summaries linked to one project."""
    try:
        from app.api.artifact_service import list_artifacts
    except Exception:
        return []

    try:
        result = list_artifacts(project_id=project_id, limit=MAX_CONTINUITY_ITEMS)
    except Exception:
        return []

    summaries: list[dict[str, Any]] = []
    for summary in result.artifacts:
        payload = (
            summary.model_dump(mode="json")
            if hasattr(summary, "model_dump")
            else summary.dict()
        )
        summaries.append(
            {
                "artifact_id": payload.get("artifact_id"),
                "kind": payload.get("kind"),
                "title": payload.get("title"),
                "summary": payload.get("summary"),
                "created_at_utc": payload.get("created_at_utc"),
                "request_id": payload.get("request_id"),
                "conversation_id": payload.get("conversation_id"),
                "project_id": payload.get("project_id"),
            }
        )

    return summaries


def _linked_request_summaries(project_id: str) -> list[dict[str, Any]]:
    """Collect compact in-memory request trace summaries linked to one project."""
    try:
        from app.api.request_trace_service import list_request_trace_summaries
    except Exception:
        return []

    try:
        return list_request_trace_summaries(project_id=project_id, limit=MAX_CONTINUITY_ITEMS)
    except Exception:
        return []


def build_project_continuity_summary(
    project_id: str,
    *,
    metadata: dict[str, Any] | None = None,
    related_conversations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a compact project continuity summary with local provenance."""
    normalized_project_id = _validate_project_id(project_id)
    metadata_payload = metadata or get_project_metadata(normalized_project_id)
    conversations = (
        related_conversations
        if related_conversations is not None
        else list_project_conversations(normalized_project_id)
    )
    linked_request_ids = _linked_request_ids_from_conversations(conversations)
    linked_requests = _linked_request_summaries(normalized_project_id)
    linked_artifacts = _linked_artifact_summaries(normalized_project_id)
    linked_artifact_ids = [
        str(item.get("artifact_id"))
        for item in linked_artifacts
        if item.get("artifact_id")
    ]
    linked_evidence_packet_ids = [
        f"{item.get('request_id')}:evidence"
        for item in linked_requests
        if int(item.get("evidence_packet_count") or 0) > 0 and item.get("request_id")
    ][:MAX_CONTINUITY_ITEMS]

    latest_activity = []
    for conversation in conversations[:5]:
        latest_activity.append(
            {
                "source_kind": "conversation",
                "source_id": conversation.get("conversation_id"),
                "source_label": conversation.get("title") or "Project conversation",
                "updated_at_utc": conversation.get("updated_at_utc"),
            }
        )
    for artifact in linked_artifacts[:5]:
        latest_activity.append(
            {
                "source_kind": "artifact",
                "source_id": artifact.get("artifact_id"),
                "source_label": artifact.get("title") or "Project artifact",
                "updated_at_utc": artifact.get("created_at_utc"),
            }
        )
    latest_activity.sort(
        key=lambda item: str(item.get("updated_at_utc") or ""),
        reverse=True,
    )

    provenance = [
        {
            "source_kind": "project_metadata",
            "source_id": normalized_project_id,
            "source_label": metadata_payload.get("name") or normalized_project_id,
        },
        {
            "source_kind": "conversation_store",
            "source_id": normalized_project_id,
            "source_label": f"{len(conversations)} linked conversations",
        },
        {
            "source_kind": "artifact_store",
            "source_id": normalized_project_id,
            "source_label": f"{len(linked_artifacts)} linked artifacts",
        },
        {
            "source_kind": "request_trace_registry",
            "source_id": normalized_project_id,
            "source_label": f"{len(linked_requests)} linked request traces currently retained",
        },
    ]

    return {
        "project_id": normalized_project_id,
        "name": metadata_payload.get("name"),
        "current_state": metadata_payload.get("current_state")
        or metadata_payload.get("state_summary"),
        "latest_chunk": metadata_payload.get("latest_chunk"),
        "project_notes": metadata_payload.get("project_notes")
        or metadata_payload.get("notes_summary"),
        "recent_milestones": list(metadata_payload.get("milestones") or []),
        "decisions": list(metadata_payload.get("decisions") or []),
        "open_blockers": list(metadata_payload.get("blockers") or []),
        "next_suggested_actions": list(metadata_payload.get("next_actions") or []),
        "unresolved_questions": list(metadata_payload.get("unresolved_questions") or []),
        "corrections": list(metadata_payload.get("corrections") or []),
        "linked_conversation_ids": [
            item.get("conversation_id")
            for item in conversations
            if item.get("conversation_id")
        ],
        "linked_request_ids": linked_request_ids,
        "linked_requests": linked_requests,
        "linked_artifact_ids": linked_artifact_ids,
        "linked_artifacts": linked_artifacts,
        "linked_evidence_packet_ids": linked_evidence_packet_ids,
        "latest_activity": latest_activity[:MAX_CONTINUITY_ITEMS],
        "provenance": provenance,
        "sealed_private_memory_used": False,
        "attached_files_are_memory": False,
        "artifacts_are_memory": False,
    }


def update_project_metadata(
    project_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    notes_summary: str | None = None,
    state_summary: str | None = None,
    current_state: str | None = None,
    latest_chunk: str | None = None,
    project_notes: str | None = None,
    milestones: list[dict[str, Any]] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    blockers: list[dict[str, Any]] | None = None,
    next_actions: list[dict[str, Any]] | None = None,
    unresolved_questions: list[dict[str, Any]] | None = None,
    corrections: list[dict[str, Any]] | None = None,
    source_count: int | None = None,
    archived: bool | None = None,
) -> dict[str, Any]:
    """
    Update allowed compact metadata fields for one stored project.

    Allowed mutations are intentionally narrow:
    - name
    - description
    - status
    - notes_summary
    - state_summary
    - current_state
    - latest_chunk
    - project_notes
    - milestones
    - decisions
    - blockers
    - next_actions
    - unresolved_questions
    - corrections
    - source_count
    - archived
    """
    with _STORE_LOCK:
        record = _load_record(project_id)
        metadata_payload = dict(record["metadata"])
        _assert_record_owner(_safe_string(metadata_payload.get("owner_user_id")))

        if name is not None:
            normalized_name = _derive_project_name(name)
            metadata_payload["name"] = normalized_name
            metadata_payload["slug"] = _slugify_name(normalized_name)

        if description is not None:
            metadata_payload["description"] = _derive_description(description)

        if status is not None:
            metadata_payload["status"] = _normalize_status(status)

        if notes_summary is not None:
            metadata_payload["notes_summary"] = _derive_summary(notes_summary)

        if state_summary is not None:
            metadata_payload["state_summary"] = _derive_summary(state_summary)

        if current_state is not None:
            metadata_payload["current_state"] = _derive_continuity_text(current_state)

        if latest_chunk is not None:
            metadata_payload["latest_chunk"] = _derive_continuity_text(latest_chunk)

        if project_notes is not None:
            metadata_payload["project_notes"] = _derive_continuity_text(project_notes)

        if milestones is not None:
            metadata_payload["milestones"] = _normalize_continuity_items(
                milestones,
                default_status="complete",
            )

        if decisions is not None:
            metadata_payload["decisions"] = _normalize_continuity_items(
                decisions,
                default_status="decided",
            )

        if blockers is not None:
            metadata_payload["blockers"] = _normalize_continuity_items(
                blockers,
                default_status="blocked",
            )

        if next_actions is not None:
            metadata_payload["next_actions"] = _normalize_continuity_items(
                next_actions,
                default_status="planned",
            )

        if unresolved_questions is not None:
            metadata_payload["unresolved_questions"] = _normalize_continuity_items(
                unresolved_questions,
                default_status="open",
            )

        if corrections is not None:
            metadata_payload["corrections"] = _normalize_continuity_items(
                corrections,
                default_status="corrective",
            )

        if source_count is not None:
            metadata_payload["source_count"] = _safe_int(source_count, default=0)

        if archived is not None:
            metadata_payload["archived"] = bool(archived)
            metadata_payload["status"] = _normalize_status(
                _safe_string(metadata_payload.get("status")),
                archived=bool(archived),
            )

        metadata_payload["updated_at_utc"] = _utc_now_iso()

        normalized_metadata = _build_metadata_dict(metadata_payload)
        record["metadata"] = normalized_metadata
        _save_record(record)

        return normalized_metadata


def select_active_project(project_id: str | None) -> dict[str, Any]:
    """
    Persist the active project selection locally.

    Passing None clears the active project selection.
    """
    with _STORE_LOCK:
        if project_id is not None:
            record = _load_record(project_id)
            _assert_record_owner(_safe_string(record["metadata"].get("owner_user_id")))

        selection = _write_active_selection(project_id)
        return dict(selection)


def get_active_project_selection() -> dict[str, Any]:
    """Return the current active-project selection payload."""
    with _STORE_LOCK:
        return dict(_read_active_selection())


def delete_project(project_id: str) -> dict[str, Any]:
    """
    Delete one stored project container from the local filesystem.

    This stays intentionally narrow:
    - validate the project identifier
    - ensure the target file exists
    - delete the JSON record
    - clear active selection if needed
    - return a compact result payload
    """
    with _STORE_LOCK:
        resolved_id = _validate_project_id(project_id)
        path = _project_path(resolved_id)

        if not path.exists():
            raise ProjectNotFoundError(f"Project '{resolved_id}' does not exist.")

        _assert_record_owner(
            _safe_string(_load_record(resolved_id)["metadata"].get("owner_user_id"))
        )

        try:
            path.unlink()
        except FileNotFoundError as exc:
            raise ProjectNotFoundError(
                f"Project '{resolved_id}' does not exist."
            ) from exc
        except OSError as exc:
            raise ProjectServiceError(
                f"Unable to delete project record '{path.name}': {exc}"
            ) from exc

        selection = _read_active_selection()
        if selection.get("active_project_id") == resolved_id:
            _write_active_selection(None)

        return {
            "project_id": resolved_id,
            "deleted": True,
        }


__all__ = (
    "ProjectNotFoundError",
    "ProjectServiceError",
    "ProjectStoreCorruptError",
    "build_project_continuity_summary",
    "create_project",
    "delete_project",
    "get_active_project_selection",
    "get_project_detail",
    "get_project_metadata",
    "list_project_conversations",
    "list_projects",
    "new_project_id",
    "select_active_project",
    "update_project_metadata",
)
