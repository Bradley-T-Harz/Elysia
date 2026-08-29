import io
import json
from pathlib import Path
from urllib import error as urllib_error

import pytest

from core import model_invoker as invoker


@pytest.fixture
def base_configs():
    return {
        "models": {
            "model_roles": {
                "roles": {
                    "primary_general": {
                        "preferred_model": "qwen3:8b",
                        "preferred_model_runtime_tag": "qwen3:8b",
                        "fallback_models": ["llama3.1:8b"],
                        "fallback_model_runtime_tags": ["llama3.1:8b"],
                    },
                    "primary_code": {
                        "preferred_models": ["qwen2.5-coder:7b"],
                        "preferred_model_runtime_tags": ["qwen2.5-coder:7b"],
                    },
                    "lighter_backup": {
                        "preferred_model": "phi4-mini",
                        "preferred_model_runtime_tag": "phi4-mini",
                    },
                },
                "external_helpers": {
                    "web_search": {
                        "service": "external_helper",
                        "preferred_model": "cloud-search",
                    }
                },
            }
        }
    }


@pytest.fixture
def prompt_environment(tmp_path, monkeypatch):
    project_root = tmp_path
    runtime_dir = project_root / "derived" / "runtime"
    runtime_dir.mkdir(parents=True)

    prompt_paths = {
        "primary_general": runtime_dir / "elysia_general_system.txt",
        "primary_code": runtime_dir / "elysia_code_system.txt",
        "lighter_backup": runtime_dir / "elysia_light_system.txt",
        "optional_fallback": runtime_dir / "elysia_utility_system.txt",
    }

    for role_name, path in prompt_paths.items():
        path.write_text(f"System prompt for {role_name}", encoding="utf-8")

    monkeypatch.setattr(invoker, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(invoker, "DERIVED_RUNTIME_ROOT", runtime_dir)
    monkeypatch.setattr(invoker, "ROLE_PROMPT_PATHS", prompt_paths)

    return {
        "project_root": project_root,
        "runtime_dir": runtime_dir,
        "prompt_paths": prompt_paths,
    }


@pytest.fixture
def routing_decision():
    return {
        "allowed": True,
        "stayed_local": True,
        "selected_role": "primary_general",
        "selected_role_container": "roles",
        "selected_target": "local_model",
        "selected_model": "qwen3:8b",
        "selected_runtime": "ollama",
        "selected_service": "ollama",
        "selected_is_external": False,
        "route_block_reasons": [],
        "unmet_requirements": [],
    }


def make_http_error(body: bytes = b"server exploded") -> urllib_error.HTTPError:
    return urllib_error.HTTPError(
        url="http://127.0.0.1:11434/api/chat",
        code=500,
        msg="Internal Server Error",
        hdrs=None,
        fp=io.BytesIO(body),
    )


def test_helper_normalization_functions():
    assert invoker._as_mapping({"a": 1}) == {"a": 1}
    assert invoker._as_mapping([1, 2, 3]) == {}

    assert invoker._coerce_bool(True, default=False) is True
    assert invoker._coerce_bool("yes", default=False) is True
    assert invoker._coerce_bool("off", default=True) is False
    assert invoker._coerce_bool(None, default=True) is True

    assert invoker._coerce_string("  hello  ") == "hello"
    assert invoker._coerce_string("   ", default="fallback") == "fallback"

    assert invoker._coerce_string_list([" a ", "", None, "b"]) == ["a", "b"]
    assert invoker._coerce_string_list(" solo ") == ["solo"]
    assert invoker._coerce_string_list(None) == []

    assert invoker._dedupe_string_list(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]


def test_resolve_role_entry_prefers_declared_container_and_falls_back(base_configs, routing_decision):
    resolved = invoker._resolve_role_entry(routing_decision, base_configs)
    assert resolved["container_name"] == "roles"
    assert resolved["role_name"] == "primary_general"
    assert resolved["role_entry"]["preferred_model_runtime_tag"] == "qwen3:8b"

    external_routing = dict(routing_decision)
    external_routing.update(
        {
            "selected_role": "web_search",
            "selected_role_container": "external_helpers",
        }
    )
    resolved_external = invoker._resolve_role_entry(external_routing, base_configs)
    assert resolved_external["container_name"] == "external_helpers"
    assert resolved_external["role_name"] == "web_search"

    implicit_routing = dict(routing_decision)
    implicit_routing.update(
        {
            "selected_role": "primary_code",
            "selected_role_container": "",
        }
    )
    resolved_implicit = invoker._resolve_role_entry(implicit_routing, base_configs)
    assert resolved_implicit["container_name"] == "roles"
    assert resolved_implicit["role_name"] == "primary_code"

    missing_routing = dict(routing_decision)
    missing_routing["selected_role"] = "does_not_exist"
    missing = invoker._resolve_role_entry(missing_routing, base_configs)
    assert missing == {
        "container_name": "",
        "role_name": "does_not_exist",
        "role_entry": {},
    }


def test_build_runtime_candidates_prioritizes_and_dedupes():
    role_entry = {
        "preferred_model": "qwen3:8b",
        "preferred_model_runtime_tag": "qwen3:8b",
        "preferred_models": ["qwen3:8b", "qwen2.5-coder:7b"],
        "preferred_model_runtime_tags": ["qwen3:8b", "qwen2.5-coder:7b"],
        "fallback_models": ["llama3.1:8b", "phi4-mini"],
        "fallback_model_runtime_tags": ["llama3.1:8b", "phi4-mini"],
        "supplementary_models": ["mistral:7b", "phi4-mini"],
        "supplementary_model_runtime_tags": ["mistral:7b", "phi4-mini"],
    }

    candidates = invoker._build_runtime_candidates(role_entry)

    assert [candidate["runtime_tag"] for candidate in candidates] == [
        "qwen3:8b",
        "qwen2.5-coder:7b",
        "llama3.1:8b",
        "phi4-mini",
        "mistral:7b",
    ]
    assert candidates[0]["source"] == "preferred"
    assert candidates[2]["source"] == "fallback"
    assert candidates[-1]["source"] == "supplementary"


def test_resolve_prompt_path_and_load_system_prompt(prompt_environment):
    prompt_path = invoker._resolve_prompt_path("primary_general")
    assert prompt_path == prompt_environment["prompt_paths"]["primary_general"]
    assert invoker._load_system_prompt(prompt_path) == "System prompt for primary_general"


@pytest.mark.parametrize(
    ("writer", "expected_exception", "expected_text"),
    [
        (
            lambda path: None,
            FileNotFoundError,
            "Derived system prompt not found",
        ),
        (
            lambda path: path.write_text("   ", encoding="utf-8"),
            ValueError,
            "Derived system prompt is empty",
        ),
    ],
)
def test_load_system_prompt_error_cases(tmp_path, writer, expected_exception, expected_text):
    path = tmp_path / "prompt.txt"
    writer(path)

    with pytest.raises(expected_exception, match=expected_text):
        invoker._load_system_prompt(path)


def test_normalize_conversation_messages_filters_invalid_history():
    messages = [
        {"role": "system", "content": "ignore me"},
        {"role": "user", "content": "  hello  "},
        {"role": "assistant", "content": "world"},
        {"role": "tool", "content": "ignore me too"},
        {"role": "user", "content": "   "},
        "not a mapping",
    ]

    normalized = invoker._normalize_conversation_messages(messages)

    assert normalized == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]


