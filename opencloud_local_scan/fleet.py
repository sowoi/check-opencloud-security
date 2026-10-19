"""
A summary of the fleet, from the result documents already on disk.

Somebody running twenty instances has twenty archived reports and four
questions the reports never answer on their own:

* **Which instances run a release nobody patches any more?** Each report says
  so about itself, but only as of the day it was written. A release line that
  was supported last month can have closed since, so the recorded version is
  placed in the release schedule again, as of today.
* **Which waivers are about to run out?** A waiver's deadline is written in
  the report of the one host it applies to. Nobody reads twenty reports to
  find the one that alerts again on Friday.
* **What is wrong everywhere?** A finding that fails on fourteen instances is
  one change to a shared template, not fourteen tickets.
* **What did the fleet not look at?** An instance whose last report is a
  month old, whose last scan failed, or that has no report at all, is not an
  instance in good shape. It is one nobody knows about.

This module answers them from files. **It never scans and it stores
nothing**: the reports are read, summarised and forgotten, and the summary is
printed. Collecting the reports into one directory - a cron job writing
``check-opencloud-scanner scan`` output, a CI artefact store, a shared mount -
is left to whatever the operator already uses.

It measures, it does not judge, for the same reason
:mod:`opencloud_local_scan.remediation` does not: ratings stay the scanner's
0-5 numbers, and nothing here decides that a count is a WARNING. A dashboard
that went red would be a second set of thresholds nobody configured.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import coverage as coverage_module
from .findings import ADVISORY_CATEGORY, normalise_severity, severity_rank
from .hardening import describe, is_actionable
from .versions import STATE_END_OF_LIFE, STATE_UNKNOWN, ReleaseSchedule
from .waivers import scanned_at

#: Bumped when a key of the JSON summary changes meaning.
FLEET_SCHEMA = 1

#: How many days ahead a waiver deadline or an end of support is worth
#: showing. A month is long enough to plan a change and short enough that the
#: list is not every waiver ever written.
DEFAULT_WINDOW_DAYS = 30

#: How old the newest report of a host may be before the host counts as not
#: being looked at. A week, because a scan that runs daily and silently
#: stopped is exactly what this is meant to notice.
DEFAULT_STALE_AFTER_DAYS = 7

#: How many common findings are listed. The long tail is one host each and is
#: what the per-host reports are for.
DEFAULT_TOP_FINDINGS = 10

#: Coverage reasons that are not a gap in anybody's knowledge. An instance
#: with no IPv6 address was not "not checked" over IPv6 in any sense an
#: operator can act on.
_NOT_GAPS: frozenset[str] = frozenset({coverage_module.NOT_APPLICABLE})

_DEFAULT_PORTS = {"https": 443, "http": 80}

#: Control characters, including the escape that starts an ANSI sequence. A
#: version string and an error message were chosen by somebody else's server
#: and must not be able to rewrite the operator's terminal.
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _clean(value: Any, limit: int = 160) -> str:
    """A string from a report, safe to print: one line, bounded, no escapes."""
    text = _CONTROL.sub(" ", str(value if value is not None else "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def host_key(value: str) -> str:
    """
    One spelling per instance, so reports and an inventory can be matched.

    ``https://opencloud.example.com/`` and ``opencloud.example.com`` are the
    same instance; ``opencloud.example.com:9200`` is not, because two
    instances behind one name on different ports are two instances. A default
    port is dropped so that writing it out does not create a second host.
    """
    text = value.strip()
    parsed = urlsplit(text if "://" in text else f"//{text}")
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        return text.lower()
    try:
        port = parsed.port
    except ValueError:
        port = None
    scheme = parsed.scheme.lower() or "https"
    if ":" in host:
        host = f"[{host}]"
    if port and port != _DEFAULT_PORTS.get(scheme):
        return f"{host}:{port}"
    return host


def _document_host_key(document: Mapping[str, Any]) -> str:
    """The instance a document describes, including a non-default port."""
    url = document.get("url")
    if isinstance(url, str) and url:
        return host_key(url)
    return host_key(str(document.get("domain") or document.get("host") or "unknown"))


@dataclass(frozen=True)
class Report:
    """One result document read from disk."""

    path: str
    host: str
    document: Mapping[str, Any]
    #: When the scan ran, or when the file was written if the document does
    #: not say - a failed scan records no time of its own.
    at: datetime
    error: str = ""

    @property
    def failed(self) -> bool:
        return bool(self.error)


@dataclass
class _Loaded:
    reports: list[Report] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


def _moment(document: Mapping[str, Any], path: Path) -> datetime:
    moment = scanned_at(document)
    if moment is not None:
        return moment
    provenance = document.get("provenance")
    if isinstance(provenance, Mapping) and isinstance(provenance.get("scannedAt"), str):
        try:
            parsed = datetime.fromisoformat(provenance["scannedAt"])
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _files(paths: Iterable[Path]) -> list[Path]:
    """Every JSON file named, or found below a named directory."""
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(item for item in path.rglob("*.json") if item.is_file()))
        else:
            found.append(path)
    return found


def load_reports(paths: Iterable[Path]) -> tuple[list[Report], list[tuple[str, str]]]:
    """
    Read every result document under ``paths``.

    A file ``scan`` wrote for several hosts holds an array, and each element
    is a report of its own. A file that is not a result document - a baseline,
    a configuration, somebody's notes - is skipped and named rather than
    failing the whole summary: an archive directory accumulates things.
    """
    loaded = _Loaded()
    for path in _files(paths):
        name = str(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            loaded.skipped.append((name, f"cannot be read: {exc.strerror or exc}"))
            continue
        except ValueError:
            loaded.skipped.append((name, "not valid JSON"))
            continue
        entries = payload if isinstance(payload, list) else [payload]
        accepted = 0
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            if entry.get("error") and (entry.get("host") or entry.get("domain")):
                loaded.reports.append(
                    Report(
                        path=name,
                        host=_document_host_key(entry),
                        document=entry,
                        at=_moment(entry, path),
                        error=_clean(entry["error"], 300),
                    )
                )
                accepted += 1
            elif "rating" in entry and (entry.get("domain") or entry.get("url")):
                loaded.reports.append(
                    Report(
                        path=name,
                        host=_document_host_key(entry),
                        document=entry,
                        at=_moment(entry, path),
                    )
                )
                accepted += 1
        if not accepted:
            loaded.skipped.append((name, "not a result document from `scan`"))
    return loaded.reports, loaded.skipped


def read_inventory(path: Path) -> list[str]:
    """The hosts a fleet is expected to have: one per line, ``#`` comments."""
    hosts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            hosts.append(entry)
    return hosts


