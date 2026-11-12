"""
The web application end to end, the way a visitor uses it: in a browser,
from the landing page to a finished report and what can be done with it.

Every target is a fake OpenCloud instance scanned for real by the in-process
worker; expectations come from the scan itself (the JSON API of the same
application), not from hardcoded grades, except where the rating rules fix
them outright - an end-of-life release is always F.

Plumbing and browser choice: ``tests/browser_support.py`` (ADR 0061).
"""

from __future__ import annotations

import csv
import io
import json
import uuid as uuid_module
from pathlib import Path

import pytest

from opencloud_local_scan.vulndb import load_database
from tests.browser_support import (  # noqa: F401 - the fixtures register under their own names
    PHONE,
    UNAFFECTED_RELEASE,
    PageWatch,
    browser_fixture,
    new_page,
    page_fixture,
    shown_but_hidden,
    site_fixture,
    submit_scan,
    wait_for_visible_findings,
    wait_until_final,
    watch_fixture,
)


def _api(page, site, uuid: str) -> dict:
    response = page.request.get(f"{site.base}/api/scans/{uuid}")
    assert response.ok
    return response.json()


@pytest.fixture(scope="module")
def ratings(browser, site) -> dict[str, dict]:
    """Each profile scanned once through the form; the API's summary per profile."""
    found = {}
    for profile, target in site.targets.items():
        tab = new_page(browser, PageWatch())
        try:
            uuid = submit_scan(tab, site, target)
            found[profile] = {"uuid": uuid, **_api(tab, site, uuid)["summary"]}
        finally:
            tab.context.close()
    return found


@pytest.mark.parametrize("profile", ["hardened", "weak", "eol"])
def test_a_scan_from_the_form_ends_on_a_report_that_matches_the_api(page, site, watch, ratings, profile):
    """The grade dial, the tab title and the JSON API tell the same story."""
    summary = ratings[profile]
    response = page.goto(f"{site.base}/scan/{summary['uuid']}")
    assert response is not None and response.status == 200
    assert page.get_attribute("body", "data-scan-state") == "completed"
    assert page.get_attribute(".score-dial", "data-rating") == str(summary["rating"])
    assert page.title().startswith(f"Grade {summary['label']}")
    assert page.locator("#progress-card").is_hidden()
    assert shown_but_hidden(page) == []
    watch.assert_clean()


def test_the_profiles_run_a_release_no_bundled_advisory_covers():
    """An advisory over that release would cap both profiles and blur their grades."""
    assert load_database().matches(UNAFFECTED_RELEASE) == [], (
        f"a bundled advisory now covers {UNAFFECTED_RELEASE}; move "
        "UNAFFECTED_RELEASE in tests/browser_support.py to a release no advisory covers"
    )


def test_the_grades_follow_the_rating_rules(ratings):
    """End of life is F, and the hardened instance outranks the weak one."""
    assert ratings["eol"]["rating"] == 0
    assert ratings["eol"]["label"] == "F"
    assert ratings["hardened"]["rating"] > ratings["weak"]["rating"] > ratings["eol"]["rating"]


def test_the_waiting_page_follows_the_scan_and_hands_over_by_itself(page, site, watch):
    """While queued the page says so; once the scan finishes it reloads into the report unaided."""
    site.worker_open.clear()
    try:
        page.goto(site.base + "/")
        page.fill("#target_url", site.targets["hardened"])
        page.click("form.scan-form button[type=submit]")
        page.wait_for_url("**/scan/**")
        assert page.get_attribute("body", "data-scan-state") == "queued"
        assert page.locator("#progress-card").is_visible()
        assert page.get_attribute("#step-queued", "data-state") == "active"
        assert page.get_attribute("#step-done", "data-state") is None
        page.wait_for_function("() => /\\d+:\\d{2}/.test(document.getElementById('progress-elapsed').textContent)")
        waiting_title = page.title()
        assert not waiting_title.startswith("Grade")
    finally:
        site.worker_open.set()
    wait_until_final(page)
    assert page.get_attribute("body", "data-scan-state") == "completed"
    assert page.title().startswith("Grade")
    assert page.locator(".score-dial").is_visible()
    watch.assert_clean()


