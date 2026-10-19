"""
The reference data as Atom feeds: what this service has learned, subscribable.

Two documents refresh themselves daily and may only ever gain knowledge - the
advisory database ([ADR 0017](../adr/0017-the-advisory-database-refreshes-itself.md))
and the release schedule ([ADR 0016](../adr/0016-the-release-schedule-refreshes-itself.md)).
Until now the only way to notice a new advisory was to open `/catalogue` and
remember what had been there before, which is not a thing anybody does. A feed
is the cheapest possible way to be told, and it needs nothing from this
service that a visitor could not already read.

Both feeds are built from the same functions the pages use - `advisories`'
catalogue and the `ReleaseSchedule` object a scan is rated against - so a feed
and the page describing the same advisory cannot drift apart.

Everything from the advisory source is **somebody else's text**. It is escaped
and carried as `type="text"`, never as markup: a feed reader that rendered an
advisory title as HTML would be running a string this project did not write,
in an application nobody inspected. For the same reason the feeds are English
like every other machine-readable document here (ADR 0020).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, time
from typing import Any
from xml.sax.saxutils import escape

from opencloud_local_scan.versions import ReleaseSchedule

#: Entry ids have to survive a deployment moving host, so they are URNs of the
#: thing itself rather than URLs of this service.
ADVISORY_URN = "urn:check-opencloud-security:advisory:{id}"
RELEASE_URN = "urn:check-opencloud-security:release-line:{line}"
FEED_URN = "urn:check-opencloud-security:feed:{name}"

ADVISORIES_PATH = "/advisories.atom"
SCHEDULE_PATH = "/release-schedule.atom"

ATOM_MEDIA_TYPE = "application/atom+xml"


def _timestamp(value: object) -> str:
    """
    An RFC 3339 timestamp for a date the reference data recorded.

    The documents date themselves by the day, so a day becomes midnight UTC.
    Anything unreadable becomes the epoch rather than "now": a feed whose
    entries claim to have changed on every fetch is a feed that notifies
    somebody every night about advisories they read months ago.
    """
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return datetime.combine(value, time(), tzinfo=UTC).isoformat().replace(
            "+00:00", "Z"
        )
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return "1970-01-01T00:00:00Z"
    return _timestamp(parsed)


def _element(name: str, text: object, **attributes: str) -> str:
    rendered = "".join(
        f' {key}="{escape(str(value), {chr(34): "&quot;"})}"'
        for key, value in attributes.items()
    )
    return f"<{name}{rendered}>{escape(str(text))}</{name}>"


def _entry(
    *,
    entry_id: str,
    title: str,
    updated: str,
    summary: str,
    link: str = "",
    categories: Iterable[str] = (),
) -> str:
    parts = [
        _element("id", entry_id),
        _element("title", title, type="text"),
        _element("updated", updated),
        _element("summary", summary, type="text"),
    ]
    if link:
        parts.append(f'<link rel="alternate" href="{escape(link, {chr(34): "&quot;"})}"/>')
    parts.extend(
        f'<category term="{escape(str(term), {chr(34): "&quot;"})}"/>' for term in categories
    )
    return "<entry>" + "".join(parts) + "</entry>"


def _feed(
    *,
    name: str,
    title: str,
    subtitle: str,
    self_url: str,
    alternate_url: str,
    updated: str,
    entries: Iterable[str],
) -> str:
    quoted = {chr(34): "&quot;"}
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        + _element("id", FEED_URN.format(name=name))
        + _element("title", title, type="text")
        + _element("subtitle", subtitle, type="text")
        + _element("updated", updated)
        + f'<link rel="self" href="{escape(self_url, quoted)}"/>'
        + f'<link rel="alternate" href="{escape(alternate_url, quoted)}"/>'
        + "<author>" + _element("name", "check-opencloud-security") + "</author>"
        + "".join(entries)
        + "</feed>"
    )


def _range_text(ranges: Iterable[Mapping[str, Any]]) -> str:
    """The affected versions, in the half-open form the scanner matches on."""
    written = [
        f"{entry.get('introduced') or '0'} up to but not including "
        f"{entry.get('fixed') or 'any later release'}"
        for entry in ranges
    ]
    return "; ".join(written) or "every known release"


def advisories_feed(
    catalogue: list[dict[str, Any]],
    *,
    origin: str,
    updated: object,
) -> str:
    """
    The advisory database this service rates scans against, as Atom.

    Every entry carries the database's own date rather than a publication date
    of its own, because the database has never recorded one per advisory - the
    document dates the file, not the entry. So the date is the same on every
    entry, a refresh that gains one advisory restamps them all, and a reader
    should treat this as "what is known" rather than as a timeline. What a
    reader keys on is the entry id, which is stable.
    """
    stamp = _timestamp(updated)
    entries = [
        _entry(
            entry_id=ADVISORY_URN.format(id=advisory["id"]),
            title=f"{advisory['id']}: {advisory.get('title') or 'Advisory'}",
            updated=stamp,
            summary=(
                f"Severity: {advisory.get('severity') or 'unknown'}. "
                f"Affects {_range_text(advisory.get('ranges') or [])}. "
                f"{advisory.get('description') or ''}"
            ).strip(),
            link=str(advisory.get("url") or ""),
            categories=[term for term in (advisory.get("severity"), advisory.get("cwe")) if term],
        )
        for advisory in catalogue
    ]
    return _feed(
        name="advisories",
        title="OpenCloud security advisories",
        subtitle=(
            "The advisory database check-opencloud-security rates an instance "
            "against. It only ever gains entries."
        ),
        self_url=f"{origin}{ADVISORIES_PATH}",
        alternate_url=f"{origin}/catalogue",
        updated=stamp,
        entries=entries,
    )


def schedule_feed(schedule: ReleaseSchedule, *, origin: str) -> str:
    """
    The OpenCloud release lifecycle as Atom: one entry per release line.

    A line's entry is dated by its release date, which does not move, so a
    reader hears about a line once - when it appears - rather than every time
    the schedule is re-read. What each line means for an instance running it
    is the judgement the scanner already made: `status_for` is asked, not
    re-derived here.
    """
    entries = []
    for entry in sorted(schedule.lines.values(), key=lambda line: line.line, reverse=True):
        status = schedule.status_for(entry.latest)
        tracks = ", ".join(entry.tracks) or "unknown"
        end_of_life = status.end_of_life or "not yet dated"
        entries.append(
            _entry(
                entry_id=RELEASE_URN.format(line=entry.name),
                title=f"OpenCloud {entry.name} ({tracks})",
                updated=_timestamp(entry.released),
                summary=(
                    f"Released {entry.released.isoformat()}. "
                    f"Newest release on this line: {entry.latest}. "
                    f"Tracks: {tracks}. "
                    f"Supported until: {end_of_life}."
                ),
                link=schedule.source,
                categories=entry.tracks,
            )
        )
    return _feed(
        name="release-schedule",
        title="OpenCloud release schedule",
        subtitle=(
            "The release lines check-opencloud-security knows about, and when "
            "each one stops receiving fixes."
        ),
        self_url=f"{origin}{SCHEDULE_PATH}",
        alternate_url=f"{origin}/grades",
        updated=_timestamp(schedule.updated or datetime.now(UTC).date()),
        entries=entries,
    )
