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
