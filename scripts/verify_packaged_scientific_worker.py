#!/usr/bin/env python3
"""Exercise fixed mathematical workers in the actual frozen Core binary.

This gate proves packaged adapters, not authenticated workflow/model/UI
qualification. It runs without repository or developer interpreter imports.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile


def qualify(binary: Path) -> dict:
    checks = []
    with tempfile.TemporaryDirectory(prefix="elysia-packaged-science-") as directory:
        root = Path(directory)
        env = {
            "PATH": "/usr/bin:/bin", "HOME": str(root), "LANG": "C.UTF-8",
            "PYTHONNOUSERSITE": "1", "PYINSTALLER_RESET_ENVIRONMENT": "1",
            "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
        }
        for axis in ("CONFIG", "DATA", "CACHE", "STATE"):
            env[f"XDG_{axis}_HOME"] = str(root / axis.lower())

        def run(name, payload, expected="completed"):
            request = root / f"{name}.request.json"
            result = root / f"{name}.result.json"
            request.write_text(json.dumps(payload), encoding="utf-8")
            process = subprocess.Popen(
                [str(binary), "scientific-worker", "--request", str(request), "--result", str(result)],
                cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True,
            )
            try:
                _, errors = process.communicate(timeout=30)
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            assert process.returncode == (0 if expected == "completed" else 3), (name, errors[-1000:])
            data = json.loads(result.read_text())
            assert data["status"] == expected, (name, data)
            for field in ("network_access_used", "source_mutated", "arbitrary_python_used", "shell_used", "package_install_used"):
                assert data[field] is False, (name, field)
            checks.append({"name": name, "status": data["status"], "result": data.get("result"),
                           "diagnostics": data.get("diagnostics"), "engine_versions": data.get("engine_versions")})
            return data

        stats = run("v01_descriptive", {"operation": "descriptive_stats", "values": [1, 2, 3, 4, 5]})
        assert stats["result"]["statistics"]["mean"] == 3
        matrix = run("v01_matrix", {"operation": "matrix_multiply", "matrix_a": [[2, 3]], "matrix_b": [[4], [5]]})
        assert matrix["result"]["matrix"] == [[23.0]]
        source = root / "observations.csv"
        source.write_text("a,b\n1,2\n2,4\n3,6\n", encoding="utf-8")
        correlation = run("v01_correlation", {"operation": "correlation_matrix", "source_snapshot": str(source),
            "expected_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "columns": ["a", "b"]})
        assert math.isclose(correlation["result"]["matrix"][0][1], 1.0)
        for operation, extra in (
            ("bootstrap_mean_ci", {"values": [1, 2, 3, 4, 5], "bootstrap_samples": 100}),
            ("monte_carlo_normal", {"monte_carlo_samples": 100, "distribution_mean": 2, "distribution_stddev": 1}),
        ):
            job = {"operation": operation, "seed": 1729, **extra}
            first = run("v01_" + operation, job)
            second = run("v01_" + operation + "_repeat", job)
            assert first["result"] == second["result"] and first["seed_used"] == 1729

        def typed(name, operation, backend, **fields):
            return run(name, {"ir_version": "scientific-ir-v0.2", "node_id": "node",
                "operation": operation, "backend_family": backend, "symbols": [], **fields})

        solve = typed("v02_solve", "solve_linear_system", "numpy", inputs={"matrix": [[2, 1], [1, 3]], "rhs": [5, 7]})
        assert all(math.isclose(a, b) for a, b in zip(solve["result"]["solution"], [1.6, 1.8]))
        assert solve["diagnostics"]["residual"] < 1e-8
        derivative = typed("v02_calculus", "differentiate", "sympy",
            expression={"kind": "power", "args": [{"kind": "symbol", "symbol": "x"}, {"kind": "number", "value": 2}]},
            symbols=[{"name": "x", "role": "variable"}], variable="x")
        assert derivative["result"]["expression"] == {
            "kind": "multiply", "args": [{"kind": "number", "value": 2}, {"kind": "symbol", "symbol": "x"}]}
        converted = typed("v02_units", "unit_convert", "pint", unit="meter", target_unit="centimeter", inputs={"value": 2})
        assert converted["result"]["value"] == 200
        dimension = typed("v02_dimensions", "dimensional_check", "pint", unit="meter", target_unit="second")
        assert dimension["result"]["compatible"] is False
        run("arbitrary_operation_refused", {"operation": "eval", "expression": "print(1)"}, expected="blocked")

    return {"passed": True, "scope": "frozen fixed-worker adapters; not workflow or desktop proof",
            "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "checks": checks}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_packaged_scientific_worker.py PACKAGED_BINARY")
    print(json.dumps(qualify(Path(sys.argv[1]).resolve(strict=True)), sort_keys=True))
