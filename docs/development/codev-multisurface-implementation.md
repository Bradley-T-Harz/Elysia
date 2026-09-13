# Codev multi-surface implementation evidence

Product versions remain 1.0.0. The Codev Add-on and historical release artifacts
are read-only throughout this implementation. The four owner-supplied directives
were read in full before changes (master plus local, Marketplace, and Forge).

## Baseline

- Elysia: `25fd355607019cc0d0dbf5e33d9ac72727c1042d`, clean `main`.
- Codev: `20ae5e28dae0eb9e38a09e2a519ff1bdb94caa59`, clean `main`.
- Online: `9fecc07`, clean `main`; after fetch, `online/main` remains `c042605`.
- Online production: deployment `ff1939d0-ed57-4516-9784-dce3a5cf878d`, source `9fecc07`.
- Elysia published main: `6e9b9899ebeb211b94c255171edafc65ac6131b6`; separate release history.
- Baseline backend focus: 45 passed in the Elysia Python 3.11 environment.
- Baseline desktop: typecheck passed; 24 test files, 112 tests passed.
- Online: frontend/Functions typechecks, publisher contracts, synthetic build,
  desktop/mobile Forge CSP browser regression passed. Baseline screenshots and
  build preserved in task evidence outside source.

## Phase order and remaining gates

1. Canonical authority and v1 compatibility (qualified locally).
2. Neutral installation and capability truth (qualified locally).
3. Shared workspace/grant/approval/receipt/pairing contracts (qualified locally).
4. Install-gated local workroom and governed reasoning.
5. Revision-correct browser workspace, save/export/transfer and recovery.
6. Native pairing and narrow broker; no workspace authority from pairing.
7. Marketplace Sync Codev, reload and scoped assistance.
8. Forge Sync Codev, reload and scoped assistance.
9. Security, UI, migration, build/deploy and production qualification.
10. Deferred Add-on/release finalization record.

## Authority decisions

The legacy `/code` boolean/reference execution interface fails closed. Its
response schema and proposal-only Conversations remain compatible; real
consequential work uses the existing exact-approved `/coding` execution contract
through the canonical domain facade. New product UI must additionally enforce
installation, authenticated local identity, session and workspace grants.

Explicit repository revocation overrides configuration/environment approvals,
including descendant roots. Existing v1 registry entries remain recognizable;
new approvals record local-profile attribution. Websites never inherit them.

No public source history is force-pushed. Publication must preserve the existing
remote lineage and include only reviewed implementation changes.

## Phase 1 qualification

- Coding/v1 compatibility regression: 260 passed, 1 skipped (optional
  DatabaseForge interpreter absent). Binary inspection used a disposable test
  interpreter containing the repository-declared pyelftools/pefile versions.
- Final streaming-backup change: 50 focused filesystem, patch, document, visual,
  and data mutation tests passed, including a document larger than 16 MiB.
- New security checks cover denial precedence, actor-bound one-time approvals,
  symlink/hardlink/FIFO refusal, competing edits, destination no-overwrite,
  exact backup bytes, audit failure truth, real cancellation, output floods,
  timeout, emergency cancellation, and cross-client status isolation.
- Writes are descriptor-relative and atomic. Source revisions are rechecked;
  root locks serialize Codev writers. Independent external editors do not
  participate in advisory locking; clients must handle revision conflicts.
- General shell, package scripts, repository-controlled builds/tests, Git
  mutation, and network authority remain unavailable through this runner.
- Production schema inventory completed in an enforced READ ONLY transaction
  after explicit owner approval of the existing connection. It reports 66
  applied migrations through 20260910050000. No production migration applied.

## Phase 2 qualification

The native `/codev/installation` endpoint resolves a private, user-owned,
regular legacy receipt with package evidence. It never infers installation
from source directories, ports, or editor processes. Absent installations do
not trigger profile/runtime probing. Incompatible, malformed, insecure, or
unavailable evidence cannot enable the workroom. Legacy `/coding` installation
responses and the VS Code contract remain unchanged. The neutral receipt is
installation evidence, not remote binary attestation.

The capability manifest distinguishes exact file/patch/check operations from
unavailable build/test scripts, package execution, remote access, and cloud
models. No capability grants a workspace. Frontend gating is added in Phase 4.

## Phase 3 qualification

- Python contracts generate matching JSON Schema and TypeScript into Elysia
  desktop and Online. The generator's check mode verifies all four outputs.
- Grants and exact approvals bind actor, client, account, workspace, revision,
  scope, selected files, command, expiry, and grant epoch. Revocation increments
  the epoch; another grant cannot revive an old approval. Plans are consumed
  once even if multiple approval tickets were requested.
- Browser grants cannot authorize native file mutation or commands. Pairing
  sessions structurally allow zero workspace grants. Browser public-key
  contracts reject private key material.
- Workspace identity hashes actual UTF-8 bytes, path, and size; changing file
  availability or provenance does not silently change content identity. Unsafe
  paths, case collisions, and mismatched source hashes are refused.
- Shared qualification: 31 tests passed, followed by 18 focused contract tests
  after expiry/replay additions. Both desktop and Online typechecks passed.
