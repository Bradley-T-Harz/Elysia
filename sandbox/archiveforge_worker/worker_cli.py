"""CLI wrapper for ArchiveForge's inspection-only worker boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

try:
    from sandbox.archiveforge_worker.worker import ExternalListError, list_external_archive
except ModuleNotFoundError:  # Direct script launch in the isolated worker environment.
    from worker import ExternalListError, list_external_archive


def main() -> int:
    parser = argparse.ArgumentParser(prog="archiveforge-worker")
    parser.add_argument("--operation", choices=("list",), required=True)
    parser.add_argument("--archive-type", choices=("7z", "rar"), required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--max-stdout-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--max-stderr-bytes", type=int, default=64 * 1024)
    args = parser.parse_args()
    try:
        result = list_external_archive(
            Path(args.source),
            archive_type=args.archive_type,
            timeout_seconds=max(1, min(args.timeout_seconds, 60)),
            max_stdout_bytes=max(1024, min(args.max_stdout_bytes, 4 * 1024 * 1024)),
            max_stderr_bytes=max(1024, min(args.max_stderr_bytes, 128 * 1024)),
        )
    except (ExternalListError, OSError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": "completed", **result}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
