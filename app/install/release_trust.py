"""Exact release-manifest and Ed25519 updater verification.

Only public verification material is consumed here. Production private-key
custody remains operator-controlled, and final release signing remains Pass V.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator
import yaml


TRUST_CONTRACT_VERSION = "elysia-update-trust-1.0"
RELEASE_MANIFEST_CONTRACT_VERSION = "elysia-release-artifact-manifest-1.0"
TRUST_TRANSITION_CONTRACT_VERSION = "elysia-update-trust-transition-1.0"


class ReleaseTrustError(RuntimeError):
    """A release identity, key, signature, or artifact failed closed."""


class ReleaseArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    contract_version: str = Field(pattern=r"^elysia-release-artifact-manifest-1\.0$")
    publisher: str = Field(min_length=1, max_length=200)
    product: str = Field(pattern=r"^Elysia$")
    release_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")
    channel: str = Field(pattern=r"^(stable|candidate|development)$")
    signing_key_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,199}$")
    artifact_filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,255}$")
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact_size_bytes: int = Field(gt=0)
    component_graph_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    minimum_memory_schema: int = Field(ge=0)
    maximum_memory_schema: int = Field(ge=0)
    memory_schema_target: int | None = Field(default=None, ge=0)
    memory_migration_ids: list[str] = Field(default_factory=list, max_length=100)
    component_changes: list[str] = Field(default_factory=list, max_length=500)
    created_at_utc: str
    expires_at_utc: str
    file_inventory: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_release_plan(self) -> "ReleaseArtifactManifest":
        target = self.memory_schema_target
        if target is not None and not (
            self.minimum_memory_schema <= target <= self.maximum_memory_schema
        ):
            raise ValueError("The target memory schema is outside the signed compatibility range.")
        if target is None and self.memory_migration_ids:
            raise ValueError("Memory migration identifiers require an exact target schema.")
        for migration_id in self.memory_migration_ids:
            if not migration_id or any(
                character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._+-"
                for character in migration_id
            ):
                raise ValueError("A memory migration identifier is unsafe.")
        if len(self.file_inventory) > 500:
            raise ValueError("The signed artifact-family inventory exceeds its bound.")
        for filename, digest in self.file_inventory.items():
            segments = filename.split("/")
            if (
                not filename
                or len(filename) > 1024
                or filename.startswith("/")
                or "\\" in filename
                or any(
                    not segment
                    or segment in {".", ".."}
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,255}", segment)
                    for segment in segments
                )
            ):
                raise ValueError("An artifact-family filename is unsafe.")
            if not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError("An artifact-family digest is invalid.")
        if self.artifact_filename in self.file_inventory and (
            self.file_inventory.get(self.artifact_filename) != self.artifact_sha256
        ):
            raise ValueError("The primary artifact is not identically bound in the family inventory.")
        return self

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")


class UpdateTrustPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    version: int = Field(pattern=None)
    contract_version: str = Field(pattern=r"^elysia-update-trust-1\.0$")
    state: str = Field(pattern=r"^(active|operator_key_decision_required|revoked)$")
    algorithm: str = Field(pattern=r"^ed25519$")
    publisher: str = Field(min_length=1, max_length=200)
    key_id: str | None = Field(default=None, max_length=200)
    public_key_base64: str | None = Field(default=None, max_length=200)
    not_before_utc: str | None = None
    not_after_utc: str | None = None
    channel: str = Field(pattern=r"^(stable|candidate|development)$")
    mutation_authority: str = Field(default="local_admin_explicit", pattern=r"^local_admin_explicit$")
    silent_update_allowed: bool = False
    supersedes_key_id: str | None = Field(default=None, max_length=200)
    revoked_at_utc: str | None = None
    revocation_reason: str | None = Field(default=None, max_length=500)
    notes: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_trust_state(self) -> "UpdateTrustPolicy":
        if self.silent_update_allowed:
            raise ValueError("Silent updater mutation is constitutionally unavailable.")
        if self.state == "active":
            if not self.key_id or not self.public_key_base64 or not self.not_before_utc:
                raise ValueError("Active updater trust requires an exact key identity and activation time.")
            if self.revoked_at_utc or self.revocation_reason:
                raise ValueError("Active updater trust cannot carry revocation state.")
        elif self.state == "operator_key_decision_required":
            if self.key_id or self.public_key_base64 or self.revoked_at_utc:
                raise ValueError("Pending operator trust cannot grant key authority.")
        elif self.state == "revoked":
            if not self.key_id or not self.public_key_base64:
                raise ValueError("Revoked trust retains the exact public identity for refusal/audit.")
            if not self.revoked_at_utc or not self.revocation_reason:
                raise ValueError("Revoked trust requires time and reason.")
        if self.public_key_base64:
            _decode_public_key(self.public_key_base64)
        if self.not_before_utc:
            start = _parse_utc(self.not_before_utc)
            if self.not_after_utc and start >= _parse_utc(self.not_after_utc):
                raise ValueError("Updater trust validity has no positive interval.")
        return self


class ReleaseTrustTransition(BaseModel):
    """Old-key-authorized transition to one exact successor trust root."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    contract_version: str = Field(pattern=r"^elysia-update-trust-transition-1\.0$")
    transition_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
    publisher: str = Field(min_length=1, max_length=200)
    channel: str = Field(pattern=r"^(stable|candidate|development)$")
    previous_key_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,199}$")
    new_key_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,199}$")
    new_public_key_base64: str = Field(min_length=1, max_length=200)
    created_at_utc: str
    activates_at_utc: str
    new_not_after_utc: str
    transition_expires_at_utc: str
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_transition(self) -> "ReleaseTrustTransition":
        if self.previous_key_id == self.new_key_id:
            raise ValueError("A trust transition must name a distinct successor key.")
        created = _parse_utc(self.created_at_utc)
        activates = _parse_utc(self.activates_at_utc)
        successor_expiry = _parse_utc(self.new_not_after_utc)
        transition_expiry = _parse_utc(self.transition_expires_at_utc)
        if activates < created or successor_expiry <= activates or transition_expiry <= created:
            raise ValueError("The trust transition time bounds are invalid.")
        _decode_public_key(self.new_public_key_base64)
        return self

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReleaseTrustError("A release trust timestamp is invalid.") from exc
    if parsed.tzinfo is None:
        raise ReleaseTrustError("A release trust timestamp must include UTC authority.")
    return parsed.astimezone(UTC)


