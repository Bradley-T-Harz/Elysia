"""
Elysia response scaffold.

This module turns internal planning, policy, verification, and invocation
state into a user-facing response object. It can now pass through live
local invoker output when available, while still falling back to scaffold
response text when invocation is blocked, fails, or returns no usable text.

At this stage, responder also reflects memory-aware policy, verification
signals, and the scaffold memory-class decision path in a user-facing but
still careful way.
"""

import re
from typing import Any, Dict, List, Optional


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """
    Coerce a value into a boolean with light string handling.
    """
    if isinstance(value, bool):
        return value

    if value is None:
        return default

    if isinstance(value, str):
        lowered = value.strip().lower()

        if lowered in {"true", "1", "yes", "on"}:
            return True

        if lowered in {"false", "0", "no", "off"}:
            return False

    return bool(value)


def _enum_payload_value(value: Any) -> str:
    """
    Return enum values as strings while leaving plain values stringified.
    """
    return str(getattr(value, "value", value) or "")


def _normalize_memory_class_name(value: Any, fallback: str = "") -> str:
    """
    Normalize one memory-class name into a clean string.
    """
    text = str(value or "").strip()
    return text if text else fallback


def _explicitly_requests_latex(message: str) -> bool:
    lowered = message.lower()
    triggers = (
        "latex",
        "tex notation",
        "tex format",
        "write it in latex",
        "use latex",
    )
    return any(trigger in lowered for trigger in triggers)


def _normalize_latexish_text(text: str) -> str:
    normalized = text

    normalized = normalized.replace("\\(", "")
    normalized = normalized.replace("\\)", "")
    normalized = normalized.replace("\\[", "")
    normalized = normalized.replace("\\]", "")
    normalized = normalized.replace("$$", "")

    normalized = normalized.replace("\\cdot", " * ")
    normalized = normalized.replace("\\times", " * ")
    normalized = normalized.replace("\\to", " -> ")

    normalized = re.sub(
        r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}",
        r"(\1) / (\2)",
        normalized,
    )
    normalized = re.sub(r"\^\{([^{}]+)\}", r"^(\1)", normalized)
    normalized = re.sub(r"_\{([^{}]+)\}", r"_(\1)", normalized)
    normalized = re.sub(r"\\([A-Za-z]+)", r"\1", normalized)

    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)

    return normalized.strip()



def _coerce_string_list(values: Any) -> List[str]:
    """
    Normalize a value into a clean list of strings for deterministic response text.
    """
    if values is None:
        return []

    if isinstance(values, str):
        text = values.strip()
        return [text] if text else []

    if isinstance(values, (list, tuple)):
        normalized: List[str] = []

        for value in values:
            if value is None:
                continue

            text = str(value).strip()
            if text:
                normalized.append(text)

        return normalized

    text = str(values).strip()
    return [text] if text else []


def _compact_join(values: Any, empty_text: str = "not surfaced", limit: int = 5) -> str:
    """
    Return a compact, bounded comma-joined list.
    """
    normalized = _coerce_string_list(values)

    if not normalized:
        return empty_text

    visible = normalized[:limit]
    remaining = len(normalized) - len(visible)

    if remaining > 0:
        return ", ".join(visible) + f" + {remaining} more"

    return ", ".join(visible)


def _extend_bullets(
    lines: List[str],
    values: Any,
    *,
    empty_text: str,
    limit: int = 8,
) -> None:
    """
    Append bounded bullet lines.
    """
    normalized = _coerce_string_list(values)

    if not normalized:
        lines.append(f"- {empty_text}")
        return

    visible = normalized[:limit]
    for value in visible:
        lines.append(f"- {value}")

    remaining = len(normalized) - len(visible)
    if remaining > 0:
        lines.append(f"- + {remaining} more")


