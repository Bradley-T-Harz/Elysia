from __future__ import annotations

from sandbox.fetch_worker.config import load_fetch_worker_config


def test_fetch_worker_config_loads_safe_defaults():
    config = load_fetch_worker_config()

    assert config.worker_key == "bounded_fetch_worker"
    assert config.service["enabled"] is True
    # Public, read-only GETs are allowed without per-request approval when the
    # account Internet master is enabled.  Sensitive payloads are classified
    # and exact-approval gated before this bounded worker is called.
    assert config.posture["approval_required"] is False
    assert config.posture["private_context_allowed"] is False
    assert config.posture["browser_automation_allowed"] is False
    assert set(config.allowed_schemes) == {"http", "https"}
