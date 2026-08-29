# Archive/container threat model

ArchiveForge treats every container and every member name as hostile input. Its protected assets are the selected workspace, Elysia source and runtime state, the host filesystem, secrets/private stores, process execution authority, and central audit privacy.

The principal threats and controls are:

- path escape: absolute, home-relative, traversal, Windows drive, and UNC paths are blocked before planning; normalized destinations must remain below the private extraction root;
- link and special-node redirection: symlinks, hardlinks, devices, FIFOs, sockets, and set-ID entries are never materialized;
- filesystem races: the sandbox must be new, private, owned by the process user, and not a symlink; directories and files use descriptor-relative no-follow/exclusive creation;
- archive mutation: apply re-inspects the source and creates a bounded, hash-verified private snapshot before reading member streams;
- decompression denial of service: input, member, directory, projected-size, single-file, path, ratio, runtime, worker-output, and actual-write caps fail closed;
- namespace ambiguity: exact duplicates and Unicode/case-fold collisions block extraction;
- recursive/code-bearing payloads: nested archives are reported but never expanded, and package scripts, entrypoints, executable bits, and native binaries are static risk truth only;
- password/coercion risks: encrypted archives are blocked, worker stdin is closed, and no password-recovery lane exists;
- authority escalation: no route or worker operation installs, executes, imports, activates, mounts, trusts, opens, extracts all, or writes into a project;
- privacy leakage: full names and package detail remain in local artifacts; central audit/trace receives only compact IDs, hashes, counts, risk totals, policy/tool truth, and outcomes.

RAR tooling is locally available but mixed multiverse/nonfree/license-sensitive. That provenance is surfaced in policy and UI; redistribution or broader enablement requires separate review.
