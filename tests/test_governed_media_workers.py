from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
import wave
from contextlib import contextmanager
from pathlib import Path

from app.api import imageforge_service, speechforge_service, videoforge_service
from app.api.coding_audit_service import get_coding_audit_record
from app.api.capability_service import get_capabilities_status
from app.api.coding_operation_service import approve_operation
from app.api.main import create_app
from app.api.media_worker_process_service import _bounded_process, _offline_environment, _worker_lock, execute_media_worker
from app.api.media_worker_registry_service import governed_media_gates, kokoro_voice_catalog, media_runtime_registry, media_worker_truth, model_registry
from app.api.request_trace_service import get_request_trace_record
from app.api.routes.media_workers import get_imageforge_models, get_media_gates, get_media_workers, get_tts_voices, get_videoforge_models
from app.api.schemas.coding_operations import CodingOperationApproveRequest
from app.api.schemas.media_workers import (
    ImageForgeApplyRequest,
    ImageForgePlanRequest,
    SpeechTranscriptionApplyRequest,
    SpeechTranscriptionPlanRequest,
    SpeechTtsApplyRequest,
    SpeechTtsPlanRequest,
    VideoForgeApplyRequest,
    VideoForgePlanRequest,
)


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        stream.writeframes(b"\x00\x00" * 16_000)


def _approve(
    *,
    workspace_root: Path,
    operation_kind: str,
    exact_files: list[str],
    source_hash: str,
    plan_hash: str,
) -> dict[str, str]:
    approval = approve_operation(CodingOperationApproveRequest(
        operation_kind=operation_kind,
        operation_summary=f"Approve governed {operation_kind} test",
        workspace_root=str(workspace_root),
        exact_files=exact_files,
        source_hash=source_hash,
        plan_hash=plan_hash,
        allowed_mutation_class="artifact_generation",
        operator_approved=True,
        approval_phrase="approve exact local artifact",
        rollback_note="Delete the derived artifact if no longer wanted.",
    ))
    assert approval.status == "approved"
    assert approval.approval_token
    return {"approval_id": approval.approval_id, "approval_token": approval.approval_token}


def test_worker_truth_is_sanitized_and_routes_are_registered():
    app = create_app()
    paths = set(app.openapi()["paths"])
    assert {
        "/coding/media/workers",
        "/coding/media/gates",
        "/coding/media/transcribe/preview",
        "/coding/media/transcribe/apply",
        "/coding/media/tts/preview",
        "/coding/media/tts/apply",
        "/coding/media/tts/voices",
        "/coding/media/imageforge/models",
        "/coding/media/imageforge/preview",
        "/coding/media/imageforge/apply",
        "/coding/media/imageforge/jobs/{operation_id}",
        "/coding/media/imageforge/jobs/{operation_id}/cancel",
        "/coding/media/videoforge/models",
        "/coding/media/videoforge/preview",
        "/coding/media/videoforge/apply",
        "/coding/media/videoforge/jobs/{operation_id}",
        "/coding/media/videoforge/jobs/{operation_id}/cancel",
    } <= paths
    assert not any("clone" in path or "reference-voice" in path for path in paths)
    assert not any(item["module"] == "app.api.routes.media_workers" for item in app.state.pending_route_modules)

    truth = media_worker_truth()
    rendered = repr(truth)
    assert truth["speechforge"]["stt_model_present"] is False
    # Owner-local XDG overrides may legitimately bind optional reviewed assets.
    # The public contract is the boolean truth plus absence of raw local paths,
    # not a machine-specific expectation that those assets must be missing.
    assert isinstance(truth["speechforge"]["tts_model_present"], bool)
    assert isinstance(truth["speechforge"]["tts_voices_present"], bool)
    assert truth["voice_cloning"]["available"] is False
    assert ("Elysia_" + "Model_Vault") not in rendered
    assert "/tmp/" not in rendered
    assert all("local_path" not in model and "voices_path" not in model for model in model_registry("speechforge"))
    assert {voice["id"] for voice in kokoro_voice_catalog()} >= {"af_sarah", "am_adam"}

    worker_payload = asyncio.run(get_media_workers())
    voice_payload = asyncio.run(get_tts_voices())
    image_payload = asyncio.run(get_imageforge_models())
    video_payload = asyncio.run(get_videoforge_models())
    gate_payload = asyncio.run(get_media_gates())
    assert worker_payload["data"]["media_workers"]["voice_cloning"]["state"] == "deliberately_unavailable"
    assert voice_payload["data"]["voice_cloning_available"] is False
    assert image_payload["data"]["production_enabled_count"] == 1
    assert video_payload["data"]["production_enabled_count"] == 0
    assert gate_payload["data"]["media_gates"]["features"]["voice_cloning"]["status"] == "unavailable_by_design"
    assert governed_media_gates()["features"]["videoforge"]["status"] == "lab_only"
    assert {runtime["id"] for runtime in media_runtime_registry()} >= {"whisper-cpp", "kokoro-onnx", "diffusers-videoforge"}

    capabilities = {
        entry["capability_key"]: entry
        for entry in get_capabilities_status()["data"]["capabilities"]
    }
    assert capabilities["speech_transcription"]["state"] == "degraded"
    assert capabilities["synthetic_reading_voice"]["state"] in {"live", "degraded"}
    assert capabilities["imageforge_lab"]["state"] in {"live", "degraded"}
    assert capabilities["videoforge_lab"]["state"] == "degraded"
    assert capabilities["voice_cloning"]["state"] == "unavailable"


