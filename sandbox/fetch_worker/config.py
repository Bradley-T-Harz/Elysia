"""Config loading and validation for the bounded fetch worker."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import yaml
except ImportError:  # pragma: no cover - fallback is for minimal envs
    yaml = None


DEFAULT_FETCH_WORKER_CONFIG_PATH = Path("config/workers/fetch_worker.yaml")


@dataclass(frozen=True)
class FetchWorkerConfig:
    version: int
    worker_key: str
    worker_kind: str
    state: str
    contract_doc: str
    service: dict[str, Any]
    posture: dict[str, Any]
    allowed_schemes: list[str]
    blocked_schemes: list[str]
    blocked_hosts: list[str]
    trace: dict[str, Any]
    ui_truth: dict[str, Any]


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to load fetch worker config.")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Fetch worker config must be a mapping.")
    return raw


def load_fetch_worker_config(
    path: str | Path = DEFAULT_FETCH_WORKER_CONFIG_PATH,
) -> FetchWorkerConfig:
    raw = _load_yaml(Path(path))
    config = FetchWorkerConfig(
        version=int(raw.get("version", 1)),
        worker_key=str(raw.get("worker_key", "bounded_fetch_worker")),
        worker_kind=str(raw.get("worker_kind", "governed_public_page_fetch_worker")),
        state=str(raw.get("state", "configured")),
        contract_doc=str(raw.get("contract_doc", "")),
        service=dict(raw.get("service") or {}),
        posture=dict(raw.get("posture") or {}),
        allowed_schemes=list(raw.get("allowed_schemes") or []),
        blocked_schemes=list(raw.get("blocked_schemes") or []),
        blocked_hosts=list(raw.get("blocked_hosts") or []),
        trace=dict(raw.get("trace") or {}),
        ui_truth=dict(raw.get("ui_truth") or {}),
    )
    validate_fetch_worker_config(config)
    return config


def validate_fetch_worker_config(config: FetchWorkerConfig) -> None:
    if config.worker_key != "bounded_fetch_worker":
        raise ValueError("Fetch worker key must be bounded_fetch_worker.")
    if "http" not in config.allowed_schemes or "https" not in config.allowed_schemes:
        raise ValueError("Fetch worker must allow only bounded HTTP(S) schemes.")
    for scheme in config.allowed_schemes:
        if scheme not in {"http", "https"}:
            raise ValueError(f"Unsupported fetch worker allowed scheme: {scheme}")
    if config.posture.get("private_context_allowed") is not False:
        raise ValueError("Fetch worker config must block private context.")
    if config.posture.get("cloud_search_allowed") is not False:
        raise ValueError("Fetch worker config must block cloud search.")
    if config.posture.get("cloud_model_allowed") is not False:
        raise ValueError("Fetch worker config must block cloud models.")
    if config.posture.get("browser_automation_allowed") is not False:
        raise ValueError("Fetch worker config must block browser automation.")
    if config.posture.get("crawling_allowed") is not False:
        raise ValueError("Fetch worker config must block crawling.")
    if int(config.service.get("timeout_seconds", 0)) < 1:
        raise ValueError("Fetch worker timeout must be positive.")
    if int(config.service.get("max_response_bytes", 0)) < 1:
        raise ValueError("Fetch worker max_response_bytes must be positive.")
    if int(config.service.get("max_decompressed_bytes", 0)) < int(config.service.get("max_response_bytes", 0)):
        raise ValueError("Fetch worker decompressed limit must cover the compressed byte limit.")
    if not 0 <= int(config.service.get("max_redirects", -1)) <= 5:
        raise ValueError("Fetch worker max_redirects must be between zero and five.")
    if config.posture.get("approval_required") is not False:
        raise ValueError("Harmless public GETs must not require per-request approval.")


def is_public_fetch_url(url: str, *, blocked_hosts: list[str]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if not host or host in {item.lower() for item in blocked_hosts}:
        return False
    return True


__all__ = (
    "DEFAULT_FETCH_WORKER_CONFIG_PATH",
    "FetchWorkerConfig",
    "is_public_fetch_url",
    "load_fetch_worker_config",
    "validate_fetch_worker_config",
)
