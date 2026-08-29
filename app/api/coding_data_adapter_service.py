"""Adapter router for governed science/data inspection and preview."""

from __future__ import annotations

import csv
import json
import math
import multiprocessing as mp
import sqlite3
import warnings as py_warnings
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from hashlib import sha256
from importlib.util import find_spec
from pathlib import Path
from queue import Empty
from typing import Any

from app.api.coding_data_safety_service import CodingDataSafetyResult, check_data_safety
from app.api.coding_data_type_registry import CodingDataTypeDescriptor, detect_data_type
from app.api.coding_secret_scan_service import redact_secret_lines, scan_preview_for_secrets


def _hash_bytes(path: Path) -> str:
    digest = sha256()
    if path.is_dir():
        for child in sorted(item for item in path.rglob("*") if item.is_file()):
            digest.update(child.relative_to(path).as_posix().encode("utf-8"))
            digest.update(child.read_bytes()[:8192])
        return digest.hexdigest()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dependency_status() -> dict[str, str]:
    modules = {
        "pandas": "pandas",
        "pyarrow": "pyarrow",
        "geopandas": "geopandas",
        "rasterio": "rasterio",
        "xarray": "xarray",
        "netCDF4": "netcdf4",
        "h5py": "h5py",
        "zarr": "zarr",
        "shapely": "shapely",
        "pyogrio": "pyogrio",
        "fiona": "fiona",
        "numpy": "numpy",
    }
    return {package: ("available" if find_spec(module) else "missing") for module, package in modules.items()}


SENSITIVE_SAMPLE_KEYS = ("secret", "token", "password", "api_key", "apikey", "access_key", "private_key")
ZARR_LIBRARY_TIMEOUT_SECONDS = 1.0
NETCDF4_WORKER_TIMEOUT_SECONDS = 1.0


def _redact_value(value: Any, *, key: str | None = None) -> Any:
    text = "" if value is None else str(value)
    lowered_key = (key or "").lower()
    if any(marker in lowered_key for marker in SENSITIVE_SAMPLE_KEYS) or scan_preview_for_secrets(text):
        return "[REDACTED]"
    return value


def _redact_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    count = 0
    redacted: list[dict[str, Any]] = []
    for row in rows:
        output: dict[str, Any] = {}
        for key, value in row.items():
            safe = _redact_value(value, key=key)
            if safe != value:
                count += 1
            output[key] = safe
        redacted.append(output)
    return redacted, count


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return value.name
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    if hasattr(value, "tolist"):
        try:
            return _json_safe(value.tolist())
        except Exception:
            pass
    return str(value)


def _dataframe_sample_rows(frame: Any, *, max_rows: int) -> tuple[list[dict[str, Any]], int]:
    sample = frame.head(max_rows)
    rows = [_json_safe(row) for row in sample.to_dict(orient="records")]
    redacted, redactions = _redact_rows(rows)
    return redacted, redactions


@dataclass(frozen=True)
class CodingDataPreview:
    descriptor: CodingDataTypeDescriptor
    safety: CodingDataSafetyResult
    status: str
    content_hash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_summary: dict[str, Any] = field(default_factory=dict)
    preview: dict[str, Any] = field(default_factory=dict)
    layers: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    bands: list[dict[str, Any]] = field(default_factory=list)
    dimensions: list[dict[str, Any]] = field(default_factory=list)
    variables: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provenance_refs: list[dict[str, Any]] = field(default_factory=list)
    redaction_count: int = 0
    preview_truncated: bool = False
    blocked_reason: str | None = None
    dependencies: dict[str, str] = field(default_factory=dict)

    def to_payload(self, *, file_label: str, relative_path: str | None, path_hash: str | None) -> dict[str, Any]:
        return {
            "status": self.status,
            "file_label": file_label,
            "relative_path": relative_path,
            "path_hash": path_hash,
            "content_hash": self.content_hash,
            "blocked_reason": self.blocked_reason,
            "descriptor": self.descriptor.to_payload(),
            "size_bytes": self.safety.size_bytes,
            "metadata": self.metadata,
            "schema_summary": self.schema_summary,
            "preview": self.preview,
            "layers": self.layers,
            "tables": self.tables,
            "bands": self.bands,
            "dimensions": self.dimensions,
            "variables": self.variables,
            "warnings": self.warnings,
            "risk_flags": self.safety.risk_flags,
            "provenance_refs": self.provenance_refs,
            "redaction_count": self.redaction_count,
            "preview_truncated": self.preview_truncated,
            "dependencies": self.dependencies,
        }


