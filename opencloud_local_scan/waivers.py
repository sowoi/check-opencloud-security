"""
Accepting a failed check, for a while, for a stated reason.

A waiver is an operator saying "I know, and not today". The existing form of
that is a pattern in ``--ignore-hardening``: it suppresses the alert, it says
nothing about why, and it lasts until somebody remembers to take it out.
Nobody remembers. A year later the check is still failing, the alert is still
suppressed, and the reason is in a ticket nobody can find.

This adds the two things that fix that - a reason and a deadline - without
taking anything away:

* **A pattern on its own is still a permanent waiver.** Every existing
  configuration keeps working and keeps meaning what it meant.
* **A temporary waiver is refused unless it is complete.** It needs a
  non-empty reason and a timezone-qualified expiry. A record that cannot be
  parsed is an error, never a permanent waiver by accident - failing open is
  how a typo becomes a blind spot that outlives everybody who knew about it.
* **Expiry is decided once, at the start of the scan, in UTC.** The boundary
  is ``now >= expires_at``: at the stroke of the expiry the waiver is over.
  Nothing re-reads the clock while the scan runs, so a long scan cannot have
  a check waived at the top and not at the bottom.
* **Every applicable record is reported, not just the one that matched.**
  Otherwise a permanent ``*`` sitting quietly in a configuration file would
  mask the expiry of every temporary waiver underneath it, and the report
  would say the suppression was still deliberate when it was not.

None of it touches severity, grading or the rating. A waiver decides whether
an alert is raised; the evidence stays exactly as measured.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from difflib import get_close_matches
from typing import Any

from .hardening import all_checks, header_names, is_actionable

#: What separates the three fields of a temporary waiver. A check identifier
#: is a name, a path or a port - `exposed:/config/opencloud.yaml`,
#: `debugPort:9205` - and a pattern is an fnmatch glob over those, so none of
#: them can contain a pipe. A comma or a semicolon could not be used here:
#: both already separate entries in a flag and in an environment variable.
FIELD_SEPARATOR = "|"


class WaiverError(ValueError):
    """A waiver record that cannot be understood, and so is not accepted."""


@dataclass(frozen=True)
class Waiver:
    """One accepted failure: what, why, and until when."""

    pattern: str
    #: When this stops suppressing anything. ``None`` is the old, permanent
    #: form, which has no deadline because nobody wrote one.
    expires_at: datetime | None = None
    reason: str = ""

    def matches(self, name: str) -> bool:
        """
        Whether this record covers a check identifier.

        Case-insensitive, with shell-style wildcards, so a generated family -
        ``exposed:/some/path``, ``debugPort:9205`` - is waived by one
        ``debugPort:*`` rather than one entry per port. This is the rule the
        scanner has always used and it is unchanged.
        """
        candidate, pattern = name.casefold(), self.pattern.casefold()
        return bool(pattern) and (
            candidate == pattern or fnmatch.fnmatch(candidate, pattern)
        )

    def active_at(self, now: datetime) -> bool:
        """Whether this record still suppresses an alert at ``now``."""
        if self.expires_at is None:
            return True
        return now < self.expires_at

    @property
    def temporary(self) -> bool:
        """Whether an expiry was written down for this record."""
        return self.expires_at is not None

    def as_dict(self, now: datetime) -> dict[str, Any]:
        """Render the record for the result document, camelCase as usual."""
        return {
            "pattern": self.pattern,
            "reason": self.reason,
            "expiresAt": self.expires_at.isoformat() if self.expires_at else None,
            "state": "active" if self.active_at(now) else "expired",
        }


def parse_waiver(text: str, *, require_deadline: bool = False) -> Waiver:
    """
    Read one configured waiver.

    ``pattern`` on its own is the permanent form this project has always
    accepted. ``pattern|expires|reason`` is the temporary one, and every part
    of it is required: an expiry without a reason documents nothing, and a
    reason without an expiry is the permanent form wearing a note.

    ``require_deadline`` refuses the permanent form. The inputs that exist to
    carry a deadline - ``--waive-until`` and ``temporary_waivers`` - pass it:
    there a bare pattern is never what was meant. It is usually the tail of a
    reason that a ``;`` split off into an entry of its own, and reading that
    as a permanent waiver would suppress whatever the fragment happens to
    match, forever.

    Raises :class:`WaiverError` rather than degrading to a permanent waiver.
    A malformed record is a mistake, and the safe reading of a mistake is
    "this does not suppress anything", not "this suppresses everything
    forever".
    """
    raw = text.strip()
    if not raw:
        raise WaiverError("A waiver needs a check identifier or pattern.")

    parts = [part.strip() for part in raw.split(FIELD_SEPARATOR)]
    if len(parts) == 1 and require_deadline:
        raise WaiverError(
            f"{raw!r} has no expiry and no reason. A temporary waiver is "
            f"written pattern{FIELD_SEPARATOR}expires{FIELD_SEPARATOR}reason, "
            "and a ';' separates two waivers, so it cannot appear in a "
            "reason. A permanent waiver belongs in --ignore-hardening."
        )
    if len(parts) == 1:
        return Waiver(parts[0])
    if len(parts) != 3:
        raise WaiverError(
            f"A temporary waiver is written pattern{FIELD_SEPARATOR}expires"
            f"{FIELD_SEPARATOR}reason; {raw!r} has {len(parts)} field(s)."
        )

    pattern, expires, reason = parts
    if not pattern:
        raise WaiverError(f"{raw!r} waives nothing: the pattern is empty.")
    if not reason:
        raise WaiverError(
            f"{raw!r} has no reason. A temporary waiver records why the "
            "failure is acceptable, so that whoever finds it later can tell."
        )
    return Waiver(pattern, _parse_expiry(expires, raw), reason)


def _parse_expiry(value: str, raw: str) -> datetime:
    """
    Read an expiry, which must say what timezone it is in.

    A naive timestamp is refused rather than assumed to be UTC or local: the
    two readings are hours apart, the difference decides whether an alert is
    suppressed, and the scanner has no way to know which one was meant.
    """
    text = value.strip()
    if not text:
        raise WaiverError(f"{raw!r} has no expiry.")
    # `datetime.fromisoformat` learned to read a trailing Z in 3.11, and this
    # project supports 3.10.
    normalised = f"{text[:-1]}+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(normalised)
    except ValueError as error:
        raise WaiverError(
            f"{raw!r} has an expiry that is not an ISO 8601 timestamp: {error}."
        ) from error
    if parsed.tzinfo is None:
        raise WaiverError(
            f"{raw!r} has an expiry with no timezone. Write it as "
            "2026-12-31T00:00:00Z or with an offset, so that it means the "
            "same moment wherever the scan runs."
        )
    return parsed.astimezone(UTC)


def parse_timestamp(text: str) -> datetime:
    """
    Read one moment by the same rules as an expiry: ISO 8601, with a timezone.

    For the review's ``--at``, which must mean the same instant an expiry it
    is compared against does.
    """
    return _parse_expiry(text, text)


def parse_waivers(
    values: Iterable[str], *, require_deadline: bool = False
) -> tuple[Waiver, ...]:
    """Read every configured waiver, keeping the order they were given in."""
    return tuple(
        parse_waiver(value, require_deadline=require_deadline)
        for value in values
        if value.strip()
    )


@dataclass(frozen=True)
class WaiverDecision:
    """What the configured waivers say about one failing check."""

    check: str
    #: Every record whose pattern covers this check, expired ones included.
    #: A permanent wildcard must not be able to hide that a specific
    #: temporary waiver underneath it has run out.
    applicable: tuple[Waiver, ...]
    waived: bool
    #: The moment the decision was made against, carried so that the
    #: breakdown below cannot answer against a different clock.
    at: datetime

    @property
    def expired(self) -> tuple[Waiver, ...]:
        """The applicable records that have run out."""
        return tuple(
            record
            for record in self.applicable
            if record.temporary and not record.active_at(self.at)
        )

    @property
    def only_covered_by_a_wildcard(self) -> bool:
        """
        Whether this check is suppressed only because something broader is.

        A specific temporary waiver has expired and a wider record is still
        carrying the suppression. The alert is still correctly suppressed -
        the wider record says so - but nobody re-decided it, and that is
        worth saying out loud rather than letting the expiry pass silently.
        """
        return bool(self.waived and self.expired)


def resolve(
    waivers: Sequence[Waiver], check: str, now: datetime
) -> WaiverDecision:
    """
    Decide one check against every configured record.

    Any active record is enough to suppress the alert - waivers are
    permissions, and one permission is a permission. Every applicable record
    is carried along whether it is active or not, so the report can say that
    a suppression is still deliberate, or that it is only still happening
    because something broader is covering for an expiry.
    """
    applicable = tuple(record for record in waivers if record.matches(check))
    waived = any(record.active_at(now) for record in applicable)
    return WaiverDecision(check, applicable, waived, now)


def scan_clock() -> datetime:
    """
    The one moment a scan decides every expiry against.

    Read once, at the start, in UTC. A scan that re-read the clock could
    waive a check in its first second and alert on it in its last.
    """
    return datetime.now(UTC)


def report(
    waivers: Sequence[Waiver], decisions: Iterable[WaiverDecision], now: datetime
) -> list[dict[str, Any]]:
    """
    The waiver block of the result document.

    Every configured record appears, with what it matched. A record that
    matched nothing is worth seeing too: it is usually a pattern that no
    longer corresponds to any check, which is how a waiver outlives the
    finding it was written for.
    """
    matched: dict[int, list[str]] = {index: [] for index in range(len(waivers))}
    for decision in decisions:
        for index, record in enumerate(waivers):
            if record in decision.applicable:
                matched[index].append(decision.check)
    return [
        {**record.as_dict(now), "matched": sorted(set(matched[index]))}
        for index, record in enumerate(waivers)
    ]


@dataclass(frozen=True)
class UpcomingExpiry:
    """The next moment a waiver stops suppressing a failing check."""

    at: datetime
    #: The failing checks that lose their last active waiver at ``at``.
    checks: tuple[str, ...]
    #: The record whose deadline that is, so the alert can name it.
    pattern: str
    reason: str
    #: Every record ending at ``at`` as ``(pattern, reason)``, the one above
    #: first. Two waivers written with the same deadline end together, and
    #: an alert naming one of them would leave the other's checks unexplained.
    ending: tuple[tuple[str, str], ...] = ()


def next_expiry(block: Any) -> UpcomingExpiry | None:
    """
    When the result document's waivers next let a failing check alert again.

    Read from the ``waivers`` block the scan wrote, so it answers against the
    same decisions the scan made. A check is only uncovered once *every*
    active record matching it has run out: a temporary waiver beneath a
    permanent wildcard ends without anything changing, and two overlapping
    temporary waivers end at the later of the two. Records that matched
    nothing are ignored for the same reason - their deadline passes
    unnoticed - and so are flags OpenCloud hardcodes, which never alert
    whether waived or not.

    ``None`` when no failing check is suppressed by a temporary waiver alone.
    """
    if not isinstance(block, list):
        return None
    # check -> the deadlines of the active records covering it; None is a
    # permanent record, which covers the check for good.
    covering: dict[str, list[tuple[datetime | None, dict[str, Any]]]] = {}
    for record in block:
        if not isinstance(record, dict) or record.get("state") != "active":
            continue
        expires = record.get("expiresAt")
        deadline: datetime | None = None
        if expires is not None:
            try:
                deadline = _parse_expiry(str(expires), str(expires))
            except WaiverError:
                continue
        for check in record.get("matched") or ():
            if is_actionable(str(check)):
                covering.setdefault(str(check), []).append((deadline, record))

    ends: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for check, records in covering.items():
        if any(deadline is None for deadline, _ in records):
            continue
        ends[check] = max(
            ((deadline, record) for deadline, record in records if deadline is not None),
            key=lambda item: item[0],
        )
    if not ends:
        return None
    at = min(end for end, _ in ends.values())
    checks = tuple(sorted(check for check, (end, _) in ends.items() if end == at))
    ending: list[tuple[str, str]] = []
    for check in checks:
        record = ends[check][1]
        named = (str(record.get("pattern") or ""), str(record.get("reason") or ""))
        if named not in ending:
            ending.append(named)
    return UpcomingExpiry(
        at=at,
        checks=checks,
        pattern=ending[0][0],
        reason=ending[0][1],
        ending=tuple(ending),
    )


def scanned_at(result: Mapping[str, Any]) -> datetime | None:
    """The moment the scan decided its waivers, read back from the document."""
    scanned = result.get("scannedAt")
    date = scanned.get("date") if isinstance(scanned, Mapping) else None
    if not isinstance(date, str):
        return None
    try:
        return datetime.strptime(date, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=UTC)
    except ValueError:
        return None


def days_left(result: Mapping[str, Any], now: datetime | None = None) -> int | None:
    """
    Whole days until the next waiver expiry lets a failing check alert again.

    Counted from the scan's own moment, so the number agrees with the
    ``active`` state beside it, and truncated as the certificate's
    ``daysRemaining`` is: ``0`` means it ends within the next 24 hours.
    ``None`` when nothing is suppressed by a temporary waiver alone.
    """
    upcoming = next_expiry(result.get("waivers"))
    if upcoming is None:
        return None
    moment = now or scanned_at(result) or scan_clock()
    return max((upcoming.at - moment).days, 0)


# ------------------------------------------------------------ review
#
# Everything above decides a scan. What follows reads the same records at
# rest and says which of them need a person's attention: the ones that have
# run out, are about to, cover nothing, cover the same thing twice, or were
# never given a deadline at all. It reports and suggests; it never rewrites a
# configuration, because the only person who can say whether a failure is
# still acceptable is the one who accepted it.

#: The kinds of problem a review reports, in the order it reports them. An
#: expired record comes first: it is the one that is already wrong.
EXPIRED = "expired"
EXPIRING = "expiring"
UNUSED = "unused"
OVERLAPPING = "overlapping"
PERMANENT = "permanent"
REVIEW_KINDS: tuple[str, ...] = (EXPIRED, EXPIRING, UNUSED, OVERLAPPING, PERMANENT)

#: How far ahead a suggested replacement for a permanent waiver is dated. It
#: is a placeholder for the operator to change, not a recommendation; a
#: quarter is long enough to fix most things and short enough to be re-read.
SUGGESTED_TERM_DAYS = 90


@dataclass(frozen=True)
class ReviewItem:
    """One waiver that needs a person to look at it, and what they could do."""

    kind: str
    waiver: Waiver
    detail: str
    suggestion: str
    #: What the finding is about: the failing checks a record matches, or
    #: the patterns of the records it overlaps with.
    related: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Render the item for ``--format json``, camelCase as usual."""
        return {
            "kind": self.kind,
            "pattern": self.waiver.pattern,
            "reason": self.waiver.reason,
            "expiresAt": self.waiver.expires_at.isoformat()
            if self.waiver.expires_at
            else None,
            "detail": self.detail,
            "suggestion": self.suggestion,
            "related": list(self.related),
        }


