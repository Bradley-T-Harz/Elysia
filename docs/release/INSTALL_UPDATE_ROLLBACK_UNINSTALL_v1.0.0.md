# Elysia 1.0.0 install and lifecycle guide

Use Elysia Setup or one of the supported package forms described in the signed release manifest. Review the exact profile, acquisition, network, disk, model/license, hardware, and privilege preview before applying an installation. Setup installs the machine first; it does not create machine-global autobiography or assume that the Linux account, installer operator, Local Admin, local user, and public Commons identity are the same person.

After Doctor verifies the machine, first run atomically creates a local profile/account, establishes its encryption ownership, and starts its session. Personal onboarding is optional, question-by-question skippable, resumable, editable, privacy-classifiable, and review-before-memory. No onboarding answer becomes canonical memory without explicit account-owner approval.

Installation-wide update and repair mutation is Local Admin initiated and explicitly authorized. Elysia does not silently auto-update. Update material must match the governed publisher, stable channel, key identity, trust schema, artifact hashes, and Ed25519 signature. Unsigned, modified, malformed, wrong-key, wrong-publisher, wrong-channel, expired/revoked, or otherwise untrusted material fails closed.

Update previews the change, creates the required checkpoint, stages and verifies material, applies compatible migrations transactionally, runs Doctor, and activates atomically. Repair detects and reacquires package-owned corruption without resetting user Memory. Rollback respects schema compatibility and must not silently destroy newer user data.

Uninstall distinguishes optional-component removal, application removal with profiles/Memory preserved, export-then-remove, and an explicit total local-data purge. Preserved-data reinstall must recover the profile/account state. Purge is a separate, exact-target, previewed action; model vaults or user data outside Elysia ownership are not silently deleted.

The detailed contracts remain `UPGRADE_UNINSTALL.md`, `INSTALLER_DOCTOR_RUNTIME.md`, `INSTALL_PROFILES.md`, and the authoritative manifests under `config/install/`.
