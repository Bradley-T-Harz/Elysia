from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest
import yaml

from app.install.release_trust import (
    ReleaseArtifactManifest,
    ReleaseTrustTransition,
    ReleaseTrustError,
    UpdateTrustPolicy,
    public_trust_state,
    revoked_trust_policy,
    verify_release_artifact,
    verify_trust_transition,
)


def _fixture(root: Path, *, expired: bool = False) -> tuple[Path, Path, Path, Path]:
    artifact = root / "elysia-test.tar"
    artifact.write_bytes(b"exact disposable release bytes")
    now = datetime.now(UTC)
    manifest = ReleaseArtifactManifest(
        contract_version="elysia-release-artifact-manifest-1.0",
        publisher="EcoSyneva Commons LLC",
        product="Elysia",
        release_id="test-1",
        version="0.1.0",
        channel="candidate",
        signing_key_id="disposable-test-key",
        artifact_filename=artifact.name,
        artifact_sha256=sha256(artifact.read_bytes()).hexdigest(),
        artifact_size_bytes=artifact.stat().st_size,
        component_graph_sha256="a" * 64,
        minimum_memory_schema=0,
        maximum_memory_schema=99,
        created_at_utc=(now - timedelta(minutes=1)).isoformat(),
        expires_at_utc=(now - timedelta(minutes=1) if expired else now + timedelta(hours=1)).isoformat(),
        file_inventory={},
    )
    manifest_path = root / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json")), encoding="utf-8")
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signature_path = root / "release-manifest.sig"
    signature_path.write_text(
        base64.b64encode(private.sign(manifest.canonical_bytes())).decode("ascii"),
        encoding="ascii",
    )
    policy_path = root / "trust.yaml"
    policy_path.write_text(
        yaml.safe_dump({
            "version": 1,
            "contract_version": "elysia-update-trust-1.0",
            "state": "active",
            "algorithm": "ed25519",
            "publisher": "EcoSyneva Commons LLC",
            "key_id": "disposable-test-key",
            "public_key_base64": base64.b64encode(public).decode("ascii"),
            "not_before_utc": (now - timedelta(hours=1)).isoformat(),
            "not_after_utc": (now + timedelta(hours=1)).isoformat(),
            "channel": "candidate",
            "notes": ["Disposable test key only."],
        }),
        encoding="utf-8",
    )
    return artifact, manifest_path, signature_path, policy_path


def test_valid_signed_candidate_is_accepted_without_private_key_material(tmp_path: Path) -> None:
    artifact, manifest, signature, policy = _fixture(tmp_path)
    result = verify_release_artifact(
        artifact_path=artifact,
        manifest_path=manifest,
        signature_path=signature,
        trust_policy_path=policy,
    )
    assert result.release_id == "test-1"
    assert public_trust_state(policy)["verification_ready"] is True
    assert public_trust_state(policy)["private_key_present"] is False
    assert public_trust_state(policy)["mutation_authority"] == "local_admin_explicit"
    assert public_trust_state(policy)["silent_update_allowed"] is False


@pytest.mark.parametrize(
    "mutation",
    ["artifact", "signature", "wrong_key", "wrong_key_id", "missing_signature", "expired", "revoked"],
)
def test_modified_unsigned_expired_or_wrong_key_candidate_is_rejected(
    tmp_path: Path, mutation: str
) -> None:
    artifact, manifest, signature, policy = _fixture(tmp_path, expired=mutation == "expired")
    if mutation == "artifact":
        artifact.write_bytes(b"modified")
    elif mutation == "signature":
        signature.write_text(base64.b64encode(b"x" * 64).decode("ascii"), encoding="ascii")
    elif mutation == "wrong_key":
        payload = yaml.safe_load(policy.read_text(encoding="utf-8"))
        wrong = Ed25519PrivateKey.generate().public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        payload["public_key_base64"] = base64.b64encode(wrong).decode("ascii")
        policy.write_text(yaml.safe_dump(payload), encoding="utf-8")
    elif mutation == "wrong_key_id":
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["signing_key_id"] = "unknown-signer"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
    elif mutation == "missing_signature":
        signature.unlink()
    elif mutation == "revoked":
        payload = yaml.safe_load(policy.read_text(encoding="utf-8"))
        payload.update({
            "state": "revoked",
            "revoked_at_utc": datetime.now(UTC).isoformat(),
            "revocation_reason": "Synthetic compromise proof.",
        })
        policy.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ReleaseTrustError):
        verify_release_artifact(
            artifact_path=artifact,
            manifest_path=manifest,
            signature_path=signature,
            trust_policy_path=policy,
        )


def test_tracked_example_has_no_key_and_grants_no_update_authority() -> None:
    state = public_trust_state(Path("config/install/update_trust.example.yaml"))
    assert state["state"] == "operator_key_decision_required"
    assert state["verification_ready"] is False
    assert state["private_key_present"] is False
    assert state["silent_update_allowed"] is False


def test_trust_policy_refuses_silent_update_or_malformed_public_key() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="Silent updater mutation"):
        UpdateTrustPolicy(
            version=1,
            contract_version="elysia-update-trust-1.0",
            state="active",
            algorithm="ed25519",
            publisher="EcoSyneva Commons LLC",
            key_id="synthetic",
            public_key_base64=base64.b64encode(b"k" * 32).decode("ascii"),
            not_before_utc=now.isoformat(),
            not_after_utc=(now + timedelta(days=1)).isoformat(),
            channel="stable",
            silent_update_allowed=True,
        )
    with pytest.raises(ReleaseTrustError, match="length"):
        UpdateTrustPolicy(
            version=1,
            contract_version="elysia-update-trust-1.0",
            state="active",
            algorithm="ed25519",
            publisher="EcoSyneva Commons LLC",
            key_id="synthetic",
            public_key_base64=base64.b64encode(b"short").decode("ascii"),
            not_before_utc=now.isoformat(),
            not_after_utc=(now + timedelta(days=1)).isoformat(),
            channel="stable",
        )


