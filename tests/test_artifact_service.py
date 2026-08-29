from __future__ import annotations

import json
from pathlib import Path


def _enum_text_for_test(value):
    return str(getattr(value, "value", value) or "")

import pytest

from app.api.artifact_service import (
    ArtifactCreationError,
    artifact_detail_from_record,
    artifact_summary_from_record,
    build_data_summary_artifact_record,
    create_data_summary_artifact,
    get_artifact_detail,
    list_artifacts,
)
from app.api.schemas.artifacts import (
    ArtifactKind,
    ArtifactMemoryPosture,
)
from app.api.schemas.common import ApprovalState, LocalityState
from app.api.schemas.execution import ExecutionStatus, ExecutionToolKind


def write_file(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def completed_data_execution_payload(csv_path: Path) -> dict:
    return {
        "ok": True,
        "used": True,
        "status": ExecutionStatus.COMPLETED,
        "tool_kind": ExecutionToolKind.DATA_EXECUTOR,
        "operation": "summarize_csv",
        "source_kind": "attached_file",
        "source_path": str(csv_path),
        "file_id": "file_sites_001",
        "file_name": csv_path.name,
        "file_kind": "csv",
        "row_count": 3,
        "column_count": 4,
        "columns": ["site", "temperature_c", "ph", "notes"],
        "numeric_columns": ["temperature_c", "ph"],
        "text_columns": ["site", "notes"],
        "missing_values_by_column": {
            "site": 0,
            "temperature_c": 0,
            "ph": 0,
            "notes": 1,
        },
        "preview_rows": [
            {
                "site": "A",
                "temperature_c": "12.5",
                "ph": "7.1",
                "notes": "clear",
            },
            {
                "site": "B",
                "temperature_c": "18.5",
                "ph": "7.3",
                "notes": "",
            },
        ],
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
                "mean": 7.3333333333,
            },
        },
        "locality": LocalityState.LOCAL,
        "approval_state": ApprovalState.NOT_NEEDED,
        "network_access_used": False,
        "mutated_files": False,
        "warnings": [],
        "errors": [],
    }


def test_completed_csv_summary_creates_local_data_summary_artifact(tmp_path):
    source_csv = write_file(
        tmp_path / "sites.csv",
        "site,temperature_c,ph,notes\n"
        "A,12.5,7.1,clear\n"
        "B,18.5,7.3,\n"
        "C,20.0,7.6,cloudy\n",
    )
    artifact_root = tmp_path / "artifacts"

    record = create_data_summary_artifact(
        completed_data_execution_payload(source_csv),
        request_id="req_test_001",
        conversation_id="conv_test_001",
        project_id="proj_test_001",
        artifact_root=artifact_root,
    )

    assert record.artifact_id.startswith("artifact_")
    assert record.kind == ArtifactKind.DATA_SUMMARY
    assert record.request_id == "req_test_001"
    assert record.conversation_id == "conv_test_001"
    assert record.project_id == "proj_test_001"
    assert record.producer_tool_kind == "data_executor"
    assert record.producer_operation == "summarize_csv"

    assert record.source.source_kind == "attached_file"
    assert record.source.source_file_id == "file_sites_001"
    assert record.source.source_file_name == "sites.csv"
    assert record.source.source_file_kind == "csv"
    assert record.source.source_path == str(source_csv)

    assert record.payload.row_count == 3
    assert record.payload.column_count == 4
    assert record.payload.columns == ["site", "temperature_c", "ph", "notes"]
    assert record.payload.numeric_columns == ["temperature_c", "ph"]
    assert record.payload.text_columns == ["site", "notes"]
    assert record.payload.missing_values_by_column["notes"] == 1
    assert record.payload.numeric_stats["temperature_c"]["mean"] == 17.0
    assert len(record.payload.preview_rows) == 2

    artifact_path = Path(record.artifact_path)
    assert artifact_path.exists()
    assert artifact_path.parent == artifact_root

    saved_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert saved_payload["artifact_id"] == record.artifact_id
    assert saved_payload["kind"] == "data_summary"
    assert saved_payload["payload"]["row_count"] == 3
    assert saved_payload["payload"]["column_count"] == 4
    assert saved_payload["source"]["source_file_name"] == "sites.csv"
    assert saved_payload["boundary"]["locality"] == "local"
    assert saved_payload["boundary"]["memory_posture"] == "not_memory"


