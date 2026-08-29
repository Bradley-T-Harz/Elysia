#!/usr/bin/env python3
"""Operator-only Ed25519 updater-key custody and signing utility.

Private keys are encrypted before they are written. The utility emits only
public fingerprints and bounded status; it never prints passphrases or private
key bytes. Release signing remains a separately authorized operator action
under the governed updater trust architecture.
"""

from __future__ import annotations

import argparse
import base64
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import tempfile
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.install.release_trust import (
    ReleaseArtifactManifest,
    ReleaseTrustError,
    ReleaseTrustTransition,
    UpdateTrustPolicy,
    revoked_trust_policy,
    verify_release_artifact,
    verify_trust_transition,
)


PASSPHRASE_BYTES = 64


class SigningCeremonyError(RuntimeError):
    """Operator signing input or custody state failed closed."""


def _private_file(
    path: Path,
    description: str,
    *,
    require_posix_private_mode: bool = True,
) -> Path:
    try:
        info = path.lstat()
    except OSError as exc:
        raise SigningCeremonyError(f"The {description} is unavailable.") from exc
    if (
        path.is_symlink()
        or not path.is_file()
        or info.st_uid != os.getuid()
        or (require_posix_private_mode and stat.S_IMODE(info.st_mode) != 0o600)
    ):
        expectation = (
            "exact private ownership/0600 mode"
            if require_posix_private_mode
            else "safe current-operator ownership"
        )
        raise SigningCeremonyError(f"The {description} lacks {expectation}.")
    return path


def _new_private_parent(path: Path) -> Path:
    parent = path.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent.chmod(0o700)
    info = parent.lstat()
    if parent.is_symlink() or not parent.is_dir() or info.st_uid != os.getuid():
        raise SigningCeremonyError("A private custody parent is unsafe.")
    if path.exists() or path.is_symlink():
        raise SigningCeremonyError("A custody output already exists; key material is never overwritten.")
    return parent


def _atomic_write(path: Path, content: bytes, *, mode: int, private_parent: bool) -> None:
    parent = _new_private_parent(path) if private_parent else path.parent
    if not private_parent:
        parent.mkdir(parents=True, exist_ok=True)
        if path.exists() or path.is_symlink():
            raise SigningCeremonyError("A public ceremony output already exists; overwrite is refused.")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=parent, prefix=f".{path.name}-", delete=False) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _public_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _fingerprint(public_key: bytes) -> str:
    return f"SHA256:{base64.urlsafe_b64encode(sha256(public_key).digest()).decode('ascii').rstrip('=')}"


def _encrypted_pkcs8(private_key: Ed25519PrivateKey, passphrase: bytes) -> bytes:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(passphrase),
    )


def _load_private_key(
    key_path: Path,
    passphrase_path: Path,
    *,
    encrypted_removable_copy: bool = False,
) -> Ed25519PrivateKey:
    key_blob = _private_file(
        key_path,
        "encrypted updater private key",
        require_posix_private_mode=not encrypted_removable_copy,
    ).read_bytes()
    passphrase = _private_file(passphrase_path, "updater custody passphrase").read_bytes().strip()
    if len(passphrase) < 48:
        raise SigningCeremonyError("The updater custody passphrase is below the required strength floor.")
    try:
        key = serialization.load_pem_private_key(key_blob, password=passphrase)
    except (TypeError, ValueError) as exc:
        raise SigningCeremonyError("The encrypted updater private key could not be recovered.") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise SigningCeremonyError("The custody file is not an Ed25519 updater key.")
    return key


def _load_public_policy(path: Path) -> UpdateTrustPolicy:
    try:
        return UpdateTrustPolicy.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise SigningCeremonyError("The production public trust policy is invalid.") from exc