- No new workroom or website UI is exposed in this phase.

## Phase 4 progress: cognition boundary

Before adding workroom UI, Codev gained a trusted in-process cognition scope.
The existing runtime continues to plan, route, budget, verify, and record a
content-free receipt. Codev requests admit only explicitly shared workspace or
handoff candidates, without personal memory/profile retrieval, ambient repo
scans, automatic tools, public research, or journal import. HTTP hints cannot
create this trusted scope. Ordinary Elysia request behavior retains its defaults.

Qualification: 31 cognition/runtime regression tests passed; an additional
integrated planner/router test verified context, network, and journal boundaries
(9 focused tests passed). Phase 4 workroom implementation remains in progress.

## Phase 4 native workroom checkpoint

The desktop now discovers the neutral installation truth through its existing
native credential bridge. Absent/unusable Codev creates no route, rail item,
placeholder, or Conversations control. Profile changes invalidate the cached
installation result and the workroom. The existing Coder conversation remains.
An explicit handoff shares only the visible draft instruction and continuity IDs;
mentioning a repository never grants it.

Native Codev sessions bind the exact authenticated local login session. Selecting
an owned, guarded repository creates no access grant. File-name inspection,
selected contents, reviewed writes, and the fixed Git check have explicit grants.
New session grants do not populate the legacy ambient repository registry.

The workroom supports governed local reasoning, selected text inspection/editing,
exact diff approval, fixed command planning and real process status/cancellation,
revocation, and truthful verification/backup receipts. Source changes preserve
unsaved buffers and require a fresh review; room navigation preserves the session.
Same-user logout/login, account changes, grant revocation/expiry, and cancellation
prevent an in-flight cognition response from being returned. Grant revocation
also signals owned workspace requests and commands. Recovery/status access remains
possible if a selected folder disappears. Repository-controlled build/test/package
scripts remain unavailable under their existing isolated-worker requirement.

Visual evidence uses the real shell/components with synthetic account,
installation, API and native-dialog fixtures; it does not claim a live model or
packaged native-dialog run. The absent-Codev DOM matched the pre-change baseline
exactly, and both screenshots have SHA-256
`fe0f158c629bdd136f169ed5b44af611e1de390c874ae293d7ac24ac0af8f368`.
The installed flow passed selection, sharing, review, approval/receipt rendering,
unsaved navigation continuity, and narrow-layout overflow checks. Wide empty,
review, receipt and narrow file screenshots were inspected. Artifacts are under
`/tmp/codev-implementation-20260913/native-visual`; fixture-only Vite HMR WebSocket
connections were refused by browser local-network policy, without page errors.
The website pairing transport still requires its own real origin/browser gate.

Native checkpoint qualification: 302 backend Codev/coding tests passed and one
optional DatabaseForge interpreter test skipped; the final command-plan display
check passed all seven native-action tests. Desktop production build/typecheck
passed and 25 test files / 120 tests passed. Generated contracts verified in all
four destinations. Diff whitespace checks passed. Native API tests require the
desktop credential even for session-bound reads, status, receipts, and cancellation.
No Codev Add-on file, product version, public release artifact, or website UI was
changed by this native checkpoint. Website pairing controls follow Phase 5.

## Phase 6 pairing and broker checkpoint

The native workroom now offers explicit website pairing review. A five-minute
Online intent binds the exact production origin, website account/login, page
surface, browser session and browser P-256 public key. The local user separately
reviews the website account and confirms. The native adapter rechecks installation
and its exact local login; native and website account IDs are never equated.
The native API bearer never enters browser or cloud pairing payloads. Native
confirmation uses a distinct short-lived RAM secret; pairing grants no workspace.

`core/codev/pairing.py` owns the native binding and lease. The dedicated broker
binds only `127.0.0.1:47321`, with exclusive listener ownership, exact Host/Origin,
POST allowlisting, bounded bodies/connections/work, request rate limits, strict
JSON, P-256 request/response signatures and nonce replay resistance. Responses
are tied to the request nonce/hash and the pinned native public key. There is no
broad API proxy, arbitrary filesystem endpoint, command endpoint or URL forwarder.
Browser source enters only `browser_workspaces.py` under a later explicit grant;
only selected text (40 files, 128 KiB each, 1 MiB aggregate) is admitted. Other
files carry metadata. Browser plans use the same grant/plan/approval authority;
authorization consumes an exact one-use plan without changing native files. The
owning browser must still apply its revision/hash comparison. Grant revocation
clears source-bearing plans and cancels scoped cognition.

The browser and native adapters share `_governed_chat`, the existing planner,
router, local invoker, compute governor, and context budget. The invoker's Codev
context now pins literal local Ollama and rejects inherited proxies/redirects.
Personal memory, automatic journals, repository tools and remote providers cannot
expand this context. Native authority is monitored every half-second; browser
cognition also rechecks its live website lease every two seconds and before a
response is returned. The broker reserves capacity by allowing at most four
simultaneous browser cognition requests among eight connection slots.

