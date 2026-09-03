"""
Whether an instance builds its public URLs from a host the caller chose.

Every other check in this scan reads what the instance volunteers. This one
asks a question the instance cannot answer by accident: it requests the
OpenID Connect discovery document while claiming to have arrived at a host
that does not exist, once through the request's own ``Host`` and once through
``X-Forwarded-Host``, and looks for that host in the answer. An instance that
knows its own address answers with it whatever the caller claimed; one that
was never told derives an issuer and a set of endpoints from each request,
and a caller who picks the host has picked where the next sign-in goes.

The failure mode this file exists to rule out is the opposite one. A server
that refuses an unknown virtual host commonly *names it* in the error page,
so a check that searched the body for the probe host would report the correct
behaviour as the finding. Only somewhere a client would actually be sent
counts - the redirect target, or a URL the document publishes - and
``test_a_body_that_merely_mentions_the_host_is_not_a_finding`` is what keeps
it that way.
"""

from __future__ import annotations

import requests

from opencloud_local_scan import scanner as scanner_module
from opencloud_local_scan.scanner import FORWARDED_HOST_PROBE, failed_extra_checks
from tests.fake_opencloud import InstanceBehaviour
from tests.test_local_scanner import run_scan


def _finding(result: dict, identifier: str) -> dict:
    """The one extra check with this id, so a missing one fails loudly."""
    matches = [entry for entry in result["extraChecks"] if entry["id"] == identifier]
    assert len(matches) == 1, f"expected exactly one {identifier}, got {matches}"
    return matches[0]


def test_an_instance_that_knows_its_own_address_passes():
    """
    The negative case, and the one every healthy deployment is in.

    A configured OC_URL means the discovery document reads the same whoever
    asks for it, so claiming a host that does not exist changes nothing.
    """
    result = run_scan(InstanceBehaviour())
    finding = _finding(result, "forwardedHostIgnored")

    assert finding["passed"] is True
    assert FORWARDED_HOST_PROBE not in finding["detail"]
    assert "forwardedHostIgnored" not in failed_extra_checks(result)


def test_a_host_the_caller_invented_coming_back_in_the_issuer_fails():
    """
    The finding itself: the caller decided where the next sign-in goes.

    Both headers are reported, because the mistake behind each is a different
    one - an instance with no public address of its own, or a proxy handing a
    stranger's header to one that has - and an operator who is told only that
    "a host was repeated" has to find out which before they can fix it.
    """
    result = run_scan(InstanceBehaviour(forwarded_host_trusted=True))
    finding = _finding(result, "forwardedHostIgnored")

    assert finding["passed"] is False
    assert finding["severity"] == "medium"
    assert "Host comes back as the issuer it publishes" in finding["detail"]
    assert "X-Forwarded-Host comes back as the issuer it publishes" in finding["detail"]
    assert "forwardedHostIgnored" in failed_extra_checks(result)


def test_a_redirect_to_the_invented_host_fails_just_as_a_document_does():
    """
    An instance that redirects discovery to its issuer reflects it there.

    The evidence has to name the redirect rather than a field, because the
    two are fixed in different places: one is a document built from the
    request, the other a Location built from it.
    """
    behaviour = InstanceBehaviour(forwarded_host_trusted=True, openid_redirect=True)

    finding = _finding(run_scan(behaviour), "forwardedHostIgnored")

    assert finding["passed"] is False
    assert "comes back as the address it redirects to" in finding["detail"]
    assert "it publishes" not in finding["detail"]


def test_an_instance_with_no_discovery_document_is_not_judged_at_all():
    """
    Nothing answered, so nothing was learned - which is not the same as a pass.

    Reporting this instance as having ignored the host would be a clean
    result derived from two 404s, and the operator would read a guarantee
    nobody measured.
    """
    result = run_scan(InstanceBehaviour(openid_configuration=False))

    assert not [
        entry for entry in result["extraChecks"] if entry["id"] == "forwardedHostIgnored"
    ]


def test_a_body_that_merely_mentions_the_host_is_not_a_finding():
    """
    The false positive this check is shaped around.

    A default virtual host refusing a name it does not recognise usually
    prints that name back, and a server behaving correctly must not be read
    as the one misbehaviour this check looks for. Only a URL a client would
    be sent to counts.
    """
    response = requests.Response()
    response.status_code = 200
    response.headers["Content-Type"] = "text/html"
    response._content = (
        f"<html><body>Unknown host {FORWARDED_HOST_PROBE}</body></html>".encode()
    )

    assert scanner_module._forwarded_host_repeated(response) == ""

    published = requests.Response()
    published.status_code = 200
    published.headers["Content-Type"] = "application/json"
    published._content = (
        f'{{"issuer": "https://{FORWARDED_HOST_PROBE}"}}'.encode()
    )

    assert scanner_module._forwarded_host_repeated(published) == (
        "the issuer it publishes"
    )


def test_the_probe_host_can_never_name_a_real_site():
    """
    The request carries a host somebody else's server will log.

    '.invalid' is reserved by RFC 2606 and resolves nowhere, so the name in
    that log points at nothing and nobody can register it and collect what a
    misconfigured instance sends.
    """
    assert FORWARDED_HOST_PROBE.endswith(".invalid")
