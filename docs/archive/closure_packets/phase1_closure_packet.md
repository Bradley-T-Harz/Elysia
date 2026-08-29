# Phase 1 Closure Packet

## Stage 15 matrix

- 3.1 Healthy startup: PASS
- 3.2 Ollama-offline startup: PASS if captured earlier; otherwise PARTIAL pending evidence link
- 3.3 API-bridge-offline startup: PASS if captured earlier; otherwise PARTIAL pending evidence link
- 3.4 Runtime-degraded startup: N/A with explanation. Request-level degraded/fallback truth was tested instead.
- Standard local request: PASS
- Fallback request: PASS
- Approval-needed request: PASS
- Blocked request: PASS if Packet 5 blocked evidence was captured; otherwise PARTIAL pending final blocked screenshot/payload
- Drawer truth: PASS
- Bottom bar truth: PASS
- Governance mutability truth: PASS
- Capability-manifest honesty: PASS
- Inactive/planned surfaces not fake-live: PASS

## Evidence

- screenshots:
  - Healthy local chat drawer state
  - Fallback/degraded drawer state
  - Approval-needed drawer state
  - Projects index/detail states
  - Memory room
  - Governance room
  - Status Menu / bottom bar
  - Quick Invoke
- terminal outputs:
  - Focused pytest runs passed
  - Broader pytest run passed
  - Frontend build passed
- payload captures:
  - /projects
  - /governance/state
  - /status/capabilities
- logs:
  - Launcher startup output
  - Ollama/service status where relevant

## Mismatches found

- Ordinary local chat was being treated too much like approval-needed work.
- Approval-needed requests were being described too much like blocked requests.
- Drawer cards sometimes stayed fake-live when rows said no active trace or no approval required.
- Projects drawer truth had fake-live Approval Needed and Request Trace cards.
- Capability manifest was honest, but the hook only exposed startup-level manifest status at first.
- Some shell copy still sounded like scaffolding or future-only planning language.

## Fixes applied

- Updated policy-gate behavior so low-risk local response generation is allowed without approval.
- Updated responder/status semantics so approval-needed is not collapsed into blocked.
- Updated runtime smoke/policy tests for the corrected approval truth.
- Hardened Conversations drawer truth for healthy, fallback/degraded, approval-needed, and blocked/terminal states.
- Updated right drawer contract defaults to avoid fake-live request trace and approval states.
- Updated Projects and Project Detail drawer truth so idle approval and trace states are inactive/partial instead of live.
- Confirmed Memory remains honest as partial/planned rather than fake-live.
- Confirmed Governance is display-only/planned/inactive where appropriate and does not expose fake toggles.
- Confirmed /status/capabilities reports live, unavailable, and warning states honestly.
- Expanded useCapabilityManifest.ts so future pages can consume capability entries, groups, catalog state, warnings, and count.
- Applied minimal Stage 16 copy polish to TopBar, HomePage, and LeftRail.

## Retests

- Focused backend tests passed.
- Broader backend tests passed.
- Frontend build passed.
- Healthy local request retested.
- Fallback/degraded request retested.
- Approval-needed request retested.
- Drawer idle/index/detail states retested.
- Projects, Memory, Governance, Status Menu, Bottom Bar, and Quick Invoke visually reviewed.

## Remaining notes

- Pydantic V2 deprecation warnings remain but are non-blocking for Phase 1.
- Full dynamic capability-manifest-driven UI rendering is not required for Phase 1, but the hook now exposes manifest data for later use.
- Deeper Stage 16 visual polish should be deferred unless a real truth-language or usability mismatch appears.
- Do not broaden power until Part 1 closure is committed and the next implementation part is scoped.

## Final judgment

- Part 1 complete enough to move on, provided blocked-request evidence is confirmed in the saved screenshots/payloads.
