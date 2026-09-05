"""
Tests for the plugin output: perfdata, hardening reporting and formatting.
"""

import pytest

import check_opencloud_security as plugin
from check_opencloud_security import NagiosExitCode, ScanContext, ScanResult
from opencloud_local_scan.scanner import ScannerSettings

RESULT = {
    "domain": "cloud.example.com",
    "product": "OpenCloud",
    "version": "7.2.0",
    "scannedAt": {"date": "2026-05-01 10:00:00.000000"},
    "rating": 5,
    "EOL": False,
    "vulnerabilities": [],
    "hardenings": {
        "hstsLongMaxAge": True,
        "hstsPreload": True,
        "cspWithoutUnsafeInline": True,
        "basicAuthDisabled": True,
    },
    "setup": {
        "https": {"used": True, "enforced": True},
        "headers": {"X-Frame-Options": True, "Content-Security-Policy": True},
    },
    "extraChecks": [],
    "updates": {"available": False, "version": "7.2.0", "source": "pinned"},
}


def run(result, **kwargs):
    """Run check_vulnerabilities and capture its output and exit code."""
    context = ScanContext(host="cloud.example.com", **kwargs)
    with pytest.raises(SystemExit) as excinfo:
        plugin.check_vulnerabilities(
            context, ScanResult(response=result, uuid="local-x"), duration_seconds=1.25
        )
    return excinfo.value.code


# --- perfdata ---
def test_perfdata_carries_the_configured_thresholds():
    """Graphing frontends draw the thresholds next to the measured value."""
    context = ScanContext(host="h", warning_rating=3, critical_rating=1)

    perfdata = plugin._build_perfdata(5, plugin.RATE_MAP, 0, 1.5, context=context)

    assert "rating=5;@0:3;@0:1;0;5" in perfdata
    assert "vulnerabilities=0;;;0;" in perfdata
    assert "time=1.500s;;;0;" in perfdata


def test_unknown_rating_becomes_the_nagios_undefined_marker():
    """'U' is how Nagios expresses "no value" in performance data."""
    assert plugin._build_perfdata(-1, plugin.RATE_MAP, 0, None).startswith("rating=U")


def test_optional_metrics_are_omitted_when_not_measured():
    """A metric that was never collected must not be reported as zero."""
    perfdata = plugin._build_perfdata(5, plugin.RATE_MAP, 0, None)

    assert "time=" not in perfdata
    assert "hardenings_missing=" not in perfdata
    assert "extra_checks_failed=" not in perfdata
    assert "update_available=" not in perfdata


def test_optional_metrics_are_included_when_measured():
    """Everything the check knows should be graphable."""
    perfdata = plugin._build_perfdata(
        4,
        plugin.RATE_MAP,
        1,
        2.0,
        missing_hardenings=2,
        failed_extra_checks_count=3,
        update_available=True,
    )

    assert "hardenings_missing=2;;;0;" in perfdata
    assert "extra_checks_failed=3;;;0;" in perfdata
    assert "update_available=1;;;0;1" in perfdata


def test_perfdata_is_appended_to_the_output(capsys):
    """Nagios splits the output on the first '|'."""
    run(RESULT)

    output = capsys.readouterr().out
    assert " | rating=5" in output


# --- hardening ---
def test_missing_hardening_is_collected_from_every_block():
    """Hardenings, headers and HTTPS enforcement all feed the same list."""
    result = {
        "hardenings": {"cspWithoutUnsafeInline": False, "basicAuthDisabled": True},
        "setup": {
            "https": {"used": True, "enforced": False},
            "headers": {"X-Frame-Options": False, "X-Robots-Tag": True},
        },
    }

    missing = plugin._collect_missing_hardenings(result)

    assert missing == ["cspWithoutUnsafeInline", "httpsEnforced", "X-Frame-Options"]


def test_missing_hardening_of_an_empty_result_is_empty():
    """A result document without those blocks must not crash the check."""
    assert plugin._collect_missing_hardenings({}) == []


