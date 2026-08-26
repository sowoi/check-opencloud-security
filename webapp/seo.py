"""
Discoverability: robots.txt, sitemap.xml and the canonical URL of a page.

The service itself is not a secret. The landing page, its explanations and
the generated operator documentation are public, and a person looking for a
way to check an OpenCloud instance should be able to find them. A *result* is
the opposite: the uuid is the whole of the authorisation, so nothing under
``/scan/`` is listed, linked or indexed, and this module knows only about
pages that exist before anybody submits anything.

Nothing here decides anything about a scan. It renders two small files and a
handful of ``<head>`` values from a fixed list of paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .documentation import DOCUMENTATION_PAGES

SITE_NAME = "OpenCloud Security Scan"

#: Where the crawler is pointed, and the OpenGraph image every page shares.
#: The image is a PNG on purpose: most crawlers and chat clients will not
#: draw an SVG, so the hand-written `og-image.svg` next to it is only the
#: source this one is rendered from.
SITEMAP_PATH = "/sitemap.xml"
ROBOTS_PATH = "/robots.txt"
LLMS_PATH = "/llms.txt"
LLMS_FULL_PATH = "/llms-full.txt"
OG_IMAGE_PATH = "/static/img/og-image.png"


@dataclass(frozen=True)
class PublicPage:
    """One page a crawler may have, and the template it is rendered from."""

    path: str
    template: str
    changefreq: str
    priority: str


# The order is the order of the sitemap, and the priorities say what this
# service is for: one page does the work and the rest explain it - including
# the one that explains how to do it without this service at all.
PUBLIC_PAGES: tuple[PublicPage, ...] = (
    PublicPage("/", "index.html", "weekly", "1.0"),
    PublicPage("/how-it-works", "how-it-works.html", "monthly", "0.8"),
    PublicPage("/grades", "grades.html", "monthly", "0.8"),
    PublicPage("/documentation", "documentation.html", "monthly", "0.8"),
    *(
        PublicPage(
            f"/documentation/{document.slug}",
            f"docs/{document.slug}.html",
            "monthly",
            "0.6",
        )
        for document in DOCUMENTATION_PAGES
    ),
    PublicPage("/search", "search.html", "monthly", "0.6"),
    PublicPage("/api", "api.html", "monthly", "0.7"),
    PublicPage("/ai", "ai.html", "monthly", "0.6"),
    PublicPage("/cli", "cli.html", "monthly", "0.6"),
    PublicPage("/about", "about.html", "yearly", "0.5"),
    PublicPage("/privacy", "privacy.html", "yearly", "0.4"),
)

#: Every path that may be indexed. A page not in here gets ``noindex``, and
#: that includes every result, every export and every error page.
INDEXABLE_PATHS = frozenset(page.path for page in PUBLIC_PAGES)

# The files a crawler fetches before anything else, and the three documents
# an agent is *meant* to find, must not be told to forget what they just read.
_ROBOTS_EXEMPT = frozenset({ROBOTS_PATH, SITEMAP_PATH})

# Everything a crawler has no business in. `/api` is a page about the API and
# stays crawlable; `/api/` and below is the API itself. `/mcp` speaks a
# protocol rather than serving a document, so there is nothing there to fetch.
_DISALLOWED = (
    "/scan/",
    "/api/",
    "/docs",
    "/redoc",
    "/healthz",
    "/mcp",
)

# The machine-readable contract, said out loud. These are the three documents
# an agent needs in order to use this service without reading its source, and
# a crawler that finds them has found what it came for.
_MACHINE_READABLE = (
    LLMS_PATH,
    "/.well-known/ai.json",
    "/openapi.json",
    "/arazzo.json",
)

_XML_ESCAPES = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
)


def _escape(value: str) -> str:
    """Escape a URL for XML text. Small enough not to want a parser."""
    for character, replacement in _XML_ESCAPES:
        value = value.replace(character, replacement)
    return value


def site_origin(base_url: str, configured: str | None) -> str:
    """
    The origin every absolute URL is built from.

    ``configured`` wins when an operator set one, because a service behind a
    proxy sees its own internal address and would otherwise publish a sitemap
    full of URLs nobody outside can reach.
    """
    if configured:
        return configured.strip().rstrip("/")
    return base_url.rstrip("/")


def canonical_url(origin: str, path: str) -> str:
    """The one address a page should be known by."""
    if path == "/":
        return f"{origin}/"
    return f"{origin}{path}"


def is_indexable(path: str, *, allow_indexing: bool, status: int = 200) -> bool:
    """Whether this response may be indexed at all."""
    return allow_indexing and status == 200 and path in INDEXABLE_PATHS


def wants_robots_tag(path: str, *, allow_indexing: bool) -> bool:
    """
    Whether the response needs an ``X-Robots-Tag: noindex`` header.

    The meta tag covers HTML; this covers the exports, the JSON and anything
    else a crawler reaches that never renders a template.
    """
    if path in _ROBOTS_EXEMPT or path in _MACHINE_READABLE:
        return False
    if not allow_indexing:
        return True
    return path not in INDEXABLE_PATHS


def last_modified(templates_dir: Path, page: PublicPage) -> date:
    """
    When the page last changed, taken from the template that renders it.

    Automatic on purpose: a hand-maintained date in a sitemap is a date that
    is wrong within a release, and a crawler that learns to distrust it stops
    reading it.
    """
    candidate = templates_dir / page.template
    try:
        stamp = candidate.stat().st_mtime
    except OSError:
        return datetime.now(timezone.utc).date()
    return datetime.fromtimestamp(stamp, tz=timezone.utc).date()


def sitemap_xml(origin: str, templates_dir: Path) -> str:
    """The sitemap, built from :data:`PUBLIC_PAGES` rather than from a file."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for page in PUBLIC_PAGES:
        lines.extend(
            [
                "  <url>",
                f"    <loc>{_escape(canonical_url(origin, page.path))}</loc>",
                f"    <lastmod>{last_modified(templates_dir, page).isoformat()}</lastmod>",
                f"    <changefreq>{page.changefreq}</changefreq>",
                f"    <priority>{page.priority}</priority>",
                "  </url>",
            ]
        )
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def robots_txt(origin: str, *, allow_indexing: bool) -> str:
    """
    What a crawler is allowed to read.

    With indexing turned off this is a flat refusal, and no sitemap is
    advertised - a deployment that does not want to be found should not hand
    out a list of its pages.
    """
    if not allow_indexing:
        return "User-agent: *\nDisallow: /\n"
    lines = ["User-agent: *", "Allow: /"]
    lines.extend(f"Allow: {path}" for path in _MACHINE_READABLE)
    lines.extend(f"Disallow: {path}" for path in _DISALLOWED)
    lines.append("")
    lines.append(f"Sitemap: {origin}{SITEMAP_PATH}")
    lines.append("")
    return "\n".join(lines)
