"""
The prose that used to sit under the form now lives on its own pages.

These tests protect the split itself: that the landing page stays about
scanning, that nothing was lost on the way out of it, and that every new page
is reachable, self-describing and reachable *back* from.
"""

from __future__ import annotations

import re

import pytest

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
)

CONTENT_PAGES = ("/how-it-works", "/api", "/privacy", "/about")


@pytest.mark.parametrize(
    ("path", "heading"),
    [
        ("/how-it-works", "How the scan works"),
        ("/api", "Scanning from a script"),
        ("/privacy", "What this server keeps"),
        ("/about", "About OpenCloud and this scanner"),
    ],
)
def test_each_explanation_has_a_page_of_its_own(path: str, heading: str):
    """
    A visitor sent a link to one explanation should land on that explanation.

    Before the split every one of these was an anchor halfway down a very long
    landing page, which is unreadable on a phone and impossible to link to
    with any confidence.
    """
    page = client().get(path)

    assert page.status_code == 200
    assert f"<h1>{heading}</h1>" in page.text


def test_the_landing_page_leads_with_the_form_and_delegates_the_prose():
    """
    The first screen is the product: an address field, not an essay.

    The moved sections must be gone from it - a page that keeps both the
    summary and the full text has not been shortened at all - while every one
    of them stays one click away.
    """
    body = client().get("/").text

    assert 'name="target_url"' in body
    for moved in (
        "What happens when you press the button",
        "The operational log records",
        "curl -X POST",
        "docs.opencloud.eu",
    ):
        assert moved not in body
    for path in CONTENT_PAGES:
        assert f'href="{path}"' in body


def test_a_content_page_links_on_but_never_to_itself():
    """
    A cross-link back to the page you are reading is a dead end dressed as one.

    The "Read on" block is built from the request path, so a bug there shows
    up as a card pointing at the current page - and as a missing way back to
    the form, which is the only thing a visitor came here to use.
    """
    test_client = client()

    for path in CONTENT_PAGES:
        body = test_client.get(path).text
        read_on = body.split('class="page-nav', 1)[1].split("</nav>", 1)[0]
        assert f'href="{path}"' not in read_on
        for other in CONTENT_PAGES:
            if other != path:
                assert f'href="{other}"' in read_on
        assert 'class="card page-nav-card page-nav-cta" href="/"' in read_on


def test_every_page_is_navigable_from_every_other_one():
    """
    The header nav is the map: losing an entry hides a page for good.

    There is no site search and no listing endpoint, so a page that is not in
    the nav and not in a "Read on" block cannot be found at all.
    """
    test_client = client()

    for path in ("/", *CONTENT_PAGES):
        body = test_client.get(path).text
        nav = body.split('class="site-nav"', 1)[1].split("</nav>", 1)[0]
        for target in ("/", *CONTENT_PAGES):
            assert f'href="{target}"' in nav
        assert f'href="{path}" aria-current="page"' in nav


def test_a_content_page_carries_no_inline_style_or_script():
    """
    The strict CSP applies to the new pages as much as to the old one.

    A `style=` attribute or an `onclick` would be dropped by the browser and
    the page would look broken for everybody but its author.
    """
    test_client = client()

    for path in CONTENT_PAGES:
        body = test_client.get(path).text
        assert "style=" not in body
        assert "<style" not in body
        assert "onclick" not in body
        assert "<script>" not in body


def test_the_new_pages_are_not_advertised_in_the_openapi_schema():
    """
    The schema describes the JSON API; HTML pages are noise in a client generator.

    `/api` in particular is a page about the API, and a generated client that
    grew a `get_api_page()` method would be quietly wrong.
    """
    schema = client(enable_docs=True).get("/openapi.json").json()

    for path in CONTENT_PAGES:
        assert path not in schema["paths"]
    assert "/api/scans" in schema["paths"]


def test_the_moved_prose_survived_the_move():
    """
    Splitting a page is only safe if nothing quietly falls out of it.

    Each of these sentences answered a question a visitor actually asks; a
    move that dropped one would look like a tidier site and read like a less
    honest one.
    """
    test_client = client()
    kept = {
        "/how-it-works": (
            "Private, loopback and\n      cloud metadata addresses are refused",
            "Version and lifecycle",
            "Transport and headers",
            "Hardening and exposure",
        ),
        "/privacy": ("one-way\n    fingerprint for rate limiting",),
        "/api": ("curl https://scan.okxo.de/api/scans", "<code>202</code>"),
        "/about": ("https://opencloud.eu/", "docs.opencloud.eu"),
    }

    for path, phrases in kept.items():
        body = test_client.get(path).text
        for phrase in phrases:
            assert re.sub(r"\s+", " ", phrase) in re.sub(r"\s+", " ", body)


def test_an_unknown_page_is_still_a_404():
    """
    Adding routes must not turn a typo into a match.

    A prefix route or a catch-all would make `/privacy-policy` render the
    privacy page, which hides real broken links behind a page that looks fine.
    """
    test_client = client()

    assert test_client.get("/privacy-policy").status_code == 404
    assert test_client.get("/how-it-works/extra").status_code == 404
    assert test_client.get("/privacy").status_code == 200
