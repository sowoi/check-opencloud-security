"""
Tests for the two operator-facing knobs: accepting hardening findings that
will never be fixed, and declaring which release track an instance follows.
"""

from datetime import date

import pytest

import check_opencloud_security as plugin
from check_opencloud_security import ScanContext, ScanResult, _waiver_patterns
from opencloud_local_scan.config import load_configuration
from opencloud_local_scan.factory import scanner_settings_from_config
from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.scanner import (
    Finding,
    ScannerSettings,
    _apply_waivers,
    _compute_rating,
    _is_ignored,
    failed_extra_checks,
    scan,
)
from opencloud_local_scan.versions import load_release_schedule
from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour

TODAY = date(2026, 8, 12)


def run_scan(behaviour: InstanceBehaviour, **settings_kwargs) -> dict:
    """Start a fake instance, scan it and return the result document."""
    settings = ScannerSettings(
        scheme="http",
        timeout=3,
        check_debug_ports=False,
        include_bundled_db=True,
        **settings_kwargs,
    )
    with FakeOpenCloud(behaviour) as instance:
        return scan(
            instance.host, settings=settings, release_settings=ReleaseSettings(mode="off")
        )


def run(result, capsys, **kwargs):
    """Run the plugin over a result document and capture output and exit code."""
    context = ScanContext(host="cloud.example.com", **kwargs)
    with pytest.raises(SystemExit) as exit_info:
        plugin.check_vulnerabilities(
            context, ScanResult(response=result, uuid="local-x"), duration_seconds=1.0
        )
    return capsys.readouterr().out, exit_info.value.code


# --- matching ---
def test_a_waiver_matches_regardless_of_case():
    """Operators type identifiers by hand; case should not decide the outcome."""
    assert _is_ignored("basicAuthDisabled", ("basicauthdisabled",))
    assert _is_ignored("basicAuthDisabled", ("BASICAUTHDISABLED",))


def test_a_waiver_can_use_a_wildcard():
    """Some ids carry a path or port, so they cannot be spelled out in advance."""
    assert _is_ignored("debugPort:9205", ("debugPort:*",))
    assert _is_ignored("exposed:/config/config.php", ("exposed:*",))
    assert not _is_ignored("basicAuthDisabled", ("debugPort:*",))


def test_an_unrelated_waiver_matches_nothing():
    """A typo must not silently waive something else."""
    assert not _is_ignored("basicAuthDisabled", ("basicAuthEnabled",))


# --- the rating responds to a waiver ---
def test_a_waived_check_no_longer_caps_the_rating():
    """This is the point of the option: accepting a finding changes the grade."""
    findings = [Finding("basicAuthDisabled", "high", False, "basic auth is on")]
    settings = ScannerSettings(ignore_hardenings=("basicAuthDisabled",))
    _apply_waivers(settings, findings, {}, {}, {"enforced": True})

    explanation = _compute_rating(
        eol=False,
        vulnerabilities=[],
        update_available=False,
        behind_line=False,
        findings=findings,
        settings=settings,
    )

    assert findings[0].ignored is True
    assert explanation.rating == 5
    assert explanation.caps == ()


def test_waiving_one_finding_leaves_the_others_capping():
    """A waiver is targeted, not a blanket switch-off of the rating."""
    findings = [
        Finding("basicAuthDisabled", "high", False, "basic auth is on"),
        Finding("exposed:/data", "critical", False, "readable without auth"),
    ]
    settings = ScannerSettings(ignore_hardenings=("basicAuthDisabled",))
    _apply_waivers(settings, findings, {}, {}, {"enforced": True})

    explanation = _compute_rating(
        eol=False,
        vulnerabilities=[],
        update_available=False,
        behind_line=False,
        findings=findings,
        settings=settings,
    )

    assert explanation.rating == 2
    assert [cap.check for cap in explanation.caps] == ["exposed:/data"]


def test_a_waiver_for_a_passing_check_changes_nothing():
    """Waiving something that passes would be a blind spot, so it is not applied."""
    findings = [Finding("basicAuthDisabled", "high", True, "")]
    settings = ScannerSettings(ignore_hardenings=("basicAuthDisabled",))

    ignored = _apply_waivers(settings, findings, {}, {}, {"enforced": True})

    assert ignored == []
    assert findings[0].ignored is False


