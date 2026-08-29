from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import struct
import sys
import zipfile

from app.api.coding_engineering_artifact_service import get_engineering_artifact
from app.api.coding_engineering_service import apply_engineering_preview, inspect_engineering, plan_engineering_preview
from app.api.coding_engineering_type_registry import (
    ENGINEERING_EXTENSIONS,
    engineering_registry_payload,
    engineering_type_from_extension,
)
from app.api.coding_file_service import read_selected_file_preview
from app.api.coding_file_type_registry import detect_file_type
from app.api.coding_operation_service import approve_operation
from app.api.main import create_app
from app.api.routes import coding_engineering
from app.api.schemas.coding_operations import CodingOperationApproveRequest
from app.api.schemas.coding_files import CodingFileReadPreviewRequest
from app.api.schemas.engineering import EngineeringInspectRequest, EngineeringPreviewApplyRequest, EngineeringPreviewPlanRequest
from scripts.engineeringforge_environment_probe import collect_environment_truth


def _ascii_stl(facets: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]) -> str:
    lines = ["solid synthetic"]
    for a, b, c in facets:
        lines.extend(
            [
                "facet normal 0 0 1",
                "outer loop",
                f"vertex {a[0]} {a[1]} {a[2]}",
                f"vertex {b[0]} {b[1]} {b[2]}",
                f"vertex {c[0]} {c[1]} {c[2]}",
                "endloop",
                "endfacet",
            ]
        )
    lines.append("endsolid synthetic")
    return "\n".join(lines) + "\n"


def _binary_stl() -> bytes:
    header = b"synthetic binary STL".ljust(80, b"\x00") + struct.pack("<I", 1)
    triangle = struct.pack("<12fH", 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0)
    return header + triangle


def _iges(entity_type: int = 110) -> str:
    return (
        "synthetic".ljust(72) + "S      1\n"
        + "1H,,2HMM".ljust(72) + "G      1\n"
        + f"{entity_type:8d}".ljust(72) + "D      1\n"
        + "".ljust(72) + "D      2\n"
        + "".ljust(72) + "T      1\n"
    )


