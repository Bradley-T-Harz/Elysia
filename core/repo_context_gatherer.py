"""
Safe local repo context gatherer v0 for Elysia.

This module provides bounded, read-only repository inspection for future Coder
mode. It is intentionally conservative.

It does not run shell commands, does not call git, does not touch the network,
does not mutate files, does not inspect arbitrary home folders, and does not
read secret-looking files. Git truth is limited to safely reading .git/HEAD
when available.

v0 produces a compact repo summary:
- approved repo root
- minimal git/branch truth
- important top-level files
- safe tree entries
- language/framework/test command hints
- explicit boundary notes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


REPO_CONTEXT_TOOL_KIND = "repo_context_gatherer"
REPO_CONTEXT_OPERATION = "gather_repo_context"

DEFAULT_CONFIG_PATH = Path("config/coder/approved_repos.yaml")
DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_ENTRIES = 240
DEFAULT_MAX_FILE_SIZE_BYTES = 250_000

CHANGED_FILES_NOTE = "Git status detection is not live in repo context v0."

IMPORTANT_TOP_LEVEL_FILES = {
    "README.md",
    "README",
    "pyproject.toml",
    "pytest.ini",
    "requirements.txt",
    "requirements-dev.txt",
    "environment.yml",
    "environment.yaml",
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "vite.config.ts",
    "vite.config.js",
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
}

SKIPPED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "target",
    "coverage",
    ".next",
    ".turbo",
    "vault",
    "secrets",
    "credentials",
    "private",
    "browser_profiles",
    "browser profile",
    "browser profiles",
}

SKIPPED_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "known_hosts",
    "authorized_keys",
}

SKIPPED_FILE_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
    ".cer",
    ".der",
    ".sqlite",
    ".db",
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
    ".wav",
    ".mp3",
    ".flac",
    ".ogg",
    ".m4a",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
}

SECRET_NAME_FRAGMENTS = {
    "token",
    "secret",
    "credential",
    "password",
    "passwd",
    "apikey",
    "api_key",
    "private_key",
}

LANGUAGE_HINTS_BY_SUFFIX = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".rs": "Rust",
    ".md": "Markdown",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".sh": "Shell",
    ".css": "CSS",
    ".html": "HTML",
    ".toml": "TOML",
}

LANGUAGE_ORDER = [
    "Python",
    "TypeScript",
    "JavaScript",
    "Rust",
    "Markdown",
    "YAML",
    "JSON",
    "Shell",
    "CSS",
    "HTML",
    "TOML",
]


class RepoContextStatus(str, Enum):
    """Small status vocabulary for repo context gathering."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass
