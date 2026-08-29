"""Workspace path guard for Elysia Codev coding bridge requests."""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from app.api.coding_policy_service import load_coding_policy
from app.api.project_paths import config_path, elysia_repo_root
from app.api.coding_data_type_registry import SUPPORTED_DATA_EXTENSIONS, is_supported_data_path
from app.api.coding_document_type_registry import DOCUMENT_EXTENSIONS, is_supported_document_path
from app.api.coding_media_type_registry import SUPPORTED_MEDIA_EXTENSIONS, is_supported_media_path
from app.api.coding_visual_type_registry import SUPPORTED_VISUAL_EXTENSIONS, is_supported_visual_path
from app.api.coding_archive_type_registry import ARCHIVE_EXTENSIONS, is_registered_archive_path
from app.api.coding_binary_type_registry import BINARY_EXTENSIONS, is_registered_binary_path
from app.api.coding_database_type_registry import DATABASE_EXTENSIONS, is_registered_database_path
from app.api.coding_engineering_type_registry import ENGINEERING_EXTENSIONS, is_registered_engineering_path
from app.api.coding_repo_registry import list_approved_repo_roots


@dataclass(frozen=True)
class GuardedPath:
    allowed: bool
    workspace_root: Path
    target_path: Path
    relative_path: str | None
    reason: str | None = None
    approved_root: Path | None = None
    approved_root_key: str | None = None


def hash_path(path: Path | str) -> str:
    return sha256(str(path).encode("utf-8")).hexdigest()[:24]


def _normalized_parts(relative_path: str) -> list[str]:
    return [part for part in relative_path.replace("\\", "/").split("/") if part and part != "."]


def _configured_workspace_roots() -> list[tuple[str, Path]]:
    roots: list[tuple[str, Path]] = []
    config_file = config_path("coder", "approved_repos.yaml")
    try:
        import yaml

        loaded = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
    except Exception:
        loaded = {}
    repos = loaded.get("repos") if isinstance(loaded, dict) else {}
    if isinstance(repos, dict):
        for key, value in repos.items():
            if not isinstance(value, dict):
                continue
            if value.get("allowed") is not True or value.get("coding_workspace_allowed") is not True:
                continue
            raw_root = Path(str(value.get("root") or "")).expanduser()
            if not raw_root.is_absolute():
                raw_root = elysia_repo_root() / raw_root
            roots.append((str(key), raw_root.resolve(strict=False)))

    for index, raw_root in enumerate(os.environ.get("ELYSIA_CODING_APPROVED_ROOTS", "").split(os.pathsep)):
        if raw_root.strip():
            roots.append((f"runtime_{index}", Path(raw_root).expanduser().resolve(strict=False)))
    roots.extend(list_approved_repo_roots())
    return roots


