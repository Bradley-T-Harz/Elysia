# Account API Contract

## Status

This document is the local account/API contract for the Identity + Access Gate.
The account service, routes, frontend gate, terminal setup helper, and Linux
desktop installer configuration are now implemented, but the privacy rules here
remain the binding contract.

The account API must remain a local bridge surface. Routes should be thin and delegate to account service logic.

## Standard Envelope

Account endpoints should use the existing Elysia API envelope style:

```json
{
  "status": "ok",
  "request_id": "req_example",
  "api_version": "1.0.0",
  "contract_version": "phase1-ui-contract-1.0",
  "timestamp_utc": "2026-06-01T00:00:00Z",
  "result_type": "account_state",
  "capability_state": "live",
  "locality": "local",
  "approval_state": "not_needed",
  "warnings": [],
  "errors": [],
  "data": {}
}
```

Examples in this document use placeholder values only. They must not include real private profile values.

## Routes

### `GET /account/state`

Returns whether the desktop should show first-run user creation, login, or the app shell.

Safe fields:

- `has_user`
- `is_authenticated`
- `requires_user_creation`
- `requires_login`
- `active_username`
- `account_status`

### `POST /account/create`

Creates the first local account, stores only a password hash, creates the private profile, and creates a persistent local session.

Request may include:

- `username`
- `password`
- `interests`
- `bio`
- `birthdate`
- `emails`
- `phone_number`
- `social_media`
- `github`
- `city_state`
- `profile_color_id`
- `profile_photo_asset_id`

Response must not include:

- password
- password hash
- session token
- original profile photo path

### `POST /account/login`

Verifies username/password and creates a persistent local session. The password must be checked against a local password hash.

### `POST /account/logout`

Revokes the current local session and clears the current session pointer. Logout must invalidate the session, not merely hide the UI.

### `GET /account/profile`

Authenticated UI-only private profile read. This endpoint is for the user interface, not runtime context.

### `PUT /account/profile`

Authenticated UI-only private profile update. A blank password field in edit mode should mean “leave password unchanged.”

### `GET /account/profile/elysia-visible`

Returns only the Elysia-visible profile projection:

- `name_or_username`
- `interests`
- `bio`
- `profile_photo_asset_id`
- `profile_photo_available`

It must not include birthdate, emails, phone number, social media, GitHub, city/state, password hash, session token, or original profile photo path.

### `POST /account/profile-photo/select`

Accepts a trusted local UI/Tauri-selected image reference, validates it, copies it into controlled identity storage, and returns a safe asset reference.

Allowed V1 extensions:

- `.jpg`
- `.jpeg`
- `.png`
- `.webp`

The response must not include the original filesystem path.

### `DELETE /account/profile-photo`

Deletes or deactivates the current copied profile photo asset and clears the profile reference.

### `GET /account/profile-photo/{asset_id}/preview`

Returns the copied sealed profile photo bytes for the authenticated owner of the
asset. This route is for UI image rendering only.

It must not return JSON containing the private identity storage path or original
filesystem path. It must reject unavailable assets and assets not owned by the
current authenticated local user.

### `GET /account/colors`

Returns the 10 allowed page-local account colors from `config/ui/account_colors.yaml`.

### `GET /account/privacy`

Returns a user-facing privacy view derived from `config/policies/account_privacy.yaml`, including visible fields, sealed fields, and warnings that visible fields may be used as current Elysia context.

## Runtime Projection

The governed runtime may receive only the Elysia-visible projection:

- `name_or_username`
- `interests`
- `bio`
- `profile_photo_asset_id`
- `profile_photo_available`

Chat response data may expose only compact projection truth, such as whether the
projection was used and which allowed field names were present. It must not echo
the private profile or credential fields.

## Current Non-Goals

- No Tauri filesystem permission broadening.
- No account data in normal Memory.
- No password hash, session token, original profile-photo path, or private
  profile field exposure to runtime, tools, workers, traces, logs, or journals.
- No global Elysia theme changes from account colors.
