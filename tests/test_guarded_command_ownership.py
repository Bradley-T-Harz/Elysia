"""External qualification must own children which create separate sessions."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("parent_delay", [0.1, 20])
def test_guard_reaps_detached_descendant_after_exit_or_deadline(tmp_path, parent_delay):
    root = Path(__file__).resolve().parents[1]
    receipt_dir = tmp_path / "receipt"
    pidfile = tmp_path / "child_pid"
    child = (
        "import subprocess,sys,time;from pathlib import Path;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'],start_new_session=True);"
        f"Path({str(pidfile)!r}).write_text(str(p.pid));time.sleep({parent_delay})"
    )
    # Controlled telemetry is confined to this negative test. No real hot load.
    bootstrap = (
        "import time;from scripts import run_guarded_command as s;"
        "from app.cognition.resource_guard import ResourceSample;"
        "s.sample_resources=lambda:ResourceSample(time.monotonic(),60,50,32000);"
        "raise SystemExit(s.main())"
    )
    result = subprocess.run([sys.executable, "-c", bootstrap, "--receipt-dir", str(receipt_dir),
                             "--timeout", "1", "--", sys.executable, "-c", child],
                            cwd=root, capture_output=True, text=True, timeout=8)
    assert result.returncode == (0 if parent_delay < 1 else 125), result.stderr
    receipt = json.loads((receipt_dir / "receipt.json").read_text())
    pid = int(pidfile.read_text())
    assert pid in receipt["killed_owned_descendants"]
    assert receipt["remaining_owned_descendants"] == []
    assert receipt["owned_leader_reaped"]
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
