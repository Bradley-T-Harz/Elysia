"""Private local-only detail artifacts for DatabaseForge and BinaryForge."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from app.api.project_paths import data_path
from app.api.schemas.database_binary import DataBinaryArtifactReceipt


ArtifactFamily = Literal["database", "binary"]


def _root(family: ArtifactFamily) -> Path:
    variable = f"ELYSIA_{family.upper()}FORGE_ARTIFACT_ROOT"
    configured = os.environ.get(variable, "").strip()
    return (Path(configured).expanduser() if configured else data_path("artifacts", family)).resolve(strict=False)


def create_data_binary_artifact(family: ArtifactFamily, artifact_kind: str, payload: dict[str, Any]) -> DataBinaryArtifactReceipt:
    safe_kind = "".join(character for character in artifact_kind if character.isalnum() or character in {"_", "-"})
    if not safe_kind:
        raise ValueError("artifact_kind_required")
    artifact_id = f"{family}_{safe_kind}_{uuid4().hex[:16]}"
    record = {"artifact_id": artifact_id, "artifact_kind": safe_kind, "local_only": True, "memory_posture": "not_memory", "network_used": False, "payload": payload}
    raw = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    digest = sha256(raw).hexdigest()
    root = _root(family)
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
        path.unlink(missing_ok=True)
        raise
    return DataBinaryArtifactReceipt(artifact_id=artifact_id, artifact_kind=safe_kind, sha256=digest, size_bytes=len(raw))


def get_data_binary_artifact(family: ArtifactFamily, artifact_id: str) -> dict[str, Any] | None:
    safe_id = "".join(character for character in artifact_id if character.isalnum() or character in {"_", "-"})
    if safe_id != artifact_id or not safe_id.startswith(f"{family}_"):
        return None
    path = _root(family) / f"{safe_id}.json"
    if not path.is_file() or path.is_symlink():
        return None
    flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


__all__ = ("create_data_binary_artifact", "get_data_binary_artifact")
