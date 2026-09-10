"""
The exports: the same scan as a file, and the ways it can be asked for wrongly.

Every expectation here is derived from an actual scan of
``tests/fake_opencloud.py`` rather than from a hardcoded list, so a check
added to the scanner shows up in the reports without anybody remembering to
update this file.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from opencloud_local_scan import __version__
from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour
from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    MEMORY_URL,
    _isolated_backend,
    _offline_resolver,
    backend,
    client,
    settings,
)
from webapp.catalog import summarise
from webapp.export_signing import verify_bytes
from webapp.redis_backend import memory_backend
from webapp.reports import csv_report, pdf_report, sarif_report
from webapp.store import ScanStore
from webapp.tasks import run_scan

IDENTIFIER = "b6f2c0c5-1c4b-4f4e-9a3b-0d3f8b7c1a20"


@pytest.fixture
def finished_scan():
    """One real scan of the fake instance, stored and completed."""
    configured = settings(
        allow_private_targets=True, verify_tls=False, scan_timeout=5
    )
    store = ScanStore(backend=memory_backend(MEMORY_URL), ttl=configured.result_ttl)
    behaviour = InstanceBehaviour(basic_auth=True)
    with FakeOpenCloud(behaviour) as instance:
        asyncio.run(
            store.create(
                IDENTIFIER,
                target=f"http://{instance.host}",
                ignore_hardenings=(),
                output_format="dashboard",
            )
        )
        asyncio.run(
            run_scan({"web_settings": configured, "store": store}, IDENTIFIER)
        )
    record = asyncio.run(store.get(IDENTIFIER))
    assert record is not None and record.result is not None
    return record.result


def test_the_csv_holds_a_row_for_every_finding_the_dashboard_shows(finished_scan):
    """A report that omits a finding the page shows is worse than no report."""
    summary = summarise(finished_scan)
    report = csv_report(finished_scan)

    assert summary["issues"], "the fake instance must fail something to test this"
    for issue in summary["issues"]:
        assert str(issue["id"]) in report
    for item in summary["missingHardenings"]:
        assert str(item["id"]) in report
    assert f"{summary['rating']}" in report
    # And it does not silently invent a section: a passing check is not a row.
    assert "not a finding" not in report


def test_the_sarif_report_names_this_build_and_describes_every_rule(finished_scan):
    """A SARIF result whose rule is missing is an identifier nobody can look up."""
    report = sarif_report(finished_scan)
    run = report["runs"][0]

    assert report["version"] == "2.1.0"
    assert run["tool"]["driver"]["version"] == __version__
    rule_ids = {rule["id"] for rule in run["tool"]["driver"]["rules"]}
    assert rule_ids, "a scan with findings must produce rules"
    for result in run["results"]:
        assert result["ruleId"] in rule_ids
        assert result["level"] in {"error", "warning", "note"}
    assert run["properties"]["rating"] == summarise(finished_scan)["rating"]


def test_the_pdf_is_a_real_pdf_and_carries_the_grade(finished_scan):
    """A download that no reader opens is not an export."""
    document = pdf_report(finished_scan, identifier=IDENTIFIER)
    text = document.decode("latin-1")

    assert document.startswith(b"%PDF-")
    assert document.rstrip().endswith(b"%%EOF")
    assert "xref" in text and "trailer" in text
    # The offsets in the table have to point at the objects, or a reader
    # rejects the file even though it looks plausible in an editor.
    start = int(text.rsplit("startxref", 1)[1].split("%%EOF")[0].strip())
    assert text[start:].startswith("xref")
    assert "/Type /Catalog" in text and "/Type /Pages" in text
    summary = summarise(finished_scan)
    assert f"Rating: {summary['label']}" in text
    assert IDENTIFIER in text
    assert "not affiliated with" in text


def test_a_pdf_survives_a_finding_full_of_characters_it_cannot_encode():
    """A report generator that crashes on an em dash is a report generator nobody trusts."""
    document = pdf_report(
        {
            "domain": "opencloud.example.com",
            "rating": 3,
            "extraChecks": [
                {
                    "id": "basicAuthDisabled",
                    "severity": "high",
                    "passed": False,
                    "detail": "Ünicode — parentheses ( ) and a backslash \\ here",
                }
            ],
        }
    )

    assert document.startswith(b"%PDF-")
    assert b"%%EOF" in document


def test_every_export_format_downloads_with_the_scans_own_name(finished_scan):
    """The uuid is the only name a file may carry: it names nothing else."""
    test_client = client()
    expected = {
        "json": "application/json",
        "csv": "text/csv",
        "sarif": "application/sarif+json",
        "pdf": "application/pdf",
    }

    for fmt, media_type in expected.items():
        response = test_client.get(f"/api/scans/{IDENTIFIER}/export/{fmt}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(media_type)
        assert IDENTIFIER in response.headers["content-disposition"]
        assert response.content

    assert json.loads(
        test_client.get(f"/api/scans/{IDENTIFIER}/export/sarif").text
    )["runs"]


@pytest.mark.parametrize("fmt", ["json", "sarif", "pdf"])
def test_a_configured_export_key_signs_the_exact_downloaded_bytes(finished_scan, fmt):
    """CI can verify an export without trusting an intermediate proxy."""
    test_client = client(export_signing_key="test-export-signing-key")
    response = test_client.get(f"/api/scans/{IDENTIFIER}/export/{fmt}")

    signature = response.headers["x-cos-signature"]
    assert verify_bytes(response.content, signature, "test-export-signing-key")
    assert not verify_bytes(response.content + b"\n", signature, "test-export-signing-key")


def test_an_unfinished_scan_says_so_rather_than_pretending_to_be_missing():
    """404 would send a caller into a retry loop against the wrong endpoint."""
    test_client = client()
    identifier = test_client.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]

    response = test_client.get(f"/api/scans/{identifier}/export/pdf")

    assert response.status_code == 409
    assert response.json()["state"] == "queued"


def test_an_unknown_uuid_or_format_is_indistinguishable_from_anything_else():
    """The uuid is a capability, and a probe learns nothing from the answer."""
    test_client = client()

    unknown = test_client.get(
        "/api/scans/0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa/export/pdf"
    )
    invalid = test_client.get("/api/scans/not-a-uuid/export/pdf")
    wrong_format = test_client.get(f"/api/scans/{IDENTIFIER}/export/docx")

    assert unknown.status_code == 404
    assert invalid.status_code == 404
    assert wrong_format.status_code == 404
    assert unknown.json() == invalid.json() == wrong_format.json()


def test_a_finished_scan_advertises_where_its_exports_live(finished_scan):
    """A client should not have to guess a URL this service already knows."""
    payload = client().get(f"/api/scans/{IDENTIFIER}").json()

    assert payload["done"] is True
    assert payload["exports"]["pdf"] == f"/api/scans/{IDENTIFIER}/export/pdf"
    assert set(payload["exports"]) == {"json", "csv", "sarif", "pdf"}


def test_the_result_page_offers_every_export_as_a_download(finished_scan):
    """The buttons are the feature; the endpoints are only how they work."""
    page = client().get(f"/scan/{IDENTIFIER}")

    assert page.status_code == 200
    for fmt in ("pdf", "csv", "sarif", "json"):
        assert f'href="/api/scans/{IDENTIFIER}/export/{fmt}"' in page.text
    # The CSP forbids inline anything, so a download must not need a handler.
    assert "onclick" not in page.text


def test_a_hostile_product_name_cannot_become_a_formula_in_the_spreadsheet():
    """
    Half of a report is text the *scanned* instance chose.

    A cell beginning with `=` is executed by Excel, LibreOffice and Sheets, so
    an instance that names itself `=cmd|...` would own the machine of whoever
    opens the download - and the download is handed to anyone holding the
    uuid, which includes whoever chose the payload.
    """
    payload = '=cmd|" /C calc"!A0'
    report = csv_report(
        {
            "product": payload,
            "rating": 1,
            "extraChecks": {},
            "vulnerabilities": [{"id": "+CVE-2026-0001", "severity": "high", "summary": payload}],
        }
    )

    for line in report.splitlines():
        for cell in line.split(","):
            unquoted = cell.strip().strip('"')
            assert not unquoted.startswith(("=", "+", "-", "@")), line
    # The negative half: the text is still there to read, merely disarmed.
    assert "cmd" in report
    assert "'=cmd" in report


def test_a_newline_in_a_finding_cannot_forge_a_row():
    """A response header from the scanned host reaches a cell verbatim."""
    report = csv_report(
        {
            "product": "OpenCloud\r\nnot actionable,forged,,,",
            "rating": 5,
            "extraChecks": {},
        }
    )

    assert "forged" in report
    assert not any(line.startswith("not actionable,forged") for line in report.splitlines())


def test_an_unbounded_string_from_the_instance_is_truncated():
    """A product name is somebody else's unbounded input, and the file is a download."""
    report = csv_report({"product": "A" * 10000, "rating": 5, "extraChecks": {}})

    assert "A" * 400 not in report
    assert "A" * 100 in report


