"""Tests for host parsing, target validation, retries and multi-host runs."""

import json
import threading

import pytest
import requests

import check_opencloud_security as plugin
from check_opencloud_security import NagiosExitCode, ScanContext

RESULT = {
    "domain": "cloud.example.com",
    "product": "OpenCloud",
    "version": "7.2.0",
    "scannedAt": {"date": "2026-05-01 10:00:00.000000"},
    "rating": 5,
    "EOL": False,
    "vulnerabilities": [],
    "hardenings": {},
    "setup": {"https": {"used": True, "enforced": True}, "headers": {}},
    "extraChecks": [],
    "updates": {"available": False, "version": "7.2.0", "source": "pinned"},
}


# --- host parsing ---
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("cloud.example.com", "cloud.example.com"),
        ("https://cloud.example.com/", "cloud.example.com"),
        ("http://cloud.example.com/apps/files?x=1", "cloud.example.com"),
        ("https://user:pw@cloud.example.com", "cloud.example.com"),
        ("cloud.example.com.", "cloud.example.com"),
        ("  cloud.example.com  ", "cloud.example.com"),
        # OpenCloud's own proxy listens on 9200, so the port must survive.
        ("https://cloud.example.com:9200/", "cloud.example.com:9200"),
        ("[2001:db8::1]", "[2001:db8::1]"),
    ],
)
def test_normalise_host(raw, expected):
    """Pasting a URL is a natural thing to do and must just work."""
    assert plugin._normalise_host(raw) == expected


def test_parse_hosts_splits_on_commas():
    """One check can cover a fleet."""
    hosts = plugin._parse_hosts("a.example.com, https://b.example.com/ ,,c.example.com")

    assert hosts == ["a.example.com", "b.example.com", "c.example.com"]


def test_parse_hosts_of_an_empty_value_is_empty():
    """An empty --host is caught by the caller, not silently scanned."""
    assert plugin._parse_hosts("  ,  ") == []


# --- target validation ---
@pytest.mark.parametrize(
    "host",
    [
        "cloud.example.com",
        "cloud.example.com:9200",
        # IP addresses are fine as targets: the built-in
        # scanner has no public API that would refuse them.
        "10.0.0.5",
        "10.0.0.5:9200",
        "[2001:db8::1]",
        "fe80::1%eth0",
        "localhost",
    ],
)
def test_valid_targets_are_accepted(host):
    """Anything an operator can actually point the scanner at must pass."""
    plugin.check_if_ip_or_host(host)


@pytest.mark.parametrize("host", ["", "   ", "not a host", "a/b"])
def test_unusable_targets_are_rejected(host, capsys):
    """A value that cannot be a target is a configuration error."""
    with pytest.raises(SystemExit) as excinfo:
        plugin.check_if_ip_or_host(host)

    assert excinfo.value.code == int(NagiosExitCode.UNKNOWN)
    assert "not a usable target address" in capsys.readouterr().out


# --- retries ---
def test_call_with_retry_returns_the_first_success():
    """No retry means no delay."""
    calls = []

    def _func():
        calls.append(1)
        return "ok"

    assert plugin._call_with_retry(_func, retries=3, backoff_factor=0, description="x") == "ok"
    assert len(calls) == 1


def test_call_with_retry_recovers_from_a_transient_error():
    """A single dropped connection must not fail the check."""
    calls = []

    def _func():
        calls.append(1)
        if len(calls) < 3:
            raise requests.exceptions.ConnectionError("flaky")
        return "ok"

    assert plugin._call_with_retry(_func, retries=3, backoff_factor=0, description="x") == "ok"
    assert len(calls) == 3


def test_call_with_retry_reraises_after_the_last_attempt():
    """Retries hide flakiness, not a genuinely broken target."""
    calls = []

    def _func():
        calls.append(1)
        raise requests.exceptions.ConnectionError("always down")

    with pytest.raises(requests.exceptions.ConnectionError):
        plugin._call_with_retry(_func, retries=2, backoff_factor=0, description="x")

    assert len(calls) == 3