def test_build_chat_messages_uses_system_prompt_history_and_context_summary():
    messages = invoker._build_chat_messages(
        system_prompt="You are Elysia.",
        message="Answer carefully.",
        context_summary="Project: UI build",
        conversation_messages=[
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
            {"role": "system", "content": "Should not survive"},
        ],
    )

    assert messages[0] == {"role": "system", "content": "You are Elysia."}
    assert messages[1:3] == [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier answer"},
    ]
    assert messages[-1]["role"] == "user"
    assert "Context summary:" in messages[-1]["content"]
    assert "Project: UI build" in messages[-1]["content"]
    assert "User message:" in messages[-1]["content"]
    assert "Answer carefully." in messages[-1]["content"]


def test_call_ollama_chat_success_builds_payload_and_result(monkeypatch):
    captured = {}

    def fake_post_json(url, payload, timeout_s):
        captured["url"] = url
        captured["payload"] = payload
        captured["timeout_s"] = timeout_s
        return {"message": {"content": "Hello from Ollama"}, "done": True}

    monkeypatch.setattr(invoker, "_post_json", fake_post_json)

    result = invoker._call_ollama_chat(
        runtime_tag="qwen3:8b",
        system_prompt="You are Elysia.",
        message="Say hello.",
        context_summary="Local-only mode",
        conversation_messages=[{"role": "assistant", "content": "Prior reply"}],
        timeout_s=12.0,
        ollama_base_url="http://127.0.0.1:11434",
        stream_transport=False,
        num_gpu=0,
        max_output_tokens=256,
    )

    assert result["ok"] is True
    assert result["response_text"] == "Hello from Ollama"
    assert result["latency_ms"] >= 0
    assert result["provider_metadata"]["done"] is True

    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["timeout_s"] == 12.0
    assert captured["payload"]["model"] == "qwen3:8b"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["options"] == {"num_gpu": 0, "num_predict": 256}
    assert captured["payload"]["messages"][0] == {
        "role": "system",
        "content": "You are Elysia.",
    }