def test_an_end_of_life_release_cannot_be_waived_away():
    """Waivers cover checks, not the fact that a release gets no security fixes."""
    findings = [Finding("basicAuthDisabled", "high", False, "basic auth is on")]
    settings = ScannerSettings(ignore_hardenings=("*",))
    _apply_waivers(settings, findings, {}, {}, {"enforced": True})

    explanation = _compute_rating(
        eol=True,
        vulnerabilities=[],
        update_available=False,
        behind_line=False,
        findings=findings,
        settings=settings,
    )

    assert explanation.rating == 0


# --- what a waiver does to the result document ---
def test_a_waived_check_stays_in_the_result_but_not_in_the_failures():
    """A waiver hides an alert, not the evidence behind it."""
    result = run_scan(
        InstanceBehaviour(basic_auth=True), ignore_hardenings=("basicAuthDisabled",)
    )

    entry = next(
        check for check in result["extraChecks"] if check["id"] == "basicAuthDisabled"
    )
    assert entry["passed"] is False
    assert entry["ignored"] is True
    assert "basicAuthDisabled" not in failed_extra_checks(result)
    assert "basicAuthDisabled" in result["ignored"]


def test_only_failing_measures_appear_in_the_ignored_list():
    """The list reports what was actually waived, not what was asked for."""
    result = run_scan(
        InstanceBehaviour(basic_auth=True), ignore_hardenings=("nonexistentMeasure",)
    )

    assert result["ignored"] == []


def test_without_the_option_nothing_is_waived():
    """The default must not change any existing behaviour."""
    result = run_scan(InstanceBehaviour(basic_auth=True))

    assert result["ignored"] == []
    assert all(not check.get("ignored") for check in result["extraChecks"])


# --- what a waiver does to the plugin output ---
def test_a_waived_measure_is_reported_rather_than_hidden(capsys):
    """An operator reading the output must be able to see what is being skipped."""
    result = run_scan(
        InstanceBehaviour(basic_auth=True), ignore_hardenings=("basicAuthDisabled",)
    )

    output, _ = run(result, capsys, check_hardening=True)

    assert "Ignored by configuration" in output
    assert "basicAuthDisabled" in output


def test_waiving_every_missing_measure_clears_the_hardening_warning(capsys):
    """The alert follows the waiver, otherwise the option would be pointless."""
    result = run_scan(InstanceBehaviour(basic_auth=True))
    missing = plugin._collect_missing_hardenings(result, actionable_only=True)
    assert missing, "the fake instance is expected to miss some hardening"

    waived = run_scan(InstanceBehaviour(basic_auth=True), ignore_hardenings=tuple(missing))
    output, _ = run(waived, capsys, check_hardening=True)

    assert "Missing hardening:" not in output
    assert "hardenings_missing=0" in output


def test_a_waived_measure_is_marked_in_the_debug_explanation(capsys):
    """Debug mode explains the rating, so it must say why a finding did not count."""
    result = run_scan(
        InstanceBehaviour(basic_auth=True), ignore_hardenings=("basicAuthDisabled",)
    )

    output, _ = run(result, capsys, check_hardening=True, debug=True)

    assert "--- Ignored by configuration ---" in output
    assert "ignored by configuration]" in output


def test_a_waived_measure_is_left_out_of_the_webhook(monkeypatch, capsys):
    """An accepted finding should not page anyone."""
    sent: list[dict] = []
    monkeypatch.setattr(
        plugin,
        "_send_webhook",
        lambda context, payload: sent.append(payload) or True,
    )

    hooked = {
        "check_hardening": True,
        "webhook_url": "https://hooks.example.com/x",
        "webhook_on": "always",
    }
    run(run_scan(InstanceBehaviour(basic_auth=True)), capsys, **hooked)
    run(
        run_scan(
            InstanceBehaviour(basic_auth=True), ignore_hardenings=("basicAuthDisabled",)
        ),
        capsys,
        **hooked,
    )

    reported, waived_payload = sent
    # Without the waiver the measure is reported, which is what makes the
    # second assertion meaningful rather than a check against a typo.
    assert "basicAuthDisabled" in reported["missing_hardenings"]
    assert "basicAuthDisabled" not in waived_payload["missing_hardenings"]


# --- the option is configurable the same way as every other one ---
def test_waivers_can_be_given_as_a_comma_separated_list():
    """One environment variable has to be able to carry several measures."""
    assert _waiver_patterns(["a,b", "c"]) == ("a", "b", "c")


