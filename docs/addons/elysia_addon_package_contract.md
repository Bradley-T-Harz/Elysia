# Elysia Add-on Package Contract

The governing Pass 7 release doctrine is
`docs/release/ADDON_DEVELOPER_FORGE_MARKETPLACE_DOCTRINE.md`. This compact contract
describes the implemented local package shape. Pass 7 extends it without
introducing a second manifest format.

`.elysia-addon` packages are ZIP-like archives inspected by local Elysia before any installation state changes.
The portable schema 1.1 example is `config/addons/manifest.example.json`; its
placeholder checksum must be replaced with the real payload digest before packaging.

Required package contents:

- `manifest.json`
- declared entrypoint files
- files listed in `manifest.checksums.files`

Schema 1.1 carries license, provenance, dependency, network/filesystem/memory/
model/tool policy, execution, bridge, sandbox, checksum, and signing-ready
identity fields. A README, dependency inventory or SBOM, and changelog remain
review/package-quality expectations where applicable. Missing signing
infrastructure is reported as `unsigned`, never as a valid signature.

Required manifest fields:

- `schema_version`
- `addon_id`
- `name`
- `version`
- `publisher`
- `compatibility`
- `required_profiles`
- `entrypoints`
- `bridge`
- `permissions`
- deny-by-default network, filesystem, memory, model/provider, and tool/worker policies
- `execution`
- `sandbox`
- `external_services`
- `license`
- `provenance`
- `signing`
- `dependencies`
- `checksums`
- `binaries`

Local Elysia rejects packages with path traversal, absolute paths, symlinks, special
files, hidden `.env` or credential material, private path references, excessive file
count/size or archive nesting, undeclared binaries/scripts/network behavior,
undeclared permissions, invalid compatibility, missing entrypoints, or checksum
mismatches.

The website may prepare install intents, but the package contract is enforced locally. A Marketplace listing, saved add-on, or deep link is never a permission grant.

Package and ordinary upload inspection are static. They do not import or execute
payload code. `manifest.json` is the canonical manifest name for v1; alternative
serializations require a later versioned contract rather than silent acceptance.
