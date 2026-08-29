import unittest

from core.verifier import verify_result


def _base_verified_plan():
    return {
        "intent": "tutoring",
        "mode": "tutor",
        "steps": [
            "interpret the request",
            "gather allowed context",
            "explain clearly",
            "check whether the explanation matches the learning goal",
        ],
        "retrieved_memory_count": 0,
        "uses_memory_context": False,
        "memory_context_source": "",
        "reads_private_memory": False,
        "memory_class": "conversation_memory",
        "primary_memory_class": "conversation_memory",
        "forced_memory_class": "",
        "memory_class_source": "primary_memory_class",
        "memory_class_declared": True,
        "memory_class_boundary_sensitive": False,
        "memory_class_requires_boundary_check": False,
    }


def _base_internal_result():
    return {
        "status": "ok_scaffold",
        "note": "Internal scaffold result created before final response composition.",
    }




class TestVerifier(unittest.TestCase):
    def test_valid_plan_and_result_pass_verification(self):
        plan = {
            "intent": "tutoring",
            "mode": "tutor",
            "steps": [
                "interpret the request",
                "gather allowed context",
                "explain clearly",
                "check whether the explanation matches the learning goal",
            ],
            "retrieved_memory_count": 2,
            "uses_memory_context": True,
            "memory_context_source": "local_session_journal_scaffold",
            "reads_private_memory": True,
            "memory_class": "working_memory",
            "primary_memory_class": "working_memory",
            "forced_memory_class": "working_memory",
            "memory_class_source": "forced_memory_class",
            "memory_class_declared": True,
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": True,
        }

        internal_result = {
            "status": "ok_scaffold",
            "note": "Internal scaffold result created before final response composition.",
        }

        result = verify_result(plan, internal_result)

        self.assertTrue(result["verified"])
        self.assertIn("plan_has_intent", result["checks_passed"])
        self.assertIn("plan_has_mode", result["checks_passed"])
        self.assertIn("result_has_status", result["checks_passed"])
        self.assertIn("result_has_note", result["checks_passed"])
        self.assertIn("memory_count_is_nonnegative", result["checks_passed"])
        self.assertIn("memory_usage_matches_count", result["checks_passed"])
        self.assertIn(
            "memory_source_present_when_memory_used",
            result["checks_passed"],
        )
        self.assertIn(
            "declared_memory_class_present",
            result["checks_passed"],
        )
        self.assertIn(
            "memory_class_source_present_when_memory_class_set",
            result["checks_passed"],
        )
        self.assertIn(
            "primary_memory_class_present_when_memory_class_set",
            result["checks_passed"],
        )
        self.assertIn(
            "forced_memory_class_matches_selected_memory_class",
            result["checks_passed"],
        )
        self.assertIn(
            "forced_memory_class_source_is_explicit",
            result["checks_passed"],
        )
        self.assertIn(
            "memory_class_not_boundary_sensitive",
            result["checks_passed"],
        )
        self.assertIn(
            "memory_class_boundary_check_flag_present",
            result["checks_passed"],
        )
        self.assertEqual(result["issues"], [])

    def test_missing_plan_fields_fail_verification(self):
        plan = {
            "steps": ["interpret the request"],
            "retrieved_memory_count": 0,
            "uses_memory_context": False,
            "memory_context_source": "",
        }

        internal_result = {
            "status": "ok_scaffold",
        }

        result = verify_result(plan, internal_result)

        self.assertFalse(result["verified"])
        self.assertNotEqual(result["issues"], [])

    def test_missing_result_fields_fail_verification(self):
        plan = {
            "intent": "conversation",
            "mode": "companion",
            "retrieved_memory_count": 0,
            "uses_memory_context": False,
            "memory_context_source": "",
        }

        internal_result = {}

        result = verify_result(plan, internal_result)

        self.assertFalse(result["verified"])
        self.assertNotEqual(result["issues"], [])

    def test_memory_usage_mismatch_fails_verification(self):
        plan = {
            "intent": "research",
            "mode": "analyst",
            "retrieved_memory_count": 0,
            "uses_memory_context": True,
            "memory_context_source": "",
        }

        internal_result = {
            "status": "ok_scaffold",
            "note": "Internal scaffold result created before final response composition.",
        }

        result = verify_result(plan, internal_result)

        self.assertFalse(result["verified"])
        self.assertIn(
            "uses_memory_context does not match retrieved_memory_count",
            result["issues"],
        )

    def test_memory_source_required_when_memory_is_used(self):
        plan = {
            "intent": "research",
            "mode": "analyst",
            "retrieved_memory_count": 2,
            "uses_memory_context": True,
            "memory_context_source": "",
        }

        internal_result = {
            "status": "ok_scaffold",
            "note": "Internal scaffold result created before final response composition.",
        }

        result = verify_result(plan, internal_result)

        self.assertFalse(result["verified"])
        self.assertIn(
            "memory_context_source is missing despite retrieved memory",
            result["issues"],
        )

    def test_declared_memory_class_requires_memory_class_value(self):
        plan = {
            "intent": "research",
            "mode": "researcher",
            "retrieved_memory_count": 0,
            "uses_memory_context": False,
            "memory_context_source": "",
            "memory_class_declared": True,
            "memory_class": "",
            "primary_memory_class": "research_memory",
            "memory_class_source": "",
            "forced_memory_class": "",
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": False,
            "reads_private_memory": False,
        }

        internal_result = {
            "status": "ok_scaffold",
            "note": "Internal scaffold result created before final response composition.",
        }

        result = verify_result(plan, internal_result)

        self.assertFalse(result["verified"])
        self.assertIn(
            "memory_class_declared is true but memory_class is missing",
            result["issues"],
        )

    def test_memory_class_requires_source_when_set(self):
        plan = {
            "intent": "research",
            "mode": "researcher",
            "retrieved_memory_count": 0,
            "uses_memory_context": False,
            "memory_context_source": "",
            "memory_class_declared": True,
            "memory_class": "research_memory",
            "primary_memory_class": "research_memory",
            "memory_class_source": "",
            "forced_memory_class": "",
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": False,
            "reads_private_memory": False,
        }

        internal_result = {
            "status": "ok_scaffold",
            "note": "Internal scaffold result created before final response composition.",
        }

        result = verify_result(plan, internal_result)

        self.assertFalse(result["verified"])
        self.assertIn(
            "memory_class_source is missing despite memory_class being set",
            result["issues"],
        )

    def test_forced_memory_class_must_match_selected_memory_class(self):
        plan = {
            "intent": "writing",
            "mode": "writer",
            "retrieved_memory_count": 0,
            "uses_memory_context": False,
            "memory_context_source": "",
            "reads_private_memory": True,
            "memory_class_declared": True,
            "memory_class": "project_memory",
            "primary_memory_class": "project_memory",
            "forced_memory_class": "sealed_private_memory",
            "memory_class_source": "forced_memory_class",
            "memory_class_boundary_sensitive": True,
            "memory_class_requires_boundary_check": True,
        }

        internal_result = {
            "status": "ok_scaffold",
            "note": "Internal scaffold result created before final response composition.",
        }

        result = verify_result(plan, internal_result)

        self.assertFalse(result["verified"])
        self.assertIn(
            "forced_memory_class does not match selected memory_class",
            result["issues"],
        )

    def test_boundary_sensitive_memory_class_requires_private_memory_read(self):
        plan = {
            "intent": "research",
            "mode": "researcher",
            "retrieved_memory_count": 0,
            "uses_memory_context": False,
            "memory_context_source": "",
            "reads_private_memory": False,
            "memory_class_declared": True,
            "memory_class": "sealed_private_memory",
            "primary_memory_class": "research_memory",
            "forced_memory_class": "",
            "memory_class_source": "forced_memory_class",
            "memory_class_boundary_sensitive": True,
            "memory_class_requires_boundary_check": True,
        }

        internal_result = {
            "status": "ok_scaffold",
            "note": "Internal scaffold result created before final response composition.",
        }

        result = verify_result(plan, internal_result)

        self.assertFalse(result["verified"])
        self.assertIn(
            "boundary-sensitive memory_class should imply reads_private_memory",
            result["issues"],
        )

    def test_forced_memory_class_requires_boundary_check_flag(self):
        plan = {
            "intent": "research",
            "mode": "researcher",
            "retrieved_memory_count": 0,
            "uses_memory_context": False,
            "memory_context_source": "",
            "reads_private_memory": True,
            "memory_class_declared": True,
            "memory_class": "sealed_private_memory",
            "primary_memory_class": "research_memory",
            "forced_memory_class": "sealed_private_memory",
            "memory_class_source": "forced_memory_class",
            "memory_class_boundary_sensitive": True,
            "memory_class_requires_boundary_check": False,
        }

        internal_result = {
            "status": "ok_scaffold",
            "note": "Internal scaffold result created before final response composition.",
        }

        result = verify_result(plan, internal_result)

        self.assertFalse(result["verified"])
        self.assertIn(
            "forced_memory_class should require memory_class_requires_boundary_check",
            result["issues"],
        )


    def test_completed_math_execution_candidate_passes_structural_verification(self):
        plan = _base_verified_plan()
        plan.update(
            {
                "bounded_math_execution_candidate": True,
                "math_execution_operation": "evaluate",
                "math_execution_expression": "2 + 2",
            }
        )
        internal_result = _base_internal_result()
        internal_result["math_execution"] = {
            "used": True,
            "status": "completed",
            "tool_kind": "math_executor",
            "operation": "evaluate",
            "result": "4",
            "numeric_result": 4.0,
            "errors": [],
        }

        result = verify_result(plan, internal_result)

        self.assertTrue(result["verified"])
        self.assertIn("math_execution_summary_present", result["checks_passed"])
        self.assertIn("math_execution_status_present", result["checks_passed"])
        self.assertIn("math_execution_marked_used", result["checks_passed"])
        self.assertIn("math_execution_completed_with_result", result["checks_passed"])
        self.assertEqual(result["issues"], [])

    def test_math_execution_candidate_without_result_fails_verification(self):
        plan = _base_verified_plan()
        plan["bounded_math_execution_candidate"] = True
        internal_result = _base_internal_result()

        result = verify_result(plan, internal_result)

        self.assertFalse(result["verified"])
        self.assertIn(
            "plan requested bounded math execution but result is missing",
            result["issues"],
        )

    def test_completed_math_execution_without_result_fails_verification(self):
        plan = _base_verified_plan()
        plan["bounded_math_execution_candidate"] = True
        internal_result = _base_internal_result()
        internal_result["math_execution"] = {
            "used": True,
            "status": "completed",
            "tool_kind": "math_executor",
            "operation": "evaluate",
            "result": None,
            "numeric_result": None,
            "errors": [],
        }

        result = verify_result(plan, internal_result)

        self.assertFalse(result["verified"])
        self.assertIn(
            "completed math execution is missing result",
            result["issues"],
        )

    def test_failed_math_execution_without_errors_fails_verification(self):
        plan = _base_verified_plan()
        plan["bounded_math_execution_candidate"] = True
        internal_result = _base_internal_result()
        internal_result["math_execution"] = {
            "used": True,
            "status": "failed",
            "tool_kind": "math_executor",
            "operation": "evaluate",
            "result": None,
            "numeric_result": None,
            "errors": [],
        }

        result = verify_result(plan, internal_result)

        self.assertFalse(result["verified"])
        self.assertIn(
            "failed math execution is missing errors",
            result["issues"],
        )




if __name__ == "__main__":
    unittest.main()
