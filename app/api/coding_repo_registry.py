"""Private XDG registry for explicitly approved Codev repository roots."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from functools import wraps
from core.codev.filesystem import read_bytes
from typing import Any

from app.install.paths import resolve_elysia_paths
from core.codev.identity import local_profile_id


REGISTRY_VERSION = 1
_REGISTRY_LOCK = RLock()


def _serialized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _REGISTRY_LOCK:
            return function(*args, **kwargs)
    return wrapped


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def approved_repo_registry_path() -> Path:
    return resolve_elysia_paths().config_dir / "coding" / "approved-repos.json"


def _empty_registry() -> dict[str, Any]:
    return {"version": REGISTRY_VERSION, "repos": {}}


def load_approved_repo_registry(path: Path | None = None) -> dict[str, Any]:
    target = path or approved_repo_registry_path()
    try:
        payload = json.loads(read_bytes(target.parent, target.name, limit=1024 * 1024))
    except FileNotFoundError:
        return _empty_registry()
    except (OSError, ValueError):
        return {**_empty_registry(), "invalid": True}
    if not isinstance(payload, dict) or payload.get("version") != REGISTRY_VERSION:
        return {**_empty_registry(), "invalid": True}
    repos = payload.get("repos")
    if not isinstance(repos, dict):
        return {**_empty_registry(), "invalid": True}
    return {"version": REGISTRY_VERSION, "repos": repos}


def _save_registry(payload: dict[str, Any], path: Path | None = None) -> None:
    target = path or approved_repo_registry_path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        target.parent.chmod(0o700)
    except OSError:
        pass
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target.parent,
        prefix=".approved-repos-",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(payload, handle, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    temporary.replace(target)


def list_approved_repo_roots(path: Path | None = None) -> list[tuple[str, Path]]:
    payload = load_approved_repo_registry(path)
    roots: list[tuple[str, Path]] = []
    for key, raw in payload["repos"].items():
        if not isinstance(raw, dict) or raw.get("approved") is not True or raw.get("revoked") is True:
            continue
        if raw.get("local_profile_id") not in {None, local_profile_id()}:
            continue
        root = Path(str(raw.get("root") or "")).expanduser()
        if not root.is_absolute() or not root.exists() or not root.is_dir():
            continue
        current = Path(root.anchor)
        contains_symlink = False
        for part in root.parts[1:]:
            current = current / part
            if current.is_symlink():
                contains_symlink = True
                break
        if contains_symlink:
            continue
        resolved = root.resolve(strict=False)
        expected_key = sha256(str(resolved).encode("utf-8")).hexdigest()[:24]
        broad = {Path(resolved.anchor), Path.home().resolve(), Path("/home"), Path("/tmp")}
        if key != expected_key or resolved in broad:
            continue
        roots.append((f"user_{key}", resolved))
    return roots


@_serialized
def record_repo_approval(*, root_hash: str, root: Path, label: str, path: Path | None = None) -> dict[str, Any]:
    payload = load_approved_repo_registry(path)
    if payload.get("invalid"):
        raise ValueError("repository_registry_requires_recovery")
    now = _utc_now_iso()
    entry = {
        "root": str(root),
        "label": label,
        "approved": True,
        "revoked": False,
        "approved_at_utc": now,
        "updated_at_utc": now,
        "local_profile_id": local_profile_id(),
    }
    payload["repos"][root_hash] = entry
    _save_registry(payload, path)
    return entry


@_serialized
def revoke_repo_approval(*, root_hash: str, path: Path | None = None, root: Path | None = None) -> bool:
    payload = load_approved_repo_registry(path)
    if payload.get("invalid"):
        raise ValueError("repository_registry_requires_recovery")
    entry = payload["repos"].get(root_hash)
    if not isinstance(entry, dict):
        if root is None:
            return False
        entry = {"root": str(root), "local_profile_id": local_profile_id()}
        payload["repos"][root_hash] = entry
    entry["approved"] = False
    entry["revoked"] = True
    entry["updated_at_utc"] = _utc_now_iso()
    _save_registry(payload, path)
    return True


def repository_revoked(root: Path, path: Path | None = None) -> bool:
    """Explicit denials override every positive root source and its descendants."""
    registry = load_approved_repo_registry(path)
    if registry.get("invalid"):
        return True
    for key, entry in registry["repos"].items():
        if not isinstance(entry, dict) or entry.get("revoked") is not True:
            continue
        denied = Path(str(entry.get("root") or ""))
        if not denied.is_absolute() or sha256(str(denied).encode()).hexdigest()[:24] != key:
            continue
        if root == denied or denied in root.parents:
            return True
    return False


__all__ = (
    "approved_repo_registry_path",
    "list_approved_repo_roots",
    "load_approved_repo_registry",
    "record_repo_approval",
    "revoke_repo_approval",
)