def _write_fixture_set(root: Path) -> dict[str, Path]:
    fixtures: dict[str, bytes | str] = {
        "safe_ascii.stl": _ascii_stl([((0, 0, 0), (1, 0, 0), (0, 1, 0))]),
        "safe_binary.stl": _binary_stl(),
        "nonmanifold.stl": _ascii_stl(
            [
                ((0, 0, 0), (1, 0, 0), (0, 1, 0)),
                ((0, 0, 0), (1, 0, 0), (0, -1, 0)),
                ((0, 0, 0), (1, 0, 0), (0, 0, 1)),
            ]
        ),
        "huge_count_header.stl": b"synthetic".ljust(80, b"\x00") + struct.pack("<I", 0xFFFFFFFF),
        "safe.obj": "o private_fixture_part\nv 0 0 0\nv 2 0 0\nv 0 3 0\nf 1 2 3\n",
        "obj_with_mtl.obj": "mtllib safe.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl private_material\nf 1 2 3\n",
        "obj_with_traversal_mtl.obj": "mtllib ../../private.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n",
        "safe.mtl": "newmtl private_material\nmap_Kd texture.png\n",
        "texture.png": b"not decoded by EngineeringForge",
        "safe.dae": '<?xml version="1.0"?><COLLADA version="1.4.1"><asset><unit name="meter" meter="1"/></asset><library_geometries><geometry id="g"/></library_geometries><visual_scene><node id="private"/></visual_scene></COLLADA>',
        "dae_with_external_texture.dae": '<COLLADA version="1.4.1"><library_images><image><init_from>https://example.invalid/private.png</init_from></image></library_images></COLLADA>',
        "dae_with_xml_entity_attack.dae": '<!DOCTYPE x [<!ENTITY attack SYSTEM "file:///etc/passwd">]><COLLADA version="1.4.1">&attack;</COLLADA>',
        "minimal.step": "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AP214'));\nENDSEC;\nDATA;\n#1=CARTESIAN_POINT('',(0.,0.,0.));\n#2=PRODUCT('private_product','',(),());\n#3=MANIFOLD_SOLID_BREP('',#4);\nENDSEC;\nEND-ISO-10303-21;\n",
        "assembly_like.step": "ISO-10303-21;\nHEADER;FILE_SCHEMA(('AP242'));ENDSEC;\nDATA;\n#1=PRODUCT('private_assembly','',(),());\n#2=NEXT_ASSEMBLY_USAGE_OCCURRENCE('','','',#3,#4,$);\nENDSEC;END-ISO-10303-21;\n",
        "malformed.step": "not a STEP exchange",
        "minimal.iges": _iges(),
        "malformed.iges": "not an IGES exchange",
        "simple.dxf": "0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1027\n9\n$INSUNITS\n70\n4\n0\nENDSEC\n0\nSECTION\n2\nTABLES\n0\nLAYER\n2\nprivate_layer\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n0\nLINE\n10\n0\n20\n0\n11\n5\n21\n7\n0\nENDSEC\n0\nEOF\n",
        "dxf_with_xref.dxf": "0\nSECTION\n2\nBLOCKS\n0\nBLOCK\n2\nprivate_xref\n70\n4\n1\n../../outside.dxf\n0\nENDBLK\n0\nENDSEC\n0\nEOF\n",
        "dxf_with_sensitive_text.dxf": "0\nSECTION\n2\nENTITIES\n0\nTEXT\n1\nprivate customer annotation\n10\n0\n20\n0\n0\nENDSEC\n0\nEOF\n",
        "safe.urdf": '<robot name="private_robot"><link name="base"><inertial><mass value="1"/><inertia ixx="1" iyy="1" izz="1" ixy="0" ixz="0" iyz="0"/></inertial></link></robot>',
        "urdf_missing_inertia.urdf": '<robot name="r"><link name="base"/></robot>',
        "urdf_with_mesh_refs.urdf": '<robot name="r"><link name="base"><visual><geometry><mesh filename="meshes/body.dae"/></geometry></visual></link></robot>',
        "urdf_with_package_refs.urdf": '<robot name="r"><link name="base"><visual><geometry><mesh filename="package://private_robot/body.dae"/></geometry></visual></link></robot>',
        "urdf_with_xacro_indicator.urdf": '<robot xmlns:xacro="http://ros.org/wiki/xacro" name="r"><xacro:property name="x" value="1"/><link name="base"/></robot>',
        "urdf_cycle.urdf": '<robot name="r"><link name="a"/><link name="b"/><joint name="ab" type="fixed"><parent link="a"/><child link="b"/></joint><joint name="ba" type="fixed"><parent link="b"/><child link="a"/></joint></robot>',
        "safe.sdf": '<sdf version="1.9"><model name="private_model"><link name="base"><inertial/></link></model></sdf>',
        "sdf_with_plugin.sdf": '<sdf version="1.9"><model name="m"><plugin name="private_plugin" filename="libprivate.so"/></model></sdf>',
        "sdf_with_include_uri.sdf": '<sdf version="1.9"><include><uri>fuel://private/model</uri></include></sdf>',
        "sdf_world.sdf": '<sdf version="1.9"><world name="w"><physics name="p" type="ode"/><light name="l" type="point"/></world></sdf>',
        "safe_preview.gcode": "G21\nG90\nG28\nG0 X0 Y0 Z0\nG1 X10 Y5 F1200\nM2\n",
        "missing_units.gcode": "G90\nG1 X1 Y1\n",
        "rapid_negative_z.gcode": "G21\nG90\nG0 X1 Z-2 F99999\n",
        "spindle_start.gcode": "G21\nG90\nM3 S12000\nG1 X1 F100\n",
        "heater_high_temp.gcode": "G21\nG90\nM109 S350\n",
        "unknown_mcodes.gcode": "G21\nG90\nM987\n",
        "large_file.gcode": ("G1 X1 Y1\n" * 1000),
        "blend_header_fixture.blend": b"BLENDER-v400" + b"\x00" * 64,
        "f3d_header_fixture.f3d": b"opaque local Fusion fixture",
    }
    paths: dict[str, Path] = {}
    for name, content in fixtures.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        paths[name] = path
    (root / "meshes").mkdir()
    (root / "meshes" / "body.dae").write_text("<COLLADA version=\"1.4.1\"/>", encoding="utf-8")
    with zipfile.ZipFile(root / "f3z_archive_fixture.f3z", "w") as archive:
        archive.writestr("private_design.f3d", b"fixture")
        archive.writestr("../traversal.txt", b"never extracted")
    paths["f3z_archive_fixture.f3z"] = root / "f3z_archive_fixture.f3z"
    return paths


