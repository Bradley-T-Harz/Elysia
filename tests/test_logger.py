import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import logger


class TestLogger(unittest.TestCase):
    def test_summarize_message_truncates_long_input(self):
        message = "word " * 50

        result = logger.summarize_message(message, limit=40)

        self.assertLessEqual(len(result), 40)
        self.assertTrue(result.endswith("..."))

    def test_write_runtime_log_writes_memory_and_model_routing_fields(self):
        temp_dir = Path(tempfile.mkdtemp())

        try:
            with patch.object(logger, "RUNTIME_LOG_DIR", temp_dir):
                log_path = logger.write_runtime_log(
                    {
                        "message_summary": "Can you explain derivatives step by step?",
                        "intent": "tutoring",
                        "mode": "tutor",
                        "selected_skill_id": "tutoring.tutoring_helper",
                        "skill_count": 4,
                        "config_groups": ["memory", "models", "policies", "system"],
                        "retrieved_memory_count": 2,
                        "uses_memory_context": True,
                        "reads_private_memory": True,
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
                        "journal_mode": "standard",
                        "journal_write_allowed": True,
                        "execution_allowed": False,
                        "verified": True,
                    }
                )

                self.assertTrue(log_path.exists())

                contents = log_path.read_text(encoding="utf-8")

                self.assertIn("Intent: tutoring", contents)
                self.assertIn("Mode: tutor", contents)
                self.assertIn(
                    "Selected skill: tutoring.tutoring_helper",
                    contents,
                )
                self.assertIn("Retrieved memory count: 2", contents)
                self.assertIn("Uses memory context: True", contents)
                self.assertIn("Reads private memory: True", contents)
                self.assertIn("Memory class: working_memory", contents)
                self.assertIn(
                    "Memory class source: forced_memory_class",
                    contents,
                )
                self.assertIn(
                    "Primary memory class: working_memory",
                    contents,
                )
                self.assertIn(
                    "Forced memory class: working_memory",
                    contents,
                )
                self.assertIn(
                    "Memory class boundary-sensitive: False",
                    contents,
                )
                self.assertIn(
                    "Memory class requires boundary check: True",
                    contents,
                )
                self.assertIn("Selected model role: primary_general", contents)
                self.assertIn(
                    "Selected model target: mistral-small-3.1",
                    contents,
                )
                self.assertIn("Selected model runtime: ollama", contents)
                self.assertIn("Model route stayed local: True", contents)
                self.assertIn("Model route allowed: True", contents)
                self.assertIn("Journal mode: standard", contents)
                self.assertIn("Journal write allowed: True", contents)
                self.assertIn("Execution allowed: False", contents)
                self.assertIn("Verification passed: True", contents)

        finally:
            shutil.rmtree(temp_dir)

    def test_write_runtime_log_uses_safe_defaults_for_missing_richer_fields(self):
        temp_dir = Path(tempfile.mkdtemp())

        try:
            with patch.object(logger, "RUNTIME_LOG_DIR", temp_dir):
                log_path = logger.write_runtime_log(
                    {
                        "message_summary": "Hello there",
                        "intent": "conversation",
                        "mode": "default",
                        "selected_skill_id": None,
                        "skill_count": 4,
                        "config_groups": ["memory", "models"],
                        "retrieved_memory_count": 0,
                        "uses_memory_context": False,
                        "reads_private_memory": False,
                        "execution_allowed": False,
                        "verified": True,
                    }
                )

                self.assertTrue(log_path.exists())

                contents = log_path.read_text(encoding="utf-8")

                self.assertIn("Selected skill: none", contents)
                self.assertIn("Memory class: unspecified", contents)
                self.assertIn("Memory class source: unknown", contents)
                self.assertIn("Primary memory class: unspecified", contents)
                self.assertIn("Forced memory class: none", contents)
                self.assertIn(
                    "Memory class boundary-sensitive: False",
                    contents,
                )
                self.assertIn(
                    "Memory class requires boundary check: False",
                    contents,
                )
                self.assertIn("Selected model role: none", contents)
                self.assertIn("Selected model target: none", contents)
                self.assertIn("Selected model runtime: unknown", contents)
                self.assertIn("Model route stayed local: True", contents)
                self.assertIn("Model route allowed: False", contents)
                self.assertIn("Journal mode: unknown", contents)
                self.assertIn("Journal write allowed: True", contents)

        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
