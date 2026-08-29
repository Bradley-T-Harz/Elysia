from __future__ import annotations

import importlib.util
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "normalize_appimage_metadata.py"
SPEC = importlib.util.spec_from_file_location("normalize_appimage_metadata", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_metadata_is_canonical_across_umask_and_creation_time(tmp_path: Path) -> None:
    root = tmp_path / "AppDir"
    root.mkdir(mode=0o770)
    regular = root / "notice.txt"
    regular.write_text("notice", encoding="utf-8")
    regular.chmod(0o664)
    executable = root / "AppRun"
    executable.write_text("run", encoding="utf-8")
    executable.chmod(0o775)
    link = root / ".DirIcon"
    link.symlink_to("notice.txt")
    epoch = 1_787_998_971

    assert MODULE.normalize(root, epoch) == 4

    assert root.stat().st_mode & 0o777 == 0o755
    assert regular.stat().st_mode & 0o777 == 0o644
    assert executable.stat().st_mode & 0o777 == 0o755
    assert int(root.stat().st_mtime) == epoch
    assert int(regular.stat().st_mtime) == epoch
    assert int(executable.stat().st_mtime) == epoch
    assert int(os.lstat(link).st_mtime) == epoch