@dataclass(frozen=True)
class WaiverReview:
    """Everything a review found, decided against one moment."""

    at: datetime
    waivers: tuple[Waiver, ...]
    items: tuple[ReviewItem, ...]
    #: Whether the review had a result document to tell a used waiver from
    #: an unused one. Without it "unused" can only mean "matches nothing this
    #: build knows", which is a much weaker statement.
    evidence: bool
    #: When a failing check next alerts again, as the plugin's expiry
    #: warning computes it. Only known with evidence.
    upcoming: UpcomingExpiry | None = None

    def of_kind(self, kind: str) -> tuple[ReviewItem, ...]:
        """The items of one kind, in the order they were found."""
        return tuple(item for item in self.items if item.kind == kind)

    def as_dict(self) -> dict[str, Any]:
        """The whole review as one JSON document."""
        return {
            "reviewedAt": self.at.isoformat(),
            "waivers": len(self.waivers),
            "evidence": self.evidence,
            "counts": {kind: len(self.of_kind(kind)) for kind in REVIEW_KINDS},
            "items": [item.as_dict() for item in self.items],
            "nextExpiry": {
                "at": self.upcoming.at.isoformat(),
                "checks": list(self.upcoming.checks),
                "patterns": [pattern for pattern, _ in self.upcoming.ending],
            }
            if self.upcoming
            else None,
        }


