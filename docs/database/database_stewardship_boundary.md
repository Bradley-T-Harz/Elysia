# Database stewardship boundary

Database files are potentially private, stateful data stores. A recognized extension, valid header, locally installed driver, or successful metadata read does not authorize opening a schema, reading rows, running SQL, loading extensions, exporting data, or changing the file.

DatabaseForge accepts only an explicitly selected regular file under an approved, path-guarded workspace. Metadata inspection computes bounded type, size, magic, SHA-256, BLAKE3, sidecar, and policy truth. An unknown `.db` remains metadata-only. Symlinked sources and unsafe symlink/non-regular sidecars are refused.

SQLite and DuckDB schema preview is a separate exact-approved operation. Approval binds the selected file, source hash, sidecar state, engine, relative path, policy plan, and operation class. It expires and is consumed once. Any source or bound-state change invalidates it.

SQLite opens the source through read-only URI mode, disables extension loading, enables query-only posture, and uses the backup API to create a private mode-`0400` snapshot. Fixed schema and table-valued pragma statements run only after the snapshot is reopened immutable and read-only. DuckDB copies the selected file to a private mode-`0400` snapshot, opens it with `read_only=true`, disables external access and extension auto-install/load, and runs fixed `information_schema`/catalog introspection. No caller supplies SQL.

Only schema names and definitions may enter the private local schema artifact after approval. Rows and cell values are never returned. Central audit and request trace retain hashes, counts, risk totals, policy versions, IDs, and outcome flags only; they exclude schema names, definitions, row values, absolute paths, and worker output.

There are no database query, export, extension-load, attach, mutation, migration, repair, vacuum, or replacement routes in Chunk 7. Future read-only SQL requires a separate bounded grammar, privacy review, and result policy. Future mutation requires a distinct migration/backup/rollback workflow and cannot reuse schema approval.