def _inspect(root: Path, path: Path):
    return inspect_engineering(
        EngineeringInspectRequest(
            workspace_root=str(root),
            file_path=str(path),
            approval_granted=True,
            approval_reason="synthetic_fixture_test",
        )
    )


def test_registry_recognizes_all_chunk8_formats_and_truth_is_immutable(tmp_path: Path):
    expected = {".stl", ".obj", ".dae", ".step", ".stp", ".iges", ".igs", ".dxf", ".gcode", ".urdf", ".sdf", ".blend", ".f3d", ".f3z"}
    assert expected <= ENGINEERING_EXTENSIONS
    payload = engineering_registry_payload()
    formats = {item["type_id"]: item for item in payload["formats"]}
    assert set(formats) == {"stl", "obj", "dae", "step", "iges", "dxf", "urdf", "sdf", "gcode", "blend", "f3d", "f3z"}
    assert all(item["physical_output_state"] == "unavailable_by_design" for item in formats.values())
    assert all(item["generation_state"] == "unavailable_by_design" for item in formats.values())
    assert payload["hard_boundaries"]["machine_send"] == "unavailable_by_design"
    assert payload["hard_boundaries"]["robot_control"] == "unavailable_by_design"
    assert payload["hard_boundaries"]["cloud_translation_upload"] == "unavailable_by_design"
    assert any(worker["environment"] == "elysia_parametricforge" and worker["state"] == "experimental_dependency_warning" for worker in payload["workers"])
    assert all(worker["live_route_handoff"] is False for worker in payload["workers"])
    for extension in expected:
        descriptor = detect_file_type(f"fixture{extension}")
        assert descriptor.category == "engineering"
        assert descriptor.adapter == "engineering"
        assert descriptor.writable is False
        assert descriptor.patchable is False


def test_registered_aliases_map_to_canonical_types():
    assert engineering_type_from_extension("part.step") == "step"
    assert engineering_type_from_extension("part.stp") == "step"
    assert engineering_type_from_extension("part.iges") == "iges"
    assert engineering_type_from_extension("part.igs") == "iges"
    assert engineering_type_from_extension("program.nc") == "gcode"


def test_all_minimal_format_fixtures_inspect_and_hash_without_mutation(tmp_path: Path):
    fixtures = _write_fixture_set(tmp_path)
    names = [
        "safe_ascii.stl",
        "safe_binary.stl",
        "safe.obj",
        "safe.dae",
        "minimal.step",
        "minimal.iges",
        "simple.dxf",
        "safe.urdf",
        "safe.sdf",
        "safe_preview.gcode",
        "blend_header_fixture.blend",
        "f3d_header_fixture.f3d",
        "f3z_archive_fixture.f3z",
    ]
    before = {name: fixtures[name].read_bytes() for name in names}
    results = {name: _inspect(tmp_path, fixtures[name]) for name in names}
    assert all(result.status == "completed" for result in results.values())
    assert all(result.source_sha256 and len(result.source_sha256) == 64 for result in results.values())
    assert results["safe_ascii.stl"].report["format_variant"] == "ascii"
    assert results["safe_binary.stl"].report["format_variant"] == "binary"
    assert results["minimal.step"].report["exchange_schema"] == ["AP214"]
    assert results["simple.dxf"].report["dxf_version"] == "AC1027"
    assert results["safe.urdf"].report["link_count"] == 1
    assert results["safe.sdf"].report["model_count"] == 1
    assert results["blend_header_fixture.blend"].report["blender_file_version"] == "4.00"
    assert results["f3z_archive_fixture.f3z"].report["container_recognized"] is True
    assert all(result.source_mutated is False and result.network_used is False and result.physical_output_performed is False for result in results.values())
    assert {name: fixtures[name].read_bytes() for name in names} == before