def test_streaming_transport_measures_first_token_and_supports_cancellation(monkeypatch):
    class FakeStream:
        def __init__(self, rows):
            self.rows = rows
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

        def __iter__(self):
            return iter(self.rows)

        def close(self):
            self.closed = True

    completed = FakeStream([
        b'{"message":{"content":"Hello "},"done":false}\n',
        b'{"message":{"content":"locally."},"done":true,"eval_count":2}\n',
    ])
    monkeypatch.setattr(invoker.urllib_request, "urlopen", lambda *_args, **_kwargs: completed)
    result = invoker._call_ollama_chat(
        runtime_tag="synthetic:local", system_prompt="system", message="hello",
        stream_transport=True,
    )
    assert result["ok"] is True
    assert result["response_text"] == "Hello locally."
    assert result["provider_metadata"]["stream_transport"] is True
    assert result["provider_metadata"]["first_token_ms"] >= 0
    assert completed.closed is True

    interrupted = FakeStream([
        b'{"message":{"content":"partial"},"done":false}\n',
        b'{"message":{"content":" must not escape"},"done":true}\n',
    ])
    checks = iter((False, True))
    monkeypatch.setattr(invoker.urllib_request, "urlopen", lambda *_args, **_kwargs: interrupted)
    cancelled = invoker._call_ollama_chat(
        runtime_tag="synthetic:local", system_prompt="system", message="hello",
        cancel_check=lambda: next(checks), stream_transport=True,
    )
    assert cancelled["ok"] is False
    assert cancelled["cancelled"] is True
    assert "response_text" not in cancelled
    assert interrupted.closed is True


@pytest.mark.parametrize(
    ("fake_post", "expected_substring"),
    [
        (
            lambda *_args, **_kwargs: {"message": {"content": ""}},
            "Ollama returned no assistant content",
        ),
        (
            lambda *_args, **_kwargs: (_ for _ in ()).throw(make_http_error(b"bad request")),
            "Ollama HTTP error: bad request",
        ),
        (
            lambda *_args, **_kwargs: (_ for _ in ()).throw(urllib_error.URLError("connection refused")),
            "Ollama unavailable",
        ),
        (
            lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad json")),
            "Ollama response decoding failed",
        ),
    ],
)
def test_call_ollama_chat_error_paths(monkeypatch, fake_post, expected_substring):
    monkeypatch.setattr(invoker, "_post_json", fake_post)

    result = invoker._call_ollama_chat(
        runtime_tag="qwen3:8b",
        system_prompt="system",
        message="hello",
        stream_transport=False,
    )

    assert result["ok"] is False
    assert expected_substring in result["error"]
    assert result["provider_metadata"] == {}
    assert result["latency_ms"] >= 0


