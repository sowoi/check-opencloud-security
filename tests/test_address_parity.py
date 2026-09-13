"""
Every address a name resolves to, dialled one by one.

A scan dials a name once and sees whichever node the resolver put first. The
failure this protects against is a pool where one node missed a rollout: no
HSTS, demo accounts still signing in, an older release - and a scan that
reports the healthy node as the whole deployment. ``tlsAddressParity`` cannot
see it, because it compares only the TLS identity of the two DNS families.

The pool here is real: two fake instances on the same port, one on 127.0.0.1
and one on ::1, behind the name ``localhost`` pinned to both. Nothing is
mocked between the scanner and the sockets, so a test passes only when the
scanner really did connect to each address in turn.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from opencloud_local_scan import scanner as scanner_module
from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.scanner import AddressObservation, ScannerSettings, scan
from tests.fake_opencloud import (
    DEFAULT_HEADERS,
    STATUS_PAYLOAD,
    FakeOpenCloud,
    InstanceBehaviour,
)

NO_UPDATES = ReleaseSettings(mode="off")
NAME = "localhost"


def _ipv6_loopback_available() -> bool:
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
            probe.bind(("::1", 0))
        return True
    except OSError:
        return False


needs_ipv6 = pytest.mark.skipif(
    not _ipv6_loopback_available(), reason="no IPv6 loopback to put a second node on"
)


def _settings(**overrides) -> ScannerSettings:
    values: dict[str, Any] = {
        "scheme": "http",
        "timeout": 3,
        "check_debug_ports": False,
        "include_bundled_db": True,
        "ipv6_enabled": True,
        "pinned_addresses": ((NAME, ("127.0.0.1", "::1")),),
    }
    values.update(overrides)
    return ScannerSettings(**values)


@contextmanager
def _pool(first: InstanceBehaviour, second: InstanceBehaviour) -> Iterator[int]:
    """Two nodes on one port: the first on 127.0.0.1, the second on ::1."""
    with FakeOpenCloud(first) as ipv4:
        # The fake provider names 127.0.0.1 as its issuer unless told otherwise,
        # which on a scan of `localhost` would read as an external provider -
        # and the demo accounts are only ever tried against the built-in one.
        for behaviour in (first, second):
            behaviour.openid_issuer = behaviour.openid_issuer or f"http://{NAME}:{ipv4.port}"
        with FakeOpenCloud(second, address="::1", port=ipv4.port):
            yield ipv4.port


def _lagging_node() -> InstanceBehaviour:
    """The node that missed the rollout."""
    headers = dict(DEFAULT_HEADERS)
    headers.pop("Strict-Transport-Security")
    return InstanceBehaviour(
        headers=headers,
        demo_users=True,
        status_payload={**STATUS_PAYLOAD, "productversion": "7.1.0"},
    )


def _finding(result: dict, check: str) -> dict | None:
    return next((entry for entry in result["extraChecks"] if entry["id"] == check), None)


@needs_ipv6
def test_a_node_that_missed_the_rollout_is_reported_when_every_address_is_dialled():
    """The lagging node's release, headers and demo accounts must all surface."""
    with _pool(InstanceBehaviour(), _lagging_node()) as port:
        result = scan(
            f"{NAME}:{port}",
            settings=_settings(check_all_addresses=True),
            release_settings=NO_UPDATES,
        )

    parity = _finding(result, "addressParity")
    assert parity is not None
    assert parity["passed"] is False
    assert "::1" in parity["detail"]
    assert "version 7.1.0" in parity["detail"]
    assert "Strict-Transport-Security fails" in parity["detail"]
    assert "demo accounts still sign in" in parity["detail"]
    # As serious as the demo accounts are on their own: the rating was built
    # from the node that answered first, which here is the healthy one.
    assert parity["severity"] == scanner_module.DEMO_USER_SEVERITY
    assert [entry["address"] for entry in result["addressObservations"]] == ["127.0.0.1", "::1"]
    assert result["addressObservations"][1]["demoUsersDisabled"] is False


@needs_ipv6
def test_the_same_pool_scans_clean_without_the_option():
    """Off by default, and then the lagging node is exactly as invisible as before."""
    with _pool(InstanceBehaviour(), _lagging_node()) as port:
        result = scan(f"{NAME}:{port}", settings=_settings(), release_settings=NO_UPDATES)

    assert _finding(result, "addressParity") is None
    assert result["addressObservations"] == []
    demo = _finding(result, "demoUsersDisabled")
    assert demo is not None and demo["passed"] is True


@needs_ipv6
def test_a_pool_that_serves_the_same_instance_everywhere_passes():
    """Identical nodes must not produce a difference, or people learn to ignore it."""
    with _pool(InstanceBehaviour(), InstanceBehaviour()) as port:
        result = scan(
            f"{NAME}:{port}",
            settings=_settings(check_all_addresses=True),
            release_settings=NO_UPDATES,
        )

    parity = _finding(result, "addressParity")
    assert parity is not None
    assert parity["passed"] is True
    assert len(result["addressObservations"]) == 2
    assert all(entry["reachable"] for entry in result["addressObservations"])


