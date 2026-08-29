"""Release entry point for the self-contained Elysia Core runtime.

The packaged command deliberately exposes only the fixed local API launcher,
the non-repairing doctor, a bounded local Codev VSIX installer, and version
truth.  It never accepts an arbitrary module, Python expression, or shell
command.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence


VERSION = "1.0.0"


def _enter_packaged_resource_root() -> None:
    """Resolve tracked configuration from the PyInstaller payload only."""
    if not bool(getattr(sys, "frozen", False)):
        return
    resource_root = Path(str(getattr(sys, "_MEIPASS", "")))
    if not resource_root.is_absolute() or not resource_root.is_dir():
        raise RuntimeError("The packaged Elysia resource root is unavailable.")
    os.chdir(resource_root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elysia",
        description="Elysia Core packaged runtime and non-repairing diagnostics.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start the governed loopback API.")
    serve.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "::1"))
    serve.add_argument("--port", default=8000, type=int)
    serve.add_argument("--mode", default="packaged", choices=("packaged",))

    doctor = subparsers.add_parser(
        "doctor",
        help="Inspect readiness without installing, repairing, or starting services.",
    )
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--probe-local-services", action="store_true")
    doctor.add_argument("--record", action="store_true")
    doctor.add_argument("--api-port", default=8000, type=int)

    codev_install = subparsers.add_parser(
        "codev-install",
        help="Validate and install one reviewed local Codev VSIX.",
    )
    codev_install.add_argument("--vsix", required=True)
    codev_install.add_argument("--editor")
    codev_install.add_argument("--select-profile", action="store_true")

    lifecycle = subparsers.add_parser(
        "lifecycle",
        help="As Local Admin, preview or approve one exact verified lifecycle operation; never auto-update.",
    )
    lifecycle_subparsers = lifecycle.add_subparsers(dest="lifecycle_command", required=True)
    lifecycle_subparsers.add_parser("status", help="Show content-free lifecycle state.")
    lifecycle_preview = lifecycle_subparsers.add_parser(
        "preview", help="As authenticated Local Admin, create a non-mutating exact lifecycle preview."
    )
    lifecycle_preview.add_argument(
        "operation", choices=(
            "update", "repair", "rollback", "uninstall_preserve",
            "export_then_remove", "purge_local_data",
        )
    )
    lifecycle_preview.add_argument("--artifact")
    lifecycle_preview.add_argument("--manifest")
    lifecycle_preview.add_argument("--signature")
    lifecycle_preview.add_argument("--target-release-id")
    lifecycle_preview.add_argument("--export-path")
    lifecycle_preview.add_argument("--destructive-confirmation")
    lifecycle_apply = lifecycle_subparsers.add_parser(
        "apply", help="As the initiating Local Admin, explicitly approve one exact unexpired preview."
    )
    lifecycle_apply.add_argument("--preview-id", required=True)
    lifecycle_apply.add_argument("--approval-token", required=True)
    lifecycle_apply.add_argument("--approve", action="store_true")

    emergency = subparsers.add_parser(
        "emergency-stop",
        help="Request the authenticated system-wide emergency posture over loopback.",
    )
    emergency.add_argument("--api-port", default=8000, type=int)
    emergency.add_argument("--reason", default="Operator CLI emergency stop")

    subparsers.add_parser("version", help="Print the packaged component version.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _enter_packaged_resource_root()

    if args.command == "serve":
        from app.cli.runtime import main as runtime_main

        return runtime_main(
            [
                "serve",
                "--host",
                args.host,
                "--port",
                str(args.port),
                "--mode",
                "packaged",
            ]
        )
    if args.command == "doctor":
        from app.cli.doctor import main as doctor_main

        doctor_args: list[str] = ["--api-port", str(args.api_port)]
        if args.json:
            doctor_args.append("--json")
        if args.probe_local_services:
            doctor_args.append("--probe-local-services")
        if args.record:
            doctor_args.append("--record")
        return doctor_main(doctor_args)
    if args.command == "version":
        print(f"Elysia {VERSION}")
        return 0
    if args.command == "codev-install":
        from app.install.codev_installer import CodevInstallError, install_codev_vsix

        try:
            result = install_codev_vsix(
                args.vsix,
                editor=args.editor,
                select_profile=args.select_profile,
            )
        except CodevInstallError as exc:
            print(f"Codev installation refused: {exc}", file=sys.stderr)
            return 2
        print("Codev local installation completed.")
        print(json.dumps(result.public_summary(), sort_keys=True))
        print("No download, publication, shell, package-manager, Git, or repository authority was granted.")
        return 0
    if args.command == "lifecycle":
        from app.install.lifecycle_service import (
            LifecycleApplyRequest,
            LifecycleError,
            LifecyclePreviewRequest,
            LifecycleService,
        )

        service = LifecycleService()
        try:
            if args.lifecycle_command == "status":
                result = service.state()
            elif args.lifecycle_command == "preview":
                result = service.preview(LifecyclePreviewRequest(
                    operation=args.operation,
                    artifact_path=args.artifact,
                    manifest_path=args.manifest,
                    signature_path=args.signature,
                    target_release_id=args.target_release_id,
                    export_path=args.export_path,
                    destructive_confirmation=args.destructive_confirmation,
                ))
            else:
                result = service.apply(LifecycleApplyRequest(
                    preview_id=args.preview_id,
                    approval_token=args.approval_token,
                    operator_approved=args.approve,
                ))
        except (LifecycleError, ValueError) as exc:
            print(f"Lifecycle operation refused: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "emergency-stop":
        from urllib import error as urllib_error
        from urllib import request as urllib_request

        from app.install.paths import resolve_elysia_paths

        if not (1024 <= args.api_port <= 65535):
            print("Emergency stop refused: API port is outside the local bounded range.", file=sys.stderr)
            return 2
        credential_path = resolve_elysia_paths().auth_dir / "local-api.credential"
        try:
            credential = credential_path.read_text(encoding="utf-8").strip()
        except OSError:
            credential = ""
        headers = {"Content-Type": "application/json"}
        if credential:
            headers["Authorization"] = f"Bearer {credential}"
        request = urllib_request.Request(
            f"http://127.0.0.1:{args.api_port}/emergency/stop",
            data=json.dumps({"reason": args.reason}).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, urllib_error.URLError) as exc:
            print(
                f"Emergency API did not acknowledge the stop ({type(exc).__name__}). "
                "Use the Desktop emergency shortcut for owned-sidecar hard-stop fallback.",
                file=sys.stderr,
            )
            return 3
        active = bool((payload.get("data") or {}).get("active"))
        print(json.dumps({"emergency_stop_active": active, "credential_exposed": False}))
        return 0 if active else 4
    raise RuntimeError("Unsupported packaged Elysia command.")


if __name__ == "__main__":
    raise SystemExit(main())