def test_every_export_carries_the_remediation_plan(finished_scan):
    """A report that says what is wrong and not what to do first is half a report."""
    plan = summarise(finished_scan)["remediation"]
    assert plan["steps"], "the fake instance is meant to fail at least one check"
    first = plan["steps"][0]

    sarif = sarif_report(finished_scan)
    carried = sarif["runs"][0]["properties"]["remediation"]
    assert [step["id"] for step in carried["steps"]] == [
        step["id"] for step in plan["steps"]
    ]

    csv_text = csv_report(finished_scan)
    assert plan["summary"] in csv_text
    assert f"fix step {first['order']}" in csv_text

    pdf = pdf_report(finished_scan)
    assert b"What gets you to" in pdf


def test_the_exported_plan_keeps_the_order_the_scanner_worked_out(finished_scan):
    """Reordering the steps would silently change what the grades mean."""
    plan = summarise(finished_scan)["remediation"]
    orders = [step["order"] for step in plan["steps"]]

    assert orders == sorted(orders)
    # The negative half: the predicted ratings never go backwards either, so
    # no step is presented as undoing the one before it.
    ratings = [step["ratingAfter"] for step in plan["steps"]]
    assert ratings == sorted(ratings)


def test_the_dashboard_shows_the_plan_with_the_grade_each_step_reaches(
    finished_scan,
):
    """A page listing findings without an order leaves the triage to the reader."""
    from webapp.app import build_templates

    templates = build_templates()
    summary = summarise(finished_scan)
    assert summary["remediation"]["steps"], "the fake instance fails a check"

    request = SimpleNamespace(url=SimpleNamespace(path=f"/scan/{IDENTIFIER}"))
    page = templates.env.get_template("scan.html").render(
        summary=summary,
        scan={
            "outputFormat": "dashboard",
            "result": finished_scan,
            "uuid": IDENTIFIER,
            "expiresIn": 3600,
            "exports": {},
        },
        request=request,
    )

    first = summary["remediation"]["steps"][0]
    assert "What gets you to" in page
    assert first["id"] in page
    assert first["action"][:40] in page
    # The negative half: the letters shown are the plugin's own, not a
    # second scale invented for the page.
    from check_opencloud_security import RATE_MAP

    assert f"{RATE_MAP[first['ratingAfter']]}" in page