def _inspect_tabular(path: Path, *, delimiter: str, max_rows: int) -> CodingDataPreview:
    descriptor = detect_data_type(path)
    safety = check_data_safety(path, descriptor)
    if not safety.allowed:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=safety.blocked_reason, warnings=safety.warnings)
    rows: list[dict[str, Any]] = []
    line_count = 0
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        try:
            sniffed = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            delimiter = sniffed.delimiter
        except csv.Error:
            pass
        reader = csv.DictReader(handle, delimiter=delimiter)
        columns = list(reader.fieldnames or [])
        for index, row in enumerate(reader):
            line_count += 1
            if index < max_rows:
                rows.append(dict(row))
        if line_count == 0 and not columns:
            handle.seek(0)
            raw_reader = csv.reader(handle, delimiter=delimiter)
            raw_rows = list(raw_reader)[:max_rows]
            columns = [f"column_{idx + 1}" for idx in range(max((len(row) for row in raw_rows), default=0))]
            rows = [dict(zip(columns, row)) for row in raw_rows]
            line_count = len(raw_rows)
    redacted_rows, redactions = _redact_rows(rows)
    missing = {column: sum(1 for row in rows if row.get(column) in {"", None}) for column in columns}
    return CodingDataPreview(
        descriptor,
        safety,
        "completed",
        content_hash=_hash_bytes(path),
        metadata={"delimiter": delimiter, "row_count_estimate": line_count, "column_count": len(columns)},
        schema_summary={"columns": [{"name": column, "missing_in_preview": missing.get(column, 0)} for column in columns]},
        preview={"rows": redacted_rows, "row_count": len(redacted_rows)},
        tables=[{"table": "data", "columns": columns, "sample_rows": redacted_rows}],
        warnings=safety.warnings,
        provenance_refs=[{"kind": "rows", "start": 1, "count": len(redacted_rows)}],
        redaction_count=redactions,
        preview_truncated=line_count > len(redacted_rows),
        dependencies=_dependency_status(),
    )


def _inspect_jsonl(path: Path, *, max_rows: int) -> CodingDataPreview:
    descriptor = detect_data_type(path)
    safety = check_data_safety(path, descriptor)
    if not safety.allowed:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=safety.blocked_reason, warnings=safety.warnings)
    records: list[dict[str, Any]] = []
    malformed: list[int] = []
    keys: set[str] = set()
    total = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            total += 1
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    keys.update(parsed.keys())
                    if len(records) < max_rows:
                        records.append(parsed)
            except json.JSONDecodeError:
                malformed.append(number)
    redacted, redactions = _redact_rows(records)
    return CodingDataPreview(
        descriptor,
        safety,
        "completed",
        content_hash=_hash_bytes(path),
        metadata={"record_count_estimate": total, "malformed_line_count": len(malformed), "malformed_lines_preview": malformed[:20]},
        schema_summary={"keys": sorted(keys)},
        preview={"records": redacted, "record_count": len(redacted)},
        warnings=safety.warnings + (["Malformed JSONL lines were skipped in preview."] if malformed else []),
        provenance_refs=[{"kind": "jsonl_lines", "count": len(redacted)}],
        redaction_count=redactions,
        preview_truncated=total > len(redacted),
        dependencies=_dependency_status(),
    )


def _inspect_sqlite(path: Path, *, max_rows: int) -> CodingDataPreview:
    descriptor = detect_data_type(path)
    safety = check_data_safety(path, descriptor)
    if not safety.allowed:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=safety.blocked_reason, warnings=safety.warnings)
    tables: list[dict[str, Any]] = []
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            table_rows = connection.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            for table in table_rows:
                name = str(table["name"])
                quoted = '"' + name.replace('"', '""') + '"'
                columns = [dict(row) for row in connection.execute(f"PRAGMA table_info({quoted})").fetchall()]
                indexes = [dict(row) for row in connection.execute(f"PRAGMA index_list({quoted})").fetchall()]
                count = connection.execute(f"SELECT COUNT(*) AS n FROM {quoted}").fetchone()["n"]
                sample = [dict(row) for row in connection.execute(f"SELECT * FROM {quoted} LIMIT ?", (max_rows,)).fetchall()]
                redacted, redactions = _redact_rows(sample)
                tables.append({"name": name, "kind": table["type"], "columns": columns, "indexes": indexes, "row_count": count, "sample_rows": redacted, "redaction_count": redactions})
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=f"sqlite_open_failed:{exc.__class__.__name__}", warnings=safety.warnings)
    return CodingDataPreview(
        descriptor,
        safety,
        "completed",
        content_hash=_hash_bytes(path),
        metadata={"table_count": len(tables), "opened_read_only": True},
        schema_summary={"tables": [{"name": item["name"], "columns": [col["name"] for col in item["columns"]], "row_count": item["row_count"]} for item in tables]},
        tables=tables,
        preview={"tables": tables[:5]},
        warnings=safety.warnings,
        provenance_refs=[{"kind": "sqlite_schema", "tables": [item["name"] for item in tables]}],
        redaction_count=sum(int(item.get("redaction_count") or 0) for item in tables),
        dependencies=_dependency_status(),
    )


