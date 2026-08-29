# Governed Add-ons API Contract

Status: qualified stable v1.0 contract

The local API is the only add-on staging and lifecycle authority. Marketplace
pages, deep links, manifests, add-on output, and frontend state are untrusted
inputs. Add-ons never enter Elysia Core as imported modules; future execution
must use a governed bridge after the complete local sandbox gate is proven.

## Read and validation routes

- `GET /addons/status` returns sanitized lifecycle, storage-label, sandbox, and
  official-candidate truth.
- `GET /addons/installed` returns sanitized registry entries without storage
  paths.
- `GET /addons/audit` returns allowlisted receipts without raw payloads, paths,
  credentials, approval tokens, or private values.
- `GET /addons/permissions` returns the declared permission vocabulary.
- `GET /addons/official-candidates` returns draft/listing metadata only.
- `POST /addons/inspect-package` performs bounded static inspection only.
- `POST /addons/test-sandbox` is a validation-only check. It is not an
  execution sandbox and starts no add-on code.

## Exact lifecycle routes

Every local state change uses:

1. `POST /addons/transitions/plan`
2. operator review of exact add-on/version/hash/current state/proposed state and
   permissions
3. `POST /addons/transitions/approve` with the exact confirmation phrase
4. `POST /addons/transitions/apply` with the short-lived one-time approval

Plans bind the package hash, registry revision, state, requested/approved/
effective permissions, actor, request ID, operation ID, and expiry. Apply fails
closed on stale state, changed package, tampering, expiration, approval replay,
or permission widening.

Authoritative lifecycle states are:

`draft`, `packaged`, `submitted`, `pending_review`, `approved`, `rejected`,
`installed_disabled`, `enabled_limited`, `disabled`, `revoked`, and `removed`.

`installed_disabled` means validated files are staged under XDG user data with
no bridge or runtime authority. `enabled_limited` remains non-executing in Pass
7 because runtime permissions and the local sandbox/bridge proof are off.
`revoked` withdraws trust and grants. `removed` is a registry state that retains
staged files; it is not deletion.

Legacy `/install-disabled`, `/enable`, `/disable`, `/revoke`, and `/remove`
routes refuse requests without an already issued exact plan and approval.
`/rollback` remains blocked because no approved immutable snapshot contract is
implemented.

## Developer Forge and Marketplace preview routes

- `POST /addons/developer/package-plan` validates caller-supplied manifest and
  sanitized source-inventory metadata. It reads no arbitrary repository, writes
  no archive, runs no code, and does not upload, push, submit, or publish.
- `POST /addons/marketplace/submission-preview` prepares a non-uploading,
  hash-bound pending-review preview only after static-scan and external-upload
  privacy acknowledgment.
- `POST /addons/marketplace/review-preview` validates a non-persisting admin
  review record bound to the exact hash, publisher, requested permissions,
  dependency inventory count, compatibility/dependency/license/provenance
  checks, static scan, sandbox result, reviewer, server timestamp, risks, and
  decision.

Website upload is not local-only: selected repository, folder, source bundle,
Git metadata, or package material leaves the computer when a future user
explicitly submits it. No upload or Marketplace database mutation is present in
these routes.

## Permission and execution law

Effective permissions are the intersection of declared, profile-allowed,
policy-allowed, user-approved, doctor-proven, runtime-available, bridge-ready,
and non-revoked permissions. No caller or add-on can widen that intersection.

Pass 7 enables no add-on execution, network, shell, package manager, worker,
hardware, host Docker socket, private memory, vault, credential, browser,
model-secret, raw-log, or Core-internal access. No cloud sandbox is required.
