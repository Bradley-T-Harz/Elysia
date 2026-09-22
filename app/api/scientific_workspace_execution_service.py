"""Authority-preserving bridge from approved science workspaces to ScientificForge.

Workspace paths never enter ScientificForge directly. An exact approved regular
CSV source is resolved through scientific workspace authority, staged through
the existing Elysia ingest authority with project scope, then executed through
the existing account-bound ScientificForge source resolver.
"""

from __future__ import annotations

from app.api.file_ingest_service import attach_file
from app.cognition.emergency_control import emergency_active
from app.api.scientific_workspace_service import (
    ScientificWorkspaceError,
    resolve_scientific_workspace_source,
)
from app.api.scientificforge_service import (
    run_scientific_execution,
)
from app.api.schemas.scientific_workspace import (
    ScientificWorkspaceExecutionRequest,
    ScientificWorkspaceExecutionResult,
)


_SOURCE_OPERATIONS = {
    "descriptive_stats",
    "correlation_matrix",
    "bootstrap_mean_ci",
}

_ALLOWED_STAGING_TYPES = {
    "csv_table",
}


def run_scientific_workspace_execution(
    request: ScientificWorkspaceExecutionRequest | dict,
) -> ScientificWorkspaceExecutionResult:
    request_model = (
        request
        if isinstance(
            request,
            ScientificWorkspaceExecutionRequest,
        )
        else ScientificWorkspaceExecutionRequest(
            **dict(request)
        )
    )

    operation = request_model.operation.strip()

    if emergency_active():
        return ScientificWorkspaceExecutionResult(
            status="blocked",
            project_id=request_model.project_id,
            workspace_root_hash="unknown",
            relative_path=request_model.relative_path,
            source_type_id="unknown",
            source_category="unknown",
            scientific_operation=operation,
            errors=[
                "emergency_stop_active"
            ],
        )

    try:
        source = resolve_scientific_workspace_source(
            project_id=request_model.project_id,
            workspace_root=request_model.workspace_root,
            relative_path=request_model.relative_path,
        )
    except ScientificWorkspaceError as exc:
        return ScientificWorkspaceExecutionResult(
            status="blocked",
            project_id=request_model.project_id,
            workspace_root_hash="unknown",
            relative_path=request_model.relative_path,
            source_type_id="unknown",
            source_category="unknown",
            scientific_operation=operation,
            errors=[str(exc)],
        )

    base = {
        "project_id": request_model.project_id,
        "workspace_root_hash": source.workspace_root_hash,
        "relative_path": source.relative_path,
        "source_type_id": source.type_id,
        "source_category": source.category,
        "scientific_operation": operation,
    }

    if operation not in _SOURCE_OPERATIONS:
        return ScientificWorkspaceExecutionResult(
            status="blocked",
            **base,
            errors=[
                "scientific_workspace_operation_not_source_backed"
            ],
        )

    if source.type_id not in _ALLOWED_STAGING_TYPES:
        return ScientificWorkspaceExecutionResult(
            status="blocked",
            **base,
            errors=[
                "scientific_workspace_source_not_supported_by_scientificforge_v0"
            ],
            warnings=[
                (
                    "The source may be supported by another governed science/data "
                    "adapter, but ScientificForge v0 source execution is currently "
                    "limited to explicitly staged tabular CSV."
                )
            ],
        )

    if emergency_active():
        return ScientificWorkspaceExecutionResult(
            status="blocked",
            **base,
            errors=[
                "emergency_stop_active"
            ],
        )

    ingest = attach_file(
        source.source_path,
        project_id=request_model.project_id,
        cancel_check=emergency_active,
    )

    if (
        not ingest.accepted
        or not ingest.ready
        or ingest.blocked
        or ingest.file is None
    ):
        return ScientificWorkspaceExecutionResult(
            status="blocked",
            **base,
            staged_file_id=ingest.file_id,
            errors=[
                *list(ingest.errors),
                "scientific_workspace_source_staging_failed",
            ],
        )

    staged_file_id = str(
        ingest.file_id or ""
    ).strip()

    attached_file_id = str(
        getattr(
            ingest.file,
            "file_id",
            "",
        )
        or ""
    ).strip()

    staged_project_id = str(
        getattr(
            ingest.file,
            "source_project_id",
            "",
        )
        or ""
    ).strip()

    if (
        not staged_file_id
        or attached_file_id != staged_file_id
    ):
        return ScientificWorkspaceExecutionResult(
            status="blocked",
            **base,
            staged_file_id=staged_file_id or None,
            errors=[
                "scientific_workspace_staged_file_identity_mismatch"
            ],
        )

    if (
        staged_project_id
        != request_model.project_id
    ):
        return ScientificWorkspaceExecutionResult(
            status="blocked",
            **base,
            staged_file_id=staged_file_id,
            errors=[
                "scientific_workspace_staged_project_scope_mismatch"
            ],
        )

    scientific_request: dict = {
        "operation": operation,
        "request_id": request_model.request_id,
        "source_file_id": staged_file_id,
        "columns": list(request_model.columns),
    }

    if operation == "bootstrap_mean_ci":
        scientific_request.update(
            seed=request_model.seed,
            bootstrap_samples=request_model.bootstrap_samples,
            confidence_level=request_model.confidence_level,
        )

    if emergency_active():
        return ScientificWorkspaceExecutionResult(
            status="blocked",
            **base,
            staged_file_id=staged_file_id,
            errors=[
                "emergency_stop_active"
            ],
        )

    result = run_scientific_execution(
        scientific_request
    )

    status = getattr(
        result.status,
        "value",
        result.status,
    )

    provenance = (
        result.provenance.model_dump(
            mode="json"
        )
        if result.provenance is not None
        else {}
    )

    return ScientificWorkspaceExecutionResult(
        status=str(status),
        ok=bool(result.ok),
        **base,
        staged_file_id=ingest.file_id,
        scientific_job_id=result.job_id,
        result=dict(result.result or {}),
        provenance=provenance,
        source_mutated=bool(
            result.source_mutated
        ),
        network_used=bool(
            result.network_access_used
        ),
        shell_used=bool(
            result.shell_used
        ),
        raw_absolute_path_exposed=False,
        warnings=list(
            result.warnings or []
        ),
        errors=list(
            result.errors or []
        ),
    )


__all__ = (
    "run_scientific_workspace_execution",
)
