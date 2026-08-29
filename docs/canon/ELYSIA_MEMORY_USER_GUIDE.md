# Elysia Memory User Guide

## What Memory is

Memory is Elysia's account-owned, inspectable continuity system. A chat
transcript remains a Conversation and a project remains a Project; Memory
links to them without replacing them. Attached files and temporary working
context are not memory unless you explicitly teach or approve a candidate.

## Creating memory

Open **Memory** and choose a form, privacy class, scope, and stable authority ID
when the scope is a Conversation, Project, or Shared Space. Form-specific
fields are validated before anything is written. The default privacy and the
master Memory-recording control in Settings are enforced by the canonical
writer, not just the Desktop.

- Episodic: describe what happened and when.
- Semantic: store a confirmed claim or fact.
- Procedural: provide ordered steps; verify or invalidate them later.
- Prospective: provide a due time or condition; complete, dismiss, reopen, or snooze it.
- Relational: name a typed relation and target authority.
- Predictive: record a prediction and its basis, then record the outcome separately.
- Corrective: identify correction, refinement, changed reality, contradiction, or retraction.
- Metacognitive: record a bounded strategy/quality observation, never hidden reasoning.
- Audit: record a content-minimized operational event; audit records are append-only and excluded from ordinary model context.

## Privacy

Normal memory may participate in persistent FTS and, when installed, semantic
retrieval. Private memory is encrypted and uses authorized explicit lexical or
ephemeral semantic handling; it has no persistent semantic vector. Sealed
memory requires a user unlock with a bounded TTL, is never persistently
indexed, and is excluded from ordinary retrieval. See the privacy threat model
for the complete boundary.

## Candidate Queue

Candidates do not become active autobiographical truth automatically. The
queue shows proposed wording and evidence. You may approve, edit and approve,
reject, defer, or approve into Sealed Memory. Each decision is atomic and
receipt-backed. The Candidate behavior control can forbid inferred capture
while still allowing explicit user-submitted teaching.

## Tiers and continuity

- Working: bounded active-request material.
- Hot: recent, frequent, urgent, important, corrective, or active-project memory.
- Warm: ordinary durable memory and the default tier.
- Cold: encrypted/compressed governed payload with live metadata and authorized rehydration.
- Archived: explicitly removed from ordinary active use, but still restorable.

Pins and retention holds prevent automatic demotion. Explicit lookup can still
retrieve a suppressed or Cold item under authorization. The tier timeline and
mutation receipts explain changes without exposing hidden reasoning.

## Corrections and belief explanations

Use **Correct** rather than overwriting history. The prior revision remains
immutable. Changed reality supersedes the old validity interval; direct
contradiction may leave both claims visible with uncertainty until resolved.
**Why believed?** shows sources, timing, confidence, truth events, and conflicts
in human-readable form.

## Relationships

Add typed relations in Memory stewardship. The deterministic map is a derived
view, not an authority. Private/Sealed topology is not persisted. Shared
results retain the original owner and Shared Space instead of becoming the
reader's personal memory.

## Backup and restore

Use a strong recovery material for a portable encrypted archive. Save it
separately; Elysia does not store the recovery material. Restore first stages
and validates the archive, then shows the exact additions, conflicts, mappings,
and rebuild plan. The exact one-time approval applies that plan only. A failed
precommit restore leaves live memory untouched.

## Forgetting

Use suppression when you only want to stop automatic recall. Use a tier change
to alter performance, Archive to retain but remove from active continuity,
Supersede to preserve historical truth, and Hard Delete only for irreversible
purge from Elysia-managed authorities. Hard Delete previews consequences and
cannot promise erasure from disconnected copies held elsewhere.

## Where operational truth appears

Settings contains real controls only. Current jobs, archive health, projection
health, storage pressure, and failures appear in Memory, Requests, Health,
Capabilities, Governance, Admin (metadata only), Status, or the Right Drawer.
