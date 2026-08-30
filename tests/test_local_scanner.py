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
import requests

import opencloud_local_scan.scanner as scanner_module
from opencloud_local_scan.releases import ReleaseSettings
from opencloud_local_scan.scanner import (
    ScanError,
    ScannerSettings,
    _Probe,
    failed_extra_checks,
    scan,
)
from opencloud_local_scan.tls import Certificate
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


def test_an_instance_below_a_subfolder_is_probed_below_that_base_path():
    """Every known endpoint must stay below the deployment prefix."""
    behaviour = InstanceBehaviour(base_path="/opencloud")

    with FakeOpenCloud(behaviour) as instance:
        result = scan(
            f"{instance.host}/opencloud",
            settings=SETTINGS,
            release_settings=NO_UPDATES,
        )

    assert result["product"] == "OpenCloud"
    requested = {path for _, path, _ in behaviour.seen}
    assert "/opencloud/status.php" in requested
    assert "/status.php" not in requested
    assert all(path.startswith("/opencloud") for path in requested)


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


def test_a_disabled_password_policy_is_reported_instead_of_disappearing():
    """Turning the policy off must fail more loudly than lowering its minimum."""
    behaviour = InstanceBehaviour()
    policy = behaviour.capabilities["ocs"]["data"]["capabilities"]["password_policy"]
    policy.clear()
    policy["max_characters"] = 72

    result = run_scan(behaviour)

    assert result["hardenings"]["passwordPolicyEnforced"] is False

    unknown = InstanceBehaviour()
    unknown.capabilities["ocs"]["data"]["capabilities"]["password_policy"].clear()
    unknown_result = run_scan(unknown)
    assert "passwordPolicyEnforced" not in unknown_result["hardenings"]


def test_unsafe_web_embed_origins_are_failed_and_safe_defaults_pass():
    """An iframe must not choose where delegated credentials are accepted from."""
    unsafe = run_scan(
        InstanceBehaviour(
            web_config={
                "options": {
                    "embed": {
                        "messagesOrigin": "*",
                        "delegateAuthentication": True,
                    }
                }
            }
        )
    )
    safe = run_scan(InstanceBehaviour())

    wildcard = _check(unsafe, "webEmbedMessageOriginRestricted")
    delegated = _check(unsafe, "webEmbedDelegatedAuthenticationRestricted")
    assert wildcard["passed"] is False
    assert wildcard["severity"] == "high"
    assert delegated["passed"] is False
    assert delegated["severity"] == "critical"
    assert _check(safe, "webEmbedMessageOriginRestricted")["passed"] is True
    assert _check(safe, "webEmbedDelegatedAuthenticationRestricted")["passed"] is True


def test_a_matching_opencloud_backend_on_the_direct_port_is_reported(monkeypatch):
    """A reverse proxy must not be bypassable through its private listener."""
    settings = ScannerSettings(
        scheme="http",
        timeout=3,
        check_debug_ports=True,
        debug_port_timeout=1,
        include_bundled_db=True,
    )
    with FakeOpenCloud(InstanceBehaviour(base_path="/opencloud")) as public, FakeOpenCloud(
        InstanceBehaviour()
    ) as backend:
        monkeypatch.setattr(scanner_module, "BACKEND_PORT", backend.port)
        exposed = scan(
            f"{public.host}/opencloud",
            settings=settings,
            release_settings=NO_UPDATES,
        )

    finding = _check(exposed, "backendPortClosed")
    assert finding["passed"] is False
    assert finding["severity"] == "high"

    with FakeOpenCloud(InstanceBehaviour()) as public:
        monkeypatch.setattr(scanner_module, "BACKEND_PORT", backend.port)
        closed = scan(
            public.host,
            settings=settings,
            release_settings=NO_UPDATES,
        )
    assert _check(closed, "backendPortClosed")["passed"] is True


