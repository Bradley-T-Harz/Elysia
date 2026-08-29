# Coding Data Boundary

The data stewardship boundary keeps science/data work local, bounded, and operator-governed.

## Allowed

- Metadata/schema inspection for supported data formats.
- Bounded previews of rows, records, features, placemarks, tables, layers, bands, variables, arrays, and local-store metadata.
- Approved exports of metadata/schema/previews to derived Markdown/JSON files.
- Approved CSV/TSV, JSONL, SQLite, GeoJSON, KML, vector export, raster tag-copy, and array/dataset attribute operations where the adapter can validate structure.

## Blocked

- Arbitrary SQL execution.
- Shell, package manager, cloud, Marketplace, or autonomous execution.
- Unapproved mutation.
- Private/runtime/secrets paths.
- KMZ zip-slip archives.
- Unbounded full dataset reads.

## Dependency Truth

Heavy formats such as Parquet, GPKG, Shapefile, GeoTIFF, NetCDF, HDF5, and Zarr use the Conda science/geospatial stack for full local parsing, preview, and stable derived-copy workflows. If a dependency is ever absent from a future environment, Elysia must report dependency truth instead of pretending support.
