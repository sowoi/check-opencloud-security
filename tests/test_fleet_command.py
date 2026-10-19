"""
`check-opencloud-scanner fleet`: a dashboard from reports already on disk.

The documents are real scans of the fake instance, adjusted only where a test
needs one fact to differ - an end-of-life version, a waiver deadline, a second
host - so a change to what the scanner writes moves these tests with it.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from opencloud_local_scan.cli import main
from opencloud_local_scan.fleet import (
    headline,
    host_key,
    load_reports,
    render_html,
    render_text,
    summarise,
)
from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.scanner import ScannerSettings, scan
from opencloud_local_scan.versions import load_release_schedule
from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour

SETTINGS = ScannerSettings(
    scheme="http", timeout=3, check_debug_ports=False, include_bundled_db=True
)
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def scanned() -> dict:
    """An instance publishing its .env, so every report has a shared finding."""
    with FakeOpenCloud(InstanceBehaviour(exposed_paths={"/.env"})) as instance:
        return scan(
            instance.host, settings=SETTINGS, release_settings=ReleaseSettings(mode="off")
        )


def _as(document: dict, host: str, *, at: datetime = NOW, **changes) -> dict:
    """The same scan, as if it had been of ``host`` at ``at``."""
    copied = copy.deepcopy(document)
    copied["domain"] = host
    copied["url"] = f"https://{host}/status.php"
    copied["scannedAt"] = {
        "date": at.strftime("%Y-%m-%d %H:%M:%S.%f"),
        "timezone_type": 3,
        "timezone": "UTC",
    }
    copied.update(changes)
    return copied


def _write(directory: Path, name: str, payload) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _summary(tmp_path: Path, *documents, **options) -> dict:
    for index, document in enumerate(documents):
        _write(tmp_path, f"report-{index}.json", document)
    reports, skipped = load_reports([tmp_path])
    options.setdefault("schedule", load_release_schedule())
    return summarise(reports, skipped=skipped, now=NOW, **options)


def _waiver(pattern: str, expires: datetime | None, matched: list[str], reason: str = "") -> dict:
    return {
        "pattern": pattern,
        "reason": reason,
        "expiresAt": expires.isoformat() if expires else None,
        "state": "active",
        "matched": matched,
    }


def test_an_end_of_life_release_is_listed_and_a_supported_one_is_not(tmp_path, scanned):
    """The first question of a fleet review: which instances receive no fixes."""
    old = _as(
        scanned,
        "old.example.com",
        version="2.0.0",
        EOL=True,
        lifecycle={**scanned["lifecycle"], "state": "endOfLife", "line": "2.0"},
    )
    summary = _summary(tmp_path, old, _as(scanned, "current.example.com"))

    unsupported = [item["host"] for item in summary["unsupported"]]
    assert unsupported == ["old.example.com"]


def test_a_release_that_closed_after_the_scan_is_unsupported_now(tmp_path, scanned):
    """
    A report is evidence about the day it was written.

    It said "supported" then; the version it recorded is placed in today's
    schedule again, and a line that has closed since is flagged as such -
    otherwise an archive of month-old reports would hide every lapse.
    """
    lapsed = _as(
        scanned,
        "lapsed.example.com",
        version="2.0.0",
        EOL=False,
        lifecycle={**scanned["lifecycle"], "state": "supported", "line": "2.0"},
    )
    summary = _summary(tmp_path, lapsed)

    (entry,) = summary["unsupported"]
    assert entry["host"] == "lapsed.example.com"
    assert entry["changedSinceScan"] is True

    without_schedule = summarise(load_reports([tmp_path])[0], now=NOW, schedule=None)
    assert without_schedule["unsupported"] == [], (
        "with no schedule to consult, the report's own verdict must stand"
    )


def test_a_waiver_ending_inside_the_window_is_listed_and_a_later_one_is_not(
    tmp_path, scanned
):
    """The window is the lead time; a deadline beyond it is not news yet."""
    soon = _as(
        scanned,
        "soon.example.com",
        waivers=[_waiver("exposed:*", NOW + timedelta(days=5), ["exposed:/.env"], "OPS-1")],
    )
    later = _as(
        scanned,
        "later.example.com",
        waivers=[_waiver("exposed:*", NOW + timedelta(days=90), ["exposed:/.env"])],
    )
    summary = _summary(tmp_path, soon, later, window_days=30)

    (deadline,) = summary["waiverDeadlines"]
    assert deadline["host"] == "soon.example.com"
    assert deadline["daysLeft"] == 5
    assert deadline["checks"] == ["exposed:/.env"]
    assert deadline["waivers"] == [{"pattern": "exposed:*", "reason": "OPS-1"}]


def test_a_waiver_that_ran_out_since_the_scan_is_shown_as_expired(tmp_path, scanned):
    """The report said active; measured against now, the check alerts again."""
    lapsed = _as(
        scanned,
        "lapsed.example.com",
        at=NOW - timedelta(days=10),
        waivers=[_waiver("exposed:*", NOW - timedelta(days=2), ["exposed:/.env"])],
    )
    summary = _summary(tmp_path, lapsed)

    (deadline,) = summary["waiverDeadlines"]
    assert deadline["expired"] is True
    assert deadline["daysLeft"] < 0


def test_a_deadline_that_changes_nothing_is_not_a_deadline(tmp_path, scanned):
    """
    Two deadlines no alert follows: one under a permanent waiver, and one on a
    flag OpenCloud hardcodes. Listing either would teach the reader to skip
    the section - the same rule the plugin's --waiver-warning follows.
    """
    covered = _as(
        scanned,
        "covered.example.com",
        waivers=[
            _waiver("exposed:*", NOW + timedelta(days=3), ["exposed:/.env"]),
            _waiver("exposed:/.env", None, ["exposed:/.env"]),
            _waiver(
                "publicLinkExpirationEnforced",
                NOW + timedelta(days=3),
                ["publicLinkExpirationEnforced"],
            ),
        ],
    )
    assert _summary(tmp_path, covered)["waiverDeadlines"] == []


def test_a_finding_shared_by_several_hosts_is_counted_once_per_host(tmp_path, scanned):
    """One broken template shows as one line with a count, not N tickets."""
    summary = _summary(
        tmp_path,
        _as(scanned, "one.example.com"),
        _as(scanned, "two.example.com"),
        _as(scanned, "three.example.com"),
    )

    common = {item["id"]: item for item in summary["commonFindings"]}
    assert common["exposed:/.env"]["count"] == 3
    assert common["exposed:/.env"]["severity"] == "critical"
    # Headers no OpenCloud sends fail on every instance and are never alerted
    # on (ADR 0028); a "common finding" nobody can fix is noise.
    assert "Permissions-Policy" not in common
    assert "publicLinkExpirationEnforced" not in common


def test_only_the_newest_report_of_a_host_counts(tmp_path, scanned):
    """An archive holds every day's report; yesterday's is not a second host."""
    fixed = copy.deepcopy(scanned)
    fixed["extraChecks"] = [dict(check, passed=True) for check in scanned["extraChecks"]]
    summary = _summary(
        tmp_path,
        _as(scanned, "cloud.example.com", at=NOW - timedelta(days=2)),
        _as(fixed, "cloud.example.com", at=NOW - timedelta(days=1)),
    )

    assert summary["reports"] == {"read": 2, "hosts": 1, "superseded": 1, "skipped": []}
    assert "exposed:/.env" not in {item["id"] for item in summary["commonFindings"]}


def test_a_failed_scan_newer_than_a_clean_one_is_the_state_of_the_host(
    tmp_path, scanned
):
    """Last week's clean report says nothing about an instance nobody can reach."""
    clean = _as(scanned, "cloud.example.com", at=NOW - timedelta(days=3))
    summary = _summary(tmp_path, clean)
    assert summary["coverage"]["failedScans"] == []

    _write(
        tmp_path,
        "later/failed.json",
        [{"host": "https://cloud.example.com/", "error": "status.php is unreachable"}],
    )
    summary = _summary(tmp_path)
    (failed,) = summary["coverage"]["failedScans"]
    assert failed["host"] == "cloud.example.com"


