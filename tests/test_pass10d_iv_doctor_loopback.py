from __future__ import annotations

import sys

from app.install import doctor_service


class _Response:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_doctor_probes_only_explicit_loopback_urls(monkeypatch) -> None:
    observed: list[str] = []

    def fake_urlopen(url: str, timeout: float):
        observed.append(url)
        assert timeout == 3.0
        return _Response()

    monkeypatch.setattr(doctor_service, "urlopen", fake_urlopen)
    assert doctor_service._loopback_reachable("http://127.0.0.1:8888/") is True
    assert doctor_service._loopback_reachable("http://localhost:11434/api/tags") is True
    assert doctor_service._loopback_reachable("https://example.com/") is False
    assert observed == ["http://127.0.0.1:8888/", "http://localhost:11434/api/tags"]


def test_doctor_accepts_normal_venv_interpreter_symlink(tmp_path) -> None:
    component_root = tmp_path / "components"
    binary_root = component_root / "elysia_workstation" / "bin"
    binary_root.mkdir(parents=True)
    (binary_root / "python").symlink_to(sys.executable)

    resolved = doctor_service._isolated_python_executable(
        component_root, "elysia_workstation"
    )

    assert resolved == binary_root / "python"


def test_doctor_uses_python_package_name_canonicalization_for_lock_proof() -> None:
    installed = doctor_service._canonical_installed_versions(
        {"pdfminer.six": "20260107", "argon2_cffi": "25.1.0"}
    )

    assert installed == {
        "pdfminer-six": "20260107",
        "argon2-cffi": "25.1.0",
    }


def test_doctor_reports_failed_loopback_probe_without_egress(monkeypatch) -> None:
    calls = 0

    def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise OSError("synthetic local refusal")

    monkeypatch.setattr(doctor_service, "urlopen", fail)
    assert doctor_service._loopback_reachable("http://127.0.0.1:9/") is False
    assert calls == 3


def test_doctor_retries_one_transient_loopback_failure(monkeypatch) -> None:
    calls = 0

    def transient_then_ready(url: str, timeout: float):
        nonlocal calls
        calls += 1
        assert url == "http://127.0.0.1:8888/"
        assert timeout == 3.0
        if calls == 1:
            raise TimeoutError("synthetic clean-VM scheduling delay")
        return _Response()

    monkeypatch.setattr(doctor_service, "urlopen", transient_then_ready)
    assert doctor_service._loopback_reachable("http://127.0.0.1:8888/") is True
    assert calls == 2


def test_rootless_podman_probe_retries_transient_vm_pressure(monkeypatch) -> None:
    calls = 0

    def run(command, **kwargs):
        nonlocal calls
        calls += 1
        assert command == [
            "/usr/bin/podman",
            "info",
            "--format",
            "{{.Host.Security.Rootless}}",
        ]
        assert kwargs["timeout"] == 60
        assert "DOCKER_HOST" not in kwargs["env"]
        assert "CONTAINER_HOST" not in kwargs["env"]
        if calls == 1:
            raise doctor_service.subprocess.TimeoutExpired(command, 60)
        return type("Result", (), {"returncode": 0, "stdout": "true\n"})()

    monkeypatch.setenv("DOCKER_HOST", "tcp://untrusted.invalid")
    monkeypatch.setenv("CONTAINER_HOST", "tcp://untrusted.invalid")
    monkeypatch.setattr(doctor_service.subprocess, "run", run)

    assert doctor_service._rootless_podman_ready("/usr/bin/podman") is True
    assert calls == 2


def test_rootless_podman_probe_fails_closed_after_bounded_attempts(
    monkeypatch,
) -> None:
    calls = 0

    def run(command, **kwargs):
        nonlocal calls
        calls += 1
        return type("Result", (), {"returncode": 125, "stdout": ""})()

    monkeypatch.setattr(doctor_service.subprocess, "run", run)

    assert doctor_service._rootless_podman_ready("/usr/bin/podman") is False
    assert calls == 3


def test_neurofabric_probe_allows_bounded_clean_vm_startup_time(
    tmp_path, monkeypatch,
) -> None:
    component_root = tmp_path / "components"
    binary_root = component_root / "elysia_neurofabric" / "bin"
    binary_root.mkdir(parents=True)
    python = binary_root / "python"
    python.write_text("placeholder", encoding="utf-8")
    python.chmod(0o700)
    receipt_root = tmp_path / "state" / "install" / "components"
    receipt_root.mkdir(parents=True)
    receipt = receipt_root / "scientific_engineering.json"
    receipt.write_text(
        '{"status":"ready","lock_name":"neurofabric-cpu-py312.lock.txt"}',
        encoding="utf-8",
    )
    receipt.chmod(0o600)
    paths = type("Paths", (), {"state_dir": tmp_path / "state"})()
    monkeypatch.setattr(
        doctor_service, "resolve_component_runtime_root", lambda _paths: component_root
    )
    observed = {}

    def run(command, **kwargs):
        observed["timeout"] = kwargs["timeout"]
        return type("Result", (), {
            "stdout": '{"cpu_ok":true,"ncps":"1.0.1","cuda":null,"available":false,"devices":0}\n'
        })()

    monkeypatch.setattr(doctor_service.subprocess, "run", run)
    result = doctor_service._neurofabric_runtime_check(
        paths, {"scientific_engineering"}, probe=True
    )
    assert observed["timeout"] == 180
    assert result.status == "present"
