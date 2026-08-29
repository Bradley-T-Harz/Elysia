import unittest

from core.policy_gate import evaluate_plan


class TestPolicyGate(unittest.TestCase):
    def test_safe_nonexecuting_local_response_plan_is_allowed_without_approval(self):
        plan = {
            "steps": [
                "interpret the request",
                "gather allowed context",
                "respond carefully",
                "check the result",
            ],
            "requires_tools": False,
            "touches_external_network": False,
            "writes_files": False,
            "reads_private_memory": False,
            "risk_level": "low",
            "execution_allowed": False,
        }

        result = evaluate_plan(plan)

        self.assertTrue(result["allowed"])
        self.assertFalse(result["approval_required"])
        self.assertIn(
            "governed local response generation may proceed",
            result["approval_reasons"][0],
        )
        self.assertEqual(result["boundary_flags"], ["low_risk_nonexecuting_path"])
        self.assertEqual(result["checked_step_count"], 4)

    def test_external_network_plan_gets_flagged_and_requires_approval(self):
        plan = {
            "steps": ["interpret", "check"],
            "touches_external_network": True,
            "risk_level": "low",
            "execution_allowed": False,
        }

        result = evaluate_plan(plan)

        self.assertFalse(result["allowed"])
        self.assertTrue(result["approval_required"])
        self.assertIn("external_network", result["boundary_flags"])
        self.assertIn(
            "plan touches external network",
            result["approval_reasons"],
        )

    def test_file_writing_plan_gets_flagged_and_requires_approval(self):
        plan = {
            "steps": ["interpret", "write"],
            "writes_files": True,
            "risk_level": "low",
            "execution_allowed": False,
        }

        result = evaluate_plan(plan)

        self.assertFalse(result["allowed"])
        self.assertTrue(result["approval_required"])
        self.assertIn("file_writes", result["boundary_flags"])
        self.assertIn(
            "plan writes files",
            result["approval_reasons"],
        )

    def test_high_risk_plan_gets_flagged_and_requires_approval(self):
        plan = {
            "steps": ["interpret", "decide"],
            "risk_level": "high",
            "execution_allowed": False,
        }

        result = evaluate_plan(plan)

        self.assertFalse(result["allowed"])
        self.assertTrue(result["approval_required"])
        self.assertIn("high_risk", result["boundary_flags"])
        self.assertIn(
            "plan is marked high risk",
            result["approval_reasons"],
        )

    def test_tool_and_private_memory_flags_are_recorded_and_require_approval(self):
        plan = {
            "steps": ["interpret", "retrieve"],
            "requires_tools": True,
            "reads_private_memory": True,
            "memory_context_source": "other_private_memory_source",
            "risk_level": "low",
            "execution_allowed": False,
        }

        result = evaluate_plan(plan)

        self.assertFalse(result["allowed"])
        self.assertTrue(result["approval_required"])
        self.assertIn("tool_usage", result["boundary_flags"])
        self.assertIn("private_memory", result["boundary_flags"])
        self.assertIn(
            "plan requests tool usage",
            result["approval_reasons"],
        )
        self.assertIn(
            "plan reads private memory",
            result["approval_reasons"],
        )

    def test_local_session_memory_gets_specific_flag_without_requiring_approval(self):
        plan = {
            "steps": ["interpret", "retrieve"],
            "reads_private_memory": True,
            "memory_context_source": "local_session_journal_scaffold",
            "risk_level": "low",
            "execution_allowed": False,
        }

        result = evaluate_plan(plan)

        self.assertTrue(result["allowed"])
        self.assertFalse(result["approval_required"])
        self.assertIn("local_session_memory", result["boundary_flags"])
        self.assertIn(
            "plan reads local session journal memory",
            result["approval_reasons"],
        )
        self.assertNotIn("private_memory", result["boundary_flags"])

    def test_local_session_memory_variant_gets_specific_flag_without_requiring_approval(self):
        plan = {
            "steps": ["interpret", "retrieve"],
            "reads_private_memory": True,
            "memory_context_source": "local_session_journal_scaffold_excluding_current_day",
            "risk_level": "low",
            "execution_allowed": False,
        }

        result = evaluate_plan(plan)

        self.assertTrue(result["allowed"])
        self.assertFalse(result["approval_required"])
        self.assertIn("local_session_memory", result["boundary_flags"])
        self.assertIn(
            "plan reads local session journal memory",
            result["approval_reasons"],
        )
        self.assertNotIn("private_memory", result["boundary_flags"])

    def test_sealed_private_memory_gets_specific_flag_and_requires_approval(self):
        plan = {
            "steps": ["interpret", "retrieve"],
            "reads_private_memory": True,
            "memory_context_source": "non_local_memory_source",
            "memory_class": "sealed_private_memory",
            "memory_class_boundary_sensitive": True,
            "memory_class_requires_boundary_check": True,
            "risk_level": "low",
            "execution_allowed": False,
        }

        result = evaluate_plan(plan)

        self.assertFalse(result["allowed"])
        self.assertTrue(result["approval_required"])
        self.assertIn("sealed_private_memory", result["boundary_flags"])
        self.assertNotIn("private_memory", result["boundary_flags"])
        self.assertIn(
            "plan uses sealed private memory class",
            result["approval_reasons"],
        )
        self.assertIn(
            "plan memory class sealed_private_memory is boundary-sensitive",
            result["approval_reasons"],
        )
        self.assertIn(
            "selected memory class requires boundary check",
            result["approval_reasons"],
        )

    def test_audit_memory_gets_specific_flag_and_requires_approval(self):
        plan = {
            "steps": ["interpret", "retrieve"],
            "reads_private_memory": True,
            "memory_context_source": "non_local_memory_source",
            "memory_class": "audit_memory",
            "memory_class_boundary_sensitive": True,
            "memory_class_requires_boundary_check": True,
            "risk_level": "low",
            "execution_allowed": False,
        }

        result = evaluate_plan(plan)

        self.assertFalse(result["allowed"])
        self.assertTrue(result["approval_required"])
        self.assertIn("audit_memory", result["boundary_flags"])
        self.assertNotIn("private_memory", result["boundary_flags"])
        self.assertIn(
            "plan uses audit memory class",
            result["approval_reasons"],
        )
        self.assertIn(
            "plan memory class audit_memory is boundary-sensitive",
            result["approval_reasons"],
        )
        self.assertIn(
            "selected memory class requires boundary check",
            result["approval_reasons"],
        )

    def test_forced_sensitive_memory_class_reason_is_recorded_and_requires_approval(self):
        plan = {
            "steps": ["interpret", "retrieve"],
            "reads_private_memory": False,
            "memory_context_source": "non_local_memory_source",
            "memory_class": "project_memory",
            "forced_memory_class": "sealed_private_memory",
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": False,
            "risk_level": "low",
            "execution_allowed": False,
        }

        result = evaluate_plan(plan)

        self.assertFalse(result["allowed"])
        self.assertTrue(result["approval_required"])
        self.assertIn("sealed_private_memory", result["boundary_flags"])
        self.assertIn(
            "plan memory class was forced to sealed_private_memory",
            result["approval_reasons"],
        )
        self.assertIn(
            "forced memory class sealed_private_memory is approval-bound",
            result["approval_reasons"],
        )

    def test_local_session_memory_does_not_add_forced_memory_class_reason_or_require_approval(self):
        plan = {
            "steps": ["interpret", "retrieve"],
            "reads_private_memory": True,
            "memory_context_source": "local_session_journal_scaffold_excluding_current_day",
            "memory_class": "working_memory",
            "forced_memory_class": "working_memory",
            "memory_class_boundary_sensitive": False,
            "memory_class_requires_boundary_check": True,
            "risk_level": "low",
            "execution_allowed": False,
        }

        result = evaluate_plan(plan)

        self.assertTrue(result["allowed"])
        self.assertFalse(result["approval_required"])
        self.assertIn("local_session_memory", result["boundary_flags"])
        self.assertIn(
            "plan reads local session journal memory",
            result["approval_reasons"],
        )
        self.assertNotIn(
            "plan memory class was forced to working_memory",
            result["approval_reasons"],
        )
        self.assertIn(
            "selected memory class requires boundary check",
            result["approval_reasons"],
        )
        self.assertNotIn("private_memory", result["boundary_flags"])


    def test_bounded_local_math_execution_is_allowed_without_approval(self):
        plan = {
            "steps": ["interpret", "check bounded local math", "respond"],
            "requires_tools": False,
            "touches_external_network": False,
            "writes_files": False,
            "reads_private_memory": False,
            "risk_level": "low",
            "execution_allowed": False,
            "bounded_math_execution_candidate": True,
        }

        result = evaluate_plan(plan)

        self.assertTrue(result["allowed"])
        self.assertFalse(result["approval_required"])
        self.assertIn("bounded_local_math_execution", result["boundary_flags"])
        self.assertIn(
            "bounded local math execution is allowed as non-side-effecting local computation",
            result["approval_reasons"],
        )
        self.assertNotIn("tool_usage", result["boundary_flags"])
        self.assertNotIn("external_network", result["boundary_flags"])
        self.assertNotIn("file_writes", result["boundary_flags"])

    def test_hard_blocked_private_outward_mutation_request_requires_approval(self):
        plan = {
            "steps": ["interpret request", "block unsafe boundary"],
            "requires_tools": False,
            "touches_external_network": True,
            "writes_files": True,
            "reads_private_memory": True,
            "hard_blocked_request": True,
            "risk_level": "high",
            "execution_allowed": False,
        }

        result = evaluate_plan(plan)

        self.assertFalse(result["allowed"])
        self.assertTrue(result["approval_required"])
        self.assertIn("hard_blocked_request", result["boundary_flags"])
        self.assertIn("external_network", result["boundary_flags"])
        self.assertIn("file_writes", result["boundary_flags"])
        self.assertIn("private_memory", result["boundary_flags"])

    def test_general_execution_request_remains_approval_bound(self):
        plan = {
            "steps": ["interpret", "execute"],
            "requires_tools": False,
            "touches_external_network": False,
            "writes_files": False,
            "reads_private_memory": False,
            "risk_level": "low",
            "execution_allowed": True,
            "bounded_math_execution_candidate": False,
        }

        result = evaluate_plan(plan)

        self.assertFalse(result["allowed"])
        self.assertTrue(result["approval_required"])
        self.assertTrue(
            any("execution" in flag for flag in result["boundary_flags"])
        )
        self.assertTrue(
            any("execution" in reason for reason in result["approval_reasons"])
        )




if __name__ == "__main__":
    unittest.main()