def test_geometry_reports_topology_bounds_and_reference_risks(tmp_path: Path):
    fixtures = _write_fixture_set(tmp_path)
    stl = _inspect(tmp_path, fixtures["nonmanifold.stl"])
    assert stl.report["triangle_count"] == 3
    assert stl.report["nonmanifold_edge_count"] >= 1
    assert "nonmanifold_edges" in stl.risk_counts
    obj = _inspect(tmp_path, fixtures["obj_with_mtl.obj"])
    assert obj.report["vertex_count"] == 3
    assert obj.report["material_count"] == 1
    assert {ref.reference_kind for ref in obj.external_references} >= {"obj_mtl", "obj_texture"}
    traversal = _inspect(tmp_path, fixtures["obj_with_traversal_mtl.obj"])
    assert any(ref.resolution_state == "blocked_traversal" for ref in traversal.external_references)
    assert "blocked_external_references" in traversal.risk_counts
    dae = _inspect(tmp_path, fixtures["dae_with_external_texture.dae"])
    assert dae.report["image_count"] == 1
    assert dae.external_references[0].resolution_state == "blocked_external_scheme"


def test_xml_entity_attack_and_malformed_cad_fail_closed(tmp_path: Path):
    fixtures = _write_fixture_set(tmp_path)
    attack = _inspect(tmp_path, fixtures["dae_with_xml_entity_attack.dae"])
    assert attack.status == "blocked"
    assert attack.blocked_reason == "xml_doctype_or_entity_blocked"
    assert attack.scripts_executed is False and attack.network_used is False
    assert _inspect(tmp_path, fixtures["malformed.step"]).status == "blocked"
    assert _inspect(tmp_path, fixtures["malformed.iges"]).status == "blocked"
    huge = _inspect(tmp_path, fixtures["huge_count_header.stl"])
    assert huge.status == "blocked"


def test_cad_dxf_fusion_reports_are_truthful_and_never_extract(tmp_path: Path):
    fixtures = _write_fixture_set(tmp_path)
    step = _inspect(tmp_path, fixtures["assembly_like.step"])
    assert step.report["assembly_relationship_count"] >= 1
    assert step.report["conversion_readiness"].startswith("plan_only")
    iges = _inspect(tmp_path, fixtures["minimal.iges"])
    assert iges.report["entity_count"] == 1
    assert iges.report["units_detected"] == "millimetre"
    dxf = _inspect(tmp_path, fixtures["dxf_with_xref.dxf"])
    assert dxf.report["xref_count"] == 1
    assert dxf.external_references[0].resolution_state == "blocked_traversal"
    f3z = _inspect(tmp_path, fixtures["f3z_archive_fixture.f3z"])
    assert f3z.report["member_count"] == 2
    assert f3z.report["cloud_translation"] == "unavailable_by_design"
    assert {ref.resolution_state for ref in f3z.external_references} >= {"not_resolved", "blocked_traversal"}
    assert not (tmp_path.parent / "traversal.txt").exists()


