import unittest
from unittest.mock import patch

import core.runtime as runtime



def _route_value(model_routing_decision, key, default=""):
    if isinstance(model_routing_decision, dict):
        return model_routing_decision.get(key, default)
    return getattr(model_routing_decision, key, default)


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
    selected_role = _route_value(model_routing_decision, "selected_role", "primary_general")
    selected_role_container = _route_value(model_routing_decision, "selected_role_container", "roles")
    selected_target = (
        _route_value(model_routing_decision, "selected_target", "")
        or _route_value(model_routing_decision, "selected_model", "")
        or "mistral-small-3.1"
    )
    selected_model = _route_value(model_routing_decision, "selected_model", selected_target)
    selected_model_runtime_tag = (
        _route_value(model_routing_decision, "selected_model_runtime_tag", "")
        or selected_model
    )
    selected_runtime = _route_value(model_routing_decision, "selected_runtime", "ollama")
    selected_service = _route_value(model_routing_decision, "selected_service", selected_runtime)
    allowed = bool(_route_value(model_routing_decision, "allowed", True))
    stayed_local = bool(_route_value(model_routing_decision, "stayed_local", True))
    used_fallback = bool(_route_value(model_routing_decision, "used_fallback", False))

    return {
        "status": "ok" if allowed else "blocked",
        "allowed": allowed,
        "stayed_local": stayed_local,
        "selected_role": selected_role,
        "selected_role_container": selected_role_container,
        "selected_target": selected_target,
        "selected_model": selected_model,
        "selected_model_runtime_tag": selected_model_runtime_tag,
        "selected_runtime": selected_runtime,
        "selected_service": selected_service,
        "used_fallback": used_fallback,
        "fallback_from": _route_value(model_routing_decision, "fallback_from", ""),
        "fallback_to": _route_value(model_routing_decision, "fallback_to", ""),
        "prompt_source": "test/fake_runtime_system.txt",
        "response_text": "Fake governed local answer for runtime-flow tests.",
        "error": "",
        "block_reasons": [] if allowed else ["fake_blocked_route"],
        "unmet_requirements": _route_value(model_routing_decision, "unmet_requirements", []),
        "latency_ms": 0,
        "provider_metadata": {"mocked": True},
        "note": "Live model invocation mocked for deterministic runtime-flow testing.",
    }


