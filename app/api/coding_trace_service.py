"""Bridge sanitized coding audit truth into the central request trace ledger."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from app.api.request_trace_service import (
    mark_request_trace_blocked,
    mark_request_trace_completed,
    start_request_trace,
    update_request_trace_ledger_snapshot,
    update_request_trace_snapshot,
)


def coding_request_id(record_id: str, approval_id: str | None = None) -> str:
    anchor = approval_id or record_id
    safe = "".join(char for char in anchor if char.isalnum() or char in {"_", "-"})[:48]
    return f"req_coding_{safe or sha256(anchor.encode('utf-8')).hexdigest()[:16]}"


def _compact_paths(payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in (
        "relative_path",
        "source_relative_path",
        "target_relative_path",
        "destination_relative_path",
        "backup_relative_path",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value and not value.startswith("/"):
            paths.append(value[:240])
    return list(dict.fromkeys(paths))[:10]


def record_coding_trace(*, kind: str, record_id: str, payload: dict[str, Any], audit_persisted: bool) -> str:
    approval_id = str(payload.get("approval_id") or "") or (record_id if kind.startswith("approval") else None)
    request_id = coding_request_id(record_id, approval_id)
    status = str(payload.get("status") or "completed")
    blocked = status in {"blocked", "denied", "approval_required", "failed", "timeout", "cancelled", "cancel_requested"} or "blocked" in kind
    pending = status in {"queued", "running"}
    archive_operation = kind.startswith("archive_") or str(payload.get("operation_kind") or "").startswith("archive_")
    database_binary_operation = kind.startswith(("database_", "binary_")) or str(payload.get("operation_kind") or "").startswith(("database_", "binary_"))
    mutation = any(marker in kind for marker in ("apply", "edit", "mutation", "file_operation", "export", "backup")) or bool(payload.get("mutation_performed", False))
    shell_used = bool(payload.get("shell", False))
    approval_required = mutation or shell_used or bool(payload.get("approval_required", False))
    operator_approved = bool(payload.get("operator_approved", False))
    result_hash = payload.get("new_hash") or payload.get("new_content_hash") or payload.get("result_hash")
    source_hash = payload.get("source_hash") or payload.get("previous_hash") or payload.get("previous_content_hash") or payload.get("content_hash")
    plan_hash = payload.get("plan_hash") or payload.get("patch_hash")
    paths = _compact_paths(payload)
    backup_path = payload.get("backup_relative_path")
    backup_summary = f"Recoverable backup: {backup_path}" if isinstance(backup_path, str) and backup_path else None
    tool_entry = {
        "tool_key": f"coding.{kind}",
        "tool_label": "Governed coding operation",
        "tool_kind": "coding_operation",
        "state": "blocked" if blocked else "pending" if pending else "used",
        "available": True,
        "used": True,
        "approval_required": approval_required,
        "approval_state": "approved" if (approval_id or operator_approved) and not blocked else "denied" if blocked else "not_needed",
        "locality": "local",
        "boundary_kind": "private_snapshot_or_static_worker" if database_binary_operation else "host_or_sandbox" if archive_operation else "file_mutation" if mutation else "local_selected_file",
        "boundary_state": "blocked" if blocked else "pending" if pending else "completed",
        "operation": kind,
        "summary": f"{kind.replace('_', ' ')} {'was blocked' if blocked else f'is {status} locally' if pending else 'completed locally'}.",
        "mutated_files": mutation and not blocked and not archive_operation,
        "network_access_used": False,
        "private_context_sent": False,
        "shell_used": shell_used,
        "git_mutation_used": False,
        "cloud_used": False,
        "session_id": payload.get("session_id"),
        "operation_id": record_id,
        "approval_id": approval_id,
        "workspace_root_hash": payload.get("workspace_root_hash"),
        "relative_paths": paths,
        "source_hash": source_hash,
        "plan_hash": plan_hash,
        "result_hash": result_hash,
        "mutation_class": payload.get("allowed_mutation_class") or kind,
        "backup_summary": backup_summary,
        "audit_persisted": audit_persisted,
        "artifact_id": payload.get("artifact_id"),
        "model_id": payload.get("model_id"),
        "synthetic_media": bool(payload.get("synthetic_media", False)),
        "raw_content_logged": bool(payload.get("raw_content_logged", False)),
        "runtime_seconds": payload.get("runtime_seconds"),
        "peak_gpu_memory_mib": payload.get("peak_gpu_memory_mib"),
        "cancel_requested": bool(payload.get("cancel_requested", False)),
        "archive_type": payload.get("archive_type"),
        "archive_hash": payload.get("archive_hash"),
        "manifest_hash": payload.get("manifest_hash"),
        "member_count": payload.get("member_count") or 0,
        "risk_total": payload.get("risk_total") or 0,
        "selected_member_count": payload.get("selected_member_count") or 0,
        "sandbox_hash": payload.get("sandbox_hash"),
        "extracted_file_count": payload.get("extracted_file_count") or 0,
        "extracted_bytes": payload.get("extracted_bytes") or 0,
        "blocked_member_count": payload.get("blocked_member_count") or 0,
        "skipped_member_count": payload.get("skipped_member_count") or 0,
        "policy_version": payload.get("policy_version"),
        "database_engine": payload.get("database_engine"),
        "binary_format": payload.get("binary_format"),
        "snapshot_hash": payload.get("snapshot_hash"),
        "artifact_hash": payload.get("artifact_hash"),
        "table_count": payload.get("table_count") or 0,
        "view_count": payload.get("view_count") or 0,
        "index_count": payload.get("index_count") or 0,
        "trigger_count": payload.get("trigger_count") or 0,
        "schema_object_count": payload.get("schema_object_count") or 0,
        "section_count": payload.get("section_count") or 0,
        "import_count": payload.get("import_count") or 0,
        "export_count": payload.get("export_count") or 0,
        "symbol_count": payload.get("symbol_count") or 0,
        "string_count": payload.get("string_count") or 0,
        "sandbox_files_written": archive_operation and bool(payload.get("mutation_performed", False)) and not blocked,
        "project_files_mutated": False if archive_operation else mutation and not blocked,
    }
    start_request_trace(
        request_id=request_id,
        route_used=f"coding.{kind}",
        selected_mode="coding",
        ui_surface="codev_or_desktop",
        phase="coding_operation",
        label="Governed coding operation",
        detail=tool_entry["summary"],
    )
    update_request_trace_snapshot(
        request_id=request_id,
        route_used=f"coding.{kind}",
        ui_surface="codev_or_desktop",
        selected_mode="coding",
        locality_state="local",
        approval_state=tool_entry["approval_state"],
        approval_needed=tool_entry["approval_required"],
        execution_tool_kind="coding_operation",
        execution_status="blocked" if blocked else status if pending else "completed",
        execution_operation=kind,
        execution_summary=tool_entry["summary"],
    )
    update_request_trace_ledger_snapshot(
        request_id=request_id,
        tools_used=[tool_entry],
        mutated_files=tool_entry["mutated_files"],
        shell_used=shell_used,
        git_mutation_used=False,
        rollback_note=backup_summary,
    )
    if not pending:
        marker = mark_request_trace_blocked if blocked else mark_request_trace_completed
        marker(
            request_id=request_id,
            detail=tool_entry["summary"],
            selected_mode="coding",
            locality_state="local",
            approval_state=tool_entry["approval_state"],
            approval_needed=tool_entry["approval_required"],
            execution_tool_kind="coding_operation",
            execution_status="blocked" if blocked else "completed",
            execution_operation=kind,
            execution_summary=tool_entry["summary"],
        )
    return request_id


__all__ = ("coding_request_id", "record_coding_trace")
