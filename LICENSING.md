# Elysia licensing architecture

Copyright 2026 EcoSyneva Commons LLC.

Unless a file, directory, or notice says otherwise, the first-party Elysia software and documentation in this repository are licensed under Apache-2.0. The complete license is in `LICENSE` and `LICENSES/Apache-2.0.txt`.

The optional Workstation PDF worker at `workers/pdf/pymupdf_worker.py` is a separate stdin/stdout program licensed under AGPL-3.0-or-later because it links to AGPL-licensed PyMuPDF. It is not imported into Elysia Core. Its complete corresponding source is retained in this repository and its license is in `LICENSES/AGPL-3.0-or-later.txt`. A commercial Artifex license may be substituted by an operator who separately acquires one; Elysia does not claim such a license.

Third-party packages, models, voices, datasets, binaries, and system tools retain their own licenses. `THIRD_PARTY_NOTICES.md`, `MODEL_ASSET_NOTICES.md`, the profile manifests, and the Pass-III SBOMs describe the applicable relationships. Large model weights are selected and downloaded after installation; they are not relicensed or bundled by the Apache-2.0 grant.

Elysia and EcoSyneva names, logos, character identity, and distinctive branding are not granted for unrestricted use by Apache-2.0. See `TRADEMARKS.md`. Generated files and dependency lockfiles preserve their upstream metadata and are not claims of first-party authorship.

File-level policy is recorded through SPDX headers on exceptional files and `REUSE.toml` annotations for files that cannot carry headers. Contributions are accepted under the contribution terms in `CONTRIBUTING.md`.
