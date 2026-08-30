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
    assert 'opencloud_security_end_of_life{host="opencloud.example.com",release_type="production"} 0' in metrics
    assert 'opencloud_security_support_days_remaining{host="opencloud.example.com",release_type="production"} 42' in metrics
    assert 'opencloud_security_update_available{host="opencloud.example.com",target_version="7.4.0"} 1' in metrics
    assert "opencloud_security_scan_duration_seconds{host=\"opencloud.example.com\"} 1.25" in metrics
    assert "opencloud_security_scrape_success{host=\"opencloud.example.com\"} 1" in metrics


def test_waived_measures_are_not_counted_as_missing_or_failed():
    """
    A waiver hides an alert, so it has to hide the metric an alert is built on.

    The plugin already drops waived measures from its own hardenings_missing
    and extra_checks_failed perfdata. Counting them here left the same instance
    reporting zero to Icinga and non-zero to Prometheus, so an alert rule on
    these gauges fired for exactly the measures the operator had switched off.
    """
    waived = {
        **RESULT,
        "hardenings": {"hstsLongMaxAge": False, "basicAuthDisabled": True},
        "setup": {
            "https": {"used": True, "enforced": False},
            "headers": {"X-Robots-Tag": False},
        },
        "extraChecks": [
            {"id": "tlsTrusted", "passed": False, "ignored": True},
            {"id": "tlsChain", "passed": False, "ignored": False},
        ],
        "ignored": ["hstsLongMaxAge", "httpsEnforced", "X-Robots-Tag", "tlsTrusted"],
    }

    metrics = render("opencloud.example.com", waived, duration_seconds=1, success=True)

    host = 'host="opencloud.example.com"'
    assert f"opencloud_security_hardenings_missing_total{{{host}}} 0" in metrics
    # The negative half: the one check that was not waived is still counted.
    assert f"opencloud_security_failed_extra_checks_total{{{host}}} 1" in metrics


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


def test_end_of_life_is_its_own_metric_rather_than_a_negative_day_count():
    """
    An undated release must not be indistinguishable from an expired one.

    A rolling or production release whose end of life has not been announced
    publishes no `support_days_remaining` sample at all. Without a separate
    boolean, the only alert that matters most - "this release gets no fixes" -
    would have to be inferred from a missing series, and a missing series is
    also what a broken scan looks like.
    """
    undated = {**RESULT, "EOL": True, "lifecycle": {"releaseType": "rolling"}}

    metrics = render("opencloud.example.com", undated, duration_seconds=1, success=True)

    assert 'opencloud_security_end_of_life{host="opencloud.example.com",release_type="rolling"} 1' in metrics
    assert "opencloud_security_support_days_remaining" not in metrics


def test_a_failed_scan_publishes_no_lifecycle_verdict():
    """A stale end-of-life reading is worse than none: it is a verdict nobody measured."""
    metrics = render("opencloud.example.com", RESULT, duration_seconds=1, success=False)

    assert "opencloud_security_end_of_life" not in metrics
    assert 'opencloud_security_scrape_success{host="opencloud.example.com"} 0' in metrics
