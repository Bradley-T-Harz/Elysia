import unittest

from core.journal_policy import build_journal_policy


def make_configs(scaffold_journaling):
    return {
        "memory": {
            "memory_policy": {
                "scaffold_journaling": scaffold_journaling,
            }
        }
    }


class TestJournalPolicy(unittest.TestCase):
    def test_build_journal_policy_uses_base_defaults(self):
        configs = make_configs(
            {
                "journaling_enabled": True,
                "default_journal_mode": "standard",
                "include_plan_summary": True,
                "include_retrieval_summary": False,
                "include_boundary_flags": True,
                "include_memory_class": False,
                "include_policy_summary": True,
                "redact_sensitive_content": True,
            }
        )

        policy = build_journal_policy(
            configs=configs,
            mode="tutor",
            autonomy_level=1,
            boundary_flags=[],
        )

        self.assertTrue(policy["journaling_enabled"])
        self.assertTrue(policy["journal_write_allowed"])
        self.assertEqual(policy["journal_mode"], "standard")
        self.assertTrue(policy["include_plan_summary"])
        self.assertFalse(policy["include_retrieval_summary"])
        self.assertTrue(policy["include_boundary_flags"])
        self.assertFalse(policy["include_memory_class"])
        self.assertTrue(policy["include_policy_summary"])
        self.assertTrue(policy["redact_sensitive_content"])
        self.assertEqual(policy["applied_boundary_overrides"], [])
        self.assertIn("mode=tutor", policy["note"])
        self.assertIn("autonomy_level=1", policy["note"])

    def test_build_journal_policy_applies_default_mode_override(self):
        configs = make_configs(
            {
                "journaling_enabled": True,
                "default_journal_mode": "standard",
                "mode_overrides": {
                    "default": {
                        "default_journal_mode": "minimal",
                        "include_plan_summary": False,
                    }
                },
            }
        )

        policy = build_journal_policy(
            configs=configs,
            mode="companion",
            autonomy_level=1,
            boundary_flags=[],
        )

        self.assertEqual(policy["journal_mode"], "minimal")
        self.assertFalse(policy["include_plan_summary"])

    def test_build_journal_policy_applies_active_mode_override(self):
        configs = make_configs(
            {
                "journaling_enabled": True,
                "default_journal_mode": "minimal",
                "include_retrieval_summary": False,
                "mode_overrides": {
                    "researcher": {
                        "default_journal_mode": "detailed",
                        "include_retrieval_summary": True,
                    }
                },
            }
        )

        policy = build_journal_policy(
            configs=configs,
            mode="researcher",
            autonomy_level=1,
            boundary_flags=[],
        )

        self.assertEqual(policy["journal_mode"], "detailed")
        self.assertTrue(policy["include_retrieval_summary"])

    def test_build_journal_policy_applies_autonomy_override_after_mode(self):
        configs = make_configs(
            {
                "journaling_enabled": True,
                "default_journal_mode": "minimal",
                "include_plan_summary": True,
                "mode_overrides": {
                    "researcher": {
                        "default_journal_mode": "detailed",
                        "include_plan_summary": True,
                    }
                },
                "autonomy_overrides": {
                    "2": {
                        "default_journal_mode": "standard",
                        "include_plan_summary": False,
                    }
                },
            }
        )

        policy = build_journal_policy(
            configs=configs,
            mode="researcher",
            autonomy_level=2,
            boundary_flags=[],
        )

        self.assertEqual(policy["journal_mode"], "standard")
        self.assertFalse(policy["include_plan_summary"])
        self.assertIn("autonomy_level=2", policy["note"])

    def test_build_journal_policy_applies_boundary_override_last(self):
        configs = make_configs(
            {
                "journaling_enabled": True,
                "default_journal_mode": "standard",
                "include_retrieval_summary": True,
                "mode_overrides": {
                    "researcher": {
                        "default_journal_mode": "detailed",
                    }
                },
                "autonomy_overrides": {
                    "2": {
                        "default_journal_mode": "standard",
                    }
                },
                "boundary_overrides": {
                    "sealed_private_memory": {
                        "default_journal_mode": "minimal",
                        "include_retrieval_summary": False,
                        "redact_sensitive_content": True,
                    }
                },
            }
        )

        policy = build_journal_policy(
            configs=configs,
            mode="researcher",
            autonomy_level=2,
            boundary_flags=["sealed_private_memory"],
        )

        self.assertEqual(policy["journal_mode"], "minimal")
        self.assertFalse(policy["include_retrieval_summary"])
        self.assertTrue(policy["redact_sensitive_content"])
        self.assertEqual(
            policy["applied_boundary_overrides"],
            ["sealed_private_memory"],
        )
        self.assertIn(
            "boundary_overrides=sealed_private_memory",
            policy["note"],
        )

    def test_build_journal_policy_ignores_malformed_override_containers(self):
        configs = make_configs(
            {
                "journaling_enabled": True,
                "default_journal_mode": "standard",
                "include_policy_summary": True,
                "mode_overrides": ["not", "a", "mapping"],
                "autonomy_overrides": "also bad",
                "boundary_overrides": 42,
            }
        )

        policy = build_journal_policy(
            configs=configs,
            mode="writer",
            autonomy_level=99,
            boundary_flags=["sealed_private_memory"],
        )

        self.assertTrue(policy["journal_write_allowed"])
        self.assertEqual(policy["journal_mode"], "standard")
        self.assertTrue(policy["include_policy_summary"])
        self.assertEqual(policy["applied_boundary_overrides"], [])

    def test_build_journal_policy_disables_journaling_cleanly(self):
        configs = make_configs(
            {
                "journaling_enabled": False,
                "default_journal_mode": "detailed",
                "include_plan_summary": True,
            }
        )

        policy = build_journal_policy(
            configs=configs,
            mode="tutor",
            autonomy_level=1,
            boundary_flags=[],
        )

        self.assertFalse(policy["journaling_enabled"])
        self.assertFalse(policy["journal_write_allowed"])
        self.assertEqual(policy["journal_mode"], "skip")
        self.assertTrue(policy["include_plan_summary"])

    def test_build_journal_policy_normalizes_legacy_mode_names(self):
        configs = make_configs(
            {
                "journaling_enabled": True,
                "default_journal_mode": "scaffold_local_memory_minimal",
            }
        )

        policy = build_journal_policy(
            configs=configs,
            mode="tutor",
            autonomy_level=1,
            boundary_flags=[],
        )

        self.assertEqual(policy["journal_mode"], "standard")


if __name__ == "__main__":
    unittest.main()
