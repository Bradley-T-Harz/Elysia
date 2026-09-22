from __future__ import annotations

from threading import Event, Thread
from time import monotonic

import pytest
from urllib.request import Request

from app.api import research_service
from sandbox.fetch_worker import client as fetch_client
from sandbox.searxng_worker import client as searxng_client
from sandbox.searxng_worker.contract import (
    SearxngWorkerRequest,
    SearxngWorkerResult,
    SearxngWorkerStatus,
)
from sandbox.searxng_worker.worker import run_searxng_worker
from tests.test_searxng_worker_safety import write_config


def test_active_searxng_transport_closes_real_connection_on_cancel(
    monkeypatch,
):
    entered = Event()
    cancel = Event()

    class BlockingConnection:
        def __init__(
            self,
            _host,
            port,
            timeout,
        ):
            assert port == 8888
            assert timeout == 5
            self.closed = Event()
            self.sock = None

        def request(
            self,
            method,
            path,
            *,
            headers,
        ):
            assert method == "GET"
            assert path.startswith(
                "/search?"
            )
            assert headers["Accept"] == (
                "application/json"
            )

        def getresponse(self):
            entered.set()

            self.closed.wait(2)

            raise OSError(
                "synthetic socket closed"
            )

        def close(self):
            self.closed.set()

    connection = BlockingConnection(
        "127.0.0.1",
        8888,
        5,
    )

    monkeypatch.setattr(
        searxng_client,
        "HTTPConnection",
        lambda *_args, **_kwargs: connection,
    )

    def trigger_cancel():
        assert entered.wait(1)
        cancel.set()

    Thread(
        target=trigger_cancel,
        daemon=True,
    ).start()

    started = monotonic()

    with pytest.raises(
        InterruptedError,
        match="cancelled",
    ):
        searxng_client.search_searxng(
            base_url="http://127.0.0.1:8888",
            search_endpoint="/search",
            query="wetland restoration",
            max_results=5,
            timeout_seconds=5,
            safe_search="moderate",
            categories=["general"],
            language="en",
            cancel_check=cancel.is_set,
        )

    assert monotonic() - started < 1.0
    assert connection.closed.is_set()


def test_searxng_worker_cancel_before_dispatch_never_calls_client(
    tmp_path,
):
    calls: list[dict] = []

    result = run_searxng_worker(
        SearxngWorkerRequest(
            request_id="req_cancel_before_search",
            ticket_id="ticket_cancel_before_search",
            question="Wetland restoration",
            queries=["wetland restoration"],
        ),
        config_path=write_config(
            tmp_path / "searxng_worker.yaml",
            enabled=True,
        ),
        search_client=lambda **kwargs: (
            calls.append(kwargs)
            or []
        ),
        cancel_check=lambda: True,
    )

    assert result.status == SearxngWorkerStatus.FAILED
    assert result.worker_used is False
    assert result.network_access_used is False
    assert result.queries_sent == []
    assert calls == []
    assert result.query_outcomes[0]["state"] == "cancelled"


def test_run_bounded_research_threads_combined_cancel_to_worker(
    monkeypatch,
):
    observed: dict[str, object] = {}

    def fake_worker(
        request,
        *,
        cancel_check=None,
    ):
        observed["cancel_check"] = cancel_check
        observed["cancelled"] = bool(
            cancel_check and cancel_check()
        )

        return SearxngWorkerResult(
            status=SearxngWorkerStatus.FAILED,
            request_id=request.request_id,
            ticket_id=request.ticket_id,
            queries_requested=list(request.queries),
            query_outcomes=[
                {
                    "query": request.queries[0],
                    "state": "cancelled",
                    "outward_boundary_state": (
                        "external_boundary_planned"
                    ),
                    "network_access_used": False,
                    "searxng_used": False,
                }
            ],
            errors=[
                "Synthetic cancellation before dispatch."
            ],
        )

    monkeypatch.setattr(
        research_service,
        "run_searxng_worker",
        fake_worker,
    )

    result = (
        research_service
        .run_bounded_public_research(
            {
                "request_id": "req_combined_cancel",
                "question": "Wetland restoration",
                "queries": ["wetland restoration"],
            },
            internet_enabled_reader=lambda: True,
            cancel_check=lambda: True,
        )
    )

    assert callable(observed["cancel_check"])
    assert observed["cancelled"] is True
    assert result["data"]["worker_summary"][
        "query_outcomes"
    ][0]["state"] == "cancelled"


