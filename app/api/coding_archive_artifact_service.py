"""Local-only full ArchiveForge artifacts and compact receipts."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.api.project_paths import data_path
from app.api.schemas.archive import ArchiveManifestArtifact


DEFAULT_ARCHIVE_ARTIFACT_ROOT = data_path("artifacts", "archive")


def archive_artifact_root() -> Path:
    configured = os.environ.get("ELYSIA_ARCHIVE_ARTIFACT_ROOT", "").strip()
    return (Path(configured).expanduser() if configured else DEFAULT_ARCHIVE_ARTIFACT_ROOT).resolve(strict=False)


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def create_archive_artifact(artifact_kind: str, payload: dict[str, Any]) -> ArchiveManifestArtifact:
    safe_kind = "".join(character for character in artifact_kind if character.isalnum() or character in {"_", "-"})
    if not safe_kind:
        raise ValueError("archive_artifact_kind_required")
    artifact_id = f"archive_{safe_kind}_{uuid4().hex[:16]}"
    record = {
        "artifact_id": artifact_id,
        "artifact_kind": safe_kind,
        "local_only": True,
        "memory_posture": "not_memory",
        "network_used": False,
        "payload": payload,
    }
    raw = _canonical_bytes(record)
    digest = sha256(raw).hexdigest()
    root = archive_artifact_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    path = root / f"{artifact_id}.json"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
    except Exception:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise
    return ArchiveManifestArtifact(
        artifact_id=artifact_id,
        artifact_kind=safe_kind,
        sha256=digest,
        size_bytes=len(raw),
    )


def get_archive_artifact(artifact_id: str) -> dict[str, Any] | None:
    safe_id = "".join(character for character in artifact_id if character.isalnum() or character in {"_", "-"})
    if not safe_id or safe_id != artifact_id or not safe_id.startswith("archive_"):
        return None
    path = archive_artifact_root() / f"{safe_id}.json"
    if not path.is_file() or path.is_symlink():
        return None
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


__all__ = (
    "DEFAULT_ARCHIVE_ARTIFACT_ROOT",
    "archive_artifact_root",
    "create_archive_artifact",
    "get_archive_artifact",
)
