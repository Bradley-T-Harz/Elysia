from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import app.api.runtime_bridge as runtime_bridge


def _disable_trace_writes(monkeypatch):
    """
    Keep this focused runtime-bridge test from depending on request-trace
    storage or the workstation's sealed local identity projection.
    """
    monkeypatch.setattr(
        runtime_bridge,
        "_load_visible_profile_context",
        lambda: None,
    )
    for name in [
        "append_request_trace_event",
        "mark_request_trace_blocked",
        "mark_request_trace_completed",
        "mark_request_trace_degraded",
        "mark_request_trace_error",
        "start_request_trace",
        "update_request_trace_snapshot",
    ]:
        monkeypatch.setattr(
            runtime_bridge,
            name,
            lambda *args, **kwargs: None,
        )


def _fake_attached_context_packet() -> dict[str, Any]:
    return {
        "attached_files_are_memory": False,
        "source": "user_selected_local_files",
        "locality": "local",
        "bounded": True,
        "requested_file_ids": ["file_alpha_001"],
        "used_file_ids": ["file_alpha_001"],
        "used_text_file_ids": ["file_alpha_001"],
        "used_data_file_ids": [],
        "requested_file_count": 1,
        "file_count": 1,
        "text_file_count": 1,
        "data_file_count": 0,
        "files": [
            {
                "file_id": "file_alpha_001",
                "display_name": "field-notes.md",
                "file_kind": "markdown",
                "processing_state": "ready",
                "parser_used": "markdown_text_parser",
                "memory_posture": "not_memory",
                "usable_as_context": True,
                "chunk_count": 2,
                "selected_chunk_count": 2,
                "chunks": [
                    {
                        "chunk_id": "file_alpha_001_chunk_0000",
                        "file_id": "file_alpha_001",
                        "chunk_index": 0,
                        "heading": None,
                        "char_start": 0,
                        "char_end": 45,
                        "token_estimate": 11,
                        "excerpt": "Alpha ecology note from the attached file.",
                    },
                    {
                        "chunk_id": "file_alpha_001_chunk_0001",
                        "file_id": "file_alpha_001",
                        "chunk_index": 1,
                        "heading": None,
                        "char_start": 45,
                        "char_end": 93,
                        "token_estimate": 12,
                        "excerpt": "Beta justice note from the attached file.",
                    },
                ],
            }
        ],
        "data_files": [],
        "warnings": [],
        "errors": [],
    }


def test_attached_file_context_is_injected_into_runtime_message_and_response(
    monkeypatch,
):
    _disable_trace_writes(monkeypatch)

    captured: dict[str, Any] = {}
    ledger: dict[str, Any] = {}

    class FakeSessionState:
        def __init__(
            self,
            active_mode=None,
            autonomy_level=None,
            memory_layers=None,
        ):
            self.active_mode = active_mode
            self.autonomy_level = autonomy_level
            self.memory_layers = memory_layers or []

    def fake_handle_user_message(
        message,
        session_state,
        request_context=None,
    ):
        captured["message"] = message
        captured["session_state"] = session_state
        captured["request_context"] = request_context

        return {
            "status": "ok_local_runtime",
            "internal_result": {
                "stayed_local": True,
            },
            "response": {
                "response_text": "The attached file contains Alpha ecology and Beta justice notes.",
                "response_source": "live_invoker",
                "invocation_status": "ok",
                "selected_model_role": "primary_general",
                "selected_runtime": "ollama",
                "selected_model_runtime_tag": "fake-local-model",
                "used_fallback": False,
                "fallback_from": "",
                "fallback_to": "",
                "caveats": [],
            },
            "policy_review": {
                "approval_required": False,
            },
            "log_status": {},
            "journal_status": {},
        }

    monkeypatch.setattr(
        runtime_bridge,
        "_load_runtime_module",
        lambda: SimpleNamespace(
            SessionState=FakeSessionState,
            handle_user_message=fake_handle_user_message,
        ),
    )
    monkeypatch.setattr(
        runtime_bridge,
        "build_attached_file_context_packet",
        lambda file_ids: _fake_attached_context_packet(),
        raising=False,
    )
    monkeypatch.setattr(
        runtime_bridge,
        "update_request_trace_ledger_snapshot",
        lambda **kwargs: ledger.update(kwargs),
    )

    result = runtime_bridge.send_chat_request(
        {
            "message": "Please summarize the attached file.",
            "request_id": "req_attached_runtime_001",
            "conversation_id": "conv_attached_runtime_001",
            "project_id": "project_attached_runtime_001",
            "requested_mode": "researcher",
            "ui_surface": "conversations_room",
            "request_context": {
                "attached_file_ids": ["file_alpha_001"],
                "attached_files_are_memory": False,
                "attached_files_source": "user_selected_local_files",
            },
        }
    )

    assert result["status"] == "ok"
    assert result["request_id"] == "req_attached_runtime_001"
    assert result["data"]["response_text"].startswith("The attached file contains")

    assert "Attached local file context:" in captured["message"]
    assert "These files were explicitly selected by the user" in captured["message"]
    assert "They are context only. They are not memory." in captured["message"]
    assert "field-notes.md" in captured["message"]
    assert "Alpha ecology note from the attached file." in captured["message"]
    assert "Beta justice note from the attached file." in captured["message"]
    assert "User request:\nPlease summarize the attached file." in captured["message"]

    runtime_context = captured["request_context"]

    assert runtime_context["attached_file_ids"] == ["file_alpha_001"]
    assert runtime_context["attached_files_are_memory"] is False
    assert runtime_context["attached_files_source"] == "user_selected_local_files"
    assert runtime_context["attached_context"]["file_count"] == 1
    assert runtime_context["attached_context"]["text_file_count"] == 1
    assert runtime_context["attached_context"]["data_file_count"] == 0
    assert runtime_context["attached_data_files"] == []

    attached_summary = result["data"]["attached_context_summary"]

    assert attached_summary["attached_files_are_memory"] is False
    assert attached_summary["attached_files_source"] == "user_selected_local_files"
    assert attached_summary["file_count"] == 1
    assert attached_summary["text_file_count"] == 1
    assert attached_summary["data_file_count"] == 0
    assert attached_summary["attached_file_ids"] == ["file_alpha_001"]
    assert attached_summary["attached_text_file_ids"] == ["file_alpha_001"]
    assert attached_summary["attached_data_file_ids"] == []
    assert attached_summary["files_in_use"] == ["field-notes.md"]
    assert attached_summary["text_files_in_use"] == ["field-notes.md"]
    assert attached_summary["data_files_in_use"] == []
    assert "not promoted into memory" in attached_summary["active_context_note"]
    assert attached_summary["files"][0]["parser_used"] == "markdown_text_parser"
    assert attached_summary["files"][0]["memory_promotion_allowed"] is False
    assert attached_summary["files"][0]["outward_sharing_allowed"] is False

    assert ledger["request_id"] == "req_attached_runtime_001"
    assert ledger["files_used_count"] == 1
    assert ledger["file_chunks_used_count"] == 2
    assert ledger["file_parsers_used"] == ["markdown_text_parser"]
    assert ledger["file_memory_promotion"] is False
    assert ledger["file_outward_sharing"] is False
    assert ledger["files_attached"][0]["file_name"] == "field-notes.md"
    assert ledger["files_attached"][0]["summary"] == (
        "Attached local file context; contents are not dumped in trace."
    )
    assert "excerpt" not in ledger["files_attached"][0]


