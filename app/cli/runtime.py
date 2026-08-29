"""Fixed loopback launcher for the Elysia local API."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elysia-api")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve", help="Start the governed loopback API.")
    serve.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "::1"))
    serve.add_argument("--port", default=8000, type=int)
    serve.add_argument("--mode", default="packaged", choices=("source", "packaged"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not (1024 <= args.port <= 65535):
        raise SystemExit("Port must be between 1024 and 65535.")
    os.environ["ELYSIA_RUNTIME_MODE"] = args.mode
    os.environ["ELYSIA_API_AUTH_MODE"] = (
        "required" if args.mode == "packaged" else "development-disabled"
    )
    if "ELYSIA_DISTRIBUTION_FORM" not in os.environ:
        executable = Path(sys.executable).resolve(strict=False)
        os.environ["ELYSIA_DISTRIBUTION_FORM"] = (
            "source"
            if args.mode == "source"
            else "deb"
            if executable == Path("/usr/bin/elysia")
            else "onefile_core"
        )

    from app.install.local_auth import build_local_api_auth_policy
    from app.install.paths import ensure_elysia_directories, resolve_elysia_paths

    paths = resolve_elysia_paths()
    ensure_elysia_directories(paths)
    auth_policy = build_local_api_auth_policy(paths=paths, initialize=True)
    from app.memory.migration_service import prepare_memory_authority_for_startup

    prepare_memory_authority_for_startup(paths)

    import uvicorn
    from app.api.main import create_app

    uvicorn.run(
        create_app(auth_policy=auth_policy),
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
