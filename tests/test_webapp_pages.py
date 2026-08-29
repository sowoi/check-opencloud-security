"""
The prose that used to sit under the form now lives on its own pages.

These tests protect the split itself: that the landing page stays about
scanning, that nothing was lost on the way out of it, and that every new page
is reachable, self-describing and reachable *back* from.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
)

CONTENT_PAGES = (
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


@pytest.mark.parametrize(
    ("path", "heading"),
    [
        ("/how-it-works", "How the scan works"),
        ("/grades", "What the grades mean"),
        ("/catalogue", "What the scanner checks"),
        ("/documentation", "Run the scanner from your terminal"),
        ("/search", "Search the scanner"),
        ("/api", "Scanning from a script"),
        ("/ai", "For AI agents"),
        ("/cli", "Run it yourself, in one line"),
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


def test_the_ai_page_explains_browser_webmcp_when_agent_tools_are_enabled():
    """A browser agent needs page-tool names and boundaries where users find AI help."""
    enabled = client(enable_mcp=True).get("/ai").text

    assert "Use the page as a tool" in enabled
    assert "scan_opencloud_security" in enabled
    assert "get_scan_result" in enabled
    assert "export_scan_report" in enabled
    assert "https://webmachinelearning.github.io/webmcp/" in enabled
    assert "Accept: application/json" in enabled

    disabled = client(enable_mcp=False).get("/ai").text
    assert "Use the page as a tool" not in disabled
    assert "scan_opencloud_security" not in disabled


def test_the_header_brand_is_short_and_cannot_wrap():
    """The first line must stay compact even before the menu is enhanced."""
    body = client().get("/").text
    css = (
        Path(__file__).resolve().parent.parent / "frontend/static/css/app.css"
    ).read_text(encoding="utf-8")

    assert "Security scan for OpenCloud</span>" in body
    assert "Security scan for OpenCloud instances" not in body
    assert re.search(r"\.brand\s*\{[^}]*white-space:\s*nowrap", css, re.DOTALL)
    assert re.search(r"\.site-nav\s*\{[^}]*white-space:\s*nowrap", css, re.DOTALL)


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
        assert 'action="/search"' in nav
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


# --- The result page, when our own data is older than the instance ---


def _finished_page(version: str, *, openid_issuer: str | None = None) -> str:
    """Scan a fake instance claiming ``version`` and return its result page."""
    import asyncio

    from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour
    from tests.webapp_support import MEMORY_URL, settings
    from webapp.redis_backend import memory_backend
    from webapp.store import ScanStore
    from webapp.tasks import run_scan

    identifier = "9d4b1f2e-3c4d-4a5b-8c9d-0e1f2a3b4c5d"
    configured = settings(allow_private_targets=True, verify_tls=False, scan_timeout=5)
    store = ScanStore(backend=memory_backend(MEMORY_URL), ttl=configured.result_ttl)
    behaviour = InstanceBehaviour()
    if openid_issuer is not None:
        behaviour.openid_issuer = openid_issuer
        behaviour.openid_redirect = True
    behaviour.status_payload["productversion"] = version
    with FakeOpenCloud(behaviour) as instance:
        asyncio.run(
            store.create(
                identifier,
                target=f"http://{instance.host}",
                ignore_hardenings=(),
                output_format="dashboard",
            )
        )
        asyncio.run(run_scan({"web_settings": configured, "store": store}, identifier))
    served = client(
        allow_private_targets=True, verify_tls=False, redis_url=MEMORY_URL
    )
    page = served.get(f"/scan/{identifier}")
    assert page.status_code == 200
    return page.text


def test_a_result_page_says_when_our_schedule_is_older_than_the_instance():
    """
    The bundled release schedule is a snapshot of a page that keeps moving,
    so a visitor who patched yesterday can be newer than the file we judged
    them with. Telling them - and linking the page the schedule came from -
    is the difference between an answer they can check and one they have to
    take on trust.
    """
    page = _finished_page("99.0.0")

    assert "Release schedule" in page
    assert "probably out of date" in page
    assert "docs.opencloud.eu/docs/admin/resources/lifecycle/" in page
    # The negative half, and the whole promise of it: being ahead of our data
    # is not a finding, so the page must not have marked them down for it.
    assert "End of life" not in page


def test_a_result_page_stays_quiet_when_the_schedule_knows_the_release():
    """A notice on every result would be furniture, and furniture is what
    people stop reading - it appears only when it is actually true."""
    from opencloud_local_scan.versions import load_release_schedule

    # Taken from the schedule that ships beside this test rather than typed
    # out, so regenerating the schedule cannot quietly make this pass for the
    # wrong reason.
    current = load_release_schedule().latest_for()
    assert current, "the bundled schedule should name a newest release"

    page = _finished_page(current)

    assert "Release schedule" not in page


def test_a_finished_result_links_false_reports_without_sharing_the_scan():
    """Issue reports must be possible without putting the capability in the URL."""
    from opencloud_local_scan.versions import load_release_schedule

    page = _finished_page(load_release_schedule().latest_for() or "7.2.3")
    link = re.search(
        r'<a href="([^"]+)" rel="noopener noreferrer">'
        r"Report a false positive or false negative</a>",
        page,
    )

    assert link is not None
    assert link.group(1) == (
        "https://github.com/sowoi/check-opencloud-security/issues"
    )
    assert "/scan/" not in link.group(1)
    assert "opencloud.example.com" not in link.group(1)


@pytest.mark.parametrize(
    ("issuer", "vendor", "advisory_url"),
    [
        (
            "https://id.example.com/realms/opencloud",
            "Keycloak",
            "https://github.com/keycloak/keycloak/security/advisories",
        ),
        (
            "https://id.example.com/api/oidc",
            "Authelia",
            "https://github.com/authelia/authelia/security/advisories",
        ),
        (
            "https://id.example.com/application/o/opencloud/",
            "Authentik",
            "https://github.com/goauthentik/authentik/security/advisories",
        ),
    ],
)
def test_a_result_links_recognised_identity_providers_to_their_advisories(
    issuer: str, vendor: str, advisory_url: str
):
    """The overview must offer a current source without inventing a version."""
    from opencloud_local_scan.versions import load_release_schedule

    page = _finished_page(
        load_release_schedule().latest_for() or "7.2.3",
        openid_issuer=issuer,
    )

    assert vendor in page
    assert "version not exposed" in page
    assert f'href="{advisory_url}"' in page
    assert "check security advisories" in page


def test_a_result_page_shows_the_addresses_the_instance_resolved_to():
    """
    A grade is about a machine, and the address is which machine it was.

    Somebody looking at an unexpected result needs to know whether the name
    still points where they think it does - so the overview prints the IPv4
    and IPv6 the scan actually connected to.
    """
    from opencloud_local_scan.versions import load_release_schedule

    page = _finished_page(load_release_schedule().latest_for() or "7.2.3")

    assert "Resolved to" in page
    assert "127.0.0.1" in page


def test_a_result_without_addresses_prints_no_empty_row():
    """
    A document from an older scanner still has to render.

    An 'unknown' row on every such result would be furniture; the summary
    normalises the missing block to empty lists and the template leaves the
    row out entirely.
    """
    from webapp.catalog import summarise

    summary = summarise({"rating": 5, "domain": "opencloud.example.com"})

    assert summary["addresses"] == {"ipv4": [], "ipv6": []}
    # And the positive half, so this cannot pass by returning empty always.
    kept = summarise(
        {"rating": 5, "addresses": {"ipv4": ["198.51.100.7"], "ipv6": ["2001:db8::7"]}}
    )
    assert kept["addresses"] == {"ipv4": ["198.51.100.7"], "ipv6": ["2001:db8::7"]}


def test_summary_reports_whether_the_scanner_could_reach_ipv6_at_all():
    """
    A document from a deployment with no IPv6 route says so, so the page can
    explain why an instance's IPv6 side went unchecked instead of counting it
    against the rating.
    """
    from webapp.catalog import summarise

    # A document from an older scanner has no such key and defaults to true,
    # matching every scanner that predates this flag.
    assert summarise({"rating": 5})["ipv6Enabled"] is True
    assert summarise({"rating": 5, "ipv6Enabled": False})["ipv6Enabled"] is False


def test_the_one_liner_page_is_a_menu_tab_of_its_own():
    """
    The visitor who does not want to use this website should find that out from it.

    The command belongs where the hesitation happens, so it gets a tab in the
    primary navigation rather than a sentence buried on another page - and the
    page names the published image and links the full documentation.
    """
    test_client = client()
    page = test_client.get("/cli")

    assert page.status_code == 200
    assert "okxo/opencloud-scanner" in page.text
    assert "docs/docker-oneliner.md" in page.text

    for path in ("/", "/api", "/about"):
        assert 'href="/cli"' in test_client.get(path).text


def test_the_grade_page_uses_the_plugins_real_scale():
    """
    The explanation must never invent a letter the plugin cannot produce.

    In particular, this scale deliberately has no B; deriving the page from
    RATE_MAP keeps an innocent-looking copy edit from changing a monitoring
    contract.
    """
    from check_opencloud_security import RATE_MAP

    page = client().get("/grades")

    assert page.status_code == 200
    for rating, label in RATE_MAP.items():
        assert f">{label}</span>" in page.text
        assert f"{rating} out of 5" in page.text
    assert "there is no <strong>B</strong>" in page.text
    assert ">B</span>" not in page.text


def test_the_grade_page_explains_how_a_result_can_improve():
    """A grade without a route upward is a scoreboard rather than a tool."""
    page = client().get("/grades").text

    assert "How this scanner helps you climb" in page
    assert "A remediation plan, in payoff order" in page
    assert "The exact release to move to" in page
    assert "End of life overrides" in page


def test_the_docs_tab_is_a_local_cli_reference_and_a_guide_index():
    """
    A visitor should not need a third-party renderer to read the common path.

    The page carries working commands and configuration precedence locally,
    then points at the repository documents for the long operator guides.
    """
    page = client().get("/documentation")

    assert page.status_code == 200
    assert "check-opencloud-security --configure" in page.text
    assert "check-opencloud-scanner scan" in page.text
    assert "--ignore-hardening" in page.text
    assert "CLI flag" in page.text
    assert "Environment" in page.text
    assert "/blob/main/" not in page.text
    for slug in (
        "reference",
        "docker",
        "scheduling",
        "many-instances",
        "troubleshooting",
    ):
        assert f'href="/documentation/{slug}"' in page.text


def test_about_names_the_author_and_the_reason_for_the_project():
    """The project's origin belongs on About, not hidden in package metadata."""
    page = client().get("/about").text

    assert "Massoud Ahmed" in page
    assert "alternative to" in page
    assert "<code>scan.nextcloud.com</code>" in page
