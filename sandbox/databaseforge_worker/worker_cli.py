"""CLI for DatabaseForge's two fixed read-only operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

try:
    from sandbox.databaseforge_worker.worker import DatabaseWorkerError, metadata, snapshot_schema
except ModuleNotFoundError:
    from worker import DatabaseWorkerError, metadata, snapshot_schema


def main() -> int:
    parser = argparse.ArgumentParser(prog="databaseforge-worker")
    parser.add_argument("--operation", choices=("metadata", "snapshot_schema"), required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--snapshot")
    parser.add_argument("--engine", choices=("sqlite", "duckdb", "unknown"), default="unknown")
    parser.add_argument("--limits-json", required=True)
    args = parser.parse_args()
    try:
        limits = {key: max(1, int(value)) for key, value in json.loads(args.limits_json).items()}
        if args.operation == "metadata":
            result = metadata(Path(args.source), max_input_bytes=limits["max_input_bytes"])
        else:
            if not args.snapshot:
                raise DatabaseWorkerError("snapshot_target_required")
            result = snapshot_schema(Path(args.source), Path(args.snapshot), engine=args.engine, limits=limits)
    except (DatabaseWorkerError, KeyError, TypeError, ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc) or type(exc).__name__}, separators=(",", ":")))
        return 2
    except Exception as exc:
        print(json.dumps({"status": "blocked", "reason": f"database_worker_{type(exc).__name__}"}, separators=(",", ":")))
        return 2
    print(json.dumps({"status": "completed", **result}, separators=(",", ":"), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
