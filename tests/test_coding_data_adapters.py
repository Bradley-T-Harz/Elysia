from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

from app.api.coding_data_adapter_service import inspect_data_path


def test_csv_preview_redacts_secret_like_values(tmp_path: Path):
    path = tmp_path / "sample.csv"
    path.write_text("name,token\nalpha,SECRET_KEY=abc123\nbeta,ok\n", encoding="utf-8")

    preview = inspect_data_path(path)

    assert preview.status == "completed"
    assert preview.schema_summary["columns"][0]["name"] == "name"
    assert preview.redaction_count >= 1
    assert "[REDACTED]" in str(preview.preview)


def test_jsonl_preview_reports_malformed_lines(tmp_path: Path):
    path = tmp_path / "sample.jsonl"
    path.write_text('{"a": 1}\nnot-json\n{"b": 2}\n', encoding="utf-8")

    preview = inspect_data_path(path)

    assert preview.status == "completed"
    assert preview.metadata["malformed_line_count"] == 1
    assert preview.schema_summary["keys"] == ["a", "b"]


def test_sqlite_legacy_data_preview_defers_to_databaseforge_without_rows(tmp_path: Path):
    path = tmp_path / "sample.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE samples (id INTEGER PRIMARY KEY, name TEXT)")
    connection.execute("INSERT INTO samples (name) VALUES (?)", ("alpha",))
    connection.commit()
    connection.close()

    preview = inspect_data_path(path)

    assert preview.status == "blocked"
    assert preview.blocked_reason == "database_requires_databaseforge_schema_only_route"
    assert preview.tables == []
    assert preview.preview == {}
    assert any("DatabaseForge" in warning for warning in preview.warnings)


def test_geojson_preview_reports_schema_and_bounds(tmp_path: Path):
    path = tmp_path / "sample.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {"name": "a"}, "geometry": {"type": "Point", "coordinates": [1, 2]}},
                    {"type": "Feature", "properties": {"name": "b"}, "geometry": {"type": "Point", "coordinates": [3, 4]}},
                ],
            }
        ),
        encoding="utf-8",
    )

    preview = inspect_data_path(path)

    assert preview.status == "completed"
    assert preview.metadata["feature_count"] == 2
    assert preview.metadata["bounds"] == (1.0, 2.0, 3.0, 4.0)
    assert preview.schema_summary["properties"] == ["name"]


def test_kmz_zip_slip_is_blocked(tmp_path: Path):
    path = tmp_path / "evil.kmz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../evil.kml", "<kml />")

    preview = inspect_data_path(path)

    assert preview.status == "blocked"
    assert preview.blocked_reason == "zip_slip_member"


def test_corrupted_heavy_file_reports_adapter_read_failure(tmp_path: Path):
    path = tmp_path / "sample.parquet"
    path.write_bytes(b"PAR1fake")

    preview = inspect_data_path(path)

    assert preview.status == "blocked"
    assert str(preview.blocked_reason).startswith("parquet_read_failed:")
    assert preview.dependencies["pyarrow"] == "available"
