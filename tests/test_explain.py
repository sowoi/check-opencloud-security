"""
Tests for the debug mode: why a rating is what it is, and what the
hardening identifiers actually mean.
"""

import pytest

import check_opencloud_security as plugin
from check_opencloud_security import ScanContext, ScanResult
from opencloud_local_scan import hardening
from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.scanner import (
    SCAN_HEADERS,
    Finding,
    RatingCap,
    RatingExplanation,
    ScannerSettings,
    _compute_rating,
    scan,
)
from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour

RESULT = {
    "domain": "cloud.example.com",
    "product": "OpenCloud",
    "version": "7.2.3",
    "scannedAt": {"date": "2026-08-12 10:00:00.000000"},
    "rating": 3,
    "ratingExplanation": {
        "rating": 3,
        "base": {"rating": 5, "reason": "the installed release is current"},
        "caps": [
            {
                "check": "basicAuthDisabled",
                "severity": "high",
                "cap": 3,
                "detail": "PROXY_ENABLE_BASIC_AUTH is on",
                "applied": True,
            }
        ],
    },
    "EOL": False,
    "vulnerabilities": [],
    "hardenings": {
        "basicAuthDisabled": False,
        "cspWithoutUnsafeInline": False,
        "publicLinkExpirationEnforced": False,
        "hstsPreload": True,
    },
    "setup": {
        "https": {"used": True, "enforced": True},
        "headers": {"X-Frame-Options": True, "Content-Security-Policy": True},
    },
    "extraChecks": [
        {
            "id": "basicAuthDisabled",
            "severity": "high",
            "passed": False,
            "detail": "PROXY_ENABLE_BASIC_AUTH is on",
        }
    ],
    "updates": {"available": False, "version": "7.2.3", "source": "pinned"},
}


def run_scan(behaviour: InstanceBehaviour) -> dict:
    """Start a fake instance, scan it and return the result document."""
    settings = ScannerSettings(
        scheme="http", timeout=3, check_debug_ports=False, include_bundled_db=True
    )
    with FakeOpenCloud(behaviour) as instance:
        return scan(
            instance.host, settings=settings, release_settings=ReleaseSettings(mode="off")
        )


def run(result, **kwargs):
    """Run the check and return its output."""
    context = ScanContext(host="cloud.example.com", **kwargs)
    with pytest.raises(SystemExit):
        plugin.check_vulnerabilities(
            context, ScanResult(response=result, uuid="local-x"), duration_seconds=1.0
        )


# --- the rating explains itself ---
def test_a_clean_instance_explains_why_it_scored_full_marks():
    """"Nothing is wrong" is also a verdict that deserves a reason."""
    explanation = _compute_rating(
        eol=False,
        vulnerabilities=[],
        update_available=False,
        behind_line=False,
        findings=[],
        settings=ScannerSettings(),
    )

    assert explanation.rating == 5
    assert explanation.base_rating == 5
    assert "current" in explanation.base_reason
    assert explanation.caps == ()


def test_the_worst_failed_check_is_named_as_the_reason():
    """An operator asking "why a D?" gets the check that caused it."""
    explanation = _compute_rating(
        eol=False,
        vulnerabilities=[],
        update_available=False,
        behind_line=False,
        findings=[
            Finding("exposed:/config", "critical", False, "readable without auth"),
            Finding("tlsProtocol", "low", False, "TLS 1.1 offered"),
            Finding("httpsAvailable", "critical", True, ""),
        ],
        settings=ScannerSettings(),
    )

    assert explanation.rating == 2
    assert explanation.base_rating == 5
    binding = [cap.check for cap in explanation.caps if cap.applied]
    assert binding == ["exposed:/config"]
    # The check that did not decide the outcome is still reported, so that a
    # finding is never silently dropped from the explanation.
    assert "tlsProtocol" in [cap.check for cap in explanation.caps]


def test_passing_checks_are_not_listed_as_reasons():
    """Only failures cap a rating."""
    explanation = _compute_rating(
        eol=False,
        vulnerabilities=[],
        update_available=False,
        behind_line=False,
        findings=[Finding("tlsTrusted", "critical", True, "")],
        settings=ScannerSettings(),
    )

    assert explanation.rating == 5
    assert explanation.caps == ()


def test_the_explanation_does_not_depend_on_the_order_of_the_checks():
    """The same evidence must always produce the same story."""
    findings = [
        Finding("tlsProtocol", "low", False, ""),
        Finding("exposed:/config", "critical", False, ""),
        Finding("directoryListing", "medium", False, ""),
    ]
    kwargs = {
        "eol": False,
        "vulnerabilities": [],
        "update_available": False,
        "behind_line": False,
        "settings": ScannerSettings(),
    }

    forwards = _compute_rating(findings=findings, **kwargs)
    backwards = _compute_rating(findings=list(reversed(findings)), **kwargs)

    assert forwards == backwards


