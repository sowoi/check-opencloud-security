"""Tests for Prometheus rendering and the native /metrics exporter."""

from __future__ import annotations

import threading
from urllib.request import urlopen

import check_opencloud_security as plugin
from opencloud_local_scan.prometheus import render

RESULT = {
    "domain": "cloud.example.com",
    "product": "OpenCloud",
    "version": "7.2.0",
    "rating": 4,
    "vulnerabilities": [{"id": "CVE-2026-0001", "severity": "high"}],
    "hardenings": {"hstsLongMaxAge": False, "basicAuthDisabled": True},
    "extraChecks": [{"id": "tlsTrusted", "passed": False}],
    "lifecycle": {"daysRemaining": 42, "releaseType": "production"},
    "updates": {"available": True, "availableVersion": "7.4.0"},
}


def test_prometheus_exporter_binds_to_loopback_by_default():
    """Metrics must not become reachable over the network without an explicit opt-in."""
    args = plugin.build_arg_parser().parse_args(["-H", "opencloud.example.com"])

    assert args.prometheus_listen_addr == "127.0.0.1"


def test_scan_result_is_rendered_as_prometheus_gauges():
    """Every documented metric must have a typed, scrapeable sample."""
    metrics = render("opencloud.example.com", RESULT, duration_seconds=1.25, success=True)

    assert "# TYPE opencloud_security_rating_score gauge" in metrics
    assert 'opencloud_security_rating_score{host="opencloud.example.com",' in metrics
    assert 'opencloud_security_vulnerabilities_total{host="opencloud.example.com",severity="high"} 1' in metrics
    assert "opencloud_security_hardenings_missing_total{host=\"opencloud.example.com\"} 1" in metrics
    assert "opencloud_security_failed_extra_checks_total{host=\"opencloud.example.com\"} 1" in metrics
    assert 'opencloud_security_support_days_remaining{host="opencloud.example.com",release_type="production"} 42' in metrics
    assert 'opencloud_security_update_available{host="opencloud.example.com",target_version="7.4.0"} 1' in metrics
    assert "opencloud_security_scan_duration_seconds{host=\"opencloud.example.com\"} 1.25" in metrics
    assert "opencloud_security_scrape_success{host=\"opencloud.example.com\"} 1" in metrics


def test_prometheus_labels_escape_scan_metadata():
    """Untrusted response metadata must not escape or corrupt a metric label."""
    metrics = render(
        'opencloud.example.com"\\\r\n',
        {**RESULT, "domain": 'cloud.example.com"\r\n', "version": '7.2"0'},
        duration_seconds=1,
        success=True,
    )

    assert 'host="opencloud.example.com\\"\\\\\\r\\n"' in metrics
    assert 'domain="cloud.example.com\\"\\r\\n"' in metrics
    assert 'version="7.2\\"0"' in metrics


def test_metrics_endpoint_returns_prometheus_payload(monkeypatch):
    """The native exporter must refresh a scan and serve it at /metrics."""
    monkeypatch.setattr(plugin, "local_scan", lambda *args, **kwargs: RESULT)
    args = plugin.build_arg_parser().parse_args(
        [
            "-H",
            "opencloud.example.com",
            "--prometheus-listen-addr",
            "127.0.0.1",
            "--prometheus-listen-port",
            "0",
        ]
    )
    server = plugin.build_prometheus_server(["opencloud.example.com"], args)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        port = server.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2) as response:
            body = response.read().decode("utf-8")

        assert response.status == 200
        assert response.headers["Content-Type"].startswith("text/plain")
        assert "# TYPE opencloud_security_rating_score gauge" in body
        assert "opencloud_security_scrape_success" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
