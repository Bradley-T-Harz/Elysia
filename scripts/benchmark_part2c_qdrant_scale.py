#!/usr/bin/env python3
"""Qdrant embedded-mode scale measurement with deterministic 1024-D vectors."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import resource
import statistics
from time import perf_counter

import numpy as np
from qdrant_client import QdrantClient, models


DIMENSION = 1024


def percentile(values: list[float], p: float) -> float:
    values = sorted(values)
    return round(values[min(len(values) - 1, int(round((len(values) - 1) * p)))], 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--queries", type=int, default=100)
    args = parser.parse_args()
    if args.path.exists():
        raise SystemExit("Choose a fresh disposable --path; existing paths are never overwritten.")
    records = max(1, args.records)
    rng = np.random.default_rng(20260822)
    client = QdrantClient(path=str(args.path))
    collection = "elysia_part2c_scale"
    client.create_collection(
        collection,
        vectors_config=models.VectorParams(size=DIMENSION, distance=models.Distance.COSINE),
    )
    started = perf_counter()
    batch_size = 500
    query_vectors: list[list[float]] = []
    for start in range(0, records, batch_size):
        stop = min(records, start + batch_size)
        matrix = rng.standard_normal((stop - start, DIMENSION), dtype=np.float32)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
        if len(query_vectors) < args.queries:
            query_vectors.extend(row.tolist() for row in matrix[: args.queries - len(query_vectors)])
        client.upsert(
            collection,
            points=[
                models.PointStruct(
                    id=index,
                    vector=matrix[index - start].tolist(),
                    payload={
                        "owner": f"user_{index % 8}",
                        "space": f"space_{index % 32}",
                        "privacy": "normal",
                        "status": "active" if index % 101 else "superseded",
                    },
                )
                for index in range(start, stop)
            ],
            wait=True,
        )
    build_seconds = perf_counter() - started
    query_filter = models.Filter(
        must=[
            models.FieldCondition(key="owner", match=models.MatchValue(value="user_0")),
            models.FieldCondition(key="privacy", match=models.MatchValue(value="normal")),
            models.FieldCondition(key="status", match=models.MatchValue(value="active")),
        ]
    )
    for vector in query_vectors[:20]:
        client.query_points(collection, query=vector, query_filter=query_filter, limit=20)
    latencies = []
    for vector in query_vectors[: args.queries]:
        tick = perf_counter()
        client.query_points(collection, query=vector, query_filter=query_filter, limit=20)
        latencies.append((perf_counter() - tick) * 1000)
    client.close()
    disk_bytes = sum(path.stat().st_size for path in args.path.rglob("*") if path.is_file())
    print(
        json.dumps(
            {
                "benchmark": "part2c-qdrant-embedded-scale-v1",
                "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "records": records,
                "dimension": DIMENSION,
                "vectors": "deterministic synthetic normalized float32; semantic quality not measured here",
                "mode": "embedded local persistent; no server/listener",
                "build_seconds": round(build_seconds, 3),
                "measured_queries": len(latencies),
                "latency_ms": {
                    "p50": percentile(latencies, 0.50),
                    "p95": percentile(latencies, 0.95),
                    "p99": percentile(latencies, 0.99),
                    "mean": round(statistics.mean(latencies), 3),
                },
                "disk_bytes": disk_bytes,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "hard_filter": "owner + privacy + active lifecycle",
                "sealed_vectors": 0,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
