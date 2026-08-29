"""Private resolution of the Setup-selected user-local component root.

The application, account, Memory, cache, and runtime authorities remain in
their stable XDG locations. Only Elysia-owned optional runtimes use this root.
Raw paths stay inside the private Setup receipt.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .paths import ElysiaPaths


class InstallRootError(RuntimeError):
    """The private Setup install-root authority is absent or unsafe."""


def install_root_hash(path: Path) -> str:
    return hashlib.sha256(str(path.resolve(strict=False)).encode()).hexdigest()


def _private_setup_receipt(paths: ElysiaPaths) -> dict[str, Any] | None:
    receipt_path = paths.state_dir / "setup" / "installation.json"
    if not receipt_path.exists():
        return None
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise InstallRootError("The private Setup receipt is unavailable or unsafe.")
    if receipt_path.stat().st_mode & 0o077:
        raise InstallRootError("The private Setup receipt permissions are unsafe.")
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InstallRootError("The private Setup receipt is invalid.") from exc
    if not isinstance(payload, dict):
        raise InstallRootError("The private Setup receipt is invalid.")
    return payload


def resolve_component_runtime_root(paths: ElysiaPaths) -> Path:
    """Resolve one component root for install, Doctor, repair, and removal."""

    receipt = _private_setup_receipt(paths)
    if receipt is None:
        # Direct service tests and pre-Setup source operation retain their
        # historical XDG-data root. Packaged Setup always records its choice.
        return paths.data_dir / "components"
    if receipt.get("status") != "configured":
        raise InstallRootError("The Setup receipt is not configured.")
    raw_root = receipt.get("install_root")
    if not isinstance(raw_root, str) or not raw_root.strip():
        raise InstallRootError("The Setup receipt has no component install-root authority.")
    root = Path(raw_root)
    if not root.is_absolute():
        raise InstallRootError("The Setup component install root is not absolute.")
    resolved = root.resolve(strict=False)
    if resolved in {Path("/"), Path.home().resolve()}:
        raise InstallRootError("The Setup component install root is too broad.")
    expected_hash = receipt.get("install_root_sha256")
    if not isinstance(expected_hash, str) or expected_hash != install_root_hash(resolved):
        raise InstallRootError("The Setup component install-root receipt failed integrity.")
    return resolved / "components"


__all__ = ("InstallRootError", "install_root_hash", "resolve_component_runtime_root")