def test_worker_environment_does_not_inherit_credentials(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "do-not-inherit")
    monkeypatch.setenv("HF_TOKEN", "do-not-inherit")
    monkeypatch.setenv("HTTPS_PROXY", "http://do-not-inherit.invalid")
    environment = _offline_environment(tmp_path)
    assert environment["HOME"] == str(tmp_path)
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert "AWS_SECRET_ACCESS_KEY" not in environment
    assert "HF_TOKEN" not in environment
    assert "HTTPS_PROXY" not in environment


def test_worker_boundary_refuses_concurrent_job():
    worker_lock = _worker_lock("speechforge_worker")
    assert worker_lock.acquire(blocking=False)
    try:
        with execute_media_worker("speechforge_worker", {"kind": "stt"}) as result:
            assert result == {"status": "unavailable", "blocked_reason": "worker_busy"}
    finally:
        worker_lock.release()


def test_worker_boundary_cancellation_stops_process_group(tmp_path: Path):
    cancel_event = threading.Event()
    timer = threading.Timer(0.1, cancel_event.set)
    started = time.monotonic()
    timer.start()
    try:
        code, stdout, stderr, failure = _bounded_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout_seconds=5,
            stdout_limit=1024,
            stderr_limit=1024,
            env=_offline_environment(tmp_path),
            cancel_event=cancel_event,
        )
    finally:
        timer.cancel()
    assert failure == "worker_cancelled"
    assert code != 0
    assert stdout == b"" and stderr == b""
    assert time.monotonic() - started < 2


def test_transcription_requires_consent_and_exact_approval(tmp_path: Path, monkeypatch):
    source = tmp_path / "synthetic.wav"
    _write_wav(source)
    unapproved = speechforge_service.plan_transcription(SpeechTranscriptionPlanRequest(
        workspace_root=str(tmp_path), file_path=str(source), operator_has_processing_rights=True,
    ))
    assert unapproved.status == "approval_required"

    plan_request = SpeechTranscriptionPlanRequest(
        session_id="session_stt_test",
        workspace_root=str(tmp_path),
        file_path=str(source),
        target_path="elysia-artifacts/transcripts/synthetic.txt",
        approval_granted=True,
        operator_has_processing_rights=True,
        contains_other_people=False,
        private_local_use=True,
    )
    plan = speechforge_service.plan_transcription(plan_request)
    assert plan.status == "planned"
    assert plan.target_relative_path and plan.sidecar_relative_path and plan.source_hash and plan.plan_hash
    approval = _approve(
        workspace_root=tmp_path,
        operation_kind="speech_transcription",
        exact_files=[str(source), plan.target_relative_path, plan.sidecar_relative_path],
        source_hash=plan.source_hash,
        plan_hash=plan.plan_hash,
    )
    worker_output = tmp_path / "worker-transcript.txt"
    worker_output.write_text("Synthetic local audio.\n", encoding="utf-8")

    @contextmanager
    def fake_worker(_worker_key: str, _job: dict):
        yield {
            "status": "completed",
            "output_path": str(worker_output),
            "output_sha256": speechforge_service._sha_file(worker_output),
            "output_bytes": worker_output.stat().st_size,
            "language": "en",
            "segment_count": 1,
        }

    monkeypatch.setattr(speechforge_service, "execute_media_worker", fake_worker)
    result = speechforge_service.apply_transcription(SpeechTranscriptionApplyRequest(
        **plan_request.model_dump(),
        expected_source_hash=plan.source_hash,
        expected_plan_hash=plan.plan_hash,
        **approval,
    ))
    assert result.status == "completed"
    assert result.artifact_id and result.audit_written and result.raw_transcript_returned is False
    transcript = tmp_path / str(result.target_relative_path)
    assert transcript.read_text(encoding="utf-8") == "Synthetic local audio.\n"

    audit = get_coding_audit_record(result.operation_id or "")
    trace = get_request_trace_record(result.request_id or "")
    assert audit is not None and trace is not None
    assert "Synthetic local audio" not in json.dumps(audit)
    assert "Synthetic local audio" not in json.dumps(trace)
    tool = trace["snapshot"]["tools_used"][0]
    assert tool["artifact_id"] == result.artifact_id
    assert tool["model_id"] == "whisper-cpp-base-en"
    assert tool["raw_content_logged"] is False
    assert str(tmp_path) not in json.dumps(audit)
    assert str(tmp_path) not in json.dumps(trace)


