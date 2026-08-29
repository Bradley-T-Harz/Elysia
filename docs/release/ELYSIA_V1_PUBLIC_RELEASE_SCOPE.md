# Elysia v1.0 Public Release Scope

Status: qualified stable v1.0 release contract
Target version: `1.0.0`
Current channel: `stable`
Qualification state: `Pass 10D VI qualified`
Publication state: authoritative only at the canonical GitHub Release and Elysia Archive surfaces; mutable external state is not embedded in release bytes.

## Product definition

Elysia v1.0 is a coherent, installable, local-first AI companion platform with governed capability, inspectable boundaries, profile-based optional power, and an official Developer/Codev path.

The release is:

- local-first;
- privacy-first;
- governed;
- installable;
- auditable;
- developer-friendly;
- profile-aware;
- add-on-capable;
- honest about optional external and cloud boundaries.

Elysia is one canonical codebase. Public and private installations use profiles, local overrides, permissions, and excluded runtime state rather than separate source forks.

## What v1.0 is not

Elysia v1.0 is not:

- a ChatGPT clone;
- a Codex clone;
- a cloud-first product;
- a single giant installation that requires every scientific, media, generative, and developer dependency;
- a fake coming-soon shell;
- a reckless autonomous agent;
- a promise that no data can ever leave the machine under any optional profile;
- a production-ready uncontrolled Marketplace;
- a physical-control system enabled by a normal Core install;
- the operator-private or EcoSyneva-private runtime state in a public repository or package.

In plain terms: Elysia is not a ChatGPT clone and not a Codex clone. Comparable workflow quality means practical capability and trustworthiness, not copied branding, interaction style, centralized assumptions, or product claims.

## Canonical v1 shape

```text
Elysia Core
  + optional Recommended Workstation profile
  + optional Creator / AI Media profile
  + optional Developer / Codev profile
  + optional governed add-ons
  + explicit future external/hardware profiles
```

Profiles compose capabilities and dependencies. They do not weaken baseline governance, grant silent network access, or authorize private-context export.

## Core release surface

Core v1 is expected to provide:

- the Elysia Desktop chamber;
- a lifecycle-managed local API/runtime;
- local account and profile handling;
- conversations and projects;
- local files, artifacts, requests, and trace truth;
- bounded text/code/file stewardship;
- basic document/data/visual type and dependency truth;
- safe local metadata and preview paths whose dependencies are present;
- archive inspection and selected safe extraction;
- DatabaseForge schema-only and BinaryForge static inspection boundaries;
- EngineeringForge static reports and supported non-actuating projections;
- read-only governance, capability, health, and profile truth;
- explicit degraded behavior when an optional provider or adapter is missing.

Core must not require GPU frameworks, generative image/video models, speech model vaults, Codev, container engines, cloud accounts, or giant model downloads.

## Optional power

Optional profiles may add local system tools, Python packages, models, Codev, local workers, or explicitly selected external boundaries. Before an optional profile acts, Elysia must report:

- what will be installed or used;
- whether an external download is required;
- approximate resource implications where known;
- model/tool provenance and licensing status;
- whether runtime network access is allowed;
- whether any selected data may leave the machine;
- which operations require approval;
- how the profile can be disabled or removed.

No profile may silently enable cloud fallback, arbitrary host shell, physical actuation, unconsented voice cloning, raw private diagnostics, or outbound posting.

## Add-ons

Elysia is add-on-capable, but add-ons remain governed, permissioned, auditable, revocable, profile-aware, and sandbox-aware. Core v1 may support safe package inspection, permission review, validation, and install-disabled behavior. Add-on code execution requires a separately proven local sandbox and effective permission lifecycle.

## External and cloud boundaries

Core requires no cloud account. Optional external services may exist only when explicitly enabled by the user. Their UI and receipts must identify the provider, destination, data scope, approval state, and whether private context was excluded.

“Local-first” does not justify a false “nothing can ever leave the machine” promise. It means external movement is absent by default and explicit, narrow, reviewable, revocable, and auditable when enabled.

## Version doctrine

- Product version: `1.0.0`.
- Current release channel: `stable`.
- Qualification state: exact-byte Pass 10D VI qualified stable release.
- Elysia API, Desktop, Tauri, Setup/Core installer, profiles, packages, Codev compatibility metadata, and applicable lockfiles are aligned to `1.0.0`. Independent protocol, schema, skill, dependency, and third-party versions retain their own versioning.
- API contract versions remain independent from product versions and change only when their contract changes.
- Historical candidate/build provenance remains in signed release evidence; current external availability is never inferred from immutable source bytes.

## Publication condition

Elysia `1.0.0` may be described as the qualified stable release. A repository, tag, or package is publicly available only when the canonical GitHub Release or Elysia Archive surface actually exposes the exact signed bytes.
