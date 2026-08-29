# Marketplace Link API Contract

## Scope

This API stores only local, redacted Marketplace link metadata. It does not authenticate against Supabase, receive Marketplace passwords, store Supabase tokens, or install add-ons.

## Endpoints

### `GET /marketplace/link/status`

Returns the current local Marketplace link status.

Safe fields:

- `linked`
- `marketplace_user_id`
- `marketplace_email`
- `marketplace_username`
- `linked_at_utc`
- `last_sync_at_utc`
- `sync_enabled_fields` (legacy compatibility; current allowed set is empty)
- `password_stored`
- `token_stored`
- `local_private_profile_shared`

### `POST /marketplace/link`

Stores local link metadata after the desktop frontend has authenticated with Marketplace/Supabase.

Accepted fields:

- `marketplace_user_id`
- `marketplace_email`
- `marketplace_username`
- `sync_enabled_fields` (filtered to an empty list; Marketplace Link does not sync Personal Identity fields)

Forbidden fields are rejected by schema strictness and must never be accepted:

- passwords
- password hashes
- Supabase access tokens
- Supabase refresh tokens
- service-role keys
- local files
- memory
- request traces
- dependency inventory
- local paths

### `DELETE /marketplace/link`

Removes local Marketplace link metadata. It does not affect the Supabase account.

## Locality

These endpoints are local API endpoints. Marketplace authentication happens in the desktop frontend against Supabase using the browser-safe anon key.

Marketplace Link is for add-ons and account-gated Marketplace functions only. It does not sync Personal Identity, Story, local photos, memory, files, vaults, logs, chats, request traces, credentials, or machine data.
