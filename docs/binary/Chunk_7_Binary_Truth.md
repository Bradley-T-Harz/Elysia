# Chunk 7 BinaryForge — final source truth

Date: 2026-08-12

| Format | Inspection | Final truth |
| --- | --- | --- |
| PE/EXE/DLL | `available` | Static PE headers, architecture, sections, imports/exports, debug/certificate presence, and risk indicators through `pefile`. |
| ELF/SO/O | `available` | Static ELF class/architecture, sections, dependencies, RPATH/RUNPATH, symbols, debug/strip, and executable-stack indicators through `pyelftools`. |
| Java CLASS | `available` | Bounded class version, hierarchy, constant-pool/reference, method/field count, native/reflection/file/process/network indicators; no class loading or decompilation. |
| WebAssembly | `available` | Bounded version, section, import/export, memory/table/function/global/start/custom-section truth; no instantiation. |
| Unknown BIN | `metadata_only` | Hash, size, magic, entropy, executable bit, and bounded artifact-only strings. |

Content signatures take precedence over extensions, and mismatches are reported. Every completed result explicitly reports that execution, loading, and mutation did not occur. Structural risk indicators are not a malware verdict, antivirus certification, trust decision, provenance finding, legal clearance, or license determination.

Detailed headers, section/import/export/symbol names, bounded strings, and toolchain truth are stored only in private mode-`0600` local artifacts. Central audit/request trace stores hashes, format, aggregate counts, risk totals, policy versions, IDs, approval state, and no-effect flags. It excludes binary bytes, raw strings and names, debug/absolute paths, and worker output.

Routes live now: `GET /coding/binary/types`, `POST /coding/binary/inspect`, and `GET /coding/binary/artifacts/{artifact_id}`. Execution, loading, import, installation, linking, trust, mutation, patching, signature tampering, decompilation, exploit assistance, and DRM/license bypass are unavailable by design. Deeper disassembly is `future_sandbox_required`; any future execution requires an independent capability-empty sandbox and exact approval.
