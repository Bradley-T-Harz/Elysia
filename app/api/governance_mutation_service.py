"""Exact, fail-closed plan/apply/restore contracts for Governance changes.

The production registry intentionally contains no writable control in Pass 3.
The generic YAML adapter exists so a later pass can promote a reviewed low-risk
control without inventing a second approval or recovery system.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from hmac import compare_digest
import json
import os
from pathlib import Path
from secrets import token_urlsafe
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Any
from uuid import uuid4

try:
    import yaml
except Exception:  # pragma: no cover - defensive environment guard
    yaml = None

from app.api.schemas.approval import (
    ApprovalDecision,
    ApprovalRequestState,
    ApprovalResolutionStatus,
    ApprovalResolveRequest,
    ApprovalResolveResponseData,
)
from app.api.schemas.common import (
    ApprovalState,
    CapabilityState,
    EnvelopeStatus,
    LocalityState,
)
from app.api.schemas.envelope import TraceSummary, build_response_envelope
from app.api.schemas.governance_mutation import (
    GovernanceChangeApplyRequest,
    GovernanceChangeApplyResult,
    GovernanceChangePlan,
    GovernanceChangePlanRequest,
    GovernanceMutationAction,
    GovernanceMutationOutcome,
    GovernanceMutationReceipt,
    GovernanceRestoreRequest,
    GovernanceRestoreResult,
    GovernanceScalar,
)
from app.governance.governance_control_registry import (
    GovernanceControlRegistry,
    GovernanceControlRule,
    GovernanceMutationClassification,
    GovernanceMutationRisk,
    fail_closed_governance_control_registry,
    load_governance_control_registry,
)
from app.install.paths import resolve_elysia_paths


API_VERSION = "1.0.0"
CONTRACT_VERSION = "governance-mutation-contract-1.0"
PLAN_TTL_SECONDS = 600
APPROVAL_TTL_SECONDS = 300

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = REPO_ROOT / "config"


def _default_state_root() -> Path:
    return resolve_elysia_paths().state_dir


BACKUP_ROOT = _default_state_root() / "governance" / "backups"


@dataclass
class _PlanRecord:
    plan: GovernanceChangePlan
    rule: GovernanceControlRule
    current_value: GovernanceScalar
    proposed_value: GovernanceScalar
    expires_at: datetime


@dataclass
class _ApprovalRecord:
    request_id: str
    action: GovernanceMutationAction
    subject_id: str
    subject_hash: str
    expires_at: datetime
    state: ApprovalRequestState = ApprovalRequestState.PENDING
    approval_id: str | None = None
    token: str | None = None
    consumed_at: datetime | None = None


@dataclass
class _RestoreRecord:
    restore_id: str
    control_id: str
    rule: GovernanceControlRule
    backup_path: Path
    backup_hash: str
    applied_value: GovernanceScalar
    restored_value: GovernanceScalar
    expected_config_hash: str
    restore_plan_hash: str
    approval_request_id: str
    used_at: datetime | None = None


_PLANS: dict[str, _PlanRecord] = {}
_APPROVAL_REQUESTS: dict[str, _ApprovalRecord] = {}
_RESTORES: dict[str, _RestoreRecord] = {}
_STATE_LOCK = RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:20]}"


def _hash_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _model_payload(model: Any) -> dict[str, Any]:
    if hasattr(model, "to_payload"):
        return model.to_payload()
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json", exclude_none=True)
    if hasattr(model, "dict"):
        return model.dict(exclude_none=True)
    raise TypeError("Unable to serialize governance mutation model.")


def _registry() -> GovernanceControlRegistry:
    try:
        return load_governance_control_registry()
    except Exception:
        return fail_closed_governance_control_registry()


def _read_authoritative_state() -> tuple[dict[str, Any], str]:
    from app.api.governance_service import get_governance_state

    envelope = get_governance_state()
    data = envelope.get("data") if isinstance(envelope, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError("Authoritative Governance state is unavailable.")
    config_hash = str(data.get("governance_config_hash") or "").strip()
    if len(config_hash) != 64:
        raise RuntimeError("Authoritative Governance config hash is unavailable.")
    return data, config_hash


def _control_from_state(data: dict[str, Any], control_id: str) -> dict[str, Any] | None:
    controls = data.get("control_states")
    if not isinstance(controls, list):
        return None
    for control in controls:
        if isinstance(control, dict) and control.get("control_id") == control_id:
            return control
    return None


def _scalar_matches(left: GovernanceScalar, right: GovernanceScalar) -> bool:
    return type(left) is type(right) and left == right


def _value_allowed(rule: GovernanceControlRule, value: GovernanceScalar) -> bool:
    return any(_scalar_matches(value, allowed) for allowed in rule.allowed_values)


def _trace_receipt(receipt: GovernanceMutationReceipt) -> None:
    """Record only allowlisted IDs/outcomes; never raw values, paths, or user reason."""
    try:
        from app.api.request_trace_service import (
            mark_request_trace_blocked,
            mark_request_trace_completed,
            start_request_trace,
        )

        action_value = (
            receipt.action.value if hasattr(receipt.action, "value") else str(receipt.action)
        )
        outcome_value = (
            receipt.outcome.value if hasattr(receipt.outcome, "value") else str(receipt.outcome)
        )
        start_request_trace(
            request_id=receipt.request_id,
            route_used=f"governance.changes.{action_value}",
            ui_surface="governance_room",
            selected_mode="governance_exact_change",
            phase="governance_contract",
            label="Governance contract evaluated",
            detail=f"{receipt.control_id}: {outcome_value}",
        )
        terminal = (
            mark_request_trace_completed
            if outcome_value in {"planned", "applied", "restored"}
            else mark_request_trace_blocked
        )
        terminal(
            request_id=receipt.request_id,
            phase=f"governance_{action_value}",
            label=f"Governance {outcome_value}",
            detail=receipt.reason_code or "governance_contract_evaluated",
            locality_state="local",
            approval_state=(
                "approved"
                if outcome_value in {"applied", "restored"}
                else "needed"
                if outcome_value == "planned"
                else "denied"
            ),
            approval_needed=action_value != "plan" or outcome_value == "planned",
            execution_operation=f"governance_{action_value}",
            execution_status=outcome_value,
            execution_summary=receipt.reason_code or "sanitized_governance_receipt",
        )
    except Exception:
        # The returned receipt remains the source of truth if trace support degrades.
        return


def _receipt(
    *,
    request_id: str,
    operation_id: str,
    action: GovernanceMutationAction,
    outcome: GovernanceMutationOutcome,
    control_id: str,
    rule: GovernanceControlRule,
    config_hash_before: str | None = None,
    config_hash_after: str | None = None,
    plan_hash: str | None = None,
    approval_id: str | None = None,
    reason_code: str | None = None,
) -> GovernanceMutationReceipt:
    receipt = GovernanceMutationReceipt(
        request_id=request_id,
        operation_id=operation_id,
        action=action,
        outcome=outcome,
        control_id=control_id,
        classification=rule.classification,
        risk=rule.risk,
        recorded_at_utc=_iso(),
        config_hash_before=config_hash_before,
        config_hash_after=config_hash_after,
        plan_hash=plan_hash,
        approval_id=approval_id,
        reason_code=reason_code,
    )
    _trace_receipt(receipt)
    return receipt


def _envelope(
    *,
    status: EnvelopeStatus,
    request_id: str,
    result_type: str,
    approval_state: ApprovalState,
    data: dict[str, Any],
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return build_response_envelope(
        status=status,
        request_id=request_id,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        result_type=result_type,
        capability_state=CapabilityState.LIVE,
        locality=LocalityState.LOCAL,
        approval_state=approval_state,
        warnings=warnings or [],
        errors=errors or [],
        trace_summary=TraceSummary(
            route_used=f"governance_mutation_service.{result_type}",
            log_written=False,
            journal_written=False,
        ),
        data=data,
    ).to_payload()


def _blocked_plan(
    *,
    request_id: str,
    plan_id: str,
    plan_hash: str,
    control_id: str,
    rule: GovernanceControlRule,
    current_value: GovernanceScalar,
    proposed_value: GovernanceScalar,
    config_hash: str,
    expires_at: datetime,
    reason_code: str,
    blocker: str,
    outcome: GovernanceMutationOutcome = GovernanceMutationOutcome.BLOCKED,
) -> dict[str, Any]:
    receipt = _receipt(
        request_id=request_id,
        operation_id=plan_id,
        action=GovernanceMutationAction.PLAN,
        outcome=outcome,
        control_id=control_id,
        rule=rule,
        config_hash_before=config_hash,
        plan_hash=plan_hash,
        reason_code=reason_code,
    )
    plan = GovernanceChangePlan(
        plan_id=plan_id,
        control_id=control_id,
        classification=rule.classification,
        risk=rule.risk,
        mutation_allowed=False,
        approval_required=False,
        current_value=current_value,
        proposed_value=proposed_value,
        config_hash=config_hash,
        plan_hash=plan_hash,
        expires_at_utc=_iso(expires_at),
        consequences=["No authoritative Governance state will be changed."],
        blockers=[blocker],
        receipt=receipt,
    )
    return _envelope(
        status=EnvelopeStatus.BLOCKED,
        request_id=request_id,
        result_type="governance_change_plan",
        approval_state=ApprovalState.DENIED,
        data={"plan": _model_payload(plan)},
        errors=[blocker],
    )


def plan_governance_change(
    payload: GovernanceChangePlanRequest | dict[str, Any],
) -> dict[str, Any]:
    request = (
        payload
        if isinstance(payload, GovernanceChangePlanRequest)
        else GovernanceChangePlanRequest(**payload)
    )
    request_id = _new_id("govreq")
    plan_id = _new_id("govplan")
    expires_at = _now() + timedelta(seconds=PLAN_TTL_SECONDS)
    registry = _registry()
    rule = registry.rule_for(request.control_id)

    try:
        state, config_hash = _read_authoritative_state()
    except Exception:
        config_hash = "0" * 64
        plan_hash = _hash_payload(
            {"plan_id": plan_id, "control_id": request.control_id, "unavailable": True}
        )
        return _blocked_plan(
            request_id=request_id,
            plan_id=plan_id,
            plan_hash=plan_hash,
            control_id=request.control_id,
            rule=fail_closed_governance_control_registry().default_rule,
            current_value=None,
            proposed_value=request.proposed_value,
            config_hash=config_hash,
            expires_at=expires_at,
            reason_code="authoritative_state_unavailable",
            blocker="Authoritative Governance state is unavailable; mutation fails closed.",
        )

    control = _control_from_state(state, request.control_id)
    current_value = control.get("value") if control else None
    plan_hash = _hash_payload(
        {
            "plan_id": plan_id,
            "control_id": request.control_id,
            "current_value": current_value,
            "proposed_value": request.proposed_value,
            "config_hash": config_hash,
            "contract_version": registry.contract_version,
            "classification": rule.classification.value,
        }
    )

    if control is None:
        return _blocked_plan(
            request_id=request_id,
            plan_id=plan_id,
            plan_hash=plan_hash,
            control_id=request.control_id,
            rule=registry.default_rule,
            current_value=None,
            proposed_value=request.proposed_value,
            config_hash=config_hash,
            expires_at=expires_at,
            reason_code="unknown_control_id",
            blocker="The requested control ID is not part of authoritative Governance state.",
        )

    if not compare_digest(request.expected_config_hash, config_hash):
        return _blocked_plan(
            request_id=request_id,
            plan_id=plan_id,
            plan_hash=plan_hash,
            control_id=request.control_id,
            rule=rule,
            current_value=current_value,
            proposed_value=request.proposed_value,
            config_hash=config_hash,
            expires_at=expires_at,
            reason_code="stale_config_hash",
            blocker="Governance state changed or the supplied config hash is stale; refresh before planning.",
            outcome=GovernanceMutationOutcome.STALE,
        )

    if not rule.mutation_allowed:
        return _blocked_plan(
            request_id=request_id,
            plan_id=plan_id,
            plan_hash=plan_hash,
            control_id=request.control_id,
            rule=rule,
            current_value=current_value,
            proposed_value=request.proposed_value,
            config_hash=config_hash,
            expires_at=expires_at,
            reason_code=rule.classification.value,
            blocker=rule.reason,
        )

    try:
        current_value = _YamlGovernanceMutationAdapter(rule).read_current()
    except Exception:
        return _blocked_plan(
            request_id=request_id,
            plan_id=plan_id,
            plan_hash=plan_hash,
            control_id=request.control_id,
            rule=rule,
            current_value=None,
            proposed_value=request.proposed_value,
            config_hash=config_hash,
            expires_at=expires_at,
            reason_code="authoritative_adapter_unavailable",
            blocker="The authoritative mutation adapter is unavailable; no plan was issued.",
        )

    plan_hash = _hash_payload(
        {
            "plan_id": plan_id,
            "control_id": request.control_id,
            "current_value": current_value,
            "proposed_value": request.proposed_value,
            "config_hash": config_hash,
            "contract_version": registry.contract_version,
            "classification": rule.classification.value,
        }
    )

    if not _value_allowed(rule, request.proposed_value):
        return _blocked_plan(
            request_id=request_id,
            plan_id=plan_id,
            plan_hash=plan_hash,
            control_id=request.control_id,
            rule=rule,
            current_value=current_value,
            proposed_value=request.proposed_value,
            config_hash=config_hash,
            expires_at=expires_at,
            reason_code="proposed_value_not_allowlisted",
            blocker="The proposed value is not in the exact allowlist for this control.",
        )

    if _scalar_matches(current_value, request.proposed_value):
        return _blocked_plan(
            request_id=request_id,
            plan_id=plan_id,
            plan_hash=plan_hash,
            control_id=request.control_id,
            rule=rule,
            current_value=current_value,
            proposed_value=request.proposed_value,
            config_hash=config_hash,
            expires_at=expires_at,
            reason_code="no_state_change",
            blocker="The proposed value already matches authoritative Governance state.",
        )

    approval_request_id = _new_id("govapprovalreq")
    receipt = _receipt(
        request_id=request_id,
        operation_id=plan_id,
        action=GovernanceMutationAction.PLAN,
        outcome=GovernanceMutationOutcome.PLANNED,
        control_id=request.control_id,
        rule=rule,
        config_hash_before=config_hash,
        plan_hash=plan_hash,
        reason_code="exact_approval_required",
    )
    plan = GovernanceChangePlan(
        plan_id=plan_id,
        control_id=request.control_id,
        classification=rule.classification,
        risk=rule.risk,
        mutation_allowed=True,
        approval_required=True,
        current_value=current_value,
        proposed_value=request.proposed_value,
        config_hash=config_hash,
        plan_hash=plan_hash,
        expires_at_utc=_iso(expires_at),
        approval_request_id=approval_request_id,
        consequences=[
            "Only the exact allowlisted key and proposed scalar value may change.",
            "A recovery copy is written before the atomic replacement.",
            "The approval is expiring, exact, and one-time.",
        ],
        blockers=[],
        receipt=receipt,
    )
    with _STATE_LOCK:
        _PLANS[plan_id] = _PlanRecord(
            plan=plan,
            rule=rule,
            current_value=current_value,
            proposed_value=request.proposed_value,
            expires_at=expires_at,
        )
        _APPROVAL_REQUESTS[approval_request_id] = _ApprovalRecord(
            request_id=approval_request_id,
            action=GovernanceMutationAction.APPLY,
            subject_id=plan_id,
            subject_hash=plan_hash,
            expires_at=min(expires_at, _now() + timedelta(seconds=APPROVAL_TTL_SECONDS)),
        )

    return _envelope(
        status=EnvelopeStatus.OK,
        request_id=request_id,
        result_type="governance_change_plan",
        approval_state=ApprovalState.NEEDED,
        data={"plan": _model_payload(plan)},
        warnings=["Planning does not mutate Governance state."],
    )


class _YamlGovernanceMutationAdapter:
    """Narrow atomic YAML scalar adapter used only by allowlisted registry rules."""

    def __init__(self, rule: GovernanceControlRule) -> None:
        if not rule.mutation_allowed or not rule.target_relative_path:
            raise ValueError("Governance control has no live mutation adapter.")
        target = (Path(CONFIG_ROOT) / rule.target_relative_path).resolve()
        config_root = Path(CONFIG_ROOT).resolve()
        if not target.is_relative_to(config_root) or target.suffix not in {".yaml", ".yml"}:
            raise ValueError("Governance mutation target is outside the approved YAML config root.")
        self.rule = rule
        self.target = target

    def _read_document(self) -> tuple[str, dict[str, Any]]:
        if yaml is None:
            raise RuntimeError("PyYAML is required for Governance config mutation.")
        source = self.target.read_text(encoding="utf-8")
        document = yaml.safe_load(source)
        if not isinstance(document, dict):
            raise ValueError("Governance mutation target must contain a YAML mapping.")
        return source, document

    def read_current(self) -> GovernanceScalar:
        _, document = self._read_document()
        cursor: Any = document
        for key in self.rule.yaml_key_path:
            if not isinstance(cursor, dict) or key not in cursor:
                raise KeyError("Governance mutation key path is not present.")
            cursor = cursor[key]
        if type(cursor) not in {str, bool, int, float, type(None)}:
            raise TypeError("Governance mutation key must contain a scalar value.")
        return cursor

    def _replace_value(self, document: dict[str, Any], value: GovernanceScalar) -> None:
        cursor: dict[str, Any] = document
        for key in self.rule.yaml_key_path[:-1]:
            next_value = cursor.get(key)
            if not isinstance(next_value, dict):
                raise KeyError("Governance mutation key path is not present.")
            cursor = next_value
        leaf = self.rule.yaml_key_path[-1]
        if leaf not in cursor:
            raise KeyError("Governance mutation key path is not present.")
        cursor[leaf] = value

    @staticmethod
    def _atomic_write(path: Path, content: str, *, mode: int | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)
            if mode is not None:
                temporary_path.chmod(mode)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _secure_backup_parent(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)

    def apply(self, *, expected_value: GovernanceScalar, proposed_value: GovernanceScalar) -> tuple[Path, str]:
        source, document = self._read_document()
        current = self.read_current()
        if not _scalar_matches(current, expected_value):
            raise RuntimeError("Authoritative target value changed before apply.")
        if not _value_allowed(self.rule, proposed_value):
            raise RuntimeError("Proposed value is no longer allowlisted.")

        backup_hash = sha256(source.encode("utf-8")).hexdigest()
        backup_path = Path(BACKUP_ROOT) / f"backup_{uuid4().hex}.yaml"
        self._secure_backup_parent(backup_path)
        self._atomic_write(backup_path, source, mode=0o600)
        self._replace_value(document, proposed_value)
        rendered = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)  # type: ignore[union-attr]
        target_mode = self.target.stat().st_mode & 0o777
        self._atomic_write(self.target, rendered, mode=target_mode)
        return backup_path, backup_hash

    def restore(self, *, backup_path: Path, backup_hash: str, expected_value: GovernanceScalar) -> GovernanceScalar:
        current_source, _ = self._read_document()
        current = self.read_current()
        if not _scalar_matches(current, expected_value):
            raise RuntimeError("Authoritative target value changed before restore.")
        backup_source = backup_path.read_text(encoding="utf-8")
        if not compare_digest(sha256(backup_source.encode("utf-8")).hexdigest(), backup_hash):
            raise RuntimeError("Governance recovery copy failed integrity validation.")

        # Preserve the current applied state before restoring the earlier recovery copy.
        recovery_path = Path(BACKUP_ROOT) / f"pre_restore_{uuid4().hex}.yaml"
        self._secure_backup_parent(recovery_path)
        self._atomic_write(recovery_path, current_source, mode=0o600)
        target_mode = self.target.stat().st_mode & 0o777
        self._atomic_write(self.target, backup_source, mode=target_mode)
        return self.read_current()


def _approval_failure(
    record: _ApprovalRecord | None,
    *,
    approval_id: str | None,
    approval_token: str | None,
    action: GovernanceMutationAction,
    subject_id: str,
    subject_hash: str,
) -> str | None:
    if record is None:
        return "approval_missing"
    if record.action is not action or record.subject_id != subject_id:
        return "approval_scope_mismatch"
    if not compare_digest(record.subject_hash, subject_hash):
        return "approval_subject_hash_mismatch"
    if _now() >= record.expires_at:
        return "approval_expired"
    if not approval_id or not approval_token:
        return "approval_missing"
    if record.state is not ApprovalRequestState.APPROVED or not record.approval_id or not record.token:
        return "approval_not_approved"
    if record.consumed_at is not None:
        return "approval_already_used"
    if not compare_digest(approval_id, record.approval_id):
        return "approval_id_mismatch"
    if not compare_digest(approval_token, record.token):
        return "approval_token_mismatch"
    return None


def _blocked_action(
    *,
    request_id: str,
    operation_id: str,
    action: GovernanceMutationAction,
    control_id: str,
    rule: GovernanceControlRule,
    reason_code: str,
    error: str,
    config_hash: str,
    plan_hash: str | None,
    approval_id: str | None,
    outcome: GovernanceMutationOutcome = GovernanceMutationOutcome.BLOCKED,
) -> dict[str, Any]:
    receipt = _receipt(
        request_id=request_id,
        operation_id=operation_id,
        action=action,
        outcome=outcome,
        control_id=control_id,
        rule=rule,
        config_hash_before=config_hash,
        plan_hash=plan_hash,
        approval_id=approval_id,
        reason_code=reason_code,
    )
    key = "apply_result" if action is GovernanceMutationAction.APPLY else "restore_result"
    return _envelope(
        status=EnvelopeStatus.BLOCKED,
        request_id=request_id,
        result_type=f"governance_change_{action.value}",
        approval_state=ApprovalState.DENIED,
        data={key: {"applied" if action is GovernanceMutationAction.APPLY else "restored": False, "control_id": control_id, "receipt": _model_payload(receipt)}},
        errors=[error],
    )


def apply_governance_change(
    payload: GovernanceChangeApplyRequest | dict[str, Any],
) -> dict[str, Any]:
    request = payload if isinstance(payload, GovernanceChangeApplyRequest) else GovernanceChangeApplyRequest(**payload)
    request_id = _new_id("govreq")
    fallback_rule = fail_closed_governance_control_registry().default_rule

    with _STATE_LOCK:
        record = _PLANS.get(request.plan_id)
        if record is None:
            return _blocked_action(
                request_id=request_id,
                operation_id=request.plan_id,
                action=GovernanceMutationAction.APPLY,
                control_id="unknown",
                rule=fallback_rule,
                reason_code="unknown_plan_id",
                error="The exact Governance change plan is unknown or no longer available.",
                config_hash=request.expected_config_hash,
                plan_hash=request.plan_hash,
                approval_id=request.approval_id,
            )

        plan = record.plan
        rule = record.rule
        current_rule = _registry().rule_for(plan.control_id)
        if current_rule != rule or not current_rule.mutation_allowed:
            return _blocked_action(
                request_id=request_id,
                operation_id=request.plan_id,
                action=GovernanceMutationAction.APPLY,
                control_id=plan.control_id,
                rule=rule,
                reason_code="control_registry_changed",
                error="The control registry changed or no longer permits this exact mutation.",
                config_hash=plan.config_hash,
                plan_hash=request.plan_hash,
                approval_id=request.approval_id,
            )
        if _now() >= record.expires_at:
            return _blocked_action(
                request_id=request_id,
                operation_id=request.plan_id,
                action=GovernanceMutationAction.APPLY,
                control_id=plan.control_id,
                rule=rule,
                reason_code="plan_expired",
                error="The Governance change plan expired; create a fresh plan.",
                config_hash=plan.config_hash,
                plan_hash=request.plan_hash,
                approval_id=request.approval_id,
                outcome=GovernanceMutationOutcome.EXPIRED,
            )
        if not compare_digest(request.plan_hash, plan.plan_hash):
            return _blocked_action(
                request_id=request_id,
                operation_id=request.plan_id,
                action=GovernanceMutationAction.APPLY,
                control_id=plan.control_id,
                rule=rule,
                reason_code="plan_hash_mismatch",
                error="The Governance change plan hash did not match the server-held plan.",
                config_hash=plan.config_hash,
                plan_hash=request.plan_hash,
                approval_id=request.approval_id,
                outcome=GovernanceMutationOutcome.TAMPERED,
            )
        if not request.confirmed:
            return _blocked_action(
                request_id=request_id,
                operation_id=request.plan_id,
                action=GovernanceMutationAction.APPLY,
                control_id=plan.control_id,
                rule=rule,
                reason_code="explicit_confirmation_required",
                error="Explicit confirmation is required before applying Governance law.",
                config_hash=plan.config_hash,
                plan_hash=plan.plan_hash,
                approval_id=request.approval_id,
            )

        approval_request_id = plan.approval_request_id or ""
        approval = _APPROVAL_REQUESTS.get(approval_request_id)
        approval_error = _approval_failure(
            approval,
            approval_id=request.approval_id,
            approval_token=request.approval_token,
            action=GovernanceMutationAction.APPLY,
            subject_id=request.plan_id,
            subject_hash=plan.plan_hash,
        )
        if approval_error:
            return _blocked_action(
                request_id=request_id,
                operation_id=request.plan_id,
                action=GovernanceMutationAction.APPLY,
                control_id=plan.control_id,
                rule=rule,
                reason_code=approval_error,
                error="The exact expiring approval was missing, invalid, expired, or already used.",
                config_hash=plan.config_hash,
                plan_hash=plan.plan_hash,
                approval_id=request.approval_id,
                outcome=(
                    GovernanceMutationOutcome.EXPIRED
                    if approval_error == "approval_expired"
                    else GovernanceMutationOutcome.BLOCKED
                ),
            )

        _, current_hash = _read_authoritative_state()
        if (
            not compare_digest(request.expected_config_hash, plan.config_hash)
            or not compare_digest(current_hash, plan.config_hash)
        ):
            return _blocked_action(
                request_id=request_id,
                operation_id=request.plan_id,
                action=GovernanceMutationAction.APPLY,
                control_id=plan.control_id,
                rule=rule,
                reason_code="stale_config_hash",
                error="Authoritative Governance state changed after planning; refresh and plan again.",
                config_hash=current_hash,
                plan_hash=plan.plan_hash,
                approval_id=request.approval_id,
                outcome=GovernanceMutationOutcome.STALE,
            )

        adapter = _YamlGovernanceMutationAdapter(rule)
        adapter_current = adapter.read_current()
        if not _scalar_matches(adapter_current, record.current_value):
            return _blocked_action(
                request_id=request_id,
                operation_id=request.plan_id,
                action=GovernanceMutationAction.APPLY,
                control_id=plan.control_id,
                rule=rule,
                reason_code="authoritative_value_changed",
                error="The exact target value changed after planning; no write was performed.",
                config_hash=current_hash,
                plan_hash=plan.plan_hash,
                approval_id=request.approval_id,
                outcome=GovernanceMutationOutcome.STALE,
            )

        backup_path, backup_hash = adapter.apply(
            expected_value=record.current_value,
            proposed_value=record.proposed_value,
        )
        try:
            _, new_hash = _read_authoritative_state()
            if compare_digest(new_hash, current_hash):
                raise RuntimeError("Authoritative Governance hash did not change after apply.")
        except Exception:
            adapter.restore(
                backup_path=backup_path,
                backup_hash=backup_hash,
                expected_value=record.proposed_value,
            )
            raise

        if approval is None:  # pragma: no cover - guarded above
            raise RuntimeError("Approval record disappeared during atomic apply.")
        approval.consumed_at = _now()

        restore_id = _new_id("govrestore")
        restore_plan_hash = _hash_payload(
            {
                "restore_id": restore_id,
                "control_id": plan.control_id,
                "applied_value": record.proposed_value,
                "restored_value": record.current_value,
                "expected_config_hash": new_hash,
                "backup_hash": backup_hash,
            }
        )
        restore_approval_request_id = _new_id("govapprovalreq")
        _RESTORES[restore_id] = _RestoreRecord(
            restore_id=restore_id,
            control_id=plan.control_id,
            rule=rule,
            backup_path=backup_path,
            backup_hash=backup_hash,
            applied_value=record.proposed_value,
            restored_value=record.current_value,
            expected_config_hash=new_hash,
            restore_plan_hash=restore_plan_hash,
            approval_request_id=restore_approval_request_id,
        )
        _APPROVAL_REQUESTS[restore_approval_request_id] = _ApprovalRecord(
            request_id=restore_approval_request_id,
            action=GovernanceMutationAction.RESTORE,
            subject_id=restore_id,
            subject_hash=restore_plan_hash,
            expires_at=_now() + timedelta(seconds=APPROVAL_TTL_SECONDS),
        )

        receipt = _receipt(
            request_id=request_id,
            operation_id=request.plan_id,
            action=GovernanceMutationAction.APPLY,
            outcome=GovernanceMutationOutcome.APPLIED,
            control_id=plan.control_id,
            rule=rule,
            config_hash_before=current_hash,
            config_hash_after=new_hash,
            plan_hash=plan.plan_hash,
            approval_id=request.approval_id,
            reason_code="exact_governance_change_applied",
        )
        result = GovernanceChangeApplyResult(
            applied=True,
            control_id=plan.control_id,
            config_hash_before=current_hash,
            config_hash_after=new_hash,
            restore_id=restore_id,
            restore_plan_hash=restore_plan_hash,
            restore_approval_request_id=restore_approval_request_id,
            receipt=receipt,
        )
        return _envelope(
            status=EnvelopeStatus.OK,
            request_id=request_id,
            result_type="governance_change_apply",
            approval_state=ApprovalState.APPROVED,
            data={"apply_result": _model_payload(result)},
            warnings=["Authoritative Governance state must be re-read after this response."],
        )


def restore_governance_change(
    payload: GovernanceRestoreRequest | dict[str, Any],
) -> dict[str, Any]:
    request = payload if isinstance(payload, GovernanceRestoreRequest) else GovernanceRestoreRequest(**payload)
    request_id = _new_id("govreq")
    fallback_rule = fail_closed_governance_control_registry().default_rule

    with _STATE_LOCK:
        record = _RESTORES.get(request.restore_id)
        if record is None:
            return _blocked_action(
                request_id=request_id,
                operation_id=request.restore_id,
                action=GovernanceMutationAction.RESTORE,
                control_id="unknown",
                rule=fallback_rule,
                reason_code="unknown_restore_id",
                error="The Governance recovery record is unknown or no longer available.",
                config_hash=request.expected_config_hash,
                plan_hash=request.restore_plan_hash,
                approval_id=request.approval_id,
            )
        if record.used_at is not None:
            return _blocked_action(
                request_id=request_id,
                operation_id=request.restore_id,
                action=GovernanceMutationAction.RESTORE,
                control_id=record.control_id,
                rule=record.rule,
                reason_code="restore_already_used",
                error="This Governance recovery record has already been used.",
                config_hash=record.expected_config_hash,
                plan_hash=record.restore_plan_hash,
                approval_id=request.approval_id,
            )
        if not compare_digest(request.restore_plan_hash, record.restore_plan_hash):
            return _blocked_action(
                request_id=request_id,
                operation_id=request.restore_id,
                action=GovernanceMutationAction.RESTORE,
                control_id=record.control_id,
                rule=record.rule,
                reason_code="restore_plan_hash_mismatch",
                error="The Governance restore hash did not match the server-held recovery record.",
                config_hash=record.expected_config_hash,
                plan_hash=request.restore_plan_hash,
                approval_id=request.approval_id,
                outcome=GovernanceMutationOutcome.TAMPERED,
            )
        if not request.confirmed:
            return _blocked_action(
                request_id=request_id,
                operation_id=request.restore_id,
                action=GovernanceMutationAction.RESTORE,
                control_id=record.control_id,
                rule=record.rule,
                reason_code="explicit_confirmation_required",
                error="Explicit confirmation is required before restoring Governance law.",
                config_hash=record.expected_config_hash,
                plan_hash=record.restore_plan_hash,
                approval_id=request.approval_id,
            )

        _, current_hash = _read_authoritative_state()
        if (
            not compare_digest(request.expected_config_hash, record.expected_config_hash)
            or not compare_digest(current_hash, record.expected_config_hash)
        ):
            return _blocked_action(
                request_id=request_id,
                operation_id=request.restore_id,
                action=GovernanceMutationAction.RESTORE,
                control_id=record.control_id,
                rule=record.rule,
                reason_code="stale_config_hash",
                error="Authoritative Governance state changed after apply; restore was refused.",
                config_hash=current_hash,
                plan_hash=record.restore_plan_hash,
                approval_id=request.approval_id,
                outcome=GovernanceMutationOutcome.STALE,
            )

        approval = _APPROVAL_REQUESTS.get(record.approval_request_id)
        approval_error = _approval_failure(
            approval,
            approval_id=request.approval_id,
            approval_token=request.approval_token,
            action=GovernanceMutationAction.RESTORE,
            subject_id=request.restore_id,
            subject_hash=record.restore_plan_hash,
        )
        if approval_error:
            return _blocked_action(
                request_id=request_id,
                operation_id=request.restore_id,
                action=GovernanceMutationAction.RESTORE,
                control_id=record.control_id,
                rule=record.rule,
                reason_code=approval_error,
                error="The exact restore approval was missing, invalid, expired, or already used.",
                config_hash=current_hash,
                plan_hash=record.restore_plan_hash,
                approval_id=request.approval_id,
            )

        adapter = _YamlGovernanceMutationAdapter(record.rule)
        restored_value = adapter.restore(
            backup_path=record.backup_path,
            backup_hash=record.backup_hash,
            expected_value=record.applied_value,
        )
        if not _scalar_matches(restored_value, record.restored_value):
            raise RuntimeError("Governance restore did not recover the expected exact value.")
        _, new_hash = _read_authoritative_state()
        if approval is None:  # pragma: no cover - guarded above
            raise RuntimeError("Approval record disappeared during atomic restore.")
        approval.consumed_at = _now()
        record.used_at = _now()

        receipt = _receipt(
            request_id=request_id,
            operation_id=request.restore_id,
            action=GovernanceMutationAction.RESTORE,
            outcome=GovernanceMutationOutcome.RESTORED,
            control_id=record.control_id,
            rule=record.rule,
            config_hash_before=current_hash,
            config_hash_after=new_hash,
            plan_hash=record.restore_plan_hash,
            approval_id=request.approval_id,
            reason_code="exact_governance_change_restored",
        )
        result = GovernanceRestoreResult(
            restored=True,
            control_id=record.control_id,
            config_hash_before=current_hash,
            config_hash_after=new_hash,
            receipt=receipt,
        )
        return _envelope(
            status=EnvelopeStatus.OK,
            request_id=request_id,
            result_type="governance_change_restore",
            approval_state=ApprovalState.APPROVED,
            data={"restore_result": _model_payload(result)},
        )


def resolve_governance_approval(
    payload: ApprovalResolveRequest | dict[str, Any],
) -> dict[str, Any]:
    request = payload if isinstance(payload, ApprovalResolveRequest) else ApprovalResolveRequest(**payload)
    envelope_request_id = _new_id("govreq")
    decision = ApprovalDecision(
        request.decision.value
        if hasattr(request.decision, "value")
        else str(request.decision)
    )

    with _STATE_LOCK:
        record = _APPROVAL_REQUESTS.get(request.request_id)
        resolution_status = ApprovalResolutionStatus.ACCEPTED
        request_state = ApprovalRequestState.UNKNOWN
        approval_id: str | None = None
        approval_token: str | None = None
        expires_at_utc: str | None = None
        can_proceed = False
        next_action = "Refresh Governance state."
        notes: list[str] = []
        status = EnvelopeStatus.OK
        envelope_approval_state = ApprovalState.UNKNOWN

        if record is None:
            resolution_status = ApprovalResolutionStatus.REJECTED
            status = EnvelopeStatus.BLOCKED
            notes = ["The approval request is unknown; no authority changed."]
        elif _now() >= record.expires_at:
            record.state = ApprovalRequestState.EXPIRED
            resolution_status = ApprovalResolutionStatus.IGNORED
            request_state = ApprovalRequestState.EXPIRED
            status = EnvelopeStatus.BLOCKED
            envelope_approval_state = ApprovalState.DENIED
            notes = ["The approval request expired; create a fresh plan."]
        elif record.state is not ApprovalRequestState.PENDING:
            resolution_status = ApprovalResolutionStatus.IGNORED
            request_state = record.state
            status = EnvelopeStatus.BLOCKED
            envelope_approval_state = (
                ApprovalState.APPROVED
                if record.state is ApprovalRequestState.APPROVED
                else ApprovalState.DENIED
            )
            notes = ["The approval request was already resolved; no second token was issued."]
        elif decision is ApprovalDecision.APPROVED:
            record.state = ApprovalRequestState.APPROVED
            record.approval_id = _new_id("govapproval")
            record.token = token_urlsafe(32)
            request_state = record.state
            approval_id = record.approval_id
            approval_token = record.token
            expires_at_utc = _iso(record.expires_at)
            can_proceed = True
            next_action = "Apply the exact server-held plan before the approval expires."
            envelope_approval_state = ApprovalState.APPROVED
            notes = ["Approval is exact, expiring, and one-time; it grants no broader authority."]
        else:
            record.state = (
                ApprovalRequestState.DENIED
                if decision is ApprovalDecision.DENIED
                else ApprovalRequestState.CANCELLED
            )
            request_state = record.state
            envelope_approval_state = ApprovalState.DENIED
            next_action = "No Governance change may proceed from this approval request."
            notes = ["The exact Governance request remains unexecuted."]

        data_model = ApprovalResolveResponseData(
            request_id=request.request_id,
            resolution_status=resolution_status,
            decision=decision,
            resolver_identity=None,
            reason=None,
            resolved_at_utc=_iso(),
            request_state=request_state,
            approval_required=True,
            can_proceed=can_proceed,
            next_action=next_action,
            notes=notes,
            approval_id=approval_id,
            approval_token=approval_token,
            expires_at_utc=expires_at_utc,
        )
        return _envelope(
            status=status,
            request_id=envelope_request_id,
            result_type="approval_resolution",
            approval_state=envelope_approval_state,
            data={"approval_resolution": _model_payload(data_model)},
            errors=notes if status is EnvelopeStatus.BLOCKED else [],
        )


def clear_governance_mutation_state_for_tests() -> None:
    with _STATE_LOCK:
        _PLANS.clear()
        _APPROVAL_REQUESTS.clear()
        _RESTORES.clear()


__all__ = (
    "apply_governance_change",
    "clear_governance_mutation_state_for_tests",
    "plan_governance_change",
    "resolve_governance_approval",
    "restore_governance_change",
)
