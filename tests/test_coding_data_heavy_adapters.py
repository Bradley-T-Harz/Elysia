from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import geopandas as gpd
import h5py
import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from rasterio.transform import from_origin
from shapely.geometry import Point

from app.api.coding_data_adapter_service import inspect_data_path
import app.api.coding_data_adapter_service as data_adapter
from app.api.project_paths import elysia_path
from app.api.coding_data_edit_service import apply_data_edit, plan_data_edit
from app.api.schemas.coding_data import CodingDataApplyRequest as _CodingDataApplyRequest, CodingDataEditPlanRequest
from tests.coding_approval_test_helpers import approval_fields_for_plan


def CodingDataApplyRequest(**kwargs):
    plan = plan_data_edit(
        CodingDataEditPlanRequest(
            **{key: value for key, value in kwargs.items() if key in {"session_id", "workspace_root", "file_path", "approval_granted", "approval_reason", "max_rows", "max_features", "max_values", "operation", "parameters"}}
        )
    )
    approval = approval_fields_for_plan(workspace_root=kwargs["workspace_root"], operation_kind="data_edit", mutation_class="data_edit", source_file=kwargs["file_path"], plan=plan)
    return _CodingDataApplyRequest(**approval, **kwargs)


def test_parquet_real_schema_and_preview(tmp_path: Path):
    path = tmp_path / "sample.parquet"
    pd.DataFrame({"name": ["alpha", "beta"], "value": [1, 2]}).to_parquet(path)

    preview = inspect_data_path(path)

    assert preview.status == "completed"
    assert preview.metadata["row_count"] == 2
    assert any(column["name"] == "name" for column in preview.schema_summary["columns"])
    assert preview.preview["rows"][0]["name"] == "alpha"


def test_gpkg_and_shapefile_real_layer_preview(tmp_path: Path):
    frame = gpd.GeoDataFrame(
        {"name": ["alpha", "beta"], "value": [1, 2]},
        geometry=[Point(1, 2), Point(3, 4)],
        crs="EPSG:4326",
    )
    gpkg = tmp_path / "sample.gpkg"
    shp = tmp_path / "sample.shp"
    frame.to_file(gpkg, layer="points", driver="GPKG")
    frame.to_file(shp)

    gpkg_preview = inspect_data_path(gpkg)
    shp_preview = inspect_data_path(shp)

    assert gpkg_preview.status == "completed"
    assert gpkg_preview.layers[0]["feature_count"] == 2
    assert "EPSG" in gpkg_preview.layers[0]["crs"]
    assert shp_preview.status == "completed"
    assert shp_preview.metadata["sidecars"][".shx"] is True
    assert shp_preview.preview["features"][0]["properties"]["name"] == "alpha"


def test_geotiff_real_metadata_bands_and_derived_tag_update(tmp_path: Path):
    path = tmp_path / "sample.tif"
    data = np.arange(100, dtype=np.uint16).reshape((10, 10))
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=from_origin(0, 10, 1, 1),
        nodata=0,
    ) as dataset:
        dataset.write(data, 1)

    preview = inspect_data_path(path)
    assert preview.status == "completed"
    assert preview.metadata["width"] == 10
    assert preview.bands[0]["sample_count"] > 0

    target = tmp_path / "sample.tagged.tif"
    plan = plan_data_edit(
        CodingDataEditPlanRequest(
            workspace_root=str(tmp_path),
            file_path=str(path),
            approval_granted=True,
            operation="raster_update_tags",
            parameters={"target_path": str(target), "tags": {"reviewed": "yes"}},
        )
    )
    assert plan.status == "planned"
    result = apply_data_edit(
        CodingDataApplyRequest(
            workspace_root=str(tmp_path),
            file_path=str(path),
            approval_granted=True,
            operator_approved=True,
            operation="raster_update_tags",
            parameters={"target_path": str(target), "tags": {"reviewed": "yes"}},
            expected_source_hash=plan.source_hash,
        )
    )
    assert result.status == "applied", result.blocked_reason
    with rasterio.open(target) as dataset:
        assert dataset.tags()["reviewed"] == "yes"