def _decode_public_key(value: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeError) as exc:
        raise ReleaseTrustError("The updater public key encoding is invalid.") from exc
    if len(decoded) != 32:
        raise ReleaseTrustError("The updater public key length is invalid.")
    return decoded


def _safe_local_file(path: Path, description: str, *, max_bytes: int = 2_000_000) -> Path:
    try:
        stat = path.lstat()
    except OSError as exc:
        raise ReleaseTrustError(f"The {description} is unavailable.") from exc
    if path.is_symlink() or not path.is_file() or stat.st_size > max_bytes:
        raise ReleaseTrustError(f"The {description} is not a safe bounded local file.")
    return path


def _read_signature(path: Path) -> bytes:
    _safe_local_file(path, "detached release signature")
    try:
        signature = base64.b64decode(path.read_text(encoding="ascii").strip(), validate=True)
    except (OSError, ValueError, UnicodeError) as exc:
        raise ReleaseTrustError("The detached release signature encoding is invalid.") from exc
    if len(signature) != 64:
        raise ReleaseTrustError("The detached release signature length is invalid.")
    return signature


def load_trust_policy(path: Path) -> UpdateTrustPolicy:
    try:
        _safe_local_file(path, "updater trust policy")
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        policy = UpdateTrustPolicy.model_validate(payload)
    except Exception as exc:
        raise ReleaseTrustError("The updater trust policy is invalid.") from exc
    if policy.version != 1:
        raise ReleaseTrustError("The updater trust policy version is unsupported.")
    return policy


def load_release_manifest(path: Path) -> ReleaseArtifactManifest:
    try:
        _safe_local_file(path, "release artifact manifest")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ReleaseArtifactManifest.model_validate(payload)
    except Exception as exc:
        raise ReleaseTrustError("The release artifact manifest is invalid.") from exc


def verify_release_artifact(
    *,
    artifact_path: Path,
    manifest_path: Path,
    signature_path: Path,
    trust_policy_path: Path,
    now: datetime | None = None,
) -> ReleaseArtifactManifest:
    _safe_local_file(artifact_path, "release artifact", max_bytes=64 * 1024 * 1024 * 1024)
    _safe_local_file(manifest_path, "release artifact manifest")
    _safe_local_file(signature_path, "detached release signature")
    _safe_local_file(trust_policy_path, "updater trust policy")
    policy = load_trust_policy(trust_policy_path)
    if policy.state != "active" or not policy.key_id or not policy.public_key_base64:
        raise ReleaseTrustError("No approved active updater verification key is configured.")
    manifest = load_release_manifest(manifest_path)
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if manifest.publisher != policy.publisher or manifest.channel != policy.channel:
        raise ReleaseTrustError("The release publisher or channel does not match updater trust.")
    if manifest.signing_key_id != policy.key_id:
        raise ReleaseTrustError("The release signing key identity does not match updater trust.")
    if policy.not_before_utc and current < _parse_utc(policy.not_before_utc):
        raise ReleaseTrustError("The updater verification key is not active yet.")
    if policy.not_after_utc and current > _parse_utc(policy.not_after_utc):
        raise ReleaseTrustError("The updater verification key expired.")
    if current > _parse_utc(manifest.expires_at_utc):
        raise ReleaseTrustError("The signed release manifest expired.")
    if manifest.minimum_memory_schema > manifest.maximum_memory_schema:
        raise ReleaseTrustError("The signed memory compatibility range is invalid.")
    try:
        Ed25519PublicKey.from_public_bytes(_decode_public_key(policy.public_key_base64)).verify(
            _read_signature(signature_path), manifest.canonical_bytes()
        )
    except (ValueError, InvalidSignature, UnicodeError) as exc:
        raise ReleaseTrustError("The release signature is invalid or uses the wrong key.") from exc
    if artifact_path.name != manifest.artifact_filename:
        raise ReleaseTrustError("The artifact filename does not match the signed manifest.")
    if artifact_path.stat().st_size != manifest.artifact_size_bytes:
        raise ReleaseTrustError("The artifact size does not match the signed manifest.")
    actual_sha = sha256(artifact_path.read_bytes()).hexdigest()
    if actual_sha != manifest.artifact_sha256:
        raise ReleaseTrustError("The artifact hash does not match the signed manifest.")
    return manifest