def _coords_bbox(geometry: Any) -> tuple[float, float, float, float] | None:
    values: list[tuple[float, float]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            if len(node) >= 2 and all(isinstance(item, (int, float)) for item in node[:2]):
                values.append((float(node[0]), float(node[1])))
            else:
                for child in node:
                    walk(child)

    if isinstance(geometry, dict):
        walk(geometry.get("coordinates"))
    if not values:
        return None
    xs, ys = zip(*values)
    return (min(xs), min(ys), max(xs), max(ys))


def _inspect_geojson(path: Path, *, max_features: int) -> CodingDataPreview:
    descriptor = detect_data_type(path)
    safety = check_data_safety(path, descriptor)
    if not safety.allowed:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=safety.blocked_reason, warnings=safety.warnings)
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=f"geojson_parse_failed:{exc.__class__.__name__}", warnings=safety.warnings)
    features = payload.get("features") if isinstance(payload, dict) else []
    features = features if isinstance(features, list) else []
    geometry_types = sorted({str(item.get("geometry", {}).get("type")) for item in features if isinstance(item, dict)})
    keys = sorted({key for item in features if isinstance(item, dict) for key in (item.get("properties") or {}).keys()})
    bboxes = [_coords_bbox(item.get("geometry")) for item in features if isinstance(item, dict)]
    bboxes = [bbox for bbox in bboxes if bbox]
    bounds = None
    if bboxes:
        bounds = (min(b[0] for b in bboxes), min(b[1] for b in bboxes), max(b[2] for b in bboxes), max(b[3] for b in bboxes))
    sample = []
    for index, feature in enumerate(features[:max_features]):
        props = feature.get("properties") if isinstance(feature, dict) else {}
        redacted, _ = _redact_rows([props if isinstance(props, dict) else {}])
        sample.append({"index": index, "geometry_type": feature.get("geometry", {}).get("type") if isinstance(feature, dict) else None, "properties": redacted[0]})
    return CodingDataPreview(
        descriptor,
        safety,
        "completed",
        content_hash=_hash_bytes(path),
        metadata={"feature_count": len(features), "bounds": bounds, "crs": payload.get("crs") if isinstance(payload, dict) else None},
        schema_summary={"geometry_types": geometry_types, "properties": keys},
        preview={"features": sample},
        layers=[{"name": path.stem, "feature_count": len(features), "geometry_types": geometry_types, "bounds": bounds, "properties": keys}],
        warnings=safety.warnings,
        provenance_refs=[{"kind": "features", "count": len(sample)}],
        preview_truncated=len(features) > len(sample),
        dependencies=_dependency_status(),
    )


def _inspect_kml_text(text: str, descriptor: CodingDataTypeDescriptor, safety: CodingDataSafetyResult, path: Path) -> CodingDataPreview:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=f"kml_parse_failed:{exc.__class__.__name__}", warnings=safety.warnings)
    placemarks = []
    network_links = 0
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag == "NetworkLink":
            network_links += 1
        if tag == "Placemark":
            name = ""
            for child in elem:
                if child.tag.rsplit("}", 1)[-1] == "name" and child.text:
                    name = child.text
            placemarks.append({"name": _redact_value(name), "kind": "Placemark"})
    return CodingDataPreview(
        descriptor,
        safety,
        "completed",
        content_hash=_hash_bytes(path),
        metadata={"placemark_count": len(placemarks), "network_link_count": network_links},
        schema_summary={"elements": ["Placemark", "NetworkLink"]},
        preview={"placemarks": placemarks[:25]},
        layers=[{"name": path.stem, "feature_count": len(placemarks), "network_link_count": network_links}],
        warnings=safety.warnings + (["KML/KMZ network links were detected but not fetched."] if network_links else []),
        provenance_refs=[{"kind": "placemarks", "count": min(len(placemarks), 25)}],
        preview_truncated=len(placemarks) > 25,
        dependencies=_dependency_status(),
    )


def _inspect_kml(path: Path) -> CodingDataPreview:
    descriptor = detect_data_type(path)
    safety = check_data_safety(path, descriptor)
    if not safety.allowed:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=safety.blocked_reason, warnings=safety.warnings)
    return _inspect_kml_text(path.read_text(encoding="utf-8", errors="replace"), descriptor, safety, path)


def _inspect_kmz(path: Path) -> CodingDataPreview:
    descriptor = detect_data_type(path)
    safety = check_data_safety(path, descriptor)
    if not safety.allowed:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=safety.blocked_reason, warnings=safety.warnings)
    with zipfile.ZipFile(path) as archive:
        kml_names = [name for name in archive.namelist() if name.lower().endswith(".kml")]
        if not kml_names:
            return CodingDataPreview(descriptor, safety, "blocked", blocked_reason="kmz_missing_kml", warnings=safety.warnings)
        text = archive.read(kml_names[0]).decode("utf-8", errors="replace")
    preview = _inspect_kml_text(text, descriptor, safety, path)
    return CodingDataPreview(**{**preview.__dict__, "metadata": {**preview.metadata, "kml_member": kml_names[0], "archive_members": kml_names[:20]}})


def _inspect_parquet(path: Path, *, max_rows: int) -> CodingDataPreview:
    descriptor = detect_data_type(path)
    safety = check_data_safety(path, descriptor)
    if not safety.allowed:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=safety.blocked_reason, warnings=safety.warnings, dependencies=_dependency_status())
    try:
        import pyarrow.parquet as pq
        parquet = pq.ParquetFile(path)
        schema = parquet.schema_arrow
        table = parquet.read_row_group(0).slice(0, max_rows) if parquet.num_row_groups else None
        rows: list[dict[str, Any]] = []
        redactions = 0
        if table is not None:
            frame = table.to_pandas()
            rows, redactions = _dataframe_sample_rows(frame, max_rows=max_rows)
        row_groups = [
            {
                "index": index,
                "num_rows": parquet.metadata.row_group(index).num_rows,
                "total_byte_size": parquet.metadata.row_group(index).total_byte_size,
            }
            for index in range(parquet.num_row_groups)
        ]
        return CodingDataPreview(
            descriptor,
            safety,
            "completed",
            content_hash=_hash_bytes(path),
            metadata={
                "row_count": parquet.metadata.num_rows,
                "column_count": parquet.metadata.num_columns,
                "row_group_count": parquet.num_row_groups,
                "created_by": parquet.metadata.created_by,
            },
            schema_summary={"columns": [{"name": field.name, "type": str(field.type)} for field in schema]},
            preview={"rows": rows, "row_count": len(rows)},
            tables=[{"table": path.stem, "columns": schema.names, "row_groups": row_groups, "sample_rows": rows}],
            warnings=safety.warnings,
            provenance_refs=[{"kind": "parquet_row_group", "row_group": 0, "rows": len(rows)}],
            redaction_count=redactions,
            preview_truncated=(parquet.metadata.num_rows or 0) > len(rows),
            dependencies=_dependency_status(),
        )
    except Exception as exc:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=f"parquet_read_failed:{exc.__class__.__name__}", warnings=safety.warnings, dependencies=_dependency_status())


