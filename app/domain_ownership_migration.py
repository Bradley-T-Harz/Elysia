"""One-time owner-ID backfill for existing conversation/project authorities."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


def _write_atomic(path: Path, payload: dict) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.stem}-owner-", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def claim_unowned_domain_records(root: Path, owner_user_id: str) -> int:
    """Claim only established records lacking an owner; never overwrite one."""
    if not root.is_dir():
        return 0
    claimed = 0
    for path in sorted(root.glob("*.json")):
        if path.name.startswith("_") or path.is_symlink() or not path.is_file():
            continue
        # Ownership adoption must not make Personal Identity creation depend on
        # the health of an unrelated old conversation/project file. Corrupt
        # records remain untouched for doctor to report and repair later.
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        metadata = payload.get("metadata")
        target = metadata if isinstance(metadata, dict) else payload
        if target.get("owner_user_id"):
            continue
        target["owner_user_id"] = owner_user_id
        _write_atomic(path, payload)
        claimed += 1
    return claimed


__all__ = ("claim_unowned_domain_records",)