def failing_checks(result: Mapping[str, Any]) -> tuple[str, ...]:
    """
    Every identifier a result document reports as failing, waived or not.

    The same four places the scanner decides waivers against: the extra
    checks, the hardening flags, the counted response headers and HTTPS
    enforcement. Advisory observations are left out because they can never
    be waived, and nothing here consults the ``ignored`` flag, because the
    question is what a waiver *could* be covering, not what it did.
    """
    failing: set[str] = set()
    for entry in result.get("extraChecks") or ():
        if isinstance(entry, Mapping) and entry.get("id") and not entry.get("passed"):
            failing.add(str(entry["id"]))
    hardenings = result.get("hardenings")
    if isinstance(hardenings, Mapping):
        failing.update(str(name) for name, enabled in hardenings.items() if not enabled)
    setup = result.get("setup")
    if isinstance(setup, Mapping):
        https = setup.get("https")
        if isinstance(https, Mapping) and not https.get("enforced", True):
            failing.add("httpsEnforced")
        headers = setup.get("headers")
        if isinstance(headers, Mapping):
            failing.update(str(name) for name, present in headers.items() if not present)
    return tuple(sorted(failing))


def _pattern_covers(broad: Waiver, narrow: Waiver) -> bool:
    """
    Whether every check ``narrow`` can match, ``broad`` matches too.

    Decided on the pattern text, so it holds for checks no scan has reported
    yet: ``debugPort:*`` covers ``debugPort:9205`` and ``debugPort:92*``
    alike. Two patterns that merely intersect - ``*Policy`` and
    ``Content-*`` - are not a cover; those are found from the evidence.
    """
    return broad.matches(narrow.pattern)


