"""
Integration tests for the built-in scanner.

A small HTTP server impersonates an OpenCloud instance so that the whole
scan path (status.php, capabilities, headers, exposed paths, protected
endpoints, extra checks) runs without touching the network.
"""

from __future__ import annotations

import pytest

from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.scanner import (
    ScanError,
    ScannerSettings,
    failed_extra_checks,
    scan,
)
from tests.fake_opencloud import DEFAULT_CSP_UNSAFE, FakeOpenCloud, InstanceBehaviour

# The fake instance speaks plain HTTP, and there is no point in looking up
# releases on GitHub from a test.
SETTINGS = ScannerSettings(
    scheme="http", timeout=3, check_debug_ports=False, include_bundled_db=True
)
NO_UPDATES = ReleaseSettings(mode="off")


def run_scan(behaviour: InstanceBehaviour, settings: ScannerSettings = SETTINGS) -> dict:
    """Start a fake instance, scan it and return the result document."""
    with FakeOpenCloud(behaviour) as instance:
        return scan(instance.host, settings=settings, release_settings=NO_UPDATES)


@pytest.fixture
def default_result() -> dict:
    """Result of scanning an instance with OpenCloud's default configuration."""
    return run_scan(InstanceBehaviour())


def test_reads_product_version_not_the_legacy_constant(default_result):
    """The real release lives in 'productversion'; 'version' is a fixed legacy value."""
    assert default_result["version"] == "7.2.3"
    assert default_result["legacyVersion"] == "0.1.0.0"
    assert default_result["product"] == "OpenCloud"
    assert default_result["edition"] == "stable"


def test_default_headers_are_recognised(default_result):
    """A stock OpenCloud sets every header the scanner looks for."""
    headers = default_result["setup"]["headers"]
    assert set(headers) >= {
        "Strict-Transport-Security",
        "Content-Security-Policy",
        "X-Content-Type-Options",
        "X-Frame-Options",
    }
    assert all(headers.values()), headers


def test_missing_headers_are_reported():
    """Stripping a header in front of the instance shows up in the result."""
    behaviour = InstanceBehaviour()
    behaviour.headers.pop("X-Content-Type-Options")
    behaviour.headers.pop("Referrer-Policy")

    result = run_scan(behaviour)

    headers = result["setup"]["headers"]
    assert headers["X-Content-Type-Options"] is False
    assert headers["Referrer-Policy"] is False
    assert headers["X-Frame-Options"] is True


def test_wrong_header_value_counts_as_missing():
    """A header that is present but useless is not a pass."""
    behaviour = InstanceBehaviour()
    behaviour.headers["X-Content-Type-Options"] = "maybe"

    result = run_scan(behaviour)

    assert result["setup"]["headers"]["X-Content-Type-Options"] is False


def test_capabilities_drive_the_hardening_block(default_result):
    """Public link policies are read from the capabilities document."""
    hardenings = default_result["hardenings"]
    assert default_result["capabilitiesAvailable"] is True
    assert hardenings["publicLinkPasswordEnforced"] is True
    assert hardenings["publicLinkExpirationEnforced"] is True
    assert hardenings["passwordPolicyEnforced"] is True


def test_capabilities_absent_does_not_invent_hardenings():
    """Without a capabilities document, capability-derived keys are omitted."""
    behaviour = InstanceBehaviour()
    behaviour.capabilities = None

    result = run_scan(behaviour)

    assert result["capabilitiesAvailable"] is False
    assert "publicLinkPasswordEnforced" not in result["hardenings"]
    # Header-derived hardenings are still there.
    assert "hstsLongMaxAge" in result["hardenings"]


def test_unsafe_inline_csp_is_flagged():
    """OpenCloud's default CSP allows inline scripts, which must be reported."""
    behaviour = InstanceBehaviour()
    behaviour.headers["Content-Security-Policy"] = DEFAULT_CSP_UNSAFE

    result = run_scan(behaviour)

    assert result["hardenings"]["cspWithoutUnsafeInline"] is False
    # The header itself is still present, so the setup block stays happy.
    assert result["setup"]["headers"]["Content-Security-Policy"] is True


