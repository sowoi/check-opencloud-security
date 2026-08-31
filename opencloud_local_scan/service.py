"""
HTTP service around the built-in scanner.

This is what runs inside the Docker container: a small JSON API so that
several monitoring hosts can share one scanner, and so that results are
cached instead of being produced again on every poll.

======================================  ==========================================
Endpoint                                Behaviour
======================================  ==========================================
``POST /api/queue`` (``url=<host>``)    Scan the host and return ``{"uuid": ...}``
``GET  /api/result/<uuid>``             Return the stored scan result
``POST /api/requeue`` (``url=<host>``)  Discard the cached result and scan again
``GET  /api/scan?url=<host>``           Convenience: scan and return the result
``GET  /healthz``                       Liveness probe
======================================  ==========================================

Results are cached per host for ``cache_ttl`` seconds so that a monitoring
system polling several times a minute does not hammer the instance.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import threading
import time
import urllib.parse
import uuid as uuid_module
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .releases import ReleaseSettings
from .scanner import ScanError, ScannerSettings, scan

LOGGER = logging.getLogger("check_opencloud.service")

# Loopback, for the same reason ADR 0001 moved the Prometheus exporter there
# and ADR 0030 generalised it: this service takes a hostname from whoever
# connects and fetches it, with no target validation of its own, so a wide
# bind with no token is an open request forwarder into the network the
# monitoring host sits on. A container publishes a port or joins a network to
# be reached; that is a deployment decision, and it is made by setting this
# explicitly.
DEFAULT_LISTEN = "127.0.0.1"
DEFAULT_PORT = 8811
DEFAULT_CACHE_TTL_SECONDS = 900
MAX_BODY_BYTES = 8192

# Addresses that reach only this machine. Binding anywhere else exposes the
# service to a network, which is what makes a token mandatory.
LOOPBACK_LISTEN = frozenset({"127.0.0.1", "::1", "localhost", ""})


class ServiceMisconfigured(RuntimeError):
    """The service was asked to listen somewhere it must not listen openly."""


def _is_loopback_listen(listen: str) -> bool:
    """Whether this bind address reaches only the machine it runs on."""
    candidate = listen.strip().strip("[]").lower()
    if candidate in LOOPBACK_LISTEN:
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        # A hostname that is not one of the names above. Unresolvable here
        # without a lookup that could itself be answered with anything, so it
        # counts as exposed - the safe way to be wrong.
        return False


def ensure_listen_is_safe(listen: str, auth_token: str | None) -> None:
    """
    Refuse to serve a network without a credential in front.

    The scan endpoint takes a host from the request and connects to it. On
    loopback that is the operator talking to their own machine. On any other
    address it is whoever reaches the port, and an unauthenticated one is a
    way to read the inside of the network this host sits on - the metadata
    endpoint, a Docker socket, an admin panel - through a service that will
    report back what it saw.

    Failing to start is the right end for that: an operator who published the
    port meant to publish the service, and would otherwise find out what they
    published from somebody else.
    """
    if _is_loopback_listen(listen) or auth_token:
        return
    raise ServiceMisconfigured(
        f"Refusing to serve on {listen} without a token. This service scans "
        "whatever host a request names, so on anything but loopback it needs "
        "a credential: set --token, or COS_SERVICE_TOKEN (a 'secret://' "
        "reference is read from /run/secrets). Generate one with "
        "`openssl rand -hex 32`. To serve without one, bind 127.0.0.1 and "
        "publish the port with your container runtime instead."
    )


@dataclass
class _Entry:
    """One cached scan result."""

    uuid: str
    host: str
    result: dict[str, Any]
    created_at: float


@dataclass
class ScanStore:
    """Thread-safe result cache keyed by uuid and by host."""

    scanner_settings: ScannerSettings = field(default_factory=ScannerSettings)
    release_settings: ReleaseSettings | None = None
    cache_ttl: int = DEFAULT_CACHE_TTL_SECONDS
    _by_uuid: dict[str, _Entry] = field(default_factory=dict)
    _by_host: dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _fresh(self, entry: _Entry) -> bool:
        return (time.time() - entry.created_at) < self.cache_ttl

    def get_by_uuid(self, uuid: str) -> dict[str, Any] | None:
        """Return a stored result, ignoring its age (the client asked for it)."""
        with self._lock:
            entry = self._by_uuid.get(uuid)
        return entry.result if entry else None

    def scan(self, host: str, *, force: bool = False) -> _Entry:
        """Scan a host, reusing a cached result unless force is set."""
        with self._lock:
            cached_uuid = self._by_host.get(host)
            entry = self._by_uuid.get(cached_uuid) if cached_uuid else None
            if entry and not force and self._fresh(entry):
                LOGGER.debug("Serving cached result for %s", host)
                return entry

        result = scan(
            host,
            settings=self.scanner_settings,
            release_settings=self.release_settings,
        )
        entry = _Entry(
            uuid=str(uuid_module.uuid4()), host=host, result=result, created_at=time.time()
        )
        with self._lock:
            self._by_uuid[entry.uuid] = entry
            self._by_host[host] = entry.uuid
        return entry

    def purge(self) -> None:
        """Drop cache entries that outlived the TTL."""
        with self._lock:
            stale = [key for key, entry in self._by_uuid.items() if not self._fresh(entry)]
            for key in stale:
                host = self._by_uuid.pop(key).host
                if self._by_host.get(host) == key:
                    self._by_host.pop(host, None)


class _Handler(BaseHTTPRequestHandler):
    """Request handler implementing the scan service API."""

    server_version = "check-opencloud-scanner"
    protocol_version = "HTTP/1.1"

    store: ScanStore
    auth_token: str | None = None

    def log_message(self, format: str, *args: Any) -> None:
        """Route the built-in access log through the module logger."""
        LOGGER.debug("%s - %s", self.address_string(), format % args)

    # --- helpers ---
    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message, "status": int(status)}, status)

    def _authorized(self) -> bool:
        if not self.auth_token:
            return True
        provided = self.headers.get("X-Auth-Token") or ""
        authorization = self.headers.get("Authorization") or ""
        if authorization.lower().startswith("bearer "):
            provided = provided or authorization[7:].strip()
        # Encoded, because a header can carry bytes that are not ASCII and
        # comparing those as str raises instead of answering 401.
        return hmac.compare_digest(
            provided.encode("utf-8", "surrogateescape"),
            self.auth_token.encode("utf-8", "surrogateescape"),
        )

    def _read_host(self) -> str | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY_BYTES:
            return None
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        fields = urllib.parse.parse_qs(body)
        values = fields.get("url") or fields.get("host") or []
        return values[0].strip() if values else None

    def _scan_and_reply(self, host: str, *, force: bool, full: bool) -> None:
        try:
            entry = self.store.scan(host, force=force)
        except ScanError as exc:
            LOGGER.info("Scan of %s failed: %s", host, exc)
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._send_json(entry.result if full else {"uuid": entry.uuid})

    # --- routes ---
    def do_GET(self) -> None:
        """Handle result lookups, one-shot scans and the health probe."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/healthz":
            self._send_json({"status": "ok"})
            return

        if not self._authorized():
            self._send_error(HTTPStatus.UNAUTHORIZED, "Invalid or missing token.")
            return

        if path.startswith("/api/result/"):
            uuid = path[len("/api/result/"):]
            result = self.store.get_by_uuid(uuid)
            if result is None:
                self._send_error(HTTPStatus.NOT_FOUND, f"Unknown scan {uuid}.")
                return
            self._send_json(result)
            return

        if path == "/api/scan":
            query = urllib.parse.parse_qs(parsed.query)
            hosts = query.get("url") or query.get("host") or []
            if not hosts:
                self._send_error(HTTPStatus.BAD_REQUEST, "Missing 'url' parameter.")
                return
            force = (query.get("force") or ["0"])[0].lower() in {"1", "true", "yes"}
            self._scan_and_reply(hosts[0].strip(), force=force, full=True)
            return

        self._send_error(HTTPStatus.NOT_FOUND, f"Unknown endpoint {path}.")

    def do_POST(self) -> None:
        """Handle queue and requeue requests."""
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"

        if not self._authorized():
            self._send_error(HTTPStatus.UNAUTHORIZED, "Invalid or missing token.")
            return

        if path not in {"/api/queue", "/api/requeue"}:
            self._send_error(HTTPStatus.NOT_FOUND, f"Unknown endpoint {path}.")
            return

        host = self._read_host()
        if not host:
            self._send_error(HTTPStatus.BAD_REQUEST, "Missing 'url' parameter.")
            return

        self.store.purge()
        self._scan_and_reply(host, force=path == "/api/requeue", full=False)


def build_server(
    store: ScanStore,
    listen: str = DEFAULT_LISTEN,
    port: int = DEFAULT_PORT,
    auth_token: str | None = None,
) -> ThreadingHTTPServer:
    """Create the HTTP server without starting it (handy for tests)."""
    ensure_listen_is_safe(listen, auth_token)
    handler = type("BoundHandler", (_Handler,), {"store": store, "auth_token": auth_token})
    return ThreadingHTTPServer((listen, port), handler)


def serve(
    store: ScanStore,
    listen: str = DEFAULT_LISTEN,
    port: int = DEFAULT_PORT,
    auth_token: str | None = None,
) -> None:
    """Run the scan service until interrupted."""
    server = build_server(store, listen, port, auth_token)
    LOGGER.info(
        "OpenCloud scan service listening on %s:%d (%s)",
        listen,
        port,
        "token required" if auth_token else "loopback, no token",
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - interactive shutdown
        LOGGER.info("Shutting down")
    finally:
        server.server_close()
