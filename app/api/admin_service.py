"""Local installation governance without content-superuser authority."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import secrets
import sqlite3
from typing import Any

from app.api.account_service import (
    AccountAuthError,
    AccountBlockedError,
    AccountStore,
)
from app.api.schemas.account import LocalAccountRole
from app.api.schemas.admin import (
    AdminChangeApplyRequest,
    AdminChangeKind,
    AdminChangePreviewRequest,
    AdminEventView,
    AdminRestoreRequest,
    AdminRosterEntry,
    ManagedProfilePolicy,
)
from app.ids import new_id


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AdminService:
    """Govern installation roles and ceilings; never read content stores."""

    def __init__(self, store: AccountStore | None = None) -> None:
        self.store = store or AccountStore()

    def initialize(self) -> None:
        self.store.initialize()
        with self.store._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS admin_change_previews (
                    preview_id TEXT PRIMARY KEY,
                    actor_user_id TEXT NOT NULL,
                    target_user_id TEXT NOT NULL,
                    change_kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    approval_token_hash TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,
                    applied_at_utc TEXT
                );
                CREATE TABLE IF NOT EXISTS admin_policy_history (
                    history_id TEXT PRIMARY KEY,
                    actor_user_id TEXT NOT NULL,
                    target_user_id TEXT NOT NULL,
                    change_kind TEXT NOT NULL,
                    previous_state_json TEXT NOT NULL,
                    applied_state_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    restored_at_utc TEXT
                );
                """
            )

    def _actor(self) -> dict[str, Any]:
        actor = self.store.authenticated_governance()
        role = LocalAccountRole(str(actor["role"]))
        if role not in {LocalAccountRole.INSTALLATION_OWNER, LocalAccountRole.ADMIN}:
            raise AccountAuthError("Local installation governance authority is required.")
        return actor

    @staticmethod
    def _row_state(row: sqlite3.Row) -> dict[str, Any]:
        policy: dict[str, Any] | None = None
        if row["managed_policy_json"]:
            policy = ManagedProfilePolicy.model_validate_json(
                str(row["managed_policy_json"])
            ).model_dump(mode="json")
        return {
            "role": str(row["local_role"]),
            "managed": bool(row["managed"]),
            "managed_by_user_id": row["managed_by_user_id"],
            "managed_policy": policy,
            "enabled": row["disabled_at_utc"] is None,
            "policy_version": int(row["policy_version"] or 1),
        }

    def _target_row(self, conn: sqlite3.Connection, user_id: str) -> sqlite3.Row:
        row = conn.execute(
            """
            SELECT id, username, local_role, managed, managed_by_user_id,
                   managed_policy_json, policy_version, disabled_at_utc,
                   created_at_utc
            FROM users WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            raise AccountBlockedError("The requested local profile does not exist.")
        return row

    @staticmethod
    def _assert_change_authority(
        actor: dict[str, Any],
        target: sqlite3.Row,
        request: AdminChangePreviewRequest,
    ) -> None:
        actor_role = LocalAccountRole(str(actor["role"]))
        target_role = LocalAccountRole(str(target["local_role"]))
        if target_role == LocalAccountRole.INSTALLATION_OWNER:
            raise AccountBlockedError(
                "Admin policy cannot alter or disable the Installation Owner."
            )
        if request.change_kind == AdminChangeKind.SET_ROLE:
            if actor_role != LocalAccountRole.INSTALLATION_OWNER:
                raise AccountBlockedError("Only the Installation Owner may change Admin roles.")
            if request.target_role == LocalAccountRole.INSTALLATION_OWNER:
                raise AccountBlockedError("Owner transfer requires a separate recovery ceremony.")
            if request.managed:
                raise AccountBlockedError("Role changes do not silently change managed status.")
        elif actor_role == LocalAccountRole.ADMIN and target_role == LocalAccountRole.ADMIN:
            raise AccountBlockedError("An Admin cannot govern a peer Admin.")

    def summary(self) -> dict[str, Any]:
        actor = self._actor()
        self.initialize()
        with self.store._connect() as conn:
            rows = conn.execute(
                """
                SELECT users.id, users.username, users.local_role, users.managed,
                       users.managed_policy_json, users.policy_version,
                       users.disabled_at_utc, users.created_at_utc,
                       SUM(CASE WHEN sessions.revoked_at_utc IS NULL THEN 1 ELSE 0 END)
                           AS active_session_count
                FROM users
                LEFT JOIN sessions ON sessions.user_id = users.id
                GROUP BY users.id
                ORDER BY users.created_at_utc, users.id
                """
            ).fetchall()
            events = conn.execute(
                """
                SELECT event_id, event_type, created_at_utc, actor_user_id,
                       target_user_id, safe_summary, safe_details_json
                FROM account_events
                ORDER BY created_at_utc DESC, event_id DESC LIMIT 100
                """
            ).fetchall()
        roster: list[dict[str, Any]] = []
        for row in rows:
            policy = None
            if row["managed_policy_json"]:
                policy = ManagedProfilePolicy.model_validate_json(
                    str(row["managed_policy_json"])
                )
            roster.append(
                AdminRosterEntry(
                    user_id=str(row["id"]),
                    username=str(row["username"]),
                    role=LocalAccountRole(str(row["local_role"])),
                    managed=bool(row["managed"]),
                    enabled=row["disabled_at_utc"] is None,
                    active_session_count=int(row["active_session_count"] or 0),
                    policy_version=int(row["policy_version"] or 1),
                    created_at_utc=str(row["created_at_utc"]),
                    managed_policy=policy,
                ).to_payload()
            )
        safe_events = []
        for row in events:
            try:
                details = json.loads(str(row["safe_details_json"] or "{}"))
            except json.JSONDecodeError:
                details = {}
            safe_events.append(
                AdminEventView(
                    event_id=str(row["event_id"]),
                    event_type=str(row["event_type"]),
                    created_at_utc=str(row["created_at_utc"]),
                    actor_user_id=row["actor_user_id"],
                    target_user_id=row["target_user_id"],
                    safe_summary=str(row["safe_summary"]),
                    safe_details=details if isinstance(details, dict) else {},
                ).to_payload()
            )
        storage_truth: list[dict[str, Any]] = []
        memory_database = self.store.elysia_paths.memory_database_path
        if memory_database.is_file() and not memory_database.is_symlink():
            try:
                with sqlite3.connect(
                    f"file:{memory_database.as_posix()}?mode=ro", uri=True, timeout=1.0
                ) as memory_conn:
                    memory_conn.row_factory = sqlite3.Row
                    for roster_row in roster:
                        owner_id = str(roster_row["user_id"])
                        record = memory_conn.execute(
                            "SELECT COUNT(*) AS records FROM memory_records WHERE owner_user_id=? AND status!='deleted'",
                            (owner_id,),
                        ).fetchone()
                        objects = memory_conn.execute(
                            "SELECT COALESCE(SUM(stored_size),0) AS bytes, COUNT(*) AS objects FROM memory_objects WHERE owner_user_id=?",
                            (owner_id,),
                        ).fetchone()
                        backups = memory_conn.execute(
                            "SELECT COUNT(*) AS backups, COALESCE(SUM(size_bytes),0) AS bytes, SUM(CASE WHEN state!='verified' THEN 1 ELSE 0 END) AS degraded FROM memory_archive_registry WHERE owner_user_id=? AND archive_kind='managed_backup'",
                            (owner_id,),
                        ).fetchone()
                        failed_jobs = memory_conn.execute(
                            "SELECT COUNT(*) FROM memory_jobs WHERE owner_user_id=? AND state IN ('failed','interrupted','paused_storage_pressure')",
                            (owner_id,),
                        ).fetchone()
                        storage_truth.append(
                            {
                                "user_id": owner_id,
                                "record_count": int(record["records"] or 0),
                                "managed_object_count": int(objects["objects"] or 0),
                                "managed_object_bytes": int(objects["bytes"] or 0),
                                "managed_backup_count": int(backups["backups"] or 0),
                                "managed_backup_bytes": int(backups["bytes"] or 0),
                                "managed_backup_degraded_count": int(backups["degraded"] or 0),
                                "maintenance_attention_count": int(failed_jobs[0] or 0),
                                "content_included": False,
                            }
                        )
            except sqlite3.Error:
                storage_truth = []
        return {
            "installation_authority": actor,
            "roster": roster,
            "events": safe_events,
            "content_authorities_queried": [],
            "metadata_authorities_queried": ["canonical_memory_metadata"],
            "memory_storage_by_profile": storage_truth,
            "admin_content_access_granted": False,
            "local_online_identity_federated": False,
        }

    def preview(self, request: AdminChangePreviewRequest) -> dict[str, Any]:
        actor = self._actor()
        self.initialize()
        with self.store._connect() as conn:
            target = self._target_row(conn, request.target_user_id)
            self._assert_change_authority(actor, target, request)
            before = self._row_state(target)
            after = dict(before)
            if request.change_kind == AdminChangeKind.SET_ROLE:
                after["role"] = str(request.target_role)
                if request.target_role != LocalAccountRole.USER:
                    after.update(
                        managed=False,
                        managed_by_user_id=None,
                        managed_policy=None,
                    )
            elif request.change_kind == AdminChangeKind.SET_MANAGED_POLICY:
                if LocalAccountRole(str(target["local_role"])) != LocalAccountRole.USER:
                    raise AccountBlockedError("Only normal user profiles may be managed.")
                after["managed"] = bool(request.managed)
                after["managed_by_user_id"] = (
                    str(actor["user_id"]) if request.managed else None
                )
                after["managed_policy"] = (
                    request.managed_policy.model_dump(mode="json")
                    if request.managed and request.managed_policy
                    else None
                )
            else:
                after["enabled"] = bool(request.enabled)
            after["policy_version"] = int(before["policy_version"]) + 1
            token = secrets.token_urlsafe(32)
            preview_id = new_id("adminpreview")
            now = datetime.now(UTC).replace(microsecond=0)
            conn.execute(
                """
                INSERT INTO admin_change_previews (
                    preview_id, actor_user_id, target_user_id, change_kind,
                    payload_json, reason, approval_token_hash, created_at_utc,
                    expires_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    preview_id,
                    actor["user_id"],
                    request.target_user_id,
                    str(request.change_kind),
                    json.dumps(after, sort_keys=True),
                    request.reason,
                    _token_hash(token),
                    now.isoformat().replace("+00:00", "Z"),
                    (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
                ),
            )
        return {
            "preview_id": preview_id,
            "approval_token": token,
            "expires_in_seconds": 600,
            "change_kind": str(request.change_kind),
            "target_user_id": request.target_user_id,
            "before": before,
            "after": after,
            "content_access_changed": False,
        }

    def apply(self, request: AdminChangeApplyRequest) -> dict[str, Any]:
        actor = self._actor()
        self.initialize()
        with self.store._connect() as conn:
            preview = conn.execute(
                "SELECT * FROM admin_change_previews WHERE preview_id = ?",
                (request.preview_id,),
            ).fetchone()
            if preview is None or preview["applied_at_utc"] is not None:
                raise AccountBlockedError("This Admin preview is unavailable or already used.")
            if str(preview["actor_user_id"]) != str(actor["user_id"]):
                raise AccountAuthError("Only the previewing authority may apply this change.")
            expires = datetime.fromisoformat(str(preview["expires_at_utc"]).replace("Z", "+00:00"))
            if datetime.now(UTC) > expires:
                raise AccountBlockedError("This Admin preview expired.")
            if not secrets.compare_digest(
                str(preview["approval_token_hash"]), _token_hash(request.approval_token)
            ):
                raise AccountAuthError("The one-time Admin approval token is invalid.")
            target = self._target_row(conn, str(preview["target_user_id"]))
            before = self._row_state(target)
            after = json.loads(str(preview["payload_json"]))
            conn.execute(
                """
                UPDATE users SET local_role = ?, managed = ?, managed_by_user_id = ?,
                    managed_policy_json = ?, policy_version = ?, disabled_at_utc = ?,
                    updated_at_utc = ? WHERE id = ?
                """,
                (
                    after["role"],
                    1 if after["managed"] else 0,
                    after.get("managed_by_user_id"),
                    json.dumps(after["managed_policy"], sort_keys=True)
                    if after.get("managed_policy") is not None
                    else None,
                    int(after["policy_version"]),
                    None if after["enabled"] else _utc_now(),
                    _utc_now(),
                    preview["target_user_id"],
                ),
            )
            if not after["enabled"]:
                conn.execute(
                    "UPDATE sessions SET revoked_at_utc = ?, revocation_reason = ? WHERE user_id = ? AND revoked_at_utc IS NULL",
                    (_utc_now(), "account_disabled_by_installation_governance", preview["target_user_id"]),
                )
            history_id = new_id("adminhistory")
            conn.execute(
                """
                INSERT INTO admin_policy_history (
                    history_id, actor_user_id, target_user_id, change_kind,
                    previous_state_json, applied_state_json, reason, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    history_id,
                    actor["user_id"],
                    preview["target_user_id"],
                    preview["change_kind"],
                    json.dumps(before, sort_keys=True),
                    json.dumps(after, sort_keys=True),
                    preview["reason"],
                    _utc_now(),
                ),
            )
            conn.execute(
                "UPDATE admin_change_previews SET applied_at_utc = ? WHERE preview_id = ?",
                (_utc_now(), request.preview_id),
            )
            self.store._record_event(
                conn,
                "installation_policy_changed",
                actor_user_id=str(actor["user_id"]),
                target_user_id=str(preview["target_user_id"]),
                safe_details={
                    "change_kind": str(preview["change_kind"]),
                    "history_id": history_id,
                    "content_access_changed": False,
                },
            )
        return {
            "applied": True,
            "history_id": history_id,
            "target_user_id": str(preview["target_user_id"]),
            "effective_state": after,
            "content_access_changed": False,
        }

    def restore(self, request: AdminRestoreRequest) -> dict[str, Any]:
        actor = self._actor()
        self.initialize()
        with self.store._connect() as conn:
            history = conn.execute(
                "SELECT * FROM admin_policy_history WHERE history_id = ? AND target_user_id = ?",
                (request.history_id, request.target_user_id),
            ).fetchone()
            if history is None or history["restored_at_utc"] is not None:
                raise AccountBlockedError("The requested policy history is unavailable.")
            target = self._target_row(conn, request.target_user_id)
            if str(target["local_role"]) == LocalAccountRole.INSTALLATION_OWNER.value:
                raise AccountBlockedError("The Installation Owner cannot be restored through this path.")
            previous = json.loads(str(history["previous_state_json"]))
            if (
                LocalAccountRole(str(actor["role"])) == LocalAccountRole.ADMIN
                and previous["role"] == LocalAccountRole.ADMIN.value
            ):
                raise AccountBlockedError("Only the Owner may restore an Admin role state.")
            restored_version = int(target["policy_version"] or 1) + 1
            conn.execute(
                """
                UPDATE users SET local_role = ?, managed = ?, managed_by_user_id = ?,
                    managed_policy_json = ?, policy_version = ?, disabled_at_utc = ?,
                    updated_at_utc = ? WHERE id = ?
                """,
                (
                    previous["role"],
                    1 if previous["managed"] else 0,
                    previous.get("managed_by_user_id"),
                    json.dumps(previous["managed_policy"], sort_keys=True)
                    if previous.get("managed_policy") is not None
                    else None,
                    restored_version,
                    None if previous["enabled"] else _utc_now(),
                    _utc_now(),
                    request.target_user_id,
                ),
            )
            conn.execute(
                "UPDATE admin_policy_history SET restored_at_utc = ? WHERE history_id = ?",
                (_utc_now(), request.history_id),
            )
            self.store._record_event(
                conn,
                "installation_policy_restored",
                actor_user_id=str(actor["user_id"]),
                target_user_id=request.target_user_id,
                safe_details={
                    "history_id": request.history_id,
                    "content_access_changed": False,
                },
            )
        previous["policy_version"] = restored_version
        return {
            "restored": True,
            "target_user_id": request.target_user_id,
            "effective_state": previous,
            "content_access_changed": False,
        }


def get_admin_summary() -> dict[str, Any]:
    return AdminService().summary()


def preview_admin_change(request: AdminChangePreviewRequest) -> dict[str, Any]:
    return AdminService().preview(request)


def apply_admin_change(request: AdminChangeApplyRequest) -> dict[str, Any]:
    return AdminService().apply(request)


def restore_admin_change(request: AdminRestoreRequest) -> dict[str, Any]:
    return AdminService().restore(request)


__all__ = (
    "AdminService",
    "apply_admin_change",
    "get_admin_summary",
    "preview_admin_change",
    "restore_admin_change",
)
