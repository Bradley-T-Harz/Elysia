# Add-on Sandbox Mode

This add-on-specific contract inherits
`docs/release/LOCAL_SANDBOX_DOCTRINE.md` and
`docs/release/ADDON_DEVELOPER_FORGE_MARKETPLACE_DOCTRINE.md`.

Current sandbox mode is validation-only.

It verifies package structure, manifest fields, checksums, paths, permissions, entrypoints, and risk flags. It does not run add-on code, start workers, allow shell, allow network, mount private folders, or read private Elysia memory.

Future execution sandboxing is local to the user's machine and requires an isolated,
authenticated worker boundary; explicit allowlisted mounts; CPU, memory, process,
file/output, and time limits; no secrets or private memory; network denied by
default; no host Docker socket; sanitized logs/receipts; cancellation, kill,
cleanup, and revocation controls; exact permission approval; and doctor proof.

No cloud sandbox is required. If local isolation is unavailable, execution fails
closed and remains blocked/profile-gated/Lab-gated. It must never fall back to direct
host execution.