def test_artifact_summary_is_compact_and_not_memory(tmp_path):
    source_csv = write_file(tmp_path / "sites.csv", "site,value\nA,1\n")
    record = create_data_summary_artifact(
        completed_data_execution_payload(source_csv),
        artifact_root=tmp_path / "artifacts",
    )

    summary = artifact_summary_from_record(record)
    summary_payload = summary.model_dump(mode="json")

    assert summary.kind == ArtifactKind.DATA_SUMMARY
    assert summary.locality == LocalityState.LOCAL
    assert summary.memory_posture == ArtifactMemoryPosture.NOT_MEMORY
    assert summary.source_file_id == "file_sites_001"
    assert summary.source_file_name == "sites.csv"
    assert summary.source_file_kind == "csv"
    assert summary.row_count == 3
    assert summary.column_count == 4
    assert summary.memory_promotion is False
    assert summary.private_context_sent is False
    assert summary.detail_available is True
    assert "source_path" not in summary_payload
    assert "artifact_path" not in summary_payload
    assert str(source_csv) not in json.dumps(summary_payload)


def test_artifact_list_and_detail_helpers_filter_without_raw_paths(tmp_path):
    source_csv = write_file(tmp_path / "sites.csv", "site,value\nA,1\n")
    artifact_root = tmp_path / "artifacts"
    record = create_data_summary_artifact(
        completed_data_execution_payload(source_csv),
        request_id="req_artifact_helper",
        conversation_id="conv_artifact_helper",
        project_id="proj_artifact_helper",
        artifact_root=artifact_root,
    )

    listed = list_artifacts(project_id="proj_artifact_helper", artifact_root=artifact_root)
    assert listed.total == 1
    assert listed.artifacts[0].artifact_id == record.artifact_id
    assert listed.artifacts[0].request_id == "req_artifact_helper"
    assert listed.artifacts[0].private_context_sent is False

    detail = get_artifact_detail(record.artifact_id, artifact_root=artifact_root)
    assert detail is not None
    payload = detail.model_dump(mode="json")
    assert payload["summary"]["artifact_id"] == record.artifact_id
    assert payload["boundary_truth"]["private_context_sent"] is False
    assert payload["boundary_truth"]["memory_promotion"] is False
    assert str(source_csv) not in json.dumps(payload)
    assert "artifact_path" not in json.dumps(payload)

    direct_detail = artifact_detail_from_record(record)
    assert direct_detail.summary.artifact_id == record.artifact_id


def test_artifact_boundary_truth_does_not_claim_risky_actions(tmp_path):
    source_csv = write_file(tmp_path / "sites.csv", "site,value\nA,1\n")
    record = create_data_summary_artifact(
        completed_data_execution_payload(source_csv),
        artifact_root=tmp_path / "artifacts",
    )

    assert record.boundary.locality == LocalityState.LOCAL
    assert record.boundary.approval_state == ApprovalState.NOT_NEEDED
    assert record.boundary.memory_posture == ArtifactMemoryPosture.NOT_MEMORY
    assert record.boundary.artifact_saved_locally is True
    assert record.boundary.source_file_mutated is False
    assert record.boundary.network_access_used is False
    assert record.boundary.memory_promoted is False
    assert record.boundary.arbitrary_python_used is False
    assert record.boundary.shell_used is False
    assert any("not memory" in note for note in record.boundary.notes)


def test_source_csv_is_not_modified_when_artifact_is_created(tmp_path):
    source_csv = write_file(
        tmp_path / "sites.csv",
        "site,value\nA,1\nB,2\n",
    )
    before = source_csv.read_text(encoding="utf-8")

    create_data_summary_artifact(
        completed_data_execution_payload(source_csv),
        artifact_root=tmp_path / "artifacts",
    )

    after = source_csv.read_text(encoding="utf-8")
    assert after == before


def test_failed_data_execution_does_not_create_success_artifact(tmp_path):
    source_csv = tmp_path / "missing.csv"
    artifact_root = tmp_path / "artifacts"
    payload = completed_data_execution_payload(source_csv)
    payload.update(
        {
            "ok": False,
            "used": True,
            "status": ExecutionStatus.FAILED,
            "row_count": 0,
            "column_count": 0,
            "errors": ["Data file does not exist."],
        }
    )

    with pytest.raises(ArtifactCreationError):
        create_data_summary_artifact(
            payload,
            artifact_root=artifact_root,
        )

    assert not artifact_root.exists()


def test_skipped_data_execution_does_not_create_artifact(tmp_path):
    source_csv = write_file(tmp_path / "sites.csv", "site,value\nA,1\n")
    payload = completed_data_execution_payload(source_csv)
    payload.update(
        {
            "ok": False,
            "used": False,
            "status": "not_needed",
        }
    )

    with pytest.raises(ArtifactCreationError):
        build_data_summary_artifact_record(
            payload,
            artifact_root=tmp_path / "artifacts",
        )


