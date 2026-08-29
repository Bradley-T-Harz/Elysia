"""Fail-closed mutability registry for surfaced Governance controls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except Exception:  # pragma: no cover - defensive environment guard
    yaml = None


REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "config" / "governance" / "control_registry.yaml"


class GovernanceMutationClassification(str, Enum):
    SAFE_LIVE_EDITABLE_NOW = "safe-live-editable-now"
    PLAN_ONLY = "plan-only"
    READ_ONLY_CONSTITUTIONAL = "read-only-constitutional"
    PROFILE_GATED_LATER = "profile-gated-later"
    LAB_GATED_LATER = "lab-gated-later"
    HARD_PROHIBITED_BY_DEFAULT = "hard-prohibited-by-default"


class GovernanceMutationRisk(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class GovernanceControlRule:
    rule_id: str
    classification: GovernanceMutationClassification
    risk: GovernanceMutationRisk
    reason: str
    later_gate: str | None = None
    exact: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()
    allowed_values: tuple[str | bool | int | float | None, ...] = ()
    target_relative_path: str | None = None
    yaml_key_path: tuple[str, ...] = ()

    @property
    def mutation_allowed(self) -> bool:
        return (
            self.classification
            is GovernanceMutationClassification.SAFE_LIVE_EDITABLE_NOW
            and bool(self.target_relative_path)
            and bool(self.yaml_key_path)
            and bool(self.allowed_values)
        )


@dataclass(frozen=True)
class GovernanceControlRegistry:
    contract_version: str
    default_rule: GovernanceControlRule
    rules: tuple[GovernanceControlRule, ...]

    def rule_for(self, control_id: str) -> GovernanceControlRule:
        for rule in self.rules:
            if control_id in rule.exact:
                return rule
        for rule in self.rules:
            if any(control_id.startswith(prefix) for prefix in rule.prefixes):
                return rule
        return self.default_rule


def fail_closed_governance_control_registry() -> GovernanceControlRegistry:
    """Return an in-code safety floor when the tracked registry is unavailable."""
    default_rule = GovernanceControlRule(
        rule_id="default_fail_closed",
        classification=GovernanceMutationClassification.READ_ONLY_CONSTITUTIONAL,
        risk=GovernanceMutationRisk.CRITICAL,
        reason="Governance registry truth is unavailable, so mutation fails closed.",
        later_gate="Restore and validate the tracked registry before planning any change.",
    )
    return GovernanceControlRegistry(
        contract_version="governance-mutation-contract-unavailable",
        default_rule=default_rule,
        rules=(),
    )


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _parse_rule(raw: Any, *, fallback_id: str) -> GovernanceControlRule:
    if not isinstance(raw, dict):
        raise ValueError(f"Governance registry rule {fallback_id!r} must be a mapping.")

    rule_id = str(raw.get("rule_id") or fallback_id).strip()
    reason = str(raw.get("reason") or "").strip()
    if not rule_id or not reason:
        raise ValueError("Every governance registry rule requires a rule_id and reason.")

    classification = GovernanceMutationClassification(str(raw.get("classification") or ""))
    risk = GovernanceMutationRisk(str(raw.get("risk") or ""))
    allowed_values_raw = raw.get("allowed_values")
    allowed_values = (
        tuple(allowed_values_raw)
        if isinstance(allowed_values_raw, list)
        else ()
    )

    return GovernanceControlRule(
        rule_id=rule_id,
        classification=classification,
        risk=risk,
        reason=reason,
        later_gate=str(raw.get("later_gate") or "").strip() or None,
        exact=_string_tuple(raw.get("exact")),
        prefixes=_string_tuple(raw.get("prefix")),
        allowed_values=allowed_values,
        target_relative_path=str(raw.get("target_relative_path") or "").strip() or None,
        yaml_key_path=_string_tuple(raw.get("yaml_key_path")),
    )


@lru_cache(maxsize=4)
def load_governance_control_registry(
    path: Path | None = None,
) -> GovernanceControlRegistry:
    """Load the tracked registry. Any invalid registry fails closed."""
    resolved_path = Path(path or REGISTRY_PATH)
    if yaml is None:
        raise RuntimeError("PyYAML is required to load the governance control registry.")

    raw = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Governance control registry must be a mapping.")

    contract_version = str(raw.get("contract_version") or "").strip()
    if not contract_version:
        raise ValueError("Governance control registry requires contract_version.")

    default_rule = _parse_rule(raw.get("default_rule"), fallback_id="default_fail_closed")
    rules_raw = raw.get("rules")
    if not isinstance(rules_raw, list) or not rules_raw:
        raise ValueError("Governance control registry requires at least one rule.")

    rules = tuple(
        _parse_rule(item, fallback_id=f"rule_{index}")
        for index, item in enumerate(rules_raw)
    )
    registry = GovernanceControlRegistry(
        contract_version=contract_version,
        default_rule=default_rule,
        rules=rules,
    )

    for rule in registry.rules:
        if any(
            type(value) not in {str, bool, int, float, type(None)}
            for value in rule.allowed_values
        ):
            raise ValueError("Governance allowed_values must contain scalars only.")
        if rule.mutation_allowed and rule.risk is not GovernanceMutationRisk.LOW:
            raise ValueError("Only low-risk controls may be safe-live-editable-now.")
        if (
            rule.classification
            is GovernanceMutationClassification.SAFE_LIVE_EDITABLE_NOW
            and not rule.mutation_allowed
        ):
            raise ValueError(
                "safe-live-editable-now rules require an exact target, key path, and allowed values."
            )
        if rule.mutation_allowed and (len(rule.exact) != 1 or rule.prefixes):
            raise ValueError("Live-editable rules must bind exactly one explicit control ID.")

    return registry


def governance_config_hash(
    controls: Iterable[dict[str, Any]],
    *,
    registry: GovernanceControlRegistry | None = None,
) -> str:
    """Hash only compact authoritative control truth; omit paths and private payloads."""
    resolved_registry = registry or load_governance_control_registry()
    normalized: list[dict[str, Any]] = []
    for control in controls:
        control_id = str(control.get("control_id") or "").strip()
        if not control_id:
            continue
        rule = resolved_registry.rule_for(control_id)
        normalized.append(
            {
                "control_id": control_id,
                "value": control.get("value"),
                "classification": rule.classification.value,
                "risk": rule.risk.value,
            }
        )
    payload = {
        "contract_version": resolved_registry.contract_version,
        "controls": sorted(normalized, key=lambda item: item["control_id"]),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(canonical.encode("utf-8")).hexdigest()


__all__ = (
    "GovernanceControlRegistry",
    "GovernanceControlRule",
    "GovernanceMutationClassification",
    "GovernanceMutationRisk",
    "fail_closed_governance_control_registry",
    "governance_config_hash",
    "load_governance_control_registry",
)
