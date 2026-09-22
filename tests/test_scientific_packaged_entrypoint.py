"""Fixed CLI dispatch proof; a real frozen binary is a separate package gate."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from app.api import scientificforge_process_service as process_service


def test_declared_core_payload_preserves_fixed_scientific_worker():
    root = Path(__file__).resolve().parents[1]
    manifest = yaml.safe_load((root / "packaging/public_manifest.yaml").read_text())
    assert "sandbox/scientificforge_worker" in manifest["core_payload"]["include_roots"]
    assert (root / "sandbox/scientificforge_worker/worker_cli.py").is_file()


def test_source_install_executes_science_without_developer_tree(tmp_path):
    root = Path(__file__).resolve().parents[1]
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"PYTHONPATH", "PYTHONHOME"}}
    for axis in ("CONFIG", "DATA", "STATE", "CACHE"):
        environment[f"XDG_{axis}_HOME"] = str(tmp_path / axis.lower())
    environment["XDG_RUNTIME_DIR"] = str(tmp_path / "runtime")
    installed = subprocess.run(
        ["bash", str(root / "scripts/install_core.sh"), "--apply", "--python", sys.executable],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=120)
    assert installed.returncode == 0, installed.stderr
    payload = tmp_path / "data/elysia/runtime/current"
    worker = payload / "sandbox/scientificforge_worker/worker_cli.py"
    assert worker.is_file(), "source installation omitted the fixed scientific worker"
    assert worker.read_bytes() == (root / "sandbox/scientificforge_worker/worker_cli.py").read_bytes()
    environment["PYTHONPATH"] = str(payload)
    for name, job, expected in (
        ("legacy", {"operation": "matrix_multiply", "matrix_a": [[3]], "matrix_b": [[7]]},
         {"matrix": [[21.0]]}),
        ("typed", {"ir_version": "scientific-ir-v0.2", "operation": "unit_convert",
                   "backend_family": "pint", "node_id": "convert", "symbols": [],
                   "unit": "meter", "target_unit": "centimeter", "inputs": {"value": 2}},
         {"value": 200.0}),
    ):
        request, result = tmp_path / f"{name}.json", tmp_path / f"{name}.result.json"
        request.write_text(json.dumps(job))
        execution = subprocess.run(
            [sys.executable, "-m", "sandbox.scientificforge_worker.worker_cli",
             "--request", str(request), "--result", str(result)],
            cwd=payload, env=environment, capture_output=True, text=True, timeout=30)
        assert execution.returncode == 0, execution.stderr
        outcome = json.loads(result.read_text())
        assert outcome["status"] == "completed"
        assert all(outcome["result"][key] == value for key, value in expected.items())
        assert outcome["network_access_used"] is False


def cli():
    spec = importlib.util.spec_from_file_location(
        "elysia_fixed_cli", Path(__file__).resolve().parents[1] / "packaging/elysia_cli.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixed_packaged_dispatch_executes_real_worker(tmp_path, monkeypatch):
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    request.write_text(json.dumps({"operation": "matrix_multiply", "matrix_a": [[2, 3]],
                                   "matrix_b": [[4], [5]]}))
    resource_root = tmp_path / "resources"
    resource_root.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(resource_root), raising=False)
    assert cli().main(["scientific-worker", "--request", "request.json", "--result", "result.json"]) == 0
    payload = json.loads(result.read_text())
    assert payload["status"] == "completed"
    assert payload["result"]["matrix"] == [[23.0]]
    assert payload["arbitrary_python_used"] is False
    assert payload["network_access_used"] is False


def test_fixed_cli_does_not_accept_arbitrary_module_or_code(tmp_path):
    for args in (["-m", "os"], ["scientific-worker", "--python", "print(1)"]):
        with pytest.raises(SystemExit) as exc:
            cli().main(args)
        assert exc.value.code == 2
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    request.write_text(json.dumps({"operation": "eval", "expression": "print(1)"}))
    assert cli().main(["scientific-worker", "--request", str(request), "--result", str(result)]) == 3
    assert json.loads(result.read_text())["blocked_reason"] == "unsupported_scientific_operation"


@pytest.mark.usefixtures("safe_resource_samples")
def test_frozen_parent_selects_fixed_child_entrypoint(tmp_path, monkeypatch):
    calls = []
    def launch(argv, **kwargs):
        calls.append(argv)
        # Exercise exactly the child argv's CLI contract and real adapter.
        status = cli().main(argv[1:])
        return status, b"", b"", None
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(Path.cwd()), raising=False)
    monkeypatch.setattr(process_service, "_bounded_process", launch)
    result = process_service.run_scientific_worker_process(
        {"operation": "matrix_multiply", "matrix_a": [[3]], "matrix_b": [[7]]})
    assert calls[0][1] == "scientific-worker"
    assert "-m" not in calls[0]
    assert result["status"] == "completed" and result["result"]["matrix"] == [[21.0]]
