"""Bounded heterogeneous compute decisions and GPU lease accounting."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import threading
from typing import Any, Literal
from urllib import error as urllib_error
from urllib import request as urllib_request

from app.ids import new_id
from app.install.paths import ElysiaPaths, ensure_elysia_directories, resolve_elysia_paths


COMPUTE_GOVERNOR_VERSION = "compute-governor-v1"
DeviceDecision = Literal["cpu", "gpu", "hybrid", "deferred", "rejected", "background"]
_PRIORITY = {"background": 0, "batch": 1, "normal": 2, "interactive": 3, "emergency": 4}
_LOCK = threading.RLock()
_RECOVERED_DATABASES: set[str] = set()
_LAST_CPU_SAMPLE: tuple[int, int] | None = None


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class WorkloadDescriptor:
    workload_id: str
    owner_user_id: str | None
    task_kind: str
    priority: str = "normal"
    interactive: bool = False
    privacy: str = "normal"
    estimated_cpu_percent: int = 10
    estimated_gpu_percent: int = 0
    estimated_ram_mb: int = 512
    estimated_vram_mb: int = 0
    incremental_vram_mb: int | None = None
    estimated_duration_ms: int = 1000
    batchable: bool = False
    deadline_utc: str | None = None
    cancellable: bool = True
    preemptible: bool = True
    cpu_fallback_allowed: bool = True
    required_model: str | None = None
    required_resources: tuple[str, ...] = ()
    hard_vram_limit_mb: int | None = None
    model_to_evict: str | None = None
    estimate_source: str = "declared_by_workload_owner"


@dataclass(frozen=True)
class ComputeDecision:
    version: str
    workload_id: str
    decision: DeviceDecision
    selected_device: str
    lease_id: str | None
    reasons: tuple[str, ...]
    resource_snapshot: dict[str, Any]
    fallback: str | None
    queue_position: int | None
    content_free: bool = True
    reservation_id: str | None = None
    workload: dict[str, Any] | None = None
    observed_vram_mb: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _system_metrics() -> dict[str, Any]:
    result: dict[str, Any] = {
        "cpu_percent": None,
        "logical_cpus": os.cpu_count() or 1,
        "ram_total_mb": None,
        "ram_available_mb": None,
        "load_1m": None,
        "process_rss_mb": None,
        "process_threads": None,
        "process_count": None,
        "telemetry": "stdlib_fallback",
    }
    try:
        import psutil

        memory = psutil.virtual_memory()
        process = psutil.Process()
        result.update(
            cpu_percent=round(float(psutil.cpu_percent(interval=None)), 2),
            logical_cpus=int(psutil.cpu_count(logical=True) or os.cpu_count() or 1),
            ram_total_mb=int(memory.total // (1024 * 1024)),
            ram_available_mb=int(memory.available // (1024 * 1024)),
            load_1m=round(float(os.getloadavg()[0]), 3) if hasattr(os, "getloadavg") else None,
            process_rss_mb=int(process.memory_info().rss // (1024 * 1024)),
            process_threads=int(process.num_threads()),
            process_count=len(psutil.pids()),
            telemetry="psutil",
        )
    except Exception:
        global _LAST_CPU_SAMPLE
        try:
            result["load_1m"] = round(float(os.getloadavg()[0]), 3)
        except Exception:
            pass
        try:
            memory_rows = {}
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                key, _, raw = line.partition(":")
                if key in {"MemTotal", "MemAvailable"}:
                    memory_rows[key] = int(raw.strip().split()[0]) // 1024
            result["ram_total_mb"] = memory_rows.get("MemTotal")
            result["ram_available_mb"] = memory_rows.get("MemAvailable")
        except (OSError, ValueError, IndexError):
            pass
        try:
            cpu_fields = [int(value) for value in Path("/proc/stat").read_text(
                encoding="utf-8"
            ).splitlines()[0].split()[1:]]
            total = sum(cpu_fields)
            idle = cpu_fields[3] + (cpu_fields[4] if len(cpu_fields) > 4 else 0)
            with _LOCK:
                prior = _LAST_CPU_SAMPLE
                _LAST_CPU_SAMPLE = (total, idle)
            if prior and total > prior[0]:
                busy_delta = (total - prior[0]) - (idle - prior[1])
                result["cpu_percent"] = round(
                    max(0.0, min(100.0, busy_delta * 100.0 / (total - prior[0]))), 2
                )
                result["telemetry"] = "linux_procfs_delta"
            elif result["load_1m"] is not None:
                result["cpu_percent"] = round(
                    max(0.0, min(100.0, float(result["load_1m"]) * 100.0 / result["logical_cpus"])),
                    2,
                )
                result["telemetry"] = "linux_procfs_load_estimate"
        except (OSError, ValueError, IndexError):
            pass
        try:
            statm = Path("/proc/self/statm").read_text(encoding="utf-8").split()
            result["process_rss_mb"] = int(
                int(statm[1]) * os.sysconf("SC_PAGE_SIZE") // (1024 * 1024)
            )
            status_rows = Path("/proc/self/status").read_text(encoding="utf-8").splitlines()
            threads = next(line for line in status_rows if line.startswith("Threads:"))
            result["process_threads"] = int(threads.split()[1])
            result["process_count"] = sum(
                1 for entry in Path("/proc").iterdir() if entry.name.isdigit()
            )
        except (OSError, ValueError, IndexError, StopIteration):
            pass
    return result


def _gpu_metrics() -> dict[str, Any]:
    fields = (
        "index,name,uuid,memory.total,memory.used,memory.free,utilization.gpu,"
        "temperature.gpu,power.draw"
    )
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={fields}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2.5,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return {"available": False, "telemetry": "unavailable", "devices": []}
    if completed.returncode != 0:
        return {"available": False, "telemetry": "nvidia-smi-error", "devices": []}
    devices: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 9:
            continue
        try:
            devices.append(
                {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "uuid_suffix": parts[2][-12:],
                    "memory_total_mb": int(float(parts[3])),
                    "memory_used_mb": int(float(parts[4])),
                    "memory_free_mb": int(float(parts[5])),
                    "utilization_percent": float(parts[6]),
                    "temperature_c": float(parts[7]),
                    "power_w": float(parts[8]),
                }
            )
        except ValueError:
            continue
    return {"available": bool(devices), "telemetry": "nvidia-smi", "devices": devices}


def _ollama_residency() -> list[dict[str, Any]]:
    try:
        with urllib_request.urlopen("http://127.0.0.1:11434/api/ps", timeout=1.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib_error.URLError):
        return []
    return [
        {
            "model": str(item.get("model") or item.get("name") or ""),
            "size_vram_mb": int(item.get("size_vram") or 0) // (1024 * 1024),
            "context_length": int(item.get("context_length") or 0),
            "expires_at": item.get("expires_at"),
        }
        for item in payload.get("models", [])
        if isinstance(item, dict)
    ]


def resource_snapshot() -> dict[str, Any]:
    return {
        "captured_at_utc": _utc_now(),
        "system": _system_metrics(),
        "gpu": _gpu_metrics(),
        "ollama_residency": _ollama_residency(),
        "private_content_included": False,
    }


def _record_safely(ledger: "ComputeLedger", decision: ComputeDecision) -> None:
    try:
        ledger.record(decision)
    except (OSError, sqlite3.Error):
        # The decision remains truthful; status surfaces report receipt storage
        # degradation when the XDG state authority is not writable.
        pass


def is_accelerator_oom_error(error: BaseException | str | None) -> bool:
    """Classify an accelerator OOM without retaining provider error text."""
    normalized = " ".join(str(error or "").casefold().split())
    return any(
        marker in normalized
        for marker in (
            "cuda out of memory",
            "cuda error: out of memory",
            "hip out of memory",
            "accelerator out of memory",
            "gpu out of memory",
            "outofmemoryerror",
        )
    )


class ComputeLedger:
    def __init__(self, paths: ElysiaPaths | None = None) -> None:
        self.paths = paths or resolve_elysia_paths()
        self.database_path = self.paths.compute_governance_database_path

    def initialize(self) -> None:
        ensure_elysia_directories(self.paths)
        self.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS gpu_leases (
                    lease_id TEXT PRIMARY KEY,
                    workload_id TEXT NOT NULL,
                    owner_user_id TEXT,
                    task_kind TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    estimated_vram_mb INTEGER NOT NULL,
                    incremental_vram_mb INTEGER,
                    hard_vram_limit_mb INTEGER,
                    expected_duration_ms INTEGER NOT NULL DEFAULT 0,
                    required_model TEXT,
                    model_to_evict TEXT,
                    actual_vram_mb INTEGER,
                    deadline_utc TEXT,
                    cancellable INTEGER NOT NULL,
                    preemptible INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    release_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS compute_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    workload_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    selected_device TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS compute_jobs (
                    reservation_id TEXT PRIMARY KEY,
                    workload_id TEXT NOT NULL,
                    owner_user_id TEXT,
                    task_kind TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    deadline_utc TEXT,
                    state TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    release_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS compute_incidents (
                    incident_id TEXT PRIMARY KEY,
                    workload_id TEXT NOT NULL,
                    task_kind TEXT NOT NULL,
                    selected_device TEXT NOT NULL,
                    incident_code TEXT NOT NULL,
                    observed_vram_mb INTEGER,
                    hard_vram_limit_mb INTEGER,
                    recovery_action TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    content_free INTEGER NOT NULL DEFAULT 1
                );
                """
            )
            lease_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(gpu_leases)").fetchall()
            }
            for name, declaration in {
                "hard_vram_limit_mb": "INTEGER",
                "incremental_vram_mb": "INTEGER",
                "expected_duration_ms": "INTEGER NOT NULL DEFAULT 0",
                "required_model": "TEXT",
                "model_to_evict": "TEXT",
            }.items():
                if name not in lease_columns:
                    conn.execute(f"ALTER TABLE gpu_leases ADD COLUMN {name} {declaration}")
            database_key = str(self.database_path.resolve())
            with _LOCK:
                if database_key not in _RECOVERED_DATABASES:
                    conn.execute(
                        """
                        UPDATE gpu_leases SET state = 'interrupted', updated_at_utc = ?,
                            release_reason = 'restart_recovery'
                        WHERE state IN ('active','preempting')
                        """,
                        (_utc_now(),),
                    )
                    conn.execute(
                        """
                        UPDATE compute_jobs SET state = 'interrupted', updated_at_utc = ?,
                            release_reason = 'restart_recovery'
                        WHERE state = 'active'
                        """,
                        (_utc_now(),),
                    )
                    _RECOVERED_DATABASES.add(database_key)
        try:
            self.database_path.chmod(0o600)
        except OSError:
            pass

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def active_leases(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.connect() as conn:
            now = _utc_now()
            conn.execute(
                """
                UPDATE gpu_leases SET state = 'expired', updated_at_utc = ?,
                    release_reason = 'deadline_expired'
                WHERE state IN ('active','preempting')
                    AND deadline_utc IS NOT NULL AND deadline_utc <= ?
                """,
                (now, now),
            )
            rows = conn.execute(
                "SELECT * FROM gpu_leases WHERE state IN ('active','preempting') ORDER BY created_at_utc"
            ).fetchall()
        return [dict(row) for row in rows]

    def active_jobs(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.connect() as conn:
            now = _utc_now()
            conn.execute(
                """
                UPDATE compute_jobs SET state = 'expired', updated_at_utc = ?,
                    release_reason = 'deadline_expired'
                WHERE state = 'active' AND deadline_utc IS NOT NULL AND deadline_utc <= ?
                """,
                (now, now),
            )
            rows = conn.execute(
                "SELECT * FROM compute_jobs WHERE state = 'active' ORDER BY created_at_utc"
            ).fetchall()
        return [dict(row) for row in rows]

    def reserve_job(self, workload: WorkloadDescriptor) -> str:
        self.initialize()
        reservation_id = new_id("computejob")
        now = _utc_now()
        with _LOCK, self.connect() as conn:
            conn.execute(
                """
                INSERT INTO compute_jobs (
                    reservation_id, workload_id, owner_user_id, task_kind,
                    priority, deadline_utc, state, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    reservation_id, workload.workload_id, workload.owner_user_id,
                    workload.task_kind, workload.priority, workload.deadline_utc,
                    now, now,
                ),
            )
        return reservation_id

    def release_job(self, reservation_id: str, *, reason: str) -> bool:
        self.initialize()
        with _LOCK, self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE compute_jobs SET state = 'released', updated_at_utc = ?,
                    release_reason = ? WHERE reservation_id = ? AND state = 'active'
                """,
                (_utc_now(), reason[:160], reservation_id),
            )
        return cursor.rowcount > 0

    def acquire(self, workload: WorkloadDescriptor, available_vram_mb: int) -> tuple[str | None, list[str]]:
        self.initialize()
        reasons: list[str] = []
        with _LOCK, self.connect() as conn:
            active = conn.execute(
                "SELECT * FROM gpu_leases WHERE state IN ('active','preempting') ORDER BY created_at_utc"
            ).fetchall()
            reserved = sum(
                int(row["incremental_vram_mb"])
                if row["incremental_vram_mb"] is not None
                else int(row["estimated_vram_mb"] or 0)
                for row in active
            )
            needed = max(
                0,
                int(workload.incremental_vram_mb)
                if workload.incremental_vram_mb is not None
                else workload.estimated_vram_mb,
            )
            if needed > max(0, available_vram_mb - reserved):
                lower = [
                    row for row in active
                    if row["state"] == "active"
                    and bool(row["preemptible"])
                    and _PRIORITY.get(str(row["priority"]), 1) < _PRIORITY.get(workload.priority, 1)
                ]
                for row in lower:
                    conn.execute(
                        "UPDATE gpu_leases SET state = 'preempting', updated_at_utc = ?, release_reason = ? WHERE lease_id = ?",
                        (_utc_now(), f"preemption_requested_by:{workload.workload_id}", row["lease_id"]),
                    )
                    # A lease is not free until the owning worker acknowledges
                    # cancellation and releases it. Never overcommit VRAM merely
                    # because a preemption request was issued.
                    reasons.append(f"preemption_requested:{row['workload_id']}")
            if needed > max(0, available_vram_mb - reserved):
                return None, reasons + ["insufficient_unreserved_vram"]
            lease_id = new_id("gpulease")
            conn.execute(
                """
                INSERT INTO gpu_leases (
                    lease_id, workload_id, owner_user_id, task_kind, priority,
                    estimated_vram_mb, incremental_vram_mb, hard_vram_limit_mb, expected_duration_ms,
                    required_model, model_to_evict, deadline_utc, cancellable, preemptible,
                    state, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    lease_id, workload.workload_id, workload.owner_user_id,
                    workload.task_kind, workload.priority, workload.estimated_vram_mb,
                    needed,
                    workload.hard_vram_limit_mb, workload.estimated_duration_ms,
                    workload.required_model, workload.model_to_evict,
                    workload.deadline_utc, int(workload.cancellable),
                    int(workload.preemptible), _utc_now(), _utc_now(),
                ),
            )
            return lease_id, reasons + ["bounded_gpu_lease_acquired"]

    def release(self, lease_id: str, *, reason: str, actual_vram_mb: int | None = None) -> bool:
        self.initialize()
        with _LOCK, self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE gpu_leases SET state = 'released', updated_at_utc = ?,
                    release_reason = ?, actual_vram_mb = COALESCE(?, actual_vram_mb)
                WHERE lease_id = ? AND state IN ('active','preempting')
                """,
                (_utc_now(), reason[:160], actual_vram_mb, lease_id),
            )
        return cursor.rowcount > 0

    def preemption_requested(self, lease_id: str) -> bool:
        """Let an owning worker checkpoint/yield after higher-priority demand."""
        self.initialize()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT state FROM gpu_leases WHERE lease_id = ?",
                (lease_id,),
            ).fetchone()
        return bool(row and str(row["state"]) in {"preempting", "cancelled", "expired"})

    def cancel_all(self, reason: str = "emergency_stop") -> int:
        self.initialize()
        with _LOCK, self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE gpu_leases SET state = 'cancelled', updated_at_utc = ?,
                    release_reason = ? WHERE state IN ('active','preempting')
                """,
                (_utc_now(), reason[:160]),
            )
            conn.execute(
                """
                UPDATE compute_jobs SET state = 'cancelled', updated_at_utc = ?,
                    release_reason = ? WHERE state = 'active'
                """,
                (_utc_now(), reason[:160]),
            )
        return int(cursor.rowcount)

    def record_oom(
        self,
        *,
        workload_id: str,
        task_kind: str,
        selected_device: str,
        observed_vram_mb: int | None = None,
        hard_vram_limit_mb: int | None = None,
        recovery_action: str = "lease_released_cpu_fallback_allowed",
    ) -> str:
        """Persist a content-free accelerator OOM incident, never the raw error."""
        self.initialize()
        incident_id = new_id("computeincident")
        safe_task_kind = "".join(
            character for character in str(task_kind)[:80]
            if character.isalnum() or character in {"_", "-"}
        ) or "unknown_workload"
        safe_device = (
            str(selected_device) if str(selected_device) in {"cpu", "cuda:0", "none"}
            else "accelerator"
        )
        safe_recovery = (
            str(recovery_action) if str(recovery_action) in {
                "lease_released_cpu_fallback_allowed",
                "lease_released_request_failed",
                "bounded_probe_recovered",
            } else "lease_released_request_failed"
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO compute_incidents (
                    incident_id, workload_id, task_kind, selected_device,
                    incident_code, observed_vram_mb, hard_vram_limit_mb,
                    recovery_action, created_at_utc, content_free
                ) VALUES (?, ?, ?, ?, 'accelerator_out_of_memory', ?, ?, ?, ?, 1)
                """,
                (
                    incident_id, str(workload_id)[:160], safe_task_kind, safe_device,
                    observed_vram_mb, hard_vram_limit_mb, safe_recovery, _utc_now(),
                ),
            )
        return incident_id

    def recent_oom_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return bounded, content-free OOM operational history."""
        self.initialize()
        bounded_limit = max(1, min(int(limit), 100))
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT incident_id, workload_id, task_kind, selected_device,
                    incident_code, observed_vram_mb, hard_vram_limit_mb,
                    recovery_action, created_at_utc, content_free
                FROM compute_incidents
                WHERE incident_code = 'accelerator_out_of_memory'
                ORDER BY created_at_utc DESC, incident_id DESC LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def record(self, decision: ComputeDecision) -> None:
        self.initialize()
        safe_metrics = {
            "system": decision.resource_snapshot.get("system", {}),
            "gpu": decision.resource_snapshot.get("gpu", {}),
            "ollama_residency": decision.resource_snapshot.get("ollama_residency", []),
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO compute_receipts (
                    receipt_id, workload_id, decision, selected_device,
                    reasons_json, metrics_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("computereceipt"), decision.workload_id, decision.decision,
                    decision.selected_device, json.dumps(decision.reasons),
                    json.dumps(safe_metrics, sort_keys=True), _utc_now(),
                ),
            )


def decide_compute(
    workload: WorkloadDescriptor,
    *,
    preference: str = "automatic",
    cpu_percent_ceiling: int = 85,
    ram_mb_ceiling: int = 16384,
    vram_mb_ceiling: int = 12288,
    max_background_jobs: int = 2,
    stop_active: bool = False,
    paths: ElysiaPaths | None = None,
    resource_state: dict[str, Any] | None = None,
) -> ComputeDecision:
    ledger = ComputeLedger(paths)
    workload_payload = asdict(workload)
    snapshot = resource_state or resource_snapshot()
    reasons: list[str] = ["policy_before_optimization"]
    system = dict(snapshot.get("system") or {})
    gpu = dict(snapshot.get("gpu") or {})
    if workload.deadline_utc:
        try:
            deadline = datetime.fromisoformat(workload.deadline_utc.replace("Z", "+00:00"))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
        except ValueError:
            deadline = datetime.now(UTC)
        if deadline <= datetime.now(UTC):
            decision = ComputeDecision(
                COMPUTE_GOVERNOR_VERSION, workload.workload_id, "rejected", "none",
                None, tuple(reasons + ["workload_deadline_expired"]), snapshot, None, None,
            )
            decision = replace(decision, workload=workload_payload)
            _record_safely(ledger, decision)
            return decision
    if stop_active:
        decision = ComputeDecision(
            COMPUTE_GOVERNOR_VERSION, workload.workload_id, "rejected", "none",
            None, tuple(reasons + ["emergency_stop_active"]), snapshot, None, None,
        )
        decision = replace(decision, workload=workload_payload)
        _record_safely(ledger, decision)
        return decision
    if workload.estimated_ram_mb > ram_mb_ceiling:
        decision = ComputeDecision(
            COMPUTE_GOVERNOR_VERSION, workload.workload_id, "rejected", "none",
            None, tuple(reasons + ["ram_ceiling_exceeded"]), snapshot, None, None,
        )
        decision = replace(decision, workload=workload_payload)
        _record_safely(ledger, decision)
        return decision
    if (
        system.get("ram_available_mb") is not None
        and workload.estimated_ram_mb > int(system["ram_available_mb"])
    ):
        decision = ComputeDecision(
            COMPUTE_GOVERNOR_VERSION, workload.workload_id, "rejected", "none",
            None, tuple(reasons + ["insufficient_available_ram"]), snapshot, None, None,
        )
        decision = replace(decision, workload=workload_payload)
        _record_safely(ledger, decision)
        return decision
    if workload.estimated_cpu_percent > cpu_percent_ceiling:
        decision = ComputeDecision(
            COMPUTE_GOVERNOR_VERSION, workload.workload_id,
            "deferred" if workload.priority == "background" else "rejected", "none",
            None, tuple(reasons + ["workload_cpu_ceiling_exceeded"]), snapshot,
            None, 1 if workload.priority == "background" else None,
        )
        decision = replace(decision, workload=workload_payload)
        _record_safely(ledger, decision)
        return decision
    try:
        background_active = sum(
            1 for item in ledger.active_jobs() if item.get("priority") == "background"
        )
    except (OSError, sqlite3.Error):
        background_active = max_background_jobs
    if workload.priority == "background" and background_active >= max_background_jobs:
        decision = ComputeDecision(
            COMPUTE_GOVERNOR_VERSION, workload.workload_id, "deferred", "none",
            None,
            tuple(reasons + [
                "background_work_disabled" if max_background_jobs <= 0
                else "background_queue_ceiling_reached"
            ]),
            snapshot, None, background_active + 1,
        )
        decision = replace(decision, workload=workload_payload)
        _record_safely(ledger, decision)
        return decision
    cpu_busy = float(system.get("cpu_percent") or 0) >= cpu_percent_ceiling
    devices = list(gpu.get("devices") or [])
    gpu_available = bool(gpu.get("available") and devices)
    if gpu_available and float(devices[0].get("temperature_c") or 0) >= 88:
        gpu_available = False
        reasons.append("gpu_thermal_safety_fallback")
    if (
        gpu_available
        and workload.priority == "background"
        and float(devices[0].get("utilization_percent") or 0) >= 98
    ):
        gpu_available = False
        reasons.append("interactive_or_existing_gpu_load_wins")
    wants_gpu = preference == "gpu" or (
        preference == "automatic" and workload.estimated_vram_mb > 0
    )
    if wants_gpu and gpu_available:
        if workload.estimated_vram_mb > vram_mb_ceiling:
            reasons.append("workload_total_vram_ceiling_exceeded")
            gpu_available = False
        free = min(int(devices[0].get("memory_free_mb") or 0), vram_mb_ceiling)
    if wants_gpu and gpu_available:
        try:
            lease_id, lease_reasons = ledger.acquire(workload, free)
        except (OSError, sqlite3.Error):
            lease_id, lease_reasons = None, ["gpu_lease_ledger_unavailable"]
        reasons.extend(lease_reasons)
        if lease_id:
            decision = ComputeDecision(
                COMPUTE_GOVERNOR_VERSION, workload.workload_id,
                "hybrid" if workload.estimated_cpu_percent else "gpu",
                "cuda:0", lease_id, tuple(reasons), snapshot,
                "cpu" if workload.cpu_fallback_allowed else None, None,
            )
            try:
                decision = replace(decision, reservation_id=ledger.reserve_job(workload))
            except (OSError, sqlite3.Error):
                ledger.release(lease_id, reason="compute_job_reservation_failed")
                decision = ComputeDecision(
                    COMPUTE_GOVERNOR_VERSION, workload.workload_id, "rejected", "none",
                    None, tuple(reasons + ["compute_job_ledger_unavailable"]),
                    snapshot, None, None,
                )
            decision = replace(decision, workload=workload_payload)
            _record_safely(ledger, decision)
            return decision
    if workload.cpu_fallback_allowed and not cpu_busy:
        reasons.append("cpu_fallback" if wants_gpu else "cpu_earned")
        decision = ComputeDecision(
            COMPUTE_GOVERNOR_VERSION, workload.workload_id, "cpu", "cpu", None,
            tuple(reasons), snapshot, None, None,
        )
    elif workload.priority == "background":
        decision = ComputeDecision(
            COMPUTE_GOVERNOR_VERSION, workload.workload_id, "deferred", "none", None,
            tuple(reasons + ["resource_ceiling_busy"]), snapshot,
            "cpu" if workload.cpu_fallback_allowed else None, 1,
        )
    else:
        decision = ComputeDecision(
            COMPUTE_GOVERNOR_VERSION, workload.workload_id, "rejected", "none", None,
            tuple(reasons + ["no_safe_compute_path"]), snapshot, None, None,
        )
    if decision.decision in {"cpu", "gpu", "hybrid", "background"}:
        try:
            decision = replace(decision, reservation_id=ledger.reserve_job(workload))
        except (OSError, sqlite3.Error):
            decision = ComputeDecision(
                COMPUTE_GOVERNOR_VERSION, workload.workload_id, "rejected", "none",
                None, tuple(reasons + ["compute_job_ledger_unavailable"]),
                snapshot, None, None,
            )
    decision = replace(decision, workload=workload_payload)
    _record_safely(ledger, decision)
    return decision


__all__ = (
    "COMPUTE_GOVERNOR_VERSION",
    "ComputeDecision",
    "ComputeLedger",
    "WorkloadDescriptor",
    "decide_compute",
    "is_accelerator_oom_error",
    "resource_snapshot",
)