def _inspect_vector_file(path: Path, *, max_features: int) -> CodingDataPreview:
    descriptor = detect_data_type(path)
    safety = check_data_safety(path, descriptor)
    if not safety.allowed:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=safety.blocked_reason, warnings=safety.warnings, dependencies=_dependency_status())
    try:
        import geopandas as gpd
        import pyogrio
    except Exception as exc:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=f"vector_dependency_unavailable:{exc.__class__.__name__}", warnings=safety.warnings, dependencies=_dependency_status())

    layers: list[dict[str, Any]] = []
    preview_features: list[dict[str, Any]] = []
    try:
        layer_names = pyogrio.list_layers(path)[:, 0].tolist() if descriptor.type_id == "geopackage" else [path.stem]
    except Exception:
        layer_names = [path.stem]
    try:
        for layer_name in layer_names[:20]:
            info = pyogrio.read_info(path, layer=layer_name if descriptor.type_id == "geopackage" else None)
            frame = gpd.read_file(path, layer=layer_name if descriptor.type_id == "geopackage" else None, rows=slice(0, max_features))
            columns = [column for column in frame.columns if column != frame.geometry.name]
            rows, redactions = _dataframe_sample_rows(frame.drop(columns=[frame.geometry.name], errors="ignore"), max_rows=max_features)
            geometry_types = sorted(str(item) for item in frame.geometry.geom_type.dropna().unique()) if frame.geometry.name in frame else []
            bounds = tuple(float(item) for item in frame.total_bounds) if len(frame) else None
            layer = {
                "name": layer_name,
                "feature_count": info.get("features"),
                "geometry_type": info.get("geometry_type"),
                "geometry_types_preview": geometry_types,
                "crs": str(info.get("crs") or frame.crs or ""),
                "bounds_preview": bounds,
                "properties": columns,
                "redaction_count": redactions,
            }
            layers.append(_json_safe(layer))
            for index, (properties, geometry) in enumerate(zip(rows, frame.geometry.head(max_features).to_list())):
                preview_features.append({"layer": layer_name, "index": index, "geometry_type": getattr(geometry, "geom_type", None), "properties": properties})
        return CodingDataPreview(
            descriptor,
            safety,
            "completed",
            content_hash=_hash_bytes(path),
            metadata={"layer_count": len(layers), "sidecars": {suffix: path.with_suffix(suffix).exists() for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg")} if descriptor.type_id == "shapefile" else {}},
            schema_summary={"layers": layers},
            preview={"features": _json_safe(preview_features[:max_features])},
            layers=layers,
            warnings=safety.warnings,
            provenance_refs=[{"kind": "vector_features", "count": min(len(preview_features), max_features)}],
            redaction_count=sum(int(layer.get("redaction_count") or 0) for layer in layers),
            preview_truncated=any((layer.get("feature_count") or 0) > max_features for layer in layers if isinstance(layer.get("feature_count"), int)),
            dependencies=_dependency_status(),
        )
    except Exception as exc:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=f"vector_read_failed:{exc.__class__.__name__}", warnings=safety.warnings, dependencies=_dependency_status())


def _inspect_raster(path: Path, *, max_values: int) -> CodingDataPreview:
    descriptor = detect_data_type(path)
    safety = check_data_safety(path, descriptor)
    if not safety.allowed:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=safety.blocked_reason, warnings=safety.warnings, dependencies=_dependency_status())
    try:
        import numpy as np
        import rasterio
        from rasterio.windows import Window
        with rasterio.open(path) as dataset:
            window_width = min(dataset.width, 64)
            window_height = min(dataset.height, max(1, max_values // max(1, window_width)))
            window = Window(0, 0, window_width, window_height)
            bands: list[dict[str, Any]] = []
            for band_index in range(1, min(dataset.count, descriptor.max_preview_bands) + 1):
                data = dataset.read(band_index, window=window, masked=True)
                compressed = data.compressed()
                stats = {
                    "band": band_index,
                    "dtype": str(dataset.dtypes[band_index - 1]),
                    "nodata": _json_safe(dataset.nodatavals[band_index - 1]),
                    "sample_window": [0, 0, int(window_width), int(window_height)],
                    "sample_count": int(compressed.size),
                    "min": _json_safe(np.min(compressed)) if compressed.size else None,
                    "max": _json_safe(np.max(compressed)) if compressed.size else None,
                    "mean": _json_safe(np.mean(compressed)) if compressed.size else None,
                }
                bands.append(stats)
            return CodingDataPreview(
                descriptor,
                safety,
                "completed",
                content_hash=_hash_bytes(path),
                metadata={
                    "driver": dataset.driver,
                    "width": dataset.width,
                    "height": dataset.height,
                    "band_count": dataset.count,
                    "crs": str(dataset.crs or ""),
                    "bounds": tuple(float(item) for item in dataset.bounds),
                    "transform": tuple(float(item) for item in dataset.transform),
                    "nodata": _json_safe(dataset.nodata),
                    "overviews": {str(index): dataset.overviews(index) for index in range(1, dataset.count + 1)},
                },
                schema_summary={"bands": bands},
                preview={"sample_window_stats": bands},
                bands=bands,
                warnings=safety.warnings,
                provenance_refs=[{"kind": "raster_window", "window": [0, 0, int(window_width), int(window_height)], "bands": len(bands)}],
                preview_truncated=dataset.count > len(bands) or dataset.width * dataset.height > window_width * window_height,
                dependencies=_dependency_status(),
            )
    except Exception as exc:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=f"raster_read_failed:{exc.__class__.__name__}", warnings=safety.warnings, dependencies=_dependency_status())


def _netcdf_payload_from_xarray(path: Path, descriptor: CodingDataTypeDescriptor, *, max_values: int, engine: str) -> dict[str, Any]:
    import xarray as xr

    with xr.open_dataset(path, engine=engine) as dataset:
        dims = [{"name": name, "size": int(size)} for name, size in dataset.sizes.items()]
        variables: list[dict[str, Any]] = []
        preview_values: dict[str, Any] = {}
        for name, array in list(dataset.variables.items())[:descriptor.max_preview_variables]:
            selector = {dim: slice(0, min(int(array.sizes[dim]), max(1, min(5, max_values)))) for dim in array.dims}
            sample = array.isel(selector).values
            variables.append({"name": name, "dims": list(array.dims), "shape": [int(item) for item in array.shape], "dtype": str(array.dtype), "attrs": _json_safe(dict(array.attrs))})
            preview_values[name] = _json_safe(sample)
        return {
            "engine": engine,
            "metadata": {"attrs": _json_safe(dict(dataset.attrs)), "dimension_count": len(dims), "variable_count": len(dataset.variables), "engine": engine},
            "schema_summary": {"dimensions": dims, "variables": variables},
            "preview": {"sample_values": preview_values},
            "dimensions": dims,
            "variables": variables,
            "preview_truncated": len(dataset.variables) > len(variables),
        }


def _netcdf4_worker_main(path_text: str, max_items: int, max_values: int, result_queue: Any) -> None:
    caught_messages: list[str] = []
    try:
        with py_warnings.catch_warnings(record=True) as caught:
            py_warnings.simplefilter("always", RuntimeWarning)
            from netCDF4 import Dataset

            with Dataset(path_text, "r") as dataset:
                dimensions = [{"name": name, "size": int(len(dim))} for name, dim in dataset.dimensions.items()]
                variables: list[dict[str, Any]] = []
                preview_values: dict[str, Any] = {}
                for name, variable in list(dataset.variables.items())[:max_items]:
                    shape = [int(item) for item in getattr(variable, "shape", ())]
                    slices = tuple(slice(0, min(dim, max(1, min(5, max_values)))) for dim in shape)
                    try:
                        sample = variable[slices] if slices else variable[()]
                    except Exception:
                        sample = "sample_unavailable"
                    variables.append(
                        {
                            "name": name,
                            "dims": list(getattr(variable, "dimensions", ())),
                            "shape": shape,
                            "dtype": str(getattr(variable, "dtype", "unknown")),
                            "attrs": _json_safe({attr: variable.getncattr(attr) for attr in variable.ncattrs()}),
                        }
                    )
                    preview_values[name] = _json_safe(sample)
                metadata = {
                    "attrs": _json_safe({attr: dataset.getncattr(attr) for attr in dataset.ncattrs()}),
                    "dimension_count": len(dimensions),
                    "variable_count": len(dataset.variables),
                    "engine": "netCDF4_worker",
                }
            caught_messages = [str(item.message) for item in caught]
        result_queue.put({"status": "completed", "metadata": metadata, "schema_summary": {"dimensions": dimensions, "variables": variables}, "preview": {"sample_values": preview_values}, "dimensions": dimensions, "variables": variables, "preview_truncated": metadata["variable_count"] > len(variables), "warnings": caught_messages})
    except Exception as exc:
        result_queue.put({"status": "error", "error": f"{exc.__class__.__name__}: {exc}", "warnings": caught_messages})


def _inspect_netcdf4_with_timeout(path: Path, *, max_items: int, max_values: int, timeout_seconds: float | None = None) -> dict[str, Any]:
    timeout_seconds = NETCDF4_WORKER_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    methods = mp.get_all_start_methods()
    context = mp.get_context("fork") if "fork" in methods else mp.get_context()
    result_queue = context.Queue(maxsize=1)
    process = context.Process(target=_netcdf4_worker_main, args=(str(path), max_items, max_values, result_queue))
    process.daemon = True
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(1)
        return {"status": "timeout", "timeout_seconds": timeout_seconds}
    try:
        return result_queue.get_nowait()
    except Empty:
        return {"status": "error", "error": "worker_returned_no_result"}


def _inspect_netcdf(path: Path, *, max_values: int) -> CodingDataPreview:
    descriptor = detect_data_type(path)
    safety = check_data_safety(path, descriptor)
    if not safety.allowed:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=safety.blocked_reason, warnings=safety.warnings, dependencies=_dependency_status())
    payload: dict[str, Any] | None = None
    warnings = list(safety.warnings)
    errors: list[str] = []
    for engine in ("h5netcdf", "scipy"):
        try:
            payload = _netcdf_payload_from_xarray(path, descriptor, max_values=max_values, engine=engine)
            break
        except Exception as exc:
            errors.append(f"{engine}:{exc.__class__.__name__}")
    worker_result = _inspect_netcdf4_with_timeout(path, max_items=descriptor.max_preview_variables, max_values=max_values)
    if worker_result.get("status") == "completed":
        worker_warnings = [f"netCDF4 worker warning: {message}" for message in worker_result.get("warnings", [])]
        warnings.extend(worker_warnings)
        if payload is None and not worker_warnings:
            payload = worker_result
    elif worker_result.get("status") == "timeout":
        warnings.append(f"Optional netCDF4 fallback worker timed out after {worker_result.get('timeout_seconds')}s; h5netcdf/scipy result was used when available.")
    else:
        warning_suffix = f" Reason: {worker_result.get('error', 'unknown_error')}"
        if worker_result.get("warnings"):
            warning_suffix += f" Warnings: {'; '.join(str(item) for item in worker_result.get('warnings', []))}"
        warnings.append(f"Optional netCDF4 fallback worker failed; h5netcdf/scipy result was used when available.{warning_suffix}")
    if payload is None:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=f"netcdf_read_failed:{';'.join(errors) or 'no_backend_succeeded'}", warnings=warnings, dependencies=_dependency_status())
    return CodingDataPreview(
        descriptor,
        safety,
        "completed",
        content_hash=_hash_bytes(path),
        metadata=_json_safe(payload["metadata"]),
        schema_summary=_json_safe(payload["schema_summary"]),
        preview=_json_safe(payload["preview"]),
        dimensions=_json_safe(payload["dimensions"]),
        variables=_json_safe(payload["variables"]),
        warnings=warnings,
        provenance_refs=[{"kind": "netcdf_variables", "count": len(payload["variables"])}],
        preview_truncated=bool(payload.get("preview_truncated")),
        dependencies=_dependency_status(),
    )


