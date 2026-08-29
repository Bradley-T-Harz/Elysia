"""
Elysia planner scaffold.

This module builds a small structured plan from intent, mode, selected
skill, and gathered context. It still does not authorize execution.

At this stage, the planner also begins explicit scaffold memory-class
reasoning in a backward-compatible way.
"""

import re
from typing import Any, Dict, List, Optional

from .mode_profile_loader import ModeProfile, resolve_mode_profile


_SENSITIVE_MEMORY_CLASSES = {
    "sealed_private_memory",
    "audit_memory",
}


def _coerce_string_list(values: Any) -> List[str]:
    """
    Normalize a value into a clean list of strings.
    """
    if values is None:
        return []

    if isinstance(values, (list, tuple)):
        normalized: List[str] = []

        for value in values:
            text = str(value).strip()
            if text:
                normalized.append(text)

        return normalized

    text = str(values).strip()
    return [text] if text else []


def _normalize_memory_class_name(value: Any, fallback: str = "") -> str:
    """
    Normalize one memory-class name into a clean string.
    """
    text = str(value or "").strip()
    return text if text else fallback


def _scaffold_mode_memory_class_defaults(mode: str) -> Dict[str, Any]:
    """
    Provide scaffold fallback memory-class defaults by mode.

    These defaults are intentionally aligned with the declared
    scaffold_memory_classes config and act as a planner-side fallback until
    runtime passes fully resolved memory-class policy into the planner.
    """
    defaults = {
        "default": {
            "primary_memory_class": "conversation_memory",
            "default_memory_class": "conversation_memory",
            "fallback_memory_class": "working_memory",
            "allowed_memory_classes": [
                "working_memory",
                "conversation_memory",
                "preference_memory",
            ],
            "disallowed_memory_classes": [],
        },
        "tutor": {
            "primary_memory_class": "working_memory",
            "default_memory_class": "conversation_memory",
            "fallback_memory_class": "working_memory",
            "allowed_memory_classes": [
                "working_memory",
                "conversation_memory",
                "preference_memory",
                "project_memory",
            ],
            "disallowed_memory_classes": [],
        },
        "researcher": {
            "primary_memory_class": "research_memory",
            "default_memory_class": "research_memory",
            "fallback_memory_class": "working_memory",
            "allowed_memory_classes": [
                "working_memory",
                "research_memory",
                "project_memory",
                "preference_memory",
                "operational_memory",
            ],
            "disallowed_memory_classes": [],
        },
        "writer": {
            "primary_memory_class": "project_memory",
            "default_memory_class": "project_memory",
            "fallback_memory_class": "working_memory",
            "allowed_memory_classes": [
                "working_memory",
                "conversation_memory",
                "project_memory",
                "preference_memory",
            ],
            "disallowed_memory_classes": [],
        },
    }

    return dict(defaults.get(str(mode), defaults["default"]))


