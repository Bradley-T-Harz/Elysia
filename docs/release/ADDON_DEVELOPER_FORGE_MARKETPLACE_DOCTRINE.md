# Add-on, Developer Forge, and Marketplace Doctrine

Status: qualified stable v1.0 contract; Pass 7 foundation implemented 2026-08-15.

This document is the canonical release contract for Pass 7. It complements the
existing package, permission, installer, revocation, sandbox, API, and UI contracts
under `docs/addons/`, `docs/api/`, `docs/security/`, and `config/addons/`.

## 1. Binding principle

> Add-ons do not enter Elysia's bloodstream. They speak to Elysia through governed ports.

Elysia should accept broad, well-formed local capability without allowing arbitrary
third-party code to become part of Core. Every binding site has a versioned schema,
exact permissions, an approval boundary, a stop/revoke path, and a sanitized receipt.

The architecture separates four domains:

- **Elysia Core:** private, local-first, governed, and unaware of add-on internals.
- **Add-on runtime boundary:** exposes only approved capabilities and can be stopped,
  disabled, or revoked without modifying Core.
- **Developer Forge / Codev:** creates and validates local files, repositories, and
  packages; it does not silently upload, push, publish, or acquire credentials.
- **Marketplace:** accepts untrusted submissions for review and distributes only
  exact reviewed package versions. It is not an uncontrolled plugin catalog.

“Blocked by default” does not mean “never build.” Powerful behavior advances only
when its binding contract, profile, local isolation, approval, receipt, and recovery
path are real.

## 2. Capability and state law

These are separate facts and must never be collapsed:

```text
Submitted does not mean approved.
Approved does not mean installed.
Installed does not mean enabled.
Enabled does not mean unrestricted.
Permission granted does not mean broad authority.
Admin-reviewed does not mean guaranteed safe.
```

The target lifecycle vocabulary is:

| State | Meaning | Authority |
|---|---|---|
| `draft` | Local project or listing metadata is being prepared | None |
| `packaged` | A local immutable package was created and hashed | None |
| `submitted` | Selected material left the local machine for review | None |
| `pending_review` | Marketplace review is in progress | None |
| `approved` | One exact version/hash was reviewed and accepted | No local install or execution |
| `rejected` | Review declined the exact submission | None |
| `installed_disabled` | Validated files are staged locally | No execution |
| `enabled_limited` | An approved effective permission set is active | Only exact granted bridge operations |
| `disabled` | Local files/registry may remain, but runtime authority is off | None |
| `revoked` | Trust/permission is withdrawn and runtime must stop | None |
| `removed` | Registry removal is recorded; retained-file behavior is explicit | None |

Every transition must name the add-on ID, version, package hash, current state,
proposed state, requested permissions, effective grants, approval requirement,
actor, request/operation ID, and sanitized result. Stale state, changed hashes,
tampering, expired/reused approval, and permission widening fail closed.

## 3. Creation paths

Elysia must eventually support add-ons created through:

1. Elysia Developer Forge local projects.
2. Codev / VS Code local workspaces.
3. Any user-selected local IDE or manual repository.
4. Codex or another external coding assistant.
5. An imported local folder or repository.
6. A zipped source bundle.
7. A packaged `.elysia-addon`.
8. A Git repository URL supplied as review metadata; fetch/clone is a separately
   governed external action and is never implied by entering a URL.

Elysia validates and packages outputs from external tools but does not silently
connect to Codex, OpenAI, GitHub, VS Code services, or any other provider. Users who
choose external tools are subject to those tools' own accounts, terms, privacy
policies, and data flows.

## 4. Local FileForge and Repository Forge target

File and repository creation remains a broad governed capability, not a forbidden
one. The future local flow is:

```text
request
→ classify output and risk
→ choose reviewed generator/adapter
→ preview file tree and consequences
→ bind an approved project/output root
→ require overwrite approval where relevant
→ write and validate
→ checksum/provenance receipt
```

Text, code, structured data, documents, spreadsheets, SVG, PDFs, archives, project
configuration, tests, manifests, and other well-defined artifacts may be produced.
Executables, installers, scripts, service files, extensions, code-bearing archives,
controller configuration, G-code, and binary patches are higher-risk outputs. They
may be created under a project-scoped path, but creation never grants execution,
installation, overwrite, network, hardware, publishing, or system authority.

Repository creation may generate a file tree, README, license, tests, and configs.
Local Git initialization requires an exact approved action. No remote, credential,
push, package publication, Marketplace submission, telemetry, or hidden upload is
added by default. Packaging/publication requires a private-path and secret scan.

