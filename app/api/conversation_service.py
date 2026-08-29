"""
Conversation storage/service organ for the Elysia local API bridge.

This module is the local persistence and retrieval layer for Stage 8 conversation
list/thread support.

It should stay in this lane:
- create and normalize conversation containers
- persist compact metadata plus message history locally
- list conversations for later route surfaces
- load a single conversation thread
- record chat exchanges coming back from the governed /chat/send path
- mutate compact conversation metadata locally when explicitly requested
- delete one stored conversation container locally when explicitly requested

It should not become:
- a route module
- a response-envelope builder
- a runtime/invoker layer
- a governance layer
- a capability-reporting layer
- a full database abstraction fantasy

Current storage posture:
- local filesystem only
- one JSON file per conversation
- atomic writes
- modest schema discipline
- robust enough for Stage 8, without pretending to be the final store
"""

from __future__ import annotations

import json
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

from app.api.schemas.conversation import ConversationMetadata
from app.install.paths import resolve_elysia_paths

LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONVERSATIONS_DIR = resolve_elysia_paths().conversation_dir

STORAGE_VERSION = 1
CONVERSATION_ID_PREFIX = "conv"
MESSAGE_ID_PREFIX = "msg"

MAX_TITLE_LENGTH = 80
MAX_PREVIEW_LENGTH = 160
MAX_LIST_LIMIT = 500

_CONVERSATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_STORE_LOCK = threading.RLock()


class ConversationServiceError(Exception):
    """Base exception for conversation service failures."""


class ConversationNotFoundError(ConversationServiceError):
    """Raised when a requested conversation container does not exist."""


class ConversationStoreCorruptError(ConversationServiceError):
    """Raised when a stored conversation record cannot be interpreted safely."""


def _assert_record_owner(owner_user_id: str | None) -> None:
    try:
        assert_domain_owner(owner_user_id)
    except DomainOwnershipError as exc:
        raise ConversationNotFoundError("The conversation is unavailable to this account.") from exc


def _validate_project_reference(project_id: str | None) -> str | None:
    """Prevent new conversation→project links from becoming dangling."""
    normalized = _safe_string(project_id)
    if not normalized:
        return None
    try:
        from app.api.project_service import get_project_metadata

        get_project_metadata(normalized)
    except Exception as exc:
        raise ConversationServiceError(
            "The linked project does not exist or is unavailable to this account."
        ) from exc
    return normalized


class ConversationMessageRecord(TypedDict):
    message_id: str
    conversation_id: str
    role: str
    content: str
    created_at_utc: str
    request_id: NotRequired[str | None]
    invocation_status: NotRequired[str | None]
    response_source: NotRequired[str | None]
    selected_role: NotRequired[str | None]
    selected_runtime: NotRequired[str | None]
    selected_model_runtime_tag: NotRequired[str | None]
    used_fallback: NotRequired[bool]
    fallback_from: NotRequired[str | None]
    fallback_to: NotRequired[str | None]
    approval_needed: NotRequired[bool]
    approval_state: NotRequired[str | None]
    locality_state: NotRequired[str | None]
    capability_state: NotRequired[str | None]
    blocked: NotRequired[bool]
    degraded: NotRequired[bool]
    error: NotRequired[str | None]
    warnings: NotRequired[list[str]]
    caveats: NotRequired[list[str]]


class ConversationRecord(TypedDict):
    storage_version: int
    metadata: dict[str, Any]
    messages: list[ConversationMessageRecord]