def test_backoff_grows_exponentially(monkeypatch):
    """Hammering a struggling instance would make things worse."""
    sleeps = []
    monkeypatch.setattr(plugin.time, "sleep", sleeps.append)

    def _func():
        raise requests.exceptions.ConnectionError("down")

    with pytest.raises(requests.exceptions.ConnectionError):
        plugin._call_with_retry(_func, retries=3, backoff_factor=0.5, description="x")

    assert sleeps == [0.5, 1.0, 2.0]


def test_scan_errors_are_not_retried(monkeypatch):
    """
    A target that is not an OpenCloud will not become one.

    ScanError means the instance answered, just not with something usable,
    so retrying only wastes the check's timeout budget.
    """
    calls = []

    def _boom(*args, **kwargs):
        calls.append(1)
        raise plugin.ScanError("Instance did not return a usable status document.")

    monkeypatch.setattr(plugin, "local_scan", _boom)

    with pytest.raises(SystemExit):
        plugin.send_scan_request(ScanContext(host="cloud.example.com", retries=3))

    assert len(calls) == 1


# --- multi host ---
@pytest.fixture
def scans(monkeypatch):
    """Serve a canned result per host, or raise for hosts marked as broken."""
    results = {}

    def _scan(host, settings=None, release_settings=None):
        if host not in results:
            raise plugin.ScanError(f"{host} is unreachable")
        return {**RESULT, "domain": host, **results[host]}

    monkeypatch.setattr(plugin, "local_scan", _scan)
    return results


def parse_args(argv):
    """Parse plugin arguments the way main() does."""
    return plugin.build_arg_parser().parse_args(argv)


def test_single_host_run_reports_its_own_state(scans, capsys):
    """One host is the common case and must not gain a summary line."""
    scans["a.example.com"] = {}

    message, code, webhook_payload = plugin._run_single_host_check(
        ScanContext(host="a.example.com")
    )

    assert code is NagiosExitCode.OK
    assert "OpenCloud 7.2.0 on a.example.com" in message
    assert webhook_payload is None


def test_unexpected_worker_errors_cannot_inject_monitoring_framing(monkeypatch):
    """The last-resort multi-host boundary must flatten hostile exception text."""

    def fail(context):
        raise RuntimeError("remote\nforged line | forged_metric=1")

    monkeypatch.setattr(plugin, "send_scan_request", fail)

    message, code, _webhook_payload = plugin._run_single_host_check(
        ScanContext(host="opencloud.example.com")
    )

    assert code is NagiosExitCode.UNKNOWN
    assert "\nforged line" not in message
    assert "|" not in message


def test_multi_host_summary_counts_every_state(scans, capsys):
    """The first line must answer "how bad is it?" on its own."""
    scans["ok.example.com"] = {}
    scans["bad.example.com"] = {"rating": 0, "EOL": True}

    args = parse_args(["-H", "ok.example.com,bad.example.com,down.example.com"])
    code = plugin._run_multi_host_checks(
        ["ok.example.com", "bad.example.com", "down.example.com"], args
    )

    output = capsys.readouterr().out
    assert code is NagiosExitCode.CRITICAL
    assert "Checked 3 host(s): overall CRITICAL" in output
    assert "1 CRITICAL" in output
    assert "1 UNKNOWN" in output
    assert "1 OK" in output


def test_multi_host_prints_one_block_per_host(scans, capsys):
    """Each host's own verdict must stay readable."""
    scans["a.example.com"] = {}
    scans["b.example.com"] = {}

    args = parse_args(["-H", "a.example.com,b.example.com"])
    plugin._run_multi_host_checks(["a.example.com", "b.example.com"], args)

    output = capsys.readouterr().out
    assert "[a.example.com]" in output
    assert "[b.example.com]" in output