def test_runtime_message_is_not_augmented_without_attached_file_ids(monkeypatch):
    _disable_trace_writes(monkeypatch)

    captured: dict[str, Any] = {}

    class FakeSessionState:
        def __init__(
            self,
            active_mode=None,
            autonomy_level=None,
            memory_layers=None,
        ):
            self.active_mode = active_mode
            self.autonomy_level = autonomy_level
            self.memory_layers = memory_layers or []

    def fake_handle_user_message(
        message,
        session_state,
        request_context=None,
    ):
        captured["message"] = message
        captured["session_state"] = session_state
        captured["request_context"] = request_context

        return {
            "status": "ok_local_runtime",
            "internal_result": {
                "stayed_local": True,
            },
            "response": {
                "response_text": "Plain local response.",
                "response_source": "live_invoker",
                "invocation_status": "ok",
                "selected_model_role": "primary_general",
                "selected_runtime": "ollama",
                "selected_model_runtime_tag": "fake-local-model",
                "used_fallback": False,
                "fallback_from": "",
                "fallback_to": "",
                "caveats": [],
            },
            "policy_review": {
                "approval_required": False,
            },
            "log_status": {},
            "journal_status": {},
        }

    monkeypatch.setattr(
        runtime_bridge,
        "_load_runtime_module",
        lambda: SimpleNamespace(
            SessionState=FakeSessionState,
            handle_user_message=fake_handle_user_message,
        ),
    )

    result = runtime_bridge.send_chat_request(
        {
            "message": "Hello without files.",
            "request_id": "req_plain_runtime_001",
            "conversation_id": "conv_plain_runtime_001",
            "requested_mode": "default",
            "ui_surface": "conversations_room",
        }
    )

    assert result["status"] == "ok"
    assert captured["message"] == "Hello without files."
    assert "Attached local file context:" not in captured["message"]
    assert captured["request_context"]["request_id"] == "req_plain_runtime_001"
    assert captured["request_context"]["conversation_id"] == "conv_plain_runtime_001"
    assert captured["request_context"]["internet_master_enabled"] is False
    assert "attached_context" not in captured["request_context"]
    assert result["data"].get("attached_context_summary") is None



