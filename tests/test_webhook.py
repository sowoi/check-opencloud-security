"""Tests for the optional webhook notification."""

import json

import pytest
import requests

import check_opencloud_security as plugin
from check_opencloud_security import NagiosExitCode, ScanContext, ScanResult

CRITICAL_RESULT = {
    "domain": "cloud.example.com",
    "product": "OpenCloud",
    "version": "5.0.0",
    "scannedAt": {"date": "2026-05-01 10:00:00.000000"},
    "rating": 0,
    "EOL": True,
    "vulnerabilities": [{"id": "CVE-2026-0001"}],
    "hardenings": {"cspWithoutUnsafeInline": False},
    "setup": {"https": {"used": True, "enforced": True}, "headers": {}},
    "extraChecks": [{"id": "exposed:/opencloud.yaml", "severity": "critical", "passed": False}],
    "updates": {"available": True, "availableVersion": "7.4.0", "source": "feed"},
}

OK_RESULT = {**CRITICAL_RESULT, "rating": 5, "EOL": False, "vulnerabilities": []}


@pytest.fixture
def posts(monkeypatch):
    """Record every webhook POST instead of sending it."""
    recorded = []

    class _Response:
        status_code = 200

        def raise_for_status(self):
            pass

    def _post(url, **kwargs):
        recorded.append((url, kwargs))
        return _Response()

    monkeypatch.setattr(plugin.requests, "post", _post)
    return recorded


def run(result, **kwargs):
    """Run the check and return its exit code."""
    context = ScanContext(host="cloud.example.com", **kwargs)
    with pytest.raises(SystemExit) as excinfo:
        plugin.check_vulnerabilities(
            context, ScanResult(response=result, uuid="local-x"), duration_seconds=1.0
        )
    return excinfo.value.code


def test_no_webhook_url_means_no_request(posts):
    """The webhook is entirely opt-in."""
    run(CRITICAL_RESULT)

    assert posts == []


def test_critical_result_fires_the_webhook(posts):
    """The default trigger is 'critical'."""
    run(CRITICAL_RESULT, webhook_url="https://hooks.example.com/x")

    assert len(posts) == 1
    url, kwargs = posts[0]
    assert url == "https://hooks.example.com/x"
    assert kwargs["json"]["status"] == "CRITICAL"


def test_ok_result_does_not_fire_by_default(posts):
    """Nobody wants a notification for every healthy poll."""
    run(OK_RESULT, webhook_url="https://hooks.example.com/x")

    assert posts == []


def test_warning_trigger_includes_critical(posts):
    """Trigger levels are cumulative, worst-inclusive."""
    run(OK_RESULT, webhook_url="https://x/", webhook_on="warning")
    assert posts == []

    run(CRITICAL_RESULT, webhook_url="https://x/", webhook_on="warning")
    assert len(posts) == 1


def test_always_fires_even_when_ok(posts):
    """'always' is for heartbeat-style integrations."""
    run(OK_RESULT, webhook_url="https://x/", webhook_on="always")

    assert posts[0][1]["json"]["status"] == "OK"


def test_payload_is_flat_and_self_describing(posts):
    """A generic receiver must not have to parse the human output."""
    run(CRITICAL_RESULT, webhook_url="https://x/", check_hardening=True)

    payload = posts[0][1]["json"]

    assert payload["plugin"] == "check-opencloud-security"
    assert payload["plugin_version"] == plugin.__version__
    assert payload["host"] == "cloud.example.com"
    assert payload["exit_code"] == int(NagiosExitCode.CRITICAL)
    assert payload["rating"] == 0
    assert payload["rating_label"] == "F"
    assert payload["eol"] is True
    assert payload["vulnerability_count"] == 1
    assert payload["vulnerabilities"] == ["CVE-2026-0001"]
    assert payload["missing_hardenings"] == ["cspWithoutUnsafeInline"]
    assert payload["failed_extra_checks"] == ["exposed:/opencloud.yaml"]
    assert payload["scan_backend"] == "local"
    assert payload["update"]["availableVersion"] == "7.4.0"
    assert payload["duration_seconds"] == 1.0
    # The payload has to survive a round trip through a JSON transport.
    json.dumps(payload)


def test_hardening_is_omitted_from_the_payload_when_not_checked(posts):
    """The payload must not claim knowledge the check did not gather."""
    run(CRITICAL_RESULT, webhook_url="https://x/")

    assert posts[0][1]["json"]["missing_hardenings"] == []


def test_custom_headers_are_sent(posts):
    """Most receivers need an authentication header."""
    run(
        CRITICAL_RESULT,
        webhook_url="https://x/",
        webhook_headers=(("X-Auth-Token", "s3cret"),),
    )

    headers = posts[0][1]["headers"]
    assert headers["X-Auth-Token"] == "s3cret"
    assert headers["Content-Type"] == "application/json"


def test_webhook_headers_are_parsed_from_flags():
    """'Name: value' is the form curl users expect."""
    assert plugin._parse_webhook_headers(["X-Token: abc", "X-Other:  def "]) == (
        ("X-Token", "abc"),
        ("X-Other", "def"),
    )


def test_malformed_webhook_headers_are_skipped_not_fatal(caplog):
    """A typo in a header must not take the whole check down."""
    assert plugin._parse_webhook_headers(["no-colon-here"]) == ()
    assert "malformed webhook header" in caplog.text


def test_webhook_failure_does_not_change_the_check_state(monkeypatch, capsys):
    """The result must stay truthful about OpenCloud, not about the hook."""

    def _boom(*args, **kwargs):
        raise requests.exceptions.ConnectionError("hook is down")

    monkeypatch.setattr(plugin.requests, "post", _boom)

    code = run(CRITICAL_RESULT, webhook_url="https://x/")

    assert code == int(NagiosExitCode.CRITICAL)
    assert "Webhook delivery failed" in capsys.readouterr().out


def test_webhook_fires_for_an_unreachable_instance(posts, monkeypatch):
    """An instance we cannot reach must be able to raise an alert too."""
    context = ScanContext(
        host="down.example.com",
        webhook_url="https://x/",
        webhook_on="unknown",
        scanner_settings=None,
    )

    def _boom(*args, **kwargs):
        raise plugin.ScanError("Instance is unreachable")

    monkeypatch.setattr(plugin, "local_scan", _boom)

    with pytest.raises(SystemExit) as excinfo:
        plugin.send_scan_request(context)

    assert excinfo.value.code == int(NagiosExitCode.UNKNOWN)
    assert posts[0][1]["json"]["status"] == "UNKNOWN"
    assert "Scan failed" in posts[0][1]["json"]["message"]


def test_webhook_uses_the_configured_proxy(posts):
    """A monitoring host behind a proxy must reach the receiver."""
    run(CRITICAL_RESULT, webhook_url="https://x/", proxy="http://proxy:3128")

    assert posts[0][1]["proxies"] == {
        "http": "http://proxy:3128",
        "https": "http://proxy:3128",
    }
