"""
The operator's area, and the four refusals that keep it one.

This is the only surface in the service that can change what the scanner
knows and read the audit trail, so what is asserted here is mostly what it
declines to do. Each of these has a way of failing quietly - an area served
open looks exactly like an area served correctly to the operator who turned
it on - and none of them would show up in a page that renders.

The properties, in the order somebody attacking this would meet them: the
area does not exist unless it was asked for, a deployment that cannot check
its sign-in refuses to start, a request that did not come through the outpost
is not distinguishable from a request for a page that is not there, and
being signed in is not the same as being on the guest list.
"""

from __future__ import annotations

import asyncio
import json
import re

import pytest
from fastapi.testclient import TestClient

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    backend,
    settings,
)
from webapp.app import create_app
from webapp.settings import ADMIN_PROXY_SECRET_MINIMUM

SECRET = "b" * 48
OPERATOR = "okko"

#: What the outpost adds to a request it has already authenticated.
FORWARDED = {
    "x-cos-admin-proxy": SECRET,
    "x-authentik-username": OPERATOR,
    "sec-fetch-site": "same-origin",
}


def _admin_settings(**overrides):
    return settings(
        admin_enabled=True,
        admin_proxy_secret=SECRET,
        admin_users=(OPERATOR,),
        **overrides,
    )


# ----------------------------------------------------- the area may not exist


def test_the_area_is_absent_rather_than_protected_when_nobody_asked_for_it():
    """Off has to mean the path does not exist, not that it asks for a password.

    A 401 tells a stranger this deployment has an operator's area and that
    they have found it. The same 404 every unknown path answers with tells
    them nothing, which is the whole of what a deployment that does not use
    the feature should say.
    """
    with TestClient(create_app(settings())) as client:
        assert client.get("/admin").status_code == 404
        assert client.get("/admin/state").status_code == 404
        assert client.post("/admin/refresh", data={"action": "schedule"}).status_code == 404
        assert client.get("/admin/audit/stream").status_code == 404


def test_the_area_off_is_the_same_answer_as_a_path_that_never_existed():
    """Indistinguishable, or the 404 is a disclosure with extra steps."""
    with TestClient(create_app(settings())) as client:
        absent = client.get("/no-such-page-at-all")
        admin = client.get("/admin")

    assert admin.status_code == absent.status_code == 404


# --------------------------------------------------- a deployment must be able
#                                                      to enforce what it claims


def test_a_deployment_that_cannot_check_its_sign_in_refuses_to_start():
    """An unauthenticated console is worse than a container that will not boot.

    And unlike a boot failure, nobody notices it: the operator sees the area
    they asked for, and so does everybody else.
    """
    with pytest.raises(ValueError, match="ADMIN_PROXY_SECRET"):
        create_app(settings(admin_enabled=True, admin_users=(OPERATOR,)))


def test_a_secret_short_enough_to_guess_is_refused_at_startup():
    """It is the only thing between an operator and anybody on the network."""
    short = "a" * (ADMIN_PROXY_SECRET_MINIMUM - 1)
    with pytest.raises(ValueError, match="shorter than"):
        create_app(
            settings(
                admin_enabled=True, admin_proxy_secret=short, admin_users=(OPERATOR,)
            )
        )


def test_an_empty_guest_list_is_refused_rather_than_read_as_everybody():
    """"Anybody the provider authenticated" is a directory, not an operator.

    The identity provider may well exist to let strangers sign in to
    something else entirely.
    """
    with pytest.raises(ValueError, match="names nobody"):
        create_app(settings(admin_enabled=True, admin_proxy_secret=SECRET))


# ------------------------------------------------- the headers must be earned


def test_the_identity_headers_are_worthless_without_the_outpost_secret():
    """Anybody who can reach the container can send X-authentik-username.

    Which is the entire reason the shared secret exists: without it the area
    would trust a header, and a header is not a credential.
    """
    with TestClient(create_app(_admin_settings())) as client:
        forged = client.get("/admin", headers={"x-authentik-username": OPERATOR})
        wrong = client.get(
            "/admin",
            headers={"x-cos-admin-proxy": "not-it", "x-authentik-username": OPERATOR},
        )

    assert forged.status_code == 404
    assert wrong.status_code == 404


