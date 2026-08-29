# Elysia Memory Release API Contract

API version: `0.5`
Memory contract: `memory-release-closure-1.0`
Transport: governed local API through the Desktop bridge

Every route requires the authenticated local account except public startup
health. Responses use the standard Elysia envelope with locality, approval,
warnings/errors, and sanitized trace summary. Authorization failures do not
return content.

## Canonical records

- `GET /memory/summary`
- `GET /memory/items` — search plus scope/form/privacy/status/tier/space/conversation/project filters
- `POST /memory/items` — canonical explicit record creation
- `GET /memory/items/{id}` and `/revisions`
- `POST /memory/items/{id}/correct`
- `POST /memory/items/{id}/relations`
- `GET /memory/items/{id}/belief-explanation`
- `POST /memory/items/{id}/archive`, `/restore`, `/pin`

Create accepts the nine form values and validated `form_data`. It cannot grant
authority. Stable scope links are verified against their domain authority.
Memory recording and default privacy are enforced in the writer.

## Teaching and privacy

- `POST /memory/candidates`
- `POST /memory/items/{id}/candidate-decision`
- `GET /memory/approvals/pending`
- `POST /memory/sealed/unlock` and `/sealed/relock`
- `GET/PUT /memory/settings`

Candidate decisions are approve, reject, defer, and seal, with optional edited
wording. Sealed unlock is user-reauthenticated, TTL-bounded, local, and does not
create egress or a persistent index.

## Shared Space membership

- `GET /memory/spaces`
- `POST /memory/spaces`
- `GET /memory/spaces/invitations`
- `POST /memory/spaces/invitations/{id}/respond`
- `POST /memory/targets/{space_id}/consequences/preview`
- `POST /memory/targets/{space_id}/consequences/apply`

The invitation response is exactly `accept` or `decline`. Invitation, direct
membership, role change, and revocation use the actions
`invite_space_member`, `add_space_member`, `change_space_member_role`, and
`remove_space_member`. The owner role is not transferable through these
operations. Current Space role controls access even when a member originally
created the shared record; the record owner remains provenance only.

## Metabolism, graph, and forms

- `POST /memory/items/{id}/tier`; `GET /tier-history`
- `POST /memory/items/{id}/automatic-recall`
- `POST /memory/items/{id}/form-action`
- `GET /memory/items/{id}/graph`
- `GET /memory/prospective/due`
- `GET /memory/homeostasis`

Tier transitions and form actions create receipts. Graph output is
reauthorized and excludes persistent Private/Sealed topology. Prospective due
output excludes Sealed records and performs no external delivery.

## Jobs and diagnostics

- `POST /memory/jobs`
- `POST /memory/jobs/{id}/run`
- `POST /memory/jobs/{id}/cancel`
- `GET /memory/jobs`
- `GET /memory/health`

Supported Part 2E job kinds are tier maintenance, graph rebuild, object
integrity, projection rebuild, homeostasis, managed backup, consolidation, and
replay validation. Jobs use the Part 2D Compute ledger and emergency controller.

## Archive/restore

- `POST /memory/archives/export`
- `GET /memory/archives`
- `POST /memory/archives/restore/preview`
- `POST /memory/archives/restore/apply`

Portable export returns base64-encoded encrypted bytes, never the recovery
secret. Preview returns the exact plan, plan hash, expiring approval ID/token,
and no plaintext staging path. Apply must carry the same recovery material and
exact approval. Settings manifests are shown for review and are not silently
applied.

## Consequence approval and hard delete

- `POST /memory/targets/{id}/consequences/preview`
- `POST /memory/targets/{id}/consequences/apply`

Consequences include sharing/ACL/privacy and hard delete. Apply is actor,
target, action, state-digest, expiry, and one-time-token bound. Hard-delete
success returns content-free purge/verification truth and the offline-copy
limit, never deleted content. The delete plan identifies its content-free
durable-saga crash-recovery contract. Health reports only aggregate pending
saga phase counts; governed maintenance performs recovery, so a read-only
Health request never triggers deletion work.
