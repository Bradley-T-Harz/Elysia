# Coding database and binary security boundary

Chunk 7 adds static intelligence, not runtime authority.

Database authority is limited to selected-file identification, hashing, metadata, and exact-approved SQLite/DuckDB schema preview from a private read-only snapshot. Binary authority is limited to selected-file static inspection. Both use approved roots, the shared path guard, operation/request IDs, versioned policies, bounded fixed workers, private local artifacts, and sanitized central audit.

The central record may contain source/snapshot/artifact hashes, file size, detected engine/format, schema or binary aggregate counts, risk totals, policy versions, approval and operation IDs, and explicit no-effect flags. It must not contain database schema names or definitions, row values, binary strings/import/export/symbol names, embedded paths, binary bytes, absolute source paths, secrets, worker stdout/stderr, or arbitrary parser dumps.

Database schema approval is exact, expiring, and one-time. It binds the source and state digest to the `database_schema_preview` operation class. It cannot authorize SQL, row access, export, extension loading, external access, or mutation. Binary inspection approval is an explicit selected-file read action and cannot authorize execute/load/import/install/link/trust/mutate/patch operations.

Desktop and Codev are clients of Elysia core authority. They expose small identify/static-inspect/schema-preview surfaces and collapsible truth. They do not parse databases/binaries themselves and provide no run, execute, patch, install, import, load, trust, open-in-system, mutate, SQL, or decompile controls.

Future read-only SQL, database migration, deeper disassembly, and sandboxed execution are separate capability projects. Each requires its own threat model, policy registry, route, approval class, isolation, tests, and audit contract. No current token, artifact, result, UI state, or autonomy level grants those powers.
