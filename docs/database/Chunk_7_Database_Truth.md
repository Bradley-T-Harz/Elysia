# Chunk 7 DatabaseForge — final source truth

Date: 2026-08-12

| Format | Metadata | Schema preview | Final truth |
| --- | --- | --- | --- |
| SQLite (`.sqlite`, `.sqlite3`, detected `.db`) | `available` | `approval_required` | Private read-only backup snapshot and fixed introspection; no rows. |
| DuckDB (`.duckdb`, detected `.db`) | `available` | `approval_required` | Private read-only copy with external access and extension auto-load/install disabled; fixed introspection only. |
| Unknown `.db` | `metadata_only` | `blocked` | Hash, size, magic, mismatch, and artifact receipt only. |
| Corrupt database-like file | bounded metadata or safe refusal | `blocked` | No fallback write, repair, or arbitrary parser behavior. |

Metadata requires an explicit selected-file action. Schema preview additionally requires an exact one-time approval and a stable source hash/plan. WAL, SHM, and journal sidecars are detected; SQLite uses a consistent backup snapshot, and unsafe sidecars block preview. Source databases and sidecars are never modified.

Detailed metadata and approved schema reports are stored under the private local DatabaseForge artifact root with mode-`0600` files. Central audit stores only IDs, hashes, engine, counts, risk totals, policy versions, and outcome flags. Schema names, SQL definitions, row values, absolute paths, and raw worker output do not enter central trace.

Routes live now: `GET /coding/database/types`, `POST /coding/database/inspect`, `POST /coding/database/schema/preview`, and `GET /coding/database/artifacts/{artifact_id}`. Row preview, arbitrary SQL, query export, extension loading, external access, mutation, migrations, and repair remain unavailable by design.