@pytest.mark.parametrize(
    ("hosts", "concurrency", "expected_workers"),
    [
        (["only.example.com"], None, 1),
        (["a.example.com", "b.example.com", "c.example.com"], None, 3),
        (["a.example.com", "b.example.com", "c.example.com"], 2, 2),
    ],
)
def test_multi_host_workers_match_the_host_count_up_to_the_configured_cap(
    scans, monkeypatch, hosts, concurrency, expected_workers
):
    """Host pools must avoid idle workers while respecting an operator's ceiling."""
    scans.update({host: {} for host in hosts})
    workers = []
    real_executor = plugin.ThreadPoolExecutor

    class RecordingExecutor:
        def __init__(self, *, max_workers, thread_name_prefix):
            workers.append(max_workers)
            self._executor = real_executor(
                max_workers=max_workers, thread_name_prefix=thread_name_prefix
            )

        def __enter__(self):
            self._executor.__enter__()
            return self

        def __exit__(self, *args):
            return self._executor.__exit__(*args)

        def map(self, *args):
            return self._executor.map(*args)

    monkeypatch.setattr(plugin, "ThreadPoolExecutor", RecordingExecutor)
    arguments = ["-H", ",".join(hosts)]
    if concurrency is not None:
        arguments.extend(["--concurrency", str(concurrency)])
    args = parse_args(arguments)

    plugin._run_multi_host_checks(hosts, args)

    assert workers == [expected_workers]


def test_multi_host_uses_critical_as_the_overall_exit_code(scans, capsys):
    """A warning must never mask a confirmed critical result from another host."""
    scans["warning.example.com"] = {"rating": 3}
    scans["critical.example.com"] = {"rating": 0, "EOL": True}
    args = parse_args(["-H", "warning.example.com,critical.example.com"])

    code = plugin._run_multi_host_checks(
        ["warning.example.com", "critical.example.com"], args
    )

    assert code is NagiosExitCode.CRITICAL
    assert "overall CRITICAL" in capsys.readouterr().out


def test_one_failing_host_does_not_abort_the_others(scans, capsys):
    """A single unreachable instance must not hide the rest of the fleet."""
    scans["good.example.com"] = {}

    args = parse_args(["-H", "down.example.com,good.example.com"])
    code = plugin._run_multi_host_checks(["down.example.com", "good.example.com"], args)

    output = capsys.readouterr().out
    assert code is NagiosExitCode.UNKNOWN
    assert "is unreachable" in output
    assert "OpenCloud 7.2.0 on good.example.com" in output


# --- webhook digest ---
@pytest.fixture
def posts(monkeypatch):
    """Record every webhook POST instead of sending it."""
    recorded = []

    class _Response:
        status_code = 200

        def raise_for_status(self):
            pass

    def _post(url, **kwargs):
        # See the identical fixture in tests/test_webhook.py: the plugin posts
        # pre-serialised bytes so that what it signed is what it sends, and
        # these tests assert against the document parsed back out of them.
        if "data" in kwargs:
            kwargs = {**kwargs, "json": json.loads(kwargs["data"])}
        recorded.append((url, kwargs))
        return _Response()

    monkeypatch.setattr(plugin.requests, "post", _post)
    return recorded


def test_webhook_digest_sends_one_combined_post(scans, posts):
    """A fleet with several critical hosts must not fire one webhook each."""
    scans["ok.example.com"] = {}
    scans["critical-a.example.com"] = {"rating": 0, "EOL": True}
    scans["critical-b.example.com"] = {"rating": 0, "EOL": True}

    args = parse_args(
        [
            "-H",
            "ok.example.com,critical-a.example.com,critical-b.example.com",
            "--webhook-url",
            "https://hooks.example.com/x",
            "--webhook-digest",
            "--allow-private-webhooks",
        ]
    )
    code = plugin._run_multi_host_checks(
        ["ok.example.com", "critical-a.example.com", "critical-b.example.com"], args
    )

    assert code is NagiosExitCode.CRITICAL
    assert len(posts) == 1
    url, kwargs = posts[0]
    assert url == "https://hooks.example.com/x"
    body = kwargs["json"]
    assert body["digest"] is True
    assert body["status"] == "CRITICAL"
    assert body["host_count"] == 2
    assert {host["host"] for host in body["hosts"]} == {
        "critical-a.example.com",
        "critical-b.example.com",
    }


