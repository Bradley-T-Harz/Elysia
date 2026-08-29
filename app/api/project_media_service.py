"""Project-owned orchestration for governed ImageForge and SpeechForge output.

The Desktop supplies intent and explicit operator confirmation. This service
owns private XDG paths and exact one-time approvals so raw local paths and
approval tokens never cross into the webview response.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api import imageforge_service, project_service, speechforge_service
from app.api.coding_operation_service import approve_operation
from app.api.schemas.coding_operations import CodingOperationApproveRequest
from app.api.schemas.media_workers import (
    ImageForgeApplyRequest,
    ImageForgePlanRequest,
    SpeechTtsApplyRequest,
    SpeechTtsPlanRequest,
)
from app.install.paths import resolve_elysia_paths
from app.ownership import current_user_id


class ProjectMediaError(RuntimeError):
    """A Project media request could not be completed safely."""


class ProjectImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    prompt: str = Field(min_length=1, max_length=1200)
    seed: int = Field(default=5, ge=0, le=2_147_483_647)
    operator_approved: bool = False
    contains_real_person_request: bool = False


class ProjectSpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=4000)
    voice_id: str = Field(default="af_sarah", min_length=1, max_length=80)
    speed: float = Field(default=1.0, ge=0.75, le=1.25)
    operator_approved: bool = False


class ProjectImageEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_path: str = Field(min_length=1, max_length=4096)
    operator_approved: bool = False


_EDITABLE_IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
_MAX_EDITABLE_IMAGE_BYTES = 64 * 1024 * 1024


def _owner_and_project(project_id: str) -> str:
    owner = current_user_id()
    if not owner:
        raise ProjectMediaError("An authenticated local account is required.")
    metadata = project_service.get_project_metadata(project_id)
    if metadata.get("owner_user_id") and metadata.get("owner_user_id") != owner:
        raise ProjectMediaError("The project belongs to another local account.")
    return owner


def _workspace(project_id: str, owner: str) -> Path:
    owner_hash = hashlib.sha256(owner.encode("utf-8")).hexdigest()[:24]
    root = resolve_elysia_paths().data_dir / "project-artifacts" / owner_hash / project_id
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    return root


def _approval(
    *,
    workspace: Path,
    operation_kind: str,
    exact_files: list[str],
    source_hash: str,
    plan_hash: str,
    summary: str,
) -> tuple[str, str]:
    result = approve_operation(
        CodingOperationApproveRequest(
            operation_kind=operation_kind,
            operation_summary=summary,
            workspace_root=str(workspace),
            exact_files=exact_files,
            source_hash=source_hash,
            plan_hash=plan_hash,
            allowed_mutation_class="artifact_generation",
            expires_in_seconds=300,
            operator_approved=True,
            approval_phrase="Approved in Elysia Project workbench",
            rollback_note="The exact derived artifact and provenance sidecar may be removed without changing the project source.",
        )
    )
    if result.status != "approved" or not result.approval_token:
        raise ProjectMediaError("Exact local artifact approval could not be issued.")
    return result.approval_id, result.approval_token


def _public_media(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    for key in ("approval_id", "approval_token", "workspace_root", "target_path"):
        result.pop(key, None)
    return result


def _gimp_binary() -> str | None:
    for candidate in ("gimp", "gimp-3.0", "gimp-2.10"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def gimp_status(project_id: str) -> dict[str, Any]:
    _owner_and_project(project_id)
    binary = _gimp_binary()
    return {
        "available": bool(binary),
        "display_available": bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
        "provider": "local_gimp",
        "network_required": False,
        "source_mutation": False,
        "working_copy_only": True,
    }


def open_project_image_in_gimp(project_id: str, request: ProjectImageEditRequest) -> dict[str, Any]:
    """Open an exact private working copy in GIMP through a fixed argv."""

    owner = _owner_and_project(project_id)
    if not request.operator_approved:
        raise ProjectMediaError("Opening a local image editor requires explicit operator confirmation.")
    binary = _gimp_binary()
    if not binary:
        raise ProjectMediaError("GIMP is not installed; install the optional local creative dependency first.")
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise ProjectMediaError("A graphical desktop session is required to open GIMP.")
    source = Path(request.source_path).expanduser()
    try:
        if source.is_symlink() or not source.is_file():
            raise ProjectMediaError("Select a regular non-symlink image file.")
        source = source.resolve(strict=True)
        size = source.stat().st_size
    except OSError as exc:
        raise ProjectMediaError("The selected image could not be inspected.") from exc
    if source.suffix.casefold() not in _EDITABLE_IMAGE_SUFFIXES:
        raise ProjectMediaError("The selected file is not a supported image format.")
    if size <= 0 or size > _MAX_EDITABLE_IMAGE_BYTES:
        raise ProjectMediaError("The selected image is empty or exceeds the 64 MiB local editing limit.")

    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    edit_root = _workspace(project_id, owner) / "image-edits"
    edit_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    edit_root.chmod(0o700)
    safe_stem = "".join(character for character in source.stem if character.isalnum() or character in "-_")[:80] or "image"
    target = edit_root / f"{safe_stem}_{source_hash[:12]}{source.suffix.casefold()}"
    if not target.exists():
        with source.open("rb") as input_stream, target.open("xb") as output_stream:
            shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
        target.chmod(0o600)
    elif hashlib.sha256(target.read_bytes()).hexdigest() != source_hash:
        raise ProjectMediaError("The existing private working copy no longer matches the selected source.")

    process = subprocess.Popen(
        [binary, str(target)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    return {
        "status": "launched",
        "provider": "local_gimp",
        "source_label": source.name,
        "source_sha256": source_hash,
        "working_copy_label": target.name,
        "working_copy_sha256": source_hash,
        "working_copy_private": True,
        "original_unchanged": True,
        "network_used": False,
        "process_started": process.pid > 0,
    }


def create_project_image(project_id: str, request: ProjectImageRequest) -> dict[str, Any]:
    owner = _owner_and_project(project_id)
    workspace = _workspace(project_id, owner)
    target = f"images/{hashlib.sha256((request.prompt + str(request.seed)).encode('utf-8')).hexdigest()[:12]}.png"
    plan_request = ImageForgePlanRequest(
        workspace_root=str(workspace),
        model_id="flux1-schnell",
        prompt=request.prompt,
        steps=1,
        seed=request.seed,
        target_path=target,
        approval_granted=request.operator_approved,
        contains_real_person_request=request.contains_real_person_request,
    )
    plan = imageforge_service.plan_image(plan_request)
    if not request.operator_approved or plan.status != "planned":
        return {"imageforge_plan": _public_media(plan.model_dump(mode="json")), "job_started": False}
    if not plan.plan_hash or not plan.target_relative_path or not plan.sidecar_relative_path:
        raise ProjectMediaError(plan.blocked_reason or "ImageForge did not return an exact plan.")
    approval_id, approval_token = _approval(
        workspace=workspace,
        operation_kind="imageforge_generate",
        exact_files=[plan.target_relative_path, plan.sidecar_relative_path],
        source_hash=plan.prompt_hash,
        plan_hash=plan.plan_hash,
        summary="Generate one approved local synthetic Project image",
    )
    job = imageforge_service.queue_image(
        ImageForgeApplyRequest(
            **plan_request.model_dump(),
            expected_prompt_hash=plan.prompt_hash,
            expected_plan_hash=plan.plan_hash,
            approval_id=approval_id,
            approval_token=approval_token,
        )
    )
    return {"imageforge_job": _public_media(job.model_dump(mode="json")), "job_started": job.status in {"queued", "running", "completed"}}


def project_image_job(project_id: str, operation_id: str) -> dict[str, Any]:
    _owner_and_project(project_id)
    result = imageforge_service.get_image_job(operation_id)
    if result is None:
        raise ProjectMediaError("ImageForge job was not found in the current local process.")
    return {"imageforge_job": _public_media(result.model_dump(mode="json"))}


def cancel_project_image(project_id: str, operation_id: str) -> dict[str, Any]:
    _owner_and_project(project_id)
    result = imageforge_service.cancel_image_job(operation_id)
    if result is None:
        raise ProjectMediaError("ImageForge job was not found in the current local process.")
    return {"imageforge_job": _public_media(result.model_dump(mode="json"))}


def speak_project_text(project_id: str, request: ProjectSpeechRequest) -> dict[str, Any]:
    owner = _owner_and_project(project_id)
    workspace = _workspace(project_id, owner)
    text_hash = hashlib.sha256(request.text.encode("utf-8")).hexdigest()
    plan_request = SpeechTtsPlanRequest(
        workspace_root=str(workspace),
        text=request.text,
        voice_id=request.voice_id,
        speed=request.speed,
        target_path=f"speech/tts_{text_hash[:12]}.wav",
        approval_granted=request.operator_approved,
        approval_reason="Operator approved local synthetic reading voice in Project workbench.",
        purpose_category="private_reading",
    )
    plan = speechforge_service.plan_tts(plan_request)
    if not request.operator_approved or plan.status != "planned":
        return {"tts_plan": _public_media(plan.model_dump(mode="json")), "completed": False}
    if not plan.plan_hash or not plan.target_relative_path or not plan.sidecar_relative_path:
        raise ProjectMediaError(plan.blocked_reason or "SpeechForge did not return an exact plan.")
    approval_id, approval_token = _approval(
        workspace=workspace,
        operation_kind="speech_tts",
        exact_files=[plan.target_relative_path, plan.sidecar_relative_path],
        source_hash=plan.text_hash,
        plan_hash=plan.plan_hash,
        summary="Create one approved local synthetic reading-voice artifact",
    )
    result = speechforge_service.apply_tts(
        SpeechTtsApplyRequest(
            **plan_request.model_dump(),
            expected_text_hash=plan.text_hash,
            expected_plan_hash=plan.plan_hash,
            approval_id=approval_id,
            approval_token=approval_token,
        )
    )
    return {"tts_result": _public_media(result.model_dump(mode="json")), "completed": result.status == "completed"}


__all__ = (
    "ProjectImageRequest",
    "ProjectImageEditRequest",
    "ProjectMediaError",
    "ProjectSpeechRequest",
    "cancel_project_image",
    "create_project_image",
    "project_image_job",
    "gimp_status",
    "open_project_image_in_gimp",
    "speak_project_text",
)
