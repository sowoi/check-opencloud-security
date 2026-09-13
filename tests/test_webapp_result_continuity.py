"""
The result page, for the reader who is not looking at it.

Three things a scan's reader does elsewhere: waits in another tab, comes back
after fixing something, and leaves a report open meaning to download it
later. The tab title follows the scan, a later scan of the same target offers
the comparison with the earlier one, and the last minutes before a report
disappears are announced near the top of the page.

The scripts are not run here; what is protected is the contract they rely
on - the hooks and sentences the server renders, what stays hidden until a
script can make it true, and above all what must never appear: the uuid in a
title, a grade in the link-preview metadata, a download offered for a scan
that has none.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi.testclient import TestClient

from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour
from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    backend,
    settings,
)
from webapp.app import create_app
from webapp.tasks import run_scan

IDENTIFIER = "0c9e7a51-4d2b-4f6a-8e31-7b5d2c9f1a46"
STATIC_JS = Path(__file__).resolve().parents[1] / "frontend" / "static" / "js"


def _render(state: str, *, advance: int = 0) -> str:
    """The result page for one scan in ``state``, optionally near its expiry."""
    configured = settings(allow_private_targets=True, verify_tls=False, scan_timeout=5)
    app = create_app(configured)
    with TestClient(app) as test_client:
        store = app.state.store
        if state == "completed":
            with FakeOpenCloud(InstanceBehaviour(basic_auth=True)) as instance:
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
        else:
            asyncio.run(
                store.create(
                    IDENTIFIER,
                    target="http://cloud.example.com",
                    ignore_hardenings=(),
                    output_format="dashboard",
                )
            )
            if state == "running":
                asyncio.run(store.mark_running(IDENTIFIER))
            elif state == "failed":
                asyncio.run(store.mark_failed(IDENTIFIER, "The instance did not answer."))
        if advance:
            backend().advance(advance)
        return test_client.get(f"/scan/{IDENTIFIER}").text


def _tag(page: str, hook: str) -> str:
    """The opening tag carrying ``hook``."""
    match = re.search(r"<[a-z]+[^>]*\b" + re.escape(hook) + r"(?=[\s=>])[^>]*>", page)
    assert match is not None, f"{hook} is not rendered"
    return match.group(0)


def _title(page: str) -> str:
    match = re.search(r"<title>(.*?)</title>", page, re.DOTALL)
    assert match is not None
    return match.group(1)


# -------------------------------------------------------------- the tab title


def test_a_finished_scan_names_its_grade_and_host_in_the_tab():
    """A reader scanning several instances tells the tabs apart by what they found."""
    page = _render("completed")
    title = _title(page)

    assert title.startswith("Grade ")
    assert "127.0.0.1" in title or "localhost" in title
    assert "http://" not in title, "the scheme is the part every tab would share"
    assert IDENTIFIER not in title, "a title lands in history and bookmarks"


def test_the_grade_stays_out_of_what_a_link_preview_would_print():
    """og:title is what a chat channel shows everyone; the tab is the reader's own."""
    page = _render("completed")
    og = re.search(r'<meta property="og:title" content="([^"]*)"', page)

    assert og is not None
    assert og.group(1) == "Scan results"
    assert "Grade" not in og.group(1)


def test_a_waiting_scan_says_so_in_the_tab_and_carries_every_later_wording():
    """The server writes the first reading; the poller needs the rest without English of its own."""
    page = _render("queued")
    card = _tag(page, 'id="progress-card"')

    assert _title(page).startswith("Queued: cloud.example.com")
    for hook in ("tab-queued", "tab-running", "tab-done", "tab-failed"):
        assert f'data-{hook}="' in card
    position = re.search(r'data-tab-queued-position="([^"]*)"', card)
    assert position is not None
    # The host is filled in by the server, the position left for the script.
    assert "{position}" in position.group(1)
    assert "cloud.example.com" in position.group(1)
    assert "{target}" not in card


def test_each_state_is_named_in_the_tab_and_none_claims_another():
    """A failed scan must not sit in the tab strip looking like a finished one."""
    running = _title(_render("running"))
    failed = _title(_render("failed"))

    assert running.startswith("Scanning: ")
    assert failed.startswith("Scan failed: ")
    assert "Grade" not in failed and "Grade" not in running


# --------------------------------------------------------- the compare offer


def test_a_finished_scan_carries_a_hidden_offer_the_script_can_complete():
    """Without the script there is no earlier scan to name, so nothing is shown."""
    page = _render("completed")
    offer = _tag(page, "data-compare-offer")

    assert "hidden" in offer
    assert "data-compare-target=" in offer
    assert "{time}" in offer, "the sentence is the server's, the time the browser's"
    assert f'href="/compare?current={IDENTIFIER}"' in page
    assert "<script src=\"/static/js/compare-offer.js\" defer></script>" in page


def test_only_a_finished_scan_is_offered_for_comparison():
    """The comparison refuses anything unfinished, so the offer must not lead there."""
    for state in ("queued", "running", "failed"):
        assert "data-compare-offer" not in _render(state), state


def test_the_history_stays_in_the_tab_and_off_the_server():
    """Every uuid in it is a credential: it must die with the tab and never be posted."""
    source = (STATIC_JS / "compare-offer.js").read_text()

    assert "window.sessionStorage" in source
    assert "window.localStorage" not in source
    assert "fetch(" not in source and "XMLHttpRequest" not in source
    assert "sendBeacon" not in source


# ---------------------------------------------------------- the expiry warning


def test_a_report_far_from_its_expiry_renders_the_warning_hidden():
    """An hour away, a warning would be noise the reader learns to ignore."""
    page = _render("completed")
    warning = _tag(page, "data-expiry-warning")

    assert "hidden" in warning
    assert 'data-expiry-warn-after="300"' in warning
    assert "{minutes}" in warning
    assert "<script src=\"/static/js/expiry.js\" defer></script>" in page


def test_a_report_in_its_last_minutes_is_warned_about_without_any_script():
    """A reader without scripting must be told too, and offered the way to keep a copy."""
    page = _render("completed", advance=3600 - 120)
    warning = _tag(page, "data-expiry-warning")

    assert "hidden" not in warning
    assert "This report disappears in about 2 minutes." in page
    assert 'href="#exports" data-expiry-warning-action' in page


def test_a_failed_scan_is_warned_about_but_offered_no_download():
    """There is nothing to export from a failed scan, so no link may promise one."""
    page = _render("failed", advance=3600 - 60)
    warning = _tag(page, "data-expiry-warning")

    assert "hidden" not in warning
    assert "data-expiry-warning-action" not in page
    assert 'id="exports"' not in page


def test_the_new_hooks_add_no_inline_script_handler_or_style():
    """The CSP has no `unsafe-inline`, so anything inline here would silently not run."""
    page = _render("completed", advance=3600 - 120)
    head = page[page.index('class="scan-head"') : page.index('id="progress-card"')]

    assert "onclick" not in head.lower()
    assert "style=" not in head
    assert "<script" not in head.lower()
