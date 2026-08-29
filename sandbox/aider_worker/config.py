from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_AIDER_WORKER_CONFIG_PATH = Path("config/workers/aider_worker.yaml")


@dataclass
class AiderWorkerConfig:
    """Normalized posture config for the future Aider worker."""

    version: int = 1
    worker_key: str = "aider_worker"
    worker_kind: str = "governed_coding_worker"
    state: str = "skeleton"
    default_repo_key: str = "elysia"
    contract_doc: str = "docs/coder/aider_worker_contract.md"
    posture: dict[str, Any] = field(default_factory=dict)
    filesystem: dict[str, Any] = field(default_factory=dict)
    denied_path_fragments: list[str] = field(default_factory=list)
    denied_file_names: list[str] = field(default_factory=list)
    denied_file_suffixes: list[str] = field(default_factory=list)
    secret_name_fragments: list[str] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)
    ui_truth: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "AiderWorkerConfig":
        return cls(
            version=int(data.get("version") or 1),
            worker_key=str(data.get("worker_key") or "aider_worker"),
            worker_kind=str(data.get("worker_kind") or "governed_coding_worker"),
            state=str(data.get("state") or "skeleton"),
            default_repo_key=str(data.get("default_repo_key") or "elysia"),
            contract_doc=str(
                data.get("contract_doc") or "docs/coder/aider_worker_contract.md"
            ),
            posture=dict(data.get("posture") or {}),
            filesystem=dict(data.get("filesystem") or {}),
            denied_path_fragments=_as_string_list(data.get("denied_path_fragments")),
            denied_file_names=_as_string_list(data.get("denied_file_names")),
            denied_file_suffixes=_as_string_list(data.get("denied_file_suffixes")),
            secret_name_fragments=_as_string_list(data.get("secret_name_fragments")),
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

    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        return text[1:-1]

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


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """
    Parse the deliberately small config/workers/aider_worker.yaml shape.

    This is not a general YAML parser. It exists so the skeleton does not add a
    new dependency.
    """
    config: dict[str, Any] = {}
    current_section: str | None = None
    current_list_key: str | None = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        if line.startswith("- "):
            if current_list_key is None:
                continue
            config.setdefault(current_list_key, [])
            config[current_list_key].append(_parse_scalar(line[2:].strip()))
            continue

        if indent == 0:
            current_section = None
            current_list_key = None

            if line.endswith(":"):
                key = line[:-1].strip()
                config[key] = []
                current_list_key = key
                continue

            key, value = _split_key_value(line)
            config[key] = value
            continue

        if indent == 2 and current_list_key is None:
            continue

        if indent == 2:
            if current_section is None and current_list_key:
                current_list_key = None
            continue

    return config


def _parse_worker_yaml_fallback(text: str) -> dict[str, Any]:
    config: dict[str, Any] = {}
    current_section: str | None = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        if line.startswith("- "):
            if current_section:
                if not isinstance(config.get(current_section), list):
                    config[current_section] = []
                config[current_section].append(_parse_scalar(line[2:].strip()))
            continue

        if indent == 0:
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
            if isinstance(config.get(current_section), dict):
                config[current_section][key] = value
            continue

    return config


def load_aider_worker_config(
    config_path: str | Path = DEFAULT_AIDER_WORKER_CONFIG_PATH,
) -> AiderWorkerConfig:
    """Load and normalize the Aider worker posture config."""
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Aider worker config not found: {path}")

    text = path.read_text(encoding="utf-8")

    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            return AiderWorkerConfig.from_mapping(loaded)
    except Exception:
        pass

    parsed = _parse_worker_yaml_fallback(text)
    if not isinstance(parsed, dict):
        raise ValueError("Aider worker config could not be parsed as a mapping.")

    return AiderWorkerConfig.from_mapping(parsed)