def test_end_of_life_overrides_every_other_signal():
    """Rating 0 has exactly one cause, and the explanation says so."""
    explanation = _compute_rating(
        eol=True,
        vulnerabilities=[],
        update_available=False,
        behind_line=False,
        findings=[Finding("tlsProtocol", "low", False, "")],
        settings=ScannerSettings(),
    )

    assert explanation.rating == 0
    assert "out of support" in explanation.base_reason
    assert explanation.caps == ()


def test_a_critical_advisory_is_distinguished_from_an_ordinary_one():
    """Rating 1 and rating 2 are both "vulnerable", for different reasons."""
    critical = _compute_rating(
        eol=False,
        vulnerabilities=[{"id": "X", "severity": "critical"}],
        update_available=False,
        behind_line=False,
        findings=[],
        settings=ScannerSettings(),
    )
    moderate = _compute_rating(
        eol=False,
        vulnerabilities=[{"id": "Y", "severity": "medium"}],
        update_available=False,
        behind_line=False,
        findings=[],
        settings=ScannerSettings(),
    )

    assert (critical.rating, moderate.rating) == (1, 2)
    assert "critical or high" in critical.base_reason
    assert "critical or high" not in moderate.base_reason


def test_checks_excluded_from_the_rating_say_so():
    """An operator must not wonder why a failed check changed nothing."""
    explanation = _compute_rating(
        eol=False,
        vulnerabilities=[],
        update_available=False,
        behind_line=False,
        findings=[Finding("exposed:/config", "critical", False, "")],
        settings=ScannerSettings(extra_checks_affect_rating=False),
    )

    assert explanation.rating == 5
    assert "do not affect the rating" in explanation.base_reason


def test_the_explanation_renders_in_the_order_it_was_applied():
    """The rendered form reads as an argument, not a data dump."""
    lines = RatingExplanation(
        rating=3,
        base_rating=5,
        base_reason="the installed release is current",
        caps=(RatingCap(check="basicAuthDisabled", severity="high", cap=3),),
    ).lines()

    assert lines[0].startswith("Starting point: 5/5")
    assert "basicAuthDisabled" in lines[1]
    assert "caps the rating at 3/5" in lines[1]
    assert lines[-1] == "Final rating: 3/5"


# --- the plugin's debug output ---
def test_debug_mode_explains_the_rating(capsys):
    """The whole point: the number stops being a bare assertion."""
    run(RESULT, debug=True)

    output = capsys.readouterr().out
    assert "--- Why this rating ---" in output
    assert "Starting point: 5/5" in output
    assert "caps the rating at 3/5" in output
    assert "Final rating: 3/5 (C)" in output


def test_debug_mode_names_the_thresholds_that_produced_the_state(capsys):
    """"Why is this a WARNING?" is a different question from "why a C?"."""
    run(RESULT, debug=True, warning_rating=3, critical_rating=1)

    output = capsys.readouterr().out
    assert "WARNING at or below C, CRITICAL at or below E" in output


def test_debug_mode_explains_every_hardening_identifier(capsys):
    """Each identifier gets a meaning, a setting and a documentation link."""
    run(RESULT, debug=True, check_hardening=True)

    output = capsys.readouterr().out
    assert "--- Missing hardening measures ---" in output
    assert "PROXY_ENABLE_BASIC_AUTH" in output
    assert "docs.opencloud.eu" in output
    assert "Fix:" in output


def test_debug_mode_also_explains_measures_that_are_not_alerted_on(capsys):
    """
    The hardcoded flags are hidden from alerts but not from a human who asked
    for an explanation - otherwise the JSON and the output disagree.
    """
    run(RESULT, debug=True, check_hardening=True)

    output = capsys.readouterr().out
    assert "publicLinkExpirationEnforced" in output
    assert "not configurable" in output


def test_the_explanation_ends_before_the_performance_data(capsys):
    """Perfdata is appended to the last line, which must stay readable."""
    run(RESULT, debug=True, check_hardening=True)

    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith("--- end of explanation ---")
    assert "| rating=3" in last


def test_without_debug_the_output_stays_machine_sized(capsys):
    """A monitoring system gets identifiers, not essays."""
    run(RESULT, check_hardening=True)

    output = capsys.readouterr().out
    assert "--- Why this rating ---" not in output
    assert "PROXY_ENABLE_BASIC_AUTH" not in output
    assert "Missing hardening:" in output


# --- flags nobody can act on ---
def test_hardcoded_flags_are_kept_out_of_the_alert(capsys):
    """
    OpenCloud reports publicLinkExpirationEnforced as false on every instance
    and offers no setting for it. Alerting on it would be permanent noise.
    """
    run(RESULT, check_hardening=True)

    output = capsys.readouterr().out
    summary = next(line for line in output.splitlines() if line.startswith("Missing hardening:"))
    assert "publicLinkExpirationEnforced" not in summary
    assert "basicAuthDisabled" in summary


