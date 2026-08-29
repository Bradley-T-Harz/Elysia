#!/usr/bin/env python3
"""Fail-closed guard for populated or destructive Elysia QA runs.

The guard deliberately reports only disposable labels and the synthetic run ID.
It never prints the operator's default paths.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re

from app.install.paths import resolve_elysia_paths


_XDG_KEYS = (
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
    "XDG_RUNTIME_DIR",
)
_RUN_ID = re.compile(r"^pass10d-i-[a-zA-Z0-9._-]{8,160}$")


def _is_relative_to(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
    except ValueError:
        return False
    return candidate != parent


def assert_disposable_xdg(environ: dict[str, str] | None = None) -> dict[str, object]:
    values = dict(os.environ if environ is None else environ)
    run_id = values.get("ELYSIA_QA_RUN_ID", "").strip()
    if not _RUN_ID.fullmatch(run_id):
        raise RuntimeError("ELYSIA_QA_RUN_ID is missing or is not a Pass 10D I synthetic run ID.")

    root_value = values.get("ELYSIA_QA_ROOT", "").strip()
    if not root_value:
        raise RuntimeError("ELYSIA_QA_ROOT is required.")
    root = Path(root_value)
    if not root.is_absolute():
        raise RuntimeError("ELYSIA_QA_ROOT must be absolute.")
    root = root.resolve(strict=True)
    temp_root = Path("/tmp").resolve(strict=True)
    if not _is_relative_to(root, temp_root) or not root.name.startswith("elysia-pass10d-i-"):
        raise RuntimeError("ELYSIA_QA_ROOT must be a run-owned /tmp/elysia-pass10d-i-* directory.")

    bases: list[Path] = []
    for key in _XDG_KEYS:
        raw = values.get(key, "").strip()
        if not raw:
            raise RuntimeError(f"{key} must be explicitly set for Pass 10D I QA.")
        base = Path(raw)
        if not base.is_absolute():
            raise RuntimeError(f"{key} must be absolute.")
        base = base.resolve(strict=False)
        if not _is_relative_to(base, root):
            raise RuntimeError(f"{key} escaped the disposable QA root.")
        bases.append(base)
    if len(set(bases)) != len(bases):
        raise RuntimeError("Every XDG authority must use a distinct disposable base.")

    resolved = resolve_elysia_paths(values)
    resolved_roots = (
        resolved.config_dir,
        resolved.data_dir,
        resolved.state_dir,
        resolved.cache_dir,
        resolved.runtime_dir,
    )
    if any(not _is_relative_to(path.resolve(strict=False), root) for path in resolved_roots):
        raise RuntimeError("Resolved Elysia state escaped the disposable QA root.")

    operator_defaults = resolve_elysia_paths({}, home=Path.home())
    default_roots = {
        operator_defaults.config_dir.resolve(strict=False),
        operator_defaults.data_dir.resolve(strict=False),
        operator_defaults.state_dir.resolve(strict=False),
        operator_defaults.cache_dir.resolve(strict=False),
        operator_defaults.runtime_dir.resolve(strict=False),
    }
    if any(path.resolve(strict=False) in default_roots for path in resolved_roots):
        raise RuntimeError("Resolved Elysia QA state overlaps an operator-default authority.")

    canary = values.get("ELYSIA_QA_CANARY", "")
    if run_id not in canary or not canary.startswith("synthetic-gate-zero-"):
        raise RuntimeError("A run-specific synthetic QA canary is required.")

    return {
        "disposable_xdg": True,
        "run_id": run_id,
        "authority_count": len(resolved_roots),
        "all_authorities_below_run_root": True,
        "operator_defaults_overlap": False,
        "canary_bound_to_run": True,
    }


def main() -> int:
    print(json.dumps(assert_disposable_xdg(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
