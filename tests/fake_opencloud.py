"""
A stand-in for a real OpenCloud instance, used by the scanner tests.

What the tests need is an *instance*, since the scanner is built in. This
module serves the handful of endpoints the built-in scanner actually looks
at:

* ``/status.php`` and ``/status`` - the unauthenticated status document
* ``/ocs/v1.php/cloud/capabilities`` - the public capabilities document
* ``/`` - the web UI, carrying the security headers
* the protected endpoints (``/graph/v1.0/users``, ``/remote.php/dav/...``)
* ``/.well-known/webfinger``

Every aspect is switchable, so a single fixture can impersonate a hardened
instance, a wide-open one, or anything in between.
"""

from __future__ import annotations

import base64
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
    # Serve the instance below this URL prefix instead of at the origin root.
    base_path: str = ""
    # Public options rendered by the web service at /config.json.
    web_config: dict[str, Any] | None = field(
        default_factory=lambda: {"options": {"embed": {}}}
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
    # Accept the documented demo credentials on the protected endpoints, the
    # way an instance left with IDM_CREATE_DEMO_USERS=true does.
    demo_users: bool = False
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
    # What the Server header says. A stock OpenCloud sets none; a reverse proxy
    # in front of it usually does.
    server_header: str = "OpenCloud"
    # Extra headers added to every response, the way a proxy or a CDN does.
    extra_headers: dict[str, str] = field(default_factory=dict)
    # Issuer published at /.well-known/openid-configuration. None serves the
    # instance's own origin, the way the built-in identity provider does; a
    # URL impersonates an external provider in front of it.
    openid_issuer: str | None = None
    # Answer the discovery request with a redirect to the issuer instead of a
    # document, which is what a proxied external provider usually does.
    openid_redirect: bool = False
    # No discovery document at all.
    openid_configuration: bool = True
    # App providers registered with the app registry, as /app/list reports
    # them. Empty means the endpoint answers with an empty list, which is what
    # an instance without an office integration does.
    app_providers: tuple[str, ...] = ()
    # Something answers /.well-known/caldav, the way a proxied Radicale does.
    caldav: bool = False
    # What the CORS middleware grants a request that carries an Origin.
    # 'reflect' echoes it back the way a middleware configured with '*' and
    # credentials does; 'wildcard' answers a literal '*'; None sends no
    # Access-Control-Allow-Origin at all.
    cors_allow_origin: str | None = None
    # Send 'Access-Control-Allow-Credentials: true' beside it.
    cors_allow_credentials: bool = False
    # Echo a TRACE request back the way a proxy with TraceEnable on does.
    trace_enabled: bool = False
    # Cookies set on the '/' response, as raw Set-Cookie values.
    set_cookies: tuple[str, ...] = ()
    # Every request the instance saw, as (method, path, sorted header names).
    seen: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)


# The demo accounts OpenCloud's documentation publishes, which an instance
# with IDM_CREATE_DEMO_USERS=true really does accept.
DEMO_CREDENTIALS: dict[str, str] = {
    "dennis": "demo",
    "margaret": "demo",
    "alan": "demo",
    "lynn": "demo",
    "mary": "demo",
}

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
            return behaviour.server_header

        def _respond(self, code, body=b"", extra=None, cookies=()):
            self.send_response(code)
            for name, value in (extra or {}).items():
                self.send_header(name, value)
            for cookie in cookies:
                self.send_header("Set-Cookie", cookie)
            self._cors_headers()
            if behaviour.disclose_server:
                self.send_header("X-Powered-By", behaviour.disclose_server)
            for name, value in behaviour.extra_headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _cors_headers(self):
            """Answer an Origin the way the configured CORS policy would."""
            origin = self.headers.get("Origin")
            if not origin or behaviour.cors_allow_origin is None:
                return
            allowed = behaviour.cors_allow_origin
            self.send_header(
                "Access-Control-Allow-Origin",
                origin if allowed == "reflect" else allowed,
            )
            if behaviour.cors_allow_credentials:
                self.send_header("Access-Control-Allow-Credentials", "true")

        def _json(self, payload, code=200):
            self._respond(
                code,
                json.dumps(payload).encode(),
                {"Content-Type": "application/json"},
            )

        def _demo_user(self):
            """The demo account the Authorization header names, if any."""
            header = self.headers.get("Authorization", "")
            scheme, _, token = header.partition(" ")
            if scheme.lower() != "basic":
                return None
            try:
                username, _, password = (
                    base64.b64decode(token.encode()).decode().partition(":")
                )
            except (ValueError, UnicodeDecodeError):
                return None
            return username if DEMO_CREDENTIALS.get(username) == password else None

        def _route_path(self):
            path = self.path.split("?", 1)[0]
            prefix = behaviour.base_path.rstrip("/")
            if not prefix:
                return path
            if path == prefix:
                return "/"
            if path.startswith(f"{prefix}/"):
                return path[len(prefix):]
            return path

        def do_GET(self):
            path = self._route_path()
            behaviour.seen.append(
                (
                    self.command,
                    self.path.split("?", 1)[0],
                    tuple(sorted(self.headers.keys())),
                )
            )

            if path == "/app/list":
                self._json(
                    {
                        "mime-types": [
                            {
                                "mime_type": "application/vnd.oasis.opendocument.text",
                                "app_providers": [
                                    {"name": name} for name in behaviour.app_providers
                                ],
                            }
                        ]
                        if behaviour.app_providers
                        else []
                    }
                )
                return

            if path == "/config.json" and behaviour.web_config is not None:
                self._json(behaviour.web_config)
                return

            if path in ("/.well-known/caldav", "/.well-known/carddav"):
                if behaviour.caldav:
                    self._respond(302, b"", {"Location": "/caldav/"})
                else:
                    self._respond(404, b"not found")
                return

            if path == "/.well-known/openid-configuration":
                if not behaviour.openid_configuration:
                    self._respond(404, b"not found")
                    return
                issuer = behaviour.openid_issuer or f"http://{self.headers.get('Host')}"
                if behaviour.openid_redirect:
                    self._respond(
                        302,
                        b"",
                        {"Location": f"{issuer}/.well-known/openid-configuration"},
                    )
                    return
                self._json(
                    {
                        "issuer": issuer,
                        "authorization_endpoint": f"{issuer}/authorize",
                        "token_endpoint": f"{issuer}/token",
                    }
                )
                return

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
                else:
                    body = b"<html>OpenCloud</html>"
                self._respond(
                    200, body, behaviour.headers, cookies=behaviour.set_cookies
                )
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
                if behaviour.demo_users and self._demo_user():
                    self._json({"ocs": {"data": {"id": self._demo_user()}}})
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

        def do_TRACE(self):
            behaviour.seen.append(
                (self.command, self.path.split("?", 1)[0], tuple(sorted(self.headers.keys())))
            )
            if not behaviour.trace_enabled:
                self._respond(405, b"method not allowed")
                return
            # What a proxy with TRACE left on returns: the request line and
            # every header the client sent, echoed back as the body.
            echo = f"TRACE {self.path} HTTP/1.1\r\n{self.headers}".encode()
            self._respond(200, echo, {"Content-Type": "message/http"})

        def do_POST(self):
            behaviour.seen.append(
                (self.command, self.path.split("?", 1)[0], tuple(sorted(self.headers.keys())))
            )
            self._respond(405, b"method not allowed")

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
