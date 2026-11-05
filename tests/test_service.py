"""
Tests for the HTTP scan service.

The service is what runs inside the container: it wraps the built-in scanner
in a small JSON API so several monitoring hosts can share one scanner and
results are cached instead of re-scanned on every poll.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from opencloud_local_scan import service as service_module
from opencloud_local_scan.scanner import ScanError
from opencloud_local_scan.service import (
    ScanStore,
    ServiceMisconfigured,
    build_server,
    ensure_listen_is_safe,
)

RESULT = {"domain": "cloud.example.com", "rating": 5, "version": "7.2.0"}


@pytest.fixture
def fake_scan(monkeypatch):
    """Replace the scanner with a counter, so caching becomes observable."""
    calls = []

    def _scan(host, settings=None, release_settings=None):
        calls.append(host)
        if host == "broken.example.com":
            raise ScanError("Instance did not return a usable status document.")
        return {**RESULT, "domain": host, "call": len(calls)}

    monkeypatch.setattr(service_module, "scan", _scan)
    return calls


@pytest.fixture
def server(fake_scan):
    """Run the scan service on an ephemeral port."""

    def _start(token=None, cache_ttl=900):
        store = ScanStore(cache_ttl=cache_ttl)
        httpd = build_server(store, "127.0.0.1", 0, token)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        return httpd, base, store

    started = []

    def _factory(**kwargs):
        httpd, base, store = _start(**kwargs)
        started.append(httpd)
        return base, store

    yield _factory

    for httpd in started:
        httpd.shutdown()
        httpd.server_close()


def _request(url, data=None, headers=None, method=None):
    body = data.encode() if isinstance(data, str) else data
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read())


def _refusal(url, data=None, headers=None, method=None):
    """The status and body of an error answer, with the answer closed.

    An HTTPError holds the open response. Left to the garbage collector, it is
    closed whenever a later collection runs - after its socket is gone - and
    the ValueError that close raises surfaces as an unraisable-exception
    warning in whichever test happens to be running.
    """
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _request(url, data=data, headers=headers, method=method)
    with excinfo.value as error:
        return error.code, error.read()


def test_healthz_needs_no_token(server):
    """A liveness probe must work without credentials."""
    base, _ = server(token="s3cret")

    status, payload = _request(f"{base}/healthz")

    assert status == 200
    assert payload == {"status": "ok"}


@pytest.mark.parametrize("headers", [
    {"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"},
    {"Origin": "null"}, {"Origin": "https://untrusted.example.com"},
    {"Origin": "http://["},
])
@pytest.mark.parametrize("post", [False, True])
def test_browser_pages_cannot_borrow_the_loopback_scanner(server, fake_scan, headers, post):
    base, _ = server()
    url = f"{base}/api/queue" if post else f"{base}/api/scan?url=opencloud.example.com"
    code, _ = _refusal(url, data="url=opencloud.example.com" if post else None, headers=headers)
    assert code == 403
    assert fake_scan == []


def test_queue_returns_a_uuid_and_result_serves_the_document(server, fake_scan):
    """The two-step flow mirrors the API the plugin family expects."""
    base, _ = server()

    _, queued = _request(f"{base}/api/queue", data="url=cloud.example.com")
    assert "uuid" in queued

    _, result = _request(f"{base}/api/result/{queued['uuid']}")

    assert result["domain"] == "cloud.example.com"
    assert result["rating"] == 5
    assert fake_scan == ["cloud.example.com"]


def test_results_are_cached_per_host(server, fake_scan):
    """Polling twice within the TTL must not scan the instance twice."""
    base, _ = server()

    _request(f"{base}/api/queue", data="url=cloud.example.com")
    _request(f"{base}/api/queue", data="url=cloud.example.com")

    assert fake_scan == ["cloud.example.com"]


def test_requeue_forces_a_fresh_scan(server, fake_scan):
    """An operator who asks for a rescan gets one."""
    base, _ = server()

    _request(f"{base}/api/queue", data="url=cloud.example.com")
    _, requeued = _request(f"{base}/api/requeue", data="url=cloud.example.com")
    _, result = _request(f"{base}/api/result/{requeued['uuid']}")

    assert fake_scan == ["cloud.example.com", "cloud.example.com"]
    assert result["call"] == 2


def test_expired_cache_entries_are_scanned_again(server, fake_scan):
    """A zero TTL means every request is fresh."""
    base, _ = server(cache_ttl=0)

    _request(f"{base}/api/queue", data="url=cloud.example.com")
    _request(f"{base}/api/queue", data="url=cloud.example.com")

    assert len(fake_scan) == 2


def test_scan_endpoint_returns_the_document_directly(server):
    """/api/scan is the convenience route for ad-hoc use."""
    base, _ = server()

    status, result = _request(f"{base}/api/scan?url=cloud.example.com")

    assert status == 200
    assert result["domain"] == "cloud.example.com"


def test_missing_url_parameter_is_a_bad_request(server):
    """A malformed request must be answered, not crash the service."""
    base, _ = server()

    code, _ = _refusal(f"{base}/api/queue", data="")

    assert code == 400


def test_failed_scan_is_reported_as_a_bad_request(server):
    """A target that is not an OpenCloud is the client's problem, not ours."""
    base, _ = server()

    code, body = _refusal(f"{base}/api/queue", data="url=broken.example.com")

    assert code == 400
    assert "status document" in json.loads(body)["error"]


