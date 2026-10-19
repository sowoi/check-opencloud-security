"""
A waiver with a deadline, and what happens when the deadline passes.

The failure this prevents is quiet and slow: somebody accepts a failing check
during an incident, the alert stops, and a year later the check is still
failing, the suppression is still in the configuration, and the reason is in
a ticket nobody can find. A deadline makes the acceptance expire by itself; a
required reason makes it explicable when somebody does find it.

Every expiry here is decided against a clock the test supplies, so "before",
"at" and "after" are exact rather than a race with the wall clock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from opencloud_local_scan.config import ConfigurationError, load_configuration
from opencloud_local_scan.factory import scanner_settings_from_config
from opencloud_local_scan.scanner import (
    Finding,
    ScannerSettings,
    _apply_waivers,
    _compute_rating,
)
from opencloud_local_scan.waivers import (
    Waiver,
    WaiverError,
    parse_waiver,
    parse_waivers,
    resolve,
)
from tests.test_e2e_cli import UNKNOWN, run_plugin

DEADLINE = datetime(2026, 12, 31, 0, 0, tzinfo=UTC)
RECORD = f"debugPort:9205|{DEADLINE.isoformat()}|Firewall change scheduled"


def _waive(settings: ScannerSettings, now: datetime, passed: bool = False):
    """Apply the settings' waivers to one failing check at ``now``."""
    findings = [Finding("debugPort:9205", "high", passed, "metrics are readable")]
    ignored, records = _apply_waivers(
        settings, findings, {}, {}, {"enforced": True}, now
    )
    return findings[0], ignored, records


# ------------------------------------------------------------ parsing


def test_a_bare_pattern_is_still_a_permanent_waiver():
    """Every configuration written before this feature means what it meant."""
    waiver = parse_waiver("debugPort:*")

    assert waiver == Waiver("debugPort:*")
    assert waiver.expires_at is None
    assert waiver.temporary is False
    assert waiver.active_at(datetime(2099, 1, 1, tzinfo=UTC)) is True


def test_a_complete_record_carries_its_reason_and_deadline():
    waiver = parse_waiver(RECORD)

    assert waiver.pattern == "debugPort:9205"
    assert waiver.expires_at == DEADLINE
    assert waiver.reason == "Firewall change scheduled"
    assert waiver.temporary is True


@pytest.mark.parametrize(
    ("record", "because"),
    [
        ("debugPort:9205|2026-12-31T00:00:00Z", "two fields is neither form"),
        ("debugPort:9205||A reason", "no expiry"),
        ("debugPort:9205|2026-12-31T00:00:00Z|", "no reason"),
        ("|2026-12-31T00:00:00Z|A reason", "no pattern"),
        ("debugPort:9205|not a date|A reason", "unparsable expiry"),
        ("debugPort:9205|2026-12-31|A reason", "a date with no timezone"),
        ("debugPort:9205|2026-12-31T00:00:00|A reason", "no timezone"),
    ],
)
def test_an_incomplete_record_is_refused_rather_than_made_permanent(
    record: str, because: str
):
    """
    Failing open is how a typo becomes a suppression nobody chose.

    A record that cannot be understood must not quietly become the one form
    that never expires.
    """
    with pytest.raises(WaiverError):
        parse_waiver(record)


def test_an_expiry_may_be_written_in_any_timezone():
    """The same moment, however the operator's tooling writes it."""
    utc = parse_waiver("a|2026-12-31T00:00:00Z|reason").expires_at
    offset = parse_waiver("a|2026-12-31T02:00:00+02:00|reason").expires_at
    behind = parse_waiver("a|2026-12-30T19:00:00-05:00|reason").expires_at

    assert utc == offset == behind


# ------------------------------------------------------------- expiry


def test_a_waiver_holds_before_its_deadline():
    waiver = parse_waiver(RECORD)

    assert waiver.active_at(DEADLINE - timedelta(seconds=1)) is True


def test_a_waiver_is_over_at_the_stroke_of_its_deadline():
    """
    The documented boundary: `now >= expires_at` is expired.

    Somebody who writes 2026-12-31T00:00:00Z means the waiver covers the
    year, not the first instant after it.
    """
    waiver = parse_waiver(RECORD)

    assert waiver.active_at(DEADLINE) is False
    assert waiver.active_at(DEADLINE + timedelta(seconds=1)) is False