## 5. `.elysia-addon` package contract

The repository's existing canonical manifest is `manifest.json`; Pass 7 must extend
that convention rather than introducing a second `manifest.yaml` format. A package
is a ZIP-compatible archive with the `.elysia-addon` suffix and should contain:

- `manifest.json`;
- declared permissions and compatibility bounds;
- `README.md`, `LICENSE`, and preferably `CHANGELOG.md`;
- a dependency inventory or SBOM where feasible;
- checksums for all declared payloads;
- source or reviewed build artifacts;
- entrypoint descriptors and bridge protocol metadata;
- a local sandbox profile when execution is requested;
- bounded UI contribution metadata, if any;
- self-check or test metadata where available.

The manifest declares add-on/publisher identity, version, compatible Elysia
versions, required profiles, entrypoints, requested permissions, network/filesystem/
memory/model/tool policy, execution and sandbox requirements, external service use,
license/provenance, hashes, and a signing-ready identity field. A missing signature
must be reported honestly until signing infrastructure exists; it is never faked.

The package validator rejects, at minimum, path traversal or absolute paths, symlinks,
special files, archive bombs or excessive nesting, hidden credential material,
`.env` files, private absolute-path references, undeclared binaries/scripts,
undeclared permissions/network behavior, missing or duplicate manifests, invalid
compatibility, missing entrypoints, checksum mismatches, and size/count violations.

Ordinary package inspection is static and never imports or executes payload code.

## 6. Permission and bridge law

Requested permissions, approved permissions, and effective runtime permissions are
distinct. The effective set is the intersection of declared, profile-allowed,
policy-allowed, user-approved, doctor-proven, and non-revoked grants. It can never
be widened by UI state, add-on output, package metadata after approval, or a bridge
request.

No add-on receives these by default:

- private memory, journals, identity stores, or vault material;
- credentials, tokens, browser profiles, model secrets, or raw logs;
- arbitrary filesystem access or unapproved mounts;
- network, external API, shell, package-manager, worker, or hardware access;
- host Docker socket or Elysia Core internals.

Future language-neutral bridge options include typed JSON-RPC over stdio,
authenticated loopback HTTP, Unix sockets, file-drop/job-result exchange, Tauri UI
contribution metadata, and a Codev/VS Code client protocol. Each bridge must define
request/response/error schemas, health and shutdown behavior, capability IDs,
timeouts, size/resource limits, authentication, audit metadata, and cancellation.
A bridge endpoint is not general shell authority.

Elysia Core must not import arbitrary add-on modules directly.

## 7. Local sandbox and execution gate

Current sandbox behavior remains validation-only. Add-on execution stays disabled
until all of these exist and pass together:

- a local user-machine isolation mechanism proven by doctor;
- explicit allowlisted read/write mounts and no private-memory mounts;
- CPU, memory, process, file/output, and time limits;
- network denied unless the exact profile, permission, and operation allow it;
- no host Docker socket and no physical hardware by default;
- exact approved effective permissions;
- authenticated bridge, cancellation, kill, cleanup, and revocation;
- sanitized stdout/stderr/logs and request/operation receipts;
- negative tests for bypass, tamper, replay, stale state, and unavailable isolation.

No cloud or paid sandbox is required. If local isolation proof is unavailable, the
execution state is `blocked`, `profile_gated`, or `lab_gated`, not silently degraded
to host execution. Elysia must never fall back to direct host execution.

## 8. Developer Forge privacy and package preparation

Developer Forge is local-private by default. It may eventually create a new local
add-on repository, import an approved folder/repository, validate the manifest,
run static checks, build a `.elysia-addon`, generate install metadata, and prepare a
submission preview. Submission occurs only after an explicit user action.

Before packaging, the bounded pipeline should perform:

- package content allowlist and file count/size checks;
- secret, `.env`/credential, and private-path scanning;
- path, symlink, MIME/extension, executable, binary, and nested-archive review;
- manifest, compatibility, permission, entrypoint, and checksum validation;
- dependency inventory/SBOM generation where feasible;
- license/provenance review and large-file warnings;
- declared network/shell/package/hardware behavior review;
- an immutable package hash and sanitized local receipt.

It must not include private project metadata, local logs, private memory, model
tokens, credentials, machine paths, or hidden telemetry. It must not add a remote,
push, publish, upload, or submit automatically.

## 9. Website submission and privacy boundary

Future website targets `/marketplace/submit` and `/developer-forge` may accept an
`.elysia-addon`, zipped source, browser-selected folder/repository, or Git URL review
metadata. The website is a separate external boundary.