def _json_status(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def generate(args: argparse.Namespace) -> None:
    custody_paths = [args.primary_key, *args.recovery_copy]
    if len(args.recovery_copy) != 2 or len(set(custody_paths)) != 3:
        raise SigningCeremonyError("Generation requires one primary and exactly two distinct recovery outputs.")
    passphrase = secrets.token_urlsafe(PASSPHRASE_BYTES).encode("ascii")
    private_key = Ed25519PrivateKey.generate()
    public_key = _public_bytes(private_key)
    _atomic_write(args.passphrase_file, passphrase + b"\n", mode=0o600, private_parent=True)
    for destination in custody_paths:
        _atomic_write(
            destination,
            _encrypted_pkcs8(private_key, passphrase),
            mode=0o600,
            private_parent=True,
        )
    policy = UpdateTrustPolicy(
        version=1,
        contract_version="elysia-update-trust-1.0",
        state="active",
        algorithm="ed25519",
        publisher=args.publisher,
        key_id=args.key_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
        not_before_utc=args.not_before,
        not_after_utc=args.not_after,
        channel=args.channel,
        mutation_authority="local_admin_explicit",
        silent_update_allowed=False,
        notes=[
            "Dedicated production updater verification key; private custody remains external to release artifacts and follows the operator offline-custody doctrine.",
            "Update and repair mutation requires an explicit authenticated Local Admin preview and approval.",
            "Unknown, unsigned, wrong-channel, expired, or revoked authority fails closed.",
        ],
    )
    policy_bytes = yaml.safe_dump(policy.model_dump(mode="json"), sort_keys=False).encode("utf-8")
    _atomic_write(args.trust_policy, policy_bytes, mode=0o644, private_parent=False)
    device_ids = {path.stat().st_dev for path in custody_paths}
    _json_status({
        "ceremony": "production_key_generated",
        "key_id": args.key_id,
        "public_key_fingerprint": _fingerprint(public_key),
        "encrypted_private_outputs": 3,
        "private_key_plaintext_written": False,
        "distinct_filesystem_device_count": len(device_ids),
        "three_distinct_filesystem_devices_detected": len(device_ids) == 3,
        "separate_physical_custody_proven": False,
        "physical_custody_requires_external_block_identity_evidence": True,
    })


def prove_recovery(args: argparse.Namespace) -> None:
    private_key = _load_private_key(
        args.private_key,
        args.passphrase_file,
        encrypted_removable_copy=bool(getattr(args, "encrypted_removable_copy", False)),
    )
    policy = _load_public_policy(args.trust_policy)
    public_key = _public_bytes(private_key)
    expected = base64.b64decode(str(policy.public_key_base64), validate=True)
    if policy.state != "active" or policy.key_id != args.key_id or public_key != expected:
        raise SigningCeremonyError("Recovered authority does not match the exact production trust root.")
    challenge = secrets.token_bytes(64)
    signature = private_key.sign(challenge)
    Ed25519PublicKey.from_public_bytes(expected).verify(signature, challenge)
    _json_status({
        "ceremony": "recovery_proven",
        "key_id": policy.key_id,
        "public_key_fingerprint": _fingerprint(public_key),
        "signature_verified": True,
        "private_key_plaintext_written": False,
    })


def prove_wrong_secret_refusal(args: argparse.Namespace) -> None:
    """Prove an encrypted custody copy refuses an unrelated recovery secret."""

    blob = _private_file(
        args.private_key,
        "encrypted updater private key",
        require_posix_private_mode=not bool(
            getattr(args, "encrypted_removable_copy", False)
        ),
    ).read_bytes()
    if b"-----BEGIN ENCRYPTED PRIVATE KEY-----" not in blob:
        raise SigningCeremonyError("The recovery artifact is not encrypted PKCS#8 material.")
    try:
        serialization.load_pem_private_key(blob, password=secrets.token_bytes(PASSPHRASE_BYTES))
    except (TypeError, ValueError):
        _json_status({
            "ceremony": "wrong_recovery_secret_refused",
            "key_id": args.key_id,
            "wrong_recovery_secret_rejected": True,
            "private_key_plaintext_written": False,
        })
        return
    raise SigningCeremonyError("An unrelated recovery secret unexpectedly decrypted custody material.")


def prove_retired_key_rejection(args: argparse.Namespace) -> None:
    """Prove a named retired private authority cannot satisfy successor trust."""

    retired_key = _load_private_key(args.retired_private_key, args.retired_passphrase_file)
    successor_policy = _load_public_policy(args.successor_trust_policy)
    if _public_bytes(retired_key) == base64.b64decode(
        str(successor_policy.public_key_base64), validate=True
    ):
        raise SigningCeremonyError("The alleged retired authority equals the successor authority.")
    with tempfile.TemporaryDirectory(prefix="elysia-retired-key-refusal-") as temporary:
        root = Path(temporary)
        artifact = root / "retired-key-refusal.tar"
        artifact.write_bytes(b"disposable retired-key refusal proof")
        now = datetime.now(UTC).replace(microsecond=0)
        manifest = ReleaseArtifactManifest(
            contract_version="elysia-release-artifact-manifest-1.0",
            publisher=successor_policy.publisher,
            product="Elysia",
            release_id="pass-iv-retired-key-refusal",
            version="0.0.0+pass4-retired-key-refusal",
            channel=successor_policy.channel,
            signing_key_id=str(successor_policy.key_id),
            artifact_filename=artifact.name,
            artifact_sha256=sha256(artifact.read_bytes()).hexdigest(),
            artifact_size_bytes=artifact.stat().st_size,
            component_graph_sha256="0" * 64,
            minimum_memory_schema=0,
            maximum_memory_schema=999,
            created_at_utc=now.isoformat(),
            expires_at_utc=(now + timedelta(minutes=30)).isoformat(),
        )
        manifest_path = root / "manifest.json"
        signature_path = root / "manifest.sig"
        manifest_path.write_text(
            json.dumps(manifest.model_dump(mode="json")), encoding="utf-8"
        )
        signature_path.write_text(
            base64.b64encode(retired_key.sign(manifest.canonical_bytes())).decode("ascii"),
            encoding="ascii",
        )
        try:
            verify_release_artifact(
                artifact_path=artifact,
                manifest_path=manifest_path,
                signature_path=signature_path,
                trust_policy_path=args.successor_trust_policy,
                now=now,
            )
        except ReleaseTrustError:
            _json_status({
                "ceremony": "retired_key_refused",
                "retired_key_id": args.retired_key_id,
                "successor_key_id": successor_policy.key_id,
                "retired_key_rejected": True,
                "private_key_plaintext_written": False,
                "disposable_material_removed": True,
            })
            return
    raise SigningCeremonyError("The retired authority unexpectedly satisfied successor trust.")


def sign_manifest(args: argparse.Namespace) -> None:
    private_key = _load_private_key(args.private_key, args.passphrase_file)
    policy = _load_public_policy(args.trust_policy)
    try:
        manifest = ReleaseArtifactManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SigningCeremonyError("The release artifact manifest is invalid.") from exc
    if (
        policy.state != "active"
        or manifest.publisher != policy.publisher
        or manifest.channel != policy.channel
        or manifest.signing_key_id != policy.key_id
        or _public_bytes(private_key) != base64.b64decode(str(policy.public_key_base64), validate=True)
    ):
        raise SigningCeremonyError("The manifest is not bound to this exact production signing authority.")
    signature = base64.b64encode(private_key.sign(manifest.canonical_bytes())) + b"\n"
    _atomic_write(args.signature, signature, mode=0o644, private_parent=False)
    _json_status({"ceremony": "manifest_signed", "key_id": policy.key_id, "signature_created": True})


def sign_transition(args: argparse.Namespace) -> None:
    private_key = _load_private_key(args.private_key, args.passphrase_file)
    policy = _load_public_policy(args.trust_policy)
    try:
        transition = ReleaseTrustTransition.model_validate_json(
            args.transition.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise SigningCeremonyError("The updater trust transition is invalid.") from exc
    if (
        policy.state != "active"
        or transition.publisher != policy.publisher
        or transition.channel != policy.channel
        or transition.previous_key_id != policy.key_id
        or _public_bytes(private_key) != base64.b64decode(str(policy.public_key_base64), validate=True)
    ):
        raise SigningCeremonyError("The transition is not bound to this exact predecessor authority.")
    signature = base64.b64encode(private_key.sign(transition.canonical_bytes())) + b"\n"
    _atomic_write(args.signature, signature, mode=0o644, private_parent=False)
    _json_status({"ceremony": "transition_signed", "key_id": policy.key_id, "signature_created": True})


def prove_ceremony(args: argparse.Namespace) -> None:
    """Exercise production public trust with disposable, never-published material."""

    private_key = _load_private_key(args.private_key, args.passphrase_file)
    policy = _load_public_policy(args.trust_policy)
    public_key = _public_bytes(private_key)
    if (
        policy.state != "active"
        or policy.key_id != args.key_id
        or public_key != base64.b64decode(str(policy.public_key_base64), validate=True)
    ):
        raise SigningCeremonyError("Ceremony authority differs from production public trust.")

    def write_json(path: Path, model: ReleaseArtifactManifest | ReleaseTrustTransition) -> None:
        path.write_text(json.dumps(model.model_dump(mode="json")), encoding="utf-8")

    def write_signature(path: Path, key: Ed25519PrivateKey, content: bytes) -> None:
        path.write_text(base64.b64encode(key.sign(content)).decode("ascii"), encoding="ascii")

    def verify_refusal(**kwargs: Any) -> None:
        try:
            verify_release_artifact(**kwargs)
        except ReleaseTrustError:
            return
        raise SigningCeremonyError("A required fail-closed updater refusal did not occur.")

    with tempfile.TemporaryDirectory(prefix="elysia-updater-ceremony-") as temporary:
        root = Path(temporary)
        artifact = root / "elysia-ceremony.tar"
        artifact.write_bytes(b"disposable never-published production-trust ceremony bytes")
        now = datetime.now(UTC).replace(microsecond=0)

        def manifest_for(
            *,
            channel: str = policy.channel,
            key_id: str = str(policy.key_id),
            publisher: str = policy.publisher,
            expires_at: datetime | None = None,
        ) -> ReleaseArtifactManifest:
            return ReleaseArtifactManifest(
                contract_version="elysia-release-artifact-manifest-1.0",
                publisher=publisher,
                product="Elysia",
                release_id="pass-iv-trust-ceremony",
                version="0.0.0+pass4-ceremony",
                channel=channel,
                signing_key_id=key_id,
                artifact_filename=artifact.name,
                artifact_sha256=sha256(artifact.read_bytes()).hexdigest(),
                artifact_size_bytes=artifact.stat().st_size,
                component_graph_sha256="0" * 64,
                minimum_memory_schema=0,
                maximum_memory_schema=999,
                created_at_utc=now.isoformat(),
                expires_at_utc=(expires_at or now + timedelta(minutes=30)).isoformat(),
            )

        manifest = manifest_for()
        manifest_path = root / "manifest.json"
        signature_path = root / "manifest.sig"
        write_json(manifest_path, manifest)
        write_signature(signature_path, private_key, manifest.canonical_bytes())
        verify_release_artifact(
            artifact_path=artifact,
            manifest_path=manifest_path,
            signature_path=signature_path,
            trust_policy_path=args.trust_policy,
            now=now,
        )

        original_artifact = artifact.read_bytes()
        artifact.write_bytes(original_artifact + b"modified")
        verify_refusal(
            artifact_path=artifact,
            manifest_path=manifest_path,
            signature_path=signature_path,
            trust_policy_path=args.trust_policy,
            now=now,
        )
        artifact.write_bytes(original_artifact)

        wrong_key = Ed25519PrivateKey.generate()
        wrong_signature = root / "wrong-key.sig"
        write_signature(wrong_signature, wrong_key, manifest.canonical_bytes())
        verify_refusal(
            artifact_path=artifact,
            manifest_path=manifest_path,
            signature_path=wrong_signature,
            trust_policy_path=args.trust_policy,
            now=now,
        )
        invalid_signature = root / "invalid.sig"
        invalid_signature.write_text(base64.b64encode(b"invalid" * 9 + b"x").decode("ascii"), encoding="ascii")
        verify_refusal(
            artifact_path=artifact,
            manifest_path=manifest_path,
            signature_path=invalid_signature,
            trust_policy_path=args.trust_policy,
            now=now,
        )
        missing_signature = root / "missing.sig"
        verify_refusal(
            artifact_path=artifact,
            manifest_path=manifest_path,
            signature_path=missing_signature,
            trust_policy_path=args.trust_policy,
            now=now,
        )

        wrong_channel_manifest = manifest_for(channel="candidate")
        wrong_channel_path = root / "wrong-channel.json"
        wrong_channel_signature = root / "wrong-channel.sig"
        write_json(wrong_channel_path, wrong_channel_manifest)
        write_signature(wrong_channel_signature, private_key, wrong_channel_manifest.canonical_bytes())
        verify_refusal(
            artifact_path=artifact,
            manifest_path=wrong_channel_path,
            signature_path=wrong_channel_signature,
            trust_policy_path=args.trust_policy,
            now=now,
        )

        wrong_publisher_manifest = manifest_for(publisher="Untrusted Publisher")
        wrong_publisher_path = root / "wrong-publisher.json"
        wrong_publisher_signature = root / "wrong-publisher.sig"
        write_json(wrong_publisher_path, wrong_publisher_manifest)
        write_signature(
            wrong_publisher_signature,
            private_key,
            wrong_publisher_manifest.canonical_bytes(),
        )
        verify_refusal(
            artifact_path=artifact,
            manifest_path=wrong_publisher_path,
            signature_path=wrong_publisher_signature,
            trust_policy_path=args.trust_policy,
            now=now,
        )

        wrong_identity_manifest = manifest_for(key_id="unknown-production-key")
        wrong_identity_path = root / "wrong-identity.json"
        wrong_identity_signature = root / "wrong-identity.sig"
        write_json(wrong_identity_path, wrong_identity_manifest)
        write_signature(wrong_identity_signature, private_key, wrong_identity_manifest.canonical_bytes())
        verify_refusal(
            artifact_path=artifact,
            manifest_path=wrong_identity_path,
            signature_path=wrong_identity_signature,
            trust_policy_path=args.trust_policy,
            now=now,
        )

        expired_manifest = manifest_for(expires_at=now - timedelta(seconds=1))
        expired_path = root / "expired.json"
        expired_signature = root / "expired.sig"
        write_json(expired_path, expired_manifest)
        write_signature(expired_signature, private_key, expired_manifest.canonical_bytes())
        verify_refusal(
            artifact_path=artifact,
            manifest_path=expired_path,
            signature_path=expired_signature,
            trust_policy_path=args.trust_policy,
            now=now,
        )

        malformed_policy = root / "malformed-trust.yaml"
        malformed_policy.write_text("version: 999\nstate: active\n", encoding="utf-8")
        verify_refusal(
            artifact_path=artifact,
            manifest_path=manifest_path,
            signature_path=signature_path,
            trust_policy_path=malformed_policy,
            now=now,
        )

        successor_private = Ed25519PrivateKey.generate()
        successor_public = _public_bytes(successor_private)
        transition = ReleaseTrustTransition(
            contract_version="elysia-update-trust-transition-1.0",
            transition_id="pass-iv-disposable-rotation-proof",
            publisher=policy.publisher,
            channel=policy.channel,
            previous_key_id=str(policy.key_id),
            new_key_id="elysia-updater-disposable-successor",
            new_public_key_base64=base64.b64encode(successor_public).decode("ascii"),
            created_at_utc=now.isoformat(),
            activates_at_utc=now.isoformat(),
            new_not_after_utc=(now + timedelta(days=365)).isoformat(),
            transition_expires_at_utc=(now + timedelta(minutes=30)).isoformat(),
            reason="Disposable Pass-IV old-key to new-key rotation proof.",
        )
        transition_path = root / "transition.json"
        transition_signature = root / "transition.sig"
        write_json(transition_path, transition)
        write_signature(transition_signature, private_key, transition.canonical_bytes())
        successor_policy = verify_trust_transition(
            transition_path=transition_path,
            signature_path=transition_signature,
            current_trust_policy_path=args.trust_policy,
            now=now,
        )
        successor_policy_path = root / "successor-trust.yaml"
        successor_policy_path.write_text(
            yaml.safe_dump(successor_policy.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )
        successor_manifest = manifest_for(key_id=transition.new_key_id)
        successor_path = root / "successor-manifest.json"
        successor_signature = root / "successor-manifest.sig"
        write_json(successor_path, successor_manifest)
        write_signature(successor_signature, successor_private, successor_manifest.canonical_bytes())
        verify_release_artifact(
            artifact_path=artifact,
            manifest_path=successor_path,
            signature_path=successor_signature,
            trust_policy_path=successor_policy_path,
            now=now,
        )
        old_key_for_successor = root / "old-key-successor.sig"
        write_signature(old_key_for_successor, private_key, successor_manifest.canonical_bytes())
        verify_refusal(
            artifact_path=artifact,
            manifest_path=successor_path,
            signature_path=old_key_for_successor,
            trust_policy_path=successor_policy_path,
            now=now,
        )

        revoked = revoked_trust_policy(
            policy,
            reason="Disposable Pass-IV compromise/revocation proof.",
            revoked_at_utc=now.isoformat(),
        )
        revoked_path = root / "revoked-trust.yaml"
        revoked_path.write_text(yaml.safe_dump(revoked.model_dump(mode="json")), encoding="utf-8")
        verify_refusal(
            artifact_path=artifact,
            manifest_path=manifest_path,
            signature_path=signature_path,
            trust_policy_path=revoked_path,
            now=now,
        )

    _json_status({
        "ceremony": "production_trust_proven",
        "key_id": policy.key_id,
        "normal_signature_accepted": True,
        "modified_material_rejected": True,
        "wrong_key_rejected": True,
        "invalid_signature_rejected": True,
        "missing_signature_rejected": True,
        "wrong_channel_rejected": True,
        "wrong_publisher_rejected": True,
        "wrong_key_id_rejected": True,
        "expired_manifest_rejected": True,
        "malformed_trust_rejected": True,
        "old_key_authorized_rotation": True,
        "unknown_old_key_after_rotation_rejected": True,
        "revoked_key_rejected": True,
        "private_key_plaintext_written": False,
        "disposable_material_removed": True,
    })


def _contains_any(path: Path, needles: dict[str, bytes]) -> set[str]:
    matches: set[str] = set()
    active = {name: value for name, value in needles.items() if value}
    if not active:
        return matches
    overlap = max(len(value) for value in active.values()) - 1
    previous = b""
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                window = previous + chunk
                for name, value in active.items():
                    if name not in matches and value in window:
                        matches.add(name)
                if len(matches) == len(active):
                    break
                previous = window[-overlap:] if overlap > 0 else b""
    except OSError as exc:
        raise SigningCeremonyError("A hygiene scan input could not be read.") from exc
    return matches


def hygiene_audit(args: argparse.Namespace) -> None:
    """Search governed release/evidence surfaces for actual private material."""

    private_key = _load_private_key(args.private_key[0], args.passphrase_file)
    passphrase = _private_file(args.passphrase_file, "updater custody passphrase").read_bytes().strip()
    raw_private = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    unencrypted_der = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    removable_keys = list(getattr(args, "encrypted_removable_key", []))
    custody_inputs = [
        (path, True) for path in args.private_key
    ] + [
        (path, False) for path in removable_keys
    ]
    encrypted_blobs = {
        f"encrypted_custody_blob_{index}": _private_file(
            path,
            "encrypted updater private key",
            require_posix_private_mode=require_posix_mode,
        ).read_bytes()
        for index, (path, require_posix_mode) in enumerate(custody_inputs, start=1)
    }
    needles = {
        "raw_ed25519_private_key": raw_private,
        "unencrypted_pkcs8_private_key": unencrypted_der,
        "custody_passphrase": passphrase,
        **encrypted_blobs,
    }
    generic_markers = {
        "generic_unencrypted_pem_marker": b"-----BEGIN " + b"PRIVATE KEY-----",
        "generic_encrypted_pem_marker": b"-----BEGIN " + b"ENCRYPTED PRIVATE KEY-----",
        "generic_openssh_private_marker": b"-----BEGIN OPENSSH " + b"PRIVATE KEY-----",
    }

    candidates: set[Path] = set()
    if args.git_root:
        root = args.git_root.resolve(strict=True)
        try:
            completed = subprocess.run(
                ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                cwd=root,
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SigningCeremonyError("The Git hygiene inventory could not be resolved.") from exc
        for raw in completed.stdout.split(b"\0"):
            if raw:
                candidate = root / os.fsdecode(raw)
                if candidate.is_file() and not candidate.is_symlink():
                    candidates.add(candidate)
    for scan_root in args.scan_root:
        resolved = scan_root.resolve(strict=True)
        if resolved.is_file() and not resolved.is_symlink():
            candidates.add(resolved)
        elif resolved.is_dir() and not resolved.is_symlink():
            candidates.update(
                path for path in resolved.rglob("*") if path.is_file() and not path.is_symlink()
            )
        else:
            raise SigningCeremonyError("A hygiene scan root is not a safe regular file/directory.")

    custody = {
        path.resolve(strict=True)
        for path in [*args.private_key, *removable_keys, args.passphrase_file]
    }
    if custody & candidates:
        raise SigningCeremonyError("A private custody file is inside the requested public/release scan set.")

    actual_matches: dict[str, list[str]] = {name: [] for name in needles}
    marker_matches: dict[str, list[str]] = {name: [] for name in generic_markers}
    suspicious_names: list[str] = []
    for path in sorted(candidates):
        for name in _contains_any(path, needles):
            actual_matches[name].append(str(path))
        for name in _contains_any(path, generic_markers):
            marker_matches[name].append(str(path))
        lowered = path.name.casefold()
        if lowered.endswith((".key", ".pk8", ".pk8.pem")) or "passphrase" in lowered:
            suspicious_names.append(str(path))

    actual_count = sum(len(values) for values in actual_matches.values())
    _json_status({
        "ceremony": "private_material_hygiene_audit",
        "scanned_file_count": len(candidates),
        "actual_private_material_occurrences": actual_count,
        "raw_private_key_occurrences": len(actual_matches["raw_ed25519_private_key"]),
        "unencrypted_private_key_occurrences": len(actual_matches["unencrypted_pkcs8_private_key"]),
        "custody_passphrase_occurrences": len(actual_matches["custody_passphrase"]),
        "encrypted_custody_blob_occurrences": sum(
            len(values) for name, values in actual_matches.items() if name.startswith("encrypted_custody_blob_")
        ),
        "generic_private_key_marker_files": sum(len(values) for values in marker_matches.values()),
        "suspicious_private_filename_count": len(suspicious_names),
        "private_material_absent": actual_count == 0,
    })
    if actual_count or suspicious_names:
        raise SigningCeremonyError("Private signing material or a suspicious custody filename entered a scanned surface.")


def _path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("Ceremony paths must be absolute.")
    return path


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    subcommands = command.add_subparsers(dest="command", required=True)

    create = subcommands.add_parser("generate", help="Create one encrypted production key authority.")
    create.add_argument("--key-id", required=True)
    create.add_argument("--publisher", required=True)
    create.add_argument("--channel", choices=("stable", "candidate", "development"), required=True)
    create.add_argument("--not-before", required=True)
    create.add_argument("--not-after", required=True)
    create.add_argument("--primary-key", type=_path, required=True)
    create.add_argument("--recovery-copy", type=_path, action="append", required=True)
    create.add_argument("--passphrase-file", type=_path, required=True)
    create.add_argument("--trust-policy", type=_path, required=True)
    create.set_defaults(action=generate)

    recovery = subcommands.add_parser("prove-recovery", help="Recover in memory and prove authority.")
    recovery.add_argument("--key-id", required=True)
    recovery.add_argument("--private-key", type=_path, required=True)
    recovery.add_argument("--passphrase-file", type=_path, required=True)
    recovery.add_argument("--trust-policy", type=_path, required=True)
    recovery.add_argument("--encrypted-removable-copy", action="store_true")
    recovery.set_defaults(action=prove_recovery)

    wrong_secret = subcommands.add_parser(
        "prove-wrong-secret-refusal",
        help="Prove an unrelated secret cannot decrypt an encrypted custody copy.",
    )
    wrong_secret.add_argument("--key-id", required=True)
    wrong_secret.add_argument("--private-key", type=_path, required=True)
    wrong_secret.add_argument("--encrypted-removable-copy", action="store_true")
    wrong_secret.set_defaults(action=prove_wrong_secret_refusal)

    retired = subcommands.add_parser(
        "prove-retired-key-rejection",
        help="Prove a retired private authority cannot satisfy successor public trust.",
    )
    retired.add_argument("--retired-key-id", required=True)
    retired.add_argument("--retired-private-key", type=_path, required=True)
    retired.add_argument("--retired-passphrase-file", type=_path, required=True)
    retired.add_argument("--successor-trust-policy", type=_path, required=True)
    retired.set_defaults(action=prove_retired_key_rejection)

    ceremony = subcommands.add_parser(
        "prove-ceremony", help="Exercise fail-closed production trust with disposable material."
    )
    ceremony.add_argument("--key-id", required=True)
    ceremony.add_argument("--private-key", type=_path, required=True)
    ceremony.add_argument("--passphrase-file", type=_path, required=True)
    ceremony.add_argument("--trust-policy", type=_path, required=True)
    ceremony.set_defaults(action=prove_ceremony)

    hygiene = subcommands.add_parser(
        "hygiene-audit", help="Search Git/release/evidence surfaces for actual private material."
    )
    hygiene.add_argument("--private-key", type=_path, action="append", required=True)
    hygiene.add_argument("--encrypted-removable-key", type=_path, action="append", default=[])
    hygiene.add_argument("--passphrase-file", type=_path, required=True)
    hygiene.add_argument("--git-root", type=_path)
    hygiene.add_argument("--scan-root", type=_path, action="append", default=[])
    hygiene.set_defaults(action=hygiene_audit)

    for name, action, input_name in (
        ("sign-manifest", sign_manifest, "manifest"),
        ("sign-transition", sign_transition, "transition"),
    ):
        signer = subcommands.add_parser(name)
        signer.add_argument("--private-key", type=_path, required=True)
        signer.add_argument("--passphrase-file", type=_path, required=True)
        signer.add_argument("--trust-policy", type=_path, required=True)
        signer.add_argument(f"--{input_name}", type=_path, required=True)
        signer.add_argument("--signature", type=_path, required=True)
        signer.set_defaults(action=action)
    return command


def main() -> int:
    args = parser().parse_args()
    try:
        args.action(args)
    except (SigningCeremonyError, InvalidSignature, OSError, ValueError) as exc:
        print(f"Signing ceremony refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
