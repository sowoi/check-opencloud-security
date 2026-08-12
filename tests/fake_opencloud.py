"""
A stand-in for a real OpenCloud instance, used by the scanner tests.

OpenCloud has no scan API, so there is nothing to fake on that side - what
the tests need instead is an *instance*. This module serves the handful of
endpoints the built-in scanner actually looks at:

* ``/status.php`` and ``/status`` - the unauthenticated status document
* ``/ocs/v1.php/cloud/capabilities`` - the public capabilities document
* ``/`` - the web UI, carrying the security headers
* the protected endpoints (``/graph/v1.0/users``, ``/remote.php/dav/...``)
* ``/.well-known/webfinger``

Every aspect is switchable, so a single fixture can impersonate a hardened
instance, a wide-open one, or anything in between.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# The real values an OpenCloud 7.x instance reports. Note that 'version' and
# 'versionstring' are hardcoded legacy constants kept for old sync clients -
# the actual release only ever shows up in 'productversion'.
STATUS_PAYLOAD: dict[str, Any] = {
    "installed": True,
    "maintenance": False,
    "needsDbUpgrade": False,
    "version": "0.1.0.0",
    "versionstring": "0.1.0",
    "edition": "stable",
    "productname": "OpenCloud",
    "product": "OpenCloud",
    "productversion": "7.2.3",
}

# The headers OpenCloud's proxy service sets out of the box.
DEFAULT_HEADERS: dict[str, str] = {
    "Strict-Transport-Security": "max-age=315360000; preload",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "X-Permitted-Cross-Domain-Policies": "none",
    "X-Robots-Tag": "none",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Type": "text/html",
}

# What OpenCloud actually ships: 'unsafe-inline' in both script-src and
# style-src, which the scanner is expected to flag.
DEFAULT_CSP_UNSAFE = (
    "default-src 'none'; script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'"
)

CAPABILITIES_PAYLOAD: dict[str, Any] = {
    "ocs": {
        "meta": {"status": "ok", "statuscode": 100, "message": "OK"},
        "data": {
            "version": {
                "major": 7,
                "minor": 2,
                "micro": 0,
                "string": "7.2.3",
                "edition": "stable",
                "productversion": "7.2.3",
            },
            "capabilities": {
                "core": {"status": {"productversion": "7.2.3"}},
                "files_sharing": {
                    "public": {
                        "enabled": True,
                        "password": {"enforced_for": {"read_only": True}},
                        "expire_date": {"enabled": True, "enforced": True},
                    },
                    "user": {"profile_picture": True},
                    "sharee": {"query_lookup_default": False},
                },
                "password_policy": {"min_characters": 12},
            },
        },
    }
}


@dataclass
class InstanceBehaviour:
    """Everything a test may want to change about the fake instance."""

    status_payload: dict[str, Any] = field(
        default_factory=lambda: dict(STATUS_PAYLOAD)
    )
    headers: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HEADERS))
    capabilities: dict[str, Any] | None = field(
        default_factory=lambda: json.loads(json.dumps(CAPABILITIES_PAYLOAD))
    )
    # Paths served with HTTP 200 even though they must not be reachable.
    exposed_paths: set[str] = field(default_factory=set)
    # Answer every unknown path with the SPA shell instead of a 404.
    catch_all: bool = False
    # Include 'Basic realm=...' in the WWW-Authenticate challenge, as
    # PROXY_ENABLE_BASIC_AUTH=true does.
    basic_auth: bool = False
    # Serve protected endpoints with 200 and a body instead of 401.
    unprotected: bool = False
    # Publish the version through webfinger.
    webfinger_version: bool = False
    # Serve a debug endpoint (/metrics, /config) on the main port.
    debug_endpoints: bool = False
    # Answer /status.php with something that is not an OpenCloud.
    status_status_code: int = 200
    status_body: bytes | None = None
    # Serve an Apache-style directory index on '/'.
    directory_listing: bool = False
    # Leak the backend through a Server or X-Powered-By header.
    disclose_server: str | None = None


PROTECTED_PATHS = (
    "/remote.php/dav/files/",
    "/graph/v1.0/users",
    "/graph/v1.0/me",
    "/ocs/v1.php/cloud/user",
    "/dav/",
)


def _make_handler(behaviour: InstanceBehaviour):
    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def version_string(self):
            # A stock OpenCloud does not advertise its web server, and the
            # BaseHTTPRequestHandler default would leak a Python version.
            return "OpenCloud"

        def _respond(self, code, body=b"", extra=None):
            self.send_response(code)
            for name, value in (extra or {}).items():
                self.send_header(name, value)
            if behaviour.disclose_server:
                self.send_header("X-Powered-By", behaviour.disclose_server)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, payload, code=200):
            self._respond(
                code,
                json.dumps(payload).encode(),
                {"Content-Type": "application/json"},
            )

        def do_GET(self):
            path = self.path.split("?", 1)[0]

            if path in ("/status.php", "/status"):
                if behaviour.status_body is not None:
                    self._respond(
                        behaviour.status_status_code,
                        behaviour.status_body,
                        {"Content-Type": "text/html"},
                    )
                else:
                    self._json(behaviour.status_payload, behaviour.status_status_code)
                return

            if path == "/ocs/v1.php/cloud/capabilities":
                if behaviour.capabilities is None:
                    self._respond(404, b"not found")
                else:
                    self._json(behaviour.capabilities)
                return

            if path == "/":
                if behaviour.directory_listing:
                    body = b"<html><head><title>Index of /</title></head><body>"
                    body += b"<h1>Index of /</h1><a href='opencloud.yaml'>x</a></body></html>"
                    self._respond(200, body, behaviour.headers)
                else:
                    self._respond(200, b"<html>OpenCloud</html>", behaviour.headers)
                return

            if path == "/.well-known/webfinger":
                payload = {
                    "subject": "acct:me@example.com",
                    "links": [
                        {
                            "rel": "http://webfinger.opencloud.eu/rel/server-instance",
                            "href": "https://example.com",
                            "titles": {"en": "OpenCloud"},
                        }
                    ],
                }
                if behaviour.webfinger_version:
                    payload["properties"] = {
                        "http://webfinger.opencloud.eu/prop/version": "7.2.3"
                    }
                self._json(payload)
                return

            if behaviour.debug_endpoints and (
                path in ("/metrics", "/config") or path.startswith("/debug/pprof")
            ):
                self._respond(
                    200,
                    b'opencloud_proxy_build_info{version="7.2.3"} 1\n',
                    {"Content-Type": "text/plain"},
                )
                return

            if path in behaviour.exposed_paths:
                self._respond(200, b"secret: value\n", {"Content-Type": "text/plain"})
                return

            if any(path.startswith(entry) for entry in PROTECTED_PATHS):
                if behaviour.unprotected:
                    self._json({"value": [{"id": "1", "onPremisesSamAccountName": "admin"}]})
                    return
                challenge = "Bearer realm=\"example.com\""
                if behaviour.basic_auth:
                    challenge = "Basic realm=\"example.com\", " + challenge
                self._respond(401, b"", {"WWW-Authenticate": challenge})
                return

            if behaviour.catch_all:
                # A single page application answers every unknown path with
                # the very same HTML shell instead of a 404.
                self._respond(
                    200, b"<html>OpenCloud</html>", {"Content-Type": "text/html"}
                )
                return

            self._respond(404, b"not found", {"Content-Type": "text/plain"})

        do_HEAD = do_GET
        do_PROPFIND = do_GET

    return _Handler


class FakeOpenCloud:
    """A fake OpenCloud instance listening on localhost."""

    def __init__(self, behaviour: InstanceBehaviour | None = None) -> None:
        self.behaviour = behaviour or InstanceBehaviour()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self.behaviour))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        """Port the fake instance listens on."""
        return int(self._server.server_address[1])

    @property
    def host(self) -> str:
        """'host:port' string that can be handed to the scanner."""
        return f"127.0.0.1:{self.port}"

    def __enter__(self) -> FakeOpenCloud:  # noqa: PYI034 - Self needs 3.11
        self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
