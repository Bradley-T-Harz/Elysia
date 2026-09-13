"""Fixed-port, signed Codev transport. No native API proxy or filesystem routes."""
from __future__ import annotations

from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import socket
from socketserver import ThreadingMixIn
from threading import BoundedSemaphore, RLock, Thread
from time import monotonic, sleep

from core.codev import broker_crypto as crypto, pairing
from core.codev.contracts import BrokerPolicy, BrokerRequest
from core.codev.grants import GrantDenied

POLICY = BrokerPolicy()
PATHS = frozenset({"/codev/status", "/codev/revoke", "/codev/workspace/share", "/codev/workspace/revoke",
    "/codev/workspace/status", "/codev/workspace/reset", "/codev/chat", "/codev/chat/cancel", "/codev/patch/plan", "/codev/patch/authorize", "/codev/receipts"})
_SERVER = None
_SERVER_LOCK = RLock()


def dispatch(pair, path, payload):
    from core.codev import browser_workspaces
    if path == "/codev/status":
        if payload:
            raise GrantDenied("unexpected_status_input")
        return pairing.browser_status(pair)
    if path == "/codev/revoke":
        if payload:
            raise GrantDenied("unexpected_revocation_input")
        with pair.lock:
            pairing._revoke_local(pair)
        return {"local_revoked": True, "workspace_grants": []}
    return browser_workspaces.dispatch(pair, path, payload)


class _Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    block_on_close = False
    # POSIX permits restart after TIME_WAIT but still rejects another listener.
    # Windows needs exclusive binding to prevent SO_REUSEADDR listener takeover.
    allow_reuse_address = os.name != "nt"
    request_queue_size = 8

    def __init__(self):
        self.capacity = BoundedSemaphore(8)
        self.rate_lock = RLock()
        self.requests = deque()
        super().__init__(("127.0.0.1", POLICY.port), _Handler)

    def process_request(self, request, client_address):
        if not self.capacity.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.capacity.release()
            raise

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def process_request_thread(self, request, client_address):
        try:
            request.settimeout(5)
            super().process_request_thread(request, client_address)
        finally:
            self.capacity.release()

    def handle_error(self, *_args):
        # Never log raw request bodies, pairing codes, signatures, or source.
        pass

    def rate_allowed(self):
        with self.rate_lock:
            now = monotonic()
            while self.requests and self.requests[0] < now - 60:
                self.requests.popleft()
            if len(self.requests) >= 180:
                return False
            self.requests.append(now)
            return True


class _Handler(BaseHTTPRequestHandler):
    server_version = ""
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def log_message(self, *_args):
        pass

    def _reply(self, status, data=None, *, cors=False, preflight=False):
        raw = b"" if data is None else json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response_only(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        if cors:
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Vary", "Origin")
            if preflight:
                self.send_header("Access-Control-Allow-Methods", "POST")
                self.send_header("Access-Control-Allow-Headers", "content-type")
                self.send_header("Access-Control-Max-Age", "0")
                if self.headers.get("Access-Control-Request-Private-Network") == "true":
                    self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.close_connection = True
        if raw and self.command != "HEAD":
            self.wfile.write(raw)

    def send_error(self, code, message=None, explain=None):
        self._reply(code, {"ok": False, "error": "codev_broker_request_denied"})

    def _boundary(self):
        pairs = list(self.headers.raw_items())
        names = [name.lower() for name, _ in pairs]
        return (self.client_address[0] == "127.0.0.1" and self.path in PATHS
            and len(names) == len(set(names)) and sum(len(name) + len(value) for name, value in pairs) <= 8192
            and self.headers.get("Host") == POLICY.host and self.headers.get("Origin") in pairing.ORIGINS
            and not any(name in names for name in ("authorization", "cookie", "transfer-encoding", "content-encoding", "expect", "upgrade")))

    def do_OPTIONS(self):
        if (not self._boundary() or not self.server.rate_allowed()
            or self.headers.get("Access-Control-Request-Method") != "POST"
            or self.headers.get("Access-Control-Request-Headers", "").strip().lower() != "content-type"
            or self.headers.get("Content-Length", "0") != "0"):
            self._reply(403, {"ok": False, "error": "codev_broker_request_denied"})
            return
        self._reply(204, cors=True, preflight=True)

    def do_POST(self):
        if not self._boundary() or not self.server.rate_allowed():
            self._reply(403, {"ok": False, "error": "codev_broker_request_denied"})
            return
        try:
            size = self.headers.get("Content-Length", "")
            if not size.isascii() or not size.isdecimal() or not 1 <= int(size) <= POLICY.max_body_bytes:
                raise ValueError("bounded_body_required")
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                raise ValueError("json_required")
            raw = self.rfile.read(int(size))
            if len(raw) != int(size):
                raise ValueError("truncated_request")
            request = BrokerRequest.model_validate(crypto.strict_json(raw.decode("utf-8")))
            payload = crypto.strict_json(request.payload_json)
            origin = self.headers["Origin"]
            pair = pairing.authenticate(origin, self.path, request.proof, request.payload_json)
        except (ValueError, OSError, RecursionError):
            self._reply(403, {"ok": False, "error": "codev_broker_request_denied"}, cors=True)
            return
        try:
            result = {"ok": True, "data": dispatch(pair, self.path, payload)}
        except Exception:
            # Authenticated errors are signed; internal exceptions never reveal local paths.
            result = {"ok": False, "error": "Codev could not authorize or complete this request. Recheck the connection, workspace revision and grants."}
        response_json = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        if len(response_json.encode()) > POLICY.max_body_bytes:
            response_json = '{"ok":false,"error":"Codev result exceeds the bounded response limit."}'
        self._reply(200, {"payload_json": response_json, "signature": crypto.sign(pair.private_key,
            crypto.response_message(origin, self.path, request.proof, request.payload_json, response_json))}, cors=True)


def start_broker() -> None:
    global _SERVER
    with _SERVER_LOCK:
        if _SERVER is not None:
            return
        try:
            server = _Server()
        except OSError as exc:
            raise GrantDenied("codev_fixed_broker_port_unavailable") from exc
        Thread(target=server.serve_forever, name="codev-loopback-broker", daemon=True).start()
        _SERVER = server
        def monitor():
            while _SERVER is server:
                pairing.revoke_unavailable_pairs()
                sleep(0.5)
        Thread(target=monitor, name="codev-pairing-authority", daemon=True).start()


def stop_broker() -> None:
    global _SERVER
    with _SERVER_LOCK:
        server, _SERVER = _SERVER, None
    if server:
        server.shutdown()
        server.server_close()
