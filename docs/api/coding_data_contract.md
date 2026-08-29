# Coding Data Stewardship Contract

Elysia data stewardship is a local, governed API surface for science, ecological, geospatial, and environmental data files.

## Supported Formats

Chunk 3 recognizes CSV, TSV, JSONL, Parquet, GeoJSON, GPKG, Shapefile sidecar sets, KML, KMZ, GeoTIFF/TIFF, NetCDF, HDF5, and Zarr stores. SQLite, DuckDB, and ambiguous `.db` files are recognized at the shared file boundary and handed to the separate DatabaseForge surface.

CSV, TSV, JSONL, GeoJSON, KML, and KMZ have standard-library-backed inspection/preview behavior. With the Chunk 3 science/geospatial stack installed, Parquet, GPKG, Shapefile, GeoTIFF, NetCDF, HDF5, and Zarr expose real metadata, schema/layer/band/dimension summaries, bounded previews, and adapter-specific governed derived-copy operations where stable.

## Routes

- `GET /coding/data-types`
- `POST /coding/data/inspect`
- `POST /coding/data/preview`
- `POST /coding/data/export-plan`
- `POST /coding/data/export-approved`
- `POST /coding/data/edit-plan`
- `POST /coding/data/apply-approved`
- `POST /coding/data/mutation-plan`
- `POST /coding/data/apply-mutation-approved`

## Governance

Preview is bounded. Export and mutation require an exact server-issued approval and are exposed only where a stable format-specific adapter exists. File rewrites create local backups or use a format-appropriate transactional/derived-copy path.

The Chunk 3 routes do not preview or mutate SQLite, DuckDB, or ambiguous `.db` files. DatabaseForge provides static metadata and an exact-approved, private, read-only schema-count preview for supported SQLite/DuckDB files. It never returns rows and does not expose arbitrary SQL, query/export, attach, extension loading, external access, repair, mutation, or migration.

Audit records store hashes, paths relative to the approved workspace, operation names, and result summaries. They do not store full raw datasets.
