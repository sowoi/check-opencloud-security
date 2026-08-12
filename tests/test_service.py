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
import urllib.request

import pytest

from opencloud_local_scan import service as service_module
from opencloud_local_scan.scanner import ScanError
from opencloud_local_scan.service import ScanStore, build_server

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


def test_healthz_needs_no_token(server):
    """A liveness probe must work without credentials."""
    base, _ = server(token="s3cret")

    status, payload = _request(f"{base}/healthz")

    assert status == 200
    assert payload == {"status": "ok"}


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

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _request(f"{base}/api/queue", data="")

    assert excinfo.value.code == 400


def test_failed_scan_is_reported_as_a_bad_request(server):
    """A target that is not an OpenCloud is the client's problem, not ours."""
    base, _ = server()

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _request(f"{base}/api/queue", data="url=broken.example.com")

    assert excinfo.value.code == 400
    assert "status document" in json.loads(excinfo.value.read())["error"]


def test_unknown_uuid_is_a_not_found(server):
    """Asking for a scan that never happened returns 404."""
    base, _ = server()

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _request(f"{base}/api/result/does-not-exist")

    assert excinfo.value.code == 404


def test_unknown_endpoint_is_a_not_found(server):
    """The service exposes exactly the documented routes."""
    base, _ = server()

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _request(f"{base}/api/nonsense")

    assert excinfo.value.code == 404


def test_token_is_required_when_configured(server):
    """A shared scanner must not be usable by anyone who can reach it."""
    base, _ = server(token="s3cret")

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _request(f"{base}/api/queue", data="url=cloud.example.com")

    assert excinfo.value.code == 401


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

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _request(
            f"{base}/api/queue",
            data="url=cloud.example.com",
            headers={"X-Auth-Token": "s3cre"},
        )

    assert excinfo.value.code == 401


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
