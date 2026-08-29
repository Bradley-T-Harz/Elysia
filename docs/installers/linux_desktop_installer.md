# Linux Desktop Installer

This document records the Pass-IV Linux installation and lifecycle contract for
the Elysia desktop chamber.

## Scope

Machine installation and personal onboarding are separate authorities. A package
install may place package-owned application bytes and launch Elysia Setup; it
does not create autobiography, merge local and public Identity, enable an
external service, or grant new tool authority. Setup resolves profiles through
the authoritative component graph and exact acquisition manifests. First local
account creation and voluntary onboarding occur only after machine setup and
Doctor complete.

The complete dependency path, A-E dispositions, exact automatic-acquisition
boundaries, and the few unavoidable user actions are documented in
[`../release/DEPENDENCY_ACQUISITION_AND_MANUAL_ACTIONS.md`](../release/DEPENDENCY_ACQUISITION_AND_MANUAL_ACTIONS.md).

## Supported Bundles

- Debian package: `.deb`
- AppImage: `.AppImage`
- Digest-keyed user-local extraction of the `.deb`
- One-file packaged Core runtime
- Source installation for explicit development use
- Codev VSIX for the Developer/Codev profile

The Tauri bundle configuration is intentionally limited to these Linux bundle
targets for this pass.

The `.deb` uses conventional package-manager locations and lifecycle. The
AppImage remains relocatable while all account, Memory, project, configuration,
and state roots remain governed by XDG; moving the AppImage does not move or
duplicate personal state. The user-local extraction lane is implemented by
`scripts/install_desktop_user.sh`; it provides digest-keyed install/repair and
receipt-bound rollback without sudo. `scripts/uninstall_desktop_user.sh` removes
only receipted application bytes and launchers into private recoverable state,
preserving XDG personal data for reinstall.

## Build Command

From the repository root:

```bash
scripts/build_elysia_desktop_installer.sh
```

The script runs:

- frontend typecheck
- frontend production build
- Tauri Linux bundle build for `deb` and `appimage`

The Linux Tauri package command runs through a repository-owned wrapper that
remaps compiler source paths under the current user home to a generic build
label. It accepts only `deb`, `appimage`, or both through the optional
`ELYSIA_TAURI_BUNDLES` build variable and does not install the resulting file.
Every cached linuxdeploy input, the extracted appimagetool binary, and the
embedded type-2 runtime are SHA-256 bound by
`config/install/package_build_tools.yaml`. The official runtime channel is
mutable, so a build fails closed if its bytes differ from the reviewed identity;
no moving runtime is silently accepted into a package.

The qualified v1.0.0 release artifacts are produced by a clean controlled build,
bound to the signed immutable release manifest, and verified against their exact
checksums before installation. Local builds are not interchangeable with those
canonical release bytes.

## Account Gate Note

The packaged desktop app opens through the local identity gate. If no local user
exists, the User Creator is shown before the chamber mounts. If the user is
logged out, the Login page is shown before the chamber mounts.

Private account fields remain in the sealed local identity store and are not
normal Memory.

Personal onboarding is optional. It requires a real authenticated local
`user_id` and encryption owner, supports skip/save/resume/edit and per-answer
privacy, and writes nothing to canonical autobiographical Memory until the user
reviews the proposed packet and explicitly imports all, selected, or none. A
public Commons account remains optional and is never silently equated with local
Identity.

## Lifecycle boundaries

The in-app signed lifecycle panel governs the versioned managed Core runtime:
verified update, bounded repair, schema-compatible rollback, application removal
with personal data preserved, export-then-remove, and explicit total purge. It
does not pretend to be the host package manager. System `.deb` updates/removal
use the distribution package manager; AppImage replacement/removal remains an
explicit file-owner action; the receipted user-local lane uses the scripts above.
Every Elysia-owned mutating lane previews effects and preserves user data unless
the user chooses an exact destructive phrase.
