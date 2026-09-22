from __future__ import annotations

import json

from app.api import runtime_bridge
from app.api.schemas.artifacts import (
    ArtifactKind,
    ArtifactMemoryPosture,
    ArtifactSummary,
)
from app.api.schemas.chat import (
    ChatSendRequest,
)


def _scientific_payload(
    *,
    status: str = "completed",
):
    return {
        "used": True,
        "status": status,
        "ok": status == "completed",
        "tool_kind": "scientificforge",
        "project_id": "project-alpha",
        "workspace_root_hash": "workspacehash123",
        "relative_path": "measurements.csv",
        "source_type_id": "csv_table",
        "source_category": "tabular",
        "staged_file_id": "file_1234567890abcdef",
        "scientific_operation": "descriptive_stats",
        "scientific_job_id": "scientificjob_alpha",
        "result": (
            {
                "count": 2,
                "mean": 1.5,
            }
            if status == "completed"
            else {}
        ),
        "provenance": {
            "source_sha256": "c" * 64,
            "parameter_sha256": "a" * 64,
            "result_sha256": "b" * 64,
            "deterministic": True,
        },
        "source_mutated": False,
        "network_used": False,
        "shell_used": False,
        "raw_absolute_path_exposed": False,
        "warnings": [],
        "errors": (
            []
            if status == "completed"
            else ["fixture_scientific_block"]
        ),
    }


def _request():
    return ChatSendRequest(
        message="Compute descriptive statistics.",
        request_id="request-alpha",
        conversation_id="conversation-alpha",
        project_id="project-alpha",
    )


def _runtime_packet(
    *,
    status: str = "completed",
):
    scientific = _scientific_payload(
        status=status
    )

    return {
        "status": "ok_local_runtime",
        "response": {
            "response_text": "Scientific result available.",
            "response_source": "live_invoker",
            "invocation_status": "ok",
            "selected_model_role": "primary_general",
            "selected_runtime": "ollama",
            "selected_model_runtime_tag": "mistral-small-3.1:24b",
            "used_fallback": False,
            "caveats": [],
        },
        "internal_result": {
            "scientific_execution": scientific,
        },
        "scientific_execution": scientific,
        "data_execution": {
            "used": False,
            "status": "not_needed",
        },
        "math_execution": {
            "used": False,
            "status": "not_needed",
        },
    }


def _artifact_summary():
    return ArtifactSummary(
        artifact_id="artifact-science-alpha",
        kind=ArtifactKind.SCIENTIFIC_RESULT,
        title="Scientific result: descriptive_stats",
        summary="Saved governed ScientificForge result.",
        created_at_utc="2026-09-21T00:00:00Z",
        request_id="request-alpha",
        conversation_id="conversation-alpha",
        project_id="project-alpha",
        locality="local",
        memory_posture=ArtifactMemoryPosture.NOT_MEMORY,
        producer_tool_kind="scientificforge",
        producer_operation="descriptive_stats",
        source_file_id="file_1234567890abcdef",
        source_file_name="measurements.csv",
        source_file_kind="csv_table",
        scientific_operation="descriptive_stats",
        scientific_job_id="scientificjob_alpha",
        parameter_sha256="a" * 64,
        result_sha256="b" * 64,
        source_sha256="c" * 64,
        workspace_root_hash="workspacehash123",
    )


def test_completed_scientific_execution_creates_scientific_artifact(
    monkeypatch,
):
    observed = {}

    def fake_create(
        scientific_execution,
        *,
        request_id=None,
        conversation_id=None,
        project_id=None,
    ):
        observed["scientific_execution"] = dict(
            scientific_execution
        )
        observed["request_id"] = request_id
        observed["conversation_id"] = conversation_id
        observed["project_id"] = project_id

        return object()

    monkeypatch.setattr(
        runtime_bridge,
        "create_scientific_result_artifact",
        fake_create,
    )

    monkeypatch.setattr(
        runtime_bridge,
        "artifact_summary_from_record",
        lambda record: _artifact_summary(),
    )

    summaries, warnings = (
        runtime_bridge
        ._build_artifact_summaries_for_chat_response(
            request_model=_request(),
            runtime_packet=_runtime_packet(),
        )
    )

    assert warnings == []
    assert len(summaries) == 1

    assert (
        summaries[0].kind
        == ArtifactKind.SCIENTIFIC_RESULT
    )

    assert observed["request_id"] == "request-alpha"
    assert (
        observed["conversation_id"]
        == "conversation-alpha"
    )
    assert observed["project_id"] == "project-alpha"

    assert (
        observed["scientific_execution"][
            "workspace_root_hash"
        ]
        == "workspacehash123"
    )

    serialized = json.dumps(
        summaries[0].model_dump(
            mode="json"
        )
    )

    assert '"workspace_root":' not in serialized
    assert '"workspace_root_hash":' in serialized