def test_an_expected_host_without_a_report_is_missing_coverage(tmp_path, scanned):
    """The instance nobody scans never appears in any report, so it has to be asked about."""
    summary = _summary(
        tmp_path,
        _as(scanned, "seen.example.com"),
        expected=["https://seen.example.com/", "unseen.example.com"],
    )
    assert summary["coverage"]["missingHosts"] == ["unseen.example.com"]


def test_a_stale_report_is_missing_coverage_and_a_fresh_one_is_not(tmp_path, scanned):
    """A daily scan that silently stopped is exactly what this has to notice."""
    summary = _summary(
        tmp_path,
        _as(scanned, "stale.example.com", at=NOW - timedelta(days=12)),
        _as(scanned, "fresh.example.com", at=NOW - timedelta(days=1)),
        stale_after_days=7,
    )
    assert [item["host"] for item in summary["coverage"]["staleReports"]] == [
        "stale.example.com"
    ]


def test_a_host_that_is_both_failed_and_stale_is_not_covered_once(tmp_path):
    """The headline counts instances nobody knows about, not the rows naming them."""
    path = _write(
        tmp_path, "failed.json", [{"host": "gone.example.com", "error": "unreachable"}]
    )
    # A failed scan records no time of its own; the file's age is the report's.
    old = (NOW - timedelta(days=12)).timestamp()
    os.utime(path, (old, old))
    reports, skipped = load_reports([tmp_path])
    summary = summarise(reports, skipped=skipped, now=NOW, schedule=None)

    assert [item["host"] for item in summary["coverage"]["failedScans"]] == ["gone.example.com"]
    assert [item["host"] for item in summary["coverage"]["staleReports"]] == ["gone.example.com"]
    assert headline(summary)["notCovered"] == 1


