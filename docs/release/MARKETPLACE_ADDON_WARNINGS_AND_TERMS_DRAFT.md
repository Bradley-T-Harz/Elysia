# Marketplace and Add-on Warning Language — Draft

Status: product/legal-language draft for Pass 7. Attorney review is required before
public publication. This document does not itself enable upload, installation,
Marketplace publication, or add-on execution.

## In-app listing warning

Third-party add-ons may run code locally on your computer if a later, governed
execution mode is explicitly enabled. Review the publisher, exact version,
compatibility, requested permissions, known risks, and review status before staging
or enabling an add-on.

Admin review reduces risk but does not guarantee safety. Install only from publishers
you trust, and do not grant permissions you do not understand.

## Install-plan warning

Installation validates and stages this add-on in a disabled state. Installed does
not mean enabled. No execution or permission grant is implied by staging files.

Before approval, show:

- publisher, version, exact package hash, compatibility, and provenance;
- official/community/experimental/Lab classification and review status;
- requested versus effective permissions;
- network, filesystem, memory, model/provider, shell/package, and hardware access;
- execution and local sandbox requirements;
- external services, dependencies, known risks, and retained-file behavior.

## Enable-plan warning

Enablement is a separate action. Enabled does not mean unrestricted. Only the exact
effective permissions shown in the approved plan may be used. The add-on can be
disabled or revoked; the UI must explain whether files or local state remain.

If local sandbox, doctor, approval, compatibility, or permission proof is missing,
execution remains blocked. Elysia must never fall back to unsandboxed host execution.

## Upload privacy notice

Use this notice immediately before any website transfer:

> The files you select will leave your computer and be transferred to Elysia
> Ecobotics / EcoSyneva Commons review infrastructure for validation and admin
> review. Review the selection and remove secrets, credentials, private data, and
> material you do not have the right to distribute before continuing.

The upload page must not describe this transfer as local-only. Local package creation
and validation remain available as the no-submission alternative.

## Marketplace terms substance

Users should be told:

- third-party add-ons can be unsafe and may request powerful local permissions;
- review and signatures reduce risk but are not guarantees;
- backups and legal compliance remain the user's responsibility;
- requested permissions must be reviewed before install and enablement;
- Elysia may reject, remove, revoke, or disable listings that violate security,
  privacy, legal, provenance, or Marketplace rules;
- submitted, approved, installed, enabled, disabled, revoked, and removed are
  separate states with separate consequences;
- any external provider or development tool has its own terms, privacy policy, and
  data flow; Elysia does not silently connect to it.

## Required UI truth

No Install, Enable, Submit, Publish, Remove, or Run control may look active unless its
real backend contract exists. Otherwise it is read-only, disabled with a reason,
profile-gated, Lab-gated, admin-only, or hidden. Codev is the official
qualified stable v1.0 local Developer-profile add-on. Public distribution is
reported by the canonical Elysia Ecobotics Marketplace, while local install
authority remains explicit and governed.
