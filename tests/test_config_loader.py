import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core.config_loader import (
    load_config_group,
    normalize_memory_policy_config,
    normalize_model_roles_config,
    normalize_model_routing_config,
)


class TestConfigLoader(unittest.TestCase):
    def test_normalize_memory_policy_config_filters_invalid_override_entries(self):
        raw = {
            "version": 1,
            "scaffold_retrieval": {
                "local_session_memory_enabled": True,
                "mode_overrides": {
                    "researcher": {
                        "session_memory_limit": 5,
                    },
                    "writer": "not_a_mapping",
                },
                "autonomy_overrides": {
                    "1": {
                        "session_memory_limit": 4,
                    },
                    "two": {
                        "local_session_memory_enabled": False,
                    },
                    "2": "not_a_mapping",
                },
            },
        }

        normalized = normalize_memory_policy_config(raw)

        self.assertEqual(
            normalized["scaffold_retrieval"]["mode_overrides"],
            {
                "researcher": {
                    "session_memory_limit": 5,
                }
            },
        )
        self.assertEqual(
            normalized["scaffold_retrieval"]["autonomy_overrides"],
            {
                "1": {
                    "session_memory_limit": 4,
                }
            },
        )

    def test_normalize_memory_policy_config_replaces_invalid_scaffold_retrieval_container(self):
        raw = {
            "version": 1,
            "scaffold_retrieval": ["bad", "shape"],
            "notes": ["keep_this"],
        }

        normalized = normalize_memory_policy_config(raw)

        self.assertEqual(normalized["scaffold_retrieval"], {})
        self.assertEqual(normalized["notes"], ["keep_this"])

    def test_normalize_memory_policy_config_normalizes_memory_classes(self):
        raw = {
            "version": 1,
            "scaffold_memory_classes": {
                "default_memory_class": " conversation_memory ",
                "fallback_memory_class": " working_memory ",
                "classes": {
                    "working_memory": {
                        "allowed_memory_classes": "working_memory",
                    },
                    "broken": "not_a_mapping",
                },
                "mode_overrides": {
                    "tutor": {
                        "allowed_memory_classes": [
                            "working_memory",
                            "conversation_memory",
                        ],
                        "forced_memory_class": " working_memory ",
                    },
                    "writer": "not_a_mapping",
                },
                "autonomy_overrides": {
                    "2": {
                        "disallowed_memory_classes": "sealed_private_memory",
                    },
                    "bad": {
                        "forced_memory_class": "sealed_private_memory",
                    },
                },
                "boundary_overrides": {
                    "local_session_memory": {
                        "forced_memory_class": " working_memory ",
                    },
                    "broken": "not_a_mapping",
                },
            },
        }

        normalized = normalize_memory_policy_config(raw)

        self.assertEqual(
            normalized["scaffold_memory_classes"]["default_memory_class"],
            "conversation_memory",
        )
        self.assertEqual(
            normalized["scaffold_memory_classes"]["fallback_memory_class"],
            "working_memory",
        )
        self.assertEqual(
            normalized["scaffold_memory_classes"]["classes"],
            {
                "working_memory": {
                    "allowed_memory_classes": ["working_memory"],
                }
            },
        )
        self.assertEqual(
            normalized["scaffold_memory_classes"]["mode_overrides"],
            {
                "tutor": {
                    "allowed_memory_classes": [
                        "working_memory",
                        "conversation_memory",
                    ],
                    "forced_memory_class": "working_memory",
                }
            },
        )
        self.assertEqual(
            normalized["scaffold_memory_classes"]["autonomy_overrides"],
            {
                "2": {
                    "disallowed_memory_classes": ["sealed_private_memory"],
                }
            },
        )
        self.assertEqual(
            normalized["scaffold_memory_classes"]["boundary_overrides"],
            {
                "local_session_memory": {
                    "forced_memory_class": "working_memory",
                }
            },
        )

    def test_normalize_model_roles_config_normalizes_role_shapes(self):
        raw = {
            "version": 1,
            "runtime_status": " local_roles_declared_not_yet_wired ",
            "roles": {
                "primary_general": {
                    "preferred_model": " mistral-small-3.1 ",
                    "fallback_models": "granite-3.3-8b-instruct",
                    "requirements": [" strong instruction following ", "stable tone"],
                    "candidate_notes": "Matches blueprint role for Elysia-General.",
                    "local_only": "true",
                    "signup_required": "false",
                    "enabled_by_default": "true",
                    "explicit_approval_required": "false",
                },
                "broken": "not_a_mapping",
            },
            "external_helpers": {
                "optional_cloud_consultant": {
                    "preferred_service": " chatgpt ",
                    "allowed_uses": "explicit outside consultation",
                    "forbidden_uses": [" silent fallback ", "default routing"],
                    "local_only": "false",
                    "signup_required": "true",
                    "enabled_by_default": "false",
                    "explicit_approval_required": "true",
                }
            },
            "routing_principles": "local_first",
            "notes": [" role file ", " trust-first "],
            "privacy_and_trust_defaults": {
                "preferred_runtime": " ollama ",
                "preferred_interface": " open_webui ",
                "default_outbound_model_use_forbidden": "true",
            },
        }

        normalized = normalize_model_roles_config(raw)

        self.assertEqual(
            normalized["runtime_status"],
            "local_roles_declared_not_yet_wired",
        )
        self.assertEqual(
            normalized["roles"]["primary_general"]["preferred_model"],
            "mistral-small-3.1",
        )
        self.assertEqual(
            normalized["roles"]["primary_general"]["fallback_models"],
            ["granite-3.3-8b-instruct"],
        )
        self.assertEqual(
            normalized["roles"]["primary_general"]["requirements"],
            ["strong instruction following", "stable tone"],
        )
        self.assertEqual(
            normalized["roles"]["primary_general"]["candidate_notes"],
            ["Matches blueprint role for Elysia-General."],
        )
        self.assertTrue(normalized["roles"]["primary_general"]["local_only"])
        self.assertFalse(normalized["roles"]["primary_general"]["signup_required"])
        self.assertTrue(normalized["roles"]["primary_general"]["enabled_by_default"])
        self.assertFalse(
            normalized["roles"]["primary_general"]["explicit_approval_required"]
        )
        self.assertNotIn("broken", normalized["roles"])

        self.assertEqual(
            normalized["external_helpers"]["optional_cloud_consultant"]["preferred_service"],
            " chatgpt ",
        )
        self.assertEqual(
            normalized["external_helpers"]["optional_cloud_consultant"]["allowed_uses"],
            ["explicit outside consultation"],
        )
        self.assertEqual(
            normalized["external_helpers"]["optional_cloud_consultant"]["forbidden_uses"],
            ["silent fallback", "default routing"],
        )
        self.assertEqual(normalized["routing_principles"], ["local_first"])
        self.assertEqual(normalized["notes"], ["role file", "trust-first"])
        self.assertEqual(
            normalized["privacy_and_trust_defaults"]["preferred_runtime"],
            "ollama",
        )
        self.assertEqual(
            normalized["privacy_and_trust_defaults"]["preferred_interface"],
            "open_webui",
        )
        self.assertTrue(
            normalized["privacy_and_trust_defaults"][
                "default_outbound_model_use_forbidden"
            ]
        )

    def test_normalize_model_routing_config_normalizes_route_shapes(self):
        raw = {
            "version": 1,
            "routing_mode": " explicit_local_first_role_governed ",
            "defaults": {
                "primary_role": " primary_general ",
                "fallback_role": " lighter_backup ",
                "allow_silent_cloud_fallback": "false",
                "require_explicit_enablement_for_specialists": "true",
            },
            "mode_routes": {
                "default": {
                    "preferred_role": " primary_general ",
                    "fallback_role": " lighter_backup ",
                    "local_only": "true",
                },
                "broken": "not_a_mapping",
            },
            "task_routes": {
                "coding": {
                    "preferred_role": " primary_code ",
                    "fallback_role": " primary_general ",
                    "local_only": "true",
                    "requires": "bounded_task_scope",
                },
                "broken": "not_a_mapping",
            },
            "route_resolution_order": "mode_route",
            "selection_principles": [" local first ", " no silent cloud fallback "],
            "source_canons": "docs/canon/HER_MIND.md",
            "notes": [" routing file "],
            "privacy_and_trust_guards": {
                "private_identity_must_remain_local": "true",
            },
        }

        normalized = normalize_model_routing_config(raw)

        self.assertEqual(
            normalized["routing_mode"],
            "explicit_local_first_role_governed",
        )
        self.assertEqual(
            normalized["defaults"]["primary_role"],
            "primary_general",
        )
        self.assertEqual(
            normalized["defaults"]["fallback_role"],
            "lighter_backup",
        )
        self.assertFalse(
            normalized["defaults"]["allow_silent_cloud_fallback"]
        )
        self.assertTrue(
            normalized["defaults"]["require_explicit_enablement_for_specialists"]
        )
        self.assertEqual(
            normalized["mode_routes"],
            {
                "default": {
                    "preferred_role": "primary_general",
                    "fallback_role": "lighter_backup",
                    "local_only": True,
                }
            },
        )
        self.assertEqual(
            normalized["task_routes"],
            {
                "coding": {
                    "preferred_role": "primary_code",
                    "fallback_role": "primary_general",
                    "local_only": True,
                    "requires": ["bounded_task_scope"],
                }
            },
        )
        self.assertEqual(normalized["route_resolution_order"], ["mode_route"])
        self.assertEqual(
            normalized["selection_principles"],
            ["local first", "no silent cloud fallback"],
        )
        self.assertEqual(
            normalized["source_canons"],
            ["docs/canon/HER_MIND.md"],
        )
        self.assertEqual(normalized["notes"], ["routing file"])
        self.assertTrue(
            normalized["privacy_and_trust_guards"][
                "private_identity_must_remain_local"
            ]
        )

    def test_load_config_group_normalizes_memory_policy_on_load(self):
        with TemporaryDirectory() as tmpdir:
            config_root = Path(tmpdir)
            memory_dir = config_root / "memory"
            memory_dir.mkdir(parents=True, exist_ok=True)

            (memory_dir / "memory_policy.yaml").write_text(
                """version: 1
scaffold_retrieval:
  local_session_memory_enabled: true
  exclude_current_day_journal: true
  session_memory_limit: 3
  mode_overrides:
    researcher:
      session_memory_limit: 5
    writer: bad_value
  autonomy_overrides:
    "1":
      session_memory_limit: 4
    two:
      local_session_memory_enabled: false
    "2": bad_value
""",
                encoding="utf-8",
            )

            with patch("core.config_loader.CONFIG_ROOT", config_root):
                loaded = load_config_group("memory")

        scaffold_retrieval = loaded["memory_policy"]["scaffold_retrieval"]

        self.assertEqual(scaffold_retrieval["session_memory_limit"], 3)
        self.assertEqual(
            scaffold_retrieval["mode_overrides"],
            {
                "researcher": {
                    "session_memory_limit": 5,
                }
            },
        )
        self.assertEqual(
            scaffold_retrieval["autonomy_overrides"],
            {
                "1": {
                    "session_memory_limit": 4,
                }
            },
        )

    def test_load_config_group_normalizes_model_configs_on_load(self):
        with TemporaryDirectory() as tmpdir:
            config_root = Path(tmpdir)
            models_dir = config_root / "models"
            models_dir.mkdir(parents=True, exist_ok=True)

            (models_dir / "model_roles.yaml").write_text(
                """version: 1
runtime_status: local_roles_declared_not_yet_wired
roles:
  primary_general:
    preferred_model: mistral-small-3.1
    fallback_models: granite-3.3-8b-instruct
    local_only: true
    signup_required: false
    enabled_by_default: true
    explicit_approval_required: false
external_helpers:
  optional_cloud_consultant:
    allowed_uses: explicit outside consultation
    signup_required: true
""",
                encoding="utf-8",
            )

            (models_dir / "routing.yaml").write_text(
                """version: 1
routing_mode: explicit_local_first_role_governed
defaults:
  primary_role: primary_general
  fallback_role: lighter_backup
  allow_silent_cloud_fallback: false
mode_routes:
  default:
    preferred_role: primary_general
    fallback_role: lighter_backup
    local_only: true
task_routes:
  coding:
    preferred_role: primary_code
    fallback_role: primary_general
    local_only: true
    requires: bounded_task_scope
""",
                encoding="utf-8",
            )

            with patch("core.config_loader.CONFIG_ROOT", config_root):
                loaded = load_config_group("models")

        self.assertEqual(
            loaded["model_roles"]["roles"]["primary_general"]["fallback_models"],
            ["granite-3.3-8b-instruct"],
        )
        self.assertTrue(
            loaded["model_roles"]["roles"]["primary_general"]["local_only"]
        )
        self.assertEqual(
            loaded["model_roles"]["external_helpers"]["optional_cloud_consultant"]["allowed_uses"],
            ["explicit outside consultation"],
        )
        self.assertTrue(
            loaded["model_roles"]["external_helpers"]["optional_cloud_consultant"]["signup_required"]
        )

        self.assertEqual(
            loaded["routing"]["routing_mode"],
            "explicit_local_first_role_governed",
        )
        self.assertEqual(
            loaded["routing"]["defaults"]["primary_role"],
            "primary_general",
        )
        self.assertEqual(
            loaded["routing"]["mode_routes"]["default"],
            {
                "preferred_role": "primary_general",
                "fallback_role": "lighter_backup",
                "local_only": True,
            },
        )
        self.assertEqual(
            loaded["routing"]["task_routes"]["coding"],
            {
                "preferred_role": "primary_code",
                "fallback_role": "primary_general",
                "local_only": True,
                "requires": ["bounded_task_scope"],
            },
        )

    def test_load_config_group_keeps_other_model_fields_while_normalizing(self):
        with TemporaryDirectory() as tmpdir:
            config_root = Path(tmpdir)
            models_dir = config_root / "models"
            models_dir.mkdir(parents=True, exist_ok=True)

            (models_dir / "routing.yaml").write_text(
                """version: 1
rules:
  - tutoring
  - research
""",
                encoding="utf-8",
            )

            with patch("core.config_loader.CONFIG_ROOT", config_root):
                loaded = load_config_group("models")

        self.assertEqual(loaded["routing"]["version"], 1)
        self.assertEqual(loaded["routing"]["rules"], ["tutoring", "research"])
        self.assertEqual(loaded["routing"]["defaults"], {})
        self.assertEqual(loaded["routing"]["mode_routes"], {})
        self.assertEqual(loaded["routing"]["task_routes"], {})
        self.assertEqual(loaded["routing"]["route_resolution_order"], [])
        self.assertEqual(loaded["routing"]["selection_principles"], [])
        self.assertEqual(loaded["routing"]["source_canons"], [])
        self.assertEqual(loaded["routing"]["notes"], [])
        self.assertEqual(loaded["routing"]["privacy_and_trust_guards"], {})


if __name__ == "__main__":
    unittest.main()
