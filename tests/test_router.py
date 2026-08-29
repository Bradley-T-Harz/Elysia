import unittest

from core.router import classify_intent, choose_mode


class TestRouter(unittest.TestCase):
    def test_classify_intent_detects_tutoring(self):
        result = classify_intent("Can you explain derivatives step by step?")
        self.assertEqual(result["primary"], "tutoring")
        self.assertIn("confidence", result)
        self.assertIn("note", result)

    def test_classify_intent_detects_writing(self):
        result = classify_intent("Can you draft and revise this email?")
        self.assertEqual(result["primary"], "writing")

    def test_classify_intent_detects_research(self):
        result = classify_intent("Can you research and summarize these sources?")
        self.assertEqual(result["primary"], "research")

    def test_classify_intent_defaults_to_conversation(self):
        result = classify_intent("Hello there.")
        self.assertEqual(result["primary"], "conversation")

    def test_runtime_locality_truth_question_is_not_coder_by_keyword_alone(self):
        result = classify_intent(
            "Tell me what model/runtime/locality/fallback/approval truth is visible for this request."
        )
        self.assertEqual(result["primary"], "conversation")

    def test_classifier_emits_real_bounded_governor_features(self):
        result = classify_intent(
            "Research the evidence and then draft a novel architecture; also audit its security tradeoffs."
        )
        self.assertGreaterEqual(result["competing_intent_count"], 2)
        self.assertGreaterEqual(result["subproblem_count"], 2)
        self.assertGreater(result["complexity_score"], 0.0)
        self.assertGreater(result["novelty_score"], 0.5)
        self.assertGreaterEqual(result["ambiguity_score"], 0.65)
        self.assertLessEqual(result["confidence"], 0.55)
        self.assertFalse(result["authority_granted"])

    def test_choose_mode_returns_tutor_for_tutoring(self):
        intent = {"primary": "tutoring"}
        result = choose_mode(intent, session_state=None)
        self.assertEqual(result, "tutor")

    def test_choose_mode_accepts_session_state_argument(self):
        intent = {"primary": "conversation"}
        result = choose_mode(intent, session_state={"active_mode": "default"})
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, "")


if __name__ == "__main__":
    unittest.main()