def _describe_deadline(waiver: Waiver, now: datetime) -> str:
    """``2026-12-31 00:00 UTC (in 3 days)``, or ``... (5 days ago)``."""
    assert waiver.expires_at is not None
    when = waiver.expires_at.strftime("%Y-%m-%d %H:%M UTC")
    delta = waiver.expires_at - now
    if delta.total_seconds() >= 0:
        days = delta.days
        return f"{when} (in {days} day{'s' if days != 1 else ''})" if days else f"{when} (within 24 hours)"
    days = (-delta).days
    return f"{when} ({days} day{'s' if days != 1 else ''} ago)" if days else f"{when} (within the last 24 hours)"


def _known_identifiers() -> tuple[str, ...]:
    """Every identifier this build can report, family roots included."""
    return tuple(
        sorted({*(entry.id for entry in all_checks()), *header_names(), "httpsEnforced"})
    )


def _matches_known(waiver: Waiver, known: Sequence[str]) -> bool:
    """
    Whether a pattern could ever match a check this build reports.

    A member of a family - ``exposed:/.env``, ``debugPort:9205`` - is not in
    the catalogue under its own name, so a pattern with a subject is judged
    by its family root: ``debugPort:*`` can match, ``debugPrt:*`` cannot.
    """
    if any(waiver.matches(name) for name in known):
        return True
    family, separator, _ = waiver.pattern.partition(":")
    return bool(separator) and any(Waiver(family).matches(name) for name in known)


