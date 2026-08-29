"""
Elysia memory manager scaffold.

This module retrieves a small, deterministic slice of recent local
session journal memory for scaffold context gathering. It does not do
semantic retrieval yet. It only returns bounded, explicitly sorted
session notes from the local journal directory.
"""

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set
from app.install.paths import resolve_elysia_paths


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SESSIONS_DIR = resolve_elysia_paths().journal_dir

DEFAULT_SESSION_MEMORY_LIMIT = 3
PREVIEW_LIMIT = 160


def normalize_preview(text: str, limit: int = PREVIEW_LIMIT) -> str:
    """
    Normalize whitespace and shorten long text for memory previews.
    """
    cleaned = " ".join(text.split())

    if len(cleaned) <= limit:
        return cleaned

    return cleaned[: limit - 3] + "..."


def _sorted_session_files(sessions_dir: Path) -> List[Path]:
    """
    Return session journal files in deterministic recency order.

    Current scaffold rule:
    - prefer filename ordering because filenames begin with ISO dates
    - use modified time as a secondary tiebreaker
    - newest entries come first
    """
    if not sessions_dir.exists():
        return []

    files = [path for path in sessions_dir.glob("*_runtime-session.md") if path.is_file()]

    return sorted(
        files,
        key=lambda path: (path.name, path.stat().st_mtime),
        reverse=True,
    )


def get_recent_session_memory(
    limit: int = DEFAULT_SESSION_MEMORY_LIMIT,
    exclude_paths: Optional[Iterable[str]] = None,
) -> List[Dict[str, str]]:
    """
    Return a bounded, deterministic list of recent session journal entries.

    Current scaffold behavior:
    - returns at most `limit` entries
    - sorts entries explicitly by recency
    - can exclude specific paths when the caller wants to avoid
      immediate self-retrieval
    """
    if limit <= 0:
        return []

    excluded: Set[str] = set()

    if exclude_paths:
        excluded = {str(Path(path).resolve()) for path in exclude_paths}

    results: List[Dict[str, str]] = []

    for path in _sorted_session_files(SESSIONS_DIR):
        resolved_path = str(path.resolve())

        if resolved_path in excluded:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        results.append(
            {
                "source": "session_journal",
                "path": resolved_path,
                "title": path.name,
                "preview": normalize_preview(text),
            }
        )

        if len(results) >= limit:
            break

    return results


if __name__ == "__main__":
    for item in get_recent_session_memory():
        print(item)
