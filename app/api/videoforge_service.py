"""Governed lab-only VideoForge plans, cancellable jobs, and artifact receipts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.api.artifact_service import build_generated_media_artifact_record, create_artifact_id, save_artifact_record
from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_operation_service import consume_operation_approval
from app.api.coding_path_guard_service import guard_workspace_path, hash_path
from app.api.coding_trace_service import coding_request_id
from app.api.media_worker_process_service import execute_media_worker
from app.api.media_worker_registry_service import raw_model_entry
from app.api.schemas.media_workers import (
    VideoForgeApplyRequest,
    VideoForgeJobResult,
    VideoForgePlanRequest,
    VideoForgePlanResult,
)


BLOCKED_PROMPT_MARKERS = {
    "deepfake", "face swap", "faceswap", "nude", "sexual", "porn", "graphic violence",
    "political persuasion", "campaign propaganda", "celebrity", "public figure",
    "copyrighted character", "voice-driven avatar", "impersonate", "real person",
}
TERMINAL_STATUSES = {"completed", "cancelled", "failed", "blocked", "unavailable"}
_JOBS: dict[str, VideoForgeJobResult] = {}
_CANCEL_EVENTS: dict[str, threading.Event] = {}
_THREADS: dict[str, threading.Thread] = {}
_JOB_LOCK = threading.Lock()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _plan_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _default_target(prompt_hash: str) -> str:
    return f"elysia-artifacts/videos/videoforge_{prompt_hash[:12]}.mp4"


def _sidecar(target: str) -> str:
    return f"{target}.elysia-provenance.json"


def _guard_target(root: str, target: str, suffix: str) -> tuple[Path | None, str | None, str | None]:
    guarded = guard_workspace_path(workspace_root=root, target_path=target, require_existing=False, allow_directory=False)
    if not guarded.allowed or not guarded.target_path or not guarded.relative_path:
        return None, None, guarded.reason or "artifact_target_not_allowed"
    if guarded.target_path.suffix.lower() != suffix:
        return None, guarded.relative_path, "artifact_target_suffix_mismatch"
    if guarded.target_path.exists():
        return None, guarded.relative_path, "artifact_target_exists"
    return guarded.target_path, guarded.relative_path, None


def _prompt_block_reason(payload: VideoForgePlanRequest) -> str | None:
    if payload.contains_real_person_request:
        return "real_person_likeness_unavailable"
    lowered = f"{payload.prompt} {payload.negative_prompt}".casefold()
    if any(marker in lowered for marker in BLOCKED_PROMPT_MARKERS):
        return "videoforge_prompt_policy_blocked"
    return None


def plan_video(payload: VideoForgePlanRequest) -> VideoForgePlanResult:
    prompt_hash = _hash_text(payload.prompt)
    model = raw_model_entry("videoforge", payload.model_id)
    model_state = str((model or {}).get("enabled_state") or "unknown")
    base = dict(
        status="blocked",
        model_id=payload.model_id,
        model_state=model_state,
        prompt_hash=prompt_hash,
        prompt_length=len(payload.prompt),
        purpose_category=payload.purpose_category,
        width=payload.width,
        height=payload.height,
        frames=payload.frames,
        fps=payload.fps,
        steps=payload.steps,
        seed=payload.seed,
        synthetic_media=True,
        production_enabled=False,
        approval_required=True,
        cancellation_supported=True,
        warnings=[
            "VideoForge is lab-only and disabled by default; no video model is production-enabled.",
            "The prompt and video bytes are excluded from central audit/request trace.",
            "Generated output is synthetic and is not a recording of real events.",
        ],
    )
    root_guard = guard_workspace_path(workspace_root=payload.workspace_root, target_path=".", require_existing=True, allow_directory=True)
    if not root_guard.allowed:
        return VideoForgePlanResult(**base, blocked_reason=root_guard.reason)
    if model is None:
        return VideoForgePlanResult(**base, blocked_reason="unknown_videoforge_model")
    if model_state != "lab_only":
        return VideoForgePlanResult(**base, blocked_reason="videoforge_model_not_lab_enabled")
    if not payload.lab_acknowledged:
        return VideoForgePlanResult(**base, blocked_reason="videoforge_lab_acknowledgement_required")
    if os.environ.get("ELYSIA_VIDEOFORGE_LAB_ENABLED") != "1":
        return VideoForgePlanResult(**{**base, "status": "lab_only_disabled"}, blocked_reason="videoforge_lab_not_enabled")
    if not payload.approval_granted:
        return VideoForgePlanResult(**{**base, "status": "approval_required"}, blocked_reason="explicit_approval_required")
    prompt_reason = _prompt_block_reason(payload)
    if prompt_reason:
        return VideoForgePlanResult(**base, blocked_reason=prompt_reason)
    target = payload.target_path or _default_target(prompt_hash)
    target_path, target_relative, target_error = _guard_target(payload.workspace_root, target, ".mp4")
    if target_error or target_path is None or target_relative is None:
        return VideoForgePlanResult(**base, blocked_reason=target_error)
    sidecar_relative = _sidecar(target_relative)
    sidecar_path, _, sidecar_error = _guard_target(payload.workspace_root, sidecar_relative, ".json")
    if sidecar_error or sidecar_path is None:
        return VideoForgePlanResult(**base, blocked_reason=sidecar_error)
    plan_hash = _plan_hash({
        "operation": "videoforge_generate",
        "model_id": payload.model_id,
        "prompt_hash": prompt_hash,
        "prompt_length": len(payload.prompt),
        "negative_prompt_hash": _hash_text(payload.negative_prompt),
        "purpose_category": payload.purpose_category,
        "width": payload.width,
        "height": payload.height,
        "frames": payload.frames,
        "fps": payload.fps,
        "steps": payload.steps,
        "seed": payload.seed,
        "target": target_relative,
        "sidecar": sidecar_relative,
        "lab_acknowledged": payload.lab_acknowledged,
    })
    return VideoForgePlanResult(
        **{**base, "status": "planned"},
        target_relative_path=target_relative,
        sidecar_relative_path=sidecar_relative,
        plan_hash=plan_hash,
        blocked_reason=None,
    )


def _copy_job(operation_id: str) -> VideoForgeJobResult | None:
    with _JOB_LOCK:
        job = _JOBS.get(operation_id)
        return job.model_copy(deep=True) if job else None


def get_video_job(operation_id: str) -> VideoForgeJobResult | None:
    return _copy_job(operation_id)


def _store_job(result: VideoForgeJobResult) -> None:
    with _JOB_LOCK:
        _JOBS[result.operation_id] = result.model_copy(deep=True)


def _job_busy() -> bool:
    return any(job.status in {"reserving", "queued", "running", "cancel_requested"} for job in _JOBS.values())


def apply_video(payload: VideoForgeApplyRequest) -> VideoForgeJobResult:
    plan_request = VideoForgePlanRequest(**payload.model_dump(exclude={"expected_prompt_hash", "expected_plan_hash", "approval_id", "approval_token"}))
    plan = plan_video(plan_request)
    operation_id = f"videoforge_{uuid4().hex[:16]}"
    result = VideoForgeJobResult(
        **plan.model_dump(),
        operation_id=operation_id,
        request_id=coding_request_id(operation_id, payload.approval_id),
        approval_id=payload.approval_id,
        workspace_root_hash=hash_path(payload.workspace_root),
    )
    if plan.status != "planned" or plan.prompt_hash != payload.expected_prompt_hash or plan.plan_hash != payload.expected_plan_hash:
        result.status = "blocked"
        result.blocked_reason = "videoforge_plan_or_prompt_hash_mismatch"
        _audit(payload.session_id, result)
        return result
    assert plan.target_relative_path and plan.sidecar_relative_path
    with _JOB_LOCK:
        if _job_busy():
            result.status = "blocked"
            result.blocked_reason = "videoforge_worker_busy"
            _JOBS[operation_id] = result.model_copy(deep=True)
            busy = True
        else:
            result.status = "reserving"
            _JOBS[operation_id] = result.model_copy(deep=True)
            busy = False
    if busy:
        _audit(payload.session_id, result)
        return result
    approval = consume_operation_approval(
        approval_id=payload.approval_id,
        approval_token=payload.approval_token,
        operation_kind="videoforge_generate",
        workspace_root=payload.workspace_root,
        exact_files=[plan.target_relative_path, plan.sidecar_relative_path],
        source_hash=plan.prompt_hash,
        plan_hash=plan.plan_hash or "",
        allowed_mutation_class="artifact_generation",
    )
    if not approval.allowed:
        result.status = "blocked"
        result.blocked_reason = approval.reason or "approval_denied"
        _audit(payload.session_id, result)
        _store_job(result)
        return result
    target = guard_workspace_path(workspace_root=payload.workspace_root, target_path=plan.target_relative_path, require_existing=False, allow_directory=False).target_path
    sidecar = guard_workspace_path(workspace_root=payload.workspace_root, target_path=plan.sidecar_relative_path, require_existing=False, allow_directory=False).target_path
    if not target or not sidecar or target.exists() or sidecar.exists():
        result.status = "blocked"
        result.blocked_reason = "artifact_target_changed_after_approval"
        _audit(payload.session_id, result)
        _store_job(result)
        return result

    result.status = "queued"
    result.blocked_reason = None
    cancel_event = threading.Event()
    _store_job(result)
    with _JOB_LOCK:
        _CANCEL_EVENTS[operation_id] = cancel_event
    result.audit_written = _audit(payload.session_id, result)
    _store_job(result)
    thread = threading.Thread(
        target=_run_video_job,
        args=(plan_request, plan, operation_id, result.request_id, payload.approval_id, result.workspace_root_hash, cancel_event),
        daemon=True,
        name=f"elysia-{operation_id}",
    )
    with _JOB_LOCK:
        _THREADS[operation_id] = thread
    thread.start()
    return result.model_copy(deep=True)


def _run_video_job(
    payload: VideoForgePlanRequest,
    plan: VideoForgePlanResult,
    operation_id: str,
    request_id: str | None,
    approval_id: str,
    workspace_root_hash: str | None,
    cancel_event: threading.Event,
) -> None:
    result = VideoForgeJobResult(
        **{**plan.model_dump(), "status": "running", "blocked_reason": None},
        operation_id=operation_id,
        request_id=request_id,
        approval_id=approval_id,
        workspace_root_hash=workspace_root_hash,
    )
    _store_job(result)
    target = guard_workspace_path(workspace_root=payload.workspace_root, target_path=plan.target_relative_path or "", require_existing=False, allow_directory=False).target_path
    sidecar = guard_workspace_path(workspace_root=payload.workspace_root, target_path=plan.sidecar_relative_path or "", require_existing=False, allow_directory=False).target_path
    try:
        if not target or not sidecar or target.exists() or sidecar.exists():
            raise ValueError("artifact_target_changed_after_approval")
        with execute_media_worker(
            "videoforge_worker",
            {
                "kind": "video",
                "model_id": payload.model_id,
                "prompt": payload.prompt,
                "negative_prompt": payload.negative_prompt,
                "contains_real_person_request": payload.contains_real_person_request,
                "width": payload.width,
                "height": payload.height,
                "frames": payload.frames,
                "fps": payload.fps,
                "steps": payload.steps,
                "seed": payload.seed,
                "output_name": "worker-output.mp4",
            },
            cancel_event=cancel_event,
        ) as worker:
            if worker.get("status") == "cancelled" or cancel_event.is_set():
                result.status = "cancelled"
                result.cancel_requested = True
                result.blocked_reason = "operator_cancelled"
                return
            if worker.get("status") != "completed":
                result.status = str(worker.get("status") or "failed")
                result.blocked_reason = str(worker.get("blocked_reason") or "videoforge_worker_failed")
                return
            worker_output = Path(str(worker.get("output_path") or ""))
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as destination, worker_output.open("rb") as source_stream:
                shutil.copyfileobj(source_stream, destination, length=1024 * 1024)
            if cancel_event.is_set():
                target.unlink(missing_ok=True)
                result.status = "cancelled"
                result.cancel_requested = True
                result.blocked_reason = "operator_cancelled"
                return
            output_hash = _sha_file(target)
            if output_hash != worker.get("output_sha256"):
                raise ValueError("worker_output_hash_mismatch")
            artifact_id = create_artifact_id("artifact_video")
            sidecar_payload = {
                "artifact_id": artifact_id,
                "artifact_kind": "generated_video",
                "synthetic_media": True,
                "not_a_recording_of_real_events": True,
                "local_only": True,
                "network_used": False,
                "cloud_used": False,
                "model_id": payload.model_id,
                "model_state": "lab_only",
                "prompt_sha256": plan.prompt_hash,
                "prompt_length": plan.prompt_length,
                "negative_prompt_sha256": _hash_text(payload.negative_prompt),
                "purpose_category": payload.purpose_category,
                "output_sha256": output_hash,
                "settings": {
                    "width": payload.width,
                    "height": payload.height,
                    "frames": payload.frames,
                    "fps": payload.fps,
                    "steps": payload.steps,
                    "seed": payload.seed,
                },
                "runtime_seconds": worker.get("runtime_seconds"),
                "peak_gpu_memory_mib": worker.get("peak_gpu_memory_mib"),
                "license_review_status": "verified_official_wan_ai_apache_2_0_2026_08_24",
                "provenance_status": "training_data_details_incomplete",
                "production_enabled": False,
            }
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            sidecar.write_text(json.dumps(sidecar_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            sidecar_hash = _sha_file(sidecar)
            receipt = build_generated_media_artifact_record({
                "status": "completed",
                "artifact_kind": "generated_video",
                "model_id": payload.model_id,
                "worker_key": "videoforge_worker",
                "mime_type": "video/mp4",
                "output_path": str(target),
                "output_sha256": output_hash,
                "output_bytes": target.stat().st_size,
                "sidecar_path": str(sidecar),
                "sidecar_sha256": sidecar_hash,
                "synthetic_media": True,
                "duration_seconds": worker.get("duration_seconds"),
                "width": payload.width,
                "height": payload.height,
                "prompt_or_text_hash": plan.prompt_hash,
                "prompt_or_text_length": plan.prompt_length,
                "provenance_state": "license_verified_training_data_details_incomplete",
                "operation": "videoforge_generate",
                "title": "Lab-only generated video",
                "summary": "Local synthetic video; prompt and video bytes excluded from central trace.",
            }, request_id=request_id, artifact_id=artifact_id)
            save_artifact_record(receipt)
            result.status = "completed"
            result.blocked_reason = None
            result.artifact_id = artifact_id
            result.output_sha256 = output_hash
            result.sidecar_sha256 = sidecar_hash
            result.output_bytes = target.stat().st_size
            result.duration_seconds = float(worker.get("duration_seconds") or 0.0) or None
            result.runtime_seconds = float(worker.get("runtime_seconds") or 0.0) or None
            result.peak_gpu_memory_mib = float(worker.get("peak_gpu_memory_mib") or 0.0) or None
    except Exception as exc:
        if target:
            target.unlink(missing_ok=True)
        if sidecar:
            sidecar.unlink(missing_ok=True)
        result.status = "failed"
        reason = str(exc)
        result.blocked_reason = reason if reason in {
            "artifact_target_changed_after_approval", "worker_output_hash_mismatch"
        } else f"video_artifact_failed:{type(exc).__name__}"
    finally:
        result.audit_written = _audit(payload.session_id, result)
        _store_job(result)
        with _JOB_LOCK:
            _CANCEL_EVENTS.pop(operation_id, None)
            _THREADS.pop(operation_id, None)


def cancel_video_job(operation_id: str) -> VideoForgeJobResult | None:
    with _JOB_LOCK:
        current = _JOBS.get(operation_id)
        if current is None:
            return None
        if current.status in TERMINAL_STATUSES:
            copy = current.model_copy(deep=True)
            copy.warnings.append("The job is already terminal and cannot be cancelled.")
            return copy
        event = _CANCEL_EVENTS.get(operation_id)
        if event is None:
            copy = current.model_copy(deep=True)
            copy.status = "failed"
            copy.blocked_reason = "videoforge_cancel_state_missing"
            return copy
        event.set()
        current.status = "cancel_requested"
        current.cancel_requested = True
        _JOBS[operation_id] = current.model_copy(deep=True)
        return current.model_copy(deep=True)


def cancel_all_video_jobs() -> int:
    with _JOB_LOCK:
        operation_ids = [
            operation_id for operation_id, result in _JOBS.items()
            if result.status not in TERMINAL_STATUSES
        ]
    return sum(cancel_video_job(operation_id) is not None for operation_id in operation_ids)


def _audit(session_id: str | None, result: VideoForgeJobResult) -> bool:
    audit_payload = {
        "session_id": session_id,
        "operation_kind": "videoforge_generate",
        "status": result.status,
        "workspace_root_hash": result.workspace_root_hash,
        "target_relative_path": result.target_relative_path,
        "source_hash": result.prompt_hash,
        "plan_hash": result.plan_hash,
        "result_hash": result.output_sha256,
        "approval_id": result.approval_id,
        "approval_required": True,
        "operator_approved": bool(result.approval_id),
        "allowed_mutation_class": "artifact_generation",
        "artifact_id": result.artifact_id,
        "model_id": result.model_id,
        "prompt_length": result.prompt_length,
        "synthetic_media": True,
        "production_enabled": False,
        "raw_content_logged": False,
        "duration_seconds": result.duration_seconds,
        "runtime_seconds": result.runtime_seconds,
        "peak_gpu_memory_mib": result.peak_gpu_memory_mib,
        "cancel_requested": result.cancel_requested,
        "network": False,
        "shell": False,
        "mutation_performed": result.status == "completed",
    }
    try:
        return write_coding_audit_record("videoforge_generate", result.operation_id, audit_payload)
    except OSError:
        result.warnings.append("Compact VideoForge audit could not be persisted.")
        return False


def clear_video_jobs_for_tests() -> None:
    with _JOB_LOCK:
        for event in _CANCEL_EVENTS.values():
            event.set()
        threads = list(_THREADS.values())
    for thread in threads:
        thread.join(timeout=2)
    with _JOB_LOCK:
        _JOBS.clear()
        _CANCEL_EVENTS.clear()
        _THREADS.clear()


__all__ = (
    "apply_video",
    "cancel_all_video_jobs",
    "cancel_video_job",
    "clear_video_jobs_for_tests",
    "get_video_job",
    "plan_video",
)
