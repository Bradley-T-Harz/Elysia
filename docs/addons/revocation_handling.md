# Add-on Disable, Revocation, Removal, and Review Truth

Status: qualified stable v1.0 contract

The website cannot directly disable or remove a local add-on. Remote revocation
information remains advisory until local Elysia checks and applies it through an
exact local plan and one-time approval.

State meanings:

- `disabled`: runtime and bridge authority are off; staged files and trust
  metadata remain.
- `revoked`: local trust and all effective permission grants are withdrawn.
  Future runtime must stop before the receipt can complete. Pass 7 executes no
  add-on process, so the receipt truthfully records that no runtime was active.
- `removed`: the registry marks the exact version removed, while staged files
  are retained. The UI must never claim file deletion.

Every transition is bound to add-on ID, version, package hash, current state,
registry revision, proposed state, actor, request/operation IDs, and a one-time
approval. Changed hashes, stale states, expired/reused approvals, and permission
widening fail closed and write sanitized blocked receipts.

Marketplace/admin review means reviewed under the current process, not
guaranteed safe. A new package hash requires a new review. No public listing,
remote revocation mutation, periodic network check, rollback, quarantine move,
or file deletion is implemented in Pass 7.
