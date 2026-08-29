from __future__ import annotations

import app.api.artifact_service as artifact_service
from app.api.artifact_service import (
    create_data_summary_artifact,
    create_plot_image_artifact,
)
from app.api.main import create_app
from tests.asgi_test_client import ASGITestClient
from tests.test_artifact_service import completed_data_execution_payload, write_file


def test_artifact_list_and_detail_routes_return_safe_payloads(monkeypatch, tmp_path):
    artifact_root = tmp_path / "artifacts"
    monkeypatch.setattr(artifact_service, "DEFAULT_ARTIFACT_ROOT", artifact_root)

    source_csv = write_file(tmp_path / "sites.csv", "site,value\nA,1\n")
    record = create_data_summary_artifact(
        completed_data_execution_payload(source_csv),
        request_id="req_artifact_route",
        conversation_id="conv_artifact_route",
        project_id="proj_artifact_route",
        artifact_root=artifact_root,
    )

    client = ASGITestClient(create_app())
    list_response = client.get("/artifacts?project_id=proj_artifact_route")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["result_type"] == "artifact_list"
    assert list_payload["data"]["total"] == 1

    summary = list_payload["data"]["artifacts"][0]
    assert summary["artifact_id"] == record.artifact_id
    assert summary["project_id"] == "proj_artifact_route"
    assert summary["request_id"] == "req_artifact_route"
    assert summary["memory_promotion"] is False
    assert summary["private_context_sent"] is False
    assert "source_path" not in summary
    assert "artifact_path" not in summary

    detail_response = client.get(f"/artifacts/{record.artifact_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["result_type"] == "artifact_detail"
    assert detail_payload["data"]["summary"]["artifact_id"] == record.artifact_id
    assert detail_payload["data"]["boundary_truth"]["memory_promotion"] is False
    assert detail_payload["data"]["boundary_truth"]["private_context_sent"] is False
    assert str(source_csv) not in detail_response.text


def test_plot_artifact_list_is_compact_and_detail_carries_svg(monkeypatch, tmp_path):
    artifact_root = tmp_path / "artifacts"
    monkeypatch.setattr(artifact_service, "DEFAULT_ARTIFACT_ROOT", artifact_root)

    record = create_plot_image_artifact(
        {
            "ok": True,
            "status": "completed",
            "tool_kind": "plot_artifact_builder",
            "operation": "build_numeric_summary_bar_svg",
            "artifact_kind": "plot_image",
            "plot_kind": "numeric_summary_bar_svg",
            "title": "Numeric summary plot: sites.csv",
            "summary": "Generated local SVG bar chart of mean values.",
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
        },
        request_id="req_plot_route",
        conversation_id="conv_plot_route",
        project_id="proj_plot_route",
        artifact_root=artifact_root,
    )

    client = ASGITestClient(create_app())

    list_response = client.get("/artifacts?project_id=proj_plot_route")
    assert list_response.status_code == 200
    assert "<svg" not in list_response.text
    assert "artifact_path" not in list_response.text
    assert "source_path" not in list_response.text

    list_payload = list_response.json()
    summary = list_payload["data"]["artifacts"][0]
    assert summary["artifact_id"] == record.artifact_id
    assert summary["kind"] == "plot_image"
    assert summary.get("svg_text") in (None, "")
    assert summary["svg_mime_type"] == "image/svg+xml"
    assert summary["memory_promotion"] is False
    assert summary["private_context_sent"] is False

    detail_response = client.get(f"/artifacts/{record.artifact_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["result_type"] == "artifact_detail"
    assert detail_payload["data"]["summary"].get("svg_text") in (None, "")
    assert detail_payload["data"]["safe_preview"]["svg_text"].startswith("<svg")
    assert detail_payload["data"]["boundary_truth"]["memory_promotion"] is False
    assert detail_payload["data"]["boundary_truth"]["private_context_sent"] is False
    assert "artifact_path" not in detail_response.text
    assert "source_path" not in detail_response.text


def test_artifact_detail_route_returns_404_for_unknown_id(monkeypatch, tmp_path):
    monkeypatch.setattr(artifact_service, "DEFAULT_ARTIFACT_ROOT", tmp_path / "artifacts")

    client = ASGITestClient(create_app())
    response = client.get("/artifacts/artifact_missing")
    assert response.status_code == 404
