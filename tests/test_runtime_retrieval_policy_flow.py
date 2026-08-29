import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core.runtime import SessionState, handle_user_message


class TestRuntimeRetrievalPolicyFlow(unittest.TestCase):
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
                            "2": {
                                "session_memory_limit": 4,
                            },
                            "3": {
                                "local_session_memory_enabled": False,
                            },
                        },
                    },
                    "scaffold_memory_classes": {
                        "default_memory_class": "conversation_memory",
                        "fallback_memory_class": "working_memory",
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
                            "3": {
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
            day = 15 - index
            items.append(
                {
                    "source": "session_journal",
                    "path": f"/tmp/2026-03-{day:02d}_runtime-session.md",
                    "title": f"2026-03-{day:02d}_runtime-session.md",
                    "preview": f"# Runtime Session Note item {index + 1}",
                }
            )

        return items

    def _run_runtime(self, message, autonomy_level=1, memory_items=None):
        if memory_items is None:
            memory_items = []

        state = SessionState(autonomy_level=autonomy_level)

        with patch(
            "core.runtime.load_all_configs",
            return_value=self._build_configs(),
        ), patch(
            "core.runtime.load_all_skills",
            return_value=self._build_skills(),
        ), patch(
            "core.context_gatherer.get_recent_session_memory",
            return_value=memory_items,
        ) as mocked_get_recent_session_memory, patch(
            "core.runtime.write_runtime_log",
            return_value=Path("/tmp/fake_runtime.log"),
        ), patch(
            "core.runtime.write_session_journal_entry",
            return_value={
                "path": "/tmp/fake_runtime-session.md",
                "journal_write_allowed": True,
                "journal_mode": "scaffold_minimal",
                "note": "stubbed journal write",
            },
        ):
            result = handle_user_message(
                message,
                state,
            )

        return result, mocked_get_recent_session_memory

    def test_runtime_applies_researcher_mode_limit_override_end_to_end(self):
        memory_items = self._build_memory_items(5)

        result, mocked_get_recent_session_memory = self._run_runtime(
            "Can you research and summarize these sources?",
            autonomy_level=1,
            memory_items=memory_items,
        )

        self.assertEqual(result["session_state"]["active_mode"], "researcher")
        self.assertEqual(result["retrieval_policy"]["limit"], 5)
        self.assertEqual(
            result["retrieval_policy"]["retrieval_mode"],
            "local_session_journal_scaffold_excluding_current_day",
        )
        self.assertEqual(result["context"]["retrieved_memory_count"], 5)
        self.assertEqual(
            result["plan"]["memory_context_source"],
            "local_session_journal_scaffold_excluding_current_day",
        )
        self.assertTrue(result["plan"]["uses_memory_context"])
        self.assertEqual(
            result["memory_class_policy"]["primary_memory_class"],
            "research_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["forced_memory_class"],
            "working_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["applied_boundary_overrides"],
            ["local_session_memory"],
        )
        self.assertEqual(result["plan"]["memory_class"], "working_memory")
        self.assertEqual(
            result["plan"]["memory_class_source"],
            "forced_memory_class",
        )
        self.assertEqual(
            result["plan"]["primary_memory_class"],
            "research_memory",
        )
        self.assertEqual(
            result["plan"]["forced_memory_class"],
            "working_memory",
        )

        mocked_get_recent_session_memory.assert_called_once()
        kwargs = mocked_get_recent_session_memory.call_args.kwargs
        self.assertEqual(kwargs["limit"], 5)
        self.assertEqual(len(kwargs["exclude_paths"]), 1)
        self.assertTrue(
            kwargs["exclude_paths"][0].endswith(
                f"{datetime.now().date().isoformat()}_runtime-session.md"
            )
        )

    def test_runtime_applies_default_mode_limit_override_end_to_end(self):
        memory_items = self._build_memory_items(2)

        result, mocked_get_recent_session_memory = self._run_runtime(
            "Hello there.",
            autonomy_level=1,
            memory_items=memory_items,
        )

        self.assertEqual(result["session_state"]["active_mode"], "default")
        self.assertEqual(result["retrieval_policy"]["limit"], 2)
        self.assertEqual(result["context"]["retrieved_memory_count"], 2)
        self.assertTrue(result["plan"]["uses_memory_context"])
        self.assertEqual(
            result["memory_class_policy"]["primary_memory_class"],
            "conversation_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["forced_memory_class"],
            "working_memory",
        )
        self.assertEqual(result["plan"]["memory_class"], "working_memory")
        self.assertEqual(
            result["plan"]["memory_class_source"],
            "forced_memory_class",
        )
        self.assertEqual(
            result["plan"]["primary_memory_class"],
            "conversation_memory",
        )

        mocked_get_recent_session_memory.assert_called_once()
        kwargs = mocked_get_recent_session_memory.call_args.kwargs
        self.assertEqual(kwargs["limit"], 2)

    def test_runtime_applies_autonomy_override_end_to_end(self):
        memory_items = self._build_memory_items(4)

        result, mocked_get_recent_session_memory = self._run_runtime(
            "Can you research and summarize these sources?",
            autonomy_level=2,
            memory_items=memory_items,
        )

        self.assertEqual(result["session_state"]["active_mode"], "researcher")
        self.assertEqual(result["session_state"]["autonomy_level"], 2)
        self.assertEqual(result["retrieval_policy"]["limit"], 4)
        self.assertEqual(result["context"]["retrieved_memory_count"], 4)
        self.assertEqual(
            result["plan"]["memory_context_source"],
            "local_session_journal_scaffold_excluding_current_day",
        )
        self.assertTrue(result["plan"]["uses_memory_context"])
        self.assertEqual(
            result["policy_review"]["boundary_flags"],
            ["local_session_memory"],
        )
        self.assertEqual(
            result["memory_class_policy"]["primary_memory_class"],
            "research_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["forced_memory_class"],
            "working_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["applied_boundary_overrides"],
            ["local_session_memory"],
        )
        self.assertEqual(result["plan"]["memory_class"], "working_memory")
        self.assertEqual(
            result["plan"]["memory_class_source"],
            "forced_memory_class",
        )

        mocked_get_recent_session_memory.assert_called_once()
        kwargs = mocked_get_recent_session_memory.call_args.kwargs
        self.assertEqual(kwargs["limit"], 4)

    def test_runtime_autonomy_override_can_disable_retrieval_end_to_end(self):
        result, mocked_get_recent_session_memory = self._run_runtime(
            "Can you research and summarize these sources?",
            autonomy_level=3,
            memory_items=self._build_memory_items(5),
        )

        self.assertEqual(result["session_state"]["active_mode"], "researcher")
        self.assertEqual(result["session_state"]["autonomy_level"], 3)
        self.assertFalse(result["retrieval_policy"]["retrieval_enabled"])
        self.assertEqual(result["retrieval_policy"]["limit"], 0)
        self.assertEqual(
            result["retrieval_policy"]["retrieval_mode"],
            "local_session_journal_scaffold_disabled",
        )
        self.assertEqual(result["context"]["retrieved_memory_count"], 0)
        self.assertEqual(result["context"]["memory_items"], [])
        self.assertEqual(
            result["context"]["retrieval_mode"],
            "local_session_journal_scaffold_disabled",
        )
        self.assertFalse(result["plan"]["uses_memory_context"])
        self.assertFalse(result["plan"]["reads_private_memory"])
        self.assertEqual(
            result["policy_review"]["boundary_flags"],
            ["low_risk_nonexecuting_path"],
        )
        self.assertEqual(
            result["response"]["caveats"][:2],
            [
                "Tool or side-effect authority was not granted for this response; no such operation was implied by model generation.",
                "Live local invocation was blocked by the current routed path or boundary rules.",
            ],
        )
        self.assertIn(
            "Mode profile posture used: Researcher. Modes shape weighting and style, not authority.",
            result["response"]["caveats"],
        )
        self.assertTrue(
            any(
                caveat.startswith("Mode profile warning: Authority-like boundary fields")
                for caveat in result["response"]["caveats"]
            )
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
        self.assertEqual(result["plan"]["memory_class"], "research_memory")
        self.assertEqual(
            result["plan"]["memory_class_source"],
            "primary_memory_class",
        )

        mocked_get_recent_session_memory.assert_not_called()

    def test_runtime_disables_retrieval_for_writer_mode_end_to_end(self):
        result, mocked_get_recent_session_memory = self._run_runtime(
            "Can you draft and revise this email?",
            autonomy_level=1,
            memory_items=self._build_memory_items(4),
        )

        self.assertEqual(result["session_state"]["active_mode"], "writer")
        self.assertFalse(result["retrieval_policy"]["retrieval_enabled"])
        self.assertEqual(result["retrieval_policy"]["limit"], 0)
        self.assertEqual(
            result["retrieval_policy"]["retrieval_mode"],
            "local_session_journal_scaffold_disabled",
        )
        self.assertEqual(result["context"]["retrieved_memory_count"], 0)
        self.assertEqual(result["context"]["memory_items"], [])
        self.assertEqual(
            result["context"]["retrieval_mode"],
            "local_session_journal_scaffold_disabled",
        )
        self.assertFalse(result["plan"]["uses_memory_context"])
        self.assertFalse(result["plan"]["reads_private_memory"])
        self.assertEqual(
            result["memory_class_policy"]["primary_memory_class"],
            "project_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["forced_memory_class"],
            "",
        )
        self.assertEqual(result["plan"]["memory_class"], "project_memory")
        self.assertEqual(
            result["plan"]["memory_class_source"],
            "primary_memory_class",
        )

        mocked_get_recent_session_memory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
