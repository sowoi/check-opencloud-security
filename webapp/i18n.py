"""
The language a page is written in, decided once per request.

Four things happen here and nothing else: a catalogue of strings is looked up
by a stable identifier, an ``Accept-Language`` header is negotiated against
the languages this frontend actually has, a stored choice is read from a
cookie, and the path a language switch returns to is validated.

The rules that matter:

* **The identifier is the contract.** A template asks for ``nav.docs``, never
  for "Docs". A missing translation falls back to English rather than to a
  blank page, and the completeness test makes sure that fallback is a safety
  net rather than a way of working.
* **A stored choice wins over the browser's.** Somebody who picked German on
  a laptop that asks for English asked twice, and the second answer is the
  one they gave this service.
* **Nothing machine-readable is translated here.** The OpenAPI description,
  the Arazzo workflows, the discovery document, the MCP tools and every
  export stay English: they are contracts read by software, and a contract
  that changes wording with a request header is not one.
* **Scan evidence stays as measured.** A version string, a certificate
  subject or an error message from the scanned host is quoted, not
  translated - this module only ever sees text this project wrote.

Nothing in here imports the web framework, because the release build reads
the same catalogues to write the static search index.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .locales import CATALOGUES

#: The language every page falls back to, and the one every machine-readable
#: document is written in.
DEFAULT_LOCALE = "en"

#: The cookie a chosen language is remembered in. ``HttpOnly`` because no
#: script needs it - the server renders the page - and ``SameSite=Lax`` so a
#: third-party page cannot change what somebody's next visit says.
LANGUAGE_COOKIE = "cos_locale"

#: A year. A language is a preference, not a session.
LANGUAGE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365

#: Where a language switch posts to, and the only route that sets the cookie.
LANGUAGE_PATH = "/language"

# An Accept-Language header is attacker-controlled and free to be enormous.
# Both limits are generous for a real browser and cheap for anything else.
_MAX_HEADER_LENGTH = 512
_MAX_HEADER_ENTRIES = 24

_TAG = re.compile(r"^[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*$")

# A path this service could have served itself: absolute, single-slash, and
# made only of the characters its own routes use. Everything else - a scheme,
# a host, a backslash, a control character, a dot-segment - is somebody
# else's idea of where the visitor should end up.
_SAFE_PATH = re.compile(r"^/[A-Za-z0-9/_.~-]*$")
_MAX_PATH_LENGTH = 512


@dataclass(frozen=True)
class LocaleOption:
    """One language the switcher offers."""

    code: str
    #: What the language calls itself, because that is what a reader who
    #: cannot read the current page is looking for.
    native_name: str
    #: The same language named in English, for an ``aria-label`` and for the
    #: documentation.
    english_name: str


LOCALES: tuple[LocaleOption, ...] = (
    LocaleOption("en", "English", "English"),
    LocaleOption("de", "Deutsch", "German"),
    LocaleOption("es", "Español", "Spanish"),
    LocaleOption("fr", "Français", "French"),
)

SUPPORTED_LOCALES: tuple[str, ...] = tuple(option.code for option in LOCALES)

LOCALES_BY_CODE: dict[str, LocaleOption] = {option.code: option for option in LOCALES}


class _RequestLike(Protocol):
    """The two mappings this module reads off a request, and no more."""

    @property
    def cookies(self) -> Mapping[str, str]: ...

    @property
    def headers(self) -> Mapping[str, str]: ...


class _CatalogueMarkup(str):
    """HTML trusted only because it came from a source-controlled catalogue."""

    def __html__(self) -> str:
        return self


def catalogue(locale: str) -> Mapping[str, str]:
    """The strings for one language, English when it is not one we have."""
    return CATALOGUES.get(locale, CATALOGUES[DEFAULT_LOCALE])


class Translator:
    """
    One language, bound once per request and handed to the template.

    ``t("nav.docs")`` returns text that Jinja escapes as usual.
    ``t.html("footer.note")`` returns markup, for the handful of strings whose
    emphasis, code spans or links are part of the sentence rather than around
    it. Both are this project's own text - a catalogue is source code, not
    input - and any value interpolated into one is escaped on the way in.
    """

    __slots__ = ("_fallback", "_messages", "locale")

    def __init__(self, locale: str = DEFAULT_LOCALE) -> None:
        self.locale = locale if locale in CATALOGUES else DEFAULT_LOCALE
        self._messages = CATALOGUES[self.locale]
        self._fallback = CATALOGUES[DEFAULT_LOCALE]

    def has(self, key: str) -> bool:
        """Whether this key exists at all, in this language or in English."""
        return key in self._messages or key in self._fallback

    def raw(self, key: str) -> str:
        """The unformatted string, English when this language lacks it."""
        message = self._messages.get(key)
        if message is None:
            message = self._fallback.get(key)
        # A key that reaches a page is a bug the completeness test catches
        # before a visitor does; showing it beats showing nothing.
        return key if message is None else message

    def __call__(self, key: str, /, **params: Any) -> str:
        message = self.raw(key)
        if not params:
            return message
        try:
            return message.format(**params)
        except (IndexError, KeyError, ValueError):
            return message

    def html(self, key: str, /, **params: Any) -> _CatalogueMarkup:
        """The same string as markup, with every value escaped into it."""
        # Imported here rather than at the top: the release build reads these
        # catalogues to write the search index, and it has no template engine
        # installed to bring MarkupSafe with it.
        from markupsafe import escape

        message = self.raw(key)
        if not params:
            return _CatalogueMarkup(message)
        try:
            rendered = message.format(
                **{name: escape(str(value)) for name, value in params.items()}
            )
        except (IndexError, KeyError, ValueError):
            rendered = message
        return _CatalogueMarkup(rendered)


def normalise_locale(value: object) -> str | None:
    """
    Reduce a language tag to one this frontend has, or to nothing.

    ``de-AT`` is German, ``DE`` is German, ``de_AT`` is German because a
    stored cookie may have been written by hand, and ``klingon`` is nothing.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip().replace("_", "-")
    if not candidate or len(candidate) > 35 or not _TAG.match(candidate):
        return None
    lowered = candidate.lower()
    if lowered in LOCALES_BY_CODE:
        return lowered
    primary = lowered.split("-", 1)[0]
    return primary if primary in LOCALES_BY_CODE else None


