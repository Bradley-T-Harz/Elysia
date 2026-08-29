"""Authenticated local routes for restored Project workbench capabilities."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from app.api import project_capability_service as service
from app.api import project_media_service as media_service
from app.api import soundcloud_connector_service as soundcloud_service
from app.api.user_control_service import autonomy_level, current_user_controls
from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.ids import new_id


router = APIRouter(prefix="/projects", tags=["projects", "restored-capabilities"])
API_VERSION = "0.2.0"
CONTRACT_VERSION = "project-capability-workbench-1.0"


def _envelope(result_type: str, data: Any) -> dict[str, Any]:
    return build_response_envelope(
        status=EnvelopeStatus.OK,
        request_id=new_id("projectcap"),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.NOT_NEEDED,
        warnings=[],
        errors=[],
        trace_summary=TraceSummary(
            route_used=f"projects.capabilities.{result_type}",
            log_written=False,
            journal_written=result_type not in {"project_capability_workbench"},
        ),
        data=data,
    ).to_payload()


def _blocked(result_type: str, exc: Exception) -> dict[str, Any]:
    return build_response_envelope(
        status=EnvelopeStatus.BLOCKED,
        request_id=new_id("projectcap"),
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=ApprovalState.DENIED,
        warnings=[],
        errors=[str(exc)],
        trace_summary=TraceSummary(
            route_used=f"projects.capabilities.{result_type}",
            log_written=False,
            journal_written=False,
        ),
        data={"completed": False},
    ).to_payload()


def _run(result_type: str, operation) -> dict[str, Any]:
    try:
        return _envelope(result_type, operation())
    except (
        service.ProjectCapabilityError,
        media_service.ProjectMediaError,
        soundcloud_service.SoundCloudConnectorError,
        ValueError,
    ) as exc:
        return _blocked(result_type, exc)


@router.get("/{project_id}/workbench")
async def get_project_workbench(project_id: str) -> dict[str, Any]:
    return _run("project_capability_workbench", lambda: {"workbench": service.get_workbench(project_id)})


@router.post("/{project_id}/sources")
async def attach_project_source(
    project_id: str,
    payload: service.ProjectSourceAttachRequest = Body(...),
) -> dict[str, Any]:
    return _run("project_source_attachment", lambda: service.attach_project_source(project_id, payload))


@router.post("/{project_id}/study-plans")
async def create_project_study_plan(
    project_id: str,
    payload: service.StudyPlanRequest = Body(...),
) -> dict[str, Any]:
    return _run("project_study_plan", lambda: service.create_study_plan(project_id, payload))


@router.post("/{project_id}/study-plans/{study_plan_id}/modules/{module_id}/review")
async def review_project_study_module(
    project_id: str,
    study_plan_id: str,
    module_id: str,
    payload: service.StudyModuleReviewRequest = Body(...),
) -> dict[str, Any]:
    return _run(
        "project_study_review",
        lambda: service.review_study_module(project_id, study_plan_id, module_id, payload),
    )


@router.post("/{project_id}/research/iterations")
async def record_project_research_iteration(
    project_id: str,
    payload: service.ResearchIterationRequest = Body(...),
) -> dict[str, Any]:
    return _run(
        "project_research_iteration",
        lambda: service.record_research_iteration(project_id, payload),
    )


@router.post("/{project_id}/research/{investigation_id}/transition")
async def transition_project_research(
    project_id: str,
    investigation_id: str,
    payload: service.ResearchTransitionRequest = Body(...),
) -> dict[str, Any]:
    return _run(
        "project_research_transition",
        lambda: service.transition_research(project_id, investigation_id, payload),
    )


@router.post("/{project_id}/quizzes")
async def generate_project_quiz(
    project_id: str,
    payload: service.QuizGenerateRequest = Body(...),
) -> dict[str, Any]:
    return _run("project_quiz", lambda: service.generate_quiz(project_id, payload))


@router.post("/{project_id}/quizzes/{quiz_id}/answers")
async def answer_project_quiz(
    project_id: str,
    quiz_id: str,
    payload: service.QuizAnswerRequest = Body(...),
) -> dict[str, Any]:
    return _run("project_quiz_answer", lambda: service.answer_quiz(project_id, quiz_id, payload))


@router.post("/{project_id}/goals")
async def create_project_goal(
    project_id: str,
    payload: service.GoalCreateRequest = Body(...),
) -> dict[str, Any]:
    controls = current_user_controls()
    return _run(
        "project_goal",
        lambda: service.create_goal(
            project_id,
            payload,
            autonomy_level=autonomy_level(default=1),
            project_agent_limit=controls.project_agent_limit,
        ),
    )


@router.post("/{project_id}/goals/{goal_id}/transition")
async def transition_project_goal(
    project_id: str,
    goal_id: str,
    payload: service.GoalTransitionRequest = Body(...),
) -> dict[str, Any]:
    return _run("project_goal_transition", lambda: service.transition_goal(project_id, goal_id, payload))


@router.put("/{project_id}/canvas")
async def update_project_canvas(
    project_id: str,
    payload: service.CanvasUpdateRequest = Body(...),
) -> dict[str, Any]:
    return _run("project_canvas", lambda: service.update_canvas(project_id, payload))


@router.post("/{project_id}/images")
async def create_project_image(
    project_id: str,
    payload: media_service.ProjectImageRequest = Body(...),
) -> dict[str, Any]:
    return _run("project_image", lambda: media_service.create_project_image(project_id, payload))


@router.get("/{project_id}/images/jobs/{operation_id}")
async def get_project_image_job(project_id: str, operation_id: str) -> dict[str, Any]:
    return _run("project_image_job", lambda: media_service.project_image_job(project_id, operation_id))


@router.post("/{project_id}/images/jobs/{operation_id}/cancel")
async def cancel_project_image_job(project_id: str, operation_id: str) -> dict[str, Any]:
    return _run("project_image_job", lambda: media_service.cancel_project_image(project_id, operation_id))


@router.post("/{project_id}/speak")
async def speak_project_text(
    project_id: str,
    payload: media_service.ProjectSpeechRequest = Body(...),
) -> dict[str, Any]:
    return _run("project_speech", lambda: media_service.speak_project_text(project_id, payload))


@router.get("/{project_id}/creative/gimp")
async def get_project_gimp_status(project_id: str) -> dict[str, Any]:
    return _run("project_gimp_status", lambda: {"gimp": media_service.gimp_status(project_id)})


@router.post("/{project_id}/creative/gimp")
async def open_project_image_in_gimp(
    project_id: str,
    payload: media_service.ProjectImageEditRequest = Body(...),
) -> dict[str, Any]:
    return _run(
        "project_gimp_launch",
        lambda: {"gimp": media_service.open_project_image_in_gimp(project_id, payload)},
    )


def _with_project_access(project_id: str, operation):
    service.get_workbench(project_id)
    return operation()


@router.get("/{project_id}/connectors/soundcloud")
async def get_project_soundcloud_status(project_id: str) -> dict[str, Any]:
    return _run(
        "project_soundcloud_status",
        lambda: {"soundcloud": _with_project_access(project_id, soundcloud_service.status)},
    )


@router.post("/{project_id}/connectors/soundcloud/authorize")
async def begin_project_soundcloud_authorization(project_id: str) -> dict[str, Any]:
    return _run(
        "project_soundcloud_authorization",
        lambda: {"soundcloud": _with_project_access(project_id, soundcloud_service.begin_authorization)},
    )


@router.post("/{project_id}/connectors/soundcloud/complete")
async def complete_project_soundcloud_authorization(
    project_id: str,
    payload: soundcloud_service.SoundCloudCompleteRequest = Body(...),
) -> dict[str, Any]:
    return _run(
        "project_soundcloud_connection",
        lambda: {
            "soundcloud": _with_project_access(
                project_id,
                lambda: soundcloud_service.complete_authorization(payload),
            )
        },
    )


@router.post("/{project_id}/connectors/soundcloud/disconnect")
async def disconnect_project_soundcloud(project_id: str) -> dict[str, Any]:
    return _run(
        "project_soundcloud_disconnection",
        lambda: {"soundcloud": _with_project_access(project_id, soundcloud_service.disconnect)},
    )


@router.post("/{project_id}/connectors/soundcloud/verify")
async def verify_project_soundcloud_account(project_id: str) -> dict[str, Any]:
    return _run(
        "project_soundcloud_account_verification",
        lambda: {
            "soundcloud": _with_project_access(
                project_id,
                soundcloud_service.verify_connected_account,
            )
        },
    )


__all__ = ("router",)
