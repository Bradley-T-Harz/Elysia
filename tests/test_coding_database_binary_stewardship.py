from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess

import pytest

from app.api.coding_binary_service import inspect_binary
from app.api.coding_binary_type_registry import binary_registry_payload
from app.api.coding_data_binary_artifact_service import get_data_binary_artifact
from app.api.coding_database_service import inspect_database, preview_database_schema
from app.api.coding_database_type_registry import database_registry_payload
from app.api.coding_data_edit_service import plan_data_edit
from app.api.coding_data_export_service import plan_data_export
from app.api.coding_data_type_registry import detect_data_type
from app.api.coding_file_type_registry import detect_file_type
from app.api.coding_operation_service import approve_operation
from app.api.main import create_app
from app.api.schemas.coding_data import CodingDataEditPlanRequest, CodingDataExportPlanRequest
from app.api.schemas.coding_operations import CodingOperationApproveRequest
from app.api.schemas.database_binary import BinaryInspectRequest, DatabaseInspectRequest, DatabaseSchemaPreviewRequest


DATABASE_PYTHON = Path(os.environ.get("ELYSIA_DATABASEFORGE_PYTHON", ""))


@pytest.fixture
def governed_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ELYSIA_CODING_APPROVED_ROOTS", str(tmp_path))
    monkeypatch.setenv("ELYSIA_DATABASEFORGE_ARTIFACT_ROOT", str(tmp_path / "database_artifacts"))
    monkeypatch.setenv("ELYSIA_BINARYFORGE_ARTIFACT_ROOT", str(tmp_path / "binary_artifacts"))
    monkeypatch.setenv("ELYSIA_CODING_AUDIT_ROOT", str(tmp_path / "audit"))
    return tmp_path


def _sqlite(path: Path, *, sensitive: bool = False) -> None:
    connection = sqlite3.connect(path)
    table = "diagnoses_and_api_keys" if sensitive else "habitat_records"
    connection.executescript(
        f"""
        CREATE TABLE {table}(id INTEGER PRIMARY KEY, species TEXT NOT NULL, secret_note TEXT DEFAULT 'never-return-row');
        CREATE VIEW habitat_ids AS SELECT id FROM {table};
        CREATE INDEX habitat_species_idx ON {table}(species);
        CREATE TRIGGER habitat_touch AFTER INSERT ON {table}
        BEGIN UPDATE {table} SET species=species WHERE id=NEW.id; END;
        INSERT INTO {table}(species, secret_note) VALUES ('lynx', 'private-row-value');
        """
    )
    connection.commit()
    connection.close()


def _approve_schema(root: Path, inspected) -> tuple[str, str]:
    approval = approve_operation(
        CodingOperationApproveRequest(
            operation_kind="database_schema_preview",
            operation_summary="Approve exact schema-only snapshot preview",
            workspace_root=str(root),
            exact_files=[inspected.relative_path or inspected.file_label],
            source_hash=inspected.source_sha256,
            plan_hash=inspected.schema_preview_plan_hash or "",
            allowed_mutation_class="database_schema_preview",
            operator_approved=True,
            approval_phrase="approve exact schema preview",
            rollback_note="No source mutation; private snapshot is destroyed.",
        )
    )
    assert approval.status == "approved"
    assert approval.approval_token
    return approval.approval_id, approval.approval_token


def _schema_request(root: Path, inspected, approval_id: str | None = None, approval_token: str | None = None, *, operator_approved: bool = True) -> DatabaseSchemaPreviewRequest:
    return DatabaseSchemaPreviewRequest(
        workspace_root=str(root),
        database_path=inspected.relative_path or inspected.file_label,
        approval_id=approval_id,
        approval_token=approval_token,
        operator_approved=operator_approved,
        expected_source_sha256=inspected.source_sha256 or "",
        expected_plan_hash=inspected.schema_preview_plan_hash or "",
    )


def _audit_text(root: Path) -> str:
    audit_root = root / "audit"
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(audit_root.glob("*.json")))


