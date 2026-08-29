# BinaryForge autonomy policy

Binary stewardship defaults to Level 1 Directed. Elysia acts only after the operator selects a local file and requests static inspection. Extension recognition, executable permissions, signatures, installed tools, and clean-looking metadata never increase authority.

- Level 0: no binary action without an operator request.
- Level 1: Elysia may suggest static inspection but cannot start it.
- Level 2: a future explicit setting may allow bounded static metadata on an operator-provided file.
- Level 3: a future explicit setting may draft a separate sandbox-analysis request.

No autonomy level authorizes running an EXE, instantiating WASM, invoking Java, loading a DLL/SO, importing native code, linking an object, installing a package, trusting a binary, patching/mutating bytes, changing signatures, decompiling, or producing exploit guidance.

Disassembly remains `future_sandbox_required`. Sandboxed execution remains a separate future capability requiring isolation, no ambient filesystem/network/credential access, resource limits, provenance/lawfulness review, explicit exact approval, and new route and audit contracts. Static inspection can never silently cross that boundary.

Machine-readable defaults live in `config/policies/coding_binary_types.yaml`, `config/policies/binary_inspection_limits.yaml`, and `config/workers/binaryforge_worker.yaml`.