def test_webhook_digest_does_not_fire_when_no_host_meets_the_trigger(scans, posts):
    """Default --webhook-on critical must stay quiet for an all-OK fleet, digest or not."""
    scans["a.example.com"] = {}
    scans["b.example.com"] = {}

    args = parse_args(
        [
            "-H",
            "a.example.com,b.example.com",
            "--webhook-url",
            "https://hooks.example.com/x",
            "--webhook-digest",
            "--allow-private-webhooks",
        ]
    )
    plugin._run_multi_host_checks(["a.example.com", "b.example.com"], args)

    assert posts == []


def test_without_digest_each_host_posts_its_own_webhook(scans, posts):
    """The default (no --webhook-digest) must keep sending one webhook per host."""
    scans["critical-a.example.com"] = {"rating": 0, "EOL": True}
    scans["critical-b.example.com"] = {"rating": 0, "EOL": True}

    args = parse_args(
        [
            "-H",
            "critical-a.example.com,critical-b.example.com",
            "--webhook-url",
            "https://hooks.example.com/x",
            "--allow-private-webhooks",
        ]
    )
    plugin._run_multi_host_checks(["critical-a.example.com", "critical-b.example.com"], args)

    assert len(posts) == 2
    hosts_posted = {kwargs["json"]["host"] for _, kwargs in posts}
    assert hosts_posted == {"critical-a.example.com", "critical-b.example.com"}


def test_webhook_digest_slack_format_lists_only_non_ok_hosts(scans, posts):
    """A chat-native digest must not bury the failing host in a wall of OK lines."""
    scans["ok.example.com"] = {}
    scans["critical.example.com"] = {"rating": 0, "EOL": True}

    args = parse_args(
        [
            "-H",
            "ok.example.com,critical.example.com",
            "--webhook-url",
            "https://hooks.example.com/x",
            "--webhook-digest",
            "--webhook-format",
            "slack",
            "--webhook-on",
            "always",
            "--allow-private-webhooks",
        ]
    )
    plugin._run_multi_host_checks(["ok.example.com", "critical.example.com"], args)

    assert len(posts) == 1
    text = posts[0][1]["json"]["attachments"][0]["text"]
    assert "critical.example.com" in text
    assert "ok.example.com" not in text
    assert "1 host(s) OK, not shown" in text


def test_a_slow_host_does_not_prevent_a_fast_host_from_running(monkeypatch, capsys):
    """A timeout-bound worker must not serialize a healthy host behind it."""
    fast_started = threading.Event()

    def _run(context):
        if context.host == "slow.example.com":
            assert fast_started.wait(timeout=1)
            return "UNKNOWN: slow.example.com Scan failed: timed out", NagiosExitCode.UNKNOWN, None
        fast_started.set()
        return "OK: fast.example.com", NagiosExitCode.OK, None

    monkeypatch.setattr(plugin, "_run_single_host_check", _run)
    args = parse_args(["-H", "slow.example.com,fast.example.com"])

    code = plugin._run_multi_host_checks(["slow.example.com", "fast.example.com"], args)

    assert code is NagiosExitCode.UNKNOWN
    output = capsys.readouterr().out
    assert "[fast.example.com]\nOK: fast.example.com" in output
    assert "[slow.example.com]\nUNKNOWN: slow.example.com Scan failed: timed out" in output


def test_summarize_multi_host_result_orders_by_severity():
    """The breakdown reads worst-first, like the aggregate state."""
    summary = plugin._summarize_multi_host_result(
        [NagiosExitCode.OK, NagiosExitCode.CRITICAL, NagiosExitCode.WARNING]
    )

    assert summary.startswith("Checked 3 host(s): overall CRITICAL")
    assert summary.index("CRITICAL,") < summary.index("WARNING") < summary.index("OK")
