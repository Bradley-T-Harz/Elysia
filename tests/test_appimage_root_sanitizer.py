from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sanitize_appimage_root.py"
SPEC = importlib.util.spec_from_file_location("sanitize_appimage_root", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_root(root: Path, initial_target: str) -> Path:
    canonical = root / MODULE.CANONICAL_ICON_TARGET
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(b"canonical-elysia-icon")
    alternate = root / initial_target
    if not alternate.exists():
        alternate.parent.mkdir(parents=True, exist_ok=True)
        alternate.write_bytes(b"alternate-elysia-icon")
    (root / "elysia-desktop.png").symlink_to(initial_target)
    (root / ".DirIcon").symlink_to("elysia-desktop.png")
    return root


def test_root_icon_is_independent_of_linuxdeploy_selection(tmp_path: Path) -> None:
    first = make_root(tmp_path / "first", "usr/share/icons/hicolor/32x32/apps/elysia-desktop.png")
    second = make_root(tmp_path / "second", "usr/share/icons/hicolor/128x128/apps/elysia-desktop.png")

    MODULE.normalize(first)
    MODULE.normalize(second)

    expected = MODULE.CANONICAL_ICON_TARGET.as_posix()
    assert (first / "elysia-desktop.png").readlink().as_posix() == expected
    assert (second / "elysia-desktop.png").readlink().as_posix() == expected
    assert (first / ".DirIcon").readlink().as_posix() == "elysia-desktop.png"
    assert (second / ".DirIcon").readlink().as_posix() == "elysia-desktop.png"