def test_robot_models_detect_graph_inertial_xacro_plugin_and_uri_risks(tmp_path: Path):
    fixtures = _write_fixture_set(tmp_path)
    missing = _inspect(tmp_path, fixtures["urdf_missing_inertia.urdf"])
    assert missing.report["inertial_missing_count"] == 1
    assert "missing_inertial" in missing.risk_counts
    package = _inspect(tmp_path, fixtures["urdf_with_package_refs.urdf"])
    assert package.external_references[0].resolution_state == "blocked_package_unmapped"
    xacro = _inspect(tmp_path, fixtures["urdf_with_xacro_indicator.urdf"])
    assert xacro.report["xacro_detected"] is True
    assert xacro.report["xacro_expanded"] is False
    cycle = _inspect(tmp_path, fixtures["urdf_cycle.urdf"])
    assert cycle.report["cycle_detected"] is True
    assert "joint_graph_cycle" in cycle.risk_counts
    plugin = _inspect(tmp_path, fixtures["sdf_with_plugin.sdf"])
    assert plugin.report["plugin_count"] == 1
    assert "plugins_detected_not_loaded" in plugin.risk_counts
    include = _inspect(tmp_path, fixtures["sdf_with_include_uri.sdf"])
    assert include.report["include_count"] == 1
    assert include.external_references[0].resolution_state == "blocked_external_scheme"
    assert all(result.plugins_loaded is False and result.physical_output_performed is False for result in (package, xacro, cycle, plugin, include))


def test_gcode_analysis_flags_dangerous_commands_without_machine_access(tmp_path: Path):
    fixtures = _write_fixture_set(tmp_path)
    expected = {
        "missing_units.gcode": "missing_units",
        "rapid_negative_z.gcode": "negative_z_moves",
        "spindle_start.gcode": "spindle_start",
        "heater_high_temp.gcode": "heater_high_temperature",
        "unknown_mcodes.gcode": "unknown_mcode",
    }
    for name, code in expected.items():
        result = _inspect(tmp_path, fixtures[name])
        assert result.status == "completed"
        assert code in result.risk_counts
        assert result.report["physical_send_state"] == "unavailable_by_design"
        assert result.report["safety_policy_version"] == "cam-gcode-safety-0.1"
        assert result.physical_output_performed is False
    rapid = _inspect(tmp_path, fixtures["rapid_negative_z.gcode"])
    assert "rapid_moves_before_homing" in rapid.risk_counts
    assert "large_feedrate" in rapid.risk_counts


def test_exact_approved_preview_is_local_stale_safe_and_source_immutable(tmp_path: Path):
    fixtures = _write_fixture_set(tmp_path)
    source = fixtures["safe_preview.gcode"]
    before = source.read_bytes()
    plan = plan_engineering_preview(EngineeringPreviewPlanRequest(workspace_root=str(tmp_path), file_path=str(source), approval_granted=True))
    assert plan.status == "planned"
    approval = approve_operation(
        CodingOperationApproveRequest(
            operation_kind="engineering_preview",
            operation_summary="Create exact local SVG projection",
            workspace_root=str(tmp_path),
            exact_files=[str(source)],
            source_hash=plan.source_sha256,
            plan_hash=plan.plan_hash,
            allowed_mutation_class="engineering_preview_artifact",
            operator_approved=True,
            approval_phrase="Approve exact engineering preview",
            rollback_note="Delete local artifact; source remains unchanged.",
        )
    )
    result = apply_engineering_preview(
        EngineeringPreviewApplyRequest(
            operation_id=plan.operation_id,
            workspace_root=str(tmp_path),
            file_path=str(source),
            approval_granted=True,
            operator_approved=True,
            approval_id=approval.approval_id,
            approval_token=approval.approval_token,
            expected_source_sha256=plan.source_sha256,
            expected_plan_hash=plan.plan_hash,
        )
    )
    assert result.status == "completed"
    assert result.artifact and result.artifact.media_type == "image/svg+xml"
    artifact = get_engineering_artifact(result.artifact.artifact_id)
    assert artifact and "<svg" in artifact["text_content"]
    assert "<script" not in artifact["text_content"].lower()
    assert "<image" not in artifact["text_content"].lower()
    assert "href=" not in artifact["text_content"].lower()
    assert result.source_mutated is False and result.project_root_written is False
    assert source.read_bytes() == before

    reused = apply_engineering_preview(
        EngineeringPreviewApplyRequest(
            operation_id=plan.operation_id,
            workspace_root=str(tmp_path),
            file_path=str(source),
            approval_granted=True,
            operator_approved=True,
            approval_id=approval.approval_id,
            approval_token=approval.approval_token,
            expected_source_sha256=plan.source_sha256,
            expected_plan_hash=plan.plan_hash,
        )
    )
    assert reused.status == "approval_required"
    assert reused.blocked_reason == "approval_already_used"
    assert reused.artifact is None

    stale_plan = plan_engineering_preview(EngineeringPreviewPlanRequest(workspace_root=str(tmp_path), file_path=str(source), approval_granted=True))
    stale_approval = approve_operation(
        CodingOperationApproveRequest(
            operation_kind="engineering_preview",
            operation_summary="Create stale test projection",
            workspace_root=str(tmp_path),
            exact_files=[str(source)],
            source_hash=stale_plan.source_sha256,
            plan_hash=stale_plan.plan_hash,
            allowed_mutation_class="engineering_preview_artifact",
            operator_approved=True,
            rollback_note="No source mutation.",
        )
    )
    source.write_text(source.read_text(encoding="utf-8") + "G1 X20 Y20\n", encoding="utf-8")
    stale = apply_engineering_preview(
        EngineeringPreviewApplyRequest(
            operation_id=stale_plan.operation_id,
            workspace_root=str(tmp_path),
            file_path=str(source),
            approval_granted=True,
            operator_approved=True,
            approval_id=stale_approval.approval_id,
            approval_token=stale_approval.approval_token,
            expected_source_sha256=stale_plan.source_sha256,
            expected_plan_hash=stale_plan.plan_hash,
        )
    )
    assert stale.status == "blocked"
    assert stale.blocked_reason == "engineering_hash_or_plan_changed"
    assert stale.artifact is None


