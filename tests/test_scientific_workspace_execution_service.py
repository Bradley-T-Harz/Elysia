from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import scientific_workspace_execution_service as execution
from app.api import scientific_workspace_service as workspace_service
from app.api.schemas.scientific_workspace import (
    ScientificWorkspaceApplyRequest,
    ScientificWorkspaceExecutionRequest,
    ScientificWorkspacePlanRequest,
)


class _Provenance:
    def model_dump(
        self,
        mode: str = "json",
    ):
        return {
            "protocol_version": "scientificforge-v0.1",
            "parameter_sha256": "p" * 64,
            "result_sha256": "r" * 64,
            "deterministic": True,
        }


@pytest.fixture(autouse=True)
def _clear_plans():
    workspace_service.clear_scientific_workspace_plans_for_tests()
    yield
    workspace_service.clear_scientific_workspace_plans_for_tests()


@pytest.fixture
def authority(tmp_path: Path, monkeypatch):
    state = {
        "owner": "owner-alpha",
    }

    project_owners = {
        "project-alpha": "owner-alpha",
        "project-alpha-2": "owner-alpha",
        "project-beta": "owner-beta",
    }

    def current_user_id():
        return state["owner"]

    def get_project_metadata(project_id: str):
        owner = project_owners.get(project_id)

        if owner is None:
            raise workspace_service.ProjectServiceError(
                "project_not_found"
            )

        return {
            "project_id": project_id,
            "owner_user_id": owner,
        }

    registry = (
        tmp_path
        / "authority"
        / "approved-scientific-workspaces.json"
    )

    monkeypatch.setattr(
        workspace_service,
        "current_user_id",
        current_user_id,
    )

    monkeypatch.setattr(
        workspace_service,
        "get_project_metadata",
        get_project_metadata,
    )

    monkeypatch.setattr(
        workspace_service,
        "scientific_workspace_registry_path",
        lambda: registry,
    )

    root = tmp_path / "science"
    root.mkdir()

    return {
        "state": state,
        "root": root,
        "registry": registry,
    }


def _approve(
    *,
    project_id: str,
    root: Path,
):
    plan = (
        workspace_service
        .plan_scientific_workspace_approval(
            ScientificWorkspacePlanRequest(
                project_id=project_id,
                workspace_root=str(root),
            )
        )
    )

    assert plan.status == "approval_required"
    assert plan.plan_id
    assert plan.plan_hash

    result = (
        workspace_service
        .apply_scientific_workspace_approval(
            ScientificWorkspaceApplyRequest(
                project_id=project_id,
                plan_id=plan.plan_id,
                plan_hash=plan.plan_hash,
                operator_approved=True,
                confirmation_phrase=(
                    "Approve exact scientific workspace"
                ),
            )
        )
    )

    assert result.status == "approved"


def _request(
    root: Path,
    *,
    project_id: str = "project-alpha",
    relative_path: str = "measurements.csv",
    operation: str = "descriptive_stats",
    columns: list[str] | None = None,
):
    return ScientificWorkspaceExecutionRequest(
        project_id=project_id,
        workspace_root=str(root),
        relative_path=relative_path,
        operation=operation,
        request_id="request-science-test",
        columns=columns or ["value"],
        seed=17,
    )


def _ingest_result(
    *,
    project_id: str = "project-alpha",
    file_id: str = "file_1234567890abcdef",
    accepted: bool = True,
    ready: bool = True,
    blocked: bool = False,
    errors: list[str] | None = None,
):
    return SimpleNamespace(
        accepted=accepted,
        ready=ready,
        blocked=blocked,
        file_id=file_id,
        errors=list(errors or []),
        file=SimpleNamespace(
            file_id=file_id,
            source_project_id=project_id,
        ),
    )


def _scientific_result(
    *,
    status: str = "completed",
    ok: bool = True,
    errors: list[str] | None = None,
):
    return SimpleNamespace(
        status=SimpleNamespace(
            value=status,
        ),
        ok=ok,
        job_id="scientificjob_test",
        result={
            "count": 2,
            "mean": 1.5,
        },
        provenance=(
            _Provenance()
            if status == "completed"
            else None
        ),
        source_mutated=False,
        network_access_used=False,
        shell_used=False,
        warnings=[],
        errors=list(errors or []),
    )


def test_unapproved_workspace_never_reaches_ingest_or_scientificforge(
    authority,
    monkeypatch,
):
    root = authority["root"]

    (root / "measurements.csv").write_text(
        "value\n1\n2\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        execution,
        "attach_file",
        lambda *args, **kwargs: pytest.fail(
            "unapproved source reached ingest"
        ),
    )

    monkeypatch.setattr(
        execution,
        "run_scientific_execution",
        lambda *args, **kwargs: pytest.fail(
            "unapproved source reached ScientificForge"
        ),
    )

    result = (
        execution.run_scientific_workspace_execution(
            _request(root)
        )
    )

    assert result.status == "blocked"
    assert "scientific_workspace_not_approved" in result.errors


