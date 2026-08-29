"""Governed local ImageForge plans, cancellable jobs, and artifact receipts."""

from __future__ import annotations

import base64
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
from app.api.schemas.media_workers import ImageForgeApplyRequest, ImageForgePlanRequest, ImageForgePlanResult, ImageForgeResult


MAX_INLINE_IMAGE_BYTES = 2 * 1024 * 1024
BLOCKED_PROMPT_MARKERS = {
    "deepfake", "face swap", "faceswap", "nude", "sexual", "porn", "graphic violence",
    "political persuasion", "campaign propaganda", "celebrity", "public figure", "copyrighted character",
    "make it look like a real photograph of",
}
TERMINAL_STATUSES = {"completed", "cancelled", "failed", "blocked", "unavailable"}
_JOBS: dict[str, ImageForgeResult] = {}
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
    return f"elysia-artifacts/images/imageforge_{prompt_hash[:12]}.png"


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


def _prompt_block_reason(payload: ImageForgePlanRequest) -> str | None:
    if payload.contains_real_person_request:
        return "real_person_likeness_unavailable"
    lowered = f"{payload.prompt} {payload.negative_prompt}".casefold()
    if any(marker in lowered for marker in BLOCKED_PROMPT_MARKERS):
        return "image_prompt_policy_blocked"
    return None


def plan_image(payload: ImageForgePlanRequest) -> ImageForgePlanResult:
    prompt_hash = _hash_text(payload.prompt)
    model = raw_model_entry("imageforge", payload.model_id)
    model_state = str((model or {}).get("enabled_state") or "unknown")
    production_enabled = model_state == "profile_gated"
    base = dict(
        status="blocked", model_id=payload.model_id, model_state=model_state, prompt_hash=prompt_hash,
        prompt_length=len(payload.prompt), purpose_category=payload.purpose_category, width=payload.width,
        height=payload.height, steps=payload.steps, seed=payload.seed, synthetic_media=True,
        production_enabled=production_enabled, approval_required=True,
        warnings=[
            "ImageForge runs locally through the optional Creator profile; Core does not bundle model weights.",
            "Prompt text and image bytes are excluded from central audit/request trace.",
            "Generated output is synthetic and is not a recording of real events.",
        ],
    )
    root_guard = guard_workspace_path(workspace_root=payload.workspace_root, target_path=".", require_existing=True, allow_directory=True)
    if not root_guard.allowed:
        return ImageForgePlanResult(**base, blocked_reason=root_guard.reason)
    if model is None:
        return ImageForgePlanResult(**base, blocked_reason="unknown_imageforge_model")
    if model_state not in {"profile_gated", "lab_only"}:
        blockers = model.get("known_failure_modes") or [model_state]
        return ImageForgePlanResult(**base, blocked_reason=f"model_not_runnable:{','.join(str(item) for item in blockers)[:160]}")
    if model_state == "lab_only":
        if not payload.lab_acknowledged:
            return ImageForgePlanResult(**base, blocked_reason="imageforge_lab_acknowledgement_required")
        if os.environ.get("ELYSIA_IMAGEFORGE_LAB_ENABLED") != "1":
            return ImageForgePlanResult(**{**base, "status": "lab_only_disabled"}, blocked_reason="imageforge_lab_not_enabled")
    if not payload.approval_granted:
        return ImageForgePlanResult(**{**base, "status": "approval_required"}, blocked_reason="explicit_approval_required")
    prompt_reason = _prompt_block_reason(payload)
    if prompt_reason:
        return ImageForgePlanResult(**base, blocked_reason=prompt_reason)
    if payload.width != 256 or payload.height != 256 or not 1 <= payload.steps <= 12:
        return ImageForgePlanResult(**base, blocked_reason="imageforge_resource_profile_not_allowed")
    if payload.model_id == "flux1-schnell" and (payload.steps != 1 or bool(payload.negative_prompt)):
        return ImageForgePlanResult(**base, blocked_reason="imageforge_flux_sequential_profile_not_allowed")
    target = payload.target_path or _default_target(prompt_hash)
    target_path, target_relative, target_error = _guard_target(payload.workspace_root, target, ".png")
    if target_error or target_path is None or target_relative is None:
        return ImageForgePlanResult(**base, blocked_reason=target_error)
    sidecar_relative = _sidecar(target_relative)
    sidecar_path, _, sidecar_error = _guard_target(payload.workspace_root, sidecar_relative, ".json")
    if sidecar_error or sidecar_path is None:
        return ImageForgePlanResult(**base, blocked_reason=sidecar_error)
    plan_hash = _plan_hash({
        "operation": "imageforge_generate", "model_id": payload.model_id, "prompt_hash": prompt_hash,
        "prompt_length": len(payload.prompt), "negative_prompt_hash": _hash_text(payload.negative_prompt),
        "purpose_category": payload.purpose_category, "width": payload.width, "height": payload.height,
        "steps": payload.steps, "seed": payload.seed, "target": target_relative, "sidecar": sidecar_relative,
        "profile_gate": model_state,
    })
    return ImageForgePlanResult(
        **{**base, "status": "planned"}, target_relative_path=target_relative,
        sidecar_relative_path=sidecar_relative, plan_hash=plan_hash, blocked_reason=None,
    )


