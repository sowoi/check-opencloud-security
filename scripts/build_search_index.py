#!/usr/bin/env python3
"""
Build the static frontend search index from its public-page manifest.

One file per language, and the language files are overlays: the English index
carries every page and its text, and ``search-index.<locale>.json`` carries
the translated title, summary and - for the pages this project writes by hand
- the translated text. A guide generated from the repository has an English
body in one place rather than four.

The templates say ``t('some.key')`` rather than the sentence, so the strings
are read out of the catalogues here. Nothing else changes: the manifest is
still the structural reason a scan result cannot enter search.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "frontend" / "static"
OUTPUT = STATIC / "search-index.json"

sys.path.insert(0, str(ROOT))
from opencloud_local_scan import __version__
from webapp.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES, Translator
from webapp.search import SEARCH_PAGES

_JINJA = re.compile(r"{[#%].*?[#%]}|{{.*?}}", re.DOTALL)
_SPACE = re.compile(r"\s+")
# A catalogue lookup in a template, with the identifier written as a literal.
# A key built from a loop variable is left out rather than guessed at.
_LOOKUP = re.compile(r"{{-?\s*t(?:\.html|\.raw)?\(\s*'([^']+)'.*?\)\s*-?}}", re.DOTALL)
_PLACEHOLDER = re.compile(r"{[a-z_]+}")


def _localised_source(template: str, translate: Translator) -> str:
    """The template with every literal catalogue lookup already resolved."""
    source = (ROOT / "frontend" / "templates" / template).read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if not translate.has(key):
            return " "
        return " " + _PLACEHOLDER.sub("", translate.raw(key)) + " "

    return _LOOKUP.sub(replace, source)


class _Text(HTMLParser):
    """Collect visible authored text without executing a template."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def _body(template: str, translate: Translator) -> str:
    parser = _Text()
    parser.feed(_JINJA.sub(" ", _localised_source(template, translate)))
    return _SPACE.sub(" ", html.unescape(" ".join(parser.parts))).strip()[:20_000]


def _translated(key: str, fallback: str, translate: Translator) -> str:
    return translate(key) if key and translate.has(key) else fallback


def _generated(template: str) -> bool:
    """Whether the page's text is generated from the repository Markdown."""
    return template.startswith("docs/")


def render(locale: str = DEFAULT_LOCALE) -> str:
    """Return the deterministic release index for one language."""
    translate = Translator(locale)
    pages = []
    for page in SEARCH_PAGES:
        entry = {
            "path": page.path,
            "title": _translated(page.title_key, page.title, translate),
            "summary": _translated(page.summary_key, page.summary, translate),
        }
        # An overlay leaves out the English guide bodies it would only repeat.
        if locale == DEFAULT_LOCALE or not _generated(page.template):
            entry["body"] = _body(page.template, translate)
        pages.append(entry)
    # The release this index was generated for. The body text is extracted
    # from the templates by this script, which is deliberately not part of
    # the deployed bundle, so a running service cannot re-derive it to check.
    # What it can do is compare this stamp against the version it is itself
    # running: an index built for an earlier release is one whose page text
    # was written before the copy currently on screen.
    document: dict[str, object] = {
        "version": 1,
        "builtFor": __version__,
        "pages": pages,
    }
    if locale != DEFAULT_LOCALE:
        document = {
            "version": 1,
            "builtFor": __version__,
            "locale": locale,
            "pages": pages,
        }
    return json.dumps(document, ensure_ascii=True, indent=2) + "\n"


def output_for(locale: str) -> Path:
    """Where one language's index is written."""
    if locale == DEFAULT_LOCALE:
        return OUTPUT
    return STATIC / f"search-index.{locale}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail when the checked-in index differs"
    )
    arguments = parser.parse_args(argv)
    failed = False
    for locale in SUPPORTED_LOCALES:
        target = output_for(locale)
        expected = render(locale)
        if arguments.check:
            if not target.is_file() or target.read_text(encoding="utf-8") != expected:
                print(
                    f"The static search index {target.name} is not the current "
                    "release index.",
                    file=sys.stderr,
                )
                failed = True
            continue
        target.write_text(expected, encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
