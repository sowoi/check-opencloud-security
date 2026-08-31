"""
Clicking a finding has to land on the paragraph that explains it.

A result page names identifiers - ``basicAuthDisabled``,
``exposed:/config/opencloud.yaml`` - and the catalogue is where each one is
explained. The link between them is built from one function on both sides, so
the property worth testing is that no report can offer a fragment the
catalogue does not publish, in either direction.

The contents list is here for the same reason: an entry pointing at a section
that was not rendered is a link to nowhere on the reader's own page.
"""

from __future__ import annotations

import asyncio
import re

import pytest
from fastapi.testclient import TestClient

from opencloud_local_scan.hardening import catalogue_id
from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour
from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    settings,
)
from webapp.app import create_app
from webapp.catalog import catalogue_anchor, catalogue_link, check_catalogue
from webapp.tasks import run_scan

IDENTIFIER = "b6f2c0c5-1c4b-4f4e-9a3b-0d3f8b7c1a20"


@pytest.fixture
def pages() -> tuple[str, str]:
    """A real scan of an instance with something wrong, and the catalogue."""
    configured = settings(
        allow_private_targets=True,
        verify_tls=False,
        scan_timeout=5,
        public_base_url="https://scan.example.org",
    )
    app = create_app(configured)
    with TestClient(app) as test_client:
        store = app.state.store
        behaviour = InstanceBehaviour(
            basic_auth=True,
            debug_endpoints=True,
            # A per-path family finding, so the family case is exercised
            # rather than only the plain identifiers.
            exposed_paths={"/config/opencloud.yaml", "/.env"},
        )
        with FakeOpenCloud(behaviour) as instance:
            asyncio.run(
                store.create(
                    IDENTIFIER,
                    target=f"http://{instance.host}",
                    ignore_hardenings=(),
                    output_format="dashboard",
                )
            )
            asyncio.run(run_scan({"web_settings": configured, "store": store}, IDENTIFIER))
        return (
            test_client.get(f"/scan/{IDENTIFIER}").text,
            test_client.get("/catalogue").text,
        )


def _links(report: str) -> list[str]:
    return sorted(set(re.findall(r'href="/catalogue#(check-[^"]+)"', report)))


def _anchors(catalogue: str) -> set[str]:
    return set(re.findall(r'<li class="finding" id="(check-[^"]+)"', catalogue))


def test_every_link_a_report_offers_lands_on_a_real_catalogue_entry(pages):
    """A fragment the catalogue does not publish drops the reader at the top of it."""
    report, catalogue = pages
    links = _links(report)

    assert links, "the report offered no catalogue links at all"
    assert _anchors(catalogue), "the catalogue published no anchors at all"
    assert [link for link in links if link not in _anchors(catalogue)] == []


def test_a_per_path_finding_links_to_the_family_the_catalogue_lists(pages):
    """The catalogue lists `exposed` once, not every path an instance might serve."""
    report, catalogue = pages

    assert catalogue_link("exposed:/config/opencloud.yaml") == "/catalogue#check-exposed"
    assert "check-exposed" in _anchors(catalogue)
    # The finding is named in full on the report; only the link is rooted.
    assert "exposed:/config/opencloud.yaml" in report


def test_an_identifier_this_build_cannot_explain_is_not_linked():
    """A link promising an explanation that is not there is worse than no link."""
    assert catalogue_anchor("somethingNobodyHasHeardOf") is None
    assert catalogue_link("somethingNobodyHasHeardOf") is None
    # And the ones it can explain are not swept up by the same rule.
    assert catalogue_anchor("basicAuthDisabled") == "check-basicAuthDisabled"


def test_every_catalogue_entry_resolves_to_its_own_anchor():
    """The two sides are one function, so a family root must resolve to itself."""
    identifiers = [check.id for category in check_catalogue() for check in category.checks]

    assert identifiers
    assert [name for name in identifiers if catalogue_id(name) != name] == []


def test_the_contents_list_names_only_sections_the_report_rendered(pages):
    """An entry for a card that is not there is a link to nowhere on this page."""
    report, _ = pages
    contents = re.search(r'<nav class="docs-toc.*?</nav>', report, re.DOTALL)
    assert contents is not None

    entries = re.findall(r'href="#([^"]+)"', contents.group(0))
    assert len(entries) > 1
    for entry in entries:
        assert f'id="{entry}"' in report, f"contents names #{entry}, which is not on the page"


def test_a_section_the_scan_did_not_produce_gets_no_contents_entry(pages):
    """This instance has no advisories, so the reader is not offered that jump."""
    report, _ = pages
    contents = re.search(r'<nav class="docs-toc.*?</nav>', report, re.DOTALL)
    assert contents is not None

    assert "#advisories" not in contents.group(0)
    assert 'id="advisories"' not in report
    # The sections it did produce are named.
    assert "#findings" in contents.group(0)
