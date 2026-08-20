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
    from fastapi.templating import Jinja2Templates

    from webapp.app import frontend_dir, is_safe_link

    templates = Jinja2Templates(directory=str(frontend_dir() / "templates"))
    templates.env.tests["safe_link"] = is_safe_link
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
