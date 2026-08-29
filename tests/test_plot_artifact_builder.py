from __future__ import annotations

from types import SimpleNamespace

from core.plot_artifact_builder import (
    PLOT_ARTIFACT_KIND,
    PLOT_ARTIFACT_TOOL_KIND,
    PLOT_OPERATION_NUMERIC_SUMMARY_BAR_SVG,
    PlotArtifactStatus,
    build_numeric_summary_bar_svg,
)


def completed_data_execution_payload() -> dict:
    return {
        "ok": True,
        "status": "completed",
        "file_name": "sites.csv",
        "file_kind": "csv",
        "row_count": 3,
        "column_count": 4,
        "numeric_columns": ["temperature_c", "ph"],
        "numeric_stats": {
            "temperature_c": {
                "count": 3,
                "missing": 0,
                "min": 12.5,
                "max": 20.0,
                "mean": 17.0,
            },
            "ph": {
                "count": 3,
                "missing": 0,
                "min": 7.1,
                "max": 7.6,
                "mean": 7.333,
            },
        },
        "warnings": [],
        "errors": [],
    }


def test_builds_svg_from_completed_data_summary():
    result = build_numeric_summary_bar_svg(completed_data_execution_payload())

    assert result.ok is True
    assert result.status == PlotArtifactStatus.COMPLETED
    assert result.tool_kind == PLOT_ARTIFACT_TOOL_KIND
    assert result.operation == PLOT_OPERATION_NUMERIC_SUMMARY_BAR_SVG
    assert result.artifact_kind == PLOT_ARTIFACT_KIND
    assert result.plot_kind == "numeric_summary_bar_svg"
    assert result.svg_text.startswith("<svg")
    assert "temperature_c" in result.svg_text
    assert "ph" in result.svg_text
    assert result.source_file_name == "sites.csv"
    assert result.source_file_kind == "csv"
    assert result.metric == "mean"
    assert result.plotted_columns == ["temperature_c", "ph"]
    assert result.locality == "local"
    assert result.memory_posture == "not_memory"
    assert result.network_access_used is False
    assert result.mutated_files is False
    assert result.arbitrary_python_used is False
    assert result.shell_used is False
    assert result.errors == []


def test_blocks_when_data_execution_did_not_complete():
    payload = completed_data_execution_payload()
    payload.update({"ok": False, "status": "failed"})

    result = build_numeric_summary_bar_svg(payload)

    assert result.ok is False
    assert result.status == PlotArtifactStatus.BLOCKED
    assert result.svg_text == ""
    assert "Completed bounded data execution" in result.errors[0]


def test_blocks_when_no_numeric_stats_exist():
    payload = completed_data_execution_payload()
    payload["numeric_stats"] = {}

    result = build_numeric_summary_bar_svg(payload)

    assert result.ok is False
    assert result.status == PlotArtifactStatus.BLOCKED
    assert result.svg_text == ""
    assert "No numeric statistics" in result.errors[0]


def test_blocks_unsupported_metric():
    result = build_numeric_summary_bar_svg(
        completed_data_execution_payload(),
        metric="median",
    )

    assert result.ok is False
    assert result.status == PlotArtifactStatus.BLOCKED
    assert result.svg_text == ""
    assert "Unsupported plot metric" in result.errors[0]
    assert "mean" in result.errors[0]


def test_skips_non_finite_and_missing_values():
    payload = completed_data_execution_payload()
    payload["numeric_columns"] = ["a", "b", "c"]
    payload["numeric_stats"] = {
        "a": {"mean": None},
        "b": {"mean": float("nan")},
        "c": {"mean": 3.0},
    }

    result = build_numeric_summary_bar_svg(payload)

    assert result.ok is True
    assert result.status == PlotArtifactStatus.COMPLETED
    assert result.plotted_columns == ["c"]
    assert "c" in result.svg_text
    assert any("Skipped numeric columns" in warning for warning in result.warnings)


def test_escapes_svg_labels_safely():
    payload = completed_data_execution_payload()
    payload["numeric_columns"] = ["<script>alert(1)</script>"]
    payload["numeric_stats"] = {
        "<script>alert(1)</script>": {
            "count": 1,
            "missing": 0,
            "min": 1.0,
            "max": 1.0,
            "mean": 1.0,
        }
    }

    result = build_numeric_summary_bar_svg(payload)

    assert result.ok is True
    assert "<script>" not in result.svg_text
    assert "&lt;script&gt;" in result.svg_text


def test_limits_many_columns():
    payload = completed_data_execution_payload()
    payload["numeric_columns"] = [f"col_{index}" for index in range(20)]
    payload["numeric_stats"] = {
        f"col_{index}": {
            "count": 1,
            "missing": 0,
            "min": float(index),
            "max": float(index),
            "mean": float(index),
        }
        for index in range(20)
    }

    result = build_numeric_summary_bar_svg(payload, max_columns=5)

    assert result.ok is True
    assert len(result.plotted_columns) == 5
    assert result.plotted_columns == ["col_0", "col_1", "col_2", "col_3", "col_4"]
    assert any("limited to 5" in warning for warning in result.warnings)


def test_supports_negative_values():
    payload = completed_data_execution_payload()
    payload["numeric_columns"] = ["loss", "gain"]
    payload["numeric_stats"] = {
        "loss": {"mean": -5.0, "min": -7.0, "max": -3.0, "count": 3, "missing": 0},
        "gain": {"mean": 10.0, "min": 8.0, "max": 12.0, "count": 3, "missing": 0},
    }

    result = build_numeric_summary_bar_svg(payload)

    assert result.ok is True
    assert result.status == PlotArtifactStatus.COMPLETED
    assert result.plotted_columns == ["loss", "gain"]
    assert "loss" in result.svg_text
    assert "gain" in result.svg_text
    assert "<svg" in result.svg_text


def test_accepts_object_style_numeric_stats():
    payload = SimpleNamespace(
        ok=True,
        status="completed",
        file_name="object_stats.csv",
        file_kind="csv",
        row_count=3,
        column_count=2,
        numeric_columns=["value"],
        numeric_stats={
            "value": SimpleNamespace(
                count=3,
                missing=0,
                min=1,
                max=5,
                mean=3,
            )
        },
        warnings=[],
        errors=[],
    )

    result = build_numeric_summary_bar_svg(payload)

    assert result.ok is True
    assert result.status == PlotArtifactStatus.COMPLETED
    assert result.source_file_name == "object_stats.csv"
    assert result.plotted_columns == ["value"]
    assert "value" in result.svg_text
