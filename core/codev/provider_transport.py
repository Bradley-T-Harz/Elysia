"""Interrupt Codev's literal-loopback provider socket, including before headers.

The invoker still owns destination, role, prompt, fallback and compute policy.
This module only enforces a request's deadline/cancellation on its own socket;
it never stops the shared model service or changes model residency.
"""
from contextvars import ContextVar
from http.client import HTTPConnection
import socket
from threading import Event, Lock, Thread
import time
from urllib.request import HTTPHandler


_ACTIVE = ContextVar("codev_provider_request_control", default=None)


def active_provider_control():
    """Return the request-local socket control, if one is installed."""
    return _ACTIVE.get()


class ProviderCancelled(OSError):
    pass


class ProviderResourceLimited(OSError):
    pass


class ProviderControl:
    def __init__(self, timeout_s, cancel_check):
        self.deadline = time.monotonic() + max(0, timeout_s)
        self.cancel_check = cancel_check
        self.reason = None
        self._socket = None
        self._lock = Lock()
        self._stop = Event()
        self._thread = None
        self._token = _ACTIVE.set(self)

    def check(self):
        if self.reason == "cancelled" or (self.cancel_check and self.cancel_check()):
            self.reason = "cancelled"
            raise ProviderCancelled("operator_cancelled")
        if self.reason == "resource_limited":
            raise ProviderResourceLimited("owned_provider_resource_cutoff")
        if self.reason == "timeout" or time.monotonic() >= self.deadline:
            self.reason = "timeout"
            raise TimeoutError("Local provider request deadline exceeded")

    def abort(self, reason):
        """Interrupt only this invocation's socket; never unload a shared model."""
        if reason not in {"cancelled", "timeout", "resource_limited"}:
            raise ValueError("invalid_provider_abort_reason")
        with self._lock:
            if self.reason is None:
                self.reason = reason
            if self._socket is not None:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def attach(self, connection_socket):
        with self._lock:
            self._socket = connection_socket
        self.check()
        if self._thread is None:
            self._thread = Thread(target=self._watch, name="codev-provider-deadline", daemon=True)
            self._thread.start()

    def _watch(self):
        while not self._stop.wait(0.05):
            try:
                self.check()
            except (ProviderCancelled, ProviderResourceLimited, TimeoutError):
                # shutdown wakes getresponse/readline; close alone may leave a
                # buffered HTTPResponse blocked while it holds a socket reference.
                with self._lock:
                    if self._socket is not None:
                        try:
                            self._socket.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                return

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        with self._lock:
            if self._socket is not None:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self._socket.close()
            self._socket = None
        _ACTIVE.reset(self._token)


class ControlledHTTPHandler(HTTPHandler):
    def http_open(self, request):
        control = _ACTIVE.get()
        if control is None:
            return super().http_open(request)
        control.check()

        class Connection(HTTPConnection):
            def connect(self):
                super().connect()
                control.attach(self.sock)

        return self.do_open(Connection, request)
