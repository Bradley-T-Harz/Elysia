"""Bounded RobotModelForge inspectors for URDF and SDF XML."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from app.api.coding_engineering_static import (
    EngineeringInspectionError,
    classify_reference,
    local_name,
    parse_defused_xml,
    read_bounded_text,
    risk,
)


def _children(element: Any, name: str) -> list[Any]:
    return [child for child in list(element) if local_name(child.tag) == name]


def _first(element: Any, name: str) -> Any | None:
    return next((child for child in list(element) if local_name(child.tag) == name), None)


def _cycle_present(graph: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(child) for child in graph.get(node, [])):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def _urdf_report(path: Path, workspace_root: Path, limits: dict[str, int]) -> dict[str, Any]:
    root = parse_defused_xml(path, limits["max_xml_bytes"])
    if local_name(root.tag) != "robot":
        raise EngineeringInspectionError("urdf_root_not_robot")
    all_elements = list(root.iter())
    if len(all_elements) > limits["max_entities"]:
        raise EngineeringInspectionError("robot_entity_limit_exceeded")
    raw_text = read_bounded_text(path, limits["max_xml_bytes"])
    xacro_detected = "xacro:" in raw_text or "${" in raw_text or "$(" in raw_text
    links = _children(root, "link")
    joints = _children(root, "joint")
    link_names = {str(link.attrib.get("name") or "") for link in links if link.attrib.get("name")}
    joint_types: Counter[str] = Counter()
    graph: dict[str, list[str]] = {name: [] for name in link_names}
    parent_links: set[str] = set()
    child_links: set[str] = set()
    missing_link_refs = 0
    missing_joint_limits = 0
    joint_limits = 0
    for joint in joints:
        joint_type = str(joint.attrib.get("type") or "unknown")
        joint_types[joint_type] += 1
        parent = _first(joint, "parent")
        child = _first(joint, "child")
        parent_name = str(parent.attrib.get("link") or "") if parent is not None else ""
        child_name = str(child.attrib.get("link") or "") if child is not None else ""
        if not parent_name or parent_name not in link_names:
            missing_link_refs += 1
        if not child_name or child_name not in link_names:
            missing_link_refs += 1
        if parent_name and child_name:
            graph.setdefault(parent_name, []).append(child_name)
            parent_links.add(parent_name)
            child_links.add(child_name)
        limit = _first(joint, "limit")
        if limit is not None:
            joint_limits += 1
        elif joint_type in {"revolute", "prismatic"}:
            missing_joint_limits += 1
    roots = sorted(link_names - child_links)
    cycle = _cycle_present(graph)
    inertial_present = 0
    mass_warning_count = 0
    inertia_warning_count = 0
    visual_count = 0
    collision_count = 0
    geometry_counts: Counter[str] = Counter()
    references = []
    for link in links:
        inertial = _first(link, "inertial")
        if inertial is not None:
            inertial_present += 1
            mass = _first(inertial, "mass")
            try:
                mass_value = float(mass.attrib.get("value", "nan")) if mass is not None else float("nan")
            except ValueError:
                mass_value = float("nan")
            if not (mass_value > 0):
                mass_warning_count += 1
            inertia = _first(inertial, "inertia")
            try:
                diagonal = [float(inertia.attrib.get(key, "nan")) for key in ("ixx", "iyy", "izz")] if inertia is not None else []
            except ValueError:
                diagonal = []
            if len(diagonal) != 3 or any(value <= 0 for value in diagonal) or any(diagonal[index] > sum(diagonal) - diagonal[index] for index in range(3)):
                inertia_warning_count += 1
        for role in ("visual", "collision"):
            nodes = _children(link, role)
            if role == "visual":
                visual_count += len(nodes)
            else:
                collision_count += len(nodes)
            for node in nodes:
                geometry = _first(node, "geometry")
                if geometry is None:
                    continue
                for child in list(geometry):
                    kind = local_name(child.tag)
                    geometry_counts[kind] += 1
                    if kind == "mesh" and child.attrib.get("filename"):
                        references.append(classify_reference(str(child.attrib["filename"]), source_path=path, workspace_root=workspace_root, reference_kind="urdf_mesh"))
    references = references[: limits["max_external_references"]]
    transmission_count = sum(1 for item in all_elements if local_name(item.tag) == "transmission")
    gazebo_tag_count = sum(1 for item in all_elements if local_name(item.tag) == "gazebo")
    material_count = sum(1 for item in all_elements if local_name(item.tag) == "material")
    flags = [risk("robot_safety_not_assessed", "info", "Static model inspection is not robot, control, inertial, or physical safety certification.")]
    if xacro_detected:
        flags.append(risk("xacro_detected_not_expanded", "warning", "Xacro indicators were detected; expansion is disabled and requires a future sandbox."))
    if cycle:
        flags.append(risk("joint_graph_cycle", "high", "A cycle was detected in the parent/child joint graph."))
    if missing_link_refs:
        flags.append(risk("missing_joint_link_reference", "high", "Joint parent/child references are missing or do not name a declared link.", missing_link_refs))
    if len(roots) != 1:
        flags.append(risk("root_link_ambiguity", "warning", "The model does not have exactly one statically detected root link.", max(1, len(roots))))
    missing_inertial = len(links) - inertial_present
    if missing_inertial:
        flags.append(risk("missing_inertial", "warning", "Links without inertial data were detected.", missing_inertial))
    if mass_warning_count or inertia_warning_count:
        flags.append(risk("inertial_sanity_warning", "high", "Non-positive mass or non-physical-looking inertia diagonals were detected.", mass_warning_count + inertia_warning_count))
    if missing_joint_limits:
        flags.append(risk("missing_joint_limits", "warning", "Revolute or prismatic joints without limit elements were detected.", missing_joint_limits))
    blocked_refs = sum(1 for ref in references if ref.resolution_state.startswith("blocked_"))
    if blocked_refs:
        flags.append(risk("blocked_mesh_references", "high", "Package, remote, absolute, traversal, or symlink mesh references were not followed.", blocked_refs))
    return {
        "robot_name": str(root.attrib.get("name") or "")[:240],
        "link_count": len(links),
        "joint_count": len(joints),
        "joint_types": dict(joint_types),
        "root_links": roots[: limits["max_names_in_response"]],
        "joint_graph": {key: value[: limits["max_names_in_response"]] for key, value in list(sorted(graph.items()))[: limits["max_names_in_response"]]},
        "cycle_detected": cycle,
        "missing_link_reference_count": missing_link_refs,
        "visual_count": visual_count,
        "collision_count": collision_count,
        "geometry_counts": dict(geometry_counts),
        "inertial_present_count": inertial_present,
        "inertial_missing_count": missing_inertial,
        "mass_warning_count": mass_warning_count,
        "inertia_warning_count": inertia_warning_count,
        "material_count": material_count,
        "joint_limit_count": joint_limits,
        "missing_joint_limit_count": missing_joint_limits,
        "transmission_count": transmission_count,
        "gazebo_tag_count": gazebo_tag_count,
        "xacro_detected": xacro_detected,
        "xacro_expanded": False,
        "risk_flags": flags,
        "external_references": references,
        "magic_summary": "URDF robot XML",
    }


def _sdf_report(path: Path, workspace_root: Path, limits: dict[str, int]) -> dict[str, Any]:
    root = parse_defused_xml(path, limits["max_xml_bytes"])
    if local_name(root.tag) != "sdf":
        raise EngineeringInspectionError("sdf_root_not_sdf")
    elements = list(root.iter())
    if len(elements) > limits["max_entities"]:
        raise EngineeringInspectionError("robot_entity_limit_exceeded")
    counts = Counter(local_name(element.tag) for element in elements)
    references = []
    plugin_names: list[str] = []
    physics: list[dict[str, Any]] = []
    for element in elements:
        name = local_name(element.tag)
        if name == "uri" and element.text and element.text.strip():
            references.append(classify_reference(element.text.strip(), source_path=path, workspace_root=workspace_root, reference_kind="sdf_uri"))
        elif name == "plugin":
            plugin_names.append(str(element.attrib.get("name") or element.attrib.get("filename") or "unnamed")[:240])
            plugin_file = str(element.attrib.get("filename") or "").strip()
            if plugin_file:
                references.append(classify_reference(plugin_file, source_path=path, workspace_root=workspace_root, reference_kind="sdf_plugin_binary"))
        elif name == "physics":
            physics.append({
                "name": str(element.attrib.get("name") or "")[:120],
                "type": str(element.attrib.get("type") or "")[:80],
                "default": str(element.attrib.get("default") or "")[:20],
            })
    references = references[: limits["max_external_references"]]
    flags = [risk("simulation_safety_not_assessed", "info", "Static SDF inspection does not validate physics, sensors, plugins, controls, or real-world safety.")]
    if counts["plugin"]:
        flags.append(risk("plugins_detected_not_loaded", "high", "SDF/Gazebo plugins were detected and were not loaded.", counts["plugin"]))
    blocked_refs = sum(1 for ref in references if ref.resolution_state.startswith("blocked_"))
    if blocked_refs:
        flags.append(risk("blocked_sdf_references", "high", "Remote, model, fuel, package, absolute, traversal, or symlink resources were not fetched or followed.", blocked_refs))
    if counts["include"]:
        flags.append(risk("includes_not_expanded", "warning", "SDF include elements were reported but never expanded.", counts["include"]))
    model_depth = 0

    def walk(element: Any, depth: int) -> None:
        nonlocal model_depth
        if local_name(element.tag) == "model":
            model_depth = max(model_depth, depth)
            depth += 1
        for child in list(element):
            walk(child, depth)

    walk(root, 0)
    return {
        "sdf_version": root.attrib.get("version"),
        "world_count": counts["world"],
        "model_count": counts["model"],
        "nested_model_max_depth": model_depth,
        "link_count": counts["link"],
        "joint_count": counts["joint"],
        "sensor_count": counts["sensor"],
        "plugin_count": counts["plugin"],
        "plugin_names": plugin_names[: limits["max_names_in_response"]],
        "physics_settings": physics[: limits["max_names_in_response"]],
        "include_count": counts["include"],
        "visual_count": counts["visual"],
        "collision_count": counts["collision"],
        "inertial_count": counts["inertial"],
        "light_count": counts["light"],
        "camera_count": counts["camera"],
        "risk_flags": flags,
        "external_references": references,
        "magic_summary": f"SDF XML {root.attrib.get('version') or 'unknown version'}",
    }


def inspect_robot_model(path: Path, *, type_id: str, workspace_root: Path, limits: dict[str, int]) -> dict[str, Any]:
    if type_id == "urdf":
        return _urdf_report(path, workspace_root, limits)
    if type_id == "sdf":
        return _sdf_report(path, workspace_root, limits)
    raise EngineeringInspectionError("unsupported_robot_model_format")


__all__ = ("inspect_robot_model",)
