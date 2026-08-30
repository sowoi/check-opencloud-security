"""
The checks that ask what an instance grants somebody who is not its user.

Three questions share this file because they share a shape: each one sends a
request a browser would send on a foreign page's behalf, and reads what comes
back rather than what the instance says about itself.

* **CORS** - who may read an authenticated response. OpenCloud ships
  ``OC_CORS_ALLOW_ORIGINS='*'`` with ``OC_CORS_ALLOW_CREDENTIALS=true``, and a
  middleware given both commonly reflects whatever Origin it was sent, which
  is the arrangement browsers exist to prevent. The severity has to follow the
  credentials flag, because that is the difference between "any site can read
  a signed-in user's files" and "any site can read what it could already
  fetch".
* **TRACE** - whether the server will echo the request, session cookie and
  all, into a body a script can read.
* **Cookie prefixes** - whether the name itself carries the one protection a
  browser applies before any attribute is consulted.

Every expectation below is derived from a real scan of ``fake_opencloud``
rather than from a hardcoded list, so a finding that stops being produced
fails a test rather than quietly disappearing.
"""

from __future__ import annotations

import pytest

from opencloud_local_scan.scanner import CORS_PROBE_ORIGIN
from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour
from tests.test_local_scanner import NO_UPDATES, SETTINGS, run_scan


def _finding(result: dict, identifier: str) -> dict:
    """The one extra check with this id, so a missing one fails loudly."""
    matches = [entry for entry in result["extraChecks"] if entry["id"] == identifier]
    assert len(matches) == 1, f"expected exactly one {identifier}, got {matches}"
    return matches[0]


# --------------------------------------------------------------------------
# Cross-origin resource sharing
# --------------------------------------------------------------------------


def test_reflecting_a_foreign_origin_with_credentials_is_critical():
    """
    This is the whole point of the check.

    A policy that echoes back any Origin *and* allows credentials lets a page
    the visitor merely opened have their browser attach its OpenCloud session
    and hand the reply back - the file listing, the user directory, a share.
    Nothing else in this scan is reachable with so little effort, so it has to
    outrank the same policy without credentials.
    """
    behaviour = InstanceBehaviour(
        cors_allow_origin="reflect", cors_allow_credentials=True
    )

    finding = _finding(run_scan(behaviour), "corsOriginRestricted")

    assert finding["passed"] is False
    assert finding["severity"] == "critical"
    assert CORS_PROBE_ORIGIN in finding["detail"]


def test_reflecting_a_foreign_origin_without_credentials_is_only_medium():
    """
    The negative half of the test above.

    Without credentials the same reflected origin exposes what an
    unauthenticated caller could already fetch. Rating it critical anyway
    would put a deployment that merely opens a public API next to one that has
    handed over its sessions, and an operator who learns the two look alike
    stops reading the severity at all.
    """
    behaviour = InstanceBehaviour(
        cors_allow_origin="reflect", cors_allow_credentials=False
    )

    finding = _finding(run_scan(behaviour), "corsOriginRestricted")

    assert finding["passed"] is False
    assert finding["severity"] == "medium"


def test_a_wildcard_with_credentials_is_reported_below_a_reflected_origin():
    """
    Browsers refuse the pair outright, so the request fails rather than
    succeeding dangerously - a real misconfiguration, but not the one that
    leaks anything. Reporting it at the same severity as a reflected origin
    would be scoring the intent instead of the effect.
    """
    behaviour = InstanceBehaviour(cors_allow_origin="*", cors_allow_credentials=True)

    finding = _finding(run_scan(behaviour), "corsOriginRestricted")

    assert finding["passed"] is False
    assert finding["severity"] == "medium"
    assert "refuse this pair" in finding["detail"]


def test_an_instance_that_grants_no_foreign_origin_passes():
    """
    The negative case that keeps the check honest: an instance sending no
    Access-Control-Allow-Origin must pass, or the finding would be reporting
    that CORS exists rather than that it is open.
    """
    finding = _finding(run_scan(InstanceBehaviour()), "corsOriginRestricted")

    assert finding["passed"] is True
    assert finding["severity"] == "critical"


def test_an_origin_granted_to_somebody_else_is_not_our_finding():
    """
    A policy naming one specific trusted origin is the configuration this
    check asks operators to move to. Flagging it would mean the check can
    never be satisfied.
    """
    behaviour = InstanceBehaviour(
        cors_allow_origin="https://office.example.com", cors_allow_credentials=True
    )

    finding = _finding(run_scan(behaviour), "corsOriginRestricted")

    assert finding["passed"] is True


def test_the_cors_probe_origin_can_never_belong_to_anybody():
    """
    The probe announces itself to a stranger's server, so the name it uses has
    to be one that cannot be registered and cannot resolve - otherwise this
    project would be handing out a hostname somebody could buy and start
    collecting scan traffic on.
    """
    assert CORS_PROBE_ORIGIN.startswith("https://")
    assert CORS_PROBE_ORIGIN.endswith(".invalid")


