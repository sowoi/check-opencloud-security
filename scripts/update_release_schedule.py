#!/usr/bin/env python3
"""Refresh the bundled OpenCloud release schedule.

OpenCloud ships three kinds of releases and each of them has its own support
window:

``rolling``
    A new release roughly every three weeks. Community supported, and only
    the newest one receives fixes - the moment the successor appears, the
    previous rolling release is done.
``production``
    Roughly every six months, professionally supported, and kept alive with
    patch releases until the next production release takes over.
``lts``
    A production line that keeps receiving backports for two years.

All three are published as tabs of the "Release Dates" table in the admin
documentation, which is the only place where the release *type* is stated at
all - the GitHub release list cannot tell a rolling release from a production
one. This script reads that page and writes
``opencloud_local_scan/data/release_schedule.json``.

Releases are grouped into *lines* (``MAJOR.MINOR``), because that is the unit
OpenCloud maintains: ``7.2.3`` is a patch of the ``7.2`` production line. A
line can belong to more than one track - ``7.2`` was published as a rolling
release first and then promoted to production, and ``4.0`` is both the
previous production line and the current LTS line.

The script is run by the release workflow, but works standalone::

    python scripts/update_release_schedule.py            # fetch and write
    python scripts/update_release_schedule.py --check    # fail if outdated
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "opencloud_local_scan" / "data" / "release_schedule.json"

LIFECYCLE_URL = "https://docs.opencloud.eu/docs/admin/resources/lifecycle/"
USER_AGENT = "check-opencloud-security/release-schedule"

# How long a release of each type is supported when nothing supersedes it.
# Rolling and production releases are really superseded by their successor;
# these numbers only bound the newest line of each track. LTS is the one
# window the documentation states outright: two years of backports.
LIFETIME_DAYS = {"rolling": 21, "production": 183, "lts": 730}

# The tab labels used on the documentation page, mapped to our track names.
TRACK_LABELS = {
    "rolling": "rolling",
    "production": "production",
    "lts": "lts",
    "long term support": "lts",
}

# Plausibility window. Anything outside it means the page changed shape and
# the file that is checked in should be left alone.
MIN_LINES = 5
MAX_LINES = 500
MIN_MAJOR = 1
MAX_MAJOR = 200

_VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")


class ExtractionError(RuntimeError):
    """The lifecycle page could not be read or made sense of."""


class _LifecycleParser(HTMLParser):
    """Collect the tab labels and the release tables of the lifecycle page.

    The page is rendered by Docusaurus: the tab headers are ``li`` elements
    with ``role="tab"`` and the tables live in sibling ``div`` elements with
    ``role="tabpanel"``, in the same order. Only the first two columns
    (version and release date) are of interest.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.labels: list[str] = []
        self.panels: list[list[list[str]]] = []
        self._tab_depth = 0
        self._panel_depth = 0
        self._cell_depth = 0
        self._buffer: list[str] = []
        self._row: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        role = dict(attrs).get("role")
        if role == "tab":
            self._tab_depth = 1
            self._buffer = []
            return
        if role == "tabpanel":
            self._panel_depth = 1
            self.panels.append([])
            return
        if self._tab_depth:
            self._tab_depth += 1
        if self._panel_depth:
            if tag == "tr":
                self._row = []
            elif tag == "td":
                self._cell_depth = 1
                self._buffer = []
            elif self._cell_depth:
                self._cell_depth += 1
            else:
                self._panel_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._cell_depth:
            self._cell_depth -= 1
            if self._cell_depth == 0:
                self._row.append("".join(self._buffer).strip())
            return
        if self._tab_depth:
            self._tab_depth -= 1
            if self._tab_depth == 0:
                self.labels.append("".join(self._buffer).strip())
            return
        if self._panel_depth:
            if tag == "tr":
                if self._row:
                    self.panels[-1].append(self._row)
                self._row = []
                return
            self._panel_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._cell_depth or self._tab_depth:
            self._buffer.append(data)


