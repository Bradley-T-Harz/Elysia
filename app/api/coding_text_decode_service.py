"""Small bounded text decoding helpers for file previews."""

from __future__ import annotations

from pathlib import Path


def read_bounded_text(path: Path, *, max_bytes: int, max_lines: int) -> tuple[str, int, int, bool]:
    with path.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    truncated = len(raw) > max_bytes
    raw_preview = raw[:max_bytes]
    text = raw_preview.decode("utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    if len(lines) > max_lines:
        text = "".join(lines[:max_lines])
        truncated = True
    returned_bytes = len(text.encode("utf-8"))
    returned_lines = len(text.splitlines())
    return text, returned_bytes, returned_lines, truncated


def language_hint_for_path(path: Path) -> str | None:
    suffix = path.suffix.lower().lstrip(".")
    if not suffix:
        return None
    return {
        "py": "python",
        "ts": "typescript",
        "tsx": "typescriptreact",
        "js": "javascript",
        "jsx": "javascriptreact",
        "rs": "rust",
        "md": "markdown",
        "yaml": "yaml",
        "yml": "yaml",
        "json": "json",
        "toml": "toml",
        "css": "css",
        "html": "html",
        "sql": "sql",
        "sh": "shellscript",
    }.get(suffix, suffix)


__all__ = ("language_hint_for_path", "read_bounded_text")
