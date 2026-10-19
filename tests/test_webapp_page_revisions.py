"""
The sitemap's dates belong to the pages, not to the release.

A ``<lastmod>`` built from a template's modification time says "everything
changed" after every checkout, container build or unpacked tarball, because
all of them write every template at once. These tests hold the record that
replaces it: a date next to a digest, moving only when the page does.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from xml.dom import minidom  # nosec B408 - parses this server's own output

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
    settings,
)
from webapp.revisions import REVISIONS_FILE, digest_of, load, recorded_date
from webapp.seo import PUBLIC_PAGES, last_modified

TEMPLATES = Path(__file__).resolve().parents[1] / "frontend" / "templates"


def test_every_public_page_has_a_recorded_revision():
    """
    A page without a record falls back to its modification time.

    That fallback is the bug this record exists to fix, so the record has to
    cover every page the sitemap lists.
    """
    recorded = load(REVISIONS_FILE)

    assert sorted(recorded) == sorted(page.template for page in PUBLIC_PAGES)


def test_the_record_still_describes_the_checked_in_templates():
    """
    The digests are the record's claim that these dates are still true.

    This is `scripts/update_page_revisions.py --check` as a test, so a
    template edited without regenerating the record fails here rather than
    publishing a date that quietly stopped being the truth.
    """
    recorded = load(REVISIONS_FILE)

    stale = [
        template
        for template, entry in recorded.items()
        if entry.get("digest") != digest_of(TEMPLATES / template)
    ]

    assert stale == [], (
        "run python scripts/update_page_revisions.py and commit the result"
    )


def test_a_dated_page_keeps_its_date_when_only_the_deployment_is_new():
    """
    Touching a template is not a change to the page it renders.

    An unpacked release tarball does exactly this to every template at once,
    which is how every date in the sitemap used to move on release day.
    """
    page = PUBLIC_PAGES[0]
    template = TEMPLATES / page.template
    before = last_modified(TEMPLATES, page)

    future = datetime.now(tz=UTC).timestamp() + 86_400
    stamp = template.stat()
    try:
        os.utime(template, (future, future))
        assert last_modified(TEMPLATES, page) == before
    finally:
        os.utime(template, (stamp.st_atime, stamp.st_mtime))


def test_an_edited_template_loses_its_recorded_date(tmp_path):
    """
    A stale date is worse than a fallback: it denies a change that happened.

    So a digest that no longer matches is not trusted, and the date falls
    back to the file itself until the record is regenerated.
    """
    template = tmp_path / "index.html"
    template.write_text("<p>after</p>", encoding="utf-8")
    record = tmp_path / "page-revisions.json"
    record.write_text(
        json.dumps(
            {
                "pages": {
                    "index.html": {
                        "digest": digest_of(tmp_path / "index.html"),
                        "lastmod": "2026-01-02",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    entries = load(record)
    assert entries["index.html"]["lastmod"] == "2026-01-02"

    template.write_text("<p>edited</p>", encoding="utf-8")
    assert entries["index.html"]["digest"] != digest_of(template)


def test_a_page_without_a_record_falls_back_rather_than_inventing_a_date(tmp_path):
    """An unknown template has no recorded date, and says so."""
    template = tmp_path / "unknown.html"
    template.write_text("<p>hello</p>", encoding="utf-8")

    assert recorded_date(template, "unknown.html") is None


def test_the_sitemap_serves_the_recorded_dates():
    """What the record says is what a crawler is told."""
    recorded = load(REVISIONS_FILE)

    body = client().get("/sitemap.xml").text

    document = minidom.parseString(body)  # nosec B318 - our own output
    served = []
    for node in document.getElementsByTagName("lastmod"):
        assert node.firstChild is not None
        served.append(str(node.firstChild.nodeValue))

    assert served == [recorded[page.template]["lastmod"] for page in PUBLIC_PAGES]
    for value in served:
        assert date.fromisoformat(value) <= datetime.now(tz=UTC).date()