def fetch(url: str, timeout: int = 30) -> str:
    """Download the lifecycle page."""
    if not url.startswith(("http://", "https://")):
        raise ExtractionError(f"Refusing to fetch a non-HTTP URL: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - scheme validated above
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _parse_version(text: str) -> tuple[int, int, int] | None:
    """Turn a table cell such as 'v7.2.3' into (7, 2, 3).

    Announced but unnamed releases are written as '-' and upcoming ones as
    'TBD'; both are skipped.
    """
    match = _VERSION.match(text.strip())
    if not match:
        return None
    major, minor, patch = match.groups()
    if not MIN_MAJOR <= int(major) <= MAX_MAJOR:
        return None
    return int(major), int(minor), int(patch or 0)


def _parse_date(text: str) -> str | None:
    """Turn a table cell such as '2026 August 3' into '2026-08-03'."""
    cleaned = " ".join(text.split())
    for pattern in ("%Y %B %d", "%Y %b %d"):
        try:
            # A calendar date without a time of day; the timezone is
            # irrelevant and attaching one would only be misleading.
            return datetime.strptime(cleaned, pattern).date().isoformat()  # noqa: DTZ007
        except ValueError:
            continue
    return None


def extract(html: str) -> dict[str, Any]:
    """Turn the lifecycle page into the release schedule document."""
    parser = _LifecycleParser()
    parser.feed(html)

    tracks: dict[str, list[tuple[tuple[int, int, int], str | None]]] = {}
    for label, rows in zip(parser.labels, parser.panels):
        track = TRACK_LABELS.get(label.strip().lower())
        if track is None:
            continue
        releases = tracks.setdefault(track, [])
        for row in rows:
            if len(row) < 2:
                continue
            version = _parse_version(row[0])
            if version is not None:
                # The date may be 'TBD' for an announced release. Such a row
                # still tells us which track its line belongs to, which is how
                # the LTS tab is recognised long before the release lands.
                releases.append((version, _parse_date(row[1])))

    if not tracks.get("rolling") or not tracks.get("production"):
        raise ExtractionError(
            "The lifecycle page did not yield a rolling and a production "
            f"release table (found: {sorted(tracks)}) - has the page changed?"
        )

    lines: dict[tuple[int, int], dict[str, Any]] = {}
    latest: dict[str, tuple[int, int, int]] = {}
    for track, releases in tracks.items():
        for version, released in releases:
            key = (version[0], version[1])
            entry = lines.setdefault(key, {"tracks": set(), "released": None, "latest": None})
            entry["tracks"].add(track)
            if released is None:
                # Announced, but not out yet: it must not become the version
                # an operator is told to upgrade to.
                continue
            if version > latest.get(track, (0, 0, 0)):
                latest[track] = version
            # The line opens with its oldest release and the newest patch on
            # it is the one an operator should be running.
            entry["released"] = min(entry["released"] or released, released)
            entry["latest"] = max(entry["latest"] or version, version)

    lines = {key: entry for key, entry in lines.items() if entry["released"]}
    if not MIN_LINES <= len(lines) <= MAX_LINES:
        raise ExtractionError(
            f"Found {len(lines)} release lines, expected between {MIN_LINES} "
            f"and {MAX_LINES} - the lifecycle page has probably changed shape"
        )

    return {
        "lines": [
            {
                "line": f"{key[0]}.{key[1]}",
                "tracks": sorted(entry["tracks"]),
                "released": entry["released"],
                "latest": ".".join(str(part) for part in entry["latest"]),
            }
            for key, entry in sorted(lines.items(), reverse=True)
        ],
        "latest_release": {
            track: ".".join(str(part) for part in version)
            for track, version in sorted(latest.items())
        },
    }


def build_document(schedule: dict[str, Any], source: str) -> dict[str, Any]:
    """Assemble the JSON document written to disk."""
    return {
        "_comment": (
            "OpenCloud release schedule, grouped by release line "
            "(MAJOR.MINOR). 'tracks' names the release types a line was "
            "published on. A rolling or production line is supported until "
            "the next line on the same track is released; an LTS line is "
            "supported for two years from its first release. Regenerate with "
            "scripts/update_release_schedule.py."
        ),
        "source": source,
        "updated": datetime.now(tz=timezone.utc).date().isoformat(),
        "lifetime_days": dict(LIFETIME_DAYS),
        **schedule,
    }


def load_current() -> dict[str, Any] | None:
    """Read the file that is currently checked in, if any."""
    if not TARGET.exists():
        return None
    try:
        loaded = json.loads(TARGET.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _summary(document: dict[str, Any] | None) -> str:
    """One-line description of a schedule, for the console output."""
    if not document:
        return "nothing"
    lines = document.get("lines") or []
    latest = document.get("latest_release") or {}
    newest = ", ".join(f"{track} {version}" for track, version in sorted(latest.items()))
    return f"{len(lines)} lines ({newest})"


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Update the OpenCloud release schedule.")
    parser.add_argument("--url", default=LIFECYCLE_URL, help="Lifecycle page to read.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only report whether the file is up to date; write nothing.",
    )
    parser.add_argument(
        "--allow-failure",
        action="store_true",
        help="Exit successfully when the lifecycle page cannot be read or parsed.",
    )
    args = parser.parse_args(argv)

    try:
        schedule = extract(fetch(args.url, timeout=args.timeout))
    except (ExtractionError, urllib.error.URLError, OSError) as exc:
        print(f"Could not determine the release schedule: {exc}", file=sys.stderr)
        # A release must not fail because the documentation site is down; the
        # file that is checked in stays in place and the scanner keeps using it.
        return 0 if args.allow_failure else 1

    current = load_current()
    unchanged = (
        current is not None
        and current.get("lines") == schedule["lines"]
        and current.get("latest_release") == schedule["latest_release"]
    )
    if unchanged:
        print(f"Release schedule unchanged: {_summary(current)}")
        return 0

    if args.check:
        print(
            f"Outdated: file has {_summary(current)}, "
            f"the lifecycle page says {_summary(schedule)}",
            file=sys.stderr,
        )
        return 1

    TARGET.write_text(
        json.dumps(build_document(schedule, args.url), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Updated release schedule: {_summary(current)} -> {_summary(schedule)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
