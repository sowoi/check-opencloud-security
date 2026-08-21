"""
Keep the release schedule current without waiting for a release.

The schedule that ships in the wheel is written by CI, so a deployment that
has been running for six weeks rates instances against a six-week-old picture
of the world. It calls a current release "ahead of the schedule" and an
expired line "still supported", and the visitor has no way to tell.

So the worker reads the published lifecycle page once a day and keeps the
result in Redis, where the scan jobs pick it up. Three rules make that safe:

* **A refresh can only add knowledge.** A document that has lost a line the
  bundled schedule knows about is refused, because losing a line turns an
  end-of-life instance into an unknown one - a false pass, which is the one
  direction a security tool must not fail in.
* **A failure changes nothing.** An unreachable page, a redesigned page, a
  truncated page: every one of them leaves the previous schedule in place.
  There is no partial refresh and no empty schedule.
* **The bundled file always wins when it is newer.** A deployment that pulls
  a new image gets the schedule CI committed, not whatever is left in Redis
  from before.

Nothing here writes to the repository: ``README.md`` and the bundled JSON are
CI's business (``scripts/update_release_schedule.py``), and a running service
has no opinion about either.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from opencloud_local_scan.schedule_source import (
    MIN_LINES,
    ExtractionError,
    fetch_schedule_document,
)
from opencloud_local_scan.versions import (
    ReleaseSchedule,
    load_release_schedule,
    schedule_from_document,
)

from .redis_backend import RedisBackend
from .reference_data import (
    REFRESH_TIMEOUT_SECONDS,
    SCHEDULE_CHECKED_KEY,
    SCHEDULE_DOCUMENT_KEY,
    last_checked,
    read_document,
    write_document,
)
from .settings import WebSettings

LOGGER = logging.getLogger("check_opencloud.web.schedule")

__all__ = [
    "SCHEDULE_CHECKED_KEY",
    "SCHEDULE_DOCUMENT_KEY",
    "refresh_schedule",
    "schedule_state",
    "stored_schedule",
]


def _is_improvement(candidate: ReleaseSchedule, bundled: ReleaseSchedule) -> bool:
    """
    Whether a candidate schedule may replace the one that ships in the wheel.

    "Improvement" is deliberately narrow: it must be at least as complete as
    the bundled schedule and at least as recent. A schedule that dropped a
    line would quietly stop reporting an expired release as expired.
    """
    if len(candidate.lines) < MIN_LINES:
        return False
    if not set(bundled.lines).issubset(candidate.lines):
        return False
    return not (bundled.updated and (candidate.updated or "") < bundled.updated)


async def stored_schedule(
    backend: RedisBackend, settings: WebSettings
) -> ReleaseSchedule:
    """
    The schedule scans should be rated against, refreshed or bundled.

    Always returns a usable schedule. The refreshed document is used only
    when it still passes the same test it had to pass to be stored, so a
    newer bundled file after a redeployment takes precedence on its own.
    """
    bundled = load_release_schedule()
    if not settings.schedule_refresh:
        return bundled
    document = await read_document(backend, SCHEDULE_DOCUMENT_KEY)
    if document is None:
        return bundled
    candidate = schedule_from_document(document)
    if not _is_improvement(candidate, bundled):
        LOGGER.info("schedule_stored_superseded")
        return bundled
    return candidate


async def refresh_schedule(backend: RedisBackend, settings: WebSettings) -> str:
    """
    Read the lifecycle page once and store the result. Returns what happened.

    The outcome is one of ``disabled``, ``failed``, ``rejected``,
    ``unchanged`` or ``updated``, which is also what goes in the log. Every
    one of them except ``updated`` leaves the schedule exactly as it was.
    """
    if not settings.schedule_refresh:
        return "disabled"

    try:
        document = await asyncio.to_thread(
            fetch_schedule_document,
            settings.schedule_refresh_url,
            REFRESH_TIMEOUT_SECONDS,
        )
    except ExtractionError as exc:
        # The URL is operator configuration, not a visitor's target, so the
        # reason is safe to log - and without it an operator cannot tell a
        # firewall apart from a redesigned page.
        LOGGER.warning("schedule_refresh_failed %s", exc)
        return "failed"
    except Exception:  # pragma: no cover - defensive; a cron job must not die
        LOGGER.exception("schedule_refresh_error")
        return "failed"

    bundled = load_release_schedule()
    if not _is_improvement(schedule_from_document(document), bundled):
        LOGGER.warning("schedule_refresh_rejected")
        return "rejected"

    previous = await read_document(backend, SCHEDULE_DOCUMENT_KEY)
    await write_document(
        backend, SCHEDULE_DOCUMENT_KEY, SCHEDULE_CHECKED_KEY, document
    )

    if previous is not None and previous.get("lines") == document.get("lines"):
        LOGGER.info("schedule_refresh_unchanged")
        return "unchanged"
    LOGGER.info("schedule_refresh_updated %s", document.get("updated") or "?")
    return "updated"


async def schedule_state(
    backend: RedisBackend, settings: WebSettings
) -> dict[str, Any]:
    """What the health probe says about the schedule: dates, never a target."""
    schedule = await stored_schedule(backend, settings)
    checked: str | None = None
    if settings.schedule_refresh:
        checked = await last_checked(backend, SCHEDULE_CHECKED_KEY)
    return {
        "updated": schedule.updated,
        "refresh": settings.schedule_refresh,
        "checked": checked,
    }
