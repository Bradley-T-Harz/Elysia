# Account Identity Boundary

## Purpose

The Identity + Access Gate is a sealed local account system, not normal Elysia Memory. It lets the desktop chamber unlock for the authenticated local user while giving Elysia only a tiny humane profile projection.

## Private Account Store

The private account store is local-only and sealed from normal runtime, tool, worker, memory, and trace access.

Local state:

```text
data/identity/
  elysia_identity.sqlite
  current_session.json
  profile_photos/
```

This local state must remain gitignored and should not be published.

## Elysia-Visible Projection

Elysia may eventually see only:

- username/name
- interests
- bio
- profile photo asset reference or availability flag

This projection may be used as current runtime context, but it must not become Memory by default. Chat response data may surface projection truth, but not private profile values.

## Sealed Fields

Elysia, skills, workers, tools, request traces, logs, journals, and memory surfaces must not see:

- password
- password hash
- birthdate
- emails
- phone number
- social media
- GitHub
- city/state
- session token
- session token hash
- original profile photo path

GitHub and social media are intentionally sealed even though they might be useful context later. A later opt-in policy would be required before that changes.

## Passwords

Passwords must never be stored in plaintext. The account service uses `pwdlib[argon2]` through `PasswordHash.recommended()`. Password hashes must never appear in API responses, request traces, logs, journals, workers, or runtime context.

## Profile Photos

Profile photo V1 should allow only:

- JPG
- JPEG
- PNG
- WEBP

The selected file should be copied into controlled local identity storage. Runtime and UI-safe summaries should use an internal asset reference, not the original filesystem path. PDF profile photos are not part of V1.

## Request Trace And Logging

Request traces may record compact account boundary truth, such as whether a visible projection was used, but must not record private values or session values. Logs and account events should use safe summaries only, such as `profile_updated` or `session_revoked`.

## Memory Rule

Account/profile data must not be imported into normal Memory. The visible projection is current context only.

## Manual Verification Checklist

- `config/policies/account_privacy.yaml` loads.
- `config/ui/account_colors.yaml` loads and contains exactly 10 colors.
- Visible profile fields are explicit.
- Sealed fields are explicit.
- No sealed field appears in the visible projection.
- Password dependency declares Argon2id-capable hashing support.
- Frontend account gate does not mount `AppShell` until account state permits it.
- Logout revokes the local session.
