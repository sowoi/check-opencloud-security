"""
The public API of the web application: what it accepts, and what it refuses.

These tests are the security boundary written down. Each one names a way the
service could leak somebody else's scan, be talked into scanning an internal
address, or be handed a knob it does not offer, and pins the answer.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from opencloud_local_scan import ScannerSettings, __version__
from opencloud_local_scan.versions import load_release_schedule
from opencloud_local_scan.vulndb import load_database
from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    backend,
    client,
    settings,
)
from webapp.app import is_safe_link
from webapp.redis_backend import RedisUnavailable
from webapp.runner import scanner_settings_for
from webapp.ssrf import redirect_guard, validate_target
from webapp.store import (
    QUEUE_KEY,
    WORKER_HEARTBEAT_KEY,
    is_scan_uuid,
    result_key,
    status_key,
)


def _create(test_client, target: str = "https://opencloud.example.com", **body):
    payload = {"target_url": target}
    payload.update(body)
    return test_client.post("/api/scans", json=payload)


def test_the_landing_page_offers_the_form_and_the_privacy_promises():
    """The pitch is the product: a visitor has to see what is kept before they type."""
    page = client().get("/")

    assert page.status_code == 200
    body = page.text
    assert 'name="target_url"' in body
    assert 'name="ignore_hardenings"' in body
    for promise in ("air-gapped", "No data stored", "No registration needed", "Ephemeral"):
        assert promise in body
    # A form that offers a concurrency field would make the prohibition a lie.
    assert 'name="concurrency"' not in body
    assert 'name="threads"' not in body


def test_a_submission_is_accepted_queued_and_redirected(monkeypatch):
    """
    The happy path: one POST, one uuid, one redirect, and no scan yet.

    The state has to be observable as 'queued' before a worker touches it,
    because that is what the progress page shows first.
    """
    test_client = client()
    response = test_client.post(
        "/api/scans",
        data={"target_url": "https://opencloud.example.com"},
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/scan/")

    identifier = location.rsplit("/", 1)[1]
    state = test_client.get(f"/api/scans/{identifier}").json()
    assert state["state"] == "queued"
    assert state["uuid"] == identifier
    assert "result" not in state


def test_the_json_api_answers_with_the_uuid_rather_than_a_redirect():
    """A client that asked for JSON gets JSON, so it never has to parse HTML."""
    response = _create(client())

    assert response.status_code == 202
    payload = response.json()
    assert payload["state"] == "queued"
    assert len(payload["uuid"]) == 36


def test_ten_simultaneous_submissions_are_all_queued_rather_than_refused():
    """
    Overload must never become a 503.

    Five workers and ten visitors is a queue, not an outage. Every request has
    to come back with an identifier of its own, and every scan has to be
    findable afterwards - a service that drops the eleventh visitor teaches
    them to stop checking their instance.
    """
    test_client = client(max_workers=5)

    responses = [
        _create(test_client, f"https://instance{index}.example.com")
        for index in range(10)
    ]

    assert [response.status_code for response in responses] == [202] * 10
    identifiers = [response.json()["uuid"] for response in responses]
    assert len(set(identifiers)) == 10

    states = [test_client.get(f"/api/scans/{item}").json() for item in identifiers]
    assert {state["state"] for state in states} == {"queued"}

    # FIFO: the position in line is the order they arrived in, and nobody is
    # missing from it.
    positions = [state["queue"]["position"] for state in states]
    assert positions == list(range(1, 11))
    assert states[0]["queue"]["length"] == 10


def test_one_scan_never_shows_another_scans_data():
    """
    The isolation guarantee, stated as bluntly as it can be.

    Two scans, two targets, two namespaces. Reading A must never return
    anything belonging to B - not the target, not the state, not the uuid -
    and neither may reach the other's Redis keys.
    """
    test_client = client()
    first = _create(test_client, "https://alpha.example.com").json()["uuid"]
    second = _create(test_client, "https://beta.example.com").json()["uuid"]

    alpha = test_client.get(f"/api/scans/{first}").json()
    beta = test_client.get(f"/api/scans/{second}").json()

    assert alpha["uuid"] == first
    assert alpha["target"] == "https://alpha.example.com"
    assert beta["uuid"] == second
    assert beta["target"] == "https://beta.example.com"

    # The negative half: nothing of one appears in the other.
    assert second not in str(alpha)
    assert "beta.example.com" not in str(alpha)
    assert first not in str(beta)
    assert "alpha.example.com" not in str(beta)

    # And the namespaces really are separate keys, not one shared document.
    assert status_key(first) != status_key(second)
    assert result_key(first) != result_key(second)


def test_there_is_no_endpoint_that_lists_scans():
    """
    A listing endpoint would undo the capability token in one request.

    The uuid is only a secret while there is no way to ask for all of them.
    `GET /api/scans` sends a browser back to the form, which is a courtesy,
    not a collection: it must never carry an identifier with it.
    """
    test_client = client()
    created = _create(test_client).json()["uuid"]

    for path in ("/api/scans", "/api/scans/", "/scan", "/scan/"):
        response = test_client.get(path)
        assert response.status_code in {200, 404, 405}
        if response.status_code == 200:
            # The form, reached by redirect - the only 200 allowed here.
            assert str(response.url).endswith("/")
            assert 'name="target_url"' in response.text
        assert created not in response.text


def test_the_form_posts_to_a_page_a_browser_can_also_get():
    """
    A submission that fails is re-rendered where it was sent, and people reload.

    Posting the form to the API path left the browser sitting on a URL that
    answers GET with 405, so a refresh after a typo dead-ended instead of
    showing the form again.
    """
    test_client = client()
    action = re.search(r'<form class="scan-form[^>]*action="([^"]+)"', test_client.get("/").text)
    assert action is not None
    assert test_client.get(action.group(1)).status_code == 200

    rejected = test_client.post(
        action.group(1),
        data={"target_url": "http://127.0.0.1"},
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    assert rejected.status_code == 400
    assert 'name="target_url"' in rejected.text

    accepted = test_client.post(
        action.group(1),
        data={"target_url": "https://opencloud.example.com"},
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    assert accepted.status_code == 303
    assert accepted.headers["location"].startswith("/scan/")


def test_a_bare_hostname_is_a_complete_answer():
    """
    Nobody types the scheme, and the browser must not insist on one either.

    A type="url" input refuses 'opencloud.example.com' before the request is
    ever made, so the field has to stay lenient and the server has to assume
    https.
    """
    body = client().get("/").text
    field = re.search(r"<input[^>]*name=\"target_url\"[^>]*>", body, re.DOTALL)
    assert field is not None
    assert 'type="url"' not in field.group(0)

    submitted = client().post(
        "/api/scans", json={"target_url": "opencloud.example.com"}
    )
    assert submitted.status_code == 202

    identifier = submitted.json()["uuid"]
    state = client().get(f"/api/scans/{identifier}")
    assert state.status_code in {200, 404}


@pytest.mark.parametrize(
    "submitted",
    [
        "https://opencloud.example.com/?redirect=http://169.254.169.254/",
        "https://opencloud.example.com#fragment",
        "https://user:secret@opencloud.example.com",
        "https://opencloud.example.com\t/x",
        "opencloud.example.com Xhttp://elsewhere.example",
        "https://opencloud.example.com/;curl%20evil.example",
        "https://opencloud.example.com/opencloud;parameter",
        "https://opencloud.example.com/opencloud/%2e%2e/admin",
        "https://opencloud.example.com/opencloud/../admin",
        "https://opencloud.example.com/opencloud//admin",
    ],
)
def test_a_base_path_cannot_describe_a_request_or_traverse(submitted):
    """
    A submission locates an instance; it never describes an arbitrary request.

    The scanner may need a deployment prefix, but it still chooses every
    endpoint below it. Queries, parameters, escapes and traversal syntax
    would hand that choice back to the submitter and are therefore refused.
    """
    response = client().post("/api/scans", json={"target_url": submitted})

    assert response.status_code == 400
    assert "uuid" not in response.json()


def test_an_instance_in_a_subfolder_is_accepted_and_preserved():
    """
    OpenCloud can be deployed below an origin rather than at its root.

    Accepting the address is insufficient if queueing or worker revalidation
    silently drops the prefix and scans the unrelated origin root instead.
    """
    response = client().post(
        "/api/scans",
        json={"target_url": "https://opencloud.example.com/opencloud/tenant-a/"},
    )

    assert response.status_code == 202
    identifier = response.json()["uuid"]
    status = client().get(f"/api/scans/{identifier}").json()
    assert status["target"] == "https://opencloud.example.com/opencloud/tenant-a"


def test_a_trailing_slash_port_and_subfolder_are_still_an_address():
    """
    Browsers add the slash and operators run on odd ports.

    Refusing either would mean refusing what people actually paste, which is
    how a safety rule turns into a support burden.
    """
    for submitted in (
        "https://opencloud.example.com/",
        "https://opencloud.example.com:8443",
        "https://opencloud.example.com:8443/",
        "https://opencloud.example.com:8443/opencloud/",
        "OpenCloud.Example.COM.",
    ):
        response = client().post("/api/scans", json={"target_url": submitted})
        assert response.status_code == 202, submitted


def test_an_ipv6_literal_stays_a_valid_address_when_it_is_displayed_again():
    """
    Revalidation must not turn a valid IPv6 literal into an ambiguous URL.

    The brackets are URL syntax rather than part of the address; dropping
    them makes the first colon look like the beginning of a port.
    """
    target = validate_target("https://[2001:db8::7]:8443", allow_private=True)

    assert target.hostname == "2001:db8::7"
    assert target.display == "https://[2001:db8::7]:8443"


def test_the_field_itself_allows_a_subfolder_but_refuses_parameters():
    """
    The browser should accept a base path and refuse request syntax early.

    The server is the rule that counts, but a visitor who pastes a link from
    their address bar deserves the answer immediately, and the pattern is what
    gives it to them without a line of inline script.
    """
    body = client().get("/").text
    field = re.search(r"<input[^>]*name=\"target_url\"[^>]*>", body, re.DOTALL)

    assert field is not None
    assert "pattern=" in field.group(0)
    assert "subfolder" in field.group(0).lower()
    assert "parameters" in field.group(0).lower()


@pytest.mark.parametrize(
    "parameter",
    ["concurrency", "threads", "workers", "timeout", "scan_concurrency", "verify_tls"],
)
def test_performance_parameters_are_refused_rather_than_honoured(parameter):
    """
    How hard the scanner runs is the operator's decision, not the visitor's.

    Silently ignoring the field would be safe but dishonest; the caller
    believes they configured something. Refusing says so.
    """
    response = client().post(
        "/api/scans",
        json={"target_url": "https://opencloud.example.com", parameter: 50},
    )

    assert response.status_code == 422
    assert parameter in response.json()["detail"]


def test_a_tampered_form_field_cannot_reach_the_scanner_either():
    """The form is the same API; a hand-crafted POST must not get further."""
    response = client().post(
        "/api/scans",
        data={"target_url": "https://opencloud.example.com", "concurrency": "50"},
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 422
    assert "concurrency" in response.text


def test_an_unknown_waiver_is_dropped_instead_of_reaching_the_scanner():
    """
    Waivers come from an allow-list, so a wildcard cannot be smuggled in.

    ``*`` would waive every finding at once, which is the difference between
    a waiver and a blindfold.
    """
    test_client = client()
    identifier = _create(
        test_client,
        ignore_hardenings=["basicAuthDisabled", "*", "debugPort:*", "notAThing"],
    ).json()["uuid"]

    stored = test_client.get(f"/api/scans/{identifier}").json()["ignoreHardenings"]

    assert stored == ["basicAuthDisabled"]
    assert "*" not in stored
    assert "debugPort:*" not in stored


@pytest.mark.parametrize(
    "target",
    [
        "http://127.0.0.1",
        "http://127.0.0.1:8080/status.php",
        "https://localhost",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal",
        "http://10.0.0.5",
        "http://192.168.1.10",
        "http://172.16.4.4",
        "http://[::1]",
        "http://0.0.0.0",
        "file:///etc/passwd",
        "gopher://127.0.0.1:6379",
    ],
)
def test_internal_addresses_and_odd_schemes_are_refused(target):
    """
    The service must not become a way to reach the network it runs in.

    The metadata endpoints matter most: one successful request there is
    already credentials in someone else's hands.
    """
    response = client().post("/api/scans", json={"target_url": target})

    assert response.status_code == 400
    assert "uuid" not in response.json()


def test_a_private_target_is_scannable_only_when_the_operator_says_so():
    """
    The escape hatch exists for on-premise deployments, and only there.

    It is a deliberate setting rather than an accident, so the guard has to
    prove it is the setting that opens it - otherwise the tests above could be
    passing for an unrelated reason.
    """
    refused = client().post("/api/scans", json={"target_url": "http://10.1.2.3"})
    allowed = client(allow_private_targets=True).post(
        "/api/scans", json={"target_url": "http://10.1.2.3"}
    )

    assert refused.status_code == 400
    assert allowed.status_code == 202


def test_the_client_rate_limit_returns_429_with_a_retry_after():
    """
    One visitor cannot occupy the whole queue.

    The header matters as much as the status: a client told to come back
    later can, whereas a bare 429 invites a retry loop.
    """
    test_client = client(ip_rate_limit=3, ip_rate_window=60)

    accepted = [
        _create(test_client, f"https://instance{index}.example.com").status_code
        for index in range(3)
    ]
    refused = _create(test_client, "https://instance9.example.com")

    assert accepted == [202, 202, 202]
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) > 0


def test_the_same_target_cannot_be_scanned_again_immediately():
    """
    The limit that protects somebody else's instance from this service.

    Without it, a public scanner is a request amplifier pointed at whichever
    instance is currently interesting.
    """
    test_client = client(target_cooldown=300)

    first = _create(test_client, "https://opencloud.example.com")
    second = _create(test_client, "https://opencloud.example.com")
    # A different instance is unaffected: the limit is per target, not global.
    other = _create(test_client, "https://other.example.com")

    assert first.status_code == 202
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) > 0
    assert other.status_code == 202


def test_an_expired_scan_is_indistinguishable_from_one_that_never_existed():
    """
    Both are 404, and the body says nothing either way.

    A distinct 'expired' answer would confirm that a uuid was once real,
    which is one bit more than a stranger should be able to learn.
    """
    test_client = client(result_ttl=60)
    identifier = _create(test_client).json()["uuid"]
    assert test_client.get(f"/api/scans/{identifier}").status_code == 200

    backend().advance(61)

    expired = test_client.get(f"/api/scans/{identifier}")
    invented = test_client.get("/api/scans/8bd5e15c-0a5e-4d0b-9a4e-2e5b3d5c1f00")

    assert expired.status_code == 404
    assert invented.status_code == 404
    assert expired.json() == invented.json()


def test_an_expired_scan_page_explains_itself_in_html():
    """A visitor returning to a bookmark should meet a page, not a JSON blob."""
    test_client = client(result_ttl=60)
    identifier = _create(test_client).json()["uuid"]
    backend().advance(61)

    page = test_client.get(f"/scan/{identifier}", headers={"Accept": "text/html"})

    assert page.status_code == 404
    assert "that scan is gone" in page.text


def test_every_key_written_for_a_scan_carries_a_ttl():
    """
    Nothing may outlive the promise on the landing page.

    A key written without an expiry is a scan result kept forever, which is
    the one thing this service says it does not do.
    """
    test_client = client(result_ttl=1800)
    identifier = _create(test_client).json()["uuid"]

    store = backend()

    assert 0 < asyncio.run(store.ttl(status_key(identifier))) <= 1800
    assert asyncio.run(store.ttl(f"scan:{identifier}:metadata")) > 0
    assert asyncio.run(store.ttl(QUEUE_KEY)) > 0


def test_the_responses_carry_the_security_headers():
    """
    The policy has to be strict enough that the frontend proves itself.

    Everything the pages load is local, so 'self' is not a compromise - and a
    result page must never be framed or cached.
    """
    response = client().get("/")

    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert "unsafe-inline" not in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"


def test_no_style_or_script_is_inlined_into_a_page():
    """
    The strict policy is only worth having if the markup can live under it.

    An inline style attribute or a script block would be silently dropped by
    the browser, which shows up as a page that looks broken for everyone but
    the developer with the policy disabled.
    """
    body = client().get("/").text

    assert "style=" not in body
    assert "<style" not in body
    assert "onclick" not in body
    # Scripts are referenced, never embedded.
    assert "<script>" not in body
    assert '<script src="/static/js/app.js" defer></script>' in body


def test_nothing_is_loaded_from_a_third_party():
    """
    No CDN, no font service, no analytics.

    Every resource the browser fetches has to come from this origin and be
    named by a relative path. A single external stylesheet or script would
    turn "air-gapped" into a claim the network traffic contradicts, and an
    absolute URL would hand the page's own host name back to it.

    The canonical link and the discovery hints are excluded because they are
    not resources: they are addresses the browser never fetches, and the
    canonical one has to be absolute to mean anything at all.
    """
    test_client = client()
    identifier = _create(test_client).json()["uuid"]
    pages = [
        test_client.get(path).text
        for path in (
            "/",
            "/how-it-works",
            "/grades",
            "/documentation",
            "/search",
            "/api",
            "/ai",
            "/privacy",
            "/about",
        )
    ]
    pages.append(test_client.get(f"/scan/{identifier}").text)

    for body in pages:
        body = re.sub(
            r'<link rel="(?:canonical|service-desc|arazzo|ai-discovery)"[^>]*>',
            "",
            body,
        )
        resources = re.findall(r'<(?:script|link|img)[^>]*?(?:src|href)="([^"]+)"', body)
        assert resources, "the page should load at least its own stylesheet"
        for url in resources:
            assert url.startswith("/static/"), url
        assert "googleapis" not in body
        assert "cdnjs" not in body
        assert "unpkg" not in body


def test_the_health_endpoint_says_nothing_about_any_scan():
    """A probe endpoint is a probe endpoint, not a status board."""
    test_client = client()
    identifier = _create(test_client).json()["uuid"]
    asyncio.run(backend().set(WORKER_HEARTBEAT_KEY, "1", ex=30))

    payload = test_client.get("/healthz").json()

    assert payload["status"] == "ok"
    assert payload["worker"] == "ok"
    assert payload["queueDepth"] == 1
    assert identifier not in str(payload)
    assert "target" not in payload


def test_the_health_endpoint_reports_the_age_of_the_release_schedule():
    """An operator has no other way to see whether the daily refresh runs."""
    test_client = client()
    asyncio.run(backend().set(WORKER_HEARTBEAT_KEY, "1", ex=30))

    schedule = test_client.get("/healthz").json()["releaseSchedule"]

    assert schedule["updated"] == load_release_schedule().updated
    # Nothing has refreshed yet, and the probe says so rather than guessing.
    assert schedule["checked"] is None
    assert schedule["refresh"] is True


def test_the_health_endpoint_reports_the_state_of_the_advisory_database():
    """
    The same question about the other half of what a rating is made of.

    Counts and dates only: a probe nobody has to authenticate for must not
    say which findings this deployment would report.
    """
    test_client = client()
    asyncio.run(backend().set(WORKER_HEARTBEAT_KEY, "1", ex=30))

    advisories = test_client.get("/healthz").json()["advisories"]

    assert advisories["advisories"] == len(load_database().advisories)
    assert advisories["checked"] is None
    assert advisories["refresh"] is True
    assert not any(
        isinstance(value, (list, dict)) for value in advisories.values()
    ), "an advisory title or range must never reach an unauthenticated probe"


def test_the_health_endpoint_rejects_an_unavailable_redis_backend(monkeypatch):
    """A live web process cannot accept scans when its shared state store is down."""
    test_client = client()

    async def unavailable(*_keys):
        raise RedisUnavailable()

    monkeypatch.setattr(test_client.app.state.backend, "health", unavailable)

    response = test_client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "version": __version__}


def test_the_health_endpoint_rejects_a_missing_worker_heartbeat():
    """A web process without a worker must not be reported as ready for scans."""
    response = client().get("/healthz")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "version": __version__}


def test_a_rate_limited_visitor_is_pointed_at_running_the_check_themselves():
    """
    A limit should read as an invitation, not a refusal.

    The whole scanner is open source, so the person who ran into the limit is
    exactly the person who should hear they can run it at home without one.
    Losing the pointer would leave them with a dead end and no next step.
    """
    test_client = client(ip_rate_limit=1, ip_rate_window=60)

    _create(test_client, "https://first.example.com")
    refused = _create(test_client, "https://second.example.com")

    assert refused.status_code == 429
    payload = refused.json()
    assert payload["selfHostUrl"] == "https://github.com/sowoi/check-opencloud-security"
    assert "github.com/sowoi/check-opencloud-security" in payload["hint"]
    # A rejection the service can do something about must not carry the hint,
    # or it becomes noise that stops meaning anything.
    fresh = client()
    blocked = _create(fresh, "http://127.0.0.1:9200")
    assert blocked.status_code == 400
    assert "selfHostUrl" not in blocked.json()


def test_the_rate_limit_page_offers_the_same_way_out_in_html():
    """
    Most people hit the limit in a browser, not with curl.

    A JSON-only hint would reach the audience that needs it least.
    """
    test_client = client(target_cooldown=300)
    form = {"target_url": "https://opencloud.example.com"}

    test_client.post("/api/scans", data=form, headers={"Accept": "text/html"})
    refused = test_client.post("/api/scans", data=form, headers={"Accept": "text/html"})

    assert refused.status_code == 429
    assert "github.com/sowoi/check-opencloud-security" in refused.text
    assert "scanned very recently" in refused.text


def test_every_page_carries_the_trademark_notice():
    """
    The service names somebody else's product, so it has to say whose it is.

    A visitor arriving on a result page they were linked to must see it as
    plainly as one who came through the landing page.
    """
    test_client = client()
    identifier = _create(test_client).json()["uuid"]
    pages = [
        test_client.get(path).text
        for path in (
            "/",
            "/how-it-works",
            "/grades",
            "/documentation",
            "/search",
            "/api",
            "/ai",
            "/privacy",
            "/about",
        )
    ]
    pages.append(test_client.get(f"/scan/{identifier}").text)
    pages.append(test_client.get("/scan/00000000-0000-4000-8000-000000000000").text)

    for body in pages:
        assert "not affiliated with" in body
        assert "OpenCloud GmbH" in body


def test_every_page_says_the_check_is_not_exhaustive_and_a_grade_is_not_a_certificate():
    """
    A grade is the thing people quote, and quoting it as a clean bill of
    health is the misreading that does real harm.

    Somebody linked straight to a result must be told, on that page, that the
    scan sees only what an anonymous visitor sees - so the caveat lives in the
    footer, where no page can be rendered without it.
    """
    test_client = client()
    identifier = _create(test_client).json()["uuid"]
    pages = [
        test_client.get(path).text
        for path in (
            "/",
            "/how-it-works",
            "/grades",
            "/documentation",
            "/search",
            "/api",
            "/ai",
            "/privacy",
            "/about",
        )
    ]
    pages.append(test_client.get(f"/scan/{identifier}").text)

    for body in pages:
        assert "not exhaustive" in body
        assert "not that the instance" in body
        # The negative half: it does not overclaim on the way past.
        assert "security audit or a penetration test" in body


def test_the_footer_names_the_backend_version_on_every_page():
    """
    A result is only as trustworthy as the build that produced it.

    Somebody reporting a wrong finding, or wondering whether a fix has landed
    yet, needs the version without opening an API endpoint - and it has to be
    the version actually running, not a number pasted into a template.
    """
    from webapp import __version__

    test_client = client()
    identifier = _create(test_client).json()["uuid"]
    pages = [
        test_client.get(path).text
        for path in (
            "/",
            "/how-it-works",
            "/grades",
            "/documentation",
            "/search",
            "/api",
            "/ai",
            "/privacy",
            "/about",
        )
    ]
    pages.append(test_client.get(f"/scan/{identifier}").text)
    pages.append(test_client.get("/scan/00000000-0000-4000-8000-000000000000").text)

    for body in pages:
        assert f"Backend v{__version__}" in body
    # The same number the API reports, so a bug report cannot quote two.
    assert test_client.get("/healthz").json()["version"] == __version__


def test_the_browsable_api_pages_are_off_unless_an_operator_asks_for_them():
    """
    Swagger UI and ReDoc are a convenience for whoever runs the service.

    They are two more pages to render, they exist to be clicked through by a
    person, and a public deployment already has a page explaining the API. The
    default is therefore silence - which says nothing about the *documents*
    they display, which are always public.
    """
    quiet = client()
    for path in ("/docs", "/redoc"):
        assert quiet.get(path).status_code == 404

    loud = client(enable_docs=True)
    for path in ("/docs", "/redoc"):
        assert loud.get(path).status_code == 200


def test_the_machine_readable_documents_are_public_without_any_switch():
    """
    An agent handed only this address has to be able to read the contract.

    A specification nobody can fetch is not a specification, so the three
    documents that describe this service do not depend on an operator having
    turned a browsable page on.
    """
    quiet = client()
    for path in ("/openapi.json", "/arazzo.json", "/.well-known/ai.json"):
        response = quiet.get(path)
        assert response.status_code == 200, path
        assert response.json(), path

    schema = quiet.get("/openapi.json").json()
    assert set(schema["paths"]) >= {"/api/scans", "/api/scans/{identifier}", "/healthz"}
    # The negative half: the pages that only a person reads are still off.
    assert quiet.get("/docs").status_code == 404


def test_the_api_docs_load_nothing_from_anywhere_else():
    """
    Swagger UI and ReDoc are served from this origin like everything else.

    FastAPI's own pages fetch their JavaScript from a CDN, which this service
    does not do at all - and which renders a blank page wherever that CDN is
    unreachable, which is precisely the kind of deployment that runs a scanner
    like this one.
    """
    test_client = client(enable_docs=True)
    identifier = _create(test_client).json()["uuid"]

    for path in ("/docs", "/redoc"):
        body = test_client.get(path)
        assert body.status_code == 200
        assert "jsdelivr" not in body.text
        assert "/static/vendor/" in body.text
        # The only difference from the strict policy, and no foreign origin.
        policy = body.headers["content-security-policy"]
        assert "'unsafe-inline'" in policy
        assert "http" not in policy

    for asset in (
        "/static/vendor/swagger-ui-bundle.js",
        "/static/vendor/swagger-ui.css",
        "/static/vendor/redoc.standalone.js",
    ):
        assert test_client.get(asset).status_code == 200

    for path in ("/", f"/scan/{identifier}", "/healthz", "/openapi.json"):
        policy = test_client.get(path).headers["content-security-policy"]
        assert "'unsafe-inline'" not in policy
        assert policy.startswith("default-src 'self'")


def test_the_api_docs_carry_no_inline_script():
    """
    An inline script is exactly what `script-src 'self'` refuses to run.

    FastAPI starts Swagger UI from an inline <script>, so the page loaded its
    bundle, obeyed the policy, refused to run the one line that mounts the UI
    and showed a blank document. Relaxing the policy to fix that would be the
    wrong repair, so the page must stay free of inline script instead.
    """
    test_client = client(enable_docs=True)

    for path in ("/docs", "/redoc"):
        body = test_client.get(path).text
        assert "script-src 'self'" in test_client.get(path).headers[
            "content-security-policy"
        ]
        for tag in re.findall(r"<script\b[^>]*>(.*?)</script>", body, re.DOTALL):
            assert not tag.strip(), f"{path} carries an inline script"

    swagger = test_client.get("/docs").text
    assert '<div id="swagger-ui" data-openapi-url="/openapi.json">' in swagger
    assert '<script src="/static/js/docs.js"></script>' in swagger
    assert test_client.get("/static/js/docs.js").status_code == 200


def test_the_release_track_is_chosen_on_the_form_and_defaults_to_auto():
    """
    No fixed guess is right for a stranger's server, so the schedule decides.

    Assuming production called a current rolling instance out of date, and
    assuming rolling reports an end of life a production instance has not
    reached. What the visitor does say has to survive the round trip to the
    result page.
    """
    test_client = client()
    body = test_client.get("/").text
    assert 'name="release_track"' in body
    for track in ("rolling", "production", "lts", "auto"):
        assert f'value="{track}"' in body

    default = test_client.post("/api/scans", json={"target_url": "opencloud.example.com"})
    assert default.status_code == 202
    state = test_client.get(f"/api/scans/{default.json()['uuid']}").json()
    assert state["releaseTrack"] == "auto"

    chosen = test_client.post(
        "/api/scans",
        json={"target_url": "other.example.com", "release_track": "lts"},
    )
    picked = test_client.get(f"/api/scans/{chosen.json()['uuid']}").json()
    assert picked["releaseTrack"] == "lts"


def test_the_form_offers_to_detect_the_release_track():
    """A visitor rarely knows which track a stranger's server follows.

    Picking the wrong one used to rate a perfectly current release F, so
    'auto' has to be offered on the form and survive to the scan record.
    """
    test_client = client()

    assert 'value="auto"' in test_client.get("/").text

    chosen = test_client.post(
        "/api/scans",
        json={"target_url": "opencloud.example.com", "release_track": "auto"},
    )
    assert chosen.status_code == 202
    state = test_client.get(f"/api/scans/{chosen.json()['uuid']}").json()
    assert state["releaseTrack"] == "auto"


def test_an_unknown_release_track_falls_back_instead_of_failing_the_scan():
    """
    A stale bookmark or a typo should still scan, on the detected track.

    Accepting the value verbatim would let a request name a track the
    lifecycle model does not know, and the scan would rate against nothing.
    """
    test_client = client()
    for value in ("nightly", "LTS ", "", "production; rolling"):
        response = test_client.post(
            "/api/scans",
            json={"target_url": "opencloud.example.com", "release_track": value},
        )
        assert response.status_code == 202
        state = test_client.get(f"/api/scans/{response.json()['uuid']}").json()
        assert state["releaseTrack"] in {"auto", "lts"}
        assert state["releaseTrack"] != "nightly"

    trimmed = test_client.post(
        "/api/scans",
        json={"target_url": "opencloud.example.com", "release_track": "LTS "},
    )
    assert (
        test_client.get(f"/api/scans/{trimmed.json()['uuid']}").json()["releaseTrack"]
        == "lts"
    )


def test_a_redirect_to_a_private_address_is_refused_like_a_submission():
    """
    The guard handed to the scanner judges every hop, not just the first.

    Validating only what the visitor typed leaves the whole of SSRF one
    redirect away: a public target answering ``302 Location:
    http://127.0.0.1:8500/`` would have the scan read the scanning host's own
    network and report it back under the visitor's uuid.
    """
    guard = redirect_guard()

    assert guard("https://opencloud.example.com/login") is True
    for hop in (
        "http://127.0.0.1:8500/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://[::1]/",
        "file:///etc/passwd",
        "http://100.64.0.1/",
    ):
        assert guard(hop) is False, hop


def test_the_scanner_the_web_service_builds_carries_that_guard():
    """
    A guard nobody passes to the scanner protects nothing.

    This is the seam between the two: if ``scanner_settings_for`` ever stops
    setting it, the library goes back to following redirects with
    :mod:`requests`, and the test above keeps passing while the hole is open.
    """
    target = validate_target("opencloud.example.com")
    built = scanner_settings_for(target, (), settings())

    assert built.redirect_guard is not None
    assert built.redirect_guard("http://169.254.169.254/") is False
    assert ScannerSettings().redirect_guard is None


def test_a_path_that_is_not_a_uuid_is_a_404_and_never_a_redis_lookup():
    """
    The identifier is interpolated into a Redis key, so it must be an uuid.

    Nothing this service hands out is anything else, so a lookup for
    ``../`` or a wildcard is a probe and is answered like any other miss -
    without the store being asked at all.
    """
    test_client = client()
    for candidate in ("*", "../scan", "scan:*:status", "not-a-uuid", "x" * 200):
        assert is_scan_uuid(candidate) is False
        assert test_client.get(f"/api/scans/{candidate}").status_code == 404

    real = test_client.post(
        "/api/scans", json={"target_url": "opencloud.example.com"}
    ).json()["uuid"]
    assert is_scan_uuid(real) is True
    assert test_client.get(f"/api/scans/{real}").status_code == 200


def test_an_unparseable_address_is_an_answer_rather_than_a_crash():
    """
    A malformed IPv6 literal used to raise out of the handler.

    An unhandled error is a 500 that Starlette renders before the security
    headers are added, so a bad address would have cost the response its CSP
    as well as its manners.
    """
    test_client = client()
    response = test_client.post("/api/scans", json={"target_url": "https://[::1"})
    assert response.status_code == 400
    assert response.headers["Content-Security-Policy"].startswith("default-src 'self'")


def test_only_http_urls_become_advisory_links():
    """
    Advisory URLs are rendered into an href.

    They come from the bundled database today, but the moment a remote feed
    is read a ``javascript:`` URL in it would be stored cross-site scripting
    on somebody else's result page.
    """
    assert is_safe_link("https://example.com/advisory") is True
    assert is_safe_link("http://example.com/advisory") is True
    for bad in ("javascript:alert(1)", "JAVASCRIPT:alert(1)", "data:text/html,x", "", None, 5):
        assert is_safe_link(bad) is False


def test_the_about_page_credits_opencloud_and_links_to_it():
    """
    The tool is named after somebody else's software, so it says whose.

    A scanner that trades on a project's name without pointing at it - or
    without saying it is not run by them - is the kind of thing that gets a
    project's trademark lawyers involved, and it is simply bad manners. The
    credit moved off the landing page, so it has to be reachable from it.
    """
    test_client = client()
    body = test_client.get("/about").text

    assert "https://opencloud.eu/" in body
    assert "https://docs.opencloud.eu/" in body
    assert "not affiliated with" in body and "OpenCloud GmbH" in body
    # Moved, not dropped: the landing page still points at it.
    assert 'href="/about"' in test_client.get("/").text


def test_the_api_page_states_the_limits_and_links_the_schema_when_it_is_on():
    """
    A caller should learn the rules from the page, not from a 429.

    And the Swagger link must only appear where Swagger actually answers:
    advertising /docs on a deployment that has it switched off sends people
    to the 404 page.
    """
    quiet = client(ip_rate_limit=10, ip_rate_window=60, target_cooldown=300)
    body = quiet.get("/api").text
    assert "10 submissions" in body
    assert "5 minute(s)" in body
    assert 'href="/docs"' not in body
    assert "COS_WEB_ENABLE_DOCS" in body

    loud = client(enable_docs=True).get("/api").text
    assert 'href="/docs"' in loud
    assert 'href="/openapi.json"' in loud