def test_kokoro_tts_is_catalog_only_non_cloning_and_exact_approved(tmp_path: Path, monkeypatch):
    denied = speechforge_service.plan_tts(SpeechTtsPlanRequest(
        workspace_root=str(tmp_path), text="A calm local reading.", voice_id="reference_voice", approval_granted=True,
    ))
    assert denied.blocked_reason == "tts_voice_not_allowed"
    plan_request = SpeechTtsPlanRequest(
        session_id="session_tts_test",
        workspace_root=str(tmp_path),
        text="A calm local reading.",
        voice_id="af_sarah",
        target_path="elysia-artifacts/speech/calm.wav",
        approval_granted=True,
    )
    plan = speechforge_service.plan_tts(plan_request)
    assert plan.status == "planned"
    assert plan.voice_cloning_available is False
    assert plan.target_relative_path and plan.sidecar_relative_path and plan.plan_hash
    approval = _approve(
        workspace_root=tmp_path,
        operation_kind="speech_tts",
        exact_files=[plan.target_relative_path, plan.sidecar_relative_path],
        source_hash=plan.text_hash,
        plan_hash=plan.plan_hash,
    )
    worker_output = tmp_path / "worker-speech.wav"
    _write_wav(worker_output)

    @contextmanager
    def fake_worker(_worker_key: str, _job: dict):
        yield {
            "status": "completed",
            "output_path": str(worker_output),
            "output_sha256": speechforge_service._sha_file(worker_output),
            "output_bytes": worker_output.stat().st_size,
            "sample_rate_hz": 16_000,
            "duration_seconds": 1.0,
        }

    monkeypatch.setattr(speechforge_service, "execute_media_worker", fake_worker)
    result = speechforge_service.apply_tts(SpeechTtsApplyRequest(
        **plan_request.model_dump(),
        expected_text_hash=plan.text_hash,
        expected_plan_hash=plan.plan_hash,
        **approval,
    ))
    assert result.status == "completed"
    assert result.artifact_id and result.output_sha256 and result.audit_written
    assert result.audio_data_url and result.audio_data_url.startswith("data:audio/wav;base64,")
    assert result.voice_cloning_available is False
    audit = get_coding_audit_record(result.operation_id or "")
    assert audit is not None
    assert plan_request.text not in json.dumps(audit)