def _latest(reports: Sequence[Report]) -> tuple[dict[str, Report], int]:
    """
    The newest report of each host, and how many older ones were set aside.

    Newest by scan time, and a failed scan counts: if yesterday's scan could
    not reach the instance, last week's clean report is not the state of it.
    """
    newest: dict[str, Report] = {}
    for report in reports:
        current = newest.get(report.host)
        if current is None or (report.at, not report.failed) > (current.at, not current.failed):
            newest[report.host] = report
    return newest, len(reports) - len(newest)


def _days(later: datetime, earlier: datetime) -> int:
    return (later - earlier).days


def _version(document: Mapping[str, Any]) -> str:
    return _clean(document.get("version") or "unknown", 40)


def _lifecycle(
    document: Mapping[str, Any], schedule: ReleaseSchedule | None, today: date
) -> dict[str, Any]:
    """
    Where the recorded version stands: as the report said, and as of today.

    The version is a fact about the day of the scan and stays true; whether
    that version is supported is a fact about the schedule and moves. So the
    report's own verdict is kept, and the version is placed again against the
    schedule this installation has now. End of life is permanent - a line
    never comes back into support - so either side saying so is enough.
    """
    recorded = document.get("lifecycle")
    recorded = recorded if isinstance(recorded, Mapping) else {}
    recorded_state = str(recorded.get("state") or STATE_UNKNOWN)
    if document.get("EOL") is True:
        recorded_state = STATE_END_OF_LIFE
    provenance = document.get("provenance")
    track = recorded.get("declaredTrack") or (
        provenance.get("releaseTrack") if isinstance(provenance, Mapping) else None
    )

    current = None
    version = document.get("version")
    if schedule is not None and isinstance(version, str) and version:
        status = schedule.status_for(version, today=today, track=track or None)
        if status.state != STATE_UNKNOWN:
            current = status

    state = current.state if current is not None else recorded_state
    if recorded_state == STATE_END_OF_LIFE:
        state = STATE_END_OF_LIFE
    return {
        "state": state,
        "recordedState": recorded_state,
        "changedSinceScan": state != recorded_state,
        "line": _clean(current.line if current else recorded.get("line") or "", 20) or None,
        "track": _clean(
            (current.release_type if current else recorded.get("releaseType")) or "", 20
        )
        or None,
        "endOfLife": (current.end_of_life if current else recorded.get("endOfLife")) or None,
        "daysRemaining": current.days_remaining if current else None,
        "upgradeTo": _clean(
            (current.upgrade_to if current else recorded.get("upgradeTo")) or "", 40
        )
        or None,
        "reason": _clean(current.reason if current else recorded.get("reason") or "", 200),
    }


