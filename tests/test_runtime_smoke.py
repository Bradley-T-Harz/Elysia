import unittest
from unittest.mock import patch

from core.runtime import SessionState, handle_user_message


class TestRuntimeSmoke(unittest.TestCase):
    def test_runtime_returns_local_runtime_response(self):
        # This legacy-path smoke intentionally exercises Directed journaling;
        # the canonical no-argument default is Collaborative (Level 3).
        state = SessionState(autonomy_level=1)

        synthetic_memory = [
            {
                "source": "session_journal",
                "path": "/tmp/elysia-runtime-smoke-session.md",
                "title": "elysia-runtime-smoke-session.md",
                "preview": "Synthetic runtime smoke context.",
            }
        ]

        with patch(
            "core.context_gatherer.get_recent_session_memory",
            return_value=synthetic_memory,
        ), patch(
            "core.runtime.write_runtime_log",
            return_value="/tmp/elysia-smoke_runtime.log",
        ), patch(
            "core.runtime.write_session_journal_entry",
            return_value={
                "path": "/tmp/elysia-smoke_runtime-session.md",
                "journal_write_allowed": True,
                "journal_mode": "standard",
                "note": "Synthetic runtime smoke journal receipt.",
            },
        ), patch("core.runtime.invoke_model") as invoke_model:
            invoke_model.return_value = {
                "status": "ok",
                "allowed": True,
                "stayed_local": True,
                "selected_role": "primary_general",
                "selected_role_container": "roles",
                "selected_target": "mistral-small-3.1",
                "selected_model": "mistral-small-3.1",
                "selected_model_runtime_tag": "mistral-small3.1:24b",
                "selected_runtime": "ollama",
                "selected_service": "ollama",
                "used_fallback": False,
                "fallback_from": "",
                "fallback_to": "",
                "prompt_source": "derived/runtime/elysia_general_system.txt",
                "response_text": "Live governed local answer.",
                "error": "",
                "block_reasons": [],
                "unmet_requirements": [],
                "latency_ms": 1,
                "provider_metadata": {},
                "note": "Local Ollama invocation succeeded using the selected role.",
            }

            result = handle_user_message(
                "Can you explain derivatives step by step?",
                state,
            )

        self.assertEqual(result["status"], "ok_local_runtime")

        self.assertIn("config_status", result)
        self.assertIn("skill_status", result)
        self.assertIn("retrieval_policy", result)
        self.assertIn("memory_class_policy", result)
        self.assertIn("model_routing", result)
        self.assertIn("journal_policy", result)
        self.assertIn("context", result)
        self.assertIn("selected_skill", result)
        self.assertIn("log_status", result)
        self.assertIn("journal_status", result)
        self.assertIn("intent", result)
        self.assertIn("plan", result)
        self.assertIn("policy_review", result)
        self.assertIn("verification", result)
        self.assertIn("response", result)

        self.assertEqual(
            result["config_status"]["groups_loaded"],
            ["memory", "models", "policies", "system"],
        )
        self.assertTrue(
            {
                "imageforge_models",
                "media_runtime_registry",
                "model_roles",
                "routing",
                "speechforge_models",
                "videoforge_models",
            }.issubset(result["config_status"]["model_files"]),
        )
        self.assertTrue(
            {"approval_rules", "autonomy_levels", "personality_policy"}.issubset(
                result["config_status"]["policy_files"]
            ),
        )
        self.assertTrue(
            {"boundaries", "machine_profile", "source_policies", "stack"}.issubset(
                result["config_status"]["system_files"]
            ),
        )
        self.assertIn(
            "memory_policy",
            result["config_status"]["memory_files"],
        )

        self.assertEqual(result["skill_status"]["count"], 4)
        self.assertEqual(
            result["selected_skill"]["selected_skill_id"],
            "tutoring.tutoring_helper",
        )

        self.assertEqual(
            result["retrieval_policy"]["retrieval_mode"],
            "local_session_journal_scaffold_excluding_current_day",
        )
        self.assertEqual(
            result["context"]["retrieval_mode"],
            "local_session_journal_scaffold_excluding_current_day",
        )
        self.assertEqual(
            result["plan"]["memory_context_source"],
            "local_session_journal_scaffold_excluding_current_day",
        )

        self.assertTrue(result["plan"]["uses_memory_context"])
        self.assertTrue(result["plan"]["reads_private_memory"])

        self.assertEqual(
            result["memory_class_policy"]["default_memory_class"],
            "conversation_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["fallback_memory_class"],
            "working_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["primary_memory_class"],
            "working_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["forced_memory_class"],
            "working_memory",
        )
        self.assertEqual(
            result["memory_class_policy"]["allowed_memory_classes"],
            [
                "working_memory",
                "conversation_memory",
                "preference_memory",
                "project_memory",
            ],
        )
        self.assertEqual(
            result["memory_class_policy"]["disallowed_memory_classes"],
            [],
        )
        self.assertEqual(
            result["memory_class_policy"]["applied_boundary_overrides"],
            ["local_session_memory"],
        )
        self.assertIn(
            "mode=tutor",
            result["memory_class_policy"]["note"],
        )
        self.assertIn(
            "autonomy_level=1",
            result["memory_class_policy"]["note"],
        )
        self.assertIn(
            "boundary_overrides=local_session_memory",
            result["memory_class_policy"]["note"],
        )

        self.assertEqual(result["plan"]["memory_class"], "working_memory")
        self.assertEqual(result["plan"]["primary_memory_class"], "working_memory")
        self.assertEqual(result["plan"]["default_memory_class"], "conversation_memory")
        self.assertEqual(result["plan"]["fallback_memory_class"], "working_memory")
        self.assertEqual(
            result["plan"]["allowed_memory_classes"],
            [
                "working_memory",
                "conversation_memory",
                "preference_memory",
                "project_memory",
            ],
        )
        self.assertEqual(result["plan"]["disallowed_memory_classes"], [])
        self.assertEqual(result["plan"]["forced_memory_class"], "working_memory")
        self.assertEqual(
            result["plan"]["memory_class_source"],
            "forced_memory_class",
        )
        self.assertTrue(result["plan"]["memory_class_declared"])
        self.assertFalse(result["plan"]["memory_class_boundary_sensitive"])
        self.assertTrue(result["plan"]["memory_class_requires_boundary_check"])

        self.assertEqual(
            result["model_routing"]["routing_mode"],
            "explicit_local_first_role_governed",
        )
        self.assertEqual(result["model_routing"]["mode"], "tutor")
        self.assertEqual(result["model_routing"]["task_type"], "tutoring")
        self.assertEqual(result["model_routing"]["preferred_role"], "primary_general")
        self.assertEqual(result["model_routing"]["selected_role"], "primary_general")
        self.assertEqual(
            result["model_routing"]["selected_role_reason"],
            "preferred_role",
        )
        self.assertEqual(
            result["model_routing"]["selected_role_container"],
            "roles",
        )
        self.assertEqual(
            result["model_routing"]["selected_target"],
            "mistral-small-3.1",
        )
        self.assertEqual(
            result["model_routing"]["selected_model"],
            "mistral-small-3.1",
        )
        self.assertEqual(
            result["model_routing"]["selected_service"],
            "",
        )
        self.assertEqual(
            result["model_routing"]["selected_runtime"],
            "ollama",
        )
        self.assertEqual(
            result["model_routing"]["selected_role_status"],
            "candidate_declared",
        )
        self.assertTrue(result["model_routing"]["selected_role_local_only"])
        self.assertTrue(result["model_routing"]["selected_role_enabled_by_default"])
        self.assertFalse(
            result["model_routing"]["selected_role_explicit_approval_required"]
        )
        self.assertEqual(
            result["model_routing"]["selected_role_privacy_risk"],
            "low",
        )
        self.assertTrue(
            "Trust-first local general brain."
            in result["model_routing"]["selected_role_trust_note"]
        )
        self.assertEqual(result["model_routing"]["fallback_role"], "lighter_backup")
        self.assertEqual(
            result["model_routing"]["fallback_role_container"],
            "roles",
        )
        self.assertEqual(
            result["model_routing"]["fallback_target"],
            "granite-3.3-8b-instruct",
        )
        self.assertTrue(result["model_routing"]["route_local_only"])
        self.assertTrue(result["model_routing"]["requirements_met"])
        self.assertEqual(result["model_routing"]["unmet_requirements"], [])
        self.assertTrue(result["model_routing"]["stayed_local"])
        self.assertFalse(result["model_routing"]["selected_is_specialist"])
        self.assertFalse(result["model_routing"]["selected_is_external"])
        self.assertTrue(result["model_routing"]["external_routing_forbidden"])
        self.assertTrue(result["model_routing"]["allowed"])
        self.assertEqual(result["model_routing"]["route_block_reasons"], [])
        self.assertIn("mode:tutor", result["model_routing"]["applied_layers"])
        self.assertIn("task:tutoring", result["model_routing"]["applied_layers"])
        self.assertIn(
            "selected_role=primary_general",
            result["model_routing"]["note"],
        )
        self.assertIn(
            "stayed_local=True",
            result["model_routing"]["note"],
        )

        self.assertTrue(result["policy_review"]["allowed"])
        self.assertFalse(result["policy_review"]["approval_required"])
        self.assertEqual(
            result["policy_review"]["boundary_flags"],
            ["local_session_memory"],
        )
        self.assertIn(
            "plan reads local session journal memory",
            result["policy_review"]["approval_reasons"],
        )

        self.assertTrue(result["verification"]["verified"])
        self.assertIn(
            "memory_source_present_when_memory_used",
            result["verification"]["checks_passed"],
        )

        self.assertIn(
            "Local session journal memory was considered during context gathering.",
            result["response"]["caveats"],
        )

        self.assertTrue(result["log_status"]["path"].endswith("_runtime.log"))

        self.assertTrue(result["journal_policy"]["journal_write_allowed"])
        self.assertEqual(result["journal_policy"]["journal_mode"], "standard")
        self.assertTrue(result["journal_policy"]["include_plan_summary"])
        self.assertTrue(result["journal_policy"]["include_retrieval_summary"])
        self.assertTrue(result["journal_policy"]["include_boundary_flags"])
        self.assertTrue(result["journal_policy"]["include_memory_class"])
        self.assertTrue(result["journal_policy"]["include_policy_summary"])
        self.assertTrue(result["journal_policy"]["redact_sensitive_content"])
        self.assertEqual(
            result["journal_policy"]["applied_boundary_overrides"],
            [],
        )
        self.assertIn(
            "mode=tutor",
            result["journal_policy"]["note"],
        )
        self.assertIn(
            "autonomy_level=1",
            result["journal_policy"]["note"],
        )

        self.assertTrue(
            result["journal_status"]["path"].endswith("_runtime-session.md")
        )
        self.assertTrue(result["journal_status"]["journal_write_allowed"])
        self.assertEqual(
            result["journal_status"]["journal_mode"],
            "standard",
        )

        self.assertIn("governed local cognition path", result["note"])
        self.assertIn("identity-scoped workspace admission", result["note"])
        self.assertIn("deterministic cognition and compute decisions", result["note"])
        self.assertIn("gear-depth verification", result["note"])
        self.assertIn("continuity journaling", result["note"])


if __name__ == "__main__":
    unittest.main()