def test_cross_project_workspace_grant_never_reaches_ingest(
    authority,
    monkeypatch,
):
    root = authority["root"]

    (root / "measurements.csv").write_text(
        "value\n1\n2\n",
        encoding="utf-8",
    )

    _approve(
        project_id="project-alpha",
        root=root,
    )

    monkeypatch.setattr(
        execution,
        "attach_file",
        lambda *args, **kwargs: pytest.fail(
            "cross-project request reached ingest"
        ),
    )

    result = (
        execution.run_scientific_workspace_execution(
            _request(
                root,
                project_id="project-alpha-2",
            )
        )
    )

    assert result.status == "blocked"
    assert "scientific_workspace_not_approved" in result.errors


def test_relative_path_escape_is_blocked_before_ingest(
    authority,
    tmp_path: Path,
    monkeypatch,
):
    root = authority["root"]

    outside = tmp_path / "outside.csv"
    outside.write_text(
        "value\n9\n",
        encoding="utf-8",
    )

    _approve(
        project_id="project-alpha",
        root=root,
    )

    monkeypatch.setattr(
        execution,
        "attach_file",
        lambda *args, **kwargs: pytest.fail(
            "path escape reached ingest"
        ),
    )

    result = (
        execution.run_scientific_workspace_execution(
            _request(
                root,
                relative_path="../outside.csv",
            )
        )
    )

    assert result.status == "blocked"
    assert (
        "scientific_workspace_relative_path_invalid"
        in result.errors
    )


def test_symlink_and_hardlink_sources_are_blocked_before_ingest(
    authority,
    monkeypatch,
):
    root = authority["root"]

    source = root / "source.csv"
    source.write_text(
        "value\n1\n2\n",
        encoding="utf-8",
    )

    symlink = root / "linked.csv"
    symlink.symlink_to(source)

    hardlink = root / "hard.csv"
    os.link(source, hardlink)

    _approve(
        project_id="project-alpha",
        root=root,
    )

    monkeypatch.setattr(
        execution,
        "attach_file",
        lambda *args, **kwargs: pytest.fail(
            "unsafe source reached ingest"
        ),
    )

    symlink_result = (
        execution.run_scientific_workspace_execution(
            _request(
                root,
                relative_path="linked.csv",
            )
        )
    )

    hardlink_result = (
        execution.run_scientific_workspace_execution(
            _request(
                root,
                relative_path="hard.csv",
            )
        )
    )

    assert symlink_result.status == "blocked"
    assert (
        "scientific_workspace_source_symlink"
        in symlink_result.errors
    )

    assert hardlink_result.status == "blocked"
    assert (
        "scientific_workspace_source_hardlink"
        in hardlink_result.errors
    )


def test_supported_non_scientificforge_format_routes_away_before_ingest(
    authority,
    monkeypatch,
):
    root = authority["root"]

    (root / "watershed.geojson").write_text(
        '{"type":"FeatureCollection","features":[]}',
        encoding="utf-8",
    )

    _approve(
        project_id="project-alpha",
        root=root,
    )

    monkeypatch.setattr(
        execution,
        "attach_file",
        lambda *args, **kwargs: pytest.fail(
            "GeoJSON incorrectly entered ScientificForge staging"
        ),
    )

    monkeypatch.setattr(
        execution,
        "run_scientific_execution",
        lambda *args, **kwargs: pytest.fail(
            "GeoJSON incorrectly entered ScientificForge"
        ),
    )

    result = (
        execution.run_scientific_workspace_execution(
            _request(
                root,
                relative_path="watershed.geojson",
            )
        )
    )

    assert result.status == "blocked"
    assert (
        "scientific_workspace_source_not_supported_by_scientificforge_v0"
        in result.errors
    )


def test_inline_only_scientific_operation_does_not_accept_workspace_source(
    authority,
    monkeypatch,
):
    root = authority["root"]

    (root / "measurements.csv").write_text(
        "value\n1\n2\n",
        encoding="utf-8",
    )

    _approve(
        project_id="project-alpha",
        root=root,
    )

    monkeypatch.setattr(
        execution,
        "attach_file",
        lambda *args, **kwargs: pytest.fail(
            "inline-only operation reached staging"
        ),
    )

    result = (
        execution.run_scientific_workspace_execution(
            _request(
                root,
                operation="matrix_multiply",
            )
        )
    )

    assert result.status == "blocked"
    assert (
        "scientific_workspace_operation_not_source_backed"
        in result.errors
    )