def test_registries_encode_chunk7_authority_truth() -> None:
    database = database_registry_payload()
    binary = binary_registry_payload()
    assert {value["type_id"] for value in database["formats"]} == {"sqlite", "duckdb", "db_unknown"}
    assert database["authority"]["schema_preview"] == "approval_required"
    assert database["authority"]["row_preview"] == "unavailable_by_design"
    assert database["authority"]["arbitrary_sql"] == "unavailable_by_design"
    assert database["authority"]["mutation"] == "unavailable_by_design"
    assert {value["type_id"] for value in binary["formats"]} == {"pe", "elf", "class", "wasm", "bin_unknown"}
    for capability in ("execution", "loading", "installation", "linking", "mutation", "patching"):
        assert binary["authority"][capability] == "unavailable_by_design"
    assert binary["authority"]["disassembly"] == "future_sandbox_required"


def test_database_metadata_identifies_content_not_extension_and_unknown_db_is_metadata_only(governed_root: Path) -> None:
    sqlite_path = governed_root / "extension-mismatch.duckdb"
    _sqlite(sqlite_path)
    mismatch = inspect_database(DatabaseInspectRequest(workspace_root=str(governed_root), database_path=sqlite_path.name, approval_granted=True))
    assert mismatch.status == "completed"
    assert mismatch.detected_engine == "sqlite"
    assert mismatch.extension_type == "duckdb"
    assert mismatch.extension_content_match is False
    assert mismatch.schema_preview_plan_hash

    unknown_path = governed_root / "unknown.db"
    unknown_path.write_bytes(b"not a database\x00\x01\x02")
    file_descriptor = detect_file_type(unknown_path, unknown_path.read_bytes())
    assert file_descriptor.type_id == "ambiguous_database"
    assert file_descriptor.category == "database"
    assert file_descriptor.adapter == "database"
    legacy_descriptor = detect_data_type(unknown_path)
    assert legacy_descriptor.type_id == "db_unknown"
    assert legacy_descriptor.adapter == "databaseforge"
    unknown = inspect_database(DatabaseInspectRequest(workspace_root=str(governed_root), database_path=unknown_path.name, approval_granted=True))
    assert unknown.status == "completed"
    assert unknown.detected_engine == "unknown"
    assert unknown.descriptor.metadata_state == "metadata_only"
    assert unknown.descriptor.schema_preview_state == "blocked"
    assert unknown.schema_preview_plan_hash is None
    blocked = preview_database_schema(
        DatabaseSchemaPreviewRequest(
            workspace_root=str(governed_root),
            database_path=unknown_path.name,
            operator_approved=True,
            expected_source_sha256=unknown.source_sha256 or "",
            expected_plan_hash="unavailable",
        )
    )
    assert blocked.status == "blocked"
    assert blocked.blocked_reason == "schema_preview_unavailable_for_unknown_database"


def test_sqlite_schema_requires_exact_approval_uses_snapshot_and_sanitizes_audit(governed_root: Path) -> None:
    path = governed_root / "sensitive.sqlite"
    _sqlite(path, sensitive=True)
    inspected = inspect_database(DatabaseInspectRequest(workspace_root=str(governed_root), database_path=path.name, approval_granted=True))
    assert inspected.status == "completed"
    assert inspected.detected_engine == "sqlite"

    missing = preview_database_schema(_schema_request(governed_root, inspected, operator_approved=False))
    assert missing.status == "approval_required"
    assert missing.blocked_reason == "exact_approval_required"

    approval_id, approval_token = _approve_schema(governed_root, inspected)
    result = preview_database_schema(_schema_request(governed_root, inspected, approval_id, approval_token))
    assert result.status == "completed", result.blocked_reason
    assert result.snapshot_strategy == "sqlite_read_only_backup"
    assert result.snapshot_sha256
    assert (result.table_count, result.view_count, result.index_count, result.trigger_count) == (1, 1, 1, 1)
    assert result.row_data_returned is False
    assert result.arbitrary_sql_executed is False
    assert result.mutation_performed is False
    assert result.artifact
    artifact = get_data_binary_artifact("database", result.artifact.artifact_id)
    assert artifact is not None
    artifact_text = json.dumps(artifact)
    assert "diagnoses_and_api_keys" in artifact_text
    assert "private-row-value" not in artifact_text
    audit = _audit_text(governed_root)
    for private_value in ("diagnoses_and_api_keys", "secret_note", "private-row-value", str(governed_root), path.name):
        assert private_value not in audit
    assert '"raw_content_logged": false' in audit
    assert '"row_data_returned": false' in audit


