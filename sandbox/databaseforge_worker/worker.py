"""Snapshot-first, fixed-query database inspection worker.

This module has no arbitrary SQL input and no source mutation operation.
"""

from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any
from urllib.parse import quote


class DatabaseWorkerError(RuntimeError):
    """Raised when fixed database inspection cannot complete safely."""


def _regular_source(path: Path, max_input_bytes: int) -> Path:
    if path.is_symlink():
        raise DatabaseWorkerError("source_must_be_regular_non_symlink_file")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise DatabaseWorkerError("source_must_be_regular_non_symlink_file")
    if resolved.stat().st_size > max_input_bytes:
        raise DatabaseWorkerError("database_input_limit_exceeded")
    return resolved


def _hashes(path: Path) -> tuple[str, str | None]:
    sha = sha256()
    try:
        import blake3

        b3: Any = blake3.blake3()
    except Exception:
        b3 = None
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
            if b3 is not None:
                b3.update(chunk)
    return sha.hexdigest(), b3.hexdigest() if b3 is not None else None


def _magic(path: Path) -> str:
    try:
        import magic

        return str(magic.from_file(str(path)))[:240]
    except Exception:
        return "magic_unavailable"


def metadata(path: Path, *, max_input_bytes: int) -> dict[str, Any]:
    source = _regular_source(path, max_input_bytes)
    with source.open("rb") as stream:
        header = stream.read(32)
    engine = "sqlite" if header.startswith(b"SQLite format 3\x00") else "duckdb" if len(header) >= 12 and header[8:12] == b"DUCK" else "unknown"
    digest, blake3_digest = _hashes(source)
    magic_summary = _magic(source)
    return {
        "engine": engine,
        "sha256": digest,
        "blake3": blake3_digest,
        "size_bytes": source.stat().st_size,
        "magic_summary": magic_summary,
        "toolchain": ["python_hashlib", "python_magic" if magic_summary != "magic_unavailable" else "header_signature"],
    }


def _snapshot_target(path: Path) -> Path:
    resolved_parent = path.parent.resolve(strict=True)
    if path.exists() or path.is_symlink():
        raise DatabaseWorkerError("snapshot_target_must_not_exist")
    if not resolved_parent.is_dir():
        raise DatabaseWorkerError("snapshot_parent_invalid")
    return resolved_parent / path.name


def _sqlite_uri(path: Path, *, immutable: bool = False) -> str:
    suffix = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    return f"file:{quote(path.as_posix(), safe='/')}" + suffix


def _sqlite_snapshot(source: Path, snapshot: Path) -> None:
    source_connection = sqlite3.connect(_sqlite_uri(source), uri=True, timeout=2.0)
    target_connection: sqlite3.Connection | None = None
    try:
        source_connection.enable_load_extension(False)
        source_connection.execute("PRAGMA query_only=ON")
        target_connection = sqlite3.connect(snapshot)
        source_connection.backup(target_connection, pages=128, sleep=0.01)
    finally:
        if target_connection is not None:
            target_connection.close()
        source_connection.close()
    snapshot.chmod(0o400)


def _bounded_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    return str(value)[:limit]


def _sqlite_schema(snapshot: Path, limits: dict[str, int]) -> dict[str, Any]:
    connection = sqlite3.connect(_sqlite_uri(snapshot, immutable=True), uri=True, timeout=2.0)
    connection.row_factory = sqlite3.Row
    try:
        connection.enable_load_extension(False)
        connection.execute("PRAGMA query_only=ON")
        integrity = str(connection.execute("PRAGMA quick_check(1)").fetchone()[0])
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        objects = connection.execute(
            "SELECT name, type, tbl_name, sql FROM sqlite_schema "
            "WHERE type IN ('table','view','index','trigger') ORDER BY type, name LIMIT ?",
            (limits["max_schema_objects"] + 1,),
        ).fetchall()
        truncated = len(objects) > limits["max_schema_objects"]
        objects = objects[: limits["max_schema_objects"]]
        detailed: list[dict[str, Any]] = []
        foreign_key_total = 0
        index_total = 0
        risk_counts: dict[str, int] = {}
        sensitive_markers = ("secret", "token", "password", "diagnos", "medical", "tax", "email", "credential", "identity")
        for row in objects:
            name = str(row["name"])
            item: dict[str, Any] = {
                "name": name,
                "type": str(row["type"]),
                "table_name": str(row["tbl_name"]),
                "schema_sql": _bounded_text(row["sql"], limits["max_schema_sql_chars"]),
            }
            if any(marker in name.lower() for marker in sensitive_markers):
                risk_counts["sensitive_schema_name"] = risk_counts.get("sensitive_schema_name", 0) + 1
            if row["type"] in {"table", "view"}:
                columns = connection.execute(
                    "SELECT cid, name, type, \"notnull\", dflt_value, pk, hidden FROM pragma_table_xinfo(?) LIMIT ?",
                    (name, limits["max_columns_per_object"] + 1),
                ).fetchall()
                item["columns_truncated"] = len(columns) > limits["max_columns_per_object"]
                item["columns"] = [dict(value) for value in columns[: limits["max_columns_per_object"]]]
                foreign_keys = connection.execute(
                    "SELECT id, seq, \"table\", \"from\", \"to\", on_update, on_delete, match FROM pragma_foreign_key_list(?) LIMIT ?",
                    (name, limits["max_foreign_keys"] + 1),
                ).fetchall()
                item["foreign_keys"] = [dict(value) for value in foreign_keys[: limits["max_foreign_keys"]]]
                foreign_key_total += len(item["foreign_keys"])
                indexes = connection.execute(
                    "SELECT seq, name, \"unique\", origin, partial FROM pragma_index_list(?) LIMIT ?",
                    (name, limits["max_indexes"] + 1),
                ).fetchall()
                item["indexes"] = [dict(value) for value in indexes[: limits["max_indexes"]]]
                index_total += len(item["indexes"])
            detailed.append(item)
        counts = {kind: sum(1 for row in objects if row["type"] == kind) for kind in ("table", "view", "index", "trigger")}
        if counts["trigger"]:
            risk_counts["triggers_present"] = counts["trigger"]
        if truncated:
            risk_counts["schema_object_limit_reached"] = 1
        return {
            "engine": "sqlite",
            "engine_version": sqlite3.sqlite_version,
            "integrity_check": integrity,
            "page_size": page_size,
            "counts": counts,
            "schema_object_count": len(objects),
            "foreign_key_count": foreign_key_total,
            "index_reference_count": index_total,
            "objects": detailed,
            "schema_truncated": truncated,
            "risk_counts": risk_counts,
            "row_data_returned": False,
            "arbitrary_sql_executed": False,
        }
    finally:
        connection.close()


