"""Local audit writer for coding bridge approval/result records."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from typing import Any

from app.api.project_paths import state_path


_DEFAULT_AUDIT_ROOT = state_path("audit", "coding")
AUDIT_ROOT = _DEFAULT_AUDIT_ROOT


def coding_audit_root() -> Path:
    """Return the configured audit root without forcing test state into the repo."""
    if AUDIT_ROOT != _DEFAULT_AUDIT_ROOT:
        return Path(AUDIT_ROOT)
    configured = os.environ.get("ELYSIA_CODING_AUDIT_ROOT", "").strip()
    return Path(configured).expanduser() if configured else _DEFAULT_AUDIT_ROOT


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _secure_existing_coding_audit_storage(audit_root: Path) -> None:
    """Keep upgraded installs from retaining legacy group/world-readable receipts."""
    audit_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(audit_root, 0o700)
    for existing in audit_root.glob("*.json"):
        if existing.is_file() and not existing.is_symlink():
            os.chmod(existing, 0o600)


def write_coding_audit_record(kind: str, record_id: str, payload: dict[str, Any]) -> bool:
    audit_root = coding_audit_root()
    _secure_existing_coding_audit_storage(audit_root)
    safe_kind = "".join(char for char in kind if char.isalnum() or char in {"_", "-"}) or "record"
    safe_id = "".join(char for char in record_id if char.isalnum() or char in {"_", "-"})
    path = audit_root / f"{safe_kind}_{safe_id}.json"
    from app.api.coding_trace_service import coding_request_id, record_coding_trace

    approval_id = str(payload.get("approval_id") or "") or (safe_id if safe_kind.startswith("approval") else None)
    request_id = coding_request_id(safe_id, approval_id)
    record = {
        "kind": safe_kind,
        "operation_id": safe_id,
        "request_id": request_id,
        "recorded_at_utc": utc_now_iso(),
        "payload": payload,
    }
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=audit_root,
        prefix=".coding-audit-",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    try:
        record_coding_trace(kind=safe_kind, record_id=safe_id, payload=payload, audit_persisted=True)
    except Exception:
        # Durable compact audit truth must not be lost if the in-memory trace is unavailable.
        pass
    return True


_AUDIT_PAYLOAD_KEYS = {
    "session_id",
    "approval_id",
    "operation_kind",
    "operation",
    "status",
    "relative_path",
    "source_relative_path",
    "target_relative_path",
    "destination_relative_path",
    "backup_relative_path",
    "rollback_receipt_id",
    "workspace_root_hash",
    "source_hash",
    "previous_hash",
    "previous_content_hash",
    "plan_hash",
    "patch_hash",
    "new_hash",
    "new_content_hash",
    "allowed_mutation_class",
    "operator_approved",
    "approval_required",
    "shell",
    "exit_code",
    "format",
    "media_family",
    "size_bytes",
    "duration_seconds",
    "runtime_seconds",
    "peak_gpu_memory_mib",
    "stream_count",
    "thumbnail_status",
    "privacy_flags_present",
    "artifact_id",
    "model_id",
    "language",
    "segment_count",
    "text_length",
    "voice_id",
    "synthetic_media",
    "production_enabled",
    "raw_content_logged",
    "cancel_requested",
    "result_hash",
    "mutation_performed",
    "network",
    "path_hash",
    "archive_type",
    "archive_hash",
    "member_count",
    "risk_total",
    "manifest_hash",
    "selected_member_count",
    "sandbox_hash",
    "policy_version",
    "tool_used",
    "extracted_file_count",
    "extracted_bytes",
    "blocked_member_count",
    "skipped_member_count",
    "exact_file_count",
    "exact_files_digest",
    "database_engine",
    "binary_format",
    "snapshot_hash",
    "source_state_digest",
    "artifact_hash",
    "table_count",
    "view_count",
    "index_count",
    "trigger_count",
    "schema_object_count",
    "section_count",
    "import_count",
    "export_count",
    "symbol_count",
    "string_count",
    "row_data_returned",
    "arbitrary_sql_executed",
    "loading_performed",
    "engineering_format",
    "engineering_family",
    "external_reference_count",
    "worker_key",
    "worker_state",
    "source_mutated",
    "scripts_executed",
    "plugins_loaded",
    "physical_output_performed",
}


def _compact_audit_record(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    compact_payload = {key: payload[key] for key in _AUDIT_PAYLOAD_KEYS if key in payload and not isinstance(payload[key], (dict, list))}
    return {
        "kind": str(record.get("kind") or ""),
        "operation_id": str(record.get("operation_id") or ""),
        "request_id": str(record.get("request_id") or ""),
        "recorded_at_utc": str(record.get("recorded_at_utc") or ""),
        **compact_payload,
        "payload": compact_payload,
    }


def list_coding_audit_records(*, limit: int = 100, kind: str | None = None) -> list[dict[str, Any]]:
    root = coding_audit_root()
    if not root.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        compact = _compact_audit_record(record if isinstance(record, dict) else {})
        if kind and compact["kind"] != kind:
            continue
        records.append(compact)
        if len(records) >= max(1, min(limit, 200)):
            break
    return records


def get_coding_audit_record(operation_id: str) -> dict[str, Any] | None:
    safe_id = "".join(char for char in operation_id if char.isalnum() or char in {"_", "-"})
    if not safe_id or safe_id != operation_id:
        return None
    for record in list_coding_audit_records(limit=200):
        if record["operation_id"] == safe_id:
            return record
    return None


__all__ = ("AUDIT_ROOT", "coding_audit_root", "get_coding_audit_record", "list_coding_audit_records", "utc_now_iso", "write_coding_audit_record")
