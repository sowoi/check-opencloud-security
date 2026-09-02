"""
What the operator's area can tell an operator, and what it can do for them.

The area is a window and four switches, and the split matters: everything it
*reads* is either a setting this deployment already holds or a date it
already recorded, and everything it *does* is something the worker already
does on a timer. Nothing here is a second implementation of anything, and
nothing here can be asked a question about a particular scan.

**No scan is visible from this module.** Not a target, not a uuid, not a
result, not a client address. The statistics are counts and settings; the
audit view shows the pseudonymised records the audit log already wrote. An
operator's area that could read what people scanned would be the database of
what everybody scanned that the rest of this service refuses to keep.

**Refreshing is the worker's job, borrowed.** The two buttons call
:func:`webapp.schedule.refresh_schedule` and
:func:`webapp.advisories.refresh_advisories` - the same functions, with the
same acceptance rules, so a document that would be refused at four in the
morning is refused when a person presses the button too. A cooldown sits in
front of both, because a button that can be held down is a way to point one
deployment's impatience at somebody else's documentation site.

**A refusal and a failure are told apart by asking, not by guessing.** Both
outcomes leave the reference data exactly as it was, so from the outside they
are the same non-event; only one of them is a network an operator can go and
look at. The probe runs the identical fetch and the identical guards and then
throws the answer away, which is what makes it safe to offer beside the two
buttons that do not.

**The search index is read, never written.** ADR 0019 makes the index a
release artefact and the container read-only, so this reports whether the
shipped index still matches the pages and the copy this build serves, and
names the release workflow as the thing that fixes it. A button that quietly
rebuilt it at runtime would put a file nobody reviewed in front of every
visitor's search.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .advisories import advisory_state, probe_advisories, refresh_advisories
from .i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES, Translator
from .redis_backend import RedisBackend, RedisUnavailable
from .schedule import probe_schedule, refresh_schedule, schedule_state
from .search import SEARCH_PAGES
from .settings import WebSettings

LOGGER = logging.getLogger("check_opencloud.web.admin")

#: The actions the area offers, as the request names them.
ACTION_SCHEDULE = "schedule"
ACTION_ADVISORIES = "advisories"
ACTIONS = frozenset({ACTION_SCHEDULE, ACTION_ADVISORIES})

#: The dry run, which is not one of :data:`ACTIONS`: it is a different route
#: because it changes nothing, and giving it its own cooldown is what lets an
#: operator press it immediately after a refresh answered ``failed`` - which
#: is the only moment anybody wants it.
ACTION_PROBE = "probe"

#: Where the cooldown for each action is remembered. Keyed per action, so a
#: schedule refresh does not hold up an advisory one.
_COOLDOWN_KEY = "cos:web:admin:cooldown:{action}"


@dataclass(frozen=True)
class IndexFreshness:
    """Whether the shipped search index still describes this build."""

    fresh: bool
    missing_locales: tuple[str, ...]
    missing_paths: tuple[str, ...]
    extra_paths: tuple[str, ...]
    changed_paths: tuple[str, ...]
    unreadable: bool = False
    #: The release the index says it was generated for, when it says.
    built_for: str | None = None


def _index_path(frontend: Path, locale: str) -> Path:
    if locale == DEFAULT_LOCALE:
        return frontend / "static" / "search-index.json"
    return frontend / "static" / f"search-index.{locale}.json"


def index_freshness(frontend: Path) -> IndexFreshness:
    """Compare the shipped index against the pages and copy this build serves.

    The generator itself lives in ``scripts/`` and is deliberately not part
    of the deployed bundle, so this cannot re-derive the index and does not
    try. What it can do is exactly what goes wrong in practice: a page added
    to :data:`webapp.search.SEARCH_PAGES` and never indexed is unsearchable,
    a language without an overlay falls back to English silently, and copy
    edited after the last release leaves the index describing pages by
    sentences they no longer contain.
    """
    missing_locales: list[str] = []
    missing_paths: list[str] = []
    extra_paths: list[str] = []
    changed_paths: list[str] = []
    built_for: str | None = None

    for locale in SUPPORTED_LOCALES:
        path = _index_path(frontend, locale)
        if not path.is_file():
            missing_locales.append(locale)
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            indexed = {
                str(entry.get("path")): entry for entry in document.get("pages", [])
            }
        except (OSError, ValueError, AttributeError, TypeError):
            # An index this build cannot read is one search is already
            # failing on; saying so is more use than a traceback nobody sees.
            return IndexFreshness(
                fresh=False,
                missing_locales=(),
                missing_paths=(),
                extra_paths=(),
                changed_paths=(),
                unreadable=True,
            )

        if locale == DEFAULT_LOCALE:
            stamp = document.get("builtFor")
            built_for = str(stamp) if stamp else None

        translate = Translator(locale)
        expected = {page.path: page for page in SEARCH_PAGES}

        if locale == DEFAULT_LOCALE:
            missing_paths = sorted(set(expected) - set(indexed))
            extra_paths = sorted(set(indexed) - set(expected))

        for path_name, page in expected.items():
            entry = indexed.get(path_name)
            if entry is None:
                continue
            title = (
                translate(page.title_key) if page.title_key else page.title
            )
            summary = (
                translate(page.summary_key) if page.summary_key else page.summary
            )
            if entry.get("title") != title or entry.get("summary") != summary:
                changed_paths.append(f"{locale}:{path_name}")

    # An index generated for another release is stale whatever the titles
    # say: the page bodies were extracted from the templates as they read
    # then. An index with no stamp at all was built before this check
    # existed, and is reported as unknown rather than asserted to be either.
    stale_release = built_for is not None and built_for != __version__
    fresh = not (
        missing_locales or missing_paths or extra_paths or changed_paths or stale_release
    )
    return IndexFreshness(
        fresh=fresh,
        missing_locales=tuple(missing_locales),
        missing_paths=tuple(missing_paths),
        extra_paths=tuple(extra_paths),
        changed_paths=tuple(sorted(changed_paths)),
        built_for=built_for,
    )


async def statistics(
    backend: RedisBackend,
    settings: WebSettings,
    *,
    queue_key: str,
    worker_key: str,
    frontend: Path,
) -> dict[str, Any]:
    """Everything the area shows, as one document.

    Counts and settings only. Every number here is either a configured limit
    or a depth, and none of them names anything anybody scanned.
    """
    try:
        health = await backend.health(queue_key, worker_key)
    except RedisUnavailable:
        health = None

    freshness = index_freshness(frontend)
    return {
        "version": __version__,
        "worker": {
            "alive": bool(health and health.worker_alive),
            "queueDepth": health.queue_depth if health else None,
            "maxWorkers": settings.max_workers,
            "scanConcurrency": settings.scan_concurrency,
        },
        "limits": {
            "ipRateLimit": settings.ip_rate_limit,
            "ipRateWindow": settings.ip_rate_window,
            "targetCooldown": settings.target_cooldown,
            "maxBatchTargets": settings.max_batch_targets,
            "resultTtl": settings.result_ttl,
            "scanTimeout": settings.scan_timeout,
        },
        "referenceData": {
            "releaseSchedule": await schedule_state(backend, settings),
            "advisories": await advisory_state(backend, settings),
            "scheduleRefresh": settings.schedule_refresh,
            "advisoryRefresh": settings.advisory_refresh,
            "refreshHour": settings.schedule_refresh_hour,
        },
        "searchIndex": {
            "fresh": freshness.fresh,
            "unreadable": freshness.unreadable,
            "builtFor": freshness.built_for,
            "running": __version__,
            "missingLocales": list(freshness.missing_locales),
            "missingPaths": list(freshness.missing_paths),
            "extraPaths": list(freshness.extra_paths),
            "changedPaths": list(freshness.changed_paths),
        },
        "audit": {
            "enabled": settings.audit_log,
            "file": bool(settings.audit_log_file),
            "buffer": settings.admin_audit_buffer,
            "recordsTargets": settings.audit_log_targets,
        },
        "surfaces": {
            "mcp": settings.enable_mcp,
            "mcpAuth": settings.mcp_auth_enabled,
            "docs": settings.enable_docs,
            "encryptResults": settings.encrypt_results,
            "allowPrivateTargets": settings.allow_private_targets,
        },
    }


async def cooldown_remaining(
    backend: RedisBackend, settings: WebSettings, action: str
) -> int:
    """Seconds before ``action`` may be triggered again, or ``0``."""
    if settings.admin_refresh_cooldown <= 0:
        return 0
    try:
        remaining = await backend.ttl(_COOLDOWN_KEY.format(action=action))
    except RedisUnavailable:
        return 0
    return max(remaining, 0)


async def _claim(backend: RedisBackend, settings: WebSettings, action: str) -> None:
    """Start ``action``'s cooldown, or note that it could not be started."""
    if settings.admin_refresh_cooldown <= 0:
        return
    try:
        await backend.set(
            _COOLDOWN_KEY.format(action=action),
            str(int(time.time())),
            ex=settings.admin_refresh_cooldown,
        )
    except RedisUnavailable:
        # The refresh itself is still safe to run; losing the cooldown
        # only means the next press is not held back.
        LOGGER.info("admin_cooldown_unavailable action=%s", action)