def test_web_research_port_promotes_cancelled_query_outcome_to_parent_state(
    monkeypatch,
):
    monkeypatch.setattr(
        research_service,
        "internet_master_enabled",
        lambda: True,
    )

    def cancelled_search(_payload):
        return {
            "status": "error",
            "errors": [
                "Synthetic in-flight search cancellation."
            ],
            "data": {
                "worker_summary": {
                    "worker_used": True,
                    "searxng_used": True,
                    "query_outcomes": [
                        {
                            "query": "wetland restoration",
                            "state": "cancelled",
                            "outward_boundary_state": "unknown",
                            "network_access_used": True,
                            "searxng_used": True,
                        }
                    ],
                },
                "queries_sent": [],
                "network_access_used": True,
                "durable_research": {
                    "state": "not_persisted",
                    "evidence_ids": [],
                },
                "evidence_packets": [],
                "errors": [
                    "Synthetic in-flight search cancellation."
                ],
            },
        }

    result = research_service.WebResearchPort().investigate(
        question="Research wetland restoration.",
        request_id="req_port_cancel",
        conversation_id=None,
        project_id=None,
        reasoning_gear="standard",
        autonomy_level=3,
        cancel_check=lambda: False,
        search_runner=cancelled_search,
    )

    assert result["state"] == "cancelled"
    assert result["research_attempted"] is True
    assert result["worker_used"] is True
    assert result["network_access_used"] is True
    assert result["progress"][0]["state"] == "cancelled"


def test_public_fetch_connection_is_closed_when_cancelled(
    monkeypatch,
):
    entered = Event()
    cancel = Event()
    instances = []

    class FakePinnedHTTPSConnection:
        def __init__(
            self,
            _target_ip,
            _hostname,
            _port,
            _timeout,
        ):
            self.closed = Event()
            instances.append(self)

        def request(
            self,
            _method,
            _path,
            *,
            headers,
        ):
            assert headers["Host"] == "example.com"

        def getresponse(self):
            entered.set()
            self.closed.wait(2)
            raise OSError(
                "synthetic connection closed"
            )

        def close(self):
            self.closed.set()

    monkeypatch.setattr(
        fetch_client,
        "_PinnedHTTPSConnection",
        FakePinnedHTTPSConnection,
    )

    def trigger_cancel():
        assert entered.wait(1)
        cancel.set()

    Thread(
        target=trigger_cancel,
        daemon=True,
    ).start()

    with pytest.raises(
        InterruptedError,
        match="cancelled",
    ):
        fetch_client._pinned_open(
            Request("https://example.com/"),
            timeout_seconds=5,
            allowed_public_ips=[
                "93.184.216.34"
            ],
            cancel_check=cancel.is_set,
        )

    assert instances
    assert instances[0].closed.is_set()

def test_public_fetch_body_read_is_interrupted_by_cancel(
    monkeypatch,
):
    entered_read = Event()
    cancel = Event()
    connection_closed = Event()

    class FakeHeaders(dict):
        def get(self, key, default=None):
            return super().get(
                key.lower(),
                default,
            )

    class BlockingResponse:
        status = 200

        def __init__(self):
            self.headers = FakeHeaders(
                {
                    "content-type": (
                        "text/plain; charset=utf-8"
                    )
                }
            )

        def getcode(self):
            return self.status

        def read(self, _size=-1):
            entered_read.set()

            connection_closed.wait(2)

            raise OSError(
                "synthetic blocked body read woke"
            )

        def close(self):
            return None

    response = BlockingResponse()

    class BlockingBodyConnection:
        def __init__(
            self,
            _target_ip,
            _hostname,
            _port,
            _timeout,
        ):
            self.sock = None

        def request(
            self,
            _method,
            _path,
            *,
            headers,
        ):
            assert headers["Host"] == "example.com"

        def getresponse(self):
            return response

        def close(self):
            connection_closed.set()

    monkeypatch.setattr(
        fetch_client,
        "_PinnedHTTPSConnection",
        BlockingBodyConnection,
    )

    def trigger_cancel():
        assert entered_read.wait(1)
        cancel.set()

    Thread(
        target=trigger_cancel,
        daemon=True,
    ).start()

    started = monotonic()

    result = fetch_client.fetch_public_page(
        url="https://example.com/",
        timeout_seconds=5,
        max_response_bytes=4096,
        max_snippet_chars=256,
        user_agent="Elysia-Test",
        allowed_public_ips=[
            "93.184.216.34"
        ],
        cancel_check=cancel.is_set,
    )

    assert monotonic() - started < 1.0
    assert connection_closed.is_set()
    assert result["cancelled"] is True
    assert result["network_access_used"] is True
    assert result["page_fetch_used"] is True
    assert "cancelled" in result["errors"][0].lower()


def test_fetch_worker_cancel_before_network_reports_no_network(
    monkeypatch,
):
    from sandbox.fetch_worker.contract import (
        FetchWorkerRequest,
        FetchWorkerStatus,
    )
    from sandbox.fetch_worker.worker import (
        run_fetch_worker,
    )
    import sandbox.fetch_worker.url_guard as fetch_url_guard

    monkeypatch.setattr(
        fetch_url_guard,
        "_resolved_ips",
        lambda _host: ["93.184.216.34"],
    )

    result = run_fetch_worker(
        FetchWorkerRequest(
            request_id="req_fetch_stop_before_network",
            ticket_id="ticket_fetch_stop_before_network",
            url="https://example.com/",
        ),
        cancel_check=lambda: True,
    )

    assert result.status == FetchWorkerStatus.FAILED
    assert result.network_access_used is False
    assert result.page_fetch_used is False
    assert result.evidence_packets == []
    assert any(
        "cancelled" in error.lower()
        for error in result.errors
    )
