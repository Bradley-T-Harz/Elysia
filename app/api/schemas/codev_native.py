"""Strict native transport requests; the browser broker never exposes these."""
from pydantic import Field
from core.codev.contracts import Contract


class NativeRequest(Contract):
    client_id: str = Field(min_length=16, max_length=128)


class WorkspaceRequest(NativeRequest):
    workspace_id: str = Field(min_length=16, max_length=128)


class SelectRequest(NativeRequest):
    root_path: str = Field(min_length=1, max_length=4096)


class GrantRequest(WorkspaceRequest):
    scopes: list[str] = Field(max_length=5)
    files: list[str] = Field(default_factory=list, max_length=40)
    command_ids: list[str] = Field(default_factory=list, max_length=1)
    expected_epoch: int = Field(ge=0)
    explicitly_approved: bool = False


class PatchRequest(WorkspaceRequest):
    edits: dict[str, str]
    revision: int = Field(ge=0)
    summary: str = Field(min_length=1, max_length=2000)


class ApprovalRequest(NativeRequest):
    plan_id: str = Field(min_length=16, max_length=128)
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    explicitly_approved: bool = False


class ApplyRequest(WorkspaceRequest):
    plan_id: str = Field(min_length=16, max_length=128)
    approval_id: str = Field(min_length=16, max_length=128)
    approval_token: str = Field(min_length=32, max_length=128)


class CommandPlanRequest(WorkspaceRequest):
    command_id: str = Field(min_length=1, max_length=80)


class CommandStatusRequest(WorkspaceRequest):
    run_id: str = Field(min_length=16, max_length=128)


class ChatRequest(NativeRequest):
    workspace_id: str | None = None
    message: str = Field(min_length=1, max_length=16000)
    request_id: str = Field(pattern=r"^codev_[a-f0-9]{32}$")
    requested_gear: str = "standard"
    handoff: str = Field(default="", max_length=16000)


class ChatCancelRequest(NativeRequest):
    request_id: str = Field(pattern=r"^codev_[a-f0-9]{32}$")


class PairingClaimRequest(NativeRequest):
    code: str = Field(pattern=r"^EC1\.[AW]\.[A-Za-z0-9_-]{43}$")


class PairingActionRequest(NativeRequest):
    pairing_id: str = Field(min_length=16, max_length=128)
    action: str = Field(pattern=r"^(confirm|deny|revoke)$")
    explicitly_approved: bool = False


class PairingRevokeRequest(NativeRequest):
    pairing_id: str = Field(min_length=16, max_length=128)