def test_a_newline_in_a_failed_host_cannot_forge_a_log_line(server, monkeypatch, caplog):
    """The host comes from the request body, and the log is evidence an operator reads."""
    base, _ = server()

    def _scan(host, settings=None, release_settings=None):
        raise ScanError(f"Could not resolve {host}.")

    monkeypatch.setattr(service_module, "scan", _scan)
    forged = "INFO opencloud_local_scan.service: Scan of admin succeeded"
    caplog.set_level("INFO", logger=service_module.LOGGER.name)

    code, _ = _refusal(
        f"{base}/api/queue",
        data=urllib.parse.urlencode({"url": f"bad.example.com\n{forged}"}),
    )

    assert code == 400
    messages = [r.getMessage() for r in caplog.records if "failed" in r.getMessage()]
    assert messages, "the failed scan is still logged"
    assert all("\n" not in message for message in messages)
    assert any("bad.example.com\\n" in message for message in messages)


def test_unknown_uuid_is_a_not_found(server):
    """Asking for a scan that never happened returns 404."""
    base, _ = server()

    code, _ = _refusal(f"{base}/api/result/does-not-exist")

    assert code == 404


def test_unknown_endpoint_is_a_not_found(server):
    """The service exposes exactly the documented routes."""
    base, _ = server()

    code, _ = _refusal(f"{base}/api/nonsense")

    assert code == 404


def test_token_is_required_when_configured(server):
    """A shared scanner must not be usable by anyone who can reach it."""
    base, _ = server(token="s3cret")

    code, _ = _refusal(f"{base}/api/queue", data="url=cloud.example.com")

    assert code == 401


def test_correct_token_is_accepted_in_both_forms(server):
    """X-Auth-Token and a bearer Authorization header are equivalent."""
    base, _ = server(token="s3cret")

    status, _ = _request(
        f"{base}/api/queue",
        data="url=cloud.example.com",
        headers={"X-Auth-Token": "s3cret"},
    )
    assert status == 200

    status, _ = _request(
        f"{base}/api/scan?url=other.example.com",
        headers={"Authorization": "Bearer s3cret"},
    )
    assert status == 200


def test_wrong_token_is_rejected(server):
    """A near miss is still a miss."""
    base, _ = server(token="s3cret")

    code, _ = _refusal(
        f"{base}/api/queue",
        data="url=cloud.example.com",
        headers={"X-Auth-Token": "s3cre"},
    )

    assert code == 401


def _status(url, headers):
    try:
        return _request(url, headers=headers)[0]
    except urllib.error.HTTPError as error:
        with error:
            return error.code


def test_a_page_rebound_onto_loopback_cannot_use_a_service_without_a_token(server):
    """
    DNS rebinding turns a browser tab into a client of a loopback service.

    The page's own hostname stays in ``Host``, and without a token that header
    is the only thing telling the operator's request apart from the page's -
    which would otherwise be reading scans of the operator's own network.
    """
    base, _ = server()

    status = _status(f"{base}/api/scan?url=cloud.example.com", {"Host": "rebind.example.net"})

    assert status == 403


@pytest.mark.parametrize("host", ["127.0.0.1:8811", "localhost:8811", "[::1]:8811", "localhost"])
def test_a_request_addressed_to_a_loopback_name_is_still_served(server, host):
    """The operator's own curl, and an SSH tunnel, name the machine they reach."""
    base, _ = server()

    assert _status(f"{base}/api/scan?url=cloud.example.com", {"Host": host}) == 200


def test_a_service_with_a_token_does_not_judge_the_host_header(server):
    """A rebinding page cannot know the token, and a proxy may name any host."""
    base, _ = server(token="s3cret")

    status = _status(
        f"{base}/api/scan?url=cloud.example.com",
        {"Host": "scanner.example.net", "Authorization": "Bearer s3cret"},
    )

    assert status == 200


def test_a_rebound_page_cannot_queue_a_scan_either(server, fake_scan):
    """POST is refused the same way, before anything reaches the scanner."""
    base, _ = server()

    code, _ = _refusal(
        f"{base}/api/queue",
        data="url=cloud.example.com",
        headers={"Host": "rebind.example.net"},
        method="POST",
    )

    assert code == 403
    assert fake_scan == []


def test_responses_carry_nosniff(server):
    """The service itself must not be a soft target."""
    base, _ = server()

    with urllib.request.urlopen(f"{base}/healthz", timeout=5) as response:
        assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_purge_drops_stale_entries(fake_scan):
    """Cache purging keeps a long-running service from growing forever."""
    store = ScanStore(cache_ttl=0)

    entry = store.scan("cloud.example.com")
    store.purge()

    assert store.get_by_uuid(entry.uuid) is None