def _build_structured_repo_context_response(repo_context: Dict[str, object]) -> str:
    """
    Build deterministic repo-context response text.

    This intentionally overrides live model prose for Coder repo inspection so
    the final answer cannot invent git status, shell use, file mutation, or
    network behavior beyond the structured payload.
    """
    status = _enum_payload_value(repo_context.get("status", "")).lower()
    repo_label = str(
        repo_context.get("repo_label")
        or repo_context.get("repo_key")
        or "approved repo"
    ).strip()
    repo_root = str(repo_context.get("repo_root") or "not surfaced").strip()
    branch = str(repo_context.get("current_branch") or "not surfaced").strip()
    trust_zone = str(repo_context.get("trust_zone") or "project_local").strip()
    changed_files_note = str(
        repo_context.get("changed_files_note")
        or "Git changed-file detection is not live in repo context v0."
    ).strip()

    if status == "completed":
        heading = "Read-only repo context gathered."
    elif status in {"blocked", "failed"}:
        heading = "Read-only repo context did not complete successfully."
    else:
        heading = "Read-only repo context was considered."

    lines: List[str] = [
        heading,
        "",
        "Repo:",
        f"- Repo: {repo_label}",
        f"- Root: {repo_root}",
        f"- Trust zone: {trust_zone}",
        f"- Branch: {branch}",
        f"- Appears git repo: {_coerce_bool(repo_context.get('appears_git_repo', False), False)}",
        f"- Languages: {_compact_join(repo_context.get('language_hints', []))}",
        f"- Frameworks: {_compact_join(repo_context.get('framework_hints', []), limit=4)}",
        "",
        "Safe project hints:",
    ]

    _extend_bullets(
        lines,
        repo_context.get("safe_tree_entries", []),
        empty_text="Safe tree entries were not surfaced.",
        limit=8,
    )

    lines.extend(
        [
            "",
            "Suggested test hints:",
        ]
    )
    _extend_bullets(
        lines,
        repo_context.get("test_command_hints", []),
        empty_text="Test hints were not surfaced.",
        limit=4,
    )

    lines.extend(
        [
            "",
            "Boundary:",
            "- No shell was used.",
            "- No network access was used.",
            "- No files were changed.",
            "- No git status/diff command was run.",
            f"- {changed_files_note}",
        ]
    )

    warnings = _coerce_string_list(repo_context.get("warnings", []))
    errors = _coerce_string_list(repo_context.get("errors", []))

    if warnings:
        lines.extend(["", "Warnings:"])
        _extend_bullets(lines, warnings, empty_text="", limit=4)

    if errors:
        lines.extend(["", "Errors:"])
        _extend_bullets(lines, errors, empty_text="", limit=4)

    return "\n".join(lines).strip()


def _build_structured_code_patch_plan_response(
    code_patch_plan: Dict[str, object],
) -> str:
    """
    Build deterministic proposal-only patch-plan response text.

    This intentionally overrides live model prose when a structured patch plan
    exists, so Coder mode cannot claim files were changed, tests were run, shell
    was used, or external coding workers were invoked.
    """
    status = _enum_payload_value(code_patch_plan.get("status", "")).lower()
    summary = str(code_patch_plan.get("summary") or "").strip()

    if status == "completed":
        heading = "Proposal-only patch plan created."
    elif status == "blocked":
        heading = "Proposal-only patch plan blocked safely."
    elif status == "failed":
        heading = "Proposal-only patch planning failed safely."
    else:
        heading = "Proposal-only patch plan recorded."

    lines: List[str] = [heading]

    if summary:
        lines.extend(["", "Summary:", f"- {summary}"])

    lines.extend(["", "Files proposed:"])
    _extend_bullets(
        lines,
        code_patch_plan.get("files_to_touch", []),
        empty_text="No explicit files were surfaced.",
        limit=12,
    )

    lines.extend(["", "Patch steps:"])
    _extend_bullets(
        lines,
        code_patch_plan.get("patch_plan", []),
        empty_text="Patch steps were not surfaced.",
        limit=8,
    )

    lines.extend(["", "Tests to run after any approved patch:"])
    _extend_bullets(
        lines,
        code_patch_plan.get("tests_to_run", []),
        empty_text="No test commands were surfaced.",
        limit=6,
    )

    risk_notes = _coerce_string_list(code_patch_plan.get("risk_notes", []))
    if risk_notes:
        lines.extend(["", "Risk notes:"])
        _extend_bullets(lines, risk_notes, empty_text="", limit=5)

    rollback_notes = _coerce_string_list(code_patch_plan.get("rollback_notes", []))
    if rollback_notes:
        lines.extend(["", "Rollback notes:"])
        _extend_bullets(lines, rollback_notes, empty_text="", limit=5)

    warnings = _coerce_string_list(code_patch_plan.get("warnings", []))
    errors = _coerce_string_list(code_patch_plan.get("errors", []))

    if warnings:
        lines.extend(["", "Warnings:"])
        _extend_bullets(lines, warnings, empty_text="", limit=4)

    if errors:
        lines.extend(["", "Errors:"])
        _extend_bullets(lines, errors, empty_text="", limit=4)

    lines.extend(
        [
            "",
            "Approval boundary:",
            "- Approval is required before any future patch application.",
            "- Patch application is not live.",
            "- No files were changed.",
            "- No shell, network, Aider, OpenHands, external workers, or tests were used.",
        ]
    )

    return "\n".join(lines).strip()


