"""
The observations that are reported but never held against a deployment.

``setup.advisoryChecks`` is the sibling of ``setup.advisoryHeaders`` for what
is not a response header, and it exists for the same reason: no OpenCloud
publishes a ``security.txt`` on any instance, so counting its absence would
hand every ``--check-hardening`` user a permanent WARNING describing the
software rather than their deployment.

The trap this check has to survive is specific to it. OpenCloud's frontend
answers unknown paths with its own single-page shell, so a check that trusted
the status code would report every instance in existence as publishing a
security policy - the most confident possible way to be wrong. See ADR 0034.
"""

from __future__ import annotations

from dataclasses import replace

from check_opencloud_security import (
    _absent_advisory_checks,
    _collect_missing_hardenings,
)
from opencloud_local_scan.scanner import ADVISORY_CHECK_IDS
from tests.fake_opencloud import InstanceBehaviour
from tests.test_local_scanner import SETTINGS, run_scan

POLICY = (
    "Contact: mailto:security@example.com\n"
    "Expires: 2030-01-01T00:00:00.000Z\n"
    "Preferred-Languages: en, de\n"
)


def test_a_stock_instance_reports_no_security_txt():
    """OpenCloud serves none, so the block has to say so rather than being
    empty - an empty block would read as 'nothing to improve'."""
    result = run_scan(InstanceBehaviour())

    checks = result["setup"]["advisoryChecks"]

    assert set(checks) == set(ADVISORY_CHECK_IDS)
    assert checks["securityTxtPublished"] is False


def test_an_instance_that_publishes_one_is_credited():
    """The negative case: without it the check would pass by only ever being
    able to report absence."""
    behaviour = InstanceBehaviour(security_txt=(POLICY, "text/plain; charset=utf-8"))

    checks = run_scan(behaviour)["setup"]["advisoryChecks"]

    assert checks["securityTxtPublished"] is True


def test_the_single_page_shell_is_not_mistaken_for_a_policy():
    """
    The whole reason the check reads the body. An instance that answers every
    unknown path with its own HTML shell returns 200 for the well-known path
    too, and crediting that would report a reporting channel that does not
    exist - on every OpenCloud deployed behind a catch-all route.
    """
    behaviour = InstanceBehaviour(catch_all=True)

    checks = run_scan(behaviour)["setup"]["advisoryChecks"]

    assert checks["securityTxtPublished"] is False


def test_a_file_without_a_contact_field_is_not_a_policy():
    """
    'Contact' is the one field RFC 9116 makes mandatory, because it is the
    only one that tells a finder where to send anything. A file that omits it
    is a file, not a way to report a vulnerability.
    """
    behaviour = InstanceBehaviour(
        security_txt=("Expires: 2030-01-01T00:00:00.000Z\n", "text/plain")
    )

    checks = run_scan(behaviour)["setup"]["advisoryChecks"]

    assert checks["securityTxtPublished"] is False


def test_a_policy_served_as_markup_is_not_credited():
    """
    A proxy that rewrites the path into a rendered page has not published a
    machine-readable policy, whatever the body happens to contain - and this
    is the case that keeps the shell test above from passing by accident on
    the content type alone.
    """
    behaviour = InstanceBehaviour(
        security_txt=(f"<html><pre>{POLICY}</pre></html>", "text/html")
    )

    checks = run_scan(behaviour)["setup"]["advisoryChecks"]

    assert checks["securityTxtPublished"] is False


def test_an_absent_security_txt_is_never_a_missing_hardening():
    """
    The invariant the separate block exists for. If this ever joins the
    hardening list, every instance in the world gains a finding whose fix is
    a file nobody asked for, and the hardening line becomes noise.
    """
    result = run_scan(InstanceBehaviour())

    missing = _collect_missing_hardenings(result)

    for name in ADVISORY_CHECK_IDS:
        assert name not in missing, name

    # The negative case: an ordinary hardening still reaches that list, so
    # this is not passing because the list is empty.
    stripped = run_scan(InstanceBehaviour(headers={"Content-Type": "text/html"}))
    assert "X-Frame-Options" in _collect_missing_hardenings(stripped)


def test_the_explanation_still_names_it():
    """
    Keeping it out of the alert must not mean hiding it: an operator asking
    for the long form is told what could be added and why.
    """
    result = run_scan(InstanceBehaviour())

    assert _absent_advisory_checks(result) == ["securityTxtPublished"]


def test_a_scan_without_extra_checks_reports_nothing_rather_than_a_failure():
    """
    An observation nobody made is not an observation that failed. Reporting
    False here would tell a reader the instance publishes no policy when the
    truth is that the scan never asked.
    """
    result = run_scan(InstanceBehaviour(), settings=replace(SETTINGS, extra_checks=False))

    assert result["setup"]["advisoryChecks"] == {}
    assert _absent_advisory_checks(result) == []


def test_a_result_without_the_block_is_read_as_having_nothing_to_say():
    """
    A document from an older scanner, or from a scan that failed before the
    block was written, must not crash the explanation - the plugin reads
    results it did not necessarily produce.
    """
    assert _absent_advisory_checks({}) == []
    assert _absent_advisory_checks({"setup": {}}) == []
    assert _absent_advisory_checks({"setup": {"advisoryChecks": "nonsense"}}) == []