def test_hardcoded_flags_are_not_counted_in_the_metric(capsys):
    """A metric that can never reach zero is not worth graphing."""
    run(RESULT, check_hardening=True)

    output = capsys.readouterr().out
    # basicAuthDisabled and cspWithoutUnsafeInline, not the hardcoded third.
    assert "hardenings_missing=2;;;0;" in output


def test_an_instance_whose_only_gap_is_hardcoded_is_not_warned_about(capsys):
    """Otherwise every OpenCloud instance in the world warns forever."""
    result = {
        **RESULT,
        "rating": 5,
        "ratingExplanation": {"rating": 5, "base": {"rating": 5, "reason": "fine"}, "caps": []},
        "hardenings": {"publicLinkExpirationEnforced": False, "basicAuthDisabled": True},
        "extraChecks": [],
    }

    run(result, check_hardening=True)

    output = capsys.readouterr().out
    assert "Hardening: all checked measures in place" in output
    assert output.startswith("OK:")


def test_the_webhook_reports_the_same_measures_as_the_alert():
    """A notification and its webhook must not disagree about the count."""
    context = ScanContext(host="h", check_hardening=True)

    payload = plugin._build_webhook_payload(
        context,
        scan_result=ScanResult(response=RESULT, uuid="u"),
        response_scan=RESULT,
        message="m",
        exit_code=plugin.NagiosExitCode.WARNING,
        rating=3,
        rate="C",
        vulnerabilities=[],
        missing_hardenings=plugin._collect_missing_hardenings(RESULT, actionable_only=True),
        duration_seconds=1.0,
    )

    assert payload["missing_hardenings"] == ["basicAuthDisabled", "cspWithoutUnsafeInline"]


# --- the catalogue itself ---
def test_every_flag_a_real_scan_produces_is_documented():
    """
    A new check without an explanation is the bug this module exists to
    prevent. The expectation is taken from an actual scan rather than from a
    list kept alongside it, so adding a hardening without documenting it fails
    here instead of reaching an operator as a bare identifier.
    """
    result = run_scan(InstanceBehaviour())
    produced = set(result["hardenings"]) | set(result["setup"]["headers"]) | {"httpsEnforced"}

    assert produced, "the fake instance produced no hardening flags at all"
    for name in produced:
        described = hardening.describe(name)
        assert described.meaning, f"{name} has no explanation"
        assert described.remediation, f"{name} has no remediation"
        assert "No description" not in described.meaning, f"{name} is undocumented"


def test_the_catalogue_documents_every_security_header_the_scanner_checks():
    """SCAN_HEADERS and the catalogue must not drift apart."""
    for name in SCAN_HEADERS:
        assert "No description" not in hardening.describe(name).meaning


def test_an_unknown_identifier_still_produces_something_printable():
    """A future check must not crash the explanation."""
    described = hardening.describe("someFutureCheck")

    assert described.id == "someFutureCheck"
    assert "No description" in described.meaning


def test_settings_are_named_for_the_measures_that_have_one():
    """The point of the catalogue is naming the knob, not just the problem."""
    assert hardening.describe("basicAuthDisabled").setting == "PROXY_ENABLE_BASIC_AUTH"
    assert (
        "OC_PASSWORD_POLICY_MIN_CHARACTERS"
        in hardening.describe("passwordPolicyEnforced").remediation
    )


def test_measures_without_a_setting_do_not_invent_one():
    """Naming a variable that does not exist is worse than naming none."""
    for name in ("publicLinkExpirationEnforced", "userEnumerationRestricted"):
        described = hardening.describe(name)
        assert described.setting == ""
        assert described.actionable is False
        assert "Nothing to change" in described.remediation


def test_hsts_points_at_the_reverse_proxy_not_at_opencloud():
    """OpenCloud hardcodes a ten-year HSTS, so a short one comes from ahead."""
    for name in ("hstsLongMaxAge", "hstsPreload"):
        assert "reverse proxy" in hardening.describe(name).remediation


def test_the_csp_explanation_admits_it_is_the_shipped_default():
    """Telling an operator to "fix" the vendor default without saying so is a trap."""
    described = hardening.describe("cspWithoutUnsafeInline")

    assert "default" in described.meaning
    assert "break the UI" in described.remediation


def test_headers_are_explained_even_though_they_are_not_settings():
    """A missing header is a finding too, and needs the same treatment."""
    described = hardening.describe("Referrer-Policy")

    assert "Referer" in described.meaning
    assert described.reference.endswith("Referrer-Policy")