def test_hash_change_invalidates_database_schema_approval(governed_root: Path) -> None:
    path = governed_root / "change.sqlite"
    _sqlite(path)
    inspected = inspect_database(DatabaseInspectRequest(workspace_root=str(governed_root), database_path=path.name, approval_granted=True))
    approval_id, approval_token = _approve_schema(governed_root, inspected)
    connection = sqlite3.connect(path)
    connection.execute("INSERT INTO habitat_records(species) VALUES ('changed-after-approval')")
    connection.commit()
    connection.close()
    result = preview_database_schema(_schema_request(governed_root, inspected, approval_id, approval_token))
    assert result.status == "blocked"
    assert result.blocked_reason == "database_hash_or_plan_changed"
    connection = sqlite3.connect(path)
    assert connection.execute("SELECT COUNT(*) FROM habitat_records").fetchone()[0] == 2
    connection.close()


def test_sqlite_wal_shm_are_detected_and_snapshot_backup_is_consistent(governed_root: Path) -> None:
    path = governed_root / "wal.sqlite"
    connection = sqlite3.connect(path)
    assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
    connection.execute("CREATE TABLE observations(id INTEGER PRIMARY KEY, note TEXT)")
    connection.execute("INSERT INTO observations(note) VALUES ('sidecar-row-never-returned')")
    connection.commit()
    inspected = inspect_database(DatabaseInspectRequest(workspace_root=str(governed_root), database_path=path.name, approval_granted=True))
    assert inspected.sidecars["wal"]["present"] is True
    assert inspected.sidecars["shm"]["present"] is True
    approval_id, approval_token = _approve_schema(governed_root, inspected)
    result = preview_database_schema(_schema_request(governed_root, inspected, approval_id, approval_token))
    connection.close()
    assert result.status == "completed"
    assert result.snapshot_strategy == "sqlite_read_only_backup"
    assert result.table_count == 1
    artifact = get_data_binary_artifact("database", result.artifact.artifact_id if result.artifact else "")
    assert "sidecar-row-never-returned" not in json.dumps(artifact)


def test_corrupt_sqlite_fails_closed_without_rows_or_mutation(governed_root: Path) -> None:
    path = governed_root / "corrupt.db"
    path.write_bytes(b"SQLite format 3\x00" + b"corrupt" * 20)
    inspected = inspect_database(DatabaseInspectRequest(workspace_root=str(governed_root), database_path=path.name, approval_granted=True))
    assert inspected.detected_engine == "sqlite"
    approval_id, approval_token = _approve_schema(governed_root, inspected)
    before = path.read_bytes()
    result = preview_database_schema(_schema_request(governed_root, inspected, approval_id, approval_token))
    assert result.status == "blocked"
    assert result.row_data_returned is False
    assert result.mutation_performed is False
    assert path.read_bytes() == before


def test_large_sqlite_schema_is_bounded_and_truthfully_truncated(governed_root: Path) -> None:
    path = governed_root / "large_schema.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript("\n".join(f"CREATE TABLE bulk_{index:04d}(id INTEGER);" for index in range(2001)))
    connection.close()
    inspected = inspect_database(DatabaseInspectRequest(workspace_root=str(governed_root), database_path=path.name, approval_granted=True))
    approval_id, approval_token = _approve_schema(governed_root, inspected)
    result = preview_database_schema(_schema_request(governed_root, inspected, approval_id, approval_token))
    assert result.status == "completed"
    assert result.schema_object_count == 2000
    assert result.risk_counts["schema_object_limit_reached"] == 1
    assert result.row_data_returned is False
    artifact = get_data_binary_artifact("database", result.artifact.artifact_id if result.artifact else "")
    assert artifact["payload"]["schema"]["schema_truncated"] is True


