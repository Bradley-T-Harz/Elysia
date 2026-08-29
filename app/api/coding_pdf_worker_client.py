"""Bounded client for the separately licensed optional PyMuPDF worker."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKER = Path(__file__).resolve().parents[2] / "workers" / "pdf" / "pymupdf_worker.py"


def run_pdf_worker(request: dict[str, Any], *, timeout_seconds: int = 45) -> dict[str, Any]:
    if not WORKER.is_file():
        raise RuntimeError("optional_pdf_worker_missing")
    environment = {
        "HOME": os.environ.get("HOME", "/nonexistent"),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(WORKER.parents[2]),
        "PYTHONNOUSERSITE": "1",
    }
    result = subprocess.run(
        [sys.executable, str(WORKER)],
        input=json.dumps(request, separators=(",", ":")),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        env=environment,
        shell=False,
        check=False,
    )
    try:
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("optional_pdf_worker_invalid_response") from exc
    except IndexError as exc:
        raise RuntimeError("optional_pdf_worker_invalid_response") from exc
    if result.returncode != 0 or payload.get("status") != "completed":
        raise ValueError(str(payload.get("error") or "optional_pdf_worker_blocked"))
    return payload


__all__ = ("run_pdf_worker",)
