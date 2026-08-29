# Local Installer Security

This contract is governed by
`docs/release/ADDON_DEVELOPER_FORGE_MARKETPLACE_DOCTRINE.md`.

Local Elysia is the final installer authority.

The public website cannot silently install, enable, disable, revoke, remove,
execute, or control local add-ons. Validated package material is staged under
the Pass 6 XDG user-data root, never inside the source tree in public/package
mode. Normal responses expose only the storage label, not its absolute path.

Current local operations:

- inspect package
- create a hash/state/revision-bound transition plan
- issue a short-lived one-time exact approval
- stage disabled after revalidation and approval
- record limited-enable, disable, revoke, or retain-files removal through the
  same exact transition contract
- validation-only sandbox test
- append local audit record

The first install state is `installed_disabled`. Enabling is separate, planned,
approved, and audited. Current `enabled_limited` state does not execute add-on
code, activate a bridge, or grant private memory, vault, log, identity,
credential, network, worker, shell, hardware, or machine-data access.

`removed` marks the registry while retaining staged files. No Pass 7 control
claims deletion. `revoked` withdraws trust and effective permission grants.

Requested, approved, and effective permissions are separate. Effective permissions
may never exceed the intersection allowed by the manifest, active profile, local
policy, explicit approval, doctor proof, and revocation state. Registry enablement
must not be presented as runtime execution.

Future execution remains off until a local-only sandbox, authenticated governed
bridge, resource/network/mount limits, exact approval, doctor proof, cancellation,
revocation/kill path, and sanitized receipts are implemented and tested together.
Unavailable isolation fails closed; it never falls back to direct host execution.
