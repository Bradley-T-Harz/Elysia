# Dependency acquisition and the ordinary-user Setup path

Elysia v1.0 uses one authoritative component graph and one Setup flow. A normal
user should not create Python environments, identify package names, edit XDG
configuration, wire workers, or reconstruct a development workstation.

The intended path is:

1. launch a verified Elysia package;
2. choose Core, Workstation/Research, Creator/Perception, Developer/Codev,
   Scientific/Engineering, Complete MEGA, or a valid Custom selection;
3. review the exact dependency, hardware, download, storage, license, network,
   and privilege effects;
4. approve the specific Setup and component operations;
5. let Setup acquire, verify, install, configure, and receipt the selected
   components;
6. run the non-repairing Doctor;
7. create the first local account;
8. optionally complete autobiographical onboarding.

Profile selection alone is not download or privilege approval. Setup keeps
those approvals explicit without sending the user away to hunt for internal
package names.

## The five installation dispositions

Every entry in `config/install/dependency_catalog.yaml` and every distinct
system prerequisite named by `config/install/component_graph.yaml` has exactly
one validated disposition in
`config/install/dependency_install_dispositions.yaml`. Catalog components and
host prerequisites remain separate layers so a WebKit/GTK/driver/provider
requirement cannot disappear behind a Python-package count:

- **A — bundled:** legally and technically included in the exact Elysia
  payload.
- **B — Setup-acquired:** downloaded only from an approved source after exact
  identity, size, license, network, resource, and storage disclosure.
- **C — operating-system package:** installed only after an exact Ubuntu
  package/version preview and graphical polkit authorization. Setup itself does
  not run as root and never uses silent sudo.
- **D — detected/reused:** adopted only after a bounded local validity check.
- **E — user action:** automatic installation would require Elysia to choose a
  third-party product, accept terms, add a moving publisher channel, or perform
  a host-wide operation outside its qualified lifecycle. These are documented
  below.

Setup and its tests fail closed if a dependency is missing from the map,
appears in more than one category, lacks a component owner, or lacks the
required category-E guidance.

## What Setup handles

Depending on the selected profile, Setup handles:

- the package-bound Core and Desktop runtime;
- exact hash-locked Workstation Python adapters;
- FFmpeg, Tesseract, Git, and rootless-container prerequisites through the
  reviewed Ubuntu package lane;
- digest-pinned rootless SearXNG and Qdrant services;
- the exact Qwen embedding model after approval;
- hardware-selected CPU or qualified CUDA Creator/Scientific environments;
- individually selected, immutable-revision Creator models after license and
  resource review;
- the exact first-party Codev v1.0.0 VSIX from its canonical GitHub Release, or
  an already-downloaded byte-identical local copy;
- component receipts, cancellation, repair, governed removal, and Doctor
  verification.

Large optional profiles remain opt-in. Complete MEGA resolves the complete
release-supported v1 component family, while Core remains intentionally small
and CPU-useful.

## User action 1: Ollama local model provider

**What and why.** Ollama is an external loopback model provider used for local
conversation/model roles and the optional Qwen semantic model. Core remains
usable without it.

**Official source.** <https://docs.ollama.com/linux>

**Account.** Installing Ollama itself does not require a website signup.
Individual gated model publishers may impose separate terms or account/token
requirements; Setup discloses those per model.

**Data boundary.** Download requests reveal ordinary connection metadata to
Ollama or the chosen model publisher. Elysia runtime prompts remain local under
the loopback/no-silent-cloud policy. Do not expose the Ollama listener to a LAN
or public interface for Elysia.

**Why Setup does not silently install it.** The publisher's ordinary Linux path
is a moving installer or host-wide archive/service installation. Elysia v1 does
not execute a moving curl-to-shell script, choose a system-service policy, or
mutate `/usr` without an exact, version-bound lifecycle and privilege contract.

**Supported steps.**

1. Review the current official Linux instructions and Ollama license.
2. Install through the publisher-supported method appropriate to the machine.
3. Start the local service and confirm `ollama --version` succeeds.
4. Return to Setup and approve each exact model identity, source, license, size,
   and storage requirement.

**Doctor.** Doctor checks the local command, loopback reachability, selected
model manifests, and exact model identities without sending a prompt.

**Retry/repair.** Repair or update through Ollama's documented lifecycle,
restart the loopback service, and rerun Doctor and the exact model operation.

## User action 2: choose a VS Code-family host

**What and why.** Codev is an extension and therefore needs a compatible VS
Code or VSCodium Extension Host.

**Official VS Code source.** <https://code.visualstudio.com/docs/setup/linux>

**Account.** A local editor and local VSIX installation do not require a
Microsoft or GitHub account.

**Data boundary.** The selected editor's download/update mechanisms contact its
publisher. Codev itself has no independent network, arbitrary shell,
package-install, Git-push, or unauthorized-repository authority.

**License/privacy.** Microsoft VS Code binaries use Microsoft's product license
and privacy disclosures. VSCodium uses a different publisher and package
channel. Setup will not silently choose one, accept its terms, add a repository,
or enable telemetry for the user.

**Supported steps.**

1. Choose VS Code or VSCodium and review that publisher's license, privacy, and
   update behavior.
2. Install a supported Linux build through the publisher's instructions.
3. Confirm `code --version` or `codium --version` succeeds.
4. Return to Setup. Setup acquires and installs the exact first-party Codev
   v1.0.0 VSIX after its own source/hash/size/permission review.

**Doctor.** Doctor checks host presence and engine compatibility, Codev's exact
extension identity, the Elysia API contract, workspace trust, and repository
approval/revocation.

**Retry/repair.** Repair/update the chosen editor through its publisher, then
rerun the Codev component operation and Doctor.

## Optional CUDA acceleration

The CPU variant is always the supported fallback. Setup does not silently
install a host NVIDIA driver because that is a kernel/host-wide,
hardware-specific, reboot-sensitive operation.

Use Ubuntu's official instructions:
<https://documentation.ubuntu.com/server/how-to/graphics/install-nvidia-drivers/>

After the host driver is installed and any required reboot is complete, confirm
`nvidia-smi` works and rerun Setup/Doctor. Elysia selects CUDA only after the
driver, GPU, VRAM, real workload, pressure, cancellation, and OOM-recovery
checks pass. A failed CUDA check never forces or fakes a GPU profile.

## Source-contributor toolchains are not runtime prerequisites

Pytest, HTTPX, Node.js/npm, and Rust/Cargo are category-E source-development
tools. They are not required to run packaged Elysia or install the qualified
Codev VSIX. Contributors should use `CONTRIBUTING.md`, the declared versions,
Python lock, `package-lock.json`, and `Cargo.lock` in isolated development
environments. Setup deliberately does not bloat an ordinary Developer/Codev
profile with compilers and test runners.

## Doctor states and recovery

Doctor classifies each selected component as `ready`, `degraded`, `blocked`,
`missing`, or `not selected`. It does not download or repair while checking.
Use the Setup component flow for exact repair or governed removal. Repair
reacquires package-owned bytes and never resets account, Memory, projects,
conversations, settings, or user-created artifacts.

The machine-readable manifests—not this prose—are authoritative for exact
versions, hashes, URLs, sizes, licenses, and lifecycle behavior. This document
explains the user path and the narrow reasons any manual action remains.