def test_a_granted_null_origin_is_treated_as_granting_everybody():
    """
    'null' is what a sandboxed iframe sends, and any page can put itself in
    one - so an allow-list containing it is an allow-list containing the
    internet, and it has to be read that way rather than as a named origin.
    """
    behaviour = InstanceBehaviour(
        cors_allow_origin="null", cors_allow_credentials=True
    )

    finding = _finding(run_scan(behaviour), "corsOriginRestricted")

    assert finding["passed"] is False
    assert finding["severity"] == "critical"


# --------------------------------------------------------------------------
# The TRACE method
# --------------------------------------------------------------------------


def test_an_echoed_trace_request_is_a_finding():
    """
    An echoed TRACE hands a script the headers it is forbidden to read -
    the session cookie among them - as ordinary response text.
    """
    finding = _finding(run_scan(InstanceBehaviour(trace_enabled=True)), "traceMethodDisabled")

    assert finding["passed"] is False
    assert finding["severity"] == "medium"
    assert "echoed" in finding["detail"]


def test_a_refused_trace_request_passes():
    """The negative case: OpenCloud does not implement TRACE, so a stock
    instance must pass rather than the check reporting every deployment."""
    finding = _finding(run_scan(InstanceBehaviour()), "traceMethodDisabled")

    assert finding["passed"] is True
    assert "405" in finding["detail"]


def test_a_catch_all_page_answering_trace_is_not_mistaken_for_an_echo():
    """
    An OpenCloud frontend answers unknown requests with its own HTML shell and
    HTTP 200. Reading that as an echo would report the finding on every single
    page application in existence, which is the same trap the exposed-path
    checks guard against.
    """
    behaviour = InstanceBehaviour(catch_all=True, trace_enabled=False)

    finding = _finding(run_scan(behaviour), "traceMethodDisabled")

    assert finding["passed"] is True


def test_the_scanner_sends_trace_and_nothing_less_safe():
    """
    TRACE is safe by RFC 9110 - it echoes and changes nothing - which is what
    makes probing for it acceptable in a plugin that may run every minute.
    This is the test that fails if the probe is ever widened into a method
    that could alter the instance.
    """
    behaviour = InstanceBehaviour()

    with FakeOpenCloud(behaviour) as instance:
        from opencloud_local_scan.scanner import scan

        scan(instance.host, settings=SETTINGS, release_settings=NO_UPDATES)

    methods = {entry[0] for entry in behaviour.seen}

    assert "TRACE" in methods
    assert methods <= {"GET", "HEAD", "PROPFIND", "TRACE"}


# --------------------------------------------------------------------------
# Cookie name prefixes
# --------------------------------------------------------------------------


def test_a_cookie_without_a_name_prefix_is_reported():
    """
    Secure and HttpOnly stop a cookie being *read*; neither stops one being
    written. A sibling subdomain can overwrite an unprefixed session cookie
    however carefully those flags were set, and the prefix is the only thing
    that prevents it.
    """
    behaviour = InstanceBehaviour(
        set_cookies=("oc_sessionpassphrase=abc; Secure; HttpOnly; SameSite=Lax; Path=/",)
    )

    finding = _finding(run_scan(behaviour), "cookiePrefix")

    assert finding["passed"] is False
    assert finding["severity"] == "low"
    assert "__Host-" in finding["detail"]


def test_a_correctly_prefixed_cookie_passes():
    """The negative case, without which the test above would pass on a
    check that always fails."""
    behaviour = InstanceBehaviour(
        set_cookies=("__Host-session=abc; Secure; HttpOnly; SameSite=Lax; Path=/",)
    )

    finding = _finding(run_scan(behaviour), "cookiePrefix")

    assert finding["passed"] is True


@pytest.mark.parametrize(
    ("cookie", "problem"),
    [
        ("__Host-session=a; Secure; Path=/; Domain=example.com", "a Domain attribute"),
        ("__Host-session=a; Secure; Path=/app", "Path is not /"),
        ("__Host-session=a; Path=/", "no Secure"),
        ("__Secure-session=a; Path=/", "no Secure"),
    ],
)
def test_a_cookie_that_breaks_the_prefix_it_claims_is_reported(cookie, problem):
    """
    A prefix a cookie does not honour is worse than no prefix: the browser
    rejects the cookie outright, so the session silently does not work. The
    detail has to name which rule was broken, because 'rejected by the
    browser' is not something an operator can act on.
    """
    finding = _finding(run_scan(InstanceBehaviour(set_cookies=(cookie,))), "cookiePrefix")

    assert finding["passed"] is False
    assert problem in finding["detail"]


def test_an_instance_that_sets_no_cookie_reports_nothing_about_cookies():
    """
    A stock OpenCloud sets no cookie on the public page, and inventing a
    finding for a cookie that does not exist would put a permanent mark on
    every instance - the noise that trains operators to skip the whole
    section.
    """
    ids = {entry["id"] for entry in run_scan(InstanceBehaviour())["extraChecks"]}

    assert "cookiePrefix" not in ids
    assert "cookieSecure" not in ids