def _duckdb_snapshot(source: Path, snapshot: Path) -> None:
    shutil.copyfile(source, snapshot)
    snapshot.chmod(0o400)


def _duckdb_schema(snapshot: Path, limits: dict[str, int]) -> dict[str, Any]:
    try:
        import duckdb
    except Exception as exc:
        raise DatabaseWorkerError("duckdb_dependency_unavailable") from exc
    config = {"enable_external_access": "false", "allow_unsigned_extensions": "false", "autoinstall_known_extensions": "false", "autoload_known_extensions": "false"}
    connection = duckdb.connect(database=str(snapshot), read_only=True, config=config)
    try:
        object_rows = connection.execute(
            "SELECT table_schema, table_name, table_type FROM information_schema.tables "
            "WHERE table_schema <> 'information_schema' ORDER BY table_schema, table_name LIMIT ?",
            [limits["max_schema_objects"] + 1],
        ).fetchall()
        truncated = len(object_rows) > limits["max_schema_objects"]
        object_rows = object_rows[: limits["max_schema_objects"]]
        objects: list[dict[str, Any]] = []
        risk_counts: dict[str, int] = {}
        sensitive_markers = ("secret", "token", "password", "diagnos", "medical", "tax", "email", "credential", "identity")
        for schema_name, table_name, table_type in object_rows:
            columns = connection.execute(
                "SELECT column_name, data_type, is_nullable, column_default, ordinal_position "
                "FROM information_schema.columns WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position LIMIT ?",
                [schema_name, table_name, limits["max_columns_per_object"] + 1],
            ).fetchall()
            if any(marker in str(table_name).lower() for marker in sensitive_markers):
                risk_counts["sensitive_schema_name"] = risk_counts.get("sensitive_schema_name", 0) + 1
            objects.append({
                "schema": str(schema_name),
                "name": str(table_name),
                "type": str(table_type),
                "columns_truncated": len(columns) > limits["max_columns_per_object"],
                "columns": [
                    {"name": str(value[0]), "type": str(value[1]), "nullable": str(value[2]), "default": _bounded_text(value[3], limits["max_schema_sql_chars"]), "ordinal": int(value[4])}
                    for value in columns[: limits["max_columns_per_object"]]
                ],
            })
        try:
            index_rows = connection.execute("SELECT schema_name, table_name, index_name, is_unique FROM duckdb_indexes() LIMIT ?", [limits["max_indexes"] + 1]).fetchall()
        except Exception:
            index_rows = []
        table_count = sum(1 for value in object_rows if str(value[2]).upper() == "BASE TABLE")
        view_count = len(object_rows) - table_count
        if truncated:
            risk_counts["schema_object_limit_reached"] = 1
        return {
            "engine": "duckdb",
            "engine_version": str(duckdb.__version__),
            "counts": {"table": table_count, "view": view_count, "index": min(len(index_rows), limits["max_indexes"]), "trigger": 0},
            "schema_object_count": len(object_rows),
            "objects": objects,
            "indexes": [{"schema": str(value[0]), "table": str(value[1]), "name": str(value[2]), "unique": bool(value[3])} for value in index_rows[: limits["max_indexes"]]],
            "schema_truncated": truncated,
            "risk_counts": risk_counts,
            "external_access_enabled": False,
            "extension_install_load_used": False,
            "row_data_returned": False,
            "arbitrary_sql_executed": False,
        }
    finally:
        connection.close()


def snapshot_schema(source_path: Path, snapshot_path: Path, *, engine: str, limits: dict[str, int]) -> dict[str, Any]:
    source = _regular_source(source_path, limits["max_input_bytes"])
    snapshot = _snapshot_target(snapshot_path)
    if engine == "sqlite":
        _sqlite_snapshot(source, snapshot)
        strategy = "sqlite_read_only_backup"
        schema = _sqlite_schema(snapshot, limits)
    elif engine == "duckdb":
        _duckdb_snapshot(source, snapshot)
        strategy = "private_file_copy"
        schema = _duckdb_schema(snapshot, limits)
    else:
        raise DatabaseWorkerError("unsupported_database_engine")
    snapshot_sha256, _ = _hashes(snapshot)
    return {"snapshot_sha256": snapshot_sha256, "snapshot_strategy": strategy, "schema": schema, "source_mutated": False, "network_used": False}


__all__ = ("DatabaseWorkerError", "metadata", "snapshot_schema")
