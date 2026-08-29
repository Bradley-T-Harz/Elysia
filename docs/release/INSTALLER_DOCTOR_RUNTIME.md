# Elysia Core Installer, Doctor, and Runtime Contract

Status: Elysia v1.0.0 installation, Doctor, and lifecycle contract

This contract covers local Linux package, Setup, profile, Doctor, and lifecycle
behavior. Exact release artifacts remain authoritative only through the signed
release manifest and canonical external release surfaces.

## User-local layout

Elysia resolves runtime state through the XDG base-directory contract:

| Class | Default when the XDG variable is absent | Elysia-owned use |
|---|---|---|
| Config | `$HOME/.config/elysia` | Profile/model overrides and future user policy |
| Data | `$HOME/.local/share/elysia` | Conversations, projects, identity, artifacts, ingest, installed runtime payload |
| Cache | `$HOME/.cache/elysia` | Rebuildable cache/model metadata |
| State | `$HOME/.local/state/elysia` | Logs, doctor/install receipts, audit and recovery state |
| Runtime | `$XDG_RUNTIME_DIR/elysia` | Session-local API credential and process coordination |

If `XDG_RUNTIME_DIR` is absent, Elysia uses the private state fallback
`$XDG_STATE_HOME/elysia/runtime`. Normal status and diagnostics expose only the
labels above, never resolved user paths.

Tracked config remains an application resource. Operator overrides live in XDG
config and are gitignored by location rather than copied into the source tree.
Legacy source-tree `data/`, `logs/`, and journal locations are not migrated or
deleted automatically. A later explicitly approved migration must preview
categories, copy without deleting the source, verify results, and provide
recovery before changing a live user store.

## Source and packaged modes

- `source` mode is an explicit development contract. The developer launcher
  starts the API on loopback and local HTTP mutation authentication is marked
  development-disabled.
- `packaged` mode requires a private bearer credential for every POST, PUT,
  PATCH, and DELETE request. Reads remain available for startup and diagnosis.
- The packaged Tauri bootstrap may launch only its package-owned sibling
  `elysia` Core executable with fixed `serve`, loopback, and packaged-mode
  arguments. Unless an explicit test/operator port is supplied, each Desktop
  session selects an unoccupied loopback port so a stale or unrelated listener
  cannot be mistaken for its owned Core. The separate user-local source installer retains its versioned XDG
  runtime payload and launcher contract. Neither path accepts shell text or an
  arbitrary executable from the webview.
- The API process is owned by the Desktop instance that started it and is
  stopped on Desktop exit. An already reachable loopback API is not replaced or
  trusted; an explicit-port collision fails closed as `port_conflict`.

The credential is generated locally with private file permissions and stored in
XDG runtime state. Tauri reads it only for bridge request headers. Its value is
not returned by API status routes, rendered, logged, or included in diagnostic
summaries. Rotation invalidates the old value.

## Core installer

`scripts/install_core.sh` defaults to `--dry-run`. `--apply`:

1. creates private Elysia XDG roots;
2. stages the tracked `app/`, `core/`, portable `config/`, `derived/`, and only
   the disabled/bounded worker contract modules imported by Core routes into a
   versioned user-data release; machine profiles, optional worker interpreter
   configs, heavy model-vault configs, and heavy worker payloads are deliberately
   excluded from Core;
3. atomically switches the `current` application link;
4. installs the fixed user-local API launcher;
5. either verifies already-present Core Python imports or installs only from an
   explicitly supplied offline wheelhouse with `--no-index`;
6. writes a sanitized install receipt.

An operator may select an already provisioned interpreter with
`--python ABSOLUTE_PATH`. Elysia records that selection only inside the private
user-local application runtime so its launcher and verifier use the same
interpreter; normal API/UI/doctor output never surfaces the path. An offline
wheelhouse instead creates a user-local virtual environment.

It uses no sudo, system service mutation, external network, optional profile,
model download, worker enablement, cloud connection, or user-data deletion.
Desktop `.deb`/AppImage installation remains a separate package-manager action.
For a user-local `.deb` extraction, `scripts/install_desktop_user.sh` stages an
immutable digest-keyed release, atomically selects one `current` payload, creates
one stable user-local launcher, and generates the standard application entry
plus any explicitly requested convenience shortcuts. Every generated entry
converges on that same stable launcher; prior release payloads and user data are
preserved.

## Doctor and verify

Run from source with:

```bash
python -m app.cli.doctor --probe-local-services
```

Run against a user-local installed payload with:

```bash
scripts/verify_install.sh
```

