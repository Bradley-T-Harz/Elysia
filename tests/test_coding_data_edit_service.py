from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from app.api.coding_data_edit_service import apply_data_edit, plan_data_edit
from app.api.schemas.coding_data import CodingDataApplyRequest as _CodingDataApplyRequest, CodingDataEditPlanRequest
from tests.coding_approval_test_helpers import approval_fields_for_plan


def CodingDataApplyRequest(**kwargs):
    plan = plan_data_edit(
        CodingDataEditPlanRequest(
            **{key: value for key, value in kwargs.items() if key in {"session_id", "workspace_root", "file_path", "approval_granted", "approval_reason", "max_rows", "max_features", "max_values", "operation", "parameters"}}
        )
    )
    approval = approval_fields_for_plan(workspace_root=kwargs["workspace_root"], operation_kind="data_edit", mutation_class="data_edit", source_file=kwargs["file_path"], plan=plan)
    return _CodingDataApplyRequest(**approval, **kwargs)


def test_tabular_append_row_creates_backup_and_audit_summary(tmp_path: Path):
    path = tmp_path / "sample.csv"
    path.write_text("name,value\nalpha,1\n", encoding="utf-8")

    plan = plan_data_edit(CodingDataEditPlanRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True, operation="tabular_append_row", parameters={"row": {"name": "beta", "value": "2"}}))
    assert plan.status == "planned"

    result = apply_data_edit(CodingDataApplyRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True, operator_approved=True, operation="tabular_append_row", parameters={"row": {"name": "beta", "value": "2"}}, expected_source_hash=plan.source_hash))

    assert result.status == "applied"
    assert result.backup["created"] is True
    with path.open() as handle:
        rows = list(csv.DictReader(handle))
    assert rows[-1]["name"] == "beta"


def test_sqlite_insert_is_unavailable_under_databaseforge_boundary(tmp_path: Path):
    path = tmp_path / "sample.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE samples (id INTEGER PRIMARY KEY, name TEXT)")
    connection.commit()
    connection.close()

    plan = plan_data_edit(CodingDataEditPlanRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True, operation="sqlite_insert_row", parameters={"table": "samples", "row": {"name": "alpha"}}))
    assert plan.status == "blocked"
    assert plan.blocked_reason == "database_mutation_unavailable_by_design"

    result = apply_data_edit(_CodingDataApplyRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True, operator_approved=True, operation="sqlite_insert_row", parameters={"table": "samples", "row": {"name": "alpha"}}, expected_source_hash=plan.source_hash))

    assert result.status == "blocked"
    assert result.blocked_reason == "database_mutation_unavailable_by_design"
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 0
    finally:
        connection.close()


def test_sqlite_update_is_blocked_before_legacy_selector_handling(tmp_path: Path):
    path = tmp_path / "sample.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE samples (id INTEGER PRIMARY KEY, name TEXT)")
    connection.execute("INSERT INTO samples (name) VALUES ('alpha')")
    connection.commit()
    connection.close()

    plan = plan_data_edit(CodingDataEditPlanRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True, operation="sqlite_update_row", parameters={"table": "samples", "values": {"name": "beta"}}))
    result = apply_data_edit(_CodingDataApplyRequest(workspace_root=str(tmp_path), file_path=str(path), approval_granted=True, operator_approved=True, operation="sqlite_update_row", parameters={"table": "samples", "values": {"name": "beta"}}, expected_source_hash=plan.source_hash))

    assert plan.status == "blocked"
    assert plan.blocked_reason == "database_mutation_unavailable_by_design"
    assert result.status == "blocked"
    assert result.blocked_reason == "database_mutation_unavailable_by_design"
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT name FROM samples").fetchone()[0] == "alpha"
    finally:
        connection.close()
