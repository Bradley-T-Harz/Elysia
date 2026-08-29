# Coding Archive API Contract

ArchiveForge is Elysia core's local archive/container stewardship lane. Desktop and Codev are operator surfaces only; neither client extracts a container or runs archive tooling directly.

## Routes

- `GET /coding/archive/types`
- `POST /coding/archive/inspect`
- `POST /coding/archive/extract/plan`
- `POST /coding/archive/extract/apply`
- `GET /coding/archive/jobs/{operation_id}`
- `POST /coding/archive/jobs/{operation_id}/cancel`
- `GET /coding/archive/artifacts/{artifact_id}`

There are no install, execute, import, trust, open, extract-all, or project-merge routes.

## Inspection contract

Inspection accepts one existing non-symlink archive beneath an approved workspace root and an explicit user inspection signal. It returns extension/content classification, bounded member summaries, hashes, projected sizes, collision and risk counts, package-container summary truth, policy/tool truth, and local artifact receipts. The full manifest and risk report are stored only as local ArchiveForge artifacts.

Inspection detects path traversal, absolute/home/Windows-drive/UNC paths, excessive paths, duplicates, Unicode/case collisions, links and special nodes, encrypted members, set-id and executable modes, nested containers, native binaries, package entrypoints/scripts, extension/content mismatch, compression ratios, and configured size/count limits. Detection never grants trust.

## Extraction contract

Only ZIP, TAR, and TAR.GZ have `extract_sandbox_only` support. A plan names its operation ID, exact member indexes, archive and manifest hashes, selected-member digest, projected bytes, policy version, sandbox ID and destination hash. Apply must carry that same operation ID and requires a fresh expiring one-time approval bound to the approved root, source archive, archive hash, plan hash, and `archive_sandbox_extract` mutation class.

Apply creates a new server-owned sandbox outside source/project roots. The root must be process-owned and non-symlinked. A bounded, hash-verified private snapshot closes the source mutation race. ArchiveForge writes only the selected regular files with mode `0600` beneath mode-`0700` directories using descriptor-relative, exclusive, no-follow creation. It uses manual bounded streams; `extractall` is forbidden. It never materializes links, devices, FIFOs, sockets, owners, set-id bits, or executable bits. Runtime, actual bytes written, and per-file bytes are checked while streaming. Failure or cancellation removes partial sandbox output.

## Compact ledger contract

Central coding audit and request trace may contain operation/request/approval IDs, archive/manifest/plan hashes, counts, risk totals, sandbox destination hash, policy version, tool identity, compact outcome, and mutation/locality booleans. They must not contain full member lists, sensitive raw names, extracted content, archive bytes, absolute paths, package metadata dumps, passwords, or worker stdout/stderr.
