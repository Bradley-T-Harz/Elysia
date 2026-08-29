from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization

from app.install.release_trust import (
    ReleaseArtifactManifest,
    ReleaseTrustError,
    verify_release_artifact,
)
from scripts.elysia_updater_signing import (
    SigningCeremonyError,
    generate,
    hygiene_audit,
    prove_ceremony,
    prove_recovery,
    prove_retired_key_rejection,
    prove_wrong_secret_refusal,
    sign_manifest,
)
from scripts.verify_candidate_family import verify_family


def _generated(tmp_path: Path) -> SimpleNamespace:
    now = datetime.now(UTC)
    args = SimpleNamespace(
        key_id="synthetic-production-trust",
        publisher="EcoSyneva Commons LLC",
        channel="stable",
        not_before=(now - timedelta(minutes=1)).isoformat(),
        not_after=(now + timedelta(days=30)).isoformat(),
        primary_key=tmp_path / "primary" / "key.pk8.pem",
        recovery_copy=[
            tmp_path / "recovery-a" / "key.pk8.pem",
            tmp_path / "recovery-b" / "key.pk8.pem",
        ],
        passphrase_file=tmp_path / "secret" / "passphrase",
        trust_policy=tmp_path / "public" / "trust.yaml",
    )
    generate(args)
    return args


def test_generation_writes_three_distinct_encrypted_copies_and_public_trust(tmp_path: Path) -> None:
    args = _generated(tmp_path)
    custody = [args.primary_key, *args.recovery_copy]
    assert len({path.read_bytes() for path in custody}) == 3
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in custody)
    assert args.passphrase_file.stat().st_mode & 0o777 == 0o600
    assert b"PRIVATE KEY" not in args.trust_policy.read_bytes()
    for path in custody:
        prove_recovery(SimpleNamespace(
            key_id=args.key_id,
            private_key=path,
            passphrase_file=args.passphrase_file,
            trust_policy=args.trust_policy,
        ))