def test_debug_ports_use_the_validated_address_pin(monkeypatch):
    """Enabling optional port probes must not reopen DNS rebinding."""
    dialled: list[tuple[str, int]] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    def connect(address, timeout):
        dialled.append(address)
        return Connection()

    monkeypatch.setattr(scanner_module.socket, "create_connection", connect)
    settings = ScannerSettings(
        check_debug_ports=True,
        debug_ports=(9205,),
        pinned_addresses=(("opencloud.example.com", ("192.0.2.10",)),),
    )

    findings = scanner_module._debug_port_findings(
        "opencloud.example.com", settings
    )

    assert dialled == [("192.0.2.10", 9205)]
    assert findings[0].passed is False


def test_unsafe_inline_csp_is_flagged():
    """OpenCloud's default CSP allows inline scripts, which must be reported."""
    behaviour = InstanceBehaviour()
    behaviour.headers["Content-Security-Policy"] = DEFAULT_CSP_UNSAFE

    result = run_scan(behaviour)

    assert result["hardenings"]["cspWithoutUnsafeInline"] is False
    # The header itself is still present, so the setup block stays happy.
    assert result["setup"]["headers"]["Content-Security-Policy"] is True


def test_unsafe_eval_csp_is_flagged():
    """'unsafe-eval' undoes CSP protection just as 'unsafe-inline' does."""
    behaviour = InstanceBehaviour()
    behaviour.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self' 'unsafe-eval'; style-src 'self'"
    )

    result = run_scan(behaviour)

    assert result["hardenings"]["cspWithoutUnsafeInline"] is False


def test_nonce_neutralised_unsafe_inline_is_not_flagged():
    """
    A nonce alongside 'unsafe-inline' is the standard strict-dynamic pattern.

    Every browser that understands nonces ignores 'unsafe-inline' when one is
    present, so 'unsafe-inline' there is a fallback for pre-CSP2 browsers,
    not a real weakening of the policy, and must not be flagged.
    """
    behaviour = InstanceBehaviour()
    behaviour.headers["Content-Security-Policy"] = (
        "default-src 'none'; "
        "script-src 'nonce-xyz123' 'strict-dynamic' 'unsafe-inline' https:; "
        "style-src 'self'"
    )

    result = run_scan(behaviour)

    assert result["hardenings"]["cspWithoutUnsafeInline"] is True


def test_hash_neutralised_unsafe_inline_is_not_flagged():
    """A hash-source in script-src neutralises 'unsafe-inline' just like a nonce."""
    behaviour = InstanceBehaviour()
    behaviour.headers["Content-Security-Policy"] = (
        "default-src 'none'; "
        "script-src 'sha256-abc123' 'unsafe-inline'; style-src 'self'"
    )

    result = run_scan(behaviour)

    assert result["hardenings"]["cspWithoutUnsafeInline"] is True


def test_unsafe_eval_is_still_flagged_alongside_a_nonce():
    """A nonce neutralises 'unsafe-inline', not 'unsafe-eval'."""
    behaviour = InstanceBehaviour()
    behaviour.headers["Content-Security-Policy"] = (
        "default-src 'none'; "
        "script-src 'nonce-xyz123' 'strict-dynamic' 'unsafe-eval'; style-src 'self'"
    )

    result = run_scan(behaviour)

    assert result["hardenings"]["cspWithoutUnsafeInline"] is False


def test_style_only_unsafe_inline_does_not_flag_the_script_check():
    """
    'unsafe-inline' in style-src is not a script-execution weakness.

    Without an explicit script-src, CSP falls back to default-src to govern
    scripts - a naive substring search over the whole header would wrongly
    catch style-src's 'unsafe-inline' too, which is a false positive.
    """
    behaviour = InstanceBehaviour()
    behaviour.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'"
    )

    result = run_scan(behaviour)

    assert result["hardenings"]["cspWithoutUnsafeInline"] is True