# ------------------------------------------- the transport block in a report


def _tls_document(inspection) -> dict:
    """A result document carrying one real inspection, as the scanner writes it."""
    return {
        "domain": "localhost",
        "product": "OpenCloud",
        "rating": 3,
        "tls": inspection.as_dict(),
        "extraChecks": [],
    }


def _tls_scan(tmp_path, **certificate):
    """One real handshake against a loopback endpoint, inspected."""
    from opencloud_local_scan import tls
    from tests.test_tls import TIMEOUT, _certificate, _server

    paths = _certificate(tmp_path, **certificate)
    with _server(*paths) as port:
        return tls.inspect(
            "localhost", port, TIMEOUT, probe_deprecated=False, check_stapling=False
        )


def test_the_flat_reports_carry_the_numbers_behind_the_transport_findings(tmp_path):
    """
    A finding says a check failed; these say what was actually measured.

    Somebody reading the report a month later needs the negotiated version,
    the chain and the dates in order to tell whether anything changed - the
    pass/fail alone cannot answer that, and it is the only thing the rest of
    the export carries.
    """
    inspection = _tls_scan(tmp_path)
    document = _tls_document(inspection)
    observed = inspection.as_dict()

    csv_text = csv_report(document)

    assert observed["protocol"] in csv_text
    assert observed["certificate"]["notAfter"] in csv_text
    assert observed["certificate"]["issuer"] in csv_text
    assert "Certificate chain" in csv_text

    pdf = pdf_report(document)
    assert b"Transport security" in pdf


