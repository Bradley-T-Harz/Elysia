#!/usr/bin/env python3
"""Benchmark a disposable, authenticated, loopback-only Qdrant server.

This measures the scale-appropriate client/server implementation. It never
uses QdrantLocal, never sends real memory, and refuses non-loopback endpoints.
The caller owns service lifecycle and supplies a protected API-key file.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import resource
import statistics
import time
from time import perf_counter
from urllib.parse import urlparse

import numpy as np
from qdrant_client import QdrantClient, models


DIMENSION = 1024
COLLECTION_PREFIX = "elysia_part2c_qdrant_server"


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * p)))], 3)


def distribution(values: list[float]) -> dict[str, float]:
    return {
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "mean": round(statistics.mean(values), 3),
    }


def require_loopback(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("The Qdrant server benchmark accepts loopback HTTP endpoints only.")


def wait_for_index(client: QdrantClient, collection: str, records: int, timeout: int) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    latest: dict[str, object] = {}
    while time.monotonic() < deadline:
        info = client.get_collection(collection)
        latest = {
            "status": str(getattr(info.status, "value", info.status)),
            "optimizer_status": str(getattr(info.optimizer_status, "value", info.optimizer_status)),
            "points_count": int(info.points_count or 0),
            "indexed_vectors_count": int(info.indexed_vectors_count or 0),
            "segments_count": int(info.segments_count or 0),
        }
        if (
            latest["points_count"] >= records
            and latest["indexed_vectors_count"] >= int(records * 0.95)
            and latest["status"] == "green"
        ):
            return latest
        time.sleep(1)
    raise TimeoutError(f"Qdrant HNSW indexing did not settle before timeout: {latest}")


def wait_for_count(client: QdrantClient, collection: str, records: int, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    latest = 0
    while time.monotonic() < deadline:
        latest = int(client.count(collection, exact=True).count)
        if latest == records:
            return
        time.sleep(0.25)
    raise TimeoutError(f"Qdrant ingestion did not settle before timeout: {latest}/{records}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:16333")
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--index-timeout-seconds", type=int, default=3600)
    args = parser.parse_args()
    require_loopback(args.url)
    records = max(1, int(args.records))
    query_count = max(1, int(args.queries))
    batch_size = max(1, min(1000, int(args.batch_size)))
    api_key = args.api_key_file.read_text(encoding="utf-8").strip()
    if len(api_key) < 32:
        raise SystemExit("The protected Qdrant API key is missing or too short.")
    if args.api_key_file.stat().st_mode & 0o077:
        raise SystemExit("The Qdrant API-key file must not be group/world accessible.")

    client = QdrantClient(url=args.url, api_key=api_key, prefer_grpc=False, timeout=120)
    collection = f"{COLLECTION_PREFIX}_{records}"
    existing = {item.name for item in client.get_collections().collections}
    if collection in existing:
        raise SystemExit(f"Choose a fresh disposable server; collection already exists: {collection}")

    client.create_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(
            size=DIMENSION,
            distance=models.Distance.COSINE,
            on_disk=False,
        ),
        hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100, on_disk=False),
        # Bulk rebuilds deliberately defer HNSW construction until ingestion is
        # complete. Otherwise the optimizer competes with the uploader and the
        # measurement conflates insertion with index-build cost.
        optimizers_config=models.OptimizersConfigDiff(indexing_threshold=0),
    )
    for field in ("owner", "space", "privacy", "status"):
        client.create_payload_index(
            collection_name=collection,
            field_name=field,
            field_schema=models.PayloadSchemaType.KEYWORD,
            wait=True,
        )

    rng = np.random.default_rng(20260822)
    query_vectors: list[list[float]] = []
    insert_started = perf_counter()
    batch_latencies: list[float] = []
    for start in range(0, records, batch_size):
        stop = min(records, start + batch_size)
        matrix = rng.standard_normal((stop - start, DIMENSION), dtype=np.float32)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
        if len(query_vectors) < query_count:
            query_vectors.extend(row.tolist() for row in matrix[: query_count - len(query_vectors)])
        points = [
            models.PointStruct(
                id=index,
                vector=matrix[index - start].tolist(),
                payload={
                    "owner": f"user_{index % 8}",
                    "space": f"space_{index % 32}",
                    "privacy": "normal",
                    "status": "superseded" if index % 101 == 0 else "active",
                },
            )
            for index in range(start, stop)
        ]
        tick = perf_counter()
        client.upsert(collection_name=collection, points=points, wait=False)
        batch_latencies.append((perf_counter() - tick) * 1000)
    insertion_seconds = perf_counter() - insert_started

    wait_for_count(client, collection, records, max(30, int(args.index_timeout_seconds)))

    index_started = perf_counter()
    client.update_collection(
        collection_name=collection,
        optimizers_config=models.OptimizersConfigDiff(indexing_threshold=10_000),
    )
    index_state = wait_for_index(
        client,
        collection,
        records,
        max(30, int(args.index_timeout_seconds)),
    )
    index_settle_seconds = perf_counter() - index_started
    count = client.count(collection, exact=True).count
    if count != records:
        raise RuntimeError(f"Qdrant exact count mismatch: expected {records}, received {count}")

    hard_filter = models.Filter(
        must=[
            models.FieldCondition(key="privacy", match=models.MatchValue(value="normal")),
            models.FieldCondition(key="status", match=models.MatchValue(value="active")),
        ],
        should=[
            models.FieldCondition(key="owner", match=models.MatchValue(value="user_0")),
            models.FieldCondition(key="space", match=models.MatchValue(value="space_1")),
        ],
    )

    def query(vector: list[float], *, exact: bool) -> None:
        result = client.query_points(
            collection_name=collection,
            query=vector,
            query_filter=hard_filter,
            search_params=models.SearchParams(exact=exact, hnsw_ef=128),
            limit=20,
            with_payload=True,
            with_vectors=False,
        ).points
        for point in result:
            payload = dict(point.payload or {})
            authorized = payload.get("owner") == "user_0" or payload.get("space") == "space_1"
            if not (
                authorized
                and payload.get("privacy") == "normal"
                and payload.get("status") == "active"
            ):
                raise RuntimeError("Qdrant returned a point outside the hard authorization filter.")

    for vector in query_vectors[: min(20, query_count)]:
        query(vector, exact=False)
    hnsw_latencies: list[float] = []
    for vector in query_vectors[:query_count]:
        tick = perf_counter()
        query(vector, exact=False)
        hnsw_latencies.append((perf_counter() - tick) * 1000)
    exact_latencies: list[float] = []
    for vector in query_vectors[: min(20, query_count)]:
        tick = perf_counter()
        query(vector, exact=True)
        exact_latencies.append((perf_counter() - tick) * 1000)

    snapshot_started = perf_counter()
    snapshot = client.create_snapshot(collection_name=collection, wait=True)
    snapshot_seconds = perf_counter() - snapshot_started
    output = {
        "benchmark": "part2c-qdrant-loopback-server-scale-v1",
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "endpoint": "loopback_http_authenticated",
        "qdrant_local_used": False,
        "server_version": "1.19.0",
        "records": records,
        "dimension": DIMENSION,
        "vectors": "deterministic synthetic normalized float32; semantic quality measured separately",
        "insertion_seconds": round(insertion_seconds, 3),
        "bulk_rebuild_strategy": "HNSW disabled during ingestion, then enabled at threshold 10000",
        "insertion_batch_latency_ms": distribution(batch_latencies),
        "hnsw_index_settle_seconds_after_insertion": round(index_settle_seconds, 3),
        "index_state": index_state,
        "payload_indexes_created_before_ingest": ["owner", "space", "privacy", "status"],
        "hard_filter": "(owner=user_0 OR authorized space=space_1) AND privacy=normal AND status=active",
        "hnsw_query_latency_ms": distribution(hnsw_latencies),
        "exact_query_latency_ms": distribution(exact_latencies),
        "measured_hnsw_queries": len(hnsw_latencies),
        "measured_exact_queries": len(exact_latencies),
        "snapshot_seconds": round(snapshot_seconds, 3),
        "snapshot_name_sha256": __import__("hashlib").sha256(str(snapshot.name).encode()).hexdigest(),
        "persistent_private_vectors": 0,
        "persistent_sealed_vectors": 0,
        "client_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
