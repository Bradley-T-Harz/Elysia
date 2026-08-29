# Elysia Memory Privacy and Threat Model

## Protected assets

The protected set includes record bodies and titles, revision history,
provenance labels, queries, prompts, context, relationship topology, content
equality, embeddings, cold objects, archives, recovery material, account/vault
keys, and ownership/Shared Space boundaries.

The model protects against another local account, an unauthorized Shared Space
reader, an installation administrator acting only with Admin authority,
untrusted web content, ordinary filesystem disclosure, persistent derived-index
leakage, interrupted writes, corrupted projections, and cross-account
deduplication or timing oracles. It does not claim to defeat a host root user,
live process-memory inspection by a privileged debugger, hardware compromise,
or user-controlled offline copies.

## Privacy classes

### Normal

Canonical content is local and account/ACL authorized. Normal content may enter
FTS5 and the optional authenticated loopback semantic projection. Projection
payloads preserve owner and Shared Space identity and are reauthorized before
return.

### Private

Private revisions are AES-256-GCM ciphertext under the authenticated account
key. Titles and source labels are not stored in clear canonical metadata.
Content equality uses HMAC rather than a public plaintext hash. Private cold
objects use equivalent authenticated encryption. Private content has no
persistent semantic vector and no persistent relationship-graph node. Explicit
authorized retrieval may use lexical or bounded ephemeral semantic processing.

### Sealed

Sealed revisions use a per-revision data key wrapped by a separate vault key.
The vault key is released only after user reauthentication, held in process
memory for a bounded TTL, and removed on relock, logout, emergency stop, or
expiry. Sealed memory is absent from FTS, semantic vectors, ordinary cognition,
and the persistent graph. Cold Sealed bytes remain ciphertext. Hard deletion
destroys the wrapped per-revision key material and all Elysia-managed bytes.

Legacy protected records that used a raw content hash are upgraded after the
required authority exists: Private at authenticated session provisioning and
Sealed only after explicit vault unlock. The obsolete hash bytes are removed
with WAL truncation and SQLite compaction.

## Content-addressed objects and deduplication

Object equality is scoped to a security domain:

- account + Normal/Private privacy;
- source owner + Shared Space + privacy;
- Sealed record/revision.

There is no global content address exposed to users. Protected addresses are
secret-keyed. Sealed records never deduplicate across records. Shared content
retains its source owner and space ACL. Dedup savings are reported only as an
authorized account aggregate. Garbage collection removes only bytes whose
canonical reference metadata is absent.

## Cold storage and archives

Cold payloads live in an XDG-private packed SQLite object store to avoid a flat
million-file layout. Compression occurs before encryption. Private and Sealed
content is authenticated ciphertext at rest. Canonical metadata stores the
verified object pointer and checksums necessary to detect corruption.

Portable and managed archives use AES-256-GCM with Scrypt-derived keys and
Zstandard compression. Portable recovery material is user-controlled and is
not stored. Managed backup keys derive locally from the owning account key so
Elysia can enforce retention and hard-delete rewrites. Archives contain no raw
account keys, session credentials, passwords, password hashes, API keys, or
connector credentials.

## Administrative boundary

Installation Admin is governance authority, not a memory super-reader. Admin
may see account roster, role/managed state, content-free security events,
aggregate storage, quota/pressure, job failures, archive health, dependency
health, and policy ceilings. Admin does not gain memory, conversation, project,
query, prompt, graph, backup plaintext, Private, or Sealed content access.

Managed profiles are visibly supervised. Ceilings can restrict Internet,
autonomy, background work, consolidation, backup, archival, connectors,
external mutation, and resources without granting content access.

Local Elysia Identity and Elysia Ecobotics Online Identity remain separate
authorities. Any Marketplace connector is optional, narrow, revocable,
Internet-master governed, credential isolated, and cannot receive unrelated
local account or memory state.

## Web and model boundaries

Authorization and privacy filtering occur before relevance ranking. Internet
OFF means zero non-local egress. Untrusted web content is evidence, never
policy or memory authority, and prompt-injection text is quarantined. Private
egress requires the governed sensitive-egress path; Sealed egress is denied.
Model context receives only the bounded, authorized Global Working Workspace.
Hidden reasoning is never stored or exposed as metacognitive memory.

## Honest limits

Elysia can purge canonical memory, derived projections, governed objects,
managed backups, caches, and connected writable authorities it owns. It cannot
erase a portable archive copied to disconnected media, screenshots, exports
another application imported, or a backup outside Elysia's control. The delete
preview and receipt state this limit.