def parse_accept_language(header: str | None) -> tuple[tuple[str, float], ...]:
    """
    The tags in a header, best first, with their quality weights.

    Ordering is by weight, and ties keep the order the client wrote them in,
    which is what a client means by writing them in that order. A weight of
    zero is not a preference but a refusal, and is dropped.
    """
    if not header or len(header) > _MAX_HEADER_LENGTH:
        return ()
    entries: list[tuple[int, str, float]] = []
    for position, part in enumerate(header.split(",")[:_MAX_HEADER_ENTRIES]):
        pieces = part.split(";")
        tag = pieces[0].strip()
        if not tag:
            continue
        quality = 1.0
        for parameter in pieces[1:]:
            name, _, raw = parameter.partition("=")
            if name.strip().lower() != "q":
                continue
            try:
                parsed = float(raw.strip())
            except ValueError:
                parsed = 0.0
            # ``q=nan`` parses as a float and then compares false against every
            # other weight, which would leave the sort below - and with it the
            # language a visitor is served - depending on the order Python
            # happened to compare the entries in. A weight that is not a
            # weight is not a preference, so it is dropped like an unparsable
            # one; an out-of-range one is still clamped, because a client
            # writing ``q=1.5`` plainly means "this one first".
            quality = 0.0 if math.isnan(parsed) else parsed
        if quality <= 0.0:
            continue
        entries.append((position, tag, min(quality, 1.0)))
    entries.sort(key=lambda entry: (-entry[2], entry[0]))
    return tuple((tag, quality) for _, tag, quality in entries)


def negotiate_locale(
    header: str | None,
    *,
    supported: Iterable[str] = SUPPORTED_LOCALES,
    default: str = DEFAULT_LOCALE,
) -> str:
    """
    The best language for a browser that has not chosen one.

    Exact tags win over regional fallbacks in the order the client asked for
    them: ``fr-CA`` is served French because French is what this frontend has
    of it, and ``*`` means "anything", which here is English.
    """
    available = tuple(supported)
    for tag, _ in parse_accept_language(header):
        if tag == "*":
            return default
        resolved = normalise_locale(tag)
        if resolved is not None and resolved in available:
            return resolved
    return default


def stored_locale(request: _RequestLike) -> str | None:
    """The language this visitor chose, if the cookie still says one."""
    return normalise_locale(request.cookies.get(LANGUAGE_COOKIE))


def locale_for_request(request: _RequestLike) -> str:
    """
    The language this request is answered in.

    A stored choice first, the browser's own list second, English last. There
    is no fourth source: a query parameter would put a language into every
    link somebody copies, and a path prefix would give every page two
    addresses and every result page two uuids to leak.
    """
    chosen = stored_locale(request)
    if chosen is not None:
        return chosen
    return negotiate_locale(request.headers.get("accept-language"))


def safe_next_path(value: object, *, default: str = "/") -> str:
    """
    The path a language switch may return to.

    Only somewhere on this service, and only the path of it: no host, no
    scheme, no query and no fragment. Dropping the query is deliberate as
    well as simple - a result is reached by a uuid in the path, and a switch
    that rebuilt query strings would be one refactor away from putting that
    uuid somewhere it gets logged, shared or sent as a referrer.
    """
    if not isinstance(value, str):
        return default
    candidate = value.strip()
    if not candidate or len(candidate) > _MAX_PATH_LENGTH:
        return default
    # A query or fragment is cut rather than rejected: the page it belongs to
    # is still a perfectly good place to come back to.
    candidate = candidate.split("?", 1)[0].split("#", 1)[0]
    if not candidate.startswith("/") or candidate.startswith("//"):
        return default
    if not _SAFE_PATH.match(candidate):
        return default
    if any(segment in {"..", "."} for segment in candidate.split("/")):
        return default
    return candidate


def locale_options(current: str) -> tuple[dict[str, Any], ...]:
    """The switcher's entries, each knowing whether it is the current one."""
    return tuple(
        {
            "code": option.code,
            "native_name": option.native_name,
            "english_name": option.english_name,
            "current": option.code == current,
        }
        for option in LOCALES
    )


def catalogue_keys(locale: str = DEFAULT_LOCALE) -> frozenset[str]:
    """Every identifier one catalogue defines, for the completeness test."""
    return frozenset(catalogue(locale))
