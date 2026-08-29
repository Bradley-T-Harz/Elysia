# Add-on Permission Vocabulary

The governing permission and lifecycle law is
`docs/release/ADDON_DEVELOPER_FORGE_MARKETPLACE_DOCTRINE.md`.

The canonical local vocabulary is `config/addons/permission_vocabulary.json`.

Initial permissions:

- `network.fetch`
- `filesystem.read_project`
- `filesystem.write_project`
- `memory.read_scoped`
- `memory.write_scoped`
- `model.invoke.local`
- `tool.run_sandboxed`
- `shell.run`
- `external_api.call`

Risk levels are `low`, `medium`, `high`, and `critical`.

Default posture:

- network denied by default
- filesystem limited to user-selected or project-scoped paths
- private memory and vault access denied until a future scoped policy exists
- shell execution blocked

Requested permissions are not grants. The effective set is the intersection of
declared, compatible, profile-allowed, policy-allowed, user-approved, doctor-proven,
and non-revoked permissions. An add-on response or frontend state cannot widen it.

Private memory, journals, vaults, credentials, browser profiles, model tokens, raw
logs, arbitrary filesystem/network access, package installation, host shell, and
hardware access remain denied unless a future exact permission and its full governed
boundary are separately implemented. Existing vocabulary entries are forward-looking
identifiers, not evidence that their runtime authority is live.
