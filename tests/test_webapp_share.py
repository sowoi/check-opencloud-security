"""
Sharing a report without handing it to anybody on the way.

The address of a report page is the credential for it (ADR 0007), so the
tests here are mostly negative: no third party is contacted, no share-intent
URL is offered, and the text held out for pasting into a chat channel carries
the findings *without* the link. The positive half is small by comparison -
there is a ``mailto:`` and there are two clipboard buttons.
"""

from __future__ import annotations

import asyncio
import re

import pytest
from fastapi.testclient import TestClient

from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour
from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    settings,
)
from webapp.app import create_app
from webapp.tasks import run_scan

IDENTIFIER = "b6f2c0c5-1c4b-4f4e-9a3b-0d3f8b7c1a20"
ORIGIN = "https://scan.example.org"

# Anything that would fetch the page to build a preview of it, or that would
# carry the address off this origin as a side effect of a click.
THIRD_PARTY_SHARE = (
    "slack.com",
    "teams.microsoft.com",
    "office.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "linkedin.com",
    "wa.me",
    "telegram.me",
    "share?",
    "sharer",
    "intent/tweet",
)


@pytest.fixture
def report_page() -> str:
    """One real scan of the fake instance, rendered as the page a reader sees."""
    configured = settings(
        allow_private_targets=True,
        verify_tls=False,
        scan_timeout=5,
        public_base_url=ORIGIN,
    )
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


def _share_section(page: str) -> str:
    """Just the sharing card, so an assertion cannot pass on the rest of the page."""
    start = page.index('data-share-copy="link"') - 2000
    end = page.index("data-share-link-text") + 200
    return page[start:end]


def test_sharing_offers_no_third_party_and_names_none(report_page: str):
    """A service that unfurls a link would be fetching somebody's report to preview it."""
    section = _share_section(report_page)

    for host in THIRD_PARTY_SHARE:
        assert host not in section.lower(), f"{host} is offered a report address"


def test_the_email_link_is_a_mailto_and_reaches_no_server(report_page: str):
    """`mailto:` is handed to the reader's own client; nothing is posted anywhere."""
    hrefs = re.findall(r'href="(mailto:[^"]*)"', report_page)

    assert len(hrefs) == 1
    body = hrefs[0]
    # The report address travels in the body the reader chooses to send.
    assert "scan.example.org" in body.replace("%3A", ":").replace("%2F", "/")
    assert "http" not in body.split("body=")[0]


def test_the_summary_for_a_chat_channel_carries_no_link(report_page: str):
    """Pasting findings into a channel must not hand everyone in it a capability."""
    summary = re.search(
        r"<div hidden data-share-summary-text>(.*?)</div>", report_page, re.DOTALL
    )
    assert summary is not None
    text = summary.group(1)

    assert "OpenCloud security report" in text
    # The negative, which is the whole reason this exists separately.
    assert IDENTIFIER not in text
    assert "http://" not in text and "https://" not in text
    assert "/scan/" not in text


def test_the_copy_buttons_are_hidden_until_a_script_can_use_them(report_page: str):
    """A button that cannot reach a clipboard is worse than the address in plain text."""
    section = _share_section(report_page)
    buttons = re.findall(r"<button[^>]*data-share-copy[^>]*>", section)

    assert len(buttons) == 2
    for button in buttons:
        assert "hidden" in button
    # And the reader who never runs the script still gets the address.
    assert "data-share-fallback" in report_page


def test_the_reader_is_told_the_address_is_the_credential(report_page: str):
    """Someone about to paste a link into a channel needs to know what it grants."""
    section = _share_section(report_page)

    assert "share-warning" in report_page
    assert "anyone who has it" in report_page.lower()
    assert "expires" in report_page.lower()
    assert section


def test_sharing_adds_no_inline_script_or_handler(report_page: str):
    """The CSP has no `unsafe-inline`, so a handler in the markup would not run."""
    section = _share_section(report_page)

    assert "onclick" not in section.lower()
    assert "<script" not in section.lower()
    assert "javascript:" not in section.lower()
