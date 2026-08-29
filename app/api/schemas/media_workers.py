"""Schemas for governed local speech and generative-media worker lanes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.api.schemas.common import ElysiaSchemaModel


class SpeechTranscriptionPlanRequest(ElysiaSchemaModel):
    session_id: str | None = None
    workspace_root: str
    file_path: str
    target_path: str | None = None
    output_format: Literal["txt", "json", "srt", "vtt"] = "txt"
    approval_granted: bool = False
    approval_reason: str | None = None
    operator_has_processing_rights: bool = False
    contains_other_people: bool = False
    other_people_consent_confirmed: bool = False
    private_local_use: bool = True
    redact_sensitive_text: bool = True


class SpeechTranscriptionApplyRequest(SpeechTranscriptionPlanRequest):
    expected_source_hash: str
    expected_plan_hash: str
    approval_id: str
    approval_token: str


class SpeechTranscriptionPlanResult(ElysiaSchemaModel):
    status: str
    file_label: str
    relative_path: str | None = None
    target_relative_path: str | None = None
    sidecar_relative_path: str | None = None
    source_hash: str | None = None
    plan_hash: str | None = None
    model_id: str | None = None
    engine: str | None = None
    language: str | None = None
    duration_seconds: float | None = None
    size_bytes: int = 0
    output_format: str = "txt"
    consent_state: str = "unconfirmed"
    approval_required: bool = True
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SpeechTranscriptionResult(SpeechTranscriptionPlanResult):
    artifact_id: str | None = None
    transcript_sha256: str | None = None
    sidecar_sha256: str | None = None
    transcript_bytes: int = 0
    segment_count: int = 0
    operation_id: str | None = None
    request_id: str | None = None
    approval_id: str | None = None
    audit_written: bool = False
    network_used: bool = False
    cloud_used: bool = False
    raw_transcript_returned: bool = False


class SpeechTtsPlanRequest(ElysiaSchemaModel):
    session_id: str | None = None
    workspace_root: str
    text: str = Field(min_length=1, max_length=4000)
    voice_id: str = "af_sarah"
    speed: float = Field(default=1.0, ge=0.75, le=1.25)
    target_path: str | None = None
    approval_granted: bool = False
    approval_reason: str | None = None
    purpose_category: Literal["accessibility", "private_reading", "local_artifact"] = "private_reading"


class SpeechTtsApplyRequest(SpeechTtsPlanRequest):
    expected_text_hash: str
    expected_plan_hash: str
    approval_id: str
    approval_token: str


class SpeechTtsPlanResult(ElysiaSchemaModel):
    status: str
    voice_id: str
    voice_label: str | None = None
    language: str | None = None
    text_hash: str
    text_length: int
    speed: float
    purpose_category: str
    target_relative_path: str | None = None
    sidecar_relative_path: str | None = None
    plan_hash: str | None = None
    model_id: str = "kokoro-onnx-v1"
    synthetic_reading_voice: bool = True
    voice_cloning_available: bool = False
    approval_required: bool = True
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SpeechTtsResult(SpeechTtsPlanResult):
    artifact_id: str | None = None
    output_sha256: str | None = None
    sidecar_sha256: str | None = None
    output_bytes: int = 0
    sample_rate_hz: int | None = None
    duration_seconds: float | None = None
    audio_data_url: str | None = None
    operation_id: str | None = None
    request_id: str | None = None
    approval_id: str | None = None
    audit_written: bool = False
    network_used: bool = False
    cloud_used: bool = False


class ImageForgePlanRequest(ElysiaSchemaModel):
    session_id: str | None = None
    workspace_root: str
    model_id: str = "flux1-schnell"
    prompt: str = Field(min_length=1, max_length=1200)
    negative_prompt: str = Field(default="", max_length=500)
    purpose_category: Literal["private_creative", "accessibility", "documentary_illustration", "lab_smoke"] = "private_creative"
    width: int = 256
    height: int = 256
    steps: int = Field(default=1, ge=1, le=12)
    seed: int = Field(default=5, ge=0, le=2_147_483_647)
    target_path: str | None = None
    approval_granted: bool = False
    approval_reason: str | None = None
    lab_acknowledged: bool = False
    contains_real_person_request: bool = False


class ImageForgeApplyRequest(ImageForgePlanRequest):
    expected_prompt_hash: str
    expected_plan_hash: str
    approval_id: str
    approval_token: str


class ImageForgePlanResult(ElysiaSchemaModel):
    status: str
    model_id: str
    model_state: str
    prompt_hash: str
    prompt_length: int
    purpose_category: str
    width: int
    height: int
    steps: int
    seed: int
    target_relative_path: str | None = None
    sidecar_relative_path: str | None = None
    plan_hash: str | None = None
    synthetic_media: bool = True
    production_enabled: bool = False
    approval_required: bool = True
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ImageForgeResult(ImageForgePlanResult):
    artifact_id: str | None = None
    output_sha256: str | None = None
    sidecar_sha256: str | None = None
    output_bytes: int = 0
    runtime_seconds: float | None = None
    peak_gpu_memory_mib: float | None = None
    image_data_url: str | None = None
    operation_id: str | None = None
    request_id: str | None = None
    approval_id: str | None = None
    audit_written: bool = False
    network_used: bool = False
    cloud_used: bool = False
    cancellation_supported: bool = True
    cancel_requested: bool = False


class VideoForgePlanRequest(ElysiaSchemaModel):
    session_id: str | None = None
    workspace_root: str
    model_id: Literal["wan21-t2v-1.3b"] = "wan21-t2v-1.3b"
    prompt: str = Field(min_length=1, max_length=1200)
    negative_prompt: str = Field(default="", max_length=500)
    purpose_category: Literal["private_creative", "documentary_illustration", "lab_smoke"] = "private_creative"
    width: Literal[416] = 416
    height: Literal[256] = 256
    frames: Literal[9] = 9
    fps: Literal[8] = 8
    steps: Literal[4] = 4
    seed: int = Field(default=5, ge=0, le=2_147_483_647)
    target_path: str | None = None
    approval_granted: bool = False
    approval_reason: str | None = None
    lab_acknowledged: bool = False
    contains_real_person_request: bool = False


class VideoForgeApplyRequest(VideoForgePlanRequest):
    expected_prompt_hash: str
    expected_plan_hash: str
    approval_id: str
    approval_token: str


class VideoForgePlanResult(ElysiaSchemaModel):
    status: str
    model_id: str
    model_state: str
    prompt_hash: str
    prompt_length: int
    purpose_category: str
    width: int
    height: int
    frames: int
    fps: int
    steps: int
    seed: int
    target_relative_path: str | None = None
    sidecar_relative_path: str | None = None
    plan_hash: str | None = None
    synthetic_media: bool = True
    production_enabled: bool = False
    approval_required: bool = True
    cancellation_supported: bool = True
    blocked_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class VideoForgeJobResult(VideoForgePlanResult):
    operation_id: str
    request_id: str | None = None
    approval_id: str | None = None
    workspace_root_hash: str | None = None
    artifact_id: str | None = None
    output_sha256: str | None = None
    sidecar_sha256: str | None = None
    output_bytes: int = 0
    duration_seconds: float | None = None
    runtime_seconds: float | None = None
    peak_gpu_memory_mib: float | None = None
    audit_written: bool = False
    cancel_requested: bool = False
    network_used: bool = False
    cloud_used: bool = False


class VideoForgeCancelRequest(ElysiaSchemaModel):
    session_id: str | None = None
    reason: str = Field(default="operator_cancelled", max_length=160)


class MediaWorkerTruth(ElysiaSchemaModel):
    speechforge: dict[str, Any] = Field(default_factory=dict)
    imageforge: dict[str, Any] = Field(default_factory=dict)
    videoforge: dict[str, Any] = Field(default_factory=dict)
    voice_cloning: dict[str, Any] = Field(default_factory=dict)


__all__ = (
    "ImageForgeApplyRequest",
    "ImageForgePlanRequest",
    "ImageForgePlanResult",
    "ImageForgeResult",
    "MediaWorkerTruth",
    "SpeechTranscriptionApplyRequest",
    "SpeechTranscriptionPlanRequest",
    "SpeechTranscriptionPlanResult",
    "SpeechTranscriptionResult",
    "SpeechTtsApplyRequest",
    "SpeechTtsPlanRequest",
    "SpeechTtsPlanResult",
    "SpeechTtsResult",
    "VideoForgeApplyRequest",
    "VideoForgeCancelRequest",
    "VideoForgeJobResult",
    "VideoForgePlanRequest",
    "VideoForgePlanResult",
)
