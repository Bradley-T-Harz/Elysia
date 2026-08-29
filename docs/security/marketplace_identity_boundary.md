# Marketplace Identity Boundary

## Purpose

The Marketplace link lets the local Elysia desktop chamber recognize a signed-in Marketplace account without merging it with the sealed local Elysia account.

The local Elysia account remains local. The Marketplace account remains Supabase/cloud-backed. They are separate identities with separate passwords.

## Password Boundary

The local Elysia password is only for local account login, sensitive rooms, and future operator approval. It must never be sent to Supabase or the Marketplace.

The Marketplace password is only for Supabase Marketplace login. It must never be sent to the local Elysia backend. In V0, the desktop frontend performs Marketplace sign-in and sends only redacted link metadata to the local API.

## Local Link Metadata

The local backend may store only:

- Marketplace user id
- Marketplace email
- Marketplace username
- Linked timestamp
- Legacy compatibility timestamp, if a retired sync-record endpoint is called
- Empty sync field lists only

The local backend must not store:

- Marketplace password
- Supabase access token
- Supabase refresh token
- service-role key
- local Elysia password
- local session token
- local files
- memory
- request traces
- dependency inventory
- local paths

## Runtime Boundary

Runtime, chat, tools, workers, memory, and request traces must not receive Marketplace sessions, tokens, or private local Personal Identity fields.

The existing Elysia-visible identity projection remains narrow:

- username/name
- interests
- Story (stored internally as `bio`)
- identity photo asset reference or availability

Marketplace link status is an operator/account UI surface, not model context.

## Retired Profile Sync Boundary

Profile sync through Marketplace Link is retired. Commons Profile is edited online. Personal Identity stays sealed, local-first, and separate.

Allowed sync candidates: none.

Local-only fields:

- birthdate
- emails
- phone number
- social media
- GitHub
- city/state
- Story
- original profile photo path
- identity storage path
- memory, files, vaults, logs, chats, and request traces

## Add-ons Boundary

Marketplace add-on manifests may be imported for local operator review. They do not grant local execution authority.

Install, uninstall, enable, and disable actions must remain inside a future password-gated local Add-ons room with explicit approval, audit truth, and rollback notes.
