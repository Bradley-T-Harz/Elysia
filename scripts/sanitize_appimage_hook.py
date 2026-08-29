#!/usr/bin/env python3
"""Normalize linuxdeploy's generated GTK hook without private build paths."""

from __future__ import annotations

import re
import sys
from pathlib import Path


GIO_ASSIGNMENT = re.compile(
    r'^export GIO_EXTRA_MODULES="(?P<value>.*?)"\s*$',
    re.MULTILINE | re.DOTALL,
)
GIO_MODULE_SUFFIX = re.compile(r"(/usr/lib/[^:\n\"]+/gio/modules)")


def normalize_gio_extra_modules(text: str) -> str:
    matches = list(GIO_ASSIGNMENT.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"expected one GIO_EXTRA_MODULES assignment, got {len(matches)}")
    suffixes = sorted(set(GIO_MODULE_SUFFIX.findall(matches[0].group("value"))))
    if not suffixes:
        raise ValueError("GIO_EXTRA_MODULES contains no AppDir module paths")
    value = ":".join(f"$APPDIR{suffix}" for suffix in suffixes)
    replacement = f'export GIO_EXTRA_MODULES="{value}"'
    return text[: matches[0].start()] + replacement + text[matches[0].end() :]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: sanitize_appimage_hook.py HOOK")
    hook = Path(sys.argv[1])
    hook.write_text(
        normalize_gio_extra_modules(hook.read_text(encoding="utf-8")),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
