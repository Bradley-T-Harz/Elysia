from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sanitize_appimage_hook.py"
SPEC = importlib.util.spec_from_file_location("sanitize_appimage_hook", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_normalize_gio_modules_removes_private_multiline_build_path() -> None:
    original = """#!/bin/sh
export APPDIR="$APPDIR"
export GIO_EXTRA_MODULES="$APPDIR/usr/lib/i386-linux-gnu/gio/modules
/tmp/private-build/Elysia.AppDir/usr/lib/x86_64-linux-gnu/gio/modules"
"""

    normalized = MODULE.normalize_gio_extra_modules(original)

    assert "/tmp/private-build" not in normalized
    assert normalized.endswith(
        'export GIO_EXTRA_MODULES="$APPDIR/usr/lib/i386-linux-gnu/gio/modules:'
        '$APPDIR/usr/lib/x86_64-linux-gnu/gio/modules"'
    )


@pytest.mark.parametrize(
    "text",
    [
        "#!/bin/sh\n",
        'export GIO_EXTRA_MODULES="/opt/unrelated"\n',
        'export GIO_EXTRA_MODULES="$APPDIR/usr/lib/a/gio/modules"\n'
        'export GIO_EXTRA_MODULES="$APPDIR/usr/lib/b/gio/modules"\n',
    ],
)
def test_normalize_gio_modules_fails_closed_on_invalid_contract(text: str) -> None:
    with pytest.raises(ValueError):
        MODULE.normalize_gio_extra_modules(text)
