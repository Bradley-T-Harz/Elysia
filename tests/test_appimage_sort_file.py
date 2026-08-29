from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "write_appimage_sort_file.py"
SPEC = importlib.util.spec_from_file_location("write_appimage_sort_file", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_tree(root: Path, order: list[str]) -> Path:
    root.mkdir()
    for relative in order:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
    return root


def test_sort_file_is_independent_of_creation_order(tmp_path: Path) -> None:
    names = ["usr/bin/elysia", "Elysia.desktop", "usr/share/icons/elysia.png"]
    first = make_tree(tmp_path / "first", names)
    second = make_tree(tmp_path / "second", list(reversed(names)))
    first_output = tmp_path / "first.sort"
    second_output = tmp_path / "second.sort"

    first_count = MODULE.write_sort_file(first, first_output)
    second_count = MODULE.write_sort_file(second, second_output)

    assert first_count == second_count
    assert first_output.read_bytes() == second_output.read_bytes()
    lines = first_output.read_text(encoding="utf-8").splitlines()
    assert lines == sorted(lines, key=lambda line: line.rsplit(" ", 1)[0])
    priorities = [int(line.rsplit(" ", 1)[1]) for line in lines]
    assert len(priorities) == len(set(priorities))
    assert priorities == sorted(priorities, reverse=True)
