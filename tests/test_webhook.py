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
        # The plugin posts pre-serialised bytes (`data=`) rather than handing
        # requests an object, so that the bytes it signed are the bytes that go
        # out. Parse them back under "json" so a test can talk about the
        # document a receiver would see - and so every such assertion is made
        # against what was actually transmitted.
        if "data" in kwargs:
            kwargs = {**kwargs, "json": json.loads(kwargs["data"])}
        recorded.append((url, kwargs))
        return _Response()

    monkeypatch.setattr(plugin.requests, "post", _post)
    return recorded


def run(result, **kwargs):
    """Run the check and return its exit code."""
    context = ScanContext(host="cloud.example.com", allow_private_webhooks=True, **kwargs)
    with pytest.raises(SystemExit) as excinfo:
        plugin.check_vulnerabilities(
            context, ScanResult(response=result, uuid="local-x"), duration_seconds=1.0
        )
    return excinfo.value.code


def test_no_webhook_url_means_no_request(posts):
    """The webhook is entirely opt-in."""
    run(CRITICAL_RESULT)

    assert posts == []


def test_private_webhook_protection_is_enabled_by_default():
    """Webhook destinations must be protected unless an operator opts out."""
    assert ScanContext(host="cloud.example.com").allow_private_webhooks is False


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
        allow_private_webhooks=True,
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


def _fake_getaddrinfo(*addresses):
    """Build a socket.getaddrinfo replacement that answers with fixed addresses."""

    def _getaddrinfo(hostname, *args, **kwargs):
        return [(None, None, None, "", (address, 0)) for address in addresses]

    return _getaddrinfo


