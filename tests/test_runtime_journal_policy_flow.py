import unittest
from pathlib import Path
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


class TestRuntimeJournalPolicyFlow(unittest.TestCase):
    def setUp(self):
        self._invoke_model_patcher = patch.object(
            runtime,
            "invoke_model",
            side_effect=_fake_invoke_model,
        )
        self._invoke_model_patcher.start()
        self.addCleanup(self._invoke_model_patcher.stop)

    def _assert_policy_and_status_match(self, result, expected_mode):
        self.assertIn("journal_policy", result)
        self.assertIn("journal_status", result)

        self.assertEqual(result["journal_policy"]["journal_mode"], expected_mode)
        self.assertEqual(result["journal_status"]["journal_mode"], expected_mode)

        self.assertEqual(
            result["journal_policy"]["journal_write_allowed"],
            result["journal_status"]["journal_write_allowed"],
        )
        self.assertTrue(result["journal_status"]["journal_write_allowed"])
        self.assertTrue(
            result["journal_status"]["path"].endswith("_runtime-session.md")
        )

    def _assert_memory_class_alignment(
        self,
        result,
        *,
        expected_memory_class,
        expected_memory_class_source,
        expected_primary_memory_class,
    ):
        self.assertIn("memory_class_policy", result)
        self.assertIn("plan", result)

        self.assertEqual(result["plan"]["memory_class"], expected_memory_class)
        self.assertEqual(
            result["plan"]["memory_class_source"],
            expected_memory_class_source,
        )
        self.assertEqual(
            result["plan"]["primary_memory_class"],
            expected_primary_memory_class,
        )
        self.assertTrue(result["plan"]["memory_class_declared"])

    def _assert_model_routing_alignment(
        self,
        result,
        *,
        expected_role,
        expected_target,
        expected_runtime,
        expected_stayed_local,
        expected_allowed,
    ):
        self.assertIn("model_routing", result)

        self.assertEqual(
            result["model_routing"]["selected_role"],
            expected_role,
        )
        self.assertEqual(
            result["model_routing"]["selected_target"],
            expected_target,
        )
        self.assertEqual(
            result["model_routing"]["selected_runtime"],
            expected_runtime,
        )
        self.assertEqual(
            result["model_routing"]["stayed_local"],
            expected_stayed_local,
        )
        self.assertEqual(
            result["model_routing"]["allowed"],
            expected_allowed,
        )

    def _read_journal_contents(self, result):
        return Path(result["journal_status"]["path"]).read_text(encoding="utf-8")

    def test_tutor_mode_produces_expected_journal_policy(self):
        state = runtime.SessionState(autonomy_level=1)

        result = runtime.handle_user_message(
            "Can you explain derivatives step by step?",
            state,
        )

        self.assertEqual(result["session_state"]["active_mode"], "tutor")
        self._assert_policy_and_status_match(result, "standard")
        self._assert_memory_class_alignment(
            result,
            expected_memory_class="working_memory",
            expected_memory_class_source="primary_memory_class",
            expected_primary_memory_class="working_memory",
        )
        self._assert_model_routing_alignment(
            result,
            expected_role="primary_general",
            expected_target="mistral-small-3.1",
            expected_runtime="ollama",
            expected_stayed_local=True,
            expected_allowed=True,
        )

        self.assertEqual(
            result["memory_class_policy"]["default_memory_class"],
            "conversation_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["fallback_memory_class"],
            "working_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["primary_memory_class"],
            "working_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["forced_memory_class"],
            "",
        )
        self.assertEqual(
            result["memory_class_policy"]["allowed_memory_classes"],
            [
                "working_memory",
                "conversation_memory",
                "preference_memory",
                "project_memory",
            ],
        )
        self.assertEqual(
            result["memory_class_policy"]["disallowed_memory_classes"],
            [],
        )
        self.assertEqual(
            result["memory_class_policy"]["applied_boundary_overrides"],
            [],
        )
        self.assertIn("mode=tutor", result["memory_class_policy"]["note"])
        self.assertIn("autonomy_level=1", result["memory_class_policy"]["note"])
        self.assertNotIn("boundary_overrides=", result["memory_class_policy"]["note"])

        self.assertTrue(result["journal_policy"]["include_plan_summary"])
        self.assertTrue(result["journal_policy"]["include_retrieval_summary"])
        self.assertTrue(result["journal_policy"]["include_boundary_flags"])
        self.assertTrue(result["journal_policy"]["include_memory_class"])
        self.assertTrue(result["journal_policy"]["include_policy_summary"])
        self.assertTrue(result["journal_policy"]["redact_sensitive_content"])
        self.assertEqual(
            result["journal_policy"]["applied_boundary_overrides"],
            [],
        )

        journal_contents = self._read_journal_contents(result)
        self.assertIn("## Memory class reasoning", journal_contents)
        self.assertIn("- Selected memory class: working_memory", journal_contents)
        self.assertIn("- Memory class source: primary_memory_class", journal_contents)
        self.assertIn("- Primary memory class: working_memory", journal_contents)
        self.assertIn("- Forced memory class: none", journal_contents)
        self.assertIn(
            "- Boundary-sensitive memory class: False",
            journal_contents,
        )
        self.assertIn(
            "- Memory class requires boundary check: False",
            journal_contents,
        )
        self.assertIn(
            "- Boundary flags: low_risk_nonexecuting_path",
            journal_contents,
        )
        self.assertIn("## Model routing reasoning", journal_contents)
        self.assertIn("- Selected model role: primary_general", journal_contents)
        self.assertIn(
            "- Selected model target: mistral-small-3.1",
            journal_contents,
        )
        self.assertIn("- Selected model runtime: ollama", journal_contents)
        self.assertIn("- Model route stayed local: True", journal_contents)
        self.assertIn("- Model route allowed: True", journal_contents)

    def test_writer_mode_becomes_more_minimal(self):
        state = runtime.SessionState(autonomy_level=1)

        with patch.object(runtime, "choose_mode", return_value="writer"):
            result = runtime.handle_user_message(
                "Please help me rewrite this paragraph.",
                state,
            )

        self.assertEqual(result["session_state"]["active_mode"], "writer")
        self._assert_policy_and_status_match(result, "minimal")
        self._assert_memory_class_alignment(
            result,
            expected_memory_class="project_memory",
            expected_memory_class_source="primary_memory_class",
            expected_primary_memory_class="project_memory",
        )
        self._assert_model_routing_alignment(
            result,
            expected_role="primary_general",
            expected_target="mistral-small-3.1",
            expected_runtime="ollama",
            expected_stayed_local=True,
            expected_allowed=True,
        )

        self.assertEqual(
            result["memory_class_policy"]["default_memory_class"],
            "conversation_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["fallback_memory_class"],
            "working_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["primary_memory_class"],
            "project_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["forced_memory_class"],
            "",
        )
        self.assertEqual(
            result["memory_class_policy"]["allowed_memory_classes"],
            [
                "working_memory",
                "conversation_memory",
                "project_memory",
                "preference_memory",
            ],
        )
        self.assertEqual(
            result["memory_class_policy"]["applied_boundary_overrides"],
            [],
        )

        self.assertTrue(result["journal_policy"]["include_plan_summary"])
        self.assertFalse(result["journal_policy"]["include_retrieval_summary"])
        self.assertTrue(result["journal_policy"]["include_boundary_flags"])
        self.assertTrue(result["journal_policy"]["include_memory_class"])
        self.assertTrue(result["journal_policy"]["include_policy_summary"])

        journal_contents = self._read_journal_contents(result)
        self.assertIn("- Selected memory class: project_memory", journal_contents)
        self.assertIn(
            "- Memory class source: primary_memory_class",
            journal_contents,
        )
        self.assertIn("- Primary memory class: project_memory", journal_contents)
        self.assertIn("- Forced memory class: none", journal_contents)
        self.assertIn("## Model routing reasoning", journal_contents)
        self.assertIn("- Selected model role: primary_general", journal_contents)
        self.assertIn(
            "- Selected model target: mistral-small-3.1",
            journal_contents,
        )

    def test_autonomy_level_changes_journaling(self):
        state = runtime.SessionState(autonomy_level=3)

        with patch.object(runtime, "choose_mode", return_value="researcher"):
            result = runtime.handle_user_message(
                "Can you help me analyze this source?",
                state,
            )

        self.assertEqual(result["session_state"]["active_mode"], "researcher")
        self.assertEqual(result["session_state"]["autonomy_level"], 3)
        self._assert_policy_and_status_match(result, "minimal")
        self._assert_memory_class_alignment(
            result,
            expected_memory_class="research_memory",
            expected_memory_class_source="primary_memory_class",
            expected_primary_memory_class="research_memory",
        )
        self._assert_model_routing_alignment(
            result,
            expected_role="primary_general",
            expected_target="mistral-small-3.1",
            expected_runtime="ollama",
            expected_stayed_local=True,
            expected_allowed=True,
        )

        self.assertEqual(
            result["memory_class_policy"]["primary_memory_class"],
            "research_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["forced_memory_class"],
            "",
        )
        self.assertEqual(
            result["memory_class_policy"]["disallowed_memory_classes"],
            ["sealed_private_memory"],
        )
        self.assertEqual(
            result["memory_class_policy"]["applied_boundary_overrides"],
            [],
        )
        self.assertIn("autonomy_level=3", result["memory_class_policy"]["note"])

        self.assertFalse(result["journal_policy"]["include_plan_summary"])
        self.assertFalse(result["journal_policy"]["include_retrieval_summary"])
        self.assertTrue(result["journal_policy"]["include_boundary_flags"])
        self.assertTrue(result["journal_policy"]["include_memory_class"])
        self.assertTrue(result["journal_policy"]["include_policy_summary"])
        self.assertEqual(
            result["journal_policy"]["applied_boundary_overrides"],
            [],
        )
        self.assertIn("autonomy_level=3", result["journal_policy"]["note"])

        journal_contents = self._read_journal_contents(result)
        self.assertIn("- Selected memory class: research_memory", journal_contents)
        self.assertIn(
            "- Memory class source: primary_memory_class",
            journal_contents,
        )
        self.assertIn("- Primary memory class: research_memory", journal_contents)
        self.assertIn("- Forced memory class: none", journal_contents)
        self.assertIn("## Model routing reasoning", journal_contents)
        self.assertIn("- Selected model role: primary_general", journal_contents)

    def test_sensitive_boundary_flags_tighten_journaling(self):
        state = runtime.SessionState()

        original_evaluate_plan = runtime.evaluate_plan

        def inject_sensitive_boundary(plan):
            review = dict(original_evaluate_plan(plan))
            review["boundary_flags"] = ["sealed_private_memory"]

            approval_reasons = list(review.get("approval_reasons", []))
            approval_reasons.append(
                "sensitive boundary injected for runtime journal policy flow test"
            )
            review["approval_reasons"] = approval_reasons
            return review

        with patch.object(runtime, "choose_mode", return_value="researcher"):
            with patch.object(runtime, "evaluate_plan", side_effect=inject_sensitive_boundary):
                result = runtime.handle_user_message(
                    "Here is highly private material that should not be echoed back.",
                    state,
                )

        self.assertEqual(result["session_state"]["active_mode"], "researcher")
        self._assert_policy_and_status_match(result, "minimal")
        self._assert_memory_class_alignment(
            result,
            expected_memory_class="sealed_private_memory",
            expected_memory_class_source="forced_memory_class",
            expected_primary_memory_class="research_memory",
        )
        self._assert_model_routing_alignment(
            result,
            expected_role="primary_general",
            expected_target="mistral-small-3.1",
            expected_runtime="ollama",
            expected_stayed_local=True,
            expected_allowed=True,
        )

        self.assertEqual(
            result["memory_class_policy"]["forced_memory_class"],
            "sealed_private_memory",
        )
        self.assertTrue(result["memory_class_policy"]["require_boundary_check"])
        self.assertEqual(
            result["memory_class_policy"]["applied_boundary_overrides"],
            ["sealed_private_memory"],
        )
        self.assertIn(
            "boundary_overrides=sealed_private_memory",
            result["memory_class_policy"]["note"],
        )

        self.assertFalse(result["journal_policy"]["include_retrieval_summary"])
        self.assertTrue(result["journal_policy"]["redact_sensitive_content"])
        self.assertEqual(
            result["journal_policy"]["applied_boundary_overrides"],
            ["sealed_private_memory"],
        )
        self.assertIn(
            "boundary_overrides=sealed_private_memory",
            result["journal_policy"]["note"],
        )

        journal_contents = self._read_journal_contents(result)
        self.assertIn(
            "Withheld by journal policy due to sensitive boundary flags.",
            journal_contents,
        )
        self.assertIn(
            "- Selected memory class: Withheld by journal policy.",
            journal_contents,
        )
        self.assertIn(
            "- Memory class source: Withheld by journal policy.",
            journal_contents,
        )
        self.assertIn(
            "- Primary memory class: Withheld by journal policy.",
            journal_contents,
        )
        self.assertIn(
            "- Forced memory class: Withheld by journal policy.",
            journal_contents,
        )
        self.assertIn("## Model routing reasoning", journal_contents)
        self.assertIn(
            "- Selected model role: Withheld by journal policy.",
            journal_contents,
        )
        self.assertIn(
            "- Selected model target: Withheld by journal policy.",
            journal_contents,
        )
        self.assertIn(
            "- Selected model runtime: Withheld by journal policy.",
            journal_contents,
        )
        self.assertIn("- Boundary flags: sealed_private_memory", journal_contents)

    def test_runtime_returns_consistent_journal_policy_and_status(self):
        state = runtime.SessionState()

        with patch.object(runtime, "choose_mode", return_value="researcher"):
            result = runtime.handle_user_message(
                "Please help me study this topic.",
                state,
            )

        self.assertIn("journal_policy", result)
        self.assertIn("journal_status", result)
        self.assertIn("memory_class_policy", result)
        self.assertIn("plan", result)
        self.assertIn("model_routing", result)

        self.assertEqual(
            result["journal_policy"]["journal_mode"],
            result["journal_status"]["journal_mode"],
        )
        self.assertEqual(
            result["journal_policy"]["journal_write_allowed"],
            result["journal_status"]["journal_write_allowed"],
        )
        self.assertTrue(
            result["journal_status"]["path"].endswith("_runtime-session.md")
        )

        self.assertEqual(
            result["memory_class_policy"]["primary_memory_class"],
            result["plan"]["primary_memory_class"],
        )
        self.assertEqual(
            result["memory_class_policy"]["forced_memory_class"],
            result["plan"]["forced_memory_class"],
        )
        self.assertEqual(
            result["plan"]["memory_class"],
            "research_memory",
        )
        self.assertEqual(
            result["plan"]["memory_class_source"],
            "primary_memory_class",
        )

        self.assertEqual(
            result["model_routing"]["selected_role"],
            "primary_general",
        )
        self.assertEqual(
            result["model_routing"]["selected_target"],
            "mistral-small-3.1",
        )
        self.assertEqual(
            result["model_routing"]["selected_runtime"],
            "ollama",
        )

        journal_contents = self._read_journal_contents(result)
        self.assertIn("- Selected memory class: research_memory", journal_contents)
        self.assertIn("- Memory class source: primary_memory_class", journal_contents)
        self.assertIn("- Primary memory class: research_memory", journal_contents)
        self.assertIn("- Forced memory class: none", journal_contents)
        self.assertIn("## Model routing reasoning", journal_contents)
        self.assertIn("- Selected model role: primary_general", journal_contents)
        self.assertIn(
            "- Selected model target: mistral-small-3.1",
            journal_contents,
        )
        self.assertIn("- Selected model runtime: ollama", journal_contents)


if __name__ == "__main__":
    unittest.main()
