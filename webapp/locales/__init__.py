"""
The string catalogues, one module per language.

English is the source and the fallback; the others are translations of it,
keyed identically. The documentation manifest is folded in here rather than
copied into the English module, so that the title of a guide is written once
in :mod:`webapp.documentation` and translated under the same identifier
everywhere else.

Nothing in this package imports the web framework: the release build reads
these catalogues to write the static search index, and it has no server.
"""

from __future__ import annotations

from ..documentation import DOCUMENTATION_PAGES
from . import de, en, es, fr


def _with_manifest(messages: dict[str, str]) -> dict[str, str]:
    """Add the English guide titles a translation has not overridden."""
    complete = dict(messages)
    for page in DOCUMENTATION_PAGES:
        complete.setdefault(f"docs.{page.slug}.title", page.title)
        complete.setdefault(f"docs.{page.slug}.description", page.description)
    return complete


#: Every language this frontend speaks, by code. English is filled in from the
#: manifest as well, so a guide added to the manifest is immediately readable
#: in every language even before it is translated.
CATALOGUES: dict[str, dict[str, str]] = {
    "en": _with_manifest(en.MESSAGES),
    "de": _with_manifest(de.MESSAGES),
    "es": _with_manifest(es.MESSAGES),
    "fr": _with_manifest(fr.MESSAGES),
}

__all__ = ["CATALOGUES"]
