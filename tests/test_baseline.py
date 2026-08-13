"""Tests for --baseline and --warn-on-new: reporting only what changed."""

from __future__ import annotations

import json

import pytest

import check_opencloud_security as check
from opencloud_local_scan.baseline import (
    Snapshot,
    load_baseline,
    snapshot_of,
)
from opencloud_local_scan.scanner import ScannerSettings
from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour

SETTINGS = ScannerSettings(
    scheme="http", timeout=3, check_debug_ports=False, include_bundled_db=True
)


@pytest.fixture
def result() -> dict:
    """
    A real result document, so the tests cannot drift from the scanner.

    Basic auth is switched on and a header removed, because the fake instance
    is otherwise fully hardened and a baseline with nothing in it proves
    nothing.
    """
    from opencloud_local_scan import scan
    from opencloud_local_scan.releases import ReleaseSettings

    behaviour = InstanceBehaviour(basic_auth=True)
    behaviour.headers.pop("X-Content-Type-Options")
    with FakeOpenCloud(behaviour) as instance:
        return scan(
            instance.host, settings=SETTINGS, release_settings=ReleaseSettings(mode="off")
        )


def test_a_real_scan_produces_findings_a_baseline_can_compare(result):
    """A snapshot of a stock instance must not be empty, or nothing can ever be 'new'."""
    snapshot = snapshot_of(result)

    assert snapshot.findings, "a default OpenCloud has missing hardening to record"
    assert snapshot.rating == result["rating"]
    assert all(":" in finding for finding in snapshot.findings)


def test_hardening_findings_follow_the_alert_line():
    """A measure nobody can change must never be recorded as a new finding."""
    # publicLinkExpirationEnforced is hardcoded by OpenCloud, so every instance
    # fails it forever; basicAuthDisabled is a real setting.
    response = {
        "rating": 3,
        "hardenings": {"publicLinkExpirationEnforced": False, "basicAuthDisabled": False},
    }

    snapshot = snapshot_of(response)

    assert "hardening:basicAuthDisabled" in snapshot.findings
    assert "hardening:publicLinkExpirationEnforced" not in snapshot.findings


def test_a_waived_finding_is_not_recorded(result):
    """Accepting a measure has to silence it here too, or waivers leak back in."""
    missing = [
        name
        for name, ok in result["hardenings"].items()
        if not ok and check.is_actionable(name)
    ]
    assert missing, "the fixture must produce something worth waiving"
    waivable = missing[0]

    with_waiver = snapshot_of(result, waived=[waivable])
    without = snapshot_of(result)

    assert f"hardening:{waivable}" in without.findings
    assert f"hardening:{waivable}" not in with_waiver.findings


def test_the_first_run_counts_as_a_regression(tmp_path):
    """With nothing to compare against, staying quiet would hide a real problem."""
    store = load_baseline(tmp_path / "baseline.json")
    comparison = store.compare("opencloud.example.com", Snapshot(rating=5, eol=False))

    assert comparison.first_run
    assert comparison.regressed
    assert "becomes the baseline" in comparison.summary()


def test_an_unchanged_picture_is_not_a_regression(tmp_path):
    """The whole point: a known issue must stop alerting until it changes."""
    path = tmp_path / "baseline.json"
    store = load_baseline(path)
    snapshot = Snapshot(rating=3, eol=False, findings=("hardening:basicAuthDisabled",))
    store.record("opencloud.example.com", snapshot)
    store.save()

    again = load_baseline(path)
    comparison = again.compare("opencloud.example.com", snapshot)

    assert not comparison.first_run
    assert not comparison.regressed
    assert "No new findings" in comparison.summary()