def test_csp_frame_ancestors_satisfies_the_clickjacking_check():
    """
    A CSP 'frame-ancestors' directive is a recognised X-Frame-Options alternative.

    Modern browsers honour 'frame-ancestors' over X-Frame-Options, and the
    hardening catalogue already documents it as an accepted substitute, so
    the scanner must not raise a false clickjacking alarm when it is present.
    """
    behaviour = InstanceBehaviour()
    del behaviour.headers["X-Frame-Options"]
    behaviour.headers["Content-Security-Policy"] = (
        "default-src 'self'; frame-ancestors 'self'"
    )

    result = run_scan(behaviour)

    assert result["setup"]["headers"]["X-Frame-Options"] is True


def test_wildcard_frame_ancestors_does_not_satisfy_the_clickjacking_check():
    """'frame-ancestors *' allows framing from anywhere, so it is not a pass."""
    behaviour = InstanceBehaviour()
    del behaviour.headers["X-Frame-Options"]
    behaviour.headers["Content-Security-Policy"] = (
        "default-src 'self'; frame-ancestors *"
    )

    result = run_scan(behaviour)

    assert result["setup"]["headers"]["X-Frame-Options"] is False


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
    # Nothing was posted, and no credential was offered anywhere. TRACE joins
    # the list because RFC 9110 defines it as a safe method: it echoes the
    # request back and changes nothing, which is exactly why asking whether it
    # is answered costs the instance nothing.
    assert [
        entry
        for entry in behaviour.seen
        if entry[0] not in {"GET", "HEAD", "PROPFIND", "TRACE"}
    ] == []
    assert not [entry for entry in behaviour.seen if "Authorization" in entry[2]]


@pytest.mark.parametrize(
    ("issuer", "vendor", "advisory_url"),
    [
        (
            "https://id.example.com/realms/opencloud",
            "Keycloak",
            "https://github.com/keycloak/keycloak/security/advisories",
        ),
        (
            "https://id.example.com/api/oidc",
            "Authelia",
            "https://github.com/authelia/authelia/security/advisories",
        ),
        (
            "https://id.example.com/application/o/opencloud/",
            "Authentik",
            "https://github.com/goauthentik/authentik/security/advisories",
        ),
    ],
)
def test_recognised_identity_providers_point_to_their_official_advisories(
    issuer: str, vendor: str, advisory_url: str
):
    """Operators need a current upstream database without a guessed version."""
    result = run_scan(
        InstanceBehaviour(openid_issuer=issuer, openid_redirect=True)
    )

    provider = result["identityProvider"]
    assert provider["vendor"] == vendor
    assert provider["advisoryUrl"] == advisory_url
    assert provider["version"] == ""


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


def _closed_sessions(monkeypatch) -> list[requests.Session]:
    """Every session whose close() ran, recorded as it happens."""
    closed: list[requests.Session] = []
    original = requests.Session.close

    def record(self) -> None:
        closed.append(self)
        original(self)

    monkeypatch.setattr(requests.Session, "close", record)
    return closed


def _probes(monkeypatch) -> list:
    """Every probe the scan opened, captured where the scan makes it."""
    seen = []
    original = scanner_module._open_instance

    def record(host, settings):
        opened = original(host, settings)
        seen.append(opened[0])
        return opened

    monkeypatch.setattr(scanner_module, "_open_instance", record)
    return seen


def test_a_scan_closes_every_connection_it_opened(monkeypatch):
    """
    A pooled connection outliving the scan is a socket held for no reason.

    Over a fleet that is one per host, kept until the collector happens to run,
    and where the instance has gone away in the meantime the response still in
    the pool is finalised against a socket somebody else already closed - which
    surfaces as an ignored exception from a destructor, attributed to whatever
    unrelated code was running at the time.
    """
    closed = _closed_sessions(monkeypatch)
    probes = _probes(monkeypatch)

    run_scan(InstanceBehaviour())

    assert probes, "the scan opened no probe at all"
    assert closed, "the scan closed no session at all"
    assert probes[0].session in closed
    # The probe has let go of them too, so a second close is a no-op rather
    # than a second round of work on sessions somebody may have replaced.
    assert probes[0]._opened == []


