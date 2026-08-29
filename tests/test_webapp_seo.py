"""
Being found, and not being found.

The pages that explain the service are public documentation and should turn
up in a search; a result is a capability behind a uuid and must never leave
this server in a crawler's index. These tests hold that line from both sides,
and they also protect the header nav on a phone - a menu wider than the
screen is a menu whose last entries nobody reaches.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from xml.dom import minidom  # nosec B408 - parses this server's own output

import pytest

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
    settings,
)
from webapp.app import create_app
from webapp.documentation import DOCUMENTATION_PAGES
from webapp.seo import PUBLIC_PAGES

NAV_PAGES = (
    "/",
    "/how-it-works",
    "/grades",
    "/catalogue",
    "/documentation",
    "/api",
    "/ai",
    "/cli",
    "/privacy",
    "/about",
)
CONTENT_PAGES = (
    *NAV_PAGES,
    *(f"/documentation/{page.slug}" for page in DOCUMENTATION_PAGES),
)


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


def test_agents_txt_matches_robots_and_names_the_agent_facing_endpoints():
    """
    Two files a fetcher might read first must not disagree.

    `agents.txt` reuses the same allow/disallow list as `robots.txt` and adds
    what a crawling convention has no field for - the discovery document, the
    contracts and the MCP endpoint - so an agent finds the tools, not only
    the pages.
    """
    robots = client().get("/robots.txt").text
    body = client().get("/agents.txt").text

    assert body.startswith("User-agent: *\nAllow: /\n")
    assert "Disallow: /scan/" in body
    assert "Disallow: /api/" in body
    assert "Disallow: /\n" not in body
    # The negative half: both documents agree on what is off limits.
    for line in body.splitlines():
        if line.startswith("Disallow:"):
            assert line in robots
    assert "# Discovery: http://testserver/.well-known/ai.json" in body
    assert "Tools (Model Context Protocol): http://testserver/mcp" in body


def test_agents_txt_is_a_flat_refusal_when_indexing_is_off():
    """A private deployment should not hand an agent a list of its tools either."""
    body = client(allow_indexing=False).get("/agents.txt").text

    assert body == "User-agent: *\nDisallow: /\n"


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


def test_the_public_origin_is_required_before_the_service_starts():
    """
    Canonicals and discovery documents must not reflect an untrusted Host header.

    A stable origin is deployment configuration, not a fact a client is
    allowed to supply in the request that it wants indexed.
    """
    with pytest.raises(ValueError, match="COS_WEB_PUBLIC_BASE_URL is required"):
        create_app(settings(public_base_url=None))


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


def test_search_results_are_useful_navigation_but_not_search_engine_content():
    """
    A query page has no standalone subject and must not become a doorway page.

    Search engines should follow its documentation links, but never index an
    unbounded set of query URLs that compete with the source documents.
    """
    response = client().get("/search?q=tls")

    assert response.status_code == 200
    assert '<meta name="robots" content="noindex, nofollow">' in response.text
    assert "rel=\"canonical\"" not in response.text
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert "/search" not in client().get("/sitemap.xml").text


def test_structured_data_uses_valid_json_and_never_describes_private_results():
    """
    JSON-LD is a machine contract, not HTML with a different content type.

    Escaped catalogue text broke localized parsers, while putting an
    application record on a UUID result would associate private evidence with
    the public service.
    """
    public = client().get("/", headers={"accept-language": "fr"}).text
    script = re.search(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        public,
        re.DOTALL,
    )
    assert script is not None
    document = json.loads(script.group(1))
    assert document["url"] == "http://testserver/"
    assert "&#" not in document["description"]

    identifier = _create(client()).json()["uuid"]
    private = client().get(f"/scan/{identifier}").text
    assert 'application/ld+json' not in private


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
    for path in NAV_PAGES:
        assert f'href="{path}"' in nav
    assert '[data-nav="enhanced"] .site-nav { display: none; }' in css
    assert 'document.documentElement.setAttribute("data-nav", "enhanced")' in (
        client().get("/static/js/nav.js").text
    )


def test_the_legal_notice_is_served_only_by_the_deployment_it_names():
    """
    The notice carries one operator's name, address and phone number.

    A self-hosted copy that served it would publish somebody else's contact
    details as its own, and would tell a visitor that a stranger is legally
    responsible for a service they are not.
    """
    served = client()

    hosted = served.get("/legal-notice", headers={"host": "scan.okxo.de"})
    elsewhere = served.get("/legal-notice", headers={"host": "scanner.example.com"})

    assert hosted.status_code == 200
    assert "Hauptstr 151" in hosted.text
    assert elsewhere.status_code == 404
    assert "Hauptstr 151" not in elsewhere.text


def test_only_that_deployment_offers_the_legal_notice_in_its_footer():
    """A link to a 404 is worse than no link, and the notice is not indexable."""
    served = client()

    hosted = served.get("/", headers={"host": "scan.okxo.de"})
    elsewhere = served.get("/", headers={"host": "scanner.example.com"})

    assert 'href="/legal-notice"' in hosted.text
    assert 'href="/legal-notice"' not in elsewhere.text
    # The external link it replaced is gone from every page.
    assert "okxo.de/impressum-legal-notice" not in hosted.text
    assert "/legal-notice" not in served.get("/sitemap.xml").text
    assert 'name="robots" content="noindex, nofollow"' in (
        served.get("/legal-notice", headers={"host": "scan.okxo.de"}).text
    )


def test_a_security_report_about_this_service_has_somewhere_to_go():
    """
    RFC 9116 is the first place a researcher looks, and an absent or expired
    document sends the report to a contact form, a social account, or nowhere.
    """
    response = client().get("/.well-known/security.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "Contact: https://github.com/sowoi/check-opencloud-security" in body
    assert "Policy: " in body

    expires = [line for line in body.splitlines() if line.startswith("Expires: ")]
    assert len(expires) == 1, "the field is mandatory and must appear exactly once"
    moment = datetime.strptime(
        expires[0][len("Expires: ") :] + "+0000", "%Y-%m-%dT%H:%M:%SZ%z"
    )
    assert moment > datetime.now(timezone.utc), (
        "a document that has already expired is treated as no document at all"
    )


def test_only_the_named_deployment_gives_out_the_operator_address():
    """
    A self-hosted copy must not direct reports about itself to an operator
    who has no access to it and cannot fix anything.
    """
    served = client()

    hosted = served.get(
        "/.well-known/security.txt", headers={"host": "scan.okxo.de"}
    )
    elsewhere = served.get(
        "/.well-known/security.txt", headers={"host": "scanner.example.com"}
    )

    assert "mailto:okko@okxo.de" in hosted.text
    assert "mailto:" not in elsewhere.text
    # Both still reach the project, which is where a scanner flaw belongs.
    assert "Policy: " in elsewhere.text


def test_a_crawler_is_not_told_to_stay_out_of_the_security_contact():
    """robots.txt must not hide the one file a reporting tool goes looking for."""
    body = client().get("/robots.txt").text

    assert "Disallow: /.well-known" not in body
    assert "Disallow: /\n" not in body
