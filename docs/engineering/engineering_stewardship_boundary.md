# EngineeringForge stewardship boundary

EngineeringForge is Elysia's local, read-only domain layer for engineering files. The sacred coding/file core identifies a selected file, enforces the workspace-root guard, hashes it, applies policy, records a compact audit event, and registers local artifacts. Format-specific interpretation belongs to GeometryForge, CADForge, RobotModelForge, CAMForge, and BlendForge modules. The core does not import CadQuery, OCP, ROS, Gazebo, Blender, mesh-processing, or CAM libraries.

The live scope is capability levels 0–3: identification, hash/size/header metadata, bounded static parsing, and descriptive reports. Level 4 is available only for exact-approved, local SVG previews of STL, OBJ, DXF, and G-code. STEP/IGES/DAE preview, neutral conversion, repair, simplification, simulation, and parametric generation are plan-only, future-sandbox work, or unavailable as stated by `/coding/engineering/types`. Levels 8 and 9 are unavailable by design.

EngineeringForge never actuates hardware, sends G-code, opens a controller or device, launches ROS/Gazebo, loads a plugin, expands xacro, runs a Blender script, fetches a remote reference, uploads to a cloud service, mutates a source, overwrites an original, or certifies engineering/manufacturing safety. A report is evidence about file contents, not a professional verdict.

## Local artifacts and central audit

Each successful inspection writes a private report and `engineering_manifest.json` under Elysia's EngineeringForge artifact root. Artifact directories are mode `0700`; files are mode `0600`. Preview planning writes `preview_plan.json`, and an exact-approved apply writes an SVG derivative plus `preview_receipt.json`. Source hashes are checked again immediately before and after preview generation; a mismatch blocks the operation as stale.

Local reports may retain useful names and reference strings. Central audit records retain only compact facts such as hashes, sizes, format/family, counts, risk category, operation/artifact identifiers and hashes, policy/worker state, and outcome. They exclude absolute/relative source paths, geometry, toolpaths, comments, private object/layer/material/assembly names, proprietary metadata, and rendered content.

## Reference handling

OBJ/DAE/URDF/SDF/DXF/BLEND/F3Z references are classified, not loaded. URLs, absolute paths, traversal, unmapped `package://`, and symlinks escaping the approved root are blocked. Elysia never fetches a reference. `package://` remains unresolved unless a separate future design explicitly maps an approved local root.
