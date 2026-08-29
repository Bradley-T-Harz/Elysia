from __future__ import annotations

import asyncio
from pathlib import Path

from app.api.main import create_app
from app.api.routes.coding_data import get_data_types, post_data_export_plan, post_data_inspect, post_data_preview
from app.api.schemas.coding_data import CodingDataExportPlanRequest, CodingDataPathRequest


async def _await_payload(coro):
    return await coro


def test_data_routes_registered_on_local_bridge():
    app = create_app()
    paths = set(app.openapi()["paths"])

    assert "/coding/data-types" in paths
    assert "/coding/data/inspect" in paths
    assert "/coding/data/preview" in paths
    assert "/coding/data/export-plan" in paths
    assert "/coding/data/edit-plan" in paths
    assert "/coding/data/apply-approved" in paths


def test_data_routes_inspect_preview_and_export_plan(tmp_path: Path):
    path = tmp_path / "sample.tsv"
    path.write_text("name\tvalue\nalpha\t1\n", encoding="utf-8")

    types_payload = asyncio.run(_await_payload(get_data_types()))
    assert any(item["type_id"] == "tsv_table" for item in types_payload["data"]["data_types"])

    inspect_payload = asyncio.run(_await_payload(post_data_inspect(CodingDataPathRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True))))
    assert inspect_payload["data"]["data"]["status"] == "completed"

    approval_payload = asyncio.run(_await_payload(post_data_preview(CodingDataPathRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=False))))
    assert approval_payload["data"]["data"]["status"] == "approval_required"

    preview_payload = asyncio.run(_await_payload(post_data_preview(CodingDataPathRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True))))
    assert preview_payload["data"]["data"]["preview"]["rows"][0]["name"] == "alpha"

    plan_payload = asyncio.run(_await_payload(post_data_export_plan(CodingDataExportPlanRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True, export_format="markdown"))))
    assert plan_payload["data"]["data_export_plan"]["status"] == "planned"
