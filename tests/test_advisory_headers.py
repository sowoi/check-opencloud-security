"""
The headers that are reported but never held against a deployment.

``Permissions-Policy``, the two Cross-Origin policies and
``Cross-Origin-Embedder-Policy`` are worth having and OpenCloud sends none of
them. That combination is what makes them a different kind of finding from
everything under ``setup.headers``: a missing ``X-Frame-Options`` means
something in front of this instance stripped a header OpenCloud's proxy sets,
which is a fact about this deployment, while a missing ``Permissions-Policy``
is the shipped state of every OpenCloud there has ever been.

So they are measured into their own block and kept out of the alert. The
tests here are the ones that have to fail if that ever stops being true,
because the failure mode is quiet in both directions: promote them and every
``--check-hardening`` user gets a permanent WARNING nobody can clear, drop
them and four real improvements silently stop being suggested. See ADR 0028.
"""

from __future__ import annotations

from check_opencloud_security import (
    _absent_advisory_headers,
    _collect_missing_hardenings,
)
from opencloud_local_scan.scanner import ADVISORY_HEADERS
from tests.fake_opencloud import InstanceBehaviour
from tests.test_local_scanner import run_scan


def test_a_stock_instance_reports_every_advisory_header_as_absent():
    """OpenCloud sends none of them, so the block has to say so rather than
    being empty - an empty block would read as 'nothing to improve'."""
    result = run_scan(InstanceBehaviour())

    advisory = result["setup"]["advisoryHeaders"]

    assert set(advisory) == set(ADVISORY_HEADERS)
    assert all(present is False for present in advisory.values())


def test_an_instance_that_sends_them_is_credited():
    """The negative case: without it the block would pass a check that can
    only ever report absence."""
    behaviour = InstanceBehaviour(
        extra_headers={
            "Permissions-Policy": "camera=(), microphone=()",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Cross-Origin-Resource-Policy": "same-site",
            "Cross-Origin-Embedder-Policy": "require-corp",
        }
    )

    advisory = run_scan(behaviour)["setup"]["advisoryHeaders"]

    assert all(present is True for present in advisory.values())


def test_a_header_whose_value_restricts_nothing_is_not_credited():
    """
    'Cross-Origin-Opener-Policy: unsafe-none' is the browser default written
    out, and 'Cross-Origin-Resource-Policy: cross-origin' is the absence of
    the restriction. Accepting any non-empty value would let a deployment
    score a pass for sending a header that changes nothing.
    """
    behaviour = InstanceBehaviour(
        extra_headers={
            "Cross-Origin-Opener-Policy": "unsafe-none",
            "Cross-Origin-Resource-Policy": "cross-origin",
            "Cross-Origin-Embedder-Policy": "unsafe-none",
            "Permissions-Policy": "camera=()",
        }
    )

    advisory = run_scan(behaviour)["setup"]["advisoryHeaders"]

    assert advisory["Cross-Origin-Opener-Policy"] is False
    assert advisory["Cross-Origin-Resource-Policy"] is False
    assert advisory["Cross-Origin-Embedder-Policy"] is False
    # The one real value in the same response still passes, so this is about
    # the values and not about the whole block failing.
    assert advisory["Permissions-Policy"] is True


def test_an_absent_advisory_header_is_never_a_missing_hardening():
    """
    This is the invariant the whole separation exists for. If these ever join
    the hardening list, every instance in the world gains three findings no
    setting can clear and every --check-hardening run becomes a WARNING.
    """
    result = run_scan(InstanceBehaviour())

    missing = _collect_missing_hardenings(result)

    for name in ADVISORY_HEADERS:
        assert name not in missing, name

    # And the negative case: the ordinary headers still reach that list, so
    # this is not passing because the list is empty.
    stripped = run_scan(InstanceBehaviour(headers={"Content-Type": "text/html"}))
    assert "X-Frame-Options" in _collect_missing_hardenings(stripped)


def test_the_explanation_still_names_them():
    """
    Keeping them out of the alert must not mean hiding them: an operator who
    asks for the long form should be told what could be added and why.
    """
    result = run_scan(InstanceBehaviour())

    assert _absent_advisory_headers(result) == sorted(ADVISORY_HEADERS)


def test_a_result_without_the_block_is_read_as_having_nothing_to_say():
    """
    A result document from an older scanner, or from a scan that failed
    before the headers were read, must not crash the explanation - the plugin
    reads results it did not necessarily produce.
    """
    assert _absent_advisory_headers({}) == []
    assert _absent_advisory_headers({"setup": {}}) == []
    assert _absent_advisory_headers({"setup": {"advisoryHeaders": "nonsense"}}) == []
