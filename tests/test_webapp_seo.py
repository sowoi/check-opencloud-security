"""
Being found, and not being found.

The pages that explain the service are public documentation and should turn
up in a search; a result is a capability behind a uuid and must never leave
this server in a crawler's index. These tests hold that line from both sides,
and they also protect the header nav on a phone - a menu wider than the
screen is a menu whose last entries nobody reaches.
"""

from __future__ import annotations

import re
from xml.dom import minidom  # nosec B408 - parses this server's own output

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
)
from webapp.seo import PUBLIC_PAGES

CONTENT_PAGES = ("/", "/how-it-works", "/api", "/ai", "/privacy", "/about")


def _create(test_client, target: str = "https://opencloud.example.com"):
    return test_client.post("/api/scans", json={"target_url": target})


def test_the_sitemap_lists_every_public_page_and_only_those():
    """
    A sitemap is the list of pages this service admits to having.

    Generated from the page list rather than written by hand, because a
    sitemap that has drifted from the routes is worse than none: it teaches a
    crawler to distrust the file it reads first.
    """
    response = client().get("/sitemap.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    document = minidom.parseString(response.text)  # nosec B318 - our own output
    locations = [
        node.firstChild.nodeValue
        for node in document.getElementsByTagName("loc")
    ]

    assert locations == [
        "http://testserver/" if page.path == "/" else f"http://testserver{page.path}"
        for page in PUBLIC_PAGES
    ]
    assert len(locations) == len(CONTENT_PAGES)
    # Every entry carries a date, and it is the template's own.
    assert len(document.getElementsByTagName("lastmod")) == len(locations)


def test_the_sitemap_never_mentions_a_result():
    """
    A uuid is the whole of the authorisation, and a sitemap is a listing.

    An entry for a scan would publish somebody else's result to every crawler
    on the internet, which is exactly what the absent listing endpoint exists
    to prevent.
    """
    test_client = client()
    identifier = _create(test_client).json()["uuid"]

    body = test_client.get("/sitemap.xml").text

    assert identifier not in body
    assert "/scan/" not in body


def test_the_sitemap_follows_the_configured_public_address():
    """
    Behind a proxy the service only ever sees its own internal address.

    Publishing that address would fill the sitemap with URLs nobody outside
    can reach, so the operator's answer wins over the request's.
    """
    body = client(public_base_url="https://scan.example.com/").get("/sitemap.xml").text

    assert "<loc>https://scan.example.com/</loc>" in body
    assert "testserver" not in body


def test_robots_points_at_the_sitemap_and_keeps_crawlers_out_of_the_results():
    """
    The first file a crawler reads decides what it does with the rest.

    `/api` is a page about the API and stays crawlable; everything under
    `/api/` is the API itself, and `/scan/` is somebody's result.
    """
    response = client().get("/robots.txt")

    assert response.status_code == 200
    body = response.text
    assert "Sitemap: http://testserver/sitemap.xml" in body
    assert "Disallow: /scan/" in body
    assert "Disallow: /api/" in body
    assert "Disallow: /api\n" not in body
    assert "Disallow: /\n" not in body


def test_indexing_can_be_turned_off_completely():
    """
    A private deployment should be able to disappear.

    Turning it off has to hold on every channel at once: a flat robots.txt, no
    sitemap to read instead, and `noindex` on the pages themselves.
    """
    test_client = client(allow_indexing=False)

    robots = test_client.get("/robots.txt")
    assert robots.text == "User-agent: *\nDisallow: /\n"
    assert "Sitemap:" not in robots.text
    assert test_client.get("/sitemap.xml").status_code == 404

    landing = test_client.get("/")
    assert '<meta name="robots" content="noindex, nofollow">' in landing.text
    assert "rel=\"canonical\"" not in landing.text
    assert landing.headers["x-robots-tag"] == "noindex, nofollow"


def test_a_public_page_is_indexable_and_names_itself_once():
    """
    A page that may be indexed says so, and says which address it is.

    Without a canonical URL the same page under a second host name is two
    pages competing with each other; with the wrong one it is nobody's.
    """
    test_client = client()

    for path in CONTENT_PAGES:
        body = test_client.get(path).text
        expected = "http://testserver/" if path == "/" else f"http://testserver{path}"
        assert '<meta name="robots" content="index, follow">' in body
        assert f'<link rel="canonical" href="{expected}">' in body
        assert f'<meta property="og:url" content="{expected}">' in body
        assert '<meta property="og:title"' in body


def test_no_page_carries_metadata_for_a_surveillance_platform():
    """
    Being findable must not mean being wired to somebody's advertising graph.

    Card metadata for Twitter, Google or Meta is markup that makes no request
    of its own, which is exactly why it survives a review: the cost is not a
    byte on the wire but a page tuned for the platforms this service exists
    to keep out of a security report.
    """
    test_client = client()
    forbidden = ("twitter:", "fb:", "og:video", "google-site-verification")

    for path in (*CONTENT_PAGES, "/404-not-a-page"):
        body = test_client.get(path).text.lower()
        for marker in forbidden:
            assert marker not in body, f"{marker} on {path}"
        # The negative half: the open metadata that names no platform stays.
        if path in CONTENT_PAGES:
            assert '<meta property="og:title"' in body


def test_a_result_page_is_never_indexable():
    """
    The one page that must stay out of a search index is the one with a
    result on it.

    Both channels have to say so: the meta tag for the rendered page and the
    header for everything a crawler reaches that renders no template at all.
    """
    test_client = client()
    identifier = _create(test_client).json()["uuid"]

    response = test_client.get(f"/scan/{identifier}")

    assert response.status_code == 200
    assert '<meta name="robots" content="noindex, nofollow">' in response.text
    assert "rel=\"canonical\"" not in response.text
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert test_client.get(f"/api/scans/{identifier}").headers["x-robots-tag"]


def test_every_page_has_a_title_and_a_description_of_its_own():
    """
    A shared title and description make five pages look like one duplicate.

    They are also the only two lines a search result shows, so a page without
    them is a page nobody clicks.
    """
    test_client = client()
    titles = set()
    descriptions = set()

    for path in CONTENT_PAGES:
        body = test_client.get(path).text
        title = re.search(r"<title>(.*?)</title>", body, re.DOTALL)
        description = re.search(r'<meta name="description" content="(.*?)">', body, re.DOTALL)
        assert title and description
        assert "OpenCloud Security Scan" in title.group(1)
        titles.add(title.group(1))
        descriptions.add(description.group(1))

    assert len(titles) == len(CONTENT_PAGES)
    assert len(descriptions) == len(CONTENT_PAGES)


def test_the_header_nav_collapses_behind_a_button_on_a_narrow_screen():
    """
    Six links and a brand line do not fit across a phone.

    They used to run off the side of the screen, so the last entries could
    only be reached by scrolling the page sideways. The button is the fix, and
    it has to be a real control - labelled, and wired to the menu it opens.
    """
    body = client().get("/").text

    assert 'class="nav-toggle"' in body
    assert 'aria-controls="site-nav"' in body
    assert 'aria-expanded="false"' in body
    assert 'id="site-nav"' in body
    assert '<script src="/static/js/nav.js" defer></script>' in body
    # The control is a button, not a link that would navigate somewhere.
    assert '<button class="nav-toggle" type="button"' in body


def test_the_nav_stays_usable_without_javascript():
    """
    The collapsed menu is an enhancement, and enhancements can fail to load.

    Nothing in the markup hides the links: the collapsed layout only applies
    once `nav.js` has marked the document, so a browser that never ran it
    shows every entry and wraps them onto a second row.
    """
    body = client().get("/").text
    css = client().get("/static/css/app.css").text

    nav = body.split('class="site-nav"', 1)[1].split("</nav>", 1)[0]
    for path in CONTENT_PAGES:
        assert f'href="{path}"' in nav
    assert '[data-nav="enhanced"] .site-nav { display: none; }' in css
    assert 'document.documentElement.setAttribute("data-nav", "enhanced")' in (
        client().get("/static/js/nav.js").text
    )