def _inspect_hdf5(path: Path, *, max_values: int) -> CodingDataPreview:
    descriptor = detect_data_type(path)
    safety = check_data_safety(path, descriptor)
    if not safety.allowed:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=safety.blocked_reason, warnings=safety.warnings, dependencies=_dependency_status())
    try:
        import h5py
        arrays: list[dict[str, Any]] = []
        preview_values: dict[str, Any] = {}
        with h5py.File(path, "r") as handle:
            def visit(name: str, obj: Any) -> None:
                if len(arrays) >= descriptor.max_preview_variables:
                    return
                if isinstance(obj, h5py.Dataset):
                    sample_slices = tuple(slice(0, min(int(dim), max(1, min(5, max_values)))) for dim in obj.shape)
                    try:
                        sample = obj[sample_slices] if obj.shape else obj[()]
                    except Exception:
                        sample = "sample_unavailable"
                    arrays.append({"path": "/" + name, "shape": [int(item) for item in obj.shape], "dtype": str(obj.dtype), "chunks": _json_safe(obj.chunks), "compression": _json_safe(obj.compression), "attrs": _json_safe(dict(obj.attrs))})
                    preview_values["/" + name] = _json_safe(sample)
            handle.visititems(visit)
            metadata = {"attrs": _json_safe(dict(handle.attrs)), "object_count_previewed": len(arrays)}
        return CodingDataPreview(
            descriptor,
            safety,
            "completed",
            content_hash=_hash_bytes(path),
            metadata=metadata,
            schema_summary={"datasets": arrays},
            preview={"sample_values": preview_values},
            variables=arrays,
            warnings=safety.warnings,
            provenance_refs=[{"kind": "hdf5_datasets", "count": len(arrays)}],
            preview_truncated=len(arrays) >= descriptor.max_preview_variables,
            dependencies=_dependency_status(),
        )
    except Exception as exc:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=f"hdf5_read_failed:{exc.__class__.__name__}", warnings=safety.warnings, dependencies=_dependency_status())


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _sample_zarr_v2_chunk(array_dir: Path, metadata: dict[str, Any], *, max_values: int) -> Any:
    if metadata.get("compressor") not in {None, False}:
        return "sample_unavailable_compressed_chunk"
    try:
        import numpy as np

        shape = [int(item) for item in metadata.get("shape") or []]
        chunks = [int(item) for item in metadata.get("chunks") or []]
        dtype = np.dtype(str(metadata.get("dtype")))
        if not shape or not chunks:
            return "sample_unavailable_missing_shape"
        chunk_name = ".".join("0" for _ in shape)
        chunk_path = array_dir / chunk_name
        if not chunk_path.exists():
            return "sample_unavailable_missing_chunk"
        chunk_shape = tuple(min(dim, chunk) for dim, chunk in zip(shape, chunks))
        values = np.frombuffer(chunk_path.read_bytes(), dtype=dtype).reshape(chunk_shape, order=str(metadata.get("order") or "C"))
        flat = values.reshape(-1)[:max_values]
        return _json_safe(flat)
    except Exception:
        return "sample_unavailable"


