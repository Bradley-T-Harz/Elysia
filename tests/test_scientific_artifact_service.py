from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from app.api import artifact_service
from app.api.artifact_service import (
    ArtifactCreationError,
    artifact_detail_from_record,
    artifact_summary_from_record,
    build_scientific_result_artifact_record,
    create_scientific_result_artifact,
)
from app.api.schemas.artifacts import (
    ArtifactKind,
    ScientificResultArtifactPayload,
)


OWNER = "owner-alpha"


def _scientific_execution():
    return {
        "used": True,
        "status": "completed",
        "ok": True,
        "project_id": "project-alpha",
        "workspace_root_hash": "workspacehash123",
        "relative_path": "measurements.csv",
        "source_type_id": "csv_table",
        "source_category": "tabular",
        "staged_file_id": "file_1234567890abcdef",
        "scientific_operation": "descriptive_stats",
        "scientific_job_id": "scientificjob_alpha",
        "result": {
            "count": 2,
            "mean": 1.5,
        },
        "provenance": {
            "source_sha256": "c" * 64,
            "parameter_sha256": "a" * 64,
            "result_sha256": "b" * 64,
            "seed": None,
            "deterministic": True,
            "engine_versions": {
                "scientificforge": "v0.1",
            },
        },
        "source_mutated": False,
        "network_used": False,
        "shell_used": False,
        "raw_absolute_path_exposed": False,
        "warnings": [],
        "errors": [],
    }


def test_scientific_artifact_record_contains_reproducible_truth_without_root(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(
        artifact_service,
        "current_user_id",
        lambda: OWNER,
    )

    execution = _scientific_execution()

    record = (
        build_scientific_result_artifact_record(
            execution,
            request_id="request-alpha",
            conversation_id="conversation-alpha",
            project_id="project-alpha",
            artifact_root=tmp_path,
        )
    )

    assert (
        record.kind
        == ArtifactKind.SCIENTIFIC_RESULT
    )

    assert record.owner_user_id == OWNER

    assert (
        record.producer_tool_kind
        == "scientificforge"
    )

    assert (
        record.producer_operation
        == "descriptive_stats"
    )

    assert (
        record.source.source_file_id
        == "file_1234567890abcdef"
    )

    assert (
        record.source.source_file_name
        == "measurements.csv"
    )

    assert record.source.source_path is None

    assert isinstance(
        record.payload,
        ScientificResultArtifactPayload,
    )

    assert (
        record.payload.parameter_sha256
        == "a" * 64
    )

    assert (
        record.payload.result_sha256
        == "b" * 64
    )

    assert (
        record.payload.source_sha256
        == "c" * 64
    )

    assert (
        record.payload.result["mean"]
        == 1.5
    )

    serialized = json.dumps(
        record.model_dump(
            mode="json"
        ),
        sort_keys=True,
    )

    assert "/private/" not in serialized

    # The non-reversible root hash is intentional provenance. What must never
    # appear is a raw authority-bearing workspace_root field/value.
    assert '"workspace_root":' not in serialized
    assert '"workspace_root_hash":' in serialized


def test_create_scientific_artifact_uses_account_namespace_and_validates_links(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv(
        "ELYSIA_ARTIFACT_ROOT",
        str(tmp_path),
    )

    monkeypatch.setattr(
        artifact_service,
        "current_user_id",
        lambda: OWNER,
    )

    observed = {}

    def validate_links(
        *,
        request_id,
        conversation_id,
        project_id,
    ):
        observed.update(
            request_id=request_id,
            conversation_id=conversation_id,
            project_id=project_id,
        )

    monkeypatch.setattr(
        artifact_service,
        "_validate_new_authority_links",
        validate_links,
    )

    record = create_scientific_result_artifact(
        _scientific_execution(),
        request_id="request-alpha",
        conversation_id="conversation-alpha",
        project_id="project-alpha",
    )

    assert observed == {
        "request_id": "request-alpha",
        "conversation_id": "conversation-alpha",
        "project_id": "project-alpha",
    }

    owner_hash = sha256(
        OWNER.encode(
            "utf-8"
        )
    ).hexdigest()[:24]

    expected_root = (
        tmp_path
        / "accounts"
        / owner_hash
    )

    artifact_path = Path(
        record.artifact_path
    )

    assert artifact_path.parent == expected_root
    assert artifact_path.is_file()

    assert (
        artifact_path.stat().st_mode
        & 0o777
        == 0o600
    )

    assert (
        artifact_path.parent.stat().st_mode
        & 0o777
        == 0o700
    )


@pytest.mark.parametrize(
    "patch",
    [
        {
            "status": "blocked",
            "ok": False,
        },
        {
            "source_mutated": True,
        },
        {
            "network_used": True,
        },
        {
            "shell_used": True,
        },
        {
            "provenance": {
                "parameter_sha256": "",
                "result_sha256": "",
            },
        },
    ],
)
def test_scientific_artifact_fails_closed_on_unqualified_truth(
    tmp_path: Path,
    monkeypatch,
    patch,
):
    monkeypatch.setattr(
        artifact_service,
        "current_user_id",
        lambda: OWNER,
    )

    execution = _scientific_execution()
    execution.update(patch)

    with pytest.raises(
        ArtifactCreationError
    ):
        build_scientific_result_artifact_record(
            execution,
            project_id="project-alpha",
            artifact_root=tmp_path,
        )


def test_scientific_summary_and_detail_are_safe_and_useful(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(
        artifact_service,
        "current_user_id",
        lambda: OWNER,
    )

    record = (
        build_scientific_result_artifact_record(
            _scientific_execution(),
            project_id="project-alpha",
            artifact_root=tmp_path,
        )
    )

    summary = artifact_summary_from_record(
        record
    )

    assert (
        summary.kind
        == ArtifactKind.SCIENTIFIC_RESULT
    )

    assert (
        summary.scientific_operation
        == "descriptive_stats"
    )

    assert (
        summary.result_sha256
        == "b" * 64
    )

    assert (
        summary.parameter_sha256
        == "a" * 64
    )

    detail = artifact_detail_from_record(
        record
    )

    assert (
        detail.safe_preview[
            "operation"
        ]
        == "descriptive_stats"
    )

    assert (
        detail.safe_preview[
            "result"
        ]["mean"]
        == 1.5
    )

    assert (
        detail.safe_preview[
            "raw_workspace_root_included"
        ]
        is False
    )

    serialized = json.dumps(
        detail.model_dump(
            mode="json"
        ),
        sort_keys=True,
    )

    assert "/private/" not in serialized
