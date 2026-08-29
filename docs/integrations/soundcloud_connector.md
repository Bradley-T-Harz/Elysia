# Optional SoundCloud connector

SoundCloud is an optional, user-configured external connector. It is not a Base Elysia dependency and Elysia ships no SoundCloud account, client credential, or operator-specific configuration.

## Setup contract

1. Register an application through SoundCloud's developer process.
2. Configure `ELYSIA_SOUNDCLOUD_CLIENT_ID` and `ELYSIA_SOUNDCLOUD_REDIRECT_URI` in the user's local override. A client secret is accepted only where the registered application requires one and must remain local.
3. Turn Internet ON in Elysia Settings.
4. Open a Project, choose **SoundCloud**, and authorize the account using OAuth 2.1 authorization code with PKCE.
5. Complete the local callback handoff by entering the returned authorization code and state.

The PKCE verifier, pending state, encryption key, and token payload are account-scoped under Elysia's XDG state directory with owner-only permissions. Tokens never enter webview JavaScript or API responses. Disconnecting removes the exact local connector credential and pending authorization state.

## Boundaries

- Internet OFF blocks authorization and token exchange before network access.
- Token exchange uses a fixed HTTPS SoundCloud host and refuses cross-host redirects.
- The connector cannot read Project sources, Memory, journals, credentials, or unrelated account state.
- SoundCloud receives only requests the user explicitly initiates after its own authorization page.
- A registered SoundCloud developer application is a real external prerequisite; Elysia cannot create or accept that application on a user's behalf.

The connector preserves the historical SoundCloud capability as an opt-in integration without turning SoundCloud into Elysia infrastructure.
