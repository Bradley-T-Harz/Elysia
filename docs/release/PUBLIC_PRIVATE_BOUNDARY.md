# Elysia Public/Private Boundary

Elysia uses one canonical source codebase. Public/private separation is achieved through tracked portable defaults, gitignored local overrides, per-user runtime directories, package-content rules, and sanitized diagnostics—not through drifting source forks.

## Material that must not ship

The public repository and release packages must not contain:

- user-private memory or personal journals;
- private logs, request transcripts, raw prompts, or raw tool output;
- `.env` files;
- keys, tokens, credentials, browser profiles, or service-role secrets;
- vault contents or local model-vault secrets;
- identity databases, sessions, profile photos, or private profile fields;
- local runtime databases and generated runtime artifacts;
- private EcoSyneva runtime or business material not deliberately approved for publication;
- machine-specific config or approved-repository lists;
- avoidable local absolute paths;
- private model tokens or authenticated download state;
- downloaded model weights, caches, build artifacts, or dependency trees.

Reviewed canon is public doctrine after operator-specific relational and workstation details are generalized. Historical reports still require explicit public-release classification. A tracked file is not automatically approved public content.

## Tracked defaults and local overrides

Tracked files may contain:

- schemas;
- portable default policy;
- symbolic model, worker, capability, and dependency identifiers;
- example configuration with null, relative, or environment-resolved values;
- public documentation and sanitized fixtures.

User-specific values must live in gitignored local configuration. Local overrides may select:

- model provider endpoints restricted by policy;
- installed model tags;
- model-vault roots;
- optional worker executables and model assets;
- approved repository roots;
- profile choices and explicitly permitted external providers.

Tracked configuration must never claim that a machine-specific model, tool, sandbox, or path exists. Doctor verifies local reality.

## Per-user path doctrine

Public installs will use platform user directories. On Linux the intended roots are:

| Kind | Root |
|---|---|
| Configuration | `${XDG_CONFIG_HOME:-$HOME/.config}/elysia` |
| Durable user data | `${XDG_DATA_HOME:-$HOME/.local/share}/elysia` |
| Rebuildable cache and optionally selected models | `${XDG_CACHE_HOME:-$HOME/.cache}/elysia` or a user-selected model vault |
| Logs and operational state | `${XDG_STATE_HOME:-$HOME/.local/state}/elysia` |
| Runtime socket/client credential | `${XDG_RUNTIME_DIR}/elysia` |

The source checkout is not a production data directory. Pass 1 documents this contract but does not migrate existing local state.

## Override precedence target

```text
immutable built-in safety floor
→ tracked public defaults
→ selected install profile
→ validated user-local override
→ exact per-operation approval
```

A user override cannot disable the immutable safety floor or silently authorize cloud, outbound, hardware, private-memory, or arbitrary-shell behavior.

## Diagnostics

Normal UI and support reports use:

- stable component and capability IDs;
- versions and profile names;
- relative labels rather than absolute paths;
- hashes where identity is necessary;
- bounded status/reason codes;
- sanitized warnings and stderr summaries;
- request, operation, approval, and receipt IDs.

Normal UI must not expose raw private paths, tokens, prompts, transcripts, journals, environment values, full tool command lines, or secret-bearing logs.

An explicit diagnostic export may be added later only if it previews its exact contents, applies sanitization, and requires user confirmation before saving or sending.

## Packaging and Git hygiene

Before release:

1. Enumerate package contents from a clean checkout.
2. Reject runtime data, local overrides, secrets, models, caches, dependency trees, generated test state, and machine-specific files.
3. Run path-only secret and absolute-path scans without printing secret values.
4. Verify examples contain no operator names, home paths, private repository roots, or credentials.
5. Verify the package creates user data only under the documented per-user roots.
6. Verify uninstall does not delete user data without an explicit separate action.

## Pass 9 path status

Tracked machine, model, and worker defaults are portable and fail closed. Optional local asset and interpreter paths come only from validated XDG local overrides; public status surfaces expose presence/state, never values. Historical reports are classified separately and excluded from the installed Core payload. Pass 10 must still enumerate the exact source snapshot and package artifact before publication.
