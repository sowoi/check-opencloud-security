"""
--waiver-warning and waiver_days_left: lead time before a waiver runs out.

A temporary waiver is binary - silent until its deadline, an alert on the
next run after it - so a daily check could go from OK to WARNING with no
warning at all. These tests pin the countdown that closes that gap: which
deadline counts, what it is counted from, and when it raises the state.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

import pytest

import check_opencloud_security as plugin
from check_opencloud_security import NagiosExitCode, ScanContext, ScanResult
from opencloud_local_scan import wizard
from opencloud_local_scan.metrics import collect
from opencloud_local_scan.waivers import days_left, next_expiry, scanned_at

HOST = "opencloud.example.com"
SCANNED = "2026-05-01 10:00:00.000000"
NOW = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)


def record(pattern: str, expires: str | None, matched: list[str], state: str = "active"):
    return {
        "pattern": pattern,
        "reason": f"reason for {pattern}" if expires else "",
        "expiresAt": expires,
        "state": state,
        "matched": matched,
    }


RESULT: dict[str, Any] = {
    "domain": HOST,
    "product": "OpenCloud",
    "version": "7.2.0",
    "scannedAt": {"date": SCANNED},
    "rating": 5,
    "EOL": False,
    "vulnerabilities": [],
    "hardenings": {},
    "setup": {"https": {"used": True, "enforced": True}, "headers": {}},
    "ignored": ["debugPort:9205"],
    "waivers": [
        record("debugPort:9205", "2026-05-09T10:00:00+00:00", ["debugPort:9205"]),
    ],
}


def result(*waivers):
    document = copy.deepcopy(RESULT)
    if waivers:
        document["waivers"] = list(waivers)
    return document


def run(document, capsys, **kwargs):
    context = ScanContext(host=HOST, update_check=False, **kwargs)
    with pytest.raises(SystemExit) as excinfo:
        plugin.check_vulnerabilities(
            context, ScanResult(response=document, uuid="local-x"), duration_seconds=1.0
        )
    output = capsys.readouterr().out
    code = excinfo.value.code
    assert isinstance(code, int), code
    return NagiosExitCode(code), output


def perfdata(output: str) -> dict[str, str]:
    data = output.split("|", 1)[1].split()
    return dict(item.split("=", 1) for item in data)


# --- which deadline counts ---------------------------------------------------


def test_the_countdown_runs_from_the_scan_to_the_deadline():
    """Eight days between the scan and the deadline is eight days left."""
    assert days_left(result()) == 8
    assert scanned_at(result()) == NOW


def test_the_countdown_truncates_a_partial_day():
    """Hours short of a full day do not round up, as with the certificate."""
    document = result(record("x", "2026-05-02T09:00:00Z", ["x"]))

    assert days_left(document) == 0


def test_a_deadline_under_a_permanent_pattern_changes_nothing():
    """The check stays waived after the temporary record ends, so nothing counts down."""
    document = result(
        record("debugPort:*", None, ["debugPort:9205"]),
        record("debugPort:9205", "2026-05-09T10:00:00Z", ["debugPort:9205"]),
    )

    assert next_expiry(document["waivers"]) is None
    assert days_left(document) is None


def test_overlapping_deadlines_end_at_the_later_one():
    """A check is only uncovered once its last active waiver has run out."""
    document = result(
        record("debugPort:*", "2026-05-20T10:00:00Z", ["debugPort:9205"]),
        record("debugPort:9205", "2026-05-09T10:00:00Z", ["debugPort:9205"]),
    )

    upcoming = next_expiry(document["waivers"])

    assert upcoming is not None
    assert upcoming.pattern == "debugPort:*"
    assert days_left(document) == 19


def test_the_earliest_uncovered_check_is_the_one_reported():
    """Two checks on two deadlines: the sooner one is the lead time."""
    document = result(
        record("a", "2026-05-20T10:00:00Z", ["a"]),
        record("b", "2026-05-04T10:00:00Z", ["b"]),
    )

    upcoming = next_expiry(document["waivers"])

    assert upcoming is not None
    assert upcoming.checks == ("b",)
    assert days_left(document) == 3


@pytest.mark.parametrize(
    "waiver",
    [
        record("stale", "2026-05-09T10:00:00Z", []),
        record("gone", "2026-04-01T10:00:00Z", ["gone"], state="expired"),
        record("forever", None, ["forever"]),
        record("broken", "not a date", ["broken"]),
    ],
    ids=["matched-nothing", "already-expired", "permanent", "unreadable"],
)
def test_a_waiver_whose_end_changes_nothing_has_no_countdown(waiver):
    """Only a deadline that lets a failing check alert again is counted."""
    assert days_left(result(waiver)) is None


def test_a_waiver_on_a_hardcoded_flag_has_no_countdown():
    """A flag OpenCloud hardcodes never alerts, so its waiver ending changes nothing."""
    hardcoded = record(
        "publicLinkExpirationEnforced", "2026-05-09T10:00:00Z", ["publicLinkExpirationEnforced"]
    )

    assert days_left(result(hardcoded)) is None
    both = result(
        record("*", "2026-05-09T10:00:00Z", ["publicLinkExpirationEnforced", "debugPort:9205"])
    )
    upcoming = next_expiry(both["waivers"])
    assert upcoming is not None
    assert upcoming.checks == ("debugPort:9205",)


def test_a_result_without_waivers_has_no_countdown():
    """No waivers block is not a waiver ending today."""
    document = result()
    del document["waivers"]

    assert days_left(document) is None


# --- the alert ---------------------------------------------------------------


def test_a_waiver_ending_inside_the_window_warns_and_names_it(capsys):
    """Eight days left inside a fourteen-day window is a WARNING naming the waiver."""
    code, output = run(result(), capsys, waiver_warning_days=14)
    first = output.split("\n", 1)[0]

    assert code is NagiosExitCode.WARNING
    assert first.startswith("WARNING: The waiver debugPort:9205 (reason for debugPort:9205)")
    assert "2026-05-09 10:00 UTC (8 days left)" in first
    assert "debugPort:9205 alerts again" in first


def test_the_warning_counts_one_day_and_several_checks_in_plain_english(capsys):
    """One day is "1 day left", and two checks "alert", not "alerts"."""
    document = result(record("debugPort:*", "2026-05-02T12:00:00Z", ["debugPort:9205", "debugPort:9229"]))

    code, output = run(document, capsys, waiver_warning_days=14)
    first = output.split("\n", 1)[0]

    assert code is NagiosExitCode.WARNING
    assert "(1 day left)" in first
    assert "debugPort:9205, debugPort:9229 alert again." in first


def test_two_waivers_ending_together_are_both_named(capsys):
    """Each check that alerts again is explained by the waiver that covered it."""
    document = result(
        record("debugPort:9205", "2026-05-09T10:00:00Z", ["debugPort:9205"]),
        record("debugPort:9229", "2026-05-09T10:00:00Z", ["debugPort:9229"]),
    )

    code, output = run(document, capsys, waiver_warning_days=14)
    first = output.split("\n", 1)[0]

    assert code is NagiosExitCode.WARNING
    assert first.startswith(
        "WARNING: The waivers debugPort:9205 (reason for debugPort:9205), "
        "debugPort:9229 (reason for debugPort:9229) end on 2026-05-09 10:00 UTC"
    )
    assert "debugPort:9205, debugPort:9229 alert again." in first


def test_a_hardcoded_flag_under_a_waiver_does_not_warn(capsys):
    """Nothing alerts when a waiver on a flag nobody can change runs out."""
    document = result(
        record(
            "publicLinkExpirationEnforced",
            "2026-05-09T10:00:00Z",
            ["publicLinkExpirationEnforced"],
        )
    )

    code, output = run(document, capsys, waiver_warning_days=14)

    assert code is NagiosExitCode.OK
    assert "waiver_days_left" not in perfdata(output)


def test_a_waiver_ending_outside_the_window_stays_ok(capsys):
    """Eight days left is not inside a seven-day window."""
    code, _ = run(result(), capsys, waiver_warning_days=7)

    assert code is NagiosExitCode.OK


def test_the_last_day_of_the_window_warns(capsys):
    """The window is inclusive, as --eol-warning's is."""
    code, _ = run(result(), capsys, waiver_warning_days=8)

    assert code is NagiosExitCode.WARNING


