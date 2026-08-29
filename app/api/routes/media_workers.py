"""Governed SpeechForge and lab-only ImageForge route surfaces."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

from app.api.imageforge_service import cancel_image_job, get_image_job, plan_image, queue_image
from app.api.media_worker_registry_service import governed_media_gates, kokoro_voice_catalog, media_worker_truth, model_registry
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.api.schemas.media_workers import (
    ImageForgeApplyRequest,
    ImageForgePlanRequest,
    SpeechTranscriptionApplyRequest,
    SpeechTranscriptionPlanRequest,
    SpeechTtsApplyRequest,
    SpeechTtsPlanRequest,
    VideoForgeApplyRequest,
    VideoForgeCancelRequest,
    VideoForgePlanRequest,
)
from app.api.speechforge_service import apply_transcription, apply_tts, plan_transcription, plan_tts
from app.api.videoforge_service import apply_video, cancel_video_job, get_video_job, plan_video


router = APIRouter(prefix="/coding/media", tags=["coding", "media-workers"])
API_VERSION = "1.0.0"
CONTRACT_VERSION = "governed-media-workers-0.1"


def _request_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _payload(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude_none=False) if hasattr(model, "model_dump") else dict(model)


def _result_envelope(result_type: str, key: str, result: Any, *, lab: bool = False) -> dict[str, Any]:
    if result.status == "completed":
        approval = ApprovalState.APPROVED
        capability = CapabilityState.LIVE if not lab else CapabilityState.DEGRADED
    elif result.status in {"queued", "running", "cancel_requested"}:
        approval = ApprovalState.APPROVED
        capability = CapabilityState.DEGRADED if lab else CapabilityState.LIVE
    elif result.status in {"planned", "approval_required"}:
        approval = ApprovalState.NEEDED
        capability = CapabilityState.LIVE if not lab else CapabilityState.DEGRADED
    else:
        approval = ApprovalState.DENIED
        capability = CapabilityState.DEGRADED if lab or result.status in {"unavailable", "lab_only_disabled"} else CapabilityState.LIVE
    request_id = getattr(result, "request_id", None) or _request_id(f"req_{result_type}")
    return build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=capability,
        locality=LocalityState.LOCAL,
        approval_state=approval,
        warnings=[
            "Heavy ML runtimes execute only through fixed local subprocess workers; no cloud or network model loading is allowed.",
            "Voice cloning and reference-voice input are deliberately unavailable.",
        ],
        errors=[],
        trace_summary=TraceSummary(
            route_used=f"coding.media.{result_type}",
            log_written=bool(getattr(result, "audit_written", False)),
            journal_written=False,
        ),
        data={key: _payload(result)},
    ).to_payload()


@router.get("/workers")
async def get_media_workers() -> dict[str, Any]:
    return build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_request_id("req_media_workers"),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="media_worker_truth",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=["Installed or smoke-passed does not mean production-enabled."],
        errors=[],
        trace_summary=TraceSummary(route_used="coding.media.workers", log_written=False, journal_written=False),
        data={"media_workers": media_worker_truth()},
    ).to_payload()


@router.get("/gates")
async def get_media_gates() -> dict[str, Any]:
    return build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=_request_id("req_media_gates"),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type="media_gate_truth",
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=["Lab-only and disabled gates cannot be promoted silently."],
        errors=[],
        trace_summary=TraceSummary(route_used="coding.media.gates", log_written=False, journal_written=False),
        data={"media_gates": governed_media_gates()},
    ).to_payload()


@router.get("/tts/voices")
async def get_tts_voices() -> dict[str, Any]:
    return build_response_envelope(
        status=EnvelopeStatus.OK, request_id=_request_id("req_tts_voices"), api_version=API_VERSION,
        contract_version=CONTRACT_VERSION, result_type="tts_voice_catalog", capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL, approval_state=ApprovalState.NOT_NEEDED,
        warnings=["Catalog voices are synthetic reading voices. Voice cloning is unavailable by design."], errors=[],
        trace_summary=TraceSummary(route_used="coding.media.tts.voices", log_written=False, journal_written=False),
        data={"voices": kokoro_voice_catalog(), "voice_cloning_available": False},
    ).to_payload()


@router.get("/imageforge/models")
async def get_imageforge_models() -> dict[str, Any]:
    models = model_registry("imageforge")
    production_count = sum(1 for model in models if model.get("enabled_state") == "profile_gated")
    return build_response_envelope(
        status=EnvelopeStatus.OK, request_id=_request_id("req_imageforge_models"), api_version=API_VERSION,
        contract_version=CONTRACT_VERSION, result_type="imageforge_models", capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL, approval_state=ApprovalState.NOT_NEEDED,
        warnings=["FLUX.1-schnell is available only when the optional Creator profile runtime and local model assets pass doctor; CommonCanvas and Mitsua remain blocked."], errors=[],
        trace_summary=TraceSummary(route_used="coding.media.imageforge.models", log_written=False, journal_written=False),
        data={"models": models, "production_enabled_count": production_count},
    ).to_payload()


@router.get("/videoforge/models")
async def get_videoforge_models() -> dict[str, Any]:
    return build_response_envelope(
        status=EnvelopeStatus.OK, request_id=_request_id("req_videoforge_models"), api_version=API_VERSION,
        contract_version=CONTRACT_VERSION, result_type="videoforge_models", capability_state=CapabilityState.DEGRADED,
        locality=LocalityState.LOCAL, approval_state=ApprovalState.NOT_NEEDED,
        warnings=["Wan is lab-only; license/provenance verification and sustained resource testing block production."], errors=[],
        trace_summary=TraceSummary(route_used="coding.media.videoforge.models", log_written=False, journal_written=False),
        data={"models": model_registry("videoforge"), "production_enabled_count": 0},
    ).to_payload()


@router.post("/transcribe/preview")
async def post_transcribe_preview(payload: SpeechTranscriptionPlanRequest = Body(...)) -> dict[str, Any]:
    return _result_envelope("speech_transcription_plan", "transcription_plan", plan_transcription(payload))


@router.post("/transcribe/apply")
async def post_transcribe_apply(payload: SpeechTranscriptionApplyRequest = Body(...)) -> dict[str, Any]:
    return _result_envelope("speech_transcription_result", "transcription_result", apply_transcription(payload))


@router.post("/tts/preview")
async def post_tts_preview(payload: SpeechTtsPlanRequest = Body(...)) -> dict[str, Any]:
    return _result_envelope("speech_tts_plan", "tts_plan", plan_tts(payload))


@router.post("/tts/apply")
async def post_tts_apply(payload: SpeechTtsApplyRequest = Body(...)) -> dict[str, Any]:
    return _result_envelope("speech_tts_result", "tts_result", apply_tts(payload))


@router.post("/imageforge/preview")
async def post_imageforge_preview(payload: ImageForgePlanRequest = Body(...)) -> dict[str, Any]:
    return _result_envelope("imageforge_plan", "imageforge_plan", plan_image(payload))


@router.post("/imageforge/apply")
async def post_imageforge_apply(payload: ImageForgeApplyRequest = Body(...)) -> dict[str, Any]:
    return _result_envelope("imageforge_result", "imageforge_result", queue_image(payload))


@router.get("/imageforge/jobs/{operation_id}")
async def get_imageforge_job(operation_id: str) -> dict[str, Any]:
    result = get_image_job(operation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="ImageForge job was not found in the current local process.")
    return _result_envelope("imageforge_result", "imageforge_result", result)


@router.post("/imageforge/jobs/{operation_id}/cancel")
async def post_imageforge_cancel(operation_id: str) -> dict[str, Any]:
    result = cancel_image_job(operation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="ImageForge job was not found in the current local process.")
    return _result_envelope("imageforge_result", "imageforge_result", result)


@router.post("/videoforge/preview")
async def post_videoforge_preview(payload: VideoForgePlanRequest = Body(...)) -> dict[str, Any]:
    return _result_envelope("videoforge_plan", "videoforge_plan", plan_video(payload), lab=True)


@router.post("/videoforge/apply")
async def post_videoforge_apply(payload: VideoForgeApplyRequest = Body(...)) -> dict[str, Any]:
    return _result_envelope("videoforge_job", "videoforge_job", apply_video(payload), lab=True)


@router.get("/videoforge/jobs/{operation_id}")
async def get_videoforge_job(operation_id: str) -> dict[str, Any]:
    result = get_video_job(operation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="VideoForge job was not found in the current local process.")
    return _result_envelope("videoforge_job", "videoforge_job", result, lab=True)


@router.post("/videoforge/jobs/{operation_id}/cancel")
async def post_videoforge_cancel(
    operation_id: str,
    _payload: VideoForgeCancelRequest | None = Body(default=None),
) -> dict[str, Any]:
    result = cancel_video_job(operation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="VideoForge job was not found in the current local process.")
    return _result_envelope("videoforge_job", "videoforge_job", result, lab=True)


__all__ = ("router",)
