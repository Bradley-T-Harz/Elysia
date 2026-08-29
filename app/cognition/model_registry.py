"""Measured local model inventory, residency, and bounded outcome history."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from statistics import median
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from app.ids import new_id
from app.install.paths import ElysiaPaths, ensure_elysia_directories, resolve_elysia_paths


REGISTRY_VERSION = "measured-local-model-registry-v1"
ROOT = Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _get_json(url: str, timeout: float) -> dict[str, Any]:
    with urllib_request.urlopen(url, timeout=timeout) as response:
        value = json.loads(response.read().decode("utf-8"))
    return value if isinstance(value, dict) else {}


def model_resource_estimate(
    snapshot: dict[str, Any], runtime_tag: str
) -> dict[str, Any]:
    """Return a conservative estimate from Ollama's measured local inventory.

    The installed artifact plus a bounded runtime/context allowance is used
    for an unloaded model; Ollama's live ``size_vram`` becomes authoritative
    while resident. Missing telemetry never earns a speculative GPU lease.
    """
    model = next(
        (
            item for item in snapshot.get("models", [])
            if isinstance(item, dict) and item.get("runtime_tag") == runtime_tag
        ),
        None,
    )
    if model is None:
        return {
            "runtime_tag": runtime_tag,
            "estimated_ram_mb": 1024,
            "estimated_vram_mb": 0,
            "incremental_vram_mb": 0,
            "measurement_source": "model_inventory_unavailable_cpu_safe_default",
            "loaded": False,
        }
    artifact_mb = max(1, (int(model.get("size_bytes") or 0) + 1024**2 - 1) // 1024**2)
    live_vram_mb = max(
        0, (int(model.get("size_vram_bytes") or 0) + 1024**2 - 1) // 1024**2
    )
    unloaded_runtime_mb = artifact_mb + 1024
    return {
        "runtime_tag": runtime_tag,
        "estimated_ram_mb": live_vram_mb or unloaded_runtime_mb,
        "estimated_vram_mb": live_vram_mb or unloaded_runtime_mb,
        # Ollama owns one resident model allocation. A concurrent governed
        # request leases bounded incremental context/workspace headroom rather
        # than pretending the same model weights must be allocated twice.
        "incremental_vram_mb": 1024 if live_vram_mb else unloaded_runtime_mb,
        "measurement_source": (
            "ollama_live_residency_size_vram" if live_vram_mb
            else "ollama_installed_artifact_plus_runtime_allowance"
        ),
        "loaded": bool(model.get("loaded")),
        "digest": model.get("digest"),
    }


class ModelRegistry:
    def __init__(self, paths: ElysiaPaths | None = None) -> None:
        self.paths = paths or resolve_elysia_paths()
        self.database_path = self.paths.state_dir / "cognition" / "model-registry.sqlite"

    def initialize(self) -> None:
        ensure_elysia_directories(self.paths)
        self.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_outcomes (
                    outcome_id TEXT PRIMARY KEY,
                    runtime_tag TEXT NOT NULL,
                    status TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    load_duration_ns INTEGER,
                    prompt_eval_duration_ns INTEGER,
                    eval_duration_ns INTEGER,
                    created_at_utc TEXT NOT NULL
                )
                """
            )
        try:
            self.database_path.chmod(0o600)
        except OSError:
            pass

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def record_outcome(
        self,
        *,
        runtime_tag: str,
        status: str,
        latency_ms: int,
        provider_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.initialize()
        metadata = provider_metadata or {}
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO model_outcomes (
                    outcome_id, runtime_tag, status, latency_ms, load_duration_ns,
                    prompt_eval_duration_ns, eval_duration_ns, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("modeloutcome"), runtime_tag, status, max(0, int(latency_ms)),
                    metadata.get("load_duration"), metadata.get("prompt_eval_duration"),
                    metadata.get("eval_duration"), _utc_now(),
                ),
            )

    def _history(self) -> dict[str, dict[str, Any]]:
        self.initialize()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT runtime_tag, status, latency_ms, load_duration_ns FROM model_outcomes ORDER BY created_at_utc DESC LIMIT 500"
            ).fetchall()
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(str(row["runtime_tag"]), []).append(row)
        return {
            tag: {
                "sample_count": len(items),
                "success_count": sum(str(item["status"]) == "ok" for item in items),
                "failure_count": sum(str(item["status"]) != "ok" for item in items),
                "median_latency_ms": int(median(int(item["latency_ms"]) for item in items)),
                "median_load_duration_ms": (
                    round(median(int(item["load_duration_ns"]) for item in items if item["load_duration_ns"] is not None) / 1_000_000, 3)
                    if any(item["load_duration_ns"] is not None for item in items)
                    else None
                ),
            }
            for tag, items in grouped.items()
        }

    def snapshot(self, timeout: float = 1.0) -> dict[str, Any]:
        try:
            tags = _get_json("http://127.0.0.1:11434/api/tags", timeout)
            provider_healthy = True
        except (OSError, ValueError, urllib_error.URLError):
            tags = {}
            provider_healthy = False
        try:
            running = _get_json("http://127.0.0.1:11434/api/ps", timeout)
        except (OSError, ValueError, urllib_error.URLError):
            running = {}
        loaded = {
            str(item.get("model") or item.get("name") or ""): item
            for item in running.get("models", [])
            if isinstance(item, dict)
        }
        role_tags: dict[str, list[str]] = {}
        role_capabilities: dict[str, set[str]] = {}
        try:
            import yaml

            role_payload = yaml.safe_load(
                (ROOT / "config" / "models" / "model_roles.yaml").read_text(encoding="utf-8")
            )
            for role_id, role in dict(role_payload.get("roles") or {}).items():
                role_capabilities[str(role_id)] = {
                    str(value)
                    for value in [
                        role.get("purpose"),
                        *list(role.get("requirements") or []),
                    ]
                    if str(value or "").strip()
                }
                for tag in [
                    *list(role.get("preferred_model_runtime_tags") or []),
                    *list(role.get("fallback_model_runtime_tags") or []),
                    *list(role.get("supplementary_model_runtime_tags") or []),
                ]:
                    role_tags.setdefault(str(tag), []).append(str(role_id))
            role_contract_state = "tracked_role_contract_loaded"
        except Exception:
            role_tags = {}
            role_contract_state = "tracked_role_contract_unavailable"
        try:
            history = self._history()
            history_state = "durable"
        except (OSError, sqlite3.Error):
            history = {}
            history_state = "unavailable_read_only_snapshot"
        models = []
        for item in tags.get("models", []):
            if not isinstance(item, dict):
                continue
            tag = str(item.get("name") or item.get("model") or "")
            resident = loaded.get(tag, {})
            details = dict(item.get("details") or {})
            size_bytes = int(item.get("size") or 0)
            models.append(
                {
                    "runtime_tag": tag,
                    "digest": str(item.get("digest") or "") or None,
                    "installed": True,
                    "loaded": bool(resident),
                    "size_bytes": size_bytes,
                    "expected_ram_mb": size_bytes // (1024 * 1024),
                    "size_vram_bytes": int(resident.get("size_vram") or 0),
                    "expected_vram_mb": (
                        int(resident.get("size_vram") or 0) // (1024 * 1024)
                        if resident else None
                    ),
                    "context_length": int(resident.get("context_length") or 0),
                    "expires_at": resident.get("expires_at"),
                    "format": details.get("format"),
                    "family": details.get("family"),
                    "families": list(details.get("families") or []),
                    "parameter_size": details.get("parameter_size"),
                    "quantization_level": details.get("quantization_level"),
                    "role_ids": sorted(set(role_tags.get(tag, []))),
                    "capabilities": sorted({
                        capability
                        for role_id in role_tags.get(tag, [])
                        for capability in role_capabilities.get(role_id, set())
                    }),
                    "benchmark_classes": sorted(set(role_tags.get(tag, []))),
                    "role_assignment_provenance": "config/models/model_roles.yaml",
                    "license_provenance_state": "not_reported_by_ollama_api_requires_model_manifest",
                    "modified_at": item.get("modified_at"),
                    "history": history.get(tag, {"sample_count": 0, "success_count": 0, "failure_count": 0, "median_latency_ms": None, "median_load_duration_ms": None}),
                    "local_external_state": "installed_local_ollama",
                }
            )
        return {
            "version": REGISTRY_VERSION,
            "provider": "ollama",
            "provider_healthy": provider_healthy,
            "local_only": True,
            "models": models,
            "captured_at_utc": _utc_now(),
            "private_content_included": False,
            "outcome_history_state": history_state,
            "role_contract_state": role_contract_state,
        }


__all__ = ("ModelRegistry", "REGISTRY_VERSION", "model_resource_estimate")