@needs_ipv6
def test_a_waived_header_is_not_a_difference_between_nodes():
    """An operator who waived a header has said they will not act on it anywhere."""
    headers = dict(DEFAULT_HEADERS)
    headers.pop("Strict-Transport-Security")
    with _pool(InstanceBehaviour(), InstanceBehaviour(headers=headers)) as port:
        waived = scan(
            f"{NAME}:{port}",
            settings=_settings(
                check_all_addresses=True,
                ignore_hardenings=("Strict-Transport-Security", "hsts*"),
            ),
            release_settings=NO_UPDATES,
        )
        unwaived = scan(
            f"{NAME}:{port}",
            settings=_settings(check_all_addresses=True),
            release_settings=NO_UPDATES,
        )

    assert _finding(waived, "addressParity")["passed"] is True
    assert _finding(unwaived, "addressParity")["passed"] is False
    assert _finding(unwaived, "addressParity")["severity"] == "medium"


def test_a_resolved_address_that_does_not_answer_fails_parity():
    """A node in DNS that nobody can reach is a node every n-th visitor fails on."""
    with FakeOpenCloud() as instance:
        # 192.0.2.0/24 is TEST-NET-1: routable nowhere, so the dial fails.
        result = scan(
            f"{NAME}:{instance.port}",
            settings=_settings(
                check_all_addresses=True,
                timeout=1,
                pinned_addresses=((NAME, ("127.0.0.1", "192.0.2.1")),),
            ),
            release_settings=NO_UPDATES,
        )

    parity = _finding(result, "addressParity")
    assert parity is not None
    assert parity["passed"] is False
    assert "192.0.2.1" in parity["detail"]


def test_a_single_address_has_nothing_to_compare_and_is_not_dialled_again(monkeypatch):
    """One address is most deployments: no finding, and no second round of requests."""
    dialled: list[str] = []
    original = scanner_module._observe_address

    def spy(base_url, hostname, address, settings):
        dialled.append(address)
        return original(base_url, hostname, address, settings)

    monkeypatch.setattr(scanner_module, "_observe_address", spy)
    with FakeOpenCloud() as instance:
        result = scan(
            f"{NAME}:{instance.port}",
            settings=_settings(
                check_all_addresses=True, pinned_addresses=((NAME, ("127.0.0.1",)),)
            ),
            release_settings=NO_UPDATES,
        )

    assert dialled == []
    assert _finding(result, "addressParity") is None


def test_a_pinned_scan_dials_only_the_pinned_addresses_and_never_resolves(monkeypatch):
    """
    The web application's SSRF guard is a pin. Widening a pinned scan to what
    the resolver says would dial addresses nobody vetted.
    """
    real_getaddrinfo = socket.getaddrinfo

    def refuse(host, *args, **kwargs):
        # Connecting to a pinned IP literal still passes through getaddrinfo;
        # looking the *name* up is what would widen the scan.
        if host == NAME:
            raise AssertionError("a pinned scan must not ask the resolver")
        return real_getaddrinfo(host, *args, **kwargs)

    dialled: list[str] = []
    monkeypatch.setattr(scanner_module.socket, "getaddrinfo", refuse)
    monkeypatch.setattr(
        scanner_module,
        "_observe_address",
        lambda base_url, hostname, address, settings: dialled.append(address)
        or AddressObservation(address=address, reachable=True),
    )
    with FakeOpenCloud() as instance:
        scan(
            f"{NAME}:{instance.port}",
            settings=_settings(
                check_all_addresses=True,
                pinned_addresses=((NAME, ("127.0.0.1", "::1")),),
            ),
            release_settings=NO_UPDATES,
        )

    assert dialled == ["127.0.0.1", "::1"]


def test_ipv6_addresses_are_left_out_when_the_scanner_has_no_route():
    """A timeout that belongs to the machine running the scan is not the instance's fault."""
    settings = ScannerSettings(ipv6_enabled=False, check_all_addresses=True)
    addresses = {"ipv4": ["198.51.100.7"], "ipv6": ["2001:db8::7", "2001:db8::8"]}

    assert scanner_module._addresses_to_compare(settings, addresses) == ["198.51.100.7"]
    assert not scanner_module._content_parity_may_run(settings, addresses)
    assert scanner_module._content_parity_may_run(
        ScannerSettings(ipv6_enabled=True, check_all_addresses=True), addresses
    )


def test_a_node_on_another_release_raises_the_severity_but_drift_alone_does_not():
    """A different release may be the one the advisories apply to; a header is drift."""
    base = AddressObservation(
        address="198.51.100.1",
        reachable=True,
        version="7.2.3",
        headers={"X-Frame-Options": True},
    )
    older = AddressObservation(
        address="198.51.100.2",
        reachable=True,
        version="7.1.0",
        headers={"X-Frame-Options": True},
    )
    drifted = AddressObservation(
        address="198.51.100.3",
        reachable=True,
        version="7.2.3",
        headers={"X-Frame-Options": False},
    )

    release = scanner_module._content_parity_finding([base, older])
    drift = scanner_module._content_parity_finding([base, drifted])

    assert release is not None and release.severity == "high"
    assert drift is not None and drift.severity == "medium" and drift.passed is False