def _utc_now_iso() -> str:
    """Return a compact UTC timestamp string with trailing Z."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_store_dir() -> None:
    """Ensure the conversation storage directory exists."""
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)


def _new_compact_id(prefix: str) -> str:
    """Create a sortable UUIDv7 identifier for local storage surfaces."""
    return new_id(prefix)


def new_conversation_id() -> str:
    """Create a new conversation identifier."""
    return _new_compact_id(CONVERSATION_ID_PREFIX)


def new_message_id() -> str:
    """Create a new message identifier."""
    return _new_compact_id(MESSAGE_ID_PREFIX)


def _validate_conversation_id(conversation_id: str) -> str:
    """
    Validate and normalize one conversation identifier.

    This stays intentionally modest: the service should reject obviously unsafe
    identifiers without pretending to solve every future identity question.
    """
    normalized = conversation_id.strip()
    if not normalized:
        raise ConversationServiceError("Conversation identifier must not be empty.")

    if not _CONVERSATION_ID_PATTERN.fullmatch(normalized):
        raise ConversationServiceError(
            "Conversation identifier contains unsupported characters."
        )

    return normalized


def _conversation_path(conversation_id: str) -> Path:
    """Return the local JSON storage path for one conversation."""
    safe_id = _validate_conversation_id(conversation_id)
    return CONVERSATIONS_DIR / f"{safe_id}.json"


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


def _derive_title_from_message(message: str | None) -> str:
    """Build a modest human-facing title from the first meaningful user message."""
    title = _truncate_text(message, MAX_TITLE_LENGTH)
    return title or "New conversation"


def _is_placeholder_title(title: str | None) -> bool:
    """
    Determine whether a stored title is still just the generic placeholder.

    This lets the first real user message replace "New conversation" without
    disturbing already-meaningful titles later on.
    """
    normalized = _compact_text(title)
    if not normalized:
        return True

    return normalized.casefold() == "new conversation"


def _derive_preview(user_message: str | None, response_text: str | None) -> str | None:
    """
    Build a short preview for conversation list/header use.

    Prefer the assistant response when present, because it is often the more useful
    summary of the most recent exchange.
    """
    preview_source = response_text or user_message
    preview = _truncate_text(preview_source, MAX_PREVIEW_LENGTH)
    return preview or None


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


def _normalize_capability_state(
    raw_state: str | None,
    *,
    blocked: bool = False,
    degraded: bool = False,
) -> str:
    """Normalize capability-state truth to the known trust-language family."""
    normalized = _safe_string(raw_state)
    if normalized:
        return normalized

    if blocked:
        return "blocked"

    if degraded:
        return "degraded"

    return "live"


def _normalize_locality_state(raw_state: str | None) -> str:
    """Normalize locality-state truth."""
    normalized = _safe_string(raw_state)
    return normalized or "local"


def _normalize_approval_state(
    raw_state: str | None,
    *,
    approval_needed: bool = False,
) -> str:
    """Normalize approval-state truth."""
    normalized = _safe_string(raw_state)
    if normalized:
        return normalized

    return "needed" if approval_needed else "not_needed"


def _model_to_dict(model: Any) -> dict[str, Any]:
    """Support pydantic v1/v2 style dumping without binding the service too tightly."""
    dump_method = getattr(model, "model_dump", None)
    if callable(dump_method):
        return dump_method(mode="json")

    dict_method = getattr(model, "dict", None)
    if callable(dict_method):
        return dict_method()

    if isinstance(model, dict):
        return dict(model)

    raise ConversationServiceError("Unable to serialize model into dictionary form.")


def _build_metadata_model(data: dict[str, Any]) -> ConversationMetadata:
    """Validate one metadata payload through the shared schema model."""
    try:
        return ConversationMetadata(**data)
    except Exception as exc:
        raise ConversationStoreCorruptError(
            f"Conversation metadata is invalid or incomplete: {exc}"
        ) from exc


def _empty_record(
    conversation_id: str,
    *,
    title: str | None = None,
    project_id: str | None = None,
    current_mode: str | None = None,
    current_role: str | None = None,
) -> ConversationRecord:
    """Create an empty conversation record with valid compact metadata."""
    now = _utc_now_iso()

    metadata = ConversationMetadata(
        conversation_id=conversation_id,
        owner_user_id=current_user_id(),
        title=title or "New conversation",
        created_at_utc=now,
        updated_at_utc=now,
        last_message_preview=None,
        message_count=0,
        current_mode=current_mode,
        current_role=current_role,
        capability_state="live",
        locality="local",
        approval_state="not_needed",
        project_id=project_id,
        archived=False,
        pinned=False,
        conversation_state="active",
    )

    return {
        "storage_version": STORAGE_VERSION,
        "metadata": _model_to_dict(metadata),
        "messages": [],
    }


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
        raise ConversationNotFoundError(
            f"Conversation '{path.stem}' does not exist."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ConversationStoreCorruptError(
            f"Conversation record '{path.name}' is not valid JSON: {exc}"
        ) from exc
    except OSError as exc:
        raise ConversationServiceError(
            f"Unable to read conversation record '{path.name}': {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise ConversationStoreCorruptError(
            f"Conversation record '{path.name}' is not a JSON object."
        )

    return payload


def _normalize_loaded_record(
    conversation_id: str,
    payload: dict[str, Any],
) -> ConversationRecord:
    """
    Normalize a loaded on-disk record into the service's internal shape.

    This accepts the intended nested shape and one modest migration fallback where
    metadata fields were stored top-level alongside messages.
    """
    storage_version = int(payload.get("storage_version", STORAGE_VERSION))
    raw_messages = payload.get("messages", [])

    if not isinstance(raw_messages, list):
        raise ConversationStoreCorruptError(
            f"Conversation '{conversation_id}' stores non-list messages."
        )

    raw_metadata = payload.get("metadata")
    if isinstance(raw_metadata, Mapping):
        metadata_payload = dict(raw_metadata)
    else:
        metadata_payload = {
            key: payload.get(key)
            for key in (
                "conversation_id",
                "owner_user_id",
                "title",
                "created_at_utc",
                "updated_at_utc",
                "last_message_preview",
                "message_count",
                "current_mode",
                "current_role",
                "capability_state",
                "locality",
                "approval_state",
                "project_id",
                "archived",
                "pinned",
                "conversation_state",
            )
            if key in payload
        }

    metadata_payload["conversation_id"] = conversation_id
    metadata_model = _build_metadata_model(metadata_payload)

    normalized_messages: list[ConversationMessageRecord] = []
    for index, raw_message in enumerate(raw_messages):
        if not isinstance(raw_message, Mapping):
            raise ConversationStoreCorruptError(
                f"Conversation '{conversation_id}' contains a non-object message at index {index}."
            )

        role = _safe_string(raw_message.get("role")) or "unknown"
        content = _safe_string(raw_message.get("content")) or ""

        if not content:
            raise ConversationStoreCorruptError(
                f"Conversation '{conversation_id}' contains an empty message at index {index}."
            )

        normalized_message: ConversationMessageRecord = {
            "message_id": _safe_string(raw_message.get("message_id")) or new_message_id(),
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "created_at_utc": _safe_string(raw_message.get("created_at_utc"))
            or _safe_string(raw_message.get("created_at"))
            or metadata_model.updated_at_utc
            or _utc_now_iso(),
        }

        for optional_key in (
            "request_id",
            "invocation_status",
            "response_source",
            "selected_role",
            "selected_runtime",
            "selected_model_runtime_tag",
            "fallback_from",
            "fallback_to",
            "approval_state",
            "locality_state",
            "capability_state",
            "error",
        ):
            optional_value = _safe_string(raw_message.get(optional_key))
            if optional_value is not None:
                normalized_message[optional_key] = optional_value

        for bool_key in ("used_fallback", "approval_needed", "blocked", "degraded"):
            if bool_key in raw_message:
                normalized_message[bool_key] = _safe_bool(raw_message.get(bool_key))

        for list_key in ("warnings", "caveats"):
            raw_list = raw_message.get(list_key)
            if isinstance(raw_list, list):
                normalized_message[list_key] = [
                    _compact_text(item) for item in raw_list if _compact_text(item)
                ]

        normalized_messages.append(normalized_message)

    metadata_dict = _model_to_dict(metadata_model)
    if metadata_dict.get("message_count") is None:
        metadata_dict["message_count"] = len(normalized_messages)

    return {
        "storage_version": storage_version,
        "metadata": metadata_dict,
        "messages": normalized_messages,
    }


def _load_record(conversation_id: str) -> ConversationRecord:
    """Load and normalize one conversation record from local storage."""
    path = _conversation_path(conversation_id)
    payload = _read_json(path)
    return _normalize_loaded_record(conversation_id, payload)


def _save_record(record: ConversationRecord) -> None:
    """Persist one normalized conversation record."""
    metadata = record.get("metadata", {})
    conversation_id = _safe_string(metadata.get("conversation_id"))
    if not conversation_id:
        raise ConversationServiceError("Cannot save conversation record without conversation_id.")

    path = _conversation_path(conversation_id)
    _write_json_atomic(path, record)


def _last_message_role(messages: list[ConversationMessageRecord]) -> str | None:
    """Return the role of the most recent message when available."""
    if not messages:
        return None

    return _safe_string(messages[-1].get("role"))


def _sorted_record_paths() -> list[Path]:
    """Return all stored conversation paths in a stable local order."""
    _ensure_store_dir()
    return sorted(
        CONVERSATIONS_DIR.glob("*.json"),
        key=lambda path: path.name.lower(),
    )


def ensure_conversation(
    conversation_id: str | None = None,
    *,
    title: str | None = None,
    project_id: str | None = None,
    requested_mode: str | None = None,
    requested_role: str | None = None,
) -> ConversationMetadata:
    """
    Ensure one conversation container exists locally and return its metadata.

    If a conversation_id is supplied and already exists, return its metadata.
    If a conversation_id is supplied and does not exist yet, create it.
    If no conversation_id is supplied, create a fresh container.
    """
    with _STORE_LOCK:
        validated_project_id = _validate_project_reference(project_id)
        resolved_id = _validate_conversation_id(conversation_id) if conversation_id else new_conversation_id()
        path = _conversation_path(resolved_id)

        if path.exists():
            return get_conversation_metadata(resolved_id)

        record = _empty_record(
            resolved_id,
            title=title,
            project_id=validated_project_id,
            current_mode=requested_mode,
            current_role=requested_role,
        )
        _save_record(record)
        return _build_metadata_model(record["metadata"])


def get_conversation_metadata(conversation_id: str) -> ConversationMetadata:
    """Return validated compact metadata for one conversation container."""
    with _STORE_LOCK:
        record = _load_record(conversation_id)
        metadata = _build_metadata_model(record["metadata"])
        _assert_record_owner(metadata.owner_user_id)
        return metadata


def list_conversations(
    *,
    include_archived: bool = False,
    limit: int | None = None,
) -> list[ConversationMetadata]:
    """
    List stored conversation metadata records in UI-friendly order.

    Current sort order:
    - pinned first
    - then most recently updated
    """
    if limit is not None and limit < 0:
        raise ConversationServiceError("Conversation list limit must not be negative.")

    effective_limit = None
    if limit is not None:
        effective_limit = min(limit, MAX_LIST_LIMIT)

    metadata_items: list[ConversationMetadata] = []

    with _STORE_LOCK:
        for path in _sorted_record_paths():
            try:
                record = _normalize_loaded_record(path.stem, _read_json(path))
                metadata = _build_metadata_model(record["metadata"])
            except ConversationServiceError as exc:
                LOGGER.warning("Skipping unreadable conversation record %s: %s", path.name, exc)
                continue

            if metadata.archived and not include_archived:
                continue
            active_owner = current_user_id()
            if active_owner is not None and metadata.owner_user_id != active_owner:
                continue

            metadata_items.append(metadata)

    metadata_items.sort(
        key=lambda item: (
            not bool(item.pinned),
            item.updated_at_utc or "",
            item.created_at_utc or "",
            item.conversation_id,
        ),
        reverse=False,
    )

    # The key above puts False before True, so invert pinned/updated ordering manually.
    metadata_items.sort(
        key=lambda item: (
            bool(item.pinned),
            item.updated_at_utc or "",
            item.created_at_utc or "",
        ),
        reverse=True,
    )

    if effective_limit is not None:
        metadata_items = metadata_items[:effective_limit]

    return metadata_items


def get_conversation_thread(conversation_id: str) -> dict[str, Any]:
    """
    Return one conversation thread payload for future route/schema use.

    The service intentionally returns plain data here so later route-level schema
    work can shape the exact endpoint transport without forcing this module to
    own endpoint-specific contracts.
    """
    with _STORE_LOCK:
        record = _load_record(conversation_id)
        metadata = _build_metadata_model(record["metadata"])
        _assert_record_owner(metadata.owner_user_id)

        return {
            "conversation_id": metadata.conversation_id,
            "metadata": _model_to_dict(metadata),
            "messages": list(record["messages"]),
            "last_message_role": _last_message_role(record["messages"]),
            "message_count": len(record["messages"]),
            "storage_version": record["storage_version"],
        }


def update_conversation_metadata(
    conversation_id: str,
    *,
    title: str | None = None,
    project_id: str | None = None,
    pinned: bool | None = None,
    archived: bool | None = None,
) -> ConversationMetadata:
    """
    Update allowed compact metadata fields for one stored conversation.

    Allowed mutations are intentionally narrow:
    - title
    - project_id
    - pinned
    - archived

    This function:
    - loads the existing record
    - patches only allowed fields
    - updates updated_at_utc
    - keeps conversation_state aligned with archived
    - validates via the shared metadata schema
    - persists atomically
    - returns the updated compact metadata
    """
    with _STORE_LOCK:
        record = _load_record(conversation_id)
        metadata_payload = dict(record["metadata"])
        _assert_record_owner(_safe_string(metadata_payload.get("owner_user_id")))

        if title is not None:
            metadata_payload["title"] = _derive_title_from_message(title)

        if project_id is not None:
            metadata_payload["project_id"] = _validate_project_reference(project_id)

        if pinned is not None:
            metadata_payload["pinned"] = bool(pinned)

        if archived is not None:
            metadata_payload["archived"] = bool(archived)

        metadata_payload["updated_at_utc"] = _utc_now_iso()
        metadata_payload["conversation_state"] = (
            "archived" if _safe_bool(metadata_payload.get("archived")) else "active"
        )

        validated_metadata = _build_metadata_model(metadata_payload)
        record["metadata"] = _model_to_dict(validated_metadata)
        _save_record(record)

        return validated_metadata


def delete_conversation(conversation_id: str) -> dict[str, Any]:
    """
    Delete one stored conversation container from the local filesystem.

    This stays intentionally narrow:
    - validate the conversation identifier
    - ensure the target file exists
    - delete the JSON record
    - return a compact result payload

    It does not build envelopes, route responses, or frontend behavior.
    """
    with _STORE_LOCK:
        resolved_id = _validate_conversation_id(conversation_id)
        path = _conversation_path(resolved_id)

        if not path.exists():
            raise ConversationNotFoundError(
                f"Conversation '{resolved_id}' does not exist."
            )

        _assert_record_owner(
            _safe_string(_load_record(resolved_id)["metadata"].get("owner_user_id"))
        )

        try:
            path.unlink()
        except FileNotFoundError as exc:
            raise ConversationNotFoundError(
                f"Conversation '{resolved_id}' does not exist."
            ) from exc
        except OSError as exc:
            raise ConversationServiceError(
                f"Unable to delete conversation record '{path.name}': {exc}"
            ) from exc

        return {
            "conversation_id": resolved_id,
            "deleted": True,
        }


def _append_message(
    messages: list[ConversationMessageRecord],
    *,
    conversation_id: str,
    role: str,
    content: str,
    created_at_utc: str,
    request_id: str | None = None,
    invocation_status: str | None = None,
    response_source: str | None = None,
    selected_role: str | None = None,
    selected_runtime: str | None = None,
    selected_model_runtime_tag: str | None = None,
    used_fallback: bool | None = None,
    fallback_from: str | None = None,
    fallback_to: str | None = None,
    approval_needed: bool | None = None,
    approval_state: str | None = None,
    locality_state: str | None = None,
    capability_state: str | None = None,
    blocked: bool | None = None,
    degraded: bool | None = None,
    error: str | None = None,
    warnings: list[str] | None = None,
    caveats: list[str] | None = None,
) -> ConversationMessageRecord:
    """Append one normalized message record to the thread."""
    message: ConversationMessageRecord = {
        "message_id": new_message_id(),
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "created_at_utc": created_at_utc,
    }

    if request_id is not None:
        message["request_id"] = request_id
    if invocation_status is not None:
        message["invocation_status"] = invocation_status
    if response_source is not None:
        message["response_source"] = response_source
    if selected_role is not None:
        message["selected_role"] = selected_role
    if selected_runtime is not None:
        message["selected_runtime"] = selected_runtime
    if selected_model_runtime_tag is not None:
        message["selected_model_runtime_tag"] = selected_model_runtime_tag
    if used_fallback is not None:
        message["used_fallback"] = used_fallback
    if fallback_from is not None:
        message["fallback_from"] = fallback_from
    if fallback_to is not None:
        message["fallback_to"] = fallback_to
    if approval_needed is not None:
        message["approval_needed"] = approval_needed
    if approval_state is not None:
        message["approval_state"] = approval_state
    if locality_state is not None:
        message["locality_state"] = locality_state
    if capability_state is not None:
        message["capability_state"] = capability_state
    if blocked is not None:
        message["blocked"] = blocked
    if degraded is not None:
        message["degraded"] = degraded
    if error is not None:
        message["error"] = error
    if warnings:
        message["warnings"] = [_compact_text(item) for item in warnings if _compact_text(item)]
    if caveats:
        message["caveats"] = [_compact_text(item) for item in caveats if _compact_text(item)]

    messages.append(message)
    return message


def record_chat_exchange(
    *,
    conversation_id: str | None,
    user_message: str,
    response_text: str,
    request_id: str | None = None,
    project_id: str | None = None,
    requested_mode: str | None = None,
    selected_role: str | None = None,
    selected_runtime: str | None = None,
    selected_model_runtime_tag: str | None = None,
    invocation_status: str | None = None,
    response_source: str | None = None,
    used_fallback: bool = False,
    fallback_from: str | None = None,
    fallback_to: str | None = None,
    approval_needed: bool = False,
    approval_state: str | None = None,
    locality_state: str | None = None,
    capability_state: str | None = None,
    blocked: bool = False,
    degraded: bool = False,
    caveats: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    """
    Persist one user/assistant exchange into the local conversation store.

    This is the core Stage 8 persistence path that future chat/send routing should
    call after the governed runtime bridge returns.
    """
    compact_user_message = _compact_text(user_message)
    compact_response_text = _compact_text(response_text)

    if not compact_user_message:
        raise ConversationServiceError("Cannot record chat exchange without a user message.")

    if not compact_response_text:
        raise ConversationServiceError(
            "Cannot record chat exchange without a response text payload."
        )

    with _STORE_LOCK:
        validated_project_id = _validate_project_reference(project_id)
        metadata = ensure_conversation(
            conversation_id=conversation_id,
            title=_derive_title_from_message(compact_user_message),
            project_id=validated_project_id,
            requested_mode=requested_mode,
            requested_role=selected_role,
        )
        record = _load_record(metadata.conversation_id)
        messages = record["messages"]

        timestamp = _utc_now_iso()

        user_record = _append_message(
            messages,
            conversation_id=metadata.conversation_id,
            role="user",
            content=compact_user_message,
            created_at_utc=timestamp,
            request_id=request_id,
        )

        assistant_record = _append_message(
            messages,
            conversation_id=metadata.conversation_id,
            role="assistant",
            content=compact_response_text,
            created_at_utc=timestamp,
            request_id=request_id,
            invocation_status=_safe_string(invocation_status),
            response_source=_safe_string(response_source),
            selected_role=_safe_string(selected_role),
            selected_runtime=_safe_string(selected_runtime),
            selected_model_runtime_tag=_safe_string(selected_model_runtime_tag),
            used_fallback=bool(used_fallback),
            fallback_from=_safe_string(fallback_from),
            fallback_to=_safe_string(fallback_to),
            approval_needed=bool(approval_needed),
            approval_state=_normalize_approval_state(
                _safe_string(approval_state),
                approval_needed=approval_needed,
            ),
            locality_state=_normalize_locality_state(_safe_string(locality_state)),
            capability_state=_normalize_capability_state(
                _safe_string(capability_state),
                blocked=blocked,
                degraded=degraded,
            ),
            blocked=bool(blocked),
            degraded=bool(degraded),
            error=(errors[0] if errors else None),
            warnings=warnings,
            caveats=caveats,
        )

        metadata_payload = dict(record["metadata"])
        if _is_placeholder_title(metadata_payload.get("title")):
            metadata_payload["title"] = _derive_title_from_message(compact_user_message)
        metadata_payload["updated_at_utc"] = timestamp
        metadata_payload["last_message_preview"] = _derive_preview(
            compact_user_message,
            compact_response_text,
        )
        metadata_payload["message_count"] = len(messages)
        metadata_payload["current_mode"] = _safe_string(requested_mode) or metadata_payload.get(
            "current_mode"
        )
        metadata_payload["current_role"] = _safe_string(selected_role) or metadata_payload.get(
            "current_role"
        )
        metadata_payload["capability_state"] = _normalize_capability_state(
            _safe_string(capability_state),
            blocked=blocked,
            degraded=degraded,
        )
        metadata_payload["locality"] = _normalize_locality_state(_safe_string(locality_state))
        metadata_payload["approval_state"] = _normalize_approval_state(
            _safe_string(approval_state),
            approval_needed=approval_needed,
        )
        metadata_payload["project_id"] = validated_project_id or metadata_payload.get(
            "project_id"
        )
        metadata_payload["conversation_state"] = (
            "archived" if _safe_bool(metadata_payload.get("archived")) else "active"
        )

        validated_metadata = _build_metadata_model(metadata_payload)
        record["metadata"] = _model_to_dict(validated_metadata)
        _save_record(record)

        return {
            "conversation_id": validated_metadata.conversation_id,
            "metadata": _model_to_dict(validated_metadata),
            "user_message": user_record,
            "assistant_message": assistant_record,
            "messages": list(messages),
        }


def record_chat_exchange_from_bridge_result(
    *,
    request_payload: Mapping[str, Any],
    bridge_result: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Convenience adapter for persisting one /chat/send result.

    This keeps future chat route logic thin: it can hand the original request and
    returned bridge envelope into this service instead of re-deriving every field.
    """
    if not isinstance(request_payload, Mapping):
        raise ConversationServiceError("request_payload must be a mapping.")

    if not isinstance(bridge_result, Mapping):
        raise ConversationServiceError("bridge_result must be a mapping.")

    data = bridge_result.get("data")
    if not isinstance(data, Mapping):
        raise ConversationServiceError("bridge_result must contain a mapping data payload.")

    status = _safe_string(bridge_result.get("status"))
    capability_state = _safe_string(bridge_result.get("capability_state"))
    approval_state = _safe_string(bridge_result.get("approval_state"))
    locality_state = _safe_string(
        bridge_result.get("locality_state") or bridge_result.get("locality")
    )

    blocked = status == "blocked" or capability_state == "blocked"
    degraded = status in {"degraded", "unavailable"} or capability_state in {
        "degraded",
        "unavailable",
    }

    response_text = _safe_string(data.get("response_text")) or ""
    user_message = _safe_string(request_payload.get("message")) or _safe_string(
        data.get("user_message")
    )

    if not user_message:
        raise ConversationServiceError("Bridge result persistence requires a user message.")

    if not response_text:
        raise ConversationServiceError("Bridge result persistence requires response_text.")

    return record_chat_exchange(
        conversation_id=_safe_string(data.get("conversation_id"))
        or _safe_string(request_payload.get("conversation_id")),
        user_message=user_message,
        response_text=response_text,
        request_id=_safe_string(bridge_result.get("request_id")),
        project_id=_safe_string(data.get("project_id"))
        or _safe_string(request_payload.get("project_id")),
        requested_mode=_safe_string(request_payload.get("requested_mode")),
        selected_role=_safe_string(data.get("selected_model_role")),
        selected_runtime=_safe_string(data.get("selected_runtime")),
        selected_model_runtime_tag=_safe_string(data.get("selected_model_runtime_tag")),
        invocation_status=_safe_string(data.get("invocation_status")),
        response_source=_safe_string(data.get("response_source")),
        used_fallback=_safe_bool(data.get("used_fallback")),
        fallback_from=_safe_string(data.get("fallback_from")),
        fallback_to=_safe_string(data.get("fallback_to")),
        approval_needed=_safe_bool(data.get("approval_needed")),
        approval_state=approval_state,
        locality_state=locality_state,
        capability_state=capability_state,
        blocked=blocked,
        degraded=degraded,
        caveats=(
            list(data.get("caveats"))
            if isinstance(data.get("caveats"), list)
            else None
        ),
        warnings=(
            list(bridge_result.get("warnings"))
            if isinstance(bridge_result.get("warnings"), list)
            else None
        ),
        errors=(
            list(bridge_result.get("errors"))
            if isinstance(bridge_result.get("errors"), list)
            else None
        ),
    )


__all__ = (
    "ConversationNotFoundError",
    "ConversationServiceError",
    "ConversationStoreCorruptError",
    "delete_conversation",
    "ensure_conversation",
    "get_conversation_metadata",
    "get_conversation_thread",
    "list_conversations",
    "new_conversation_id",
    "record_chat_exchange",
    "record_chat_exchange_from_bridge_result",
    "update_conversation_metadata",
)
