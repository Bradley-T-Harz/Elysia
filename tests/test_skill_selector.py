import unittest

from core.skill_selector import select_skill


class TestSkillSelector(unittest.TestCase):
    def test_selects_tutoring_skill_when_available(self):
        intent = {"primary": "tutoring"}
        skills = {
            "tutoring.tutoring_helper": {"id": "tutoring.tutoring_helper"},
            "writing.drafting_helper": {"id": "writing.drafting_helper"},
        }

        result = select_skill(intent, skills)

        self.assertTrue(result["found"])
        self.assertEqual(
            result["selected_skill_id"],
            "tutoring.tutoring_helper",
        )
        self.assertEqual(result["selection_basis"], "intent_map")

    def test_returns_no_match_when_skill_missing(self):
        intent = {"primary": "research"}
        skills = {
            "writing.drafting_helper": {"id": "writing.drafting_helper"},
        }

        result = select_skill(intent, skills)

        self.assertFalse(result["found"])
        self.assertIsNone(result["selected_skill_id"])
        self.assertEqual(result["selection_basis"], "no_match")


if __name__ == "__main__":
    unittest.main()
