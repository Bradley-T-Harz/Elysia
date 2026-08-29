from __future__ import annotations

from app.api.schemas.common import ApprovalState, LocalityState
from app.api.schemas.requests import (
    RequestArtifactSummary,
    RequestFileSummary,
    RequestSummaryData,
    RequestSummaryState,
)
from app.api.schemas.tools import ToolLedgerEntry, ToolLedgerState


def _minimal_request_summary() -> RequestSummaryData:
    return RequestSummaryData(
        request_id="req_schema_001",
        request_state=RequestSummaryState.COMPLETED,
        request_type="local_runtime_request",
        summary_text="Local runtime request completed.",
        approval_required=False,
        approval_state=ApprovalState.NOT_NEEDED,
        locality=LocalityState.LOCAL,
        can_proceed=True,
    )


def test_request_summary_ledger_fields_default_safe():
    summary = _minimal_request_summary()

    assert summary.files_attached_count == 0
    assert summary.files_attached == []
    assert summary.tools_available_count == 0
    assert summary.tools_used_count == 0
    assert summary.tools_available == []
    assert summary.tools_used == []
    assert summary.artifact_count == 0
    assert summary.artifacts == []
    assert summary.repo_context_status is None
    assert summary.repo_context_file_count == 0
    assert summary.repo_context_files == []
    assert summary.patch_plan_status is None
    assert summary.patch_plan_file_count == 0
    assert summary.patch_plan_files == []
    assert summary.mutated_files is False
    assert summary.shell_used is False
    assert summary.git_mutation_used is False
    assert summary.external_worker_used is False
    assert summary.mode_profile_key is None
    assert summary.mode_profile_label is None
    assert summary.mode_profile_used is False
    assert summary.mode_profile_effects == []
    assert summary.mode_profile_warnings == []
    assert summary.authority_granted_by_mode is False
    assert summary.files_used_count == 0
    assert summary.file_chunks_used_count == 0
    assert summary.file_parsers_used == []
    assert summary.file_memory_promotion is False
    assert summary.file_outward_sharing is False


def test_request_summary_accepts_compact_ledger_truth():
    summary = RequestSummaryData(
        request_id="req_schema_ledger_001",
        request_state=RequestSummaryState.COMPLETED,
        request_type="coder_request",
        summary_text="Coder request produced a patch plan but did not mutate files.",
        approval_required=False,
        approval_state=ApprovalState.NOT_NEEDED,
        locality=LocalityState.LOCAL,
        can_proceed=True,
        files_attached_count=1,
        files_attached=[
            RequestFileSummary(
                file_id="file_001",
                file_name="notes.md",
                file_kind="markdown",
                status="ready",
                summary="Selected markdown file.",
                parser_used="markdown_text_parser",
                chunks_created_count=2,
                chunks_used_count=1,
                memory_promotion_allowed=False,
                outward_sharing_allowed=False,
                trust_zone="user_selected_local_file",
            )
        ],
        mode_profile_key="writer",
        mode_profile_label="Writer",
        mode_profile_used=True,
        mode_profile_effects=["tone:polished"],
        authority_granted_by_mode=False,
        files_used_count=1,
        file_chunks_used_count=1,
        file_parsers_used=["markdown_text_parser"],
        file_memory_promotion=False,
        file_outward_sharing=False,
        tools_available_count=2,
        tools_used_count=1,
        tools_available=[
            ToolLedgerEntry(
                tool_key="repo_context",
                state=ToolLedgerState.AVAILABLE,
                available=True,
            )
        ],
        tools_used=[
            ToolLedgerEntry(
                tool_key="code_patch_plan",
                state=ToolLedgerState.USED,
                available=True,
                used=True,
            )
        ],
        artifact_count=1,
        artifacts=[
            RequestArtifactSummary(
                artifact_id="artifact_001",
                kind="data_summary",
                title="Summary",
                summary="Compact artifact summary.",
            )
        ],
        repo_context_status="used",
        repo_context_files=["core/example.py"],
        repo_context_file_count=1,
        patch_plan_status="created",
        patch_plan_files=["core/example.py"],
        patch_plan_file_count=1,
    )

    payload = summary.to_payload()

    assert payload["files_attached"][0]["file_name"] == "notes.md"
    assert payload["files_attached"][0]["parser_used"] == "markdown_text_parser"
    assert payload["files_used_count"] == 1
    assert payload["file_chunks_used_count"] == 1
    assert payload["file_parsers_used"] == ["markdown_text_parser"]
    assert payload["file_memory_promotion"] is False
    assert payload["file_outward_sharing"] is False
    assert payload["mode_profile_key"] == "writer"
    assert payload["mode_profile_used"] is True
    assert payload["authority_granted_by_mode"] is False
    assert payload["tools_used"][0]["tool_key"] == "code_patch_plan"
    assert payload["artifacts"][0]["artifact_id"] == "artifact_001"
    assert payload["mutated_files"] is False
    assert payload["shell_used"] is False
    assert payload["git_mutation_used"] is False
    assert payload["external_worker_used"] is False