def test_artifacts_are_private_and_central_audit_is_sanitized(tmp_path: Path):
    fixtures = _write_fixture_set(tmp_path)
    result = _inspect(tmp_path, fixtures["dxf_with_sensitive_text.dxf"])
    assert result.status == "completed" and result.artifacts
    artifact_root = Path(os.environ["ELYSIA_ENGINEERING_ARTIFACT_ROOT"])
    assert artifact_root.stat().st_mode & 0o777 == 0o700
    for path in artifact_root.rglob("*"):
        expected = 0o700 if path.is_dir() else 0o600
        assert path.stat().st_mode & 0o777 == expected
    audit_root = Path(os.environ["ELYSIA_CODING_AUDIT_ROOT"])
    audit_text = "\n".join(path.read_text(encoding="utf-8") for path in audit_root.glob("*.json"))
    assert "private customer annotation" not in audit_text
    assert "private_layer" not in audit_text
    assert str(tmp_path) not in audit_text
    assert result.source_sha256 in audit_text
    local_report = get_engineering_artifact(result.artifacts[0].artifact_id)
    assert local_report and local_report["payload"]["engineering_format"] == "dxf"

    preview = read_selected_file_preview(
        CodingFileReadPreviewRequest(
            workspace_root=str(tmp_path),
            file_path=str(fixtures["safe_ascii.stl"]),
            session_id="private-engineering-session",
            approval_granted=True,
        )
    )
    assert preview.adapter == "engineering" and preview.status == "blocked"
    audit_text = "\n".join(path.read_text(encoding="utf-8") for path in audit_root.glob("*.json"))
    assert "private-engineering-session" not in audit_text
    assert "safe_ascii.stl" not in audit_text


