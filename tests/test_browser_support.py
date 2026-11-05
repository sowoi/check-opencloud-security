"""
The browser-test plumbing's own rules, checked without a browser.

`PageWatch` turns every console error into a failed test. That is only
useful if it fails for the page's faults and not for the test's own timing.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.browser_support import PageWatch, aborted_font_download, trace_path

# Verbatim from a Firefox run in CI: the test reloaded while a font that text
# had just asked for was still downloading.
ABORTED = (
    '[JavaScript Error: "downloadable font: download failed (font-family: "JetBrains Mono" '
    "style:normal weight:700 width:100 src index:0): status=2152398850 "
    'source: http://127.0.0.1:40993/static/fonts/JetBrainsMono-Bold.woff2"]'
)


@dataclass
class _Message:
    type: str
    text: str


def test_a_font_download_cut_short_by_navigation_is_not_a_page_error():
    """Firefox logs the abort as an error; the page did nothing wrong."""
    assert aborted_font_download(ABORTED)

    watch = PageWatch()
    watch._console(_Message("error", ABORTED))
    assert watch.console_errors == []


def test_a_font_that_fails_for_another_reason_is_still_reported():
    """Only the abort status is excused - a missing or refused font still fails."""
    failed = ABORTED.replace("status=2152398850", "status=2147746065")
    assert not aborted_font_download(failed)

    watch = PageWatch()
    watch._console(_Message("error", failed))
    watch._console(_Message("error", "Uncaught TypeError: x is undefined"))
    assert watch.console_errors == [failed, "Uncaught TypeError: x is undefined"]


def test_a_console_warning_is_never_an_error():
    """The watch collects errors only."""
    watch = PageWatch()
    watch._console(_Message("warning", "something odd"))
    assert watch.console_errors == []


def test_a_trace_file_is_named_after_its_test():
    """One readable, file-system-safe name per failed test."""
    path = trace_path("/traces", "tests/test_webapp_browser_ux.py::test_x[/api]")
    assert path.name == "tests_test_webapp_browser_ux.py_test_x_api.zip"
    assert str(path.parent) == "/traces"
