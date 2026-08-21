"""
Integration tests for the built-in scanner.

A small HTTP server impersonates an OpenCloud instance so that the whole
scan path (status.php, capabilities, headers, exposed paths, protected
endpoints, extra checks) runs without touching the network.
"""

from __future__ import annotations

import http.server
import threading

import pytest

from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.scanner import (
    ScanError,
    ScannerSettings,
    _Probe,
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
    assert result["lifecycle"]["state"] == "supported"
    # Newer than every line on record can only be a rolling release, and the
    # default track asks the schedule rather than guessing - so it says so
    # instead of leaving the type blank.
    assert result["releaseType"] == "rolling"
    assert result["lifecycle"]["declaredTrack"] == "auto"


def test_a_release_newer_than_the_schedule_keeps_a_declared_track():
    """An operator who names a track is not overruled by the rolling guess."""
    settings = ScannerSettings(scheme="http", timeout=3, release_track="lts")

    result = scan_version("99.0.0", settings)

    assert result["EOL"] is False
    assert result["releaseType"] == "lts"
    assert result["lifecycle"]["declaredTrack"] == "lts"


def test_a_release_newer_than_the_schedule_says_the_schedule_is_stale():
    """
    The bundled schedule is a snapshot; OpenCloud keeps publishing patches
    after it was generated, so an instance patched promptly is routinely
    newer than the file it is compared against. The result document says so
    and points at the published lifecycle page, because a support window
    worked out from stale data is worth re-reading at its source.
    """
    result = scan_version("99.0.0")

    lifecycle = result["lifecycle"]
    assert lifecycle["scheduleStale"] is True
    assert "out of date" in lifecycle["scheduleNote"]
    assert lifecycle["scheduleSource"].startswith("https://docs.opencloud.eu/")
    assert lifecycle["scheduleUpdated"]


def test_being_newer_than_the_schedule_costs_the_instance_nothing():
    """
    The note is a remark about this project's own data, never a finding.

    An instance ahead of the bundled schedule must rate exactly as one the
    schedule knows about: same grade, no end-of-life verdict, no upgrade
    being recommended backwards. Anything else would punish an operator for
    patching faster than this package is released.
    """
    ahead = scan_version("99.0.0")
    known = scan_version("7.2.3")

    assert ahead["lifecycle"]["scheduleStale"] is True
    assert ahead["EOL"] is False
    assert ahead["rating"] >= known["rating"]
    assert ahead["lifecycle"]["upgradeTo"] is None
    assert ahead["latestVersionInBranch"] is not False
    # The negative half: a version the schedule does know about carries no
    # note at all, so the note means something when it does appear.
    assert known["lifecycle"]["scheduleStale"] is False
    assert known["lifecycle"]["scheduleNote"] is None


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


def test_an_owncloud_product_is_not_scanned_as_opencloud():
    """A legacy product's release data and hardenings must not get an OpenCloud verdict.

    ownCloud, its Infinite Scale name and Nextcloud serve the same status
    endpoint, but their release data and defaults are different products.
    """
    for product, field in (
        ("ownCloud", "productname"),
        ("Infinite Scale", "ProductName"),
        ("Nextcloud Hub", "product"),
    ):
        behaviour = InstanceBehaviour()
        behaviour.status_payload.pop("productname")
        behaviour.status_payload.pop("product")
        behaviour.status_payload[field] = product

        with pytest.raises(ScanError) as raised:
            run_scan(behaviour)

        assert product in str(raised.value)


def test_opencloud_itself_is_never_mistaken_for_one_of_them():
    """The negative case: 'opencloud' contains neither word, and must pass."""
    result = run_scan(InstanceBehaviour())

    assert result["product"] == "OpenCloud"


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


def test_a_refused_redirect_is_never_fetched():
    """
    The scanner asks before it follows, and reports the redirect it stopped at.

    Without this the address that was checked is only the first one: a target
    answering ``302 Location: http://127.0.0.1:.../`` would have the scan read
    whatever is listening there. The unfollowed 3xx is returned rather than an
    error, so a scan of an instance that redirects somewhere it may not go
    still has something to say about it.
    """
    fetched: list[str] = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            fetched.append(self.path)
            if self.path == "/hop":
                self.send_response(302)
                self.send_header("Location", "/secret")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", "6")
            self.end_headers()
            self.wfile.write(b"secret")

        def log_message(self, *args: object) -> None:
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        refusing = _Probe(
            base_url=base,
            settings=ScannerSettings(redirect_guard=lambda url: False),
        )
        stopped = refusing.get("/hop")
        assert stopped is not None
        assert stopped.status_code == 302
        assert fetched == ["/hop"]

        allowing = _Probe(
            base_url=base,
            settings=ScannerSettings(redirect_guard=lambda url: True),
        )
        followed = allowing.get("/hop")
        assert followed is not None
        assert followed.status_code == 200
        assert followed.text == "secret"
        assert fetched == ["/hop", "/hop", "/secret"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _check(result: dict, identifier: str) -> dict:
    """The one extra check with this id, so a test can read its severity."""
    matches = [
        entry for entry in result["extraChecks"] if entry["id"] == identifier
    ]
    assert len(matches) == 1, matches
    return matches[0]


def test_an_external_identity_provider_is_recognised_from_the_redirect_alone():
    """
    Knowing who signs users in is context the rest of the scan needs.

    It is read from the discovery document the instance publishes, or from
    where that redirects - the instance is never asked to authenticate
    anybody, because a scanner that tries logins is a scanner nobody should
    point at their server.
    """
    behaviour = InstanceBehaviour(
        openid_issuer="https://id.example.com/realms/opencloud",
        openid_redirect=True,
    )

    result = run_scan(behaviour)

    provider = result["identityProvider"]
    assert provider["detected"] is True
    assert provider["external"] is True
    assert provider["vendor"] == "Keycloak"
    assert provider["issuer"] == "https://id.example.com"
    # Nothing was posted, and no credential was offered anywhere.
    assert [entry for entry in behaviour.seen if entry[0] not in {"GET", "HEAD", "PROPFIND"}] == []
    assert not [entry for entry in behaviour.seen if "Authorization" in entry[2]]


def test_the_built_in_provider_is_not_reported_as_an_external_one():
    """
    An instance signing its own users in has not thereby failed anything.

    The check exists to recognise Keycloak, Authentik or Authelia in front of
    the instance; reading the built-in provider's own issuer as external would
    hand every default deployment the softer basic-auth rating it has not
    earned.
    """
    result = run_scan(InstanceBehaviour())

    provider = result["identityProvider"]
    assert provider["detected"] is True
    assert provider["external"] is False
    assert provider["vendor"] == ""

    without = run_scan(InstanceBehaviour(openid_configuration=False))
    assert without["identityProvider"]["detected"] is False
    assert without["identityProvider"]["external"] is False


def test_basic_auth_is_a_medium_finding_and_milder_behind_a_provider():
    """
    Basic auth is the only thing a CalDAV or WebDAV client can use.

    Rating it 'high' capped an otherwise healthy instance at 3 for running a
    calendar, which is a verdict operators were right to disbelieve. It stays
    a finding - a password does work on every request - but it costs a grade
    rather than two, and less again when an external provider handles the
    interactive login and basic auth is only the side door.
    """
    plain = run_scan(InstanceBehaviour(basic_auth=True))
    assert _check(plain, "basicAuthDisabled")["passed"] is False
    assert _check(plain, "basicAuthDisabled")["severity"] == "medium"
    assert plain["rating"] <= 4

    behind = run_scan(
        InstanceBehaviour(
            basic_auth=True,
            openid_issuer="https://auth.example.com/api/oidc",
        )
    )
    finding = _check(behind, "basicAuthDisabled")
    assert finding["passed"] is False
    assert finding["severity"] == "low"
    assert "Authelia" in finding["detail"]

    off = run_scan(InstanceBehaviour())
    assert _check(off, "basicAuthDisabled")["passed"] is True


def test_a_reverse_proxy_is_recognised_and_its_absence_costs_nothing():
    """
    Running behind a proxy is worth recording, and never finding one proves little.

    Traefik and HAProxy announce nothing at all, so a deployment doing exactly
    the right thing can look bare from outside. The check therefore reports
    what it saw at the lowest severity there is: it shows up in the output and
    leaves the grade alone.
    """
    behind = run_scan(InstanceBehaviour(server_header="nginx"))
    detected = _check(behind, "reverseProxyDetected")
    assert detected["passed"] is True
    assert behind["reverseProxy"]["vendor"] == "Nginx"

    forwarded = run_scan(InstanceBehaviour(extra_headers={"Via": "1.1 edge"}))
    assert _check(forwarded, "reverseProxyDetected")["passed"] is True

    bare = run_scan(InstanceBehaviour())
    missing = _check(bare, "reverseProxyDetected")
    assert missing["passed"] is False
    assert missing["severity"] == "low"
    assert bare["reverseProxy"]["detected"] is False
    # The whole point of 'low': the rating is the same either way.
    assert bare["rating"] == behind["rating"]


def test_an_instance_with_no_discoverable_provider_is_pointed_at_the_docs():
    """
    'No identity provider found' is only useful with somewhere to go next.

    It is usually a proxy that does not forward /.well-known/, and the
    catalogue entry is what turns the identifier into that sentence and a link
    to OpenCloud's own documentation.
    """
    from opencloud_local_scan import describe_hardening

    result = run_scan(InstanceBehaviour(openid_configuration=False))
    finding = _check(result, "identityProviderDetected")
    assert finding["passed"] is False
    assert finding["severity"] == "low"

    explained = describe_hardening("identityProviderDetected")
    assert "docs.opencloud.eu" in explained.reference
    assert "Keycloak" in explained.remediation

    found = run_scan(InstanceBehaviour())
    assert _check(found, "identityProviderDetected")["passed"] is True


def test_office_and_calendar_integrations_are_reported_as_observations():
    """
    What can be seen is reported; what cannot be seen is not guessed at.

    `/app/list` names the registered app providers and the CalDAV well-known
    path answers only when something is wired to it. Neither says the
    integration is *correctly* configured - that lives behind a login - so
    neither is a finding, and the result document says what was observed.
    """
    behaviour = InstanceBehaviour(app_providers=("Collabora",), caldav=True)
    behaviour.capabilities["ocs"]["data"]["capabilities"]["groupware"] = {
        "enabled": True
    }

    result = run_scan(behaviour)

    office = result["integrations"]["office"]
    assert office["detected"] is True
    assert office["apps"] == ["Collabora"]
    assert office["groupware"] is True
    assert result["integrations"]["calendar"]["detected"] is True

    # Neither becomes a check, so neither can hold the rating down.
    ids = {entry["id"] for entry in result["extraChecks"]}
    assert not [name for name in ids if "office" in name.lower()]
    assert not [name for name in ids if "calendar" in name.lower()]

    bare = run_scan(InstanceBehaviour())
    assert bare["integrations"]["office"]["detected"] is False
    assert bare["integrations"]["office"]["apps"] == []
    assert bare["integrations"]["calendar"]["detected"] is False
    assert bare["rating"] == result["rating"]
