# Elysia Memory Archive, Backup, and Restore

## Archive contract

The portable contract is `elysia-memory-archive`, currently format version 2.
It is a logical archive, not a copied live SQLite database. The clear envelope
contains only versioned cryptographic/compression metadata and ciphertext. Its
payload is Zstandard-compressed and AES-256-GCM authenticated with a key
derived from user recovery material by Scrypt.

Applicable payload components are:

- canonical record metadata and immutable revision plaintext inside the encrypted envelope;
- stable memory/revision/source/relation/candidate/truth/contradiction/space IDs;
- owner and Shared Space mapping metadata;
- provenance and temporal fields;
- content-free mutation receipts;
- settings manifest for review, not automatic application;
- projection rebuild manifest;
- component counts and archive checksum.

Raw account/vault keys, sessions, passwords, password hashes, API keys,
connector credentials, and raw protected database ciphertext are not exported.
Private and Sealed logical content exists only inside the authenticated archive
envelope and is re-encrypted under the destination profile's keys during
restore.

Supported scopes are full account, selected Project, selected Shared Space,
and metadata/audit. Scoped exports include only receipts belonging to included
records. Shared Space membership outside the restoring owner is never
federated automatically.

## Portable export versus managed backup

A portable export uses recovery material supplied by the user. Elysia returns
the encrypted archive bytes but never stores that recovery material. Copies
moved outside the managed XDG directory are user-controlled offline copies.

A managed backup is an encrypted Elysia-held archive whose recovery key is
derived from the authenticated account key. This lets Elysia validate
retention, rewrite backups during hard deletion, and report health without
giving Admin plaintext access. Managed retention is a real Settings control.

## Restore protocol

Restore proceeds as follows:

1. copy encrypted bytes into an XDG-private staging file;
2. verify envelope, ciphertext hash, recovery material, AEAD, compression, and schema;
3. validate required components, stable-ID uniqueness, revision chains, provenance, relations, truth events, contradictions, spaces, and receipts;
4. detect conflicts against every live stable-ID authority;
5. show exact additions, conflicts, owner mapping, space-role choice, settings handling, and projection plan;
6. bind an expiring one-time approval token to the exact plan and archive checksum;
7. re-read and re-authenticate the staged archive;
8. re-check conflicts so live changes cannot invalidate the preview;
9. re-encrypt every revision for the authenticated destination account;
10. import all canonical rows in one SQLite transaction;
11. rebuild and verify FTS, deterministic graph, and optional configured semantic projection;
12. remove staging only after successful projection verification.

Wrong recovery material, corruption, tampered authenticated content, missing
required components, incomplete revision chains, unsupported future schema,
or changed live conflicts fail. Any failure before canonical commit leaves live
memory untouched. If an optional derived projection fails after a safe
canonical commit, the plan is marked as requiring projection repair and the
staging evidence is retained; canonical memory remains authoritative.

Version 1 archives remain supported through their zlib compression contract
and may omit components introduced in version 2. Future versions are rejected
until supported explicitly.

## Recovery practice

Keep portable recovery material separately from the archive. Test a restore
into a disposable clean profile before relying on a backup. A valid test checks
record counts, representative Normal/Private/Sealed content, source and
relation integrity, Shared Space owner mapping, FTS, graph, optional semantics,
restart continuity, and `PRAGMA foreign_key_check`.
