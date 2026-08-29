import unittest

from core.retrieval_policy import build_retrieval_policy


class DummySessionState:
    def __init__(self, autonomy_level=1):
        self.autonomy_level = autonomy_level
        self.active_mode = "default"
        self.memory_layers = ["working", "conversation", "project", "preferences"]


class TestRetrievalPolicy(unittest.TestCase):
    def test_build_retrieval_policy_uses_scaffold_defaults_when_no_override_applies(self):
        state = DummySessionState(autonomy_level=1)
        configs = {
            "memory": {
                "memory_policy": {
                    "scaffold_retrieval": {
                        "local_session_memory_enabled": True,
                        "exclude_current_day_journal": True,
                        "session_memory_limit": 3,
                        "mode_overrides": {
                            "researcher": {
                                "session_memory_limit": 5,
                            }
                        },
                        "autonomy_overrides": {
                            "2": {
                                "session_memory_limit": 4,
                            }
                        },
                    }
                }
            }
        }

        result = build_retrieval_policy(state, "tutor", configs)

        self.assertTrue(result["retrieval_enabled"])
        self.assertEqual(result["limit"], 3)
        self.assertEqual(
            result["retrieval_mode"],
            "local_session_journal_scaffold_excluding_current_day",
        )
        self.assertEqual(len(result["exclude_paths"]), 1)

    def test_build_retrieval_policy_applies_researcher_mode_limit_override(self):
        state = DummySessionState(autonomy_level=1)
        configs = {
            "memory": {
                "memory_policy": {
                    "scaffold_retrieval": {
                        "local_session_memory_enabled": True,
                        "exclude_current_day_journal": True,
                        "session_memory_limit": 3,
                        "mode_overrides": {
                            "researcher": {
                                "session_memory_limit": 5,
                            }
                        },
                    }
                }
            }
        }

        result = build_retrieval_policy(state, "researcher", configs)

        self.assertTrue(result["retrieval_enabled"])
        self.assertEqual(result["limit"], 5)
        self.assertEqual(
            result["retrieval_mode"],
            "local_session_journal_scaffold_excluding_current_day",
        )

    def test_build_retrieval_policy_applies_autonomy_limit_override(self):
        state = DummySessionState(autonomy_level=1)
        configs = {
            "memory": {
                "memory_policy": {
                    "scaffold_retrieval": {
                        "local_session_memory_enabled": True,
                        "exclude_current_day_journal": True,
                        "session_memory_limit": 3,
                        "autonomy_overrides": {
                            "1": {
                                "session_memory_limit": 4,
                            }
                        },
                    }
                }
            }
        }

        result = build_retrieval_policy(state, "tutor", configs)

        self.assertTrue(result["retrieval_enabled"])
        self.assertEqual(result["limit"], 4)
        self.assertEqual(
            result["retrieval_mode"],
            "local_session_journal_scaffold_excluding_current_day",
        )

    def test_autonomy_override_wins_over_mode_override(self):
        state = DummySessionState(autonomy_level=1)
        configs = {
            "memory": {
                "memory_policy": {
                    "scaffold_retrieval": {
                        "local_session_memory_enabled": True,
                        "exclude_current_day_journal": True,
                        "session_memory_limit": 3,
                        "mode_overrides": {
                            "researcher": {
                                "session_memory_limit": 5,
                            }
                        },
                        "autonomy_overrides": {
                            "1": {
                                "session_memory_limit": 4,
                            }
                        },
                    }
                }
            }
        }

        result = build_retrieval_policy(state, "researcher", configs)

        self.assertTrue(result["retrieval_enabled"])
        self.assertEqual(result["limit"], 4)

    def test_build_retrieval_policy_can_allow_current_day_from_autonomy_override(self):
        state = DummySessionState(autonomy_level=1)
        configs = {
            "memory": {
                "memory_policy": {
                    "scaffold_retrieval": {
                        "local_session_memory_enabled": True,
                        "exclude_current_day_journal": True,
                        "session_memory_limit": 3,
                        "autonomy_overrides": {
                            "1": {
                                "exclude_current_day_journal": False,
                                "session_memory_limit": 4,
                            }
                        },
                    }
                }
            }
        }

        result = build_retrieval_policy(state, "tutor", configs)

        self.assertTrue(result["retrieval_enabled"])
        self.assertEqual(
            result["retrieval_mode"],
            "local_session_journal_scaffold",
        )
        self.assertEqual(result["exclude_paths"], [])
        self.assertEqual(result["limit"], 4)

    def test_build_retrieval_policy_can_disable_local_session_memory_from_autonomy_override(self):
        state = DummySessionState(autonomy_level=2)
        configs = {
            "memory": {
                "memory_policy": {
                    "scaffold_retrieval": {
                        "local_session_memory_enabled": True,
                        "exclude_current_day_journal": True,
                        "session_memory_limit": 3,
                        "mode_overrides": {
                            "researcher": {
                                "session_memory_limit": 5,
                            }
                        },
                        "autonomy_overrides": {
                            "2": {
                                "local_session_memory_enabled": False,
                            }
                        },
                    }
                }
            }
        }

        result = build_retrieval_policy(state, "researcher", configs)

        self.assertFalse(result["retrieval_enabled"])
        self.assertEqual(
            result["retrieval_mode"],
            "local_session_journal_scaffold_disabled",
        )
        self.assertEqual(result["exclude_paths"], [])
        self.assertEqual(result["limit"], 0)
        self.assertIn("disabled", result["note"])

    def test_invalid_mode_overrides_container_is_ignored(self):
        state = DummySessionState(autonomy_level=1)
        configs = {
            "memory": {
                "memory_policy": {
                    "scaffold_retrieval": {
                        "local_session_memory_enabled": True,
                        "exclude_current_day_journal": True,
                        "session_memory_limit": 3,
                        "mode_overrides": ["not", "a", "dict"],
                    }
                }
            }
        }

        result = build_retrieval_policy(state, "researcher", configs)

        self.assertTrue(result["retrieval_enabled"])
        self.assertEqual(result["limit"], 3)

    def test_invalid_mode_override_entry_is_ignored(self):
        state = DummySessionState(autonomy_level=1)
        configs = {
            "memory": {
                "memory_policy": {
                    "scaffold_retrieval": {
                        "local_session_memory_enabled": True,
                        "exclude_current_day_journal": True,
                        "session_memory_limit": 3,
                        "mode_overrides": {
                            "researcher": 5,
                        },
                    }
                }
            }
        }

        result = build_retrieval_policy(state, "researcher", configs)

        self.assertTrue(result["retrieval_enabled"])
        self.assertEqual(result["limit"], 3)

    def test_invalid_autonomy_overrides_container_is_ignored(self):
        state = DummySessionState(autonomy_level=1)
        configs = {
            "memory": {
                "memory_policy": {
                    "scaffold_retrieval": {
                        "local_session_memory_enabled": True,
                        "exclude_current_day_journal": True,
                        "session_memory_limit": 3,
                        "autonomy_overrides": "definitely not a dict",
                    }
                }
            }
        }

        result = build_retrieval_policy(state, "tutor", configs)

        self.assertTrue(result["retrieval_enabled"])
        self.assertEqual(result["limit"], 3)

    def test_nonnumeric_autonomy_key_is_ignored(self):
        state = DummySessionState(autonomy_level=1)
        configs = {
            "memory": {
                "memory_policy": {
                    "scaffold_retrieval": {
                        "local_session_memory_enabled": True,
                        "exclude_current_day_journal": True,
                        "session_memory_limit": 3,
                        "autonomy_overrides": {
                            "high": {
                                "session_memory_limit": 99,
                            }
                        },
                    }
                }
            }
        }

        result = build_retrieval_policy(state, "tutor", configs)

        self.assertTrue(result["retrieval_enabled"])
        self.assertEqual(result["limit"], 3)

    def test_invalid_autonomy_override_entry_is_ignored(self):
        state = DummySessionState(autonomy_level=1)
        configs = {
            "memory": {
                "memory_policy": {
                    "scaffold_retrieval": {
                        "local_session_memory_enabled": True,
                        "exclude_current_day_journal": True,
                        "session_memory_limit": 3,
                        "autonomy_overrides": {
                            "1": 4,
                        },
                    }
                }
            }
        }

        result = build_retrieval_policy(state, "tutor", configs)

        self.assertTrue(result["retrieval_enabled"])
        self.assertEqual(result["limit"], 3)

    def test_invalid_override_values_fall_back_cleanly(self):
        state = DummySessionState(autonomy_level=1)
        configs = {
            "memory": {
                "memory_policy": {
                    "scaffold_retrieval": {
                        "local_session_memory_enabled": True,
                        "exclude_current_day_journal": True,
                        "session_memory_limit": 3,
                        "mode_overrides": {
                            "researcher": {
                                "session_memory_limit": "bananas",
                                "exclude_current_day_journal": "mystery",
                            }
                        },
                        "autonomy_overrides": {
                            "1": {
                                "local_session_memory_enabled": "certainly",
                            }
                        },
                    }
                }
            }
        }

        result = build_retrieval_policy(state, "researcher", configs)

        self.assertTrue(result["retrieval_enabled"])
        self.assertEqual(result["limit"], 3)
        self.assertEqual(
            result["retrieval_mode"],
            "local_session_journal_scaffold_excluding_current_day",
        )
        self.assertEqual(len(result["exclude_paths"]), 1)


if __name__ == "__main__":
    unittest.main()
