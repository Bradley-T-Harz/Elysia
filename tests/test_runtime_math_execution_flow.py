from __future__ import annotations

from typing import Any

import pytest

import core.runtime as runtime
from app.api.schemas.execution import (
    ExecutionStatus,
    ExecutionToolKind,
    MathExecutionResult,
)


def _route_value(model_routing_decision: Any, key: str, default: Any = "") -> Any:
    if isinstance(model_routing_decision, dict):
        return model_routing_decision.get(key, default)

    return getattr(model_routing_decision, key, default)


def _fake_invoke_model_factory(captured: dict[str, Any]):
    def _fake_invoke_model(
        *,
        message,
        model_routing_decision,
        configs,
        mode,
        task_type,
        context_summary,
        conversation_messages,
    ):
        captured["message"] = message
        captured["model_routing_decision"] = model_routing_decision
        captured["configs"] = configs
        captured["mode"] = mode
        captured["task_type"] = task_type
        captured["context_summary"] = context_summary
        captured["conversation_messages"] = conversation_messages

        selected_role = _route_value(
            model_routing_decision,
            "selected_role",
            "primary_general",
        )
        selected_target = (
            _route_value(model_routing_decision, "selected_target", "")
            or _route_value(model_routing_decision, "selected_model", "")
            or "mistral-small-3.1"
        )
        selected_runtime = _route_value(
            model_routing_decision,
            "selected_runtime",
            "ollama",
        )
        allowed = bool(_route_value(model_routing_decision, "allowed", True))
        stayed_local = bool(_route_value(model_routing_decision, "stayed_local", True))

        return {
            "status": "ok" if allowed else "blocked",
            "allowed": allowed,
            "stayed_local": stayed_local,
            "selected_role": selected_role,
            "selected_role_container": _route_value(
                model_routing_decision,
                "selected_role_container",
                "roles",
            ),
            "selected_target": selected_target,
            "selected_model": _route_value(
                model_routing_decision,
                "selected_model",
                selected_target,
            ),
            "selected_model_runtime_tag": _route_value(
                model_routing_decision,
                "selected_model_runtime_tag",
                selected_target,
            ),
            "selected_runtime": selected_runtime,
            "selected_service": _route_value(
                model_routing_decision,
                "selected_service",
                selected_runtime,
            ),
            "used_fallback": bool(
                _route_value(model_routing_decision, "used_fallback", False)
            ),
            "fallback_from": _route_value(
                model_routing_decision,
                "fallback_from",
                "",
            ),
            "fallback_to": _route_value(
                model_routing_decision,
                "fallback_to",
                "",
            ),
            "prompt_source": "test/fake_runtime_system.txt",
            "response_text": "Fake governed local answer with checked math context.",
            "error": "",
            "block_reasons": [] if allowed else ["fake_blocked_route"],
            "unmet_requirements": _route_value(
                model_routing_decision,
                "unmet_requirements",
                [],
            ),
            "latency_ms": 0,
            "provider_metadata": {"mocked": True},
            "note": "Live model invocation mocked for deterministic math runtime-flow testing.",
        }

    return _fake_invoke_model


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def test_runtime_math_request_uses_bounded_local_math_execution(monkeypatch):
    captured_invocation: dict[str, Any] = {}
    execution_requests: list[Any] = []

    def fake_run_math_execution(request):
        execution_requests.append(request)

        return MathExecutionResult(
            ok=True,
            status=ExecutionStatus.COMPLETED,
            tool_kind=ExecutionToolKind.MATH_EXECUTOR,
            operation="evaluate",
            input="(4.0875 - 3.27) / 4.0875 * 100",
            result="20.0000000000000",
            numeric_result=20.0,
            locality="local",
            approval_state="not_needed",
            warnings=[],
            errors=[],
        )

    def fake_build_math_execution_context_block(result):
        return (
            "Bounded local math execution result:\n"
            "Tool: math_executor\n"
            "Locality: local\n"
            "Approval required: no\n"
            f"Status: {result.status}\n"
            f"Operation: {result.operation}\n"
            f"Input: {result.input}\n"
            f"Result: {result.result}\n"
            f"Numeric result: {result.numeric_result}\n"
            "Boundary note: this was bounded local math execution, not arbitrary Python, shell, web, or file mutation."
        )

    monkeypatch.setattr(
        runtime,
        "run_math_execution",
        fake_run_math_execution,
        raising=False,
    )
    monkeypatch.setattr(
        runtime,
        "build_math_execution_context_block",
        fake_build_math_execution_context_block,
        raising=False,
    )
    monkeypatch.setattr(
        runtime,
        "invoke_model",
        _fake_invoke_model_factory(captured_invocation),
    )

    result = runtime.handle_user_message(
        "Evaluate (4.0875 - 3.27) / 4.0875 * 100.",
        runtime.SessionState(active_mode="tutor"),
    )

    assert execution_requests, "Runtime should call bounded local math execution."

    request = execution_requests[0]
    operation = _enum_value(
        getattr(request, "operation", None)
        if not isinstance(request, dict)
        else request.get("operation")
    )

    assert operation == "evaluate"

    context_summary = captured_invocation["context_summary"]

    assert "Bounded local math execution result:" in context_summary
    assert "Tool: math_executor" in context_summary
    assert "Numeric result: 20.0" in context_summary
    assert "not arbitrary Python, shell, web, or file mutation" in context_summary

    math_execution = result["math_execution"]

    assert math_execution["used"] is True
    assert math_execution["status"] == "completed"
    assert math_execution["tool_kind"] == "math_executor"
    assert math_execution["operation"] == "evaluate"
    assert math_execution["stayed_local"] is True
    assert math_execution["approval_required"] is False
    assert math_execution["result"] == "20.0000000000000"
    assert math_execution["numeric_result"] == 20.0