def test_a_new_finding_is_a_regression(tmp_path):
    """A second problem appearing next to a known one must still alert."""
    store = load_baseline(tmp_path / "baseline.json")
    store.record(
        "opencloud.example.com",
        Snapshot(rating=3, eol=False, findings=("hardening:basicAuthDisabled",)),
    )

    comparison = store.compare(
        "opencloud.example.com",
        Snapshot(
            rating=3,
            eol=False,
            findings=("hardening:basicAuthDisabled", "vuln:CVE-2025-0001"),
        ),
    )

    assert comparison.regressed
    assert comparison.new_findings == ("vuln:CVE-2025-0001",)
    assert "New since last run (1)" in comparison.summary()


def test_a_resolved_finding_is_not_a_regression(tmp_path):
    """Fixing something must not look like a change for the worse."""
    store = load_baseline(tmp_path / "baseline.json")
    store.record(
        "opencloud.example.com",
        Snapshot(rating=3, eol=False, findings=("a:one", "b:two")),
    )

    comparison = store.compare(
        "opencloud.example.com", Snapshot(rating=3, eol=False, findings=("a:one",))
    )

    assert not comparison.regressed
    assert comparison.resolved_findings == ("b:two",)


def test_itemized_diffs_categorize_vulnerabilities_hardening_and_versions(tmp_path):
    """Reports need the exact security change, not merely a changed/not-changed flag."""
    store = load_baseline(tmp_path / "baseline.json")
    store.record(
        "opencloud.example.com",
        Snapshot(
            rating=5,
            eol=False,
            findings=("hardening:basicAuthDisabled",),
            version="7.2.0",
            update_version="7.3.0",
            support_days=45,
        ),
    )

    comparison = store.compare(
        "opencloud.example.com",
        Snapshot(
            rating=3,
            eol=True,
            findings=("vuln:CVE-2026-0001",),
            version="7.3.0",
            update_version="7.4.0",
            support_days=5,
        ),
    )

    changes = comparison.items()

    assert {"category": "Vulnerability", "change": "+ CVE-2026-0001"} in changes
    assert {"category": "Hardening", "change": "- basicAuthDisabled"} in changes
    assert {"category": "Rating", "change": "A+ (5) -> C (3)"} in changes
    assert {"category": "Lifecycle", "change": "EOL: False -> True"} in changes
    assert {"category": "Lifecycle", "change": "Support days: 45 days -> 5 days"} in changes
    assert {"category": "Version", "change": "7.2.0 -> 7.3.0"} in changes
    assert {"category": "Update", "change": "Target version: 7.3.0 -> 7.4.0"} in changes


def test_markdown_diff_is_a_table_with_the_itemized_changes(tmp_path):
    """CI summaries need Markdown that renders without a custom parser."""
    store = load_baseline(tmp_path / "baseline.json")
    store.record("opencloud.example.com", Snapshot(rating=5, eol=False))
    comparison = store.compare("opencloud.example.com", Snapshot(rating=3, eol=False))

    markdown = comparison.render("markdown")

    assert markdown.startswith("### OpenCloud baseline diff\n\n| Category | Change |")
    assert "| Rating | A+ (5) -> C (3) |" in markdown


def test_slack_diff_is_valid_block_kit_json(tmp_path):
    """Webhook receivers can use the diff without scraping human-readable output."""
    store = load_baseline(tmp_path / "baseline.json")
    store.record("opencloud.example.com", Snapshot(rating=5, eol=False))
    comparison = store.compare("opencloud.example.com", Snapshot(rating=3, eol=False))

    slack = json.loads(comparison.render("slack"))

    assert slack["attachments"][0]["color"] == "warning"
    assert slack["blocks"][0] == {
        "type": "header",
        "text": {"type": "plain_text", "text": "OpenCloud baseline diff"},
    }
    assert slack["blocks"][1]["type"] == "section"
    assert slack["blocks"][1]["text"]["type"] == "mrkdwn"


