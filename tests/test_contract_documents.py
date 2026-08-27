"""External validation for the published API contract."""

from __future__ import annotations

from openapi_spec_validator import validate

from tests.webapp_support import (  # noqa: F401 - fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
)


def test_the_published_openapi_document_passes_the_standard_validator():
    """Client generators must receive a valid OpenAPI 3.1 document."""
    validate(client().get("/openapi.json").json())
