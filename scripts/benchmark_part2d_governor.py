#!/usr/bin/env python3
"""Reproducible synthetic Governor promotion gate; never an authority path."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from statistics import median
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cognition.governor import GEARS, GovernorInput, decide_cognition


TRAINING = {
    "reflex": ["hello", "thanks", "good morning", "who are you"],
    "quick": ["name four seasons?", "define estuary?", "summarize this sentence?", "what is photosynthesis?"],
    "standard": ["explain a wetland carbon budget with an example", "draft a clear project update for the restoration team", "teach derivatives step by step with one example", "compare two ordinary local planning options"],
    "deep": ["analyze a complex watershed plan with uncertainty constraints and dependencies", "reason through a multi-stage project with several conflicting requirements", "plan a careful architecture across storage routing and user experience", "analyze ambiguity novelty and five interacting subproblems"],
    "deliberative": ["audit and verify a legal privacy threat model", "compare security tradeoffs and prove the approval boundary", "review medical risk evidence with uncertainty and independent verification", "audit governance ownership contradictions and safety policy"],
    "research_engineering": ["research current CUDA architecture with primary sources", "debug and benchmark the repository database migration", "investigate sources and engineer a reproducible package", "research then verify a GPU service architecture"],
}

EVALUATION = {
    "reflex": ["hi", "thank you", "who are you", "good evening"],
    "quick": [
        "Which month follows April?", "What does riparian mean?",
        "List three primary colors?", "Give a one-sentence definition of habitat?",
    ],
    "standard": [
        "Explain how a small native plant garden supports pollinators, including one concrete example and a concise caveat for a community volunteer team.",
        "Draft an ordinary progress note that states the completed survey, the next field visit, the known scheduling constraint, and one question for collaborators.",
        "Teach the difference between weather and climate with a practical example, a short comparison, and an age-appropriate recap for a new learner.",
        "Describe a basic water-quality monitoring workflow from sample labeling through a simple result review, with assumptions and one everyday example.",
    ],
    "deep": [
        "Analyze and plan a multi-stage habitat survey whose teams, seasonal windows, sensor limits, and uncertain access constraints interact across five subproblems.",
        "Reason through a complex restoration schedule with ambiguity, dependencies, uncertain funding, several sites, and competing measurement priorities.",
        "Plan a careful architecture for coordinating storage, local inference, user experience, failure recovery, and five interacting subsystems.",
        "Analyze a complex field program with uncertain observations, multiple dependent phases, scarce equipment, and several plausible interpretations.",
    ],
    "deliberative": [
        "Audit the privacy threat model, verify its approval boundary, search for contradictions, and compare security counterexamples.",
        "Review a medical-risk evidence summary with uncertainty and independent verification before presenting any bounded conclusion.",
        "Prove whether the ownership policy preserves least privilege, including adversarial cases and a separate verification pass.",
        "Compare legal governance tradeoffs, test counterexamples, and verify that credentials cannot cross the stated security boundary.",
    ],
    "research_engineering": [
        "Research current GPU compatibility from primary sources and produce a reproducible benchmark.",
        "Debug the repository migration, inspect the database, run a bounded benchmark, and verify the package.",
        "Investigate current scientific sources and engineer a reproducible local implementation with provenance.",
        "Research then verify a CUDA service architecture using official documentation and measured tests.",
    ],
}


def rows(source: dict[str, list[str]]) -> list[tuple[str, str]]:
    return [(text, gear) for gear, examples in source.items() for text in examples]


def tokens(text: str) -> list[str]:
    return [part.strip(".,?!:;()[]").casefold() for part in text.split() if part.strip(".,?!:;()[]")]


class NaiveBayesProposal:
    def __init__(self) -> None:
        self.labels: Counter[str] = Counter()
        self.words: dict[str, Counter[str]] = defaultdict(Counter)
        self.totals: Counter[str] = Counter()
        self.vocabulary: set[str] = set()

    def fit(self, rows: list[tuple[str, str]]) -> None:
        for text, label in rows:
            self.labels[label] += 1
            for word in tokens(text):
                self.words[label][word] += 1
                self.totals[label] += 1
                self.vocabulary.add(word)

    def propose(self, text: str) -> str:
        total_labels = sum(self.labels.values())
        scores: dict[str, float] = {}
        for label in GEARS:
            score = math.log((self.labels[label] + 1) / (total_labels + len(GEARS)))
            denominator = self.totals[label] + len(self.vocabulary)
            for word in tokens(text):
                score += math.log((self.words[label][word] + 1) / denominator)
            scores[label] = score
        return max(scores, key=scores.get)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))]


def metrics(expected: list[str], predicted: list[str], latency_us: list[float]) -> dict[str, float | int]:
    indices = {gear: index for index, gear in enumerate(GEARS)}
    return {
        "samples": len(expected),
        "accuracy": round(sum(a == b for a, b in zip(expected, predicted)) / len(expected), 4),
        "missed_escalation_rate": round(sum(indices[b] < indices[a] for a, b in zip(expected, predicted)) / len(expected), 4),
        "unnecessary_escalation_rate": round(sum(indices[b] > indices[a] for a, b in zip(expected, predicted)) / len(expected), 4),
        "latency_us_p50": round(median(latency_us), 3),
        "latency_us_p95": round(percentile(latency_us, 0.95), 3),
        "latency_us_p99": round(percentile(latency_us, 0.99), 3),
    }


def main() -> None:
    train = rows(TRAINING)
    test = rows(EVALUATION)
    expected = [label for _, label in test]
    learned = NaiveBayesProposal()
    learned.fit(train)

    rule_predictions: list[str] = []
    rule_latency: list[float] = []
    learned_predictions: list[str] = []
    learned_latency: list[float] = []
    for index, (text, expected_gear) in enumerate(test):
        start = time.perf_counter_ns()
        decision = decide_cognition(GovernorInput(
            request_id=f"benchmark-rule-{index}", message=text, mode="default",
            intent={"primary": "ordinary"}, autonomy_level=3,
            requested_gear="automatic",
        ))
        rule_latency.append((time.perf_counter_ns() - start) / 1000)
        rule_predictions.append(decision.selected_gear)
        start = time.perf_counter_ns()
        learned_predictions.append(learned.propose(text))
        learned_latency.append((time.perf_counter_ns() - start) / 1000)

    result = {
        "contract": "part2d-governor-candidate-benchmark-v1",
        "fixture_policy": "synthetic_nonprivate",
        "evaluation_split": "lexically_distinct_held_out_synthetic_prompts",
        "representative_elysia_production_labels_available": False,
        "candidate_authority": "proposal_only_never_executes",
        "deterministic": metrics(expected, rule_predictions, rule_latency),
        "interpretable_naive_bayes_candidate": metrics(expected, learned_predictions, learned_latency),
        "promotion_rule": "candidate must materially improve accuracy without missed-escalation, privacy, explainability, drift, or rollback regression",
    }
    deterministic = result["deterministic"]
    candidate = result["interpretable_naive_bayes_candidate"]
    evidence_gate = (
        candidate["accuracy"] > deterministic["accuracy"]
        and candidate["missed_escalation_rate"] <= deterministic["missed_escalation_rate"]
        and result["representative_elysia_production_labels_available"] is True
        and candidate["samples"] >= 1000
    )
    result["decision"] = (
        "promote_candidate" if evidence_gate else "retain_deterministic_production_governor"
    )
    result["candidate_blockers"] = [] if evidence_gate else [
        "no_representative_versioned_elysia_task_labels",
        "synthetic_sample_is_too_small_for_calibration_or_drift_proof",
        "no_rollback_qualified_online_shadow_evaluation",
    ]
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
