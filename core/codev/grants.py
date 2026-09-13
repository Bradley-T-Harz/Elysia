"""Actor/workspace grants with explicit revocation and monotonically rising epochs.

Adapters supply verified actors. Pairing does not call this service. State is
session-local: restarting Elysia requires new workspace grants and approvals.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4

from core.codev.contracts import Actor, WorkspaceGrant
from core.codev.revisions import relative_path, denied_path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


class GrantDenied(ValueError):
    pass


class GrantAuthority:
    def __init__(self):
        self._grants: dict[tuple[str, str, str], WorkspaceGrant] = {}
        self._lock = RLock()

    @staticmethod
    def _key(actor: Actor, workspace_id: str) -> tuple[str, str, str]:
        return actor.local_profile_id, actor.client_id, workspace_id

    def issue(self, *, actor: Actor, workspace_id: str, scopes: list[str], files: list[str],
              command_ids: list[str], expected_epoch: int, explicitly_approved: bool,
              ttl_seconds: int = 3600) -> WorkspaceGrant:
        if not explicitly_approved:
            raise GrantDenied("explicit_workspace_approval_required")
        if actor.client_kind == "browser" and (set(scopes) - {"metadata", "read", "propose"} or command_ids):
            raise GrantDenied("browser_cannot_grant_native_mutation_or_commands")
        if set(scopes) - {"metadata", "read", "propose", "apply", "command"}:
            raise GrantDenied("unsupported_workspace_scope")
        selected = sorted(set(relative_path(path) for path in files))
        if len(selected) > 40 or any(denied_path(path) for path in selected):
            raise GrantDenied("file_scope_denied")
        if set(command_ids) - {"git_diff_check"}:
            raise GrantDenied("command_scope_not_qualified")
        with self._lock:
            key = self._key(actor, workspace_id)
            previous = self._grants.get(key)
            if previous and previous.actor != actor:
                raise GrantDenied("workspace_actor_mismatch")
            if (previous.epoch if previous else 0) != expected_epoch:
                raise GrantDenied("grant_epoch_conflict")
            if key not in self._grants and len(self._grants) >= 256:
                raise GrantDenied("workspace_grant_capacity_reached")
            grant = WorkspaceGrant(grant_id=f"grant_{uuid4().hex}", workspace_id=workspace_id,
                actor=actor.model_copy(deep=True), epoch=expected_epoch + 1, scopes=sorted(set(scopes)), files=selected,
                command_ids=sorted(set(command_ids)),
                expires_at=(utc_now() + timedelta(seconds=max(1, min(ttl_seconds, 3600)))).isoformat())
            self._grants[key] = grant
            return grant.model_copy(deep=True)

    def get(self, actor: Actor, workspace_id: str) -> WorkspaceGrant | None:
        with self._lock:
            grant = self._grants.get(self._key(actor, workspace_id))
            return grant.model_copy(deep=True) if grant and grant.actor == actor else None

    def require(self, actor: Actor, workspace_id: str, scope: str, *, files: list[str] | None = None,
                epoch: int | None = None, command_id: str | None = None) -> WorkspaceGrant:
        grant = self.get(actor, workspace_id)
        if not grant or grant.actor != actor or grant.revoked or utc_now() >= datetime.fromisoformat(grant.expires_at):
            raise GrantDenied("workspace_grant_missing_expired_or_revoked")
        if epoch is not None and grant.epoch != epoch:
            raise GrantDenied("grant_epoch_conflict")
        if scope not in grant.scopes or set(files or []) - set(grant.files):
            raise GrantDenied("workspace_scope_not_granted")
        if command_id and command_id not in grant.command_ids:
            raise GrantDenied("command_scope_not_granted")
        return grant

    def revoke(self, actor: Actor, workspace_id: str) -> WorkspaceGrant | None:
        with self._lock:
            grant = self._grants.get(self._key(actor, workspace_id))
            if grant and grant.actor == actor:
                grant.epoch += 1
                grant.revoked = True
                grant.scopes = []
                grant.files = []
                grant.command_ids = []
            return grant.model_copy(deep=True) if grant and grant.actor == actor else None

    def epochs(self, actor: Actor) -> dict[str, int]:
        with self._lock:
            return {grant.workspace_id: grant.epoch for grant in self._grants.values() if grant.actor == actor}

    def retire_actor(self, actor: Actor) -> None:
        """Only after the adapter permanently revokes this unique client identity."""
        with self._lock:
            self._grants = {key: grant for key, grant in self._grants.items() if grant.actor != actor}


GRANTS = GrantAuthority()