def test_netcdf_real_dimensions_variables_and_attr_copy(tmp_path: Path):
    path = tmp_path / "sample.nc"
    xr.Dataset(
        {"temperature": (("time", "x"), np.array([[1.0, 2.0], [3.0, 4.0]]))},
        coords={"time": [0, 1], "x": [10, 20]},
        attrs={"title": "source"},
    ).to_netcdf(path, engine="h5netcdf")

    preview = inspect_data_path(path)
    assert preview.status == "completed"
    assert preview.metadata["engine"] == "h5netcdf"
    assert any(dim["name"] == "time" for dim in preview.dimensions)
    assert any(var["name"] == "temperature" for var in preview.variables)
    assert preview.preview["sample_values"]["temperature"][0][0] == 1.0

    target = tmp_path / "sample.attr.nc"
    plan = plan_data_edit(
        CodingDataEditPlanRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True, operation="netcdf_update_attr", parameters={"target_path": str(target), "attr_name": "reviewed", "value": "yes"})
    )
    result = apply_data_edit(
        CodingDataApplyRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True, operator_approved=True, operation="netcdf_update_attr", parameters={"target_path": str(target), "attr_name": "reviewed", "value": "yes"}, expected_source_hash=plan.source_hash)
    )
    assert result.status == "applied"
    assert "sample_values" not in json.dumps(result.operation_details)
    with xr.open_dataset(target, engine="h5netcdf") as dataset:
        assert dataset.attrs["reviewed"] == "yes"


def test_netcdf4_worker_warning_is_surfaced_without_replacing_h5netcdf_result(tmp_path: Path, monkeypatch):
    path = tmp_path / "sample.nc"
    xr.Dataset({"value": (("x",), np.array([1, 2, 3]))}, attrs={"title": "source"}).to_netcdf(path, engine="h5netcdf")

    monkeypatch.setattr(
        data_adapter,
        "_inspect_netcdf4_with_timeout",
        lambda *_args, **_kwargs: {
            "status": "completed",
            "warnings": ["numpy.ndarray size changed, may indicate binary incompatibility. Expected 16 from C header, got 96 from PyObject"],
            "metadata": {"engine": "netCDF4_worker"},
            "schema_summary": {"dimensions": [], "variables": []},
            "preview": {"sample_values": {}},
            "dimensions": [],
            "variables": [],
            "preview_truncated": False,
        },
    )

    preview = inspect_data_path(path)

    assert preview.status == "completed"
    assert preview.metadata["engine"] == "h5netcdf"
    assert any("netCDF4 worker warning" in warning for warning in preview.warnings)
    assert "value" in preview.preview["sample_values"]


def test_netcdf4_worker_timeout_returns_h5netcdf_result_quickly(tmp_path: Path, monkeypatch):
    path = tmp_path / "sample.nc"
    xr.Dataset({"value": (("x",), np.array([1, 2, 3]))}).to_netcdf(path, engine="h5netcdf")

    monkeypatch.setattr(data_adapter, "_inspect_netcdf4_with_timeout", lambda *_args, **_kwargs: {"status": "timeout", "timeout_seconds": 0.05})
    started = time.monotonic()
    preview = inspect_data_path(path)
    elapsed = time.monotonic() - started

    assert elapsed < 2
    assert preview.status == "completed"
    assert preview.metadata["engine"] == "h5netcdf"
    assert any("netCDF4 fallback worker timed out" in warning for warning in preview.warnings)


def test_netcdf_main_path_has_no_direct_netcdf4_import():
    adapter_source = Path(data_adapter.__file__).read_text(encoding="utf-8")
    edit_source = elysia_path("app", "api", "coding_data_edit_service.py").read_text(encoding="utf-8")

    assert "from netCDF4 import" not in edit_source
    assert "import netCDF4" not in edit_source
    assert adapter_source.count("from netCDF4 import Dataset") == 1
    assert "def _netcdf4_worker_main" in adapter_source


