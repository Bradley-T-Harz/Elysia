#!/usr/bin/env python3
"""Canonicalize AppDir modes and timestamps before SquashFS assembly."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


def normalize(root: Path, epoch: int) -> int:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("AppImage metadata root must be a real directory")
    if epoch < 0:
        raise ValueError("SOURCE_DATE_EPOCH must be non-negative")
    entries = [root, *sorted(root.rglob("*"))]
    for path in entries:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            os.utime(path, (epoch, epoch), follow_symlinks=False)
        elif stat.S_ISDIR(mode):
            path.chmod(0o755)
            os.utime(path, (epoch, epoch))
        elif stat.S_ISREG(mode):
            path.chmod(0o755 if mode & 0o111 else 0o644)
            os.utime(path, (epoch, epoch))
        else:
            raise ValueError(f"unsupported AppImage payload entry: {path}")
    return len(entries)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: normalize_appimage_metadata.py APPDIR SOURCE_DATE_EPOCH")
    count = normalize(Path(sys.argv[1]), int(sys.argv[2]))
    print(f"Canonical AppImage metadata entries: {count}")


if __name__ == "__main__":
    main()
