"""
Keep the advisory database current without waiting for a release.

The database that decides whether a scanned instance is reported as
vulnerable is written by CI and frozen into the image. An advisory published
the day after a build reaches nobody running it, and the visitor is told their
instance is fine - which is the one answer a security check must not get
wrong by omission.

So the worker asks OSV once a day which advisories affect OpenCloud, and the
scan jobs rate against the answer. Where the release schedule can fail by
*losing* a line, this can fail by *gaining* an advisory that affects nothing
in particular, so the rules are the mirror image:

* **A refresh never removes an advisory.** The document is merged into the
  bundled one, so a feed that answers with an empty list changes nothing.
* **Nothing unbounded is ever believed.** An advisory that does not say which
  versions it affects would flag every instance in the world; the parser drops
  those, and this module refuses a document that slipped one through.
* **A failure changes nothing.** An unreachable feed, an HTML error page, an
  answer with a hundred advisories in it: all of them leave the database
  exactly as it was.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from opencloud_local_scan.advisory_source import (
    AdvisoryFetchError,
    fetch_advisory_document,
)
from opencloud_local_scan.vulndb import (
    BUNDLED_DB,
    VulnerabilityDatabase,
    is_unbounded_advisory,
    load_database,
    parse_document,
)

from .redis_backend import RedisBackend
from .reference_data import (
    ADVISORY_ATTEMPT_KEY,
    ADVISORY_CHECKED_KEY,
    ADVISORY_DOCUMENT_KEY,
    REFRESH_TIMEOUT_SECONDS,
    last_checked,
    read_document,
    record_attempt,
    write_document,
)
from .settings import WebSettings

LOGGER = logging.getLogger("check_opencloud.web.advisories")

__all__ = [
    "advisory_catalogue",
    "advisory_state",
    "probe_advisories",
    "refresh_advisories",
    "stored_database",
]

# Worst first, so the catalogue page reads the same way the dashboard's own
# severity ordering does.
_SEVERITY_ORDER = {"critical": 0, "high": 1, "moderate": 2, "medium": 2, "low": 3}


def advisory_catalogue(database: VulnerabilityDatabase) -> list[dict[str, Any]]:
    """
    Every advisory the current database knows about, for the reference page.

    Unlike a scan result this is not filtered to one version: it is the whole
    database a scan is rated against, so a visitor can see what the scanner
    would catch before ever running it.
    """
    return [
        {
            "id": advisory.id,
            "title": advisory.title,
            "description": advisory.description,
            "severity": advisory.severity,
            "url": advisory.url,
            "cwe": advisory.cwe,
            "ranges": [
                {"introduced": introduced, "fixed": fixed}
                for introduced, fixed in advisory.all_ranges()
            ],
        }
        for advisory in sorted(
            database.advisories,
            key=lambda item: (
                _SEVERITY_ORDER.get(item.severity.lower(), 9),
                item.id,
            ),
        )
    ]


def _is_usable(document: dict[str, Any]) -> bool:
    """
    Whether a fetched advisory document may be believed.

    One rule, and it is the one that matters: no advisory may be unbounded.
    An entry with no ``introduced`` and no ``fixed`` matches every version
    there has ever been, so a single one of them turns every scan this
    deployment runs into a critical finding.

    Read off the *raw* records rather than the parsed advisories. The parser
    now drops an unbounded record on its own, which is right for the plugin -
    a scan should not be poisoned by one bad line in an operator's feed - but
    it would leave this function inspecting a list the bad entry had already
    been filtered out of, and quietly turn a refusal into a silent repair.
    That is the wrong trade here: a feed emitting an advisory that affects
    every version is a feed that has gone wrong, and ADR 0017's answer is to
    keep the database this deployment already had rather than accept the rest
    of a document that demonstrably contains nonsense.
    """
    records = document.get("advisories")
    if records is None:
        # Nothing to disbelieve. An empty or differently shaped document is
        # judged by the callers, which fall back to the bundled database.
        return True
    if not isinstance(records, list):
        return False
    return not any(
        is_unbounded_advisory(record)
        for record in records
        if isinstance(record, dict)
    )


def _bundled() -> VulnerabilityDatabase:
    """The advisory database that shipped in the wheel."""
    return load_database()


async def stored_database(
    backend: RedisBackend, settings: WebSettings
) -> VulnerabilityDatabase:
    """
    The advisory database a scan should be rated against, refreshed or bundled.

    Always returns a usable database. The refreshed document has to pass the
    same test it passed to be stored, so nothing that has since become
    unusable is believed on the way out either.
    """
    if not settings.advisory_refresh:
        return _bundled()
    document = await read_document(backend, ADVISORY_DOCUMENT_KEY)
    if document is None or not _is_usable(document):
        if document is not None:
            LOGGER.warning("advisory_stored_rejected")
        return _bundled()
    advisories = parse_document(document)
    # The refreshed document is the bundled one plus whatever the feed added,
    # so it replaces rather than supplements it. Naming every feed the entries
    # came from keeps the result document honest about where a verdict
    # originated, which is the only way a reader can check one.
    return VulnerabilityDatabase(
        advisories=advisories,
        sources=[str(BUNDLED_DB), *_feed_sources(document)],
    )


def _feed_sources(document: dict[str, Any]) -> list[str]:
    """Every distinct feed the stored advisories name, in first-seen order."""
    seen: list[str] = []
    for entry in document.get("advisories") or []:
        source = entry.get("source") if isinstance(entry, dict) else None
        if isinstance(source, str) and source and source not in seen:
            seen.append(source)
    return seen


async def refresh_advisories(backend: RedisBackend, settings: WebSettings) -> str:
    """
    Ask the advisory feed once and store the result. Returns what happened.

    The outcome is one of ``disabled``, ``failed``, ``rejected``,
    ``unchanged`` or ``updated``, which is also what goes in the log. Every
    one of them except ``updated`` leaves the database exactly as it was -
    and is written down for that reason, exactly as
    :func:`webapp.schedule.refresh_schedule` writes its own: a stamp that
    only moves on success cannot say which failure has been stopping it.
    """
    outcome = await _refresh_advisories(backend, settings)
    await record_attempt(backend, ADVISORY_ATTEMPT_KEY, outcome)
    return outcome


async def _refresh_advisories(backend: RedisBackend, settings: WebSettings) -> str:
    """The attempt itself. See :func:`refresh_advisories`."""
    if not settings.advisory_refresh:
        return "disabled"

    # Merge into whatever this deployment is already using, so an advisory
    # that reached it yesterday is not lost if the feed forgets it today.
    previous = await read_document(backend, ADVISORY_DOCUMENT_KEY)
    if previous is None:
        previous = _bundled_document()

    try:
        document = await asyncio.to_thread(
            fetch_advisory_document,
            settings.advisory_refresh_url,
            previous,
            REFRESH_TIMEOUT_SECONDS,
        )
    except AdvisoryFetchError as exc:
        # The URL is operator configuration, not a visitor's target, so the
        # reason is safe to log - and without it an operator cannot tell a
        # firewall apart from a feed that moved.
        LOGGER.warning("advisory_refresh_failed %s", exc)
        return "failed"
    except Exception:  # a cron job must not die of a surprise
        LOGGER.exception("advisory_refresh_error")
        return "failed"

    if not _is_usable(document):
        LOGGER.warning("advisory_refresh_rejected")
        return "rejected"

    await write_document(
        backend, ADVISORY_DOCUMENT_KEY, ADVISORY_CHECKED_KEY, document
    )

    if previous.get("advisories") == document.get("advisories"):
        LOGGER.info("advisory_refresh_unchanged")
        return "unchanged"
    LOGGER.info(
        "advisory_refresh_updated %d", len(document.get("advisories") or [])
    )
    return "updated"


async def probe_advisories(backend: RedisBackend, settings: WebSettings) -> str:
    """
    Ask the feed what a refresh would make of its answer, storing nothing.

    The counterpart of :func:`webapp.schedule.probe_schedule`, and for the
    same reason: ``failed`` and ``rejected`` both leave the database as it
    was, and only one of them is something an operator can do anything about.
    The merge is performed exactly as a refresh performs it - against what
    this deployment is actually using - because whether the answer is usable
    depends on what it is merged into. The result is then discarded.

    ``disabled``, ``unreadable``, ``rejected`` or ``usable``.
    """
    if not settings.advisory_refresh:
        return "disabled"

    previous = await read_document(backend, ADVISORY_DOCUMENT_KEY)
    if previous is None:
        previous = _bundled_document()

    try:
        document = await asyncio.to_thread(
            fetch_advisory_document,
            settings.advisory_refresh_url,
            previous,
            REFRESH_TIMEOUT_SECONDS,
        )
    except AdvisoryFetchError as exc:
        LOGGER.info("advisory_probe_unreadable %s", exc)
        return "unreadable"
    except Exception:  # pragma: no cover - defensive, as the refresh is
        LOGGER.exception("advisory_probe_error")
        return "unreadable"

    if not _is_usable(document):
        LOGGER.info("advisory_probe_rejected")
        return "rejected"
    LOGGER.info("advisory_probe_usable")
    return "usable"


def _bundled_document() -> dict[str, Any]:
    """The bundled advisory file, as a document to merge into."""
    try:
        loaded = json.loads(BUNDLED_DB.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


async def advisory_state(
    backend: RedisBackend, settings: WebSettings
) -> dict[str, Any]:
    """What the health probe says about the database: counts and dates only."""
    database = await stored_database(backend, settings)
    checked: str | None = None
    if settings.advisory_refresh:
        checked = await last_checked(backend, ADVISORY_CHECKED_KEY)
    return {
        "advisories": len(database.advisories),
        "refresh": settings.advisory_refresh,
        "checked": checked,
    }
