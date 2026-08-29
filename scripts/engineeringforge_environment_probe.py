#!/usr/bin/env python3
"""Read-only EngineeringForge environment evidence; never used by production routes."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any


ENVIRONMENT_PROBES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("GeometryForge", "elysia_geometryforge", ("trimesh", "meshio", "stl", "collada"), "configured_worker_disabled_static_module_live"),
    ("CADForge", "elysia_cadforge", ("cadquery", "OCP", "ezdxf", "gmsh"), "configured_worker_disabled_static_module_live"),
    ("RobotModelForge", "elysia_robotforge", ("yourdfpy", "urdf_parser_py", "pinocchio", "hppfcl"), "configured_worker_disabled_static_module_live"),
    ("CAMForge", "elysia_camforge", ("pygcode", "gcodeparser", "gcode_machine"), "configured_worker_disabled_static_module_live"),
    ("BlendForge", "elysia_blendforge", ("numpy",), "metadata_only_future_sandbox_required"),
    ("ParametricForge", "elysia_parametricforge", ("build123d", "cadquery", "ezdxf"), "experimental_dependency_warning"),
)

TOOL_PROBES: tuple[str, ...] = (
    "blender",
    "openscad",
    "meshlab",
    "meshlabserver",
    "assimp",
    "gmsh",
    "librecad",
    "prusa-slicer",
    "slic3r",
    "bCNC",
    "ros2",
    "rviz2",
    "xacro",
    "check_urdf",
    "gz",
    "freecad",
    "qcad",
    "cura",
    "CuraEngine",
    "camotics",
    "linuxcnc",
)

def _environment_root() -> Path:
    explicit = str(os.environ.get("ELYSIA_ENGINEERING_ENV_ROOT") or "").strip()
    if explicit:
        candidate = Path(explicit).expanduser()
        return candidate if candidate.is_absolute() else Path("")
    prefix_text = str(os.environ.get("CONDA_PREFIX") or "").strip()
    if not prefix_text:
        return Path("")
    prefix = Path(prefix_text).expanduser()
    if not prefix.is_absolute():
        return Path("")
    return prefix.parent if prefix.parent.name == "envs" else prefix / "envs"


_ENVS_ROOT = _environment_root()
_PROBE_CODE = (
    "import importlib.util,json,sys;"
    "print(json.dumps({name: importlib.util.find_spec(name) is not None for name in sys.argv[1:]}))"
)


def _probe_environment(forge: str, environment: str, modules: tuple[str, ...], expected_state: str) -> dict[str, Any]:
    if not _ENVS_ROOT.is_absolute():
        return {
            "forge": forge,
            "environment": environment,
            "interpreter_available": False,
            "expected_state": expected_state,
            "modules": {module: False for module in modules},
            "probe_status": "interpreter_unavailable",
        }
    python_path = _ENVS_ROOT / environment / "bin" / "python"
    try:
        resolved_python = python_path.resolve(strict=True)
        resolved_python.relative_to((_ENVS_ROOT / environment).resolve(strict=True))
        interpreter_available = resolved_python.is_file()
    except (OSError, ValueError):
        resolved_python = python_path
        interpreter_available = False
    result: dict[str, Any] = {
        "forge": forge,
        "environment": environment,
        "interpreter_available": interpreter_available,
        "expected_state": expected_state,
        "modules": {module: False for module in modules},
        "probe_status": "interpreter_unavailable",
    }
    if not result["interpreter_available"]:
        return result
    try:
        completed = subprocess.run(
            [str(resolved_python), "-I", "-c", _PROBE_CODE, *modules],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
            timeout=10,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONNOUSERSITE": "1"},
        )
    except (OSError, subprocess.TimeoutExpired):
        result["probe_status"] = "probe_failed_or_timed_out"
        return result
    if completed.returncode != 0 or len(completed.stdout) > 65536 or len(completed.stderr) > 65536:
        result["probe_status"] = "probe_failed_or_output_limited"
        return result
    try:
        parsed = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        result["probe_status"] = "invalid_probe_output"
        return result
    result["modules"] = {module: bool(parsed.get(module)) for module in modules}
    result["probe_status"] = "completed"
    return result


def collect_environment_truth() -> dict[str, Any]:
    return {
        "diagnostic": "engineeringforge_environment_probe",
        "production_route_dependency": False,
        "network_used": False,
        "shell_used": False,
        "heavy_modules_imported": False,
        "environments": [_probe_environment(*probe) for probe in ENVIRONMENT_PROBES],
        "tools": {tool: shutil.which(tool) is not None for tool in TOOL_PROBES},
        "missing_optional_tools_are_not_failures": True,
    }


def main() -> int:
    print(json.dumps(collect_environment_truth(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
