# Coding File Type Boundary

Chunk 1 teaches Elysia to treat local files as governed file types, not generic
text blobs. Codev can request previews and operations, but Elysia core owns the
registry, adapters, path guard, secret scanning, mutation approval, and audit.

Supported Chunk 1 files include code, structured data, Markdown/docs,
CSV/TSV, XML/HTML, styles, shell scripts, project manifests, lockfiles,
`.gitignore`, `Dockerfile`, and `.env.example`.

Blocked by default:

- `.env` and `.env.local`
- private keys, certs, tokens, and secret-looking paths
- `.git/`, `node_modules/`, build outputs, Tauri targets, caches
- `data/identity/`, `data/coding/`, `memory/`, `vault/`, and logs
- unsupported binary, archive, database, and unregistered media files; the
  separately governed Chunk 5 metadata lane recognizes only WAV, MP3, FLAC,
  OGG, M4A, MP4, MOV, MKV, and WebM and grants no generic write authority

`.env.example` is intentionally different from `.env`: it may be previewed and
patched with caution, and secret scanning always runs.

Patch apply and file operations remain local, workspace-scoped, text-only,
hash-checked, path-guarded, approval-gated, and audited. File type support does
not grant shell execution, package-manager behavior, git mutation, cloud upload,
or autonomous loops.
