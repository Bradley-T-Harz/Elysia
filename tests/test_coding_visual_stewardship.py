from __future__ import annotations

import asyncio
from pathlib import Path

import piexif
from PIL import Image, ImageDraw

from app.api.coding_exif_privacy_service import exif_privacy_report
from app.api.coding_image_edit_service import apply_visual_edit, plan_visual_edit
from app.api.coding_ocr_service import run_local_ocr
from app.api.coding_visual_adapter_service import inspect_visual_path
from app.api.coding_visual_export_service import apply_visual_export, plan_visual_export
from app.api.coding_visual_type_registry import detect_visual_type, visual_registry_payload
from app.api.main import create_app
from app.api.routes.coding_files import post_file_read_preview
from app.api.routes.coding_visual import (
    get_visual_types,
    post_visual_analysis,
    post_visual_export_plan,
    post_visual_inspect,
    post_visual_ocr,
    post_visual_preview,
)
from app.api.schemas.coding_files import CodingFileReadPreviewRequest
from app.api.schemas.coding_visual import (
    CodingVisualAnalysisRequest,
    CodingVisualApplyRequest as _CodingVisualApplyRequest,
    CodingVisualEditPlanRequest,
    CodingVisualExportApplyRequest as _CodingVisualExportApplyRequest,
    CodingVisualExportPlanRequest,
    CodingVisualOcrRequest,
    CodingVisualPathRequest,
)
from tests.coding_approval_test_helpers import approval_fields_for_plan


def CodingVisualExportApplyRequest(**kwargs):
    plan = plan_visual_export(
        CodingVisualExportPlanRequest(
            **{key: value for key, value in kwargs.items() if key in {"session_id", "workspace_root", "file_path", "approval_granted", "approval_reason", "export_format", "target_path"}}
        )
    )
    approval = approval_fields_for_plan(workspace_root=kwargs["workspace_root"], operation_kind="visual_export", mutation_class="visual_export", source_file=kwargs["file_path"], plan=plan)
    return _CodingVisualExportApplyRequest(**approval, **kwargs)


def CodingVisualApplyRequest(**kwargs):
    plan = plan_visual_edit(
        CodingVisualEditPlanRequest(
            **{key: value for key, value in kwargs.items() if key in {"session_id", "workspace_root", "file_path", "approval_granted", "approval_reason", "operation", "parameters"}}
        )
    )
    approval = approval_fields_for_plan(workspace_root=kwargs["workspace_root"], operation_kind="visual_edit", mutation_class="visual_edit", source_file=kwargs["file_path"], plan=plan)
    return _CodingVisualApplyRequest(**approval, **kwargs)


async def _await_payload(coro):
    return await coro


def _write_png(path: Path, text: str | None = None) -> None:
    image = Image.new("RGB", (180, 90), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 170, 80), outline="blue", width=3)
    if text:
        draw.text((24, 34), text, fill="black")
    image.save(path)


def _write_jpeg_with_gps(path: Path) -> None:
    image = Image.new("RGB", (80, 60), "green")
    gps = {
        piexif.GPSIFD.GPSLatitudeRef: "N",
        piexif.GPSIFD.GPSLatitude: ((40, 1), (0, 1), (0, 1)),
        piexif.GPSIFD.GPSLongitudeRef: "W",
        piexif.GPSIFD.GPSLongitude: ((105, 1), (0, 1), (0, 1)),
    }
    exif = {"GPS": gps, "0th": {piexif.ImageIFD.Make: "ElysiaCam"}}
    image.save(path, exif=piexif.dump(exif))


def test_visual_type_registry_supports_chunk4_formats():
    payload = visual_registry_payload()
    type_ids = {item["type_id"] for item in payload}
    assert {"png_image", "jpeg_image", "webp_image", "gif_image", "bmp_image", "tiff_image", "svg_vector_image"} <= type_ids
    assert detect_visual_type("icon.svg").adapter == "svg"
    assert detect_visual_type("photo.jpeg").type_id == "jpeg_image"


def test_visual_routes_registered_on_local_bridge():
    app = create_app()
    paths = set(app.openapi()["paths"])
    assert "/coding/visual-types" in paths
    assert "/coding/visual/inspect" in paths
    assert "/coding/visual/preview" in paths
    assert "/coding/visual/ocr" in paths
    assert "/coding/visual/analysis" in paths
    assert "/coding/visual/export-plan" in paths
    assert "/coding/visual/apply-approved" in paths


