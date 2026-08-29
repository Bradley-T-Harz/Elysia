"""Validated acquisition truth derived from Pass-III dispositions.

This module intentionally separates profile selection from download/install
approval. It exposes bounded public metadata and validates every acquisition
record against the authoritative component graph.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from .component_graph_service import load_component_graph


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ACQUISITION_MANIFEST_PATH = ROOT / "config" / "install" / "acquisition_manifests.yaml"
CONTRACT_VERSION = "elysia-acquisition-manifests-1.0"
REQUIRED_FIELDS = {
    "method", "source", "publisher", "identity", "digest", "size_state",
    "estimated_download_bytes", "estimated_installed_bytes", "license",
    "redistribution", "network", "privilege", "removal",
}


class AcquisitionManifestError(ValueError):
    """The acquisition contract cannot safely drive Setup."""


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise AcquisitionManifestError("The acquisition manifest could not be loaded.") from exc
    if not isinstance(payload, dict):
        raise AcquisitionManifestError("The acquisition manifest must be a mapping.")
    return payload


def validate_acquisition_manifests(payload: dict[str, Any]) -> None:
    if payload.get("version") != 1 or payload.get("contract_version") != CONTRACT_VERSION:
        raise AcquisitionManifestError("The acquisition manifest version is unsupported.")
    rules = payload.get("rules")
    if not isinstance(rules, dict) or any(
        rules.get(key) is not expected
        for key, expected in {
            "silent_downloads": False,
            "exact_identity_before_transfer": True,
            "exact_size_before_transfer": True,
            "receipt_required": True,
            "private_data_egress": False,
            "profile_selection_grants_acquisition_approval": False,
            "unlisted_source_allowed": False,
        }.items()
    ):
        raise AcquisitionManifestError("Acquisition safety rules are incomplete.")
    graph_components = set(load_component_graph()["components"])
    components = payload.get("components")
    if not isinstance(components, dict) or set(components) != graph_components:
        raise AcquisitionManifestError("Every graph component needs exactly one acquisition disposition.")
    for component_id, record in components.items():
        if not isinstance(record, dict) or set(record) != REQUIRED_FIELDS:
            raise AcquisitionManifestError(f"Component {component_id} has an incomplete acquisition record.")
        for field in REQUIRED_FIELDS - {"estimated_download_bytes", "estimated_installed_bytes"}:
            if not isinstance(record[field], str) or not record[field].strip():
                raise AcquisitionManifestError(f"Component {component_id} has invalid {field} truth.")
        for field in ("estimated_download_bytes", "estimated_installed_bytes"):
            if not isinstance(record[field], int) or record[field] < 0:
                raise AcquisitionManifestError(f"Component {component_id} has an invalid size estimate.")


def load_acquisition_manifests(
    path: Path = DEFAULT_ACQUISITION_MANIFEST_PATH,
) -> dict[str, Any]:
    payload = _load(path)
    validate_acquisition_manifests(payload)
    return payload


def lock_file_truth(component_id: str) -> dict[str, Any] | None:
    """Verify the tracked hash-lock used by a Python acquisition record."""
    record = load_acquisition_manifests()["components"].get(component_id)
    if not record:
        return None
    identity = str(record["identity"])
    if identity == "hardware-selected exact hash lock":
        prefix = {
            "creator_perception": "creator",
            "scientific_engineering": "neurofabric",
        }.get(component_id)
        if prefix is None:
            return {
                "state": "invalid_hardware_variant_contract",
                "verified": False,
                "raw_path_exposed": False,
            }
        expected: dict[str, str] = {}
        for item in str(record["digest"]).split(";"):
            variant, separator, digest = item.partition("=sha256:")
            if not separator or variant not in {"cpu", "cuda"} or len(digest) != 64:
                return {
                    "state": "invalid_hardware_variant_contract",
                    "verified": False,
                    "raw_path_exposed": False,
                }
            expected[variant] = digest
        variants: dict[str, dict[str, Any]] = {}
        for variant in ("cpu", "cuda"):
            path = ROOT / "config" / "install" / "locks" / f"{prefix}-{variant}-py312.lock.txt"
            actual = sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            variants[variant] = {
                "verified": actual == expected.get(variant),
                "sha256": actual,
            }
        verified = all(item["verified"] for item in variants.values())
        return {
            "state": "variant_selected_after_hardware_proof" if verified else "invalid",
            "verified": verified,
            "variants": variants,
            "raw_path_exposed": False,
        }
    if not identity.endswith(".lock.txt"):
        return None
    path = ROOT / identity
    expected = str(record["digest"]).removeprefix("sha256:")
    actual = sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return {
        "state": "verified" if actual == expected else "invalid",
        "verified": actual == expected,
        "sha256": actual,
        "raw_path_exposed": False,
    }


def public_acquisition_summary() -> dict[str, Any]:
    payload = load_acquisition_manifests()
    rows = []
    for component_id, record in payload["components"].items():
        rows.append({
            "component_id": component_id,
            **record,
            "lock_truth": lock_file_truth(component_id),
        })
    return {
        "contract_version": CONTRACT_VERSION,
        "authority": payload["authority"],
        "rules": payload["rules"],
        "components": rows,
        "raw_paths_exposed": False,
    }


__all__ = (
    "AcquisitionManifestError",
    "CONTRACT_VERSION",
    "DEFAULT_ACQUISITION_MANIFEST_PATH",
    "load_acquisition_manifests",
    "lock_file_truth",
    "public_acquisition_summary",
    "validate_acquisition_manifests",
)
