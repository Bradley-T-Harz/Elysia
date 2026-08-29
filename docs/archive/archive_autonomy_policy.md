# ArchiveForge autonomy policy

Archive stewardship defaults to Level 1 Directed. Elysia acts only when the operator selects a local archive and requests an action. Installed tools, a recognized container, or a clean risk report never raise authority.

The policy-ready progression is deliberately narrow:

- Level 0: no archive action without an operator request.
- Level 1: Elysia may suggest inspection but cannot start it.
- Level 2: a future explicit setting may permit read-only inspection of an operator-provided archive.
- Level 3: a future explicit setting may permit drafting an extraction plan.

No level can authorize extraction. Selected-file sandbox extraction always requires a fresh, exact, expiring, one-time human approval bound to the operation ID, archive hash, manifest, selection, policy limits, and sandbox destination. Installation, execution, import, activation, auto-open, trust, recursive expansion, and movement into a project remain unavailable by design. A later move/copy workflow would require a separate policy and approval; Chunk 6 does not provide one.

The machine-readable defaults are in `config/policies/coding_archive_types.yaml` and `config/policies/coding_autonomy.yaml`.