async def run_probe(
    backend: RedisBackend, settings: WebSettings
) -> tuple[bool, dict[str, str], int]:
    """Ask both sources what a refresh would make of them, and store nothing.

    It reaches somebody else's server exactly as a refresh does, so it is
    held back exactly as a refresh is - under its own key, because the moment
    to press it is the moment after a refresh reported ``failed`` and its
    cooldown is running.
    """
    remaining = await cooldown_remaining(backend, settings, ACTION_PROBE)
    if remaining:
        return False, {}, remaining

    await _claim(backend, settings, ACTION_PROBE)
    sources = {
        ACTION_SCHEDULE: await probe_schedule(settings),
        ACTION_ADVISORIES: await probe_advisories(backend, settings),
    }
    LOGGER.info(
        "admin_probe schedule=%s advisories=%s",
        sources[ACTION_SCHEDULE],
        sources[ACTION_ADVISORIES],
    )
    return True, sources, await cooldown_remaining(backend, settings, ACTION_PROBE)


async def run_action(
    backend: RedisBackend, settings: WebSettings, action: str
) -> tuple[bool, str, int]:
    """Perform one refresh, unless its cooldown says not yet.

    Returns whether it ran, the outcome the refresh reported - the same
    ``updated`` / ``unchanged`` / ``rejected`` / ``failed`` vocabulary that
    goes in the log - and the seconds left on the cooldown.
    """
    remaining = await cooldown_remaining(backend, settings, action)
    if remaining:
        return False, "cooldown", remaining

    await _claim(backend, settings, action)

    if action == ACTION_SCHEDULE:
        outcome = await refresh_schedule(backend, settings)
    else:
        outcome = await refresh_advisories(backend, settings)
    LOGGER.info("admin_refresh action=%s outcome=%s", action, outcome)
    return True, outcome, await cooldown_remaining(backend, settings, action)


