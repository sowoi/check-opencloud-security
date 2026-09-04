"""The frontend speaks the visitor's language without changing API contracts."""

from __future__ import annotations

import re
from string import Formatter

import pytest
from jinja2 import Environment

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    client,
)
from webapp.i18n import (
    LANGUAGE_COOKIE,
    Translator,
    negotiate_locale,
    parse_accept_language,
    safe_next_path,
)
from webapp.locales import CATALOGUES

FRONTEND_PATHS = (
    "/",
    "/how-it-works",
    "/grades",
    "/catalogue",
    "/documentation",
    "/search",
    "/api",
    "/ai",
    "/privacy",
    "/about",
)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("de-DE,de;q=0.9,en;q=0.8", "de"),
        ("es-MX;q=0.7,fr;q=0.9", "fr"),
        ("fr-CA,en;q=0.5", "fr"),
        ("nl-NL,*;q=0.5", "en"),
        ("de;q=0,en;q=0.5", "en"),
        ("not a language", "en"),
    ],
)
def test_browser_language_negotiation_honours_regions_and_quality(
    header: str, expected: str
):
    """A browser's weighted language list must select the best supported locale."""
    assert negotiate_locale(header) == expected


def test_a_quality_that_is_not_a_number_is_not_a_preference():
    """
    ``q=nan`` parses as a float and then compares false against everything.

    Left in, it decides the order of the weighted list by whichever
    comparisons Python happened to make, so the language a visitor is served
    stops following the header they sent. A weight that is not a weight is
    dropped like an unparsable one, while a client that overshoots the range
    is still understood.
    """
    assert parse_accept_language("de;q=nan") == ()
    assert negotiate_locale("de;q=nan,fr;q=0.5") == "fr"
    # The negative half: a real weight in the same header still counts, and an
    # out-of-range one is clamped rather than discarded.
    assert parse_accept_language("de;q=nan,fr;q=0.5") == (("fr", 0.5),)
    assert parse_accept_language("de;q=1.5") == (("de", 1.0),)
    assert negotiate_locale("de;q=1.5,fr;q=0.9") == "de"


def test_a_chosen_language_persists_and_overrides_the_browser():
    """A deliberate switch must win over later browser-language negotiation."""
    test_client = client()

    response = test_client.post(
        "/language",
        data={"locale": "de", "next": "/grades"},
        headers={"accept-language": "fr"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/grades"
    assert f"{LANGUAGE_COOKIE}=de" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    page = test_client.get("/grades", headers={"accept-language": "fr"})
    assert '<html lang="de">' in page.text
    assert Translator("de")("grades.title") in page.text


@pytest.mark.parametrize(
    "destination",
    [
        "https://attacker.example/",
        "//attacker.example/",
        "/../admin",
        r"/\attacker",
        "/%2f%2fattacker.example",
    ],
)
def test_the_language_switch_cannot_redirect_off_site(destination: str):
    """The switcher's return field must never become an open redirect."""
    response = client().post(
        "/language",
        data={"locale": "fr", "next": destination},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_safe_language_return_paths_keep_local_pages_and_drop_queries():
    """Switching on a result page should retain its path without copying a query."""
    assert safe_next_path("/scans/1234?source=elsewhere#result") == "/scans/1234"


def test_every_catalog_has_the_same_keys_placeholders_and_markup():
    """A translated page must not lose a sentence, value, link, or emphasis."""
    english = CATALOGUES["en"]

    for locale in ("de", "es", "fr"):
        translated = CATALOGUES[locale]
        assert translated.keys() == english.keys()
        for key, source in english.items():
            assert _fields(translated[key]) == _fields(source), (locale, key)
            assert _tags(translated[key]) == _tags(source), (locale, key)


@pytest.mark.parametrize("locale", ["en", "de", "es", "fr"])
def test_every_handwritten_page_renders_in_each_language(locale: str):
    """One incomplete catalog key must not break an otherwise reachable page."""
    test_client = client()
    test_client.cookies.set(LANGUAGE_COOKIE, locale)

    for path in FRONTEND_PATHS:
        page = test_client.get(path)
        assert page.status_code == 200
        assert f'<html lang="{locale}">' in page.text
        assert 'action="/language"' in page.text


def test_machine_readable_contracts_remain_english():
    """Language negotiation must never mutate schemas consumed by software."""
    test_client = client(enable_docs=True)
    english = test_client.get("/openapi.json").json()
    german = test_client.get(
        "/openapi.json", headers={"accept-language": "de-DE"}
    ).json()

    assert german == english


def test_html_translation_placeholders_cannot_inject_tags_or_attributes():
    """Untrusted placeholder text must stay escaped inside trusted catalogue HTML."""
    payload = '"><img src=x onerror="alert(1)">'
    translated = Translator("en").html("docs.index.options.manual", project=payload)
    rendered = Environment(autoescape=True).from_string("{{ value }}").render(
        value=translated
    )

    assert "<img" not in rendered
    assert 'onerror="' not in rendered
    assert "&lt;img" in rendered
    assert "&#34;alert(1)&#34;" in rendered


def test_html_translation_keeps_trusted_catalogue_markup_renderable():
    """Allow-listed inline elements authored in a catalogue must remain HTML."""
    translated = Translator("en").html(
        "docs.index.options.manual", project="https://opencloud.example.com/docs"
    )
    rendered = Environment(autoescape=True).from_string("{{ value }}").render(
        value=translated
    )

    assert '<a href="https://opencloud.example.com/docs#cli-usage"' in rendered
    assert "</a>" in rendered
    assert "&lt;a " not in rendered


def _fields(value: str) -> tuple[str, ...]:
    return tuple(
        field_name
        for _, field_name, _, _ in Formatter().parse(value)
        if field_name is not None
    )


def _tags(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"</?[^>]+>", value))