def test_waiver_deadlines_are_ordered_by_moment_not_by_their_spelling(tmp_path, scanned):
    """
    A waiver keeps the offset it was written with. 10:00 in Berlin is before
    09:00 UTC on the same day, although its ISO string sorts after it.
    """
    berlin = timezone(timedelta(hours=2))
    first = datetime(2026, 9, 30, 10, 0, tzinfo=berlin)
    second = datetime(2026, 9, 30, 9, 0, tzinfo=UTC)
    summary = _summary(
        tmp_path,
        _as(scanned, "a.example.com", waivers=[_waiver("exposed:*", second, ["exposed:/.env"])]),
        _as(scanned, "b.example.com", waivers=[_waiver("exposed:*", first, ["exposed:/.env"])]),
    )

    assert [item["host"] for item in summary["waiverDeadlines"]] == [
        "b.example.com",
        "a.example.com",
    ]


def test_a_check_that_could_not_apply_is_not_a_coverage_gap(tmp_path, scanned):
    """An instance without IPv6 was not "not checked" over IPv6 in any useful sense."""
    summary = _summary(tmp_path, _as(scanned, "cloud.example.com"))
    gaps = {item["id"]: item for item in summary["coverage"]["gaps"]}

    reasons = {
        entry["id"]: entry["reason"]
        for entry in scanned["coverage"]["checks"]
        if entry["state"] in ("not_checked", "inconclusive")
    }
    assert any(reason == "not_applicable" for reason in reasons.values())
    for identifier, reason in reasons.items():
        assert (identifier in gaps) is (reason != "not_applicable"), identifier


def test_host_spellings_of_one_instance_agree_and_a_port_does_not():
    """Matching reports to an inventory depends on this."""
    assert host_key("https://Cloud.Example.com/") == "cloud.example.com"
    assert host_key("cloud.example.com:443") == "cloud.example.com"
    assert host_key("cloud.example.com:9200") == "cloud.example.com:9200"
    assert host_key("http://[2001:db8::1]:8080") == "[2001:db8::1]:8080"


def test_a_value_chosen_by_the_scanned_host_cannot_inject_markup_or_escapes(
    tmp_path, scanned
):
    """A version string is somebody else's input: escaped in HTML, stripped in a terminal."""
    hostile = _as(scanned, "cloud.example.com", version="<script>x</script>\x1b[2J")
    summary = _summary(tmp_path, hostile)

    page = render_html(summary)
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "unsafe-inline" not in page
    assert "default-src &#x27;none&#x27;" in page
    assert "\x1b" not in render_text(summary)


def test_the_command_reads_a_directory_tree_and_names_what_it_skipped(
    tmp_path, capsys, scanned
):
    """Archives accumulate other files; one of them must not fail the summary."""
    _write(tmp_path, "2026-09-23/cloud.json", _as(scanned, "cloud.example.com"))
    _write(tmp_path, "baseline.json", {"hosts": {}})

    assert main(["fleet", str(tmp_path), "--format", "json"]) == 0
    summary = json.loads(capsys.readouterr().out)

    assert summary["reports"]["hosts"] == 1
    assert [Path(item["path"]).name for item in summary["reports"]["skipped"]] == [
        "baseline.json"
    ]


@pytest.mark.parametrize("output_format", ["text", "markdown", "html"])
def test_every_readable_format_carries_every_section(
    tmp_path, capsys, scanned, output_format
):
    """A section missing from one format would be a question that format cannot answer."""
    _write(tmp_path, "cloud.json", _as(scanned, "cloud.example.com"))

    assert main(["fleet", str(tmp_path), "--format", output_format]) == 0
    printed = capsys.readouterr().out
    for section in (
        "Unsupported releases",
        "Waiver deadlines",
        "Common findings",
        "Missing coverage",
        "Checks not evaluated",
    ):
        assert section in printed, section


def test_nothing_to_summarise_is_an_error_not_an_empty_dashboard(tmp_path, capsys):
    """An empty page would read as a fleet with nothing wrong."""
    assert main(["fleet", str(tmp_path)]) == 2
    assert capsys.readouterr().out == ""