def test_without_the_option_a_waiver_never_warns(capsys):
    """The default window is off; the countdown is still graphed and shown."""
    code, output = run(result(), capsys)

    assert code is NagiosExitCode.OK
    assert "Next waiver expiry: The waiver debugPort:9205" in output
    assert perfdata(output)["waiver_days_left"] == "8;;;0;"


def test_a_worse_result_is_not_replaced_by_the_waiver_warning(capsys):
    """A CRITICAL rating says something more urgent than a waiver ending."""
    document = result()
    document["rating"] = 1

    code, output = run(document, capsys, waiver_warning_days=14)

    assert code is NagiosExitCode.CRITICAL
    assert "The waiver" not in output.split("\n", 1)[0]


def test_a_waiver_covered_by_a_permanent_pattern_does_not_warn(capsys):
    """Nothing will alert when that deadline passes, so nothing warns."""
    document = result(
        record("debugPort:*", None, ["debugPort:9205"]),
        record("debugPort:9205", "2026-05-09T10:00:00Z", ["debugPort:9205"]),
    )

    code, output = run(document, capsys, waiver_warning_days=14)

    assert code is NagiosExitCode.OK
    assert "waiver_days_left" not in perfdata(output)
    assert "Next waiver expiry" not in output


# --- perfdata, Checkmk, Prometheus, webhook -----------------------------------


