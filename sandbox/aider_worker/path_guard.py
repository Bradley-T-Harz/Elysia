from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath

from .config import AiderWorkerConfig


@dataclass
class PathGuardResult:
    ok: bool
    accepted_paths: list[str] = field(default_factory=list)
    blocked_paths: list[str] = field(default_factory=list)
    refusal_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def normalize_candidate_path(path: str) -> str:
    raw = str(path or "").strip()
    return raw.replace("\\", "/")


def path_is_absolute_or_home(path: str) -> bool:
    normalized = normalize_candidate_path(path)
    if not normalized:
        return False
    if normalized.startswith("~"):
        return True
    if Path(normalized).is_absolute():
        return True
    if PurePosixPath(normalized).is_absolute():
        return True
    return PureWindowsPath(str(path or "")).is_absolute()


def path_has_traversal(path: str) -> bool:
    parts = [part for part in PurePosixPath(normalize_candidate_path(path)).parts]
    return any(part == ".." for part in parts)


def path_has_denied_fragment(path: str, config: AiderWorkerConfig) -> bool:
    normalized = normalize_candidate_path(path).lower()
    parts = [part.lower() for part in PurePosixPath(normalized).parts]

    for fragment in config.denied_path_fragments:
        denied = normalize_candidate_path(fragment).lower().strip("/")
        if not denied:
            continue
        if "/" in denied:
            if denied in normalized.strip("/"):
                return True
            continue
        if denied in parts:
            return True

    return False


def path_has_denied_filename(path: str, config: AiderWorkerConfig) -> bool:
    file_name = PurePosixPath(normalize_candidate_path(path)).name.lower()
    denied_names = {name.lower() for name in config.denied_file_names}
    return file_name in denied_names


def path_has_denied_suffix(path: str, config: AiderWorkerConfig) -> bool:
    suffix = PurePosixPath(normalize_candidate_path(path)).suffix.lower()
    denied_suffixes = {suffix.lower() for suffix in config.denied_file_suffixes}
    return suffix in denied_suffixes


def path_looks_secret(path: str, config: AiderWorkerConfig) -> bool:
    file_name = PurePosixPath(normalize_candidate_path(path)).name.lower()
    if path_has_denied_filename(path, config):
        return True
    return any(
        fragment.lower() in file_name
        for fragment in config.secret_name_fragments
        if str(fragment).strip()
    )


def _path_too_long(path: str, config: AiderWorkerConfig) -> bool:
    try:
        max_length = int(config.filesystem.get("max_path_length") or 512)
    except (TypeError, ValueError):
        max_length = 512
    return len(path) > max_length


def _max_selected_files(config: AiderWorkerConfig) -> int:
    try:
        value = int(config.filesystem.get("max_selected_files") or 24)
    except (TypeError, ValueError):
        return 24
    return value if value > 0 else 24


def validate_selected_files(
    selected_files: list[str] | tuple[str, ...] | None,
    config: AiderWorkerConfig,
) -> PathGuardResult:
    accepted_paths: list[str] = []
    blocked_paths: list[str] = []
    refusal_reasons: list[str] = []
    seen: set[str] = set()
    paths = list(selected_files or [])

    if len(paths) > _max_selected_files(config):
        refusal_reasons.append(
            f"Selected files exceed configured limit of {_max_selected_files(config)}."
        )

    for raw_path in paths:
        normalized = normalize_candidate_path(raw_path)

        if not normalized:
            blocked_paths.append(str(raw_path))
            refusal_reasons.append("Selected file path is empty.")
            continue

        if "\x00" in normalized:
            blocked_paths.append(str(raw_path))
            refusal_reasons.append(f"Selected file path contains a null byte: {raw_path}")
            continue

        if "://" in normalized:
            blocked_paths.append(str(raw_path))
            refusal_reasons.append(
                f"Selected file path must be local and relative, not a URL: {raw_path}"
            )
            continue

        if path_is_absolute_or_home(normalized):
            blocked_paths.append(str(raw_path))
            refusal_reasons.append(
                f"Selected file path must be relative to an approved repo: {raw_path}"
            )
            continue

        if path_has_traversal(normalized):
            blocked_paths.append(str(raw_path))
            refusal_reasons.append(
                f"Selected file path must not traverse outside the repo: {raw_path}"
            )
            continue

        if _path_too_long(normalized, config):
            blocked_paths.append(str(raw_path))
            refusal_reasons.append(f"Selected file path is too long: {raw_path}")
            continue

        if path_has_denied_fragment(normalized, config):
            blocked_paths.append(str(raw_path))
            refusal_reasons.append(
                f"Selected file path targets a denied or generated path: {raw_path}"
            )
            continue

        if path_looks_secret(normalized, config):
            blocked_paths.append(str(raw_path))
            refusal_reasons.append(
                f"Selected file path looks secret-bearing or sealed: {raw_path}"
            )
            continue

        if path_has_denied_suffix(normalized, config):
            blocked_paths.append(str(raw_path))
            refusal_reasons.append(f"Selected file path has a blocked file type: {raw_path}")
            continue

        parts = [part for part in PurePosixPath(normalized).parts if part not in {"", "."}]
        clean_path = "/".join(parts)
        if not clean_path:
            blocked_paths.append(str(raw_path))
            refusal_reasons.append(f"Selected file path is not usable: {raw_path}")
            continue

        if clean_path not in seen:
            seen.add(clean_path)
            accepted_paths.append(clean_path)

    return PathGuardResult(
        ok=not refusal_reasons,
        accepted_paths=accepted_paths,
        blocked_paths=blocked_paths,
        refusal_reasons=refusal_reasons,
        warnings=[],
    )