Qualification: 65 focused backend tests passed, including real socket and
Chromium transport tests; 120 existing desktop tests passed before adding the
pairing interaction, and the final nine workroom/pairing interaction tests passed.
Desktop build and typechecks passed. The interaction fixture holds an old list
response across local review to prove it cannot erase the reviewed account.
Chromium 151.0.7922.34 used normal browser security and an actual signed Python
broker: the original CSP and denied loopback permission each caused zero broker
requests; the proposed single-origin CSP allowance plus granted loopback permission
allowed a signed connection and exact browser patch. Full LICENSE and binary
hashes were unchanged; replay, impostor native key, private-key export and account
change were rejected. Identity/provider adapters were synthetic; this is not a
production-account, installed-release, or manual native-dialog qualification.
Evidence: `/tmp/codev-implementation-20260913/{backend-broker-final-phase6.log,signed-broker-browser-phase6.json,desktop-pairing-phase6.log}`.

Online's additive pairing migration replayed with all 67 current migrations in a
network-disabled disposable PostgreSQL instance. Pairing/login/role-isolation tests
passed and `plpgsql_check` found no error-level findings across 576 governed
function names. The approved production inventory was metadata-only in an enforced
READ ONLY transaction. No production migration, push or deployment has occurred.
Online CSP/route exposure and visible Sync controls remain pending the next phases.
Codev Add-on, historical artifacts, and all Elysia/Codev versions remain unchanged.

## Phase 7 browser lifecycle qualification

The native broker now supports a signed, zero-authority workspace reset for the
required browser refresh. It removes source, pending plans and cognition while
preserving grant epoch tombstones; an old share/approval cannot become current by
refreshing. Workspace revocation is idempotent within the exact actor. Browser
cognition receives the explicitly granted, bounded file inventory plus only the
selected contents. No-op proposals are rejected.

Nineteen broker/security tests and two actual Chromium transport/full-Marketplace
tests passed (21 total). The Marketplace test uses the actual built page and real
loopback signatures while isolating account, installation and model-provider
adapters. It verifies required native confirmation/reload, no pairing source share,
read/proposal scopes, stale patches, copied-tab isolation, original LICENSE/binary
preservation and exact browser recovery. No production/native-install qualification
is claimed. The current Codev Add-on remains untouched at v1.0.0.

## Phase 8 website qualification

The actual-page browser integration now covers both Marketplace and Forge by
default. Forge's existing controller, draft lock and pending-operation state
constrain the same shared Codev client. A required sync refresh preserved the
dirty README, selected draft, active file and complete LICENSE/binary contents.
Per-file review produced a fresh exact plan; rejected file content stayed intact.
Locked draft editing failed closed and a revision copy received no inherited
Codev scope. Browser account switching sent a signed native revocation and removed
the old source grant. A delayed browser intent across A → B → A did not revive
old authority. These are actual browser/broker checks with synthetic installation,
account and provider adapters; production installation/provider verification is
still a separate final gate.

## Phase 9 qualification and publication preparation

The broad native regression ran 585 cases: 583 passed, one optional interpreter
case skipped, and one stale diagnostic-string assertion failed. The assertion
now checks the existing exact-approved patch wording without relaxing any
permission expectation; the focused capability/contracts/publication checks
passed all 47 cases. Desktop qualification passed 121 tests in 26 files. A final
35-case installation/native-action/contracts run passed.

The packaged source candidate uses the existing public Git lineage in a separate
checkout, preserving private local history and operator repository configuration.
Its first Core binary imported all required new Codev routes. Native and desktop
compilation/CSP checks passed; Debian normalization used the recorded source
timestamp. The real unchanged Codev 1.0.0 VSIX installed through the packaged CLI
into a disposable VS Code profile. The actual native API passed absent → installed
but unavailable → authenticated/ready, credential refusal, zero authority from
selection, exact file grants, patch/replay refusal and a real Git check. Full
governed model requests timed out in initial runs; this remains an open runtime
qualification item at this checkpoint, not a successful-model claim.

The signed broker and both actual website workflows passed in Chromium
151.0.7922.34 and Firefox 153.0 with normal browser security. Both engines proved
unsynced DOM/screenshot identity after removing the single Sync slot, scoped
sharing, mandatory reload, exact revision changes, denied files, revocation,
account changes, complete LICENSE/binary preservation, recovery and draft locks.
Firefox Monaco qualification now uses keyboard events and verifies current export
bytes before Sync. Desktop/mobile Firefox views were manually inspected.

Production rejected the generic Python user agent before the request reached
Pages. The native client now honestly identifies Elysia-Codev 1.0.0 and its pairing
contract; the existing edge accepted that identification without a rule change.
No proxy inheritance, redirect, destination, credential or permission rule changed.

Online migration `20260913010000_codev_pairing_sessions.sql` was applied in a
hash-pinned transaction after a successful exact rehearsal and replay refusal.
Post-application inventory shows 67 migrations, two added private tables with
forced RLS, nine functions and one audit trigger. Existing policies and objects
were not removed or altered. Migration SHA-256:
`d931217ae703ab97ae464a56db9aaedfe7ae9465e7d46c57b42a96b281508193`.
Publication and production website deployment/verification follow this checkpoint.