def test_short_hsts_max_age_is_flagged():
    """An HSTS header below one year is present but not strong."""
    behaviour = InstanceBehaviour()
    behaviour.headers["Strict-Transport-Security"] = "max-age=300"

    result = run_scan(behaviour)

    assert result["setup"]["headers"]["Strict-Transport-Security"] is True
    assert result["hardenings"]["hstsLongMaxAge"] is False
    assert result["hardenings"]["hstsPreload"] is False


def test_basic_auth_challenge_is_detected():
    """PROXY_ENABLE_BASIC_AUTH is visible in the WWW-Authenticate header."""
    behaviour = InstanceBehaviour(basic_auth=True)

    result = run_scan(behaviour)

    assert result["hardenings"]["basicAuthDisabled"] is False
    assert "basicAuthDisabled" in failed_extra_checks(result)


def test_protected_endpoints_must_demand_authentication():
    """An endpoint that serves user data without a token is critical."""
    behaviour = InstanceBehaviour(unprotected=True)

    result = run_scan(behaviour)

    failures = failed_extra_checks(result)
    assert any(entry.startswith("authentication:") for entry in failures), failures
    assert result["rating"] <= 2


def test_exposed_configuration_file_is_critical():
    """A reverse proxy publishing opencloud.yaml is the worst case."""
    behaviour = InstanceBehaviour(exposed_paths={"/opencloud.yaml"})

    result = run_scan(behaviour)

    assert "exposed:/opencloud.yaml" in failed_extra_checks(result)
    assert result["rating"] <= 2


def test_catch_all_spa_does_not_create_false_positives():
    """
    The OpenCloud web UI answers unknown paths with its app shell.

    Without the catch-all probe every single 'exposed path' check would
    report a hit, so this is the most important false-positive guard.
    """
    behaviour = InstanceBehaviour(catch_all=True)

    result = run_scan(behaviour)

    exposures = [
        entry for entry in failed_extra_checks(result) if entry.startswith("exposed:")
    ]
    assert exposures == []


def test_debug_endpoint_on_the_public_port_is_reported():
    """/metrics leaks the build version and must not be public."""
    behaviour = InstanceBehaviour(debug_endpoints=True)

    result = run_scan(behaviour)

    failures = failed_extra_checks(result)
    assert any(entry.startswith("debugEndpoint:") for entry in failures), failures


def test_directory_listing_is_reported():
    """An Apache-style index means the deployment directory is served raw."""
    behaviour = InstanceBehaviour(directory_listing=True)

    result = run_scan(behaviour)

    assert "directoryListing" in failed_extra_checks(result)


def test_server_disclosure_is_reported():
    """X-Powered-By tells an attacker what to attack."""
    behaviour = InstanceBehaviour(disclose_server="PHP/8.2.1")

    result = run_scan(behaviour)

    assert "versionDisclosure:X-Powered-By" in failed_extra_checks(result)


def test_webfinger_version_disclosure_is_reported():
    """Publishing the release through webfinger is a mild disclosure."""
    behaviour = InstanceBehaviour(webfinger_version=True)

    result = run_scan(behaviour)

    assert "webfingerVersionDisclosure" in failed_extra_checks(result)


def test_plain_http_is_reported_as_not_enforced(default_result):
    """The fake instance speaks HTTP only, which must never look fine."""
    assert default_result["setup"]["https"]["used"] is False
    assert default_result["setup"]["https"]["enforced"] is False


def scan_version(version: str, settings: ScannerSettings = SETTINGS) -> dict:
    """Scan a fake instance that claims to run a particular release."""
    behaviour = InstanceBehaviour()
    behaviour.status_payload["productversion"] = version
    return run_scan(behaviour, settings)


def test_a_superseded_rolling_release_rates_f():
    """A rolling release stops receiving fixes when its successor lands."""
    result = scan_version("3.5.0")

    assert result["EOL"] is True
    assert result["rating"] == 0
    assert result["releaseType"] == "rolling"


