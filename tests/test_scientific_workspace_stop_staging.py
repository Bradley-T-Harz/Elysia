from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import scientific_workspace_execution_service as execution
from app.api.scientific_workspace_service import (
    VerifiedScientificWorkspaceSource,
)
from app.api.schemas.scientific_workspace import (
    ScientificWorkspaceExecutionRequest,
)


def _request() -> ScientificWorkspaceExecutionRequest:
    return ScientificWorkspaceExecutionRequest(
        project_id="project-alpha",
        workspace_root="/approved/science",
        relative_path="measurements.csv",
        operation="descriptive_stats",
        request_id="request-stop-test",
        columns=["value"],
    )


def _verified_source(
    source: Path,
) -> VerifiedScientificWorkspaceSource:
    return VerifiedScientificWorkspaceSource(
        project_id="project-alpha",
        workspace_root_hash="root-hash",
        relative_path="measurements.csv",
        source_path=source,
        type_id="csv_table",
        category="tabular",
        adapter="tabular",
        size_bytes=source.stat().st_size,
    )


def _successful_ingest():
    return SimpleNamespace(
        accepted=True,
        ready=True,
        blocked=False,
        file_id="file_1234567890abcdef",
        errors=[],
        file=SimpleNamespace(
            file_id="file_1234567890abcdef",
            source_project_id="project-alpha",
        ),
    )


def test_stop_active_before_resolution_blocks_everything(
    monkeypatch,
):
    monkeypatch.setattr(
        execution,
        "emergency_active",
        lambda: True,
    )

    monkeypatch.setattr(
        execution,
        "resolve_scientific_workspace_source",
        lambda **kwargs: pytest.fail(
            "STOP-active request reached workspace resolution"
        ),
    )

    monkeypatch.setattr(
        execution,
        "attach_file",
        lambda *args, **kwargs: pytest.fail(
            "STOP-active request reached staging"
        ),
    )

    monkeypatch.setattr(
        execution,
        "run_scientific_execution",
        lambda *args, **kwargs: pytest.fail(
            "STOP-active request reached ScientificForge"
        ),
    )

    result = (
        execution.run_scientific_workspace_execution(
            _request()
        )
    )

    assert result.status == "blocked"
    assert result.ok is False
    assert result.errors == [
        "emergency_stop_active"
    ]


def test_stop_after_resolution_blocks_before_ingest(
    tmp_path: Path,
    monkeypatch,
):
    source = tmp_path / "measurements.csv"
    source.write_text(
        "value\n1\n2\n",
        encoding="utf-8",
    )

    states = iter(
        [False, True]
    )

    monkeypatch.setattr(
        execution,
        "emergency_active",
        lambda: next(states, True),
    )

    monkeypatch.setattr(
        execution,
        "resolve_scientific_workspace_source",
        lambda **kwargs: _verified_source(
            source
        ),
    )

    monkeypatch.setattr(
        execution,
        "attach_file",
        lambda *args, **kwargs: pytest.fail(
            "post-resolution STOP reached staging"
        ),
    )

    result = (
        execution.run_scientific_workspace_execution(
            _request()
        )
    )

    assert result.status == "blocked"
    assert result.errors == [
        "emergency_stop_active"
    ]


def test_central_stop_callback_is_passed_into_ingest(
    tmp_path: Path,
    monkeypatch,
):
    source = tmp_path / "measurements.csv"
    source.write_text(
        "value\n1\n2\n",
        encoding="utf-8",
    )

    calls = {
        "stop": 0,
    }

    def stop_check():
        calls["stop"] += 1

        # Initial bridge check and pre-ingest check pass.
        # The callback observed inside ingest is then STOP-active.
        return calls["stop"] >= 3

    monkeypatch.setattr(
        execution,
        "emergency_active",
        stop_check,
    )

    monkeypatch.setattr(
        execution,
        "resolve_scientific_workspace_source",
        lambda **kwargs: _verified_source(
            source
        ),
    )

    observed = {}

    def fake_attach(
        source_path,
        *,
        project_id=None,
        cancel_check=None,
        **kwargs,
    ):
        observed["source_path"] = Path(
            source_path
        )
        observed["project_id"] = project_id
        observed["cancel_check"] = cancel_check

        assert callable(
            cancel_check
        )

        assert cancel_check() is True

        return SimpleNamespace(
            accepted=False,
            ready=False,
            blocked=True,
            file_id="file_cancelled_fixture",
            file=None,
            errors=[
                "file_ingest_cancelled"
            ],
        )

    monkeypatch.setattr(
        execution,
        "attach_file",
        fake_attach,
    )

    monkeypatch.setattr(
        execution,
        "run_scientific_execution",
        lambda *args, **kwargs: pytest.fail(
            "cancelled staging reached ScientificForge"
        ),
    )

    result = (
        execution.run_scientific_workspace_execution(
            _request()
        )
    )

    assert (
        observed["source_path"]
        == source
    )

    assert (
        observed["project_id"]
        == "project-alpha"
    )

    assert (
        observed["cancel_check"]
        is execution.emergency_active
    )

    assert result.status == "blocked"
    assert "file_ingest_cancelled" in result.errors
    assert (
        "scientific_workspace_source_staging_failed"
        in result.errors
    )


