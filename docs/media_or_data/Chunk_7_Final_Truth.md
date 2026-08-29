# Chunk 7 databases and binaries — final truth

Date: 2026-08-12

Chunk 7 gives Elysia local static intelligence over SQLite, DuckDB, unknown `.db`, PE/EXE/DLL, ELF/SO/O, Java CLASS, WebAssembly, and unknown BIN files. It does not add execution or mutation authority.

Database metadata and hashes are available after an explicit selected-file action. SQLite and DuckDB schema counts/details are available only through an exact-approved, snapshot-first, read-only workflow using fixed introspection. Unknown `.db` files are metadata-only. Rows, arbitrary SQL, export, attach, extension loading, external access, repair, and mutation are unavailable by design.

Binary hashing, format/architecture/header/section/import/export/symbol/string counts, entropy, and structural risk summaries are static only and bounded by policy. Detailed names and strings stay in private local artifacts. Execution, dynamic loading, import, installation, linking, trust, mutation, patching, signature tampering, decompilation, and exploit help are unavailable. Deeper disassembly and any execution are future sandbox-required capabilities.

Central audit/request trace is compact: hashes, counts, IDs, risk totals, policy versions, approvals, and outcomes. It excludes schema names, row data, raw binary strings/names/paths/bytes, absolute paths, and worker output. Desktop and Codev surface the same truthful boundary without dangerous controls.

Future autonomy cannot bypass exact database schema approval or create binary runtime authority. Future read-only SQL, database mutation, disassembly, and sandboxed execution require separate policies, approval classes, isolation, privacy/lawfulness review, and proof.