# ------------------------------------------------------------- the live view

#: Where the area is served. Fixed, because a configurable path would be a
#: deployment's idea of a secret and this is protected by a sign-in instead.
ADMIN_PATH = "/admin"

#: How often the page asks for the readings again.
ADMIN_POLL_SECONDS = 10

#: How long a stream waits between looks before it sends a keep-alive. Long
#: enough not to be a busy loop, short enough that a record does not sit
#: unseen for a noticeable time.
_STREAM_INTERVAL_SECONDS = 1.0

#: A stream is closed after this long whatever happens, so a forgotten tab
#: does not hold a connection and a task open for ever.
_STREAM_MAX_SECONDS = 60 * 30

#: The same cap in whole minutes, for the sentence the page shows when it
#: happens. A view that goes quiet after half an hour and does not say why is
#: a view somebody eventually reads as "nothing is happening" - which is the
#: one conclusion a live audit trail must never let somebody reach by
#: accident. Derived rather than written twice, so the number in the sentence
#: cannot drift away from the number that closes the connection.
ADMIN_STREAM_MAX_MINUTES = _STREAM_MAX_SECONDS // 60


def _sse(event: str, data: str) -> str:
    """One server-sent event.

    Every newline in the payload would otherwise end the event early, which
    is both a broken frame and the way a crafted record could forge a second
    one. The audit log already JSON-encodes its records, so a newline cannot
    reach here - stripping them anyway costs nothing and means this does not
    depend on that staying true.
    """
    payload = data.replace("\r", " ").replace("\n", " ")
    return f"event: {event}\ndata: {payload}\n\n"


async def audit_events(
    request: Any,
    recent: Any,
    settings: WebSettings,
) -> AsyncIterator[str]:
    """The audit trail as it is written, for as long as somebody is watching.

    Two sources, in the order a deployment is likely to have them. The
    in-memory window is what a container logging to stdout has, and it is
    bounded. A file, when ``COS_WEB_AUDIT_LOG_FILE`` named one, is followed
    from its end - not from its beginning, because the point is what happens
    next and because replaying a retained audit trail into a browser is a
    copy of it nobody asked for.

    Neither path can show more than the log wrote. A client is a truncated
    HMAC under a salt this process holds; nothing here resolves one, and
    there is no map to resolve it with.
    """
    if not settings.audit_log:
        yield _sse("state", "disabled")
        return

    started = time.monotonic()
    cursor = 0
    if recent is not None:
        # Start from the end of the window rather than replaying it: the
        # view is a window on what happens now.
        cursor, _ = recent.since(0)

    def _follow(target: str) -> Any:
        """Open the audit file positioned at its end, or give up quietly."""
        try:
            handle = open(target, encoding="utf-8", errors="replace")  # noqa: SIM115
            handle.seek(0, os.SEEK_END)
            return handle
        except OSError:
            return None

    # Off the event loop: opening and reading a file on a mount that may be
    # slow is not something to do while nothing else can run.
    handle = None
    path = settings.audit_log_file
    if path:
        handle = await asyncio.to_thread(_follow, path)

    yield _sse("state", "live")
    try:
        while True:
            if await request.is_disconnected():
                return
            if time.monotonic() - started > _STREAM_MAX_SECONDS:
                yield _sse("state", "closed")
                return

            sent = False
            if recent is not None:
                cursor, pending = recent.since(cursor)
                for line in pending:
                    sent = True
                    yield _sse("record", line)
            elif handle is not None:
                for line in handle.readlines():
                    stripped = line.strip()
                    if stripped:
                        sent = True
                        yield _sse("record", stripped)

            if not sent:
                # A comment frame: it keeps the connection and any proxy in
                # front of it from deciding a quiet stream is a dead one.
                yield ": keep-alive\n\n"
            await asyncio.sleep(_STREAM_INTERVAL_SECONDS)
    finally:
        if handle is not None:
            handle.close()


#: What the area tells a crawler, stated rather than inherited. The area is
#: never in the sitemap and never in robots.txt - a Disallow line is a public
#: file naming the path, and a deployment's operator area is not something to
#: advertise the existence of.
ADMIN_ROBOTS = "noindex, nofollow, noarchive"