class RepoContextResult:
    """Structured result for safe local repo context gathering."""

    ok: bool
    status: RepoContextStatus
    tool_kind: str = REPO_CONTEXT_TOOL_KIND
    operation: str = REPO_CONTEXT_OPERATION
    repo_key: str | None = None
    repo_label: str | None = None
    repo_root: str = ""
    requested_path: str | None = None
    trust_zone: str = "project_local"

    appears_git_repo: bool = False
    current_branch: str | None = None
    git_head_read: bool = False
    changed_files_live: bool = False
    changed_files_note: str = CHANGED_FILES_NOTE

    important_top_level_files: list[str] = field(default_factory=list)
    top_level_directories: list[str] = field(default_factory=list)
    safe_tree_entries: list[str] = field(default_factory=list)

    language_hints: list[str] = field(default_factory=list)
    framework_hints: list[str] = field(default_factory=list)
    test_command_hints: list[str] = field(default_factory=list)

    skipped_paths: list[str] = field(default_factory=list)
    boundary_notes: list[str] = field(default_factory=list)

    locality: str = "local"
    read_only: bool = True
    approval_required: bool = False
    network_access_used: bool = False
    shell_used: bool = False
    mutated_files: bool = False

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-safe payload."""
        return {
            "ok": self.ok,
            "status": self.status.value,
            "tool_kind": self.tool_kind,
            "operation": self.operation,
            "repo_key": self.repo_key,
            "repo_label": self.repo_label,
            "repo_root": self.repo_root,
            "requested_path": self.requested_path,
            "trust_zone": self.trust_zone,
            "appears_git_repo": self.appears_git_repo,
            "current_branch": self.current_branch,
            "git_head_read": self.git_head_read,
            "changed_files_live": self.changed_files_live,
            "changed_files_note": self.changed_files_note,
            "important_top_level_files": list(self.important_top_level_files),
            "top_level_directories": list(self.top_level_directories),
            "safe_tree_entries": list(self.safe_tree_entries),
            "language_hints": list(self.language_hints),
            "framework_hints": list(self.framework_hints),
            "test_command_hints": list(self.test_command_hints),
            "skipped_paths": list(self.skipped_paths),
            "boundary_notes": list(self.boundary_notes),
            "locality": self.locality,
            "read_only": self.read_only,
            "approval_required": self.approval_required,
            "network_access_used": self.network_access_used,
            "shell_used": self.shell_used,
            "mutated_files": self.mutated_files,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def _parse_scalar(value: str) -> Any:
    text = str(value or "").strip()

    if not text:
        return ""

    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        return text[1:-1]

    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None

    try:
        return int(text)
    except ValueError:
        return text


def _split_key_value(line: str) -> tuple[str, Any]:
    key, value = line.split(":", 1)
    return key.strip(), _parse_scalar(value)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """
    Parse the deliberately small config/coder/approved_repos.yaml shape.

    This is not a general YAML parser. It exists so repo context v0 does not
    depend on PyYAML.
    """
    config: dict[str, Any] = {}
    section: str | None = None
    current_repo_key: str | None = None
    current_list_key: str | None = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        if line.startswith("- "):
            item = _parse_scalar(line[2:].strip())

            if section == "repos" and current_repo_key and current_list_key:
                config["repos"][current_repo_key].setdefault(current_list_key, [])
                config["repos"][current_repo_key][current_list_key].append(item)
                continue

            if section and current_list_key:
                config[section].setdefault(current_list_key, [])
                config[section][current_list_key].append(item)
                continue

            continue

        if indent == 0:
            current_repo_key = None
            current_list_key = None

            if line.endswith(":"):
                section = line[:-1].strip()
                config[section] = {}
                continue

            key, value = _split_key_value(line)
            section = None
            config[key] = value
            continue

        if section == "inspection_defaults" and indent == 2:
            key, value = _split_key_value(line)
            config.setdefault("inspection_defaults", {})[key] = value
            current_list_key = key if line.endswith(":") else None
            continue

        if section == "repos":
            if indent == 2 and line.endswith(":"):
                current_repo_key = line[:-1].strip()
                current_list_key = None
                config.setdefault("repos", {})[current_repo_key] = {}
                continue

            if indent == 4 and current_repo_key:
                if line.endswith(":"):
                    current_list_key = line[:-1].strip()
                    config["repos"][current_repo_key][current_list_key] = []
                    continue

                key, value = _split_key_value(line)
                current_list_key = None
                config["repos"][current_repo_key][key] = value
                continue

    return config


def load_approved_repos_config(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """
    Load approved repo configuration.

    Uses PyYAML only if it is already available. Otherwise falls back to a narrow
    parser for the local config shape.
    """
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Approved repo config not found: {path}")

    text = path.read_text(encoding="utf-8")

    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass

    parsed = _parse_simple_yaml(text)
    if not isinstance(parsed, dict):
        raise ValueError("Approved repo config could not be parsed as a mapping.")

    return parsed


def _blocked_result(
    *,
    repo_key: str | None = None,
    repo_root: str | Path | None = None,
    requested_path: str | Path | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> RepoContextResult:
    return RepoContextResult(
        ok=False,
        status=RepoContextStatus.BLOCKED,
        repo_key=repo_key,
        repo_root=str(repo_root or ""),
        requested_path=str(requested_path) if requested_path is not None else None,
        warnings=list(warnings or []),
        errors=list(errors or []),
        boundary_notes=_default_boundary_notes(),
    )


def _failed_result(
    *,
    repo_key: str | None = None,
    repo_root: str | Path | None = None,
    requested_path: str | Path | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> RepoContextResult:
    return RepoContextResult(
        ok=False,
        status=RepoContextStatus.FAILED,
        repo_key=repo_key,
        repo_root=str(repo_root or ""),
        requested_path=str(requested_path) if requested_path is not None else None,
        warnings=list(warnings or []),
        errors=list(errors or []),
        boundary_notes=_default_boundary_notes(),
    )


def _default_boundary_notes() -> list[str]:
    return [
        "Read-only local repo context v0.",
        "No shell commands were run.",
        "No network access was used.",
        "No files were mutated.",
        "No git status or diff inspection is live in repo context v0.",
        "Secret-looking paths and heavy/generated directories are skipped.",
    ]


def _as_int(value: Any, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback

    return number if number > 0 else fallback


def _resolve_configured_root(root_value: Any) -> Path:
    root_text = str(root_value or "").strip()
    if not root_text:
        return Path.cwd().resolve()

    root = Path(root_text).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root

    return root.resolve(strict=False)


def _approved_repo_entries(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    repos = config.get("repos", {})
    if not isinstance(repos, dict):
        return {}

    return {
        str(key): value
        for key, value in repos.items()
        if isinstance(value, dict)
    }


def _find_approved_repo(
    *,
    config: dict[str, Any],
    repo_key: str | None,
    repo_root: str | Path | None,
) -> tuple[str | None, dict[str, Any] | None, Path | None, str | None]:
    repos = _approved_repo_entries(config)

    if not repos:
        return None, None, None, "No approved repositories are configured."

    if repo_key is None and repo_root is None:
        default_key = config.get("default_repo_key")
        repo_key = str(default_key or "").strip() or None

    if repo_key:
        repo = repos.get(repo_key)
        if repo is None:
            return repo_key, None, None, f"Repo key is not approved: {repo_key}"

        if repo.get("allowed") is not True:
            return repo_key, repo, None, f"Repo key is configured but not allowed: {repo_key}"

        return repo_key, repo, _resolve_configured_root(repo.get("root")), None

    if repo_root is not None:
        requested = Path(repo_root).expanduser().resolve(strict=False)

        for key, repo in repos.items():
            if repo.get("allowed") is not True:
                continue

            approved_root = _resolve_configured_root(repo.get("root"))
            if requested == approved_root:
                return key, repo, approved_root, None

        return (
            None,
            None,
            requested,
            "Requested repo root is not an approved repository root.",
        )

    return None, None, None, "No repo key or approved repo root was provided."


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _name_looks_secret(name: str) -> bool:
    lowered = name.lower()

    if lowered in SKIPPED_FILE_NAMES:
        return True

    if any(fragment in lowered for fragment in SECRET_NAME_FRAGMENTS):
        return True

    return False


def _should_skip_path(path: Path, *, root: Path, max_file_size_bytes: int) -> bool:
    rel_parts = [part.lower() for part in path.relative_to(root).parts]
    name = path.name.lower()

    if any(part in SKIPPED_DIRECTORY_NAMES for part in rel_parts):
        return True

    if path.is_dir():
        return name in SKIPPED_DIRECTORY_NAMES or _name_looks_secret(name)

    if _name_looks_secret(name):
        return True

    if path.suffix.lower() in SKIPPED_FILE_SUFFIXES:
        return True

    try:
        if path.is_file() and path.stat().st_size > max_file_size_bytes:
            return True
    except OSError:
        return True

    return False


def _discover_top_level(root: Path, *, max_file_size_bytes: int) -> tuple[list[str], list[str], list[str]]:
    important_files: list[str] = []
    directories: list[str] = []
    skipped: list[str] = []

    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return important_files, directories, skipped

    for entry in entries:
        rel = _relative_path(root, entry)

        if _should_skip_path(entry, root=root, max_file_size_bytes=max_file_size_bytes):
            skipped.append(rel)
            continue

        if entry.is_dir():
            directories.append(entry.name)
        elif entry.is_file() and entry.name in IMPORTANT_TOP_LEVEL_FILES:
            important_files.append(entry.name)

    return important_files, directories, skipped


def _walk_safe_tree(
    root: Path,
    *,
    max_depth: int,
    max_entries: int,
    max_file_size_bytes: int,
) -> tuple[list[str], list[str], list[str]]:
    entries: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []

    def walk(directory: Path, depth: int) -> None:
        if len(entries) >= max_entries:
            return

        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name.lower())
        except OSError as exc:
            skipped.append(_relative_path(root, directory))
            warnings.append(f"Could not inspect directory {directory}: {exc}")
            return

        for child in children:
            rel = _relative_path(root, child)

            if _should_skip_path(
                child,
                root=root,
                max_file_size_bytes=max_file_size_bytes,
            ):
                skipped.append(rel)
                continue

            if len(entries) >= max_entries:
                warnings.append(
                    f"Repo tree summary was limited to {max_entries} entries for v0."
                )
                return

            entries.append(rel)

            if child.is_dir() and depth < max_depth:
                walk(child, depth + 1)

    walk(root, 1)

    return entries, skipped, warnings


def _read_git_head(root: Path) -> tuple[bool, str | None, bool, list[str]]:
    git_path = root / ".git"
    head_path = git_path / "HEAD"
    warnings: list[str] = []

    if not git_path.exists():
        return False, None, False, warnings

    if not git_path.is_dir():
        warnings.append(".git exists but is not a directory; git branch was not read.")
        return True, None, False, warnings

    if not head_path.exists() or not head_path.is_file():
        warnings.append(".git/HEAD was not available for minimal branch inspection.")
        return True, None, False, warnings

    try:
        text = head_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        warnings.append(f".git/HEAD could not be read: {exc}")
        return True, None, False, warnings

    if text.startswith("ref:"):
        ref = text.split(":", 1)[1].strip()
        prefix = "refs/heads/"
        if ref.startswith(prefix):
            return True, ref[len(prefix):], True, warnings

        return True, ref, True, warnings

    if text:
        return True, f"detached:{text[:12]}", True, warnings

    warnings.append(".git/HEAD was empty.")
    return True, None, True, warnings


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        ordered.append(value)

    return ordered


def _infer_language_hints(root: Path, safe_tree_entries: list[str]) -> list[str]:
    hints: list[str] = []

    for entry in safe_tree_entries:
        suffix = Path(entry).suffix.lower()
        hint = LANGUAGE_HINTS_BY_SUFFIX.get(suffix)
        if hint:
            hints.append(hint)

    if (root / "apps" / "elysia-desktop" / "src").exists():
        hints.append("TypeScript")

    ordered = _ordered_unique(hints)
    return [hint for hint in LANGUAGE_ORDER if hint in ordered]


def _infer_framework_hints(root: Path) -> list[str]:
    hints: list[str] = []

    if (root / "app" / "api" / "main.py").exists():
        hints.append("FastAPI local API bridge")

    if (root / "apps" / "elysia-desktop" / "src").exists():
        hints.append("React desktop UI")

    if (root / "apps" / "elysia-desktop" / "src-tauri").exists():
        hints.append("Tauri desktop shell")

    if (
        (root / "apps" / "elysia-desktop" / "vite.config.ts").exists()
        or (root / "apps" / "elysia-desktop" / "vite.config.js").exists()
        or (root / "vite.config.ts").exists()
        or (root / "vite.config.js").exists()
    ):
        hints.append("Vite frontend build")

    if (root / "tests").exists():
        hints.append("Pytest backend tests")

    if (root / "core").exists():
        hints.append("Core Python organs")

    if (root / "app" / "api").exists() and (root / "config" / "models").exists():
        hints.append("Local model/API routing config")

    return hints


def _infer_test_command_hints(root: Path) -> list[str]:
    hints: list[str] = []

    if (root / "scripts" / "test_backend.sh").exists():
        hints.append("./scripts/test_backend.sh -q")
    elif (root / "tests").exists():
        hints.append("PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q")

    if (root / "apps" / "elysia-desktop" / "package.json").exists():
        hints.append("npm --prefix apps/elysia-desktop run typecheck")
        hints.append("npm --prefix apps/elysia-desktop run build")

    return hints


def gather_repo_context(
    *,
    repo_key: str | None = None,
    repo_root: str | Path | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    max_depth: int | None = None,
    max_entries: int | None = None,
) -> RepoContextResult:
    """
    Gather bounded read-only context for one approved local repository.

    v0 accepts only configured approved repo roots. If repo_root is provided, it
    must exactly match an approved root after resolution.
    """
    try:
        config = load_approved_repos_config(config_path)
    except Exception as exc:
        return _failed_result(
            repo_key=repo_key,
            repo_root=repo_root,
            requested_path=repo_root,
            errors=[f"Approved repo config could not be loaded: {exc}"],
        )

    inspection_defaults = config.get("inspection_defaults", {})
    if not isinstance(inspection_defaults, dict):
        inspection_defaults = {}

    effective_max_depth = _as_int(
        max_depth if max_depth is not None else inspection_defaults.get("max_depth"),
        DEFAULT_MAX_DEPTH,
    )
    effective_max_entries = _as_int(
        max_entries if max_entries is not None else inspection_defaults.get("max_entries"),
        DEFAULT_MAX_ENTRIES,
    )
    effective_max_file_size_bytes = _as_int(
        inspection_defaults.get("max_file_size_bytes"),
        DEFAULT_MAX_FILE_SIZE_BYTES,
    )

    selected_key, repo, approved_root, selection_error = _find_approved_repo(
        config=config,
        repo_key=repo_key,
        repo_root=repo_root,
    )

    if selection_error:
        return _blocked_result(
            repo_key=selected_key or repo_key,
            repo_root=approved_root or repo_root,
            requested_path=repo_root,
            errors=[selection_error],
        )

    if repo is None or approved_root is None:
        return _blocked_result(
            repo_key=selected_key or repo_key,
            repo_root=repo_root,
            requested_path=repo_root,
            errors=["Approved repo selection failed unexpectedly."],
        )

    if not approved_root.exists():
        return _failed_result(
            repo_key=selected_key,
            repo_root=approved_root,
            requested_path=repo_root,
            errors=[f"Approved repo root does not exist: {approved_root}"],
        )

    if not approved_root.is_dir():
        return _blocked_result(
            repo_key=selected_key,
            repo_root=approved_root,
            requested_path=repo_root,
            errors=[f"Approved repo root is not a directory: {approved_root}"],
        )

    repo_label = str(repo.get("label") or selected_key or "Approved repo")
    trust_zone = str(repo.get("trust_zone") or "project_local")

    appears_git_repo, current_branch, git_head_read, git_warnings = _read_git_head(
        approved_root
    )

    important_files, top_dirs, top_skipped = _discover_top_level(
        approved_root,
        max_file_size_bytes=effective_max_file_size_bytes,
    )
    safe_entries, tree_skipped, tree_warnings = _walk_safe_tree(
        approved_root,
        max_depth=effective_max_depth,
        max_entries=effective_max_entries,
        max_file_size_bytes=effective_max_file_size_bytes,
    )

    skipped_paths = _ordered_unique(top_skipped + tree_skipped)
    warnings = git_warnings + tree_warnings

    return RepoContextResult(
        ok=True,
        status=RepoContextStatus.COMPLETED,
        repo_key=selected_key,
        repo_label=repo_label,
        repo_root=str(approved_root),
        requested_path=str(repo_root) if repo_root is not None else None,
        trust_zone=trust_zone,
        appears_git_repo=appears_git_repo,
        current_branch=current_branch,
        git_head_read=git_head_read,
        changed_files_live=False,
        changed_files_note=CHANGED_FILES_NOTE,
        important_top_level_files=important_files,
        top_level_directories=top_dirs,
        safe_tree_entries=safe_entries,
        language_hints=_infer_language_hints(approved_root, safe_entries),
        framework_hints=_infer_framework_hints(approved_root),
        test_command_hints=_infer_test_command_hints(approved_root),
        skipped_paths=skipped_paths,
        boundary_notes=_default_boundary_notes(),
        locality="local",
        read_only=True,
        approval_required=False,
        network_access_used=False,
        shell_used=False,
        mutated_files=False,
        warnings=warnings,
        errors=[],
    )


__all__ = (
    "CHANGED_FILES_NOTE",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_MAX_ENTRIES",
    "DEFAULT_MAX_FILE_SIZE_BYTES",
    "REPO_CONTEXT_OPERATION",
    "REPO_CONTEXT_TOOL_KIND",
    "RepoContextResult",
    "RepoContextStatus",
    "gather_repo_context",
    "load_approved_repos_config",
)
