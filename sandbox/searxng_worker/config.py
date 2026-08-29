from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_SEARXNG_WORKER_CONFIG_PATH = Path("config/workers/searxng_worker.yaml")
DEFAULT_LOCAL_OVERRIDE_PATH = (
    Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    / "elysia"
    / "workers"
    / "searxng.yaml"
)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass
class SearxngWorkerConfig:
    """Normalized posture config for bounded public SearXNG research."""

    version: int = 1
    worker_key: str = "searxng_research_worker"
    worker_kind: str = "governed_public_web_research_worker"
    state: str = "configured"
    contract_doc: str = "docs/research/searxng_worker_contract.md"
    service: dict[str, Any] = field(default_factory=dict)
    posture: dict[str, Any] = field(default_factory=dict)
    limits: dict[str, Any] = field(default_factory=dict)
    allowed_schemes: list[str] = field(default_factory=list)
    blocked_schemes: list[str] = field(default_factory=list)
    blocked_query_fragments: list[str] = field(default_factory=list)
    sensitive_query_categories: list[str] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)
    ui_truth: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SearxngWorkerConfig":
        return cls(
            version=int(data.get("version") or 1),
            worker_key=str(data.get("worker_key") or "searxng_research_worker"),
            worker_kind=str(
                data.get("worker_kind") or "governed_public_web_research_worker"
            ),
            state=str(data.get("state") or "configured"),
            contract_doc=str(
                data.get("contract_doc")
                or "docs/research/searxng_worker_contract.md"
            ),
            service=dict(data.get("service") or {}),
            posture=dict(data.get("posture") or {}),
            limits=dict(data.get("limits") or {}),
            allowed_schemes=_as_string_list(data.get("allowed_schemes")),
            blocked_schemes=_as_string_list(data.get("blocked_schemes")),
            blocked_query_fragments=_as_string_list(
                data.get("blocked_query_fragments")
            ),
            sensitive_query_categories=_as_string_list(
                data.get("sensitive_query_categories")
            ),
            trace=dict(data.get("trace") or {}),
            ui_truth=dict(data.get("ui_truth") or {}),
        )


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _parse_scalar(value: str) -> Any:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    try:
        return int(text)
    except ValueError:
        return text


def _split_key_value(line: str) -> tuple[str, Any]:
    key, value = line.split(":", 1)
    return key.strip(), _parse_scalar(value)


def _parse_worker_yaml_fallback(text: str) -> dict[str, Any]:
    config: dict[str, Any] = {}
    current_section: str | None = None
    current_list_key: str | None = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        if line.startswith("- "):
            target = current_list_key or current_section
            if target is None:
                continue
            if current_section and current_list_key:
                section = config.setdefault(current_section, {})
                if isinstance(section, dict):
                    section.setdefault(current_list_key, [])
                    section[current_list_key].append(_parse_scalar(line[2:].strip()))
            else:
                config.setdefault(target, [])
                if isinstance(config[target], list):
                    config[target].append(_parse_scalar(line[2:].strip()))
            continue

        if indent == 0:
            current_list_key = None
            if line.endswith(":"):
                current_section = line[:-1].strip()
                config[current_section] = {}
                continue
            current_section = None
            key, value = _split_key_value(line)
            config[key] = value
            continue

        if indent == 2 and current_section:
            key, value = _split_key_value(line)
            section = config.setdefault(current_section, {})
            if isinstance(section, dict):
                if value == "":
                    section[key] = []
                    current_list_key = key
                else:
                    section[key] = value
                    current_list_key = None

    return config


