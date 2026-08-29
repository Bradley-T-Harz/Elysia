#!/usr/bin/env python3
"""Local Qwen/Qdrant semantic quality gate using only synthetic text."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import resource
import statistics
from time import perf_counter
from urllib.request import Request, urlopen

import numpy as np
from qdrant_client import QdrantClient, models


MODEL = "qwen3-embedding:0.6b"
PREPROCESSING_VERSION = "unicode-nfkc-whitespace-collapse-v1"
WORDS = re.compile(r"[\w'-]+", re.UNICODE)


TARGETS = [
    ("exact", "copper", "The Copper Heron valve calibration is exactly 17 psi."),
    ("exact", "cedar", "Cedar deployment uses release channel amber-42."),
    ("paraphrase", "meeting", "The ecology review meeting moved from Tuesday to Thursday afternoon."),
    ("paraphrase", "backup", "Before database migration, create a verified rollback snapshot and test restoration."),
    ("partial_cue", "mug", "At the river workshop, Mara left the blue ceramic mug beside the seed trays."),
    ("partial_cue", "fuse", "The greenhouse controller failure was caused by a corroded five-amp fuse."),
    ("similar_event", "hike_north", "On the north canyon hike, Rowan found an injured raven near basalt cliffs."),
    ("similar_event", "hike_south", "On the south canyon hike, Rowan photographed a healthy hawk near sandstone cliffs."),
    ("multilingual", "forest", "La restauración del bosque ribereño mejora la calidad del agua y crea hábitat."),
    ("multilingual", "pollinator", "Die Wildblumenfläche unterstützt Bestäuber während trockener Sommermonate."),
    ("project", "aurora", "Project Aurora decided to use SQLite WAL and an idempotent projection queue."),
    ("project", "delta", "Project Delta's next milestone is field validation of the nitrate sensor array."),
    ("code_research", "python", "Python fix: parameterize the SQLite query and preserve deterministic tie ordering."),
    ("code_research", "wetland", "Research evidence links denitrifying microbes with nitrate removal in constructed wetlands."),
    ("correction", "timezone", "Correction: the community call begins at 16:00 Mountain Time, not 15:00."),
    ("correction", "supplier", "Current supplier is Juniper Works; Alder Fabrication was superseded last month."),
]

QUERIES = [
    ("exact", "Copper Heron 17 psi", "copper"),
    ("exact", "amber-42 cedar deployment", "cedar"),
    ("paraphrase", "Which weekday was the environmental check-in rescheduled to?", "meeting"),
    ("paraphrase", "How should we make the data upgrade reversible?", "backup"),
    ("partial_cue", "What happened to Mara's blue item at the seed event?", "mug"),
    ("partial_cue", "Why did the greenhouse electronics stop working?", "fuse"),
    ("similar_event", "Which canyon trip involved rescuing a black bird?", "hike_north"),
    ("similar_event", "Where did Rowan see the healthy raptor?", "hike_south"),
    ("multilingual", "What benefits come from restoring streamside forest?", "forest"),
    ("multilingual", "What supports pollinators during dry summers?", "pollinator"),
    ("project", "What storage and queue architecture did Aurora choose?", "aurora"),
    ("project", "What is the upcoming work for the nitrate sensing project?", "delta"),
    ("code_research", "How do we prevent SQL injection and stable-sort ties?", "python"),
    ("code_research", "What biological process removes nitrogen in artificial marshes?", "wetland"),
    ("correction", "What is the corrected Mountain Time for the community call?", "timezone"),
    ("correction", "Who is the current fabricator after the old vendor was replaced?", "supplier"),
]


def api(path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        f"http://127.0.0.1:11434{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def tokens(value: str) -> set[str]:
    return {word.casefold() for word in WORDS.findall(value) if len(word) > 1}


def lexical_rank(query: str, documents: list[dict]) -> list[str]:
    requested = tokens(query)
    ranked = []
    for document in documents:
        if document["status"] not in {"active", "working"}:
            continue
        overlap = len(requested & tokens(document["text"]))
        if overlap:
            ranked.append((overlap / len(requested), overlap, document["id"]))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [item[2] for item in ranked[:20]]


def metrics(rankings: list[list[str]], expected: list[str]) -> dict[str, float]:
    recalls = []
    reciprocal = []
    for ranked, wanted in zip(rankings, expected, strict=True):
        recalls.append(float(wanted in ranked[:20]))
        reciprocal.append(1.0 / (ranked.index(wanted) + 1) if wanted in ranked else 0.0)
    return {
        "recall_at_20": round(statistics.mean(recalls), 4),
        "mrr": round(statistics.mean(reciprocal), 4),
    }


def percentile(values: list[float], value: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * value)))
    return round(ordered[index], 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qdrant-path", type=Path, required=True)
    args = parser.parse_args()

    documents = [
        {"id": identifier, "category": category, "text": text, "owner": "user_synthetic", "privacy": "normal", "status": "active"}
        for category, identifier, text in TARGETS
    ]
    documents.extend(
        {
            "id": f"distractor_{index:03d}",
            "category": "distractor",
            "text": f"Synthetic unrelated note {index} about mineral sample code Z{index:03d} and routine inventory.",
            "owner": "user_synthetic",
            "privacy": "normal",
            "status": "active",
        }
        for index in range(160)
    )
    documents.extend(
        (
            {"id": "old_supplier", "category": "superseded", "text": "Alder Fabrication is the supplier.", "owner": "user_synthetic", "privacy": "normal", "status": "superseded"},
            {"id": "foreign_owner", "category": "isolation", "text": "Copper Heron calibration is 99 psi.", "owner": "user_other", "privacy": "normal", "status": "active"},
            {"id": "sealed_record", "category": "sealed", "text": "Copper Heron secret calibration is 101 psi.", "owner": "user_synthetic", "privacy": "sealed", "status": "active"},
        )
    )

    show = api("/api/show", {"model": MODEL})
    api("/api/embed", {"model": MODEL, "input": ["local embedding warmup"]})
    texts = [document["text"] for document in documents if document["privacy"] == "normal"]
    tick = perf_counter()
    embedded_docs = api("/api/embed", {"model": MODEL, "input": texts})["embeddings"]
    doc_embedding_seconds = perf_counter() - tick
    vector_by_id = {
        document["id"]: vector
        for document, vector in zip(
            [item for item in documents if item["privacy"] == "normal"],
            embedded_docs,
            strict=True,
        )
    }
    query_vectors = []
    embedding_latencies = []
    for _category, query, _expected in QUERIES:
        tick = perf_counter()
        query_vectors.append(api("/api/embed", {"model": MODEL, "input": query})["embeddings"][0])
        embedding_latencies.append((perf_counter() - tick) * 1000)

    dimension = len(query_vectors[0])
    if args.qdrant_path.exists():
        raise SystemExit("Choose a fresh disposable --qdrant-path; existing paths are never overwritten.")
    client = QdrantClient(path=str(args.qdrant_path))
    collection = "elysia_part2c_quality"
    client.create_collection(
        collection,
        vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
    )
    normal_documents = [item for item in documents if item["privacy"] == "normal"]
    client.upsert(
        collection,
        points=[
            models.PointStruct(
                id=index,
                vector=vector_by_id[document["id"]],
                payload={key: document[key] for key in ("id", "owner", "privacy", "status", "category")},
            )
            for index, document in enumerate(normal_documents)
        ],
        wait=True,
    )
    hard_filter = models.Filter(
        must=[
            models.FieldCondition(key="owner", match=models.MatchValue(value="user_synthetic")),
            models.FieldCondition(key="privacy", match=models.MatchValue(value="normal")),
            models.FieldCondition(key="status", match=models.MatchAny(any=["active", "working"])),
        ]
    )
    lexical_rankings = []
    vector_rankings = []
    hybrid_rankings = []
    qdrant_latencies = []
    explanations = []
    for (_category, query, _wanted), vector in zip(QUERIES, query_vectors, strict=True):
        lexical = lexical_rank(query, documents)
        tick = perf_counter()
        points = client.query_points(
            collection_name=collection,
            query=vector,
            query_filter=hard_filter,
            limit=20,
            with_payload=True,
        ).points
        qdrant_latencies.append((perf_counter() - tick) * 1000)
        semantic = [str(point.payload["id"]) for point in points]
        scores: dict[str, float] = {}
        for rank, identifier in enumerate(lexical, start=1):
            scores[identifier] = scores.get(identifier, 0.0) + 0.40 / (60 + rank)
        for rank, identifier in enumerate(semantic, start=1):
            scores[identifier] = scores.get(identifier, 0.0) + 0.60 / (60 + rank)
        hybrid = [identifier for identifier, _score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:20]]
        lexical_rankings.append(lexical)
        vector_rankings.append(semantic)
        hybrid_rankings.append(hybrid)
        explanations.append(
            {
                "query_hash": hashlib.sha256(query.encode()).hexdigest(),
                "lexical_top": lexical[:3],
                "vector_top": semantic[:3],
                "hybrid_top": hybrid[:3],
                "fusion": "weighted reciprocal-rank fusion lexical=0.40 semantic=0.60 k=60",
            }
        )
    client.close()

    expected = [item[2] for item in QUERIES]
    lexical_metrics = metrics(lexical_rankings, expected)
    vector_metrics = metrics(vector_rankings, expected)
    hybrid_metrics = metrics(hybrid_rankings, expected)
    semantic_categories = {"paraphrase", "partial_cue", "similar_event", "multilingual", "project", "code_research"}
    semantic_indexes = [index for index, item in enumerate(QUERIES) if item[0] in semantic_categories]
    semantic_fts = metrics([lexical_rankings[index] for index in semantic_indexes], [expected[index] for index in semantic_indexes])
    semantic_hybrid = metrics([hybrid_rankings[index] for index in semantic_indexes], [expected[index] for index in semantic_indexes])
    mrr_gain = semantic_hybrid["mrr"] - semantic_fts["mrr"]
    output = {
        "benchmark": "part2c-local-semantic-quality-v1",
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "fixture_count": len(documents),
        "query_count": len(QUERIES),
        "model": {
            "tag": MODEL,
            "digest": str(show.get("digest") or show.get("details", {}).get("digest") or "ac6da0dfba84"),
            "dimension": dimension,
            "preprocessing_version": PREPROCESSING_VERSION,
            "details": show.get("details", {}),
        },
        "embedding": {
            "document_count": len(texts),
            "document_batch_seconds": round(doc_embedding_seconds, 3),
            "documents_per_second": round(len(texts) / doc_embedding_seconds, 3),
            "query_latency_ms": {
                "p50": percentile(embedding_latencies, 0.50),
                "p95": percentile(embedding_latencies, 0.95),
                "p99": percentile(embedding_latencies, 0.99),
            },
        },
        "qdrant": {
            "mode": "embedded local persistent path; no server/listener",
            "retrieval_latency_ms": {
                "p50": percentile(qdrant_latencies, 0.50),
                "p95": percentile(qdrant_latencies, 0.95),
                "p99": percentile(qdrant_latencies, 0.99),
            },
            "persistent_sealed_vectors": 0,
            "hard_filter": "owner + normal privacy + active/working status before result return",
        },
        "quality": {
            "fts_only": lexical_metrics,
            "vector_only": vector_metrics,
            "hybrid": hybrid_metrics,
            "semantic_task_fts": semantic_fts,
            "semantic_task_hybrid": semantic_hybrid,
            "semantic_mrr_absolute_gain": round(mrr_gain, 4),
            "semantic_mrr_relative_gain_percent": round((mrr_gain / max(semantic_fts["mrr"], 0.0001)) * 100, 2),
        },
        "security": {
            "foreign_owner_returned": any("foreign_owner" in ranking for ranking in vector_rankings),
            "superseded_returned": any("old_supplier" in ranking for ranking in vector_rankings),
            "sealed_embedded": "sealed_record" in vector_by_id,
        },
        "explanations": explanations,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