def test_an_expired_waiver_stops_suppressing_the_alert():
    """The point of the deadline, end to end, with no configuration change."""
    settings = ScannerSettings(waivers=parse_waivers([RECORD]))

    before, ignored_before, _ = _waive(settings, DEADLINE - timedelta(days=1))
    after, ignored_after, _ = _waive(settings, DEADLINE + timedelta(days=1))

    assert before.ignored is True and ignored_before == ["debugPort:9205"]
    assert after.ignored is False and ignored_after == []


def test_an_expired_waiver_caps_the_rating_again():
    """A suppression that has run out has to reach the grade, or it did not run out."""
    settings = ScannerSettings(waivers=parse_waivers([RECORD]))

    ratings = []
    for now in (DEADLINE - timedelta(days=1), DEADLINE + timedelta(days=1)):
        findings = [Finding("debugPort:9205", "high", False, "metrics are readable")]
        _apply_waivers(settings, findings, {}, {}, {"enforced": True}, now)
        ratings.append(
            _compute_rating(
                eol=False,
                vulnerabilities=[],
                update_available=False,
                behind_line=False,
                findings=findings,
                settings=settings,
            ).rating
        )

    assert ratings[0] > ratings[1]


# --------------------------------------------------------- overlapping


def test_any_active_record_is_enough_to_suppress():
    """Waivers are permissions, and one permission is a permission."""
    waivers = parse_waivers([f"debugPort:9205|{DEADLINE.isoformat()}|Expired", "debugPort:*"])

    decision = resolve(waivers, "debugPort:9205", DEADLINE + timedelta(days=1))

    assert decision.waived is True
    assert len(decision.applicable) == 2


def test_a_wildcard_cannot_silently_mask_an_expiry():
    """
    The report names every applicable record, not only the one that matched.

    Otherwise a permanent `*` in a configuration file would carry every
    expired waiver underneath it and the report would call the suppression
    deliberate when nobody had re-decided it.
    """
    waivers = parse_waivers([f"debugPort:9205|{DEADLINE.isoformat()}|Expired", "debugPort:*"])

    decision = resolve(waivers, "debugPort:9205", DEADLINE + timedelta(days=1))

    assert decision.only_covered_by_a_wildcard is True
    assert [record.reason for record in decision.expired] == ["Expired"]


def test_a_record_still_in_date_is_not_reported_as_covered_by_something_else():
    waivers = parse_waivers([RECORD, "debugPort:*"])

    decision = resolve(waivers, "debugPort:9205", DEADLINE - timedelta(days=1))

    assert decision.waived is True
    assert decision.expired == ()
    assert decision.only_covered_by_a_wildcard is False


# ------------------------------------------------------- the document


def test_the_result_records_every_waiver_with_what_it_matched():
    """A pattern that matches nothing is how a waiver outlives its finding."""
    stale = f"somethingThatDoesNotExist|{DEADLINE.isoformat()}|Stale"
    settings = ScannerSettings(waivers=parse_waivers([RECORD, stale]))

    _, _, records = _waive(settings, DEADLINE - timedelta(days=1))

    by_pattern = {record["pattern"]: record for record in records}
    assert by_pattern["debugPort:9205"]["matched"] == ["debugPort:9205"]
    assert by_pattern["debugPort:9205"]["state"] == "active"
    assert by_pattern["debugPort:9205"]["reason"] == "Firewall change scheduled"
    assert by_pattern["somethingThatDoesNotExist"]["matched"] == []


def test_an_expired_record_is_still_in_the_document():
    """The evidence of the decision survives the decision expiring."""
    settings = ScannerSettings(waivers=parse_waivers([RECORD]))

    finding, ignored, records = _waive(settings, DEADLINE + timedelta(days=1))

    assert ignored == []
    assert finding.passed is False
    assert records[0]["state"] == "expired"
    assert records[0]["expiresAt"] == DEADLINE.isoformat()


