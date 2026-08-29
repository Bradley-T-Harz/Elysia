# Elysia Public Package Manifest

The machine-readable contract is [`packaging/public_manifest.yaml`](../../packaging/public_manifest.yaml). This document explains its law.

## Release surfaces

1. **Reviewed source snapshot:** code, public contracts, operator-neutral runtime prompts, reviewed canon, templates, selected tests, and build inputs exported through the manifest allowlist. Historical reports and architecture snapshots remain preserved locally but are excluded from the first public snapshot.
2. **Installed Core payload:** the smallest runnable local API/runtime payload plus license, requirements, and package metadata. It excludes development history, tests, Creator/Developer assets, optional heavy worker registries, and all user state.
3. **User-local state:** XDG config/data/cache/state/runtime roots. It is never sourced from or folded back into a release artifact.

## Public Core content

The Core payload may contain reviewed modules from `app/`, `core/`, portable `config/`, selected bounded worker code under `sandbox/`, and the operator-neutral prompts from `packaging/core_runtime_prompts/`. The installer maps those reviewed prompts to `derived/runtime/` in the installed payload. The source-tree runtime prompts are the same operator-neutral public material; user personalization belongs only in validated local state. Core also contains the root license, README, requirements, and public manifest.

## Absolute exclusions

No public source snapshot or package may contain `.env` values, credentials, tokens, private keys, local overrides, private operator identifiers or personalized runtime defaults, home paths, memory stores, journals, raw logs, vaults, runtime databases, browser profiles, model weights, model caches, private repositories, deployment secrets, database backups, dependency trees, build caches, or private operator/company state. Legitimate project authorship may remain in Git attribution, but it is not an installed user profile.

Tracked examples may describe secret and path fields only with null values, obvious placeholders, or non-secret test markers. Sanitizer source and tests may contain known secret-signature strings solely to prove rejection; the hygiene test distinguishes those fixtures from credentials.

## Optional profiles

Creator, media, Codev, and Lab source contracts may exist in reviewed public source. They are not silently included or enabled by Core. Machine-local model and worker paths resolve only from validated XDG local overrides and remain absent from UI, logs, receipts, and packages.

## Desktop asset decision

The historical development launcher at `../Elysia_App/Elysia.desktop` remains outside the repository because it contained checkout assumptions. Tauri owns the packaged Linux identity, icons, and desktop integration. `scripts/install_desktop_user.sh` may generate operator-local standard and convenience entries from a reviewed `.deb`; those generated files converge on one stable user-local install and are never copied into public source.

## Verification

Pass 9 contract tests parse the manifest, reject forbidden tracked paths and workstation markers, validate canon classification, and prove that portable tracked defaults contain no operator-specific model or worker path. Pass 10 must enumerate the exact clean artifact and compare it with this contract before publication.
