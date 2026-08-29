from __future__ import annotations

from app.api.coding_data_type_registry import data_registry_payload, detect_data_type


def test_data_registry_identifies_chunk3_formats():
    expected = {
        "table.csv": "csv_table",
        "table.tsv": "tsv_table",
        "records.jsonl": "json_lines",
        "data.parquet": "parquet_table",
        "sample.sqlite": "sqlite_database",
        "map.geojson": "geojson_vector",
        "layer.gpkg": "geopackage",
        "roads.shp": "shapefile",
        "places.kml": "kml_vector",
        "places.kmz": "kmz_vector_archive",
        "image.tif": "geotiff_raster",
        "cube.nc": "netcdf_dataset",
        "tree.h5": "hdf5_dataset",
        "store.zarr": "zarr_store",
    }
    for path, type_id in expected.items():
        assert detect_data_type(path).type_id == type_id

    payload = data_registry_payload()
    assert len(payload) >= len(expected)
    assert all("capabilities" in item for item in payload)

