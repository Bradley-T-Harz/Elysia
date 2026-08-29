# Coding engineering security boundary

The `/coding/engineering` family is local, selected-file, root-guarded, read-only, bounded, and descriptive. Its live routes are:

- `GET /coding/engineering/types`
- `POST /coding/engineering/inspect`
- `POST /coding/engineering/preview/plan`
- `POST /coding/engineering/preview/apply`
- `GET /coding/engineering/jobs/{operation_id}`
- `POST /coding/engineering/jobs/{operation_id}/cancel`
- `GET /coding/engineering/artifacts/{artifact_id}`

There are intentionally no machine-send, print, CNC, serial, controller, robot-connect, ROS/Gazebo launch, Blender execution, Fusion upload, source patch/overwrite, conversion apply, repair apply, or safety-trust routes.

The path guard rejects files outside the selected workspace, escaping symlinks, and non-files. Static parsers enforce file, text/XML/archive, record, entity, triangle, line, and reference limits. XML entities/DOCTYPE are rejected; archives are inspected without extraction; references are classified without retrieval. Heavy CAD/robot/Blender libraries are neither imported by the core nor launched by live static inspection.

Central audit uses a format-specific safe-field allowlist and hashes paths. Detailed content stays in private local artifacts. Exact-approved preview apply revalidates the operation contract and source hash, generates a sandbox-only SVG, then verifies the source hash again. Tests assert source bytes are unchanged and that forbidden route fragments, network retrieval, script/plugin execution, and hardware imports are absent.
