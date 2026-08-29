# VS Code / Elysia Codev Coding Bridge Contract

Status: local-first coding bridge contract for the Elysia Codev companion.

## Purpose

The coding bridge lets a local VS Code companion talk to Elysia's governed coding spine. Elysia core owns the coding contracts and policy boundaries. Elysia Codev is only a doorway and operator interface.

## Live endpoints

- `GET /coding/status`
- `GET /coding/developer-profile`
- `POST /coding/session/start`
- `POST /coding/chat`
- `POST /coding/repo/inspect-preview`
- `POST /coding/repo/approval-status`
- `POST /coding/repo/approval-plan`
- `POST /coding/repo/approval-apply`
- `POST /coding/repo/revoke`
- `GET /coding/file-types`
- `POST /coding/file/inspect-type`
- `POST /coding/file/read-preview`
- `POST /coding/file/operation-plan`
- `POST /coding/file/operation-execute-approved`
- `GET /coding/document-types`
- `POST /coding/document/inspect`
- `POST /coding/document/extract-preview`
- `POST /coding/document/export-plan`
- `POST /coding/document/export-approved`
- `POST /coding/document/edit-plan`
- `POST /coding/document/apply-approved`
- `GET /coding/data-types`
- `POST /coding/data/inspect`
- `POST /coding/data/preview`
- `POST /coding/data/export-plan`
- `POST /coding/data/export-approved`
- `POST /coding/data/edit-plan`
- `POST /coding/data/apply-approved`
- `POST /coding/data/mutation-plan`
- `POST /coding/data/apply-mutation-approved`
- `GET /coding/visual-types`
- `POST /coding/visual/inspect`
- `POST /coding/visual/preview`
- `POST /coding/visual/ocr`
- `POST /coding/visual/analysis`
- `POST /coding/visual/export-plan`
- `POST /coding/visual/export-approved`
- `POST /coding/visual/edit-plan`
- `POST /coding/visual/apply-approved`
- `GET /coding/media-types`
- `GET /coding/media/workers`
- `GET /coding/media/gates`
- `POST /coding/media/inspect`
- `POST /coding/media/thumbnail`
- `POST /coding/media/transcribe/preview`
- `POST /coding/media/transcribe/apply`
- `GET /coding/media/tts/voices`
- `POST /coding/media/tts/preview`
- `POST /coding/media/tts/apply`
- `GET /coding/media/imageforge/models`
- `POST /coding/media/imageforge/preview`
- `POST /coding/media/imageforge/apply`
- `GET /coding/media/videoforge/models`
- `POST /coding/media/videoforge/preview`
- `POST /coding/media/videoforge/apply`
- `GET /coding/media/videoforge/jobs/{operation_id}`
- `POST /coding/media/videoforge/jobs/{operation_id}/cancel`
- `GET /coding/archive/types`
- `POST /coding/archive/inspect`
- `POST /coding/archive/extract/plan`
- `POST /coding/archive/extract/apply`
- `GET /coding/archive/jobs/{operation_id}`
- `POST /coding/archive/jobs/{operation_id}/cancel`
- `GET /coding/archive/artifacts/{artifact_id}`
- `GET /coding/database/types`
- `POST /coding/database/inspect`
- `POST /coding/database/schema/preview`
- `GET /coding/database/artifacts/{artifact_id}`
- `GET /coding/binary/types`
- `POST /coding/binary/inspect`
- `GET /coding/binary/artifacts/{artifact_id}`
- `GET /coding/engineering/types`
- `POST /coding/engineering/inspect`
- `POST /coding/engineering/preview/plan`
- `POST /coding/engineering/preview/apply`
- `GET /coding/engineering/jobs/{operation_id}`
- `POST /coding/engineering/jobs/{operation_id}/cancel`
- `GET /coding/engineering/artifacts/{artifact_id}`
- `POST /coding/patch/propose`
- `POST /coding/patch/apply-approved`
- `POST /coding/operation/approve`
- `GET /coding/operation/audit`
- `GET /coding/operation/audit/{operation_id}`
- `POST /coding/operation/result`
- `POST /coding/command/plan`
- `GET /coding/command/catalog`
- `POST /coding/command/run-approved`
- `GET /coding/command/status/{run_id}`
- `POST /coding/command/cancel`
- `POST /coding/git/preview`
- `POST /coding/task/plan`
- `POST /coding/task/approve`
- `POST /coding/task/next`
- `POST /coding/task/stop`

## Boundary truth

- Local loopback only.
- Packaged mutating requests require the private XDG local-client credential. Codev reads it only in the extension host; it is never returned to or displayed by the webview.
- VS Code workspace trust and an exact Elysia repository approval are separate gates. Broad roots, private paths, and symlink roots fail closed; revocation withdraws repo authority.
- Git status uses fixed direct argv with `shell=False` and reports real branch/HEAD/remote/SCM state without granting Git mutation.
- No cloud upload.
- No Marketplace account requirement.
- File previews are type-aware: Elysia returns file type, adapter, language,
  capability, risk, encoding, hash, parse summary, and redaction truth for
  supported Chunk 1 text/code/config/doc/data files.