def test_the_severity_counters_filter_the_findings_and_give_them_back(page, site, watch, ratings):
    """Pressing a counter shows only that severity, as many as it says; pressing again restores all."""
    page.goto(f"{site.base}/scan/{ratings['weak']['uuid']}")
    findings = page.locator("[data-findings-list] .finding")
    total = findings.count()
    critical = page.locator(".counter[data-filter=critical]")
    announced = int(critical.inner_text().split()[0])
    assert 0 < announced < total
    assert page.locator("#findings-filter-status").is_hidden()

    critical.click()
    assert critical.get_attribute("aria-pressed") == "true"
    # Each press is waited out rather than sampled: the list it leaves behind
    # is a different height from the one that was pressed, and the control the
    # next press aims at is still moving until it has settled.
    wait_for_visible_findings(page, announced)
    visible = page.locator("[data-findings-list] .finding:not([hidden])")
    assert set(visible.evaluate_all("els => els.map(e => e.dataset.tag)")) == {"critical"}
    status = page.locator("#findings-filter-status")
    assert status.is_visible()
    assert critical.locator("span").text_content().strip() in status.text_content()

    critical.click()
    assert critical.get_attribute("aria-pressed") == "false"
    wait_for_visible_findings(page, total)
    assert status.is_hidden()

    warning = page.locator(".counter[data-filter=warning]")
    announced_warnings = int(warning.inner_text().split()[0])
    assert 0 < announced_warnings < total
    warning.click()
    wait_for_visible_findings(page, announced_warnings)
    page.click("[data-filter-clear]")
    wait_for_visible_findings(page, total)
    assert warning.get_attribute("aria-pressed") == "false"
    watch.assert_clean()


def _download(page, selector: str):
    with page.expect_download() as info:
        page.click(selector)
    download = info.value
    with open(download.path(), "rb") as handle:
        return download.suggested_filename, handle.read()


def test_every_export_downloads_and_describes_the_same_scan(page, site, ratings):
    """JSON, CSV, SARIF and PDF come down as files named after the scan, with matching content."""
    summary = ratings["weak"]
    page.goto(f"{site.base}/scan/{summary['uuid']}")
    stem = f"scan-{summary['uuid']}"

    name, body = _download(page, "a[href$='/export/json']")
    assert name == f"{stem}.json"
    document = json.loads(body)
    assert document["rating"] == summary["rating"]

    name, body = _download(page, "a[href$='/export/csv']")
    assert name == f"{stem}.csv"
    rows = list(csv.reader(io.StringIO(body.decode("utf-8"))))
    assert rows[0][0] == "check-opencloud-security"
    assert any(row and row[0] == "Instance" for row in rows)

    name, body = _download(page, "a[href$='/export/sarif']")
    assert name == f"{stem}.sarif.json"
    assert json.loads(body)["version"] == "2.1.0"

    name, body = _download(page, "a[href$='/export/pdf']")
    assert name == f"{stem}.pdf"
    assert body.startswith(b"%PDF-")


def test_a_waived_check_stops_counting_and_is_listed_as_waived(page, site, watch, ratings):
    """Waiving the failed checks the form offers moves them to the waived list and never lowers the grade."""
    baseline = ratings["weak"]
    page.goto(site.base + "/")
    offered = set(page.eval_on_selector_all("[data-waiver-option] input", "els => els.map(e => e.value)"))
    waivable = sorted({issue["id"] for issue in baseline["issues"]} & offered)
    assert waivable, "the weak profile should fail at least one waivable check"

    page.fill("#target_url", site.targets["weak"])
    page.click("details.waivers summary")
    for identifier in waivable:
        page.check(f"[data-waiver-option] input[value='{identifier}']")
    page.click("form.scan-form button[type=submit]")
    page.wait_for_url("**/scan/**")
    wait_until_final(page)

    uuid = page.url.rsplit("/scan/", 1)[1]
    waived = _api(page, site, uuid)
    assert sorted(waived["ignoreHardenings"]) == waivable
    assert waived["summary"]["rating"] >= baseline["rating"]
    excluded = page.locator("#excluded").locator("xpath=..").inner_text()
    for identifier in waivable:
        assert identifier in excluded
    listed = set(page.locator("[data-findings-list] .finding-head code").all_inner_texts())
    assert listed.isdisjoint(waivable)
    watch.assert_clean()


