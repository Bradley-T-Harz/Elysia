"""
Mode-profile posture loader for Elysia.

Mode profiles are posture law, not authority law. This module loads the
declarative mode profile config and normalizes it into compact runtime truth
that can safely shape planning, response style, and UI/trace surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover - exercised by fallback tests if needed
    yaml = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODE_PROFILE_CONFIG_PATH = PROJECT_ROOT / "config" / "modes" / "mode_profiles.yaml"
EXPECTED_MODE_KEYS = ("default", "tutor", "researcher", "writer", "coder")

SAFE_DEFAULTS = {
    "preferred_model_role": "primary_general",
    "response_style": "balanced",
    "explanation_depth": "medium",
    "citation_strictness": "medium",
    "math_execution_preference": "normal",
    "file_retrieval_preference": "normal",
    "repo_context_preference": "normal",
    "web_research_preference": "explicit_only",
    "approval_sensitivity": "normal",
    "output_format": "conversational",
}

AUTHORITY_LIKE_KEYS = {
    "shell_execution_allowed",
    "patch_application_allowed",
    "git_mutation_allowed",
    "dependency_install_allowed",
    "cloud_use_allowed",
    "private_context_outward_allowed",
    "external_code_worker_allowed_without_approval",
    "page_fetch_allowed_by_default",
}


@dataclass(frozen=True)
class ModeProfile:
    key: str
    label: str
    preferred_model_role: str
    response_style: str
    explanation_depth: str
    citation_strictness: str
    math_execution_preference: str
    file_retrieval_preference: str
    repo_context_preference: str
    web_research_preference: str
    approval_sensitivity: str
    output_format: str
    preferred_tools: tuple[str, ...]
    posture: dict[str, str]
    authority_granted_by_mode: bool
    warnings: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "used": True,
            "preferred_model_role": self.preferred_model_role,
            "response_style": self.response_style,
            "explanation_depth": self.explanation_depth,
            "citation_strictness": self.citation_strictness,
            "math_execution_preference": self.math_execution_preference,
            "file_retrieval_preference": self.file_retrieval_preference,
            "repo_context_preference": self.repo_context_preference,
            "web_research_preference": self.web_research_preference,
            "approval_sensitivity": self.approval_sensitivity,
            "output_format": self.output_format,
            "preferred_tools": list(self.preferred_tools),
            "posture": dict(self.posture),
            "authority_granted_by_mode": False,
            "warnings": list(self.warnings),
        }

    def compact_effects(self) -> list[str]:
        effects = [
            f"explanation_depth:{self.explanation_depth}",
            f"citation_strictness:{self.citation_strictness}",
            f"math:{self.math_execution_preference}",
            f"files:{self.file_retrieval_preference}",
            f"repo:{self.repo_context_preference}",
            f"web:{self.web_research_preference}",
            f"approval:{self.approval_sensitivity}",
            f"output:{self.output_format}",
        ]
        return effects


def _coerce_string(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _coerce_string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()

    normalized: list[str] = []
    for item in value:
        text = _coerce_string(item)
        if text:
            normalized.append(text)
    return tuple(normalized)


def _coerce_string_mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}

    return {
        str(key): _coerce_string(raw_value)
        for key, raw_value in value.items()
        if _coerce_string(raw_value)
    }


def _style_summary(value: Any) -> str:
    if isinstance(value, dict):
        return _coerce_string(value.get("summary"), SAFE_DEFAULTS["response_style"])
    return _coerce_string(value, SAFE_DEFAULTS["response_style"])


def _default_profile(key: str, warnings: list[str] | None = None) -> ModeProfile:
    label = key.replace("_", " ").title() if key else "Default"
    return ModeProfile(
        key=key or "default",
        label=label,
        preferred_model_role=SAFE_DEFAULTS["preferred_model_role"],
        response_style=SAFE_DEFAULTS["response_style"],
        explanation_depth=SAFE_DEFAULTS["explanation_depth"],
        citation_strictness=SAFE_DEFAULTS["citation_strictness"],
        math_execution_preference=SAFE_DEFAULTS["math_execution_preference"],
        file_retrieval_preference=SAFE_DEFAULTS["file_retrieval_preference"],
        repo_context_preference=SAFE_DEFAULTS["repo_context_preference"],
        web_research_preference=SAFE_DEFAULTS["web_research_preference"],
        approval_sensitivity=SAFE_DEFAULTS["approval_sensitivity"],
        output_format=SAFE_DEFAULTS["output_format"],
        preferred_tools=(),
        posture={},
        authority_granted_by_mode=False,
        warnings=tuple(warnings or ()),
    )


def _normalize_profile(key: str, raw_profile: Any) -> ModeProfile:
    warnings: list[str] = []
    if not isinstance(raw_profile, dict):
        warnings.append(f"Mode profile '{key}' was malformed; safe defaults were used.")
        return _default_profile(key, warnings)

    boundaries = raw_profile.get("boundaries", {})
    if isinstance(boundaries, dict):
        inert_keys = sorted(AUTHORITY_LIKE_KEYS.intersection(boundaries.keys()))
        if inert_keys:
            warnings.append(
                "Authority-like boundary fields are treated as inert posture only: "
                + ", ".join(inert_keys)
            )

    posture = _coerce_string_mapping(raw_profile.get("posture", {}))

    return ModeProfile(
        key=key,
        label=_coerce_string(raw_profile.get("label"), key.title()),
        preferred_model_role=_coerce_string(
            raw_profile.get("preferred_model_role"),
            SAFE_DEFAULTS["preferred_model_role"],
        ),
        response_style=_style_summary(raw_profile.get("response_style")),
        explanation_depth=_coerce_string(
            raw_profile.get("explanation_depth"),
            SAFE_DEFAULTS["explanation_depth"],
        ),
        citation_strictness=_coerce_string(
            raw_profile.get("citation_strictness"),
            SAFE_DEFAULTS["citation_strictness"],
        ),
        math_execution_preference=_coerce_string(
            raw_profile.get("math_execution_preference"),
            SAFE_DEFAULTS["math_execution_preference"],
        ),
        file_retrieval_preference=_coerce_string(
            raw_profile.get("file_retrieval_preference"),
            SAFE_DEFAULTS["file_retrieval_preference"],
        ),
        repo_context_preference=_coerce_string(
            raw_profile.get("repo_context_preference"),
            SAFE_DEFAULTS["repo_context_preference"],
        ),
        web_research_preference=_coerce_string(
            raw_profile.get("web_research_preference"),
            SAFE_DEFAULTS["web_research_preference"],
        ),
        approval_sensitivity=_coerce_string(
            raw_profile.get("approval_sensitivity"),
            SAFE_DEFAULTS["approval_sensitivity"],
        ),
        output_format=_coerce_string(
            raw_profile.get("output_format"),
            SAFE_DEFAULTS["output_format"],
        ),
        preferred_tools=_coerce_string_list(raw_profile.get("preferred_tools")),
        posture=posture,
        authority_granted_by_mode=False,
        warnings=tuple(warnings),
    )


def load_mode_profiles(
    config_path: str | Path = DEFAULT_MODE_PROFILE_CONFIG_PATH,
) -> dict[str, ModeProfile]:
    path = Path(config_path)
    warnings: list[str] = []

    if yaml is None:
        warnings.append("PyYAML is unavailable; safe default mode profiles were used.")
        return {
            key: _default_profile(key, warnings if key == "default" else [])
            for key in EXPECTED_MODE_KEYS
        }

    try:
        raw_payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warning = f"Mode profile config could not be loaded: {exc}"
        return {
            key: _default_profile(key, [warning] if key == "default" else [])
            for key in EXPECTED_MODE_KEYS
        }

    if not isinstance(raw_payload, dict):
        warning = "Mode profile config root was malformed; safe defaults were used."
        return {
            key: _default_profile(key, [warning] if key == "default" else [])
            for key in EXPECTED_MODE_KEYS
        }

    raw_modes = raw_payload.get("modes", {})
    if not isinstance(raw_modes, dict):
        raw_modes = {}

    profiles: dict[str, ModeProfile] = {}
    for key in EXPECTED_MODE_KEYS:
        if key not in raw_modes:
            profiles[key] = _default_profile(
                key,
                [f"Expected mode profile '{key}' is missing; safe defaults were used."],
            )
            continue
        profiles[key] = _normalize_profile(key, raw_modes.get(key))

    return profiles


def resolve_mode_profile(
    requested_mode: str | None,
    *,
    config_path: str | Path = DEFAULT_MODE_PROFILE_CONFIG_PATH,
) -> ModeProfile:
    profiles = load_mode_profiles(config_path)
    requested_key = _coerce_string(requested_mode, "default").lower()
    if requested_key in profiles:
        return profiles[requested_key]

    default_profile = profiles.get("default", _default_profile("default"))
    warnings = list(default_profile.warnings)
    warnings.append(
        f"Unknown mode profile '{requested_key}' requested; default profile was used."
    )
    return ModeProfile(
        **{
            **default_profile.__dict__,
            "warnings": tuple(warnings),
        }
    )


__all__ = (
    "DEFAULT_MODE_PROFILE_CONFIG_PATH",
    "EXPECTED_MODE_KEYS",
    "ModeProfile",
    "load_mode_profiles",
    "resolve_mode_profile",
)
