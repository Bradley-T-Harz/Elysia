"""Authoritative Setup classifications for every release-supported dependency.

The component graph owns profile composition.  The dependency catalog owns
fine-grained package/tool truth.  This module validates the one-to-one A-E
installation disposition between them and returns only public guidance.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from .component_graph_service import load_component_graph
from .dependency_service import validate_dependency_catalog


ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "config" / "install" / "dependency_catalog.yaml"
SYSTEM_PREREQUISITES_PATH = (
    ROOT / "config" / "install" / "system_prerequisites.yaml"
)
DISPOSITIONS_PATH = (
    ROOT / "config" / "install" / "dependency_install_dispositions.yaml"
)
CONTRACT_VERSION = "elysia-dependency-install-dispositions-1.0"
CATEGORIES = {"A", "B", "C", "D", "E"}
GUIDANCE_FIELDS = {
    "title",
    "why",
    "official_source",
    "signup_required",
    "data_leaving_local_control",
    "license_privacy_security",
    "supported_steps",
    "doctor_detection",
    "retry_repair",
}


class DependencyDispositionError(ValueError):
    """Dependency installation classifications are incomplete or ambiguous."""


def _yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise DependencyDispositionError(
            "The dependency installation disposition could not be loaded."
        ) from exc
    if not isinstance(payload, dict):
        raise DependencyDispositionError(
            "The dependency installation disposition must be a mapping."
        )
    return payload


def _valid_guidance(payload: Any) -> bool:
    return bool(
        isinstance(payload, dict)
        and set(payload) == GUIDANCE_FIELDS
        and all(
            isinstance(payload[field], str) and payload[field].strip()
            for field in GUIDANCE_FIELDS - {"supported_steps"}
        )
        and isinstance(payload["supported_steps"], list)
        and payload["supported_steps"]
        and all(
            isinstance(step, str) and step.strip()
            for step in payload["supported_steps"]
        )
    )


def validate_dependency_install_dispositions(
    payload: dict[str, Any],
    *,
    catalog: dict[str, Any] | None = None,
    graph: dict[str, Any] | None = None,
) -> None:
    catalog = catalog or _yaml(CATALOG_PATH)
    graph = graph or load_component_graph()
    validate_dependency_catalog(catalog)
    if (
        payload.get("version") != 1
        or payload.get("contract_version") != CONTRACT_VERSION
        or set(payload.get("category_definitions", {})) != CATEGORIES
        or set(payload.get("categories", {})) != CATEGORIES
    ):
        raise DependencyDispositionError(
            "The dependency installation disposition version is unsupported."
        )
    rules = payload.get("rules")
    if not isinstance(rules, dict) or any(
        rules.get(field) is not expected
        for field, expected in {
            "every_catalog_dependency_classified_once": True,
            "every_graph_system_dependency_classified_once": True,
            "every_runtime_dependency_owned_by_component_graph": True,
            "selected_profile_dependencies_owned_by_component_graph": True,
            "automatic_download_requires_exact_identity_size_source_and_approval": True,
            "system_mutation_requires_exact_polkit_preview": True,
            "category_e_requires_complete_guidance": True,
            "profile_selection_grants_acquisition_approval": False,
            "private_data_egress_during_install": False,
        }.items()
    ):
        raise DependencyDispositionError(
            "The dependency installation safety rules are incomplete."
        )

    classifications = [
        dependency_id
        for category in sorted(CATEGORIES)
        for dependency_id in payload["categories"][category]
    ]
    counts = Counter(classifications)
    catalog_ids = set(catalog["dependencies"])
    if set(classifications) != catalog_ids or any(count != 1 for count in counts.values()):
        missing = sorted(catalog_ids - set(classifications))
        extra = sorted(set(classifications) - catalog_ids)
        duplicates = sorted(key for key, count in counts.items() if count != 1)
        raise DependencyDispositionError(
            "Every dependency needs exactly one Setup category "
            f"(missing={missing}, extra={extra}, duplicates={duplicates})."
        )

    component_map = payload.get("component_dependency_ids")
    if not isinstance(component_map, dict) or set(component_map) != set(graph["components"]):
        raise DependencyDispositionError(
            "Every component needs exactly one dependency projection."
        )
    if any(
        not isinstance(values, list)
        or len(values) != len(set(values))
        or any(value not in catalog_ids for value in values)
        for values in component_map.values()
    ):
        raise DependencyDispositionError(
            "A component dependency projection is invalid."
        )
    contributor_only = payload.get("contributor_only_dependency_ids")
    mapped_ids = {
        dependency_id
        for values in component_map.values()
        for dependency_id in values
    }
    if (
        not isinstance(contributor_only, list)
        or len(contributor_only) != len(set(contributor_only))
        or set(contributor_only) != set(payload["categories"]["E"])
        or mapped_ids != catalog_ids - set(contributor_only)
    ):
        raise DependencyDispositionError(
            "Every runtime dependency must be owned by the component graph, "
            "with contributor-only tools excluded explicitly."
        )

    guidance = payload.get("category_e_guidance")
    guidance_required = set(payload["categories"]["D"]) | set(
        payload["categories"]["E"]
    )
    if not isinstance(guidance, dict) or set(guidance) != guidance_required:
        raise DependencyDispositionError(
            "Every reused or category-E dependency needs exactly one guidance record."
        )
    if any(not _valid_guidance(record) for record in guidance.values()):
        raise DependencyDispositionError(
            "A category-E dependency guidance record is incomplete."
        )
    system_guidance = payload.get("system_only_guidance")
    if not isinstance(system_guidance, dict) or any(
        not isinstance(record, dict)
        or record.get("category") != "E"
        or not _valid_guidance({
            key: value for key, value in record.items() if key != "category"
        })
        for record in system_guidance.values()
    ):
        raise DependencyDispositionError(
            "System-only category-E guidance is incomplete."
        )

    system_categories = payload.get("system_dependency_categories")
    if not isinstance(system_categories, dict) or set(system_categories) != CATEGORIES:
        raise DependencyDispositionError(
            "The component-graph system dependency categories are incomplete."
        )
    system_classifications = [
        dependency_id
        for category in sorted(CATEGORIES)
        for dependency_id in system_categories[category]
    ]
    system_counts = Counter(system_classifications)
    graph_system_ids = {
        dependency_id
        for component in graph["components"].values()
        for dependency_id in component["system_dependencies"]
    }
    if (
        set(system_classifications) != graph_system_ids
        or any(count != 1 for count in system_counts.values())
    ):
        raise DependencyDispositionError(
            "Every component-graph system dependency needs exactly one Setup category."
        )
    system_guidance_refs = payload.get("system_dependency_guidance_refs")
    if (
        not isinstance(system_guidance_refs, dict)
        or set(system_guidance_refs) != set(system_categories["E"])
        or any(
            reference not in guidance and reference not in system_guidance
            for reference in system_guidance_refs.values()
        )
    ):
        raise DependencyDispositionError(
            "Every category-E system dependency needs complete public guidance."
        )


def _system_guidance(
    payload: dict[str, Any], dependency_id: str,
) -> dict[str, Any]:
    reference = payload["system_dependency_guidance_refs"][dependency_id]
    record = (
        payload["category_e_guidance"].get(reference)
        or payload["system_only_guidance"].get(reference)
    )
    return {
        key: value for key, value in record.items() if key != "category"
    }


def load_dependency_install_dispositions() -> dict[str, Any]:
    payload = _yaml(DISPOSITIONS_PATH)
    validate_dependency_install_dispositions(payload)
    return payload


def dependency_install_summary(
    component_ids: list[str],
    *,
    scientific_variant: str = "cpu",
) -> dict[str, Any]:
    payload = load_dependency_install_dispositions()
    catalog = _yaml(CATALOG_PATH)
    graph = load_component_graph()
    if not component_ids or any(item not in graph["components"] for item in component_ids):
        raise DependencyDispositionError(
            "The dependency summary contains an unknown component."
        )
    if scientific_variant not in {"cpu", "cuda"}:
        raise DependencyDispositionError("The scientific dependency variant is invalid.")

    selected: list[str] = []
    for component_id in component_ids:
        for dependency_id in payload["component_dependency_ids"][component_id]:
            if dependency_id.startswith("neurofabric_") and (
                (scientific_variant == "cpu" and dependency_id.endswith("_cuda"))
                or (scientific_variant == "cuda" and dependency_id.endswith("_cpu"))
            ):
                continue
            if dependency_id not in selected:
                selected.append(dependency_id)
    category_by_id = {
        dependency_id: category
        for category, dependency_ids in payload["categories"].items()
        for dependency_id in dependency_ids
    }
    selected_system_ids = sorted({
        dependency_id
        for component_id in component_ids
        for dependency_id in graph["components"][component_id]["system_dependencies"]
    })
    system_category_by_id = {
        dependency_id: category
        for category, dependency_ids in payload["system_dependency_categories"].items()
        for dependency_id in dependency_ids
    }
    system_records = _yaml(SYSTEM_PREREQUISITES_PATH)["dependencies"]
    system_category_counts = {category: 0 for category in sorted(CATEGORIES)}
    system_rows = []
    system_action_groups: dict[str, dict[str, Any]] = {}
    for dependency_id in selected_system_ids:
        category = system_category_by_id[dependency_id]
        system_category_counts[category] += 1
        row = {
            "dependency_id": dependency_id,
            "purpose": system_records[dependency_id]["purpose"],
            "kind": system_records[dependency_id]["kind"],
            "setup_category": category,
            "setup_disposition": payload["category_definitions"][category],
        }
        if category == "E":
            guidance_reference = payload["system_dependency_guidance_refs"][
                dependency_id
            ]
            row["guidance"] = _system_guidance(payload, dependency_id)
            row["guidance_reference"] = guidance_reference
            group = system_action_groups.setdefault(
                guidance_reference,
                {
                    "dependency_id": guidance_reference,
                    "dependency_ids": [],
                    "purposes": [],
                    "kind": "system_prerequisite_group",
                    "setup_category": "E",
                    "setup_disposition": payload["category_definitions"]["E"],
                    "guidance": row["guidance"],
                },
            )
            group["dependency_ids"].append(dependency_id)
            group["purposes"].append(system_records[dependency_id]["purpose"])
        system_rows.append(row)
    rows = []
    category_counts = {category: 0 for category in sorted(CATEGORIES)}
    for dependency_id in selected:
        record = catalog["dependencies"][dependency_id]
        category = category_by_id[dependency_id]
        category_counts[category] += 1
        row = {
            "dependency_id": dependency_id,
            "label": record["package_name"],
            "purpose": record["purpose"],
            "required": record["required"],
            "profile": record["profile"],
            "kind": record["kind"],
            "setup_category": category,
            "setup_disposition": payload["category_definitions"][category],
            "external_download_required": record["external_download_required"],
        }
        if category == "E":
            row["guidance"] = payload["category_e_guidance"][dependency_id]
        rows.append(row)
    return {
        "contract_version": CONTRACT_VERSION,
        "component_ids": component_ids,
        "scientific_variant": scientific_variant,
        "dependency_count": len(rows),
        "category_counts": category_counts,
        "dependencies": rows,
        "category_e_actions": [
            row for row in rows if row["setup_category"] == "E"
        ],
        "system_dependency_count": len(system_rows),
        "system_category_counts": system_category_counts,
        "system_dependencies": system_rows,
        # Multiple graph prerequisite identifiers can intentionally point to
        # one operator action (for example required vs optional Ollama
        # semantics). Keep every prerequisite in ``system_dependencies`` and
        # render each distinct action once with all affected identifiers.
        "system_category_e_actions": list(system_action_groups.values()),
        "profile_selection_grants_acquisition_approval": False,
        "private_data_egress_during_install": False,
        "raw_paths_exposed": False,
    }


def complete_dependency_install_summary() -> dict[str, Any]:
    payload = load_dependency_install_dispositions()
    catalog = _yaml(CATALOG_PATH)
    category_by_id = {
        dependency_id: category
        for category, dependency_ids in payload["categories"].items()
        for dependency_id in dependency_ids
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "dependency_count": len(catalog["dependencies"]),
        "category_counts": {
            category: len(payload["categories"][category])
            for category in sorted(CATEGORIES)
        },
        "system_dependency_count": sum(
            len(payload["system_dependency_categories"][category])
            for category in CATEGORIES
        ),
        "system_category_counts": {
            category: len(payload["system_dependency_categories"][category])
            for category in sorted(CATEGORIES)
        },
        "dependencies": [
            {
                "dependency_id": dependency_id,
                "label": record["package_name"],
                "purpose": record["purpose"],
                "profile": record["profile"],
                "kind": record["kind"],
                "required": record["required"],
                "setup_category": category_by_id[dependency_id],
                "setup_disposition": payload["category_definitions"][
                    category_by_id[dependency_id]
                ],
            }
            for dependency_id, record in sorted(catalog["dependencies"].items())
        ],
        "system_only_guidance": payload["system_only_guidance"],
        "raw_paths_exposed": False,
    }


def external_prerequisite_guidance(dependency_id: str) -> dict[str, Any] | None:
    payload = load_dependency_install_dispositions()
    if dependency_id in payload["system_dependency_guidance_refs"]:
        return {
            "dependency_id": dependency_id,
            "setup_category": "E",
            **_system_guidance(payload, dependency_id),
        }
    return None


__all__ = (
    "CATEGORIES",
    "CONTRACT_VERSION",
    "DependencyDispositionError",
    "complete_dependency_install_summary",
    "dependency_install_summary",
    "external_prerequisite_guidance",
    "load_dependency_install_dispositions",
    "validate_dependency_install_dispositions",
)