def test_a_certificate_that_has_expired_says_so_rather_than_printing_a_date(tmp_path):
    """
    "Expires 3 March" reads as fine to somebody skimming; "expired 40 days ago" does not.

    The remaining days are already negative in the measurement, so the report
    has the fact - the only question is whether a reader has to subtract two
    dates to notice it.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    inspection = _tls_scan(
        tmp_path, not_before=now - timedelta(days=60), not_after=now - timedelta(days=30)
    )
    days = inspection.as_dict()["certificate"]["daysRemaining"]
    assert days < 0, "the certificate was generated already expired"

    csv_text = csv_report(_tls_document(inspection))

    assert f"expired {abs(days)} day(s) ago" in csv_text
    assert "day(s) left" not in csv_text


def test_a_live_certificate_reports_the_days_it_has_left(tmp_path):
    """The negative half of the expiry wording: a valid certificate is never called expired."""
    inspection = _tls_scan(tmp_path)
    days = inspection.as_dict()["certificate"]["daysRemaining"]
    assert days > 0

    csv_text = csv_report(_tls_document(inspection))

    assert f"{days} day(s) left" in csv_text
    assert "expired" not in csv_text


def test_a_chain_that_reaches_no_public_root_is_not_reported_as_merely_untrusted(tmp_path):
    """
    Two different problems that a single word would flatten into one.

    A self-signed certificate and a server that forgot to send its
    intermediate both fail to verify, but only one of them is fixed by
    installing the missing certificate - the report has to keep them apart.
    """
    document = _tls_document(_tls_scan(tmp_path))
    document["tls"]["trusted"] = False
    document["tls"]["chainComplete"] = False

    csv_text = csv_report(document)
    assert "not trusted, no path to a public root" in csv_text

    document["tls"]["chainComplete"] = True
    assert "no path to a public root" not in csv_report(document)


def test_a_deprecated_version_still_accepted_is_told_apart_from_one_refused(tmp_path):
    """A probe that found nothing and a probe that found TLS 1.0 must not read alike."""
    document = _tls_document(_tls_scan(tmp_path))
    document["tls"]["deprecatedProtocolsProbed"] = ["TLSv1", "TLSv1.1"]

    document["tls"]["deprecatedProtocolsAccepted"] = ["TLSv1"]
    accepted = csv_report(document)
    assert "still accepted: TLSv1" in accepted

    document["tls"]["deprecatedProtocolsAccepted"] = []
    refused = csv_report(document)
    assert "refused: TLSv1, TLSv1.1" in refused
    assert "still accepted" not in refused


def test_an_instance_that_was_never_reached_over_tls_claims_nothing_about_it(finished_scan):
    """
    The fake instance is plain HTTP, so there is no transport to describe.

    An export that printed "unknown" rows here would be inventing a
    measurement that no handshake produced.
    """
    csv_text = csv_report(finished_scan)

    assert "Certificate chain" not in csv_text
    assert "Transport security" not in pdf_report(finished_scan).decode(
        "latin-1", errors="replace"
    )
