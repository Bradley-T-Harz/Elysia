# Chunk 8 final truth: EngineeringForge

Chunk 8 moves Elysia from generic file awareness to bounded engineering-file stewardship. The implementation follows the canonical Chunk 8 specification and the recorded local-install evidence rather than assuming an ideal toolchain.

## Local environment evidence

The preparation record showed system Blender 4.0.2, OpenSCAD, MeshLab/`meshlabserver`, Assimp, gmsh, LibreCAD, PrusaSlicer/Slic3r, bCNC, ROS 2 Jazzy tooling, RViz, xacro/check_urdf, and gz vendor tooling. It also showed that FreeCAD, QCAD, Cura/CuraEngine, CAMotics, and LinuxCNC were unavailable. Their absence is not reported as a failure because no live route depends on them.

Lightweight import probes in the preparation record confirmed the GeometryForge, CADForge, RobotForge, and CAMForge environment libraries. The CAD environment's broken OCP overlay was rebuilt and direct imports then passed. Standalone Blender `bpy` was rejected/uninstalled; live support therefore remains static metadata-only. ParametricForge imports passed after rebuild, but `pip check` retained `ocpsvg 0.5.0 requires ocp`; it remains experimental and unused. This is why Elysia reports direct capability truth rather than treating `pip check` as sufficient proof. Bubblewrap is installed, but a non-mutating probe showed that this host disallows unprivileged namespace creation. Heavy environment handoffs therefore remain configured but disabled; the live routes use bounded static domain modules rather than weakening the no-network/no-home/no-device boundary.

## Implemented truth

- STL: ASCII/binary form, triangles, bounds, surface area, bounded topology/normal/degenerate/duplicate/non-finite observations, unit and manufacturing cautions.
- OBJ: vertex/face/object/group/material metadata, bounds, and safely classified MTL/texture references.
- DAE: defused XML asset/unit and scene counts, animation/skinning flags, safely classified references.
- STEP/IGES: bounded exchange metadata, entity/unit/product/assembly or curve/surface/solid summaries and explicit import/validity limitations.
- DXF: version/units/layers/entities/blocks/text, bounds and dimensional/profile signals, XREF warnings.
- URDF/SDF: safe XML model/graph/inertial/geometry/dependency/plugin summaries; xacro and plugins are detected but never expanded or loaded.
- G-code: inert command/mode/extents/feed/spindle/heater/tool/probe/homing/risk analysis with a mandatory machine-profile warning.
- BLEND: static header/version and risk metadata only.
- F3D/F3Z: limited local metadata/container recognition only, with neutral-export guidance and no Autodesk/cloud workflow.

Exact-approved local SVG preview is live only for STL, OBJ, DXF, and G-code. Reports, manifests, preview plans, receipts, and derivatives remain private local artifacts. Conversion/repair/simulation are plan-only or unavailable and expose no apply route. Generation/modification and physical output are unavailable by design.

Desktop and Codev display EngineeringForge family, source hash/size, capability truth, risks, static results, external-reference summaries, artifacts, and stale-file state. Codev delegates parsing to Elysia. Neither UI exposes run, machine, print, send, execute, ROS/Gazebo launch, Blender-script, Fusion-upload, patch, overwrite, or “trust as safe” controls.

EngineeringForge can identify and inspect these files, explain what they contain, warn about risk, and create limited local reports/previews. It cannot certify a design, execute instructions, machine/print/actuate, upload, or modify the selected source.
