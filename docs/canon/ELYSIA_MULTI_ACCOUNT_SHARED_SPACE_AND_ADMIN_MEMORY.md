# Multi-account, Shared Space, and Admin Memory Boundaries

## Local account isolation

Each local profile owns separate Memory, Conversations, Projects, settings,
keys, jobs, and archive registry entries. Every Memory operation starts with an
authenticated local principal. Ownership or Shared Space ACL is checked before
content lookup, ranking, graph traversal, mutation, export, or deletion.

## Deliberate sharing

A Normal memory can be shared only through an explicit Shared Space operation
and exact consequence approval. If User A shares Memory M into Space X and
User B is an authorized reader:

- User A remains the owner;
- Space X remains the sharing authority;
- User B can retrieve it under the Space X ACL;
- it is never relabeled or copied as User B's personal memory;
- Private memory requires an exact, disclosed declassification to Normal before
  the move completes; Sealed memory cannot enter a Shared Space.

Membership has a complete governed lifecycle. An owner may issue a pending
invitation for a non-owner role; the invited local profile explicitly accepts
or declines it. Direct membership, role changes, and revocation require exact
consequence approval and produce content-free receipts. Revocation or downgrade
takes effect immediately for every shared record, including records originally
created by that member: record ownership is provenance, never an ACL bypass.

Restoring a portable archive into another installation creates its spaces with
the restoring owner as the only member. External local identities are not
federated by name or ID; the owner must deliberately invite or add local
members later.

## Installation governance

Installation Owner/Admin can manage profile roles, managed-profile state,
capability/install policy, resources, connectors, objective security events,
emergency state, aggregate storage, and bounded policy ceilings. It cannot read
another user's content merely because it is Admin.

Allowed Admin memory truth includes:

- per-profile aggregate record/object/archive byte counts;
- storage budget/pressure and backup health;
- count/state of failed or interrupted maintenance jobs;
- subsystem and projection status;
- managed policy and blocked-operation events.

Disallowed Admin access includes bodies, titles, source labels, transcript,
project text, prompts, queries, model context, graph topology for protected
content, archive plaintext, recovery material, Private memory, and Sealed
memory. The Admin API reports which content authorities it queried; for the
memory aggregate that list is empty.

## Managed profiles

Supervision is visible to the managed user. Policy may cap or deny background
cognition, consolidation, managed backup, cold archival, CPU/RAM/VRAM,
storage budget, backup retention, autonomy, Internet, Add-ons, and external
mutation. Those ceilings do not transfer ownership and do not create a covert
monitoring channel.

## Online separation

Local account IDs, roles, and Admin state are not Website identities, badges,
Commune membership, or Marketplace publisher roles. No shared database or
automatic federation exists. An optional Marketplace connector, if enabled,
uses separate minimal credentials and does not send the local roster or memory
state.
