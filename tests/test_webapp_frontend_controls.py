"""
The four controls a reader drives the report and the form with.

Each of them is enhancement over markup that already worked, and that is the
property worth protecting: the counters were readings, the waiver list was a
list, the address field was a field, and the page was lit by whatever the
operating system asked for. A change that made any of them *depend* on
scripting would take the page away from the readers who have none, and none of
the four would fail loudly enough to notice.

The other half is the Content-Security-Policy, which has no `unsafe-inline`.
An `onclick` or a `style=` added to one of these controls would be dropped by
the browser and the control would silently stop working, so the absence of
both is asserted here rather than left to a review.
"""

from __future__ import annotations

import asyncio
import re

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

IDENTIFIER = "6b2e1f4d-0c3a-4d92-b8f7-3a1c5e0d2f84"

#: The three severities that are both counted and used as a tag on a finding.
FILTERABLE = ("critical", "warning", "info")


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
                    release_track="lts",
                )
            )
            asyncio.run(run_scan({"web_settings": configured, "store": store}, IDENTIFIER))
        return test_client.get(f"/scan/{IDENTIFIER}").text


def _landing() -> str:
    """The form, with the waiver catalogue on it."""
    app = create_app(settings())
    with TestClient(app) as test_client:
        return test_client.get("/").text


def _counters(page: str) -> dict[str, str]:
    """Every counter on the report, by the severity it filters, with its markup."""
    found = {}
    for match in re.finditer(
        r'<button class="counter"[^>]*data-filter="(\w+)"(.*?)</button>', page, re.DOTALL
    ):
        found[match.group(1)] = match.group(0)
    return found


# ------------------------------------------------- the counters as the filter


def test_each_severity_counter_is_a_button_that_filters_the_findings_below():
    """The filter's vocabulary has to be the one the server tagged with.

    `data-filter` and `data-tag` are written by different parts of the
    template. A rename on either side would leave a control that presses
    cleanly and matches nothing.
    """
    page = _report()
    counters = _counters(page)

    assert set(counters) == set(FILTERABLE)
    tags = set(re.findall(r'<li class="finding" data-tag="(\w+)"', page))
    assert tags, "the fixture scan produced no findings to filter"
    assert tags.issubset(set(FILTERABLE))
    assert 'class="findings" data-findings-list' in page


def test_a_counter_is_pressable_exactly_when_it_has_findings_behind_it():
    """A control that reveals nothing is worse than no control.

    Asserted as the invariant rather than against a fixed number, because the
    fake instance's findings change whenever a check is added to the scanner.
    """
    page = _report()
    counters = _counters(page)

    for severity, markup in counters.items():
        count = int(re.search(r"<strong>(\d+)</strong>", markup).group(1))
        disabled = "disabled" in markup
        assert disabled == (count == 0), (
            f"the {severity} counter counts {count} and "
            f"{'is' if disabled else 'is not'} disabled"
        )


def test_the_counters_that_no_list_stands_behind_stay_readings():
    """Advisories and passed checks are counted but not listed on this page.

    Offering them as filters would promise a narrowing that cannot happen.
    """
    page = _report()
    counters = _counters(page)

    assert "vulnerabilities" not in counters
    assert "passed" not in counters
    # Both are still on the page, as the readings they were.
    assert page.count('<div class="counter">') == 2


def test_the_filter_status_names_the_severity_and_offers_the_way_back():
    """The sentence is the server's, in the page's language, and starts hidden.

    A filter that could only be undone by finding the same counter again is a
    filter somebody gets stuck inside.
    """
    page = _report()
    start = page.index('id="findings-filter-status"')
    status = page[page.rindex("<p", 0, start) : page.index("</p>", start)]

    assert "hidden" in status
    assert 'aria-live="polite"' in status
    assert "{severity}" in status, "the severity is filled in from the pressed counter"
    assert "data-filter-clear" in status


def test_the_findings_filter_adds_no_inline_script_or_handler():
    """The policy has no 'unsafe-inline': either would be dropped silently."""
    page = _report()
    start = page.index('<div class="counters"')
    block = page[start : page.index("</div>", page.index("</button>", start))]

    assert "onclick" not in block
    assert "style=" not in block
    assert "<script" not in block


# ------------------------------------------------------------- the two schemes