def test_private_webhook_addresses_are_blocked(monkeypatch, caplog):
    """A webhook must not be usable to reach internal services by default."""
    posted = []
    monkeypatch.setattr(plugin.socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1"))
    monkeypatch.setattr(
        plugin.requests,
        "post",
        lambda *args, **kwargs: posted.append((args, kwargs)),
    )

    sent = plugin._send_webhook(
        ScanContext(host="cloud.example.com", webhook_url="https://hooks.example.com/x"),
        {"status": "CRITICAL"},
    )

    assert sent is False
    assert posted == []
    assert "restricted private/local IP address" in caplog.text


def test_private_webhooks_require_an_explicit_opt_out(monkeypatch):
    """An intentional internal receiver remains available with an opt-out."""
    posted = []
    monkeypatch.setattr(plugin.socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1"))

    class _Response:
        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        plugin.requests,
        "post",
        lambda url, **kwargs: posted.append((url, kwargs)) or _Response(),
    )

    sent = plugin._send_webhook(
        ScanContext(
            host="cloud.example.com",
            webhook_url="https://hooks.example.com/x",
            allow_private_webhooks=True,
        ),
        {"status": "CRITICAL"},
    )

    assert sent is True
    assert posted[0][0] == "https://hooks.example.com/x"


@pytest.mark.parametrize("url", ["not a URL", "https://unresolvable.example.com/x"])
def test_invalid_or_unresolvable_webhook_urls_are_blocked(monkeypatch, url):
    """A malformed or unresolvable destination must fail closed."""

    def _raise(*args, **kwargs):
        raise plugin.socket.gaierror()

    monkeypatch.setattr(plugin.socket, "getaddrinfo", _raise)

    assert plugin._is_safe_webhook_url(url) is False


def test_ipv6_private_address_is_blocked(monkeypatch):
    """An IPv6 loopback/private/link-local address must be blocked too."""
    for address in ("::1", "fd00::1", "fe80::1", "::ffff:127.0.0.1", "64:ff9b::7f00:1"):
        monkeypatch.setattr(plugin.socket, "getaddrinfo", _fake_getaddrinfo(address))
        assert plugin._is_safe_webhook_url("https://hooks.example.com/x") is False


def test_carrier_grade_nat_addresses_are_blocked(monkeypatch):
    """
    `ipaddress` does not call 100.64.0.0/10 private, but a webhook must not reach it.

    A host behind carrier-grade NAT shares that range with every other
    subscriber on the same carrier, and it contains 100.100.100.200 - a cloud
    metadata endpoint, where one successful request is already a breach. The
    scan-target guard in `webapp/ssrf.py` has always refused the range; this
    one let it through because none of the `is_private`/`is_reserved` flags
    covers it.
    """
    for address in ("100.64.0.1", "100.100.100.200", "100.127.255.254"):
        monkeypatch.setattr(plugin.socket, "getaddrinfo", _fake_getaddrinfo(address))
        assert plugin._is_safe_webhook_url("https://hooks.example.com/x") is False

    # The negative half: 100.128.0.0 is the first address past the range and is
    # ordinary public space, so the new rule must not swallow it.
    for address in ("100.128.0.1", "99.255.255.255", "8.8.8.8"):
        monkeypatch.setattr(plugin.socket, "getaddrinfo", _fake_getaddrinfo(address))
        assert plugin._is_safe_webhook_url("https://hooks.example.com/x") is True


def test_dual_stack_hostname_with_a_public_ipv4_and_private_ipv6_is_blocked(monkeypatch, caplog):
    """
    A hostname can answer a validator's A-record check while its AAAA record,
    the address `requests` may actually connect to, points somewhere private.

    Checking only the IPv4 address here would let this through.
    """
    posted = []
    monkeypatch.setattr(
        plugin.socket, "getaddrinfo", _fake_getaddrinfo("8.8.8.8", "fd00::1")
    )
    monkeypatch.setattr(
        plugin.requests,
        "post",
        lambda *args, **kwargs: posted.append((args, kwargs)),
    )

    sent = plugin._send_webhook(
        ScanContext(host="cloud.example.com", webhook_url="https://hooks.example.com/x"),
        {"status": "CRITICAL"},
    )

    assert sent is False
    assert posted == []
    assert "restricted private/local IP address" in caplog.text


def test_dns_rebinding_attack_is_prevented(monkeypatch, caplog):
    """DNS rebinding attacks must be detected and blocked.

    An attacker submits a webhook URL pointing to a public address, which passes
    validation. Between validation and delivery, they change the DNS record to
    point to a private address. The webhook must detect this and block delivery.
    """
    resolve_count = 0
    posted = []

    def _getaddrinfo_rebinding(hostname, *args, **kwargs):
        nonlocal resolve_count
        resolve_count += 1
        address = "8.8.8.8" if resolve_count == 1 else "127.0.0.1"
        return [(None, None, None, "", (address, 0))]

    class _Response:
        def raise_for_status(self):
            pass

    def _post(url, **kwargs):
        posted.append((url, kwargs))
        return _Response()

    monkeypatch.setattr(plugin.socket, "getaddrinfo", _getaddrinfo_rebinding)
    monkeypatch.setattr(plugin.requests, "post", _post)

    sent = plugin._send_webhook(
        ScanContext(
            host="cloud.example.com",
            webhook_url="https://hooks.example.com/x",
        ),
        {"status": "CRITICAL"},
    )

    assert sent is False
    assert posted == []
    assert "DNS resolution changed" in caplog.text
    assert "DNS rebinding attack" in caplog.text


def test_webhook_signature_verifies_against_the_bytes_actually_sent(posts):
    """
    A receiver verifies the raw body it received, so the signature has to be
    the HMAC of exactly those bytes.

    Recomputing it from the re-serialised *document* instead would pass even
    if the plugin signed one encoding and transmitted another, which is
    precisely the bug this guards: `json=` lets requests choose its own
    separators and key order, so the hash a receiver computes would never
    match the header.
    """
    import hashlib
    import hmac

    run(
        CRITICAL_RESULT,
        webhook_url="https://hooks.example.com/x",
        webhook_secret="my-secret",
    )

    assert len(posts) == 1
    _, kwargs = posts[0]

    sent_bytes = kwargs["data"]
    assert isinstance(sent_bytes, bytes)

    expected_sig = hmac.new(b"my-secret", sent_bytes, hashlib.sha256).hexdigest()
    assert kwargs["headers"]["X-COS-Signature"] == f"sha256={expected_sig}"

    # The body must still be the JSON a receiver expects, and be sent as such.
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert json.loads(sent_bytes)["status"] == "CRITICAL"


def test_webhook_signature_is_wrong_for_a_different_body(posts):
    """
    The negative half: a signature that verified against any body would be no
    signature at all.
    """
    import hashlib
    import hmac

    run(
        CRITICAL_RESULT,
        webhook_url="https://hooks.example.com/x",
        webhook_secret="my-secret",
    )

    _, kwargs = posts[0]
    tampered = json.dumps({**json.loads(kwargs["data"]), "status": "OK"}).encode("utf-8")
    forged = hmac.new(b"my-secret", tampered, hashlib.sha256).hexdigest()

    assert kwargs["headers"]["X-COS-Signature"] != f"sha256={forged}"


def test_webhook_signature_is_not_added_when_secret_is_not_set(posts):
    """No X-COS-Signature header is added when webhook_secret is None."""
    run(CRITICAL_RESULT, webhook_url="https://hooks.example.com/x")

    assert len(posts) == 1
    _, kwargs = posts[0]
    assert "X-COS-Signature" not in kwargs["headers"]


def test_webhook_signature_changes_with_different_secret(posts):
    """Different secrets produce different signatures."""
    run(
        CRITICAL_RESULT,
        webhook_url="https://hooks.example.com/x",
        webhook_secret="secret-1",
    )
    sig1 = posts[0][1]["headers"].get("X-COS-Signature")
    
    posts.clear()
    
    run(
        CRITICAL_RESULT,
        webhook_url="https://hooks.example.com/x",
        webhook_secret="secret-2",
    )
    sig2 = posts[0][1]["headers"].get("X-COS-Signature")
    
    assert sig1 != sig2


def test_webhook_signature_format_is_sha256_hex(posts):
    """The X-COS-Signature header follows the sha256=<hex> format."""
    import re
    
    run(
        CRITICAL_RESULT,
        webhook_url="https://hooks.example.com/x",
        webhook_secret="my-secret",
    )

    assert len(posts) == 1
    _, kwargs = posts[0]
    sig_header = kwargs["headers"]["X-COS-Signature"]
    
    pattern = r"^sha256=[0-9a-f]{64}$"
    assert re.match(pattern, sig_header), f"Invalid signature format: {sig_header}"


def test_generic_webhook_format_is_the_default(posts):
    """No behaviour changes for anyone not opting into the new formats."""
    run(CRITICAL_RESULT, webhook_url="https://hooks.example.com/x")

    _, kwargs = posts[0]
    assert kwargs["json"]["status"] == "CRITICAL"
    assert "attachments" not in kwargs["json"]
    assert "embeds" not in kwargs["json"]


def test_slack_webhook_format_is_a_block_kit_attachment(posts):
    run(
        CRITICAL_RESULT,
        webhook_url="https://hooks.example.com/x",
        webhook_format="slack",
    )

    _, kwargs = posts[0]
    body = kwargs["json"]
    assert list(body.keys()) == ["attachments"]
    attachment = body["attachments"][0]
    assert attachment["color"] == "#a30200"  # CRITICAL, matches webhook-recipes.md
    assert "cloud.example.com" in attachment["text"]
    assert "CRITICAL" in attachment["text"]


def test_slack_webhook_format_colors_every_status(posts):
    run(OK_RESULT, webhook_url="https://x/", webhook_on="always", webhook_format="slack")
    assert posts[0][1]["json"]["attachments"][0]["color"] == "#2eb886"


def test_discord_webhook_format_is_a_single_embed(posts):
    run(
        CRITICAL_RESULT,
        webhook_url="https://hooks.example.com/x",
        webhook_format="discord",
    )

    _, kwargs = posts[0]
    body = kwargs["json"]
    assert list(body.keys()) == ["embeds"]
    embed = body["embeds"][0]
    assert embed["title"].startswith("cloud.example.com - CRITICAL")
    assert embed["color"] == 0xA30200
    field_names = {field["name"] for field in embed["fields"]}
    assert "Rating" in field_names


def test_discord_webhook_format_omits_empty_fields(posts):
    """A failed-scan payload carries only the common fields; nothing crashes on their absence."""
    run(
        {**CRITICAL_RESULT},
        webhook_url="https://hooks.example.com/x",
        webhook_format="discord",
    )
    embed = posts[0][1]["json"]["embeds"][0]
    assert all(field["value"] for field in embed["fields"])


def test_webhook_signature_is_computed_over_the_formatted_body(posts):
    """A receiver verifying HMAC must verify what was actually sent, not the generic document."""
    import hashlib
    import hmac

    run(
        CRITICAL_RESULT,
        webhook_url="https://hooks.example.com/x",
        webhook_format="slack",
        webhook_secret="my-secret",
    )

    _, kwargs = posts[0]
    body_json = json.dumps(kwargs["json"], separators=(",", ":"), sort_keys=True)
    expected_sig = hmac.new(b"my-secret", body_json.encode("utf-8"), hashlib.sha256).hexdigest()
    assert kwargs["headers"]["X-COS-Signature"] == f"sha256={expected_sig}"


def test_webhook_format_survives_a_failed_scan_payload(posts, monkeypatch):
    """The base (failure-shaped) payload has no rating/product fields; formatting must not crash."""
    from opencloud_local_scan.scanner import ScanError

    def _raise_scan_error(*_args, **_kwargs):
        raise ScanError("connection refused")

    monkeypatch.setattr(plugin, "local_scan", _raise_scan_error)
    context = plugin.ScanContext(
        host="unreachable.example.com",
        allow_private_webhooks=True,
        webhook_url="https://hooks.example.com/x",
        webhook_on="always",
        webhook_format="discord",
    )
    with pytest.raises(SystemExit):
        plugin.send_scan_request(context)

    assert len(posts) == 1
    embed = posts[0][1]["json"]["embeds"][0]
    assert embed["title"].startswith("unreachable.example.com")
    assert embed["fields"] == []


# --- webhook digest renderers (--webhook-digest) ---
def _host_payload(host: str, status: str) -> dict:
    return {
        "host": host,
        "status": status,
        "exit_code": int(getattr(NagiosExitCode, status)),
        "message": f"{status}: {host}",
    }


def test_build_digest_webhook_payload_is_flat_and_self_describing():
    payloads = [
        _host_payload("a.example.com", "CRITICAL"),
        _host_payload("b.example.com", "OK"),
    ]

    document = plugin._build_digest_webhook_payload(payloads)

    assert document["digest"] is True
    assert document["host_count"] == 2
    assert document["status"] == "CRITICAL"
    assert document["exit_code"] == int(NagiosExitCode.CRITICAL)
    assert document["hosts"] == payloads
    json.dumps(document)  # must survive a round trip through a JSON transport


def test_slack_digest_omits_ok_hosts_and_counts_them():
    payload = plugin._build_digest_webhook_payload(
        [_host_payload("bad.example.com", "CRITICAL"), _host_payload("ok.example.com", "OK")]
    )

    rendered = plugin._slack_digest_webhook_payload(payload)

    text = rendered["attachments"][0]["text"]
    assert "bad.example.com" in text
    assert "ok.example.com" not in text
    assert "1 host(s) OK, not shown" in text


def test_discord_digest_truncates_a_large_non_ok_host_count():
    """Discord embeds cap at 25 fields; a large fleet must not exceed that."""
    payloads = [_host_payload(f"host{i}.example.com", "CRITICAL") for i in range(30)]
    payload = plugin._build_digest_webhook_payload(payloads)

    rendered = plugin._discord_digest_webhook_payload(payload)

    fields = rendered["embeds"][0]["fields"]
    assert len(fields) <= 25
    assert fields[-1] == {"name": "...", "value": "+10 more", "inline": False}


def test_discord_digest_reports_ok_count_as_a_field():
    payload = plugin._build_digest_webhook_payload(
        [_host_payload("bad.example.com", "CRITICAL"), _host_payload("ok.example.com", "OK")]
    )

    rendered = plugin._discord_digest_webhook_payload(payload)

    fields = {field["name"]: field["value"] for field in rendered["embeds"][0]["fields"]}
    assert fields["OK"] == "1 host(s)"
    assert "bad.example.com - CRITICAL" in fields
