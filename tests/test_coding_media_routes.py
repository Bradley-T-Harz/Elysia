from __future__ import annotations

import asyncio
import shutil
import wave
from pathlib import Path

import pytest

from app.api.coding_audit_service import get_coding_audit_record
from app.api.coding_trace_service import coding_request_id
from app.api.main import create_app
from app.api.request_trace_service import get_request_trace_record
from app.api.routes.coding_media import get_media_types, post_media_inspect, post_media_thumbnail
from app.api.schemas.media import CodingMediaPathRequest


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\x00\x00" * 800)


def test_media_routes_registered_on_local_bridge():
    app = create_app()
    paths = set(app.openapi()["paths"])
    assert "/coding/media-types" in paths
    assert "/coding/media/inspect" in paths
    assert "/coding/media/thumbnail" in paths
    assert "app.api.routes.coding_media" in app.state.registered_route_modules
    assert not any(item["module"] == "app.api.routes.coding_media" for item in app.state.pending_route_modules)


def test_media_types_route_reports_governed_worker_truth():
    payload = asyncio.run(get_media_types())
    assert payload["status"] == "ok"
    assert len(payload["data"]["media_types"]) == 9
    health = payload["data"]["dependency_health"]
    assert health["network_allowed"] is False
    assert health["transcription_live"] is False
    # Optional owner-local reviewed assets can make these profile-gated workers
    # live without changing the portable tracked defaults.
    assert isinstance(health["tts_live"], bool)
    assert isinstance(health["generation_live"], bool)
    assert health["voice_cloning_live"] is False


def test_media_inspect_requires_approval_and_writes_compact_trace(tmp_path: Path):
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe is not available")
    source = tmp_path / "approved.wav"
    _write_wav(source)
    request = CodingMediaPathRequest(
        session_id="session_media_test",
        workspace_root=str(tmp_path),
        file_path=str(source),
        approval_granted=False,
    )
    blocked = asyncio.run(post_media_inspect(request))
    assert blocked["data"]["media"]["status"] == "approval_required"
    assert blocked["approval_state"] == "needed"

    approved = asyncio.run(post_media_inspect(request.model_copy(update={"approval_granted": True})))
    result = approved["data"]["media"]
    assert result["status"] == "completed"
    assert result["audit_written"] is True
    assert result["request_id"] == coding_request_id(result["operation_id"])
    audit = get_coding_audit_record(result["operation_id"])
    assert audit is not None
    assert audit["relative_path"] == "approved.wav"
    assert str(tmp_path) not in repr(audit)
    trace = get_request_trace_record(result["request_id"])
    assert trace is not None
    assert trace["snapshot"]["route_used"] == "coding.media_inspect"
    assert trace["snapshot"]["tools_used"][0]["operation_id"] == result["operation_id"]
    assert trace["snapshot"]["tools_used"][0]["approval_required"] is True
    assert trace["snapshot"]["tools_used"][0]["approval_state"] == "approved"
    assert str(tmp_path) not in repr(trace)


def test_media_path_guard_blocks_symlink_and_audio_thumbnail(tmp_path: Path):
    source = tmp_path / "real.wav"
    _write_wav(source)
    linked = tmp_path / "linked.wav"
    linked.symlink_to(source)
    blocked = asyncio.run(post_media_inspect(CodingMediaPathRequest(
        workspace_root=str(tmp_path), file_path=str(linked), approval_granted=True
    )))
    assert blocked["data"]["media"]["status"] == "blocked"
    assert blocked["data"]["media"]["blocked_reason"] == "symlink_not_allowed"

    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe is not available")
    thumbnail = asyncio.run(post_media_thumbnail(CodingMediaPathRequest(
        workspace_root=str(tmp_path), file_path=str(source), approval_granted=True
    )))
    result = thumbnail["data"]["media"]
    assert result["thumbnail_status"] == "not_applicable"
    assert result["thumbnail_data_url"] is None