def test_hardening_is_only_reported_when_asked_for(capsys):
    """--check-hardening is opt-in, because it changes the check's verdict."""
    result = {**RESULT, "hardenings": {"cspWithoutUnsafeInline": False}}

    code = run(result)

    assert code == int(NagiosExitCode.OK)
    assert "Missing hardening" not in capsys.readouterr().out


def test_missing_hardening_raises_an_ok_result_to_warning(capsys):
    """That is the whole point of the flag."""
    result = {**RESULT, "hardenings": {"cspWithoutUnsafeInline": False}}

    code = run(result, check_hardening=True)

    output = capsys.readouterr().out
    assert code == int(NagiosExitCode.WARNING)
    assert "Missing hardening: cspWithoutUnsafeInline" in output
    assert "hardenings_missing=1" in output


def test_hardening_does_not_downgrade_a_critical_result(capsys):
    """A vulnerability outranks a missing header."""
    result = {
        **RESULT,
        "rating": 1,
        "vulnerabilities": [{"id": "CVE-2026-0001"}],
        "hardenings": {"cspWithoutUnsafeInline": False},
    }

    code = run(result, check_hardening=True)

    assert code == int(NagiosExitCode.CRITICAL)


def test_complete_hardening_is_stated_explicitly(capsys):
    """"No news" is not good news in a monitoring output."""
    code = run(RESULT, check_hardening=True)

    assert code == int(NagiosExitCode.OK)
    assert "all checked measures in place" in capsys.readouterr().out


# --- extra checks ---
def test_failed_extra_checks_are_summarised(capsys):
    """The operator sees the worst findings first, and how many there are."""
    result = {
        **RESULT,
        "extraChecks": [
            {"id": f"exposed:/f{index}", "severity": "critical", "passed": False}
            for index in range(7)
        ],
    }

    run(result)

    output = capsys.readouterr().out
    assert "Additional checks failed (7)" in output
    assert "(+2 more)" in output


def test_passing_extra_checks_are_stated(capsys):
    """A clean extra-check run deserves a line of its own."""
    result = {**RESULT, "extraChecks": [{"id": "tlsTrusted", "passed": True}]}

    run(result)

    assert "Additional checks: all passed" in capsys.readouterr().out


# --- vulnerabilities ---
def test_vulnerability_list_is_truncated():
    """A long list would drown the alert."""
    entries = [{"id": f"CVE-2026-{index:04d}"} for index in range(8)]

    summary = plugin._format_vulnerabilities(entries)

    assert summary.count("CVE-") == 5
    assert summary.endswith("(+3 more)")


def test_vulnerability_without_an_id_falls_back_to_the_cwe():
    """Some advisory sources only carry a CWE."""
    assert plugin._format_vulnerabilities([{"cwe": "CWE-79"}]) == "CWE-79"


def test_empty_vulnerability_list_says_so():
    """An empty summary would look like a formatting bug."""
    assert plugin._format_vulnerabilities([]) == "details unavailable"


# --- update reporting ---
def test_update_information_is_printed(capsys):
    """The update state is part of every result that has one."""
    result = {
        **RESULT,
        "rating": 4,
        "updates": {
            "available": True,
            "version": "7.2.0",
            "availableVersion": "7.4.0",
            "source": "feed",
        },
    }

    code = run(result)

    output = capsys.readouterr().out
    assert code == int(NagiosExitCode.OK)
    assert "update available: 7.4.0" in output
    assert "update_available=1" in output


def test_update_warning_raises_an_ok_result(capsys):
    """--update-warning turns a pending update into a WARNING."""
    result = {
        **RESULT,
        "rating": 4,
        "updates": {
            "available": True,
            "version": "7.2.0",
            "availableVersion": "7.4.0",
            "source": "feed",
        },
    }

    code = run(result, update_warning=True)

    assert code == int(NagiosExitCode.WARNING)
    assert "WARNING: Update available (7.4.0)" in capsys.readouterr().out


