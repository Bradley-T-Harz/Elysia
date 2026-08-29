#!/usr/bin/env python3
"""Canonicalize AppImage root icon links independently of filesystem order."""

from __future__ import annotations

import sys
from pathlib import Path


CANONICAL_ICON_TARGET = Path(
    "usr/share/icons/hicolor/256x256@2/apps/elysia-desktop.png"
)


def replace_symlink(path: Path, target: str) -> None:
    if path.exists() or path.is_symlink():
        path.unlink()
    path.symlink_to(target)


def normalize(root: Path) -> None:
    canonical = root / CANONICAL_ICON_TARGET
    if not canonical.is_file() or canonical.is_symlink():
        raise ValueError("AppImage payload is missing the canonical high-resolution Elysia icon")
    replace_symlink(root / "elysia-desktop.png", CANONICAL_ICON_TARGET.as_posix())
    replace_symlink(root / ".DirIcon", "elysia-desktop.png")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: sanitize_appimage_root.py APPDIR")
    normalize(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
