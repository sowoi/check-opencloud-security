"""The browser documentation generated from the Markdown operator guides."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
)
from webapp.documentation import DOCUMENTATION_PAGES

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_generator():
    """Load the standalone build script without making scripts/ a package."""
    path = REPO_ROOT / "scripts" / "build_frontend_documentation.py"
    spec = importlib.util.spec_from_file_location("build_frontend_documentation", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_frontend_documentation"] = module
    spec.loader.exec_module(module)
    return module


generator = _load_generator()


def test_the_generated_documentation_is_current():
    """
    The checked-in HTML must be the page the source Markdown generates.

    Serving generated files keeps Markdown out of the runtime, but only this
    check turns regeneration from a convention into a pipeline.
    """
    assert generator.stale_pages() == []


def test_every_document_has_its_own_local_html_page():
    """The Docs tab must not send somebody to a GitHub Markdown renderer."""
    test_client = client()
    index = test_client.get("/documentation")

    assert index.status_code == 200
    assert "/blob/main/" not in index.text
    for document in DOCUMENTATION_PAGES:
        path = f"/documentation/{document.slug}"
        assert f'href="{path}"' in index.text
        response = test_client.get(path)
        assert response.status_code == 200
        assert f"<h1>{document.title}</h1>" in response.text
        assert generator.GENERATED_MARKER not in response.text
        assert "style=" not in response.text
        assert "<script>" not in response.text
        resources_body = re.sub(
            r'<link rel="(?:canonical|service-desc|arazzo|ai-discovery)"[^>]*>',
            "",
            response.text,
        )
        resources = re.findall(
            r'<(?:script|link|img)[^>]*?(?:src|href)="([^"]+)"',
            resources_body,
        )
        assert resources
        assert all(resource.startswith("/static/") for resource in resources)


def test_an_unknown_document_is_the_same_404_as_any_unknown_page():
    """The generated catalogue must not become a file-serving catch-all."""
    response = client().get(
        "/documentation/not-a-document", headers={"Accept": "text/html"}
    )

    assert response.status_code == 404
    assert "Nothing here" in response.text
