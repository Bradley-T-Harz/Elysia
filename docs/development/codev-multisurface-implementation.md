# Codev multi-surface implementation evidence

## Portable installed-product correction (qualification in progress)

The later owner directive authorizes the canonical VS Code client changes required for portable installation. Earlier receipt/profile-based installation descriptions in this report are historical. Codev Core is now a separate Debian payload; the editor is optional. The authoritative package manifest, private Unix service and generated client contracts separate installation, runtime readiness, local account state, workspace grants and website pairing.

The real failure combined an older installed Elysia package, a dynamically selected desktop TCP port, the adapter's fixed port-8000 assumption and receipt/readiness gating. Unit and synthetic browser checks had not exercised that exact installed lifecycle. The new compiled native and Core package lifecycle gates run without a source environment, and actual Debian 13/Ubuntu 24.04 guests cover ordinary users, both installation orders, reboot, absence, reinstall and an empty workroom. The install contract is documented in [Codev Core installation](../release/CODEV_DEVELOPER_PROFILE_INSTALL.md).

Recovery validation: 1,405 backend tests passed, four were explicitly skipped, and two GIS failures reproduced against the unchanged baseline. Desktop React: 123 passed in 26 files. Rust: 9 passed, one ignored subprocess fixture. VS Code adapter: 23 passed. The compiled artifact lifecycle gate passed installation, private runtime identity, zero initial authority, permission damage/repair, uninstall/reinstall and preservation of local state. These counts do not substitute for final artifact, actual-machine and production evidence. Final committed build identities and closeout results will be recorded after those gates finish.


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


## Production model qualification follow-up — 13 September 2026

The preceding phase sections record their state at each checkpoint. Online is now
pushed at `e8fa5cad8f4fbf80beb2abf8e9c0496a3b534915`, migration
`20260913010000_codev_pairing_sessions.sql` is applied, and production Pages
`60239324-be2b-46dd-bd74-5157584ba8c3` is live. The follow-up changes only native
runtime/transport and tests; it requires no additional website deployment or
migration. Elysia and the unchanged Codev Add-on remain 1.0.0.

The original website timeout had several interacting causes, established from
actual local provider options/timing and the runtime path:

- A bounded Quick explanation selected the configured 24B general model on CPU.
  It waited 180 seconds before headers; a fallback then received a fresh full
  timeout although the website allows 240 seconds for the entire request.
- Coding proposal wording was classified as requiring tools even though shared
  Codev chat only returns text/proposals. That unnecessarily raised the requested
  Quick gear to research/engineering and a larger coding model/output budget.
- A blocked provider read could ignore cancellation before response headers or
  between streamed tokens. Partial output must never count as a completed answer.
- Native desktop transport allowed 120 seconds, shorter than the model request.

Codev now uses the existing within-role latency selection for a bounded Quick
request when the user has balanced preference. Explicit quality preference,
role membership, installation and compute admission remain authoritative. Ordinary
Elysia routing does not receive this Codev-only flag. Chat no longer claims tool
execution is required merely because it discusses code. Stakes, verification,
resource and authority floors still apply; actual tools remain separately gated.

The invoker shares a total deadline across preflight and attempts. A scoped Codev
request can invoke only the concrete model whose compute was admitted; a failed
provider cannot launch another model with that admission. A subsequent request
can re-route from updated measured health and seek a new admission. A request-owned
socket monitor interrupts only its literal-loopback provider connection on cancel
or deadline, including before headers; completion requires a terminal provider
frame. It never kills/unloads shared Ollama, changes GPU policy, enables proxies,
follows redirects, or uses cloud models.

Both Codev clients now use a trusted 210-second request deadline, including planning
and preflight, inside their 240-second transport allowance. An explicit shorter
internal timeout still wins. The desktop extension is limited to POST /codev/chat;
other desktop API requests keep 120 seconds. Late responses are withheld and
installation/account/grant/lease checks still run before delivery.

Focused validation: 157 native/runtime/governance/security regressions passed in
one serialized run; later routing-scope refinement passed 78 tests. The final
whole-request deadline change passed 71 affected Python tests and all 7 desktop
Rust tests. Real Chromium/Firefox signed broker checks passed 2/2 after this change.
The separate public checkout skipped these browser cases because its adjacent
Online checkout is absent; those skips are not counted as passes. Its source and
history hygiene scan passed with zero findings.

Actual production model qualification passed with the rebuilt v1.0.0 package
(Core SHA-256 `528263a9652864313874d01484a3afe775ffc570735daf2924ed42a15c1b454d`,
Debian SHA-256 `770739b743437f8c77c246173845c72cde9df9b9021a89eec243877da5e1ec46`).
The package source is public commit `ddc94ec594a352724794781fa6f690b6230a1101`.

The complete CPU run used real production pages, real account sessions and the
unchanged VSIX installed into a disposable native profile. Marketplace reasoning
and proposal completed in 186.522s and 203.338s; Forge in 188.700s and 206.650s.
Both pages separately granted read/proposal context, received real local
`granite3.3:8b` proposals, reviewed current hashes/revisions, and explicitly applied
the exact replacement. Marketplace changed `answer` 41 to 42 at revision 3 to 4;
Forge changed `retryLimit` 3 to 5 at revision 2 to 3. The harness did not supply
replacement JSON or intercept the provider/API. Original source backups and all
unselected LICENSE/binary/manifest bytes were verified. Replayed approvals returned
403; an unrelated account could not access the pairing. Native revocation
cancelled a fifth real inference (4.458s) and preserved the browser workspace.

A normal automatic-compute repeat also passed both actual proposal/review/apply
flows, taking 182.689s for Marketplace and 64.215s for Forge, with another real
inference cancelled by revocation (4.334s). The governor admitted its normal hybrid
`cuda:0` path with CPU fallback allowed; provider residency reported zero GPU bytes.
This qualifies the automatic setting, not GPU execution/performance. An earlier
automatic harness used the wrong literal `gpu` device identifier and stopped after
a successful 171.086s model response; the corrected harness checks the canonical
device identifier, concrete model admission and resource ceiling.

Both final runs reported `passed: true`, zero page errors, zero initial workspace
grants, no implicit authority increase and no research network access. Their
review, applied/recovery and revoked-state screenshots were manually inspected.
Browser loopback permission was explicitly configured under normal browser
security; interactive CAPTCHA and the human OS/browser permission dialogs are not
qualified by this automation. Repository tests/builds were not executed by these
model edits: patch verification means exact approved browser bytes.

CPU prefill dominated latency and the slowest browser request took 209.001s.
This qualification covers bounded Quick requests and selected small files on this
host; it does not guarantee performance or complete context for larger workspaces,
all models/gears, or other hardware. Deadline exhaustion still fails closed.
Evidence: `/tmp/codev-implementation-20260913/production-model-full-budget-cpu/results.json`
and `/tmp/codev-implementation-20260913/production-model-proposals-automatic/results.json`.
The owner evidence report records exact source inventory, production/security
rechecks, fixture-cleanup status, commits and artifact hashes.

The reviewed public source is pushed to `codev-multisurface-v1-integration` in
https://github.com/Bradley-T-Harz/Elysia/pull/2. GitHub's existing main protection
requires an independent approving review; the PR author/last pusher cannot satisfy
it by self-review. Main is not merged. No protection or repository auto-merge
setting was changed. Private local history/configuration remains excluded.