def test_completed_plot_build_creates_local_plot_image_artifact(tmp_path):
    import json

    from app.api.artifact_service import (
        artifact_summary_from_record,
        create_plot_image_artifact,
    )

    artifact_root = tmp_path / "artifacts"
    plot_build_result = {
        "ok": True,
        "status": "completed",
        "tool_kind": "plot_artifact_builder",
        "operation": "build_numeric_summary_bar_svg",
        "artifact_kind": "plot_image",
        "plot_kind": "numeric_summary_bar_svg",
        "title": "Numeric summary plot: sites.csv",
        "summary": "Generated local SVG bar chart of mean values for 2 numeric columns.",
        "svg_text": "<svg xmlns=\"http://www.w3.org/2000/svg\"><title>safe</title></svg>",
        "svg_mime_type": "image/svg+xml",
        "width": 720,
        "height": 420,
        "source_file_name": "sites.csv",
        "source_file_kind": "csv",
        "row_count": 3,
        "column_count": 4,
        "metric": "mean",
        "plotted_columns": ["temperature_c", "ph"],
        "network_access_used": False,
        "arbitrary_python_used": False,
        "shell_used": False,
        "warnings": [],
        "errors": [],
    }

    record = create_plot_image_artifact(
        plot_build_result,
        request_id="req_plot_001",
        conversation_id="conv_plot_001",
        project_id="proj_plot_001",
        artifact_root=artifact_root,
    )

    assert _enum_text_for_test(record.kind) == "plot_image"
    assert record.request_id == "req_plot_001"
    assert record.conversation_id == "conv_plot_001"
    assert record.project_id == "proj_plot_001"
    assert record.producer_tool_kind == "plot_artifact_builder"
    assert record.producer_operation == "build_numeric_summary_bar_svg"
    assert record.source.source_file_name == "sites.csv"
    assert record.source.source_file_kind == "csv"
    assert _enum_text_for_test(record.boundary.locality) == "local"
    assert _enum_text_for_test(record.boundary.memory_posture) == "not_memory"
    assert record.boundary.source_file_mutated is False
    assert record.boundary.network_access_used is False
    assert record.boundary.arbitrary_python_used is False
    assert record.boundary.shell_used is False
    assert record.payload.plot_kind == "numeric_summary_bar_svg"
    assert record.payload.svg_text.startswith("<svg")
    assert record.payload.svg_mime_type == "image/svg+xml"
    assert record.payload.metric == "mean"
    assert record.payload.plotted_columns == ["temperature_c", "ph"]

    saved = json.loads(Path(record.artifact_path).read_text(encoding="utf-8"))
    assert saved["kind"] == "plot_image"
    assert saved["payload"]["svg_text"].startswith("<svg")
    assert saved["payload"]["plotted_columns"] == ["temperature_c", "ph"]

    summary = artifact_summary_from_record(record)
    assert _enum_text_for_test(summary.kind) == "plot_image"
    assert summary.plot_kind == "numeric_summary_bar_svg"
    assert summary.svg_text is None
    assert summary.svg_mime_type == "image/svg+xml"
    assert summary.metric == "mean"
    assert summary.plotted_columns == ["temperature_c", "ph"]
    assert summary.source_file_name == "sites.csv"
    assert summary.row_count == 3
    assert summary.column_count == 4
    assert summary.preview_available is True
    assert summary.detail_available is True

    listed = list_artifacts(project_id="proj_plot_001", artifact_root=artifact_root)
    list_payload = listed.model_dump(mode="json")
    assert listed.total == 1
    assert listed.artifacts[0].artifact_id == record.artifact_id
    assert listed.artifacts[0].svg_text is None
    assert "<svg" not in json.dumps(list_payload)
    assert "artifact_path" not in json.dumps(list_payload)
    assert "source_path" not in json.dumps(list_payload)

    detail = artifact_detail_from_record(record)
    detail_payload = detail.model_dump(mode="json")
    assert detail.summary.svg_text is None
    assert detail_payload["safe_preview"]["svg_text"].startswith("<svg")
    assert detail_payload["safe_preview"]["svg_mime_type"] == "image/svg+xml"
    assert "artifact_path" not in json.dumps(detail_payload)
    assert "source_path" not in json.dumps(detail_payload)


def test_blocked_plot_build_does_not_create_plot_artifact(tmp_path):
    import pytest

    from app.api.artifact_service import (
        ArtifactCreationError,
        create_plot_image_artifact,
    )

    with pytest.raises(ArtifactCreationError):
        create_plot_image_artifact(
            {
                "ok": False,
                "status": "blocked",
                "artifact_kind": "plot_image",
                "svg_text": "",
            },
            artifact_root=tmp_path / "artifacts",
        )
