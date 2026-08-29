"""
The fixed public-page manifest used to build the browser search index.

The English title and summary are the source, and each page also names the
catalogue identifiers for the same two strings, so a release can build an
index a German reader recognises without this manifest growing a copy of
every translation. What may *not* appear here is a page reached with a scan
uuid: the list is the structural reason a result cannot enter search, so it
is written out by hand rather than discovered.
"""

from __future__ import annotations

from dataclasses import dataclass

from .documentation import DOCUMENTATION_PAGES


@dataclass(frozen=True)
class SearchPage:
    """One public page whose authored text may enter the static index."""

    path: str
    title: str
    summary: str
    template: str
    #: The catalogue identifier for the title, when there is one.
    title_key: str = ""
    #: The catalogue identifier for the summary, when there is one.
    summary_key: str = ""


SEARCH_PAGES: tuple[SearchPage, ...] = (
    SearchPage(
        "/",
        "Scan an OpenCloud instance",
        "Run a public security scan against an OpenCloud instance.",
        "index.html",
        "search.page.index.title",
        "search.page.index.summary",
    ),
    SearchPage(
        "/how-it-works",
        "How the scanner works",
        "What the scanner measures, what it cannot see, and how results are handled.",
        "how-it-works.html",
        "search.page.how.title",
        "search.page.how.summary",
    ),
    SearchPage(
        "/grades",
        "What the grades mean",
        "The A+ to F rating scale and the fixes that improve each grade.",
        "grades.html",
        "search.page.grades.title",
        "search.page.grades.summary",
    ),
    SearchPage(
        "/catalogue",
        "What the scanner checks",
        "Every hardening flag, header and TLS check the scanner runs, and every known advisory.",
        "catalogue.html",
        "search.page.catalogue.title",
        "search.page.catalogue.summary",
    ),
    SearchPage(
        "/documentation",
        "CLI documentation",
        "Command-line quick start, configuration, monitoring, and deployment guides.",
        "documentation.html",
        "search.page.documentation.title",
        "search.page.documentation.summary",
    ),
    *(
        SearchPage(
            f"/documentation/{document.slug}",
            document.title,
            document.description,
            f"docs/{document.slug}.html",
            f"docs.{document.slug}.title",
            f"docs.{document.slug}.description",
        )
        for document in DOCUMENTATION_PAGES
    ),
    SearchPage(
        "/api",
        "API",
        "Submit scans, poll results, export reports, and erase retained data.",
        "api.html",
        "search.page.api.title",
        "search.page.api.summary",
    ),
    SearchPage(
        "/ai",
        "AI and MCP",
        "Machine-readable OpenAPI, Arazzo, discovery, MCP tools, and prompts.",
        "ai.html",
        "search.page.ai.title",
        "search.page.ai.summary",
    ),
    SearchPage(
        "/cli",
        "Run the scanner with Docker",
        "One-line Docker and uvx commands for scanning without the website.",
        "cli.html",
        "search.page.cli.title",
        "search.page.cli.summary",
    ),
    SearchPage(
        "/privacy",
        "Privacy",
        "Result retention, request logging, rate limits, and third-party policy.",
        "privacy.html",
        "search.page.privacy.title",
        "search.page.privacy.summary",
    ),
    SearchPage(
        "/about",
        "About this project",
        "Why this independent OpenCloud security scanner exists.",
        "about.html",
        "search.page.about.title",
        "search.page.about.summary",
    ),
)