def test_a_scan_that_fails_partway_still_closes_its_connections(monkeypatch):
    """
    The negative half: the close must not depend on reaching the last line.

    A `finally` is the whole point - an exception raised anywhere in the scan
    is exactly when a leaked socket is least likely to be noticed.
    """
    closed = _closed_sessions(monkeypatch)
    probes = _probes(monkeypatch)

    def explode(_result):
        raise RuntimeError("remediation planning blew up")

    monkeypatch.setattr(scanner_module, "remediation_plan", explode)

    with pytest.raises(RuntimeError):
        run_scan(InstanceBehaviour())

    assert probes
    assert probes[0].session in closed
    assert probes[0]._opened == []


# ------------------------------------- the discovery document, rated --------
# The scan already fetches /.well-known/openid-configuration to work out who
# signs users in, and used to read one field out of it. These check the rest,
# and above all that a field the document does not publish stays an unknown:
# OpenCloud's own provider omits several of them.

EXTERNAL_KEYCLOAK = "https://id.example.com/realms/opencloud"


def _hardening(result: dict, identifier: str):
    """What the scan concluded about one hardening, or None if it said nothing."""
    return result["hardenings"].get(identifier)


def test_pkce_is_rated_only_when_the_provider_says_whether_it_offers_it():
    """
    OpenCloud's built-in provider publishes no code_challenge_methods at all.

    Reading that absence as "PKCE is missing" would fail every stock instance
    for something its operator cannot change, which is the opposite of what
    the flag is for. The secure-deployment guide tells operators to require
    S256 on an external provider; this is what finally checks that they did.
    """
    offered = run_scan(
        InstanceBehaviour(
            openid_issuer=EXTERNAL_KEYCLOAK,
            openid_code_challenge_methods=("S256", "plain"),
        )
    )
    assert _hardening(offered, "oidcPkceSupported") is True

    # 'plain' is not PKCE worth having: the verifier travels in clear.
    weak = run_scan(
        InstanceBehaviour(
            openid_issuer=EXTERNAL_KEYCLOAK, openid_code_challenge_methods=("plain",)
        )
    )
    assert _hardening(weak, "oidcPkceSupported") is False

    # The negative half: no key published, no finding either way.
    silent = run_scan(InstanceBehaviour(openid_issuer=EXTERNAL_KEYCLOAK))
    assert "oidcPkceSupported" not in silent["hardenings"]


def test_the_implicit_flow_is_rated_for_an_external_provider_only():
    """
    The built-in provider offers implicit response types and cannot be changed.

    libregraph/lico publishes 'id_token token' and 'id_token' in
    response_types_supported, so rating every instance on this would mark down
    a stock OpenCloud for its own shipped provider. Against Keycloak, where
    Standard and Implicit really are separate switches, it is actionable.
    """
    implicit = run_scan(
        InstanceBehaviour(
            openid_issuer=EXTERNAL_KEYCLOAK,
            openid_response_types=("code", "id_token token"),
        )
    )
    assert _hardening(implicit, "oidcImplicitFlowDisabled") is False

    code_only = run_scan(
        InstanceBehaviour(
            openid_issuer=EXTERNAL_KEYCLOAK, openid_response_types=("code",)
        )
    )
    assert _hardening(code_only, "oidcImplicitFlowDisabled") is True

    # The negative half: the same document from the instance's own provider
    # produces no finding, however loudly it advertises the implicit flow.
    built_in = run_scan(
        InstanceBehaviour(openid_response_types=("id_token token", "id_token"))
    )
    assert built_in["identityProvider"]["external"] is False
    assert "oidcImplicitFlowDisabled" not in built_in["hardenings"]


