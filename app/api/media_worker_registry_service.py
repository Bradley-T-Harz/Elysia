"""Load sanitized model, voice, and worker capability truth without ML imports."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from app.api.project_paths import config_path, elysia_path
from app.api.worker_runtime_path_service import resolve_worker_python
from app.install.profile_service import load_local_model_override_values


REGISTRY_PATHS = {
    "speechforge": config_path("models", "speechforge_models.yaml"),
    "imageforge": config_path("models", "imageforge_models.yaml"),
    "videoforge": config_path("models", "videoforge_models.yaml"),
}
GATE_REGISTRY_PATH = config_path("policies", "governed_media_gates.yaml")
RUNTIME_REGISTRY_PATH = config_path("models", "media_runtime_registry.yaml")


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _absolute_private_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    return path if path.is_absolute() else None


def _relative_asset_path(root: Path | None, value: Any) -> Path | None:
    text = str(value or "").strip()
    if root is None or not text:
        return None
    relative = Path(text)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    return root / relative


def _local_worker_overrides(kind: str, overrides: dict[str, Any]) -> dict[str, Any]:
    workers = overrides.get("worker_overrides")
    if not isinstance(workers, dict):
        return {}
    values = workers.get(kind)
    return dict(values) if isinstance(values, dict) else {}


def _model_asset_paths(
    kind: str,
    model: dict[str, Any],
    overrides: dict[str, Any],
) -> tuple[Path | None, Path | None]:
    worker = _local_worker_overrides(kind, overrides)
    model_id = str(model.get("id") or "")
    if kind == "speechforge":
        if model_id == "whisper-cpp-base-en":
            return _absolute_private_path(worker.get("transcription_model")), None
        if model_id == "kokoro-onnx-v1":
            return (
                _absolute_private_path(worker.get("tts_model")),
                _absolute_private_path(worker.get("tts_voices")),
            )
        return None, None
    vault = overrides.get("model_vault")
    vault_root = _absolute_private_path(vault.get("root")) if isinstance(vault, dict) else None
    root = _absolute_private_path(worker.get("model_root")) or vault_root
    return (
        _relative_asset_path(root, model.get("relative_path")),
        _relative_asset_path(root, model.get("voices_relative_path")),
    )


def _asset_truth(
    kind: str,
    model: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    sanitized = {
        key: value
        for key, value in model.items()
        if key not in {"local_path", "voices_path", "relative_path", "voices_relative_path"}
    }
    local_path, voices_path = _model_asset_paths(kind, model, overrides)
    sanitized["local_assets_present"] = bool(local_path and local_path.exists())
    if model.get("voices_relative_path") is not None or str(model.get("id") or "") == "kokoro-onnx-v1":
        sanitized["voice_assets_present"] = bool(voices_path and voices_path.exists())
    return sanitized


def _smoke_truth(worker: dict[str, Any]) -> dict[str, Any]:
    smoke = worker.get("smoke_truth")
    if not isinstance(smoke, dict):
        return {}
    return {key: value for key, value in smoke.items() if key not in {"output_path", "provenance_path"}}


def model_registry(kind: str) -> list[dict[str, Any]]:
    path = REGISTRY_PATHS.get(kind)
    if path is None:
        return []
    models = _load_yaml(path).get("models")
    overrides = load_local_model_override_values()
    return (
        [_asset_truth(kind, item, overrides) for item in models if isinstance(item, dict)]
        if isinstance(models, list)
        else []
    )


def governed_media_gates() -> dict[str, Any]:
    """Return explicit public gate truth without host paths or raw content."""
    payload = _load_yaml(GATE_REGISTRY_PATH)
    features = payload.get("features")
    return {
        "version": payload.get("version", 1),
        "status_vocabulary": list(payload.get("status_vocabulary") or []),
        "production_gate": dict(payload.get("production_gate") or {}),
        "features": {
            str(key): dict(value)
            for key, value in (features.items() if isinstance(features, dict) else [])
            if isinstance(value, dict)
        },
    }


def media_runtime_registry() -> list[dict[str, Any]]:
    payload = _load_yaml(RUNTIME_REGISTRY_PATH)
    runtimes = payload.get("runtimes")
    return [dict(item) for item in runtimes if isinstance(item, dict)] if isinstance(runtimes, list) else []


def raw_model_entry(kind: str, model_id: str) -> dict[str, Any] | None:
    path = REGISTRY_PATHS.get(kind)
    models = _load_yaml(path).get("models") if path else None
    if not isinstance(models, list):
        return None
    return next((dict(item) for item in models if isinstance(item, dict) and item.get("id") == model_id), None)


def kokoro_voice_catalog() -> list[dict[str, Any]]:
    payload = _load_yaml(config_path("workers", "kokoro_voice_catalog.yaml"))
    voices = payload.get("voices")
    return [dict(item) for item in voices if isinstance(item, dict) and item.get("enabled") is True] if isinstance(voices, list) else []


def kokoro_voice(voice_id: str) -> dict[str, Any] | None:
    return next((voice for voice in kokoro_voice_catalog() if voice.get("id") == voice_id), None)


def _worker_yaml(name: str) -> dict[str, Any]:
    return _load_yaml(config_path("workers", f"{name}_worker.yaml"))


def resolved_media_runtime_paths(worker_key: str, model_id: str | None = None) -> dict[str, Path]:
    """Resolve private local paths without returning them through a public API."""
    kind = worker_key.removesuffix("_worker")
    overrides = load_local_model_override_values()
    worker = _local_worker_overrides(kind, overrides)
    resolved: dict[str, Path] = {}
    python_path = _absolute_private_path(worker.get("python_path"))
    if python_path is None:
        worker_config = _worker_yaml(kind)
        runtime = (
            worker_config.get("runtime")
            if isinstance(worker_config.get("runtime"), dict)
            else worker_config
        )
        python_path = resolve_worker_python(
            {**worker_config, **runtime},
            override_env=f"ELYSIA_{kind.upper()}_PYTHON",
            allow_current_interpreter=False,
        )
    if python_path is not None:
        resolved["python_path"] = python_path
    if kind == "speechforge":
        mapping = {
            "stt_executable": "executable",
            "stt_model": "transcription_model",
            "tts_model": "tts_model",
            "tts_voices": "tts_voices",
        }
        for target, source in mapping.items():
            value = _absolute_private_path(worker.get(source))
            if value is not None:
                resolved[target] = value
    elif model_id:
        model = raw_model_entry(kind, model_id)
        if model is not None:
            model_path, _ = _model_asset_paths(kind, model, overrides)
            if model_path is not None:
                resolved["model_path"] = model_path
    return resolved


def media_worker_truth() -> dict[str, Any]:
    speech = _worker_yaml("speechforge")
    image = _worker_yaml("imageforge")
    video = _worker_yaml("videoforge")
    speech_runtime = speech.get("runtime") if isinstance(speech.get("runtime"), dict) else {}
    stt = speech.get("stt") if isinstance(speech.get("stt"), dict) else {}
    tts = speech.get("tts") if isinstance(speech.get("tts"), dict) else {}
    speech_paths = resolved_media_runtime_paths("speechforge_worker")
    image_paths = resolved_media_runtime_paths("imageforge_worker")
    video_paths = resolved_media_runtime_paths("videoforge_worker")
    return {
        "gates": governed_media_gates(),
        "runtime_registry": media_runtime_registry(),
        "speechforge": {
            "state": speech.get("state", "unavailable"),
            "enabled": speech.get("enabled") is True,
            "worker_python_present": bool(speech_paths.get("python_path") and speech_paths["python_path"].is_file()),
            "worker_script_present": elysia_path(str(speech_runtime.get("worker_script") or "")).is_file(),
            "stt_enabled": stt.get("enabled") is True,
            "stt_executable_present": bool(speech_paths.get("stt_executable") and speech_paths["stt_executable"].is_file()),
            "stt_model_present": bool(speech_paths.get("stt_model") and speech_paths["stt_model"].is_file()),
            "tts_enabled": tts.get("enabled") is True,
            "tts_model_present": bool(speech_paths.get("tts_model") and speech_paths["tts_model"].is_file()),
            "tts_voices_present": bool(speech_paths.get("tts_voices") and speech_paths["tts_voices"].is_file()),
            "models": model_registry("speechforge"),
        },
        "imageforge": {
            "state": image.get("state", "unavailable"),
            "enabled_by_default": image.get("enabled") is True,
            "lab_environment_enabled": os.environ.get("ELYSIA_IMAGEFORGE_LAB_ENABLED") == "1",
            "worker_python_present": bool(image_paths.get("python_path") and image_paths["python_path"].is_file()),
            "worker_script_present": elysia_path(str(image.get("worker_script") or "")).is_file(),
            "smoke_truth": _smoke_truth(image),
            "models": model_registry("imageforge"),
        },
        "videoforge": {
            "state": video.get("state", "unavailable"),
            "enabled_by_default": video.get("enabled") is True,
            "lab_environment_enabled": os.environ.get("ELYSIA_VIDEOFORGE_LAB_ENABLED") == "1",
            "worker_python_present": bool(video_paths.get("python_path") and video_paths["python_path"].is_file()),
            "worker_script_present": elysia_path(str(video.get("worker_script") or "")).is_file(),
            "routes_live": video.get("routes_live") is True,
            "cancellation_supported": bool((video.get("limits") or {}).get("cancellation_supported")) if isinstance(video.get("limits"), dict) else False,
            "smoke_truth": _smoke_truth(video),
            "models": model_registry("videoforge"),
        },
        "voice_cloning": {
            "state": "deliberately_unavailable",
            "available": False,
            "reference_voice_input_allowed": False,
            "reason": "Voice cloning is identity-bearing and unavailable by design.",
        },
    }


__all__ = (
    "kokoro_voice",
    "kokoro_voice_catalog",
    "governed_media_gates",
    "media_runtime_registry",
    "media_worker_truth",
    "model_registry",
    "resolved_media_runtime_paths",
    "raw_model_entry",
)
