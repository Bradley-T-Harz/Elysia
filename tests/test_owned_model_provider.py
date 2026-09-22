"""Real process ownership with a synthetic local provider; no model heating."""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from core.owned_model_provider import OwnedModelProfile, OwnedModelProvider, qualified_profile
from core.model_invoker import _call_owned_ollama_chat


@pytest.fixture
def profile():
    return OwnedModelProfile("synthetic_v1", "fixture:local", "a" * 64, "Synthetic GPU",
                             2, 4096, 1, 64, (min(os.sched_getaffinity(0)),),
                             1., 2048, 1024, 4096, 10, "synthetic")


def test_profile_selection_requires_exact_model_hardware_and_affinity(profile):
    cfg = {"models": {"execution_profiles": {"profiles": [asdict(profile)]}}}
    inventory = {"models": [{"runtime_tag": profile.runtime_tag, "digest": "a" * 64}]}
    state = {"gpu": {"devices": [{"name": "Synthetic GPU"}]}}
    assert qualified_profile(cfg, profile.runtime_tag, inventory, state) == profile
    assert qualified_profile(cfg, profile.runtime_tag, {"models": []}, state) is None
    assert qualified_profile(cfg, profile.runtime_tag, inventory, {"gpu": {}}) is None
    assert qualified_profile(cfg, "unapproved:local", inventory, state) is None
    estimated = profile.estimate({"digest": "a" * 64, "loaded": True})
    # An owned provider allocates its own weights even if the shared service is resident.
    assert estimated["incremental_vram_mb"] == profile.vram_mb


@pytest.fixture
def fake_provider(monkeypatch, isolated_account_store, safe_resource_samples):
    import core.owned_model_provider as owned
    from app.cognition import resource_guard
    monkeypatch.setattr(resource_guard, "sample_resources", lambda:
        resource_guard.ResourceSample(time.monotonic(), 50, 40, 32000, 1000))
    real_popen = subprocess.Popen
    children = []
    program = '''
import os,json,time,subprocess,sys
from http.server import BaseHTTPRequestHandler,HTTPServer
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(b'{"version":"synthetic"}')
 def do_POST(self):
  self.rfile.read(int(self.headers['Content-Length']))
  self.send_response(200);self.end_headers()
  self.wfile.write(b'{"message":{"content":"bounded answer"},"done":true,"model":"fixture:local"}\\n');self.wfile.flush()
HTTPServer(('127.0.0.1',int(os.environ['OLLAMA_HOST'].rsplit(':',1)[1])),Handler).serve_forever()
'''
    def launch(command, **kwargs):
        assert command[-1] == "serve"
        assert kwargs["start_new_session"] is True
        assert kwargs["env"]["OLLAMA_NO_CLOUD"] == "true"
        assert "PYTHONPATH" not in kwargs["env"]
        proc = real_popen([sys.executable, "-u", "-c", program], **kwargs)
        children.append(proc)
        return proc
    monkeypatch.setattr(owned.subprocess, "Popen", launch)
    monkeypatch.setattr(owned.shutil, "which", lambda _name: "/synthetic/ollama")
    monkeypatch.setattr(OwnedModelProvider, "_stage_model", lambda self, root: root)
    return children


@pytest.mark.parametrize("terminal", ["complete", "cancel", "timeout", "error"])
def test_real_owned_group_cleanup_on_every_terminal_path(profile, fake_provider, terminal):
    cancel = threading.Event()
    owner = OwnedModelProvider(profile, timeout_s=3, cancel_check=cancel.is_set)
    try:
        with owner:
            assert owner.process.poll() is None
            if terminal == "cancel":
                cancel.set()
            elif terminal == "timeout":
                owner.deadline = time.monotonic() + .05
            elif terminal == "error":
                raise RuntimeError("synthetic transport failure")
            if terminal in {"cancel", "timeout"}:
                until = time.monotonic() + 1
                while owner.process.poll() is None and time.monotonic() < until:
                    time.sleep(.02)
                assert owner.process.poll() is not None
    except RuntimeError:
        assert terminal == "error"
    assert all(proc.poll() is not None for proc in fake_provider)
    assert owner.receipt["provider_compute_stop_verified"]
    assert owner.receipt["remaining_active_pids"] == []
    assert owner.receipt["termination_reason"] == {
        "cancel": "operator_cancelled", "timeout": "owned_provider_wall_deadline"
    }.get(terminal, "owned_scope_finished")
    assert owner._temp is None
    owner.close()  # Repeated cleanup cannot target a reused PID.


def test_owned_provider_transport_returns_real_reply_and_cleanup_receipt(profile, fake_provider):
    result = _call_owned_ollama_chat(profile, dict(runtime_tag=profile.runtime_tag,
        system_prompt="bounded", message="synthetic question", timeout_s=3,
        max_output_tokens=16))
    assert result["ok"], result
    assert result["response_text"] == "bounded answer"
    assert result["provider_metadata"]["provider_compute_stop_verified"]
    assert result["execution_controls"]["num_gpu"] == 2
    assert result["execution_controls"]["context_tokens"] == 4096
    assert "models/" not in json.dumps(result)


def test_unowned_listener_cannot_receive_private_prompt(profile, fake_provider, monkeypatch):
    monkeypatch.setattr(OwnedModelProvider, "_owns_listener", lambda *a: False)
    result = _call_owned_ollama_chat(profile, dict(runtime_tag=profile.runtime_tag,
        system_prompt="PRIVATE_SYSTEM_CANARY", message="PRIVATE_MESSAGE_CANARY", timeout_s=.4,
        max_output_tokens=16))
    assert not result["ok"]
    assert "PRIVATE_" not in json.dumps(result)
    assert result["provider_metadata"]["provider_compute_stop_verified"]
    assert result["provider_metadata"]["timeout"]


def test_unqualified_provider_version_is_refused_before_inference(profile, fake_provider):
    result = _call_owned_ollama_chat(replace(profile, provider_version="unqualified"),
        dict(runtime_tag=profile.runtime_tag, system_prompt="private", message="private",
             timeout_s=3, max_output_tokens=16))
    assert not result["ok"]
    assert result["error"] == "owned_provider_version_not_qualified"
    assert result["provider_metadata"]["provider_compute_stop_verified"]