@dataclass(frozen=True)
class _Finding:
    id: str
    kind: str
    severity: str | None
    title: str
    waived: bool


def _failing(document: Mapping[str, Any]) -> list[_Finding]:
    """
    Every failing finding that could alert, as the plugin would count it.

    Extra checks and advisories carry their severity; hardening flags and
    headers carry none in the document, and none is invented for them. Flags
    OpenCloud hardcodes, and the advisory headers no OpenCloud sends, are left
    out: a finding every instance has and no operator can change would top
    this list on every fleet in existence and say nothing (ADR 0028).
    """
    waived = {str(name) for name in document.get("ignored") or () if isinstance(name, str)}
    found: dict[str, _Finding] = {}

    for entry in document.get("extraChecks") or ():
        if not isinstance(entry, Mapping) or not entry.get("id") or entry.get("passed", True):
            continue
        identifier = str(entry["id"])
        if not is_actionable(identifier):
            continue
        found[identifier] = _Finding(
            id=identifier,
            kind="check",
            severity=normalise_severity(entry.get("severity")),
            title=describe(identifier).title,
            waived=bool(entry.get("ignored")) or identifier in waived,
        )

    flags: list[tuple[str, str]] = []
    hardenings = document.get("hardenings")
    if isinstance(hardenings, Mapping):
        flags.extend((str(name), "hardening") for name, ok in hardenings.items() if not ok)
    setup = document.get("setup")
    if isinstance(setup, Mapping):
        https = setup.get("https")
        if isinstance(https, Mapping) and https.get("enforced") is False:
            flags.append(("httpsEnforced", "hardening"))
        headers = setup.get("headers")
        if isinstance(headers, Mapping):
            flags.extend((str(name), "header") for name, ok in headers.items() if not ok)
    for identifier, kind in flags:
        if identifier in found or not is_actionable(identifier):
            continue
        found[identifier] = _Finding(
            id=identifier,
            kind=kind,
            severity=None,
            title=describe(identifier).title,
            waived=identifier in waived,
        )

    for entry in document.get("vulnerabilities") or ():
        if not isinstance(entry, Mapping):
            continue
        raw = entry.get("id") or entry.get("identifier")
        if not raw:
            continue
        identifier = _clean(raw, 80)
        found[identifier] = _Finding(
            id=identifier,
            kind=ADVISORY_CATEGORY,
            severity=normalise_severity(entry.get("severity")),
            title=_clean(entry.get("title") or entry.get("summary") or identifier, 160),
            waived=False,
        )
    return list(found.values())


