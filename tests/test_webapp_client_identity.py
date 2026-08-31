"""
Which address a request counts as, when the deployment sits behind a proxy.

Everything that limits a caller keys on the string ``client_address`` returns:
the rate limit, the audit pseudonym and the allowance of purge attempts. So
the question these tests ask is not "does it read the header" but "can the
caller choose what it returns" - and every one of them asserts the negative,
because a fingerprint the client picks is not a fingerprint.
"""

from __future__ import annotations

from dataclasses import replace

from starlette.requests import Request

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    settings,
)
from webapp.app import client_address

PEER = "10.0.0.1"


def _request(forwarded: str | None = None) -> Request:
    """A real request carrying whatever a proxy and a client between them left."""
    headers = [] if forwarded is None else [(b"x-forwarded-for", forwarded.encode())]
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/",
            "query_string": b"",
            "headers": headers,
            "client": (PEER, 51234),
            "server": ("scan.example.org", 443),
        }
    )


def _behind_proxy(hops: int = 1):
    return replace(
        settings(trust_forwarded_for=True), trusted_proxy_hops=hops
    )


def test_the_forwarded_address_is_read_from_the_proxy_written_end():
    """nginx and Traefik append, so the leftmost entry is whatever the client sent."""
    address = client_address(_request("1.2.3.4, 9.9.9.9"), _behind_proxy(hops=1))

    assert address == "9.9.9.9"
    # The negative is the whole point: the entry the client wrote is not it.
    assert address != "1.2.3.4"


def test_a_hop_count_of_zero_cannot_hand_the_choice_back_to_the_client():
    """``entries[-0]`` is ``entries[0]``, which would silently read the client's entry."""
    for hops in (0, -1, -5):
        address = client_address(_request("1.2.3.4, 9.9.9.9"), _behind_proxy(hops=hops))

        assert address == "9.9.9.9", f"hop count {hops} read the wrong end"
        assert address != "1.2.3.4"


def test_one_address_written_three_ways_is_one_rate_limit_bucket():
    """Three spellings of one host must not buy three allowances of anything."""
    spellings = ["[2001:db8::1]", "2001:db8::1", "2001:0DB8:0000::1"]

    seen = {
        client_address(_request(spelling), _behind_proxy(hops=1))
        for spelling in spellings
    }

    assert seen == {"2001:db8::1"}
    assert len(seen) == 1


def test_an_entry_that_is_not_an_address_is_ignored_rather_than_counted():
    """A bucket keyed on a hostname somebody typed is a bucket they chose."""
    address = client_address(_request("not-an-address"), _behind_proxy(hops=1))

    assert address == PEER
    assert address != "not-an-address"


def test_fewer_entries_than_hops_still_reads_a_proxy_written_entry():
    """A request that skipped a proxy must not fall through to the client's entry."""
    address = client_address(_request("9.9.9.9"), _behind_proxy(hops=3))

    assert address == "9.9.9.9"


def test_the_header_is_not_believed_unless_the_deployment_says_so():
    """Believing it by default would make every limit a suggestion."""
    direct = settings(trust_forwarded_for=False)

    address = client_address(_request("1.2.3.4, 9.9.9.9"), direct)

    assert address == PEER
    assert address not in {"1.2.3.4", "9.9.9.9"}


def test_a_request_without_the_header_counts_against_its_peer():
    """The ordinary case still has to work once the header is distrusted."""
    assert client_address(_request(), _behind_proxy(hops=1)) == PEER
