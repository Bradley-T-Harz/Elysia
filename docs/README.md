# Elysia Documentation Map

The documentation tree separates current contracts, public-release truth, historical evidence, and capability-specific boundaries.

## Core collections

- `release/` — v1 scope, pass plan, public/private boundary, package manifest, install profiles, and release-gate truth.
- `canon/` — classified identity/canon documents and their index. Not every canon file is a public-package input.
- `architecture/` — dated architecture summaries, live-repo tree records, and stewardship history.
- `api/` — request/response and bridge contracts.
- `security/` — trust boundaries and governed authority contracts.
- `addons/` — package, permission, sandbox, installer, and revocation contracts.
- `installers/` — installer/runtime lifecycle documentation.
- `reports/` — audits, benchmarks, gaps, and evidence reports excluded from the first public source snapshot where declared.
- `archive/` — historical policies, worker truth, and closure packets retained for continuity rather than advertised as current product behavior.
- `benchmarks/`, `research/`, `coder/`, `database/`, `binary/`, `engineering/`, `image/`, `media/`, `media_or_data/`, `speech/`, and `video/` — capability-specific contracts and truth.

`SYSTEM_PROMPT.txt` remains at the docs root because its governed path is referenced by canon and packaging policy. It is classified private-profile-only and excluded from the first public source snapshot/package.

When moving tracked documentation, use `git mv`, update live references, preserve dated historical tree snapshots as historical evidence, and run the release documentation and public-hygiene tests.