def test_blocked_scientific_execution_creates_no_artifact(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime_bridge,
        "create_scientific_result_artifact",
        lambda *args, **kwargs: (
            (_ for _ in ()).throw(
                AssertionError(
                    "blocked scientific execution attempted artifact creation"
                )
            )
        ),
    )

    summaries, warnings = (
        runtime_bridge
        ._build_artifact_summaries_for_chat_response(
            request_model=_request(),
            runtime_packet=_runtime_packet(
                status="blocked"
            ),
        )
    )

    assert summaries == []
    assert warnings == []


def test_chat_translation_surfaces_scientific_execution_and_artifact(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime_bridge,
        "_build_artifact_summaries_for_chat_response",
        lambda **kwargs: (
            [_artifact_summary()],
            [],
        ),
    )

    chat = (
        runtime_bridge
        ._translate_runtime_packet_to_chat_data(
            _request(),
            _runtime_packet(),
        )
    )

    assert chat.scientific_execution is not None

    assert (
        chat.scientific_execution[
            "scientific_operation"
        ]
        == "descriptive_stats"
    )

    assert len(chat.artifacts) == 1

    serialized = json.dumps(
        chat.model_dump(
            mode="json"
        ),
        sort_keys=True,
    )

    assert '"workspace_root":' not in serialized


def test_scientificforge_enters_existing_tool_ledger_with_hash_truth(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime_bridge,
        "_build_artifact_summaries_for_chat_response",
        lambda **kwargs: (
            [_artifact_summary()],
            [],
        ),
    )

    chat = (
        runtime_bridge
        ._translate_runtime_packet_to_chat_data(
            _request(),
            _runtime_packet(),
        )
    )

    tools, extra = (
        runtime_bridge
        ._build_tool_ledger_from_chat_data(
            chat
        )
    )

    science = next(
        item
        for item in tools
        if item.get("tool_key")
        == "scientificforge"
    )

    assert science["used"] is True
    assert science["state"] == "completed"

    assert (
        science["operation"]
        == "descriptive_stats"
    )

    assert (
        science["operation_id"]
        == "scientificjob_alpha"
    )

    assert (
        science["workspace_root_hash"]
        == "workspacehash123"
    )

    assert (
        science["relative_paths"]
        == ["measurements.csv"]
    )

    assert (
        science["source_type_id"]
        == "csv_table"
    )

    assert (
        science["source_hash"]
        == "c" * 64
    )

    assert (
        science["parameter_hash"]
        == "a" * 64
    )

    assert (
        science["result_hash"]
        == "b" * 64
    )

    assert science["mutated_files"] is False
    assert science["network_access_used"] is False
    assert science["shell_used"] is False

    assert extra["mutated_files"] is False
    assert extra["shell_used"] is False

    serialized = json.dumps(
        science,
        sort_keys=True,
    )

    assert '"workspace_root":' not in serialized


def test_blocked_scientificforge_still_has_truthful_tool_ledger_entry(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime_bridge,
        "_build_artifact_summaries_for_chat_response",
        lambda **kwargs: (
            [],
            [],
        ),
    )

    chat = (
        runtime_bridge
        ._translate_runtime_packet_to_chat_data(
            _request(),
            _runtime_packet(
                status="blocked"
            ),
        )
    )

    tools, _ = (
        runtime_bridge
        ._build_tool_ledger_from_chat_data(
            chat
        )
    )

    science = next(
        item
        for item in tools
        if item.get("tool_key")
        == "scientificforge"
    )

    assert science["state"] == "blocked"
    assert science["used"] is True

    assert (
        "fixture_scientific_block"
        in science["errors"]
    )


def test_runtime_packet_exposes_scientific_execution_at_top_level():
    from pathlib import Path

    runtime_source = (
        Path(runtime_bridge.__file__)
        .parents[2]
        / "core"
        / "runtime.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        '"scientific_execution": scientific_execution,'
        in runtime_source
    )
