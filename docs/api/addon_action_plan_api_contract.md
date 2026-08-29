# Add-on Action Plan API Contract

The add-on action plan API turns Marketplace manifest actions into local,
preview-only plans. It does not install, enable, disable, uninstall, mutate
files, run commands, launch workers, or inspect local dependency inventory.

## Endpoint

- `POST /addon-actions/plan`

The request contains an add-on id/name, a manifest action declaration,
dependency summaries, trust tier, and local/network boundary flags.

## Returned Truth

The response returns `addon_action_plan` with:

- `plan_state`
- action identity
- dependency summary
- network boundary
- execution/mutation/command/package/shell/subprocess flags
- future approval requirement
- rollback note
- refusal reason

All execution and mutation flags are false in this version.

## Boundary

This route receives no Marketplace password, Supabase token, local Elysia
password, local files, memory, request traces, dependency inventory, vault
material, or local filesystem paths.

Future execution, if ever added, must be a separate approved operator path with
policy gates, exact action scope, ledger truth, focused tests, refusal tests,
and rollback.
