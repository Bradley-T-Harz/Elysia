import unittest

from core.responder import compose_response


class TestResponder(unittest.TestCase):
    def test_allowed_and_verified_response_can_have_no_caveats(self):
        plan = {
            "intent": "conversation",
            "mode": "companion",
            "uses_memory_context": False,
            "memory_context_source": "",
            "memory_class": "",
            "memory_class_source": "",
            "forced_memory_class": "",
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": False,
        }
        policy_review = {
            "allowed": True,
            "boundary_flags": [],
        }
        verification = {
            "verified": True,
        }

        result = compose_response(
            "Hello there",
            plan,
            policy_review,
            verification,
        )

        self.assertEqual(result["status"], "response_composed")
        self.assertEqual(result["intent"], "conversation")
        self.assertEqual(result["mode"], "companion")
        self.assertEqual(
            result["caveats"],
            [
                "Tool or side-effect authority was not granted for this response; no such operation was implied by model generation.",
                "Mode profile posture used: companion. Modes shape weighting and style, not authority.",
            ],
        )
        self.assertEqual(result["mode_profile"]["key"], "companion")
        self.assertTrue(result["mode_profile"]["used"])
        self.assertFalse(result["mode_profile"]["authority_granted_by_mode"])
        self.assertIn("without memory context", result["response_text"])
        self.assertIn(
            "The current scaffold selected memory class 'unspecified' from 'unknown'.",
            result["response_text"],
        )
        self.assertIn("Verification checks passed.", result["response_text"])

    def test_blocked_local_session_memory_response_contains_memory_caveat(self):
        plan = {
            "intent": "tutoring",
            "mode": "tutor",
            "uses_memory_context": True,
            "memory_context_source": "local_session_journal_scaffold",
            "memory_class": "working_memory",
            "memory_class_source": "forced_memory_class",
            "forced_memory_class": "working_memory",
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": True,
        }
        policy_review = {
            "allowed": False,
            "boundary_flags": ["local_session_memory"],
        }
        verification = {
            "verified": True,
        }

        result = compose_response(
            "Can you explain derivatives step by step?",
            plan,
            policy_review,
            verification,
        )

        self.assertIn(
            "Tool or side-effect authority was not granted for this response; no such operation was implied by model generation.",
            result["caveats"],
        )
        self.assertIn(
            "Local session journal memory was considered during context gathering.",
            result["caveats"],
        )
        self.assertIn(
            "Memory handling was constrained by policy boundaries.",
            result["caveats"],
        )
        self.assertIn(
            "Additional boundary checks were applied to the selected memory path.",
            result["caveats"],
        )
        self.assertIn(
            "using memory context from 'local_session_journal_scaffold'",
            result["response_text"],
        )
        self.assertIn(
            "The current scaffold selected memory class 'working_memory' from 'forced_memory_class'.",
            result["response_text"],
        )
        self.assertIn(
            "Policy boundaries forced memory class 'working_memory'.",
            result["response_text"],
        )

    def test_unverified_response_contains_verification_caveat(self):
        plan = {
            "intent": "research",
            "mode": "researcher",
            "uses_memory_context": False,
            "memory_context_source": "",
            "memory_class": "research_memory",
            "memory_class_source": "primary_memory_class",
            "forced_memory_class": "",
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": False,
        }
        policy_review = {
            "allowed": True,
            "boundary_flags": [],
        }
        verification = {
            "verified": False,
        }

        result = compose_response(
            "Summarize these sources",
            plan,
            policy_review,
            verification,
        )

        self.assertIn(
            "Internal verification did not fully pass.",
            result["caveats"],
        )
        self.assertIn(
            "The current scaffold selected memory class 'research_memory' from 'primary_memory_class'.",
            result["response_text"],
        )
        self.assertIn(
            "Verification checks did not fully pass.",
            result["response_text"],
        )

    def test_boundary_sensitive_forced_memory_class_adds_careful_caveats(self):
        plan = {
            "intent": "personal_support",
            "mode": "researcher",
            "uses_memory_context": False,
            "memory_context_source": "",
            "memory_class": "sealed_private_memory",
            "memory_class_source": "forced_memory_class",
            "forced_memory_class": "sealed_private_memory",
            "memory_class_boundary_sensitive": True,
            "memory_class_requires_boundary_check": True,
        }
        policy_review = {
            "allowed": False,
            "boundary_flags": ["sealed_private_memory"],
        }
        verification = {
            "verified": True,
        }

        result = compose_response(
            "Handle this carefully.",
            plan,
            policy_review,
            verification,
        )

        self.assertIn(
            "Tool or side-effect authority was not granted for this response; no such operation was implied by model generation.",
            result["caveats"],
        )
        self.assertIn(
            "Memory handling was constrained by policy boundaries.",
            result["caveats"],
        )
        self.assertIn(
            "A boundary-sensitive memory class shaped how this response was handled.",
            result["caveats"],
        )
        self.assertIn(
            "Additional boundary checks were applied to the selected memory path.",
            result["caveats"],
        )
        self.assertIn(
            "The current scaffold selected memory class 'sealed_private_memory' from 'forced_memory_class'.",
            result["response_text"],
        )
        self.assertIn(
            "Policy boundaries forced memory class 'sealed_private_memory'.",
            result["response_text"],
        )

    def test_non_local_memory_context_gets_generic_memory_caveat(self):
        plan = {
            "intent": "writing",
            "mode": "writer",
            "uses_memory_context": True,
            "memory_context_source": "project_memory_context",
            "memory_class": "project_memory",
            "memory_class_source": "primary_memory_class",
            "forced_memory_class": "",
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": False,
        }
        policy_review = {
            "allowed": True,
            "boundary_flags": [],
        }
        verification = {
            "verified": True,
        }

        result = compose_response(
            "Help me revise this draft.",
            plan,
            policy_review,
            verification,
        )

        self.assertIn(
            "Memory-aware context was used during planning.",
            result["caveats"],
        )
        self.assertIn(
            "using memory context from 'project_memory_context'",
            result["response_text"],
        )
        self.assertIn(
            "The current scaffold selected memory class 'project_memory' from 'primary_memory_class'.",
            result["response_text"],
        )


    def test_completed_math_execution_adds_truth_caveat(self):
        plan = {
            "intent": "tutoring",
            "mode": "tutor",
            "uses_memory_context": False,
            "memory_context_source": "",
            "memory_class": "working_memory",
            "memory_class_source": "primary_memory_class",
            "forced_memory_class": "",
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": False,
        }
        policy_review = {
            "allowed": True,
            "boundary_flags": ["bounded_local_math_execution"],
        }
        verification = {
            "verified": True,
        }
        internal_result = {
            "status": "ok_scaffold",
            "note": "Internal scaffold result created before final response composition.",
            "math_execution": {
                "used": True,
                "status": "completed",
                "tool_kind": "math_executor",
                "operation": "evaluate",
                "result": "4",
                "numeric_result": 4.0,
                "errors": [],
            },
        }

        result = compose_response(
            "Evaluate 2 + 2.",
            plan,
            policy_review,
            verification,
            internal_result=internal_result,
        )

        self.assertIn(
            "Bounded local math execution was used to check part of this response.",
            result["caveats"],
        )
        self.assertIn(
            "Tool or side-effect authority was not granted for this response; no such operation was implied by model generation.",
            result["caveats"],
        )
        self.assertEqual(result["math_execution"]["status"], "completed")

    def test_failed_math_execution_adds_failure_truth_caveat(self):
        plan = {
            "intent": "tutoring",
            "mode": "tutor",
            "uses_memory_context": False,
            "memory_context_source": "",
            "memory_class": "working_memory",
            "memory_class_source": "primary_memory_class",
            "forced_memory_class": "",
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": False,
        }
        policy_review = {
            "allowed": True,
            "boundary_flags": ["bounded_local_math_execution"],
        }
        verification = {
            "verified": True,
        }
        internal_result = {
            "status": "ok_scaffold",
            "note": "Internal scaffold result created before final response composition.",
            "math_execution": {
                "used": True,
                "status": "failed",
                "tool_kind": "math_executor",
                "operation": "evaluate",
                "result": None,
                "numeric_result": None,
                "errors": ["SymPy unavailable."],
            },
        }

        result = compose_response(
            "Evaluate 2 + 2.",
            plan,
            policy_review,
            verification,
            internal_result=internal_result,
        )

        self.assertIn(
            "Bounded local math execution was attempted but did not complete successfully.",
            result["caveats"],
        )
        self.assertEqual(result["math_execution"]["status"], "failed")


    def test_coder_patch_plan_response_overrides_live_invoker_text(self):
        plan = {
            "intent": "coding",
            "mode": "coder",
            "uses_memory_context": False,
            "memory_context_source": "",
            "memory_class": "working_memory",
            "memory_class_source": "primary_memory_class",
            "forced_memory_class": "",
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": False,
            "code_patch_plan_candidate": True,
        }
        policy_review = {
            "allowed": True,
            "approval_required": False,
            "boundary_flags": ["bounded_repo_context", "code_patch_plan"],
        }
        verification = {
            "verified": True,
        }
        internal_result = {
            "status": "ok",
            "response_text": (
                "I applied the patch, rewrote core/runtime.py, and ran the tests."
            ),
            "code_patch_plan": {
                "used": True,
                "status": "completed",
                "tool_kind": "code_patch_formatter",
                "operation": "format_code_patch_plan",
                "summary": "Proposal-only Coder patch plan for the current request. No files were changed.",
                "files_to_touch": [
                    "core/runtime.py",
                    "apps/elysia-desktop/src/ConversationsPage.tsx",
                ],
                "patch_plan": [
                    "Inspect the current runtime response seam.",
                    "Replace hallucination-prone prose with structured Coder truth.",
                ],
                "tests_to_run": [
                    "./scripts/test_backend.sh tests/test_responder.py tests/test_runtime_coder_mode_flow.py -q",
                    "npm --prefix apps/elysia-desktop run typecheck",
                ],
                "risk_notes": [
                    "Responder changes affect all final response composition.",
                ],
                "rollback_notes": [
                    "Revert core/responder.py if focused responder tests fail.",
                ],
                "approval_needed": True,
                "approval_reason": "Code/file mutation requires explicit approval before application.",
                "can_apply_patch": False,
                "patch_application_live": False,
                "shell_execution_used": False,
                "network_access_used": False,
                "mutated_files": False,
                "external_workers_used": False,
                "warnings": [],
                "errors": [],
            },
        }

        result = compose_response(
            "Make a proposal-only patch plan for core/runtime.py.",
            plan,
            policy_review,
            verification,
            internal_result=internal_result,
        )

        self.assertEqual(result["response_source"], "structured_coder_patch_plan")
        self.assertIn("Proposal-only patch plan created.", result["response_text"])
        self.assertIn("core/runtime.py", result["response_text"])
        self.assertIn(
            "apps/elysia-desktop/src/ConversationsPage.tsx",
            result["response_text"],
        )
        self.assertIn(
            "Approval is required before any future patch application.",
            result["response_text"],
        )
        self.assertIn("No files were changed.", result["response_text"])
        self.assertIn(
            "No shell, network, Aider, OpenHands, external workers, or tests were used.",
            result["response_text"],
        )
        self.assertNotIn("I applied the patch", result["response_text"])
        self.assertNotIn("ran the tests", result["response_text"])

    def test_coder_repo_context_response_overrides_overclaiming_live_invoker_text(self):
        plan = {
            "intent": "coding",
            "mode": "coder",
            "uses_memory_context": False,
            "memory_context_source": "",
            "memory_class": "working_memory",
            "memory_class_source": "primary_memory_class",
            "forced_memory_class": "",
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": False,
            "repo_context_candidate": True,
        }
        policy_review = {
            "allowed": True,
            "approval_required": False,
            "boundary_flags": ["bounded_repo_context"],
        }
        verification = {
            "verified": True,
        }
        internal_result = {
            "status": "ok",
            "response_text": (
                "Git status is clean, there are no modified files, and I checked the repo with shell."
            ),
            "repo_context": {
                "used": True,
                "status": "completed",
                "tool_kind": "repo_context_gatherer",
                "operation": "gather_repo_context",
                "repo_key": "elysia",
                "repo_label": "Elysia local repository",
                "repo_root": "/project/Elysia",
                "trust_zone": "project_local",
                "appears_git_repo": True,
                "current_branch": "main",
                "git_head_read": True,
                "changed_files_live": False,
                "changed_files_note": "Git status detection is not live in repo context v0.",
                "safe_tree_entries": ["core/runtime.py", "core/responder.py"],
                "language_hints": ["Python", "TypeScript"],
                "framework_hints": ["FastAPI local API bridge", "React desktop UI"],
                "test_command_hints": ["./scripts/test_backend.sh -q"],
                "read_only": True,
                "approval_required": False,
                "network_access_used": False,
                "shell_used": False,
                "mutated_files": False,
                "warnings": [],
                "errors": [],
            },
        }

        result = compose_response(
            "Inspect this repo.",
            plan,
            policy_review,
            verification,
            internal_result=internal_result,
        )

        self.assertEqual(result["response_source"], "structured_coder_repo_context")
        self.assertIn("Read-only repo context gathered.", result["response_text"])
        self.assertIn("Elysia local repository", result["response_text"])
        self.assertIn("Python, TypeScript", result["response_text"])
        self.assertIn(
            "Git status detection is not live in repo context v0.",
            result["response_text"],
        )
        self.assertIn("No shell was used.", result["response_text"])
        self.assertIn("No network access was used.", result["response_text"])
        self.assertIn("No files were changed.", result["response_text"])
        self.assertNotIn("Git status is clean", result["response_text"])
        self.assertNotIn("checked the repo with shell", result["response_text"])

    def test_public_research_request_without_worker_gets_bounded_research_truth(self):
        plan = {
            "intent": "research",
            "mode": "researcher",
            "uses_memory_context": False,
            "memory_context_source": "",
            "memory_class": "research_memory",
            "memory_class_source": "primary_memory_class",
            "forced_memory_class": "",
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": False,
        }
        policy_review = {
            "allowed": True,
            "approval_required": False,
            "boundary_flags": [],
        }
        verification = {
            "verified": True,
        }
        internal_result = {
            "status": "ok",
            "response_text": "Here is general guidance about SearXNG.",
        }

        result = compose_response(
            "Search public sources for current SearXNG self-hosting guidance.",
            plan,
            policy_review,
            verification,
            internal_result=internal_result,
        )

        self.assertIn(
            "bounded SearXNG research did not run",
            result["response_text"],
        )
        self.assertIn(
            "I did not fetch web pages or produce evidence packets",
            result["response_text"],
        )
        self.assertIn(
            "not current web evidence",
            " ".join(result["caveats"]),
        )





if __name__ == "__main__":
    unittest.main()
