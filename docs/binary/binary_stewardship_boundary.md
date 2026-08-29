# Binary stewardship boundary

Binary files are untrusted data. A recognized PE, ELF, Java class, WebAssembly module, executable bit, signature marker, import list, low risk count, or installed analysis library never authorizes execution, loading, importing, installation, linking, trust, patching, or mutation.

BinaryForge accepts only an explicitly selected regular file under an approved, path-guarded workspace. Its fixed worker operation computes bounded hashes, type/magic, size, entropy, strings, headers, sections, imports, exports, symbols, and risk indicators where the format parser safely supports them. PE uses `pefile`; ELF uses `pyelftools`; Java class and WebAssembly use bounded structural parsers. Unknown `.bin` files remain metadata-only. Content wins over extension, and mismatch is reported.

Detailed headers, names, imports, exports, symbols, and bounded strings remain in a private local artifact. Central audit and request trace contain only hashes, counts, IDs, format, risk totals, policy versions, and outcome flags. They exclude strings, names, debug paths, absolute paths, binary bytes, and worker output.

Risk flags are structural indicators, not a malware verdict, antivirus certification, trust decision, legal clearance, provenance finding, license decision, or exploit assessment. BinaryForge provides no decompilation, exploit assistance, DRM/license bypass, signature modification, or tampering workflow.

The worker has one static `inspect` operation. It has no shell, stdin, arbitrary arguments, execution, dynamic loading, import into Elysia, installation, linking, mutation, patch, disassembly, or decompilation operation. Future deeper disassembly requires a new sandbox and lawfulness gate. Future execution requires a separate capability-empty sandbox and cannot reuse static-inspection authority.
