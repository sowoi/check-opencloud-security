"""
The transport facts that sit beside the grade.

Somebody who scans their own instance is very often there to find out one
thing: when the certificate expires. Burying that at the bottom of the page,
under the findings and the hardening list, answers the question only for the
reader who scrolls. These tests protect the promotion - and they protect the
part that is easy to get wrong while doing it, which is that the web layer
must not decide for itself whether a certificate is acceptable. Every tone on
the page is the pass or fail the scanner already recorded.

The observations come from a real loopback TLS server with a certificate
generated for the occasion, so the dates, the chain and the verdicts are the
library's own rather than a fixture somebody typed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from opencloud_local_scan import tls
from tests.test_tls import TIMEOUT, _certificate, _server
from webapp.catalog import summarise

pytest.importorskip("fastapi", reason="the web extra is not installed")


def _document(inspection: tls.TlsInspection, *, min_days: int = 14) -> dict:
    """A result document carrying one real inspection, as the scanner writes it."""
    return {
        "rating": 3,
        "tls": inspection.as_dict(),
        "extraChecks": [
            {
                "id": check.identifier,
                "severity": check.severity,
                "passed": check.passed,
                "detail": check.detail,
                "ignored": False,
            }
            for check in inspection.checks(min_days=min_days)
        ],
    }


def _inspect(certificate_path, key_path) -> tls.TlsInspection:
    with _server(certificate_path, key_path) as port:
        return tls.inspect(
            "localhost", port, TIMEOUT, probe_deprecated=False, check_stapling=False
        )


def _facts(summary) -> dict:
    return {fact["id"]: fact for fact in summary["tlsOverview"]}


def test_the_overview_leads_with_the_protocol_expiry_and_chain(tmp_path):
    """The three transport facts somebody scans for should not need a scroll."""
    summary = summarise(_document(_inspect(*_certificate(tmp_path))))
    facts = _facts(summary)

    assert set(facts) == {"protocol", "expiry", "chain"}
    certificate = summary["tls"]["certificate"]
    assert facts["expiry"]["value"] == certificate["notAfter"]
    assert str(certificate["daysRemaining"]) in facts["expiry"]["detail"]
    assert facts["protocol"]["value"] == summary["tls"]["protocol"]


def test_an_expiring_certificate_is_marked_by_the_scanners_verdict_not_a_new_rule(
    tmp_path,
):
    """
    The colour beside a certificate must be the scan's answer, not a second one.

    A threshold invented in the web layer would disagree with the plugin the
    day an operator changed `--tls-min-days`, and the page would then contradict
    the alert the same scan produced.
    """
    now = datetime.now(timezone.utc)
    soon = _certificate(
        tmp_path, not_before=now - timedelta(days=40), not_after=now + timedelta(days=5)
    )
    inspection = _inspect(*soon)

    generous = _facts(summarise(_document(inspection, min_days=1)))
    strict = _facts(summarise(_document(inspection, min_days=30)))

    assert generous["expiry"]["tone"] == "good"
    assert strict["expiry"]["tone"] == "bad"
    # Both describe the same certificate: only the verdict moved.
    assert generous["expiry"]["value"] == strict["expiry"]["value"]


def test_an_expired_certificate_counts_the_days_the_right_way_round(tmp_path):
    """"-10 day(s) left" beside an expiry date is a puzzle, not a warning."""
    now = datetime.now(timezone.utc)
    expired = _certificate(
        tmp_path, not_before=now - timedelta(days=40), not_after=now - timedelta(days=10)
    )
    facts = _facts(summarise(_document(_inspect(*expired))))

    assert "expired 10 day(s) ago" in facts["expiry"]["detail"]
    assert "left" not in facts["expiry"]["detail"]
    assert facts["expiry"]["tone"] == "bad"


def test_an_untrusted_chain_says_so_where_the_grade_is(tmp_path):
    """A self-signed certificate is the commonest OpenCloud finding of all."""
    facts = _facts(summarise(_document(_inspect(*_certificate(tmp_path)))))

    assert facts["chain"]["tone"] == "bad"
    assert "trusted" in facts["chain"]["value"].lower()


def test_an_instance_without_tls_gets_no_transport_facts_at_all():
    """An empty row of dashes reads as a measurement; nothing reads as nothing."""
    summary = summarise({"rating": 1, "tls": {"reachable": False}, "extraChecks": []})

    assert summary["tlsOverview"] == []


def test_the_page_shows_the_transport_facts_beside_the_grade(tmp_path):
    """A fact in the summary that never reaches the template helps nobody."""
    from fastapi.templating import Jinja2Templates

    from webapp.app import frontend_dir, is_safe_link

    templates = Jinja2Templates(directory=str(frontend_dir() / "templates"))
    templates.env.tests["safe_link"] = is_safe_link
    document = _document(_inspect(*_certificate(tmp_path)))
    summary = summarise(document)
    identifier = "b6f2c0c5-1c4b-4f4e-9a3b-0d3f8b7c1a20"

    page = templates.env.get_template("scan.html").render(
        summary=summary,
        scan={
            "outputFormat": "dashboard",
            "result": document,
            "uuid": identifier,
            "expiresIn": 3600,
            "exports": {},
        },
        request=SimpleNamespace(url=SimpleNamespace(path=f"/scan/{identifier}")),
    )

    overview = page.split("Score</dt>")[0]
    for fact in summary["tlsOverview"]:
        assert fact["value"] in overview, f"{fact['id']} is missing from the overview"
    # The negative half: the tone travels as an attribute, because the CSP
    # forbids the inline style a coloured span would otherwise need.
    assert 'class="tls-fact" data-tone=' in overview
    assert "style=" not in overview
