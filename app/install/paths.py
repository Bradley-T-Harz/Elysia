"""Portable XDG path and runtime-mode contracts for public Elysia installs.

This module resolves locations only.  Directory creation is an explicit call so
read-only status surfaces and tests do not mutate the host as a side effect.
Tracked application/configuration resources remain in the application payload;
operator configuration and runtime data never default into that payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import stat
import sys
from typing import Mapping


APP_DIR_NAME = "elysia"
RUNTIME_MODE_ENV = "ELYSIA_RUNTIME_MODE"


class RuntimeMode(str, Enum):
    SOURCE = "source"
    PACKAGED = "packaged"
    TEST = "test"


class XdgPathError(ValueError):
    """Raised when a path contract cannot be resolved safely."""


@dataclass(frozen=True)
class ElysiaPaths:
    mode: RuntimeMode
    config_dir: Path
    data_dir: Path
    cache_dir: Path
    state_dir: Path
    runtime_dir: Path
    runtime_fallback_used: bool

    @property
    def log_dir(self) -> Path:
        return self.state_dir / "logs"

    @property
    def journal_dir(self) -> Path:
        return self.data_dir / "memory" / "journal" / "sessions"

    @property
    def memory_dir(self) -> Path:
        return self.data_dir / "memory"

    @property
    def memory_database_path(self) -> Path:
        return self.memory_dir / "elysia_memory.sqlite"

    @property
    def memory_blob_dir(self) -> Path:
        return self.memory_dir / "blobs"

    @property
    def memory_archive_dir(self) -> Path:
        return self.memory_dir / "archive"

    @property
    def memory_sealed_dir(self) -> Path:
        return self.memory_dir / "sealed"

    @property
    def memory_backup_dir(self) -> Path:
        return self.memory_dir / "backups"

    @property
    def memory_audit_dir(self) -> Path:
        return self.state_dir / "memory" / "audit"

    @property
    def memory_jobs_dir(self) -> Path:
        return self.state_dir / "memory" / "jobs"

    @property
    def memory_checkpoints_dir(self) -> Path:
        return self.state_dir / "memory" / "checkpoints"

    @property
    def memory_fts_rebuild_dir(self) -> Path:
        return self.cache_dir / "memory" / "fts-rebuild"

    @property
    def memory_projection_dir(self) -> Path:
        return self.cache_dir / "memory" / "projections"

    @property
    def memory_fts_database_path(self) -> Path:
        """Rebuildable plaintext projection for normal (never private/sealed) memory."""
        return self.memory_projection_dir / "lexical-v1.sqlite"

    @property
    def memory_semantic_config_dir(self) -> Path:
        return self.config_dir / "services" / "qdrant"

    @property
    def memory_semantic_client_config_path(self) -> Path:
        return self.memory_semantic_config_dir / "client.json"

    @property
    def memory_semantic_api_key_path(self) -> Path:
        return self.memory_semantic_config_dir / "api-key"

    @property
    def memory_semantic_projection_dir(self) -> Path:
        """Rebuildable Qdrant bytes; canonical Memory never lives here."""
        return self.cache_dir / "memory" / "semantic-qdrant"

    @property
    def memory_semantic_state_path(self) -> Path:
        return self.state_dir / "memory" / "semantic-projection-v1.json"

    @property
    def cognition_dir(self) -> Path:
        return self.data_dir / "cognition"

    @property
    def evidence_database_path(self) -> Path:
        return self.cognition_dir / "research-evidence.sqlite"

    @property
    def conversation_summary_dir(self) -> Path:
        return self.cache_dir / "cognition" / "conversation-summaries"

    @property
    def request_receipt_dir(self) -> Path:
        return self.state_dir / "cognition" / "request-receipts"

    @property
    def compute_governance_database_path(self) -> Path:
        return self.state_dir / "cognition" / "compute-governance.sqlite"

    @property
    def emergency_state_path(self) -> Path:
        return self.state_dir / "cognition" / "emergency-state.json"

    @property
    def memory_lock_dir(self) -> Path:
        return self.runtime_dir / "memory" / "locks"

    @property
    def memory_unlocked_sealed_dir(self) -> Path:
        return self.runtime_dir / "memory" / "unlocked-sealed"

    @property
    def identity_dir(self) -> Path:
        return self.data_dir / "identity"

    @property
    def project_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def conversation_dir(self) -> Path:
        return self.data_dir / "conversations"

    @property
    def artifact_dir(self) -> Path:
        return self.data_dir / "artifacts"

    @property
    def ingest_dir(self) -> Path:
        return self.data_dir / "file_ingest"

    @property
    def auth_dir(self) -> Path:
        return self.runtime_dir / "auth"

    @property
    def doctor_state_dir(self) -> Path:
        return self.state_dir / "doctor"

    def public_summary(self) -> dict[str, object]:
        """Return label-only path truth suitable for UI and diagnostics."""
        return {
            "runtime_mode": self.mode.value,
            "config": "XDG user config",
            "data": "XDG user data",
            "cache": "XDG user cache",
            "state": "XDG user state",
            "runtime": (
                "XDG user state runtime fallback"
                if self.runtime_fallback_used
                else "XDG session runtime"
            ),
            "raw_paths_exposed": False,
            "source_tree_runtime_state": False,
        }


def resolve_runtime_mode(
    environ: Mapping[str, str] | None = None,
    *,
    frozen: bool | None = None,
) -> RuntimeMode:
    values = os.environ if environ is None else environ
    requested = str(values.get(RUNTIME_MODE_ENV, "")).strip().lower()
    if requested:
        try:
            return RuntimeMode(requested)
        except ValueError as exc:
            raise XdgPathError("ELYSIA_RUNTIME_MODE must be source, packaged, or test.") from exc
    frozen_runtime = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    return RuntimeMode.PACKAGED if frozen_runtime else RuntimeMode.SOURCE


def _absolute_base(
    values: Mapping[str, str],
    key: str,
    fallback: Path,
) -> Path:
    configured = str(values.get(key, "")).strip()
    if not configured:
        return fallback
    candidate = Path(configured).expanduser()
    if not candidate.is_absolute():
        raise XdgPathError(f"{key} must be an absolute path when set.")
    return candidate


def resolve_elysia_paths(
    environ: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
    mode: RuntimeMode | str | None = None,
) -> ElysiaPaths:
    values = os.environ if environ is None else environ
    resolved_home = home or Path(str(values.get("HOME", ""))).expanduser()
    if not str(resolved_home) or str(resolved_home) == ".":
        resolved_home = Path.home()
    if not resolved_home.is_absolute():
        raise XdgPathError("The user home path must be absolute.")

    resolved_mode = RuntimeMode(mode) if mode is not None else resolve_runtime_mode(values)
    config_base = _absolute_base(values, "XDG_CONFIG_HOME", resolved_home / ".config")
    data_base = _absolute_base(values, "XDG_DATA_HOME", resolved_home / ".local" / "share")
    cache_base = _absolute_base(values, "XDG_CACHE_HOME", resolved_home / ".cache")
    state_base = _absolute_base(values, "XDG_STATE_HOME", resolved_home / ".local" / "state")
    runtime_value = str(values.get("XDG_RUNTIME_DIR", "")).strip()
    if runtime_value:
        runtime_base = _absolute_base(values, "XDG_RUNTIME_DIR", state_base / APP_DIR_NAME / "runtime")
        runtime_dir = runtime_base / APP_DIR_NAME
        runtime_fallback = False
    else:
        runtime_dir = state_base / APP_DIR_NAME / "runtime"
        runtime_fallback = True

    return ElysiaPaths(
        mode=resolved_mode,
        config_dir=config_base / APP_DIR_NAME,
        data_dir=data_base / APP_DIR_NAME,
        cache_dir=cache_base / APP_DIR_NAME,
        state_dir=state_base / APP_DIR_NAME,
        runtime_dir=runtime_dir,
        runtime_fallback_used=runtime_fallback,
    )


def ensure_elysia_directories(paths: ElysiaPaths) -> tuple[str, ...]:
    """Create only Elysia-owned XDG roots with private user permissions."""
    created: list[str] = []
    for label, directory in (
        ("config", paths.config_dir),
        ("data", paths.data_dir),
        ("cache", paths.cache_dir),
        ("state", paths.state_dir),
        ("runtime", paths.runtime_dir),
    ):
        existed = directory.exists()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            directory.chmod(stat.S_IRWXU)
        except OSError:
            pass
        if not existed:
            created.append(label)
    return tuple(created)


def ensure_memory_directories(paths: ElysiaPaths) -> tuple[str, ...]:
    """Create the canonical private Memory Fabric directory layout."""

    created: list[str] = []
    for label, directory in (
        ("memory_data", paths.memory_dir),
        ("memory_blobs", paths.memory_blob_dir),
        ("memory_archive", paths.memory_archive_dir),
        ("memory_sealed", paths.memory_sealed_dir),
        ("memory_backups", paths.memory_backup_dir),
        ("memory_audit", paths.memory_audit_dir),
        ("memory_jobs", paths.memory_jobs_dir),
        ("memory_checkpoints", paths.memory_checkpoints_dir),
        ("memory_fts_rebuild", paths.memory_fts_rebuild_dir),
        ("memory_projections", paths.memory_projection_dir),
        ("memory_semantic_config", paths.memory_semantic_config_dir),
        ("memory_semantic_projection", paths.memory_semantic_projection_dir),
        ("memory_locks", paths.memory_lock_dir),
        ("memory_unlocked_sealed", paths.memory_unlocked_sealed_dir),
        ("cognition_data", paths.cognition_dir),
        ("conversation_summaries", paths.conversation_summary_dir),
        ("request_receipts", paths.request_receipt_dir),
    ):
        existed = directory.exists()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            directory.chmod(stat.S_IRWXU)
        except OSError:
            pass
        if not existed:
            created.append(label)
    return tuple(created)


__all__ = (
    "APP_DIR_NAME",
    "ElysiaPaths",
    "RUNTIME_MODE_ENV",
    "RuntimeMode",
    "XdgPathError",
    "ensure_elysia_directories",
    "ensure_memory_directories",
    "resolve_elysia_paths",
    "resolve_runtime_mode",
)