def _resolve_memory_class_plan(
    mode: str,
    context: Dict[str, Any],
    retrieved_memory_count: int,
    memory_context_source: str,
    memory_class_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Resolve scaffold memory-class planning fields.

    Order of preference:
    1. explicit planner/runtime memory_class_policy values
    2. explicit context-provided values
    3. current retrieval-mode inference for local session memory
    4. scaffold mode defaults
    """
    policy = dict(memory_class_policy or {})
    defaults = _scaffold_mode_memory_class_defaults(mode)

    primary_memory_class = _normalize_memory_class_name(
        policy.get(
            "primary_memory_class",
            context.get(
                "primary_memory_class",
                defaults["primary_memory_class"],
            ),
        ),
        defaults["primary_memory_class"],
    )
    default_memory_class = _normalize_memory_class_name(
        policy.get(
            "default_memory_class",
            context.get(
                "default_memory_class",
                defaults["default_memory_class"],
            ),
        ),
        defaults["default_memory_class"],
    )
    fallback_memory_class = _normalize_memory_class_name(
        policy.get(
            "fallback_memory_class",
            context.get(
                "fallback_memory_class",
                defaults["fallback_memory_class"],
            ),
        ),
        defaults["fallback_memory_class"],
    )

    allowed_memory_classes = _coerce_string_list(
        policy.get(
            "allowed_memory_classes",
            context.get(
                "allowed_memory_classes",
                defaults["allowed_memory_classes"],
            ),
        )
    )
    disallowed_memory_classes = _coerce_string_list(
        policy.get(
            "disallowed_memory_classes",
            context.get(
                "disallowed_memory_classes",
                defaults["disallowed_memory_classes"],
            ),
        )
    )

    forced_memory_class = _normalize_memory_class_name(
        policy.get(
            "forced_memory_class",
            context.get("forced_memory_class", ""),
        )
    )
    explicit_memory_class = _normalize_memory_class_name(
        context.get("memory_class", "")
    )

    if forced_memory_class:
        memory_class = forced_memory_class
        memory_class_source = "forced_memory_class"
    elif explicit_memory_class:
        memory_class = explicit_memory_class
        memory_class_source = "context_memory_class"
    elif (
        retrieved_memory_count > 0
        and memory_context_source.startswith("local_session_journal_scaffold")
    ):
        memory_class = "working_memory"
        memory_class_source = "retrieval_mode_local_session_memory"
    elif primary_memory_class:
        memory_class = primary_memory_class
        memory_class_source = "primary_memory_class"
    elif default_memory_class:
        memory_class = default_memory_class
        memory_class_source = "default_memory_class"
    else:
        memory_class = fallback_memory_class
        memory_class_source = "fallback_memory_class"

    memory_class_boundary_sensitive = memory_class in _SENSITIVE_MEMORY_CLASSES
    memory_class_requires_boundary_check = (
        memory_class_boundary_sensitive or bool(forced_memory_class)
    )

    return {
        "memory_class": memory_class,
        "primary_memory_class": primary_memory_class,
        "default_memory_class": default_memory_class,
        "fallback_memory_class": fallback_memory_class,
        "allowed_memory_classes": allowed_memory_classes,
        "disallowed_memory_classes": disallowed_memory_classes,
        "forced_memory_class": forced_memory_class,
        "memory_class_source": memory_class_source,
        "memory_class_declared": bool(memory_class),
        "memory_class_boundary_sensitive": memory_class_boundary_sensitive,
        "memory_class_requires_boundary_check": memory_class_requires_boundary_check,
    }


def _clean_math_expression(value: Any) -> str:
    """
    Clean one candidate math expression for the bounded local math lane.
    """
    expression = str(value or "").strip()
    expression = expression.rstrip(".?!")
    return expression.strip()


def _extract_variable_from_text(text: str, fallback: str = "x") -> str:
    """
    Extract a simple variable name from user text when present.
    """
    lowered = text.lower()

    match = re.search(r"(?:with respect to|respect to|for variable|variable)\s+([a-zA-Z])\b", lowered)
    if match:
        return match.group(1)

    match = re.search(r"\bd/d([a-zA-Z])\b", lowered)
    if match:
        return match.group(1)

    return fallback


def _number_text_to_expression_value(value: str) -> str:
    """
    Normalize a human-formatted number into a math-expression-safe value.
    """
    return re.sub(r"[\s,]+", "", str(value or "").strip())


def _percentage_reduction_expression(request_text: str) -> str:
    """
    Detect narrow percent-off / percent-reduction phrasing before generic
    expression extraction sees prose like "15 percent off 3 600".
    """
    number_pattern = r"(\d[\d\s,]*(?:\.\d+)?)"
    percent_pattern = r"(\d+(?:\.\d+)?)\s*(?:percent|%)"
    patterns = (
        # "15 percent off 3 600" / "15% off 3600"
        rf"{percent_pattern}\s+off\s+(?:of\s+)?{number_pattern}",
        # "15 percent reduction from 3 600"
        rf"{percent_pattern}\s+reduction\s+(?:from|of|on)\s+{number_pattern}",
        # "from 3 600 units after a 15 percent reduction"
        rf"\b(?:starts?\s+at|begin(?:s)?\s+with|from)\s+{number_pattern}\s*(?:units?)?.*?{percent_pattern}\s+reduction",
        # "3 600 reduced by 15 percent"
        rf"{number_pattern}\s*(?:units?)?\s+(?:is\s+|was\s+|are\s+|were\s+)?reduced\s+by\s+{percent_pattern}",
        # "reduced by 15 percent from 3 600"
        rf"reduced\s+by\s+{percent_pattern}\s+(?:from|of|on)\s+{number_pattern}",
    )

    for index, pattern in enumerate(patterns):
        match = re.search(pattern, request_text, flags=re.IGNORECASE)
        if not match:
            continue

        groups = match.groups()
        if index in {0, 1}:
            percent, amount = groups[0], groups[1]
        elif index == 2:
            amount, percent = groups[0], groups[1]
        elif index == 3:
            amount, percent = groups[0], groups[1]
        else:
            percent, amount = groups[0], groups[1]

        normalized_amount = _number_text_to_expression_value(amount)
        normalized_percent = _number_text_to_expression_value(percent)
        if normalized_amount and normalized_percent:
            return f"{normalized_amount} * (1 - {normalized_percent}/100)"

    amount_match = re.search(
        r"\b(?:starts?\s+at|begin(?:s)?\s+with|from)\s+(\d[\d\s,]*(?:\.\d+)?)\s*(?:units?)?",
        request_text,
        flags=re.IGNORECASE,
    )
    percent_match = re.search(
        r"(?:reduced\s+by\s+(\d+(?:\.\d+)?)\s*(?:percent|%)|(\d+(?:\.\d+)?)\s*(?:percent|%)\s+reduction)",
        request_text,
        flags=re.IGNORECASE,
    )
    if amount_match and percent_match:
        normalized_amount = _number_text_to_expression_value(amount_match.group(1))
        normalized_percent = _number_text_to_expression_value(
            percent_match.group(1) or percent_match.group(2) or ""
        )
        if normalized_amount and normalized_percent:
            return f"{normalized_amount} * (1 - {normalized_percent}/100)"

    return ""


def _detect_bounded_math_execution_candidate(
    *,
    intent: Dict[str, Any],
    mode: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Detect narrow v0 math-execution candidates.

    This is intentionally conservative. It recognizes explicit evaluate,
    calculate, differentiate, integrate, solve, and numeric-check requests.
    It does not authorize general execution and does not try to parse broad
    tutoring questions like "explain derivatives step by step."
    """
    request_text = str(
        context.get("request_text")
        or context.get("full_request_text")
        or context.get("request_summary", "")
        or ""
    ).strip()
    lowered = request_text.lower()
    primary_intent = str(intent.get("primary", "") or "").strip().lower()
    normalized_mode = str(mode or "").strip().lower()

    base = {
        "bounded_math_execution_candidate": False,
        "math_execution_operation": "",
        "math_execution_expression": "",
        "math_execution_variable": "x",
        "math_execution_expected": None,
        "math_execution_reason": "",
    }

    if not request_text:
        return base

    allowed_context = (
        primary_intent in {"tutoring", "conversation", "writing", "unknown"}
        or normalized_mode in {"tutor", "writer", "default", "companion"}
    )

    if not allowed_context:
        return base

    percentage_expression = _percentage_reduction_expression(request_text)
    if percentage_expression:
        return {
            **base,
            "bounded_math_execution_candidate": True,
            "math_execution_operation": "evaluate",
            "math_execution_expression": percentage_expression,
            "math_execution_reason": "percentage_reduction_request",
        }

    # Numeric check examples:
    # "check whether (4.0875 - 3.27) / 4.0875 * 100 equals 20"
    # "check if 2 + 2 = 4"
    check_match = re.search(
        r"\b(?:check|verify)\b.*?(?:whether|if)?\s*(.+?)\s*(?:equals|=|is)\s*(-?\d+(?:\.\d+)?)\s*$",
        request_text,
        flags=re.IGNORECASE,
    )
    if check_match:
        expression = _clean_math_expression(check_match.group(1))
        expected = _clean_math_expression(check_match.group(2))
        if expression and expected:
            return {
                **base,
                "bounded_math_execution_candidate": True,
                "math_execution_operation": "check_numeric_result",
                "math_execution_expression": expression,
                "math_execution_expected": expected,
                "math_execution_reason": "explicit_numeric_check_request",
            }

    # Simplify examples:
    # "Simplify 2*x + 3*x."
    simplify_match = re.search(
        r"\b(?:simplify|reduce)\b\s*:?\s*(.+)$",
        request_text,
        flags=re.IGNORECASE,
    )
    if simplify_match:
        expression = _clean_math_expression(simplify_match.group(1))
        if expression:
            return {
                **base,
                "bounded_math_execution_candidate": True,
                "math_execution_operation": "simplify",
                "math_execution_expression": expression,
                "math_execution_reason": "explicit_simplify_request",
            }

    # Evaluate/calculate/compute examples:
    # "Evaluate (4.0875 - 3.27) / 4.0875 * 100."
    eval_match = re.search(
        r"\b(?:evaluate|calculate|compute)\b\s*:?\s*(.+)$",
        request_text,
        flags=re.IGNORECASE,
    )
    if eval_match:
        expression = _clean_math_expression(eval_match.group(1))
        if expression:
            return {
                **base,
                "bounded_math_execution_candidate": True,
                "math_execution_operation": "evaluate",
                "math_execution_expression": expression,
                "math_execution_reason": "explicit_evaluate_request",
            }

    # Differentiate examples:
    # "Differentiate x^2 + 3*x with respect to x."
    diff_match = re.search(
        r"\b(?:differentiate|derive the derivative of|find the derivative of)\b\s*:?\s*(.+)$",
        request_text,
        flags=re.IGNORECASE,
    )
    if diff_match:
        expression = _clean_math_expression(
            re.split(
                r"\b(?:with respect to|respect to|for variable|variable)\b",
                diff_match.group(1),
                flags=re.IGNORECASE,
            )[0]
        )
        if expression:
            return {
                **base,
                "bounded_math_execution_candidate": True,
                "math_execution_operation": "differentiate",
                "math_execution_expression": expression,
                "math_execution_variable": _extract_variable_from_text(request_text),
                "math_execution_reason": "explicit_differentiate_request",
            }

    # Integrate examples:
    # "Integrate 2*x with respect to x."
    integrate_match = re.search(
        r"\b(?:integrate|find the integral of)\b\s*:?\s*(.+)$",
        request_text,
        flags=re.IGNORECASE,
    )
    if integrate_match:
        expression = _clean_math_expression(
            re.split(
                r"\b(?:with respect to|respect to|for variable|variable|dx)\b",
                integrate_match.group(1),
                flags=re.IGNORECASE,
            )[0]
        )
        if expression:
            return {
                **base,
                "bounded_math_execution_candidate": True,
                "math_execution_operation": "integrate",
                "math_execution_expression": expression,
                "math_execution_variable": _extract_variable_from_text(request_text),
                "math_execution_reason": "explicit_integrate_request",
            }

    # Solve examples:
    # "Solve x + 2 = 5 for x."
    solve_match = re.search(
        r"\bsolve\b\s*:?\s*(.+)$",
        request_text,
        flags=re.IGNORECASE,
    )
    if solve_match:
        expression = _clean_math_expression(
            re.split(
                r"\bfor\s+[a-zA-Z]\b",
                solve_match.group(1),
                flags=re.IGNORECASE,
            )[0]
        )
        if expression:
            return {
                **base,
                "bounded_math_execution_candidate": True,
                "math_execution_operation": "solve",
                "math_execution_expression": expression,
                "math_execution_variable": _extract_variable_from_text(request_text),
                "math_execution_reason": "explicit_solve_request",
            }

    return base


def _resolve_context_mode_profile(mode: str, context: Dict[str, Any]) -> ModeProfile:
    raw_profile = context.get("mode_profile")
    if isinstance(raw_profile, ModeProfile):
        return raw_profile

    if isinstance(raw_profile, dict):
        try:
            return ModeProfile(
                key=str(raw_profile.get("key") or mode or "default"),
                label=str(raw_profile.get("label") or mode or "Default"),
                preferred_model_role=str(raw_profile.get("preferred_model_role") or "primary_general"),
                response_style=str(raw_profile.get("response_style") or "balanced"),
                explanation_depth=str(raw_profile.get("explanation_depth") or "medium"),
                citation_strictness=str(raw_profile.get("citation_strictness") or "medium"),
                math_execution_preference=str(raw_profile.get("math_execution_preference") or "normal"),
                file_retrieval_preference=str(raw_profile.get("file_retrieval_preference") or "normal"),
                repo_context_preference=str(raw_profile.get("repo_context_preference") or "normal"),
                web_research_preference=str(raw_profile.get("web_research_preference") or "explicit_only"),
                approval_sensitivity=str(raw_profile.get("approval_sensitivity") or "normal"),
                output_format=str(raw_profile.get("output_format") or "conversational"),
                preferred_tools=tuple(str(value) for value in raw_profile.get("preferred_tools", []) or []),
                posture={
                    str(key): str(value)
                    for key, value in dict(raw_profile.get("posture", {}) or {}).items()
                },
                authority_granted_by_mode=False,
                warnings=tuple(str(value) for value in raw_profile.get("warnings", []) or []),
            )
        except Exception:
            pass

    return resolve_mode_profile(mode)


def _mode_profile_planning_steps(profile: ModeProfile) -> list[str]:
    key = profile.key
    if key == "tutor":
        return [
            "apply Tutor posture: teach step by step",
            "prefer bounded local math checks when a calculation is present",
            "separate assumptions from the final answer",
        ]
    if key == "researcher":
        return [
            "apply Researcher posture: distinguish evidence, inference, and unknowns",
            "prefer evidence packets when public research is explicitly requested",
            "keep private context out of outward research boundaries",
        ]
    if key == "writer":
        return [
            "apply Writer posture: preserve requested voice and tone",
            "check numeric claims quietly when they are present",
            "avoid bloated explanation when polished prose is requested",
        ]
    if key == "coder":
        return [
            "apply Coder posture: prefer read-only repo context when relevant",
            "use proposal-only patch planning when explicit files are named",
            "keep mutation, shell, git, package install, and worker execution ungranted",
        ]
    return ["apply Default posture: concise, grounded, practical response"]


def _detect_hard_blocked_request(request_text: str) -> Dict[str, Any]:
    """
    Detect narrow requests that must be blocked before model/tool action.

    This is a deterministic Sprint 12 safety check, not a new execution organ.
    It catches requests that combine private/vault context with external web or
    direct mutation/worker asks, plus explicit destructive repo/file deletion
    requests that must not proceed through ordinary Coder context gathering.
    """
    lowered = str(request_text or "").lower()
    reasons: List[str] = []

    private_markers = (
        "vault",
        "private vault",
        "private memory",
        "private notes",
        "secret",
        "secrets",
        ".env",
        "ssh key",
        "id_rsa",
        "id_ed25519",
    )
    outward_markers = (
        "search the web",
        "web search",
        "public web",
        "internet",
        "online",
        "searxng",
    )
    mutation_worker_markers = (
        "directly edit",
        "edit files",
        "modify files",
        "write files",
        "apply patch",
        "under vault",
    )
    destructive_mutation_markers = (
        "delete this repo",
        "delete the repo",
        "delete this repository",
        "delete the repository",
        "delete my repo",
        "remove this repo",
        "remove the repo",
        "remove this repository",
        "wipe this repo",
        "wipe the repo",
        "destroy this repo",
        "destroy the repo",
        "rm -rf",
    )

    touches_private = any(marker in lowered for marker in private_markers)
    touches_outward = any(marker in lowered for marker in outward_markers)
    asks_mutation_worker = any(marker in lowered for marker in mutation_worker_markers)
    asks_destructive_mutation = any(
        marker in lowered for marker in destructive_mutation_markers
    )

    if touches_private and touches_outward:
        reasons.append("private or vault context must not be sent to public web research")

    if touches_private and asks_mutation_worker:
        reasons.append("vault/private paths must not be edited or handed to coding workers")

    if touches_outward and asks_mutation_worker and "aider" in lowered:
        reasons.append("web research and Aider mutation cannot be combined in the current governed path")

    if asks_destructive_mutation:
        reasons.append(
            "destructive repo or file deletion requests are blocked before Coder tools"
        )

    if not reasons:
        return {
            "hard_blocked_request": False,
            "block_reasons": [],
            "touches_external_network": False,
            "writes_files": False,
            "reads_private_memory": False,
        }

    return {
        "hard_blocked_request": True,
        "block_reasons": reasons,
        "touches_external_network": touches_outward,
        "writes_files": asks_mutation_worker or asks_destructive_mutation,
        "reads_private_memory": touches_private,
    }



def _coerce_attached_file_bool(value: Any, default: bool) -> bool:
    """
    Coerce attached-file truth fields from UI/API context.
    """
    if isinstance(value, bool):
        return value

    if value is None:
        return default

    if isinstance(value, str):
        lowered = value.strip().lower()

        if lowered in {"true", "1", "yes", "on", "ready"}:
            return True

        if lowered in {"false", "0", "no", "off", "blocked"}:
            return False

    return bool(value)


def _attached_file_text(record: Dict[str, Any], *keys: str) -> str:
    """
    Extract the first non-empty string-like value from an attached-file record.
    """
    for key in keys:
        value = record.get(key)
        text = str(value or "").strip()
        if text:
            return text

    return ""


def _attached_file_records_from_context(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Gather attached-file records from known context seams.

    Runtime v0 accepts attached files only from structured context. It does not
    read arbitrary file paths from user text.
    """
    records: List[Dict[str, Any]] = []

    for key in (
        "attached_data_files",
        "attached_files",
        "attached_context_files",
    ):
        values = context.get(key)

        if isinstance(values, list):
            for value in values:
                if isinstance(value, dict):
                    records.append(dict(value))

    return records


def _attached_file_source_path(record: Dict[str, Any]) -> str:
    """
    Extract a local source path from a trusted attached-file record.
    """
    return _attached_file_text(
        record,
        "source_path",
        "local_path",
        "stored_path",
        "copied_path",
        "path",
    )


def _attached_file_name(record: Dict[str, Any]) -> str:
    """
    Extract a display file name from a trusted attached-file record.
    """
    return _attached_file_text(
        record,
        "file_name",
        "display_name",
        "name",
        "filename",
    )


def _attached_file_kind(record: Dict[str, Any]) -> str:
    """
    Extract or infer a simple file kind from attached-file metadata.
    """
    explicit_kind = _attached_file_text(
        record,
        "file_kind",
        "kind",
        "extension",
        "mime_type",
        "content_type",
    ).lower()

    if explicit_kind:
        return explicit_kind

    file_name = _attached_file_name(record).lower()
    source_path = _attached_file_source_path(record).lower()

    if file_name.endswith(".csv") or source_path.endswith(".csv"):
        return "csv"

    if file_name.endswith(".xlsx") or source_path.endswith(".xlsx"):
        return "xlsx"

    return ""


def _attached_file_is_ready_context(record: Dict[str, Any]) -> bool:
    """
    Decide whether an attached file is eligible for bounded context use.
    """
    ready = _coerce_attached_file_bool(record.get("ready"), True)
    usable_as_context = _coerce_attached_file_bool(
        record.get("usable_as_context"),
        True,
    )
    blocked = _coerce_attached_file_bool(record.get("blocked"), False)

    processing_state = _attached_file_text(record, "processing_state", "state").lower()
    if processing_state in {"blocked", "failed", "error"}:
        blocked = True

    if processing_state in {"ready", "completed", "usable"}:
        ready = True

    return ready and usable_as_context and not blocked


def _attached_file_is_csv(record: Dict[str, Any]) -> bool:
    """
    Conservatively identify attached CSV/XLSX/XLSX files.
    """
    source_path = _attached_file_source_path(record)
    if not source_path:
        return False

    file_kind = _attached_file_kind(record)
    file_name = _attached_file_name(record).lower()
    lowered_path = source_path.lower()

    return (
        file_kind
        in {
            "csv",
            ".csv",
            "text/csv",
            "application/csv",
            "xlsx",
            ".xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/excel",
            "application/vnd.ms-excel",
        }
        or file_name.endswith((".csv", ".xlsx"))
        or lowered_path.endswith((".csv", ".xlsx"))
    )


def _select_first_ready_attached_csv(
    context: Dict[str, Any],
) -> Dict[str, Any] | None:
    """
    Select the first ready attached CSV/XLSX/XLSX/XLSX file for data execution v0.
    """
    for record in _attached_file_records_from_context(context):
        if _attached_file_is_ready_context(record) and _attached_file_is_csv(record):
            return record

    return None


def _request_asks_for_data_summary(request_text: str) -> bool:
    """
    Detect narrow CSV/XLSX/table summary requests.

    This is intentionally conservative. It recognizes requests to summarize,
    inspect, describe, preview, or report basic table/CSV/XLSX/dataset structure.
    """
    lowered = request_text.lower()

    data_terms = (
        "csv",
        "xlsx",
        "excel",
        "spreadsheet",
        "workbook",
        "table",
        "dataset",
        "data set",
        "data file",
        "attached file",
        "attached data",
        "columns",
        "missing values",
        "basic stats",
        "numeric columns",
    )
    action_terms = (
        "summarize",
        "summary",
        "inspect",
        "describe",
        "profile",
        "preview",
        "show",
        "list",
        "what columns",
        "missing values",
        "basic stats",
    )

    return any(term in lowered for term in data_terms) and any(
        term in lowered for term in action_terms
    )


def _detect_bounded_data_execution_candidate(
    *,
    intent: Dict[str, Any],
    mode: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Detect narrow v0 data-execution candidates.

    This marks only attached, ready CSV files as executable candidates. It does
    not read arbitrary paths from user text and does not authorize broad data
    science, plotting, notebooks, shell, web access, or file mutation.
    """
    request_text = str(context.get("request_summary", "") or "").strip()
    primary_intent = str(intent.get("primary", "") or "").strip().lower()
    normalized_mode = str(mode or "").strip().lower()

    base = {
        "bounded_data_execution_candidate": False,
        "data_execution_operation": "",
        "data_execution_source_kind": "",
        "data_execution_source_path": "",
        "data_execution_file_id": "",
        "data_execution_file_name": "",
        "data_execution_reason": "",
    }

    if not request_text:
        return base

    allowed_context = (
        primary_intent in {"conversation", "research", "tutoring", "writing", "unknown"}
        or normalized_mode in {"default", "researcher", "tutor", "writer", "companion"}
    )

    if not allowed_context:
        return base

    asks_for_data_summary = _request_asks_for_data_summary(request_text)
    attached_csv = _select_first_ready_attached_csv(context)

    if not asks_for_data_summary:
        return base

    if attached_csv is None:
        return {
            **base,
            "data_execution_reason": "data_summary_requested_but_no_ready_attached_data_file",
        }

    source_path = _attached_file_source_path(attached_csv)
    file_id = _attached_file_text(attached_csv, "file_id", "id")
    file_name = _attached_file_name(attached_csv)

    if not source_path:
        return {
            **base,
            "data_execution_reason": "attached_data_file_missing_local_source_path",
        }

    return {
        **base,
        "bounded_data_execution_candidate": True,
        "data_execution_operation": "summarize_csv",
        "data_execution_source_kind": "attached_file",
        "data_execution_source_path": source_path,
        "data_execution_file_id": file_id,
        "data_execution_file_name": file_name,
        "data_execution_reason": "explicit_attached_data_file_summary_request",
    }


def _extract_code_file_paths_from_text(text: str) -> List[str]:
    """
    Extract explicit path-like file references from a Coder request.

    This is intentionally only a string extractor. It does not authorize,
    inspect, or mutate any path. The formatter/runtime policy later validates
    whether the proposed paths are safe.
    """
    candidates: List[str] = []

    pattern = re.compile(
        r"(?<![\w@.-])"
        r"((?:\.{1,2}/)?(?:[A-Za-z0-9_@+.-]+/)+[A-Za-z0-9_@+.-]+\.[A-Za-z0-9_+-]{1,12}"
        r"|(?:\.{1,2}/)?[A-Za-z0-9_@+.-]+\.[A-Za-z0-9_+-]{1,12})"
    )

    for match in pattern.finditer(text or ""):
        candidate = match.group(1).strip("`'\"()[]{}<>,;:")
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    hidden_name_pattern = re.compile(
        r"(?<![\w/.-])(\.env(?:\.[A-Za-z0-9_+-]+)?)(?![\w/-])"
    )
    for match in hidden_name_pattern.finditer(text or ""):
        candidate = match.group(1).strip("`'\"()[]{}<>,;:")
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    return candidates


def _request_asks_for_repo_context(request_text: str) -> bool:
    """
    Detect narrow Coder v0 repo-context requests.
    """
    lowered = request_text.lower()

    repo_terms = (
        "repo",
        "repository",
        "project structure",
        "codebase",
        "this project",
        "these files",
        "file tree",
        "framework",
        "test command",
        "tests should i run",
        "what tests",
        "why did this test fail",
        "inspect",
        "summarize",
    )

    action_terms = (
        "inspect",
        "summarize",
        "what kind",
        "what files",
        "what tests",
        "tests should",
        "why did",
        "understand",
        "look at",
        "review",
        "diagnose",
    )

    return any(term in lowered for term in repo_terms) and any(
        term in lowered for term in action_terms
    )


def _request_asks_for_code_patch_plan(request_text: str) -> bool:
    """
    Detect narrow Coder v0 patch-planning requests.

    This does not mean Elysia can apply a patch. It only marks that the user is
    asking for a proposal/review plan.
    """
    lowered = request_text.lower()

    patch_terms = (
        "patch plan",
        "patch",
        "change",
        "fix",
        "proposal",
        "propose",
        "what files should",
        "files should we change",
        "how should we patch",
        "draft a safe patch",
        "code review",
        "why did this test fail",
        "apply",
        "aider",
        "openhands",
        "run tests",
    )

    return any(term in lowered for term in patch_terms)


def _detect_coder_runtime_candidates(
    *,
    intent: Dict[str, Any],
    mode: str,
    selected_skill: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Detect Coder-mode v0 runtime candidates.

    Coder v0 is proposal/read-only only:
    - approved repo context may be gathered
    - patch plans may be formatted when explicit file paths are present
    - file mutation, shell execution, external workers, git mutation, and
      dependency installation remain not live here
    """
    request_text = str(context.get("request_summary", "") or "").strip()
    primary_intent = str(intent.get("primary", "") or "").strip().lower()
    normalized_mode = str(mode or "").strip().lower()
    selected_skill_id = str(selected_skill.get("selected_skill_id", "") or "")

    base = {
        "repo_context_candidate": False,
        "repo_context_repo_key": "",
        "repo_context_reason": "",
        "code_patch_plan_candidate": False,
        "code_patch_plan_reason": "",
        "code_patch_files_to_touch": [],
    }

    coder_context = (
        normalized_mode in {"coder", "coding"}
        or primary_intent in {"coding", "debugging"}
        or selected_skill_id.startswith("coding.")
    )

    if not coder_context or not request_text:
        return base

    explicit_files = _extract_code_file_paths_from_text(request_text)
    asks_for_repo_context = _request_asks_for_repo_context(request_text)
    asks_for_patch_plan = _request_asks_for_code_patch_plan(request_text)

    repo_context_candidate = (
        asks_for_repo_context
        or asks_for_patch_plan
        or bool(explicit_files)
    )
    code_patch_plan_candidate = asks_for_patch_plan or bool(explicit_files)

    return {
        **base,
        "repo_context_candidate": repo_context_candidate,
        "repo_context_repo_key": "elysia" if repo_context_candidate else "",
        "repo_context_reason": (
            "explicit_coder_repo_context_request"
            if repo_context_candidate
            else ""
        ),
        "code_patch_plan_candidate": code_patch_plan_candidate,
        "code_patch_plan_reason": (
            "explicit_coder_patch_plan_request"
            if code_patch_plan_candidate
            else ""
        ),
        "code_patch_files_to_touch": explicit_files,
    }


def _detect_governed_public_research_candidate(
    *, request_text: str, primary_intent: str, local_data_candidate: bool
) -> bool:
    """Require a clear public-web need; Researcher mode grants no authority.

    "Analyze these sources" and attached-file work remain local.  The bounded
    ResearchPort activates only for an explicit web/Internet request, a public
    URL, or a research-class request whose wording clearly requires current
    public information.
    """
    if local_data_candidate:
        return False
    lowered = str(request_text or "").casefold()
    explicit_public = any(
        marker in lowered
        for marker in (
            "search the web",
            "search online",
            "browse the web",
            "browse online",
            "look up online",
            "use searxng",
            "public web",
            "live web",
            "internet research",
            "research online",
            "online sources",
            "current public sources",
            "latest public sources",
            "http://",
            "https://",
        )
    )
    clearly_current = primary_intent == "research" and any(
        marker in lowered
        for marker in (
            "up-to-date public",
            "current public information",
            "latest published",
            "recently published",
            "today's news",
            "latest news",
        )
    )
    return explicit_public or clearly_current

def build_plan(
    intent: Dict[str, Any],
    mode: str,
    selected_skill: Dict[str, Any],
    context: Dict[str, Any],
    memory_class_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a structured scaffold plan.

    Current scaffold behavior:
    - preserves intent and mode
    - records selected skill
    - carries a short context summary
    - records whether memory context was available
    - emits policy-relevant metadata fields
    - begins explicit scaffold memory-class reasoning
    - keeps execution disabled
    """
    primary_intent = intent.get("primary", "unknown")
    selected_skill_id = selected_skill.get("selected_skill_id")
    context_summary = context.get("request_summary", "")
    request_text = str(
        context.get("request_text")
        or context.get("full_request_text")
        or context_summary
        or ""
    )
    retrieved_memory_count = int(context.get("retrieved_memory_count", 0) or 0)
    memory_context_source = str(context.get("retrieval_mode", "unknown"))
    uses_memory_context = retrieved_memory_count > 0
    mode_profile = _resolve_context_mode_profile(mode, context)

    memory_class_fields = _resolve_memory_class_plan(
        mode=mode,
        context=context,
        retrieved_memory_count=retrieved_memory_count,
        memory_context_source=memory_context_source,
        memory_class_policy=memory_class_policy,
    )
    math_candidate_fields = _detect_bounded_math_execution_candidate(
        intent=intent,
        mode=mode,
        context=context,
    )
    data_candidate_fields = _detect_bounded_data_execution_candidate(
        intent=intent,
        mode=mode,
        context=context,
    )
    coder_candidate_fields = _detect_coder_runtime_candidates(
        intent=intent,
        mode=mode,
        selected_skill=selected_skill,
        context=context,
    )
    hard_block_fields = _detect_hard_blocked_request(request_text)
    governed_public_research = _detect_governed_public_research_candidate(
        request_text=request_text,
        primary_intent=primary_intent,
        local_data_candidate=bool(
            data_candidate_fields["bounded_data_execution_candidate"]
        ),
    )

    if hard_block_fields["hard_blocked_request"]:
        coder_candidate_fields = {
            **coder_candidate_fields,
            "repo_context_candidate": False,
            "repo_context_repo_key": "",
            "repo_context_reason": "",
            "code_patch_plan_candidate": False,
            "code_patch_plan_reason": "",
            "code_patch_files_to_touch": [],
        }

    normalized_mode = str(mode or "").strip().lower()

    if normalized_mode in {"coder", "coding"} or primary_intent in {"coding", "debugging"}:
        steps = [
            "interpret the coding request",
            "gather approved repo context if needed",
            "draft a proposal-only patch plan if explicit files are provided",
            "state tests, risks, rollback, and approval boundary",
        ]
    elif primary_intent == "tutoring":
        steps = [
            "interpret the request",
            "gather allowed context",
            "explain clearly",
            "check whether the explanation matches the learning goal",
        ]
    elif primary_intent == "research":
        steps = [
            "interpret the research question",
            "gather allowed context",
            "outline a careful answer",
            "check whether the answer matches the available evidence",
        ]
    elif primary_intent == "writing":
        steps = [
            "interpret the writing goal",
            "gather allowed context",
            "draft clearly",
            "check whether the draft matches the requested tone and purpose",
        ]
    else:
        steps = [
            "interpret the request",
            "gather allowed context",
            "respond helpfully",
            "check whether the response matches the request",
        ]

    steps = steps + _mode_profile_planning_steps(mode_profile)

    reads_private_memory = (
        uses_memory_context
        or memory_class_fields["memory_class_boundary_sensitive"]
        or hard_block_fields["reads_private_memory"]
    )

    return {
        "intent": primary_intent,
        "mode": mode,
        "selected_skill_id": selected_skill_id,
        "context_summary": context_summary,
        "mode_profile_key": mode_profile.key,
        "mode_profile_label": mode_profile.label,
        "mode_profile_used": True,
        "mode_profile_effects": mode_profile.compact_effects(),
        "mode_profile_warnings": list(mode_profile.warnings),
        "authority_granted_by_mode": False,
        "mode_profile": mode_profile.to_payload(),
        "retrieved_memory_count": retrieved_memory_count,
        "uses_memory_context": uses_memory_context,
        "memory_context_source": memory_context_source,
        "memory_class": memory_class_fields["memory_class"],
        "primary_memory_class": memory_class_fields["primary_memory_class"],
        "default_memory_class": memory_class_fields["default_memory_class"],
        "fallback_memory_class": memory_class_fields["fallback_memory_class"],
        "allowed_memory_classes": memory_class_fields["allowed_memory_classes"],
        "disallowed_memory_classes": memory_class_fields["disallowed_memory_classes"],
        "forced_memory_class": memory_class_fields["forced_memory_class"],
        "memory_class_source": memory_class_fields["memory_class_source"],
        "memory_class_declared": memory_class_fields["memory_class_declared"],
        "memory_class_boundary_sensitive": memory_class_fields[
            "memory_class_boundary_sensitive"
        ],
        "memory_class_requires_boundary_check": memory_class_fields[
            "memory_class_requires_boundary_check"
        ],
        "steps": steps,
        "bounded_math_execution_candidate": math_candidate_fields[
            "bounded_math_execution_candidate"
        ],
        "math_execution_operation": math_candidate_fields[
            "math_execution_operation"
        ],
        "math_execution_expression": math_candidate_fields[
            "math_execution_expression"
        ],
        "math_execution_variable": math_candidate_fields[
            "math_execution_variable"
        ],
        "math_execution_expected": math_candidate_fields[
            "math_execution_expected"
        ],
        "math_execution_reason": math_candidate_fields[
            "math_execution_reason"
        ],
        "bounded_data_execution_candidate": data_candidate_fields[
            "bounded_data_execution_candidate"
        ],
        "data_execution_operation": data_candidate_fields[
            "data_execution_operation"
        ],
        "data_execution_source_kind": data_candidate_fields[
            "data_execution_source_kind"
        ],
        "data_execution_source_path": data_candidate_fields[
            "data_execution_source_path"
        ],
        "data_execution_file_id": data_candidate_fields[
            "data_execution_file_id"
        ],
        "data_execution_file_name": data_candidate_fields[
            "data_execution_file_name"
        ],
        "data_execution_reason": data_candidate_fields[
            "data_execution_reason"
        ],
        "repo_context_candidate": coder_candidate_fields[
            "repo_context_candidate"
        ],
        "repo_context_repo_key": coder_candidate_fields[
            "repo_context_repo_key"
        ],
        "repo_context_reason": coder_candidate_fields[
            "repo_context_reason"
        ],
        "code_patch_plan_candidate": coder_candidate_fields[
            "code_patch_plan_candidate"
        ],
        "code_patch_plan_reason": coder_candidate_fields[
            "code_patch_plan_reason"
        ],
        "code_patch_files_to_touch": coder_candidate_fields[
            "code_patch_files_to_touch"
        ],
        "hard_blocked_request": hard_block_fields["hard_blocked_request"],
        "block_reasons": hard_block_fields["block_reasons"],
        "requires_tools": governed_public_research,
        "governed_public_research_candidate": governed_public_research,
        "touches_external_network": (
            hard_block_fields["touches_external_network"]
            or governed_public_research
        ),
        "writes_files": hard_block_fields["writes_files"],
        "reads_private_memory": reads_private_memory,
        "risk_level": "high" if hard_block_fields["hard_blocked_request"] else "low",
        "autonomy_level_needed": 1,
        "execution_allowed": False,
        "note": (
            "Planner scaffold only; no side-effecting action execution yet. "
            "Bounded local math execution may be marked as a non-side-effecting candidate. "
            "Bounded local data execution may be marked only for ready attached CSV/XLSX files. "
            "Coder mode may mark read-only approved repo context and proposal-only patch planning candidates, "
            "but file mutation, shell execution, git mutation, and external coding workers remain not live here. "
            "Memory-class reasoning is scaffold-level and may later be "
            "replaced by fully config-driven runtime policy input."
        ),
    }


if __name__ == "__main__":
    demo_intent = {"primary": "tutoring"}
    demo_skill = {
        "selected_skill_id": "tutoring.tutoring_helper",
        "selection_basis": "intent_map",
        "found": True,
    }
    demo_context = {
        "request_summary": "Can you explain derivatives step by step?",
        "retrieved_memory_count": 2,
        "retrieval_mode": "local_session_journal_scaffold",
    }

    print(build_plan(demo_intent, "tutor", demo_skill, demo_context))