def test_the_two_forms_live_side_by_side():
    """A permanent pattern keeps working next to a temporary record."""
    settings = ScannerSettings(
        ignore_hardenings=("basicAuthDisabled",), waivers=parse_waivers([RECORD])
    )
    findings = [
        Finding("basicAuthDisabled", "high", False, "basic auth is on"),
        Finding("debugPort:9205", "high", False, "metrics are readable"),
    ]

    ignored, records = _apply_waivers(
        settings, findings, {}, {}, {"enforced": True}, DEADLINE + timedelta(days=1)
    )

    assert ignored == ["basicAuthDisabled"]
    assert {record["pattern"] for record in records} == {
        "basicAuthDisabled",
        "debugPort:9205",
    }
    assert [record["state"] for record in records if record["pattern"] == "basicAuthDisabled"] == [
        "active"
    ]


# -------------------------------------------------- what a waiver may not do


def test_a_passing_check_is_never_marked_ignored():
    """
    Waiving something that passes is a blind spot waiting for the day it fails.

    True of the temporary form as well, and that is what this asserts.
    """
    settings = ScannerSettings(waivers=parse_waivers([RECORD]))

    finding, ignored, _ = _waive(settings, DEADLINE - timedelta(days=1), passed=True)

    assert ignored == []
    assert finding.ignored is False


def test_end_of_life_is_an_f_even_under_an_active_wildcard_waiver():
    """A waiver covers checks, not the fact that a release gets no fixes."""
    settings = ScannerSettings(
        waivers=parse_waivers([f"*|{DEADLINE.isoformat()}|Everything, briefly"])
    )
    findings = [Finding("debugPort:9205", "high", False, "metrics are readable")]
    _apply_waivers(
        settings, findings, {}, {}, {"enforced": True}, DEADLINE - timedelta(days=1)
    )

    explanation = _compute_rating(
        eol=True,
        vulnerabilities=[],
        update_available=False,
        behind_line=False,
        findings=findings,
        settings=settings,
    )

    assert findings[0].ignored is True
    assert explanation.rating == 0


# ------------------------------------------------- where records come from


def test_a_deadline_input_refuses_a_bare_pattern():
    """`--waive-until debugPort:*` names no deadline, so it waives nothing."""
    with pytest.raises(WaiverError, match="no expiry and no reason"):
        parse_waiver("debugPort:*", require_deadline=True)

    assert parse_waiver(RECORD, require_deadline=True).expires_at == DEADLINE


def test_a_semicolon_in_a_reason_cannot_invent_a_permanent_waiver():
    """
    The list is split on `;`, so the tail of the reason arrives on its own.

    Read as the bare form, `debugPort:9206 stays open` became a permanent
    waiver nobody wrote; it has to be a configuration error instead.
    """
    config = load_configuration(
        None,
        environ={
            "COS_SCANNER_TEMPORARY_WAIVERS": (
                f"debugPort:9205|{DEADLINE.isoformat()}|Firewall change; debugPort:9206"
            )
        },
    )

    with pytest.raises(ConfigurationError, match="temporary_waivers"):
        scanner_settings_from_config(config)


def test_two_complete_records_are_still_two_waivers():
    config = load_configuration(
        None,
        environ={
            "COS_SCANNER_TEMPORARY_WAIVERS": (
                f"{RECORD};exposed:/metrics|{DEADLINE.isoformat()}|Moving the exporter"
            )
        },
    )

    waivers = scanner_settings_from_config(config).waivers

    assert [waiver.pattern for waiver in waivers] == ["debugPort:9205", "exposed:/metrics"]
    assert all(waiver.temporary for waiver in waivers)


@pytest.mark.parametrize(
    "arguments",
    [
        ("--host", "opencloud.example.com"),
        ("--host", "opencloud.example.com,b.example.com"),
        ("--host", "opencloud.example.com", "--format", "json"),
    ],
)
def test_a_malformed_configured_waiver_is_unknown_on_every_output_path(arguments):
    """
    A traceback exits 1, which a monitoring system reads as WARNING.

    The single-host path already answered UNKNOWN for a bad configuration;
    the multi-host and machine-readable paths escaped as a traceback.
    """
    result = run_plugin(
        *arguments,
        env={"COS_SCANNER_TEMPORARY_WAIVERS": "debugPort:9205|2026-12-31|No timezone"},
    )

    assert result.returncode == UNKNOWN, result.stderr
    assert "Traceback" not in result.stderr
    assert "temporary_waivers" in result.stdout


def test_waive_until_with_a_bare_pattern_is_unknown():
    result = run_plugin("--host", "opencloud.example.com", "--waive-until", "debugPort:*")

    assert result.returncode == UNKNOWN
    assert "no expiry and no reason" in result.stdout