def test_repeated_waivers_are_deduplicated():
    """A repeated flag should not produce a repeated report."""
    assert _waiver_patterns(["a", "a"]) == ("a",)


def test_no_waiver_flag_leaves_the_configured_value_alone():
    """None means "not given on the command line", not "empty"."""
    assert _waiver_patterns(None) is None


def test_waivers_are_read_from_the_configuration():
    """The option must work from a config file or environment, not just the CLI."""
    config = load_configuration(
        None, environ={"COS_SCANNER_IGNORE_HARDENINGS": "basicAuthDisabled;hstsPreload"}
    )
    settings = scanner_settings_from_config(config)

    assert settings.ignore_hardenings == ("basicAuthDisabled", "hstsPreload")


def test_the_release_track_is_read_from_the_configuration():
    config = load_configuration(None, environ={"COS_SCANNER_RELEASE_TRACK": "lts"})
    settings = scanner_settings_from_config(config)

    assert settings.release_track == "lts"


def test_an_unknown_release_track_is_ignored():
    """A typo should fall back to inference rather than break the check."""
    config = load_configuration(None, environ={"COS_SCANNER_RELEASE_TRACK": "stable"})
    settings = scanner_settings_from_config(config)

    assert settings.release_track is None


# --- the declared release track ---
def test_without_a_declared_track_the_longest_support_wins():
    """Unchanged behaviour: nobody said, so judge the line as generously as is true."""
    status = load_release_schedule().status_for("7.2.3", today=TODAY)

    assert status.state == "supported"
    assert status.release_type == "production"
    assert status.declared_track is None


def test_a_rolling_instance_is_end_of_life_once_the_next_release_ships():
    """Three weeks is the whole point of the rolling track."""
    status = load_release_schedule().status_for("7.2.3", today=TODAY, track="rolling")

    assert status.state == "endOfLife"
    assert status.declared_track == "rolling"
    assert status.upgrade_to == "7.4.0"


def test_the_same_version_is_current_on_the_production_track():
    """The declared track, not the version number, decides the support window."""
    status = load_release_schedule().status_for("7.2.3", today=TODAY, track="production")

    assert status.state == "supported"
    assert status.release_type == "production"
    assert status.upgrade_to is None


def test_a_newer_release_can_be_less_supported_than_an_older_one():
    """A rolling build is not a production release, however new it is."""
    schedule = load_release_schedule()

    rolling = schedule.status_for("7.4.0", today=TODAY, track="production")
    older = schedule.status_for("7.2.3", today=TODAY, track="production")

    assert rolling.state == "endOfLife"
    assert older.state == "supported"


def test_a_version_that_never_shipped_on_the_declared_track_says_so():
    """The reason has to explain a verdict the version number contradicts."""
    status = load_release_schedule().status_for("7.4.0", today=TODAY, track="production")

    assert "not published on the production track" in status.reason
    assert "it is a rolling release" in status.reason


def test_such_a_version_is_never_told_to_downgrade():
    """An upgrade arrow must always point forwards, whatever the track."""
    status = load_release_schedule().status_for("7.4.0", today=TODAY, track="production")

    assert status.upgrade_to is None


def test_an_lts_release_keeps_its_two_year_window_when_declared():
    status = load_release_schedule().status_for("4.0.8", today=TODAY, track="lts")

    assert status.state == "supported"
    assert status.release_type == "lts"


def test_an_unknown_declared_track_falls_back_to_inference():
    """Validation happens at the edge; the model must not crash on bad input."""
    status = load_release_schedule().status_for("7.2.3", today=TODAY, track="stable")

    assert status.state == "supported"
    assert status.declared_track is None


def test_the_declared_track_is_visible_in_the_output(capsys):
    """An operator has to be able to tell a declared track from an inferred one."""
    result = run_scan(InstanceBehaviour(), release_track="production")

    output, _ = run(result, capsys)

    assert "track declared" in output


def test_the_declared_track_steers_the_update_recommendation():
    """A production instance must not be pushed onto the rolling track."""
    behaviour = InstanceBehaviour()
    behaviour.status_payload["productversion"] = "7.2.0"

    result = run_scan(behaviour, release_track="production")

    assert result["lifecycle"]["upgradeTo"] == "7.2.3"
