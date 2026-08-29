import unittest
from unittest.mock import patch

from core.context_gatherer import gather_context, normalize_message


class DummySessionState:
    def __init__(self, memory_layers=None):
        if memory_layers is None:
            memory_layers = ["working", "conversation", "project", "preferences"]
        self.memory_layers = memory_layers


class TestContextGatherer(unittest.TestCase):
    def test_normalize_message_truncates_long_input(self):
        message = "word " * 50

        result = normalize_message(message, limit=40)

        self.assertLessEqual(len(result), 40)
        self.assertTrue(result.endswith("..."))

    def test_gather_context_builds_expected_shape_from_runtime_policy(self):
        configs = {
            "memory": {},
            "models": {},
            "policies": {},
            "system": {},
        }
        session_state = DummySessionState()
        memory_items = [
            {
                "source": "session_journal",
                "path": "/tmp/2026-03-15_runtime-session.md",
                "title": "2026-03-15_runtime-session.md",
                "preview": "# Runtime Session Note newest",
            },
            {
                "source": "session_journal",
                "path": "/tmp/2026-03-14_runtime-session.md",
                "title": "2026-03-14_runtime-session.md",
                "preview": "# Runtime Session Note older",
            },
        ]
        retrieval_policy = {
            "retrieval_enabled": True,
            "exclude_paths": ["/tmp/2026-03-16_runtime-session.md"],
            "retrieval_mode": "local_session_journal_scaffold_excluding_current_day",
            "note": (
                "Recent session memory retrieved from local scaffold journal entries "
                "while excluding the current day session journal path."
            ),
            "limit": 3,
        }

        with patch(
            "core.context_gatherer.get_recent_session_memory",
            return_value=memory_items,
        ) as mocked_get_recent_session_memory:
            result = gather_context(
                "Can you explain derivatives step by step?",
                session_state,
                configs,
                retrieval_policy,
            )

        mocked_get_recent_session_memory.assert_called_once_with(
            limit=3,
            exclude_paths=["/tmp/2026-03-16_runtime-session.md"],
        )
        self.assertEqual(
            result["request_summary"],
            "Can you explain derivatives step by step?",
        )
        self.assertEqual(
            result["active_memory_layers"],
            ["working", "conversation", "project", "preferences"],
        )
        self.assertEqual(
            result["available_config_groups"],
            ["memory", "models", "policies", "system"],
        )
        self.assertEqual(result["retrieved_memory_count"], 2)
        self.assertEqual(result["memory_items"], memory_items)
        self.assertEqual(
            result["retrieval_mode"],
            "local_session_journal_scaffold_excluding_current_day",
        )
        self.assertEqual(
            result["note"],
            "Recent session memory retrieved from local scaffold journal entries while excluding the current day session journal path.",
        )
        self.assertEqual(result["context_items"][2]["value"], memory_items)
        self.assertEqual(
            result["context_items"][3]["value"],
            ["/tmp/2026-03-16_runtime-session.md"],
        )

    def test_gather_context_does_not_call_memory_manager_when_retrieval_disabled(self):
        configs = {
            "memory": {},
            "models": {},
        }
        session_state = object()
        retrieval_policy = {
            "retrieval_enabled": False,
            "exclude_paths": [],
            "retrieval_mode": "local_session_journal_scaffold_disabled",
            "note": "Runtime disabled local session journal retrieval by policy.",
            "limit": 0,
        }

        with patch(
            "core.context_gatherer.get_recent_session_memory"
        ) as mocked_get_recent_session_memory:
            result = gather_context(
                "hello",
                session_state,
                configs,
                retrieval_policy,
            )

        mocked_get_recent_session_memory.assert_not_called()
        self.assertEqual(result["active_memory_layers"], [])
        self.assertEqual(result["retrieved_memory_count"], 0)
        self.assertEqual(result["memory_items"], [])
        self.assertEqual(
            result["retrieval_mode"],
            "local_session_journal_scaffold_disabled",
        )
        self.assertEqual(
            result["note"],
            "Runtime disabled local session journal retrieval by policy.",
        )


if __name__ == "__main__":
    unittest.main()