def test_hdf5_real_tree_sample_and_attr_copy(tmp_path: Path):
    path = tmp_path / "sample.h5"
    with h5py.File(path, "w") as handle:
        dataset = handle.create_dataset("group/data", data=np.arange(6).reshape((2, 3)))
        dataset.attrs["units"] = "count"

    preview = inspect_data_path(path)
    assert preview.status == "completed"
    assert preview.variables[0]["path"] == "/group/data"

    target = tmp_path / "sample.attr.h5"
    plan = plan_data_edit(
        CodingDataEditPlanRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True, operation="hdf5_update_attr", parameters={"target_path": str(target), "object_path": "/group/data", "attr_name": "reviewed", "value": "yes"})
    )
    result = apply_data_edit(
        CodingDataApplyRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True, operator_approved=True, operation="hdf5_update_attr", parameters={"target_path": str(target), "object_path": "/group/data", "attr_name": "reviewed", "value": "yes"}, expected_source_hash=plan.source_hash)
    )
    assert result.status == "applied"
    with h5py.File(target, "r") as handle:
        assert handle["/group/data"].attrs["reviewed"] == "yes"


def _write_minimal_zarr_store(path: Path) -> None:
    array_dir = path / "data"
    array_dir.mkdir(parents=True)
    (path / ".zgroup").write_text('{"zarr_format": 2}', encoding="utf-8")
    (path / ".zattrs").write_text('{"title": "source"}', encoding="utf-8")
    (array_dir / ".zarray").write_text(
        json.dumps(
            {
                "zarr_format": 2,
                "shape": [2, 3],
                "chunks": [1, 3],
                "dtype": "<i8",
                "compressor": None,
                "fill_value": 0,
                "order": "C",
                "filters": None,
            }
        ),
        encoding="utf-8",
    )
    (array_dir / ".zattrs").write_text('{"units": "count"}', encoding="utf-8")
    (array_dir / "0.0").write_bytes(np.array([[0, 1, 2]], dtype="<i8").tobytes(order="C"))
    (array_dir / "1.0").write_bytes(np.array([[3, 4, 5]], dtype="<i8").tobytes(order="C"))


def test_zarr_real_store_sample_and_attr_copy(tmp_path: Path):
    path = tmp_path / "sample.zarr"
    _write_minimal_zarr_store(path)

    preview = inspect_data_path(path)
    assert preview.status == "completed"
    assert preview.variables[0]["path"] == "/data"

    target = tmp_path / "sample.attr.zarr"
    plan = plan_data_edit(
        CodingDataEditPlanRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True, operation="zarr_update_attr", parameters={"target_path": str(target), "object_path": "/data", "attr_name": "reviewed", "value": "yes"})
    )
    result = apply_data_edit(
        CodingDataApplyRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True, operator_approved=True, operation="zarr_update_attr", parameters={"target_path": str(target), "object_path": "/data", "attr_name": "reviewed", "value": "yes"}, expected_source_hash=plan.source_hash)
    )
    assert result.status == "applied", result.blocked_reason
    assert json.loads((target / "data" / ".zattrs").read_text(encoding="utf-8"))["reviewed"] == "yes"
    assert "sample_values" not in json.dumps(result.operation_details)
    assert "0.0" not in json.dumps(result.operation_details)


def test_zarr_library_timeout_returns_local_store_warning(tmp_path: Path, monkeypatch):
    path = tmp_path / "sample.zarr"
    _write_minimal_zarr_store(path)

    def slow_worker(_path_text: str, _max_items: int, _max_values: int, _result_queue: Any) -> None:
        time.sleep(5)

    monkeypatch.setattr(data_adapter, "_zarr_library_worker_main", slow_worker)
    monkeypatch.setattr(data_adapter, "ZARR_LIBRARY_TIMEOUT_SECONDS", 0.05)

    started = time.monotonic()
    preview = inspect_data_path(path)
    elapsed = time.monotonic() - started

    assert elapsed < 2
    assert preview.status == "completed"
    assert preview.metadata["store_format"] == "zarr_local_directory"
    assert preview.preview["sample_values"]["/data"] == [0, 1, 2]
    assert any("timed out" in warning for warning in preview.warnings)