def _expiry(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    # A waiver is refused without a timezone, so a naive value here is a
    # hand-edited report. It is read as UTC rather than dropped: a deadline
    # nobody is shown is the failure this whole section exists to prevent.
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _waiver_deadlines(host: str, document: Mapping[str, Any], now: datetime) -> list[dict[str, Any]]:
    """
    When each failing check of one report loses its last waiver.

    The same rule :func:`opencloud_local_scan.waivers.next_expiry` applies, for
    every deadline rather than only the next: a check covered by a permanent
    record never alerts again, a check under two temporary records alerts at
    the later of the two, and a flag OpenCloud hardcodes never alerts at all.
    Unlike the report, the deadline is measured against *now*: the report was
    written days ago, and a waiver it recorded as active may already be over.
    """
    block = document.get("waivers")
    if not isinstance(block, list):
        return []
    covering: dict[str, list[tuple[datetime | None, Mapping[str, Any]]]] = {}
    for record in block:
        if not isinstance(record, Mapping):
            continue
        deadline = _expiry(record.get("expiresAt"))
        if record.get("expiresAt") is not None and deadline is None:
            continue
        for check in record.get("matched") or ():
            if isinstance(check, str) and is_actionable(check):
                covering.setdefault(check, []).append((deadline, record))

    ends: dict[datetime, dict[str, Any]] = {}
    for check, records in sorted(covering.items()):
        if any(deadline is None for deadline, _ in records):
            continue
        at = max(deadline for deadline, _ in records if deadline is not None)
        entry = ends.setdefault(at, {"checks": [], "waivers": []})
        entry["checks"].append(_clean(check, 120))
        for deadline, record in records:
            named = {
                "pattern": _clean(record.get("pattern") or "", 120),
                "reason": _clean(record.get("reason") or "", 200),
            }
            if deadline == at and named not in entry["waivers"]:
                entry["waivers"].append(named)

    return [
        {
            "host": host,
            "expiresAt": at.isoformat(),
            "daysLeft": _days(at, now),
            "expired": at <= now,
            "checks": entry["checks"],
            "waivers": entry["waivers"],
        }
        for at, entry in sorted(ends.items())
    ]


def _gaps(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        entry
        for entry in coverage_module.gaps(document)
        if entry.get("reason") not in _NOT_GAPS and entry.get("id")
    ]


def summarise(
    reports: Sequence[Report],
    *,
    skipped: Sequence[tuple[str, str]] = (),
    expected: Sequence[str] = (),
    schedule: ReleaseSchedule | None = None,
    now: datetime | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> dict[str, Any]:
    """
    The fleet summary as a document, camelCase like the result it reads.

    Every list is sorted worst or soonest first, so the first line of each
    section is the one to act on. ``schedule`` of ``None`` keeps every report's
    own lifecycle verdict without placing it again.
    """
    moment = now or datetime.now(UTC)
    today = moment.date()
    latest, superseded = _latest(reports)
    expected_keys = {host_key(host): host for host in expected}

    hosts: list[dict[str, Any]] = []
    ratings = {str(rating): 0 for rating in range(6)}
    unsupported: list[dict[str, Any]] = []
    ending: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    deadlines: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    without_coverage: list[str] = []
    findings: dict[str, dict[str, Any]] = {}
    gaps: dict[str, dict[str, Any]] = {}

    for host in sorted(latest):
        report = latest[host]
        document = report.document
        age = _days(moment, report.at)
        row: dict[str, Any] = {
            "host": host,
            "path": report.path,
            "scannedAt": report.at.isoformat(),
            "ageDays": age,
        }
        if stale_after_days and age > stale_after_days:
            stale.append({"host": host, "scannedAt": row["scannedAt"], "ageDays": age})
        if report.failed:
            row.update({"status": "failed", "error": report.error})
            failed.append(
                {"host": host, "path": report.path, "scannedAt": row["scannedAt"], "error": report.error}
            )
            hosts.append(row)
            continue

        lifecycle = _lifecycle(document, schedule, today)
        rating = document.get("rating")
        rating = rating if isinstance(rating, int) and 0 <= rating <= 5 else None
        if rating is not None:
            ratings[str(rating)] += 1
        failing = _failing(document)
        host_gaps = _gaps(document)
        if coverage_module.coverage_of(document) is None:
            without_coverage.append(host)
        row.update(
            {
                "status": "scanned",
                "version": _version(document),
                "rating": rating,
                "lifecycle": lifecycle,
                "failing": sum(1 for item in failing if not item.waived),
                "waived": sum(1 for item in failing if item.waived),
                "coverageGaps": len(host_gaps),
            }
        )
        hosts.append(row)

        base = {"host": host, "version": row["version"], **{
            key: lifecycle[key] for key in ("line", "track", "endOfLife", "upgradeTo")
        }}
        if lifecycle["state"] == STATE_END_OF_LIFE:
            unsupported.append(
                {**base, "changedSinceScan": lifecycle["changedSinceScan"], "reason": lifecycle["reason"]}
            )
        elif lifecycle["state"] == STATE_UNKNOWN:
            unknown.append({**base, "reason": lifecycle["reason"]})
        elif (
            lifecycle["daysRemaining"] is not None
            and 0 <= lifecycle["daysRemaining"] <= window_days
        ):
            ending.append({**base, "daysRemaining": lifecycle["daysRemaining"]})

        for deadline in _waiver_deadlines(host, document, moment):
            if deadline["daysLeft"] <= window_days:
                deadlines.append(deadline)

        for item in failing:
            entry = findings.setdefault(
                item.id,
                {
                    "id": item.id,
                    "kind": item.kind,
                    "category": ADVISORY_CATEGORY
                    if item.kind == ADVISORY_CATEGORY
                    else describe(item.id).category or None,
                    "title": item.title,
                    "severity": item.severity,
                    "hosts": [],
                    "waivedOn": [],
                },
            )
            entry["hosts"].append(host)
            if item.waived:
                entry["waivedOn"].append(host)
            if item.severity and (
                entry["severity"] is None
                or severity_rank(item.severity) < severity_rank(entry["severity"])
            ):
                # Severities can differ between reports written by different
                # scanner versions; the worst one is the one to plan for.
                entry["severity"] = item.severity

        for gap in host_gaps:
            identifier = _clean(gap["id"], 120)
            entry = gaps.setdefault(
                identifier,
                {"id": identifier, "group": _clean(gap.get("group") or "", 40), "hosts": [], "reasons": {}},
            )
            entry["hosts"].append(host)
            reason = _clean(gap.get("reason") or gap.get("state") or "unknown", 40)
            entry["reasons"][reason] = entry["reasons"].get(reason, 0) + 1

    unsupported.sort(key=lambda item: (item["endOfLife"] or "", item["host"]))
    ending.sort(key=lambda item: (item["daysRemaining"], item["host"]))
    # By the moment, not the string: each deadline keeps the offset its waiver
    # was written with, and "10:00+02:00" is earlier than "09:00+00:00".
    deadlines.sort(key=lambda item: (datetime.fromisoformat(item["expiresAt"]), item["host"]))
    stale.sort(key=lambda item: (-item["ageDays"], item["host"]))
    common = sorted(
        findings.values(),
        key=lambda item: (
            -len(item["hosts"]),
            severity_rank(item["severity"] or "unknown"),
            item["id"],
        ),
    )
    for counted in common:
        counted["count"] = len(counted["hosts"])
    gap_list = sorted(gaps.values(), key=lambda item: (-len(item["hosts"]), item["id"]))
    for counted in gap_list:
        counted["count"] = len(counted["hosts"])

    return {
        "schema": FLEET_SCHEMA,
        "generatedAt": moment.isoformat(),
        "windowDays": window_days,
        "staleAfterDays": stale_after_days,
        "reports": {
            "read": len(reports),
            "hosts": len(latest),
            "superseded": superseded,
            "skipped": [{"path": path, "reason": reason} for path, reason in skipped],
        },
        "ratings": ratings,
        "hosts": hosts,
        "unsupported": unsupported,
        "supportEndingSoon": ending,
        "lifecycleUnknown": unknown,
        "waiverDeadlines": deadlines,
        "commonFindings": common,
        "coverage": {
            "missingHosts": sorted(key for key in expected_keys if key not in latest),
            "unexpectedHosts": sorted(key for key in latest if key not in expected_keys)
            if expected_keys
            else [],
            "failedScans": failed,
            "staleReports": stale,
            "withoutCoverage": without_coverage,
            "gaps": gap_list,
        },
    }


def headline(summary: Mapping[str, Any]) -> dict[str, int]:
    """The counts a reader looks at first, in the order they are shown."""
    coverage = summary["coverage"]
    return {
        "hosts": summary["reports"]["hosts"],
        "unsupported": len(summary["unsupported"]),
        "waiversEnding": len(summary["waiverDeadlines"]),
        # Hosts, not rows: a host whose last scan failed a fortnight ago is
        # both a failed scan and a stale report, and still one host.
        "notCovered": len(
            {
                *coverage["missingHosts"],
                *(item["host"] for item in coverage["failedScans"]),
                *(item["host"] for item in coverage["staleReports"]),
            }
        ),
    }


# --------------------------------------------------------------------------
# Rendering. Everything below reads the summary document and nothing else, so
# the JSON form and the three readable ones cannot disagree.
# --------------------------------------------------------------------------

_HEADLINE_LABELS = {
    "hosts": "Hosts",
    "unsupported": "Unsupported releases",
    "waiversEnding": "Waivers ending",
    "notCovered": "Not covered",
}


def _when(days: int) -> str:
    if days < 0:
        return f"{-days} day{'s' if days != -1 else ''} ago"
    if days == 0:
        return "within a day"
    return f"in {days} day{'s' if days != 1 else ''}"


_STATE_WORDS = {STATE_END_OF_LIFE: "end of life", STATE_UNKNOWN: "unknown"}


def _moment_text(value: str) -> str:
    """An ISO timestamp as a person reads it, in UTC to the minute."""
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    if moment.tzinfo:
        moment = moment.astimezone(UTC)
    return moment.strftime("%Y-%m-%d %H:%M UTC")


def _rating(value: Any) -> str:
    return f"{value}/5" if isinstance(value, int) else "-"


def _sections(summary: Mapping[str, Any], top: int) -> list[tuple[str, list[str], list[list[str]], str]]:
    """
    Every section as (title, header, rows, text when empty).

    One table model for all three readable formats, so a column cannot exist
    in the Markdown and be missing from the terminal.
    """
    window = summary["windowDays"]
    coverage = summary["coverage"]
    sections: list[tuple[str, list[str], list[list[str]], str]] = []

    sections.append(
        (
            "Hosts",
            ["Host", "Version", "Rating", "Release", "Failing", "Waived", "Gaps", "Scanned"],
            [
                [
                    row["host"],
                    row.get("version", "-"),
                    _rating(row.get("rating")),
                    (
                        f"{row['lifecycle']['line'] or '?'} "
                        + _STATE_WORDS.get(row["lifecycle"]["state"], row["lifecycle"]["state"])
                        if row["status"] == "scanned"
                        else "scan failed"
                    ),
                    str(row.get("failing", "-")),
                    str(row.get("waived", "-")),
                    str(row.get("coverageGaps", "-")),
                    _when(-row["ageDays"]) if row["ageDays"] else "today",
                ]
                for row in summary["hosts"]
            ],
            "No result documents were found.",
        )
    )

    unsupported_rows = [
        [
            item["host"],
            item["version"],
            f"{item['line'] or '?'} ({item['track'] or 'unknown track'})",
            item["endOfLife"] or "-",
            item["upgradeTo"] or "-",
            "since the scan" if item.get("changedSinceScan") else "",
        ]
        for item in summary["unsupported"]
    ]
    unsupported_rows.extend(
        [
            item["host"],
            item["version"],
            f"{item['line'] or '?'} ({item['track'] or 'unknown track'})",
            f"{item['endOfLife'] or '-'} ({_when(item['daysRemaining'])})",
            item["upgradeTo"] or "-",
            "ending soon",
        ]
        for item in summary["supportEndingSoon"]
    )
    unsupported_rows.extend(
        [item["host"], item["version"], "-", "-", "-", f"unknown: {item['reason']}"]
        for item in summary["lifecycleUnknown"]
    )
    sections.append(
        (
            "Unsupported releases",
            ["Host", "Version", "Line", "End of life", "Upgrade to", "Note"],
            unsupported_rows,
            f"Every release is supported, and none ends within {window} days.",
        )
    )

    sections.append(
        (
            f"Waiver deadlines (next {window} days)",
            ["Host", "Ends", "When", "Checks", "Waiver", "Reason"],
            [
                [
                    item["host"],
                    _moment_text(item["expiresAt"]),
                    ("expired " if item["expired"] else "") + _when(item["daysLeft"]),
                    ", ".join(item["checks"]),
                    ", ".join(waiver["pattern"] for waiver in item["waivers"]),
                    "; ".join(waiver["reason"] for waiver in item["waivers"] if waiver["reason"]),
                ]
                for item in summary["waiverDeadlines"]
            ],
            f"No waiver lets a failing check alert again within {window} days.",
        )
    )

    common = summary["commonFindings"]
    shown = common if top <= 0 else common[:top]
    title = "Common findings"
    if len(shown) < len(common):
        title += f" (top {len(shown)} of {len(common)})"
    hosts = summary["reports"]["hosts"] - len(coverage["failedScans"])
    sections.append(
        (
            title,
            ["Finding", "Severity", "Hosts", "Waived", "What it is"],
            [
                [
                    item["id"],
                    item["severity"] or item["kind"],
                    f"{item['count']}/{hosts}",
                    str(len(item["waivedOn"])) if item["waivedOn"] else "",
                    item["title"],
                ]
                for item in shown
            ],
            "No report has a failing finding.",
        )
    )

    missing_rows = [[host, "no report", "-"] for host in coverage["missingHosts"]]
    missing_rows.extend(
        [item["host"], "last scan failed", item["error"]] for item in coverage["failedScans"]
    )
    missing_rows.extend(
        [item["host"], "report is stale", f"newest is {item['ageDays']} days old"]
        for item in coverage["staleReports"]
    )
    missing_rows.extend(
        [host, "no coverage block", "written before coverage was recorded"]
        for host in coverage["withoutCoverage"]
    )
    missing_rows.extend(
        [host, "not in the inventory", "-"] for host in coverage["unexpectedHosts"]
    )
    sections.append(
        (
            "Missing coverage",
            ["Host", "Gap", "Detail"],
            missing_rows,
            "Every host has a recent report.",
        )
    )
    sections.append(
        (
            "Checks not evaluated",
            ["Check", "Area", "Hosts", "Why"],
            [
                [
                    item["id"],
                    item["group"],
                    f"{item['count']}/{hosts}",
                    ", ".join(
                        f"{reason} {count}" for reason, count in sorted(item["reasons"].items())
                    ),
                ]
                for item in coverage["gaps"]
            ],
            "Every check reached a conclusion on every host.",
        )
    )

    skipped = summary["reports"]["skipped"]
    if skipped:
        sections.append(
            (
                "Files skipped",
                ["File", "Why"],
                [[item["path"], item["reason"]] for item in skipped],
                "",
            )
        )
    return sections


def _intro(summary: Mapping[str, Any]) -> list[str]:
    reports = summary["reports"]
    counts = headline(summary)
    lines = [
        f"Fleet summary, {summary['generatedAt'][:19].replace('T', ' ')} UTC",
        f"{reports['read']} report{'s' if reports['read'] != 1 else ''} read, "
        f"{reports['hosts']} host{'s' if reports['hosts'] != 1 else ''}"
        + (f", {reports['superseded']} older superseded" if reports["superseded"] else ""),
        " | ".join(f"{_HEADLINE_LABELS[key]}: {value}" for key, value in counts.items()),
    ]
    ratings = summary["ratings"]
    if any(ratings.values()):
        lines.append(
            "Ratings: "
            + ", ".join(f"{rating}/5 x{count}" for rating, count in sorted(ratings.items(), reverse=True) if count)
        )
    return lines


def render_text(summary: Mapping[str, Any], *, top: int = DEFAULT_TOP_FINDINGS) -> str:
    """Aligned tables for a terminal."""
    out = _intro(summary)
    for title, header, rows, empty in _sections(summary, top):
        out.extend(["", f"== {title}"])
        if not rows:
            out.append(empty)
            continue
        table = [header, *rows]
        widths = [max(len(row[column]) for row in table) for column in range(len(header))]
        out.append("  ".join(cell.ljust(width) for cell, width in zip(header, widths)).rstrip())
        out.append("  ".join("-" * width for width in widths))
        out.extend(
            "  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows
        )
    return "\n".join(out)


def _markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("`", "'") or " "


def render_markdown(summary: Mapping[str, Any], *, top: int = DEFAULT_TOP_FINDINGS) -> str:
    """Markdown tables for a ticket, a wiki page or a pull request."""
    intro = _intro(summary)
    out = [f"# {intro[0]}", "", *(f"{line}  " for line in intro[1:])]
    for title, header, rows, empty in _sections(summary, top):
        out.extend(["", f"## {title}", ""])
        if not rows:
            out.append(empty)
            continue
        out.append("| " + " | ".join(header) + " |")
        out.append("|" + "|".join(":--" for _ in header) + "|")
        out.extend("| " + " | ".join(_markdown_cell(cell) for cell in row) + " |" for row in rows)
    return "\n".join(out)


#: The report's own stylesheet. Inline because the file has to open from a
#: disk, a mail attachment or an artefact store with nothing beside it, and
#: allowed by hash rather than by 'unsafe-inline' - see :func:`render_html`.
_STYLE = """
:root{color-scheme:light dark;--bg:#f7f7f5;--panel:#fff;--text:#1d1f21;--muted:#5f6368;
--line:#dcdcd6;--bad:#b3261e;--warn:#8a5a00;--ok:#1e6b3a;--accent:#2d5b9a}
@media (prefers-color-scheme:dark){:root{--bg:#141517;--panel:#1d1f22;--text:#e8e8e6;
--muted:#a0a4a8;--line:#34373b;--bad:#f2867d;--warn:#e7b35a;--ok:#7fcf98;--accent:#8fb4ea}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1200px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.5rem;margin:0 0 4px}
h2{font-size:1.1rem;margin:32px 0 8px}
p.meta{color:var(--muted);margin:0 0 20px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.tile b{display:block;font-size:1.9rem;font-variant-numeric:tabular-nums;line-height:1.2}
.tile span{color:var(--muted);font-size:.9rem}
.tile.bad b{color:var(--bad)}.tile.warn b{color:var(--warn)}.tile.ok b{color:var(--ok)}
.scroll{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{text-align:left;padding:7px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;white-space:nowrap}
tr:last-child td{border-bottom:0}
td:first-child{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all}
p.empty{color:var(--muted);background:var(--panel);border:1px solid var(--line);
border-radius:10px;padding:12px 16px;margin:0}
footer{color:var(--muted);font-size:.85rem;margin-top:40px}
"""


def render_html(summary: Mapping[str, Any], *, top: int = DEFAULT_TOP_FINDINGS) -> str:
    """
    One self-contained HTML page, openable from a disk.

    Nothing is fetched: no script, no font, no image, and a
    Content-Security-Policy that says so. The stylesheet is allowed by its
    hash, so even a report that somehow carried markup could not add a style
    or a script of its own - and every value from a report is escaped anyway,
    because a version string and an error message were chosen by the
    instance that was scanned.
    """
    digest = base64.b64encode(hashlib.sha256(_STYLE.encode("utf-8")).digest()).decode("ascii")
    policy = f"default-src 'none'; style-src 'sha256-{digest}'; base-uri 'none'; form-action 'none'"
    counts = headline(summary)
    tones = {
        "hosts": "",
        "unsupported": "bad" if counts["unsupported"] else "ok",
        "waiversEnding": "warn" if counts["waiversEnding"] else "ok",
        "notCovered": "warn" if counts["notCovered"] else "ok",
    }
    intro = _intro(summary)
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f'<meta http-equiv="Content-Security-Policy" content="{escape(policy)}">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="referrer" content="no-referrer">',
        '<meta name="robots" content="noindex, nofollow">',
        "<title>OpenCloud fleet summary</title>",
        f"<style>{_STYLE}</style>",
        "</head>",
        "<body>",
        "<main>",
        f"<h1>{escape(intro[0])}</h1>",
        f'<p class="meta">{"<br>".join(escape(line) for line in intro[1:2] + intro[3:])}</p>',
        '<section class="tiles" aria-label="Summary counts">',
    ]
    for key, value in counts.items():
        tone = f" {tones[key]}" if tones[key] else ""
        parts.append(
            f'<div class="tile{tone}"><b>{value}</b><span>{escape(_HEADLINE_LABELS[key])}</span></div>'
        )
    parts.append("</section>")
    for title, header, rows, empty in _sections(summary, top):
        parts.append(f"<section><h2>{escape(title)}</h2>")
        if not rows:
            parts.append(f'<p class="empty">{escape(empty)}</p></section>')
            continue
        parts.append('<div class="scroll"><table><thead><tr>')
        parts.extend(f'<th scope="col">{escape(cell)}</th>' for cell in header)
        parts.append("</tr></thead><tbody>")
        for row in rows:
            parts.append("<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>")
        parts.append("</tbody></table></div></section>")
    parts.extend(
        [
            (
                "<footer>Generated by check-opencloud-scanner fleet from saved "
                "result documents; nothing was scanned. This project is not "
                "affiliated with, endorsed by, sponsored by or supported by "
                "OpenCloud GmbH. &quot;OpenCloud&quot; and related marks belong "
                "to their respective owners.</footer>"
            ),
            "</main>",
            "</body>",
            "</html>",
        ]
    )
    return "\n".join(parts)


def render(summary: Mapping[str, Any], output_format: str, *, top: int = DEFAULT_TOP_FINDINGS) -> str:
    """Render the summary in one of ``text``, ``markdown``, ``html`` or ``json``."""
    if output_format == "json":
        return json.dumps(summary, indent=2)
    if output_format == "markdown":
        return render_markdown(summary, top=top)
    if output_format == "html":
        return render_html(summary, top=top)
    return render_text(summary, top=top)
