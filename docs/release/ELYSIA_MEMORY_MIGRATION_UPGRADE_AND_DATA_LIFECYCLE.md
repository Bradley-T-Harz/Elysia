# Memory Migration, Upgrade, Uninstall, and Data Preservation

## XDG authority

Source, one-file Core, `.deb`, and AppImage resolve the same XDG-local Memory
authority through the packaged path contract. No canonical write belongs under
the source tree, package payload, AppImage mount, `/usr`, or current working
directory. Database, locks, keys, objects, projections, archives, checkpoints,
and semantic configuration use their governed XDG locations and private modes.

## Schema upgrade

The Part 2E canonical schema is version 3. Initialization is additive and
idempotent. Before upgrading an existing version 1/2 database, Elysia creates a
private verified SQLite snapshot. If any schema stage fails, it quarantines the
failed candidate and restores the snapshot. The migration ledger records
content-free rollback metadata without public/private paths.

Protected digest migration is authority-aware. Private legacy hashes upgrade
after authenticated session key provisioning. Sealed legacy hashes wait for an
explicit vault unlock. Neither operation changes content or ownership.

## Legacy memory import

Package-relative legacy JSON is read-only migration input. Migration builds and
validates a candidate canonical database, checks stable IDs and counts, archives
legacy inputs, and atomically cuts over. On post-cutover failure the prior
database is restored. There is no legacy writer after cutover and no dual
writer.

## Projection/object recovery

FTS, optional semantics, and deterministic graph are derived. Corrupt or
deleted projections rebuild from canonical records. Orphan object recovery
removes only bytes lacking canonical object metadata. Cold object corruption
is reported; canonical metadata and managed backups remain the recovery path.

## Package upgrade

Upgrade must preserve Identity, accounts, sessions as defined by the Identity
contract, Memory DB/keys/objects/archives, Conversations, Projects, artifacts,
and semantic configuration. It installs the promoted Zstandard dependency and
runs doctor/schema checks before claiming the selector healthy. A failed
upgrade restores the prior payload/selector and leaves XDG data intact.

## Uninstall and reinstall

Uninstall removes application payload, launchers owned by the package, and
Elysia-owned service/container lifecycle. It does not delete intended user XDG
data. Qdrant, when the optional profile is installed, remains a derived
projection and can be removed/rebuilt without affecting Memory. Reinstall uses
the preserved authorities and repeats migrations idempotently.

Account deletion is separate from package uninstall. Identity key destruction
is refused while the account still owns Memory, Projects, Conversations,
Shared Spaces, or protected assets; the user must deliberately export/archive/
delete owned state first.

## Clean public installation

Clean install and final operator reset must report users 0, profiles 0, active
sessions 0, Memory records 0, spaces 0, and candidates 0. No personal profile
or memory is seeded. First-run account creation provisions isolated keys and
the canonical Memory Fabric only for the newly created synthetic/operator
account.