def _inspect_zarr_store_files(path: Path, *, max_items: int, max_values: int) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    root_attrs = _read_json_file(path / ".zattrs") or _read_json_file(path / "zarr.json").get("attributes", {})
    arrays: list[dict[str, Any]] = []
    samples: dict[str, Any] = {}
    for metadata_path in sorted(path.rglob(".zarray")):
        if len(arrays) >= max_items:
            break
        array_dir = metadata_path.parent
        relative = "/" + array_dir.relative_to(path).as_posix()
        metadata = _read_json_file(metadata_path)
        attrs = _read_json_file(array_dir / ".zattrs")
        sample = _sample_zarr_v2_chunk(array_dir, metadata, max_values=max_values)
        arrays.append(
            {
                "path": relative,
                "shape": _json_safe(metadata.get("shape") or []),
                "chunks": _json_safe(metadata.get("chunks") or []),
                "dtype": str(metadata.get("dtype") or "unknown"),
                "order": metadata.get("order"),
                "compressor": _json_safe(metadata.get("compressor")),
                "attrs": _json_safe(attrs),
            }
        )
        samples[relative] = sample
    for metadata_path in sorted(path.rglob("zarr.json")):
        if len(arrays) >= max_items:
            break
        if metadata_path == path / "zarr.json":
            continue
        metadata = _read_json_file(metadata_path)
        if metadata.get("node_type") != "array":
            continue
        array_dir = metadata_path.parent
        relative = "/" + array_dir.relative_to(path).as_posix()
        arrays.append(
            {
                "path": relative,
                "shape": _json_safe(metadata.get("shape") or []),
                "chunks": _json_safe(metadata.get("chunk_grid", {}).get("configuration", {}).get("chunk_shape")),
                "dtype": _json_safe(metadata.get("data_type") or "unknown"),
                "attrs": _json_safe(metadata.get("attributes") or {}),
                "zarr_format": 3,
            }
        )
        samples[relative] = "sample_unavailable_zarr_v3_codec"
    return _json_safe(root_attrs), arrays, samples