def load_trust_transition(path: Path) -> ReleaseTrustTransition:
    try:
        _safe_local_file(path, "updater trust transition")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ReleaseTrustTransition.model_validate(payload)
    except ReleaseTrustError:
        raise
    except Exception as exc:
        raise ReleaseTrustError("The updater trust transition is invalid.") from exc


def verify_trust_transition(
    *,
    transition_path: Path,
    signature_path: Path,
    current_trust_policy_path: Path,
    now: datetime | None = None,
) -> UpdateTrustPolicy:
    """Verify an old-key-signed successor and return inactive-on-disk policy bytes.

    The caller may package the returned public policy only through a separately
    authorized, old-key-verified release. This helper never writes trust state.
    """

    policy = load_trust_policy(current_trust_policy_path)
    if policy.state != "active" or not policy.key_id or not policy.public_key_base64:
        raise ReleaseTrustError("Trust rotation requires one approved active predecessor key.")
    transition = load_trust_transition(transition_path)
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if current > _parse_utc(transition.transition_expires_at_utc):
        raise ReleaseTrustError("The updater trust transition expired.")
    if (
        transition.publisher != policy.publisher
        or transition.channel != policy.channel
        or transition.previous_key_id != policy.key_id
    ):
        raise ReleaseTrustError("The updater trust transition is not bound to current authority.")
    try:
        Ed25519PublicKey.from_public_bytes(_decode_public_key(policy.public_key_base64)).verify(
            _read_signature(signature_path), transition.canonical_bytes()
        )
    except InvalidSignature as exc:
        raise ReleaseTrustError("The updater trust transition signature is invalid.") from exc
    return UpdateTrustPolicy(
        version=policy.version,
        contract_version=policy.contract_version,
        state="active",
        algorithm="ed25519",
        publisher=policy.publisher,
        key_id=transition.new_key_id,
        public_key_base64=transition.new_public_key_base64,
        not_before_utc=transition.activates_at_utc,
        not_after_utc=transition.new_not_after_utc,
        channel=policy.channel,
        mutation_authority="local_admin_explicit",
        silent_update_allowed=False,
        supersedes_key_id=policy.key_id,
        notes=[
            f"Old-key-authorized transition {transition.transition_id}.",
            "Installation mutation remains Local-Admin initiated and explicitly approved.",
        ],
    )


def revoked_trust_policy(
    policy: UpdateTrustPolicy,
    *,
    reason: str,
    revoked_at_utc: str,
) -> UpdateTrustPolicy:
    """Build a fail-closed public revocation record without private authority."""

    if policy.state != "active" or not reason.strip():
        raise ReleaseTrustError("Only an active exact trust identity can be revoked.")
    return policy.model_copy(update={
        "state": "revoked",
        "revoked_at_utc": _parse_utc(revoked_at_utc).isoformat().replace("+00:00", "Z"),
        "revocation_reason": reason.strip(),
        "notes": [*policy.notes, "This key no longer authorizes future updater material."],
    })


def public_trust_state(path: Path) -> dict[str, Any]:
    try:
        policy = load_trust_policy(path)
    except ReleaseTrustError:
        return {
            "state": "invalid",
            "verification_ready": False,
            "private_key_present": False,
            "raw_paths_exposed": False,
        }
    return {
        "state": policy.state,
        "algorithm": policy.algorithm,
        "publisher": policy.publisher,
        "key_id": policy.key_id,
        "channel": policy.channel,
        "mutation_authority": policy.mutation_authority,
        "silent_update_allowed": policy.silent_update_allowed,
        "supersedes_key_id": policy.supersedes_key_id,
        "revoked_at_utc": policy.revoked_at_utc,
        "verification_ready": bool(
            policy.state == "active" and policy.key_id and policy.public_key_base64
        ),
        "private_key_present": False,
        "raw_paths_exposed": False,
    }


__all__ = (
    "RELEASE_MANIFEST_CONTRACT_VERSION",
    "ReleaseArtifactManifest",
    "ReleaseTrustTransition",
    "ReleaseTrustError",
    "TRUST_CONTRACT_VERSION",
    "TRUST_TRANSITION_CONTRACT_VERSION",
    "UpdateTrustPolicy",
    "load_release_manifest",
    "load_trust_transition",
    "load_trust_policy",
    "public_trust_state",
    "revoked_trust_policy",
    "verify_release_artifact",
    "verify_trust_transition",
)
