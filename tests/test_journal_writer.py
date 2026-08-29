import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import journal_writer


class TestJournalWriter(unittest.TestCase):
    def test_summarize_message_truncates_long_input(self):
        message = "word " * 50

        result = journal_writer.summarize_message(message, limit=40)

        self.assertLessEqual(len(result), 40)
        self.assertTrue(result.endswith("..."))

    def test_normalize_runtime_journal_policy_maps_legacy_mode_and_defaults(self):
        policy = journal_writer.normalize_runtime_journal_policy(
            {
                "journal_mode": "scaffold_minimal",
                "include_policy_summary": True,
            }
        )

        self.assertTrue(policy["journal_write_allowed"])
        self.assertEqual(policy["journal_mode"], "minimal")
        self.assertTrue(policy["include_policy_summary"])
        self.assertTrue(policy["redact_sensitive_content"])

    def test_normalize_runtime_journal_policy_disables_write_when_requested(self):
        policy = journal_writer.normalize_runtime_journal_policy(
            {
                "journal_write_allowed": False,
                "journal_mode": "detailed",
            }
        )

        self.assertFalse(policy["journal_write_allowed"])
        self.assertEqual(policy["journal_mode"], "skip")

    def test_write_session_journal_entry_writes_default_minimal_entry(self):
        temp_dir = Path(tempfile.mkdtemp())

        try:
            with patch.object(journal_writer, "SESSIONS_DIR", temp_dir):
                status = journal_writer.write_session_journal_entry(
                    {
                        "message_summary": "Hello there",
                        "intent": "conversation",
                        "mode": "companion",
                        "skill_count": 4,
                        "config_groups": ["memory", "models", "policies", "system"],
                        "verified": True,
                    }
                )

                self.assertTrue(status["journal_write_allowed"])
                self.assertEqual(status["journal_mode"], "minimal")
                self.assertTrue(status["path"].endswith("_runtime-session.md"))

                contents = Path(status["path"]).read_text(encoding="utf-8")

                self.assertIn("# Runtime Session Note", contents)
                self.assertIn("- Journal write allowed: True", contents)
                self.assertIn("- Journal mode: minimal", contents)
                self.assertIn("- Message summary: Hello there", contents)
                self.assertIn("- Intent: conversation", contents)
                self.assertIn("- Mode: companion", contents)
                self.assertIn("- Skill count: 4", contents)
                self.assertIn(
                    "This minimal entry preserves continuity while avoiding unnecessary detail.",
                    contents,
                )
                self.assertNotIn("- Retrieved memory count:", contents)
                self.assertNotIn("- Memory context source:", contents)
                self.assertNotIn("## Plan summary", contents)
                self.assertNotIn("## Model routing reasoning", contents)
        finally:
            shutil.rmtree(temp_dir)

    def test_write_session_journal_entry_obeys_standard_policy(self):
        temp_dir = Path(tempfile.mkdtemp())

        try:
            with patch.object(journal_writer, "SESSIONS_DIR", temp_dir):
                status = journal_writer.write_session_journal_entry(
                    {
                        "message_summary": "Can you explain derivatives step by step?",
                        "intent": "tutoring",
                        "mode": "tutor",
                        "skill_count": 4,
                        "config_groups": ["memory", "models", "policies", "system"],
                        "retrieved_memory_count": 2,
                        "uses_memory_context": True,
                        "reads_private_memory": True,
                        "memory_context_source": "local_session_journal_scaffold",
                        "memory_class": "working_memory",
                        "memory_class_source": "forced_memory_class",
                        "primary_memory_class": "working_memory",
                        "forced_memory_class": "working_memory",
                        "memory_class_boundary_sensitive": False,
                        "memory_class_requires_boundary_check": True,
                        "selected_model_role": "primary_general",
                        "selected_model_target": "mistral-small-3.1",
                        "selected_model_runtime": "ollama",
                        "model_route_stayed_local": True,
                        "model_route_allowed": True,
                        "boundary_flags": ["local_session_memory"],
                        "plan_summary": "Explain the concept slowly, then work through an example.",
                        "verified": True,
                    },
                    journal_policy={
                        "journal_write_allowed": True,
                        "journal_mode": "standard",
                        "include_plan_summary": True,
                        "include_retrieval_summary": True,
                        "include_boundary_flags": True,
                        "include_memory_class": True,
                        "include_policy_summary": True,
                        "redact_sensitive_content": True,
                        "note": "Runtime requested standard journaling.",
                    },
                )

                self.assertTrue(status["journal_write_allowed"])
                self.assertEqual(status["journal_mode"], "standard")
                self.assertTrue(status["path"].endswith("_runtime-session.md"))

                contents = Path(status["path"]).read_text(encoding="utf-8")

                self.assertIn("- Journal mode: standard", contents)
                self.assertIn(
                    "- Policy note: Runtime requested standard journaling.",
                    contents,
                )
                self.assertIn("- Retrieved memory count: 2", contents)
                self.assertIn("- Uses memory context: True", contents)
                self.assertIn("- Reads private memory: True", contents)
                self.assertIn(
                    "- Memory context source: local_session_journal_scaffold",
                    contents,
                )
                self.assertIn("## Memory class reasoning", contents)
                self.assertIn("- Selected memory class: working_memory", contents)
                self.assertIn("- Memory class source: forced_memory_class", contents)
                self.assertIn("- Primary memory class: working_memory", contents)
                self.assertIn("- Forced memory class: working_memory", contents)
                self.assertIn(
                    "- Boundary-sensitive memory class: False",
                    contents,
                )
                self.assertIn(
                    "- Memory class requires boundary check: True",
                    contents,
                )
                self.assertIn(
                    "- Boundary handling influenced the selected memory class.",
                    contents,
                )
                self.assertIn("## Model routing reasoning", contents)
                self.assertIn("- Selected model role: primary_general", contents)
                self.assertIn(
                    "- Selected model target: mistral-small-3.1",
                    contents,
                )
                self.assertIn("- Selected model runtime: ollama", contents)
                self.assertIn("- Model route stayed local: True", contents)
                self.assertIn("- Model route allowed: True", contents)
                self.assertIn(
                    "- The selected model route remained inside the local-first core.",
                    contents,
                )
                self.assertIn(
                    "- The selected model route passed current scaffold approval requirements.",
                    contents,
                )
                self.assertIn("- Boundary flags: local_session_memory", contents)
                self.assertIn("## Plan summary", contents)
                self.assertIn(
                    "Explain the concept slowly, then work through an example.",
                    contents,
                )
                self.assertIn("- Verification passed: True", contents)
                self.assertIn(
                    "Runtime scaffold completed its non-executing path successfully under policy-governed journaling.",
                    contents,
                )
        finally:
            shutil.rmtree(temp_dir)

    def test_write_session_journal_entry_redacts_sensitive_details_when_flagged(self):
        temp_dir = Path(tempfile.mkdtemp())

        try:
            with patch.object(journal_writer, "SESSIONS_DIR", temp_dir):
                status = journal_writer.write_session_journal_entry(
                    {
                        "message": "Here is highly private material that should not be echoed.",
                        "message_summary": "Here is highly private material that should not be echoed.",
                        "intent": "personal_support",
                        "mode": "companion",
                        "skill_count": 4,
                        "config_groups": ["memory", "models", "policies", "system"],
                        "retrieved_memory_count": 1,
                        "uses_memory_context": True,
                        "reads_private_memory": True,
                        "memory_context_source": "sealed_private_memory",
                        "memory_class": "sealed_private_memory",
                        "memory_class_source": "forced_memory_class",
                        "primary_memory_class": "sealed_private_memory",
                        "forced_memory_class": "sealed_private_memory",
                        "memory_class_boundary_sensitive": True,
                        "memory_class_requires_boundary_check": True,
                        "selected_model_role": "optional_cloud_consultant",
                        "selected_model_target": "chatgpt",
                        "selected_model_runtime": "unknown",
                        "model_route_stayed_local": False,
                        "model_route_allowed": False,
                        "boundary_flags": ["sealed_private_memory"],
                        "plan_summary": "Handle the topic gently and carefully.",
                        "verified": True,
                    },
                    journal_policy={
                        "journal_write_allowed": True,
                        "journal_mode": "detailed",
                        "include_plan_summary": True,
                        "include_retrieval_summary": True,
                        "include_boundary_flags": True,
                        "include_memory_class": True,
                        "include_policy_summary": True,
                        "redact_sensitive_content": True,
                        "note": "Sensitive boundary override applied.",
                    },
                )

                self.assertTrue(status["journal_write_allowed"])
                self.assertEqual(status["journal_mode"], "detailed")

                contents = Path(status["path"]).read_text(encoding="utf-8")

                self.assertIn(
                    "- Message summary: Withheld by journal policy due to sensitive boundary flags.",
                    contents,
                )
                self.assertIn(
                    "- Selected memory class: Withheld by journal policy.",
                    contents,
                )
                self.assertIn(
                    "- Memory class source: Withheld by journal policy.",
                    contents,
                )
                self.assertIn(
                    "- Primary memory class: Withheld by journal policy.",
                    contents,
                )
                self.assertIn(
                    "- Forced memory class: Withheld by journal policy.",
                    contents,
                )
                self.assertIn(
                    "- Memory context source: Withheld by journal policy.",
                    contents,
                )
                self.assertIn("## Model routing reasoning", contents)
                self.assertIn(
                    "- Selected model role: Withheld by journal policy.",
                    contents,
                )
                self.assertIn(
                    "- Selected model target: Withheld by journal policy.",
                    contents,
                )
                self.assertIn(
                    "- Selected model runtime: Withheld by journal policy.",
                    contents,
                )
                self.assertIn(
                    "- Model-routing explanation detail was reduced because boundary handling required redaction.",
                    contents,
                )
                self.assertIn("Withheld by journal policy.", contents)
                self.assertIn("- Boundary flags: sealed_private_memory", contents)
                self.assertNotIn(
                    "Here is highly private material that should not be echoed.",
                    contents,
                )
                self.assertNotIn("Handle the topic gently and carefully.", contents)
                self.assertNotIn("chatgpt", contents)
        finally:
            shutil.rmtree(temp_dir)

    def test_write_session_journal_entry_can_be_skipped_by_policy(self):
        temp_dir = Path(tempfile.mkdtemp())

        try:
            with patch.object(journal_writer, "SESSIONS_DIR", temp_dir):
                status = journal_writer.write_session_journal_entry(
                    {
                        "message_summary": "Do not journal this.",
                    },
                    journal_policy={
                        "journal_write_allowed": False,
                        "journal_mode": "minimal",
                        "note": "Journaling disabled by policy.",
                    },
                )

                self.assertFalse(status["journal_write_allowed"])
                self.assertEqual(status["journal_mode"], "skip")
                self.assertEqual(status["path"], "")
                self.assertEqual(status["note"], "Journaling disabled by policy.")
                self.assertEqual(list(temp_dir.iterdir()), [])
        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
