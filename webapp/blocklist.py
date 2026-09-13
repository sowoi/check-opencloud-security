"""
The exclusions an operator can change while the service is running.

``COS_WEB_BLOCKED_TARGETS`` is read once at startup, which is right for the
promise a deployment makes about itself and wrong for the request that arrives
at four in the afternoon: somebody asks not to be scanned, and the answer
should not be "after the next deployment window". So the list has a second
half, written in the operator's area and kept here, in Redis, where both the
API process and the worker read it - the API on every submission, the worker
on every job, which is what makes a change take effect immediately in a
deployment running several of each.

Two rules hold the two halves together:

- **the environment is a floor, not a default.** What the compose file names
  can never be removed from here, so a panel nobody should have reached cannot
  quietly undo what a deployment promised, and `docker compose up` is still
  the truth about the exclusions it declares;
- **an unreadable store is not an empty list.** Every other reader in this
  service treats absent reference data as "fall back to what shipped", because
  losing a release line makes a scan *less* certain. This falls the other way:
  losing an exclusion makes the service scan something it was told not to, so a
  store that cannot be read refuses the scan rather than running it.

See [ADR 0044](../adr/0044-the-operator-area-may-write-the-exclusions.md).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from .redis_backend import RedisBackend, RedisUnavailable
from .settings import WebSettings
from .ssrf import normalise_entry

LOGGER = logging.getLogger("check_opencloud.web.blocklist")

#: Where the written half lives. No TTL: an exclusion is withdrawn by
#: somebody, never by the clock, and one that expired on its own would be a
#: promise with a quiet end date.
BLOCKLIST_KEY = "cos:web:blocklist"

#: How many entries the area may store. A list is a few dozen names at most;
#: the ceiling is here so that a control which writes to Redis cannot be used
#: to fill it, and it is checked when adding rather than when reading.
MAX_STORED_ENTRIES = 200


class EntryRejected(ValueError):
    """An entry the area will not store, with the reason to show the operator."""

    def __init__(self, reason: str, key: str) -> None:
        super().__init__(reason)
        # Same split as TargetRejected: the sentence is what a JSON caller and
        # the log see, the identifier is how the page says it in the
        # operator's language.
        self.key = key


@dataclass(frozen=True)
class Exclusions:
    """Both halves of the list, kept apart because they are governed apart."""

    configured: tuple[str, ...] = ()
    """From ``COS_WEB_BLOCKED_TARGETS``. Shown, never editable here."""

    stored: tuple[str, ...] = ()
    """Written in the operator's area, and removable there."""

    updated: str = ""
    """When the written half last changed, ISO-8601, or empty if never."""

    @property
    def effective(self) -> tuple[str, ...]:
        """What the guard is actually given: both halves, configured first."""
        stored = tuple(entry for entry in self.stored if entry not in self.configured)
        return self.configured + stored


def _document(exclusions: Exclusions) -> str:
    return json.dumps({"entries": list(exclusions.stored), "updated": exclusions.updated})


def _stored_from(raw: str | None) -> tuple[tuple[str, ...], str]:
    """Parse the stored document, treating anything unreadable as no entries.

    Unreadable here means malformed JSON, which a write from this service
    cannot produce - so it is somebody else's key, or a corrupted one, and
    neither is a list of exclusions to act on. It is distinct from a store
    that did not answer, which never reaches this function.
    """
    if not raw:
        return (), ""
    try:
        document = json.loads(raw)
    except ValueError:
        LOGGER.warning("blocklist_unreadable")
        return (), ""
    if not isinstance(document, dict):
        return (), ""
    entries = document.get("entries")
    if not isinstance(entries, list):
        return (), ""
    # Normalised again on the way out: an entry that no longer parses is not
    # an exclusion anybody can rely on, and silently keeping it in the list
    # would show the operator a promise the guard is not keeping.
    clean = [normalise_entry(str(entry)) for entry in entries]
    updated = document.get("updated")
    return (
        tuple(entry for entry in clean if entry is not None),
        updated if isinstance(updated, str) else "",
    )


