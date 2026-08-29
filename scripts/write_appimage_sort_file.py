#!/usr/bin/env python3
"""Write a deterministic mksquashfs priority file for an AppDir tree."""

from __future__ import annotations

import sys
from pathlib import Path


MAX_PRIORITY = 32767
MIN_PRIORITY = -32768


def write_sort_file(root: Path, destination: Path) -> int:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("AppImage sort root must be a real directory")
    entries = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
    available = MAX_PRIORITY - MIN_PRIORITY + 1
    if len(entries) > available:
        raise ValueError("AppImage payload exceeds deterministic sort priority space")
    for relative in entries:
        if "\n" in relative or "\r" in relative:
            raise ValueError("AppImage payload paths may not contain newlines")
    destination.write_text(
        "".join(f"{relative} {MAX_PRIORITY - index}\n" for index, relative in enumerate(entries)),
        encoding="utf-8",
    )
    return len(entries)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: write_appimage_sort_file.py APPDIR OUTPUT")
    count = write_sort_file(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"Deterministic AppImage sort entries: {count}")


if __name__ == "__main__":
    main()
