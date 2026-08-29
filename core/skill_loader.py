"""
Elysia skill loader scaffold.

This module loads YAML skill definitions from the project's skills/ tree
so runtime can begin discovering capabilities from disk instead of relying
only on hardcoded assumptions.
"""

from pathlib import Path
from typing import Any, Dict

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = PROJECT_ROOT / "skills"


def load_yaml_file(path: Path) -> Dict[str, Any]:
    """
    Load one YAML file and return its top-level dictionary.
    """
    if not path.exists():
        raise FileNotFoundError(f"Skill file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Expected a top-level mapping in: {path}")

    return data


def load_all_skills() -> Dict[str, Dict[str, Any]]:
    """
    Load all skill YAML files under skills/, excluding the shared template.

    Returns a mapping keyed by skill id, for example:
    {
        "conversation.conversation_helper": {...},
        "tutoring.tutoring_helper": {...},
    }
    """
    if not SKILLS_ROOT.exists():
        raise FileNotFoundError(f"Skills root not found: {SKILLS_ROOT}")

    loaded: Dict[str, Dict[str, Any]] = {}

    for path in sorted(SKILLS_ROOT.rglob("*.yaml")):
        if path.name == "_skill_template.yaml":
            continue

        skill_data = load_yaml_file(path)
        skill_id = skill_data.get("id")

        if not skill_id:
            raise ValueError(f"Skill file missing 'id': {path}")

        if not isinstance(skill_id, str):
            raise ValueError(f"Skill id must be a string: {path}")

        loaded[skill_id] = skill_data

    return loaded


if __name__ == "__main__":
    skills = load_all_skills()
    print(f"Loaded skills: {len(skills)}")
    for skill_id in sorted(skills):
        print(f"- {skill_id}")