def test_slack_format_adds_structured_diff_to_the_webhook_payload(tmp_path):
    """Slack receivers need blocks as well as the portable structured comparison."""
    store = load_baseline(tmp_path / "baseline.json")
    store.record("opencloud.example.com", Snapshot(rating=5, eol=False))
    comparison = store.compare("opencloud.example.com", Snapshot(rating=3, eol=False))
    context = check.ScanContext(host="opencloud.example.com", diff_format="slack")

    payload = check._build_webhook_payload(
        context,
        scan_result=check.ScanResult(response={}, uuid="local-opencloud.example.com"),
        response_scan={},
        message="WARNING: rating dropped",
        exit_code=check.NagiosExitCode.WARNING,
        rating=3,
        rate="C",
        vulnerabilities=[],
        missing_hardenings=[],
        duration_seconds=1,
        baseline_diff=comparison,
    )

    assert payload["baseline_diff"]["changes"] == comparison.items()
    assert payload["blocks"][0]["type"] == "header"
    assert payload["attachments"][0]["color"] == "warning"


def test_a_worse_rating_alone_is_a_regression(tmp_path):
    """A new advisory can lower the rating without adding a finding of its own."""
    store = load_baseline(tmp_path / "baseline.json")
    store.record("opencloud.example.com", Snapshot(rating=4, eol=False))

    worse = store.compare("opencloud.example.com", Snapshot(rating=2, eol=False))
    better = store.compare("opencloud.example.com", Snapshot(rating=5, eol=False))

    assert worse.regressed and worse.rating_worsened
    assert not better.regressed and not better.rating_worsened


def test_end_of_life_keeps_alerting_however_old_the_news_is(tmp_path):
    """A release that gets no security fixes gets worse every day it stays up."""
    store = load_baseline(tmp_path / "baseline.json")
    unchanged = Snapshot(rating=0, eol=True, findings=("vuln:CVE-2025-0001",))
    store.record("opencloud.example.com", unchanged)

    comparison = store.compare("opencloud.example.com", unchanged)

    assert not comparison.new_findings
    assert not comparison.rating_worsened
    assert comparison.regressed, "end of life must survive an identical baseline"


def test_each_host_is_remembered_separately(tmp_path):
    """One file serves a whole --host list, so hosts must not share a snapshot."""
    path = tmp_path / "baseline.json"
    store = load_baseline(path)
    store.record("one.example.com", Snapshot(rating=5, eol=False, findings=("a:one",)))
    store.record("two.example.com", Snapshot(rating=2, eol=False, findings=("b:two",)))
    store.save()

    reloaded = load_baseline(path)

    assert reloaded.snapshot("one.example.com").findings == ("a:one",)
    assert reloaded.snapshot("two.example.com").rating == 2
    assert reloaded.compare(
        "two.example.com", Snapshot(rating=2, eol=False, findings=("a:one",))
    ).regressed


def test_a_corrupt_baseline_degrades_to_no_baseline(tmp_path):
    """A truncated file must not stop the check from running at all."""
    path = tmp_path / "baseline.json"
    path.write_text('{"version": 1, "hosts": {"a": ', encoding="utf-8")

    store = load_baseline(path)

    assert store.hosts == {}
    assert store.compare("a", Snapshot(rating=5, eol=False)).first_run


def test_a_baseline_from_a_future_format_is_ignored_not_misread(tmp_path):
    """Reading unknown fields as findings would invent regressions out of nothing."""
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"version": 99, "hosts": {"a": {}}}), encoding="utf-8")

    assert load_baseline(path).hosts == {}


def test_the_baseline_is_written_atomically_and_privately(tmp_path):
    """A plugin killed by its own timeout must not leave half a file behind."""
    path = tmp_path / "sub" / "baseline.json"
    store = load_baseline(path)
    store.record("opencloud.example.com", Snapshot(rating=5, eol=False))
    store.save()

    assert json.loads(path.read_text())["hosts"]["opencloud.example.com"]["rating"] == 5
    assert not list(path.parent.glob("*.tmp")), "no temporary file may survive"
    assert path.stat().st_mode & 0o777 == 0o600