def test_route_envelopes_jobs_artifacts_and_forbidden_routes(tmp_path: Path):
    fixtures = _write_fixture_set(tmp_path)
    envelope = coding_engineering.post_engineering_inspect(
        EngineeringInspectRequest(workspace_root=str(tmp_path), file_path=str(fixtures["safe.obj"]), approval_granted=True)
    )
    assert envelope["result_type"] == "engineering_inspect"
    assert envelope["locality"] == "local"
    inspection = envelope["data"]["engineering"]
    job = asyncio.run(coding_engineering.get_engineering_job_state(inspection["operation_id"]))
    assert job["data"]["found"] is True
    artifact = asyncio.run(coding_engineering.get_engineering_artifact_detail(inspection["artifacts"][0]["artifact_id"]))
    assert artifact["data"]["found"] is True
    paths = set(create_app().openapi()["paths"])
    types_envelope = asyncio.run(coding_engineering.get_engineering_types())
    assert types_envelope["data"]["conversion_policy"]["state"] == "plan_only"
    assert types_envelope["data"]["robot_model_safety"]["static_inspection"]["xacro_detect_only"] is True
    assert types_envelope["data"]["cam_gcode_safety"]["analysis_only"] is True
    assert {
        "/coding/engineering/types",
        "/coding/engineering/inspect",
        "/coding/engineering/preview/plan",
        "/coding/engineering/preview/apply",
        "/coding/engineering/jobs/{operation_id}",
        "/coding/engineering/jobs/{operation_id}/cancel",
        "/coding/engineering/artifacts/{artifact_id}",
    } <= paths
    forbidden_fragments = ("send", "print", "machine", "controller", "launch-ros", "launch-gazebo", "fusion/upload", "overwrite", "trust-safe")
    assert not any(path.startswith("/coding/engineering") and any(fragment in path.lower() for fragment in forbidden_fragments) for path in paths)


def test_core_imports_no_heavy_engineering_libraries_and_worker_configs_are_locked():
    forbidden_modules = {"cadquery", "OCP", "trimesh", "meshio", "bpy", "yourdfpy", "pinocchio", "pygcode", "gcodeparser"}
    assert forbidden_modules.isdisjoint(sys.modules)
    repo_root = Path(__file__).resolve().parents[1]
    for name in ("geometryforge", "cadforge", "robotmodelforge", "camforge", "blendforge"):
        text = (repo_root / "config" / "workers" / f"{name}_worker.yaml").read_text(encoding="utf-8")
        assert "network_allowed: false" in text
        assert "home_mount_allowed: false" in text
        assert "devices_allowed: false" in text
        assert "shell_allowed: false" in text
        assert "stdin_allowed: false" in text
        assert "project_root_write_allowed: false" in text
        assert "sandbox_output_only: true" in text
        assert "live_route_handoff: false" in text
        assert "fixed_argv_only: true" in text
        assert "enabled: false" in text
        assert "max_concurrent_jobs: 1" in text
    service_text = (repo_root / "app" / "api" / "coding_engineering_service.py").read_text(encoding="utf-8")
    assert "subprocess" not in service_text
    assert "requests" not in service_text
    assert "urlopen" not in service_text
    assert "import serial" not in service_text
    assert "from serial" not in service_text
    domain_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in repo_root.joinpath("app", "api").glob("coding_*service.py")
        if "engineering" in path.name or path.name in {
            "coding_geometry_service.py",
            "coding_cad_service.py",
            "coding_robot_model_service.py",
            "coding_cam_service.py",
            "coding_blend_service.py",
        }
    )
    for forbidden in ("import requests", "from requests", "from urllib.request", "import socket", "import httpx", "import serial", "from serial"):
        assert forbidden not in domain_text


def test_environment_diagnostic_is_bounded_and_not_a_production_dependency():
    truth = collect_environment_truth()
    assert truth["production_route_dependency"] is False
    assert truth["network_used"] is False and truth["shell_used"] is False
    assert truth["heavy_modules_imported"] is False
    assert {item["environment"] for item in truth["environments"]} == {
        "elysia_geometryforge",
        "elysia_cadforge",
        "elysia_robotforge",
        "elysia_camforge",
        "elysia_blendforge",
        "elysia_parametricforge",
    }
    assert all(item["probe_status"] in {"completed", "interpreter_unavailable", "probe_failed_or_timed_out", "probe_failed_or_output_limited", "invalid_probe_output"} for item in truth["environments"])
