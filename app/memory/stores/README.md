# Memory Stores

These directories are legacy migration inputs for Elysia's canonical Memory Fabric.

## Purpose

Each subdirectory corresponds to one memory class:

- `working/` - short-horizon active context
- `conversations/` - dialogue continuity
- `projects/` - project-scoped continuity
- `research/` - evidence and provenance memory
- `operational/` - procedures, environment truths, recurring system knowledge
- `preferences/` - user preference memory
- `sealed_private/` - strongly protected memory
- `audit/` - accountability and trace memory

## Storage posture after canonical cutover

- The one live writer is the XDG-local `elysia_memory.sqlite` authority.
- These package-relative directories are discovery/read-only migration inputs and
  must never be used as a fallback writer.
- Installed legacy JSON is archived with a hash manifest during cutover; its
  source file is preserved for rollback evidence.
- Empty directories are preserved with `.gitkeep`.
- Legacy JSON memory items remain ignored by git through `app/memory/stores/.gitignore`.

## File model

The legacy model was:

- one JSON file per memory item
- written into the matching class directory
- formerly managed by `MemoryItemService`; its write path is now disabled

## Safety

Treat every discovered legacy record as sensitive. Migration and diagnostics
must never print bodies, credentials, encryption keys, or private source paths.