def test_staged_ingest_must_echo_exact_project_scope(
    authority,
    monkeypatch,
):
    root = authority["root"]

    (root / "measurements.csv").write_text(
        "value\n1\n2\n",
        encoding="utf-8",
    )

    _approve(
        project_id="project-alpha",
        root=root,
    )

    monkeypatch.setattr(
        execution,
        "attach_file",
        lambda *args, **kwargs: _ingest_result(
            project_id="project-alpha-2",
        ),
    )

    monkeypatch.setattr(
        execution,
        "run_scientific_execution",
        lambda *args, **kwargs: pytest.fail(
            "wrong-project staged file reached ScientificForge"
        ),
    )

    result = (
        execution.run_scientific_workspace_execution(
            _request(root)
        )
    )

    assert result.status == "blocked"
    assert (
        "scientific_workspace_staged_project_scope_mismatch"
        in result.errors
    )


def test_successful_csv_bridge_passes_only_file_id_into_scientificforge(
    authority,
    monkeypatch,
):
    root = authority["root"]

    source = root / "measurements.csv"

    source.write_text(
        "site,value\nalpha,1\nbeta,2\n",
        encoding="utf-8",
    )

    before = source.read_bytes()

    _approve(
        project_id="project-alpha",
        root=root,
    )

    observed: dict = {}

    def fake_attach_file(
        source_path,
        *,
        project_id=None,
        **kwargs,
    ):
        observed["staged_path"] = Path(
            source_path
        )
        observed["staged_project_id"] = (
            project_id
        )

        return _ingest_result(
            project_id=project_id,
        )

    def fake_scientific(request):
        observed["scientific_request"] = dict(
            request
        )

        return _scientific_result()

    monkeypatch.setattr(
        execution,
        "attach_file",
        fake_attach_file,
    )

    monkeypatch.setattr(
        execution,
        "run_scientific_execution",
        fake_scientific,
    )

    result = (
        execution.run_scientific_workspace_execution(
            _request(root)
        )
    )

    assert result.status == "completed"
    assert result.ok is True

    assert (
        observed["staged_path"]
        == source
    )

    assert (
        observed["staged_project_id"]
        == "project-alpha"
    )

    scientific_request = (
        observed["scientific_request"]
    )

    assert (
        scientific_request["source_file_id"]
        == "file_1234567890abcdef"
    )

    assert (
        scientific_request["operation"]
        == "descriptive_stats"
    )

    assert (
        scientific_request["columns"]
        == ["value"]
    )

    assert (
        scientific_request["request_id"]
        == "request-science-test"
    )

    assert "workspace_root" not in scientific_request
    assert "relative_path" not in scientific_request
    assert "source_path" not in scientific_request

    assert result.relative_path == "measurements.csv"
    assert result.raw_absolute_path_exposed is False
    assert result.source_mutated is False
    assert result.network_used is False
    assert result.shell_used is False

    serialized = json.dumps(
        result.model_dump(mode="json"),
        sort_keys=True,
    )

    assert str(root) not in serialized

    assert source.read_bytes() == before


def test_staging_failure_never_reaches_scientificforge(
    authority,
    monkeypatch,
):
    root = authority["root"]

    (root / "measurements.csv").write_text(
        "value\n1\n2\n",
        encoding="utf-8",
    )

    _approve(
        project_id="project-alpha",
        root=root,
    )

    monkeypatch.setattr(
        execution,
        "attach_file",
        lambda *args, **kwargs: _ingest_result(
            accepted=False,
            ready=False,
            blocked=True,
            errors=["fixture_ingest_blocked"],
        ),
    )

    monkeypatch.setattr(
        execution,
        "run_scientific_execution",
        lambda *args, **kwargs: pytest.fail(
            "failed staging reached ScientificForge"
        ),
    )

    result = (
        execution.run_scientific_workspace_execution(
            _request(root)
        )
    )

    assert result.status == "blocked"
    assert "fixture_ingest_blocked" in result.errors
    assert (
        "scientific_workspace_source_staging_failed"
        in result.errors
    )


def test_scientificforge_stop_or_block_result_is_propagated_truthfully(
    authority,
    monkeypatch,
):
    root = authority["root"]

    (root / "measurements.csv").write_text(
        "value\n1\n2\n",
        encoding="utf-8",
    )

    _approve(
        project_id="project-alpha",
        root=root,
    )

    monkeypatch.setattr(
        execution,
        "attach_file",
        lambda *args, **kwargs: _ingest_result(),
    )

    monkeypatch.setattr(
        execution,
        "run_scientific_execution",
        lambda *args, **kwargs: _scientific_result(
            status="blocked",
            ok=False,
            errors=["emergency_stop_active"],
        ),
    )

    result = (
        execution.run_scientific_workspace_execution(
            _request(root)
        )
    )

    assert result.status == "blocked"
    assert result.ok is False
    assert "emergency_stop_active" in result.errors
    assert result.source_mutated is False
    assert result.network_used is False
    assert result.shell_used is False