The packaged Desktop selects an available loopback port for its owned Core.
An explicitly configured source/test/operator launch may use port 8000 or
another allowlisted loopback port and can be verified with `--api-port PORT`;
doctor never probes a non-loopback host.

The doctor checks Core profile/dependencies, XDG writability, API reachability,
authentication initialization, Desktop/API version alignment, optional
loopback-provider reachability, and worker/profile/Lab gating. It does not load
a model, send a prompt, search the web, install, download, repair, start a
worker, enable a sandbox, or mutate a service. `--record` writes only a small
allowlisted status receipt so first-run truth can distinguish “never recorded”
from “verified.”

The read-only Desktop/API surface is `GET /status/doctor`. It never records a
run and returns no raw paths, tokens, logs, environment values, or private
contents.

## CSP and origins

The packaged webview CSP defaults to self-only content, permits bridge connects
to `http://127.0.0.1:8000` and Tauri IPC, and permits HTTPS connections only to
Supabase-hosted Marketplace endpoints. Every Marketplace request first rereads
the authoritative account-scoped Internet master and fails closed while it is
OFF or unreadable. The build-configured Marketplace URL remains the request
target; the CSP wildcard does not select a service. Objects and framing remain
blocked. API CORS allowlists the two local Vite development origins, local
preview origins, and known Tauri packaged origins. Local mutations still
require the native-held credential in packaged mode.

Stable public Desktop builds track one reviewed production configuration at
`apps/elysia-desktop/.env.production`. It contains only the canonical Elysia
Ecobotics Marketplace URL, the public Supabase project URL, and Supabase's
publishable browser key. That key is not a privileged credential: database and
account authority remain enforced by Supabase authentication, row-level policy,
Elysia's account-scoped Internet master, and local governance. A service-role
key, private operator secret, or local `.env.local` file must never ship. This
tracked production boundary prevents a clean source build from silently losing
Marketplace capability or inheriting workstation-local configuration.

## Upgrade, repair, rollback, and uninstall

Upgrades install a versioned application payload and atomically change the
active application link. They do not overwrite XDG config/data/state.
`scripts/uninstall_core.sh` defaults to dry-run; apply moves the application
runtime and launcher into a recoverable XDG state location. Config,
conversations, projects, artifacts, identity, models, cache, logs, and runtime
credentials remain. No command in this pass deletes user data.

The signed in-app lifecycle is specifically the managed Core-runtime lane. Its
manifest binds the release archive, version, memory-schema target, declared
migrations, and component changes; the detached Ed25519 signature is checked
before staging. Activation is transactional, Doctor-gated, and restores the
prior checkpoint if a migration or later phase fails. Repair reacquires exact
package-owned bytes instead of resetting Memory. Rollback refuses an absent or
schema-incompatible target.

Every lifecycle mutation requires an authenticated Local Admin or Installation
Owner to create an exact preview and explicitly approve that same preview in
the same account session. Ordinary users may inspect lifecycle status but
cannot exercise installation-wide mutation authority. Elysia never silently
auto-updates, and verification errors never fall back to unsigned material.
The public/private trust split, recovery, rotation, revocation, compromise, and
total-loss procedures are defined in
[`UPDATER_SIGNING_TRUST.md`](UPDATER_SIGNING_TRUST.md).

Desktop distribution lifecycle stays truthful to its form:

- system `.deb`: the operating-system package manager owns install/update/remove;
- AppImage: the user owns explicit executable replacement/removal while XDG
  personal state remains stable;
- user-local `.deb` extraction: receipt-bound digest releases provide install,
  repair, atomic rollback, recoverable uninstall, and reinstall with preserved
  data;
- source install: an explicit development lane, never the ordinary packaged
  lifecycle.

None of these lanes silently invokes sudo, silently downloads a moving artifact,
or treats deletion of personal state as repair.

## Release qualification and historical lineage

- The retained release evidence includes clean-environment, profile, first-run,
  onboarding, lifecycle, accessibility, failure-injection, and blank-state
  proof for every release-supported path.
- The signed release manifest binds the exact v1.0.0 artifact family,
  checksums, signatures, SBOMs, and provenance. Live availability is reported
  only by the canonical GitHub Release and Elysia Archive records.
- The historical `Elysia_App/Elysia.desktop` development candidate remains
  excluded because it contained checkout-specific paths. A local operational
  `Elysia_App/` may now receive a generated convenience entry from
  `install_desktop_user.sh`; that entry points to the same canonical installed
  launcher as the standard application entry and is not public source.
- Existing private source-tree state is not migrated automatically.
- Optional workers, model providers, and machine-specific overrides remain
  profile- or Lab-gated and are excluded from the self-contained Core payload.