@pytest.mark.skipif(not DATABASE_PYTHON.is_file(), reason="DatabaseForge environment is unavailable")
def test_duckdb_schema_preview_is_snapshot_first_read_only_and_external_access_disabled(governed_root: Path) -> None:
    path = governed_root / "habitat.duckdb"
    subprocess.run(
        [str(DATABASE_PYTHON), "-c", "import duckdb,sys; c=duckdb.connect(sys.argv[1]); c.execute('CREATE TABLE habitat(id INTEGER, species VARCHAR)'); c.execute('CREATE VIEW habitat_ids AS SELECT id FROM habitat'); c.close()", str(path)],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
    )
    inspected = inspect_database(DatabaseInspectRequest(workspace_root=str(governed_root), database_path=path.name, approval_granted=True))
    assert inspected.detected_engine == "duckdb"
    approval_id, approval_token = _approve_schema(governed_root, inspected)
    result = preview_database_schema(_schema_request(governed_root, inspected, approval_id, approval_token))
    assert result.status == "completed"
    assert result.snapshot_strategy == "private_file_copy"
    assert result.table_count == 1
    assert result.view_count == 1
    artifact = get_data_binary_artifact("database", result.artifact.artifact_id if result.artifact else "")
    assert artifact["payload"]["schema"]["external_access_enabled"] is False
    assert artifact["payload"]["schema"]["extension_install_load_used"] is False
    assert artifact["payload"]["schema"]["row_data_returned"] is False


