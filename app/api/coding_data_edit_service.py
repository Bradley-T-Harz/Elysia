"""Governed data edit and mutation planning/execution."""

from __future__ import annotations

import csv
import json
import sqlite3
import xml.etree.ElementTree as ET
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.api.coding_audit_service import write_coding_audit_record
from app.api.coding_data_adapter_service import inspect_data_path
from app.api.coding_data_backup_service import copy_to_derived, create_backup
from app.api.coding_data_type_registry import detect_data_type
from app.api.coding_path_guard_service import guard_workspace_path
from app.api.coding_operation_hash_service import operation_plan_hash
from app.api.coding_operation_service import consume_operation_approval
from app.api.schemas.coding_data import CodingDataApplyRequest, CodingDataApplyResponse, CodingDataEditPlanRequest, CodingDataPlanResponse


def _hash_bytes(path: Path) -> str:
    digest = sha256()
    if path.is_dir():
        for child in sorted(item for item in path.rglob("*") if item.is_file()):
            digest.update(child.relative_to(path).as_posix().encode("utf-8"))
            digest.update(child.read_bytes()[:8192])
        return digest.hexdigest()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _read_table(path: Path, delimiter: str) -> tuple[list[str], list[dict[str, str]], str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    newline = "\r\n" if "\r\n" in text else "\n"
    rows = list(csv.DictReader(text.splitlines(), delimiter=delimiter))
    headers = list(rows[0].keys()) if rows else list(csv.reader(text.splitlines(), delimiter=delimiter).__next__()) if text.strip() else []
    return headers, rows, newline


def _write_table(path: Path, headers: list[str], rows: list[dict[str, Any]], delimiter: str, newline: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, delimiter=delimiter, lineterminator=newline)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def _plan_blocked(file_label: str, relative_path: str | None, action: str, reason: str, summary: str) -> CodingDataPlanResponse:
    return CodingDataPlanResponse(status="blocked", action=action, file_label=file_label, relative_path=relative_path, blocked_reason=reason, plan_summary=summary)


def plan_data_edit(payload: CodingDataEditPlanRequest) -> CodingDataPlanResponse:
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, allow_directory=True)
    file_label = guarded.target_path.name
    action = payload.operation
    if not guarded.allowed:
        return _plan_blocked(file_label, guarded.relative_path, action, guarded.reason or "path_blocked", "Data operation is blocked by workspace/path policy.")
    if not payload.approval_granted:
        return _plan_blocked(file_label, guarded.relative_path, action, "explicit_approval_required", "Data operation planning requires approval before source content is parsed.")
    guarded_descriptor = detect_data_type(guarded.target_path)
    if guarded_descriptor.database or guarded_descriptor.adapter == "databaseforge":
        return _plan_blocked(file_label, guarded.relative_path, action, "database_mutation_unavailable_by_design", "Database mutation is unavailable in Chunk 7; only exact-approved snapshot-first schema preview is live.")
    preview = inspect_data_path(guarded.target_path, max_rows=payload.max_rows or 50, max_features=payload.max_features or 25)
    descriptor = preview.descriptor
    allowed = action in descriptor.stable_operations
    if not allowed:
        return _plan_blocked(file_label, guarded.relative_path, action, "operation_not_supported_for_data_type", f"{action} is not a stable governed operation for {descriptor.label}.")
    implemented = (
        (descriptor.adapter == "tabular" and action.startswith("tabular_"))
        or (descriptor.adapter == "jsonl" and action.startswith("jsonl_"))
        or (descriptor.adapter == "sqlite" and action.startswith("sqlite_"))
        or (descriptor.adapter == "geojson" and action.startswith("geojson_"))
        or (descriptor.adapter == "kml" and action == "kml_rename_placemark")
        or action in {"vector_export_derived", "raster_update_tags", "netcdf_update_attr", "hdf5_update_attr", "zarr_update_attr"}
    )
    if not implemented:
        return _plan_blocked(file_label, guarded.relative_path, action, "operation_not_implemented_for_adapter", f"{action} is advertised by the registry but has no governed executor and is blocked.")
    if preview.blocked_reason:
        return _plan_blocked(file_label, guarded.relative_path, action, preview.blocked_reason, "Data operation is blocked by data safety policy.")
    details = {"operation": action, "data_type_id": descriptor.type_id, "parameters": payload.parameters}
    transaction = {"required": descriptor.mutation_requires_transaction, "mode": "sqlite_transaction" if descriptor.database else "file_rewrite"}
    backup = {"required": descriptor.mutation_requires_backup, "derived_copy_preferred": descriptor.derived_copy_preferred}
    target_path = payload.parameters.get("target_path") if isinstance(payload.parameters, dict) else None
    target_relative = None
    if target_path:
        target_guard = guard_workspace_path(workspace_root=payload.workspace_root, target_path=str(target_path), require_existing=False, allow_directory=True)
        if not target_guard.allowed:
            return _plan_blocked(file_label, guarded.relative_path, action, target_guard.reason or "target_path_blocked", "Derived data target is blocked by workspace/path policy.")
        target_relative = target_guard.relative_path
    return CodingDataPlanResponse(
        status="planned",
        action=action,
        file_label=file_label,
        relative_path=guarded.relative_path,
        target_relative_path=target_relative,
        plan_summary=f"Plan governed {action} for {guarded.relative_path}; approval, source hash validation, backup/transaction, and audit are required.",
        source_hash=preview.content_hash,
        plan_hash=operation_plan_hash(
            action="data_edit",
            source_relative_path=guarded.relative_path,
            target_relative_path=target_relative,
            source_hash=preview.content_hash,
            details=details,
        ),
        operation_details=details,
        transaction=transaction,
        backup=backup,
        warnings=preview.warnings + ["No mutation has been performed. Approved execution remains local, path-guarded, and audited."],
    )