def test_signing_in_is_not_the_same_as_being_on_the_guest_list():
    """The request really came through the outpost; the person is still not an operator."""
    with TestClient(create_app(_admin_settings())) as client:
        answer = client.get(
            "/admin", headers={**FORWARDED, "x-authentik-username": "somebody-else"}
        )

    assert answer.status_code == 404


def test_an_operator_named_in_another_case_is_still_the_same_operator():
    """A username written with a capital in the compose file is not a lockout."""
    with TestClient(create_app(_admin_settings())) as client:
        answer = client.get(
            "/admin", headers={**FORWARDED, "x-authentik-username": OPERATOR.upper()}
        )

    assert answer.status_code == 200


def test_the_area_opens_for_the_operator_it_was_configured_for():
    """The positive case, so the four refusals above are not refusing everything."""
    with TestClient(create_app(_admin_settings())) as client:
        answer = client.get("/admin", headers=FORWARDED)

    assert answer.status_code == 200
    assert OPERATOR in answer.text


# ----------------------------------------------------------- never in an index


def test_the_area_tells_every_crawler_to_forget_it():
    """A console in a search index is a console somebody finds by accident."""
    with TestClient(create_app(_admin_settings())) as client:
        answer = client.get("/admin", headers=FORWARDED)

    assert 'content="noindex, nofollow, noarchive"' in answer.text
    assert "noindex" in answer.headers.get("X-Robots-Tag", "")


def test_the_area_is_not_named_in_robots_txt_or_the_sitemap():
    """A Disallow line is a public file naming the path.

    It would tell everybody who reads robots.txt that this deployment has an
    operator's area and where it is - the opposite of what a rule meant to
    keep crawlers out of it should achieve.
    """
    with TestClient(create_app(_admin_settings())) as client:
        robots = client.get("/robots.txt").text
        sitemap = client.get("/sitemap.xml").text

    assert "/admin" not in robots
    assert "/admin" not in sitemap


def test_the_area_is_absent_from_the_documented_and_indexed_surfaces():
    """It is not a page of the website, and none of the maps may say it is."""
    from webapp.documentation import DOCUMENTATION_PAGES
    from webapp.search import SEARCH_PAGES

    assert all(page.path != "/admin" for page in SEARCH_PAGES)
    assert all("admin" not in page.source for page in DOCUMENTATION_PAGES)

    with TestClient(create_app(_admin_settings())) as client:
        assert "/admin" not in client.get("/llms.txt").text
        assert "/admin" not in client.get("/openapi.json").text


# ---------------------------------------------------------------- the actions


def test_an_action_nobody_offers_is_refused_rather_than_attempted():
    """The action name reaches a dispatch; only the two names may pass it."""
    with TestClient(create_app(_admin_settings())) as client:
        answer = client.post(
            "/admin/refresh",
            data={"action": "rm -rf"},
            headers={**FORWARDED, "Accept": "application/json"},
        )

    assert answer.status_code == 422
    assert answer.json()["state"] == "failed"


def test_a_refresh_meets_the_cross_site_check_every_other_post_does():
    """The area is reachable from a browser, so a foreign page can try to post to it.

    Both buttons reach somebody else's server, which is exactly the kind of
    thing a page nobody is looking at should not be able to set off.
    """
    with TestClient(create_app(_admin_settings())) as client:
        answer = client.post(
            "/admin/refresh",
            data={"action": "schedule"},
            headers={**FORWARDED, "sec-fetch-site": "cross-site"},
        )

    assert answer.status_code == 403


def test_a_refresh_cannot_be_held_down_against_somebody_elses_server():
    """The daily refresh asks upstream once; a button must not turn that into a loop."""
    with TestClient(create_app(_admin_settings())) as client:
        first = client.post(
            "/admin/refresh",
            data={"action": "schedule"},
            headers={**FORWARDED, "Accept": "application/json"},
        ).json()
        second = client.post(
            "/admin/refresh",
            data={"action": "schedule"},
            headers={**FORWARDED, "Accept": "application/json"},
        ).json()

    assert first["state"] != "cooldown"
    assert second["state"] == "cooldown"
    assert second["seconds"] > 0


