"""Exact, consented Creator model acquisition and local-vault adoption."""

from __future__ import annotations

from hashlib import sha1, sha256
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import yaml

from .paths import ElysiaPaths


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "config" / "install" / "model_acquisitions.yaml"
CONTRACT_VERSION = "elysia-model-acquisitions-1.0"
CREATOR_MODEL_IDS = ("whisper_cpp_base_en", "kokoro_onnx_v1", "flux1_schnell")


class ModelAcquisitionError(RuntimeError):
    """An exact model plan or transfer could not be trusted."""


def _safe_relative(value: Any) -> Path:
    path = Path(str(value or ""))
    if not path.parts or path.is_absolute() or ".." in path.parts:
        raise ModelAcquisitionError("The model manifest contains an unsafe relative path.")
    return path


def _load_manifest() -> dict[str, Any]:
    try:
        payload = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ModelAcquisitionError("The exact model acquisition manifest is unavailable.") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("version") != 1
        or payload.get("contract_version") != CONTRACT_VERSION
        or not isinstance(payload.get("models"), dict)
    ):
        raise ModelAcquisitionError("The exact model acquisition manifest is invalid.")
    rules = payload.get("rules")
    if not isinstance(rules, dict) or any(
        rules.get(key) is not expected
        for key, expected in {
            "silent_downloads": False,
            "exact_identity_before_transfer": True,
            "exact_size_before_transfer": True,
            "immutable_revision_required": True,
            "verified_receipt_required": True,
            "authenticated_download_state_persisted": False,
            "redistribution_by_elysia": False,
        }.items()
    ):
        raise ModelAcquisitionError("The model acquisition safety rules are incomplete.")
    for model_id, record in payload["models"].items():
        if not isinstance(record, dict) or int(record.get("exact_download_bytes") or 0) <= 0:
            raise ModelAcquisitionError(f"Model {model_id} has no exact transfer identity.")
        if model_id == "qwen3_embedding_0_6b":
            artifacts = record.get("layers")
        else:
            _safe_relative(record.get("target_relative_path"))
            artifacts = record.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ModelAcquisitionError(f"Model {model_id} has no exact artifact set.")
        sizes = [int(item.get("size_bytes") or 0) for item in artifacts if isinstance(item, dict)]
        if len(sizes) != len(artifacts) or any(size <= 0 for size in sizes):
            raise ModelAcquisitionError(f"Model {model_id} has invalid artifact sizes.")
        if sum(sizes) != int(record["exact_download_bytes"]):
            raise ModelAcquisitionError(f"Model {model_id} transfer size does not match its artifacts.")
        if model_id != "qwen3_embedding_0_6b":
            for artifact in artifacts:
                _safe_relative(artifact.get("path"))
                if artifact.get("identity_type") not in {"sha256", "git_blob_sha1"}:
                    raise ModelAcquisitionError(f"Model {model_id} has an unsupported artifact identity.")
                identity = str(artifact.get("identity") or "")
                if len(identity) != (64 if artifact["identity_type"] == "sha256" else 40):
                    raise ModelAcquisitionError(f"Model {model_id} has an invalid artifact digest.")
    return payload


def creator_model_records(model_ids: list[str]) -> dict[str, dict[str, Any]]:
    if len(model_ids) != len(set(model_ids)) or any(item not in CREATOR_MODEL_IDS for item in model_ids):
        raise ModelAcquisitionError("The Creator model selection is invalid.")
    records = _load_manifest()["models"]
    return {model_id: records[model_id] for model_id in model_ids}