def _compile_binary_fixtures(root: Path) -> dict[str, Path]:
    clang = shutil.which("clang")
    mingw = shutil.which("x86_64-w64-mingw32-gcc")
    javac = shutil.which("javac")
    wat2wasm = shutil.which("wat2wasm")
    if not all((clang, mingw, javac, wat2wasm)):
        pytest.skip("Chunk 7 disposable fixture compilers are unavailable")
    source = root / "tiny.c"
    source.write_text("#include <stdio.h>\nint exported_answer(void){return 42;} int main(void){puts(\"fixture-internal-path\");return exported_answer();}\n", encoding="utf-8")
    java_source = root / "Tiny.java"
    java_source.write_text("public class Tiny { public static int answer(){ return 42; } }\n", encoding="utf-8")
    wat_source = root / "tiny.wat"
    wat_source.write_text('(module (import "env" "clock" (func $clock (result i32))) (memory (export "memory") 1 2) (func (export "answer") (result i32) i32.const 42))\n', encoding="utf-8")
    outputs = {
        "elf": root / "tiny.bin",
        "so": root / "tiny.so",
        "o": root / "tiny.o",
        "pe": root / "tiny.exe",
        "dll": root / "tiny.dll",
        "class": root / "Tiny.class",
        "wasm": root / "tiny.wasm",
    }
    commands = [
        [clang, str(source), "-o", str(outputs["elf"])],
        [clang, "-shared", "-fPIC", str(source), "-o", str(outputs["so"])],
        [clang, "-c", str(source), "-o", str(outputs["o"])],
        [mingw, str(source), "-o", str(outputs["pe"])],
        [mingw, "-shared", str(source), "-o", str(outputs["dll"])],
        [javac, "-d", str(root), str(java_source)],
        [wat2wasm, str(wat_source), "-o", str(outputs["wasm"])],
    ]
    for command in commands:
        subprocess.run(command, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    return outputs


def test_binaryforge_static_inspects_pe_elf_so_o_class_wasm_without_active_code(governed_root: Path) -> None:
    outputs = _compile_binary_fixtures(governed_root)
    expected = {"elf": "elf", "so": "elf", "o": "elf", "pe": "pe", "dll": "pe", "class": "class", "wasm": "wasm"}
    for key, path in outputs.items():
        result = inspect_binary(BinaryInspectRequest(workspace_root=str(governed_root), binary_path=path.name, approval_granted=True))
        assert result.status == "completed", (key, result.blocked_reason)
        assert result.detected_format == expected[key]
        assert result.source_sha256
        assert result.artifact
        assert result.execution_performed is False
        assert result.loading_performed is False
        assert result.mutation_performed is False
        assert all("malware" not in flag.code for flag in result.risk_flags)
        assert any(flag.code == "static_analysis_not_verdict" for flag in result.risk_flags)
    assert inspect_binary(BinaryInspectRequest(workspace_root=str(governed_root), binary_path=outputs["wasm"].name, approval_granted=True)).import_count == 1
    audit = _audit_text(governed_root)
    for private_value in ("fixture-internal-path", "KERNEL32.dll", "java/lang/Object", "env.clock", str(governed_root)):
        assert private_value not in audit


def test_unknown_high_entropy_bin_and_extension_mismatch_are_truthful(governed_root: Path) -> None:
    high_entropy = governed_root / "random.bin"
    high_entropy.write_bytes(bytes(range(256)) * 64)
    unknown = inspect_binary(BinaryInspectRequest(workspace_root=str(governed_root), binary_path=high_entropy.name, approval_granted=True))
    assert unknown.status == "completed"
    assert unknown.detected_format == "unknown"
    assert unknown.descriptor.inspection_state == "metadata_only"
    assert unknown.entropy == pytest.approx(8.0, abs=0.01)
    assert "packed_or_high_entropy" in unknown.risk_counts

    mismatch = governed_root / "module.exe"
    mismatch.write_bytes(b"\x00asm\x01\x00\x00\x00")
    wasm = inspect_binary(BinaryInspectRequest(workspace_root=str(governed_root), binary_path=mismatch.name, approval_granted=True))
    assert wasm.status == "completed"
    assert wasm.detected_format == "wasm"
    assert wasm.extension_type == "pe"
    assert wasm.extension_content_match is False


def test_legacy_data_routes_refuse_database_preview_export_and_mutation(governed_root: Path) -> None:
    path = governed_root / "legacy.sqlite"
    _sqlite(path)
    descriptor = detect_data_type(path)
    assert descriptor.adapter == "databaseforge"
    assert descriptor.previewable is False
    assert descriptor.exportable is False
    assert descriptor.mutation_supported is False
    export = plan_data_export(CodingDataExportPlanRequest(workspace_root=str(governed_root), file_path=path.name, approval_granted=True, export_format="json"))
    assert export.status == "blocked"
    assert export.blocked_reason == "database_export_unavailable_by_design"
    mutation = plan_data_edit(CodingDataEditPlanRequest(workspace_root=str(governed_root), file_path=path.name, approval_granted=True, operation="sqlite_insert_row", parameters={"table": "habitat_records", "row": {"species": "blocked"}}))
    assert mutation.status == "blocked"
    assert mutation.blocked_reason == "database_mutation_unavailable_by_design"


def test_no_database_or_binary_execution_mutation_sql_load_or_patch_routes_exist() -> None:
    app = create_app()
    paths = set(app.openapi()["paths"])
    assert {"/coding/database/types", "/coding/database/inspect", "/coding/database/schema/preview", "/coding/database/artifacts/{artifact_id}"}.issubset(paths)
    assert {"/coding/binary/types", "/coding/binary/inspect", "/coding/binary/artifacts/{artifact_id}"}.issubset(paths)
    forbidden = {
        "/coding/database/query/preview",
        "/coding/database/mutate/plan",
        "/coding/database/export",
        "/coding/binary/execute",
        "/coding/binary/load",
        "/coding/binary/import",
        "/coding/binary/install",
        "/coding/binary/link",
        "/coding/binary/patch/plan",
        "/coding/binary/disassemble/preview",
    }
    assert paths.isdisjoint(forbidden)


def test_worker_sources_have_no_execution_or_arbitrary_sql_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    database_worker = (root / "sandbox/databaseforge_worker/worker.py").read_text(encoding="utf-8")
    binary_worker = (root / "sandbox/binaryforge_worker/worker.py").read_text(encoding="utf-8")
    database_cli = (root / "sandbox/databaseforge_worker/worker_cli.py").read_text(encoding="utf-8")
    binary_cli = (root / "sandbox/binaryforge_worker/worker_cli.py").read_text(encoding="utf-8")
    assert 'choices=("metadata", "snapshot_schema")' in database_cli
    assert 'choices=("inspect",)' in binary_cli
    assert "argparse" not in database_worker
    assert "argparse" not in binary_worker
    assert "subprocess" not in database_worker
    assert "subprocess" not in binary_worker
    for forbidden in ("os.system", "subprocess.run", "subprocess.call", "Popen", "exec(", "eval(", "java -jar"):
        assert forbidden not in database_worker
        assert forbidden not in binary_worker
    assert "enable_load_extension(False)" in database_worker
    assert "enable_load_extension(True)" not in database_worker
    assert "read_only=True" in database_worker
    assert '"enable_external_access": "false"' in database_worker
