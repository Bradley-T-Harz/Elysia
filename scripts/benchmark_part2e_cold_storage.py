#!/usr/bin/env python3
"""Synthetic/nonprivate cold-storage qualification for Part 2E.

The three engines receive the same deterministic metadata and 256-byte payload
shape.  No operator data or live XDG paths are read.  Results distinguish a
storage engine from canonical Memory authority: every tested file is disposable
derived/archive storage only.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import resource
import sqlite3
import statistics
from time import perf_counter
import zlib


OWNERS = 32
QUERIES = 120


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def payload(index: int) -> bytes:
    if index % 10 < 7:
        text = (
            '{"title":"synthetic governed memory","body":"'
            + (f"topic-{index % 4096:04d} wetland continuity provenance " * 12)
            + '"}'
        )
        return text.encode()[:256].ljust(256, b" ")
    chunks = [sha256(f"synthetic-part2e:{index}:{part}".encode()).digest() for part in range(8)]
    return b"".join(chunks)


def row(index: int) -> tuple[object, ...]:
    return (
        f"memory_synthetic_{index:09d}",
        f"owner_{index % OWNERS:02d}",
        "normal" if index % 10 < 7 else "private" if index % 10 < 9 else "sealed",
        "active" if index % 211 else "superseded",
        "cold",
        f"2026-08-{1 + index % 22:02d}T00:00:00Z",
        payload(index),
    )


def measurements(latencies: list[float]) -> dict[str, float]:
    return {
        "p50": percentile(latencies, 0.50),
        "p95": percentile(latencies, 0.95),
        "p99": percentile(latencies, 0.99),
        "mean": round(statistics.mean(latencies), 3),
    }


def sqlite_run(records: int, target: Path, *, codec: str = "zlib") -> dict[str, object]:
    if codec == "zstd":
        import zstandard

        compressor = zstandard.ZstdCompressor(level=9)
        decompressor = zstandard.ZstdDecompressor()
        compress = compressor.compress
        decompress = decompressor.decompress
        codec_version = zstandard.__version__
    else:
        compress = lambda value: zlib.compress(value, 9)
        decompress = zlib.decompress
        codec_version = zlib.ZLIB_VERSION
    conn = sqlite3.connect(target)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.executescript(
        """
        CREATE TABLE cold_objects (
            memory_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, privacy TEXT NOT NULL,
            status TEXT NOT NULL, tier TEXT NOT NULL, updated_at TEXT NOT NULL,
            payload BLOB NOT NULL
        );
        CREATE INDEX idx_cold_filter ON cold_objects(owner_id,status,tier,updated_at);
        """
    )
    started = perf_counter()
    for start in range(0, records, 10_000):
        batch = []
        for index in range(start, min(records, start + 10_000)):
            values = list(row(index))
            compressed = compress(values[-1])
            values[-1] = (
                b"c" + compressed
                if len(compressed) + 32 < len(values[-1])
                else b"r" + values[-1]
            )
            batch.append(tuple(values))
        conn.executemany("INSERT INTO cold_objects VALUES(?,?,?,?,?,?,?)", batch)
        conn.commit()
    write_seconds = perf_counter() - started
    conn.close()

    startup = perf_counter()
    conn = sqlite3.connect(target)
    startup_ms = (perf_counter() - startup) * 1000
    latencies: list[float] = []
    rehydrate: list[float] = []
    for query in range(QUERIES):
        tick = perf_counter()
        rows = conn.execute(
            """
            SELECT memory_id,payload FROM cold_objects
            WHERE owner_id=? AND status='active' AND tier='cold'
            ORDER BY updated_at DESC,memory_id LIMIT 25
            """,
            (f"owner_{query % OWNERS:02d}",),
        ).fetchall()
        latencies.append((perf_counter() - tick) * 1000)
        tick = perf_counter()
        for item in rows:
            decompress(item[1][1:]) if item[1][:1] == b"c" else item[1][1:]
        rehydrate.append((perf_counter() - tick) * 1000)
    shutdown = perf_counter()
    conn.close()
    shutdown_ms = (perf_counter() - shutdown) * 1000
    return {
        "engine_version": sqlite3.sqlite_version,
        "compression": f"{codec}-9",
        "compression_version": codec_version,
        "write_seconds": round(write_seconds, 3),
        "query_ms": measurements(latencies),
        "rehydrate_25_ms": measurements(rehydrate),
        "startup_ms": round(startup_ms, 3),
        "shutdown_ms": round(shutdown_ms, 3),
    }


def duckdb_run(records: int, target: Path) -> dict[str, object]:
    import duckdb

    conn = duckdb.connect(str(target))
    conn.execute(
        """
        CREATE TABLE cold_objects (
            memory_id VARCHAR PRIMARY KEY, owner_id VARCHAR, privacy VARCHAR,
            status VARCHAR, tier VARCHAR, updated_at VARCHAR, payload BLOB
        )
        """
    )
    started = perf_counter()
    incompressible_blob = " || ".join(
        f"from_hex(sha256('synthetic-part2e:' || i::VARCHAR || ':{part}'))"
        for part in range(8)
    )
    blob_expression = (
        "CASE WHEN i % 10 < 7 THEN "
        "encode(rpad('{\"title\":\"synthetic governed memory\",\"body\":\"' || "
        "repeat(printf('topic-%04d wetland continuity provenance ', i % 4096), 12) || '\"}',256,' ')) "
        f"ELSE {incompressible_blob} END"
    )
    conn.execute(
        f"""
        INSERT INTO cold_objects
        SELECT printf('memory_synthetic_%09d', i), printf('owner_%02d', i % {OWNERS}),
               CASE WHEN i % 10 < 7 THEN 'normal' WHEN i % 10 < 9 THEN 'private' ELSE 'sealed' END,
               CASE WHEN i % 211 = 0 THEN 'superseded' ELSE 'active' END,
               'cold', printf('2026-08-%02dT00:00:00Z', 1 + i % 22),
               {blob_expression}
        FROM range(?) rows(i)
        """,
        [records],
    )
    conn.execute("CHECKPOINT")
    write_seconds = perf_counter() - started
    conn.close()

    startup = perf_counter()
    conn = duckdb.connect(str(target), read_only=True)
    startup_ms = (perf_counter() - startup) * 1000
    latencies: list[float] = []
    rehydrate: list[float] = []
    for query in range(QUERIES):
        tick = perf_counter()
        rows = conn.execute(
            """
            SELECT memory_id,payload FROM cold_objects
            WHERE owner_id=? AND status='active' AND tier='cold'
            ORDER BY updated_at DESC,memory_id LIMIT 25
            """,
            [f"owner_{query % OWNERS:02d}"],
        ).fetchall()
        latencies.append((perf_counter() - tick) * 1000)
        tick = perf_counter()
        for item in rows:
            bytes(item[1])
        rehydrate.append((perf_counter() - tick) * 1000)
    shutdown = perf_counter()
    conn.close()
    shutdown_ms = (perf_counter() - shutdown) * 1000
    return {
        "engine_version": duckdb.__version__,
        "write_seconds": round(write_seconds, 3),
        "query_ms": measurements(latencies),
        "rehydrate_25_ms": measurements(rehydrate),
        "startup_ms": round(startup_ms, 3),
        "shutdown_ms": round(shutdown_ms, 3),
    }


def parquet_run(records: int, target: Path) -> dict[str, object]:
    import pyarrow as pa
    import pyarrow.dataset as ds
    import pyarrow.parquet as pq

    schema = pa.schema(
        [
            ("memory_id", pa.string()), ("owner_id", pa.string()),
            ("privacy", pa.string()), ("status", pa.string()),
            ("tier", pa.string()), ("updated_at", pa.string()),
            ("payload", pa.binary()),
        ]
    )
    started = perf_counter()
    writer = pq.ParquetWriter(target, schema, compression="zstd", compression_level=9)
    try:
        for start in range(0, records, 50_000):
            values = [row(index) for index in range(start, min(records, start + 50_000))]
            writer.write_table(pa.Table.from_pylist([dict(zip(schema.names, item)) for item in values], schema=schema))
    finally:
        writer.close()
    write_seconds = perf_counter() - started

    startup = perf_counter()
    dataset = ds.dataset(target, format="parquet")
    startup_ms = (perf_counter() - startup) * 1000
    latencies: list[float] = []
    rehydrate: list[float] = []
    for query in range(QUERIES):
        tick = perf_counter()
        table = dataset.to_table(
            columns=["memory_id", "payload", "updated_at"],
            filter=(ds.field("owner_id") == f"owner_{query % OWNERS:02d}")
            & (ds.field("status") == "active")
            & (ds.field("tier") == "cold"),
        ).sort_by([("updated_at", "descending"), ("memory_id", "ascending")]).slice(0, 25)
        latencies.append((perf_counter() - tick) * 1000)
        tick = perf_counter()
        for item in table.column("payload").to_pylist():
            bytes(item)
        rehydrate.append((perf_counter() - tick) * 1000)
    return {
        "engine_version": pa.__version__,
        "compression": "parquet-zstd-9",
        "write_seconds": round(write_seconds, 3),
        "query_ms": measurements(latencies),
        "rehydrate_25_ms": measurements(rehydrate),
        "startup_ms": round(startup_ms, 3),
        "shutdown_ms": 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--engine", choices=("sqlite-zlib", "sqlite-zstd", "duckdb", "parquet"), required=True
    )
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    args.target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.target.unlink(missing_ok=True)
    if args.engine.startswith("sqlite-"):
        result = sqlite_run(
            max(1, args.records), args.target, codec=args.engine.split("-", 1)[1]
        )
    else:
        runner = {"duckdb": duckdb_run, "parquet": parquet_run}[args.engine]
        result = runner(max(1, args.records), args.target)
    result.update(
        {
            "contract": "part2e-cold-storage-qualification-v1",
            "engine": args.engine,
            "records": args.records,
            "fixture": "deterministic_synthetic_nonprivate_metadata_and_bytes",
            "authorization_filter": "owner+status+tier before payload return",
            "canonical_memory_authority": False,
            "disk_bytes": args.target.stat().st_size,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "queries": QUERIES,
            "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "machine": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "processor": platform.processor(),
                "cpu_count": os.cpu_count(),
            },
        }
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