async def read_exclusions(backend: RedisBackend, settings: WebSettings) -> Exclusions:
    """
    Both halves, as they stand right now.

    Raises :class:`RedisUnavailable` rather than answering with the
    environment half alone. A caller that cannot be sure what is excluded must
    refuse the scan; see the module docstring.
    """
    raw = await backend.get(BLOCKLIST_KEY)
    stored, updated = _stored_from(raw)
    return Exclusions(
        configured=tuple(settings.blocked_targets), stored=stored, updated=updated
    )


async def effective_exclusions(
    backend: RedisBackend, settings: WebSettings
) -> tuple[str, ...]:
    """The list to hand :func:`webapp.ssrf.validate_target` for one request."""
    return (await read_exclusions(backend, settings)).effective


async def _write(
    backend: RedisBackend, settings: WebSettings, entries: tuple[str, ...]
) -> Exclusions:
    exclusions = Exclusions(
        configured=tuple(settings.blocked_targets),
        stored=entries,
        updated=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )
    await backend.set(BLOCKLIST_KEY, _document(exclusions))
    return exclusions


async def add_exclusion(
    backend: RedisBackend, settings: WebSettings, entry: str
) -> Exclusions:
    """
    Add one entry, in this project's single spelling for it.

    Adding what is already excluded is not an error - the operator's intent is
    satisfied either way, and a refusal would only invite them to work out
    which of the two halves already had it.
    """
    candidate = normalise_entry(entry)
    if candidate is None:
        raise EntryRejected(
            "An entry is a hostname, a .suffix domain, an address or a CIDR "
            "range. That is none of them.",
            "admin.blocklist.error.shape",
        )
    current = await read_exclusions(backend, settings)
    if candidate in current.stored or candidate in current.configured:
        return current
    if len(current.stored) >= MAX_STORED_ENTRIES:
        raise EntryRejected(
            f"This list holds {MAX_STORED_ENTRIES} entries, which is as many "
            "as the area stores. Move the standing ones into "
            "COS_WEB_BLOCKED_TARGETS.",
            "admin.blocklist.error.full",
        )
    LOGGER.info("admin_blocklist op=add entries=%d", len(current.stored) + 1)
    return await _write(backend, settings, current.stored + (candidate,))


async def remove_exclusion(
    backend: RedisBackend, settings: WebSettings, entry: str
) -> Exclusions:
    """
    Withdraw one entry the area stored.

    An entry from the environment is refused rather than ignored: silently
    doing nothing would read as "removed" on the next page load, and the
    operator would believe an exclusion was gone that is still in force.
    """
    candidate = normalise_entry(entry) or entry.strip().lower()
    current = await read_exclusions(backend, settings)
    if candidate in current.configured:
        raise EntryRejected(
            "That entry comes from COS_WEB_BLOCKED_TARGETS. Remove it there "
            "and restart, so the deployment and this list cannot disagree.",
            "admin.blocklist.error.configured",
        )
    if candidate not in current.stored:
        return current
    LOGGER.info("admin_blocklist op=remove entries=%d", len(current.stored) - 1)
    return await _write(
        backend, settings, tuple(item for item in current.stored if item != candidate)
    )


async def exclusion_counts(
    backend: RedisBackend, settings: WebSettings
) -> dict[str, object]:
    """How many exclusions are in force, for the state document.

    Counts and a timestamp, never the entries themselves: this document is
    what an operator copies into an issue report, and the addresses somebody
    asked to have excluded are the one part of it that names other people.
    """
    try:
        exclusions = await read_exclusions(backend, settings)
    except RedisUnavailable:
        return {"configured": len(settings.blocked_targets), "stored": None, "updated": ""}
    return {
        "configured": len(exclusions.configured),
        "stored": len(exclusions.stored),
        "updated": exclusions.updated,
    }


async def exclusions_or_none(
    backend: RedisBackend, settings: WebSettings
) -> Exclusions | None:
    """The two halves for a page to render, or ``None`` if the store is gone.

    The area shows readings it could not take as readings it could not take,
    rather than as zero - the same courtesy `statistics` pays the queue depth.
    """
    try:
        return await read_exclusions(backend, settings)
    except RedisUnavailable:
        return None
