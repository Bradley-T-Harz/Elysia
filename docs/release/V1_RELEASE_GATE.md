# Elysia v1.0 Release Gate

Elysia is not a public v1.0 release until every required gate passes or the operator explicitly accepts a documented non-safety caveat. No push or publication occurs without the operator’s final approval.

## Source and contract gates

- [ ] The v1 scope, profiles, capability tiers, sandbox doctrine, public/private boundary, and upgrade/uninstall contracts agree.
- [ ] Root license is present and package metadata agrees.
- [ ] README and release notes accurately describe the release and optional external boundaries.
- [ ] Product and compatibility versions are aligned without falsely claiming readiness.
- [ ] Route/capability/profile truth has no dead endpoints or fake controls.

## Backend gates

- [ ] Focused Chunk 1–8, file, media, archive, database/binary, EngineeringForge, worker, approval, audit, path, and sanitization tests pass.
- [ ] Broad safe backend regression passes.
- [ ] Python compile/import checks pass from the supported Core environment.
- [ ] Async ASGI smoke passes.
- [ ] Synchronous `TestClient` behavior is either fixed or documented with an accepted reliable replacement.
- [ ] Pydantic deprecation warnings are resolved or explicitly accepted.

## Desktop gates

- [ ] Focused Desktop tests pass.
- [ ] TypeScript check passes.
- [ ] Production Vite build passes.
- [ ] Tauri `.deb` and AppImage builds pass.
- [ ] Installed packages launch the lifecycle-managed local API and Desktop successfully.
- [ ] Packaged-origin/API authentication/CSP checks pass.
- [ ] Every visible interactive control works or is truthfully non-interactive.
- [ ] Manual screenshots and keyboard/accessibility review cover every room and Quick Invoke.
- [ ] Bundle-size warnings are resolved or explicitly accepted.

## Codev gates

- [ ] Codev unit tests and full compile pass.
- [ ] VSIX packaging passes without publishing.
- [ ] Extension Host review passes in disposable trusted and untrusted workspaces.
- [ ] Session/reload, repo context, file preview, patch/review/apply, exact checks, trace IDs, and trust-mode behavior are proven.
- [ ] No hidden shell, Git push, broad repo ingestion, or cloud upload exists.

## Install/profile/doctor gates

- [ ] Core installs from a clean supported system without Creator or Developer dependencies.
- [ ] Each optional profile has a dry-run/plan and explicit dependency/resource warning.
- [ ] Doctor tests cover installed, missing, optional, blocked, degraded, no-model, no-GPU, no-sandbox, and incompatible-version states.
- [ ] No profile silently downloads a model, enables network, or weakens governance.
- [ ] Codev install checks pass for the Developer profile.

## Security and privacy gates

- [ ] Local API authentication rejects missing, invalid, stale, and cross-install credentials.
- [ ] API remains loopback/local-IPC only by default.
- [ ] XDG config/data/cache/state/runtime path tests pass.
- [ ] Runtime state is not written into the installed source/application tree.
- [ ] Public/private package-content and Git hygiene scans pass.
- [ ] No secrets, `.env`, credentials, private runtime stores, model tokens, private logs, journals, identity databases, or vault contents are included.
- [ ] Absolute-path and diagnostics scans expose no private paths in normal UI or receipts.
- [ ] Add-on and worker boundaries fail closed when approval, compatibility, sandbox, or revocation truth is missing.

## Upgrade/uninstall gates

- [ ] Upgrade preserves user config/data or performs a versioned, backed-up migration.
- [ ] Failed migration has a documented recovery path.
- [ ] Uninstall clearly reports retained user data.
- [ ] User data deletion requires a separate explicit action and exact target preview.
- [ ] Export/backup and diagnostics remain sanitized.

## Release-artifact gates

- [ ] Package contents are enumerated and reviewed from a clean checkout.
- [ ] Checksums are generated; signing/provenance policy is followed where approved.
- [ ] Third-party and model license/provenance notes are complete for shipped assets.
- [ ] Release notes list capabilities, profiles, limitations, warnings, and known caveats.
- [ ] Final Elysia and Codev Git statuses are clean at reviewed commits.
- [ ] No push, upload, Marketplace publication, or public release occurs without the operator’s explicit approval.
