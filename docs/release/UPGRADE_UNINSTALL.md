# Elysia v1.0 Upgrade and Uninstall Contract

This document defines public lifecycle behavior. Pass 6 implements the first
dry-run-first user-local Core install/verify and recoverable application
uninstall foundation; final package-manager proof remains a release gate.

## Install

- Installation must not erase or overwrite existing Elysia user data.
- The installer must distinguish application files from user config, data, cache/models, state/logs, and runtime credentials.
- Existing data is detected before any migration plan is offered.
- Optional profiles are explicit and may be added later without reinstalling Core.
- No optional model, tool, service, or cloud component is downloaded silently.
- `scripts/install_core.sh` installs a versioned application payload only after
  explicit `--apply`; its default is a non-mutating plan.
- Python dependencies may come from an explicitly selected offline wheelhouse.
  The installer uses `--no-index` and never falls back to the network.

## Upgrade

- Upgrades preserve local config and data by default.
- Schema or layout changes use an identified migration version.
- Before a material migration, Elysia previews the affected data classes and creates a recoverable backup where practical.
- Migration is atomic where practical and fails without deleting the prior usable state.
- A failed migration produces a sanitized recovery receipt.
- User-local overrides are validated; unknown or deprecated keys are reported rather than silently discarded.
- Profiles removed from a new version become disabled/degraded with explanation; their user-created data and model assets are not silently deleted.
- Pass 6 upgrades stage a versioned application payload and atomically change
  the active application link without overwriting XDG config, data, or state.

## Uninstall

- Uninstall removes application-owned binaries and integration assets selected by the uninstall action.
- Uninstall must explain which user config, conversations, projects, artifacts, models, logs, and local add-on data will remain.
- User data remains by default.
- Removing user data is a separate explicit action with exact root resolution and a preview of data categories—not private contents.
- Model vaults outside Elysia-owned directories are never deleted by uninstall.
- Add-on or profile data is not treated as disposable merely because the corresponding code was removed.
- `scripts/uninstall_core.sh --apply` moves application code and the launcher to
  a recoverable XDG state location. It does not delete user data.

## Backup and export

- Backup/export identifies included data classes and exclusions.
- Sealed/private material is excluded unless the user explicitly chooses a separately protected export.
- Exports do not include credentials, session tokens, browser profiles, model tokens, or raw operational secrets.
- Export manifests use relative paths and hashes; normal receipts remain sanitized.

## Logs and diagnostics

- Logs and diagnostics use XDG state paths, bounded retention, and sanitized content.
- Normal diagnostic export omits raw prompts, transcripts, file contents, private paths, environment values, credentials, and unrestricted command output.
- Sending a diagnostic bundle outward is a separate outbound operation with preview, destination binding, final approval, and receipt.

## Recovery and rollback

- Installer and migration operations record their version, scope, result, and recovery location using sanitized labels.
- Rollback never claims availability unless a valid snapshot exists.
- A restore operation requires explicit selection and must not overwrite newer user data without confirmation.

## Deletion doctrine

The lifecycle must not silently delete local user data. No install, update, profile removal, add-on disable, or ordinary uninstall may do so. Destructive cleanup is a distinct, explicit, auditable operation implemented only after exact path resolution and recovery options are clear.
