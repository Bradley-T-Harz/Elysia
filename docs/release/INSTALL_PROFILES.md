# Elysia v1.0 Install Profiles

Profiles are declarative capability and dependency contracts for one canonical Elysia codebase. Selecting a profile must never silently grant authority, export private data, or weaken Core governance.

The authoritative profile/component source is
`config/install/component_graph.yaml`. Exact dependency detail and installation
dispositions live in `config/install/dependency_catalog.yaml`,
`config/install/dependency_install_dispositions.yaml`, and the acquisition
manifests. See
[`DEPENDENCY_ACQUISITION_AND_MANUAL_ACTIONS.md`](DEPENDENCY_ACQUISITION_AND_MANUAL_ACTIONS.md)
for the ordinary-user path and every unavoidable manual action.

Profile selection itself grants no download or privilege authority. Elysia
Setup turns the selected graph into reviewed, exact component operations;
acquires/installs what may legally and safely be automated; and finishes with a
non-repairing Doctor gate.

Core must not require Creator, generative-media, large-model, scientific, or Developer tooling. The profile-specific files under `requirements/` are the v1 packaging contracts. The root `requirements.txt` remains a legacy development aggregate during finalization and must not be treated as the public Core install manifest; a clean-install proof must reconcile it before release.

## Profile summary

| Profile | Default | Risk | Runtime network | Large downloads | Private data leaves machine |
|---|---|---|---|---|---|
| Elysia Core | Enabled | Low/bounded | Disabled by default | No | No by default |
| Recommended Workstation | Opt-in | Moderate local tools | Disabled by default | Normally no | No |
| Creator / AI Media | Opt-in | Elevated resources/models | Disabled after explicitly approved acquisition | May occur with warning | No by default |
| Developer / Codev | Opt-in | Elevated repo/mutation capability | Disabled by default | Node/VSIX downloads may occur during explicit install | No by default |

## 1. Elysia Core

### Purpose

Provide a useful local Elysia installation without giant model, media, scientific, container, or developer stacks.

### Included capabilities

- Desktop chamber and local API/runtime;
- account gate, conversations, projects, files, artifacts, requests, health, capabilities, Settings, and read-only governance;
- bounded text/code file handling;
- type, dependency, and capability truth for document/data/visual formats;
- safe adapters included in the Core runtime;
- archive inspection and supported selected extraction;
- DatabaseForge schema-only, BinaryForge static, and EngineeringForge static boundaries;
- local model-provider integration when a compatible provider/model is already available;
- sanitized local audit/request receipts.

### Required dependencies

- the Core Python runtime group;
- packaged Desktop/native runtime artifacts;
- supported Linux runtime libraries determined by packaging tests.

### Optional dependencies

- a local Ollama-compatible provider and a hardware-appropriate local model;
- individual format adapters reported by capability truth.

### Intentionally excluded

- GPU/generative media frameworks and weights;
- SpeechForge model vault assets;
- Codev/VS Code;
- rootless container or namespace tooling;
- cloud accounts and external services;
- arbitrary shell, physical actuation, and add-on code execution.

### Doctor checks

- component/contract versions;
- local API lifecycle, authentication, bind/IPC, and Desktop reachability;
- writable XDG config/data/state/runtime locations;
- Core Python imports;
- optional provider reachability and exact model availability;
- no tracked/private runtime path requirement.

## 2. Recommended Workstation

### Purpose

Add common local document, data, image, OCR, and media-metadata support without installing generative media models.

### Included capabilities

- all Core capabilities;
- common document extraction and stable derivative export adapters;
- table/science/data adapters described by the dependency catalog;
- FFmpeg/FFprobe media metadata and bounded thumbnail support;
- Tesseract-backed OCR when the local engine is present;
- optional local non-cloning reading voice only when its separate runtime/model checks pass.

### Required dependencies

- Core;
- Workstation Python adapter group;
- FFmpeg/FFprobe for the media-metadata feature set;
- Tesseract only for OCR.

### Optional dependencies

- MediaInfo or espeak-ng only after real adapters and tests exist;
- additional geospatial/science libraries;
- SpeechForge assets, which remain a separate Creator capability group.

### Intentionally excluded

- ImageForge/VideoForge frameworks and models;
- voice cloning;
- Codev;
- add-on code execution;
- live engineering workers or hardware access.

### Doctor checks

- Core checks;
- import/command availability per selected adapter;
- tool versions and fixed-argument safety support;
- missing adapters reported as optional or degraded, never as false success.

## 3. Creator / AI Media

### Purpose

Add explicitly chosen local speech, image, video, and future engineering-lab capability for machines that meet resource, provenance, and isolation requirements.

### Included capabilities

