"""Command-line entry point for the non-repairing Elysia install doctor."""

from __future__ import annotations

import argparse
import json
import socket
from typing import Sequence

from app.install.doctor_service import record_doctor_result, run_doctor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elysia-doctor",
        description="Inspect Elysia Core readiness without installing or repairing anything.",
    )
    parser.add_argument("--json", action="store_true", help="Print the sanitized JSON report.")
    parser.add_argument(
        "--probe-local-services",
        action="store_true",
        help="Probe allowlisted loopback providers without loading models or sending prompts.",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Write a sanitized last-run receipt under XDG state.",
    )
    parser.add_argument(
        "--api-port",
        default=8000,
        type=int,
        help="Allowlisted loopback API port to verify (default: 8000).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not (1024 <= args.api_port <= 65535):
        raise SystemExit("API port must be between 1024 and 65535.")
    try:
        with socket.create_connection(("127.0.0.1", args.api_port), timeout=0.3):
            api_reachable = True
    except OSError:
        api_reachable = False
    report = run_doctor(
        api_reachable=api_reachable,
        probe_local_services=args.probe_local_services,
    )
    if args.record:
        record_doctor_result(report)
    payload = report.to_payload()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Elysia doctor: {payload['overall_status']}")
        print(f"Runtime mode: {payload['runtime_mode']}")
        print(f"Active profile: {payload['active_profile_id']}")
        for check in payload["checks"]:
            required = "required" if check["required"] else "optional"
            print(f"- {check['label']}: {check['status']} ({required}) — {check['summary']}")
        print("No packages, models, workers, services, or repairs were started.")
    return 0 if report.core_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