def _zarr_library_worker_main(path_text: str, max_items: int, max_values: int, result_queue: Any) -> None:
    try:
        import zarr

        root = zarr.open_group(path_text, mode="r")
        arrays: list[dict[str, Any]] = []
        samples: dict[str, Any] = {}

        def walk(prefix: str, node: Any) -> None:
            if len(arrays) >= max_items:
                return
            for name, child in node.items():
                if len(arrays) >= max_items:
                    return
                child_path = f"{prefix}/{name}".replace("//", "/")
                if hasattr(child, "shape") and hasattr(child, "dtype"):
                    sample_slices = tuple(slice(0, min(int(dim), 5)) for dim in child.shape)
                    try:
                        sample = child[sample_slices] if child.shape else child[()]
                    except Exception:
                        sample = "sample_unavailable"
                    arrays.append(
                        {
                            "path": child_path,
                            "shape": [int(item) for item in child.shape],
                            "chunks": _json_safe(getattr(child, "chunks", None)),
                            "dtype": str(child.dtype),
                            "attrs": _json_safe(dict(getattr(child, "attrs", {}) or {})),
                        }
                    )
                    samples[child_path] = _json_safe(sample.reshape(-1)[:max_values] if hasattr(sample, "reshape") else sample)
                elif hasattr(child, "items"):
                    walk(child_path, child)

        walk("/", root)
        result_queue.put({"status": "completed", "attrs": _json_safe(dict(root.attrs)), "arrays": arrays, "samples": samples})
    except Exception as exc:
        result_queue.put({"status": "error", "error": f"{exc.__class__.__name__}: {exc}"})


def _inspect_zarr_with_library_timeout(path: Path, *, max_items: int, max_values: int, timeout_seconds: float | None = None) -> dict[str, Any]:
    timeout_seconds = ZARR_LIBRARY_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    methods = mp.get_all_start_methods()
    context = mp.get_context("fork") if "fork" in methods else mp.get_context()
    result_queue = context.Queue(maxsize=1)
    process = context.Process(target=_zarr_library_worker_main, args=(str(path), max_items, max_values, result_queue))
    process.daemon = True
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(1)
        return {"status": "timeout", "timeout_seconds": timeout_seconds}
    try:
        return result_queue.get_nowait()
    except Empty:
        return {"status": "error", "error": "worker_returned_no_result"}


