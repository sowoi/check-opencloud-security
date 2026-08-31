"""
The configuration fragment on a report page.

The rendering itself is ``tests/test_snippets.py``' subject. What is tested
here is the join: that the page offers every flavour rather than only the one
a script happens to select, that it is built from the findings this scan
actually reported, and that it stays inside the policy the rest of the site
is served under.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from opencloud_local_scan.snippets import FLAVOURS
from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour
from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    settings,
)
from webapp.app import _configuration_fragments, create_app
from webapp.catalog import open_findings
from webapp.tasks import run_scan

IDENTIFIER = "c4e7b118-2a63-40df-9d15-6b8e2f0a7c94"


@pytest.fixture
def report_page() -> str:
    """A scan of an instance with something to fix, rendered as a reader sees it."""
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


def _card(page: str) -> str:
    """Just the fragment card, so an assertion cannot pass on the rest of the page."""
    start = page.index('id="fragment-card"')
    return page[start:page.index("</section>", start)]


def test_every_flavour_is_on_the_page_rather_than_fetched_per_click(report_page: str):
    """
    All five are rendered server-side. Fetching one per click would be a round
    trip for a picker, and building them in the browser would be a second
    implementation of the module the library tests cover.
    """
    card = _card(report_page)

    for flavour in FLAVOURS:
        assert f'data-fragment="{flavour.id}"' in card, f"{flavour.id} is missing"
        assert f'data-flavour="{flavour.id}"' in card


def test_the_picker_is_hidden_until_a_script_can_drive_it(report_page: str):
    """
    Without fragment.js the buttons do nothing, so they are not shown - and
    every fragment stays visible under its own heading instead. Offering five
    dead buttons and one visible block would hide the nginx fragment from the
    reader who runs nginx.
    """
    card = _card(report_page)
    picker = card[card.index('class="flavour-picker"'):]

    assert picker[:200].count("hidden") == 1
    assert card.count('class="fragment-name"') == len(FLAVOURS)


def test_the_fragment_is_built_from_what_this_scan_found(report_page: str):
    """
    The fake instance answers a Basic challenge, so the fragment must carry
    the assignment that turns it off - and must not carry fixes for findings
    this instance does not have.
    """
    card = _card(report_page)

    assert "PROXY_ENABLE_BASIC_AUTH" in card
    # Demo users are off on the fake instance, so nothing should offer to
    # switch them off again.
    assert "IDM_CREATE_DEMO_USERS" not in card


def test_a_summary_with_nothing_open_produces_no_fragments():
    """
    Nothing open means nothing to paste, and an empty Compose block under a
    heading saying "paste this" is an instruction to change nothing. The card
    is conditional on this being empty, so this is what keeps it off the page.
    """
    assert _configuration_fragments({}) == ()
    assert (
        _configuration_fragments(
            {"issues": [], "missingHardenings": [], "missingHeaders": []}
        )
        == ()
    )


def test_only_what_is_still_open_reaches_the_fragment():
    """
    A waived finding was excluded deliberately and an unfixable one cannot be
    acted on. Either appearing here would be the page handing back work the
    reader had already dealt with.
    """
    names = open_findings(
        {
            "issues": [{"id": "basicAuthDisabled"}],
            "missingHardenings": [{"id": "demoUsersDisabled"}],
            "missingHeaders": [{"id": "X-Frame-Options"}],
            "waived": [{"id": "corsOriginRestricted"}],
            "unfixable": ["publicLinkExpirationEnforced"],
        }
    )

    assert names == ("basicAuthDisabled", "demoUsersDisabled", "X-Frame-Options")
    assert "corsOriginRestricted" not in names
    assert "publicLinkExpirationEnforced" not in names


def test_the_copy_button_is_hidden_until_a_clipboard_exists(report_page: str):
    """
    A clipboard write needs a secure context. Offering a button that could
    never work is worse than not offering one: the fragment is on the page and
    can be selected by hand.
    """
    card = _card(report_page)
    start = card.index("data-copy-fragment")

    assert "hidden" in card[start - 120:start]


def test_the_fragment_card_adds_no_inline_script_or_handler(report_page: str):
    """
    The policy has no 'unsafe-inline'. An inline handler here would be dropped
    by the browser and the picker would silently do nothing.
    """
    card = _card(report_page)

    assert "onclick" not in card
    assert "style=" not in card
    assert "<script" not in card


def test_the_card_is_listed_in_the_table_of_contents(report_page: str):
    """A section a reader cannot navigate to is a section below the fold."""
    assert 'href="#configuration"' in report_page


@pytest.mark.parametrize("locale", ["de", "fr", "es"])
def test_the_fragment_labels_are_translated_and_keep_their_placeholders(locale: str):
    """
    Two of these sentences carry a value the template fills in. A translation
    that dropped the placeholder would name no file and no flavour.
    """
    from webapp.locales import CATALOGUES

    assert "{name}" in CATALOGUES[locale]["result.fragment.file"]
    assert "{flavours}" in CATALOGUES[locale]["result.fragment.elsewhere"]
    assert (
        CATALOGUES[locale]["result.fragment.heading"]
        != CATALOGUES["en"]["result.fragment.heading"]
    )