def test_update_check_can_be_switched_off(capsys):
    """With --no-update-check the block is not even mentioned."""
    result = {
        **RESULT,
        "updates": {"available": True, "availableVersion": "7.4.0", "source": "feed"},
    }

    run(result, update_check=False)

    assert "Update check" not in capsys.readouterr().out


def test_failed_update_check_is_reported_but_not_fatal(capsys):
    """A firewalled monitoring host still gets the security verdict."""
    result = {
        **RESULT,
        "updates": {"available": None, "source": "feed", "error": "no route to host"},
    }

    code = run(result)

    assert code == int(NagiosExitCode.OK)
    assert "no route to host" in capsys.readouterr().out


def test_summary_line_names_product_version_and_domain(capsys):
    """The first detail line is what ends up in a chat notification."""
    run(RESULT)

    assert "OpenCloud 7.2.0 on cloud.example.com, rating: A+" in capsys.readouterr().out


# --- Release lifecycle reporting ---
#
# OpenCloud maintains rolling, production and LTS releases side by side, so
# "7.2.3" on its own does not tell an operator whether the instance is safe.
# The plugin therefore prints the release line, its track and how long it is
# still supported.
def lifecycle_result(**lifecycle):
    """A scan result carrying a lifecycle section."""
    return {
        **RESULT,
        "releaseType": lifecycle.get("releaseType"),
        "lifecycle": {
            "line": "7.2",
            "releaseType": "production",
            "state": "supported",
            "released": "2026-06-25",
            "endOfLife": None,
            "daysRemaining": None,
            "latestOnLine": None,
            "upgradeTo": None,
            "reason": "current production release",
            **lifecycle,
        },
    }


def test_the_current_release_is_reported_as_such(capsys):
    """Nothing to do, but the operator still learns which track applies."""
    run(lifecycle_result())

    assert "Release lifecycle: 7.2 (production), current release" in capsys.readouterr().out


def test_a_remaining_support_window_is_reported(capsys):
    """An LTS instance wants to know how long the backports keep coming."""
    run(
        lifecycle_result(
            releaseType="lts",
            line="4.0",
            endOfLife="2027-12-01",
            daysRemaining=476,
        )
    )

    output = capsys.readouterr().out
    assert "Release lifecycle: 4.0 (lts), supported until 2027-12-01 (476 days left)" in output


def test_a_pending_patch_on_the_line_is_reported(capsys):
    """Being on a supported line is not the same as being up to date."""
    run(lifecycle_result(latestOnLine="7.2.4", upgradeTo="7.2.4"))

    assert "upgrade to 7.2.4" in capsys.readouterr().out


def test_a_schedule_older_than_the_instance_is_reported_and_not_charged_for(capsys):
    """
    The bundled schedule ages between releases of this package, so an
    instance patched last week can be newer than the file judging it. The
    operator is told, and pointed at the page the schedule came from - but
    the check still exits OK, because being ahead of our data is not a
    finding about their server.
    """
    code = run(
        lifecycle_result(
            scheduleStale=True,
            scheduleUpdated="2026-08-12",
            scheduleSource="https://docs.opencloud.eu/docs/admin/resources/lifecycle/",
            scheduleNote=(
                "7.2.4 is newer than anything in the bundled release schedule "
                "(generated 2026-08-12), so that schedule is probably out of "
                "date. This is not counted against the instance. Check the "
                "current support window at "
                "https://docs.opencloud.eu/docs/admin/resources/lifecycle/."
            ),
        )
    )

    output = capsys.readouterr().out
    assert "Release schedule:" in output
    assert "probably out of date" in output
    assert "https://docs.opencloud.eu/docs/admin/resources/lifecycle/" in output
    assert code == 0


def test_a_schedule_that_knows_the_release_says_nothing_about_itself(capsys):
    """A note on every run would be noise, and noise is how a real one gets
    missed - it appears only when the schedule is actually behind."""
    run(lifecycle_result())

    assert "Release schedule:" not in capsys.readouterr().out


