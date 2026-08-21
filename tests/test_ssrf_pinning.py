"""Tests for the scanner's validated-address connection pinning."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opencloud_local_scan.scanner import ScannerSettings, _Probe


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