def test_the_two_refreshes_do_not_hold_each_other_up():
    """One cooldown per action: an advisory check is not delayed by a schedule sync."""
    with TestClient(create_app(_admin_settings())) as client:
        client.post(
            "/admin/refresh",
            data={"action": "schedule"},
            headers={**FORWARDED, "Accept": "application/json"},
        )
        other = client.post(
            "/admin/refresh",
            data={"action": "advisories"},
            headers={**FORWARDED, "Accept": "application/json"},
        ).json()

    assert other["state"] != "cooldown"


# ------------------------------------------------------------- the statistics


def test_the_statistics_name_nothing_anybody_scanned():
    """The one property that makes this area safe to have at all.

    Counts and configured limits only. An operator's area that could answer
    "what did people scan" would be the database of what everybody scanned
    that the rest of the service refuses to keep.
    """
    identifier = "8c1d0e3c-9b2f-4c81-a7e6-2f0b4d9c1e73"
    target = "https://secret-instance.example.com"
    configured = _admin_settings()
    app = create_app(configured)
    with TestClient(app) as client:
        asyncio.run(
            app.state.store.create(
                identifier,
                target=target,
                ignore_hardenings=(),
                output_format="dashboard",
            )
        )
        body = client.get("/admin/state", headers=FORWARDED).text

    assert "secret-instance" not in body
    assert identifier not in body
    # And the readings it does carry are there.
    assert "queueDepth" in body
    assert "ipRateLimit" in body


def test_a_reading_that_stopped_arriving_cannot_look_like_one_that_is_not_moving():
    """The poll swallows its errors, so a dead backend draws the same picture.

    Which is the failure mode worth designing against here: the numbers
    simply stop moving and the page goes on presenting them as the present
    tense. So the age of the last answer is on the page and counts up
    between polls, and the sentence saying what the numbers actually are is
    the server's rather than something the script composes.
    """
    with TestClient(create_app(_admin_settings())) as client:
        page = client.get("/admin", headers=FORWARDED).text
        script = client.get("/static/js/admin.js").text

    from webapp.locales.en import MESSAGES

    assert 'data-value="age"' in page
    assert MESSAGES["admin.state.stale"][:40] in page
    # The clock ticks on its own, so an answer that never comes still ages.
    assert "window.setInterval(age, 1000)" in script
    # And only a poll that actually answered moves the stamp.
    assert "lastAnswer = Date.now();" in script


def test_the_page_stops_polling_while_nobody_is_looking_at_it():
    """A tab left open overnight was asking for the state every ten seconds.

    Nothing reads the answer, the readings are re-fetched the moment the tab
    is looked at again, and eight thousand requests before breakfast is a
    load this service put on itself for nobody.
    """
    with TestClient(create_app(_admin_settings())) as client:
        script = client.get("/static/js/admin.js").text

    assert 'document.addEventListener("visibilitychange"' in script
    assert 'document.visibilityState !== "hidden"' in script
    assert "window.clearInterval(timer)" in script


def test_the_control_that_needs_a_clipboard_is_hidden_until_it_has_one():
    """A clipboard write needs a secure context; a button that cannot work is worse than none.

    The same rule the report page's copy buttons follow: rendered hidden,
    revealed by the script once the API is actually there.
    """
    with TestClient(create_app(_admin_settings())) as client:
        page = client.get("/admin", headers=FORWARDED).text
        script = client.get("/static/js/admin.js").text

    button = re.search(r"<button[^>]*data-admin-copy[^>]*>", page)
    assert button is not None
    assert " hidden" in button.group(0)
    assert 'typeof clipboard.writeText === "function"' in script


def test_the_search_index_is_reported_and_never_rebuilt():
    """ADR 0019 makes the index a release artefact, and the container is read-only.

    The area answers whether the shipped one still describes this build; it
    offers nothing that writes one, because an index generated here would be
    page text nobody reviewed sitting in front of every visitor's search.
    """
    with TestClient(create_app(_admin_settings())) as client:
        state = client.get("/admin/state", headers=FORWARDED).json()
        page = client.get("/admin", headers=FORWARDED).text

    assert "searchIndex" in state
    assert set(state["searchIndex"]) >= {"fresh", "builtFor", "running"}

    # And no control offers to write one: the only actions the page submits
    # are the two refreshes, which is asserted against the actual form fields
    # rather than the prose, since the prose says the word "rebuild" in the
    # course of explaining that it does not do it.
    offered = set(re.findall(r'name="action" value="(\w+)"', page))
    assert offered == {"schedule", "advisories"}