def test_stop_after_successful_staging_blocks_before_scientificforge(
    tmp_path: Path,
    monkeypatch,
):
    source = tmp_path / "measurements.csv"
    source.write_text(
        "value\n1\n2\n",
        encoding="utf-8",
    )

    calls = {
        "stop": 0,
    }

    def stop_check():
        calls["stop"] += 1

        # 1: before resolution
        # 2: before staging
        # 3: after staging / before ScientificForge
        return calls["stop"] >= 3

    monkeypatch.setattr(
        execution,
        "emergency_active",
        stop_check,
    )

    monkeypatch.setattr(
        execution,
        "resolve_scientific_workspace_source",
        lambda **kwargs: _verified_source(
            source
        ),
    )

    monkeypatch.setattr(
        execution,
        "attach_file",
        lambda *args, **kwargs: _successful_ingest(),
    )

    monkeypatch.setattr(
        execution,
        "run_scientific_execution",
        lambda *args, **kwargs: pytest.fail(
            "post-staging STOP reached ScientificForge"
        ),
    )

    result = (
        execution.run_scientific_workspace_execution(
            _request()
        )
    )

    assert result.status == "blocked"
    assert result.staged_file_id == (
        "file_1234567890abcdef"
    )
    assert result.errors == [
        "emergency_stop_active"
    ]


def test_stop_inactive_still_reaches_scientificforge(
    tmp_path: Path,
    monkeypatch,
):
    source = tmp_path / "measurements.csv"
    source.write_text(
        "value\n1\n2\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        execution,
        "emergency_active",
        lambda: False,
    )

    monkeypatch.setattr(
        execution,
        "resolve_scientific_workspace_source",
        lambda **kwargs: _verified_source(
            source
        ),
    )

    observed = {}

    def fake_attach(
        source_path,
        *,
        project_id=None,
        cancel_check=None,
        **kwargs,
    ):
        observed["cancel_check"] = (
            cancel_check
        )
        observed["project_id"] = (
            project_id
        )

        return _successful_ingest()

    monkeypatch.setattr(
        execution,
        "attach_file",
        fake_attach,
    )

    def fake_scientific(
        request,
    ):
        observed["scientific_request"] = dict(
            request
        )

        return SimpleNamespace(
            status=SimpleNamespace(
                value="completed"
            ),
            ok=True,
            job_id="scientificjob_stop_control",
            result={
                "count": 2,
                "mean": 1.5,
            },
            provenance=SimpleNamespace(
                model_dump=lambda mode="json": {
                    "parameter_sha256": "a" * 64,
                    "result_sha256": "b" * 64,
                    "deterministic": True,
                }
            ),
            source_mutated=False,
            network_access_used=False,
            shell_used=False,
            warnings=[],
            errors=[],
        )

    monkeypatch.setattr(
        execution,
        "run_scientific_execution",
        fake_scientific,
    )

    result = (
        execution.run_scientific_workspace_execution(
            _request()
        )
    )

    assert result.status == "completed"
    assert result.ok is True

    assert (
        observed["cancel_check"]
        is execution.emergency_active
    )

    assert (
        observed["project_id"]
        == "project-alpha"
    )

    assert (
        observed[
            "scientific_request"
        ]["source_file_id"]
        == "file_1234567890abcdef"
    )
