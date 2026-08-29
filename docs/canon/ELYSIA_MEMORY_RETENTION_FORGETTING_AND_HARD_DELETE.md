# Memory Retention, Forgetting, and Hard Delete

## Different operations

- Suppress automatic recall: ordinary cognition stops using the record; explicit authorized lookup still works.
- Demote: move between Hot, Warm, or Cold without changing truth or ownership.
- Expire: apply an explicit lifecycle policy; expiry is not silent hard deletion.
- Supersede: retain historical truth while a newer revision/record becomes current.
- Archive: intentionally remove the record from ordinary active continuity while preserving it.
- Hard Delete: irreversible purge from authorities Elysia controls.

Homeostasis never converts any of the first five operations into Hard Delete.
Storage pressure first tiers, compacts, compresses, deduplicates, and archives.
At emergency reserve pressure it pauses nonessential jobs and reports the
condition rather than destroying history.

## Hard-delete preview

The preview enumerates the exact affected canonical record and revisions,
sources, candidates, truth/contradiction/relation rows, FTS, semantic vectors,
graph, summaries/caches, cold objects, Shared Space references, managed
archives, and protected key material. It explains that portable/offline copies
outside Elysia's control are not reachable.

The plan receives a deterministic digest. An expiring one-time approval is
bound to the actor, target, action, and exact digest. Any intervening mutation
changes the live digest and invalidates apply. The approval token is shown only
to the initiating flow and is consumed atomically.

## Apply and proof

Apply first restores any Cold payload needed to rewrite managed backups, then
purges persistent semantic and FTS projections and rewrites Elysia-held managed
archives without the target. User portable exports still inside Elysia's cache
are removed; offline copies are reported as outside reach.

The cross-store operation uses a durable, content-free saga journal. Its
prepared phase contains only the approval, owner, memory/revision identifiers,
original tier, timestamps, and phase—never a title, body, source label, content
digest, ciphertext, key, or recovery material. Derived/archive purges occur
before the canonical transaction. That transaction consumes the approval,
deletes canonical content, writes the content-free receipt, and advances the
journal to `canonical_committed` atomically. Startup can then repeat the
SQLite physical scrub after an abrupt exit; authenticated governed maintenance
reruns the exhaustive absence proof and removes the journal only after success.
An interrupted pre-commit operation keeps canonical truth and rebuilds cold
placement, projections, graph, and a current managed backup.

The canonical transaction removes revisions, sources, candidates, truth
events, contradictions, relations including incoming references, cold
pointers, object references, and the record. Sealed wrapped per-revision data
keys disappear with the revisions. Unreferenced object bytes and persistent
graph rows are removed. SQLite secure-delete, WAL truncation, and VACUUM clear
freelist/history pages.

The verifier searches canonical tables, sources/revisions, candidates,
relations, truth/contradiction state, object metadata/bytes, packed Cold store,
FTS, semantic projection, deterministic graph, and managed backups. Success
retains only a content-free deletion receipt: no title, body, source label,
memory identifier, state/content digest, scope/form/privacy classifier, protected
equality value, or path. The target-bound consequence approval is removed in
the same canonical transaction. The receipt retains only operation-level proof
such as actor, action, one-time approval identifier, completion state, reason,
and time.

## Shared memory

Sharing does not transfer ownership. Deleting an owned record therefore
removes the Shared Space reference for every reader after the exact consequence
preview. It does not create a private copy for a reader.

## Honest scope

Elysia cannot delete screenshots, disconnected drives, manually copied
portable archives, third-party backups, or content another system lawfully
ingested before deletion. The UI and receipt state this boundary and never
claim universal erasure.
