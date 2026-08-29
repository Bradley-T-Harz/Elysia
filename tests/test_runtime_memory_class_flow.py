import unittest
from pathlib import Path
from unittest.mock import patch

import core.runtime as runtime


class TestRuntimeMemoryClassFlow(unittest.TestCase):
    def _build_configs(self):
        return {
            "memory": {
                "memory_policy": {
                    "scaffold_retrieval": {
                        "local_session_memory_enabled": True,
                        "exclude_current_day_journal": True,
                        "session_memory_limit": 3,
                        "mode_overrides": {
                            "tutor": {
                                "session_memory_limit": 3,
                            },
                            "researcher": {
                                "session_memory_limit": 5,
                            },
                            "default": {
                                "session_memory_limit": 2,
                            },
                            "writer": {
                                "local_session_memory_enabled": False,
                            },
                        },
                        "autonomy_overrides": {
                            "1": {
                                "session_memory_limit": 4,
                            },
                            "2": {
                                "local_session_memory_enabled": False,
                            },
                        },
                    },
                    "scaffold_journaling": {
                        "journaling_enabled": True,
                        "default_journal_mode": "standard",
                        "include_plan_summary": True,
                        "include_retrieval_summary": True,
                        "include_boundary_flags": True,
                        "include_memory_class": True,
                        "include_policy_summary": True,
                        "redact_sensitive_content": True,
                        "mode_overrides": {
                            "default": {
                                "default_journal_mode": "minimal",
                            },
                            "tutor": {
                                "default_journal_mode": "standard",
                            },
                            "researcher": {
                                "default_journal_mode": "detailed",
                            },
                            "writer": {
                                "default_journal_mode": "minimal",
                                "include_retrieval_summary": False,
                            },
                        },
                        "autonomy_overrides": {
                            "2": {
                                "default_journal_mode": "minimal",
                                "include_plan_summary": False,
                                "include_retrieval_summary": False,
                            },
                        },
                        "boundary_overrides": {
                            "sealed_private_memory": {
                                "default_journal_mode": "minimal",
                                "redact_sensitive_content": True,
                                "include_retrieval_summary": False,
                            },
                        },
                    },
                    "scaffold_memory_classes": {
                        "require_declared_memory_class": True,
                        "planner_must_record_memory_class": True,
                        "journal_selected_memory_class": True,
                        "retrieval_must_respect_allowed_classes": True,
                        "default_memory_class": "conversation_memory",
                        "fallback_memory_class": "working_memory",
                        "classes": {
                            "working_memory": {
                                "allowed_for_scaffold": True,
                            },
                            "conversation_memory": {
                                "allowed_for_scaffold": True,
                            },
                            "project_memory": {
                                "allowed_for_scaffold": True,
                            },
                            "research_memory": {
                                "allowed_for_scaffold": True,
                            },
                            "preference_memory": {
                                "allowed_for_scaffold": True,
                            },
                            "operational_memory": {
                                "allowed_for_scaffold": True,
                            },
                            "sealed_private_memory": {
                                "allowed_for_scaffold": True,
                                "boundary_sensitive": True,
                                "requires_boundary_check": True,
                            },
                            "audit_memory": {
                                "allowed_for_scaffold": True,
                                "boundary_sensitive": True,
                                "requires_boundary_check": True,
                            },
                        },
                        "mode_overrides": {
                            "default": {
                                "primary_memory_class": "conversation_memory",
                                "allowed_memory_classes": [
                                    "working_memory",
                                    "conversation_memory",
                                    "preference_memory",
                                ],
                            },
                            "tutor": {
                                "primary_memory_class": "working_memory",
                                "allowed_memory_classes": [
                                    "working_memory",
                                    "conversation_memory",
                                    "preference_memory",
                                    "project_memory",
                                ],
                            },
                            "researcher": {
                                "primary_memory_class": "research_memory",
                                "allowed_memory_classes": [
                                    "working_memory",
                                    "research_memory",
                                    "project_memory",
                                    "preference_memory",
                                    "operational_memory",
                                ],
                            },
                            "writer": {
                                "primary_memory_class": "project_memory",
                                "allowed_memory_classes": [
                                    "working_memory",
                                    "conversation_memory",
                                    "project_memory",
                                    "preference_memory",
                                ],
                            },
                        },
                        "autonomy_overrides": {
                            "2": {
                                "disallowed_memory_classes": [
                                    "sealed_private_memory",
                                ],
                            },
                        },
                        "boundary_overrides": {
                            "local_session_memory": {
                                "forced_memory_class": "working_memory",
                                "require_boundary_check": True,
                            },
                            "sealed_private_memory": {
                                "forced_memory_class": "sealed_private_memory",
                                "require_boundary_check": True,
                            },
                            "approval_required": {
                                "audit_memory_required": True,
                            },
                        },
                    },
                }
            },
            "models": {
                "model_roles": {},
                "routing": {},
            },
            "policies": {
                "approval_rules": {},
                "autonomy_levels": {},
                "personality_policy": {},
            },
            "system": {
                "boundaries": {},
                "machine_profile": {},
                "source_policies": {},
                "stack": {},
            },
        }

    def _build_skills(self):
        return {
            "conversation.conversation_helper": {},
            "research.research_summary_helper": {},
            "tutoring.tutoring_helper": {},
            "writing.drafting_helper": {},
        }

    def _build_memory_items(self, count):
        items = []

        for index in range(count):
            items.append(
                {
                    "source": "session_journal",
                    "path": f"/tmp/2026-03-{15 - index:02d}_runtime-session.md",
                    "title": f"2026-03-{15 - index:02d}_runtime-session.md",
                    "preview": f"# Runtime Session Note item {index + 1}",
                }
            )

        return items

    def _journal_stub(self, entry, journal_policy=None):
        policy = journal_policy or {}

        return {
            "path": "/tmp/fake_runtime-session.md",
            "journal_write_allowed": policy.get("journal_write_allowed", True),
            "journal_mode": policy.get("journal_mode", "minimal"),
            "note": "stubbed journal write",
        }

    def _run_runtime(
        self,
        message,
        *,
        autonomy_level=1,
        memory_items=None,
        forced_mode=None,
        evaluate_plan_side_effect=None,
    ):
        if memory_items is None:
            memory_items = []

        state = runtime.SessionState(autonomy_level=autonomy_level)

        patches = [
            patch(
                "core.runtime.load_all_configs",
                return_value=self._build_configs(),
            ),
            patch(
                "core.runtime.load_all_skills",
                return_value=self._build_skills(),
            ),
            patch(
                "core.context_gatherer.get_recent_session_memory",
                return_value=memory_items,
            ),
            patch(
                "core.runtime.write_runtime_log",
                return_value=Path("/tmp/fake_runtime.log"),
            ),
            patch(
                "core.runtime.write_session_journal_entry",
                side_effect=self._journal_stub,
            ),
        ]

        if forced_mode is not None:
            patches.append(
                patch.object(runtime, "choose_mode", return_value=forced_mode)
            )

        if evaluate_plan_side_effect is not None:
            patches.append(
                patch.object(
                    runtime,
                    "evaluate_plan",
                    side_effect=evaluate_plan_side_effect,
                )
            )

        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            if len(patches) == 5:
                result = runtime.handle_user_message(message, state)
            elif len(patches) == 6:
                with patches[5]:
                    result = runtime.handle_user_message(message, state)
            else:
                with patches[5]:
                    with patches[6]:
                        result = runtime.handle_user_message(message, state)

        return result

    def _assert_verification_and_consistency(self, result):
        self.assertIn("memory_class_policy", result)
        self.assertIn("plan", result)
        self.assertIn("policy_review", result)
        self.assertIn("verification", result)

        self.assertTrue(result["verification"]["verified"])
        self.assertTrue(result["plan"]["memory_class_declared"])
        self.assertEqual(
            result["memory_class_policy"]["primary_memory_class"],
            result["plan"]["primary_memory_class"],
        )
        self.assertEqual(
            result["memory_class_policy"]["forced_memory_class"],
            result["plan"]["forced_memory_class"],
        )

    def test_tutor_path_with_local_session_memory_forces_working_memory(self):
        result = self._run_runtime(
            "Can you explain derivatives step by step?",
            forced_mode="tutor",
            memory_items=self._build_memory_items(2),
        )

        self._assert_verification_and_consistency(result)

        self.assertEqual(result["memory_class_policy"]["primary_memory_class"], "working_memory")
        self.assertEqual(result["memory_class_policy"]["forced_memory_class"], "working_memory")
        self.assertEqual(
            result["memory_class_policy"]["applied_boundary_overrides"],
            ["local_session_memory"],
        )
        self.assertEqual(result["plan"]["memory_class"], "working_memory")
        self.assertEqual(result["plan"]["memory_class_source"], "forced_memory_class")
        self.assertTrue(result["plan"]["memory_class_requires_boundary_check"])
        self.assertEqual(
            result["policy_review"]["boundary_flags"],
            ["local_session_memory"],
        )

    def test_writer_path_without_retrieval_uses_project_memory(self):
        result = self._run_runtime(
            "Please help me rewrite this paragraph.",
            forced_mode="writer",
            memory_items=self._build_memory_items(3),
        )

        self._assert_verification_and_consistency(result)

        self.assertFalse(result["retrieval_policy"]["retrieval_enabled"])
        self.assertEqual(result["context"]["retrieved_memory_count"], 0)
        self.assertEqual(result["memory_class_policy"]["primary_memory_class"], "project_memory")
        self.assertEqual(result["memory_class_policy"]["forced_memory_class"], "")
        self.assertEqual(result["plan"]["memory_class"], "project_memory")
        self.assertEqual(result["plan"]["memory_class_source"], "primary_memory_class")
        self.assertFalse(result["plan"]["reads_private_memory"])
        self.assertEqual(
            result["policy_review"]["boundary_flags"],
            ["low_risk_nonexecuting_path"],
        )

    def test_researcher_path_uses_research_memory_when_no_forced_boundary_applies(self):
        result = self._run_runtime(
            "Can you help me analyze these sources?",
            forced_mode="researcher",
            memory_items=[],
        )

        self._assert_verification_and_consistency(result)

        self.assertTrue(result["retrieval_policy"]["retrieval_enabled"])
        self.assertEqual(result["context"]["retrieved_memory_count"], 0)
        self.assertEqual(result["memory_class_policy"]["primary_memory_class"], "research_memory")
        self.assertEqual(result["memory_class_policy"]["forced_memory_class"], "")
        self.assertEqual(result["plan"]["memory_class"], "research_memory")
        self.assertEqual(result["plan"]["memory_class_source"], "primary_memory_class")
        self.assertFalse(result["plan"]["reads_private_memory"])
        self.assertEqual(
            result["policy_review"]["boundary_flags"],
            ["low_risk_nonexecuting_path"],
        )

    def test_sensitive_boundary_forces_sealed_private_memory(self):
        original_evaluate_plan = runtime.evaluate_plan

        def inject_sensitive_boundary(plan):
            review = dict(original_evaluate_plan(plan))
            review["boundary_flags"] = ["sealed_private_memory"]

            reasons = list(review.get("approval_reasons", []))
            reasons.append("sensitive memory boundary injected for runtime memory-class flow test")
            review["approval_reasons"] = reasons
            return review

        result = self._run_runtime(
            "Here is highly private material that should not be echoed back.",
            forced_mode="researcher",
            memory_items=[],
            evaluate_plan_side_effect=inject_sensitive_boundary,
        )

        self._assert_verification_and_consistency(result)

        self.assertEqual(
            result["memory_class_policy"]["forced_memory_class"],
            "sealed_private_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["applied_boundary_overrides"],
            ["sealed_private_memory"],
        )
        self.assertEqual(result["plan"]["memory_class"], "sealed_private_memory")
        self.assertEqual(result["plan"]["memory_class_source"], "forced_memory_class")
        self.assertTrue(result["plan"]["memory_class_boundary_sensitive"])
        self.assertTrue(result["plan"]["memory_class_requires_boundary_check"])
        self.assertTrue(result["plan"]["reads_private_memory"])
        self.assertEqual(
            result["policy_review"]["boundary_flags"],
            ["sealed_private_memory"],
        )

    def test_autonomy_restrictions_disallow_sealed_private_memory(self):
        result = self._run_runtime(
            "Can you help me analyze these sources?",
            autonomy_level=2,
            forced_mode="researcher",
            memory_items=[],
        )

        self._assert_verification_and_consistency(result)

        self.assertEqual(result["memory_class_policy"]["primary_memory_class"], "research_memory")
        self.assertEqual(result["memory_class_policy"]["forced_memory_class"], "")
        self.assertEqual(
            result["memory_class_policy"]["disallowed_memory_classes"],
            ["sealed_private_memory"],
        )
        self.assertEqual(result["plan"]["memory_class"], "research_memory")
        self.assertEqual(result["plan"]["memory_class_source"], "primary_memory_class")
        self.assertEqual(
            result["policy_review"]["boundary_flags"],
            ["low_risk_nonexecuting_path"],
        )
        self.assertFalse(result["plan"]["memory_class_boundary_sensitive"])
        self.assertFalse(result["plan"]["reads_private_memory"])


if __name__ == "__main__":
    unittest.main()
