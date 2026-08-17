"""
Version and release-lifecycle helpers for OpenCloud.

Two things shape this module:

* ``status.php`` reports a **legacy** version (``0.1.0.0`` / ``0.1.0``) in the
  ``version`` and ``versionstring`` fields for the benefit of old sync
  clients. The real release is in ``productversion``, so
  :func:`select_version` deliberately prefers that field and ignores the
  legacy placeholders.
* OpenCloud ships three kinds of releases, each with its own support window,
  so "is this version still supported?" cannot be answered from the version
  number alone:

  ``rolling``
      A release roughly every three weeks. Only the newest one is current -
      as soon as its successor appears, it stops receiving fixes.
  ``production``
      A release roughly every six months, kept alive with patch releases
      until the next production release takes over.
  ``lts``
      A production line with two years of backports.

  The published schedule lives in :data:`RELEASE_SCHEDULE_FILE`, maintained by
  ``scripts/update_release_schedule.py``. The end-of-life verdict can be
  switched off entirely with ``scanner.use_release_schedule: false``.

Releases are grouped into *lines* (``MAJOR.MINOR``) because that is the unit
OpenCloud maintains, and a line can belong to more than one track: ``7.2``
shipped as a rolling release before it became the production release.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("check_opencloud.versions")

# Maintained by scripts/update_release_schedule.py from the release dates
# published in the OpenCloud admin documentation.
RELEASE_SCHEDULE_FILE = Path(__file__).with_name("data") / "release_schedule.json"

TRACK_ROLLING = "rolling"
TRACK_PRODUCTION = "production"
TRACK_LTS = "lts"
RELEASE_TRACKS: tuple[str, ...] = (TRACK_ROLLING, TRACK_PRODUCTION, TRACK_LTS)

# Not a track of its own: "work out which track this release belongs to from
# the schedule". An operator who does not know - or who runs several
# instances on different tracks from one configuration - says this instead of
# guessing, and a wrong guess is what turns a perfectly current release into
# an F.
TRACK_AUTO = "auto"
RELEASE_TRACK_CHOICES: tuple[str, ...] = (*RELEASE_TRACKS, TRACK_AUTO)

# Ordering used to pick the track that supports a line the longest.
TRACK_RANK = {TRACK_ROLLING: 0, TRACK_PRODUCTION: 1, TRACK_LTS: 2}

# Support window of each track in days. Rolling and production releases are
# really ended by their successor; these bound the newest line of a track and
# give LTS the two-year window the documentation promises.
DEFAULT_LIFETIME_DAYS = {TRACK_ROLLING: 21, TRACK_PRODUCTION: 183, TRACK_LTS: 730}

STATE_SUPPORTED = "supported"
STATE_END_OF_LIFE = "endOfLife"
STATE_UNKNOWN = "unknown"

# Values OpenCloud reports for compatibility with legacy ownCloud clients.
# They are constants in the source and say nothing about the running release.
LEGACY_VERSIONS = frozenset({"0.1.0", "0.1.0.0"})

# Fields of status.php / the capabilities document that may carry a version,
# in the order they should be trusted.
VERSION_FIELDS: tuple[str, ...] = ("productversion", "versionstring", "version")

_VERSION_PART = re.compile(r"\d+")


def parse_version(version: str | None) -> tuple[int, ...]:
    """
    Turn a version string into a comparable tuple of integers.

    Accepts the forms seen in the wild: '7.2.0', 'v7.2.0', 'OpenCloud 7.2.0',
    '7.4.0+dev', '7.2.0-rc.1'. Only the leading numeric components are used,
    so a pre-release suffix compares equal to the release it precedes.
    Unparsable input yields an empty tuple, which compares lower than every
    real version.
    """
    if not version:
        return ()
    # '7.4.0+dev' and '7.2.0-rc.1' must not contribute their build metadata.
    head = re.split(r"[+-]", str(version).strip(), maxsplit=1)[0]
    return tuple(int(part) for part in _VERSION_PART.findall(head))


def normalise_version(version: str | None) -> str | None:
    """Strip a leading 'v' and surrounding whitespace from a release tag."""
    if not version:
        return None
    cleaned = str(version).strip()
    if cleaned[:1].lower() == "v" and cleaned[1:2].isdigit():
        cleaned = cleaned[1:]
    return cleaned or None


def is_legacy_version(version: str | None) -> bool:
    """Whether a value is one of the compatibility placeholders."""
    return (normalise_version(version) or "") in LEGACY_VERSIONS


def select_version(payload: Mapping[str, Any] | None) -> str | None:
    """
    Pick the real release from a status.php or capabilities document.

    ``productversion`` wins; ``versionstring`` and ``version`` are only used
    when they are not the legacy placeholder, which they almost always are.
    """
    if not isinstance(payload, Mapping):
        return None
    for field in VERSION_FIELDS:
        candidate = normalise_version(payload.get(field))
        if candidate and not is_legacy_version(candidate) and parse_version(candidate):
            return candidate
    return None


def compare_versions(left: str | None, right: str | None) -> int:
    """Return -1, 0 or 1 for left <, == or > right (missing parts count as 0)."""
    left_parts = parse_version(left)
    right_parts = parse_version(right)
    length = max(len(left_parts), len(right_parts))
    padded_left = left_parts + (0,) * (length - len(left_parts))
    padded_right = right_parts + (0,) * (length - len(right_parts))
    if padded_left < padded_right:
        return -1
    if padded_left > padded_right:
        return 1
    return 0


def major_version(version: str | None) -> int | None:
    """Return the major release number (the branch) of a version string."""
    parts = parse_version(version)
    return parts[0] if parts else None


def is_in_range(version: str | None, introduced: str | None, fixed: str | None) -> bool:
    """
    Test whether version falls into the half-open range [introduced, fixed).

    Both bounds are optional: an advisory without 'introduced' affects every
    older release, one without 'fixed' has no patched version yet.
    """
    if not parse_version(version):
        return False
    if introduced and compare_versions(version, introduced) < 0:
        return False
    return not (fixed and compare_versions(version, fixed) >= 0)


def newest(versions: Iterable[str]) -> str | None:
    """Return the highest version from an iterable, or None when it is empty."""
    candidates = [version for version in versions if parse_version(version)]
    if not candidates:
        return None
    return max(candidates, key=parse_version)


def release_line(version: str | None) -> tuple[int, int] | None:
    """Return the ``(MAJOR, MINOR)`` release line a version belongs to.

    The line is the unit OpenCloud maintains: ``7.2.3`` is a patch release of
    the ``7.2`` line, not a release of its own.
    """
    parts = parse_version(version)
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def format_line(line: tuple[int, int] | None) -> str | None:
    """Render a release line tuple as ``'7.2'``."""
    return None if line is None else f"{line[0]}.{line[1]}"


@dataclass(frozen=True)
class ReleaseLine:
    """One ``MAJOR.MINOR`` line of the published release schedule."""

    line: tuple[int, int]
    tracks: tuple[str, ...]
    released: date
    latest: str

    @property
    def name(self) -> str:
        """The line as it is written in the schedule, e.g. ``'7.2'``."""
        return f"{self.line[0]}.{self.line[1]}"

    @property
    def release_type(self) -> str:
        """The track that grants this line the longest support."""
        return max(self.tracks, key=lambda track: TRACK_RANK.get(track, -1))


@dataclass(frozen=True)
class LifecycleStatus:
    """Where a version stands in the OpenCloud release lifecycle."""

    version: str | None
    line: str | None = None
    release_type: str | None = None
    state: str = STATE_UNKNOWN
    released: str | None = None
    end_of_life: str | None = None
    days_remaining: int | None = None
    latest_on_line: str | None = None
    upgrade_to: str | None = None
    declared_track: str | None = None
    """The track the operator says this instance follows, if they said so."""
    reason: str = "no release schedule available"

    @property
    def eol(self) -> bool | None:
        """``True``/``False`` for a known verdict, ``None`` when unknown."""
        if self.state == STATE_UNKNOWN:
            return None
        return self.state == STATE_END_OF_LIFE

    @property
    def supported(self) -> bool | None:
        """The inverse of :attr:`eol`."""
        known = self.eol
        return None if known is None else not known

    def as_dict(self) -> dict[str, Any]:
        """Serialise for the result document."""
        return {
            "line": self.line,
            "releaseType": self.release_type,
            "state": self.state,
            "released": self.released,
            "endOfLife": self.end_of_life,
            "daysRemaining": self.days_remaining,
            "latestOnLine": self.latest_on_line,
            "upgradeTo": self.upgrade_to,
            "declaredTrack": self.declared_track,
            "reason": self.reason,
        }


class ReleaseSchedule:
    """The bundled release schedule, and the lifecycle rules that go with it.

    Support is decided per *track*, because a line can be published on more
    than one: ``7.2`` shipped as a rolling release and was then promoted to
    production, and ``4.0`` is both the previous production line and the
    current LTS line. A line is supported as long as any of its tracks still
    supports it, so the most generous track wins.
    """

    def __init__(
        self,
        lines: Iterable[ReleaseLine] = (),
        *,
        lifetime_days: Mapping[str, int] | None = None,
        latest_release: Mapping[str, str] | None = None,
        updated: str | None = None,
    ) -> None:
        self.lines: dict[tuple[int, int], ReleaseLine] = {
            entry.line: entry for entry in sorted(lines, key=lambda entry: entry.line)
        }
        self.lifetime_days = {**DEFAULT_LIFETIME_DAYS, **(lifetime_days or {})}
        self.latest_release = dict(latest_release or {})
        self.updated = updated

    def __bool__(self) -> bool:
        return bool(self.lines)

    @property
    def newest_line(self) -> tuple[int, int] | None:
        """The highest line the schedule knows about."""
        return max(self.lines) if self.lines else None

    def latest_for(self, track: str | None = None) -> str | None:
        """The newest published release, optionally restricted to one track."""
        if track:
            return normalise_version(self.latest_release.get(track))
        return newest(
            [value for value in self.latest_release.values() if value]
            or [entry.latest for entry in self.lines.values()]
        )

    def current_release(self, track: str) -> str | None:
        """The newest release published on ``track``, as far as is known.

        ``latest_release`` only records the tracks the documentation names as
        current, so a track can be missing from it while the lines it was
        published on are perfectly well known - LTS is exactly that case.
        Falling back to the lines keeps "the current release of this track"
        answerable, which is what decides whether an instance is ahead of the
        track it declared or behind it. Unlike :meth:`upgrade_target` this
        never answers with a release from a different track: the question is
        what this track ships, not where to go next.
        """
        recorded = self.latest_for(track)
        if recorded:
            return recorded
        return newest([entry.latest for entry in self.lines.values() if track in entry.tracks])

    def upgrade_target(self, track: str) -> str | None:
        """The release an instance on ``track`` should move to.

        Never recommends a less supported track than the one the instance is
        already on: an LTS instance is offered the newest LTS release and, if
        there is none on record, a production one - but never a rolling
        release, which would silently change what the operator signed up for.
        """
        rank = TRACK_RANK.get(track, 0)
        for candidate in sorted(RELEASE_TRACKS, key=lambda name: -TRACK_RANK[name]):
            if TRACK_RANK[candidate] <= rank:
                found = self.latest_for(candidate)
                if found:
                    return found
        return self.latest_for()

    def line_for(self, version: str | None) -> ReleaseLine | None:
        """The scheduled line a version belongs to, if it is a known one."""
        line = release_line(version)
        return None if line is None else self.lines.get(line)

    def successor(self, entry: ReleaseLine, track: str) -> ReleaseLine | None:
        """The next line published on ``track`` after ``entry``."""
        later = [
            candidate
            for candidate in self.lines.values()
            if track in candidate.tracks and candidate.line > entry.line
        ]
        return min(later, key=lambda candidate: candidate.line) if later else None

    def _track_end_of_life(self, entry: ReleaseLine, track: str) -> date | None:
        """When ``entry`` stops receiving fixes on ``track``.

        ``None`` means "not yet", i.e. this is the current line of the track.
        LTS is the exception: its two-year window is a promise about a length
        of time, so it expires on the clock rather than on a successor.
        """
        if track == TRACK_LTS:
            return entry.released + timedelta(days=self.lifetime_days[TRACK_LTS])
        successor = self.successor(entry, track)
        return successor.released if successor is not None else None

    def _off_track_status(
        self,
        entry: ReleaseLine,
        version: str | None,
        declared: str,
        requested: str | None,
    ) -> LifecycleStatus:
        """Judge a line that was never published on the declared track.

        There is no support window to be inside of, so the verdict comes from
        the direction the version points in. *Behind* the current release of
        the declared track means the instance is missing fixes it was promised
        and is end of life. *Ahead* of it - a rolling build seen from the
        production track - means the operator is running newer code than their
        track ships, which is a choice, not an incident: it is reported, it is
        never rated F, and no arrow points backwards.
        """
        # Name the newest release *actually on* that track. upgrade_target()
        # falls back to a better supported track when a track has none on
        # record, which is right for the arrow but would put the wrong label
        # on the version here.
        on_track = self.current_release(declared)
        released = entry.released.isoformat()

        if not on_track:
            # Nothing on record to compare against, so nothing can be said -
            # and "unknown" is the only answer that is not a guess.
            return LifecycleStatus(
                version=version,
                line=entry.name,
                release_type=entry.release_type,
                state=STATE_UNKNOWN,
                released=released,
                declared_track=requested,
                reason=f"no {declared} release is on record to compare against",
            )

        if compare_versions(version, on_track) > 0:
            latest_on_line = entry.latest if compare_versions(entry.latest, version) > 0 else None
            return LifecycleStatus(
                version=version,
                line=entry.name,
                release_type=entry.release_type,
                state=STATE_SUPPORTED,
                released=released,
                latest_on_line=latest_on_line,
                upgrade_to=latest_on_line,
                declared_track=requested,
                reason=(
                    f"ahead of the {declared} track: this is a "
                    f"{entry.release_type} release, newer than the current "
                    f"{declared} release {on_track}"
                ),
            )

        target = self.upgrade_target(declared)
        return LifecycleStatus(
            version=version,
            line=entry.name,
            release_type=declared,
            state=STATE_END_OF_LIFE,
            released=released,
            latest_on_line=None,
            upgrade_to=target if compare_versions(target, version) > 0 else None,
            declared_track=requested,
            reason=(
                f"not published on the {declared} track "
                f"(it is a {entry.release_type} release); the current "
                f"{declared} release is {on_track}"
            ),
        )

    def status_for(
        self,
        version: str | None,
        today: date | None = None,
        track: str | None = None,
    ) -> LifecycleStatus:
        """Place a version in the lifecycle.

        ``track`` is the operator declaring which track the instance follows.
        Without it - and with the explicit ``'auto'`` - the schedule picks
        whichever track supports the installed line longest, which is the
        right answer when nobody has said. With a real track, the line is
        judged on that track alone: an instance that follows the rolling track
        but sits on an old production line is behind, even though the same
        version is perfectly current for someone on production.

        A version *newer* than the current release of the declared track is
        never end of life. It is ahead of its track, which is a choice an
        operator can make deliberately, and calling it unsupported would raise
        a critical alert about a machine running the newest code there is.
        """
        now = today or datetime.now(tz=timezone.utc).date()
        requested = track.strip().lower() if track else None
        if requested not in RELEASE_TRACK_CHOICES:
            requested = None
        # 'auto' is recorded as what the operator asked for, but the judgement
        # below is the one made when nobody declared anything.
        declared = requested if requested in RELEASE_TRACKS else None
        normalised = normalise_version(version)
        line = release_line(normalised)

        if line is None or not self.lines:
            return LifecycleStatus(
                version=normalised,
                line=format_line(line),
                declared_track=requested,
                reason="no release schedule available"
                if not self.lines
                else "the reported version could not be parsed",
            )

        entry = self.lines.get(line)
        if entry is None:
            newest_line = self.newest_line
            if newest_line is not None and line > newest_line:
                # A development build or a release published after this copy
                # of the schedule was generated. Not something to alarm about.
                return LifecycleStatus(
                    version=normalised,
                    line=format_line(line),
                    # Newer than everything on record can only be a rolling
                    # release, which is the honest answer for 'auto'.
                    release_type=declared or (TRACK_ROLLING if requested else None),
                    state=STATE_SUPPORTED,
                    declared_track=requested,
                    reason="newer than every release in the bundled schedule",
                )
            return LifecycleStatus(
                version=normalised,
                line=format_line(line),
                release_type=declared,
                state=STATE_END_OF_LIFE,
                declared_track=requested,
                upgrade_to=self.upgrade_target(declared) if declared else self.latest_for(),
                reason="not part of the published release schedule",
            )

        # Pick the track that supports the line the longest. A track with no
        # end-of-life date is still current and therefore beats every date.
        # Ties go to the better supported track, so that a line published on
        # both rolling and production is described as a production release.
        if declared is not None and declared not in entry.tracks:
            return self._off_track_status(entry, normalised, declared, requested)

        if declared is not None:
            best_track, best_eol = declared, self._track_end_of_life(entry, declared)
        else:
            best_track, best_eol = max(
                ((track, self._track_end_of_life(entry, track)) for track in entry.tracks),
                key=lambda item: (
                    item[1] is None,
                    item[1] or date.min,
                    TRACK_RANK.get(item[0], 0),
                ),
            )

        released = entry.released.isoformat()
        latest_on_line = entry.latest if compare_versions(entry.latest, normalised) > 0 else None

        if best_eol is None:
            return LifecycleStatus(
                version=normalised,
                line=entry.name,
                release_type=best_track,
                state=STATE_SUPPORTED,
                released=released,
                latest_on_line=latest_on_line,
                upgrade_to=latest_on_line,
                declared_track=requested,
                reason=f"current {best_track} release",
            )

        days_remaining = (best_eol - now).days
        if days_remaining > 0:
            return LifecycleStatus(
                version=normalised,
                line=entry.name,
                release_type=best_track,
                state=STATE_SUPPORTED,
                released=released,
                end_of_life=best_eol.isoformat(),
                days_remaining=days_remaining,
                latest_on_line=latest_on_line,
                upgrade_to=latest_on_line,
                declared_track=requested,
                reason=f"{best_track} release, supported until {best_eol.isoformat()}",
            )

        # Out of support: point at the newest release of the same track so a
        # production instance is not sent onto the rolling track.
        target = self.upgrade_target(best_track)
        return LifecycleStatus(
            version=normalised,
            line=entry.name,
            release_type=best_track,
            state=STATE_END_OF_LIFE,
            released=released,
            end_of_life=best_eol.isoformat(),
            days_remaining=days_remaining,
            latest_on_line=latest_on_line,
            upgrade_to=target if compare_versions(target, normalised) > 0 else latest_on_line,
            declared_track=requested,
            reason=f"{best_track} release, unsupported since {best_eol.isoformat()}",
        )


def _parse_line_entry(raw: Any) -> ReleaseLine | None:
    """Build a :class:`ReleaseLine` from one entry of the schedule file."""
    if not isinstance(raw, Mapping):
        return None
    line = release_line(str(raw.get("line") or ""))
    latest = normalise_version(raw.get("latest"))
    tracks = tuple(
        track
        for track in (str(value).strip().lower() for value in raw.get("tracks") or ())
        if track in RELEASE_TRACKS
    )
    if line is None or not tracks or not latest:
        return None
    try:
        released = date.fromisoformat(str(raw.get("released")))
    except (TypeError, ValueError):
        return None
    return ReleaseLine(line=line, tracks=tracks, released=released, latest=latest)


def load_release_schedule(path: Path | None = None) -> ReleaseSchedule:
    """
    Read the bundled release schedule.

    Returns an empty schedule when the file is missing or unusable, which the
    callers treat as "no local knowledge" rather than "everything is EOL".
    """
    source = path or RELEASE_SCHEDULE_FILE
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        LOGGER.debug("Release schedule unavailable (%s): %s", source, exc)
        return ReleaseSchedule()
    if not isinstance(document, Mapping):
        return ReleaseSchedule()

    lines = [
        entry
        for entry in (_parse_line_entry(raw) for raw in document.get("lines") or ())
        if entry is not None
    ]
    lifetimes = {
        str(track): int(days)
        for track, days in (document.get("lifetime_days") or {}).items()
        if str(track) in RELEASE_TRACKS and str(days).isdigit()
    }
    latest = {
        str(track): str(version)
        for track, version in (document.get("latest_release") or {}).items()
        if str(track) in RELEASE_TRACKS and version
    }
    return ReleaseSchedule(
        lines,
        lifetime_days=lifetimes,
        latest_release=latest,
        updated=str(document.get("updated") or "") or None,
    )


def lifecycle_status(
    version: str | None,
    schedule: ReleaseSchedule | None = None,
    today: date | None = None,
) -> LifecycleStatus:
    """Convenience wrapper around :meth:`ReleaseSchedule.status_for`."""
    return (schedule if schedule is not None else load_release_schedule()).status_for(
        version, today
    )


def load_latest_release(track: str | None = None, path: Path | None = None) -> str | None:
    """The newest published release, optionally restricted to one track."""
    return load_release_schedule(path).latest_for(track)


def is_end_of_life(
    version: str | None,
    schedule: ReleaseSchedule | None = None,
    today: date | None = None,
) -> bool | None:
    """
    Decide whether a version is out of support.

    True when its release line stopped receiving fixes, False when it is
    still supported or newer than the schedule, and None when either the
    version or the schedule is unknown.
    """
    return lifecycle_status(version, schedule, today).eol
