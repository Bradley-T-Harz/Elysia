from __future__ import annotations

from hashlib import sha256

from app.api.coding_file_operation_service import execute_file_operation, plan_file_operation
from app.api.coding_operation_service import approve_operation
from app.api.schemas.coding_file_operations import CodingFileOperationExecuteRequest
from app.api.schemas.coding_operations import CodingOperationApproveRequest


def _with_approval(payload: CodingFileOperationExecuteRequest) -> CodingFileOperationExecuteRequest:
    plan = plan_file_operation(payload)
    exact_files = [payload.target_path]
    if payload.destination_path:
        exact_files.append(payload.destination_path)
    approval = approve_operation(
        CodingOperationApproveRequest(
            session_id=payload.session_id,
            operation_kind=f"file_operation:{plan.operation_kind}",
            operation_summary=payload.summary,
            workspace_root=payload.workspace_root,
            exact_files=exact_files,
            source_hash=plan.source_hash,
            plan_hash=plan.plan_hash or "",
            allowed_mutation_class=f"file_{plan.operation_kind}",
            operator_approved=True,
            approval_phrase="approve exact file operation",
            rollback_note="Use the governed backup receipt.",
        )
    )
    return payload.model_copy(update={"approval_id": approval.approval_id, "approval_token": approval.approval_token})


def test_file_create_execute_requires_approval(tmp_path):
    result = execute_file_operation(
        _with_approval(CodingFileOperationExecuteRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            operation_kind="create",
            target_path="new.py",
            summary="create file",
            new_text="print('hi')\n",
        ))
    )

    assert result.status == "approval_required"
    assert not (tmp_path / "new.py").exists()


def test_file_create_execute_writes_text_after_approval(tmp_path):
    result = execute_file_operation(
        _with_approval(CodingFileOperationExecuteRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            operation_kind="create",
            target_path="new.py",
            summary="create file",
            new_text="print('hi')\n",
            operator_approved=True,
        ))
    )

    assert result.status == "applied"
    assert result.mutation_performed is True
    assert (tmp_path / "new.py").read_text(encoding="utf-8") == "print('hi')\n"


def test_file_edit_execute_blocks_stale_hash(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("old\n", encoding="utf-8")

    result = execute_file_operation(
        _with_approval(CodingFileOperationExecuteRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            operation_kind="edit",
            target_path="app.py",
            summary="edit file",
            new_text="new\n",
            expected_content_hash=sha256("different\n".encode("utf-8")).hexdigest(),
            operator_approved=True,
        ))
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "current_content_hash_mismatch"
    assert source.read_text(encoding="utf-8") == "old\n"


def test_file_delete_blocks_private_paths(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=secret\n", encoding="utf-8")

    result = execute_file_operation(
        CodingFileOperationExecuteRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            operation_kind="delete",
            target_path=".env",
            summary="delete env",
            operator_approved=True,
        )
    )

    assert result.status == "blocked"
    assert env_file.exists()


def test_file_operation_blocks_outside_apply_mode_even_with_operator_approval(tmp_path):
    result = execute_file_operation(
        CodingFileOperationExecuteRequest(
            approval_mode="plan_only",
            workspace_root=str(tmp_path),
            operation_kind="create",
            target_path="new.py",
            summary="create file",
            new_text="print('hi')\n",
            operator_approved=True,
        )
    )

    assert result.status == "blocked_by_approval_mode"
    assert not (tmp_path / "new.py").exists()


def test_file_create_never_overwrites_existing_target(tmp_path):
    source = tmp_path / "existing.py"
    source.write_text("original\n", encoding="utf-8")

    result = execute_file_operation(
        CodingFileOperationExecuteRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            operation_kind="create",
            target_path="existing.py",
            summary="must not overwrite",
            new_text="replacement\n",
            operator_approved=True,
        )
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "target_exists"
    assert source.read_text(encoding="utf-8") == "original\n"


def test_file_edit_requires_exact_source_hash(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("old\n", encoding="utf-8")

    result = execute_file_operation(
        CodingFileOperationExecuteRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            operation_kind="edit",
            target_path="app.py",
            summary="edit file",
            new_text="new\n",
            operator_approved=True,
        )
    )

    assert result.blocked_reason == "expected_content_hash_required"
    assert source.read_text(encoding="utf-8") == "old\n"


def test_file_delete_creates_recoverable_backup(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("keep this\n", encoding="utf-8")
    source_hash = sha256(source.read_bytes()).hexdigest()

    result = execute_file_operation(
        _with_approval(CodingFileOperationExecuteRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            operation_kind="delete",
            target_path="notes.txt",
            summary="delete with receipt",
            expected_content_hash=source_hash,
            operator_approved=True,
        ))
    )

    assert result.status == "applied"
    assert not source.exists()
    assert result.backup_relative_path
    assert (tmp_path / result.backup_relative_path).read_text(encoding="utf-8") == "keep this\n"
    assert result.rollback_receipt_id


def test_file_rename_refuses_type_change(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("notes\n", encoding="utf-8")

    result = execute_file_operation(
        CodingFileOperationExecuteRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            operation_kind="rename",
            target_path="notes.txt",
            destination_path="notes.py",
            summary="unsafe type change",
            expected_content_hash=sha256(source.read_bytes()).hexdigest(),
            operator_approved=True,
        )
    )

    assert result.blocked_reason == "type_changing_move_not_allowed"
    assert source.exists()


def test_file_write_refuses_possible_secret(tmp_path):
    result = execute_file_operation(
        CodingFileOperationExecuteRequest(
            approval_mode="apply_with_approval",
            workspace_root=str(tmp_path),
            operation_kind="create",
            target_path="config.py",
            summary="unsafe proposed secret",
            new_text="api_key = 'abcdef1234567890'\n",
            operator_approved=True,
        )
    )

    assert result.blocked_reason == "proposed_content_contains_possible_secret"
    assert not (tmp_path / "config.py").exists()
