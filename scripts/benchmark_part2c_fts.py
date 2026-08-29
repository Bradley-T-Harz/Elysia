#!/usr/bin/env python3
"""Synthetic, nonprivate Part 2C FTS5 scale benchmark.

This intentionally benchmarks the derived projection shape rather than
creating canonical Memory records. It never reads operator data.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import platform
import resource
import sqlite3
import statistics
from time import perf_counter


SCHEMA = """
CREATE TABLE memory_fts_meta (
 candidate_id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, space_id TEXT,
 scope TEXT NOT NULL, form TEXT NOT NULL, privacy TEXT NOT NULL,
 status TEXT NOT NULL, project_id TEXT, conversation_id TEXT,
 valid_from TEXT, valid_until TEXT, importance REAL NOT NULL, updated_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE memory_fts USING fts5(
 candidate_id UNINDEXED, title, body, why_stored,
 tokenize='porter unicode61 remove_diacritics 2'
);
CREATE INDEX idx_owner_status ON memory_fts_meta(owner_user_id,status,updated_at DESC);
CREATE INDEX idx_scope_form ON memory_fts_meta(scope,form);
"""

QUERY_TERMS = (
    "wetland nitrate",
    '"copper heron"',
    "project ecology milestone",
    "python sqlite migration",
    "multilingual bosque agua",
    "correction superseded",
    "partial canary",
    "research provenance",
)


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * p))))
    return round(ordered[index], 3)


def match(text: str) -> str:
    if text.startswith('"'):
        return text
    return " OR ".join(f'"{term}"' for term in text.split())


def run(records: int, database: Path, measured_queries: int) -> dict[str, object]:
    if database.exists():
        database.unlink()
    conn = sqlite3.connect(database)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    started = perf_counter()
    now = "2026-08-22T00:00:00Z"
    batch_size = 10_000
    for start in range(0, records, batch_size):
        stop = min(records, start + batch_size)
        meta = []
        fts = []
        for index in range(start, stop):
            owner = f"user_{index % 16:02d}"
            project = f"project_{index % 97:03d}"
            scope = "project" if index % 3 == 0 else "user"
            form = ("episodic", "semantic", "procedural", "corrective")[index % 4]
            status = "superseded" if index % 211 == 0 else "active"
            # Five percent of rows carry a benchmark topic; the remainder use
            # synthetic low-frequency vocabulary. Making every row match a
            # query would measure a pathological stop-word corpus rather than
            # a representative memory projection.
            marker = (
                QUERY_TERMS[(index // 20) % len(QUERY_TERMS)].replace('"', "")
                if index % 20 == 0
                else f"synthetic-topic-{index % 4093:04d}"
            )
            candidate = f"memory_synthetic_{index:09d}"
            meta.append(
                (
                    candidate, owner, None, scope, form, "normal", status,
                    project, f"conversation_{index % 503:04d}", None, None,
                    (index % 100) / 100.0, now,
                )
            )
            fts.append(
                (
                    candidate,
                    f"Synthetic {marker} record {index}",
                    f"Nonprivate benchmark body for {marker}; entity_{index % 1000:04d} outcome_{index % 37:02d}.",
                    "Generated only for Part 2C retrieval scale measurement.",
                )
            )
        conn.executemany("INSERT INTO memory_fts_meta VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", meta)
        conn.executemany("INSERT INTO memory_fts VALUES(?,?,?,?)", fts)
        conn.commit()
    build_seconds = perf_counter() - started

    sql = """
    SELECT m.candidate_id, bm25(memory_fts,0.0,2.0,1.0,0.4) rank
    FROM memory_fts f JOIN memory_fts_meta m ON m.candidate_id=f.candidate_id
    WHERE memory_fts MATCH ? AND m.owner_user_id=? AND m.status IN ('active','working')
      AND (m.valid_from IS NULL OR m.valid_from<=?)
      AND (m.valid_until IS NULL OR m.valid_until>?)
    ORDER BY rank,m.importance DESC,m.updated_at DESC,m.candidate_id
    LIMIT 20
    """
    workload = [
        (
            match(QUERY_TERMS[index % len(QUERY_TERMS)]),
            f"user_{(4 * (index % len(QUERY_TERMS))) % 16:02d}",
            now,
            now,
        )
        for index in range(max(100, measured_queries))
    ]
    for args in workload[:100]:
        conn.execute(sql, args).fetchall()
    latencies: list[float] = []
    nonempty = 0
    for args in workload[:measured_queries]:
        tick = perf_counter()
        rows = conn.execute(sql, args).fetchall()
        latencies.append((perf_counter() - tick) * 1000)
        nonempty += bool(rows)
    conn.close()
    size = sum(
        path.stat().st_size
        for path in (database, Path(str(database) + "-wal"), Path(str(database) + "-shm"))
        if path.exists()
    )
    return {
        "records": records,
        "corpus": "deterministic synthetic nonprivate FTS5 projection rows",
        "query_mix": list(QUERY_TERMS),
        "warmup_queries": 100,
        "measured_queries": measured_queries,
        "nonempty_queries": nonempty,
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "mean": round(statistics.mean(latencies), 3),
        },
        "build_seconds": round(build_seconds, 3),
        "disk_bytes": size,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "target_p95_ms": 50 if records <= 100_000 else 200,
        "target_met": percentile(latencies, 0.95) < (50 if records <= 100_000 else 200),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--queries", type=int, default=500)
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    result = run(max(1, args.records), args.database, max(10, args.queries))
    print(
        json.dumps(
            {
                "benchmark": "part2c-sqlite-fts5-scale-v1",
                "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "machine": {
                    "platform": platform.platform(),
                    "python": platform.python_version(),
                    "logical_cpus": os.cpu_count(),
                },
                **result,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