Immediately before upload, the UI must clearly state:

> The files you select will leave your computer and be transferred to Elysia
> Ecobotics / EcoSyneva Commons review infrastructure for validation and admin
> review. Review the selection and remove secrets or private material before
> continuing.

Website upload must never be described as local-only. The local packaging path is
the alternative for users who do not wish to submit.

Every submission is untrusted. Ordinary intake performs bounded static validation:
file count and total-size limits; extension/MIME inspection; traversal, symlink,
hidden file, `.env`, credential, secret, private-path, executable, suspicious binary,
and archive-depth checks; dependency inventory; license/provenance review; manifest,
permission, compatibility, entrypoint, and network declaration checks; checksum and
SBOM generation where feasible. It does not execute uploaded code.

## 10. Admin review and listing truth

Marketplace publication requires an admin decision. A review record binds:

- exact package/repository hash and submitted version;
- publisher identity and claimed provenance;
- requested permissions and dependency inventory;
- static scan results;
- test environment and local sandbox result, if separately performed;
- known risks and compatibility bounds;
- reviewer/admin identity, timestamp, and decision.

Public listings disclose official/community/experimental status, publisher, version,
compatibility, permissions, network/filesystem/memory/model/shell/package/hardware
access, execution and sandbox requirements, dependencies, known risks, review status,
review date, and exact reviewed hash where practical.

Admin approval means “reviewed under the current process,” not “guaranteed safe.”
Users must see warnings and the effective permission set before installation and
again before enablement. Disable, revoke, and removal consequences must be explicit.

## 11. Codev listing contract

Codev is the first official add-on. Its Developer-profile installation path is
real and verified. It may display a working install action only when the exact
reviewed package and governed local installation contract are available; public
distribution never grants silent local installation authority.

The future listing identifies the final approved EcoSyneva Commons LLC / Elysia
Ecobotics publisher name, Developer profile requirement, governed local coding
purpose, approved repository access, patch proposals, exact approved mutation,
bounded command/test behavior, request/operation traceability, and the absence of
hidden shell, silent push, or silent publish authority.

Pass 8 satisfies the local installation condition with a reviewed-VSIX,
dry-run-first user-local installer, XDG receipt, Developer-profile doctor truth,
authenticated bridge, exact repository approval, and version/contract checks.
Codev is therefore the official qualified stable v1.0 local add-on. Public
distribution is supported through the Elysia Ecobotics Marketplace, while no
in-app installation control or add-on publication authority is granted by Elysia.

## 12. Marketplace cleanup boundary

Cleaning existing Elysia Ecobotics Online Marketplace entries is a separate website
task. Nothing in Pass 7 authorizes blind deletion.

- Static source entries are changed only after inspecting and testing the website.
- Database/Supabase-backed entries require an export or inventory of exact row IDs,
  a dry-run hide/delete plan, and release-owner/admin approval before mutation.
- Unrelated Marketplace records and tables remain untouched.
- Core dependencies, legally awkward material, and nonfunctional pseudo-add-ons may
  be hidden, removed, or converted to internal/deprecated records only through that
  approved cleanup pass.

An honest empty state or official Codev draft is preferable to fake installability.

## 13. Required product and legal-language surfaces

Pass 7 must carry the warning contract into the in-app Marketplace/Add-ons listing,
install plan, enable plan, and permission review. The online Marketplace/Legal terms
and Developer submission surfaces must use equivalent language before publication.

The canonical draft wording is maintained in:

- `docs/release/MARKETPLACE_ADDON_WARNINGS_AND_TERMS_DRAFT.md`;
- `docs/release/DEVELOPER_ADDON_SUBMISSION_RULES_DRAFT.md`.

These are engineering/product drafts and require attorney review before public use.

## 14. Pass 7 completion boundary

Pass 7 completes the foundation when static validation, manifest/permission/
compatibility/provenance truth, staged-disabled installation, exact state changes,
revocation, receipts, review/submission contracts, upload warnings, and UI truth are
implemented and tested. It does not need to enable arbitrary code execution.

That foundation is now implemented. Local package staging and registry changes use
exact plan/approve/apply contracts and XDG user data; Developer Forge and Marketplace
contracts remain non-writing/non-uploading previews; Codev is the official
qualified stable v1.0 local add-on with public distribution sourced from the canonical external Marketplace; and the separate website cleanup contract authorizes no
mutation. `enabled_limited` carries no bridge or runtime authority in this pass.

Execution may advance only as a separate governed promotion after the entire local
sandbox and bridge gate is proven. Powerful add-ons remain on the roadmap.
