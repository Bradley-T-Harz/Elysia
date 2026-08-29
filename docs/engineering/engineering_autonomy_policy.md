# Engineering autonomy policy

EngineeringForge uses a strict capability ladder:

| Level | Meaning | Chunk 8 state |
| --- | --- | --- |
| 0 | Identify | Live for registered formats |
| 1 | Hash, size, extension/header, basic metadata | Live |
| 2 | Bounded static parse | Live where the format supports it; BLEND/F3D limited |
| 3 | Geometry/CAD/robot/CAM report | Live where stated |
| 4 | Local preview | Exact-approved STL/OBJ/DXF/G-code SVG only; otherwise plan/future sandbox |
| 5 | Neutral conversion/export | Plan-only or unavailable; no apply route |
| 6 | Repair/simplification | Plan-only or unavailable; no apply route |
| 7 | Simulation/dry run | Plan-only only; no runtime launch |
| 8 | Generate/modify engineering source | Unavailable by design |
| 9 | Print, machine, controller send, robot actuation | Unavailable by design |

Inspection requires an explicit operator request. Level 4 uses the existing exact one-time approval contract: operation kind and mutation class must match, workspace and selected-file digests must match, the source hash and plan hash must match, the approval must be unexpired and unconsumed, and the file must not have changed. Applying a preview creates only a new derivative in Elysia's private artifact sandbox. It grants no authority to convert, repair, simulate, mutate, execute, upload, or control hardware.

Configured environments are capability evidence, not implicit runtime authority: `elysia_geometryforge`, `elysia_cadforge`, `elysia_robotforge`, `elysia_camforge`, and `elysia_blendforge` are represented by locked worker policies. Current live static parsers avoid expensive imports at API module load. A local Bubblewrap probe could not create an unprivileged namespace, so the heavy-environment handoffs are truthfully disabled rather than pretending to enforce no-network/no-home/no-device isolation. `elysia_parametricforge` is experimental because the recorded environment has an `ocpsvg`/`ocp` metadata warning even though direct imports succeeded; it is not used by live routes.

Any future worker handoff must use a fixed operation family, `shell=False`, closed stdin, bounded time/output/memory/entities/triangles/lines, no network/home/devices/project writes, sandbox-only outputs, no GUI/plugins, and one job per family. A configured or installed tool does not change the route's declared capability state.

`scripts/engineeringforge_environment_probe.py` is a read-only diagnostic, never a production dependency. It runs fixed, ten-second, isolated `find_spec` checks in the six named environments with closed stdin, bounded output, `shell=False`, and no network activity; it reports tool presence without launching any tool.
