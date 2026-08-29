"""Canonical registry for governed science/data file stewardship."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodingDataTypeDescriptor:
    type_id: str
    label: str
    extensions: tuple[str, ...]
    exact_names: tuple[str, ...]
    category: str
    adapter: str
    readable: bool = True
    previewable: bool = True
    writable: bool = False
    editable: bool = False
    exportable: bool = True
    tabular: bool = False
    geospatial_vector: bool = False
    geospatial_raster: bool = False
    multidimensional: bool = False
    database: bool = False
    binary_container: bool = False
    directory_store: bool = False
    sidecar_required: bool = False
    mutation_supported: bool = False
    mutation_requires_transaction: bool = False
    mutation_requires_backup: bool = False
    derived_copy_preferred: bool = False
    max_preview_rows: int = 50
    max_preview_features: int = 25
    max_preview_bands: int = 4
    max_preview_variables: int = 20
    max_sample_values: int = 100
    risk: str = "low"
    stable_operations: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["capabilities"] = {
            "readable": self.readable,
            "previewable": self.previewable,
            "writable": self.writable,
            "editable": self.editable,
            "exportable": self.exportable,
            "mutation_supported": self.mutation_supported,
            "requires_transaction": self.mutation_requires_transaction,
            "requires_backup": self.mutation_requires_backup,
            "derived_copy_preferred": self.derived_copy_preferred,
            "stable_operations": list(self.stable_operations),
        }
        return payload


def _d(*args, **kwargs) -> CodingDataTypeDescriptor:
    return CodingDataTypeDescriptor(*args, **kwargs)


SUPPORTED_DATA_TYPES: tuple[CodingDataTypeDescriptor, ...] = (
    _d("csv_table", "CSV table", (".csv",), (), "tabular", "tabular", writable=True, editable=True, tabular=True, mutation_supported=True, mutation_requires_backup=True, stable_operations=("tabular_append_row", "tabular_update_cell", "tabular_delete_row", "tabular_add_column", "tabular_rename_column")),
    _d("tsv_table", "TSV table", (".tsv",), (), "tabular", "tabular", writable=True, editable=True, tabular=True, mutation_supported=True, mutation_requires_backup=True, stable_operations=("tabular_append_row", "tabular_update_cell", "tabular_delete_row", "tabular_add_column", "tabular_rename_column")),
    _d("json_lines", "JSON Lines records", (".jsonl",), (), "json_lines", "jsonl", writable=True, editable=True, mutation_supported=True, mutation_requires_backup=True, stable_operations=("jsonl_append_record", "jsonl_update_record", "jsonl_delete_record", "jsonl_repair_record")),
    _d("parquet_table", "Parquet table", (".parquet",), (), "columnar", "parquet", binary_container=True, derived_copy_preferred=True, risk="medium", stable_operations=("export_metadata", "export_preview"), notes=("PyArrow-backed inspection provides real schema, row-group, and bounded preview support.",)),
    _d("sqlite_database", "SQLite database", (".sqlite", ".sqlite3", ".db"), (), "database", "databaseforge", readable=False, previewable=False, writable=False, editable=False, exportable=False, database=True, binary_container=True, mutation_supported=False, risk="high", stable_operations=(), notes=("Chunk 7 DatabaseForge supersedes legacy row preview and mutation. Use exact-approved snapshot-first schema preview only.",)),
    _d("duckdb_database", "DuckDB database", (".duckdb",), (), "database", "databaseforge", readable=False, previewable=False, writable=False, editable=False, exportable=False, database=True, binary_container=True, mutation_supported=False, risk="high", stable_operations=(), notes=("Use DatabaseForge fixed read-only schema introspection; external access, SQL, export, extensions, and mutation are unavailable.",)),
    _d("geojson_vector", "GeoJSON vector data", (".geojson",), (), "geospatial_vector", "geojson", writable=True, editable=True, geospatial_vector=True, mutation_supported=True, mutation_requires_backup=True, derived_copy_preferred=True, risk="medium", stable_operations=("geojson_append_feature", "geojson_update_properties", "geojson_delete_feature", "vector_export_derived")),
    _d("geopackage", "GeoPackage", (".gpkg",), (), "geospatial_vector", "geopackage", writable=True, editable=True, geospatial_vector=True, binary_container=True, mutation_supported=True, derived_copy_preferred=True, risk="medium", stable_operations=("vector_export_derived", "export_metadata", "export_preview"), notes=("GDAL-backed inspection provides real layer, CRS, bounds, schema, and bounded feature preview support.",)),
    _d("shapefile", "Shapefile sidecar set", (".shp",), (), "geospatial_vector", "shapefile", writable=True, editable=True, geospatial_vector=True, sidecar_required=True, mutation_supported=True, derived_copy_preferred=True, risk="medium", stable_operations=("vector_export_derived", "export_metadata", "export_preview"), notes=("A shapefile is a sidecar set; .shp, .shx, and .dbf are required and inspected together.",)),
    _d("kml_vector", "KML vector data", (".kml",), (), "geospatial_vector", "kml", writable=True, editable=True, geospatial_vector=True, mutation_supported=True, mutation_requires_backup=True, derived_copy_preferred=True, risk="medium", stable_operations=("kml_rename_placemark", "vector_export_derived"), notes=("External network links are reported but never fetched.",)),
    _d("kmz_vector_archive", "KMZ vector archive", (".kmz",), (), "geospatial_vector", "kmz", geospatial_vector=True, binary_container=True, derived_copy_preferred=True, risk="medium", stable_operations=("export_metadata",), notes=("KMZ is inspected with zip-slip protection; external links are never fetched.",)),
    _d("geotiff_raster", "GeoTIFF/TIFF raster", (".tif", ".tiff"), (), "geospatial_raster", "raster", writable=True, editable=True, geospatial_raster=True, binary_container=True, mutation_supported=True, derived_copy_preferred=True, risk="high", stable_operations=("raster_update_tags", "raster_write_window_derived", "export_metadata"), notes=("Rasterio-backed inspection provides real CRS, bounds, band metadata, and bounded sample-window statistics.",)),
    _d("netcdf_dataset", "NetCDF dataset", (".nc", ".netcdf"), (), "multidimensional_array", "netcdf", writable=True, editable=True, multidimensional=True, binary_container=True, mutation_supported=True, derived_copy_preferred=True, risk="high", stable_operations=("netcdf_update_attr", "netcdf_write_slice_derived", "export_metadata"), notes=("Xarray with h5netcdf is the preferred in-process path; netCDF4 is isolated behind a timeout worker fallback.",)),
    _d("hdf5_dataset", "HDF5 dataset", (".h5", ".hdf5"), (), "hierarchical_data", "hdf5", writable=True, editable=True, multidimensional=True, binary_container=True, mutation_supported=True, derived_copy_preferred=True, risk="high", stable_operations=("hdf5_update_attr", "hdf5_write_slice_derived", "export_metadata"), notes=("h5py-backed inspection provides real group, dataset, attrs, chunk, compression, and bounded sample support.",)),
    _d("zarr_store", "Zarr directory store", (".zarr",), (), "zarr_store", "zarr", writable=True, editable=True, multidimensional=True, directory_store=True, mutation_supported=True, derived_copy_preferred=True, risk="high", stable_operations=("zarr_update_attr", "zarr_write_slice_derived", "export_metadata"), notes=("Zarr-backed inspection provides real store, group, array, chunk, attrs, and bounded sample support.",)),
)

SUPPORTED_DATA_EXTENSIONS = {ext for descriptor in SUPPORTED_DATA_TYPES for ext in descriptor.extensions}
DATA_DIRECTORY_EXTENSIONS = {".zarr"}

UNKNOWN_DATA = CodingDataTypeDescriptor("data_unsupported", "Unsupported data file", (), (), "unsupported", "blocked", readable=False, previewable=False, exportable=False, risk="blocked", notes=("This science/data format is not supported by Chunk 3 data stewardship.",))


def detect_data_type(path: Path | str) -> CodingDataTypeDescriptor:
    candidate = Path(str(path))
    suffix = candidate.suffix.lower()
    for descriptor in SUPPORTED_DATA_TYPES:
        if suffix in descriptor.extensions:
            if descriptor.type_id == "sqlite_database" and candidate.exists() and candidate.is_file():
                try:
                    header = candidate.read_bytes()[:16]
                except OSError:
                    return descriptor
                if suffix == ".db" and header != b"SQLite format 3\x00":
                    return CodingDataTypeDescriptor("db_unknown", "Ambiguous .db database file", (".db",), (), "database", "databaseforge", readable=False, previewable=False, exportable=False, database=True, binary_container=True, risk="high", notes=("DatabaseForge identifies content; unknown .db files remain metadata-only and cannot enter row preview or mutation lanes.",))
            return descriptor
    return UNKNOWN_DATA


def is_supported_data_path(path: Path | str) -> bool:
    return detect_data_type(path).adapter != "blocked"


def data_registry_payload() -> list[dict[str, object]]:
    return [descriptor.to_payload() for descriptor in SUPPORTED_DATA_TYPES]


__all__ = (
    "CodingDataTypeDescriptor",
    "DATA_DIRECTORY_EXTENSIONS",
    "SUPPORTED_DATA_EXTENSIONS",
    "SUPPORTED_DATA_TYPES",
    "UNKNOWN_DATA",
    "data_registry_payload",
    "detect_data_type",
    "is_supported_data_path",
)