def _save(page, selector: str, directory: Path) -> Path:
    """Click a download link and keep the file, as a reader would."""
    with page.expect_download() as info:
        page.click(selector)
    download = info.value
    path = directory / download.suggested_filename
    download.save_as(path)
    return path


def test_a_downloaded_report_uploads_back_and_compares_against_a_later_scan(
    page, site, watch, tmp_path
):
    """
    The journey ADR 0057 exists for: the earlier scan is gone, the file is not.

    A reader scans an instance, keeps the download, scans again later and asks
    what changed - with the file in place of a uuid nobody kept. The round trip
    is the test: the export this application writes has to be a file its own
    parser accepts, in a real browser, through a real multipart form.
    """
    earlier = submit_scan(page, site, site.targets["weak"])
    report = _save(page, "a[href$='/export/json']", tmp_path)
    later = submit_scan(page, site, site.targets["weak"])
    assert earlier != later

    page.goto(site.base + "/compare")
    page.set_input_files("#compare-report", report)
    page.fill("#compare-upload-current", later)
    page.click("form.compare-form[method=post] button[type=submit]")

    page.wait_for_url("**/compare/**")
    # Nothing about the instance changed between the two scans, and the
    # arithmetic is the plugin's own - so the answer is "unchanged", not an
    # invented regression.
    assert page.get_attribute(".compare-verdict", "data-verdict") == "unchanged"
    # The page says where the earlier side came from, and offers no result
    # page for it: that file was read and discarded.
    assert page.locator(".compare-source").is_visible()
    assert page.locator(f"a[href='/scan/{earlier}']").count() == 0
    assert page.locator(f"a[href='/scan/{later}']").count() >= 1
    assert shown_but_hidden(page) == []
    watch.assert_clean()


def test_a_second_scan_in_the_same_tab_offers_the_comparison_with_the_first(
    page, site, watch
):
    """
    Scan, fix, scan again - and the tab remembers the uuid nobody wrote down.

    `compare-offer.js` keeps that history in sessionStorage alone, so the offer
    has to appear on the second report of an instance and not on the first,
    and the link it builds has to land on a comparison that actually works.
    """
    first = submit_scan(page, site, site.targets["hardened"])
    offer = page.locator("[data-compare-offer]")
    # Nothing to offer yet: this tab has seen one scan of this instance.
    assert offer.is_hidden()

    second = submit_scan(page, site, site.targets["hardened"])
    offer.wait_for(state="visible")
    link = page.locator("[data-compare-offer-link]")
    assert f"baseline={first}" in (link.get_attribute("href") or "")
    assert f"current={second}" in (link.get_attribute("href") or "")

    link.click()
    page.wait_for_url("**/compare?**")
    assert page.input_value("#compare-baseline") == first
    assert page.input_value("#compare-current") == second
    assert page.get_attribute(".compare-verdict", "data-verdict") == "unchanged"
    watch.assert_clean()


