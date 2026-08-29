"""Private local EngineeringForge artifact bundles and compact receipts."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.api.project_paths import data_path
from app.api.schemas.engineering import EngineeringArtifactReceipt


DEFAULT_ENGINEERING_ARTIFACT_ROOT = data_path("artifacts", "engineering")
_MAX_ARTIFACT_READ_BYTES = 16 * 1024 * 1024


def engineering_artifact_root() -> Path:
    configured = os.environ.get("ELYSIA_ENGINEERING_ARTIFACT_ROOT", "").strip()
    return (Path(configured).expanduser() if configured else DEFAULT_ENGINEERING_ARTIFACT_ROOT).resolve(strict=False)


def _safe_token(value: str) -> str:
    return "".join(character for character in value if character.isalnum() or character in {"_", "-"})


def _write_artifact(*, artifact_kind: str, file_name: str, media_type: str, raw: bytes) -> EngineeringArtifactReceipt:
    safe_kind = _safe_token(artifact_kind)
    safe_name = Path(file_name).name
    if not safe_kind or not safe_name or safe_name != file_name or safe_name in {".", ".."}:
        raise ValueError("engineering_artifact_name_required")
    artifact_id = f"engineering_{safe_kind}_{uuid4().hex[:16]}"
    root = engineering_artifact_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    bundle = root / artifact_id
    bundle.mkdir(mode=0o700)
    digest = sha256(raw).hexdigest()
    target = bundle / safe_name
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
        metadata = {
            "artifact_id": artifact_id,
            "artifact_kind": safe_kind,
            "file_name": safe_name,
            "media_type": media_type,
            "sha256": digest,
            "size_bytes": len(raw),
            "local_only": True,
            "memory_posture": "not_memory",
            "network_used": False,
        }
        metadata_raw = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        metadata_fd = os.open(bundle / "artifact.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(metadata_fd, "wb") as stream:
            stream.write(metadata_raw)
    except Exception:
        for child in bundle.iterdir():
            child.unlink(missing_ok=True)
        bundle.rmdir()
        raise
    return EngineeringArtifactReceipt(
        artifact_id=artifact_id,
        artifact_kind=safe_kind,
        file_name=safe_name,
        media_type=media_type,
        sha256=digest,
        size_bytes=len(raw),
        local_only=True,
    )


def create_engineering_json_artifact(artifact_kind: str, file_name: str, payload: dict[str, Any]) -> EngineeringArtifactReceipt:
    raw = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False, default=str).encode("utf-8")
    return _write_artifact(artifact_kind=artifact_kind, file_name=file_name, media_type="application/json", raw=raw)


def create_engineering_text_artifact(artifact_kind: str, file_name: str, content: str, *, media_type: str) -> EngineeringArtifactReceipt:
    return _write_artifact(artifact_kind=artifact_kind, file_name=file_name, media_type=media_type, raw=content.encode("utf-8"))


def get_engineering_artifact(artifact_id: str) -> dict[str, Any] | None:
    safe_id = _safe_token(artifact_id)
    if not safe_id or safe_id != artifact_id or not safe_id.startswith("engineering_"):
        return None
    bundle = engineering_artifact_root() / safe_id
    if not bundle.is_dir() or bundle.is_symlink():
        return None
    metadata_path = bundle / "artifact.json"
    if not metadata_path.is_file() or metadata_path.is_symlink():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(metadata, dict) or metadata.get("artifact_id") != safe_id:
        return None
    file_name = str(metadata.get("file_name") or "")
    if Path(file_name).name != file_name:
        return None
    target = bundle / file_name
    if not target.is_file() or target.is_symlink() or target.stat().st_size > _MAX_ARTIFACT_READ_BYTES:
        return None
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(target, flags)
        with os.fdopen(descriptor, "rb") as stream:
            raw = stream.read(_MAX_ARTIFACT_READ_BYTES + 1)
    except OSError:
        return None
    if len(raw) > _MAX_ARTIFACT_READ_BYTES or sha256(raw).hexdigest() != metadata.get("sha256"):
        return None
    response = dict(metadata)
    if metadata.get("media_type") == "application/json":
        try:
            response["payload"] = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
    else:
        response["text_content"] = raw.decode("utf-8", errors="replace")
    return response


__all__ = (
    "DEFAULT_ENGINEERING_ARTIFACT_ROOT",
    "create_engineering_json_artifact",
    "create_engineering_text_artifact",
    "engineering_artifact_root",
    "get_engineering_artifact",
)
