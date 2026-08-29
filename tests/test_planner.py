import unittest

from core.planner import build_plan


class TestPlanner(unittest.TestCase):
    def test_tutoring_plan_preserves_skill_context_and_memory(self):
        intent = {"primary": "tutoring"}
        selected_skill = {
            "selected_skill_id": "tutoring.tutoring_helper",
            "selection_basis": "intent_map",
            "found": True,
        }
        context = {
            "request_summary": "Can you explain derivatives step by step?",
            "retrieved_memory_count": 2,
            "retrieval_mode": "local_session_journal_scaffold",
        }

        result = build_plan(intent, "tutor", selected_skill, context)

        self.assertEqual(result["intent"], "tutoring")
        self.assertEqual(result["mode"], "tutor")
        self.assertEqual(
            result["selected_skill_id"],
            "tutoring.tutoring_helper",
        )
        self.assertEqual(
            result["context_summary"],
            "Can you explain derivatives step by step?",
        )
        self.assertEqual(result["retrieved_memory_count"], 2)
        self.assertTrue(result["uses_memory_context"])
        self.assertEqual(
            result["memory_context_source"],
            "local_session_journal_scaffold",
        )

        self.assertEqual(result["memory_class"], "working_memory")
        self.assertEqual(result["primary_memory_class"], "working_memory")
        self.assertEqual(result["default_memory_class"], "conversation_memory")
        self.assertEqual(result["fallback_memory_class"], "working_memory")
        self.assertEqual(
            result["allowed_memory_classes"],
            [
                "working_memory",
                "conversation_memory",
                "preference_memory",
                "project_memory",
            ],
        )
        self.assertEqual(result["disallowed_memory_classes"], [])
        self.assertEqual(result["forced_memory_class"], "")
        self.assertEqual(
            result["memory_class_source"],
            "retrieval_mode_local_session_memory",
        )
        self.assertTrue(result["memory_class_declared"])
        self.assertFalse(result["memory_class_boundary_sensitive"])
        self.assertFalse(result["memory_class_requires_boundary_check"])

        self.assertFalse(result["requires_tools"])
        self.assertFalse(result["touches_external_network"])
        self.assertFalse(result["writes_files"])
        self.assertTrue(result["reads_private_memory"])
        self.assertEqual(result["risk_level"], "low")
        self.assertEqual(result["autonomy_level_needed"], 1)
        self.assertFalse(result["execution_allowed"])
        self.assertGreaterEqual(len(result["steps"]), 4)
        self.assertTrue(result["mode_profile_used"])
        self.assertEqual(result["mode_profile_key"], "tutor")
        self.assertFalse(result["authority_granted_by_mode"])

    def test_default_plan_shape_for_unknown_intent_without_memory(self):
        intent = {"primary": "unknown"}
        selected_skill = {
            "selected_skill_id": None,
            "selection_basis": "no_match",
            "found": False,
        }
        context = {
            "request_summary": "Hello there",
            "retrieved_memory_count": 0,
            "retrieval_mode": "no_local_session_journal_memory",
        }

        result = build_plan(intent, "companion", selected_skill, context)

        self.assertEqual(result["intent"], "unknown")
        self.assertEqual(result["mode"], "companion")
        self.assertIsNone(result["selected_skill_id"])
        self.assertEqual(result["context_summary"], "Hello there")
        self.assertEqual(result["retrieved_memory_count"], 0)
        self.assertFalse(result["uses_memory_context"])
        self.assertEqual(
            result["memory_context_source"],
            "no_local_session_journal_memory",
        )

        self.assertEqual(result["memory_class"], "conversation_memory")
        self.assertEqual(result["primary_memory_class"], "conversation_memory")
        self.assertEqual(result["default_memory_class"], "conversation_memory")
        self.assertEqual(result["fallback_memory_class"], "working_memory")
        self.assertEqual(
            result["allowed_memory_classes"],
            [
                "working_memory",
                "conversation_memory",
                "preference_memory",
            ],
        )
        self.assertEqual(result["disallowed_memory_classes"], [])
        self.assertEqual(result["forced_memory_class"], "")
        self.assertEqual(
            result["memory_class_source"],
            "primary_memory_class",
        )
        self.assertTrue(result["memory_class_declared"])
        self.assertFalse(result["memory_class_boundary_sensitive"])
        self.assertFalse(result["memory_class_requires_boundary_check"])

        self.assertFalse(result["requires_tools"])
        self.assertFalse(result["touches_external_network"])
        self.assertFalse(result["writes_files"])
        self.assertFalse(result["reads_private_memory"])
        self.assertFalse(result["execution_allowed"])
        self.assertGreaterEqual(len(result["steps"]), 4)
        self.assertTrue(result["mode_profile_used"])
        self.assertEqual(result["mode_profile_key"], "default")
        self.assertFalse(result["authority_granted_by_mode"])

    def test_plan_uses_context_memory_class_when_present(self):
        intent = {"primary": "research"}
        selected_skill = {
            "selected_skill_id": "research.research_summary_helper",
            "selection_basis": "intent_map",
            "found": True,
        }
        context = {
            "request_summary": "Help me compare these sources.",
            "retrieved_memory_count": 0,
            "retrieval_mode": "no_local_session_journal_memory",
            "memory_class": "project_memory",
        }

        result = build_plan(intent, "researcher", selected_skill, context)

        self.assertEqual(result["memory_class"], "project_memory")
        self.assertEqual(result["memory_class_source"], "context_memory_class")
        self.assertEqual(result["primary_memory_class"], "research_memory")
        self.assertFalse(result["memory_class_boundary_sensitive"])
        self.assertFalse(result["memory_class_requires_boundary_check"])
        self.assertFalse(result["reads_private_memory"])

    def test_plan_prefers_forced_memory_class_from_policy(self):
        intent = {"primary": "writing"}
        selected_skill = {
            "selected_skill_id": "writing.drafting_helper",
            "selection_basis": "intent_map",
            "found": True,
        }
        context = {
            "request_summary": "Help me draft this carefully.",
            "retrieved_memory_count": 0,
            "retrieval_mode": "no_local_session_journal_memory",
            "memory_class": "project_memory",
        }
        memory_class_policy = {
            "primary_memory_class": "project_memory",
            "default_memory_class": "project_memory",
            "fallback_memory_class": "working_memory",
            "allowed_memory_classes": [
                "project_memory",
                "preference_memory",
                "sealed_private_memory",
            ],
            "disallowed_memory_classes": [
                "audit_memory",
            ],
            "forced_memory_class": "sealed_private_memory",
        }

        result = build_plan(
            intent,
            "writer",
            selected_skill,
            context,
            memory_class_policy=memory_class_policy,
        )

        self.assertEqual(result["memory_class"], "sealed_private_memory")
        self.assertEqual(result["memory_class_source"], "forced_memory_class")
        self.assertEqual(result["primary_memory_class"], "project_memory")
        self.assertEqual(result["default_memory_class"], "project_memory")
        self.assertEqual(result["fallback_memory_class"], "working_memory")
        self.assertEqual(
            result["allowed_memory_classes"],
            [
                "project_memory",
                "preference_memory",
                "sealed_private_memory",
            ],
        )
        self.assertEqual(
            result["disallowed_memory_classes"],
            ["audit_memory"],
        )
        self.assertEqual(result["forced_memory_class"], "sealed_private_memory")
        self.assertTrue(result["memory_class_declared"])
        self.assertTrue(result["memory_class_boundary_sensitive"])
        self.assertTrue(result["memory_class_requires_boundary_check"])
        self.assertTrue(result["reads_private_memory"])


    def test_explicit_evaluate_request_marks_bounded_math_candidate_without_general_execution(self):
        intent = {"primary": "tutoring"}
        selected_skill = {
            "selected_skill_id": "tutoring.tutoring_helper",
            "selection_basis": "intent_map",
            "found": True,
        }
        context = {
            "request_summary": "Evaluate (4.0875 - 3.27) / 4.0875 * 100.",
            "retrieved_memory_count": 0,
            "retrieval_mode": "no_local_session_journal_memory",
        }

        result = build_plan(intent, "tutor", selected_skill, context)

        self.assertTrue(result["bounded_math_execution_candidate"])
        self.assertEqual(result["math_execution_operation"], "evaluate")
        self.assertEqual(
            result["math_execution_expression"],
            "(4.0875 - 3.27) / 4.0875 * 100",
        )
        self.assertEqual(result["math_execution_variable"], "x")
        self.assertIsNone(result["math_execution_expected"])
        self.assertEqual(result["math_execution_reason"], "explicit_evaluate_request")

        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["requires_tools"])
        self.assertFalse(result["touches_external_network"])
        self.assertFalse(result["writes_files"])

    def test_broad_math_tutoring_request_does_not_trigger_bounded_execution(self):
        intent = {"primary": "tutoring"}
        selected_skill = {
            "selected_skill_id": "tutoring.tutoring_helper",
            "selection_basis": "intent_map",
            "found": True,
        }
        context = {
            "request_summary": "Can you explain derivatives step by step?",
            "retrieved_memory_count": 0,
            "retrieval_mode": "no_local_session_journal_memory",
        }

        result = build_plan(intent, "tutor", selected_skill, context)

        self.assertFalse(result["bounded_math_execution_candidate"])
        self.assertEqual(result["math_execution_operation"], "")
        self.assertEqual(result["math_execution_expression"], "")
        self.assertEqual(result["math_execution_variable"], "x")
        self.assertIsNone(result["math_execution_expected"])
        self.assertEqual(result["math_execution_reason"], "")

        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["requires_tools"])

    def test_percentage_reduction_request_marks_bounded_math_candidate(self):
        intent = {"primary": "writing"}
        selected_skill = {
            "selected_skill_id": "writing.drafting_helper",
            "selection_basis": "intent_map",
            "found": True,
        }
        context = {
            "request_summary": "Write a short paragraph, but first calculate the before/after numbers from 3 600 units after a 15 percent reduction.",
            "retrieved_memory_count": 0,
            "retrieval_mode": "no_local_session_journal_memory",
        }

        result = build_plan(intent, "writer", selected_skill, context)

        self.assertTrue(result["bounded_math_execution_candidate"])
        self.assertEqual(result["math_execution_operation"], "evaluate")
        self.assertEqual(result["math_execution_expression"], "3600 * (1 - 15/100)")
        self.assertEqual(result["math_execution_reason"], "percentage_reduction_request")
        self.assertFalse(result["touches_external_network"])
        self.assertFalse(result["writes_files"])

    def test_explicit_simplify_request_marks_bounded_math_candidate(self):
        intent = {"primary": "math"}
        selected_skill = {
            "selected_skill_id": "tutoring.tutoring_helper",
            "selection_basis": "intent_map",
            "found": True,
        }
        context = {
            "request_summary": "Simplify (x**2 + 2*x + 1) / (x + 1).",
            "retrieved_memory_count": 0,
            "retrieval_mode": "no_local_session_journal_memory",
        }

        result = build_plan(intent, "tutor", selected_skill, context)

        self.assertTrue(result["bounded_math_execution_candidate"])
        self.assertEqual(result["math_execution_operation"], "simplify")
        self.assertEqual(
            result["math_execution_expression"],
            "(x**2 + 2*x + 1) / (x + 1)",
        )
        self.assertEqual(result["math_execution_reason"], "explicit_simplify_request")
        self.assertFalse(result["touches_external_network"])
        self.assertFalse(result["writes_files"])

    def test_percent_off_request_marks_bounded_math_candidate_before_generic_calculate(self):
        intent = {"primary": "tutoring"}
        selected_skill = {
            "selected_skill_id": "tutoring.tutoring_helper",
            "selection_basis": "intent_map",
            "found": True,
        }
        context = {
            "request_summary": (
                "Teach me step by step how to calculate 15 percent off 3 600. "
                "Do not just give the final answer first."
            ),
            "retrieved_memory_count": 0,
            "retrieval_mode": "no_local_session_journal_memory",
        }

        result = build_plan(intent, "tutor", selected_skill, context)

        self.assertTrue(result["bounded_math_execution_candidate"])
        self.assertEqual(result["math_execution_operation"], "evaluate")
        self.assertEqual(result["math_execution_expression"], "3600 * (1 - 15/100)")
        self.assertEqual(result["math_execution_reason"], "percentage_reduction_request")
        self.assertNotIn("15 percent off", result["math_execution_expression"])
        self.assertFalse(result["touches_external_network"])
        self.assertFalse(result["writes_files"])

    def test_percent_reduction_variants_mark_bounded_math_candidate(self):
        intent = {"primary": "tutoring"}
        selected_skill = {
            "selected_skill_id": "tutoring.tutoring_helper",
            "selection_basis": "intent_map",
            "found": True,
        }
        prompts = [
            "Calculate 15% off 3600.",
            "Calculate a 15 percent reduction from 3 600.",
            "Calculate 3 600 reduced by 15 percent.",
        ]

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                result = build_plan(
                    intent,
                    "tutor",
                    selected_skill,
                    {
                        "request_summary": prompt,
                        "retrieved_memory_count": 0,
                        "retrieval_mode": "no_local_session_journal_memory",
                    },
                )

                self.assertTrue(result["bounded_math_execution_candidate"])
                self.assertEqual(result["math_execution_expression"], "3600 * (1 - 15/100)")
                self.assertEqual(result["math_execution_reason"], "percentage_reduction_request")

    def test_percentage_reduction_uses_full_request_text_before_truncated_summary(self):
        intent = {"primary": "writing"}
        selected_skill = {
            "selected_skill_id": "writing.drafting_helper",
            "selection_basis": "intent_map",
            "found": True,
        }
        full_request = (
            "Write a short professional paragraph explaining why a 15 percent "
            "reduction matters, but first calculate the before/after numbers "
            "from 3 600 units. Keep the tone human and grounded."
        )
        context = {
            "request_summary": (
                "Write a short professional paragraph explaining why a 15 percent "
                "reduction matters, but first calculate the before/af..."
            ),
            "request_text": full_request,
            "retrieved_memory_count": 0,
            "retrieval_mode": "no_local_session_journal_memory",
        }

        result = build_plan(intent, "writer", selected_skill, context)

        self.assertTrue(result["bounded_math_execution_candidate"])
        self.assertEqual(result["math_execution_operation"], "evaluate")
        self.assertEqual(result["math_execution_expression"], "3600 * (1 - 15/100)")
        self.assertEqual(result["math_execution_reason"], "percentage_reduction_request")
        self.assertNotEqual(result["math_execution_expression"], "the before/af")
        self.assertNotIn("b*e**3", result["math_execution_expression"])
        self.assertEqual(intent["primary"], "writing")
        self.assertFalse(result["touches_external_network"])
        self.assertFalse(result["writes_files"])

    def test_vault_web_aider_request_is_hard_blocked(self):
        intent = {"primary": "coding"}
        selected_skill = {
            "selected_skill_id": "coding.coding_helper",
            "selection_basis": "intent_map",
            "found": True,
        }
        context = {
            "request_summary": "Search the web using my private vault notes and then have Aider directly edit files under vault/.",
            "retrieved_memory_count": 0,
            "retrieval_mode": "no_local_session_journal_memory",
        }

        result = build_plan(intent, "coder", selected_skill, context)

        self.assertTrue(result["hard_blocked_request"])
        self.assertTrue(result["touches_external_network"])
        self.assertTrue(result["writes_files"])
        self.assertTrue(result["reads_private_memory"])
        self.assertEqual(result["risk_level"], "high")
        self.assertFalse(result["repo_context_candidate"])
        self.assertFalse(result["code_patch_plan_candidate"])
        self.assertTrue(result["block_reasons"])

    def test_explicit_public_web_research_uses_only_governed_research_port(self):
        result = build_plan(
            {"primary": "research"},
            "researcher",
            {
                "selected_skill_id": "research.research_summary_helper",
                "selection_basis": "intent_map",
                "found": True,
            },
            {
                "request_summary": "Search the web for current public wetland monitoring guidance.",
                "retrieved_memory_count": 0,
                "retrieval_mode": "no_local_session_journal_memory",
            },
        )

        self.assertTrue(result["governed_public_research_candidate"])
        self.assertTrue(result["requires_tools"])
        self.assertTrue(result["touches_external_network"])

    def test_researcher_mode_does_not_turn_local_source_analysis_into_egress(self):
        result = build_plan(
            {"primary": "research"},
            "researcher",
            {
                "selected_skill_id": "research.research_summary_helper",
                "selection_basis": "intent_map",
                "found": True,
            },
            {
                "request_summary": "Analyze these sources and summarize their evidence.",
                "retrieved_memory_count": 0,
                "retrieval_mode": "no_local_session_journal_memory",
            },
        )

        self.assertFalse(result["governed_public_research_candidate"])
        self.assertFalse(result["requires_tools"])
        self.assertFalse(result["touches_external_network"])

    def test_destructive_repo_delete_request_is_hard_blocked_before_coder_tools(self):
        intent = {"primary": "coding"}
        selected_skill = {
            "selected_skill_id": "coding.coding_helper",
            "selection_basis": "intent_map",
            "found": True,
        }
        context = {
            "request_summary": "Apply a patch to delete this repo without asking me.",
            "retrieved_memory_count": 0,
            "retrieval_mode": "no_local_session_journal_memory",
        }

        result = build_plan(intent, "coder", selected_skill, context)

        self.assertTrue(result["hard_blocked_request"])
        self.assertFalse(result["touches_external_network"])
        self.assertTrue(result["writes_files"])
        self.assertFalse(result["reads_private_memory"])
        self.assertEqual(result["risk_level"], "high")
        self.assertFalse(result["repo_context_candidate"])
        self.assertFalse(result["code_patch_plan_candidate"])
        self.assertTrue(
            any("destructive repo" in reason for reason in result["block_reasons"])
        )




if __name__ == "__main__":
    unittest.main()