def test_the_offer_does_not_follow_a_reader_into_another_tab(browser, site):
    """
    The history is the tab's, because each uuid in it is a credential.

    sessionStorage rather than localStorage is the whole of that promise, so a
    second tab that opens the same report must be offered nothing.
    """
    watch = PageWatch()
    first_tab = new_page(browser, watch)
    try:
        submit_scan(first_tab, site, site.targets["eol"])
        second = submit_scan(first_tab, site, site.targets["eol"])
        first_tab.locator("[data-compare-offer]").wait_for(state="visible")

        other_tab = first_tab.context.new_page()
        other_tab.set_default_timeout(15_000)
        watch.attach(other_tab)
        other_tab.goto(f"{site.base}/scan/{second}")
        other_tab.wait_for_load_state("load")
        assert other_tab.locator("[data-compare-offer]").is_hidden()
        watch.assert_clean()
    finally:
        first_tab.context.close()


def test_a_scan_works_without_javascript(browser, site):
    """The form, the waiting page and the report all work with scripting off; a reload finishes the wait."""
    plain = new_page(browser, PageWatch(), java_script_enabled=False)
    try:
        plain.goto(site.base + "/")
        plain.fill("#target_url", site.targets["hardened"])
        plain.click("form.scan-form button[type=submit]")
        plain.wait_for_url("**/scan/**")
        uuid = plain.url.rsplit("/scan/", 1)[1]
        for _ in range(100):
            if _api(plain, site, uuid)["state"] in ("completed", "failed"):
                break
            plain.wait_for_timeout(100)
        plain.reload()
        assert plain.get_attribute("body", "data-scan-state") == "completed"
        assert plain.locator(".score-dial").is_visible()
        assert plain.locator("[data-findings-list] .finding, .tag-good").count() >= 1
    finally:
        plain.context.close()


def test_the_report_is_reachable_by_keyboard_alone(page, site):
    """Typing an address and pressing Enter starts a scan."""
    page.goto(site.base + "/")
    page.focus("#target_url")
    page.keyboard.type(site.targets["hardened"])
    page.keyboard.press("Enter")
    page.wait_for_url("**/scan/**")
    wait_until_final(page)
    assert page.get_attribute("body", "data-scan-state") == "completed"


def test_an_unknown_report_is_a_plain_404_with_a_way_home(page, site, watch):
    """A uuid that was never issued answers 404 and offers the start page, without a script error."""
    response = page.goto(f"{site.base}/scan/{uuid_module.uuid4()}")
    assert response is not None and response.status == 404
    assert page.locator("h1").count() == 1
    assert page.locator("main a[href='/']").count() >= 1
    assert watch.page_errors == []
    assert watch.csp_violations() == []
    assert watch.foreign_requests == []


def test_a_report_reads_on_a_phone_without_sideways_scrolling(browser, site, ratings):
    """The longest report, with every remediation, fits a 390-pixel screen."""
    watch = PageWatch()
    phone = new_page(browser, watch, viewport=PHONE)
    try:
        phone.goto(f"{site.base}/scan/{ratings['weak']['uuid']}")
        overflow = phone.evaluate("() => document.scrollingElement.scrollWidth - window.innerWidth")
        assert overflow <= 1
        watch.assert_clean()
    finally:
        phone.context.close()


def test_every_table_of_contents_link_has_a_target(page, site, ratings):
    """The report's in-page links all land on a section that exists."""
    page.goto(f"{site.base}/scan/{ratings['weak']['uuid']}")
    anchors = set(page.eval_on_selector_all("a[href^='#']", "els => els.map(e => e.getAttribute('href').slice(1))"))
    assert len(anchors) > 3
    missing = [name for name in anchors if name and page.locator(f"[id='{name}']").count() == 0]
    assert missing == []


def test_a_german_visitor_gets_a_german_report(browser, site):
    """The language chosen before the scan is the language of the report."""
    watch = PageWatch()
    german = new_page(browser, watch, locale="de-DE", extra_http_headers={"Accept-Language": "de-DE,de;q=0.9"})
    try:
        german.goto(site.base + "/")
        assert german.get_attribute("html", "lang") == "de"
        submit_scan(german, site, site.targets["weak"])
        assert german.get_attribute("html", "lang") == "de"
        assert german.title().startswith("Note")
        watch.assert_clean()
    finally:
        german.context.close()