@pytest.mark.parametrize(
    ("algorithms", "expected"),
    [
        (("PS256",), True),
        (("RS256", "ES256"), True),
        (("RS256", "none"), False),
        (("HS256",), False),
        (("PS256", "HS512"), False),
    ],
)
def test_an_id_token_signing_algorithm_is_rated_on_what_can_forge_a_token(
    algorithms: tuple[str, ...], expected: bool
):
    """
    'none' means anybody can write an ID token; HS means the client secret can.

    An HMAC algorithm signs with the secret rather than a private key, and
    OpenCloud's clients are public clients that cannot keep one - so every
    party holding it can mint a token for any user. PS256, which OpenCloud's
    built-in provider uses, passes.
    """
    result = run_scan(
        InstanceBehaviour(
            openid_issuer=EXTERNAL_KEYCLOAK, openid_signing_algorithms=algorithms
        )
    )

    assert _hardening(result, "oidcSigningAlgorithmStrong") is expected


def test_an_http_endpoint_is_rated_only_when_the_instance_itself_was_https():
    """
    An instance scanned over plain HTTP publishes http:// because it was asked to.

    Reporting that would restate what setup.https already says, once, in the
    right place. The finding worth having is the disagreement: an HTTPS
    instance whose provider still advertises http://, which is a provider
    behind a terminating proxy that was never told its public URL.
    """
    # The fake instance speaks plain HTTP, so nothing is measured at all.
    plaintext = run_scan(InstanceBehaviour(openid_insecure_endpoints=True))
    assert "oidcEndpointsUseHttps" not in plaintext["hardenings"]
    assert plaintext["setup"]["https"]["used"] is False

    # The positive half, which the fake instance cannot serve because it has
    # no TLS: the same document read over HTTPS does produce the finding.
    document = {
        "issuer": "https://id.example.com",
        "authorization_endpoint": "https://id.example.com/authorize",
        "token_endpoint": "http://id.example.com/token",
    }
    provider = {
        "detected": True,
        "external": True,
        "metadata": scanner_module._openid_metadata(document, over_https=True),
    }
    assert scanner_module._openid_hardenings(provider)["oidcEndpointsUseHttps"] is False

    secure = dict(document, token_endpoint="https://id.example.com/token")
    provider["metadata"] = scanner_module._openid_metadata(secure, over_https=True)
    assert scanner_module._openid_hardenings(provider)["oidcEndpointsUseHttps"] is True


def test_the_discovery_document_is_read_without_a_second_request():
    """
    These flags were the point of ADR 0022's bar: public evidence, already paid for.

    The scan fetched /.well-known/openid-configuration once to find the issuer
    long before it rated any of this, and adding four findings must not add a
    request - so the count of times the instance was asked stays at one.
    """
    behaviour = InstanceBehaviour(
        openid_issuer=EXTERNAL_KEYCLOAK,
        openid_code_challenge_methods=("S256",),
        openid_signing_algorithms=("PS256",),
    )

    result = run_scan(behaviour)

    asked = [
        entry
        for entry in behaviour.seen
        if entry[1] == "/.well-known/openid-configuration"
    ]
    assert len(asked) == 1
    assert _hardening(result, "oidcPkceSupported") is True


def test_the_documented_demo_accounts_fail_the_scan_critically():
    """
    An admin account with a password out of the manual is the worst finding there is.

    IDM_CREATE_DEMO_USERS leaves 'dennis' - an administrator - reachable with
    the password 'demo'. It has to be critical, and it has to fail: a warning
    that does not cap the rating would let an instance anybody can log into as
    an admin still be graded well.
    """
    from opencloud_local_scan import describe_hardening

    result = run_scan(InstanceBehaviour(demo_users=True))
    finding = _check(result, "demoUsersDisabled")
    assert finding["passed"] is False
    assert finding["severity"] == "critical"
    assert "dennis" in finding["detail"]
    assert "demoUsersDisabled" in failed_extra_checks(result)
    assert result["rating"] <= 2

    explained = describe_hardening("demoUsersDisabled")
    assert explained.setting == "IDM_CREATE_DEMO_USERS"
    assert "docs.opencloud.eu" in explained.reference