- `.env` is blocked by default; `.env.example` is allowed with caution and
  secret scanning.
- Repository inspection preview returns metadata only.
- Selected file preview requires explicit operator approval.
- Patch proposals are non-mutating previews.
- File operation plans are non-mutating previews.
- Science/data stewardship is local and bounded. CSV/TSV, JSONL,
  GeoJSON, KML, and KMZ have standard-library governed workflows; Parquet,
  GIS/vector, raster, NetCDF, HDF5, and Zarr use the installed science stack
  for real metadata, schema/layer/band/variable summaries, bounded previews,
  exports, and stable derived-copy operations where supported.
- Data mutation is adapter-specific, approval-gated, backed up or transactional
  where required, and audited without storing full raw datasets.
- SQLite, DuckDB, and ambiguous `.db` files defer to DatabaseForge. Static
  metadata and exact-approved private read-only schema counts are available;
  rows, arbitrary SQL, query/export, repair, and mutation are unavailable.
- Archive/container stewardship is core-owned and local. Registered formats receive bounded static listing and risk truth. Only ZIP/TAR/TAR.GZ permit selected regular-file extraction, and only after exact one-time approval into a new disposable sandbox outside project roots.
- 7Z is list-only. RAR extraction is license-sensitive lab-only. WHL, JAR, VSIX, AppImage, and DEB are inspect-only and cannot be installed, executed, imported, activated, trusted, or merged by this bridge.
- BinaryForge is static and bounded: no execution, loading, linking, patching,
  trust, installation, decompilation, or exploit workflow is authorized.
- EngineeringForge provides bounded static reports and exact-approved
  sandbox-only SVG projections for STL, OBJ, DXF, and G-code. It grants no
  source mutation, physical output, controller/robot authority, ROS/Gazebo
  launch, script/plugin execution, cloud upload, or safety certification.
- Command planning is exact-allowlist only.
- Command execution is exact-allowlist, approval-gated, bounded-output only.
- Patch application is workspace-scoped, text-only, hash-checked,
  path-guarded, approval-gated, and audited.
- Git mutation is not implemented.
- Package-manager execution is not implemented.
- Developer Lab bounded task plan/approve/next/stop contracts are live. A plan permits at most eight manually requested checkpoints and thirty minutes. A checkpoint writes a receipt but executes no tool, command, patch, mutation, or background continuation.
- Autonomous coding loops are not implemented.

## Context receipt

Codev deliberately selects context. Chat may carry selected relative-path/SCM metadata and, only after a separate explicit approval, one bounded source preview. The response receipt states what metadata and source-preview class was included. It never includes a broad repository snapshot or raw absolute paths.

## Selected file preview

`POST /coding/file/read-preview` accepts a workspace root, selected file path, and explicit approval flag. It blocks paths outside the workspace, private/runtime/generated folders, secret-like filenames, binary extensions, and oversized content. Returned source preview is bounded and may redact lines matching conservative secret patterns. The preview includes file type, adapter, capability flags, risk flags, encoding, hashes, parse status, and adapter summary.

## Patch proposal

`POST /coding/patch/propose` validates target paths and returns a patch id, patch hash, bounded diff preview, blocked targets, and rollback note. It never applies the patch.

## Archive containers

`POST /coding/archive/inspect` requires an explicit selected-file inspection signal and returns bounded member/risk truth plus local-only artifact receipts. The plan/apply pair binds the exact archive hash, manifest digest, selected-member digest, sandbox destination hash, policy version, and plan hash. Apply consumes a fresh exact approval and never writes into the selected workspace. No extract-all, install, execute, import, trust, open, or project-merge endpoint exists.

## Operation ledger

`POST /coding/operation/approve` and `POST /coding/operation/result` record local audit truth under ignored runtime state. Approval records do not execute operations by themselves.

## Command planning

`POST /coding/command/plan` checks exact allowlist entries, per-entry execution posture, and risky blocked terms. Approved command execution currently exposes only the read-only `git diff --check` lane: exact argv, approved local workspace, timeout/bounded output, no package installs, no broad shell, and no git mutation. npm/Cargo scripts and build hooks remain visible as policy-disabled catalog entries until they can run in an isolated worker bound to reviewed workspace state.

`GET /coding/command/catalog` is the authoritative UI contract. Codev does not synthesize command choices or accept arbitrary terminal input. Run evidence carries normalized argv, sanitized cwd label, timing, exit status, bounded sanitized output, request/operation/approval IDs, and truncation truth.