def test_imageforge_flux_is_creator_profile_gated_and_other_models_remain_blocked(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ELYSIA_IMAGEFORGE_LAB_ENABLED", raising=False)
    plan = imageforge_service.plan_image(ImageForgePlanRequest(
        workspace_root=str(tmp_path),
        model_id="commoncanvas-xl-c",
        prompt="a small green local-first computer terminal in a forest",
        approval_granted=True,
        lab_acknowledged=True,
    ))
    assert plan.status == "lab_only_disabled"
    assert plan.production_enabled is False
    assert plan.blocked_reason == "imageforge_lab_not_enabled"
    by_id = {model["id"]: model for model in model_registry("imageforge")}
    assert by_id["flux1-schnell"]["enabled_state"] == "profile_gated"
    assert by_id["flux1-schnell"]["license_review_status"].startswith("verified_against_official")
    assert by_id["mitsua-diffusion-one"]["enabled_state"] == "disabled_unsafe_weights"
    assert by_id["commoncanvas-xl-c"]["enabled_state"] == "lab_only"
    assert by_id["commoncanvas-xl-c"]["gates"]["licensing"] == "passed_official_cc_by_sa_4_0_terms_but_distribution_obligations_not_yet_satisfied"
    assert "full_training_asset_attribution_chain_not_packaged" in by_id["commoncanvas-xl-c"]["production_blockers"]
    flux = imageforge_service.plan_image(ImageForgePlanRequest(
        workspace_root=str(tmp_path),
        model_id="flux1-schnell",
        prompt="a small green local-first terminal in a forest",
        steps=1,
        approval_granted=True,
        lab_acknowledged=True,
    ))
    assert flux.status == "planned"
    assert flux.production_enabled is True
    refused = imageforge_service.plan_image(ImageForgePlanRequest(
        workspace_root=str(tmp_path),
        model_id="flux1-schnell",
        prompt="a small green local-first terminal in a forest",
        steps=2,
        approval_granted=True,
        lab_acknowledged=True,
    ))
    assert refused.blocked_reason == "imageforge_flux_sequential_profile_not_allowed"
    mitsua = imageforge_service.plan_image(ImageForgePlanRequest(
        workspace_root=str(tmp_path),
        model_id="mitsua-diffusion-one",
        prompt="a small green local-first terminal in a forest",
        steps=1,
        approval_granted=True,
        lab_acknowledged=True,
    ))
    assert mitsua.status == "blocked"
    assert mitsua.blocked_reason and "unsafe_pickle" in mitsua.blocked_reason


def _wait_image_job(operation_id: str, terminal: set[str]) -> object:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = imageforge_service.get_image_job(operation_id)
        if result is not None and result.status in terminal:
            return result
        time.sleep(0.01)
    raise AssertionError(f"Image job {operation_id} did not reach {terminal}")


def test_imageforge_flux_job_is_exact_approved_cancellable_and_sanitized(tmp_path: Path, monkeypatch):
    prompt = "a small green local-first terminal in a quiet forest"
    request = ImageForgePlanRequest(
        session_id="session_image_test",
        workspace_root=str(tmp_path),
        model_id="flux1-schnell",
        prompt=prompt,
        target_path="elysia-artifacts/images/forest.png",
        steps=1,
        approval_granted=True,
    )
    plan = imageforge_service.plan_image(request)
    assert plan.status == "planned" and plan.plan_hash and plan.target_relative_path and plan.sidecar_relative_path
    approval = _approve(
        workspace_root=tmp_path,
        operation_kind="imageforge_generate",
        exact_files=[plan.target_relative_path, plan.sidecar_relative_path],
        source_hash=plan.prompt_hash,
        plan_hash=plan.plan_hash,
    )
    worker_output = tmp_path / "worker-image.png"
    worker_output.write_bytes(b"synthetic-image-fixture")

    @contextmanager
    def fake_worker(_worker_key: str, _job: dict, *, cancel_event=None):
        assert cancel_event is not None
        yield {
            "status": "completed",
            "output_path": str(worker_output),
            "output_sha256": imageforge_service._sha_file(worker_output),
            "output_bytes": worker_output.stat().st_size,
            "runtime_seconds": 0.5,
            "peak_gpu_memory_mib": 262.1,
        }

    monkeypatch.setattr(imageforge_service, "execute_media_worker", fake_worker)
    queued = imageforge_service.queue_image(ImageForgeApplyRequest(
        **request.model_dump(),
        expected_prompt_hash=plan.prompt_hash,
        expected_plan_hash=plan.plan_hash,
        **approval,
    ))
    assert queued.status in {"queued", "running", "completed"}
    result = _wait_image_job(queued.operation_id or "", {"completed", "failed"})
    assert result.status == "completed"
    assert result.production_enabled is True
    assert result.cancellation_supported is True
    assert result.output_sha256 and result.artifact_id
    audit = get_coding_audit_record(result.operation_id or "")
    if audit is not None:
        assert prompt not in json.dumps(audit)
        assert str(tmp_path) not in json.dumps(audit)


def _wait_video_job(operation_id: str, terminal: set[str]) -> object:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = videoforge_service.get_video_job(operation_id)
        if result is not None and result.status in terminal:
            return result
        time.sleep(0.01)
    raise AssertionError(f"Video job {operation_id} did not reach {terminal}")


def test_videoforge_is_lab_only_exact_approved_and_centrally_sanitized(tmp_path: Path, monkeypatch):
    prompt = "a small green local-first terminal in a quiet forest"
    request = VideoForgePlanRequest(
        session_id="session_video_test",
        workspace_root=str(tmp_path),
        prompt=prompt,
        target_path="elysia-artifacts/videos/forest.mp4",
        approval_granted=True,
        lab_acknowledged=True,
    )
    monkeypatch.delenv("ELYSIA_VIDEOFORGE_LAB_ENABLED", raising=False)
    assert videoforge_service.plan_video(request).status == "lab_only_disabled"
    monkeypatch.setenv("ELYSIA_VIDEOFORGE_LAB_ENABLED", "1")
    plan = videoforge_service.plan_video(request)
    assert plan.status == "planned"
    assert plan.target_relative_path and plan.sidecar_relative_path and plan.plan_hash
    approval = _approve(
        workspace_root=tmp_path,
        operation_kind="videoforge_generate",
        exact_files=[plan.target_relative_path, plan.sidecar_relative_path],
        source_hash=plan.prompt_hash,
        plan_hash=plan.plan_hash,
    )
    worker_output = tmp_path / "worker-video.mp4"
    worker_output.write_bytes(b"synthetic-video-fixture")

    @contextmanager
    def fake_worker(_worker_key: str, _job: dict, *, cancel_event=None):
        assert cancel_event is not None
        yield {
            "status": "completed",
            "output_path": str(worker_output),
            "output_sha256": videoforge_service._sha_file(worker_output),
            "output_bytes": worker_output.stat().st_size,
            "duration_seconds": 1.125,
            "runtime_seconds": 1.5,
            "peak_gpu_memory_mib": 1024.0,
        }

    monkeypatch.setattr(videoforge_service, "execute_media_worker", fake_worker)
    queued = videoforge_service.apply_video(VideoForgeApplyRequest(
        **request.model_dump(),
        expected_prompt_hash=plan.prompt_hash,
        expected_plan_hash=plan.plan_hash,
        **approval,
    ))
    assert queued.status in {"queued", "running", "completed"}
    result = _wait_video_job(queued.operation_id, {"completed", "failed"})
    assert result.status == "completed"
    assert result.artifact_id and result.audit_written and result.output_sha256
    assert result.production_enabled is False and result.cancellation_supported is True
    audit = get_coding_audit_record(result.operation_id)
    trace = get_request_trace_record(result.request_id or "")
    assert audit is not None and trace is not None
    assert prompt not in json.dumps(audit)
    assert prompt not in json.dumps(trace)
    assert str(tmp_path) not in json.dumps(audit)
    assert str(tmp_path) not in json.dumps(trace)
    tool = trace["snapshot"]["tools_used"][0]
    assert tool["runtime_seconds"] == "1.5"
    assert tool["peak_gpu_memory_mib"] == "1024.0"
    assert tool["cancel_requested"] is False


def test_videoforge_running_job_can_be_cancelled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ELYSIA_VIDEOFORGE_LAB_ENABLED", "1")
    request = VideoForgePlanRequest(
        workspace_root=str(tmp_path),
        prompt="a tiny abstract green light moving through a forest",
        target_path="elysia-artifacts/videos/cancel.mp4",
        approval_granted=True,
        lab_acknowledged=True,
    )
    plan = videoforge_service.plan_video(request)
    assert plan.status == "planned" and plan.plan_hash and plan.target_relative_path and plan.sidecar_relative_path
    approval = _approve(
        workspace_root=tmp_path,
        operation_kind="videoforge_generate",
        exact_files=[plan.target_relative_path, plan.sidecar_relative_path],
        source_hash=plan.prompt_hash,
        plan_hash=plan.plan_hash,
    )

    @contextmanager
    def waiting_worker(_worker_key: str, _job: dict, *, cancel_event=None):
        assert cancel_event is not None
        cancel_event.wait(timeout=2)
        yield {"status": "cancelled", "blocked_reason": "operator_cancelled"}

    monkeypatch.setattr(videoforge_service, "execute_media_worker", waiting_worker)
    queued = videoforge_service.apply_video(VideoForgeApplyRequest(
        **request.model_dump(),
        expected_prompt_hash=plan.prompt_hash,
        expected_plan_hash=plan.plan_hash,
        **approval,
    ))
    cancelled = videoforge_service.cancel_video_job(queued.operation_id)
    assert cancelled is not None and cancelled.status == "cancel_requested"
    result = _wait_video_job(queued.operation_id, {"cancelled"})
    assert result.cancel_requested is True
    assert not (tmp_path / "elysia-artifacts/videos/cancel.mp4").exists()
    trace = get_request_trace_record(result.request_id or "")
    assert trace is not None and trace["request_status"] == "blocked"
    assert request.prompt not in json.dumps(trace)
