"""CLI for BinaryForge's one fixed static-inspection operation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

try:
    from sandbox.binaryforge_worker.worker import BinaryWorkerError, inspect_binary
except ModuleNotFoundError:
    from worker import BinaryWorkerError, inspect_binary


def main() -> int:
    parser = argparse.ArgumentParser(prog="binaryforge-worker")
    parser.add_argument("--operation", choices=("inspect",), required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--limits-json", required=True)
    args = parser.parse_args()
    try:
        limits = {key: max(1, int(value)) for key, value in json.loads(args.limits_json).items()}
        result = inspect_binary(Path(args.source), limits=limits)
    except (BinaryWorkerError, KeyError, TypeError, ValueError, OSError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc) or type(exc).__name__}, separators=(",", ":")))
        return 2
    except Exception as exc:
        print(json.dumps({"status": "blocked", "reason": f"binary_worker_{type(exc).__name__}"}, separators=(",", ":")))
        return 2
    print(json.dumps({"status": "completed", **result}, separators=(",", ":"), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