# --- where this service may listen ------------------------------------------
#
# The scan endpoint takes a hostname from the request and connects to it, with
# no target validation of its own - that lives in `webapp/ssrf.py`, which this
# path never touches. Unauthenticated on a network, that is a request
# forwarder into whatever the monitoring host can reach.


def test_the_service_listens_on_loopback_unless_told_otherwise():
    """
    The default must reach only this machine.

    ADR 0001 moved the Prometheus exporter here for exposing rather less;
    ADR 0030 is why the same now holds for every listener in the project.
    """
    assert service_module.DEFAULT_LISTEN == "127.0.0.1"


# The guard is checked without opening a socket: which addresses are loopback
# is the decision under test, and binding them is the host's business - a CI
# runner with no IPv6, or no spare address in 127/8, would otherwise fail these
# for a reason that has nothing to do with the rule.


@pytest.mark.parametrize("listen", ["127.0.0.1", "::1", "localhost", "127.0.0.5"])
def test_loopback_needs_no_token(listen):
    """
    An operator on their own machine is not made to invent a credential.

    Requiring one here would push people towards `--listen 0.0.0.0` to make
    the nuisance go away, which is the opposite of the point.
    """
    ensure_listen_is_safe(listen, None)


@pytest.mark.parametrize(
    "listen", ["0.0.0.0", "::", "", " ", "192.168.1.10", "10.0.0.4", "some-host"]
)
def test_a_wide_bind_without_a_token_is_refused(listen):
    """
    The negative case, and the whole of this fix.

    Serving is refused rather than logged: an operator who published the port
    meant to publish the service, and would otherwise learn what they
    published from somebody else.
    """
    with pytest.raises(ServiceMisconfigured) as raised:
        ensure_listen_is_safe(listen, None)

    message = str(raised.value)
    assert "COS_SERVICE_TOKEN" in message
    assert "127.0.0.1" in message


@pytest.mark.parametrize("listen", ["0.0.0.0", "::", "192.168.1.10", "some-host"])
def test_a_wide_bind_with_a_token_is_allowed(listen):
    """
    A credential is what makes exposure a decision rather than an accident.

    This is the shipped container's configuration, so it has to keep working.
    """
    ensure_listen_is_safe(listen, "0123456789abcdef" * 4)


@pytest.mark.parametrize("token", ["s3cret", "a", " " * 40, "x" * 31])
def test_a_wide_bind_with_a_guessable_token_is_refused(token):
    """
    Nothing counts failed attempts, so a short token is guessable at line
    rate - and behind it is a service that scans whatever host it is told to.
    """
    with pytest.raises(ServiceMisconfigured, match="shorter than 32"):
        ensure_listen_is_safe("0.0.0.0", token)
    # On loopback the token is optional, so its length is not the guard.
    ensure_listen_is_safe("127.0.0.1", token)
    ensure_listen_is_safe("0.0.0.0", "x" * 32)


def test_the_shipped_example_token_is_refused_on_a_wide_bind():
    """
    It is long enough to pass the length rule and printed in the repository,
    so a copied example that was never replaced would guard nothing.
    """
    from pathlib import Path

    example = (
        Path(__file__).resolve().parent.parent / "secrets" / "scanner_token.example"
    ).read_text(encoding="utf-8")

    with pytest.raises(ServiceMisconfigured, match="example token"):
        ensure_listen_is_safe("0.0.0.0", example)
    ensure_listen_is_safe("127.0.0.1", example)


def test_an_empty_bind_address_is_every_interface_not_loopback():
    """
    A socket bound to "" listens on INADDR_ANY, so it must need a token.

    It used to be listed as loopback, which let the widest bind there is
    through the one check meant to stop an open request forwarder.
    """
    with pytest.raises(ServiceMisconfigured):
        ensure_listen_is_safe("", None)


def test_an_unresolvable_bind_address_counts_as_exposed():
    """
    A hostname nobody here can classify is not evidence of loopback.

    Guessing would mean a name that happens to look harmless opening the
    service to whatever it resolves to later.
    """
    with pytest.raises(ServiceMisconfigured):
        ensure_listen_is_safe("not-a-name.invalid", None)


def test_build_server_applies_the_guard_rather_than_only_documenting_it():
    """
    The check has to be on the path that actually opens the socket.

    A rule enforced only by `serve()` would be missed by every caller that
    builds the server itself, which is how the tests above reach it too.
    """
    with pytest.raises(ServiceMisconfigured):
        build_server(ScanStore(), "0.0.0.0", 0, None)  # nosec B104 - asserting the refusal


def test_a_loopback_server_still_starts(fake_scan):
    """The guard must not have made the ordinary case fail to build."""
    server = build_server(ScanStore(), "127.0.0.1", 0, None)
    server.server_close()
