"""Elysia's governed live local model-call organ.

This module is the bounded provider boundary for local model invocation.

Its job is deliberately narrow:
- accept an already-governed model-routing decision
- resolve the selected role against normalized model-role config
- load the correct derived system prompt for that role
- enforce local-only / no-silent-cloud-fallback boundaries
- call Ollama locally over HTTP
- support allowed local fallback when configured
- return a structured invocation result for runtime and UI use

It does not:
- decide routing from scratch
- override policy or routing
- inspect or write memory
- perform journaling or logging directly
- silently escalate to external helpers
"""

from copy import deepcopy
import json
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional, Sequence
from urllib import error as urllib_error
from urllib import request as urllib_request


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DERIVED_RUNTIME_ROOT = PROJECT_ROOT / "derived" / "runtime"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_LOCAL_CONTEXT_WINDOW = 32768

ROLE_PROMPT_PATHS = {
    "primary_general": DERIVED_RUNTIME_ROOT / "elysia_general_system.txt",
    "primary_code": DERIVED_RUNTIME_ROOT / "elysia_code_system.txt",
    "lighter_backup": DERIVED_RUNTIME_ROOT / "elysia_light_system.txt",
    "optional_fallback": DERIVED_RUNTIME_ROOT / "elysia_utility_system.txt",
}


def _as_mapping(value: Any) -> Dict[str, Any]:
    """
    Return a shallow-copied mapping or an empty dict.
    """
    if not isinstance(value, dict):
        return {}

    return dict(value)


def _coerce_bool(value: Any, default: bool) -> bool:
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


def _coerce_string(value: Any, default: str = "") -> str:
    """
    Normalize one value into a clean string.
    """
    text = str(value or "").strip()
    return text if text else default


def _coerce_string_list(values: Any) -> List[str]:
    """
    Normalize a value into a clean list of strings.
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


def _dedupe_string_list(values: Sequence[str]) -> List[str]:
    """
    Deduplicate a sequence of strings while preserving order.
    """
    deduped: List[str] = []
    seen = set()

    for value in values:
        if value not in seen:
            deduped.append(value)
            seen.add(value)

    return deduped


def _resolve_role_entry(
    model_routing_decision: Dict[str, Any],
    configs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Resolve the selected role against normalized model-role config.
    """
    models_config = _as_mapping(configs.get("models", {}))
    model_roles = _as_mapping(models_config.get("model_roles", {}))

    roles = _as_mapping(model_roles.get("roles", {}))
    external_helpers = _as_mapping(model_roles.get("external_helpers", {}))

    selected_role = _coerce_string(
        model_routing_decision.get("selected_role"),
        "",
    )
    selected_role_container = _coerce_string(
        model_routing_decision.get("selected_role_container"),
        "",
    )

    if selected_role_container == "roles" and selected_role in roles:
        return {
            "container_name": "roles",
            "role_name": selected_role,
            "role_entry": _as_mapping(roles.get(selected_role, {})),
        }

    if selected_role_container == "external_helpers" and selected_role in external_helpers:
        return {
            "container_name": "external_helpers",
            "role_name": selected_role,
            "role_entry": _as_mapping(external_helpers.get(selected_role, {})),
        }

    if selected_role in roles:
        return {
            "container_name": "roles",
            "role_name": selected_role,
            "role_entry": _as_mapping(roles.get(selected_role, {})),
        }

    if selected_role in external_helpers:
        return {
            "container_name": "external_helpers",
            "role_name": selected_role,
            "role_entry": _as_mapping(external_helpers.get(selected_role, {})),
        }

    return {
        "container_name": "",
        "role_name": selected_role,
        "role_entry": {},
    }


def _append_candidate(
    candidates: List[Dict[str, str]],
    runtime_tag: str,
    canonical_model: str,
    source: str,
) -> None:
    """
    Append one runtime candidate if it has a usable tag.
    """
    runtime_tag = _coerce_string(runtime_tag, "")
    canonical_model = _coerce_string(canonical_model, "")
    source = _coerce_string(source, "")

    if not runtime_tag:
        return

    candidates.append(
        {
            "runtime_tag": runtime_tag,
            "canonical_model": canonical_model,
            "source": source,
        }
    )