def apply_image(
    payload: ImageForgeApplyRequest,
    *,
    cancel_event: threading.Event | None = None,
    operation_id: str | None = None,
    request_id: str | None = None,
) -> ImageForgeResult:
    plan = plan_image(ImageForgePlanRequest(**payload.model_dump(exclude={"expected_prompt_hash", "expected_plan_hash", "approval_id", "approval_token"})))
    operation_id = operation_id or f"imageforge_{uuid4().hex[:16]}"
    result = ImageForgeResult(
        **plan.model_dump(),
        operation_id=operation_id,
        request_id=request_id or coding_request_id(operation_id, payload.approval_id),
        approval_id=payload.approval_id,
    )
    if plan.status != "planned" or plan.prompt_hash != payload.expected_prompt_hash or plan.plan_hash != payload.expected_plan_hash:
        result.status = "blocked"
        result.blocked_reason = "imageforge_plan_or_prompt_hash_mismatch"
        _audit(payload, result)
        return result
    assert plan.target_relative_path and plan.sidecar_relative_path
    approval = consume_operation_approval(
        approval_id=payload.approval_id, approval_token=payload.approval_token,
        operation_kind="imageforge_generate", workspace_root=payload.workspace_root,
        exact_files=[plan.target_relative_path, plan.sidecar_relative_path], source_hash=plan.prompt_hash,
        plan_hash=plan.plan_hash or "", allowed_mutation_class="artifact_generation",
    )
    if not approval.allowed:
        result.status = "blocked"
        result.blocked_reason = approval.reason or "approval_denied"
        _audit(payload, result)
        return result
    target = guard_workspace_path(workspace_root=payload.workspace_root, target_path=plan.target_relative_path, require_existing=False, allow_directory=False).target_path
    sidecar = guard_workspace_path(workspace_root=payload.workspace_root, target_path=plan.sidecar_relative_path, require_existing=False, allow_directory=False).target_path
    if not target or not sidecar or target.exists() or sidecar.exists():
        result.status = "blocked"
        result.blocked_reason = "artifact_target_changed_after_approval"
        _audit(payload, result)
        return result
    artifact_id = create_artifact_id("artifact_image")
    try:
        with execute_media_worker("imageforge_worker", {
            "kind": "image", "model_id": payload.model_id, "prompt": payload.prompt,
            "negative_prompt": payload.negative_prompt, "contains_real_person_request": payload.contains_real_person_request,
            "width": payload.width, "height": payload.height, "steps": payload.steps, "seed": payload.seed,
            "output_name": "worker-output.png",
        }, cancel_event=cancel_event) as worker:
            if worker.get("status") == "cancelled" or (cancel_event and cancel_event.is_set()):
                result.status = "cancelled"
                result.cancel_requested = True
                result.blocked_reason = "operator_cancelled"
                _audit(payload, result)
                return result
            if worker.get("status") != "completed":
                result.status = str(worker.get("status") or "failed")
                result.blocked_reason = str(worker.get("blocked_reason") or "imageforge_worker_failed")
                _audit(payload, result)
                return result
            worker_output = Path(str(worker.get("output_path") or ""))
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as destination, worker_output.open("rb") as source_stream:
                shutil.copyfileobj(source_stream, destination, length=1024 * 1024)
            if cancel_event and cancel_event.is_set():
                target.unlink(missing_ok=True)
                result.status = "cancelled"
                result.cancel_requested = True
                result.blocked_reason = "operator_cancelled"
                _audit(payload, result)
                return result
            output_hash = _sha_file(target)
            if output_hash != worker.get("output_sha256"):
                raise ValueError("worker_output_hash_mismatch")
            model_truth = raw_model_entry("imageforge", payload.model_id) or {}
            sidecar_payload = {
                "artifact_id": artifact_id, "artifact_kind": "generated_image", "synthetic_media": True,
                "not_a_recording_of_real_events": True, "local_only": True, "network_used": False, "cloud_used": False,
                "model_id": payload.model_id, "model_state": plan.model_state, "prompt_sha256": plan.prompt_hash,
                "prompt_length": plan.prompt_length, "negative_prompt_sha256": _hash_text(payload.negative_prompt),
                "purpose_category": payload.purpose_category, "output_sha256": output_hash,
                "settings": {"width": payload.width, "height": payload.height, "steps": payload.steps, "seed": payload.seed},
                "license_review_status": model_truth.get("license_review_status", "unverified"),
                "provenance_status": model_truth.get("training_data_provenance", "unverified"),
                "resource_profile": model_truth.get("resource_profile", "bounded_256_profile"),
                "production_enabled": plan.production_enabled,
            }
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            sidecar.write_text(json.dumps(sidecar_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            sidecar_hash = _sha_file(sidecar)
            receipt = build_generated_media_artifact_record({
                "status": "completed", "artifact_kind": "generated_image", "model_id": payload.model_id,
                "worker_key": "imageforge_worker", "mime_type": "image/png", "output_path": str(target),
                "output_sha256": output_hash, "output_bytes": target.stat().st_size, "sidecar_path": str(sidecar),
                "sidecar_sha256": sidecar_hash, "synthetic_media": True, "width": payload.width, "height": payload.height,
                "prompt_or_text_hash": plan.prompt_hash, "prompt_or_text_length": plan.prompt_length,
                "provenance_state": f"{model_truth.get('gate_status', 'blocked')}_local_synthetic_media", "operation": "imageforge_generate",
                "title": "Locally generated synthetic image", "summary": "Local synthetic image; prompt and image bytes excluded from central trace.",
            }, request_id=result.request_id, artifact_id=artifact_id)
            save_artifact_record(receipt)
            result.status = "completed"
            result.blocked_reason = None
            result.artifact_id = artifact_id
            result.output_sha256 = output_hash
            result.sidecar_sha256 = sidecar_hash
            result.output_bytes = target.stat().st_size
            result.runtime_seconds = float(worker.get("runtime_seconds") or 0.0) or None
            result.peak_gpu_memory_mib = float(worker.get("peak_gpu_memory_mib") or 0.0) or None
            if target.stat().st_size <= MAX_INLINE_IMAGE_BYTES:
                result.image_data_url = "data:image/png;base64," + base64.b64encode(target.read_bytes()).decode("ascii")
    except Exception as exc:
        target.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)
        result.status = "failed"
        result.blocked_reason = f"image_artifact_failed:{type(exc).__name__}"
    _audit(payload, result)
    return result


def _copy_job(operation_id: str) -> ImageForgeResult | None:
    with _JOB_LOCK:
        job = _JOBS.get(operation_id)
        return job.model_copy(deep=True) if job else None


def get_image_job(operation_id: str) -> ImageForgeResult | None:
    return _copy_job(operation_id)


def _store_job(result: ImageForgeResult) -> None:
    if not result.operation_id:
        return
    with _JOB_LOCK:
        _JOBS[result.operation_id] = result.model_copy(deep=True)


def _job_busy() -> bool:
    return any(job.status in {"queued", "running", "cancel_requested"} for job in _JOBS.values())


def queue_image(payload: ImageForgeApplyRequest) -> ImageForgeResult:
    plan = plan_image(
        ImageForgePlanRequest(
            **payload.model_dump(
                exclude={"expected_prompt_hash", "expected_plan_hash", "approval_id", "approval_token"}
            )
        )
    )
    operation_id = f"imageforge_{uuid4().hex[:16]}"
    result = ImageForgeResult(
        **plan.model_dump(),
        operation_id=operation_id,
        request_id=coding_request_id(operation_id, payload.approval_id),
        approval_id=payload.approval_id,
    )
    if plan.status != "planned" or plan.prompt_hash != payload.expected_prompt_hash or plan.plan_hash != payload.expected_plan_hash:
        result.status = "blocked"
        result.blocked_reason = "imageforge_plan_or_prompt_hash_mismatch"
        _audit(payload, result)
        _store_job(result)
        return result
    with _JOB_LOCK:
        if _job_busy():
            result.status = "blocked"
            result.blocked_reason = "imageforge_worker_busy"
            _JOBS[operation_id] = result.model_copy(deep=True)
            return result
    cancel_event = threading.Event()
    result.status = "queued"
    result.blocked_reason = None
    _store_job(result)
    with _JOB_LOCK:
        _CANCEL_EVENTS[operation_id] = cancel_event
    thread = threading.Thread(
        target=_run_queued_image,
        args=(payload, operation_id, cancel_event),
        daemon=True,
        name=f"elysia-{operation_id}",
    )
    with _JOB_LOCK:
        _THREADS[operation_id] = thread
    thread.start()
    return result.model_copy(deep=True)


def _run_queued_image(
    payload: ImageForgeApplyRequest,
    operation_id: str,
    cancel_event: threading.Event,
) -> None:
    queued = get_image_job(operation_id)
    if queued is None:
        return
    queued.status = "running"
    _store_job(queued)
    result = apply_image(
        payload,
        cancel_event=cancel_event,
        operation_id=operation_id,
        request_id=queued.request_id,
    )
    _store_job(result)
    with _JOB_LOCK:
        _CANCEL_EVENTS.pop(operation_id, None)
        _THREADS.pop(operation_id, None)


def cancel_image_job(operation_id: str) -> ImageForgeResult | None:
    with _JOB_LOCK:
        result = _JOBS.get(operation_id)
        event = _CANCEL_EVENTS.get(operation_id)
        if result is None:
            return None
        if result.status in TERMINAL_STATUSES:
            return result.model_copy(deep=True)
        if event is not None:
            event.set()
        result.status = "cancel_requested"
        result.cancel_requested = True
        result.blocked_reason = "operator_cancel_requested"
        _JOBS[operation_id] = result.model_copy(deep=True)
        return result.model_copy(deep=True)


def cancel_all_image_jobs() -> int:
    with _JOB_LOCK:
        operation_ids = [
            operation_id for operation_id, result in _JOBS.items()
            if result.status not in TERMINAL_STATUSES
        ]
    return sum(cancel_image_job(operation_id) is not None for operation_id in operation_ids)


def _audit(payload: Any, result: ImageForgeResult) -> None:
    audit_payload = {
        "session_id": payload.session_id, "operation_kind": "imageforge_generate", "status": result.status,
        "workspace_root_hash": hash_path(payload.workspace_root), "target_relative_path": result.target_relative_path,
        "source_hash": result.prompt_hash, "plan_hash": result.plan_hash, "result_hash": result.output_sha256,
        "approval_id": payload.approval_id if hasattr(payload, "approval_id") else None, "approval_required": True,
        "operator_approved": payload.approval_granted, "allowed_mutation_class": "artifact_generation",
        "artifact_id": result.artifact_id, "model_id": result.model_id, "prompt_length": result.prompt_length,
        "synthetic_media": True, "production_enabled": result.production_enabled, "raw_content_logged": False,
        "network": False, "shell": False, "mutation_performed": result.status == "completed",
    }
    try:
        result.audit_written = write_coding_audit_record("imageforge_generate", result.operation_id or f"imageforge_{uuid4().hex[:8]}", audit_payload)
    except OSError:
        result.warnings.append("Compact ImageForge audit could not be persisted.")


__all__ = (
    "apply_image",
    "cancel_image_job",
    "cancel_all_image_jobs",
    "get_image_job",
    "plan_image",
    "queue_image",
)
