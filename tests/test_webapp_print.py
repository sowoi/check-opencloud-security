"""
The report as a printed document.

A report gets printed for a change record and saved to PDF for somebody who
was not at the screen, and on paper the screen design is wrong in two ways
that are not matters of taste.

The first is that the dark scheme's ink is near-white. A reader who chose dark
and pressed print, with nothing done about it, is handed a blank sheet - the
one failure here that destroys the document rather than making it ugly, and
the reason the print block redefines the tokens rather than restyling the
elements.

The second is that a control on paper is furniture that survived a move. An
export button cannot be pressed and a copy-to-clipboard button has nowhere to
copy to, so what prints is what says something: the grade, the facts, the
findings, the plan - and the trademark notice, which every surface that stands
on its own carries.
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

IDENTIFIER = "9f4c7a21-6d85-4b30-9e12-7c05a8d3b6e1"

CSS_PATH = Path(__file__).resolve().parent.parent / "frontend/static/css/app.css"


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def _print_block() -> str:
    """Everything inside `@media print`, which is the last block in the file."""
    css = _css()
    start = css.index("@media print {")
    return css[start:]


def _report() -> str:
    """One finished scan of the fake instance, rendered as its report page."""
    configured = settings(allow_private_targets=True, verify_tls=False, scan_timeout=5)
    app = create_app(configured)
    with TestClient(app) as test_client:
        store = app.state.store
        with FakeOpenCloud(InstanceBehaviour(basic_auth=True)) as instance:
            asyncio.run(
                store.create(
                    IDENTIFIER,
                    target=f"http://{instance.host}",
                    ignore_hardenings=(),
                    output_format="dashboard",
                )
            )
            asyncio.run(run_scan({"web_settings": configured, "store": store}, IDENTIFIER))
        return test_client.get(f"/scan/{IDENTIFIER}").text


def test_printing_forces_the_daylight_ink_whatever_the_screen_was_set_to():
    """
    The dark scheme's `--ink` is near-white. Printed against paper that the
    browser leaves white, it is a sheet with nothing on it - so the print
    block has to redefine the token for the explicit dark override as well as
    for the default, or the readers who chose dark are the ones it fails.
    """
    block = _print_block()
    # The selector list that carries the daylight tokens, up to the first
    # declaration in it.
    selector = block[: block.index("--ink")]

    assert ':root[data-theme="dark"]' in selector
    assert ':root[data-theme="light"]' in selector
    assert re.search(r"--ink:\s*#0d0f17", block)
    assert re.search(r"--paper:\s*#ffffff", block)
    # The screen's near-white ink must not be what the printer is asked for.
    assert "#eaedf7" not in block
    # And the aurora, which is a fixed layer: on paper a fixed layer is a
    # stamp on every single sheet.
    assert re.search(r"body::before,\s*body::after\s*\{\s*display:\s*none", block)


def test_the_controls_do_not_print():
    """
    A menu, a scheme switch, an export button and a copy control are all
    instructions to a browser. On paper they are ink spent on nothing, and a
    heading over a row of dead buttons reads as a fault in the document.
    """
    block = _print_block()

    for control in (
        ".site-header",
        ".theme-toggle",
        ".back-to-top",
        ".export-list",
        ".flavour-picker",
        "[data-copy-fragment]",
        ".scan-actions",
        '[data-print="hide"]',
    ):
        assert control in block, control


def test_the_export_and_sharing_cards_are_marked_as_screen_only():
    """
    Both cards are entirely controls, so hiding the buttons alone would print
    a heading and a lede introducing nothing. The marker is on the section.
    """
    page = _report()

    # The opening tag of the section each heading belongs to: everything from
    # the last `<section` before the heading up to the heading itself.
    for heading in ('id="exports"', 'id="share"'):
        section = page[: page.index(heading)].rsplit("<section", 1)[1]
        assert 'data-print="hide"' in section, heading

    # And the cards that carry facts are not marked, or the document would
    # print as a cover sheet.
    for heading in ('id="findings"', 'id="remediation"'):
        section = page[: page.index(heading)].rsplit("<section", 1)[1]
        assert 'data-print="hide"' not in section, heading


def test_what_a_reader_came_for_still_prints():
    """
    The grade, the findings and the plan are the document. A print rule that
    hid a card carrying a fact would be a report that quietly omits part of
    itself, which is worse than one that prints a button nobody can press.
    """
    block = _print_block()

    for kept in (".score-dial", ".finding", ".tag", ".card"):
        assert kept in block, kept
    # None of them may be swept up by the blanket hide.
    hidden = block[block.index(".site-header") : block.index("display: none !important")]
    for kept in (".score-dial", ".finding{", ".finding,", ".card,"):
        assert kept not in hidden, kept


def test_the_trademark_notice_survives_the_print():
    """
    A printed report stands on its own, and DESIGN.md says every surface that
    does carries the notice. The rest of the footer - the nav, the version
    badges, the note about expiry - is chrome and goes.
    """
    block = _print_block()

    assert ".footer-nav" in block
    assert ".build," in block or ".build\n" in block
    assert re.search(r"\.legal\s*\{", block)
    # The footer itself is kept and ruled off, not hidden.
    assert re.search(r"\.site-footer\s*\{[^}]*border-top", block)


def test_a_finding_is_never_split_across_a_fold():
    """
    Half a finding at the foot of one page and half at the head of the next is
    two half-findings, and the severity is on the half that stayed behind.
    """
    block = _print_block()

    match = re.search(r"\.finding,[^{]*\{\s*break-inside:\s*avoid", block, re.DOTALL)
    assert match, "findings, counters and steps must not break across pages"


def test_a_reference_prints_the_address_it_points_at():
    """
    A link on paper is a dead end unless it says where it went - and the two
    inside a finding, the documentation and the advisory, are exactly what
    somebody reads next with the sheet in their hand.
    """
    block = _print_block()

    assert re.search(r"\.fix a::after\s*\{[^}]*attr\(href\)", block, re.DOTALL)
