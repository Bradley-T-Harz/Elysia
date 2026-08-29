# Governed local semantic retrieval profile

Elysia's optional `semantic_local` profile extends—not replaces—the canonical
Memory Fabric and mandatory SQLite FTS5 retrieval path. It runs the pinned
Qdrant 1.19.0 unprivileged image as an Elysia-owned, authenticated,
telemetry-disabled REST service bound only to `127.0.0.1:6333`. gRPC, CORS,
restart-at-boot, public/LAN listeners, cloud services, and wildcard Docker port
bindings are disabled.

`scripts/manage_qdrant.sh install` is the explicit acquisition/enablement
boundary. `start`, `stop`, `restart`, `verify`, `snapshot`, `upgrade`,
`reset-derived`, and `uninstall` own the complete local lifecycle. Uninstall
removes the container/listener while preserving XDG configuration, snapshots,
and rebuildable cache. The client contract stays governed/enabled while those
vectors exist so a later privacy transition fails closed until reinstall or an
explicit recoverable reset; ordinary FTS retrieval still works. Reset moves a
corrupt cache to recoverable user state. Neither action modifies canonical
Memory. A Core source install exposes the same lifecycle tool as
`$XDG_DATA_HOME/elysia/runtime/bin/elysia-qdrant`; Desktop packages retain the
reviewed script as an application resource.

Normal Memory may receive persistent Qwen3-Embedding vectors. Private Memory
uses the authenticated ephemeral lexical path and leaves no persistent vector.
Sealed Memory is never embedded. Shared points keep source-owner and space IDs;
Qdrant filters them before approximate ranking and Elysia re-reads each result
through canonical authorization before use.

The promoted production scheduling policy uses Qwen on CPU so the resident 24B
conversation model is not evicted from a 16-GB GPU. This is a deterministic
Part 2C resource choice, not a learned governor and not Part 2D. FTS remains
fully functional if Qdrant, Ollama, the model, or the optional profile is absent.