def _artifact_identity(path: Path, artifact: dict[str, Any]) -> str:
    if not path.is_file() or path.is_symlink() or path.stat().st_size != int(artifact["size_bytes"]):
        return ""
    if artifact["identity_type"] == "sha256":
        digest = sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(8 * 1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
    digest = sha1()
    digest.update(f"blob {path.stat().st_size}\0".encode("ascii"))
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_vault(root: Path, model_ids: list[str]) -> dict[str, Any]:
    records = creator_model_records(model_ids)
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise ModelAcquisitionError("The selected local model vault is not a safe absolute directory.")
    results: list[dict[str, Any]] = []
    for model_id, record in records.items():
        base = root / _safe_relative(record["target_relative_path"])
        failures = []
        for artifact in record["artifacts"]:
            path = base / _safe_relative(artifact["path"])
            if _artifact_identity(path, artifact) != artifact["identity"]:
                failures.append(str(artifact["path"]))
        results.append({
            "model_id": model_id,
            "verified": not failures,
            "artifact_count": len(record["artifacts"]),
            "failed_artifact_count": len(failures),
        })
    return {
        "verified": all(item["verified"] for item in results),
        "models": results,
        "raw_paths_exposed": False,
    }


def creator_model_plan(model_ids: list[str], local_model_root: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    records = creator_model_records(model_ids)
    local_root: Path | None = None
    local_truth: dict[str, Any] | None = None
    if local_model_root:
        local_root = Path(local_model_root).expanduser().resolve(strict=True)
        local_truth = verify_model_vault(local_root, model_ids)
        if not local_truth["verified"]:
            raise ModelAcquisitionError("The selected local model vault does not match every exact approved artifact.")
    public_models = [
        {
            "model_id": model_id,
            "display_name": record["display_name"],
            "source": record["source"],
            "publisher": record["publisher"],
            "immutable_revision": record["immutable_revision"],
            "license": record["license"],
            "redistribution": record["redistribution"],
            "acceptable_use": record["acceptable_use"],
            "artifact_count": len(record["artifacts"]),
            "exact_download_bytes": 0 if local_root else int(record["exact_download_bytes"]),
            "gated_access": bool(record.get("gated_access")),
        }
        for model_id, record in records.items()
    ]
    return ({
        "selected_model_ids": list(records),
        "models": public_models,
        "model_artifact_count": sum(item["artifact_count"] for item in public_models),
        "model_exact_download_bytes": sum(item["exact_download_bytes"] for item in public_models),
        "local_model_vault_adoption": local_root is not None,
        "local_model_vault_verified": bool(local_truth and local_truth["verified"]),
        "authenticated_state_persisted": False,
        "redistributed_by_elysia": False,
        "raw_paths_exposed": False,
    }, {
        "selected_model_ids": list(records),
        "local_model_root": str(local_root) if local_root else None,
    })


def _artifact_url(record: dict[str, Any], artifact: dict[str, Any]) -> str:
    if artifact.get("url"):
        return str(artifact["url"])
    if record["acquisition_method"] == "direct_https":
        return str(record["source"])
    if record["acquisition_method"] == "authenticated_huggingface_snapshot":
        path = "/".join(quote(part, safe="") for part in _safe_relative(artifact["path"]).parts)
        return f"{record['source']}/resolve/{record['immutable_revision']}/{path}"
    raise ModelAcquisitionError("The selected model has no bounded acquisition adapter.")


def _download(
    record: dict[str, Any], artifact: dict[str, Any], destination: Path,
    cancel: threading.Event, progress: Callable[[str], None] | None,
) -> None:
    headers = {"User-Agent": "Elysia-Setup/1.0"}
    if record.get("gated_access"):
        token = os.environ.get("HF_TOKEN", "").strip()
        if not token:
            raise ModelAcquisitionError(
                "This gated model requires a session-only HF_TOKEN after the user accepts the upstream terms; Elysia does not persist it."
            )
        headers["Authorization"] = f"Bearer {token}"
    request = Request(_artifact_url(record, artifact), headers=headers)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        with urlopen(request, timeout=90) as response, destination.open("wb") as handle:
            while True:
                if cancel.is_set():
                    raise ModelAcquisitionError("The Creator model transfer was cancelled.")
                chunk = response.read(4 * 1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                if progress:
                    progress(str(artifact["path"]))
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        raise ModelAcquisitionError("An approved model artifact could not be transferred from its exact upstream source.") from exc
    if _artifact_identity(destination, artifact) != artifact["identity"]:
        raise ModelAcquisitionError("A transferred model artifact failed its exact size/digest proof.")


def _write_private_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=f".{path.name}-", suffix=".tmp", delete=False,
    ) as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    temporary.replace(path)


def configure_creator_model_overrides(paths: ElysiaPaths, vault_root: Path, model_ids: list[str]) -> None:
    selected = set(model_ids)
    config_path = paths.config_dir / "models" / "local_overrides.yaml"
    payload: dict[str, Any] = {}
    if config_path.is_file() and not config_path.is_symlink() and not config_path.stat().st_mode & 0o077:
        try:
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            payload = loaded if isinstance(loaded, dict) else {}
        except (OSError, UnicodeError, yaml.YAMLError):
            payload = {}
    payload.update({
        "version": 1,
        "contract_version": "elysia-local-model-overrides-1.0",
        "local_only": True,
    })
    payload.setdefault("provider_overrides", {"ollama": {"base_url": "http://127.0.0.1:11434", "role_runtime_tags": {}}})
    payload["model_vault"] = {
        "root": str(vault_root),
        "permit_authenticated_download_state": False,
        "provenance_manifest": str(paths.state_dir / "install" / "components" / "creator-models.json"),
    }
    workers = payload.setdefault("worker_overrides", {})
    speech = workers.setdefault("speechforge", {})
    if "whisper_cpp_base_en" in selected:
        speech["transcription_model"] = str(vault_root / "tools/whisper.cpp/models/ggml-base.en.bin")
    if "kokoro_onnx_v1" in selected:
        speech["tts_model"] = str(vault_root / "speech/kokoro-onnx-v1/kokoro-v1.0.onnx")
        speech["tts_voices"] = str(vault_root / "speech/kokoro-onnx-v1/voices-v1.0.bin")
    if "flux1_schnell" in selected:
        workers.setdefault("imageforge", {})["model_root"] = str(vault_root)
    payload.setdefault("policy", {
        "allow_network_for_model_acquisition": False,
        "allow_runtime_network": False,
        "allow_private_memory_mounts": False,
        "allow_host_docker_socket": False,
        "allow_physical_hardware": False,
    })
    payload["notes"] = ["Created locally by Elysia Setup from exact model receipts; no credential or authenticated state is stored."]
    _write_private_yaml(config_path, payload)


def acquire_creator_models(
    paths: ElysiaPaths, model_ids: list[str], local_model_root: str | None,
    staging_root: Path, cancel: threading.Event,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    records = creator_model_records(model_ids)
    if local_model_root:
        vault_root = Path(local_model_root)
        truth = verify_model_vault(vault_root, model_ids)
        if not truth["verified"]:
            raise ModelAcquisitionError("The adopted local model vault no longer matches the approved preview.")
    else:
        vault_root = paths.data_dir / "models"
        model_stage = staging_root / "models"
        for model_id, record in records.items():
            target = vault_root / _safe_relative(record["target_relative_path"])
            if target.exists():
                if verify_model_vault(vault_root, [model_id])["verified"]:
                    continue
                raise ModelAcquisitionError("An existing model target differs from the approved artifact set; it was not overwritten.")
            staged_target = model_stage / _safe_relative(record["target_relative_path"])
            for artifact in record["artifacts"]:
                _download(record, artifact, staged_target / _safe_relative(artifact["path"]), cancel, progress)
        for model_id, record in records.items():
            source = model_stage / _safe_relative(record["target_relative_path"])
            target = vault_root / _safe_relative(record["target_relative_path"])
            if source.exists():
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                source.replace(target)
        truth = verify_model_vault(vault_root, model_ids)
        if not truth["verified"]:
            raise ModelAcquisitionError("The installed model vault failed its final exact verification.")
    configure_creator_model_overrides(paths, vault_root, model_ids)
    return {
        "contract_version": CONTRACT_VERSION,
        "manifest_sha256": sha256(MANIFEST_PATH.read_bytes()).hexdigest(),
        "status": "ready",
        "selected_model_ids": model_ids,
        "models": truth["models"],
        "vault_adopted": bool(local_model_root),
        "authenticated_state_persisted": False,
        "redistributed_by_elysia": False,
        "raw_paths_exposed": False,
    }


__all__ = (
    "CREATOR_MODEL_IDS", "CONTRACT_VERSION", "ModelAcquisitionError",
    "acquire_creator_models", "creator_model_plan", "creator_model_records",
    "verify_model_vault",
)
