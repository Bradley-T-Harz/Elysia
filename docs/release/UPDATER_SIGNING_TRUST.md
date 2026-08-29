# Elysia Stable Updater Signing Trust

Elysia's stable updater uses one dedicated Ed25519 verification identity:

- publisher: `EcoSyneva Commons LLC`;
- channel: `stable`;
- key identifier: `elysia-updater-ed25519-2026-02`;
- mutation authority: an authenticated Local Admin or Installation Owner must
  initiate and explicitly approve an exact lifecycle preview;
- silent automatic update: unavailable.

The package-owned public policy is
`config/install/update_trust.yaml`. It contains no private signing material.
The unpublished `elysia-updater-ed25519-2026-01` authority is permanently
retired and untrusted; it cannot authorize updater material under this policy.
The encrypted private authority must be held offline, outside the source tree,
packages, runtime state, logs, VM images, and evidence. Staging encrypted
recovery bytes on the signing workstation does not satisfy separate physical
custody; each approved recovery copy must be placed on its Bradley-designated
offline destination before that custody gate is claimed complete.

## Verification contract

The updater accepts material only when all of these facts agree:

1. the public policy is schema-valid, active, in its validity interval, and
   names the exact supported algorithm, publisher, channel, and key identifier;
2. the release manifest is schema-valid and binds the same publisher, channel,
   and key identifier;
3. the detached Ed25519 signature verifies over the manifest's canonical JSON;
4. the local artifact filename, byte count, and SHA-256 match the signed
   manifest;
5. the manifest is unexpired and its memory-schema bounds are compatible;
6. the same authenticated Local Admin who created the exact preview explicitly
   approves it before mutation.

Unsigned material, an unknown/wrong signer, a wrong key identifier, a modified
artifact, an invalid or missing signature, malformed trust metadata, an expired
or revoked key, a wrong channel, or an unsupported schema fails closed. There
is no unsigned emergency bypass and no "continue anyway" path.

## Normal signing

`scripts/elysia_updater_signing.py` is the bounded operator utility. Linux-local
primary custody and passphrase files require exact private ownership and `0600`
mode. An explicitly designated encrypted removable recovery copy may reside on
a non-POSIX filesystem such as VFAT only after its physical device, mount, and
encryption posture are independently verified; VFAT mode bits are not treated
as confidentiality. The removable copy contains encrypted PKCS#8 material only,
never its passphrase. The utility signs only schema-valid Elysia release
manifests or old-key-authorized trust transitions bound to the active public
policy. It never prints private key bytes, encrypted key ciphertext, or
passphrases. Release engineering signs each exact immutable candidate before
qualification and external publication authorization.

## Recovery and loss

Primary custody and both recovery copies remain encrypted. A recovery exercise
loads a selected encrypted copy into memory, derives its public key, requires an
exact match to the package-owned public trust root, signs a disposable
challenge, and verifies that challenge. Plaintext private material is never
written.

If primary custody is lost, an authorized operator retrieves one separately
stored encrypted recovery copy and the separately controlled decryption secret,
runs the recovery proof, and re-establishes encrypted primary custody. The
remaining copy is not overwritten until restored custody and hashes are
verified.

If every private copy is lost, Elysia fails closed: the old public key remains
verification-only, no new stable updates can be signed, and no bypass is
created. A new trust root can ship only through a separately reviewed,
explicitly authorized full application release path whose exact bytes already
contain the replacement public policy.

## Rotation

Planned rotation creates a distinct successor key. The predecessor signs an
exact transition record binding publisher, channel, predecessor and successor
key identifiers, successor public key, activation/expiry times, and reason.
The transition must verify under the currently active predecessor. The
successor policy records `supersedes_key_id`; after activation, old-key
signatures do not validate under the new policy. A public key is never silently
replaced merely because another signature is cryptographically valid.

## Revocation and compromise

On suspected compromise:

1. stop signing and isolate custody;
2. record the exact affected key and time;
3. change its public lifecycle state to revoked with a reason through an
   explicitly authorized release path;
4. create a distinct replacement identity under a fresh ceremony;
5. use the old-key transition only if the predecessor remains trustworthy;
   otherwise use the full-release replacement path;
6. investigate every potentially affected signed release and communicate the
   exposure and remediation;
7. preserve the incident and rotation evidence without private key material.

A revoked or deprecated key cannot authorize future updater material. Runtime,
Website, cloud, model, connector, and ordinary-user identities never become
updater signing authorities.
