# Chunk 6 ArchiveForge — final source truth

Date: 2026-08-12

Machine-readable authority lives in `config/policies/coding_archive_types.yaml`, `config/policies/archive_extraction_limits.yaml`, and `config/workers/archiveforge_worker.yaml`. Installed tool presence is dependency truth, not permission.

| Format | Inspection | Extraction | Final truth |
| --- | --- | --- | --- |
| ZIP | `available` | `extract_sandbox_only` | Static manifest/risk report; exact-approved selected regular files only. |
| TAR | `available` | `extract_sandbox_only` | Static manifest/risk report; links and special nodes never materialize. |
| TAR.GZ | `available` | `extract_sandbox_only` | Same selected sandbox lane as TAR with bounded decompression. |
| 7Z | `available` | `list_only` | Fixed-argument isolated external listing; no extraction lane. |
| RAR | `available` | `lab_only` | Listing when local tools permit; extraction/creation disabled and tooling is license-sensitive. |
| WHL | `available` | `unavailable_by_design` | Wheel metadata, entrypoints, RECORD presence, and native-module risk only; no pip install/import. |
| JAR | `available` | `unavailable_by_design` | Manifest, class/signature/service-provider risk only; no Java execution. |
| VSIX | `available` | `unavailable_by_design` | Manifest/package/activation/script risk only; no install or activation. |
| AppImage | `list_only` | `unavailable_by_design` | Static ELF/AppImage identification only; payload listing is not advertised; never run, mount, or `--appimage-extract`. |
| DEB | `available` | `unavailable_by_design` | Static ar/control/data and maintainer-script/system-payload inspection; no dpkg/apt install. |

## Security truth

ArchiveForge detects extension/content mismatch, traversal and absolute paths, Windows/UNC paths, excessive paths, exact duplicates, Unicode/case collisions, nested archives, encrypted members, links/devices/FIFOs/sockets, dangerous modes, native binaries, package scripts/entrypoints, bomb-like ratios, and configured archive/member/directory/projected/single-file limits. Over-limit input is refused before semantic container parsing. Extraction additionally enforces runtime, actual per-file bytes, total bytes written, exclusive descriptor-relative no-follow creation, an owned non-symlink sandbox root, a new sandbox ID, and sandbox/project separation.

Extraction is manual and selected-only; no `extractall` call exists. Source files are never mutated. A bounded hash-verified private archive snapshot closes the inspection/apply race and is deleted on success. Output modes are fixed at `0600`/`0700`. Operation ID, archive hash, manifest digest, selected-member digest, policy version, sandbox destination hash, and plan hash bind approval. A changed operation, archive, plan, selection, or destination is refused. Approval tokens expire and are consumed exactly once. Failure/cancellation removes partial output.

## Audit and interface truth

Full manifests, risk reports, extraction plans, and receipts are local artifacts. Sandbox copies are local disposable data. Central audit/request trace stores compact IDs, hashes, counts, risk totals, policy/tool truth, and outcome flags only. It excludes full member lists, sensitive names, archive/extracted bytes, absolute paths, package dumps, and worker logs.

Desktop and Codev add an ArchiveForge section to the existing selected-file surfaces. Controls are limited to list/risk, plan selected sandbox extraction, and exact-approved apply. Advanced truth is collapsible. There are no install, run, trust, executable-open, extract-all, or move-to-project controls.

## Proof boundary

Focused tests use hostile synthetic fixtures only. They cover ZIP/TAR/TAR.GZ extraction, real synthetic 7Z listing, traversal/absolute/Windows/UNC paths, collisions/duplicates, nested and encrypted members, symlink/hardlink/device/FIFO/socket entries, bomb and hard limits, package containers, one-time approvals, operation/archive/destination invalidation, sandbox escape/project overlap, abort cleanup, and compact audit/trace.

A disposable loopback route proof exercised types, inspect, plan, exact approval, apply, and token replay. It wrote one selected synthetic file at mode `0600` beneath a mode-`0700` sandbox, omitted the unselected member and private archive snapshot, reported no source/project/install/execute mutation, rejected replay as already used, and found no member name, archive name, or absolute workspace path in central audit. The complete `/tmp` proof tree was removed afterward.
