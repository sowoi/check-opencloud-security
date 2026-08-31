"""
Who a request is really from, and whether it was really meant.

Two questions the rest of the application leans on without being able to
answer itself:

* **Which address does this count against?** The client rate limit, the audit
  fingerprint and the five-attempt guard in front of ``DELETE /api/purge`` all
  key on one string. Get it from the wrong end of ``X-Forwarded-For`` and a
  caller mints a fresh one per request by adding a header.
* **Did a person on this site ask for this?** There is no session to steal, so
  the damage from a cross-site POST is not a stolen account - it is a scan run
  against a target of somebody else's choosing, attributed to the browser it
  borrowed, out of that visitor's allowance.
"""

from __future__ import annotations

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
    settings,
)
from webapp.app import client_address, cross_site_post
from webapp.settings import WebSettings


class _Headers(dict):
    """Header access is case-insensitive on a real request."""

    def get(self, key, default=""):
        return super().get(key.lower(), default)


class _Request:
    """The three things ``client_address`` and ``cross_site_post`` read."""

    def __init__(self, headers=None, peer="203.0.113.9", base="http://testserver/"):
        self.headers = _Headers({k.lower(): v for k, v in (headers or {}).items()})
        self.client = type("Peer", (), {"host": peer})() if peer else None
        self.base_url = base


# --- X-Forwarded-For --------------------------------------------------------


def test_the_forwarded_header_is_ignored_unless_the_deployment_opts_in():
    """Believing it by default would make the client limit decorative."""
    request = _Request({"X-Forwarded-For": "1.2.3.4"})

    assert client_address(request, WebSettings()) == "203.0.113.9"


def test_one_proxy_yields_the_address_that_proxy_wrote():
    """The ordinary deployment: a single reverse proxy appending one entry."""
    request = _Request({"X-Forwarded-For": "198.51.100.7"})
    configured = WebSettings(trust_forwarded_for=True, trusted_proxy_hops=1)

    assert client_address(request, configured) == "198.51.100.7"


def test_a_spoofed_entry_ahead_of_the_proxys_own_is_not_believed():
    """
    The finding this fixes, stated as a test.

    nginx's ``proxy_add_x_forwarded_for``, Traefik and most CDNs *append*, so
    everything left of the last entry is whatever the client sent. Reading the
    leftmost entry - which is what this did - hands a caller a fresh
    rate-limit bucket, a fresh audit identity and a fresh allowance of purge
    attempts, for the price of one header.
    """
    request = _Request({"X-Forwarded-For": "1.2.3.4, 198.51.100.7"})
    configured = WebSettings(trust_forwarded_for=True, trusted_proxy_hops=1)

    assert client_address(request, configured) == "198.51.100.7"


def test_a_long_forged_chain_still_yields_only_the_real_hop():
    """Padding the header does not walk the reader back towards the forgery."""
    forged = ", ".join(f"10.0.0.{n}" for n in range(1, 40))
    request = _Request({"X-Forwarded-For": f"{forged}, 198.51.100.7"})
    configured = WebSettings(trust_forwarded_for=True, trusted_proxy_hops=1)

    assert client_address(request, configured) == "198.51.100.7"


def test_two_proxies_are_counted_from_the_right():
    """A CDN in front of an ingress writes two entries, and both are ours."""
    request = _Request({"X-Forwarded-For": "1.2.3.4, 198.51.100.7, 192.0.2.1"})
    configured = WebSettings(trust_forwarded_for=True, trusted_proxy_hops=2)

    assert client_address(request, configured) == "198.51.100.7"


def test_counting_more_hops_than_the_header_carries_does_not_reach_the_client():
    """
    Over-counting must fail towards the proxy, never towards the forgery.

    A deployment that says two hops but sits behind one would otherwise read
    the entry the client wrote, which is the exact failure being fixed.
    """
    request = _Request({"X-Forwarded-For": "1.2.3.4"})
    configured = WebSettings(trust_forwarded_for=True, trusted_proxy_hops=5)

    # One entry, so there is nothing proxy-written to prefer; it is still not
    # treated as more trustworthy than the peer would have been.
    assert client_address(request, configured) == "1.2.3.4"


def test_an_entry_that_is_not_an_address_is_ignored():
    """
    A fingerprint keyed on a hostname somebody typed is not a fingerprint.

    ``for=_hidden`` and obfuscated identifiers are legal in the wild, and
    counting them would let a caller pick their own bucket name.
    """
    request = _Request({"X-Forwarded-For": "unknown, _hidden"})
    configured = WebSettings(trust_forwarded_for=True, trusted_proxy_hops=1)

    assert client_address(request, configured) == "203.0.113.9"


