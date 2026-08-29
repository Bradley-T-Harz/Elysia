"""Deterministic request classification for Elysia's governed runtime.

The router does not grant authority.  It produces transparent task features
for mode selection and the Adaptive Cognition Governor; explicit session mode
and all downstream policy gates remain independently authoritative.
"""

import re
from typing import Any, Dict


_EXPLICIT_SESSION_MODES = {
    "default",
    "tutor",
    "researcher",
    "writer",
    "coder",
}

_SESSION_MODE_ALIASES = {
    "coding": "coder",
}

_INTENT_PHRASES = {
    "tutoring": (
        "derive", "derivative", "explain", "learn", "teach", "step by step",
        "walk me through", "show me how",
    ),
    "writing": (
        "write", "draft", "revise", "edit", "rewrite", "proofread",
        "compose",
    ),
    "research": (
        "research", "summarize", "analyze", "sources", "evidence", "cite",
        "investigate", "literature review", "search the web",
    ),
    "coding": (
        "code", "coder", "coder mode", "coding", "debug", "debugging",
        "repo", "repository", "patch", "aider", "worker",
        "dry-run validation", "traceback", "pytest", "typescript",
        "python file",
    ),
}

_HIGH_STAKES_MARKERS = {
    "medical", "diagnosis", "medication", "dosage", "legal", "lawsuit",
    "contract", "financial", "investment", "security", "credential",
    "self-harm", "suicide", "emergency", "weapon", "explosive",
}

_NOVELTY_MARKERS = {
    "novel", "new architecture", "invent", "unprecedented", "hypothesis",
    "experimental", "unknown", "open question", "original approach",
}


def _phrase_present(text: str, phrase: str) -> bool:
    """Match phrases and whole words without treating substrings as intent."""
    if " " in phrase or "-" in phrase:
        return phrase in text
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def _request_features(message: str, scores: Dict[str, int]) -> Dict[str, Any]:
    """Return bounded, content-free features used by the Governor."""
    lowered = message.casefold()
    words = re.findall(r"[\w'-]+", lowered)
    nonzero = sorted((score for score in scores.values() if score), reverse=True)
    top = nonzero[0] if nonzero else 0
    second = nonzero[1] if len(nonzero) > 1 else 0
    competing_intents = sum(score > 0 for score in scores.values())
    pronoun_only_target = bool(
        re.search(r"\b(this|that|it|them|these|those)\b", lowered)
        and len(words) <= 8
        and not any(score >= 2 for score in scores.values())
    )
    ambiguity = 0.05
    if competing_intents >= 2:
        ambiguity += 0.30
    if top and second and top - second <= 1:
        ambiguity += 0.30
    if pronoun_only_target:
        ambiguity += 0.35
    if message.count("?") > 1:
        ambiguity += 0.10

    clause_markers = len(re.findall(r"\b(and then|then|also|while|but|however|plus)\b", lowered))
    numbered_steps = len(re.findall(r"(?:^|\n)\s*(?:\d+[.)]|[-*])\s+", message))
    sentence_count = len([item for item in re.split(r"[.!?]+", message) if item.strip()])
    subproblem_count = max(
        1,
        min(12, sentence_count + clause_markers + numbered_steps),
    )
    complexity = min(
        1.0,
        0.08
        + min(0.46, len(words) / 220)
        + min(0.24, max(0, subproblem_count - 1) * 0.06)
        + (0.14 if any(marker in lowered for marker in ("tradeoff", "architecture", "benchmark", "prove", "audit")) else 0.0),
    )
    novelty = min(
        1.0,
        0.12
        + min(0.32, len(set(words)) / 180)
        + (0.50 if any(marker in lowered for marker in _NOVELTY_MARKERS) else 0.0),
    )
    stakes = (
        "high"
        if any(_phrase_present(lowered, marker) for marker in _HIGH_STAKES_MARKERS)
        else "ordinary"
    )
    return {
        "ambiguity_score": round(min(1.0, ambiguity), 4),
        "complexity_score": round(complexity, 4),
        "novelty_score": round(novelty, 4),
        "subproblem_count": subproblem_count,
        "stakes": stakes,
        "competing_intent_count": competing_intents,
    }


def _normalized_session_mode(session_state: Any = None) -> str:
    """
    Preserve explicit UI/session mode selection when it is one of the known
    governed chamber modes.

    Intent classification may still choose a mode when no explicit session mode
    is present, but it should not silently collapse Coder/Researcher/etc. back
    to default after the user selected a mode chip.
    """
    raw_mode = str(getattr(session_state, "active_mode", "") or "").strip().lower()
    if not raw_mode:
        return ""

    normalized = _SESSION_MODE_ALIASES.get(raw_mode, raw_mode)

    # "default" means classifier/auto mode in the runtime scaffold. Preserve
    # explicit specialized modes such as tutor, researcher, writer, and coder,
    # but do not let the default session value suppress intent-based routing.
    if normalized == "default":
        return ""

    if normalized in _EXPLICIT_SESSION_MODES:
        return normalized

    return ""


def classify_intent(message: str) -> Dict[str, Any]:
    """Classify intent and emit deterministic Governor task features.

    All scores are heuristics, deliberately inspectable, and bounded to
    ``[0, 1]``.  They describe uncertainty and effort; they never authorize a
    tool, network request, mutation, or private-memory access.
    """
    lowered = str(message or "").casefold()
    scores = {
        intent: sum(_phrase_present(lowered, phrase) for phrase in phrases)
        for intent, phrases in _INTENT_PHRASES.items()
    }
    # Preserve established routing priority for equal scores while allowing a
    # stronger multi-signal domain to win over one incidental keyword.
    priority = {"tutoring": 4, "writing": 3, "research": 2, "coding": 1}
    primary = max(scores, key=lambda item: (scores[item], priority[item]))
    if scores[primary] == 0:
        primary = "conversation"

    ranked = sorted(scores.values(), reverse=True)
    top = ranked[0] if ranked else 0
    second = ranked[1] if len(ranked) > 1 else 0
    confidence = (
        0.68
        if primary == "conversation"
        else min(0.96, 0.58 + top * 0.12 + max(0, top - second) * 0.08)
    )
    features = _request_features(message, scores)
    if features["ambiguity_score"] >= 0.65:
        confidence = min(confidence, 0.55)
    return {
        "primary": primary,
        "confidence": round(confidence, 4),
        "note": "Deterministic inspectable intent and effort feature classifier.",
        "classifier_version": "deterministic-request-features-v1",
        "intent_scores": scores,
        **features,
        "authority_granted": False,
        "content_free_features": True,
    }


def choose_mode(intent: Dict[str, Any], session_state: Any = None) -> str:
    """
    Choose an operating mode from the classified intent.

    Explicit chamber/session mode wins when it is one of the known governed
    modes. This preserves UI mode chips such as Researcher, Writer, Tutor, and
    Coder instead of silently collapsing them back to default based on a simple
    keyword classifier.
    """
    explicit_mode = _normalized_session_mode(session_state)
    if explicit_mode:
        return explicit_mode

    primary = intent.get("primary", "conversation")

    if primary == "tutoring":
        return "tutor"
    if primary == "research":
        return "researcher"
    if primary == "writing":
        return "writer"
    if primary in {"coding", "debugging"}:
        return "coder"

    return "default"


if __name__ == "__main__":
    demo_intent = classify_intent("Can you explain derivatives step by step?")
    print(demo_intent)
    print(choose_mode(demo_intent))