def test_the_current_production_release_is_not_end_of_life(default_result):
    """7.2.3 is the production release, whatever the rolling track is up to."""
    assert default_result["EOL"] is False
    assert default_result["releaseType"] == "production"
    assert default_result["lifecycle"]["state"] == "supported"


def test_an_lts_release_is_supported_after_its_production_window():
    """4.0 stopped being the production release but keeps its backports."""
    result = scan_version("4.0.8")

    assert result["EOL"] is False
    assert result["releaseType"] == "lts"
    assert result["lifecycle"]["endOfLife"] == "2027-12-01"


def test_a_rolling_release_of_an_lts_major_gets_no_lts_treatment():
    """4.1 was a rolling release; sharing a major with 4.0 changes nothing."""
    result = scan_version("4.1.0")

    assert result["releaseType"] == "rolling"
    assert result["EOL"] is True


def test_the_release_schedule_can_be_switched_off():
    """--no-release-schedule leaves the verdict to the other checks."""
    settings = ScannerSettings(
        scheme="http",
        timeout=3,
        check_debug_ports=False,
        use_release_schedule=False,
    )

    result = scan_version("3.5.0", settings)

    assert result["EOL"] is False
    # The lifecycle is still reported, it just no longer drives the rating.
    assert result["lifecycle"]["state"] == "endOfLife"


def test_a_release_newer_than_the_schedule_is_not_end_of_life():
    """The bundled schedule ages; a fresh release must not trip the alarm."""
    result = scan_version("99.0.0")

    assert result["EOL"] is False
    assert result["releaseType"] is None


def test_extra_checks_can_be_switched_off():
    """--no-extra-checks reduces the scan to product, version and headers."""
    settings = ScannerSettings(scheme="http", timeout=3, extra_checks=False)

    result = run_scan(InstanceBehaviour(), settings)

    assert result["extraChecks"] == []
    assert result["version"] == "7.2.3"
    assert result["setup"]["headers"]


def test_extra_checks_can_be_excluded_from_the_rating():
    """Findings may be reported without influencing the rating."""
    behaviour = InstanceBehaviour(exposed_paths={"/opencloud.yaml"})
    settings = ScannerSettings(
        scheme="http",
        timeout=3,
        check_debug_ports=False,
        extra_checks_affect_rating=False,
    )

    result = run_scan(behaviour, settings)

    assert "exposed:/opencloud.yaml" in failed_extra_checks(result)
    assert result["rating"] == 5


def test_non_opencloud_target_raises_scan_error():
    """Something that is not an OpenCloud cannot be rated."""
    behaviour = InstanceBehaviour(status_body=b"<html>nginx</html>")

    with pytest.raises(ScanError):
        run_scan(behaviour)


def test_unreachable_host_raises_scan_error():
    """A closed port is a scan failure, not a rating of F."""
    with FakeOpenCloud() as instance:
        port = instance.port
    # The server is gone now, so nothing listens on that port any more.
    with pytest.raises(ScanError):
        scan(f"127.0.0.1:{port}", settings=SETTINGS, release_settings=NO_UPDATES)


def test_result_document_carries_the_expected_keys(default_result):
    """The document shape is part of the contract with the plugin."""
    assert set(default_result) >= {
        "domain",
        "url",
        "product",
        "version",
        "legacyVersion",
        "scannedAt",
        "rating",
        "EOL",
        "releaseType",
        "lifecycle",
        "vulnerabilities",
        "hardenings",
        "setup",
        "updates",
        "extraChecks",
        "capabilitiesAvailable",
    }
    assert default_result["scannedAt"]["timezone"] == "UTC"


def test_failed_extra_checks_are_sorted_by_severity():
    """The worst finding must be the one an operator sees first."""
    behaviour = InstanceBehaviour(
        exposed_paths={"/opencloud.yaml"}, disclose_server="PHP/8.2.1"
    )

    result = run_scan(behaviour)
    failures = failed_extra_checks(result)

    assert failures.index("exposed:/opencloud.yaml") < failures.index(
        "versionDisclosure:X-Powered-By"
    )
