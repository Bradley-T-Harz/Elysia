# CADForge capability truth

CADForge statically inspects STEP/STP, IGES/IGS, and DXF. F3D/F3Z are covered separately by the Fusion boundary. The live request path uses bounded domain parsers and does not import OCP, CadQuery, gmsh, FreeCAD, or GUI tooling into the core.

STEP reports Part 21 schema/version markers, entity counts, unit declarations, bounded product/assembly signals, entity-class summaries, and Cartesian point coordinate extents where available. Coordinate extents are labelled as exchange-record observations, not a validated B-rep bounding box. Shape/solid/shell/face/edge counts are descriptive. OCP/CadQuery tessellation and neutral derivative export are not live routes.

IGES reports section/entity counts, global unit metadata where detected, and bounded curve/surface/solid entity summaries. It never assumes watertightness, correct units, or successful downstream import.

DXF reports version, units, entity counts by type, layer/block/text counts, 2D/3D signals, coordinate bounds, closed/open profile observations, and XREF/external-reference warnings. Private labels remain in the local artifact and are not centrally audited. A closed profile is not a cut-ready or manufacturability claim. Exact-approved local SVG preview is available; toolpath generation is not.

Conversion, repair, and simulation are truthfully plan-only or unavailable. There are no conversion/repair/simulation apply routes in this release, no macro execution, no external-reference loading, and no source writes.
