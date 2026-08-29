# Developer Add-on Submission Rules — Draft

Status: product/legal-language draft for Pass 7. Attorney review is required before
public publication. These rules do not create an upload or publication endpoint.

## Developer commitments

Developers must not submit malware, credential harvesters, spyware, hidden telemetry,
exploitation payloads, unlawful content, impersonation tools, undisclosed network or
file access, undeclared executables, or material they do not have the right to
distribute.

Every submission must accurately declare:

- publisher identity, add-on ID, version, and compatible Elysia versions;
- entrypoints, dependencies, license, provenance, and package checksums;
- filesystem, network, memory, model/provider, tool, shell/package, and hardware
  permissions requested;
- code execution and local sandbox requirements;
- external services, accounts, telemetry, and data leaving the machine;
- known risks, bundled binaries/scripts, and generated or third-party material.

The submitted package or repository must not contain `.env` files, credentials,
tokens, keys, browser profiles, private logs, local memory/vault data, machine-local
absolute paths, hidden secrets, or private material unrelated to the add-on.

## Supported preparation paths

Developers may prepare work with Elysia Developer Forge, Codev / VS Code, a local IDE,
Git, Codex or another coding assistant, an imported folder/repository, a zipped source
bundle, or a packaged `.elysia-addon`.

Elysia may validate and package the resulting local material. It does not silently
connect to external development services, clone a Git URL, add a remote, push,
publish, upload, or submit. External tools have their own terms, privacy policies,
accounts, and data-flow implications.

## Submission privacy and consent

Before an upload, the developer must receive and accept a clear notice that the
selected repository, folder, bundle, or package will leave the local computer and be
transferred to Elysia Ecobotics / EcoSyneva Commons review infrastructure. The UI
must show the exact selected material and provide a cancel path.

A Git repository URL is review metadata until an exact, separately governed fetch or
clone action is approved. Entering a URL never authorizes hidden network access.

## Static intake and review

Every input is untrusted. Ordinary intake performs bounded static checks for count,
size, extension/MIME, path traversal, symlinks, hidden files, `.env`/credential
material, secrets, private paths, suspicious binaries, executable/scripts, archive
depth, dependencies, license/provenance, manifest, permissions, compatibility,
network declarations, checksums, and an SBOM where feasible. Ordinary upload
validation must not execute submitted code.

Public listing requires an admin review bound to the exact package/repository hash,
version, publisher, permissions, dependency inventory, static results, known risks,
reviewer, timestamp, decision, and any separately performed local sandbox result.

Admin-reviewed means reviewed under the current process, not guaranteed safe. A new
version or changed hash requires a new review.

## Publication and lifecycle law

Marketplace submission creates `pending_review`, never a public listing. Approval
does not install anything on a user's machine. Local installation begins disabled;
enablement requires separate exact permission review and approval. Disable, revoke,
and removal behavior must remain available and auditable.

Elysia Ecobotics / EcoSyneva Commons may reject, remove, revoke, or disable listings
that violate security, privacy, legal, provenance, compatibility, or Marketplace
requirements. Final public terms and publisher naming require legal/brand approval.
