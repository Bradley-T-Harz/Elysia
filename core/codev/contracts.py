"""Canonical multi-client contracts; product and legacy API versions stay 1.0.0."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

CLIENT_CONTRACT = "codev-client-1"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class Capability(Contract):
    id: str
    available: bool
    requires: list[str] = Field(default_factory=list)
    reason: str | None = None


class Installation(Contract):
    contract_version: Literal["codev-client-1"] = CLIENT_CONTRACT
    state: Literal["absent", "installed_unavailable", "installed_ready", "incompatible", "degraded"]
    installed: bool = False
    usable: bool = False
    version: str | None = None
    expected_version: Literal["1.0.0"] = "1.0.0"
    contract_versions: list[str] = Field(default_factory=list)
    source: Literal["none", "legacy_install_receipt", "installed_core_manifest"] = "none"
    installation_state: Literal["absent", "installed", "incompatible"] = "absent"
    runtime_state: Literal["disconnected", "ready", "degraded"] = "disconnected"
    session_state: Literal["approval_needed", "ready"] = "approval_needed"
    runtime_instance_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{48}$")
    installation_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    capabilities: list[Capability] = Field(default_factory=list)
    note: str
    raw_paths_exposed: Literal[False] = False


class ClientLifecycle(Contract):
    """Independent axes; pairing and installation never grant a workspace."""
    installation: Installation
    workspace_authority: Literal["no_workspace", "workspace_read", "approval_needed", "executing", "revoked"] = "no_workspace"
    network_pairing: Literal["disconnected", "connected", "revoked"] = "disconnected"


class CorePackageManifest(Contract):
    product: Literal["codev-core"] = "codev-core"
    version: Literal["1.0.0"] = "1.0.0"
    contract: Literal["codev-core-1"] = "codev-core-1"
    runtime_contract: Literal["elysia-local-runtime-1"] = "elysia-local-runtime-1"
    architecture: Literal["amd64"] = "amd64"
    core_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    adapter_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class NativeRuntimeIdentity(Contract):
    contract: Literal["elysia-local-runtime-1"] = "elysia-local-runtime-1"
    product_version: Literal["1.0.0"] = "1.0.0"
    pid: int = Field(ge=2)
    uid: int = Field(ge=0)
    instance_id: str = Field(pattern=r"^[a-f0-9]{48}$")
    transport: Literal["unix"] = "unix"
    boot_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    process_start_ticks: str = Field(pattern=r"^[0-9]+$")
    executable_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


# Ownership fields are assigned by trusted adapters, never accepted as authority
# merely because they appeared in a client payload.
class Actor(Contract):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False, frozen=True)
    local_profile_id: str = Field(min_length=1, max_length=128)
    client_id: str = Field(min_length=1, max_length=128)
    client_kind: Literal["native", "browser", "vscode_compatibility"]
    online_account_id: str | None = None
    origin: str | None = None
    surface: Literal["local", "marketplace", "forge"]

    @model_validator(mode="after")
    def validate_client_binding(self):
        if self.client_kind == "browser":
            if not self.online_account_id or self.origin not in {"https://elysiaecobotics.com", "https://www.elysiaecobotics.com"} or self.surface == "local":
                raise ValueError("browser_actor_requires_exact_site_account_and_surface")
        elif self.surface != "local" or self.origin is not None:
            raise ValueError("native_actor_binding_mismatch")
        return self


class WorkspaceFile(Contract):
    path: str = Field(min_length=1, max_length=512)
    content_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    availability: Literal["text", "binary", "oversized", "metadata_only", "excluded", "missing"]
    text: str | None = Field(default=None, max_length=131072)
    provenance: Literal["local_file", "intake", "editor", "codev_patch", "remote_draft", "recovery"]


class WorkspaceDescriptor(Contract):
    contract_version: Literal["codev-workspace-1"] = "codev-workspace-1"
    workspace_id: str = Field(min_length=1, max_length=128)
    workspace_type: Literal["local_repository", "selected_local_files", "marketplace_browser", "forge_browser", "remote_draft_snapshot"]
    label: str = Field(min_length=1, max_length=120)
    owner: Actor
    base_revision: int = Field(ge=0)
    current_revision: int = Field(ge=0)
    base_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    files: list[WorkspaceFile] = Field(default_factory=list, max_length=2000)
    allowed_operations: list[str] = Field(default_factory=list)
    denied_classes: list[str] = Field(default_factory=list)
    grant_epoch: int = Field(default=0, ge=0)
    dirty: bool = False
    validation_revision: int | None = None
    package_revision: int | None = None


class WorkspaceGrant(Contract):
    grant_id: str
    workspace_id: str
    actor: Actor
    epoch: int = Field(ge=1)
    scopes: list[Literal["metadata", "read", "propose", "apply", "command"]] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list, max_length=40)
    command_ids: list[str] = Field(default_factory=list, max_length=10)
    network_destinations: list[str] = Field(default_factory=list, max_length=10)
    expires_at: str
    revoked: bool = False


class FileChange(Contract):
    path: str = Field(min_length=1, max_length=512)
    base_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    new_text: str = Field(max_length=131072)
    new_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    diff: str = Field(max_length=262144)


class ChangePlan(Contract):
    plan_id: str
    workspace_id: str
    actor: Actor
    base_revision: int = Field(ge=0)
    workspace_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    grant_epoch: int = Field(ge=1)
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    summary: str = Field(max_length=2000)
    changes: list[FileChange] = Field(default_factory=list, max_length=20)
    command_id: str | None = None
    command_argv: list[str] = Field(default_factory=list, max_length=30)
    cwd_label: str
    network_policy: Literal["none"] = "none"
    expected_checks: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    expires_at: str
    recovery_note: str


class ExactApproval(Contract):
    approval_id: str
    actor: Actor
    workspace_id: str
    revision: int = Field(ge=0)
    workspace_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    grant_epoch: int = Field(ge=1)
    operation: Literal["patch_apply", "command_run", "browser_patch", "remote_save"]
    files: list[str] = Field(default_factory=list)
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    command_argv: list[str] = Field(default_factory=list)
    cwd_label: str
    network_policy: Literal["none", "approved_remote_save"] = "none"
    expires_at: str
    one_time: Literal[True] = True
    consumed: bool = False


class ResultArtifact(Contract):
    artifact_id: str
    label: str
    content_type: str
    relative_path: str | None = None


class OperationReceipt(Contract):
    contract_version: Literal["codev-receipt-1"] = "codev-receipt-1"
    operation_id: str
    request_id: str
    workspace_id: str | None = None
    status: Literal["proposed", "approval_required", "approved", "queued", "running", "completed", "failed", "cancelled", "partial", "blocked", "conflict", "verification_required"]
    summary: str
    base_revision: int | None = None
    resulting_revision: int | None = None
    files_inspected: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    commands_run: list[list[str]] = Field(default_factory=list)
    tests_run: list[str] = Field(default_factory=list)
    network_used: bool = False
    outward_destination: str | None = None
    artifacts: list[ResultArtifact] = Field(default_factory=list)
    recovery_note: str | None = None
    verification: Literal["not_run", "passed", "failed", "partial", "required"] = "not_run"
    audit_written: bool = False
    warnings: list[str] = Field(default_factory=list)
    created_at: str


class BrowserPublicKey(Contract):
    kty: Literal["EC"] = "EC"
    crv: Literal["P-256"] = "P-256"
    x: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    y: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class PairingIntent(Contract):
    contract_version: Literal["codev-pairing-1"] = "codev-pairing-1"
    intent_id: str
    online_account_id: str
    account_label: str = Field(max_length=200)
    origin: Literal["https://elysiaecobotics.com", "https://www.elysiaecobotics.com"]
    surface: Literal["marketplace", "forge"]
    browser_session_id: str = Field(min_length=32, max_length=128)
    browser_public_key: BrowserPublicKey
    expires_at: str
    status: Literal["pending", "native_approved", "paired", "denied", "expired", "revoked"] = "pending"


class PairingSession(Contract):
    contract_version: Literal["codev-pairing-1"] = "codev-pairing-1"
    pairing_id: str
    actor: Actor
    browser_session_id: str
    browser_public_key: BrowserPublicKey
    native_public_key: BrowserPublicKey
    expires_at: str
    installation: Installation
    workspace_grants: list[WorkspaceGrant] = Field(default_factory=list, max_length=0)
    note: Literal["Connected to local Codev. No workspace shared."] = "Connected to local Codev. No workspace shared."


class BrokerProof(Contract):
    pairing_id: str = Field(min_length=16, max_length=128)
    browser_session_id: str = Field(min_length=32, max_length=128)
    online_account_id: str = Field(min_length=1, max_length=128)
    nonce: str = Field(pattern=r"^[A-Za-z0-9_-]{32,64}$")
    timestamp_ms: int = Field(ge=0)
    signature: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")


class BrokerPolicy(Contract):
    origin: Literal["http://127.0.0.1:47321"] = "http://127.0.0.1:47321"
    host: Literal["127.0.0.1:47321"] = "127.0.0.1:47321"
    port: Literal[47321] = 47321
    max_body_bytes: Literal[2097152] = 2097152
    clock_skew_seconds: Literal[30] = 30


class BrokerRequest(Contract):
    proof: BrokerProof
    payload_json: str = Field(max_length=2097152)


class BrokerResponse(Contract):
    payload_json: str = Field(max_length=2097152)
    signature: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")


class BrowserWorkspaceShare(Contract):
    workspace_id: str = Field(min_length=1, max_length=128)
    surface: Literal["marketplace", "forge"]
    draft_id: str | None = Field(default=None, max_length=128)
    label: str = Field(min_length=1, max_length=120)
    base_revision: int = Field(ge=0)
    current_revision: int = Field(ge=0)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    files: list[WorkspaceFile] = Field(max_length=2000)
    scopes: list[Literal["read", "propose"]] = Field(max_length=2)
    explicitly_approved: bool
    expected_epoch: int = Field(default=0, ge=0)


class BrowserWorkspaceRequest(Contract):
    workspace_id: str = Field(min_length=1, max_length=128)


class BrowserRevisionRequest(BrowserWorkspaceRequest):
    revision: int = Field(ge=0)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    grant_epoch: int = Field(ge=1)


class BrowserChatRequest(BrowserRevisionRequest):
    message: str = Field(min_length=1, max_length=16000)
    requested_gear: str = "standard"
    response_kind: Literal["conversation", "edit_proposal"] = "conversation"
    request_id: str = Field(pattern=r"^codev_[a-f0-9]{32}$")


class BrowserEditProposal(Contract):
    summary: str = Field(min_length=1, max_length=2000)
    edits: dict[str, str] = Field(min_length=1, max_length=20)


class BrowserCancelRequest(Contract):
    request_id: str = Field(pattern=r"^codev_[a-f0-9]{32}$")


class BrowserPatchRequest(BrowserRevisionRequest):
    summary: str = Field(min_length=1, max_length=2000)
    edits: dict[str, str] = Field(min_length=1, max_length=20)


class BrowserApproveRequest(BrowserRevisionRequest):
    plan_id: str = Field(min_length=16, max_length=128)
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    explicitly_approved: bool = False


class CodevContracts(Contract):
    """Schema root for deterministic JSON Schema and TypeScript generation."""
    installation: Installation
    lifecycle: ClientLifecycle
    core_package: CorePackageManifest
    native_runtime: NativeRuntimeIdentity
    workspace: WorkspaceDescriptor
    grant: WorkspaceGrant
    plan: ChangePlan
    approval: ExactApproval
    receipt: OperationReceipt
    pairing_intent: PairingIntent
    pairing_session: PairingSession
    broker_proof: BrokerProof
    broker_policy: BrokerPolicy
    broker_request: BrokerRequest
    broker_response: BrokerResponse
    browser_share: BrowserWorkspaceShare
    browser_revision: BrowserRevisionRequest
    browser_chat: BrowserChatRequest
    browser_edit_proposal: BrowserEditProposal
    browser_cancel: BrowserCancelRequest
    browser_patch: BrowserPatchRequest
    browser_approve: BrowserApproveRequest