- all Recommended Workstation capabilities;
- SpeechForge planning and local non-cloning STT/TTS when assets are verified;
- ImageForge as a production target only after all production gates pass;
- VideoForge as an explicitly labeled Lab capability;
- future heavy EngineeringForge workers behind local sandbox/namespace proof;
- model/job provenance, cancellation, resource receipts, and doctor truth.

### Required dependencies

- profile-selected Creator Python/runtime groups;
- explicitly selected local model assets;
- verified model/tool license and provenance metadata;
- adequate disk, RAM, and where required GPU/CUDA resources.

### Optional dependencies

- individual image/video/speech models;
- local sandbox mechanisms supported by the host;
- future Reference Voice Lab components with consent/provenance controls.

### Intentionally excluded

- silent downloads;
- unverified or license-conflicted models promoted as production;
- cloud inference by default;
- unconsented voice cloning or impersonation;
- hardware actuation;
- unlimited jobs or missing cancellation/resource ceilings.

### Doctor checks

- model and tool path resolution through local overrides;
- file existence, checksum/provenance metadata, and safe loader posture;
- disk/RAM/VRAM/CUDA requirements;
- cancellation and resource-limit support;
- local sandbox/namespace proof before heavy engineering workers;
- network disabled after any separately approved acquisition.

Large downloads may occur only after the user selects exact assets and receives size, source, license/provenance, and storage warnings. Private data remains local unless a separately named external profile and exact operation approval exist.

## 4. Developer / Codev

### Purpose

Provide the official Codev extension and governed developer workflows without turning Elysia into an unrestricted shell.

### Included capabilities

- Codev extension;
- approved-repository metadata and selected-file context;
- patch proposal, diff review, exact-approved mutation, and receipts;
- allowlisted checks/builds with exact arguments and approval;
- worker/job traceability;
- future Pursue Goal bounded task loops as Developer Lab, with budgets, checkpoints, stop/recovery, review, and no hidden push.

### Required dependencies

- Core;
- a compatible user-chosen VS Code/VSCodium host;
- the exact Codev v1.0.0 VSIX, automatically acquired by Setup from its
  canonical release URL after approval or verified from a byte-identical local
  copy;
- Git for specifically supported read-only checks;
- no source-development toolchain is required for the packaged extension path;
  contributor-only pytest/HTTPX/Node/Rust tools follow the separate source
  instructions.

### Optional dependencies

- profile-approved language toolchains;
- a proven local sandbox mechanism;
- future task-loop worker dependencies.

### Intentionally excluded

- arbitrary shell and package scripts by default;
- hidden Git mutation or push;
- broad home/repository scanning;
- private-memory access;
- cloud code upload;
- unbounded autonomy.

### Doctor checks

- Elysia API/Codev contract compatibility;
- VS Code engine compatibility;
- workspace trust and approved-repo policy;
- exact command catalog;
- local sandbox prerequisites for Lab workers;
- trace receipt availability and stop/recovery support.

## Composition law

- Core is the base profile.
- Workstation extends Core.
- Creator extends Workstation.
- Developer extends Core and may coexist with Workstation or Creator.
- Profiles add dependencies and capability eligibility; they do not bypass per-operation approval or governance.
- Removing a profile disables its capability eligibility without deleting user-created data or model assets automatically.

## Runtime truth contract

The Pass 5 resolver uses only bounded local checks:

- Python dependencies use module discovery and installed-distribution metadata without importing the package;
- command dependencies use executable lookup without invoking the command;
- model, worker, vault, packaged-application, namespace, resource, and isolation checks remain `unknown`, `profile_gated`, or `lab_gated` until a later doctor contract can prove them safely;
- no provider network request, model load, worker execution, download, installation, or service mutation occurs;
- dependency presence is not capability activation and profile selection is not operation approval.

Dependency status vocabulary is:

`present`, `missing`, `optional_missing`, `blocked`, `degraded`, `unknown`, `profile_gated`, `lab_gated`, and `not_applicable`.

The response reports versions only when installed Python distribution metadata can be read safely. It reports configured local override labels and counts, never raw paths, provider URLs, model tags, executable paths, vault values, credentials, or private contents.

## Local override contract

- `config/install/local_profiles.example.yaml` is the tracked source/development template; `local_profiles.yaml` is gitignored.
- `config/models/local_overrides.example.yaml` is the tracked provider/model/worker template; `local_overrides.yaml` is gitignored.
- Invalid profile selection falls back to Core and is reported as invalid.
- Invalid provider/model/worker metadata is ignored and reported as fail-closed.
- Authority-bearing policy values, remote provider URLs, credential-bearing URLs, and unknown keys are rejected.
- A valid override may identify an active profile, additional profile composition, loopback provider metadata, role IDs, model-vault metadata, or optional worker metadata. It still grants no network, install, download, model-selection, worker-start, sandbox, hardware, shell, or approval authority.
- Normal UI surfaces show safe labels, states, and counts only. Sanitized diagnostics use the same allowlisted posture.
