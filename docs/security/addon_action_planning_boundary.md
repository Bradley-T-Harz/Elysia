# Add-on Action Planning Boundary

Marketplace add-ons may declare useful install, enable, disable, or uninstall
actions. In the local Elysia desktop app, those declarations are currently
displayed as plans only.

## What Works Now

- Show the exact add-on and declared action.
- Show dependency declarations from the manifest.
- Show trust, risk, and local/network boundary labels.
- Produce a safe, local preview plan.

## What Does Not Happen

- No package install, uninstall, or update.
- No `pip`, `npm`, `apt`, `cargo`, Docker, shell, subprocess, or worker launch.
- No file mutation.
- No local profile private-field upload.
- No local files, memory, request traces, dependency inventory, local paths, or
  local Elysia password are sent to Marketplace.

## Future Requirement

Any future executor must require exact local operator approval, use a narrow
contract, write ledger truth, provide rollback notes, and include refusal tests.