# ----------------------------------------------------------------- the dry run


def _usable_sources(monkeypatch):
    """Both sources answering with exactly what this build already ships.

    A document identical to the bundled one passes every guard by
    construction, which is what makes it the right stand-in for "the network
    is fine": anything the probe then declines to do, it declined for its own
    reasons rather than because the fetch failed.
    """
    from opencloud_local_scan.versions import RELEASE_SCHEDULE_FILE
    from opencloud_local_scan.vulndb import BUNDLED_DB
    from webapp import advisories as advisories_module
    from webapp import schedule as schedule_module

    schedule = json.loads(RELEASE_SCHEDULE_FILE.read_text())
    database = json.loads(BUNDLED_DB.read_text())
    monkeypatch.setattr(
        schedule_module, "fetch_schedule_document", lambda *_a: schedule
    )
    monkeypatch.setattr(
        advisories_module, "fetch_advisory_document", lambda *_a: database
    )


def test_the_dry_run_reads_both_sources_and_stores_none_of_it(monkeypatch):
    """The whole difference between the probe and the button beside it.

    It runs the same fetch and the same guards - that is the point, since an
    answer produced any other way would be about a different question - so
    the only thing keeping it a dry run is that the result is thrown away.
    Nothing may be written: not the document, not the checked stamp that
    would otherwise tell an operator this deployment had refreshed.
    """
    _usable_sources(monkeypatch)
    with TestClient(create_app(_admin_settings())) as client:
        answer = client.post(
            "/admin/probe", headers={**FORWARDED, "Accept": "application/json"}
        ).json()
        state = client.get("/admin/state", headers=FORWARDED).json()

    # It did read them, and it did reach a verdict on both.
    assert answer["state"] == "probed"
    assert answer["sources"] == {"schedule": "usable", "advisories": "usable"}
    # And the deployment is exactly where it was: nothing has been checked.
    reference = state["referenceData"]
    assert reference["releaseSchedule"]["checked"] is None
    assert reference["advisories"]["checked"] is None


def test_the_dry_run_tells_a_refusal_apart_from_a_failure(monkeypatch):
    """The reason it exists: `failed` and `rejected` are the same non-event.

    Both leave the reference data alone, so a refresh cannot say which of
    them happened in any way an operator can act on - and one is a network
    to go and look at while the other is this deployment refusing a document
    it read perfectly well.
    """
    from opencloud_local_scan.schedule_source import ExtractionError
    from webapp import schedule as schedule_module
    from webapp.schedule import probe_schedule

    def unreachable(*_args):
        raise ExtractionError("nothing answered")

    monkeypatch.setattr(schedule_module, "fetch_schedule_document", unreachable)
    assert asyncio.run(probe_schedule(_admin_settings())) == "unreadable"

    # A page that was read but has lost a release line is the other answer.
    monkeypatch.setattr(
        schedule_module, "fetch_schedule_document", lambda *_a: {"lines": []}
    )
    assert asyncio.run(probe_schedule(_admin_settings())) == "rejected"


def test_the_dry_run_is_held_back_on_a_key_of_its_own(monkeypatch):
    """It reaches upstream like a refresh, so it is limited like one.

    But under its own cooldown, because the moment somebody wants it is the
    moment after a refresh answered `failed` - and a probe sharing that
    refresh's cooldown would be unavailable exactly then.
    """
    _usable_sources(monkeypatch)
    json_headers = {**FORWARDED, "Accept": "application/json"}
    with TestClient(create_app(_admin_settings())) as client:
        first = client.post("/admin/probe", headers=json_headers).json()
        again = client.post("/admin/probe", headers=json_headers).json()
        refresh = client.post(
            "/admin/refresh", data={"action": "schedule"}, headers=json_headers
        ).json()

    assert first["state"] == "probed"
    # Held down, it is refused like everything else that reaches a stranger.
    assert again["state"] == "cooldown"
    assert again["seconds"] > 0
    # And it did not spend the refresh's cooldown on the way past.
    assert refresh["state"] != "cooldown"


