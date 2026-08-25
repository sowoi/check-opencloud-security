"""The release-built browser search and its result-data boundary."""

from __future__ import annotations

import json
from pathlib import Path

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
)
from webapp.i18n import SUPPORTED_LOCALES
from webapp.search import SEARCH_PAGES

ROOT = Path(__file__).resolve().parent.parent


def test_search_uses_the_checked_in_same_origin_index():
    """A search must need neither a runtime crawler nor a third-party service."""
    test_client = client()

    page = test_client.get("/search")
    index = test_client.get("/static/search-index.json")

    assert page.status_code == 200
    assert "/static/js/search.js" in page.text
    assert "never indexes" not in page.text.lower()
    assert "never reads the scan store" in page.text
    assert index.status_code == 200
    assert index.json()["pages"]


def test_the_manifest_has_no_surface_that_can_contain_a_scan_result():
    """The generator must have no route from a UUID capability into search."""
    assert SEARCH_PAGES
    assert all(not page.path.startswith("/scan") for page in SEARCH_PAGES)
    assert all(page.template != "scan.html" for page in SEARCH_PAGES)
    assert all("/export/" not in page.path for page in SEARCH_PAGES)

    document = json.loads(
        (ROOT / "frontend/static/search-index.json").read_text(encoding="utf-8")
    )
    assert all(not page["path"].startswith("/scan") for page in document["pages"])


def test_each_language_has_a_release_built_public_only_index():
    """A translated search must not fall back to a mutable runtime index."""
    for locale in SUPPORTED_LOCALES:
        suffix = "" if locale == "en" else f".{locale}"
        path = ROOT / f"frontend/static/search-index{suffix}.json"
        document = json.loads(path.read_text(encoding="utf-8"))

        assert document["pages"]
        assert all(not page["path"].startswith("/scan") for page in document["pages"])
        assert all("/export/" not in page["path"] for page in document["pages"])


def test_only_the_release_workflow_refreshes_the_index():
    """Ordinary CI must not make search drift between published versions."""
    release = (ROOT / ".github/workflows/publish-pypi.yml").read_text(encoding="utf-8")
    assert "python scripts/build_search_index.py" in release
    for locale in ("de", "es", "fr"):
        assert f"frontend/static/search-index.{locale}.json" in release
    for workflow in (ROOT / ".github/workflows").glob("*.yml"):
        if workflow.name != "publish-pypi.yml":
            assert "build_search_index.py" not in workflow.read_text(encoding="utf-8")