def test_call_ollama_chat_returns_structured_timeout(monkeypatch):
    monkeypatch.setattr(
        invoker.urllib_request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()),
    )

    result = invoker._call_ollama_chat(
        runtime_tag="qwen3:8b",
        system_prompt="system",
        message="hello",
        stream_transport=True,
    )

    assert result == {
        "ok": False,
        "error": "Ollama request timed out.",
        "latency_ms": result["latency_ms"],
        "provider_metadata": {
            "timeout": True,
            "stream_transport": True,
        },
    }
    assert result["latency_ms"] >= 0


def test_build_base_result_contains_expected_contract_fields(routing_decision):
    result = invoker._build_base_result(routing_decision, role_name="primary_general", role_container="roles")

    expected_keys = {
        "status",
        "allowed",
        "stayed_local",
        "selected_role",
        "selected_role_container",
        "selected_target",
        "selected_model",
        "selected_model_runtime_tag",
        "selected_runtime",
        "selected_service",
        "used_fallback",
        "fallback_from",
        "fallback_to",
        "prompt_source",
        "response_text",
        "error",
        "block_reasons",
        "unmet_requirements",
        "latency_ms",
        "provider_metadata",
        "note",
    }

    assert expected_keys.issubset(result.keys())
    assert result["selected_role"] == "primary_general"
    assert result["selected_role_container"] == "roles"
    assert result["block_reasons"] == []
    assert result["unmet_requirements"] == []


def test_invoke_model_blocks_disallowed_route(base_configs, routing_decision, prompt_environment):
    decision = dict(routing_decision)
    decision["allowed"] = False

    result = invoker.invoke_model(
        message="Hello",
        model_routing_decision=decision,
        configs=base_configs,
    )

    assert result["status"] == "blocked"
    assert result["allowed"] is False
    assert "not allowed" in result["note"]


@pytest.mark.parametrize(
    ("updates", "expected_block_reason", "expected_note_text"),
    [
        (
            {"stayed_local": False},
            "local_invoker_refuses_nonlocal_route",
            "only supports local paths",
        ),
        (
            {"selected_is_external": True},
            "external_helper_invocation_not_supported",
            "external helper routing",
        ),
        (
            {"selected_target": "external_helper"},
            "external_helper_invocation_not_supported",
            "external helper routing",
        ),
        (
            {"selected_runtime": "openai"},
            "unsupported_runtime_for_local_invoker",
            "selected runtime is not Ollama",
        ),
    ],
)
def test_invoke_model_blocks_nonlocal_external_and_unsupported_runtime(
    base_configs,
    routing_decision,
    prompt_environment,
    updates,
    expected_block_reason,
    expected_note_text,
):
    decision = dict(routing_decision)
    decision.update(updates)

    result = invoker.invoke_model(
        message="Hello",
        model_routing_decision=decision,
        configs=base_configs,
    )

    assert result["status"] == "blocked"
    assert expected_block_reason in result["block_reasons"]
    assert expected_note_text in result["note"]


def test_invoke_model_errors_when_role_cannot_be_resolved(base_configs, routing_decision, prompt_environment):
    decision = dict(routing_decision)
    decision["selected_role"] = "missing_role"

    result = invoker.invoke_model(
        message="Hello",
        model_routing_decision=decision,
        configs=base_configs,
    )

    assert result["status"] == "error"
    assert "could not be resolved" in result["error"]
    assert "normalized config" in result["note"]


def test_invoke_model_errors_when_prompt_mapping_missing(base_configs, routing_decision, prompt_environment, monkeypatch):
    monkeypatch.setattr(invoker, "ROLE_PROMPT_PATHS", {"primary_code": prompt_environment["prompt_paths"]["primary_code"]})

    result = invoker.invoke_model(
        message="Hello",
        model_routing_decision=routing_decision,
        configs=base_configs,
    )

    assert result["status"] == "error"
    assert "No derived system prompt path is defined" in result["error"]
    assert "no derived prompt mapping exists" in result["note"]