def _path_contains_symlink(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _blocked_path_reason(relative_path: str, policy: dict) -> str | None:
    parts = _normalized_parts(relative_path)
    blocked_parts = {str(item).strip().casefold() for item in policy.get("blocked_path_parts") or []}
    ignored_names = {str(item).strip().casefold() for item in policy.get("ignored_names") or []}
    lowered_parts = [part.casefold() for part in parts]
    for index, part in enumerate(lowered_parts):
        prefix = "/".join(lowered_parts[: index + 1])
        if part in blocked_parts or prefix in blocked_parts:
            return "blocked_path_part"
        if part in ignored_names or prefix in ignored_names:
            return "ignored_path"
    return None


def _authorize_workspace_root(root: Path, policy: dict) -> tuple[Path | None, str | None, str | None, str]:
    if not root.exists() or not root.is_dir():
        return None, None, None, "workspace_root_not_directory"
    if _path_contains_symlink(root):
        return None, None, None, "workspace_root_symlink"
    broad_roots = {Path(root.anchor), Path.home().resolve(), Path("/home"), Path("/tmp")}
    if root in broad_roots:
        return None, None, None, "workspace_root_too_broad"

    for key, approved_root in _configured_workspace_roots():
        if key.startswith("user_") and root != approved_root:
            continue
        try:
            root_relative = root.relative_to(approved_root).as_posix()
        except ValueError:
            continue
        blocked_reason = _blocked_path_reason(root_relative, policy)
        if blocked_reason:
            return None, None, None, "workspace_root_blocked"
        return approved_root, key, root_relative, ""
    return None, None, None, "workspace_root_not_approved"


def _matches_blocked_glob(relative_path: str, blocked_globs: list[str]) -> bool:
    name = Path(relative_path).name
    if name == ".env.example" or name.endswith(".env.example"):
        return False
    if Path(relative_path).suffix.lower() in SUPPORTED_DATA_EXTENSIONS:
        return False
    if Path(relative_path).suffix.lower() in DATABASE_EXTENSIONS | BINARY_EXTENSIONS | ENGINEERING_EXTENSIONS:
        return False
    return any(
        fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(relative_path, pattern)
        for pattern in blocked_globs
    )


def guard_workspace_path(
    *,
    workspace_root: str,
    target_path: str,
    require_existing: bool = True,
    allow_directory: bool = False,
) -> GuardedPath:
    policy = load_coding_policy()
    raw_root = Path(workspace_root).expanduser()
    root = raw_root.resolve(strict=False)
    approved_root, approved_root_key, root_relative, root_reason = _authorize_workspace_root(root, policy)
    if root_reason:
        return GuardedPath(False, root, root, None, root_reason)

    raw_target = Path(target_path).expanduser()
    if not raw_target.is_absolute():
        raw_target = root / raw_target
    lexical_target = Path(os.path.abspath(str(raw_target)))

    try:
        lexical_relative = lexical_target.relative_to(root).as_posix()
    except ValueError:
        return GuardedPath(False, root, lexical_target, None, "outside_workspace", approved_root, approved_root_key)
    if _path_contains_symlink(lexical_target):
        return GuardedPath(False, root, lexical_target, lexical_relative, "symlink_not_allowed", approved_root, approved_root_key)
    target = lexical_target.resolve(strict=False)

    try:
        relative = target.relative_to(root).as_posix()
    except ValueError:
        return GuardedPath(False, root, target, None, "outside_workspace", approved_root, approved_root_key)

    if relative in {"", "."} and not allow_directory:
        return GuardedPath(False, root, target, relative, "workspace_root_not_file", approved_root, approved_root_key)

    if require_existing and not target.exists():
        return GuardedPath(False, root, target, relative, "missing_path", approved_root, approved_root_key)

    if target.exists() and target.is_dir() and not allow_directory:
        return GuardedPath(False, root, target, relative, "directory_not_allowed", approved_root, approved_root_key)
    if target.exists() and not allow_directory and not target.is_file():
        return GuardedPath(False, root, target, relative, "regular_file_required", approved_root, approved_root_key)

    effective_relative = "/".join(part for part in (root_relative, relative) if part not in {None, "", "."})
    blocked_reason = _blocked_path_reason(effective_relative, policy)
    if blocked_reason:
        return GuardedPath(False, root, target, relative, blocked_reason, approved_root, approved_root_key)

    blocked_names = {str(item).strip().casefold() for item in policy.get("blocked_file_names") or []}
    ignored_globs = [str(item).strip() for item in policy.get("ignored_globs") or []]

    if target.name.casefold() in blocked_names:
        return GuardedPath(False, root, target, relative, "blocked_file_name", approved_root, approved_root_key)

    if _matches_blocked_glob(relative, ignored_globs):
        return GuardedPath(False, root, target, relative, "blocked_glob", approved_root, approved_root_key)

    binary_exts = {str(item).lower() for item in policy.get("binary_extensions") or []}
    target_suffix = target.suffix.lower()
    if target_suffix in DOCUMENT_EXTENSIONS and not is_supported_document_path(target):
        return GuardedPath(False, root, target, relative, "unsupported_or_blocked_document_type", approved_root, approved_root_key)
    if target_suffix in SUPPORTED_DATA_EXTENSIONS and is_supported_data_path(target):
        return GuardedPath(True, root, target, relative, approved_root=approved_root, approved_root_key=approved_root_key)
    if target_suffix in SUPPORTED_VISUAL_EXTENSIONS and is_supported_visual_path(target):
        return GuardedPath(True, root, target, relative, approved_root=approved_root, approved_root_key=approved_root_key)
    if target_suffix in SUPPORTED_MEDIA_EXTENSIONS and is_supported_media_path(target):
        return GuardedPath(True, root, target, relative, approved_root=approved_root, approved_root_key=approved_root_key)
    if any(target.name.lower().endswith(extension) for extension in ARCHIVE_EXTENSIONS) and is_registered_archive_path(target):
        return GuardedPath(True, root, target, relative, approved_root=approved_root, approved_root_key=approved_root_key)
    if target_suffix in DATABASE_EXTENSIONS and is_registered_database_path(target):
        return GuardedPath(True, root, target, relative, approved_root=approved_root, approved_root_key=approved_root_key)
    if target_suffix in BINARY_EXTENSIONS and is_registered_binary_path(target):
        return GuardedPath(True, root, target, relative, approved_root=approved_root, approved_root_key=approved_root_key)
    if target_suffix in ENGINEERING_EXTENSIONS and is_registered_engineering_path(target):
        return GuardedPath(True, root, target, relative, approved_root=approved_root, approved_root_key=approved_root_key)
    if target_suffix in binary_exts and not is_supported_document_path(target):
        return GuardedPath(False, root, target, relative, "binary_or_unsupported_file", approved_root, approved_root_key)

    return GuardedPath(True, root, target, relative, approved_root=approved_root, approved_root_key=approved_root_key)


__all__ = ("GuardedPath", "guard_workspace_path", "hash_path")
