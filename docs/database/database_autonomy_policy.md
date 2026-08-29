# DatabaseForge autonomy policy

Database stewardship defaults to Level 1 Directed. Elysia acts only after the operator selects a local database and requests an action. File recognition and installed tooling never increase authority.

- Level 0: no database action without an operator request.
- Level 1: Elysia may suggest metadata inspection but cannot start it.
- Level 2: a future explicit setting may allow metadata-only inspection of an operator-provided file.
- Level 3: a future explicit setting may draft a schema-preview plan.

No autonomy level may open schema objects. SQLite or DuckDB schema preview always requires a fresh, exact, expiring, one-time human approval bound to the source hash and source/sidecar state. Unknown `.db` files cannot enter the schema lane.

No level authorizes row preview, arbitrary or generated SQL, export, attach, extension loading, external access, mutation, migrations, repair, or replacement. Future read-only SQL and future mutation are independent capabilities requiring new policy, routes, tests, privacy controls, and approval classes. Existing schema approval cannot authorize them.

Machine-readable defaults live in `config/policies/coding_database_types.yaml`, `config/policies/database_inspection_limits.yaml`, and `config/workers/databaseforge_worker.yaml`.
