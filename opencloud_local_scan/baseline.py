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

One thing is reported that is not a finding at all: **a check that was
measured before and is inconclusive now.** The grade can stand still while
the evidence behind it shrinks, and a scan that quietly stopped being able to
see something is not a scan that found it fine. That is a statement about
coverage, kept apart from the findings and from the rating - see
:attr:`Comparison.coverage_lost`.

And a finding is only called new if the previous run could have reported it.
A check the scanner learned after that run - or one a probe setting kept it
from making - that fails now was *not measured* before, not passing, and is
named as such: :attr:`Comparison.newly_measured`. It still alerts, because
nobody has been told about it yet; it is just not blamed on the instance.

The file is written atomically, because a monitoring plugin is killed by its
own timeout often enough that a half-written baseline is a question of when,
not if.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .coverage import FAILED, INCONCLUSIVE, PASSED, considered, coverage_of
from .fingerprint import digests as fingerprint_digests
from .fingerprint import drift as configuration_drift
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
    version: str = ""
    update_version: str = ""
    support_days: int | None = None
    #: One digest per configuration group, from the scan's fingerprint. It is
    #: how a run says "the deployment is not the one you stored" when no
    #: finding and no grade moved. Empty for a snapshot written before the
    #: block existed, which is a snapshot that cannot say.
    configuration: dict[str, str] = field(default_factory=dict)
    #: The coverage checks known to be measurable on this host: the ones this
    #: run reached a conclusion on, plus any that were measurable before and
    #: are inconclusive now. The second half is what keeps a lost check
    #: alerting until it is measured again, rather than for one run only.
    #: ``None`` when the scan had no coverage block or the snapshot predates
    #: this field - a snapshot that cannot say, not one that measured nothing.
    measured: tuple[str, ...] | None = None
    #: The checks this run ran and could not decide, with the reason the
    #: scanner recorded.
    inconclusive: dict[str, str] = field(default_factory=dict)
    #: Every hardening and check finding this run *could* have reported, as
    #: finding identifiers, whether it passed, failed or was skipped. It is
    #: what tells "passed last time" from "not checked last time". ``None``
    #: when the scan did not list its checks or the snapshot predates this
    #: field - a snapshot that cannot say, and is then compared as before.
    considered: tuple[str, ...] | None = None

    def as_dict(self) -> dict[str, Any]:
        """Render the snapshot in the shape stored on disk."""
        stored: dict[str, Any] = {
            "rating": self.rating,
            "eol": self.eol,
            "findings": list(self.findings),
            "recordedAt": self.recorded_at,
            "version": self.version,
            "updateVersion": self.update_version,
            "supportDays": self.support_days,
            "configuration": dict(self.configuration),
        }
        if self.measured is not None:
            stored["measured"] = list(self.measured)
            stored["inconclusive"] = dict(self.inconclusive)
        if self.considered is not None:
            stored["considered"] = list(self.considered)
        return stored

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
            version=str(data.get("version", "")),
            update_version=str(data.get("updateVersion", "")),
            support_days=data.get("supportDays") if isinstance(data.get("supportDays"), int) else None,
            configuration={
                str(group): str(value)
                for group, value in (data.get("configuration") or {}).items()
                if isinstance(value, str)
            }
            if isinstance(data.get("configuration"), dict)
            else {},
            measured=tuple(str(item) for item in data["measured"])
            if isinstance(data.get("measured"), list)
            else None,
            inconclusive={
                str(check): str(reason)
                for check, reason in data["inconclusive"].items()
            }
            if isinstance(data.get("inconclusive"), dict)
            else {},
            considered=tuple(str(item) for item in data["considered"])
            if isinstance(data.get("considered"), list)
            else None,
        )


