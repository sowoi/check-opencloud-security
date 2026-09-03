"""
Upstream reference data, kept current in a process that outlives its image.

Two things this service rates instances against are facts about the world
rather than about any instance: which OpenCloud releases are still supported,
and which ones have a published advisory. Both ship in the wheel, both are
written by CI, and both are frozen the moment an image is built - so a
deployment that has been up for six weeks is six weeks wrong about each of
them, and nobody looking at a result page can tell.

So the worker re-reads them daily and keeps the answers here, in Redis, where
the scan jobs pick them up. This module is the part the two have in common:
the keys, the marker of when a read last succeeded, and the rule that
anything unreadable is treated as absent rather than as empty. What may
replace what is *not* here, because the two answers fail in opposite
directions - losing a release line hides an end-of-life instance, while
gaining a bogus advisory alarms every healthy one - and each of them states
its own rule where it can be read.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from .redis_backend import RedisBackend

LOGGER = logging.getLogger("check_opencloud.web.reference")

#: The refreshed documents, and when each was last successfully read. None of
#: them carries a TTL: reference data is superseded, never expired, and
#: expiring it would mean falling back to something older rather than newer.
SCHEDULE_DOCUMENT_KEY = "cos:web:schedule:document"
SCHEDULE_CHECKED_KEY = "cos:web:schedule:checked"
ADVISORY_DOCUMENT_KEY = "cos:web:advisories:document"
ADVISORY_CHECKED_KEY = "cos:web:advisories:checked"

#: What the last attempt made of each source, and when it was made. The
#: checked stamp beside it moves only when a read is *accepted*, which is what
#: makes an old one worth showing - and also what it cannot explain: a source
#: nobody can reach and a document this deployment is right to refuse leave
#: exactly the same trace, which is a stamp that stopped moving. Recording the
#: attempt is what lets the operator's area tell those two apart without
#: anybody pressing a button. No TTL, like the rest: the interesting case is
#: the marker that has said the same thing for a week.
SCHEDULE_ATTEMPT_KEY = "cos:web:schedule:attempt"
ADVISORY_ATTEMPT_KEY = "cos:web:advisories:attempt"

# How long a daily read may take. Neither source is a target and neither runs
# in the path of a request, so this is generous rather than tuned.
REFRESH_TIMEOUT_SECONDS = 30


def document_from(raw: str | None) -> dict[str, Any] | None:
    """Parse a stored document, treating anything unreadable as absent."""
    if not raw:
        return None
    try:
        document = json.loads(raw)
    except ValueError:
        return None
    return document if isinstance(document, dict) else None


async def read_document(backend: RedisBackend, key: str) -> dict[str, Any] | None:
    """The stored document, or None - never an exception into a scan."""
    try:
        raw = await backend.get(key)
    except Exception:  # noqa: BLE001 - Redis must never be why a scan fails
        LOGGER.warning("reference_read_failed %s", key)
        return None
    return document_from(raw)


async def write_document(
    backend: RedisBackend, key: str, checked_key: str, document: dict[str, Any]
) -> str:
    """Store a document and record the moment it was read. Returns that moment."""
    checked = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    await backend.set(key, json.dumps(document))
    await backend.set(checked_key, checked)
    return checked


async def last_checked(backend: RedisBackend, key: str) -> str | None:
    """When a daily read last succeeded, for the health probe."""
    try:
        return await backend.get(key)
    except Exception:  # noqa: BLE001 - a health probe still has to answer
        return None


async def record_attempt(backend: RedisBackend, key: str, outcome: str) -> None:
    """Remember what the last refresh attempt made of the source.

    ``disabled`` is not an attempt and is not recorded: a refresh that never
    ran has nothing to say about the source, and a marker left behind by the
    last deployment that did run it would be read as though it had.

    Never raises. This is an explanation of a refresh, and an explanation that
    can break the thing it explains is worth less than none.
    """
    if outcome == "disabled":
        return
    attempt = {
        "outcome": outcome,
        "at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        await backend.set(key, json.dumps(attempt))
    except Exception:  # noqa: BLE001 - never the reason a refresh fails
        LOGGER.warning("reference_attempt_unrecorded %s", key)


async def last_attempt(backend: RedisBackend, key: str) -> dict[str, str] | None:
    """What the last refresh attempt made of the source, if one is recorded."""
    try:
        raw = await backend.get(key)
    except Exception:  # noqa: BLE001 - a reading, never an error to a reader
        return None
    document = document_from(raw)
    if document is None:
        return None
    outcome = document.get("outcome")
    at = document.get("at")
    if not isinstance(outcome, str) or not isinstance(at, str):
        return None
    return {"outcome": outcome, "at": at}