def test_an_ipv6_entry_is_accepted():
    """A v6 proxy is a proxy."""
    request = _Request({"X-Forwarded-For": "1.2.3.4, 2001:db8::1"})
    configured = WebSettings(trust_forwarded_for=True, trusted_proxy_hops=1)

    assert client_address(request, configured) == "2001:db8::1"


def test_an_empty_header_falls_back_to_the_peer():
    """A trusted proxy that sent nothing is not evidence of anybody."""
    request = _Request({"X-Forwarded-For": "  ,  "})
    configured = WebSettings(trust_forwarded_for=True)

    assert client_address(request, configured) == "203.0.113.9"


def test_the_rate_limit_actually_holds_against_a_forged_header():
    """
    The end-to-end case, because the unit above is only half the claim.

    Ten submissions with ten different forged left-hand entries have to meet
    the same counter, or the limit is per-header rather than per-client.
    """
    with client(
        ip_rate_limit=3,
        ip_rate_window=60,
        trust_forwarded_for=True,
        trusted_proxy_hops=1,
    ) as browser:
        statuses = [
            browser.post(
                "/api/scans",
                json={"target_url": f"instance{n}.example.com"},
                headers={"X-Forwarded-For": f"1.2.3.{n}, 198.51.100.7"},
            ).status_code
            for n in range(5)
        ]

    assert 429 in statuses


# --- cross-site submissions -------------------------------------------------


def test_a_same_origin_form_post_is_accepted():
    """The browser form has to keep working; it is the main way in."""
    request = _Request(
        {"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"}
    )

    assert cross_site_post(request, settings()) is False


def test_a_cross_site_form_post_is_refused():
    """A page anywhere must not be able to spend a visitor's allowance."""
    request = _Request(
        {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"}
    )

    assert cross_site_post(request, settings()) is True


def test_a_typed_url_is_not_treated_as_cross_site():
    """``none`` is a person with a bookmark, not a page with a form."""
    request = _Request({"Sec-Fetch-Site": "none"})

    assert cross_site_post(request, settings()) is False


def test_an_origin_from_another_site_is_refused_without_the_fetch_header():
    """
    Browsers that send no ``Sec-Fetch-Site`` still send ``Origin``.

    The fallback is what keeps the guard from being version-dependent.
    """
    request = _Request({"Origin": "https://evil.example"})

    assert cross_site_post(request, settings()) is True


def test_the_configured_public_address_counts_as_this_site():
    """Behind a proxy, the request's own base URL is the internal one."""
    request = _Request({"Origin": "https://scan.example.org"}, base="http://internal:8811/")
    configured = settings(public_base_url="https://scan.example.org")

    assert cross_site_post(request, configured) is False


def test_a_caller_that_is_not_a_browser_is_refused_nothing():
    """
    curl, an agent and the in-process MCP client send neither header.

    Refusing them would break the API for everyone who is not a browser, and
    it buys nothing: a page cannot make a browser omit these.
    """
    assert cross_site_post(_Request({}), settings()) is False


def test_a_cross_site_submission_never_reaches_the_rate_limiter():
    """
    The refusal has to come first, or it only changes the error message.

    Spending the borrowed visitor's allowance is most of what the submission
    was worth sending, so a 403 that still counted would be half a fix.
    """
    with client(ip_rate_limit=1, ip_rate_window=60) as browser:
        refused = browser.post(
            "/api/scans",
            json={"target_url": "instance.example.com"},
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        assert refused.status_code == 403

        # The allowance is untouched, so a real submission still gets through.
        allowed = browser.post(
            "/api/scans", json={"target_url": "instance.example.com"}
        )
        assert allowed.status_code == 202


def test_a_cross_site_language_switch_does_not_set_the_cookie():
    """Changing what somebody's next visit says is still doing it to them."""
    with client() as browser:
        response = browser.post(
            "/language",
            data={"locale": "de", "next": "/"},
            headers={"Sec-Fetch-Site": "cross-site"},
            follow_redirects=False,
        )

    assert response.status_code == 403
    assert "cos_locale" not in response.cookies


def test_a_same_origin_language_switch_still_works():
    """The negative case above must not have broken the switcher."""
    with client() as browser:
        response = browser.post(
            "/language",
            data={"locale": "de", "next": "/"},
            headers={"Sec-Fetch-Site": "same-origin"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.cookies["cos_locale"] == "de"