def test_an_instance_without_demo_accounts_passes_the_check():
    """
    The check has to be able to say 'no', or it says nothing.

    A rejected login is the evidence the scan came for, so an instance that
    refuses every documented pair passes rather than being left unrated.
    """
    result = run_scan(InstanceBehaviour())
    finding = _check(result, "demoUsersDisabled")
    assert finding["passed"] is True
    assert "demoUsersDisabled" not in failed_extra_checks(result)


def test_demo_credentials_are_only_ever_sent_to_the_instances_own_provider():
    """
    Logins belong to whoever signs users in, and only OpenCloud's own IDM has demo users.

    With an external provider the accounts come from there, so the check has
    nothing to look for and must not push logins at somebody's Keycloak. The
    finding disappears entirely rather than passing quietly.
    """
    behaviour = InstanceBehaviour(
        demo_users=True, openid_issuer="https://auth.example.com/realms/opencloud"
    )
    result = run_scan(behaviour)
    assert [entry for entry in result["extraChecks"] if entry["id"] == "demoUsersDisabled"] == []
    assert not any(
        "Authorization" in headers for _, _, headers in behaviour.seen
    ), behaviour.seen

    internal = InstanceBehaviour(demo_users=True)
    run_scan(internal)
    assert any("Authorization" in headers for _, _, headers in internal.seen)


def test_a_wide_open_endpoint_does_not_invent_a_demo_user():
    """
    An instance answering everybody proves nothing about the credentials sent.

    Reporting demo accounts because an unauthenticated request also succeeds
    would turn one broken proxy into a false accusation of an admin password
    leak; the missing authentication is reported by its own check instead.
    """
    result = run_scan(InstanceBehaviour(unprotected=True))
    finding = _check(result, "demoUsersDisabled")
    assert finding["passed"] is True
    assert "without authentication" in finding["detail"]
    assert any(
        name.startswith("authentication:") for name in failed_extra_checks(result)
    )


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


def test_the_result_document_names_the_addresses_the_name_resolved_to():
    """
    'It answers on the wrong address' explains a surprising number of surprises.

    A scan judges whatever the name pointed at while it ran, so the document
    records that pair rather than leaving the reader to resolve it again later
    and possibly get a different answer.
    """
    result = run_scan(InstanceBehaviour())

    assert result["addresses"]["ipv4"] == ["127.0.0.1"]
    # The negative half: an instance with no AAAA record must not grow one.
    assert result["addresses"]["ipv6"] == []


def test_pinned_addresses_win_over_a_second_lookup():
    """
    The web application dials the addresses it validated, so those are the ones to report.

    Resolving again here could name an address the scan never connected to -
    which is exactly the confusion the block exists to remove - and a name
    that does not resolve at all must leave the scan reporting nothing rather
    than failing.
    """
    from opencloud_local_scan.scanner import _resolved_addresses

    pinned = ScannerSettings(
        pinned_addresses=(
            ("opencloud.example.com", ("198.51.100.7", "2001:db8::7", "198.51.100.7")),
        )
    )
    assert _resolved_addresses("opencloud.example.com", pinned) == {
        "ipv4": ["198.51.100.7"],
        "ipv6": ["2001:db8::7"],
    }
    # A different name is not covered by that pin and is looked up normally;
    # one that cannot be looked up is empty rather than an error.
    assert _resolved_addresses("nothing.invalid", pinned) == {"ipv4": [], "ipv6": []}


def test_observed_cookies_must_carry_security_attributes():
    """The scanner must judge only cookies a public response actually set."""
    result = run_scan(
        InstanceBehaviour(extra_headers={"Set-Cookie": "session=opaque; Path=/"})
    )
    findings = {entry["id"]: entry for entry in result["extraChecks"]}

    assert findings["cookieSecure"]["passed"] is False
    assert findings["cookieHttpOnly"]["passed"] is False
    assert findings["cookieSameSite"]["passed"] is False


