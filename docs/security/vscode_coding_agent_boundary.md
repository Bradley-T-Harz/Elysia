# VS Code / Elysia Codev Security Boundary

Elysia Codev is a local VS Code interface into Elysia core's governed coding spine. It is not an autonomous coding agent and does not own dangerous authority.

## Must remain local

- Local Elysia API calls stay on loopback.
- Packaged mutations require the local XDG credential; the extension host may read it only after owner/mode validation and must never expose the value to the webview, UI, logs, or receipts.
- A trusted VS Code workspace is not an approved Elysia repository. Exact repository approval and revocation are separate, hashed, auditable contracts.
- Source previews stay local.
- Approval and result records stay in local ignored runtime state.
- Marketplace accounts are not required.
- Cloud coding/research providers are not part of this bridge.
- Codev file previews use Elysia's file type registry and adapters. Codev is
  only the interface; Elysia core enforces path scope, file type policy, secret
  scanning, hash checks, approval mode, and audit.
- Science/data previews and operations also stay in Elysia core. Codev can
  request data inspection, bounded preview, export plans, and governed mutation
  plans, but cannot run arbitrary SQL, shell commands, package managers, cloud
  upload, or unbounded dataset reads.
- Archive/container parsing, external listing tools, hostile-member analysis, planning, and sandbox writes remain in Elysia core. Codev can request list/risk truth and carry an exact approval, but cannot install, execute, import, trust, auto-open, extract all, materialize links/devices, or write archive contents into a workspace.

## Explicitly not live

- Unapproved patch application is disabled.
- Ungoverned broad file mutation.
- Shell execution.
- Unapproved or arbitrary command execution and focused test execution.
- Git mutation.
- Package-manager execution.
- Archive install/execution/project extraction and autonomous extraction.
- Cloud upload.
- Browser automation.
- Autonomous coding loops.
- Background task continuation and hidden goal pursuit.

## Protected data

The bridge must not read or expose vault material, identity data, memory stores, logs, `.env` files, private keys, SSH files, dependency inventory, raw request payloads, or unrelated local paths. Selected source preview requires explicit operator approval and is bounded by size, line count, path guard, and secret redaction. Sanitized request and operation trace summaries are available for accountability, but omit raw contents, full logs, private absolute paths, and large diffs.

## Governed live powers

File mutation, stable document/data/visual operations, selected archive-sandbox extraction, patch application, and the exact read-only diff check are live only when Elysia core validates the approved workspace, paths, source and plan hashes where applicable, and an exact, expiring, one-time approval record. These operations write compact coding audit and central request-trace truth, and mutation workflows provide backup, derived-output, or disposable-sandbox receipts where applicable. Archive member names/details stay in local artifacts rather than central trace. Workspace-controlled npm/Cargo scripts and build hooks are policy-disabled because exact argv does not bind their ambient code-execution authority.

Developer Lab goal contracts are planning/checkpoint authority, not execution authority. Each plan has an approved repo, selected-file allowlist, step/time budget, expiring extension-host-only task token, explicit next-step click, receipt, and stop/revoke path. A checkpoint cannot run a command, apply a patch, schedule continuation, or widen permissions.

## Future risky powers

Any future authority, including git or package-manager execution, must add:

- contract
- config
- policy gate
- exact approval route
- ledger write
- UI truth
- focused tests
- refusal tests
- rollback story
