# Third-party notices

This repository depends on separately licensed Python, Node, Rust, system, container, and model components. Exact component versions, dependency profiles, license expressions, vulnerability dispositions, and distribution relationships are recorded in the Pass-III SPDX/CycloneDX SBOMs and component matrices.

The Desktop Node dependency notice is installed at `apps/elysia-desktop/THIRD_PARTY_NOTICES.txt`. Complete common license texts are retained in `LICENSES/`. Python profile dependencies are downloaded after explicit profile selection from their upstream distribution sources and are not relicensed by Elysia. Rust and Node packages bundled into a release retain the copyright/license files included by their upstream packages.

Notable bounded relationships include: PyInstaller under GPL-2.0-or-later with its bootloader exception for build-only packaging; the separately licensed optional AGPL PyMuPDF worker described in `LICENSING.md`; FFmpeg according to the exact system build configuration; Qdrant, SearXNG, and sandbox base images by pinned digest; and model/voice terms described in `MODEL_ASSET_NOTICES.md`.