def test_address_parity_compares_the_tls_identity_from_both_dns_families():
    """An IPv6 listener must not quietly lag behind the IPv4 TLS deployment."""
    certificate = Certificate(serial="same")
    ipv4 = scanner_module.TlsInspection(
        host="opencloud.example.com",
        port=443,
        reachable=True,
        protocol="TLSv1.3",
        cipher="TLS_AES_256_GCM_SHA384",
        trusted=True,
        certificate=certificate,
    )
    ipv6 = scanner_module.TlsInspection(
        host="opencloud.example.com",
        port=443,
        reachable=True,
        protocol="TLSv1.2",
        cipher="ECDHE-RSA-AES256-GCM-SHA384",
        trusted=True,
        certificate=certificate,
    )

    finding = scanner_module._address_parity_finding({"ipv4": ipv4, "ipv6": ipv6})

    assert finding is not None
    assert finding.passed is False
    assert "protocol" in finding.detail


def test_the_parity_probe_does_not_run_without_ipv6_of_its_own():
    """
    A scanner with no IPv6 route cannot reach an instance's IPv6 address at
    all, so dialling it would only time out - and penalise the instance for a
    limitation of the deployment running the scan.
    """
    addresses = {"ipv4": ["198.51.100.7"], "ipv6": ["2001:db8::7"]}

    assert scanner_module._address_parity_may_run(
        ScannerSettings(ipv6_enabled=True), addresses
    )
    assert not scanner_module._address_parity_may_run(
        ScannerSettings(ipv6_enabled=False), addresses
    )
    # Nothing to compare either way when the name has no AAAA record.
    assert not scanner_module._address_parity_may_run(
        ScannerSettings(ipv6_enabled=True), {"ipv4": ["198.51.100.7"], "ipv6": []}
    )


def test_the_result_document_reports_whether_ipv6_was_available_to_check_with():
    """The dashboard needs this to explain why the parity check is missing."""
    default = run_scan(InstanceBehaviour())
    assert default["ipv6Enabled"] is True

    settings = ScannerSettings(
        scheme="http", timeout=3, check_debug_ports=False, ipv6_enabled=False
    )
    disabled = run_scan(InstanceBehaviour(), settings=settings)
    assert disabled["ipv6Enabled"] is False


def test_a_weakened_password_policy_is_caught_even_when_it_is_long_enough(
    default_result,
):
    """
    Length alone is not a password policy.

    OpenCloud requires one lowercase, one uppercase, one digit and one special
    character by default, so an instance reporting zero for any of them had
    that lowered deliberately - and a twelve-character minimum that accepts
    'aaaaaaaaaaaa' would otherwise pass every check this scanner makes.
    """
    assert default_result["hardenings"]["passwordPolicyComplexity"] is True

    weakened = InstanceBehaviour()
    policy = weakened.capabilities["ocs"]["data"]["capabilities"]["password_policy"]
    policy["min_special_characters"] = 0

    result = run_scan(weakened)

    assert result["hardenings"]["passwordPolicyComplexity"] is False
    # The length requirement is untouched, so the older flag still passes:
    # the two findings must not collapse into one.
    assert result["hardenings"]["passwordPolicyEnforced"] is True


def test_a_policy_that_publishes_no_character_classes_reports_no_complexity_finding():
    """
    A disabled policy publishes only max_characters, and that is a different
    finding.

    Reporting an absent measurement as a failure would give every instance
    running a release that stops publishing the minimums a permanent warning
    no setting could clear.
    """
    disabled = InstanceBehaviour()
    policy = disabled.capabilities["ocs"]["data"]["capabilities"]["password_policy"]
    policy.clear()
    policy["max_characters"] = 72

    result = run_scan(disabled)

    assert "passwordPolicyComplexity" not in result["hardenings"]
    assert result["hardenings"]["passwordPolicyEnforced"] is False