def test_the_dry_run_is_refused_to_everybody_the_rest_of_the_area_is():
    """A route that fetches from two upstreams on request, gated like the rest."""
    with TestClient(create_app(_admin_settings())) as client:
        assert client.post("/admin/probe").status_code == 404
        assert (
            client.post(
                "/admin/probe", headers={"x-authentik-username": OPERATOR}
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/admin/probe", headers={**FORWARDED, "sec-fetch-site": "cross-site"}
            ).status_code
            == 403
        )


# ------------------------------------------------------------- the audit view


def test_the_audit_stream_is_refused_to_everybody_the_page_is():
    """It is the most sensitive read in the service and gets no weaker a check."""
    with TestClient(create_app(_admin_settings(audit_log=True))) as client:
        assert client.get("/admin/audit/stream").status_code == 404
        assert (
            client.get(
                "/admin/audit/stream",
                headers={"x-authentik-username": OPERATOR},
            ).status_code
            == 404
        )


def test_the_live_window_holds_nothing_when_the_audit_trail_is_off():
    """No trail, nothing to buffer: the window is not a second way to start one."""
    app = create_app(_admin_settings(audit_log=False))
    with TestClient(app):
        assert app.state.recent_audit is None


def test_every_state_the_stream_sends_is_one_the_page_can_explain():
    """A stream that stops without saying why reads as a service with nothing happening.

    The server has always sent its own account of the connection - `live`,
    `closed` at the half-hour cap, `disabled` where no trail is kept - and
    the page has to have a sentence for each of them, or the two that end
    the stream arrive as the same silence a dropped connection produces.
    This reads the states out of the module rather than listing them, so a
    new one cannot be added without the page gaining words for it.
    """
    from pathlib import Path

    from webapp import admin

    source = Path(admin.__file__).read_text(encoding="utf-8")
    states = set(re.findall(r'_sse\("state", "(\w+)"\)', source))
    assert states == {"live", "closed", "disabled"}

    with TestClient(create_app(_admin_settings(audit_log=True))) as client:
        page = client.get("/admin", headers=FORWARDED).text

    for state in states:
        assert f'data-admin-audit-{state}="' in page


def test_the_sentence_about_the_cap_carries_the_cap_that_produces_it():
    """Two numbers that must agree, written once and derived once.

    "Closed after 30 minutes" beside a connection the server ends after ten
    is worse than saying nothing: it sends an operator looking for a network
    fault that is not there.
    """
    from webapp.admin import _STREAM_MAX_SECONDS

    with TestClient(create_app(_admin_settings(audit_log=True))) as client:
        page = client.get("/admin", headers=FORWARDED).text

    note = re.search(r'data-admin-audit-closed-note="([^"]*)"', page)
    assert note is not None
    assert str(_STREAM_MAX_SECONDS // 60) in note.group(1)


def test_the_page_says_when_the_window_it_shows_is_one_replicas_own(tmp_path):
    """ADR 0035 states this limit; until an operator reads it, only the ADR does.

    Without an audit file the records come from a ring in one process's
    memory, so behind two replicas a reader is watching half a trail - and a
    half trail that presents itself as the whole one is worse than none.
    With a file every replica appends to the same place and there is nothing
    to warn about, so the sentence is absent rather than hedged.
    """
    with TestClient(create_app(_admin_settings(audit_log=True))) as client:
        in_memory = client.get("/admin", headers=FORWARDED).text

    with TestClient(
        create_app(
            _admin_settings(
                audit_log=True, audit_log_file=str(tmp_path / "audit.log")
            )
        )
    ) as client:
        with_file = client.get("/admin", headers=FORWARDED).text

    from webapp.locales.en import MESSAGES

    caveat = MESSAGES["admin.audit.replicas"][:40]
    assert caveat in in_memory
    assert caveat not in with_file


def test_the_live_window_is_bounded_and_keeps_what_the_log_wrote():
    """A window, not a copy. An unbounded one would be the retention this avoids."""
    from webapp.audit import RecentAuditRecords

    window = RecentAuditRecords(3)
    for number in range(10):
        window.add(f'{{"event": "scan_requested", "n": {number}}}')

    cursor, pending = window.since(0)
    assert window.capacity == 3
    assert len(pending) == 3
    assert '"n": 9' in pending[-1]
    # Asking again with the cursor it just gave returns nothing new.
    assert window.since(cursor)[1] == []
