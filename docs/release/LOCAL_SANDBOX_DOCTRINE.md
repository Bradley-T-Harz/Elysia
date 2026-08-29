# Elysia Local Sandbox Doctrine

Elysia sandboxes are local safety boundaries. They do not require a paid server, cloud execution account, or centralized Elysia service.

## Non-negotiable defaults

- No cloud sandbox is required.
- No host Docker socket is mounted or used by default.
- No private memory, journal, identity, credential, browser-profile, or vault mount is allowed by default.
- No network is available unless the selected profile, policy, and exact operation approval permit it.
- No physical hardware access is available unless a separately installed hardware profile and exact device approval exist.
- No sandbox unavailability may be presented as successful isolation.
- Every attempted action receives a sanitized operation/request receipt, including blocked attempts.

## Acceptable future local mechanisms

Depending on platform availability and threat model, a worker may use:

- rootless Podman;
- rootless Docker without the host daemon socket;
- bubblewrap/bwrap-style namespaces;
- firejail-like confinement;
- language-specific subprocess cages;
- disposable working directories with capability-empty subprocesses;
- a stronger platform-native sandbox selected by a future port.

Pass 1 installs and configures none of these. A worker must declare which mechanism it requires, and doctor must prove that mechanism before enablement.

## Filesystem law

1. Mounts are deny-by-default.
2. Only explicit allowlisted mounts are eligible; every mount identifies source, destination, read/write mode, purpose, and lifetime.
3. Private roots are never inherited because a parent directory was mounted.
4. Work occurs in a new disposable directory unless the contract requires an exact approved target.
5. Source mutation requires a separate operation contract, source hash, exact approval, backup/rollback truth, and receipt.
6. Path traversal, symlink escape, device nodes, sockets, and unexpected executable material fail closed.

## Process and resource law

- Fixed or validated direct argument vectors; no implicit shell.
- Closed stdin unless the contract defines bounded input.
- Bounded stdout/stderr with sanitization.
- CPU, memory, process, file-size, output-size, and wall-time limits.
- Cancellation and cleanup appropriate to the worker.
- No inherited credential or proxy environment.
- No package installation or service mutation from inside the sandbox.

## Network law

Network is disabled by default. If an optional profile supports network:

1. the destination class and data class are declared;
2. private context is excluded unless separately reviewed and explicitly selected;
3. the user sees a preview of the outbound scope;
4. an exact approval binds destination and payload summary;
5. the receipt states whether network was used;
6. network access ends with the operation.

## Hardware law

Static parsing, explanation, simulation planning, visualization, and non-actuating validation do not imply hardware authority. Actual serial, USB, controller, ROS execution, G-code send, flight control, machine motion, or printing requires a future hardware-specific profile with:

- exact device identity;
- least-privilege device access;
- simulation or dry-run proof;
- safety checklist and operating envelope;
- final per-operation approval;
- emergency stop/revoke behavior;
- complete receipt.

## Logging and receipts

Receipts may contain stable IDs, relative labels, hashes, resource summaries, status/reason codes, approval IDs, and bounded sanitized output. They must not contain raw private paths, credentials, full prompts/transcripts, private file contents, or unbounded tool output.

## Doctor prerequisite

Before a sandbox-backed capability can be enabled, doctor must verify:

- mechanism availability and version;
- unprivileged/rootless posture;
- namespace or isolation features required by the worker;
- mount and network policy support;
- resource-limit support;
- worker executable/model provenance;
- cleanup/cancellation support;
- a safe self-test that does not access private state.

If any required proof is missing, the capability remains disabled with an actionable explanation.