def _build_structured_aider_worker_response(
    aider_worker: Dict[str, object],
) -> str:
    """
    Build deterministic Aider worker skeleton validation response text.
    """
    status = _enum_payload_value(aider_worker.get("status", "")).lower()

    if status == "dry_run_ready":
        heading = "Aider worker skeleton dry-run validation is ready."
    elif status == "blocked":
        heading = "Aider worker skeleton dry-run validation blocked safely."
    elif status == "failed":
        heading = "Aider worker skeleton dry-run validation failed safely."
    else:
        heading = "Aider worker skeleton dry-run validation was recorded."

    lines: List[str] = [
        heading,
        "",
        "Scope:",
        "- Skeleton validation only.",
        "- Aider subprocess was not invoked.",
        "- No files were changed.",
        "- No shell, network, tests, git mutation, package installation, or cloud model use occurred.",
        "",
        "Files considered:",
    ]
    _extend_bullets(
        lines,
        aider_worker.get("files_considered", []),
        empty_text="No files were accepted for validation.",
        limit=12,
    )

    refusal_reasons = _coerce_string_list(aider_worker.get("refusal_reasons", []))
    warnings = _coerce_string_list(aider_worker.get("warnings", []))
    errors = _coerce_string_list(aider_worker.get("errors", []))

    if refusal_reasons:
        lines.extend(["", "Refusal reasons:"])
        _extend_bullets(lines, refusal_reasons, empty_text="", limit=6)

    if warnings:
        lines.extend(["", "Warnings:"])
        _extend_bullets(lines, warnings, empty_text="", limit=5)

    if errors:
        lines.extend(["", "Errors:"])
        _extend_bullets(lines, errors, empty_text="", limit=5)

    lines.extend(
        [
            "",
            "Future mutation boundary:",
            "- Approval is required before any future mutation.",
            "- This dry-run validation itself did not require mutation approval.",
        ]
    )

    return "\n".join(lines).strip()


