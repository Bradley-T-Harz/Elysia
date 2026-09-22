"""Operator CLI for serial, disposable qualification commands; never model IR.

Cancels only the new process group. Source tests still need their own negative
fixtures: this outer guard observes real host telemetry and cannot be mocked by
the child. No service, global setting, or existing workload is stopped.
"""
from __future__ import annotations

import argparse
import ctypes
from dataclasses import asdict
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.cognition.resource_guard import ResourceGuard, sample_resources


def descendant_identities(root_pid):
    """Read only PID ancestry/start identity; never inspect other users' argv."""
    processes = {}
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path / "stat").read_text().rsplit(") ", 1)[1].split()
            processes[int(path.name)] = (int(fields[1]), fields[19])
        except (OSError, ValueError, IndexError):
            continue
    owned = {root_pid}
    while True:
        added = {pid for pid, (parent, _) in processes.items() if parent in owned} - owned
        if not added:
            break
        owned.update(added)
    return {pid: processes[pid][1] for pid in owned if pid != root_pid and pid in processes}


def kill_descendants(root_pid):
    # Linux subreaper adoption also captures workers which start a new session
    # or outlive their immediate parent. Killing only a shell's process group
    # is insufficient for those workers.
    killed = []
    for pid, identity in descendant_identities(root_pid).items():
        try:
            current = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()[19]
            if current == identity:
                os.kill(pid, signal.SIGKILL)
                killed.append(pid)
        except (OSError, IndexError):
            pass
    return killed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--duty-cycle", type=float, default=1.0,
                        help="Owned process-group run fraction; pacing, not a hard CPU percentage guarantee.")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not 0 < args.timeout <= 7200 or not .1 <= args.duty_cycle <= 1:
        parser.error("a command and finite timeout <=7200s are required")
    root = args.receipt_dir.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    environment = os.environ.copy()
    # A virtualenv alone does not exclude host ROS/user-site packages when
    # PYTHONPATH injects them. Preserve the selected interpreter's own lock.
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONNOUSERSITE"] = "1"
    for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"):
        path = root / variable.lower()
        path.mkdir(mode=0o700)
        environment[variable] = str(path)
    environment.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", OMP_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1",
                       CARGO_BUILD_JOBS="2", CMAKE_BUILD_PARALLEL_LEVEL="2")
    (root / "command.json").write_text(json.dumps({"command": command, "cwd": str(Path.cwd()),
        "isolated_xdg": True, "native_threads": 1, "build_jobs": 2, "timeout_s": args.timeout,
        "process_group_run_fraction": args.duty_cycle, "hard_cpu_percentage_enforced": False}, indent=2))
    lock = threading.RLock()
    process = None
    events = []
    killed_descendants = set()
    libc = ctypes.CDLL(None, use_errno=True)
    previous_subreaper = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(previous_subreaper), 0, 0, 0) != 0 or libc.prctl(36, 1, 0, 0, 0) != 0:
        raise RuntimeError("qualification_child_ownership_unavailable")
    started = time.monotonic()
    def trip(reason):
        with lock:
            if not events:
                events.append({"reason": reason, "elapsed_s": time.monotonic()-started})
            if process is not None:
                killed_descendants.update(kill_descendants(os.getpid()))
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
    previous_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig in previous_handlers:
        signal.signal(sig, lambda *_: trip("operator_cancelled"))
    samples_file = (root / "samples.jsonl").open("w")
    def sample():
        reading = sample_resources()
        memory = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()
                  if line.startswith(('SwapTotal:', 'SwapFree:', 'MemAvailable:'))}
        samples_file.write(json.dumps({**asdict(reading), **memory}) + "\n")
        samples_file.flush()
        return reading
    guard = ResourceGuard(trip, sampler=sample)
    exit_code = 125
    try:
        if guard.start():
            with (root / "output.log").open("w") as output:
                with lock:
                    if not events:
                        process = subprocess.Popen(command, env=environment, stdout=output,
                            stderr=subprocess.STDOUT, start_new_session=True)
                if process is not None:
                    paused = False
                    while process.poll() is None:
                        if time.monotonic()-started >= args.timeout:
                            trip("command_wall_deadline")
                        if events:
                            try:
                                process.wait(timeout=.5)
                            except subprocess.TimeoutExpired:
                                pass
                            # Kill remaining descendants even if the leader exited.
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            process.wait(timeout=5)
                            break
                        if args.duty_cycle < 1:
                            # The supervisor/telemetry threads are outside the
                            # paced group. Wall deadlines include paused time.
                            want_pause = (time.monotonic()-started) % .2 >= .2 * args.duty_cycle
                            if want_pause != paused:
                                try:
                                    os.killpg(process.pid, signal.SIGSTOP if want_pause else signal.SIGCONT)
                                except ProcessLookupError:
                                    pass
                                paused = want_pause
                        time.sleep(.01)
                    exit_code = process.returncode if not events else 125
    finally:
        # An operator interrupt or supervisor exception must not strand the
        # workload (including a paced/stopped descendant) after its leader.
        if process is not None:
            killed_descendants.update(kill_descendants(os.getpid()))
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        guard.close()
        # Finish adoption/reaping after the top-level command has exited.
        cleanup_deadline = time.monotonic() + 3
        while True:
            children = descendant_identities(os.getpid())
            if not children:
                break
            killed_descendants.update(kill_descendants(os.getpid()))
            for pid in children:
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
            if time.monotonic() >= cleanup_deadline:
                if not events:
                    events.append({"reason": "owned_descendant_cleanup_incomplete"})
                exit_code = 125
                break
            time.sleep(.02)
        remaining_descendants = sorted(descendant_identities(os.getpid()))
        libc.prctl(36, previous_subreaper.value, 0, 0, 0)
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
        # A bounded telemetry call may still be finishing after close(). Leave
        # its file object alive until process exit instead of racing its write.
        receipt = {"exit_code": exit_code, "elapsed_s": time.monotonic()-started,
                   "events": events, "resource_guard": guard.receipt(),
                   "peak_child_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                   "owned_process_pid": process.pid if process else None,
                   "owned_leader_reaped": process is None or process.poll() is not None,
                   "killed_owned_descendants": sorted(killed_descendants),
                   "remaining_owned_descendants": remaining_descendants,
                   "unrelated_services_modified": False}
        (root / "receipt.json").write_text(json.dumps(receipt, indent=2))
        print(json.dumps(receipt, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