def test_png_inspect_preview_analysis_export_and_edit(tmp_path: Path):
    source = tmp_path / "sample.png"
    _write_png(source, "HELLO")

    inspected = inspect_visual_path(source)
    assert inspected["status"] == "completed"
    assert inspected["metadata"]["width"] == 180
    assert inspected["preview"]["thumbnail_data_url"].startswith("data:image/png;base64,")

    inspect_payload = asyncio.run(_await_payload(post_visual_inspect(CodingVisualPathRequest(workspace_root=str(tmp_path), file_path=str(source), approval_granted=True))))
    assert inspect_payload["data"]["visual"]["status"] == "completed"

    approval_payload = asyncio.run(_await_payload(post_visual_preview(CodingVisualPathRequest(workspace_root=str(tmp_path), file_path=str(source)))))
    assert approval_payload["data"]["visual"]["status"] == "approval_required"

    preview_payload = asyncio.run(_await_payload(post_visual_preview(CodingVisualPathRequest(workspace_root=str(tmp_path), file_path=str(source), approval_granted=True))))
    assert preview_payload["data"]["visual"]["preview"]["thumbnail_data_url"].startswith("data:image/png;base64,")

    analysis_payload = asyncio.run(_await_payload(post_visual_analysis(CodingVisualAnalysisRequest(workspace_root=str(tmp_path), file_path=str(source), approval_granted=True))))
    assert analysis_payload["data"]["analysis"]["status"] == "completed"

    plan = plan_visual_export(CodingVisualExportPlanRequest(workspace_root=str(tmp_path), file_path=str(source), approval_granted=True, export_format="markdown", target_path="sample.visual.md"))
    assert plan.status == "planned"
    assert "Visual stewardship summary" in (plan.preview or "")
    result = apply_visual_export(CodingVisualExportApplyRequest(workspace_root=str(tmp_path), file_path=str(source), approval_granted=True, operator_approved=True, export_format="markdown", target_path="sample.visual.md", expected_source_hash=plan.source_hash))
    assert result.status == "applied"
    assert (tmp_path / "sample.visual.md").exists()

    edit_plan = plan_visual_edit(CodingVisualEditPlanRequest(workspace_root=str(tmp_path), file_path=str(source), approval_granted=True, operation="make_thumbnail", parameters={"size": 32, "target_path": "thumb.png"}))
    assert edit_plan.status == "planned"
    edit_result = apply_visual_edit(CodingVisualApplyRequest(workspace_root=str(tmp_path), file_path=str(source), approval_granted=True, operator_approved=True, operation="make_thumbnail", parameters={"size": 32, "target_path": "thumb.png"}, expected_source_hash=edit_plan.source_hash))
    assert edit_result.status == "applied"
    assert (tmp_path / "thumb.png").exists()
    with Image.open(source) as original:
        assert original.size == (180, 90)


def test_jpeg_exif_privacy_does_not_expose_precise_gps(tmp_path: Path):
    source = tmp_path / "gps.jpg"
    _write_jpeg_with_gps(source)
    report = exif_privacy_report(source)
    assert report["exif_present"] is True
    assert report["gps_present"] is True
    assert "gps_coordinates_present" in report["privacy_fields"]
    dumped = str(report)
    assert "40.0" not in dumped
    assert "105.0" not in dumped


def test_svg_is_sanitized_before_preview(tmp_path: Path):
    source = tmp_path / "unsafe.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60" onload="bad()">'
        '<script>alert(1)</script><a href="https://example.com"><text>Hello</text></a></svg>',
        encoding="utf-8",
    )
    result = inspect_visual_path(source)
    assert result["status"] == "completed"
    assert result["preview"]["sanitized_for_rendering"] is True
    assert result["risk_flags"]["unsafe_svg_content"] is True
    assert result["svg_safety"]["sanitizer_removed"]["elements"]
    assert result["svg_safety"]["sanitizer_removed"]["event_handlers"]
    assert result["svg_safety"]["sanitizer_removed"]["external_references"] >= 1


def test_file_read_preview_routes_visual_through_visual_adapter(tmp_path: Path):
    source = tmp_path / "selected.png"
    _write_png(source)
    payload = asyncio.run(
        _await_payload(
            post_file_read_preview(
                CodingFileReadPreviewRequest(
                    workspace_root=str(tmp_path),
                    file_path=str(source),
                    approval_granted=True,
                )
            )
        )
    )
    preview = payload["data"]["file_preview"]
    assert preview["category"] == "visual"
    assert preview["adapter"] == "visual"
    assert preview["source_contents_included"] is False
    assert "Visual file" in preview["content_preview"]
    assert "thumbnail_data_url" in preview["parse_summary"]["preview"]


def test_local_ocr_is_bounded_and_redacts_secret_like_text(tmp_path: Path):
    source = tmp_path / "ocr.png"
    _write_png(source, "API_KEY=SECRET123")
    result = run_local_ocr(source, max_chars=200)
    assert result["status"] in {"completed", "unavailable", "blocked"}
    if result["status"] == "completed":
        assert len(result["text_preview"]) <= 200
        assert "SECRET123" not in result["text_preview"]


def test_corrupt_or_binary_visual_is_blocked(tmp_path: Path):
    source = tmp_path / "notreally.png"
    source.write_bytes(b"\x00\x01\x02\x03")
    result = inspect_visual_path(source)
    assert result["status"] == "blocked"
    assert result["blocked_reason"].startswith(("image_open_failed", "image_inspect_failed"))


def test_visual_route_export_plan_and_ocr_health(tmp_path: Path):
    source = tmp_path / "route.png"
    _write_png(source, "TEXT")
    types_payload = asyncio.run(_await_payload(get_visual_types()))
    assert "ocr_health" in types_payload["data"]

    plan_payload = asyncio.run(
        _await_payload(
            post_visual_export_plan(
                CodingVisualExportPlanRequest(
                    workspace_root=str(tmp_path),
                    file_path=str(source),
                    approval_granted=True,
                    export_format="json",
                    target_path="route.visual.json",
                )
            )
        )
    )
    assert plan_payload["data"]["visual_export_plan"]["status"] == "planned"

    ocr_payload = asyncio.run(
        _await_payload(
            post_visual_ocr(
                CodingVisualOcrRequest(
                    workspace_root=str(tmp_path),
                    file_path=str(source),
                    approval_granted=True,
                    max_chars=100,
                )
            )
        )
    )
    assert ocr_payload["data"]["ocr"]["status"] in {"completed", "unavailable", "blocked"}