@pytest.mark.parametrize(
    ("writer", "error_substring"),
    [
        (None, "Derived system prompt not found"),
        (lambda path: path.write_text("   ", encoding="utf-8"), "Derived system prompt is empty"),
    ],
)
def test_invoke_model_errors_when_prompt_cannot_be_loaded(
    base_configs,
    routing_decision,
    tmp_path,
    monkeypatch,
    writer,
    error_substring,
):
    project_root = tmp_path
    prompt_path = project_root / "derived" / "runtime" / "elysia_general_system.txt"
    prompt_path.parent.mkdir(parents=True)
    if writer is not None:
        writer(prompt_path)

    monkeypatch.setattr(invoker, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(invoker, "ROLE_PROMPT_PATHS", {"primary_general": prompt_path})

    result = invoker.invoke_model(
        message="Hello",
        model_routing_decision=routing_decision,
        configs=base_configs,
    )

    assert result["status"] == "error"
    assert error_substring in result["error"]
    assert result["prompt_source"] == "derived/runtime/elysia_general_system.txt"


def test_invoke_model_errors_when_no_runtime_candidates(
    base_configs,
    routing_decision,
    prompt_environment,
):
    configs = {
        "models": {
            "model_roles": {
                "roles": {
                    "primary_general": {
                        "notes": "declared without runtime tags",
                    },
                },
                "external_helpers": {},
            }
        }
    }

    result = invoker.invoke_model(
        message="Hello",
        model_routing_decision=routing_decision,
        configs=configs,
    )

    assert result["status"] == "error"
    assert "No runtime candidates were declared" in result["error"]
    assert result["prompt_source"] == "derived/runtime/elysia_general_system.txt"


def test_invoke_model_succeeds_on_preferred_runtime(
    base_configs,
    routing_decision,
    prompt_environment,
    monkeypatch,
):
    monkeypatch.setattr(invoker, "_list_ollama_models", lambda **_kwargs: ["qwen3:8b", "llama3.1:8b"])
    monkeypatch.setattr(
        invoker,
        "_call_ollama_chat",
        lambda **_kwargs: {
            "ok": True,
            "response_text": "Local answer",
            "latency_ms": 42,
            "provider_metadata": {"total_duration": 1000},
        },
    )

    result = invoker.invoke_model(
        message="Hello",
        model_routing_decision=routing_decision,
        configs=base_configs,
        context_summary="Project: UI",
        conversation_messages=[{"role": "user", "content": "Earlier"}],
    )

    assert result["status"] == "ok"
    assert result["selected_model_runtime_tag"] == "qwen3:8b"
    assert result["selected_runtime"] == "ollama"
    assert result["used_fallback"] is False
    assert result["fallback_from"] == ""
    assert result["fallback_to"] == ""
    assert result["prompt_source"] == "derived/runtime/elysia_general_system.txt"
    assert result["response_text"] == "Local answer"
    assert result["latency_ms"] == 42
    assert result["provider_metadata"] == {"total_duration": 1000}
    assert "selected role" in result["note"]


def test_invoke_model_uses_allowed_local_fallback_when_preferred_not_installed(
    base_configs,
    routing_decision,
    prompt_environment,
    monkeypatch,
):
    monkeypatch.setattr(invoker, "_list_ollama_models", lambda **_kwargs: ["llama3.1:8b"])

    def fake_call(**kwargs):
        assert kwargs["runtime_tag"] == "llama3.1:8b"
        return {
            "ok": True,
            "response_text": "Fallback answer",
            "latency_ms": 55,
            "provider_metadata": {"model": "llama3.1:8b"},
        }

    monkeypatch.setattr(invoker, "_call_ollama_chat", fake_call)

    result = invoker.invoke_model(
        message="Hello",
        model_routing_decision=routing_decision,
        configs=base_configs,
    )

    assert result["status"] == "ok"
    assert result["used_fallback"] is True
    assert result["fallback_from"] == "qwen3:8b"
    assert result["fallback_to"] == "llama3.1:8b"
    assert result["selected_model_runtime_tag"] == "llama3.1:8b"
    assert "selected_model_not_installed_locally" in result["block_reasons"]
    assert "allowed local fallback" in result["note"]


def test_invoke_model_treats_router_selected_alternate_as_primary_path(
    base_configs,
    routing_decision,
    prompt_environment,
    monkeypatch,
):
    routing_decision = dict(routing_decision)
    routing_decision["selected_runtime_tag"] = "llama3.1:8b"
    monkeypatch.setattr(
        invoker,
        "_list_ollama_models",
        lambda **_kwargs: ["qwen3:8b", "llama3.1:8b"],
    )
    monkeypatch.setattr(
        invoker,
        "_call_ollama_chat",
        lambda **kwargs: {
            "ok": True,
            "response_text": f"Adaptive answer from {kwargs['runtime_tag']}",
            "latency_ms": 40,
            "provider_metadata": {},
        },
    )

    result = invoker.invoke_model(
        message="Hello",
        model_routing_decision=routing_decision,
        configs=base_configs,
    )

    assert result["status"] == "ok"
    assert result["selected_model_runtime_tag"] == "llama3.1:8b"
    assert result["used_fallback"] is False
    assert result["fallback_from"] == ""
    assert result["fallback_to"] == ""


def test_invoke_model_uses_allowed_local_fallback_when_preferred_call_fails(
    base_configs,
    routing_decision,
    prompt_environment,
    monkeypatch,
):
    monkeypatch.setattr(invoker, "_list_ollama_models", lambda **_kwargs: ["qwen3:8b", "llama3.1:8b"])
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs["runtime_tag"])
        if kwargs["runtime_tag"] == "qwen3:8b":
            return {
                "ok": False,
                "error": "Primary model timed out",
                "latency_ms": 100,
                "provider_metadata": {},
            }
        return {
            "ok": True,
            "response_text": "Fallback recovered",
            "latency_ms": 65,
            "provider_metadata": {"model": "llama3.1:8b"},
        }

    monkeypatch.setattr(invoker, "_call_ollama_chat", fake_call)

    result = invoker.invoke_model(
        message="Hello",
        model_routing_decision=routing_decision,
        configs=base_configs,
    )

    assert calls == ["qwen3:8b", "llama3.1:8b"]
    assert result["status"] == "ok"
    assert result["used_fallback"] is True
    assert result["fallback_from"] == "qwen3:8b"
    assert result["fallback_to"] == "llama3.1:8b"
    assert "local_invocation_attempt_failed" in result["block_reasons"]