def test_the_scheme_a_visitor_chose_is_applied_before_the_first_paint():
    """Deferred, it would repaint after the page was drawn in the other scheme.

    That flash would land on every navigation, which is exactly the reason
    this one script is not deferred - so the absence of `defer` is the
    assertion.
    """
    page = _landing()
    theme = re.search(r'<script src="/static/js/theme\.js"([^>]*)>', page)

    assert theme is not None
    assert "defer" not in theme.group(1)
    # Every other script on the page still is deferred.
    others = re.findall(r'<script src="/static/js/(?!theme\.js)[^"]+"([^>]*)>', page)
    assert others and all("defer" in attributes for attributes in others)


def test_the_scheme_switch_is_offered_with_a_name_and_no_inline_handler():
    """The icon carries the state, so the label has to carry the purpose."""
    page = _landing()
    start = page.index("data-theme-toggle")
    button = page[page.rindex("<button", 0, start) : page.index("</button>", start)]

    assert "aria-label=" in button
    assert "onclick" not in button
    assert "style=" not in button


def test_both_theme_colour_tags_can_be_repointed_at_the_chosen_scheme():
    """Under an override the browser chrome would otherwise frame the page wrong."""
    page = _landing()

    assert 'id="theme-color-light"' in page
    assert 'id="theme-color-dark"' in page
    assert 'media="(prefers-color-scheme: light)"' in page
    assert 'media="(prefers-color-scheme: dark)"' in page


# ---------------------------------------------------------- the waiver picker


def test_a_waiver_option_can_be_found_by_its_identifier_or_its_title():
    """The haystack is written by the server, folded once, in its language.

    Doing it in the script instead would mean lower-casing somebody else's
    alphabet in JavaScript, and the list is already rendered.
    """
    page = _landing()
    options = re.findall(r'data-waiver-option="([^"]*)"', page)

    assert options
    assert all(text == text.lower() for text in options)
    identifiers = re.findall(
        r'data-waiver-option="[^"]*">\s*<input type="checkbox" name="ignore_hardenings" value="([^"]+)"',
        page,
    )
    assert identifiers, "every option still submits under the one field name"
    assert all(name.lower() in haystack for name, haystack in zip(identifiers, options))


def test_the_search_field_is_hidden_until_its_script_reveals_it():
    """A search box that cannot search is worse than none at all."""
    page = _landing()

    assert "data-waiver-filter" in page
    assert 'id="waiver-empty"' in page
    # The reveal is a rule keyed to an attribute the script sets, not a style
    # attribute on the element.
    assert re.search(r'<div class="waiver-search">\s*<label', page)
    assert "style=" not in page[page.index('class="waiver-search"') : page.index("</div>", page.index('class="waiver-search"'))]


def test_every_group_and_option_carries_the_hooks_the_filter_hides_them_by():
    """A group left without its hook would keep a heading over an empty list."""
    page = _landing()

    groups = page.count("data-waiver-group")
    assert groups
    assert page.count('<div class="waiver-group"') == groups


# -------------------------------------------------- the address field's answer


def test_the_address_field_points_at_the_sentence_that_corrects_it():
    """A red bar is a colour carrying a meaning nothing spells out."""
    page = _landing()

    field = page[page.index('name="target_url"') - 400 : page.index('name="target_url"') + 800]
    assert "target-error" in field
    assert re.search(r'aria-describedby="[^"]*target-error', field)
    assert '<p class="field-error" id="target-error">' in page


def test_the_correction_is_not_hidden_behind_scripting():
    """CSS reveals it on :user-invalid, so a browser without scripts still helps."""
    page = _landing()
    error = page[page.index('id="target-error"') : page.index("</p>", page.index('id="target-error"'))]

    assert "hidden" not in error, "visibility is the stylesheet's decision, not an attribute"
    assert "style=" not in error


# ------------------------------------------------------------ the progress card


def test_the_progress_card_times_the_wait_without_interrupting_the_reader():
    """A reading that changes every second must not be announced every second."""
    configured = settings(allow_private_targets=True, verify_tls=False)
    app = create_app(configured)
    with TestClient(app) as test_client:
        store = app.state.store
        asyncio.run(
            store.create(
                IDENTIFIER,
                target="http://cloud.example.com",
                ignore_hardenings=(),
                output_format="dashboard",
            )
        )
        page = test_client.get(f"/scan/{IDENTIFIER}").text

    assert "data-elapsed=" in page
    assert '{duration}' in page, "the sentence is the server's, filled in by the script"
    elapsed = page[page.index('id="progress-elapsed"') : page.index("</span>", page.index('id="progress-elapsed"'))]
    assert 'aria-live="off"' in elapsed
    # The estimate does not depend on the script having run.
    assert "progress-timing" in page