def test_old_key_authorizes_exact_rotation_and_revocation_fails_closed(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    old_private = Ed25519PrivateKey.generate()
    new_private = Ed25519PrivateKey.generate()
    old_public = old_private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    new_public = new_private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    old_policy = UpdateTrustPolicy(
        version=1,
        contract_version="elysia-update-trust-1.0",
        state="active",
        algorithm="ed25519",
        publisher="EcoSyneva Commons LLC",
        key_id="old-stable-key",
        public_key_base64=base64.b64encode(old_public).decode("ascii"),
        not_before_utc=(now - timedelta(days=1)).isoformat(),
        not_after_utc=(now + timedelta(days=365)).isoformat(),
        channel="stable",
    )
    old_policy_path = tmp_path / "old-trust.yaml"
    old_policy_path.write_text(yaml.safe_dump(old_policy.model_dump(mode="json")), encoding="utf-8")
    transition = ReleaseTrustTransition(
        contract_version="elysia-update-trust-transition-1.0",
        transition_id="rotation-proof-1",
        publisher="EcoSyneva Commons LLC",
        channel="stable",
        previous_key_id="old-stable-key",
        new_key_id="new-stable-key",
        new_public_key_base64=base64.b64encode(new_public).decode("ascii"),
        created_at_utc=now.isoformat(),
        activates_at_utc=(now + timedelta(minutes=1)).isoformat(),
        new_not_after_utc=(now + timedelta(days=730)).isoformat(),
        transition_expires_at_utc=(now + timedelta(days=30)).isoformat(),
        reason="Scheduled bounded updater trust rotation.",
    )
    transition_path = tmp_path / "transition.json"
    transition_path.write_text(json.dumps(transition.model_dump(mode="json")), encoding="utf-8")
    transition_signature = tmp_path / "transition.sig"
    transition_signature.write_text(
        base64.b64encode(old_private.sign(transition.canonical_bytes())).decode("ascii"),
        encoding="ascii",
    )
    successor = verify_trust_transition(
        transition_path=transition_path,
        signature_path=transition_signature,
        current_trust_policy_path=old_policy_path,
        now=now,
    )
    assert successor.key_id == "new-stable-key"
    assert successor.supersedes_key_id == "old-stable-key"
    assert successor.silent_update_allowed is False

    revoked = revoked_trust_policy(
        old_policy,
        reason="Synthetic compromise exercise.",
        revoked_at_utc=now.isoformat(),
    )
    revoked_path = tmp_path / "revoked.yaml"
    revoked_path.write_text(yaml.safe_dump(revoked.model_dump(mode="json")), encoding="utf-8")
    revoked_candidate = tmp_path / "revoked-candidate"
    revoked_candidate.mkdir()
    artifact, manifest, signature, _ = _fixture(revoked_candidate)
    with pytest.raises(ReleaseTrustError, match="No approved active"):
        verify_release_artifact(
            artifact_path=artifact,
            manifest_path=manifest,
            signature_path=signature,
            trust_policy_path=revoked_path,
        )


def test_tampered_or_wrong_predecessor_transition_is_rejected(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    predecessor = Ed25519PrivateKey.generate()
    successor = Ed25519PrivateKey.generate()
    predecessor_public = predecessor.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    successor_public = successor.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    policy_path = tmp_path / "trust.yaml"
    policy_path.write_text(yaml.safe_dump({
        "version": 1,
        "contract_version": "elysia-update-trust-1.0",
        "state": "active",
        "algorithm": "ed25519",
        "publisher": "EcoSyneva Commons LLC",
        "key_id": "predecessor",
        "public_key_base64": base64.b64encode(predecessor_public).decode("ascii"),
        "not_before_utc": (now - timedelta(days=1)).isoformat(),
        "not_after_utc": (now + timedelta(days=365)).isoformat(),
        "channel": "stable",
    }), encoding="utf-8")
    transition = ReleaseTrustTransition(
        contract_version="elysia-update-trust-transition-1.0",
        transition_id="rotation-proof-2",
        publisher="EcoSyneva Commons LLC",
        channel="stable",
        previous_key_id="predecessor",
        new_key_id="successor",
        new_public_key_base64=base64.b64encode(successor_public).decode("ascii"),
        created_at_utc=now.isoformat(),
        activates_at_utc=(now + timedelta(minutes=1)).isoformat(),
        new_not_after_utc=(now + timedelta(days=730)).isoformat(),
        transition_expires_at_utc=(now + timedelta(days=30)).isoformat(),
        reason="Scheduled bounded updater trust rotation.",
    )
    transition_path = tmp_path / "transition.json"
    transition_path.write_text(json.dumps(transition.model_dump(mode="json")), encoding="utf-8")
    signature_path = tmp_path / "transition.sig"
    signature_path.write_text(
        base64.b64encode(Ed25519PrivateKey.generate().sign(transition.canonical_bytes())).decode("ascii"),
        encoding="ascii",
    )
    with pytest.raises(ReleaseTrustError, match="signature is invalid"):
        verify_trust_transition(
            transition_path=transition_path,
            signature_path=signature_path,
            current_trust_policy_path=policy_path,
            now=now,
        )
