"""
Elysia skill selector scaffold.

This module performs a very small, deterministic mapping from classified
intent to one loaded skill id. It does not execute skills yet; it only
selects the most relevant scaffold skill.
"""

from typing import Dict, Any, Optional


INTENT_TO_SKILL = {
    "tutoring": "tutoring.tutoring_helper",
    "conversation": "conversation.conversation_helper",
    "research": "research.research_summary_helper",
    "writing": "writing.drafting_helper",
}


def select_skill(intent: Dict[str, Any], skills: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Select one loaded skill based on the primary intent.

    Returns a small record like:
    {
        "selected_skill_id": "tutoring.tutoring_helper",
        "selection_basis": "intent_map",
        "found": True,
    }

    If no match is available, returns a record with found=False.
    """
    primary_intent = intent.get("primary", "")
    desired_skill_id = INTENT_TO_SKILL.get(primary_intent)

    if desired_skill_id and desired_skill_id in skills:
        return {
            "selected_skill_id": desired_skill_id,
            "selection_basis": "intent_map",
            "found": True,
        }

    return {
        "selected_skill_id": None,
        "selection_basis": "no_match",
        "found": False,
    }


if __name__ == "__main__":
    demo_skills = {
        "conversation.conversation_helper": {},
        "research.research_summary_helper": {},
        "tutoring.tutoring_helper": {},
        "writing.drafting_helper": {},
    }

    demo_intent = {"primary": "tutoring"}
    print(select_skill(demo_intent, demo_skills))