def test_invoke_model_errors_when_no_models_are_installed(
    base_configs,
    routing_decision,
    prompt_environment,
    monkeypatch,
):
    monkeypatch.setattr(invoker, "_list_ollama_models", lambda **_kwargs: [])

    result = invoker.invoke_model(
        message="Hello",
        model_routing_decision=routing_decision,
        configs=base_configs,
    )

    assert result["status"] == "error"
    assert result["selected_model_runtime_tag"] == "qwen3:8b"
    assert "Local Ollama model not installed" in result["error"]
    assert "selected_model_not_installed_locally" in result["block_reasons"]
    assert "no allowed local fallback succeeded" in result["note"]


def test_invoke_model_errors_when_all_candidates_fail(
    base_configs,
    routing_decision,
    prompt_environment,
    monkeypatch,
):
    monkeypatch.setattr(invoker, "_list_ollama_models", lambda **_kwargs: ["qwen3:8b", "llama3.1:8b"])

    def always_fail(**_kwargs):
        return {
            "ok": False,
            "error": "Provider failure",
            "latency_ms": 88,
            "provider_metadata": {},
        }

    monkeypatch.setattr(invoker, "_call_ollama_chat", always_fail)

    result = invoker.invoke_model(
        message="Hello",
        model_routing_decision=routing_decision,
        configs=base_configs,
    )

    assert result["status"] == "error"
    assert result["selected_model_runtime_tag"] == "qwen3:8b"
    assert result["selected_runtime"] == "ollama"
    assert result["error"] == "Provider failure"
    assert "local_invocation_attempt_failed" in result["block_reasons"]
    assert result["prompt_source"] == "derived/runtime/elysia_general_system.txt"