def is_loopback_base_url(base_url: str) -> bool:
    parsed = urlparse(str(base_url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return False
    host = str(parsed.hostname or "").lower()
    if host == "0.0.0.0":
        return False
    return host in LOOPBACK_HOSTS


def _positive_int(mapping: dict[str, Any], key: str, default: int) -> int:
    try:
        value = int(mapping.get(key) or default)
    except (TypeError, ValueError):
        return default
    return value


def validate_searxng_worker_config(config: SearxngWorkerConfig) -> list[str]:
    """Return refusal reasons for unsafe worker config posture."""
    reasons: list[str] = []
    service = config.service
    posture = config.posture
    limits = config.limits

    if config.worker_key != "searxng_research_worker":
        reasons.append(f"Unexpected SearXNG worker key: {config.worker_key}")

    base_url = str(service.get("base_url") or "")
    if not is_loopback_base_url(base_url):
        reasons.append("SearXNG base_url must be loopback http(s), preferably http://127.0.0.1:8888.")

    if str(service.get("search_endpoint") or "/search") != "/search":
        reasons.append("SearXNG search endpoint must remain /search for Sprint 9.")

    for flag in {
        "private_context_allowed",
        "private_context_sent",
        "cloud_search_allowed",
        "cloud_model_allowed",
        "page_fetch_allowed",
        "core_network_access_allowed",
    }:
        if posture.get(flag) is not False:
            reasons.append(f"SearXNG worker config must keep {flag} false.")

    for flag in {
        "public_query_only",
        "network_access_allowed",
        "search_results_first",
        "approval_required_for_sensitive_queries",
    }:
        if posture.get(flag) is not True:
            reasons.append(f"SearXNG worker config must keep {flag} true.")

    if str(posture.get("network_access_scope") or "") != "worker_public_search_only":
        reasons.append("SearXNG worker network scope must be worker_public_search_only.")

    if _positive_int(limits, "max_queries_per_ticket", 3) > 3:
        reasons.append("SearXNG max_queries_per_ticket must not exceed 3.")
    if _positive_int(limits, "max_results_per_query", 5) > 5:
        reasons.append("SearXNG max_results_per_query must not exceed 5.")
    if _positive_int(limits, "max_query_length", 300) > 300:
        reasons.append("SearXNG max_query_length must not exceed 300.")

    if "file" not in {scheme.lower() for scheme in config.blocked_schemes}:
        reasons.append("SearXNG config must block file URLs.")

    return reasons


def load_searxng_worker_config(
    config_path: str | Path = DEFAULT_SEARXNG_WORKER_CONFIG_PATH,
    *,
    local_override_path: str | Path | None = None,
) -> SearxngWorkerConfig:
    """Load and normalize bounded SearXNG worker config without network use."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"SearXNG worker config not found: {path}")

    text = path.read_text(encoding="utf-8")

    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        mapping = loaded if isinstance(loaded, dict) else None
    except Exception:
        mapping = None

    if mapping is None:
        mapping = _parse_worker_yaml_fallback(text)
    if not isinstance(mapping, dict):
        raise ValueError("SearXNG worker config could not be parsed as a mapping.")

    should_load_default_override = Path(config_path) == DEFAULT_SEARXNG_WORKER_CONFIG_PATH
    override_path = Path(local_override_path) if local_override_path is not None else (
        DEFAULT_LOCAL_OVERRIDE_PATH if should_load_default_override else None
    )
    if override_path is not None and override_path.is_file():
        try:
            import yaml  # type: ignore

            override = yaml.safe_load(override_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError("The local SearXNG worker override could not be parsed.") from exc
        if not isinstance(override, dict) or set(override) != {"version", "service"}:
            raise ValueError("The local SearXNG worker override has unsupported fields.")
        service_override = override.get("service")
        if override.get("version") != 1 or not isinstance(service_override, dict):
            raise ValueError("The local SearXNG worker override is invalid.")
        if set(service_override) - {"enabled", "base_url"}:
            raise ValueError("The local SearXNG service override has unsupported fields.")
        if service_override.get("enabled") is not True:
            raise ValueError("A local SearXNG override may only represent an explicitly enabled service.")
        base_url = str(service_override.get("base_url") or "")
        if not is_loopback_base_url(base_url):
            raise ValueError("The local SearXNG override must use a loopback base URL.")
        mapping = dict(mapping)
        mapping["service"] = {**dict(mapping.get("service") or {}), "enabled": True, "base_url": base_url}

    return SearxngWorkerConfig.from_mapping(mapping)


__all__ = (
    "DEFAULT_SEARXNG_WORKER_CONFIG_PATH",
    "DEFAULT_LOCAL_OVERRIDE_PATH",
    "SearxngWorkerConfig",
    "is_loopback_base_url",
    "load_searxng_worker_config",
    "validate_searxng_worker_config",
)
