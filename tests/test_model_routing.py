import unittest

from core.model_routing import build_model_routing_decision


class TestModelRouting(unittest.TestCase):
    def _build_configs(self):
        return {
            "models": {
                "model_roles": {
                    "runtime_status": "local_roles_declared_not_yet_wired",
                    "roles": {
                        "primary_general": {
                            "purpose": "General reasoning role.",
                            "status": "candidate_declared",
                            "preferred_model": "mistral-small-3.1",
                            "fallback_models": ["granite-3.3-8b-instruct"],
                            "runtime": "ollama",
                            "local_only": True,
                            "signup_required": False,
                            "enabled_by_default": True,
                            "explicit_approval_required": False,
                            "privacy_risk": "low",
                            "trust_note": "Trust-first local general brain.",
                        },
                        "primary_code": {
                            "purpose": "Coding role.",
                            "status": "candidate_declared",
                            "preferred_model": "starcoder2-15b-instruct",
                            "fallback_models": ["granite-3.3-8b-instruct"],
                            "runtime": "ollama",
                            "local_only": True,
                            "signup_required": False,
                            "enabled_by_default": True,
                            "explicit_approval_required": False,
                            "privacy_risk": "low",
                            "trust_note": "Trust-first coding role.",
                        },
                        "lighter_backup": {
                            "purpose": "Fast fallback role.",
                            "status": "candidate_declared",
                            "preferred_model": "granite-3.3-8b-instruct",
                            "fallback_models": [],
                            "runtime": "ollama",
                            "local_only": True,
                            "signup_required": False,
                            "enabled_by_default": True,
                            "explicit_approval_required": False,
                            "privacy_risk": "low",
                            "trust_note": "Lightweight local fallback.",
                        },
                        "optional_specialist": {
                            "purpose": "Specialist role.",
                            "status": "candidate_declared",
                            "preferred_models": [
                                "qwen3-coder-next",
                                "deepseek-coder-v2-16b",
                            ],
                            "activation_rule": "explicit_only",
                            "runtime": "ollama",
                            "local_only": True,
                            "signup_required": False,
                            "enabled_by_default": False,
                            "explicit_approval_required": True,
                            "privacy_risk": "moderate",
                            "trust_note": "Optional lab-only specialists.",
                        },
                    },
                    "external_helpers": {
                        "optional_cloud_consultant": {
                            "purpose": "Explicit outside help.",
                            "status": "disabled_by_default",
                            "preferred_service": "chatgpt",
                            "local_only": False,
                            "signup_required": True,
                            "enabled_by_default": False,
                            "explicit_approval_required": True,
                            "privacy_risk": "high",
                            "trust_note": "Consultant only, never default.",
                            "allowed_uses": [
                                "explicit outside consultation",
                            ],
                            "forbidden_uses": [
                                "silent fallback",
                                "default routing",
                            ],
                        }
                    },
                },
                "routing": {
                    "routing_mode": "explicit_local_first_role_governed",
                    "defaults": {
                        "primary_role": "primary_general",
                        "fallback_role": "lighter_backup",
                        "allow_silent_cloud_fallback": False,
                        "require_explicit_enablement_for_specialists": True,
                        "require_explicit_approval_for_external_helpers": True,
                        "sensitive_work_must_remain_local": True,
                    },
                    "mode_routes": {
                        "default": {
                            "preferred_role": "primary_general",
                            "fallback_role": "lighter_backup",
                            "local_only": True,
                        },
                        "tutor": {
                            "preferred_role": "primary_general",
                            "fallback_role": "lighter_backup",
                            "local_only": True,
                        },
                        "researcher": {
                            "preferred_role": "primary_general",
                            "fallback_role": "lighter_backup",
                            "local_only": True,
                        },
                        "writer": {
                            "preferred_role": "primary_general",
                            "fallback_role": "lighter_backup",
                            "local_only": True,
                        },
                    },
                    "task_routes": {
                        "conversation": {
                            "preferred_role": "primary_general",
                            "fallback_role": "lighter_backup",
                            "local_only": True,
                        },
                        "coding": {
                            "preferred_role": "primary_code",
                            "fallback_role": "primary_general",
                            "local_only": True,
                        },
                        "bounded_public_research": {
                            "preferred_role": "primary_general",
                            "fallback_role": "lighter_backup",
                            "local_only": True,
                            "requires": [
                                "autonomy_level_3_or_higher",
                                "approved_tool_path",
                                "explicit_public_source_scope",
                            ],
                        },
                        "specialist_task": {
                            "preferred_role": "optional_specialist",
                            "fallback_role": "primary_general",
                            "local_only": True,
                            "requires": [
                                "explicit_enablement",
                                "bounded_task_scope",
                                "no_silent_substitution",
                            ],
                        },
                        "external_consultation": {
                            "preferred_role": "optional_cloud_consultant",
                            "fallback_role": "primary_general",
                            "local_only": False,
                            "requires": [
                                "explicit_approval",
                                "explicit_user_request",
                                "outbound_use_is_logged",
                                "no_private_memory_authority",
                            ],
                        },
                    },
                    "route_resolution_order": [
                        "mode_route",
                        "task_route",
                        "local_fallback",
                    ],
                    "selection_principles": [
                        "choose the narrowest adequate role",
                        "prefer trust-first local roles before any optional external assistance",
                    ],
                    "privacy_and_trust_guards": {
                        "private_identity_must_remain_local": True,
                        "long_term_memory_authority_must_remain_local": True,
                        "sensitive_project_context_must_remain_local": True,
                        "external_consultation_is_consultant_only": True,
                        "specialist_roles_must_never_silently_replace_core_roles": True,
                    },
                },
            }
        }

    def test_default_conversation_route_selects_primary_general(self):
        result = build_model_routing_decision(
            configs=self._build_configs(),
            mode="default",
            task_type="conversation",
            autonomy_level=1,
            context_flags=[],
        )

        self.assertEqual(result["routing_mode"], "explicit_local_first_role_governed")
        self.assertEqual(result["selected_role"], "primary_general")
        self.assertEqual(result["selected_role_reason"], "preferred_role")
        self.assertEqual(result["selected_role_container"], "roles")
        self.assertEqual(result["selected_model"], "mistral-small-3.1")
        self.assertEqual(result["selected_runtime"], "ollama")
        self.assertTrue(result["stayed_local"])
        self.assertTrue(result["allowed"])
        self.assertFalse(result["selected_is_external"])
        self.assertFalse(result["selected_is_specialist"])
        self.assertIn("mode:default", result["applied_layers"])
        self.assertIn("task:conversation", result["applied_layers"])
        self.assertIn("autonomy_level_1_or_higher", result["context_flags"])

    def test_task_route_can_override_mode_route_for_coding(self):
        result = build_model_routing_decision(
            configs=self._build_configs(),
            mode="tutor",
            task_type="coding",
            autonomy_level=1,
            context_flags=[],
        )

        self.assertEqual(result["preferred_role"], "primary_code")
        self.assertEqual(result["selected_role"], "primary_code")
        self.assertEqual(result["fallback_role"], "primary_general")
        self.assertEqual(result["selected_model"], "starcoder2-15b-instruct")
        self.assertEqual(result["selected_runtime"], "ollama")
        self.assertTrue(result["stayed_local"])
        self.assertTrue(result["allowed"])
        self.assertIn("mode:tutor", result["applied_layers"])
        self.assertIn("task:coding", result["applied_layers"])

    def test_measured_runtime_selection_stays_within_role_and_honors_resource_preference(self):
        configs = self._build_configs()
        role = configs["models"]["model_roles"]["roles"]["primary_general"]
        role["preferred_model_runtime_tags"] = ["mistral-small3.1:24b"]
        role["fallback_model_runtime_tags"] = ["granite3.3:8b"]
        health = {
            "models": [
                {
                    "runtime_tag": "mistral-small3.1:24b", "installed": True,
                    "size_bytes": 15_486_899_116, "expected_ram_mb": 14770,
                    "loaded": False,
                    "history": {"success_count": 4, "failure_count": 0, "median_latency_ms": 900},
                },
                {
                    "runtime_tag": "granite3.3:8b", "installed": True,
                    "size_bytes": 4_942_891_653, "expected_ram_mb": 4714,
                    "loaded": True,
                    "history": {"success_count": 4, "failure_count": 0, "median_latency_ms": 250},
                },
            ]
        }
        result = build_model_routing_decision(
            configs=configs, mode="default", task_type="conversation",
            autonomy_level=3, reasoning_gear="standard",
            performance_preference="resource", model_health=health,
            ram_mb_ceiling=16384,
        )
        self.assertEqual(result["selected_role"], "primary_general")
        self.assertEqual(result["selected_runtime_tag"], "granite3.3:8b")
        self.assertIn(
            "resource_preference_measured_selection",
            result["measured_selection_reasons"],
        )

        quality = build_model_routing_decision(
            configs=configs, mode="default", task_type="conversation",
            autonomy_level=3, reasoning_gear="deep",
            performance_preference="quality", model_health=health,
            ram_mb_ceiling=16384,
        )
        self.assertEqual(quality["selected_runtime_tag"], "mistral-small3.1:24b")

    def test_specialist_task_falls_back_without_explicit_enablement(self):
        result = build_model_routing_decision(
            configs=self._build_configs(),
            mode="researcher",
            task_type="specialist_task",
            autonomy_level=1,
            context_flags=["bounded_task_scope", "no_silent_substitution"],
        )

        self.assertEqual(result["selected_role"], "primary_general")
        self.assertEqual(
            result["selected_role_reason"],
            "fallback_due_to_unmet_route_requirements",
        )
        self.assertTrue(result["requirements_met"] is False)
        self.assertIn("explicit_enablement", result["unmet_requirements"])
        self.assertIn(
            "fallback_due_to_unmet_route_requirements=explicit_enablement",
            " ".join(result["decision_path"]),
        )
        self.assertTrue(result["stayed_local"])
        self.assertTrue(result["allowed"])

    def test_specialist_task_selects_specialist_with_explicit_enablement(self):
        result = build_model_routing_decision(
            configs=self._build_configs(),
            mode="researcher",
            task_type="specialist_task",
            autonomy_level=1,
            context_flags=[
                "explicit_enablement",
                "bounded_task_scope",
                "no_silent_substitution",
            ],
        )

        self.assertEqual(result["selected_role"], "optional_specialist")
        self.assertEqual(result["selected_role_container"], "roles")
        self.assertEqual(result["selected_target"], "qwen3-coder-next")
        self.assertEqual(result["selected_model"], "qwen3-coder-next")
        self.assertEqual(result["selected_runtime"], "ollama")
        self.assertTrue(result["selected_is_specialist"])
        self.assertTrue(result["requirements_met"])
        self.assertTrue(result["stayed_local"])
        self.assertTrue(result["allowed"])

    def test_bounded_public_research_falls_back_when_requirements_are_unmet(self):
        result = build_model_routing_decision(
            configs=self._build_configs(),
            mode="researcher",
            task_type="bounded_public_research",
            autonomy_level=2,
            context_flags=[],
        )

        self.assertEqual(result["selected_role"], "lighter_backup")
        self.assertEqual(
            result["selected_role_reason"],
            "fallback_due_to_unmet_route_requirements",
        )
        self.assertIn("autonomy_level_3_or_higher", result["unmet_requirements"])
        self.assertIn("approved_tool_path", result["unmet_requirements"])
        self.assertIn("explicit_public_source_scope", result["unmet_requirements"])
        self.assertEqual(result["selected_model"], "granite-3.3-8b-instruct")
        self.assertTrue(result["stayed_local"])
        self.assertTrue(result["allowed"])

    def test_external_consultation_requires_explicit_approval_and_request(self):
        result = build_model_routing_decision(
            configs=self._build_configs(),
            mode="default",
            task_type="external_consultation",
            autonomy_level=1,
            context_flags=[],
        )

        self.assertEqual(result["selected_role"], "primary_general")
        self.assertEqual(
            result["selected_role_reason"],
            "fallback_due_to_unmet_route_requirements",
        )
        self.assertIn("explicit_approval", result["unmet_requirements"])
        self.assertIn("explicit_user_request", result["unmet_requirements"])
        self.assertFalse(result["selected_is_external"])
        self.assertTrue(result["stayed_local"])
        self.assertTrue(result["external_routing_forbidden"])

    def test_external_consultation_can_select_explicit_cloud_consultant(self):
        result = build_model_routing_decision(
            configs=self._build_configs(),
            mode="default",
            task_type="external_consultation",
            autonomy_level=1,
            context_flags=[
                "explicit_approval",
                "explicit_user_request",
                "outbound_use_is_logged",
                "no_private_memory_authority",
            ],
        )

        self.assertEqual(result["selected_role"], "optional_cloud_consultant")
        self.assertEqual(result["selected_role_container"], "external_helpers")
        self.assertEqual(result["selected_service"], "chatgpt")
        self.assertEqual(result["selected_target"], "chatgpt")
        self.assertTrue(result["selected_is_external"])
        self.assertFalse(result["stayed_local"])
        self.assertTrue(result["allowed"])
        self.assertTrue(result["external_routing_forbidden"])


if __name__ == "__main__":
    unittest.main()