def _inspect_zarr(path: Path, *, max_values: int) -> CodingDataPreview:
    descriptor = detect_data_type(path)
    safety = check_data_safety(path, descriptor)
    if not safety.allowed:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=safety.blocked_reason, warnings=safety.warnings, dependencies=_dependency_status())
    try:
        attrs, arrays, samples = _inspect_zarr_store_files(path, max_items=descriptor.max_preview_variables, max_values=max_values)
        warnings = list(safety.warnings)
        store_format = "zarr_local_directory"
        worker_result = _inspect_zarr_with_library_timeout(path, max_items=descriptor.max_preview_variables, max_values=max_values)
        if worker_result.get("status") == "completed":
            attrs = _json_safe(worker_result.get("attrs") or attrs)
            arrays = _json_safe(worker_result.get("arrays") or arrays)
            samples = _json_safe(worker_result.get("samples") or samples)
            store_format = "zarr_library_worker"
        elif worker_result.get("status") == "timeout":
            warnings.append(f"Optional Zarr library inspection timed out after {worker_result.get('timeout_seconds')}s; deterministic local-store inspection was used.")
        else:
            warnings.append(f"Optional Zarr library inspection failed; deterministic local-store inspection was used. Reason: {worker_result.get('error', 'unknown_error')}")
        return CodingDataPreview(
            descriptor,
            safety,
            "completed",
            content_hash=_hash_bytes(path),
            metadata={"attrs": attrs, "array_count_previewed": len(arrays), "store_format": store_format},
            schema_summary={"arrays": arrays},
            preview={"sample_values": samples},
            variables=arrays,
            warnings=warnings,
            provenance_refs=[{"kind": "zarr_arrays", "count": len(arrays)}],
            preview_truncated=len(arrays) >= descriptor.max_preview_variables,
            dependencies=_dependency_status(),
        )
    except Exception as exc:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=f"zarr_read_failed:{exc.__class__.__name__}", warnings=safety.warnings, dependencies=_dependency_status())


def _inspect_binary_reduced(path: Path) -> CodingDataPreview:
    descriptor = detect_data_type(path)
    safety = check_data_safety(path, descriptor)
    if not safety.allowed:
        return CodingDataPreview(descriptor, safety, "blocked", blocked_reason=safety.blocked_reason, warnings=safety.warnings, dependencies=_dependency_status())
    dependencies = _dependency_status()
    required = {
        "parquet": "pyarrow",
        "geopackage": "geopandas/pyogrio/fiona",
        "shapefile": "geopandas/pyogrio/fiona",
        "raster": "rasterio",
        "netcdf": "xarray/netCDF4",
        "hdf5": "h5py",
        "zarr": "zarr",
    }.get(descriptor.adapter, "specialized package")
    metadata: dict[str, Any] = {"reduced_capability": True, "required_dependency": required}
    if path.is_file():
        metadata["signature_hex"] = path.read_bytes()[:16].hex()
    if descriptor.type_id == "shapefile":
        metadata["sidecars"] = {suffix: path.with_suffix(suffix).exists() for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg")}
    if descriptor.type_id == "zarr_store":
        metadata["zarr_entries_preview"] = [child.relative_to(path).as_posix() for child in list(path.rglob("*"))[:40]]
        for name in (".zgroup", ".zattrs", ".zmetadata"):
            candidate = path / name
            if candidate.exists():
                try:
                    metadata[name] = json.loads(candidate.read_text(encoding="utf-8"))
                except Exception:
                    metadata[name] = "present_unparsed"
    return CodingDataPreview(
        descriptor,
        safety,
        "reduced_dependency_missing",
        content_hash=_hash_bytes(path),
        metadata=metadata,
        warnings=safety.warnings + [f"Full {descriptor.label} preview/edit requires {required}; dependency is not available in the active environment."],
        dependencies=dependencies,
    )


def inspect_data_path(path: Path, *, max_rows: int = 50, max_features: int = 25, max_values: int = 100) -> CodingDataPreview:
    descriptor = detect_data_type(path)
    if descriptor.database or descriptor.adapter == "databaseforge":
        safety = check_data_safety(path, descriptor)
        return CodingDataPreview(
            descriptor,
            safety,
            "blocked",
            blocked_reason="database_requires_databaseforge_schema_only_route",
            warnings=["Legacy database row preview is unavailable. Use exact-approved snapshot-first DatabaseForge schema preview."],
        )
    if descriptor.adapter == "tabular":
        return _inspect_tabular(path, delimiter="\t" if descriptor.type_id == "tsv_table" else ",", max_rows=max_rows)
    if descriptor.adapter == "jsonl":
        return _inspect_jsonl(path, max_rows=max_rows)
    if descriptor.adapter == "sqlite":
        return _inspect_sqlite(path, max_rows=max_rows)
    if descriptor.adapter == "geojson":
        return _inspect_geojson(path, max_features=max_features)
    if descriptor.adapter == "kml":
        return _inspect_kml(path)
    if descriptor.adapter == "kmz":
        return _inspect_kmz(path)
    if descriptor.adapter == "parquet":
        return _inspect_parquet(path, max_rows=max_rows)
    if descriptor.adapter in {"geopackage", "shapefile"}:
        return _inspect_vector_file(path, max_features=max_features)
    if descriptor.adapter == "raster":
        return _inspect_raster(path, max_values=max_values)
    if descriptor.adapter == "netcdf":
        return _inspect_netcdf(path, max_values=max_values)
    if descriptor.adapter == "hdf5":
        return _inspect_hdf5(path, max_values=max_values)
    if descriptor.adapter == "zarr":
        return _inspect_zarr(path, max_values=max_values)
    return _inspect_binary_reduced(path)


def preview_data_path(path: Path, *, max_rows: int = 50, max_features: int = 25, max_values: int = 100) -> CodingDataPreview:
    return inspect_data_path(path, max_rows=max_rows, max_features=max_features, max_values=max_values)


__all__ = ("CodingDataPreview", "inspect_data_path", "preview_data_path")
