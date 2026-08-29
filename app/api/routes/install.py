"""Read-only lifecycle truth and authenticated local-client probe."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Request

from app.api.schemas.common import ApprovalState, CapabilityState, EnvelopeStatus, LocalityState
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.install.paths import resolve_elysia_paths
from app.install.component_graph_service import public_component_graph_summary
from app.install.component_install_service import (
    ComponentApplyRequest,
    ComponentCancelRequest,
    ComponentInstallError,
    ComponentInstallService,
    ComponentPreviewRequest,
)
from app.install.acquisition_service import public_acquisition_summary
from app.install.lifecycle_service import (
    LifecycleApplyRequest,
    LifecycleError,
    LifecyclePreviewRequest,
    LifecycleService,
)
from app.install.setup_service import (
    SetupApplyRequest,
    SetupError,
    SetupPreviewRequest,
    SetupService,
)
from app.install.system_prerequisite_service import (
    SystemPrerequisiteApplyRequest,
    SystemPrerequisiteError,
    SystemPrerequisitePreviewRequest,
    SystemPrerequisiteService,
)


API_VERSION = "1.0.0"
CONTRACT_VERSION = "elysia-local-lifecycle-1.0"

router = APIRouter(prefix="/install", tags=["install"])


def _envelope(
    *,
    result_type: str,
    route: str,
    data: dict[str, Any],
    status: EnvelopeStatus = EnvelopeStatus.OK,
    errors: list[str] | None = None,
    approval_state: ApprovalState = ApprovalState.NOT_NEEDED,
) -> dict[str, Any]:
    return build_response_envelope(
        status=status,
        request_id=f"req_install_{uuid4().hex[:16]}",
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE if status == EnvelopeStatus.OK else CapabilityState.DEGRADED,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=[],
        errors=errors or [],
        trace_summary=TraceSummary(route_used=route, log_written=False, journal_written=False),
        data=data,
    ).to_payload()


@router.get("/lifecycle")
async def get_lifecycle_status(request: Request) -> dict[str, Any]:
    paths = resolve_elysia_paths()
    auth = request.app.state.local_api_auth_policy
    launcher_present = (paths.data_dir / "runtime" / "bin" / "elysia-api").is_file()
    return _envelope(
        result_type="local_api_lifecycle",
        route="install.lifecycle",
        data={
            "runtime_mode": paths.mode.value,
            "strategy": (
                "tauri_fixed_user_launcher" if paths.mode.value == "packaged" else "explicit_source_runtime"
            ),
            "api_reachable": True,
            "fixed_launcher_present": launcher_present,
            "desktop_may_start_fixed_launcher": paths.mode.value == "packaged",
            "authentication": auth.public_summary(),
            "path_contract": paths.public_summary(),
            "install_authority_available": False,
            "service_mutation_available": False,
            "raw_paths_exposed": False,
        },
    )


@router.get("/component-graph")
async def get_component_graph() -> dict[str, Any]:
    """Return the validated authoritative graph without local paths or mutation authority."""
    return _envelope(
        result_type="component_profile_graph",
        route="install.component_graph",
        data=public_component_graph_summary(),
    )


@router.get("/acquisitions")
async def get_acquisitions() -> dict[str, Any]:
    """Return exact source/license/size/method truth without acquiring anything."""
    return _envelope(
        result_type="component_acquisition_manifests",
        route="install.acquisitions",
        data=public_acquisition_summary(),
    )


@router.get("/components")
async def get_component_install_state() -> dict[str, Any]:
    return _envelope(
        result_type="component_install_state",
        route="install.components",
        data=ComponentInstallService().state(),
    )


@router.post("/prerequisites/preview")
async def preview_system_prerequisites(
    payload: SystemPrerequisitePreviewRequest = Body(...),
) -> dict[str, Any]:
    try:
        data = SystemPrerequisiteService().preview(payload)
    except SystemPrerequisiteError as exc:
        return _envelope(
            result_type="system_prerequisite_preview",
            route="install.prerequisite_preview",
            data={"mutation_performed": False, "raw_paths_exposed": False},
            status=EnvelopeStatus.BLOCKED,
            errors=[str(exc)],
            approval_state=ApprovalState.NEEDED,
        )
    return _envelope(
        result_type="system_prerequisite_preview",
        route="install.prerequisite_preview",
        data=data,
        approval_state=ApprovalState.NEEDED,
    )


@router.post("/prerequisites/apply")
async def apply_system_prerequisites(
    payload: SystemPrerequisiteApplyRequest = Body(...),
) -> dict[str, Any]:
    try:
        data = SystemPrerequisiteService().apply(payload)
    except SystemPrerequisiteError as exc:
        return _envelope(
            result_type="system_prerequisite_apply",
            route="install.prerequisite_apply",
            data={"mutation_performed": False, "raw_paths_exposed": False},
            status=EnvelopeStatus.BLOCKED,
            errors=[str(exc)],
            approval_state=ApprovalState.NEEDED,
        )
    return _envelope(
        result_type="system_prerequisite_apply",
        route="install.prerequisite_apply",
        data=data,
        approval_state=ApprovalState.APPROVED,
    )


@router.post("/components/preview")
async def preview_component_operation(
    payload: ComponentPreviewRequest = Body(...),
) -> dict[str, Any]:
    try:
        data = ComponentInstallService().preview(payload)
    except ComponentInstallError as exc:
        return _envelope(
            result_type="component_install_preview",
            route="install.component_preview",
            data={"mutation_performed": False, "raw_paths_exposed": False},
            status=EnvelopeStatus.BLOCKED,
            errors=[str(exc)],
            approval_state=ApprovalState.NEEDED,
        )
    return _envelope(
        result_type="component_install_preview",
        route="install.component_preview",
        data=data,
        approval_state=ApprovalState.NEEDED,
    )


@router.post("/components/apply")
async def apply_component_operation(
    payload: ComponentApplyRequest = Body(...),
) -> dict[str, Any]:
    try:
        data = ComponentInstallService().apply(payload)
    except ComponentInstallError as exc:
        return _envelope(
            result_type="component_install_apply",
            route="install.component_apply",
            data={"mutation_performed": False, "raw_paths_exposed": False},
            status=EnvelopeStatus.BLOCKED,
            errors=[str(exc)],
            approval_state=ApprovalState.NEEDED,
        )
    return _envelope(
        result_type="component_install_apply",
        route="install.component_apply",
        data=data,
        approval_state=ApprovalState.APPROVED,
    )


@router.get("/components/jobs/{job_id}")
async def get_component_job(job_id: str) -> dict[str, Any]:
    try:
        data = ComponentInstallService().job(job_id)
    except ComponentInstallError as exc:
        return _envelope(
            result_type="component_install_job",
            route="install.component_job",
            data={"raw_paths_exposed": False},
            status=EnvelopeStatus.BLOCKED,
            errors=[str(exc)],
        )
    return _envelope(
        result_type="component_install_job",
        route="install.component_job",
        data=data,
    )


@router.post("/components/jobs/cancel")
async def cancel_component_job(
    payload: ComponentCancelRequest = Body(...),
) -> dict[str, Any]:
    try:
        data = ComponentInstallService().cancel(payload)
    except ComponentInstallError as exc:
        return _envelope(
            result_type="component_install_cancel",
            route="install.component_cancel",
            data={"cancellation_accepted": False, "raw_paths_exposed": False},
            status=EnvelopeStatus.BLOCKED,
            errors=[str(exc)],
            approval_state=ApprovalState.NEEDED,
        )
    return _envelope(
        result_type="component_install_cancel",
        route="install.component_cancel",
        data=data,
        approval_state=ApprovalState.APPROVED,
    )


@router.get("/lifecycle/state")
async def get_application_lifecycle_state() -> dict[str, Any]:
    return _envelope(
        result_type="application_lifecycle_state",
        route="install.lifecycle_state",
        data=LifecycleService().state(),
    )


@router.post("/lifecycle/preview")
async def preview_application_lifecycle(
    payload: LifecyclePreviewRequest = Body(...),
) -> dict[str, Any]:
    try:
        data = LifecycleService().preview(payload)
    except LifecycleError as exc:
        return _envelope(
            result_type="application_lifecycle_preview",
            route="install.lifecycle_preview",
            data={"mutation_performed": False, "raw_paths_exposed": False},
            status=EnvelopeStatus.BLOCKED,
            errors=[str(exc)],
            approval_state=ApprovalState.NEEDED,
        )
    return _envelope(
        result_type="application_lifecycle_preview",
        route="install.lifecycle_preview",
        data=data,
        approval_state=ApprovalState.NEEDED,
    )


@router.post("/lifecycle/apply")
async def apply_application_lifecycle(
    payload: LifecycleApplyRequest = Body(...),
) -> dict[str, Any]:
    try:
        data = LifecycleService().apply(payload)
    except LifecycleError as exc:
        return _envelope(
            result_type="application_lifecycle_apply",
            route="install.lifecycle_apply",
            data={"applied": False, "raw_paths_exposed": False},
            status=EnvelopeStatus.BLOCKED,
            errors=[str(exc)],
            approval_state=ApprovalState.NEEDED,
        )
    return _envelope(
        result_type="application_lifecycle_apply",
        route="install.lifecycle_apply",
        data=data,
        approval_state=ApprovalState.APPROVED,
    )


@router.get("/setup")
async def get_setup_state() -> dict[str, Any]:
    return _envelope(
        result_type="setup_state",
        route="install.setup_state",
        data=SetupService().state(),
    )


@router.post("/setup/preview")
async def preview_setup(payload: SetupPreviewRequest = Body(...)) -> dict[str, Any]:
    try:
        data = SetupService().preview(payload)
    except SetupError as exc:
        return _envelope(
            result_type="setup_preview",
            route="install.setup_preview",
            data={"mutation_performed": False, "raw_paths_exposed": False},
            status=EnvelopeStatus.BLOCKED,
            errors=[str(exc)],
            approval_state=ApprovalState.NEEDED,
        )
    return _envelope(
        result_type="setup_preview",
        route="install.setup_preview",
        data=data,
        approval_state=ApprovalState.NEEDED,
    )


@router.post("/setup/apply")
async def apply_setup(payload: SetupApplyRequest = Body(...)) -> dict[str, Any]:
    try:
        data = SetupService().apply(payload)
    except SetupError as exc:
        return _envelope(
            result_type="setup_apply",
            route="install.setup_apply",
            data={"mutation_performed": False, "raw_paths_exposed": False},
            status=EnvelopeStatus.BLOCKED,
            errors=[str(exc)],
            approval_state=ApprovalState.NEEDED,
        )
    return _envelope(
        result_type="setup_apply",
        route="install.setup_apply",
        data=data,
        approval_state=ApprovalState.APPROVED,
    )


@router.post("/setup/doctor")
async def run_setup_doctor() -> dict[str, Any]:
    """Execute the non-repairing selected-profile Doctor completion gate."""
    try:
        data = SetupService().run_final_doctor()
    except SetupError as exc:
        return _envelope(
            result_type="setup_doctor",
            route="install.setup_doctor",
            data={"doctor_report_recorded": True, "raw_paths_exposed": False},
            status=EnvelopeStatus.BLOCKED,
            errors=[str(exc)],
        )
    return _envelope(
        result_type="setup_doctor",
        route="install.setup_doctor",
        data=data,
    )


@router.post("/auth/probe")
async def probe_authenticated_local_client(request: Request) -> dict[str, Any]:
    auth = request.app.state.local_api_auth_policy
    return _envelope(
        result_type="local_client_auth_probe",
        route="install.auth_probe",
        data={
            "authenticated": auth.required,
            "authentication_required": auth.required,
            "credential_exposed": False,
            "mutation_performed": False,
        },
    )