class TestRuntimeModelRoutingFlow(unittest.TestCase):
    def setUp(self):
        self._invoke_model_patcher = patch.object(
            runtime,
            "invoke_model",
            side_effect=_fake_invoke_model,
        )
        self._invoke_model_patcher.start()
        self.addCleanup(self._invoke_model_patcher.stop)

    def test_runtime_surfaces_local_general_model_routing_for_tutoring(self):
        state = runtime.SessionState()

        result = runtime.handle_user_message(
            "Can you explain derivatives step by step?",
            state,
        )

        self.assertIn("model_routing", result)

        routing = result["model_routing"]

        self.assertEqual(routing["mode"], "tutor")
        self.assertEqual(routing["task_type"], "tutoring")
        self.assertEqual(routing["selected_role"], "primary_general")
        self.assertEqual(routing["selected_role_reason"], "preferred_role")
        self.assertEqual(routing["selected_role_container"], "roles")
        self.assertEqual(routing["selected_model"], "mistral-small-3.1")
        self.assertEqual(routing["selected_runtime"], "ollama")
        self.assertTrue(routing["stayed_local"])
        self.assertTrue(routing["allowed"])
        self.assertFalse(routing["selected_is_external"])
        self.assertFalse(routing["selected_is_specialist"])
        self.assertTrue(routing["external_routing_forbidden"])
        self.assertIn("mode:tutor", routing["applied_layers"])
        self.assertIn("task:tutoring", routing["applied_layers"])

    def test_runtime_coding_task_routes_to_primary_code(self):
        state = runtime.SessionState()

        with patch.object(
            runtime,
            "select_skill",
            return_value={
                "selected_skill_id": "coding.repo_helper",
                "selection_basis": "test_override",
                "found": True,
            },
        ):
            result = runtime.handle_user_message(
                "Please help me debug this Python function.",
                state,
            )

        self.assertIn("model_routing", result)

        routing = result["model_routing"]

        self.assertEqual(routing["task_type"], "coding")
        self.assertEqual(routing["preferred_role"], "primary_code")
        self.assertEqual(routing["selected_role"], "primary_code")
        self.assertEqual(routing["fallback_role"], "primary_general")
        self.assertEqual(routing["selected_model"], "starcoder2-15b-instruct")
        self.assertEqual(routing["selected_runtime"], "ollama")
        self.assertTrue(routing["stayed_local"])
        self.assertTrue(routing["allowed"])
        self.assertIn("task:coding", routing["applied_layers"])

    def test_runtime_specialist_task_falls_back_without_explicit_enablement(self):
        state = runtime.SessionState()

        with patch.object(
            runtime,
            "_derive_model_routing_task_type",
            return_value="specialist_task",
        ):
            result = runtime.handle_user_message(
                "Use a specialist coding brain for this.",
                state,
            )

        self.assertIn("model_routing", result)

        routing = result["model_routing"]

        self.assertEqual(routing["task_type"], "specialist_task")
        self.assertEqual(routing["selected_role"], "primary_general")
        self.assertEqual(
            routing["selected_role_reason"],
            "fallback_due_to_unmet_route_requirements",
        )
        self.assertIn("explicit_enablement", routing["unmet_requirements"])
        self.assertTrue(routing["stayed_local"])
        self.assertTrue(routing["allowed"])
        self.assertFalse(routing["selected_is_specialist"])
        self.assertFalse(routing["selected_is_external"])

    def test_runtime_external_consultation_stays_local_without_explicit_approval(self):
        state = runtime.SessionState()

        with patch.object(
            runtime,
            "_derive_model_routing_task_type",
            return_value="external_consultation",
        ):
            result = runtime.handle_user_message(
                "Maybe consult outside help on this.",
                state,
            )

        self.assertIn("model_routing", result)

        routing = result["model_routing"]

        self.assertEqual(routing["task_type"], "external_consultation")
        self.assertEqual(routing["selected_role"], "primary_general")
        self.assertEqual(
            routing["selected_role_reason"],
            "fallback_due_to_unmet_route_requirements",
        )
        self.assertIn("explicit_approval", routing["unmet_requirements"])
        self.assertIn("explicit_user_request", routing["unmet_requirements"])
        self.assertTrue(routing["stayed_local"])
        self.assertTrue(routing["allowed"])
        self.assertFalse(routing["selected_is_external"])
        self.assertTrue(routing["external_routing_forbidden"])

    def test_runtime_explicit_external_consultation_can_select_external_helper(self):
        state = runtime.SessionState()

        with patch.object(
            runtime,
            "_derive_model_routing_task_type",
            return_value="external_consultation",
        ):
            with patch.object(
                runtime,
                "_build_model_routing_context_flags",
                return_value=[
                    "explicit_approval",
                    "explicit_user_request",
                    "outbound_use_is_logged",
                    "no_private_memory_authority",
                ],
            ):
                result = runtime.handle_user_message(
                    "Explicitly consult outside help on this public question.",
                    state,
                )

        self.assertIn("model_routing", result)

        routing = result["model_routing"]

        self.assertEqual(routing["task_type"], "external_consultation")
        self.assertEqual(routing["selected_role"], "optional_cloud_consultant")
        self.assertEqual(routing["selected_role_container"], "external_helpers")
        self.assertEqual(routing["selected_service"], "chatgpt")
        self.assertEqual(routing["selected_target"], "chatgpt")
        self.assertTrue(routing["selected_is_external"])
        self.assertFalse(routing["stayed_local"])
        self.assertTrue(routing["allowed"])
        self.assertTrue(routing["external_routing_forbidden"])


if __name__ == "__main__":
    unittest.main()
