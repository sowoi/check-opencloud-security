"""
Remember what a host looked like last time, so a run can report only what changed.

Monitoring a long-lived instance produces the same alert every five minutes for
as long as an issue takes to fix, which is how people learn to ignore it. A
baseline records the findings of the previous run per host; the next run can
then stay quiet while the picture is unchanged and speak up the moment it gets
worse.

Two things are deliberately *not* forgiven, no matter how long they have been
true:

* **A release that is past its end of life.** It gets no security fixes at all,
  so every day it stays in production is worse than the last one.
* **A rating that drops further** than it was at the time of the baseline.

The file is written atomically, because a monitoring plugin is killed by its
own timeout often enough that a half-written baseline is a question of when,
not if.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hardening import is_actionable

__all__ = [
    "Baseline",
    "BaselineError",
    "Comparison",
    "Snapshot",
    "load_baseline",
    "snapshot_of",
]

# Bumped only when the stored shape changes in a way older files cannot satisfy;
# an unreadable or outdated baseline is treated as "no baseline yet".
FORMAT_VERSION = 1


class BaselineError(Exception):
    """Raised when a baseline file cannot be written."""


@dataclass(frozen=True)
class Snapshot:
    """What one host looked like at the end of one run."""

    rating: int
    eol: bool
    findings: tuple[str, ...] = ()
    recorded_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Render the snapshot in the shape stored on disk."""
        return {
            "rating": self.rating,
            "eol": self.eol,
            "findings": list(self.findings),
            "recordedAt": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Snapshot | None:
        """Read a snapshot back, returning None for anything unusable."""
        if not isinstance(data, dict):
            return None
        try:
            rating = int(data.get("rating", -1))
        except (TypeError, ValueError):
            return None
        raw = data.get("findings")
        findings = tuple(str(item) for item in raw) if isinstance(raw, list) else ()
        return cls(
            rating=rating,
            eol=bool(data.get("eol", False)),
            findings=findings,
            recorded_at=str(data.get("recordedAt", "")),
        )


@dataclass(frozen=True)
class Comparison:
    """The difference between a stored snapshot and the current one."""

    previous: Snapshot | None
    current: Snapshot
    new_findings: tuple[str, ...] = ()
    resolved_findings: tuple[str, ...] = ()

    @property
    def first_run(self) -> bool:
        """True when this host has no baseline yet."""
        return self.previous is None

    @property
    def rating_worsened(self) -> bool:
        """True when the rating is lower than it was (0 is the worst grade)."""
        if self.previous is None:
            return False
        return self.current.rating < self.previous.rating

    @property
    def regressed(self) -> bool:
        """
        True when this run must still alert.

        End of life is included unconditionally: a baseline may record that an
        instance is unsupported, but it must never make that acceptable.
        """
        if self.first_run:
            return True
        return bool(self.new_findings) or self.rating_worsened or self.current.eol

    def summary(self) -> str:
        """One line explaining what the comparison decided, for the output."""
        if self.first_run:
            return "Baseline: none recorded yet, this run becomes the baseline"
        if self.new_findings:
            listed = ", ".join(self.new_findings[:5])
            more = (
                f" (+{len(self.new_findings) - 5} more)"
                if len(self.new_findings) > 5
                else ""
            )
            return f"New since last run ({len(self.new_findings)}): {listed}{more}"
        if self.rating_worsened:
            assert self.previous is not None
            return (
                f"Rating dropped from {self.previous.rating} to {self.current.rating} "
                "since the last run"
            )
        if self.current.eol:
            return "No new findings, but the release is past its end of life"
        since = self.previous.recorded_at if self.previous else ""
        known = len(self.current.findings)
        tail = f" since {since}" if since else ""
        if known:
            return f"No new findings{tail} ({known} known issue(s) unchanged)"
        return f"No new findings{tail}"


@dataclass
class Baseline:
    """The stored state of every host in one baseline file."""

    path: Path
    hosts: dict[str, Snapshot] = field(default_factory=dict)

    def snapshot(self, host: str) -> Snapshot | None:
        """Return the stored snapshot for a host, if there is one."""
        return self.hosts.get(host)

    def compare(self, host: str, current: Snapshot) -> Comparison:
        """Compare the current state of a host against what was stored."""
        previous = self.snapshot(host)
        if previous is None:
            return Comparison(previous=None, current=current)
        before = set(previous.findings)
        now = set(current.findings)
        return Comparison(
            previous=previous,
            current=current,
            new_findings=tuple(sorted(now - before)),
            resolved_findings=tuple(sorted(before - now)),
        )

    def record(self, host: str, current: Snapshot) -> None:
        """Remember the current state of a host in memory."""
        self.hosts[host] = current

    def save(self) -> None:
        """Write the baseline out atomically, creating the directory if needed."""
        payload = {
            "version": FORMAT_VERSION,
            "hosts": {host: snap.as_dict() for host, snap in sorted(self.hosts.items())},
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(
                dir=str(self.path.parent), prefix=self.path.name, suffix=".tmp"
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        except OSError as exc:
            raise BaselineError(f"Cannot write baseline {self.path}: {exc}") from exc


def load_baseline(path: str | os.PathLike[str]) -> Baseline:
    """
    Read a baseline file.

    A missing, empty, corrupt or newer-format file yields an empty baseline
    rather than an error: losing the memory of the last run degrades the check
    to its normal behaviour, which is never worse than refusing to run at all.
    """
    target = Path(path)
    baseline = Baseline(path=target)
    try:
        raw = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return baseline
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return baseline
    if not isinstance(data, dict) or data.get("version") != FORMAT_VERSION:
        return baseline
    hosts = data.get("hosts")
    if not isinstance(hosts, dict):
        return baseline
    for host, stored in hosts.items():
        snapshot = Snapshot.from_dict(stored)
        if snapshot is not None:
            baseline.hosts[str(host)] = snapshot
    return baseline


def _now() -> str:
    """The current time, to the second, in UTC."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _vulnerability_ids(response: dict[str, Any]) -> Iterable[str]:
    """Every known vulnerability, by its identifier."""
    for entry in response.get("vulnerabilities", []) or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("id") or entry.get("cve") or entry.get("title")
        yield f"vuln:{name or 'unknown'}"


def _missing_hardenings(response: dict[str, Any]) -> Iterable[str]:
    """
    Every hardening measure the result reports as absent.

    Covers the same ground as the plugin's own collection - the ``hardenings``
    block, the security headers and HTTPS enforcement - so that a library user
    who does not hand in a list gets the same answer.
    """
    hardenings = response.get("hardenings")
    if isinstance(hardenings, dict):
        yield from (name for name, enabled in hardenings.items() if not enabled)

    setup = response.get("setup")
    if not isinstance(setup, dict):
        return
    https = setup.get("https")
    if isinstance(https, dict) and not https.get("enforced", True):
        yield "httpsEnforced"
    headers = setup.get("headers")
    if isinstance(headers, dict):
        yield from (name for name, enabled in headers.items() if not enabled)


def _hardening_ids(names: Iterable[str], waived: Iterable[str]) -> Iterable[str]:
    """
    The hardening measures that are worth alerting on.

    Waived and non-actionable measures are left out for the same reason they
    are left out of the alert line: they cannot become news.
    """
    ignored = set(waived)
    for name in names:
        if name in ignored or not is_actionable(str(name)):
            continue
        yield f"hardening:{name}"


def _extra_check_ids(response: dict[str, Any]) -> Iterable[str]:
    """Every additional check that failed and was not waived."""
    for entry in response.get("extraChecks", []) or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("passed") or entry.get("ignored"):
            continue
        yield f"check:{entry.get('id', 'unknown')}"


def snapshot_of(
    response: dict[str, Any],
    waived: Iterable[str] = (),
    missing_hardenings: Iterable[str] | None = None,
) -> Snapshot:
    """
    Reduce a result document to the findings a baseline compares.

    ``missing_hardenings`` lets the caller hand in the list it has already
    worked out, so that the baseline can never disagree with the alert line
    about what is missing.

    Deliberately excluded: the scan timestamp, the duration and the version
    string. They change on their own and would make every run look new.
    """
    names = (
        _missing_hardenings(response) if missing_hardenings is None else missing_hardenings
    )
    findings = sorted(
        {
            *_vulnerability_ids(response),
            *_hardening_ids(names, waived),
            *_extra_check_ids(response),
        }
    )
    update = response.get("updates")
    if isinstance(update, dict) and update.get("available"):
        findings.append(f"update:{update.get('availableVersion') or 'unknown'}")
    try:
        rating = int(response.get("rating", -1))
    except (TypeError, ValueError):
        rating = -1
    return Snapshot(
        rating=rating,
        eol=bool(response.get("EOL", False)),
        findings=tuple(findings),
        recorded_at=_now(),
    )