def test_runtime_percentage_reduction_uses_full_expression_truth(monkeypatch):
    captured_invocation: dict[str, Any] = {}
    execution_requests: list[Any] = []

    def fake_run_math_execution(request):
        execution_requests.append(request)
        expression = getattr(request, "expression", "")

        return MathExecutionResult(
            ok=True,
            status=ExecutionStatus.COMPLETED,
            tool_kind=ExecutionToolKind.MATH_EXECUTOR,
            operation="evaluate",
            input=expression,
            result="3060.00000000000",
            numeric_result=3060.0,
            locality="local",
            approval_state="not_needed",
            warnings=[],
            errors=[],
        )

    def fake_build_math_execution_context_block(result):
        return (
            "Bounded local math execution result:\n"
            "Tool: math_executor\n"
            "Locality: local\n"
            "Approval required: no\n"
            f"Status: {result.status}\n"
            f"Operation: {result.operation}\n"
            f"Input: {result.input}\n"
            f"Result: {result.result}\n"
            f"Numeric result: {result.numeric_result}\n"
            "Boundary note: this was bounded local math execution, not arbitrary Python, shell, web, or file mutation."
        )

    monkeypatch.setattr(
        runtime,
        "run_math_execution",
        fake_run_math_execution,
        raising=False,
    )
    monkeypatch.setattr(
        runtime,
        "build_math_execution_context_block",
        fake_build_math_execution_context_block,
        raising=False,
    )
    monkeypatch.setattr(
        runtime,
        "invoke_model",
        _fake_invoke_model_factory(captured_invocation),
    )

    result = runtime.handle_user_message(
        (
            "Write a short professional paragraph explaining why a 15 percent "
            "reduction matters, but first calculate the before/after numbers "
            "from 3 600 units. Keep the tone human and grounded."
        ),
        runtime.SessionState(active_mode="writer"),
    )

    assert execution_requests, "Runtime should call bounded local math execution."

    request = execution_requests[0]
    expression = getattr(request, "expression", "")

    assert expression == "3600 * (1 - 15/100)"
    assert expression != "the before/af"
    assert "b*e**3" not in expression

    math_execution = result["math_execution"]

    assert math_execution["used"] is True
    assert math_execution["status"] == "completed"
    assert math_execution["tool_kind"] == "math_executor"
    assert math_execution["operation"] == "evaluate"
    assert math_execution["input"] == "3600 * (1 - 15/100)"
    assert math_execution["result"] == "3060.00000000000"
    assert math_execution["numeric_result"] == 3060.0
    assert math_execution["stayed_local"] is True
    assert math_execution["approval_required"] is False
    assert math_execution["errors"] == []
    assert "3600 * (1 - 15/100)" in captured_invocation["context_summary"]
    assert "not arbitrary Python, shell, web, or file mutation" in captured_invocation[
        "context_summary"
    ]


def test_runtime_percent_off_tutor_request_uses_clean_expression_truth(monkeypatch):
    captured_invocation: dict[str, Any] = {}
    execution_requests: list[Any] = []

    def fake_run_math_execution(request):
        execution_requests.append(request)
        return MathExecutionResult(
            ok=True,
            status=ExecutionStatus.COMPLETED,
            tool_kind=ExecutionToolKind.MATH_EXECUTOR,
            operation="evaluate",
            input=request.expression,
            result="3060.00000000000",
            numeric_result=3060.0,
            locality="local",
            approval_state="not_needed",
            warnings=[],
            errors=[],
        )

    monkeypatch.setattr(
        runtime,
        "run_math_execution",
        fake_run_math_execution,
        raising=False,
    )
    monkeypatch.setattr(
        runtime,
        "invoke_model",
        _fake_invoke_model_factory(captured_invocation),
    )

    result = runtime.handle_user_message(
        (
            "Teach me step by step how to calculate 15 percent off 3 600. "
            "Do not just give the final answer first."
        ),
        runtime.SessionState(active_mode="tutor"),
    )

    assert execution_requests, "Runtime should call bounded local math execution."
    assert execution_requests[0].expression == "3600 * (1 - 15/100)"

    math_execution = result["math_execution"]

    assert math_execution["used"] is True
    assert math_execution["status"] == "completed"
    assert math_execution["input"] == "3600 * (1 - 15/100)"
    assert math_execution["numeric_result"] == 3060.0
    assert math_execution["stayed_local"] is True
    assert math_execution["approval_required"] is False
    assert math_execution["errors"] == []


def test_plain_runtime_message_does_not_use_math_execution(monkeypatch):
    captured_invocation: dict[str, Any] = {}
    execution_requests: list[Any] = []

    def fake_run_math_execution(request):
        execution_requests.append(request)

        return MathExecutionResult(
            ok=False,
            status=ExecutionStatus.FAILED,
            tool_kind=ExecutionToolKind.MATH_EXECUTOR,
            operation="evaluate",
            input="",
            errors=["Math execution should not have been called."],
        )

    monkeypatch.setattr(
        runtime,
        "run_math_execution",
        fake_run_math_execution,
        raising=False,
    )
    monkeypatch.setattr(
        runtime,
        "invoke_model",
        _fake_invoke_model_factory(captured_invocation),
    )

    result = runtime.handle_user_message(
        "Hello there. Please respond normally.",
        runtime.SessionState(),
    )

    assert execution_requests == []
    assert captured_invocation["message"] == "Hello there. Please respond normally."
    assert "Bounded local math execution result:" not in captured_invocation["context_summary"]

    math_execution = result.get("math_execution", {"used": False})

    assert math_execution.get("used") is False