def _build_runtime_candidates(role_entry: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Build ordered runtime candidates from a normalized role entry.

    Current priority:
    1. single preferred_model_runtime_tag
    2. plural preferred_model_runtime_tags
    3. fallback_model_runtime_tags
    4. supplementary_model_runtime_tags

    Duplicates are removed by runtime tag while preserving the first occurrence.
    """
    candidates: List[Dict[str, str]] = []

    preferred_model = _coerce_string(role_entry.get("preferred_model"), "")
    preferred_model_runtime_tag = _coerce_string(
        role_entry.get("preferred_model_runtime_tag"),
        "",
    )
    if preferred_model_runtime_tag:
        _append_candidate(
            candidates,
            runtime_tag=preferred_model_runtime_tag,
            canonical_model=preferred_model,
            source="preferred",
        )

    preferred_models = _coerce_string_list(role_entry.get("preferred_models", []))
    preferred_model_runtime_tags = _coerce_string_list(
        role_entry.get("preferred_model_runtime_tags", [])
    )
    for index, runtime_tag in enumerate(preferred_model_runtime_tags):
        canonical_model = preferred_models[index] if index < len(preferred_models) else ""
        _append_candidate(
            candidates,
            runtime_tag=runtime_tag,
            canonical_model=canonical_model,
            source="preferred",
        )

    fallback_models = _coerce_string_list(role_entry.get("fallback_models", []))
    fallback_model_runtime_tags = _coerce_string_list(
        role_entry.get("fallback_model_runtime_tags", [])
    )
    for index, runtime_tag in enumerate(fallback_model_runtime_tags):
        canonical_model = fallback_models[index] if index < len(fallback_models) else ""
        _append_candidate(
            candidates,
            runtime_tag=runtime_tag,
            canonical_model=canonical_model,
            source="fallback",
        )

    supplementary_models = _coerce_string_list(role_entry.get("supplementary_models", []))
    supplementary_model_runtime_tags = _coerce_string_list(
        role_entry.get("supplementary_model_runtime_tags", [])
    )
    for index, runtime_tag in enumerate(supplementary_model_runtime_tags):
        canonical_model = (
            supplementary_models[index] if index < len(supplementary_models) else ""
        )
        _append_candidate(
            candidates,
            runtime_tag=runtime_tag,
            canonical_model=canonical_model,
            source="supplementary",
        )

    deduped: List[Dict[str, str]] = []
    seen_runtime_tags = set()

    for candidate in candidates:
        runtime_tag = candidate.get("runtime_tag", "")

        if runtime_tag in seen_runtime_tags:
            continue

        seen_runtime_tags.add(runtime_tag)
        deduped.append(candidate)

    return deduped


def _resolve_prompt_path(role_name: str) -> Optional[Path]:
    """
    Resolve the derived system-prompt path for a supported role.
    """
    return ROLE_PROMPT_PATHS.get(role_name)


def _load_system_prompt(path: Path) -> str:
    """
    Load one derived system prompt as text.
    """
    if not path.exists():
        raise FileNotFoundError(f"Derived system prompt not found: {path}")

    text = path.read_text(encoding="utf-8").strip()

    if not text:
        raise ValueError(f"Derived system prompt is empty: {path}")

    return text


def _normalize_conversation_messages(
    conversation_messages: Optional[Sequence[Dict[str, Any]]],
) -> List[Dict[str, str]]:
    """
    Normalize chat history into Ollama-compatible message dicts.

    Only user and assistant messages are carried here. The invoker provides
    the system prompt separately from derived role files.
    """
    if not conversation_messages:
        return []

    normalized: List[Dict[str, str]] = []

    for message in conversation_messages:
        if not isinstance(message, dict):
            continue

        role = _coerce_string(message.get("role"), "").lower()
        content = _coerce_string(message.get("content"), "")

        if role not in {"user", "assistant"}:
            continue

        if not content:
            continue

        normalized.append(
            {
                "role": role,
                "content": content,
            }
        )

    return normalized


def _compose_user_content(
    message: str,
    context_summary: str = "",
) -> str:
    """
    Compose the current user turn, optionally including a compact context summary.
    """
    message = _coerce_string(message, "")
    context_summary = _coerce_string(context_summary, "")

    if context_summary:
        return (
            "Context summary:\n"
            f"{context_summary}\n\n"
            "User message:\n"
            f"{message}"
        )

    return message


def _build_chat_messages(
    system_prompt: str,
    message: str,
    context_summary: str = "",
    conversation_messages: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Dict[str, str]]:
    """
    Build Ollama chat messages with system prompt, optional history, and the current user turn.
    """
    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    messages.extend(_normalize_conversation_messages(conversation_messages))
    messages.append(
        {
            "role": "user",
            "content": _compose_user_content(message, context_summary=context_summary),
        }
    )

    return messages


def _post_json(
    url: str,
    payload: Dict[str, Any],
    timeout_s: float,
) -> Dict[str, Any]:
    """
    POST one JSON payload and return the decoded JSON response.
    """
    request = urllib_request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib_request.urlopen(request, timeout=timeout_s) as response:
        body = response.read().decode("utf-8")

    parsed = json.loads(body or "{}")

    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object response from Ollama.")

    return parsed


def _list_ollama_models(
    ollama_base_url: str,
    timeout_s: float,
) -> Optional[List[str]]:
    """
    Query the local Ollama tags endpoint for installed model names.

    Returns None if the service cannot be reached or the payload is malformed.
    """
    url = f"{ollama_base_url.rstrip('/')}/api/tags"

    try:
        with urllib_request.urlopen(url, timeout=timeout_s) as response:
            body = response.read().decode("utf-8")

        parsed = json.loads(body or "{}")
        models = parsed.get("models", [])

        if not isinstance(models, list):
            return None

        names: List[str] = []

        for entry in models:
            if not isinstance(entry, dict):
                continue

            name = _coerce_string(entry.get("name"), "")

            if name:
                names.append(name)

        return _dedupe_string_list(names)

    except (urllib_error.URLError, urllib_error.HTTPError, json.JSONDecodeError, ValueError):
        return None


def _ollama_context_window(
    runtime_tag: str,
    *,
    ollama_base_url: str,
    timeout_s: float,
) -> int | None:
    """Read the selected local model's declared context length from Ollama."""
    try:
        payload = _post_json(
            f"{ollama_base_url.rstrip('/')}/api/show",
            {"model": runtime_tag},
            timeout_s,
        )
    except Exception:
        return None
    model_info = _as_mapping(payload.get("model_info", {}))
    for key, value in model_info.items():
        if str(key).endswith(".context_length"):
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed >= 1024:
                return parsed
    return None


def resolve_invocation_target(
    model_routing_decision: Dict[str, Any],
    configs: Dict[str, Any],
    *,
    timeout_s: float = 3.0,
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL,
) -> Dict[str, Any]:
    """Resolve the concrete local runtime and context window before budgeting.

    This uses the same ordered role candidates as ``invoke_model``. If Ollama
    is cold/unavailable, the declared first candidate and an explicit fallback
    window are reported rather than inventing a different route.
    """
    routing = _as_mapping(model_routing_decision)
    role = _resolve_role_entry(routing, configs)
    candidates = _build_runtime_candidates(_as_mapping(role.get("role_entry", {})))
    available = _list_ollama_models(
        ollama_base_url=ollama_base_url,
        timeout_s=timeout_s,
    )
    routed_runtime_tag = _coerce_string(routing.get("selected_runtime_tag"), "")
    if routed_runtime_tag:
        candidates = sorted(
            candidates,
            key=lambda item: 0 if item.get("runtime_tag") == routed_runtime_tag else 1,
        )
    selected = next(
        (item for item in candidates if available is None or item["runtime_tag"] in available),
        candidates[0] if candidates else {"runtime_tag": "", "canonical_model": "", "source": "none"},
    )
    runtime_tag = str(selected.get("runtime_tag") or "")
    context_window = (
        _ollama_context_window(
            runtime_tag,
            ollama_base_url=ollama_base_url,
            timeout_s=timeout_s,
        )
        if runtime_tag and available is not None
        else None
    )
    return {
        "runtime_tag": runtime_tag,
        "canonical_model": str(selected.get("canonical_model") or ""),
        "candidate_source": str(selected.get("source") or ""),
        "context_window": context_window or DEFAULT_LOCAL_CONTEXT_WINDOW,
        "context_window_source": "ollama_model_info" if context_window else "explicit_safe_fallback",
        "ollama_available": available is not None,
        "available_candidate": available is None or runtime_tag in available,
    }


def _sanitize_provider_metadata(response: Dict[str, Any]) -> Dict[str, Any]:
    """Keep timing/count/device truth; exclude generated text and hidden reasoning."""
    allowed = {
        "model", "created_at", "done", "done_reason", "total_duration",
        "load_duration", "prompt_eval_count", "prompt_eval_duration",
        "eval_count", "eval_duration", "first_token_ms", "stream_transport",
    }
    return {key: response.get(key) for key in allowed if response.get(key) is not None}


def _call_ollama_chat(
    runtime_tag: str,
    system_prompt: str,
    message: str,
    context_summary: str = "",
    conversation_messages: Optional[Sequence[Dict[str, Any]]] = None,
    timeout_s: float = 180.0,
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL,
    cancel_check: Callable[[], bool] | None = None,
    stream_transport: bool = True,
    num_gpu: int | None = None,
    max_output_tokens: int | None = None,
) -> Dict[str, Any]:
    """
    Call Ollama's local chat endpoint, using cancellable NDJSON streaming by default.
    """
    url = f"{ollama_base_url.rstrip('/')}/api/chat"

    payload: Dict[str, Any] = {
        "model": runtime_tag,
        "messages": _build_chat_messages(
            system_prompt=system_prompt,
            message=message,
            context_summary=context_summary,
            conversation_messages=conversation_messages,
        ),
        "stream": bool(stream_transport),
        "keep_alive": "5m",
    }
    options: Dict[str, Any] = {}
    if num_gpu is not None:
        options["num_gpu"] = int(num_gpu)
    if max_output_tokens is not None:
        options["num_predict"] = max(1, int(max_output_tokens))
    if options:
        payload["options"] = options

    start_time = time.perf_counter()

    try:
        if not stream_transport:
            response = _post_json(url, payload, timeout_s=timeout_s)
        else:
            request = urllib_request.Request(
                url=url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            chunks: list[str] = []
            final: Dict[str, Any] = {}
            first_token_ms: int | None = None
            with urllib_request.urlopen(request, timeout=timeout_s) as stream:
                for raw_line in stream:
                    if cancel_check is not None and cancel_check():
                        stream.close()
                        return {
                            "ok": False,
                            "cancelled": True,
                            "error": "operator_cancelled",
                            "latency_ms": int((time.perf_counter() - start_time) * 1000),
                            "provider_metadata": {"stream_transport": True},
                        }
                    if not raw_line.strip():
                        continue
                    item = json.loads(raw_line.decode("utf-8"))
                    if not isinstance(item, dict):
                        continue
                    raw_content = _as_mapping(item.get("message", {})).get("content")
                    # Token chunks are exact text fragments.  The general string
                    # normalizer strips whitespace and would concatenate
                    # ``"Hello "`` and ``"locally"`` incorrectly.
                    content = raw_content if isinstance(raw_content, str) else ""
                    if content:
                        if first_token_ms is None:
                            first_token_ms = int((time.perf_counter() - start_time) * 1000)
                        chunks.append(content)
                    final = item
            response = dict(final)
            response["message"] = {"role": "assistant", "content": "".join(chunks)}
            response["first_token_ms"] = first_token_ms
            response["stream_transport"] = True
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        response_message = _as_mapping(response.get("message", {}))
        response_text = _coerce_string(response_message.get("content"), "")

        if not response_text:
            return {
                "ok": False,
                "error": "Ollama returned no assistant content.",
                "latency_ms": elapsed_ms,
                "provider_metadata": _sanitize_provider_metadata(response),
            }

        return {
            "ok": True,
            "response_text": response_text,
            "latency_ms": elapsed_ms,
            "provider_metadata": _sanitize_provider_metadata(response),
        }
    except urllib_error.HTTPError as exc:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""

        error_message = body.strip() or str(exc)

        return {
            "ok": False,
            "error": f"Ollama HTTP error: {error_message}",
            "latency_ms": elapsed_ms,
            "provider_metadata": {},
        }

    except urllib_error.URLError as exc:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        return {
            "ok": False,
            "error": f"Ollama unavailable: {exc}",
            "latency_ms": elapsed_ms,
            "provider_metadata": {},
        }

    except TimeoutError:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        return {
            "ok": False,
            "error": "Ollama request timed out.",
            "latency_ms": elapsed_ms,
            "provider_metadata": {
                "timeout": True,
                "stream_transport": bool(stream_transport),
            },
        }

    except (json.JSONDecodeError, ValueError) as exc:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        return {
            "ok": False,
            "error": f"Ollama response decoding failed: {exc}",
            "latency_ms": elapsed_ms,
            "provider_metadata": {},
        }


def _build_base_result(
    model_routing_decision: Dict[str, Any],
    role_name: str = "",
    role_container: str = "",
) -> Dict[str, Any]:
    """
    Build the base structured result shared by all invoker outcomes.
    """
    routing = _as_mapping(model_routing_decision)

    return {
        "status": "error",
        "allowed": _coerce_bool(routing.get("allowed", False), False),
        "stayed_local": _coerce_bool(routing.get("stayed_local", False), False),
        "selected_role": _coerce_string(routing.get("selected_role"), role_name),
        "selected_role_container": _coerce_string(
            routing.get("selected_role_container"),
            role_container,
        ),
        "selected_target": _coerce_string(routing.get("selected_target"), ""),
        "selected_model": _coerce_string(routing.get("selected_model"), ""),
        "selected_model_runtime_tag": "",
        "selected_runtime": _coerce_string(routing.get("selected_runtime"), ""),
        "selected_service": _coerce_string(routing.get("selected_service"), ""),
        "used_fallback": False,
        "fallback_from": "",
        "fallback_to": "",
        "prompt_source": "",
        "response_text": "",
        "error": "",
        "block_reasons": _coerce_string_list(routing.get("route_block_reasons", [])),
        "unmet_requirements": _coerce_string_list(routing.get("unmet_requirements", [])),
        "latency_ms": 0,
        "provider_metadata": {},
        "note": "",
    }


def invoke_model(
    message: str,
    model_routing_decision: Dict[str, Any],
    configs: Dict[str, Any],
    mode: str = "",
    task_type: str = "",
    context_summary: str = "",
    conversation_messages: Optional[Sequence[Dict[str, Any]]] = None,
    timeout_s: float = 180.0,
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL,
    cancel_check: Callable[[], bool] | None = None,
    stream_transport: bool = True,
    num_gpu: int | None = None,
    max_output_tokens: int | None = None,
) -> Dict[str, Any]:
    """
    Invoke the selected local model according to an already-governed routing decision.

    Current phase behavior:
    - supports local Ollama-backed roles only
    - loads derived system prompts from derived/runtime/
    - resolves preferred and fallback runtime tags from model_roles config
    - blocks external/helper routing rather than silently improvising around it
    """
    del mode
    del task_type

    routing = _as_mapping(model_routing_decision)

    role_resolution = _resolve_role_entry(routing, configs)
    role_name = _coerce_string(role_resolution.get("role_name"), "")
    role_container = _coerce_string(role_resolution.get("container_name"), "")
    role_entry = _as_mapping(role_resolution.get("role_entry", {}))

    result = _build_base_result(
        model_routing_decision=routing,
        role_name=role_name,
        role_container=role_container,
    )

    if not _coerce_bool(routing.get("allowed", False), False):
        result["status"] = "blocked"
        result["note"] = (
            "Model invocation blocked because the routed path was not allowed."
        )
        return result

    if not _coerce_bool(routing.get("stayed_local", False), False):
        result["status"] = "blocked"
        result["block_reasons"] = _dedupe_string_list(
            result["block_reasons"] + ["local_invoker_refuses_nonlocal_route"]
        )
        result["note"] = (
            "Model invocation blocked because the invoker only supports local paths."
        )
        return result

    selected_runtime = _coerce_string(routing.get("selected_runtime"), "").lower()
    selected_is_external = _coerce_bool(routing.get("selected_is_external", False), False)
    selected_target = _coerce_string(routing.get("selected_target"), "")

    if selected_is_external or selected_target == "external_helper":
        result["status"] = "blocked"
        result["block_reasons"] = _dedupe_string_list(
            result["block_reasons"] + ["external_helper_invocation_not_supported"]
        )
        result["note"] = (
            "Model invocation blocked because external helper routing is not "
            "supported in the local invoker."
        )
        return result

    if selected_runtime and selected_runtime != "ollama":
        result["status"] = "blocked"
        result["block_reasons"] = _dedupe_string_list(
            result["block_reasons"] + ["unsupported_runtime_for_local_invoker"]
        )
        result["note"] = (
            "Model invocation blocked because the selected runtime is not Ollama."
        )
        return result

    if role_container != "roles" or not role_entry:
        result["status"] = "error"
        result["error"] = "Selected local role could not be resolved from model_roles config."
        result["note"] = (
            "Model invocation failed because the selected role could not be "
            "resolved from normalized config."
        )
        return result

    prompt_path = _resolve_prompt_path(role_name)

    if prompt_path is None:
        result["status"] = "error"
        result["error"] = (
            f"No derived system prompt path is defined for role: {role_name}"
        )
        result["note"] = (
            "Model invocation failed because no derived prompt mapping exists "
            "for the selected role."
        )
        return result

    try:
        system_prompt = _load_system_prompt(prompt_path)
    except (FileNotFoundError, ValueError) as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        result["prompt_source"] = str(prompt_path.relative_to(PROJECT_ROOT))
        result["note"] = (
            "Model invocation failed because the derived role prompt could not be loaded."
        )
        return result

    runtime_candidates = _build_runtime_candidates(role_entry)
    configured_first_candidate = runtime_candidates[0] if runtime_candidates else {}
    routed_runtime_tag = _coerce_string(routing.get("selected_runtime_tag"), "")
    if routed_runtime_tag:
        runtime_candidates = sorted(
            runtime_candidates,
            key=lambda item: 0 if item.get("runtime_tag") == routed_runtime_tag else 1,
        )

    if not runtime_candidates:
        result["status"] = "error"
        result["prompt_source"] = str(prompt_path.relative_to(PROJECT_ROOT))
        result["error"] = (
            f"No runtime candidates were declared for role: {role_name}"
        )
        result["note"] = (
            "Model invocation failed because the selected role has no usable local runtime tags."
        )
        return result

    available_models = _list_ollama_models(
        ollama_base_url=ollama_base_url,
        timeout_s=min(timeout_s, 15.0),
    )

    prompt_source = str(prompt_path.relative_to(PROJECT_ROOT))
    first_candidate = configured_first_candidate or runtime_candidates[0]
    first_runtime_tag = _coerce_string(first_candidate.get("runtime_tag"), "")
    first_canonical_model = _coerce_string(first_candidate.get("canonical_model"), "")
    # An adaptive router may deliberately earn a configured alternate model
    # for latency/resource reasons.  That is the selected path, not a degraded
    # provider fallback.  Only moving away from the routed target after an
    # unavailable/failed attempt is a fallback.
    requested_runtime_tag = routed_runtime_tag or first_runtime_tag

    last_error = ""
    accumulated_block_reasons: List[str] = list(result["block_reasons"])

    for candidate in runtime_candidates:
        runtime_tag = _coerce_string(candidate.get("runtime_tag"), "")
        canonical_model = _coerce_string(candidate.get("canonical_model"), "")

        if available_models is not None and runtime_tag not in available_models:
            last_error = f"Local Ollama model not installed: {runtime_tag}"
            accumulated_block_reasons.append("selected_model_not_installed_locally")
            continue

        call_result = _call_ollama_chat(
            runtime_tag=runtime_tag,
            system_prompt=system_prompt,
            message=message,
            context_summary=context_summary,
            conversation_messages=conversation_messages,
            timeout_s=timeout_s,
            ollama_base_url=ollama_base_url,
            cancel_check=cancel_check,
            stream_transport=stream_transport,
            num_gpu=num_gpu,
            max_output_tokens=max_output_tokens,
        )

        try:
            from app.cognition.model_registry import ModelRegistry

            ModelRegistry().record_outcome(
                runtime_tag=runtime_tag,
                status="ok" if call_result.get("ok") else "cancelled" if call_result.get("cancelled") else "error",
                latency_ms=int(call_result.get("latency_ms") or 0),
                provider_metadata=_as_mapping(call_result.get("provider_metadata", {})),
            )
        except Exception:
            pass

        if call_result.get("ok", False):
            used_fallback = runtime_tag != requested_runtime_tag

            result.update(
                {
                    "status": "ok",
                    "selected_model": canonical_model or first_canonical_model,
                    "selected_model_runtime_tag": runtime_tag,
                    "selected_runtime": "ollama",
                    "used_fallback": used_fallback,
                    "fallback_from": requested_runtime_tag if used_fallback else "",
                    "fallback_to": runtime_tag if used_fallback else "",
                    "prompt_source": prompt_source,
                    "response_text": _coerce_string(call_result.get("response_text"), ""),
                    "latency_ms": int(call_result.get("latency_ms", 0) or 0),
                    "provider_metadata": deepcopy(
                        _as_mapping(call_result.get("provider_metadata", {}))
                    ),
                    "block_reasons": _dedupe_string_list(accumulated_block_reasons),
                    "note": (
                        "Local Ollama invocation succeeded using the selected role."
                        if not used_fallback
                        else "Local Ollama invocation succeeded using an allowed local fallback."
                    ),
                }
            )
            return result

        last_error = _coerce_string(call_result.get("error"), "Unknown Ollama invocation failure.")
        if call_result.get("cancelled"):
            accumulated_block_reasons.append("operator_cancelled")
            break
        accumulated_block_reasons.append("local_invocation_attempt_failed")

    result["status"] = "error"
    result["selected_model"] = first_canonical_model
    result["selected_model_runtime_tag"] = first_runtime_tag
    result["selected_runtime"] = "ollama"
    result["prompt_source"] = prompt_source
    result["error"] = last_error or "No local invocation candidate succeeded."
    result["block_reasons"] = _dedupe_string_list(accumulated_block_reasons)
    result["note"] = (
        "Local Ollama invocation failed and no allowed local fallback succeeded."
    )
    return result


if __name__ == "__main__":
    from .config_loader import load_all_configs
    from .model_routing import build_model_routing_decision

    configs = load_all_configs()

    routing_decision = build_model_routing_decision(
        configs=configs,
        mode="default",
        task_type="conversation",
        autonomy_level=1,
        context_flags=[],
    )

    result = invoke_model(
        message="In one sentence, who are you?",
        model_routing_decision=routing_decision,
        configs=configs,
    )

    print(json.dumps(result, indent=2))
