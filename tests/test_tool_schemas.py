from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.schemas.common import ApprovalState, LocalityState
from app.api.schemas.tools import (
    ToolBoundaryKind,
    ToolLedgerEntry,
    ToolLedgerState,
    ToolLedgerSummary,
)


def test_tool_ledger_entry_defaults_dangerous_fields_false():
    entry = ToolLedgerEntry(tool_key="bounded_math_execution")

    assert entry.state == ToolLedgerState.UNKNOWN
    assert entry.available is False
    assert entry.used is False
    assert entry.approval_required is False
    assert entry.approval_state == ApprovalState.UNKNOWN
    assert entry.locality == LocalityState.UNKNOWN
    assert entry.boundary_kind == ToolBoundaryKind.UNKNOWN
    assert entry.mutated_files is False
    assert entry.network_access_used is False
    assert entry.private_context_sent is False
    assert entry.shell_used is False
    assert entry.git_mutation_used is False
    assert entry.cloud_used is False

    payload = entry.to_payload()
    assert payload["state"] == "unknown"
    assert payload["boundary_kind"] == "unknown"
    assert payload["used"] is False
    assert payload["mutated_files"] is False


def test_tool_ledger_summary_accepts_available_and_used_entries():
    available = ToolLedgerEntry(
        tool_key="repo_context",
        state=ToolLedgerState.AVAILABLE,
        available=True,
        locality=LocalityState.LOCAL,
        boundary_kind=ToolBoundaryKind.LOCAL_SELECTED_REPO,
    )
    used = ToolLedgerEntry(
        tool_key="data_execution",
        state=ToolLedgerState.USED,
        available=True,
        used=True,
        output_count=1,
    )

    summary = ToolLedgerSummary(
        tools_available=[available],
        tools_used=[used],
        tool_count=1,
        used_tool_count=1,
    )

    payload = summary.to_payload()

    assert payload["tools_available"][0]["tool_key"] == "repo_context"
    assert payload["tools_used"][0]["tool_key"] == "data_execution"
    assert payload["tools_used"][0]["used"] is True


@pytest.mark.parametrize(
    "field_name",
    ["input_count", "output_count"],
)
def test_tool_ledger_entry_rejects_negative_counts(field_name):
    payload = {"tool_key": "bad_count", field_name: -1}

    with pytest.raises(ValidationError):
        ToolLedgerEntry(**payload)


def test_tool_ledger_entry_rejects_unexpected_fields():
    with pytest.raises(ValidationError):
        ToolLedgerEntry(tool_key="extra_tool", raw_payload={"secret": "nope"})