@dataclass(frozen=True)
class Comparison:
    """The difference between a stored snapshot and the current one."""

    previous: Snapshot | None
    current: Snapshot
    new_findings: tuple[str, ...] = ()
    resolved_findings: tuple[str, ...] = ()
    #: The configuration groups whose digest is not the one that was stored.
    #: A report of a change, never a finding: it does not make a run regress
    #: and it never reaches the exit code.
    configuration_drift: tuple[str, ...] = ()
    #: Checks a previous run reached a conclusion on that this run ran and
    #: could not decide, mapped to the reason the scanner gave. Never a
    #: finding and never a change to the rating: it says the evidence behind
    #: an unchanged grade got thinner.
    coverage_lost: dict[str, str] = field(default_factory=dict)
    #: Failing now, and not something the previous run checked at all - a
    #: check added to the scanner since, or one a setting kept it from making.
    #: Kept out of :attr:`new_findings`, which would blame the instance for a
    #: change in what was measured.
    newly_measured: tuple[str, ...] = ()
    #: Failing before, and not something this run checked at all. Kept out of
    #: :attr:`resolved_findings`, because nobody fixed it: it was not looked at.
    no_longer_measured: tuple[str, ...] = ()

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
        instance is unsupported, but it must never make that acceptable. So is
        a finding measured for the first time: it is not the instance's doing,
        but nobody has been told about it yet, and ``--warn-on-new`` must not
        file a failure nobody has seen under "nothing new".
        """
        if self.first_run:
            return True
        return (
            bool(self.new_findings)
            or bool(self.newly_measured)
            or self.rating_worsened
            or self.current.eol
            or bool(self.coverage_lost)
        )

    def coverage_summary(self) -> str:
        """
        One line naming the checks that became inconclusive, or ``""``.

        Kept out of :meth:`summary`, which reports findings: a lost
        measurement is said beside them, never instead of them.
        """
        if not self.coverage_lost:
            return ""
        names = sorted(self.coverage_lost)
        listed = ", ".join(
            f"{name} ({self.coverage_lost[name]})" for name in names[:5]
        )
        more = f" (+{len(names) - 5} more)" if len(names) > 5 else ""
        return (
            f"Coverage regressed ({len(names)}): previously measured, now "
            f"inconclusive: {listed}{more}"
        )

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
        if self.newly_measured:
            listed = ", ".join(self.newly_measured[:5])
            more = (
                f" (+{len(self.newly_measured) - 5} more)"
                if len(self.newly_measured) > 5
                else ""
            )
            return (
                f"Newly measured ({len(self.newly_measured)}): {listed}{more} "
                "- the last run did not check these"
            )
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
        # Said before the "nothing to report" line, because a deployment that
        # changed is the one thing a reader would otherwise not learn from a
        # run where the grade and the findings both stood still.
        if self.configuration_drift:
            listed = ", ".join(self.configuration_drift)
            return (
                f"No new findings{tail}, but the configuration changed "
                f"({listed})"
            )
        if known:
            return f"No new findings{tail} ({known} known issue(s) unchanged)"
        return f"No new findings{tail}"

    def items(self) -> list[dict[str, str]]:
        """Return ordered, machine-readable changes for logs and rich renderers."""
        if self.previous is None:
            return [{"category": "Baseline", "change": "Baseline created"}]
        previous = self.previous
        changes: list[dict[str, str]] = []
        labels = {
            "vuln:": "Vulnerability",
            "hardening:": "Hardening",
            "check:": "Security check",
            "update:": "Update",
        }
        for finding in self.new_findings:
            prefix = next((key for key in labels if finding.startswith(key)), "")
            changes.append(
                {
                    "category": labels.get(prefix, "Finding"),
                    "change": f"+ {finding.removeprefix(prefix)}",
                }
            )
        for finding in self.newly_measured:
            prefix = next((key for key in labels if finding.startswith(key)), "")
            changes.append(
                {
                    "category": labels.get(prefix, "Finding"),
                    "change": f"+ {finding.removeprefix(prefix)} (not checked before)",
                }
            )
        for finding in self.resolved_findings:
            prefix = next((key for key in labels if finding.startswith(key)), "")
            changes.append(
                {
                    "category": labels.get(prefix, "Finding"),
                    "change": f"- {finding.removeprefix(prefix)}",
                }
            )
        for finding in self.no_longer_measured:
            prefix = next((key for key in labels if finding.startswith(key)), "")
            changes.append(
                {
                    "category": labels.get(prefix, "Finding"),
                    "change": f"- {finding.removeprefix(prefix)} (not checked now)",
                }
            )
        if previous.rating != self.current.rating:
            changes.append(
                {
                    "category": "Rating",
                    "change": (
                        f"{_rating_label(previous.rating)} ({previous.rating}) -> "
                        f"{_rating_label(self.current.rating)} ({self.current.rating})"
                    ),
                }
            )
        if previous.eol != self.current.eol:
            changes.append(
                {
                    "category": "Lifecycle",
                    "change": f"EOL: {previous.eol} -> {self.current.eol}",
                }
            )
        if previous.support_days != self.current.support_days:
            changes.append(
                {
                    "category": "Lifecycle",
                    "change": (
                        f"Support days: {_display_days(previous.support_days)} -> "
                        f"{_display_days(self.current.support_days)}"
                    ),
                }
            )
        if previous.version and self.current.version and previous.version != self.current.version:
            changes.append(
                {
                    "category": "Version",
                    "change": f"{previous.version} -> {self.current.version}",
                }
            )
        for check in sorted(self.coverage_lost):
            changes.append(
                {
                    "category": "Coverage",
                    "change": (
                        f"{check}: measured -> inconclusive "
                        f"({self.coverage_lost[check]})"
                    ),
                }
            )
        for group in self.configuration_drift:
            changes.append(
                {
                    "category": "Configuration",
                    "change": f"{group} settings changed",
                }
            )
        if previous.update_version != self.current.update_version:
            changes.append(
                {
                    "category": "Update",
                    "change": (
                        f"Target version: {previous.update_version or 'none'} -> "
                        f"{self.current.update_version or 'none'}"
                    ),
                }
            )
        return changes

    def as_dict(self) -> dict[str, Any]:
        """Return the structured comparison included in webhook payloads."""
        return {
            "first_run": self.first_run,
            "regressed": self.regressed,
            "summary": self.summary(),
            "configuration_drift": list(self.configuration_drift),
            "coverage_regressed": dict(sorted(self.coverage_lost.items())),
            "newly_measured": list(self.newly_measured),
            "no_longer_measured": list(self.no_longer_measured),
            "changes": self.items(),
        }

    def render(self, format: str = "text") -> str:
        """Render itemized changes as text, Markdown, or Slack Block Kit JSON."""
        changes = self.items()
        if format == "text":
            return "\n".join(f"{item['category']}: {item['change']}" for item in changes)
        if format == "markdown":
            rows = ["### OpenCloud baseline diff", "", "| Category | Change |", "|:--|:--|"]
            rows.extend(
                f"| {item['category']} | {_markdown_cell(item['change'])} |"
                for item in changes
            )
            return "\n".join(rows)
        if format in {"slack", "json"}:
            return json.dumps(self.slack_blocks(), sort_keys=True)
        raise ValueError(f"Unknown diff format: {format}")

    def slack_blocks(self) -> dict[str, Any]:
        """Return a Slack Block Kit-compatible structured baseline diff."""
        banner = "warning" if self.regressed else "good"
        lines = "\n".join(
            f"• *{item['category']}*: {item['change']}" for item in self.items()
        )
        return {
            "attachments": [{"color": banner}],
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "OpenCloud baseline diff"},
                },
                {"type": "section", "text": {"type": "mrkdwn", "text": lines}},
            ],
        }


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
        # Only when both sides say what they considered, and only for a
        # finding the *other* side does list: a finding neither side lists as
        # a check (an advisory, a pending update, a check the coverage block
        # does not cover) keeps today's arithmetic, so a gap in the record
        # can never turn a real regression into a softer word.
        newly: set[str] = set()
        dropped: set[str] = set()
        if previous.considered is not None and current.considered is not None:
            known_before, known_now = set(previous.considered), set(current.considered)
            newly = {
                finding
                for finding in now - before
                if finding not in known_before and finding in known_now
            }
            dropped = {
                finding
                for finding in before - now
                if finding not in known_now and finding in known_before
            }
        lost: dict[str, str] = {}
        if previous.measured is not None and current.measured is not None:
            lost = {
                check: reason
                for check, reason in current.inconclusive.items()
                if check in previous.measured
            }
            if lost:
                # Carry the lost checks forward as measurable, so the next
                # run still compares against what this host used to show
                # rather than against the gap - one missed interval would
                # otherwise be enough to make the loss the new normal.
                current = replace(
                    current,
                    measured=tuple(sorted({*current.measured, *lost})),
                )
        return Comparison(
            previous=previous,
            current=current,
            new_findings=tuple(sorted(now - before - newly)),
            resolved_findings=tuple(sorted(before - now - dropped)),
            newly_measured=tuple(sorted(newly)),
            no_longer_measured=tuple(sorted(dropped)),
            configuration_drift=configuration_drift(
                previous.configuration, current.configuration
            ),
            coverage_lost=lost,
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
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _rating_label(rating: int) -> str:
    """Name a rating without importing plugin-layer presentation code."""
    return {5: "A+", 4: "A", 3: "C", 2: "D", 1: "E", 0: "F"}.get(rating, "Unknown")


def _display_days(days: int | None) -> str:
    """Present unknown lifecycle horizons distinctly from zero days."""
    return "unknown" if days is None else f"{days} days"


def _markdown_cell(value: str) -> str:
    """Keep an itemized change inside its Markdown table cell."""
    return value.replace("|", "\\|")


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


def _coverage_states(
    response: dict[str, Any],
) -> tuple[tuple[str, ...] | None, dict[str, str]]:
    """
    The checks a result measured, and the ones it could not decide.

    ``(None, {})`` for a document without a coverage block: nothing about
    it says which checks were measurable, so nothing can be said to be lost.
    """
    coverage = coverage_of(response)
    if coverage is None:
        return None, {}
    measured: set[str] = set()
    inconclusive: dict[str, str] = {}
    for entry in coverage["checks"]:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        check, state = str(entry["id"]), entry.get("state")
        if state in {PASSED, FAILED}:
            measured.add(check)
        elif state == INCONCLUSIVE:
            inconclusive[check] = str(entry.get("reason") or "unknown")
    return tuple(sorted(measured)), inconclusive


#: Which finding prefix a coverage group's checks are reported under - the
#: same mapping :func:`_hardening_ids` and :func:`_extra_check_ids` apply.
_FINDING_PREFIX_BY_GROUP: dict[str, str] = {
    "hardening": "hardening:",
    "header": "hardening:",
    "extraCheck": "check:",
}


def _considered_findings(response: dict[str, Any]) -> tuple[str, ...] | None:
    """Every finding identifier the result could have reported, or ``None``."""
    checks = considered(response)
    if checks is None:
        return None
    return tuple(
        sorted(
            f"{_FINDING_PREFIX_BY_GROUP[group]}{check}"
            for check, group in checks.items()
            if group in _FINDING_PREFIX_BY_GROUP
        )
    )


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
    update_version = ""
    if isinstance(update, dict) and update.get("available"):
        update_version = str(update.get("availableVersion") or "unknown")
        findings.append(f"update:{update_version}")
    lifecycle = response.get("lifecycle")
    support_days = (
        lifecycle.get("daysRemaining")
        if isinstance(lifecycle, dict) and isinstance(lifecycle.get("daysRemaining"), int)
        else None
    )
    try:
        rating = int(response.get("rating", -1))
    except (TypeError, ValueError):
        rating = -1
    measured, inconclusive = _coverage_states(response)
    return Snapshot(
        rating=rating,
        eol=bool(response.get("EOL", False)),
        findings=tuple(findings),
        recorded_at=_now(),
        version=str(response.get("version") or ""),
        update_version=update_version,
        support_days=support_days,
        configuration=fingerprint_digests(response),
        measured=measured,
        inconclusive=inconclusive,
        considered=_considered_findings(response),
    )