def _apply_tabular(path: Path, descriptor_type: str, operation: str, params: dict[str, Any]) -> dict[str, Any]:
    delimiter = "\t" if descriptor_type == "tsv_table" else ","
    headers, rows, newline = _read_table(path, delimiter)
    if operation == "tabular_append_row":
        row = dict(params.get("row") or {})
        for key in row:
            if key not in headers:
                headers.append(key)
        rows.append(row)
    elif operation == "tabular_update_cell":
        index = int(params["row_index"])
        column = str(params["column"])
        if column not in headers:
            raise ValueError("unknown_column")
        rows[index][column] = str(params.get("value", ""))
    elif operation == "tabular_delete_row":
        rows.pop(int(params["row_index"]))
    elif operation == "tabular_add_column":
        column = str(params["column"])
        if column in headers:
            raise ValueError("column_exists")
        headers.append(column)
        default = str(params.get("default", ""))
        for row in rows:
            row[column] = default
    elif operation == "tabular_rename_column":
        old = str(params["old_column"])
        new = str(params["new_column"])
        if old not in headers:
            raise ValueError("unknown_column")
        headers = [new if item == old else item for item in headers]
        for row in rows:
            row[new] = row.pop(old, "")
    else:
        raise ValueError("unsupported_tabular_operation")
    _write_table(path, headers, rows, delimiter, newline)
    return {"row_count": len(rows), "columns": headers}


def _apply_jsonl(path: Path, operation: str, params: dict[str, Any]) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if operation == "jsonl_append_record":
        record = params.get("record")
        if not isinstance(record, dict):
            raise ValueError("record_object_required")
        lines.append(json.dumps(record, sort_keys=True))
    elif operation in {"jsonl_update_record", "jsonl_repair_record"}:
        index = int(params["line_index"])
        record = params.get("record")
        if not isinstance(record, dict):
            raise ValueError("record_object_required")
        lines[index] = json.dumps(record, sort_keys=True)
    elif operation == "jsonl_delete_record":
        lines.pop(int(params["line_index"]))
    else:
        raise ValueError("unsupported_jsonl_operation")
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return {"line_count": len(lines)}


