"""Canonical capability truth for EngineeringForge file families."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import shutil
from typing import Any

import yaml

from app.api.schemas.engineering import EngineeringTypeDescriptor


ENGINEERING_TYPE_POLICY_VERSION = "engineering-types-0.1"


@dataclass(frozen=True)
class _Spec:
    type_id: str
    label: str
    family: str
    forge: str
    extensions: tuple[str, ...]
    static_state: str
    report_state: str
    preview_state: str
    conversion_state: str
    repair_state: str
    simulation_state: str
    maximum_live_level: int
    notes: tuple[str, ...] = ()


_SPECS: tuple[_Spec, ...] = (
    _Spec("stl", "STL triangle mesh", "geometry", "GeometryForge", (".stl",), "available", "available", "approval_required", "plan_only", "plan_only", "plan_only", 4, ("Units are not encoded by STL and are always reported as ambiguous.",)),
    _Spec("obj", "Wavefront OBJ mesh", "geometry", "GeometryForge", (".obj",), "available", "available", "approval_required", "plan_only", "plan_only", "plan_only", 4, ("MTL and texture references are reported but never fetched or followed outside the workspace.",)),
    _Spec("dae", "COLLADA scene/mesh", "geometry", "GeometryForge", (".dae",), "available", "available", "plan_only", "plan_only", "plan_only", "plan_only", 3, ("Parsed as defused XML; external images and references are never fetched.",)),
    _Spec("step", "STEP product model", "cad", "CADForge", (".step", ".stp"), "available", "available", "plan_only", "plan_only", "plan_only", "plan_only", 3, ("Static STEP exchange metadata is live; OCP/CadQuery tessellation remains a separately bounded future worker action.",)),
    _Spec("iges", "IGES exchange model", "cad", "CADForge", (".iges", ".igs"), "available", "available", "plan_only", "plan_only", "plan_only", "plan_only", 3, ("Entity and unit metadata do not establish watertightness or unit correctness.",)),
    _Spec("dxf", "DXF drawing/model", "cad", "CADForge", (".dxf",), "available", "available", "approval_required", "plan_only", "plan_only", "plan_only", 4, ("Closed-profile warnings are not cut-ready or manufacturing claims.",)),
    _Spec("urdf", "URDF robot model", "robot_model", "RobotModelForge", (".urdf",), "available", "available", "plan_only", "plan_only", "unavailable_by_design", "plan_only", 3, ("Xacro is detected but never expanded by default; ROS, controllers, RViz, and Gazebo are not launched.",)),
    _Spec("sdf", "SDF simulation description", "robot_model", "RobotModelForge", (".sdf",), "available", "available", "plan_only", "plan_only", "unavailable_by_design", "plan_only", 3, ("Plugins and remote/model URIs are reported but never loaded or fetched.",)),
    _Spec("gcode", "G-code machine instruction text", "cam", "CAMForge", (".gcode", ".nc", ".tap", ".cnc"), "available", "available", "approval_required", "unavailable_by_design", "unavailable_by_design", "plan_only", 4, ("Analysis and a local path preview only; machine send and physical output are unavailable by design.",)),
    _Spec("blend", "Blender scene", "blend", "BlendForge", (".blend",), "metadata_only", "metadata_only", "future_sandbox_required", "unavailable_by_design", "unavailable_by_design", "unavailable_by_design", 1, ("Static header metadata only; embedded scripts, drivers, add-ons, and linked libraries are never executed or loaded.",)),
    _Spec("f3d", "Fusion 360 design archive", "fusion", "CADForge", (".f3d",), "metadata_only", "metadata_only", "unavailable_by_design", "unavailable_by_design", "unavailable_by_design", "unavailable_by_design", 1, ("Limited local metadata only. Export to STEP/STL/DXF in the authoring tool for local-first work.",)),
    _Spec("f3z", "Fusion 360 distributed design archive", "fusion", "CADForge", (".f3z",), "metadata_only", "metadata_only", "unavailable_by_design", "unavailable_by_design", "unavailable_by_design", "unavailable_by_design", 2, ("Container recognition only; Autodesk cloud translation and upload are unavailable by design.",)),
)


def _descriptor(spec: _Spec) -> EngineeringTypeDescriptor:
    metadata_state = "metadata_only" if spec.static_state == "metadata_only" else "available"
    return EngineeringTypeDescriptor(
        type_id=spec.type_id,
        label=spec.label,
        family=spec.family,  # type: ignore[arg-type]
        forge=spec.forge,
        extensions=list(spec.extensions),
        metadata_state=metadata_state,
        static_inspection_state=spec.static_state,  # type: ignore[arg-type]
        report_state=spec.report_state,  # type: ignore[arg-type]
        preview_state=spec.preview_state,  # type: ignore[arg-type]
        conversion_state=spec.conversion_state,  # type: ignore[arg-type]
        repair_state=spec.repair_state,  # type: ignore[arg-type]
        simulation_state=spec.simulation_state,  # type: ignore[arg-type]
        generation_state="unavailable_by_design",
        physical_output_state="unavailable_by_design",
        maximum_live_level=spec.maximum_live_level,
        notes=list(spec.notes),
    )


ENGINEERING_TYPES: tuple[EngineeringTypeDescriptor, ...] = tuple(_descriptor(spec) for spec in _SPECS)
ENGINEERING_EXTENSIONS: set[str] = {extension for spec in _SPECS for extension in spec.extensions}

UNKNOWN_ENGINEERING = EngineeringTypeDescriptor(
    type_id="unknown",
    label="Unsupported or unrecognized engineering file",
    family="geometry",
    forge="EngineeringForge",
    extensions=[],
    static_inspection_state="unsupported",
    report_state="unsupported",
    preview_state="unsupported",
    conversion_state="unsupported",
    repair_state="unsupported",
    simulation_state="unsupported",
    maximum_live_level=0,
    notes=["EngineeringForge handles only explicitly registered engineering formats."],
)


def engineering_type_from_extension(path: Path | str) -> str:
    suffix = Path(str(path)).suffix.lower()
    for spec in _SPECS:
        if suffix in spec.extensions:
            return spec.type_id
    return "unknown"


def descriptor_for_engineering_type(type_id: str) -> EngineeringTypeDescriptor:
    normalized = str(type_id or "").strip().lower()
    for descriptor in ENGINEERING_TYPES:
        if descriptor.type_id == normalized:
            return descriptor
    return UNKNOWN_ENGINEERING


def is_registered_engineering_path(path: Path | str) -> bool:
    return Path(str(path)).suffix.lower() in ENGINEERING_EXTENSIONS


def _path_truth(value: str) -> dict[str, Any]:
    path = Path(value)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(path.parent.parent.resolve(strict=True))
        available = resolved.is_file()
    except (OSError, ValueError):
        available = False
    return {
        "available": available,
        "path_hash": sha256(str(path).encode("utf-8")).hexdigest()[:24] if available else None,
    }


def _tool_truth(name: str, purpose: str, *, permitted_for_live_routes: bool = False) -> dict[str, Any]:
    resolved = shutil.which(name)
    return {
        "tool": name,
        "available": bool(resolved),
        "path_hash": sha256(str(resolved).encode("utf-8")).hexdigest()[:24] if resolved else None,
        "purpose": purpose,
        "permitted_for_live_routes": permitted_for_live_routes,
    }


def _worker_path_truth(worker_key: str) -> dict[str, Any]:
    config_path = Path("config") / "workers" / f"{worker_key}.yaml"
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return {"available": False, "path_hash": None}
    if not isinstance(payload, dict):
        return {"available": False, "path_hash": None}
    python_path = str(payload.get("python_path", "")).strip()
    if not python_path or not Path(python_path).is_absolute():
        return {"available": False, "path_hash": None}
    return _path_truth(python_path)


def engineering_worker_truth() -> list[dict[str, Any]]:
    workers = (
        ("geometryforge_worker", "elysia_geometryforge", "configured_not_launched_static_module_live"),
        ("cadforge_worker", "elysia_cadforge", "configured_not_launched_static_module_live"),
        ("robotmodelforge_worker", "elysia_robotforge", "configured_not_launched_static_module_live"),
        ("camforge_worker", "elysia_camforge", "configured_not_launched_static_module_live"),
        ("blendforge_worker", "elysia_blendforge", "future_sandbox_required"),
        ("parametricforge_worker", "elysia_parametricforge", "experimental_dependency_warning"),
    )
    return [
        {
            "worker_key": key,
            "environment": environment,
            "state": state,
            "live_route_handoff": False,
            **_worker_path_truth(key),
        }
        for key, environment, state in workers
    ]


def engineering_registry_payload() -> dict[str, Any]:
    return {
        "policy_version": ENGINEERING_TYPE_POLICY_VERSION,
        "formats": [descriptor.to_payload() for descriptor in ENGINEERING_TYPES],
        "workers": engineering_worker_truth(),
        "tools": [
            _tool_truth("blender", "presence truth only; no file is loaded by registry or inspection routes"),
            _tool_truth("meshlabserver", "future bounded geometry worker candidate"),
            _tool_truth("assimp", "future bounded neutral conversion candidate"),
            _tool_truth("gmsh", "future bounded CAD/mesh worker candidate"),
            _tool_truth("ros2", "presence truth only; launching robot nodes is forbidden"),
            _tool_truth("gz", "presence truth only; launching simulation/plugins is forbidden"),
        ],
        "capability_ladder": {
            "0": "identify",
            "1": "hash_size_magic_basic_metadata",
            "2": "bounded_static_parse",
            "3": "engineering_report",
            "4": "exact_approved_local_preview_where_available",
            "5": "plan_only_or_unavailable",
            "6": "plan_only_or_unavailable",
            "7": "dry_run_plan_only",
            "8": "unavailable_by_design",
            "9": "unavailable_by_design",
        },
        "hard_boundaries": {
            "physical_output": "unavailable_by_design",
            "machine_send": "unavailable_by_design",
            "robot_control": "unavailable_by_design",
            "script_plugin_execution": "unavailable_by_design",
            "cloud_translation_upload": "unavailable_by_design",
            "source_mutation": "unavailable_by_design",
            "safety_certification": "unavailable_by_design",
        },
    }


__all__ = (
    "ENGINEERING_EXTENSIONS",
    "ENGINEERING_TYPES",
    "ENGINEERING_TYPE_POLICY_VERSION",
    "UNKNOWN_ENGINEERING",
    "descriptor_for_engineering_type",
    "engineering_registry_payload",
    "engineering_type_from_extension",
    "engineering_worker_truth",
    "is_registered_engineering_path",
)
