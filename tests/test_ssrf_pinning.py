"""Tests for the scanner's validated-address connection pinning."""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from urllib3.util import connection as urllib3_connection

from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.scanner import ScannerSettings, _Probe, scan
from tests.fake_opencloud import FakeOpenCloud


class _Handler(BaseHTTPRequestHandler):
    host_header = ""

    def do_GET(self) -> None:
        type(self).host_header = self.headers.get("Host", "")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args: object) -> None:
        """Keep the test output readable."""


def test_a_validated_hostname_dials_its_pinned_address_and_keeps_host_header():
    """IP pinning must not discard the hostname needed by HTTP and TLS."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_port
        probe = _Probe(
            f"http://opencloud.example.com:{port}",
            ScannerSettings(
                scheme="http",
                verify_tls=False,
                pinned_addresses=(("opencloud.example.com", ("127.0.0.1",)),),
            ),
        )
        response = probe.get("/")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert response is not None
    assert response.status_code == 200
    assert _Handler.host_header == f"opencloud.example.com:{port}"


def _ipv6_loopback_available() -> bool:
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as candidate:
            candidate.bind(("::1", 0))
        return True
    except OSError:
        return False


# ::1 is the dead address below: nothing listens there on the IPv4 server's
# port, so the connect is refused at once instead of waiting for a timeout.
needs_ipv6 = pytest.mark.skipif(
    not _ipv6_loopback_available(), reason="no IPv6 loopback to refuse a connection on"
)


@contextmanager
def _server() -> Iterator[int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _dialled(monkeypatch) -> list[str]:
    """Record every address a connection is attempted to."""
    attempts: list[str] = []
    real = urllib3_connection.create_connection

    def spy(address, *args, **kwargs):
        attempts.append(address[0])
        return real(address, *args, **kwargs)

    monkeypatch.setattr(urllib3_connection, "create_connection", spy)
    return attempts


@needs_ipv6
def test_a_pinned_name_whose_first_address_is_dead_is_reached_on_the_next(monkeypatch):
    """
    The guard vetted every address; failing on the first alone is not safety.

    A dual-stack name with a dead AAAA record answered "unreachable" on the
    web service, where a visitor's browser simply used IPv4.
    """
    attempts = _dialled(monkeypatch)
    with _server() as port:
        probe = _Probe(
            f"http://opencloud.example.com:{port}",
            ScannerSettings(
                scheme="http",
                pinned_addresses=(("opencloud.example.com", ("::1", "127.0.0.1")),),
            ),
        )
        first = probe.get("/")
        # Closing the pools forces a new connection rather than a reused one:
        # it must start where the first one succeeded instead of paying for
        # the dead address again.
        probe.close()
        again = probe.get("/")

    assert first is not None and first.status_code == 200
    assert _Handler.host_header == f"opencloud.example.com:{port}"
    assert attempts[:2] == ["::1", "127.0.0.1"]
    assert again is not None and again.status_code == 200
    assert attempts[2:] == ["127.0.0.1"]
    assert probe.pinned_addresses == (("opencloud.example.com", ("127.0.0.1", "::1")),)


def _closed_port() -> int:
    """A port free on both loopbacks right now, so both refuse a connection."""
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ipv4:
            ipv4.bind(("127.0.0.1", 0))
            port = ipv4.getsockname()[1]
            try:
                with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as ipv6:
                    ipv6.bind(("::1", port))
            except OSError:
                continue
            return port


@needs_ipv6
def test_the_fallback_never_leaves_the_pinned_addresses(monkeypatch):
    """Every address dead means failing, never asking the resolver for another."""
    attempts = _dialled(monkeypatch)
    probe = _Probe(
        f"http://opencloud.example.com:{_closed_port()}",
        ScannerSettings(
            scheme="http",
            timeout=2,
            pinned_addresses=(("opencloud.example.com", ("::1", "127.0.0.1")),),
        ),
    )

    assert probe.get("/") is None
    assert attempts == ["::1", "127.0.0.1"]


@needs_ipv6
def test_a_single_pinned_address_is_never_widened(monkeypatch):
    """The per-address comparison pins one address; falling back would compare nothing."""
    attempts = _dialled(monkeypatch)
    with _server() as port:
        # 127.0.0.1 would answer on this port; the pin names only ::1.
        probe = _Probe(
            f"http://opencloud.example.com:{port}",
            ScannerSettings(
                scheme="http",
                pinned_addresses=(("opencloud.example.com", ("::1",)),),
            ),
        )
        response = probe.get("/")

    assert response is None
    assert attempts == ["::1"]


@needs_ipv6
def test_a_scan_reports_resolution_order_but_inspects_the_address_that_answered():
    """
    Debug ports and TLS dial the pin too; probing the dead address would
    report a closed port or a failed handshake the instance does not have.
    """
    with FakeOpenCloud() as instance:
        result = scan(
            f"opencloud.example.com:{instance.port}",
            settings=ScannerSettings(
                scheme="http",
                timeout=3,
                ipv6_enabled=True,
                # The instance's own port as a "debug port": reachable only
                # if the probe went to 127.0.0.1 rather than to ::1.
                debug_ports=(instance.port,),
                pinned_addresses=(("opencloud.example.com", ("::1", "127.0.0.1")),),
            ),
            release_settings=ReleaseSettings(mode="off"),
        )

    assert result["addresses"] == {"ipv4": ["127.0.0.1"], "ipv6": ["::1"]}
    debug = next(
        entry for entry in result["extraChecks"] if entry["id"] == f"debugPort:{instance.port}"
    )
    assert debug["passed"] is False