def test_an_end_of_life_line_is_named_in_the_critical_message(capsys):
    """'This server version' is not actionable; the track and target are."""
    code = run(
        {
            **lifecycle_result(
                line="7.3",
                releaseType="rolling",
                state="endOfLife",
                endOfLife="2026-08-03",
                daysRemaining=-9,
                upgradeTo="7.4.0",
                reason="rolling release, unsupported since 2026-08-03",
            ),
            "EOL": True,
        }
    )

    output = capsys.readouterr().out
    assert code == int(NagiosExitCode.CRITICAL)
    assert "The 7.3 rolling release line is end-of-life" in output
    assert "Upgrade to 7.4.0." in output
    assert "out of support since 2026-08-03" in output


def test_the_remaining_support_window_becomes_perfdata(capsys):
    """So that a graph shows the support window shrinking."""
    run(lifecycle_result(endOfLife="2027-12-01", daysRemaining=476))

    assert "support_days_left=476;;;;" in capsys.readouterr().out


def test_a_lapsed_support_window_is_negative_perfdata(capsys):
    """A negative value is the clearest possible 'you are overdue'."""
    run(lifecycle_result(state="endOfLife", endOfLife="2026-08-03", daysRemaining=-9))

    assert "support_days_left=-9;;;;" in capsys.readouterr().out


def test_no_lifecycle_section_means_no_lifecycle_line(capsys):
    """An old or partial result document must not break the output."""
    run(RESULT)

    output = capsys.readouterr().out
    assert "Release lifecycle" not in output
    assert "support_days_left" not in output


def test_an_unknown_lifecycle_reports_why(capsys):
    """Silence would look like a clean bill of health."""
    run(
        lifecycle_result(
            releaseType=None,
            state="unknown",
            reason="no release schedule available",
        )
    )

    assert "Release lifecycle: unknown (no release schedule available)" in capsys.readouterr().out


# --- certificate expiry ---
def tls_result(certificate):
    """A scan result carrying a tls section with the given certificate block."""
    return {**RESULT, "tls": {"host": "cloud.example.com", "certificate": certificate}}


def test_the_certificate_expiry_is_graphable(capsys):
    """
    The scan has always measured this; until now it only ever reached an
    operator as a finding, on the day the margin had already run out.
    """
    run(tls_result({"daysRemaining": 45}))

    assert "cert_days_left=45;" in capsys.readouterr().out


def test_an_expired_certificate_is_negative_perfdata(capsys):
    """Like support_days_left, the value keeps counting past zero."""
    run(tls_result({"daysRemaining": -3}))

    assert "cert_days_left=-3;" in capsys.readouterr().out


def test_the_certificate_thresholds_restate_the_scans_own_margin():
    """
    A second opinion invented for the graph would disagree with the alert
    printed beside it. '~' is the Nagios spelling of negative infinity.
    """
    context = ScanContext(host="h", scanner_settings=ScannerSettings(tls_min_days=21))

    perfdata = plugin._build_perfdata(
        5, plugin.RATE_MAP, 0, None, context=context, certificate_days_left=45
    )

    assert "cert_days_left=45;@~:21;@~:0;;" in perfdata


def test_a_certificate_metric_without_settings_carries_no_thresholds():
    """
    Better no threshold than a wrong one: without the settings the scan ran
    with there is nothing to say what margin it judged the certificate by.
    """
    perfdata = plugin._build_perfdata(
        5, plugin.RATE_MAP, 0, None, certificate_days_left=45
    )

    assert "cert_days_left=45;;@~:0;;" in perfdata


@pytest.mark.parametrize(
    "result",
    [
        RESULT,
        {**RESULT, "tls": None},
        {**RESULT, "tls": {"reachable": False, "certificate": None}},
        {**RESULT, "tls": {"certificate": {"daysRemaining": None}}},
    ],
    ids=["no tls block", "null tls", "no certificate", "unparsable dates"],
)
def test_an_unmeasured_certificate_is_absent_rather_than_zero(result, capsys):
    """
    A scan over plain HTTP measured no certificate. Reporting that as zero
    would page somebody about an expiry that was never observed.
    """
    run(result)

    assert "cert_days_left" not in capsys.readouterr().out
