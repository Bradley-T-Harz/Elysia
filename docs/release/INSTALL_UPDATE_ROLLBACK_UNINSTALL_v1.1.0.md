# Elysia / Codev 1.1.0 installation and upgrade

Exact-byte qualification and publication status belong to the signed release
manifest and canonical release pages. Unsigned candidates are not stable updates.
Obtain Elysia and Codev only from the canonical signed GitHub release family.
Verify SHA-256, size, and the detached manifest signature with the established
Ed25519 public trust policy before installing. A checksum alone is not publisher
authentication. No new trust root or unsigned update bypass is provided.

| Combination | Intended governed behavior |
| --- | --- |
| Elysia 1.1.0, Core absent | Ordinary Elysia; no Codev workroom |
| Elysia 1.1.0 + Core 1.1.0 | Codev appears independently of workspace trust |
| Core 1.1.0 + adapter 1.1.0 | Private Unix discovery; no manual TCP port |
| Adapter alone | Missing-Core guidance |
| Mixed native 1.0.0 / 1.1.0 | Upgrade to the matching family; no false Ready |
| Compatible website + Core | Explicit Sync/native approval/refresh, zero files shared |

Install the Elysia amd64 Debian package through the normal package manager.
Install the separate `codev-core` amd64 Debian package to enable Codev. The
coordinated installation supports either order; the signed release evidence
identifies the qualified package bytes and installation scenarios. VS Code is
optional. The Core package carries the matching
VSIX for explicit later installation using `codev codev-adapter --editor code`
and an optional chosen profile. Never replace an active test-controller profile.

For user installation use the release's supplied installer and its exact local
package argument. Installer preview precedes `--apply`. Inspect both per-user
and system launchers before upgrading: a retained user-local launcher may shadow
a system package. Do not resolve precedence by deleting account or model data.

Original public 1.0.0 and later local builds bearing 1.0.0 are distinct upgrade
inputs. Their checksums/source identities must be recorded separately. Preserve
local accounts, photos, conversations, settings, memory, and files. This release
introduces no identity or memory schema migration. Do not infer downgrade safety
for any future schema. Keep the old verified package and a recoverable data
snapshot before a governed migration.

Repair/reinstall with the same verified package manager or supplied installer.
Use `apt remove codev-core` for system removal or the supplied user uninstaller
for a user installation. Removing Core must hide the Elysia workroom while
ordinary Elysia continues. Never remove local identity/memory/models as part of
package removal. Reinstallation changes installation identity and invalidates
old sessions; it must not restore revoked workspace or website grants.

Local operation requires no website account. Website development requires an
ordinary signed-in account, explicit pairing, and separate exact file grants.
No model, cloud service, arbitrary network, or repository authority is enabled
by installation. Models and optional dependencies remain separately acquired.
