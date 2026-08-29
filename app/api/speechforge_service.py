"""Governed plans and exact-approved SpeechForge STT/Kokoro execution."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.api.artifact_service import build_generated_media_artifact_record, create_artifact_id, save_artifact_record
from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_media_adapter_service import MAX_DURATION_SECONDS, inspect_media_path
from app.api.coding_operation_service import consume_operation_approval
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.coding_trace_service import coding_request_id
from app.api.media_worker_process_service import execute_media_worker
from app.api.media_worker_registry_service import kokoro_voice
from app.api.schemas.media_workers import (
    SpeechTranscriptionApplyRequest,
    SpeechTranscriptionPlanRequest,
    SpeechTranscriptionPlanResult,
    SpeechTranscriptionResult,
    SpeechTtsApplyRequest,
    SpeechTtsPlanRequest,
    SpeechTtsPlanResult,
    SpeechTtsResult,
)


MAX_STT_DURATION_SECONDS = min(MAX_DURATION_SECONDS, 1800)
MAX_INLINE_AUDIO_BYTES = 2 * 1024 * 1024


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _plan_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _default_transcript_target(relative_source: str, output_format: str) -> str:
    stem = Path(relative_source).stem[:80] or "media"
    return f"elysia-artifacts/transcripts/{stem}.machine-transcript.{output_format}"


def _default_tts_target(text_hash: str) -> str:
    return f"elysia-artifacts/speech/tts_{text_hash[:12]}.wav"


def _sidecar_relative(target_relative: str) -> str:
    return f"{target_relative}.elysia-provenance.json"


def _guard_output(workspace_root: str, target_path: str, expected_suffix: str) -> tuple[Path | None, str | None, str | None]:
    guarded = guard_workspace_path(
        workspace_root=workspace_root,
        target_path=target_path,
        require_existing=False,
        allow_directory=False,
    )
    if not guarded.allowed or guarded.target_path is None or not guarded.relative_path:
        return None, None, guarded.reason or "artifact_target_not_allowed"
    if guarded.target_path.suffix.lower() != expected_suffix:
        return None, guarded.relative_path, "artifact_target_suffix_mismatch"
    if guarded.target_path.exists():
        return None, guarded.relative_path, "artifact_target_exists"
    return guarded.target_path, guarded.relative_path, None


def plan_transcription(payload: SpeechTranscriptionPlanRequest) -> SpeechTranscriptionPlanResult:
    guarded = guard_workspace_path(
        workspace_root=payload.workspace_root,
        target_path=payload.file_path,
        require_existing=True,
        allow_directory=False,
    )
    label = guarded.target_path.name if guarded.target_path else Path(payload.file_path).name or "selected media"
    base = dict(
        status="blocked",
        file_label=label,
        relative_path=guarded.relative_path,
        output_format=payload.output_format,
        consent_state="unconfirmed",
        approval_required=True,
        warnings=["Machine transcripts can contain errors or hallucinations and are not source-of-truth records."],
    )
    if not guarded.allowed:
        return SpeechTranscriptionPlanResult(**base, blocked_reason=guarded.reason)
    if not payload.approval_granted:
        return SpeechTranscriptionPlanResult(**{**base, "status": "approval_required"}, blocked_reason="explicit_approval_required")
    if not payload.operator_has_processing_rights or not payload.private_local_use:
        return SpeechTranscriptionPlanResult(**base, blocked_reason="processing_rights_or_local_use_not_confirmed")
    if payload.contains_other_people and not payload.other_people_consent_confirmed:
        return SpeechTranscriptionPlanResult(**base, blocked_reason="other_people_consent_required")

    inspection = inspect_media_path(guarded.target_path)
    if inspection.get("status") != "completed":
        return SpeechTranscriptionPlanResult(**base, blocked_reason=inspection.get("blocked_reason") or "media_inspection_failed")
    duration = float(inspection.get("duration_seconds") or 0.0)
    if duration <= 0 or duration > MAX_STT_DURATION_SECONDS:
        return SpeechTranscriptionPlanResult(**base, blocked_reason="transcription_duration_exceeded")
    if not (inspection.get("audio") or {}).get("codec"):
        return SpeechTranscriptionPlanResult(**base, blocked_reason="audio_stream_required")

    target = payload.target_path or _default_transcript_target(guarded.relative_path or label, payload.output_format)
    target_path, target_relative, target_error = _guard_output(payload.workspace_root, target, f".{payload.output_format}")
    if target_error or target_path is None or target_relative is None:
        return SpeechTranscriptionPlanResult(**base, blocked_reason=target_error)
    sidecar_relative = _sidecar_relative(target_relative)
    sidecar_path, _, sidecar_error = _guard_output(payload.workspace_root, sidecar_relative, ".json")
    if sidecar_error or sidecar_path is None:
        return SpeechTranscriptionPlanResult(**base, blocked_reason=sidecar_error)
    source_hash = _sha_file(guarded.target_path)
    plan_hash = _plan_hash({
        "operation": "speech_transcription",
        "source_hash": source_hash,
        "source": guarded.relative_path,
        "target": target_relative,
        "sidecar": sidecar_relative,
        "output_format": payload.output_format,
        "model_id": "whisper-cpp-base-en",
        "redact_sensitive_text": payload.redact_sensitive_text,
        "consent": {
            "processing_rights": payload.operator_has_processing_rights,
            "contains_other_people": payload.contains_other_people,
            "other_people_consent": payload.other_people_consent_confirmed,
            "private_local_use": payload.private_local_use,
        },
    })
    return SpeechTranscriptionPlanResult(
        **{**base, "status": "planned", "consent_state": "confirmed"},
        target_relative_path=target_relative,
        sidecar_relative_path=sidecar_relative,
        source_hash=source_hash,
        plan_hash=plan_hash,
        model_id="whisper-cpp-base-en",
        engine="whisper_cpp",
        language="en",
        duration_seconds=duration,
        size_bytes=guarded.target_path.stat().st_size,
        blocked_reason=None,
    )


def apply_transcription(payload: SpeechTranscriptionApplyRequest) -> SpeechTranscriptionResult:
    plan = plan_transcription(SpeechTranscriptionPlanRequest(**payload.model_dump(exclude={"expected_source_hash", "expected_plan_hash", "approval_id", "approval_token"})))
    operation_id = f"speech_stt_{uuid4().hex[:16]}"
    result = SpeechTranscriptionResult(**plan.model_dump(), operation_id=operation_id, request_id=coding_request_id(operation_id, payload.approval_id), approval_id=payload.approval_id)
    if plan.status != "planned" or plan.source_hash != payload.expected_source_hash or plan.plan_hash != payload.expected_plan_hash:
        result.status = "blocked"
        result.blocked_reason = "transcription_plan_or_source_hash_mismatch"
        _audit_speech(payload, result, "speech_transcription")
        return result
    assert plan.target_relative_path and plan.sidecar_relative_path and plan.relative_path
    approval = consume_operation_approval(
        approval_id=payload.approval_id,
        approval_token=payload.approval_token,
        operation_kind="speech_transcription",
        workspace_root=payload.workspace_root,
        exact_files=[payload.file_path, plan.target_relative_path, plan.sidecar_relative_path],
        source_hash=plan.source_hash,
        plan_hash=plan.plan_hash or "",
        allowed_mutation_class="artifact_generation",
    )
    if not approval.allowed:
        result.status = "blocked"
        result.blocked_reason = approval.reason or "approval_denied"
        _audit_speech(payload, result, "speech_transcription")
        return result

    source = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, require_existing=True, allow_directory=False).target_path
    target = guard_workspace_path(workspace_root=payload.workspace_root, target_path=plan.target_relative_path, require_existing=False, allow_directory=False).target_path
    sidecar = guard_workspace_path(workspace_root=payload.workspace_root, target_path=plan.sidecar_relative_path, require_existing=False, allow_directory=False).target_path
    if not source or not target or not sidecar or target.exists() or sidecar.exists():
        result.status = "blocked"
        result.blocked_reason = "artifact_target_changed_after_approval"
        _audit_speech(payload, result, "speech_transcription")
        return result

    artifact_id = create_artifact_id("artifact_transcript")
    try:
        with execute_media_worker("speechforge_worker", {
            "kind": "stt",
            "source_path": str(source),
            "output_name": f"worker-output.{payload.output_format}",
            "output_format": payload.output_format,
            "redact_sensitive_text": payload.redact_sensitive_text,
        }) as worker:
            if worker.get("status") != "completed":
                result.status = str(worker.get("status") or "failed")
                result.blocked_reason = str(worker.get("blocked_reason") or "speech_worker_failed")
                _audit_speech(payload, result, "speech_transcription")
                return result
            worker_output = Path(str(worker.get("output_path") or ""))
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as destination, worker_output.open("rb") as source_stream:
                shutil.copyfileobj(source_stream, destination, length=1024 * 1024)
            transcript_hash = _sha_file(target)
            if transcript_hash != worker.get("output_sha256"):
                raise ValueError("worker_output_hash_mismatch")
            sidecar_payload = {
                "artifact_id": artifact_id,
                "artifact_kind": "transcript",
                "machine_generated_transcript": True,
                "not_source_of_truth": True,
                "local_only": True,
                "cloud_used": False,
                "network_used": False,
                "model_id": "whisper-cpp-base-en",
                "engine": "whisper_cpp",
                "source_sha256": plan.source_hash,
                "output_sha256": transcript_hash,
                "output_format": payload.output_format,
                "duration_seconds": plan.duration_seconds,
                "language": worker.get("language") or "en",
                "segment_count": int(worker.get("segment_count") or 0),
                "redaction_requested": payload.redact_sensitive_text,
                "consent": {
                    "processing_rights_confirmed": payload.operator_has_processing_rights,
                    "contains_other_people": payload.contains_other_people,
                    "other_people_consent_confirmed": payload.other_people_consent_confirmed,
                    "private_local_use": payload.private_local_use,
                },
            }
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            sidecar.write_text(json.dumps(sidecar_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            sidecar_hash = _sha_file(sidecar)
            receipt = build_generated_media_artifact_record({
                "status": "completed", "artifact_kind": "transcript", "model_id": "whisper-cpp-base-en",
                "worker_key": "speechforge_worker", "mime_type": _transcript_mime(payload.output_format),
                "output_path": str(target), "output_sha256": transcript_hash, "output_bytes": target.stat().st_size,
                "sidecar_path": str(sidecar), "sidecar_sha256": sidecar_hash, "machine_generated_transcript": True,
                "duration_seconds": plan.duration_seconds, "language": worker.get("language") or "en",
                "segment_count": int(worker.get("segment_count") or 0), "provenance_state": "official_whisper_model_verified_local_revision_legacy_unknown",
                "source_kind": "approved_media_file", "source_file_name": source.name, "source_file_kind": source.suffix.lower().lstrip("."),
                "source_path": str(source), "operation": "speech_transcription", "title": f"Machine transcript: {source.name}",
                "summary": f"Local machine transcript ({payload.output_format}); raw transcript excluded from central trace.",
            }, request_id=result.request_id, artifact_id=artifact_id)
            save_artifact_record(receipt)
            result.status = "completed"
            result.blocked_reason = None
            result.artifact_id = artifact_id
            result.transcript_sha256 = transcript_hash
            result.sidecar_sha256 = sidecar_hash
            result.transcript_bytes = target.stat().st_size
            result.segment_count = int(worker.get("segment_count") or 0)
            result.language = str(worker.get("language") or "en")
    except Exception as exc:
        target.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)
        result.status = "failed"
        result.blocked_reason = f"speech_artifact_failed:{type(exc).__name__}"
    _audit_speech(payload, result, "speech_transcription")
    return result


def plan_tts(payload: SpeechTtsPlanRequest) -> SpeechTtsPlanResult:
    text_hash = _hash_text(payload.text)
    voice = kokoro_voice(payload.voice_id)
    base = dict(
        status="blocked", voice_id=payload.voice_id, text_hash=text_hash, text_length=len(payload.text),
        speed=payload.speed, purpose_category=payload.purpose_category, synthetic_reading_voice=True,
        voice_cloning_available=False, approval_required=True,
        warnings=["Synthetic reading voice; voice cloning and reference-voice input are unavailable by design.", "Kokoro model and published voice assets are Apache-2.0; preserve the local model/voice hashes and synthetic-media label."],
    )
    root_guard = guard_workspace_path(workspace_root=payload.workspace_root, target_path=".", require_existing=True, allow_directory=True)
    if not root_guard.allowed:
        return SpeechTtsPlanResult(**base, blocked_reason=root_guard.reason)
    if not payload.approval_granted:
        return SpeechTtsPlanResult(**{**base, "status": "approval_required"}, blocked_reason="explicit_approval_required")
    if voice is None:
        return SpeechTtsPlanResult(**base, blocked_reason="tts_voice_not_allowed")
    target = payload.target_path or _default_tts_target(text_hash)
    target_path, target_relative, target_error = _guard_output(payload.workspace_root, target, ".wav")
    if target_error or target_path is None or target_relative is None:
        return SpeechTtsPlanResult(**base, blocked_reason=target_error)
    sidecar_relative = _sidecar_relative(target_relative)
    sidecar_path, _, sidecar_error = _guard_output(payload.workspace_root, sidecar_relative, ".json")
    if sidecar_error or sidecar_path is None:
        return SpeechTtsPlanResult(**base, blocked_reason=sidecar_error)
    plan_hash = _plan_hash({
        "operation": "speech_tts", "text_hash": text_hash, "text_length": len(payload.text), "voice_id": payload.voice_id,
        "speed": payload.speed, "language": voice.get("language"), "purpose_category": payload.purpose_category,
        "target": target_relative, "sidecar": sidecar_relative, "model_id": "kokoro-onnx-v1",
    })
    return SpeechTtsPlanResult(
        **{**base, "status": "planned"}, voice_label=str(voice.get("display_name") or payload.voice_id),
        language=str(voice.get("language") or "en-us"), target_relative_path=target_relative,
        sidecar_relative_path=sidecar_relative, plan_hash=plan_hash, blocked_reason=None,
    )


def apply_tts(payload: SpeechTtsApplyRequest) -> SpeechTtsResult:
    plan = plan_tts(SpeechTtsPlanRequest(**payload.model_dump(exclude={"expected_text_hash", "expected_plan_hash", "approval_id", "approval_token"})))
    operation_id = f"speech_tts_{uuid4().hex[:16]}"
    result = SpeechTtsResult(**plan.model_dump(), operation_id=operation_id, request_id=coding_request_id(operation_id, payload.approval_id), approval_id=payload.approval_id)
    if plan.status != "planned" or plan.text_hash != payload.expected_text_hash or plan.plan_hash != payload.expected_plan_hash:
        result.status = "blocked"
        result.blocked_reason = "tts_plan_or_text_hash_mismatch"
        _audit_speech(payload, result, "speech_tts")
        return result
    assert plan.target_relative_path and plan.sidecar_relative_path
    approval = consume_operation_approval(
        approval_id=payload.approval_id, approval_token=payload.approval_token, operation_kind="speech_tts",
        workspace_root=payload.workspace_root, exact_files=[plan.target_relative_path, plan.sidecar_relative_path],
        source_hash=plan.text_hash, plan_hash=plan.plan_hash or "", allowed_mutation_class="artifact_generation",
    )
    if not approval.allowed:
        result.status = "blocked"
        result.blocked_reason = approval.reason or "approval_denied"
        _audit_speech(payload, result, "speech_tts")
        return result
    target = guard_workspace_path(workspace_root=payload.workspace_root, target_path=plan.target_relative_path, require_existing=False, allow_directory=False).target_path
    sidecar = guard_workspace_path(workspace_root=payload.workspace_root, target_path=plan.sidecar_relative_path, require_existing=False, allow_directory=False).target_path
    if not target or not sidecar or target.exists() or sidecar.exists():
        result.status = "blocked"
        result.blocked_reason = "artifact_target_changed_after_approval"
        _audit_speech(payload, result, "speech_tts")
        return result
    artifact_id = create_artifact_id("artifact_speech")
    try:
        with execute_media_worker("speechforge_worker", {
            "kind": "tts", "text": payload.text, "voice_id": payload.voice_id, "speed": payload.speed,
            "language": plan.language, "output_name": "worker-output.wav",
        }) as worker:
            if worker.get("status") != "completed":
                result.status = str(worker.get("status") or "failed")
                result.blocked_reason = str(worker.get("blocked_reason") or "speech_worker_failed")
                _audit_speech(payload, result, "speech_tts")
                return result
            worker_output = Path(str(worker.get("output_path") or ""))
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as destination, worker_output.open("rb") as source_stream:
                shutil.copyfileobj(source_stream, destination, length=1024 * 1024)
            output_hash = _sha_file(target)
            if output_hash != worker.get("output_sha256"):
                raise ValueError("worker_output_hash_mismatch")
            sidecar_payload = {
                "artifact_id": artifact_id, "artifact_kind": "speech_audio", "synthetic_media": True,
                "synthetic_reading_voice": True, "voice_cloning_used": False, "reference_voice_used": False,
                "local_only": True, "network_used": False, "cloud_used": False, "model_id": "kokoro-onnx-v1",
                "voice_id": payload.voice_id, "language": plan.language, "text_sha256": plan.text_hash,
                "text_length": plan.text_length, "output_sha256": output_hash,
                "sample_rate_hz": worker.get("sample_rate_hz"), "duration_seconds": worker.get("duration_seconds"),
                "purpose_category": payload.purpose_category, "provenance_state": "official_kokoro_distribution_verified_local_hashes_recorded",
            }
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            sidecar.write_text(json.dumps(sidecar_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            sidecar_hash = _sha_file(sidecar)
            receipt = build_generated_media_artifact_record({
                "status": "completed", "artifact_kind": "speech_audio", "model_id": "kokoro-onnx-v1",
                "worker_key": "speechforge_worker", "mime_type": "audio/wav", "output_path": str(target),
                "output_sha256": output_hash, "output_bytes": target.stat().st_size, "sidecar_path": str(sidecar),
                "sidecar_sha256": sidecar_hash, "synthetic_media": True, "duration_seconds": worker.get("duration_seconds"),
                "sample_rate_hz": worker.get("sample_rate_hz"), "prompt_or_text_hash": plan.text_hash,
                "prompt_or_text_length": plan.text_length, "provenance_state": "official_kokoro_distribution_verified_local_hashes_recorded",
                "operation": "speech_tts", "title": f"Synthetic reading voice: {plan.voice_label}",
                "summary": "Locally generated synthetic reading-voice WAV; input text excluded from central trace.",
            }, request_id=result.request_id, artifact_id=artifact_id)
            save_artifact_record(receipt)
            result.status = "completed"
            result.blocked_reason = None
            result.artifact_id = artifact_id
            result.output_sha256 = output_hash
            result.sidecar_sha256 = sidecar_hash
            result.output_bytes = target.stat().st_size
            result.sample_rate_hz = int(worker.get("sample_rate_hz") or 0) or None
            result.duration_seconds = float(worker.get("duration_seconds") or 0.0) or None
            if target.stat().st_size <= MAX_INLINE_AUDIO_BYTES:
                result.audio_data_url = "data:audio/wav;base64," + base64.b64encode(target.read_bytes()).decode("ascii")
    except Exception as exc:
        target.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)
        result.status = "failed"
        result.blocked_reason = f"speech_artifact_failed:{type(exc).__name__}"
    _audit_speech(payload, result, "speech_tts")
    return result


def _transcript_mime(output_format: str) -> str:
    return {"txt": "text/plain", "json": "application/json", "srt": "application/x-subrip", "vtt": "text/vtt"}[output_format]


def _audit_speech(payload: Any, result: Any, kind: str) -> None:
    audit_payload = {
        "session_id": getattr(payload, "session_id", None), "operation_kind": kind, "status": result.status,
        "workspace_root_hash": hash_path(getattr(payload, "workspace_root", "")), "relative_path": getattr(result, "relative_path", None),
        "target_relative_path": getattr(result, "target_relative_path", None), "source_hash": getattr(result, "source_hash", None) or getattr(result, "text_hash", None),
        "plan_hash": getattr(result, "plan_hash", None), "result_hash": getattr(result, "transcript_sha256", None) or getattr(result, "output_sha256", None),
        "approval_id": getattr(payload, "approval_id", None), "approval_required": True,
        "operator_approved": bool(getattr(payload, "approval_granted", False)), "allowed_mutation_class": "artifact_generation",
        "artifact_id": getattr(result, "artifact_id", None), "model_id": getattr(result, "model_id", None),
        "duration_seconds": getattr(result, "duration_seconds", None), "language": getattr(result, "language", None),
        "segment_count": getattr(result, "segment_count", None), "text_length": getattr(result, "text_length", None),
        "voice_id": getattr(result, "voice_id", None), "synthetic_media": kind == "speech_tts",
        "raw_content_logged": False, "network": False, "shell": False, "mutation_performed": result.status == "completed",
    }
    try:
        result.audit_written = write_coding_audit_record(kind, result.operation_id or f"{kind}_{uuid4().hex[:8]}", audit_payload)
    except OSError:
        result.warnings.append("Compact speech audit could not be persisted.")


__all__ = ("apply_transcription", "apply_tts", "plan_transcription", "plan_tts")
