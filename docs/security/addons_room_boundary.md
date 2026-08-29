# Add-ons Room Boundary

## Purpose

The Add-ons room is a Marketplace-gated operator surface for browsing approved Marketplace add-on manifests, viewing dependency/action declarations, saving add-ons to the Marketplace account, and preparing local action previews.

It is not an execution room in V0.

## Gate

The room must remain locked unless all of these are true:

1. A Supabase Marketplace session exists in the desktop frontend.
2. The local backend Marketplace link says `linked=true`.
3. The Supabase session user id matches the locally stored `marketplace_user_id`.

If any condition fails, the room must show a locked state and must not fetch user-specific Marketplace data.

## What May Leave Local Control

When unlocked, the desktop frontend may send the Marketplace/Supabase session token to Supabase to read:

- approved add-on catalog rows
- the signed-in user's saved add-on slugs

Saving/removing add-ons writes only Marketplace add-on slugs to Supabase.

## What Must Not Leave Local Control

The Add-ons room must not upload:

- local Elysia password
- local files
- memory
- request traces
- dependency inventory
- local paths
- private local profile fields

## Preview-Only Local Actions

Install, enable, disable, and uninstall are preview-only. Clicking a preview must show:

- exact add-on
- declared action
- dependencies involved
- local/network boundary
- local execution is not implemented yet
- future execution will require local Elysia password/operator approval

No command execution, package manager, shell, worker, file mutation, or dependency installation is live in this room.
