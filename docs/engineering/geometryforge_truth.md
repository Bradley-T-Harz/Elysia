# GeometryForge capability truth

GeometryForge provides bounded, read-only static inspection for STL, OBJ, and COLLADA/DAE.

## STL

Live inspection distinguishes exact-size binary STL from ASCII STL, reports triangle count, coordinate bounds, surface area, non-finite coordinates, degenerate and duplicate triangles, edge incidence, boundary/non-manifold edges, normal inconsistency observations, and a bounded watertight observation. STL has no encoded unit, so every report carries a unit-ambiguity and manufacturing-caution warning. Results never assert printability, manufacturability, structural adequacy, or safety.

## OBJ

Live inspection reports vertex/face/object/group/material counts and coordinate bounds. Names remain in the private local report but are reduced to counts centrally. `mtllib`, material texture declarations, URL/absolute/traversal paths, missing files, and root-escaping symlinks are classified without loading or fetching referenced content.

## DAE

COLLADA is parsed with defused XML and an explicit entity/DOCTYPE rejection. Reports include asset unit metadata, geometry/material/image/scene-node counts, animation/skinning flags, and classified image/reference URIs. No entity expansion, external retrieval, script execution, or scene loading occurs.

Exact-approved local SVG previews are live for STL and OBJ as bounded orthographic line projections. DAE preview and all conversion/repair/simplification operations are plan-only. Originals are never modified.