def compose_response(
    message: str,
    plan: Dict[str, object],
    policy_review: Dict[str, object],
    verification: Dict[str, object],
    internal_result: Optional[Dict[str, object]] = None,
    model_routing: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """
    Responder scaffold with live-invoker pass-through.

    Current scaffold behavior:
    - reflects intent and mode
    - reports whether memory-aware context was used
    - includes caveats based on policy, invocation, and verification state
    - reflects scaffold memory-class handling at a careful summary level
    - passes through live local invoker output when available
    - falls back to scaffold response text when invocation is blocked, fails, or returns no usable text
    """
    intent = str(plan.get("intent", "unknown"))
    mode = str(plan.get("mode", "unknown"))
    verified = bool(verification.get("verified", False))
    local_response_allowed = _coerce_bool(policy_review.get("allowed", False), False)
    approval_required = _coerce_bool(
        policy_review.get("approval_required", False),
        False,
    )
    side_effecting_execution_allowed = _coerce_bool(
        plan.get("execution_allowed", False),
        False,
    )

    internal_result = dict(internal_result or {})
    model_routing = dict(model_routing or {})
    math_execution = internal_result.get("math_execution", {})
    if not isinstance(math_execution, dict):
        math_execution = {}

    data_execution = internal_result.get("data_execution", {})
    if not isinstance(data_execution, dict):
        data_execution = {}

    repo_context = internal_result.get("repo_context", {})
    if not isinstance(repo_context, dict):
        repo_context = {}

    code_patch_plan = internal_result.get("code_patch_plan", {})
    if not isinstance(code_patch_plan, dict):
        code_patch_plan = {}

    aider_worker = internal_result.get("aider_worker", {})
    if not isinstance(aider_worker, dict):
        aider_worker = {}

    invocation_status = str(internal_result.get("status", "") or "").strip()
    invocation_response_text = str(
        internal_result.get("response_text", "") or ""
    ).strip()
    invocation_note = str(internal_result.get("note", "") or "").strip()
    invocation_error = str(internal_result.get("error", "") or "").strip()
    block_reasons = [
        str(reason).strip()
        for reason in internal_result.get("block_reasons", []) or []
        if str(reason).strip()
    ]

    selected_model_role = str(
        internal_result.get("selected_role")
        or model_routing.get("selected_role")
        or ""
    ).strip()
    selected_runtime = str(
        internal_result.get("selected_runtime")
        or model_routing.get("selected_runtime")
        or ""
    ).strip()
    selected_model_runtime_tag = str(
        internal_result.get("selected_model_runtime_tag", "") or ""
    ).strip()

    used_fallback = _coerce_bool(internal_result.get("used_fallback", False), False)
    fallback_from = str(internal_result.get("fallback_from", "") or "").strip()
    fallback_to = str(internal_result.get("fallback_to", "") or "").strip()

    uses_memory_context = bool(plan.get("uses_memory_context", False))
    memory_context_source = str(plan.get("memory_context_source", ""))
    boundary_flags = policy_review.get("boundary_flags", [])
    mode_profile_key = str(plan.get("mode_profile_key", mode) or mode).strip()
    mode_profile_label = str(plan.get("mode_profile_label", mode_profile_key) or mode_profile_key).strip()
    mode_profile_effects = _coerce_string_list(plan.get("mode_profile_effects", []))
    mode_profile_warnings = _coerce_string_list(plan.get("mode_profile_warnings", []))
    authority_granted_by_mode = _coerce_bool(
        plan.get("authority_granted_by_mode", False),
        False,
    )
    lowered_message = str(message or "").lower()
    asks_public_research = (
        mode.strip().lower() in {"researcher", "research"}
        and any(
            marker in lowered_message
            for marker in (
                "search public",
                "public sources",
                "search the web",
                "web search",
                "searxng",
                "current source",
                "current recommended",
            )
        )
    )

    memory_class = _normalize_memory_class_name(
        plan.get("memory_class", ""),
        "unspecified",
    )
    memory_class_source = _normalize_memory_class_name(
        plan.get("memory_class_source", ""),
        "unknown",
    )
    forced_memory_class = _normalize_memory_class_name(
        plan.get("forced_memory_class", ""),
        "",
    )
    memory_class_boundary_sensitive = _coerce_bool(
        plan.get("memory_class_boundary_sensitive", False),
        False,
    )
    memory_class_requires_boundary_check = _coerce_bool(
        plan.get("memory_class_requires_boundary_check", False),
        False,
    )

    caveats: List[str] = []

    # Local-response permission is distinct from side-effecting execution.
    # A plan may be allowed for governed local text generation while tools,
    # outward actions, file writes, and other side effects remain blocked.
    if invocation_status == "ok":
        caveats.append(
            "Live local model generation succeeded through the governed invoker. "
            "Tool, network, and mutation authority remains independently governed by "
            "the effective profile, approvals, and capability adapters."
        )
    elif not side_effecting_execution_allowed:
        caveats.append(
            "Tool or side-effect authority was not granted for this response; no such "
            "operation was implied by model generation."
        )

    if approval_required:
        caveats.append(
            "Approval is required before any file write or side-effecting action; no side-effecting action has been completed."
        )

        if not local_response_allowed:
            caveats.append(
                "The current plan is approval-bound because it touches a governed boundary."
            )

    # Specific invocation outcome
    if invocation_status == "blocked":
        caveats.append(
            "Live local invocation was blocked by the current routed path or boundary rules."
        )
        for reason in block_reasons[:3]:
            caveats.append(f"Blocked reason: {reason}.")
    elif invocation_status == "error":
        caveats.append(
            "Live local invocation failed, so a governed deterministic fallback response was returned."
        )

    if invocation_status == "ok" and used_fallback:
        caveats.append(
            "An allowed local fallback model was used instead of the preferred runtime tag."
        )

    if invocation_error:
        caveats.append(
            "Invocation reported an internal error state."
        )

    # Memory and boundary caveats
    if "local_session_memory" in boundary_flags:
        caveats.append(
            "Local session journal memory was considered during context gathering."
        )
    elif uses_memory_context:
        caveats.append(
            "Memory-aware context was used during planning."
        )

    if forced_memory_class:
        caveats.append(
            "Memory handling was constrained by policy boundaries."
        )

    if memory_class_boundary_sensitive:
        caveats.append(
            "A boundary-sensitive memory class shaped how this response was handled."
        )

    if memory_class_requires_boundary_check:
        caveats.append(
            "Additional boundary checks were applied to the selected memory path."
        )

    caveats.append(
        f"Mode profile posture used: {mode_profile_label}. Modes shape weighting and style, not authority."
    )
    if authority_granted_by_mode:
        caveats.append(
            "Mode profile attempted to grant authority, but runtime treats that authority as inert."
        )
    for warning in mode_profile_warnings[:3]:
        caveats.append(f"Mode profile warning: {warning}")

    if asks_public_research:
        caveats.append(
            "Bounded SearXNG research did not run for this chat response; treat any source guidance as local model context, not current web evidence."
        )

    # Bounded math execution caveats
    if _coerce_bool(math_execution.get("used", False), False):
        math_status = _enum_payload_value(math_execution.get("status", ""))
        if math_status == "completed":
            caveats.append(
                "Bounded local math execution was used to check part of this response."
            )
        elif math_status == "failed":
            caveats.append(
                "Bounded local math execution was attempted but did not complete successfully."
            )
        else:
            caveats.append(
                "Bounded local math execution was considered during this response."
            )

    # Bounded data execution caveats
    if _coerce_bool(data_execution.get("used", False), False):
        data_status = _enum_payload_value(data_execution.get("status", ""))
        if data_status == "completed":
            caveats.append(
                "Bounded local data inspection was used to summarize an attached CSV."
            )
        elif data_status == "blocked":
            caveats.append(
                "Bounded local data inspection was blocked by v0 safety boundaries."
            )
        elif data_status == "failed":
            caveats.append(
                "Bounded local data inspection was attempted but did not complete successfully."
            )
        else:
            caveats.append(
                "Bounded local data inspection was considered during this response."
            )

    # Coder mode caveats
    if _coerce_bool(repo_context.get("used", False), False):
        repo_status = _enum_payload_value(repo_context.get("status", ""))
        if repo_status == "completed":
            caveats.append(
                "Read-only local repo context was gathered from an approved repo. No shell, network access, git status/diff command, or file mutation was used."
            )
        elif repo_status in {"blocked", "failed"}:
            caveats.append(
                "Read-only repo context gathering did not complete successfully; no shell, network access, or file mutation was used."
            )
        else:
            caveats.append(
                "Read-only repo context was considered during this response."
            )

    if _coerce_bool(code_patch_plan.get("used", False), False):
        patch_status = _enum_payload_value(code_patch_plan.get("status", ""))
        if patch_status == "completed":
            caveats.append(
                "A proposal-only patch plan was formatted. Approval is required before applying changes."
            )
        elif patch_status == "blocked":
            caveats.append(
                "Patch planning was blocked by Coder v0 boundaries. No files were changed."
            )
        elif patch_status == "failed":
            caveats.append(
                "Patch planning failed safely. No files were changed."
            )
        else:
            caveats.append(
                "Proposal-only patch planning was considered during this response."
            )
    elif _coerce_bool(plan.get("code_patch_plan_candidate", False), False):
        caveats.append(
            "Patch planning was requested, but no explicit relative file paths were provided for the formatter. No files were changed."
        )

    if _coerce_bool(aider_worker.get("used", False), False):
        aider_status = _enum_payload_value(aider_worker.get("status", ""))
        if aider_status == "dry_run_ready":
            caveats.append(
                "Aider worker skeleton dry-run validation was surfaced. Aider was not invoked and no files were changed."
            )
        elif aider_status == "blocked":
            caveats.append(
                "Aider worker skeleton dry-run validation blocked the request safely. Aider was not invoked and no files were changed."
            )
        elif aider_status == "failed":
            caveats.append(
                "Aider worker skeleton dry-run validation failed safely. Aider was not invoked and no files were changed."
            )
        else:
            caveats.append(
                "Aider worker skeleton dry-run validation was considered without invoking Aider or changing files."
            )

    # Verification caveat
    if not verified:
        caveats.append("Internal verification did not fully pass.")

    # Memory/Memory Class notes
    memory_note = "without memory context"
    if uses_memory_context and memory_context_source:
        memory_note = f"using memory context from '{memory_context_source}'"
    elif uses_memory_context:
        memory_note = "using memory-aware context"

    memory_class_note = (
        f"The current scaffold selected memory class '{memory_class}' "
        f"from '{memory_class_source}'."
    )

    if forced_memory_class:
        memory_class_note += (
            f" Policy boundaries forced memory class '{forced_memory_class}'."
        )
    elif memory_class_boundary_sensitive:
        memory_class_note += (
            " That memory path was treated as boundary-sensitive."
        )
    elif memory_class_requires_boundary_check:
        memory_class_note += (
            " That memory path required additional boundary checks."
        )

    verification_note = "Verification checks passed."
    if not verified:
        verification_note = "Verification checks did not fully pass."

    scaffold_response_text = (
        f"Elysia identified this as '{intent}' in '{mode}' mode, "
        f"{memory_note}. {memory_class_note} "
        f"A bounded scaffold response path was used. Broader tool use and side-effecting execution remain disabled during this phase. "
        f"{verification_note}"
    )

    response_source = "scaffold_fallback"
    final_response_text = scaffold_response_text

    structured_coder_response_text = ""
    structured_coder_response_source = ""

    if _coerce_bool(code_patch_plan.get("used", False), False):
        structured_coder_response_text = _build_structured_code_patch_plan_response(
            code_patch_plan
        )
        structured_coder_response_source = "structured_coder_patch_plan"
    elif (
        mode.strip().lower() in {"coder", "coding"}
        and _coerce_bool(repo_context.get("used", False), False)
    ):
        structured_coder_response_text = _build_structured_repo_context_response(
            repo_context
        )
        structured_coder_response_source = "structured_coder_repo_context"

    if structured_coder_response_text and _coerce_bool(
        aider_worker.get("used", False),
        False,
    ):
        structured_coder_response_text = (
            structured_coder_response_text
            + "\n\n"
            + _build_structured_aider_worker_response(aider_worker)
        )
    elif _coerce_bool(aider_worker.get("used", False), False):
        structured_coder_response_text = _build_structured_aider_worker_response(
            aider_worker
        )
        structured_coder_response_source = "structured_coder_aider_worker"

    if structured_coder_response_text:
        response_source = structured_coder_response_source
        final_response_text = structured_coder_response_text
    elif invocation_status == "ok" and invocation_response_text:
        response_source = "live_invoker"
        final_response_text = invocation_response_text

        if not _explicitly_requests_latex(message):
            final_response_text = _normalize_latexish_text(final_response_text)

    if (
        invocation_status == "blocked"
        and block_reasons
        and internal_result.get("prompt_source") == "hard_blocked_boundary_truth"
    ):
        response_source = "scaffold_fallback"
        final_response_text = (
            "I can’t do that. This request is blocked because "
            + "; ".join(block_reasons[:3])
            + ". No web search, private vault access, Aider invocation, file mutation, shell command, or git action was performed."
        )

    if asks_public_research and "Bounded SearXNG research did not run" not in final_response_text:
        bounded_research_notice = (
            "Bounded research note: bounded SearXNG research did not run for this "
            "chat response. If local SearXNG is disabled or not running, start and "
            "enable the local worker and use the bounded research route before "
            "treating an answer as current-source evidence. I did not fetch web "
            "pages or produce evidence packets for this response."
        )
        final_response_text = f"{bounded_research_notice}\n\n{final_response_text}".strip()

    approval_notice = (
        "Approval is required before any file write or side-effecting action. "
        "I have not performed that action."
    )
    if approval_required and approval_notice not in final_response_text:
        final_response_text = f"{approval_notice}\n\n{final_response_text}".strip()

    return {
        "status": "response_composed",
        "response_source": response_source,
        "invocation_status": invocation_status or "not_invoked",
        "user_message": message,
        "intent": intent,
        "mode": mode,
        "response_text": final_response_text,
        "caveats": caveats,
        "selected_model_role": selected_model_role,
        "selected_runtime": selected_runtime,
        "selected_model_runtime_tag": selected_model_runtime_tag,
        "used_fallback": used_fallback,
        "fallback_from": fallback_from,
        "fallback_to": fallback_to,
        "invocation_note": invocation_note,
        "math_execution": math_execution,
        "data_execution": data_execution,
        "repo_context": repo_context,
        "code_patch_plan": code_patch_plan,
        "aider_worker": aider_worker,
        "mode_profile": {
            "key": mode_profile_key,
            "label": mode_profile_label,
            "used": True,
            "effects": mode_profile_effects,
            "warnings": mode_profile_warnings,
            "authority_granted_by_mode": False,
        },
        "note": (
            "Responder now composes a user-facing response using live invoker output "
            "when available and scaffold fallback text otherwise, while surfacing "
            "bounded local math, data, repo context, proposal-only patch-plan, "
            "and Aider worker skeleton truth when those lanes are used."
        ),
    }


if __name__ == "__main__":
    demo_plan = {
        "intent": "tutoring",
        "mode": "tutor",
        "uses_memory_context": True,
        "memory_context_source": "local_session_journal_scaffold",
        "memory_class": "working_memory",
        "memory_class_source": "forced_memory_class",
        "forced_memory_class": "working_memory",
        "memory_class_boundary_sensitive": False,
        "memory_class_requires_boundary_check": True,
    }

    demo_policy_review = {
        "allowed": True,
        "approval_required": False,
        "approval_reasons": [
            "broader tool use, outward action, and side-effecting execution remain disabled during scaffold phase; governed local model generation may still be permitted",
            "plan reads local session journal memory",
        ],
        "boundary_flags": ["local_session_memory"],
        "review_note": "Policy gate scaffold only.",
        "checked_step_count": 4,
    }

    demo_verification = {
        "verified": True,
        "checks_passed": [
            "plan_has_intent",
            "plan_has_mode",
            "result_has_status",
            "result_has_note",
        ],
        "issues": [],
        "review_note": "Verifier scaffold only.",
    }

    print(
        compose_response(
            "Can you explain derivatives step by step?",
            demo_plan,
            demo_policy_review,
            demo_verification,
        )
    )
