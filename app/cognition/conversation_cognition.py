"""Derived, provenance-preserving conversation compaction.

Conversation JSON remains canonical. These summaries are rebuildable cache
objects and never become semantic Memory without an explicit governed action.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from app.install.paths import ElysiaPaths, resolve_elysia_paths


SUMMARY_SCHEMA_VERSION = "conversation-summary-v1"
SUMMARY_GENERATOR = "elysia-deterministic-compactor"
SUMMARY_GENERATOR_VERSION = "1.0"
SEGMENT_SIZE = 12
_KEY_CUES = re.compile(
    r"\b(decid(?:e|ed|ion)|must|constraint|cannot|don't|do not|remember|"
    r"correct(?:ion|ed)?|instead|next action|todo|unresolved|question|blocked|"
    r"commit(?:ment|ted)?|require(?:ment|d)?)\b",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _owner_namespace(owner_user_id: str | None) -> str:
    return sha256(str(owner_user_id or "anonymous-local").encode()).hexdigest()[:24]


def _summary_path(
    conversation_id: str,
    owner_user_id: str | None,
    *,
    paths: ElysiaPaths | None = None,
) -> Path:
    resolved = paths or resolve_elysia_paths()
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", conversation_id)
    return resolved.conversation_summary_dir / _owner_namespace(owner_user_id) / f"{safe_id}.json"


def _compact(text: Any, limit: int = 420) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _segment_summary(messages: list[dict[str, Any]]) -> tuple[str, list[str]]:
    important: list[str] = []
    fallback: list[str] = []
    for message in messages:
        content = _compact(message.get("content"), 360)
        if not content:
            continue
        line = f"{str(message.get('role') or 'unknown').title()}: {content}"
        fallback.append(line)
        if _KEY_CUES.search(content):
            important.append(line)
    selected = important[:6] or fallback[-4:]
    return "\n".join(f"- {line}" for line in selected), [
        str(message.get("message_id"))
        for message in messages
        if message.get("message_id")
    ]


def build_conversation_hierarchy(
    thread: dict[str, Any],
    *,
    owner_user_id: str | None = None,
    generator_model: str | None = None,
    paths: ElysiaPaths | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    metadata = dict(thread.get("metadata") or {})
    messages = [dict(item) for item in thread.get("messages", []) if isinstance(item, dict)]
    conversation_id = str(metadata.get("conversation_id") or thread.get("conversation_id") or "")
    digest = sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    path = _summary_path(conversation_id, owner_user_id, paths=paths)

    if path.is_file():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("transcript_digest") == digest:
                return cached
        except (OSError, json.JSONDecodeError):
            pass

    generated_at = _now()
    generator = {
        "name": SUMMARY_GENERATOR,
        "version": SUMMARY_GENERATOR_VERSION,
        "model_runtime_tag": generator_model or "deterministic-no-model",
    }
    segments: list[dict[str, Any]] = []
    for start in range(0, len(messages), SEGMENT_SIZE):
        group = messages[start : start + SEGMENT_SIZE]
        summary, message_ids = _segment_summary(group)
        if not summary:
            continue
        segments.append(
            {
                "segment_id": f"{conversation_id}:segment:{start // SEGMENT_SIZE + 1}",
                "message_ids": message_ids,
                "summary": summary,
                "summary_digest": sha256(summary.encode("utf-8")).hexdigest(),
                "summary_schema_version": SUMMARY_SCHEMA_VERSION,
                "generator": generator,
                "generated_at_utc": generated_at,
                "starts_at": group[0].get("created_at_utc") if group else None,
                "ends_at": group[-1].get("created_at_utc") if group else None,
            }
        )

    overview_lines = [
        _compact(segment["summary"].replace("\n", " "), 500)
        for segment in segments[-6:]
    ]
    payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "conversation_id": conversation_id,
        "owner_user_id_hash": _owner_namespace(owner_user_id),
        "transcript_digest": digest,
        "message_count": len(messages),
        "segments": segments,
        "overview": "\n".join(f"- {line}" for line in overview_lines),
        "overview_digest": sha256("\n".join(overview_lines).encode("utf-8")).hexdigest(),
        "generator": generator,
        "derived": True,
        "approved_semantic_memory": False,
        "approved_for_persistent_fts": False,
        "generated_at_utc": generated_at,
    }
    if persist and conversation_id:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp_path = Path(temp_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temp_path.replace(path)
            path.chmod(0o600)
        finally:
            temp_path.unlink(missing_ok=True)
    return payload


__all__ = ("build_conversation_hierarchy", "SUMMARY_SCHEMA_VERSION")