def test_attached_csv_is_passed_as_data_file_without_prompt_injection(monkeypatch):
    _disable_trace_writes(monkeypatch)

    captured: dict[str, Any] = {}

    class FakeSessionState:
        def __init__(
            self,
            active_mode=None,
            autonomy_level=None,
            memory_layers=None,
        ):
            self.active_mode = active_mode
            self.autonomy_level = autonomy_level
            self.memory_layers = memory_layers or []

    def fake_handle_user_message(
        message,
        session_state,
        request_context=None,
    ):
        captured["message"] = message
        captured["session_state"] = session_state
        captured["request_context"] = request_context

        return {
            "status": "ok_local_runtime",
            "internal_result": {
                "stayed_local": True,
            },
            "response": {
                "response_text": "The attached CSV is available for bounded local data execution.",
                "response_source": "live_invoker",
                "invocation_status": "ok",
                "selected_model_role": "primary_general",
                "selected_runtime": "ollama",
                "selected_model_runtime_tag": "fake-local-model",
                "used_fallback": False,
                "fallback_from": "",
                "fallback_to": "",
                "caveats": [],
            },
            "policy_review": {
                "approval_required": False,
            },
            "log_status": {},
            "journal_status": {},
        }

    csv_packet = {
        "attached_files_are_memory": False,
        "source": "user_selected_local_files",
        "locality": "local",
        "bounded": True,
        "requested_file_ids": ["file_sites_001"],
        "used_file_ids": ["file_sites_001"],
        "used_text_file_ids": [],
        "used_data_file_ids": ["file_sites_001"],
        "requested_file_count": 1,
        "file_count": 1,
        "text_file_count": 0,
        "data_file_count": 1,
        "files": [],
        "data_files": [
            {
                "file_id": "file_sites_001",
                "display_name": "sites.csv",
                "file_name": "sites.csv",
                "name": "sites.csv",
                "file_kind": "csv",
                "source_kind": "attached_file",
                "source_path": "/local/ingest/raw/file_sites_001/sites.csv",
                "local_path": "/local/ingest/raw/file_sites_001/sites.csv",
                "processing_state": "ready",
                "memory_posture": "not_memory",
                "ready": True,
                "usable_as_context": True,
                "blocked": False,
                "chunk_count": 0,
                "selected_chunk_count": 0,
                "notes": [
                    "CSV is ready for bounded local data execution.",
                ],
            }
        ],
        "warnings": [],
        "errors": [],
    }

    monkeypatch.setattr(
        runtime_bridge,
        "_load_runtime_module",
        lambda: SimpleNamespace(
            SessionState=FakeSessionState,
            handle_user_message=fake_handle_user_message,
        ),
    )
    monkeypatch.setattr(
        runtime_bridge,
        "build_attached_file_context_packet",
        lambda file_ids: csv_packet,
        raising=False,
    )

    result = runtime_bridge.send_chat_request(
        {
            "message": "Summarize the attached CSV.",
            "request_id": "req_attached_csv_001",
            "conversation_id": "conv_attached_csv_001",
            "project_id": "project_attached_csv_001",
            "requested_mode": "researcher",
            "ui_surface": "conversations_room",
            "request_context": {
                "attached_file_ids": ["file_sites_001"],
                "attached_files_are_memory": False,
                "attached_files_source": "user_selected_local_files",
            },
        }
    )

    assert result["status"] == "ok"
    assert result["request_id"] == "req_attached_csv_001"
    assert result["data"]["response_text"].startswith("The attached CSV is available")

    assert captured["message"] == "Summarize the attached CSV."
    assert "Attached local file context:" not in captured["message"]
    assert "sites.csv" not in captured["message"]

    runtime_context = captured["request_context"]

    assert runtime_context["attached_file_ids"] == ["file_sites_001"]
    assert runtime_context["attached_files_are_memory"] is False
    assert runtime_context["attached_files_source"] == "user_selected_local_files"
    assert runtime_context["attached_context"]["file_count"] == 1
    assert runtime_context["attached_context"]["text_file_count"] == 0
    assert runtime_context["attached_context"]["data_file_count"] == 1

    assert len(runtime_context["attached_data_files"]) == 1
    assert runtime_context["attached_data_files"][0]["file_id"] == "file_sites_001"
    assert runtime_context["attached_data_files"][0]["file_kind"] == "csv"
    assert runtime_context["attached_data_files"][0]["source_kind"] == "attached_file"
    assert runtime_context["attached_data_files"][0]["source_path"].endswith(
        "sites.csv"
    )
    assert runtime_context["attached_data_files"][0]["ready"] is True
    assert runtime_context["attached_data_files"][0]["usable_as_context"] is True
    assert runtime_context["attached_data_files"][0]["blocked"] is False
    assert runtime_context["attached_data_files"][0]["memory_posture"] == "not_memory"

    attached_summary = result["data"]["attached_context_summary"]

    assert attached_summary["attached_files_are_memory"] is False
    assert attached_summary["attached_files_source"] == "user_selected_local_files"
    assert attached_summary["file_count"] == 1
    assert attached_summary["text_file_count"] == 0
    assert attached_summary["data_file_count"] == 1
    assert attached_summary["attached_file_ids"] == ["file_sites_001"]
    assert attached_summary["attached_text_file_ids"] == []
    assert attached_summary["attached_data_file_ids"] == ["file_sites_001"]
    assert attached_summary["files_in_use"] == ["sites.csv"]
    assert attached_summary["text_files_in_use"] == []
    assert attached_summary["data_files_in_use"] == ["sites.csv"]
    assert (
        "CSV/XLSX files may be used as bounded local data-execution inputs"
        in attached_summary["active_context_note"]
    )