def review(
    waivers: Sequence[Waiver],
    now: datetime,
    *,
    result: Mapping[str, Any] | None = None,
    expiring_within_days: int = 0,
) -> WaiverReview:
    """
    Say which configured waivers need attention, and what could be done.

    ``result`` is a result document from a recent scan of the instance the
    waivers are for. With it, "unused" means "matches no check that fails
    there"; without it, only "matches no check this build knows". Either
    way nothing is changed: every suggestion is text for a person to act on.

    ``expiring_within_days`` is the plugin's ``--waiver-warning`` window.
    Zero reports only records that have already run out.
    """
    failing = failing_checks(result) if result is not None else None
    actionable_failing = (
        tuple(check for check in failing if is_actionable(check))
        if failing is not None
        else None
    )
    known = _known_identifiers()
    active = [waiver for waiver in waivers if waiver.active_at(now)]
    items: list[ReviewItem] = []

    def matched(waiver: Waiver) -> tuple[str, ...]:
        return tuple(check for check in actionable_failing or () if waiver.matches(check))

    def still_covered(check: str, besides: Waiver) -> bool:
        return any(other.matches(check) for other in active if other is not besides)

    # Expired: already wrong. Say whether the check behind it alerts now or
    # is quietly carried by something broader.
    for waiver in waivers:
        if not waiver.temporary or waiver.active_at(now):
            continue
        checks = matched(waiver)
        carried = tuple(check for check in checks if still_covered(check, waiver))
        detail = f"Expired {_describe_deadline(waiver, now)}; it suppresses nothing any more."
        if carried:
            detail += (
                f" A broader waiver still suppresses {', '.join(carried)}, so the "
                "expiry passed without an alert."
            )
        elif checks:
            detail += f" {', '.join(checks)} alert{'s' if len(checks) == 1 else ''} again."
        elif actionable_failing is not None:
            detail += " The check it named no longer fails."
        items.append(
            ReviewItem(
                EXPIRED,
                waiver,
                detail,
                "Remove it from temporary_waivers / --waive-until. If the "
                "failure is still accepted, write a new record with a new "
                "deadline and a reason that is true today.",
                checks,
            )
        )

    # Expiring: the plugin's --waiver-warning, per record rather than only
    # the next one, so every deadline inside the window is visible at once.
    if expiring_within_days > 0:
        for waiver in active:
            if not waiver.temporary:
                continue
            assert waiver.expires_at is not None
            if (waiver.expires_at - now).days > expiring_within_days:
                continue
            checks = matched(waiver)
            uncovered = tuple(check for check in checks if not still_covered(check, waiver))
            detail = f"Expires {_describe_deadline(waiver, now)}."
            if uncovered:
                detail += f" After that {', '.join(uncovered)} will alert."
            items.append(
                ReviewItem(
                    EXPIRING,
                    waiver,
                    detail,
                    "Fix the finding before the deadline, or renew the record "
                    "with a later deadline and a current reason. Letting it "
                    "expire is the intended outcome when neither applies.",
                    uncovered or checks,
                )
            )

    # Unused: an active record that covers nothing is a blind spot waiting
    # for the day the check it names starts failing.
    for waiver in active:
        close = () if _matches_known(waiver, known) else tuple(
            get_close_matches(waiver.pattern, known, n=3)
        )
        spelling = (
            f" Check the spelling - did you mean {', '.join(close)}?" if close else ""
        )
        if actionable_failing is not None:
            if matched(waiver):
                continue
            hardcoded = tuple(
                check for check in failing or () if waiver.matches(check) and not is_actionable(check)
            )
            if hardcoded:
                detail = (
                    f"It only matches {', '.join(hardcoded)}, which OpenCloud "
                    "hardcodes and which never alerts, waived or not."
                )
            else:
                detail = "It matches no check that fails in the scan result."
            suggestion = (
                "Remove it. A waiver for a check that passes suppresses nothing "
                "today and silences the check the day it starts failing."
                + spelling
            )
        else:
            if _matches_known(waiver, known):
                continue
            detail = "It matches no identifier this build knows."
            suggestion = (
                "A check that was renamed or removed leaves its waiver behind; "
                "remove it if so." + spelling
            )
        items.append(ReviewItem(UNUSED, waiver, detail, suggestion))

    # Overlapping: two active records for the same thing. The narrower one is
    # reported, because it is the one whose deadline or reason is being
    # overruled.
    for index, narrow in enumerate(active):
        broader: list[Waiver] = []
        shared: set[str] = set()
        for other_index, other in enumerate(active):
            if other_index == index:
                continue
            same = narrow.pattern.casefold() == other.pattern.casefold()
            if same and other_index > index:
                continue  # an identical pair is reported once, on the later record
            if same or _pattern_covers(other, narrow):
                broader.append(other)
            elif other_index > index and not _pattern_covers(narrow, other):
                # Neither contains the other, yet the scan shows a check both
                # match. A pair where this record is the broader one is
                # reported on the other record instead.
                overlap = set(matched(narrow)) & set(matched(other))
                if overlap:
                    broader.append(other)
                    shared.update(overlap)
        if not broader:
            continue
        names = ", ".join(repr(other.pattern) for other in broader)
        permanent_cover = [other for other in broader if not other.temporary]
        if narrow.temporary and permanent_cover:
            detail = (
                f"Also covered by the permanent waiver {names}, so its deadline "
                "will pass without anything alerting."
            )
            suggestion = (
                "Narrow or remove the permanent waiver if the deadline is what "
                "was meant; otherwise remove this record, whose deadline "
                "decides nothing."
            )
        elif any(other.pattern.casefold() == narrow.pattern.casefold() for other in broader):
            detail = f"Duplicates {names}."
            suggestion = (
                "Keep one. If both are temporary, the later deadline is the one "
                "in force."
            )
        elif shared:
            detail = f"Waives {', '.join(sorted(shared))} together with {names}."
            suggestion = "Keep the record that says why, and narrow the other."
        else:
            detail = f"Everything it matches is also matched by {names}."
            suggestion = (
                "Remove the narrower record, or narrow the broader one so each "
                "check has one waiver with one reason."
            )
        items.append(
            ReviewItem(
                OVERLAPPING,
                narrow,
                detail,
                suggestion,
                tuple(other.pattern for other in broader),
            )
        )

    # Permanent: valid, and the form every older configuration uses, but a
    # suppression nobody will ever be reminded of.
    suggested = (now + timedelta(days=SUGGESTED_TERM_DAYS)).strftime("%Y-%m-%dT00:00:00Z")
    for waiver in waivers:
        if waiver.temporary:
            continue
        blanket = waiver.pattern.strip("*") == ""
        detail = (
            "Waives every check, with no reason and no deadline."
            if blanket
            else "No reason and no deadline: it lasts until someone remembers it."
        )
        items.append(
            ReviewItem(
                PERMANENT,
                waiver,
                detail,
                "Move it from ignore_hardenings / --ignore-hardening to a "
                f"temporary waiver, e.g. --waive-until "
                f"'{waiver.pattern}{FIELD_SEPARATOR}{suggested}{FIELD_SEPARATOR}<why this is accepted>'",
                matched(waiver),
            )
        )

    upcoming = None
    if actionable_failing is not None:
        # The plugin's own arithmetic over a block built from these records,
        # so this answers exactly what --waiver-warning would.
        upcoming = next_expiry(
            report(
                waivers,
                (resolve(waivers, check, now) for check in actionable_failing),
                now,
            )
        )
    order = {kind: position for position, kind in enumerate(REVIEW_KINDS)}
    items.sort(key=lambda item: order[item.kind])
    return WaiverReview(
        at=now,
        waivers=tuple(waivers),
        items=tuple(items),
        evidence=result is not None,
        upcoming=upcoming,
    )