def test_the_window_becomes_the_perfdata_warning_range():
    """With --waiver-warning the graph warns at the same day count the alert does."""
    windowed = plugin._build_perfdata(
        5, plugin.RATE_MAP, 0, None,
        context=ScanContext(host=HOST, waiver_warning_days=14), waiver_days_left=8,
    )
    plain = plugin._build_perfdata(
        5, plugin.RATE_MAP, 0, None, context=ScanContext(host=HOST), waiver_days_left=8,
    )

    assert "waiver_days_left=8;@~:14;;0;" in windowed.split()
    assert "waiver_days_left=8;;;0;" in plain.split()


def test_the_countdown_reaches_checkmk_and_prometheus():
    """Every monitoring tool learns the same number."""
    document = result()
    metrics = plugin._checkmk_metrics(
        {"payload": {}, "scan": document, "hardening_checked": False}
    )
    families = {
        family.name: family
        for family in collect(HOST, document, duration_seconds=1.0, success=True)
    }

    assert "waiver_days_left=8" in metrics.split("|")
    assert families["opencloud_security_waiver_days_remaining"].samples[0].value == 8


def test_the_webhook_carries_the_countdown_and_the_window():
    """A receiver reads the countdown and the verdict without recomputing either."""
    payload = plugin._build_webhook_payload(
        ScanContext(host=HOST, waiver_warning_days=14),
        scan_result=ScanResult(response=result(), uuid="local-x"),
        response_scan=result(),
        message="WARNING",
        exit_code=NagiosExitCode.WARNING,
        rating=5,
        rate="A+",
        vulnerabilities=[],
        missing_hardenings=[],
        duration_seconds=1.0,
    )

    assert payload["waiver_days_left"] == 8
    assert payload["waiver_warning_days"] == 14
    assert payload["waiver_warning"] is True


def test_the_webhook_says_no_countdown_when_there_is_none():
    """null, not 0: no deadline is not a deadline today."""
    document = result(record("forever", None, ["forever"]))

    assert plugin._within_waiver_window(ScanContext(host=HOST, waiver_warning_days=14),
                                        document) is False
    assert days_left(document) is None


# --- the option ----------------------------------------------------------------


def _parse(monkeypatch, arguments, config=None):
    original = plugin._CONFIG
    try:
        plugin._set_configuration(plugin._preparse_config(config or []))
        return plugin.build_arg_parser().parse_args(["-H", HOST, *arguments])
    finally:
        plugin._set_configuration(original)


def test_the_option_defaults_to_off(monkeypatch):
    """Nothing configured means no early warning."""
    monkeypatch.delenv("COS_WAIVER_WARNING", raising=False)

    assert _parse(monkeypatch, []).waiver_warning == 0


def test_the_environment_sets_the_option_and_the_flag_wins(monkeypatch):
    """COS_WAIVER_WARNING sets the default; the flag overrides it."""
    monkeypatch.setenv("COS_WAIVER_WARNING", "21")

    assert _parse(monkeypatch, []).waiver_warning == 21
    assert _parse(monkeypatch, ["--waiver-warning", "3"]).waiver_warning == 3


def test_the_configuration_file_sets_the_option(monkeypatch, tmp_path):
    """The YAML key waiver_warning sets the default when the environment is silent."""
    monkeypatch.delenv("COS_WAIVER_WARNING", raising=False)
    path = tmp_path / "config.yml"
    path.write_text("waiver_warning: 10\n", encoding="utf-8")

    assert _parse(monkeypatch, [], ["--config", str(path)]).waiver_warning == 10


def test_a_negative_option_is_a_usage_error(capsys):
    """A negative window is a typo, not a quiet 'off'."""
    parser = plugin.build_arg_parser()
    args = parser.parse_args(["-H", HOST, "--waiver-warning", "-1"])

    with pytest.raises(SystemExit) as excinfo:
        plugin._validate_thresholds(parser, args)

    assert excinfo.value.code == 2
    assert "--waiver-warning must be 0" in capsys.readouterr().err


def test_the_wizard_asks_for_the_window():
    """The setup wizard offers the option, off by default."""
    questions = {
        question.key: question
        for group in wizard.optional_groups()
        for question in group.questions
    }

    question = questions["waiver_warning"]
    assert question.default == "0"
    assert question.validate("-1") is not None
    assert question.validate("14") is None