def test_manifest_signing_is_exact_and_verifies_fail_closed(tmp_path: Path) -> None:
    args = _generated(tmp_path)
    artifact = tmp_path / "elysia-test.tar"
    artifact.write_bytes(b"exact artifact bytes")
    now = datetime.now(UTC)
    manifest = ReleaseArtifactManifest(
        contract_version="elysia-release-artifact-manifest-1.0",
        publisher=args.publisher,
        product="Elysia",
        release_id="synthetic-1",
        version="0.1.0",
        channel="stable",
        signing_key_id=args.key_id,
        artifact_filename=artifact.name,
        artifact_sha256=sha256(artifact.read_bytes()).hexdigest(),
        artifact_size_bytes=artifact.stat().st_size,
        component_graph_sha256="a" * 64,
        minimum_memory_schema=0,
        maximum_memory_schema=99,
        created_at_utc=now.isoformat(),
        expires_at_utc=(now + timedelta(hours=1)).isoformat(),
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json")), encoding="utf-8")
    signature = tmp_path / "manifest.sig"
    sign_manifest(SimpleNamespace(
        private_key=args.primary_key,
        passphrase_file=args.passphrase_file,
        trust_policy=args.trust_policy,
        manifest=manifest_path,
        signature=signature,
    ))
    assert verify_release_artifact(
        artifact_path=artifact,
        manifest_path=manifest_path,
        signature_path=signature,
        trust_policy_path=args.trust_policy,
    ).release_id == "synthetic-1"
    assert len(base64.b64decode(signature.read_text().strip(), validate=True)) == 64


def test_encrypted_key_never_serializes_as_unprotected_pkcs8(tmp_path: Path) -> None:
    args = _generated(tmp_path)
    blob = args.primary_key.read_bytes()
    assert b"BEGIN " + b"ENCRYPTED PRIVATE KEY" in blob
    assert b"BEGIN " + b"PRIVATE KEY" not in blob
    passphrase = args.passphrase_file.read_bytes().strip()
    recovered = serialization.load_pem_private_key(blob, password=passphrase)
    assert recovered is not None


def test_full_disposable_trust_ceremony_fails_closed(tmp_path: Path) -> None:
    args = _generated(tmp_path)
    prove_ceremony(SimpleNamespace(
        key_id=args.key_id,
        private_key=args.primary_key,
        passphrase_file=args.passphrase_file,
        trust_policy=args.trust_policy,
    ))


def test_wrong_secret_and_named_retired_authority_fail_closed(tmp_path: Path) -> None:
    retired = _generated(tmp_path / "retired")
    successor = _generated(tmp_path / "successor")
    prove_wrong_secret_refusal(SimpleNamespace(
        key_id=successor.key_id,
        private_key=successor.recovery_copy[0],
        encrypted_removable_copy=True,
    ))
    prove_retired_key_rejection(SimpleNamespace(
        retired_key_id=retired.key_id,
        retired_private_key=retired.primary_key,
        retired_passphrase_file=retired.passphrase_file,
        successor_trust_policy=successor.trust_policy,
    ))


def test_hygiene_audit_accepts_clean_surface_and_rejects_actual_custody_material(
    tmp_path: Path,
) -> None:
    args = _generated(tmp_path / "custody")
    surface = tmp_path / "release-surface"
    surface.mkdir()
    (surface / "README.txt").write_text("public release material\n", encoding="utf-8")
    audit = SimpleNamespace(
        private_key=[args.primary_key, *args.recovery_copy],
        passphrase_file=args.passphrase_file,
        git_root=None,
        scan_root=[surface],
    )
    hygiene_audit(audit)

    (surface / "accidental-release-payload.bin").write_bytes(args.primary_key.read_bytes())
    with pytest.raises(SigningCeremonyError, match="Private signing material"):
        hygiene_audit(audit)


def test_signed_candidate_family_requires_exact_directory_and_hashes(tmp_path: Path) -> None:
    args = _generated(tmp_path / "trust")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    primary = artifacts / "elysia-1.0.0-source.tar.gz"
    companion = artifacts / "elysia-codev-1.0.0.vsix"
    primary.write_bytes(b"exact source bytes")
    companion.write_bytes(b"exact Codev bytes")
    inventory = {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in (primary, companion)
    }
    now = datetime.now(UTC)
    manifest = ReleaseArtifactManifest(
        contract_version="elysia-release-artifact-manifest-1.0",
        publisher=args.publisher,
        product="Elysia",
        release_id="elysia-v1.0.0-pass10dv-test",
        version="1.0.0",
        channel="stable",
        signing_key_id=args.key_id,
        artifact_filename=primary.name,
        artifact_sha256=inventory[primary.name],
        artifact_size_bytes=primary.stat().st_size,
        component_graph_sha256="b" * 64,
        minimum_memory_schema=0,
        maximum_memory_schema=99,
        created_at_utc=now.isoformat(),
        expires_at_utc=(now + timedelta(hours=1)).isoformat(),
        file_inventory=inventory,
    )
    manifest_path = tmp_path / "candidate.json"
    signature_path = tmp_path / "candidate.sig"
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json")), encoding="utf-8"
    )
    sign_manifest(SimpleNamespace(
        private_key=args.primary_key,
        passphrase_file=args.passphrase_file,
        trust_policy=args.trust_policy,
        manifest=manifest_path,
        signature=signature_path,
    ))

    assert verify_family(
        artifacts_dir=artifacts,
        manifest_path=manifest_path,
        signature_path=signature_path,
        trust_policy_path=args.trust_policy,
    )["artifact_count"] == 2

    (artifacts / "unexpected.bin").write_bytes(b"not signed")
    with pytest.raises(ReleaseTrustError, match="differs from the signed family inventory"):
        verify_family(
            artifacts_dir=artifacts,
            manifest_path=manifest_path,
            signature_path=signature_path,
            trust_policy_path=args.trust_policy,
        )


def test_candidate_family_manifest_rejects_unsafe_names_and_unbound_primary() -> None:
    now = datetime.now(UTC)
    common = dict(
        contract_version="elysia-release-artifact-manifest-1.0",
        publisher="EcoSyneva Commons LLC",
        product="Elysia",
        release_id="elysia-v1.0.0-pass10dv-test",
        version="1.0.0",
        channel="stable",
        signing_key_id="synthetic-production-trust",
        artifact_filename="elysia-source.tar.gz",
        artifact_sha256="a" * 64,
        artifact_size_bytes=1,
        component_graph_sha256="b" * 64,
        minimum_memory_schema=0,
        maximum_memory_schema=99,
        created_at_utc=now.isoformat(),
        expires_at_utc=(now + timedelta(hours=1)).isoformat(),
    )
    with pytest.raises(ValueError, match="unsafe"):
        ReleaseArtifactManifest(**common, file_inventory={"../escape": "a" * 64})
    with pytest.raises(ValueError, match="unsafe"):
        ReleaseArtifactManifest(**common, file_inventory={"bin//elysia": "a" * 64})
    payload_manifest = ReleaseArtifactManifest(
        **common,
        file_inventory={"bin/elysia": "a" * 64},
    )
    assert payload_manifest.file_inventory == {"bin/elysia": "a" * 64}
    with pytest.raises(ValueError, match="not identically bound"):
        ReleaseArtifactManifest(
            **common,
            file_inventory={"elysia-source.tar.gz": "c" * 64},
        )
