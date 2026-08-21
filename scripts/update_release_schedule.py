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
one. Reading that page is
:mod:`opencloud_local_scan.schedule_source`, because the web application
refreshes the same schedule at runtime and the two must not drift apart. This
script is what turns the result into the repository: it writes
``opencloud_local_scan/data/release_schedule.json`` and the generated block in
``README.md``.

Releases are grouped into *lines* (``MAJOR.MINOR``), because that is the unit
OpenCloud maintains: ``7.2.3`` is a patch of the ``7.2`` production line. A
line can belong to more than one track - ``7.2`` was published as a rolling
release first and then promoted to production, and ``4.0`` is both the
previous production line and the current LTS line.

The script is run by the release workflow, but works standalone::

    python scripts/update_release_schedule.py            # fetch and write
    python scripts/update_release_schedule.py --check    # fail if outdated

The README quotes the current release of each track, and a README that says
``7.4.0`` months after ``7.5.0`` shipped teaches the wrong thing to whoever
reads it first. So the same run rewrites the block between the
``release-schedule`` markers in ``README.md`` from the schedule it just
produced. Only that block: the prose and the worked examples around it are
written by hand and stay that way.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# One parser, in the library, because the web application refreshes the same
# schedule at runtime and scripts/ is not part of the wheel. Everything this
# file adds on top is about the repository: the checked-in JSON, the generated
# README block, and the CLI the workflows call.
from opencloud_local_scan.schedule_source import (
    LIFECYCLE_URL,
    LIFETIME_DAYS,
    ExtractionError,
    build_document,
    extract,
    fetch,
    parse_release_date,
    parse_version,
)

__all__ = [
    "ExtractionError",
    "build_document",
    "current_lines",
    "extract",
    "fetch",
    "main",
    "parse_release_date",
    "parse_version",
    "readme_is_current",
    "render_readme_block",
    "update_readme",
]

TARGET = REPO_ROOT / "opencloud_local_scan" / "data" / "release_schedule.json"
README = REPO_ROOT / "README.md"

# The generated block in README.md. Everything between the two markers is
# rewritten from the schedule; everything outside them is left alone.
README_START = "<!-- release-schedule:start -->"
README_END = "<!-- release-schedule:end -->"

TRACK_TITLES = {"rolling": "Rolling", "production": "Production", "lts": "LTS"}


def current_lines(document: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """The newest line of each track, in the order the README presents them.

    A line can carry more than one track, and the newest line of a track is
    not always the highest version number in the file - ``4.0`` is the current
    LTS line while ``7.x`` rolls on above it. So each track is resolved on its
    own, by release date.
    """
    found: list[tuple[str, dict[str, Any]]] = []
    for track in ("rolling", "production", "lts"):
        candidates = [
            entry
            for entry in document.get("lines") or []
            if track in (entry.get("tracks") or [])
        ]
        if candidates:
            newest = max(candidates, key=lambda entry: (entry.get("released") or ""))
            found.append((track, newest))
    return found


def _supported_until(track: str, entry: dict[str, Any], lifetimes: dict[str, Any]) -> str:
    """What the support window of one line depends on.

    Rolling and production lines end when their successor ships, which is a
    date nobody knows yet; only LTS has one that can be printed.
    """
    if track != "lts":
        return f"the next {track} release"
    released = parse_release_date(entry.get("released") or "") or entry.get("released")
    days = lifetimes.get("lts") or LIFETIME_DAYS["lts"]
    try:
        start = datetime.strptime(str(released), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return "2 years after the line opened"
    return (start + timedelta(days=int(days))).date().isoformat()


def render_readme_block(document: dict[str, Any]) -> str:
    """The generated README section, markers included."""
    lifetimes = document.get("lifetime_days") or dict(LIFETIME_DAYS)
    rows = [
        "| Track | Current release | Line | Line opened | Supported until |",
        "|:------|:----------------|:-----|:------------|:----------------|",
    ]
    for track, entry in current_lines(document):
        rows.append(
            f"| **{TRACK_TITLES.get(track, track)}** "
            f"| `{entry.get('latest', '')}` "
            f"| `{entry.get('line', '')}` "
            f"| {entry.get('released', 'unknown')} "
            f"| {_supported_until(track, entry, lifetimes)} |"
        )
    updated = document.get("updated") or "an earlier run"
    body = "\n".join(rows)
    return (
        f"{README_START}\n"
        "<!-- Generated by scripts/update_release_schedule.py. Do not edit by "
        "hand: the release workflow rewrites this block. -->\n\n"
        f"{body}\n\n"
        f"Read from the [OpenCloud release lifecycle][lifecycle] on {updated}.\n"
        f"{README_END}"
    )


def update_readme(document: dict[str, Any], path: Path | None = None) -> bool:
    """Rewrite the generated block. True when the file changed.

    A missing marker is a hard error rather than a silent no-op: it means
    somebody removed the block, and a README that quietly stops being updated
    is worse than one that never was.
    """
    path = path or README
    text = path.read_text(encoding="utf-8")
    start = text.find(README_START)
    end = text.find(README_END)
    if start == -1 or end == -1 or end < start:
        raise ExtractionError(
            f"{path.name} has no '{README_START}' ... '{README_END}' block to update"
        )

    updated = text[:start] + render_readme_block(document) + text[end + len(README_END) :]
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def readme_is_current(document: dict[str, Any], path: Path | None = None) -> bool:
    """Whether the README block already says what the schedule says."""
    path = path or README
    return render_readme_block(document) in path.read_text(encoding="utf-8")


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
        "--no-readme",
        dest="readme",
        action="store_false",
        help="Leave the generated block in README.md alone.",
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

    # When the schedule itself has not moved, the README is still checked
    # against the file that is already committed: the block can be stale
    # because somebody edited it, or because it was added after the last
    # refresh, and neither shows up as a change to the JSON.
    document = current if unchanged and current is not None else None
    if document is None:
        document = build_document(schedule, args.url)

    readme_current = args.readme and readme_is_current(document)
    if unchanged and (readme_current or not args.readme):
        print(f"Release schedule unchanged: {_summary(current)}")
        return 0

    if args.check:
        if unchanged:
            print("Outdated: the README block does not match the schedule", file=sys.stderr)
        else:
            print(
                f"Outdated: file has {_summary(current)}, "
                f"the lifecycle page says {_summary(schedule)}",
                file=sys.stderr,
            )
        return 1

    if not unchanged:
        TARGET.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"Updated release schedule: {_summary(current)} -> {_summary(schedule)}")

    if args.readme and update_readme(document):
        versions = ", ".join(
            f"{track} {entry.get('latest', '?')}" for track, entry in current_lines(document)
        )
        print(f"Updated {README.name}: {versions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