def _quote_identifier(name: str) -> str:
    if not name or "\x00" in name:
        raise ValueError("invalid_identifier")
    return '"' + name.replace('"', '""') + '"'


def _apply_sqlite(path: Path, operation: str, params: dict[str, Any]) -> dict[str, Any]:
    connection = sqlite3.connect(path)
    try:
        connection.execute("BEGIN")
        if operation == "sqlite_insert_row":
            table = _quote_identifier(str(params["table"]))
            row = dict(params.get("row") or {})
            columns = list(row.keys())
            sql = f"INSERT INTO {table} ({', '.join(_quote_identifier(c) for c in columns)}) VALUES ({', '.join('?' for _ in columns)})"
            connection.execute(sql, [row[column] for column in columns])
        elif operation == "sqlite_update_row":
            table = _quote_identifier(str(params["table"]))
            row = dict(params.get("values") or {})
            selector = dict(params.get("selector") or {})
            if not row or not selector:
                raise ValueError("values_and_exact_selector_required")
            sql = f"UPDATE {table} SET {', '.join(_quote_identifier(c) + ' = ?' for c in row)} WHERE {' AND '.join(_quote_identifier(c) + ' = ?' for c in selector)}"
            connection.execute(sql, [*row.values(), *selector.values()])
        elif operation == "sqlite_delete_row":
            table = _quote_identifier(str(params["table"]))
            selector = dict(params.get("selector") or {})
            if not selector:
                raise ValueError("exact_selector_required")
            sql = f"DELETE FROM {table} WHERE {' AND '.join(_quote_identifier(c) + ' = ?' for c in selector)}"
            connection.execute(sql, list(selector.values()))
        elif operation == "sqlite_create_table":
            table = _quote_identifier(str(params["table"]))
            columns = params.get("columns")
            if not isinstance(columns, list) or not columns:
                raise ValueError("columns_required")
            allowed_types = {"TEXT", "INTEGER", "REAL", "BLOB", "NUMERIC"}
            parts = []
            for column in columns:
                name = _quote_identifier(str(column["name"]))
                type_name = str(column.get("type") or "TEXT").upper()
                if type_name not in allowed_types:
                    raise ValueError("unsupported_column_type")
                parts.append(f"{name} {type_name}")
            connection.execute(f"CREATE TABLE {table} ({', '.join(parts)})")
        elif operation == "sqlite_add_column":
            type_name = str(params.get("type") or "TEXT").upper()
            if type_name not in {"TEXT", "INTEGER", "REAL", "BLOB", "NUMERIC"}:
                raise ValueError("unsupported_column_type")
            connection.execute(f"ALTER TABLE {_quote_identifier(str(params['table']))} ADD COLUMN {_quote_identifier(str(params['column']))} {type_name}")
        elif operation == "sqlite_create_index":
            connection.execute(f"CREATE INDEX {_quote_identifier(str(params['index']))} ON {_quote_identifier(str(params['table']))} ({', '.join(_quote_identifier(str(c)) for c in params.get('columns', []))})")
        elif operation == "sqlite_drop_index":
            connection.execute(f"DROP INDEX {_quote_identifier(str(params['index']))}")
        else:
            raise ValueError("unsupported_sqlite_operation")
        changes = connection.total_changes
        connection.commit()
        return {"sqlite_changes": changes}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _apply_geojson(path: Path, operation: str, params: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.setdefault("features", [])
    if operation == "geojson_append_feature":
        feature = params.get("feature")
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("valid_feature_required")
        features.append(feature)
    elif operation == "geojson_update_properties":
        index = int(params["feature_index"])
        props = dict(params.get("properties") or {})
        features[index].setdefault("properties", {}).update(props)
    elif operation == "geojson_delete_feature":
        features.pop(int(params["feature_index"]))
    else:
        raise ValueError("unsupported_geojson_operation")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return {"feature_count": len(features)}


def _apply_kml(path: Path, operation: str, params: dict[str, Any]) -> dict[str, Any]:
    if operation != "kml_rename_placemark":
        raise ValueError("unsupported_kml_operation")
    tree = ET.parse(path)
    root = tree.getroot()
    index = int(params["placemark_index"])
    new_name = str(params["name"])
    placemarks = [elem for elem in root.iter() if elem.tag.rsplit("}", 1)[-1] == "Placemark"]
    placemark = placemarks[index]
    name_elem = next((child for child in placemark if child.tag.rsplit("}", 1)[-1] == "name"), None)
    if name_elem is None:
        name_elem = ET.SubElement(placemark, "name")
    name_elem.text = new_name
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return {"placemark_count": len(placemarks), "renamed_index": index}


def _required_target(workspace_root: str, params: dict[str, Any]) -> Path:
    target_path = params.get("target_path")
    if not isinstance(target_path, str) or not target_path.strip():
        raise ValueError("target_path_required_for_derived_copy")
    target = guard_workspace_path(workspace_root=workspace_root, target_path=target_path, require_existing=False, allow_directory=True)
    if not target.allowed:
        raise ValueError(target.reason or "target_path_blocked")
    if target.target_path.exists():
        raise ValueError("target_path_exists")
    return target.target_path


def _apply_vector_derived(path: Path, workspace_root: str, params: dict[str, Any]) -> dict[str, Any]:
    import geopandas as gpd
    target = _required_target(workspace_root, params)
    layer = params.get("layer")
    frame = gpd.read_file(path, layer=str(layer) if layer else None)
    target.parent.mkdir(parents=True, exist_ok=True)
    driver = "GeoJSON" if target.suffix.lower() == ".geojson" else None
    frame.to_file(target, driver=driver)
    return {"target_path": target.relative_to(Path(workspace_root).resolve()).as_posix(), "feature_count": int(len(frame)), "columns": list(frame.columns)}


def _apply_raster_update_tags(path: Path, workspace_root: str, params: dict[str, Any]) -> dict[str, Any]:
    import rasterio
    target = _required_target(workspace_root, params)
    tags = params.get("tags")
    if not isinstance(tags, dict) or not tags:
        raise ValueError("tags_required")
    copy_to_derived(path, target)
    with rasterio.open(target, "r+") as dataset:
        dataset.update_tags(**{str(key): str(value) for key, value in tags.items()})
    return {"target_path": target.relative_to(Path(workspace_root).resolve()).as_posix(), "tags_updated": sorted(str(key) for key in tags)}


def _apply_netcdf_update_attr(path: Path, workspace_root: str, params: dict[str, Any]) -> dict[str, Any]:
    import h5netcdf

    target = _required_target(workspace_root, params)
    attr_name = str(params["attr_name"])
    attr_value = params.get("value", "")
    variable = params.get("variable")
    copy_to_derived(path, target)
    with h5netcdf.File(target, "a") as dataset:
        if variable:
            dataset.variables[str(variable)].attrs[attr_name] = attr_value
            scope = f"variable:{variable}"
        else:
            dataset.attrs[attr_name] = attr_value
            scope = "global"
    return {"target_path": target.relative_to(Path(workspace_root).resolve()).as_posix(), "scope": scope, "attr_name": attr_name}


def _apply_hdf5_update_attr(path: Path, workspace_root: str, params: dict[str, Any]) -> dict[str, Any]:
    import h5py
    target = _required_target(workspace_root, params)
    object_path = str(params.get("object_path") or "/")
    attr_name = str(params["attr_name"])
    attr_value = params.get("value", "")
    copy_to_derived(path, target)
    with h5py.File(target, "a") as handle:
        obj = handle[object_path] if object_path != "/" else handle
        obj.attrs[attr_name] = attr_value
    return {"target_path": target.relative_to(Path(workspace_root).resolve()).as_posix(), "object_path": object_path, "attr_name": attr_name}


def _apply_zarr_update_attr(path: Path, workspace_root: str, params: dict[str, Any]) -> dict[str, Any]:
    target = _required_target(workspace_root, params)
    object_path = str(params.get("object_path") or "/")
    attr_name = str(params["attr_name"])
    attr_value = params.get("value", "")
    copy_to_derived(path, target)
    attrs_path = target / ".zattrs" if object_path == "/" else target / object_path.strip("/") / ".zattrs"
    if not attrs_path.parent.exists():
        raise ValueError("zarr_object_path_not_found")
    attrs = json.loads(attrs_path.read_text(encoding="utf-8")) if attrs_path.exists() else {}
    if not isinstance(attrs, dict):
        raise ValueError("zarr_attrs_not_object")
    attrs[attr_name] = attr_value
    attrs_path.write_text(json.dumps(attrs, indent=2, sort_keys=True), encoding="utf-8")
    return {"target_path": target.relative_to(Path(workspace_root).resolve()).as_posix(), "object_path": object_path, "attr_name": attr_name}


def apply_data_edit(payload: CodingDataApplyRequest) -> CodingDataApplyResponse:
    plan = plan_data_edit(payload)
    if plan.status != "planned":
        return CodingDataApplyResponse(status=plan.status, action=plan.action, file_label=plan.file_label, relative_path=plan.relative_path, blocked_reason=plan.blocked_reason, warnings=plan.warnings)
    if not payload.operator_approved:
        return CodingDataApplyResponse(status="approval_required", action=payload.operation, file_label=plan.file_label, relative_path=plan.relative_path, blocked_reason="operator_approval_required", warnings=["Data mutation requires explicit operator approval."])
    if not payload.expected_source_hash:
        return CodingDataApplyResponse(status="blocked", action=payload.operation, file_label=plan.file_label, relative_path=plan.relative_path, blocked_reason="expected_source_hash_required", warnings=["Data mutations require the exact planned source hash."])
    if payload.expected_source_hash != plan.source_hash:
        return CodingDataApplyResponse(status="blocked", action=payload.operation, file_label=plan.file_label, relative_path=plan.relative_path, blocked_reason="source_hash_mismatch", warnings=["Re-inspect the data file before applying mutation."])
    guarded = guard_workspace_path(workspace_root=payload.workspace_root, target_path=payload.file_path, allow_directory=True)
    descriptor = detect_data_type(guarded.target_path)
    previous_hash = _hash_bytes(guarded.target_path) if guarded.target_path.is_file() else plan.source_hash
    if plan.target_relative_path:
        derived_target = guard_workspace_path(workspace_root=payload.workspace_root, target_path=plan.target_relative_path, require_existing=False, allow_directory=True)
        if not derived_target.allowed:
            return CodingDataApplyResponse(status="blocked", action=payload.operation, file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=derived_target.relative_path, blocked_reason=derived_target.reason)
        if derived_target.target_path.exists():
            return CodingDataApplyResponse(status="blocked", action=payload.operation, file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=derived_target.relative_path, blocked_reason="target_exists", warnings=["Derived data operations never overwrite an existing target."])
    exact_files = [payload.file_path]
    if plan.target_relative_path:
        exact_files.append(plan.target_relative_path)
    approval = consume_operation_approval(
        approval_id=payload.approval_id,
        approval_token=payload.approval_token,
        operation_kind="data_edit",
        workspace_root=payload.workspace_root,
        exact_files=exact_files,
        source_hash=plan.source_hash,
        plan_hash=plan.plan_hash or "",
        allowed_mutation_class="data_edit",
    )
    if not approval.allowed:
        return CodingDataApplyResponse(status="approval_required", action=payload.operation, file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, approval_id=payload.approval_id, blocked_reason=approval.reason, warnings=["A matching one-time data approval is required."])
    backup = create_backup(guarded.target_path) if descriptor.mutation_requires_backup else {"created": False}
    try:
        if descriptor.adapter == "tabular":
            details = _apply_tabular(guarded.target_path, descriptor.type_id, payload.operation, payload.parameters)
        elif descriptor.adapter == "jsonl":
            details = _apply_jsonl(guarded.target_path, payload.operation, payload.parameters)
        elif descriptor.adapter == "sqlite":
            details = _apply_sqlite(guarded.target_path, payload.operation, payload.parameters)
        elif descriptor.adapter == "geojson":
            details = _apply_geojson(guarded.target_path, payload.operation, payload.parameters)
        elif descriptor.adapter == "kml":
            details = _apply_kml(guarded.target_path, payload.operation, payload.parameters)
        elif payload.operation == "vector_export_derived":
            details = _apply_vector_derived(guarded.target_path, payload.workspace_root, payload.parameters)
        elif payload.operation == "raster_update_tags":
            details = _apply_raster_update_tags(guarded.target_path, payload.workspace_root, payload.parameters)
        elif payload.operation == "netcdf_update_attr":
            details = _apply_netcdf_update_attr(guarded.target_path, payload.workspace_root, payload.parameters)
        elif payload.operation == "hdf5_update_attr":
            details = _apply_hdf5_update_attr(guarded.target_path, payload.workspace_root, payload.parameters)
        elif payload.operation == "zarr_update_attr":
            details = _apply_zarr_update_attr(guarded.target_path, payload.workspace_root, payload.parameters)
        else:
            raise ValueError("operation_not_implemented_for_adapter")
    except Exception as exc:
        return CodingDataApplyResponse(status="blocked", action=payload.operation, file_label=plan.file_label, relative_path=plan.relative_path, blocked_reason=f"data_mutation_failed:{exc}", previous_hash=previous_hash, backup=backup, warnings=["Mutation failed; backup remains available if it was created."])
    target_relative = details.get("target_path") if isinstance(details, dict) else None
    target_absolute = (Path(payload.workspace_root).resolve() / str(target_relative)).resolve() if target_relative else None
    if target_absolute and target_absolute.exists():
        new_hash = _hash_bytes(target_absolute)
        rollback_note = f"Delete derived output {target_relative} to remove the approved copy; source file was preserved."
    else:
        new_hash = _hash_bytes(guarded.target_path) if guarded.target_path.is_file() else _hash_text(json.dumps(details, sort_keys=True))
        rollback_note = str(backup.get("rollback_note") or "Use project version control/backups to restore the previous dataset.")
    audit_written = write_coding_audit_record("data_mutation", uuid4().hex[:16], {"session_id": payload.session_id, "approval_id": payload.approval_id, "plan_hash": plan.plan_hash, "operation": payload.operation, "relative_path": guarded.relative_path, "data_type": descriptor.type_id, "previous_hash": previous_hash, "new_hash": new_hash, "backup": backup, "details": {k: v for k, v in details.items() if k not in {"rows", "records", "features"}}})
    return CodingDataApplyResponse(status="applied", action=payload.operation, file_label=plan.file_label, relative_path=plan.relative_path, target_relative_path=plan.target_relative_path, mutation_performed=True, audit_written=audit_written, previous_hash=previous_hash, new_hash=new_hash, approval_id=payload.approval_id, operation_details=details, transaction=plan.transaction, backup=backup, warnings=["Approved data operation completed locally through the governed adapter. No shell, package manager, cloud, or arbitrary SQL was used."], rollback_note=rollback_note)


__all__ = ("apply_data_edit", "plan_data_edit")
