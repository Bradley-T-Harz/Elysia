"""Canonical DatabaseForge format and authority registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.api.schemas.database_binary import DatabaseTypeDescriptor


SQLITE_HEADER = b"SQLite format 3\x00"

DATABASE_TYPES: dict[str, DatabaseTypeDescriptor] = {
    "sqlite": DatabaseTypeDescriptor(
        type_id="sqlite",
        label="SQLite database",
        extensions=[".sqlite", ".sqlite3", ".db"],
        schema_preview_state="approval_required",
        read_only_open_supported=True,
        notes=["Schema only, exact-approved, snapshot-first; row data and mutation are unavailable."],
    ),
    "duckdb": DatabaseTypeDescriptor(
        type_id="duckdb",
        label="DuckDB database",
        extensions=[".duckdb", ".db"],
        schema_preview_state="approval_required",
        read_only_open_supported=True,
        notes=["Fixed introspection only; extensions, external access, SQL, export, and mutation are unavailable."],
    ),
    "db_unknown": DatabaseTypeDescriptor(
        type_id="db_unknown",
        label="Unknown database-like file",
        extensions=[".db"],
        metadata_state="metadata_only",
        schema_preview_state="blocked",
        read_only_open_supported=False,
        notes=["The .db extension is ambiguous; no database engine is assumed without content evidence."],
    ),
    "database_unknown": DatabaseTypeDescriptor(
        type_id="database_unknown",
        label="Unrecognized database file",
        extensions=[],
        metadata_state="metadata_only",
        schema_preview_state="blocked",
        read_only_open_supported=False,
        notes=["Metadata only because the engine could not be safely identified."],
    ),
}
DATABASE_EXTENSIONS = {extension for descriptor in DATABASE_TYPES.values() for extension in descriptor.extensions}


def database_type_from_extension(path: Path | str) -> str:
    suffix = Path(str(path)).suffix.lower()
    if suffix in {".sqlite", ".sqlite3"}:
        return "sqlite"
    if suffix == ".duckdb":
        return "duckdb"
    if suffix == ".db":
        return "db_unknown"
    return "database_unknown"


def detect_database_engine(path: Path) -> tuple[str, str]:
    try:
        with path.open("rb") as stream:
            header = stream.read(32)
    except OSError:
        return "unknown", "unreadable"
    if header.startswith(SQLITE_HEADER):
        return "sqlite", "SQLite format 3"
    # DuckDB database files use the four-byte DUCK signature at offset 8.
    if len(header) >= 12 and header[8:12] == b"DUCK":
        return "duckdb", "DuckDB database"
    return "unknown", "unrecognized binary data"


def descriptor_for_database(engine: str, *, extension_type: str | None = None) -> DatabaseTypeDescriptor:
    if engine in DATABASE_TYPES:
        return DATABASE_TYPES[engine]
    if extension_type == "db_unknown":
        return DATABASE_TYPES["db_unknown"]
    return DATABASE_TYPES["database_unknown"]


def database_registry_payload() -> dict[str, Any]:
    return {
        "version": "database-types-0.1",
        "formats": [DATABASE_TYPES[key].to_payload() for key in ("sqlite", "duckdb", "db_unknown")],
        "authority": {
            "metadata": "available",
            "schema_preview": "approval_required",
            "row_preview": "unavailable_by_design",
            "arbitrary_sql": "unavailable_by_design",
            "mutation": "unavailable_by_design",
            "extension_install_load": "unavailable_by_design",
        },
    }


def is_registered_database_path(path: Path | str) -> bool:
    return Path(str(path)).suffix.lower() in DATABASE_EXTENSIONS


__all__ = (
    "DATABASE_TYPES",
    "DATABASE_EXTENSIONS",
    "SQLITE_HEADER",
    "database_registry_payload",
    "database_type_from_extension",
    "descriptor_for_database",
    "detect_database_engine",
    "is_registered_database_path",
)
