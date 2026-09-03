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


# ------------------------------------------------------------- the way out


def test_the_band_offers_no_way_out_where_the_deployment_named_none():
    """This service has no session to end, so it cannot invent an exit.

    A "sign out" that leaves somebody signed in is worse than no control at
    all: the operator walks away from a browser believing the area is closed.
    Where the deployment has not said where the provider's exit is, the band
    says who is signed in and nothing else.
    """
    with TestClient(create_app(_admin_settings())) as client:
        page = client.get("/admin", headers=FORWARDED).text

    from webapp.locales.en import MESSAGES

    assert MESSAGES["admin.band.signout"] not in page
    assert "admin-band-exit" not in page


def test_the_band_links_to_the_exit_the_deployment_named():
    """The positive case: configured, the way out is on the page it belongs on."""
    exit_url = "/outpost.goauthentik.io/sign_out"
    with TestClient(
        create_app(_admin_settings(admin_sign_out_url=exit_url))
    ) as client:
        page = client.get("/admin", headers=FORWARDED).text

    from webapp.locales.en import MESSAGES

    link = re.search(r'<a class="admin-band-exit"[^>]*>', page)
    assert link is not None
    assert f'href="{exit_url}"' in link.group(0)
    assert MESSAGES["admin.band.signout"] in page


def test_an_exit_that_would_be_script_is_refused_at_startup():
    """The value is rendered into an href on a page that forbids inline script.

    `javascript:` in a link is script by another name, and this page's whole
    content policy exists to keep script off it. A protocol-relative address
    is refused with it: it reads as a local path and is not one - it is
    somebody else's host on whatever scheme the page happens to be on.
    """
    for refused in (
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "//evil.example.net/sign_out",
    ):
        with pytest.raises(ValueError, match="SIGN_OUT_URL"):
            create_app(_admin_settings(admin_sign_out_url=refused))


def test_an_ordinary_address_is_accepted_as_the_exit():
    """The negative case above must not be refusing every address.

    Both shapes a real deployment uses: the outpost's path on this host, and
    a provider that ends its session somewhere else entirely.
    """
    for accepted in (
        "/outpost.goauthentik.io/sign_out",
        "https://sso.example.com/if/session-end/opencloud/",
    ):
        with TestClient(
            create_app(_admin_settings(admin_sign_out_url=accepted))
        ) as client:
            assert client.get("/admin", headers=FORWARDED).status_code == 200


# ------------------------------------------------------- what is exposed now


#: The row on the exposure card for each boolean the state document reports.
#: The document's own names on the left, so a key renamed on one side and not
#: the other fails here rather than quietly dropping a reading off the page.
SURFACE_ROWS = {
    "mcp": "mcp",
    "docs": "docs",
    "indexed": "indexed",
    "allowPrivateTargets": "private",
    "encryptResults": "encrypt",
}

#: A sign-in on /mcp that startup will accept: without an issuer and an
#: audience the deployment refuses to start, which is a different test.
SIGNED_IN_MCP = {
    "mcp_auth_enabled": True,
    "mcp_auth_issuer": "https://sso.example.com/application/o/scan/",
    "mcp_auth_audience": "scan",
    "public_base_url": "https://scan.example.com",
}


def _sentence(key):
    """One catalogue string, escaped the way the template escapes it.

    The English is written with apostrophes in it, and comparing against the
    catalogue directly would be comparing against text no page ever contains.
    """
    from markupsafe import escape

    from webapp.locales.en import MESSAGES

    return str(escape(MESSAGES[key]))


def _row(page, name):
    """The one item on the exposure card for this surface, markup and all."""
    found = re.search(
        r'<li class="admin-surface"[^>]*data-surface="' + name + r'"[^>]*>.*?</li>',
        page,
        re.DOTALL,
    )
    assert found is not None, f"no row for {name}"
    return found.group(0)


def test_the_page_says_what_this_deployment_is_exposing():
    """The question an operator opens this area with, and it went unanswered.

    Every one of these readings was already in the state document and on no
    page, so "what is switched on right now" could only be got by reading the
    compose file - which is the file that may well be why they are here. The
    card and the document are compared against each other rather than against
    a list written here, because two renderings of the same settings drifting
    apart is the failure worth catching.
    """
    with TestClient(create_app(_admin_settings())) as client:
        page = client.get("/admin", headers=FORWARDED).text
        exposed = client.get("/admin/state", headers=FORWARDED).json()["surfaces"]

    for key, name in SURFACE_ROWS.items():
        assert f'data-state="{"on" if exposed[key] else "off"}"' in _row(page, name)


def test_the_exposure_card_is_the_servers_and_needs_no_scripting():
    """These are settings, not readings: nothing polls them and nothing may.

    A setting that changed did so in a process this page is no longer talking
    to, so the card is rendered once, in the language the page is in - and it
    is there for an operator whose browser runs none of this file's scripting.
    """
    with TestClient(create_app(_admin_settings())) as client:
        page = client.get("/admin", headers=FORWARDED).text
        script = client.get("/static/js/admin.js").text

    assert _sentence("admin.surfaces.heading") in page
    assert _sentence("admin.surfaces.mcp") in page
    # No placeholder waiting to be filled in, and nothing in the script knows
    # the card exists.
    assert 'data-value=' not in _row(page, "mcp")
    assert "admin-surface" not in script


def test_an_agent_endpoint_with_no_sign_in_on_it_is_marked():
    """Anybody who can reach /mcp can spend this service's workers.

    Which is the default and often right - a public scanner is meant to be
    used by anybody. It is marked rather than refused, because the thing an
    operator needs is to know it, not to be argued with about it.
    """
    with TestClient(create_app(_admin_settings())) as client:
        open_endpoint = _row(client.get("/admin", headers=FORWARDED).text, "mcp")

    with TestClient(create_app(_admin_settings(**SIGNED_IN_MCP))) as client:
        guarded = _row(client.get("/admin", headers=FORWARDED).text, "mcp")

    assert "data-notable" in open_endpoint
    assert _sentence("admin.surfaces.mcp.open") in open_endpoint
    # And the accent means something only if the guarded deployment lacks it.
    assert "data-notable" not in guarded
    assert _sentence("admin.surfaces.mcp.guarded") in guarded


def test_private_targets_are_marked_only_where_a_stranger_can_find_the_service():
    """The one combination that is almost never meant: a scanner that can be
    found, pointed at the network it stands in.

    On a deployment that asked not to be indexed the same setting is the
    entire point of the deployment, and marking it there would be an area
    that cries wolf about its own correct configuration.
    """
    public = _admin_settings(allow_private_targets=True)
    private = _admin_settings(allow_private_targets=True, allow_indexing=False)

    with TestClient(create_app(public)) as client:
        found = _row(client.get("/admin", headers=FORWARDED).text, "private")
    with TestClient(create_app(private)) as client:
        estate = _row(client.get("/admin", headers=FORWARDED).text, "private")

    assert "data-notable" in found
    assert _sentence("admin.surfaces.private.found") in found
    assert "data-notable" not in estate
    assert _sentence("admin.surfaces.private.estate") in estate


def test_the_card_says_where_the_audit_trail_is_kept():
    """A trail in one process's memory and a trail on disk are different answers.

    ADR 0035's limit again, said where an operator is asking what this
    deployment keeps: without a file the window is a bounded ring that a
    restart takes with it.
    """
    ring = _admin_settings(audit_log=True)
    with TestClient(create_app(ring)) as client:
        page = client.get("/admin", headers=FORWARDED).text
        memory = _row(page, "audit")
        # The trail exists, so what it records about a target is a reading
        # about this deployment.
        assert _row(page, "targets")

    on_disk = _admin_settings(audit_log=True, audit_log_file="/dev/null")
    with TestClient(create_app(on_disk)) as client:
        filed = _row(client.get("/admin", headers=FORWARDED).text, "audit")

    assert str(ring.admin_audit_buffer) in memory
    assert _sentence("admin.surfaces.audit.file") in filed
    assert _sentence("admin.surfaces.audit.file") not in memory


def test_nothing_is_claimed_about_a_trail_this_deployment_does_not_keep():
    """With the audit log off, "targets in the clear" is not a reading at all.

    A pill saying `off` there would answer a question about a trail that does
    not exist, which is an answer somebody can act on wrongly.
    """
    with TestClient(create_app(_admin_settings())) as client:
        page = client.get("/admin", headers=FORWARDED).text

    assert 'data-surface="targets"' not in page
    # And the trail itself is still reported, as off.
    assert 'data-state="off"' in _row(page, "audit")


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


def test_a_store_that_is_gone_is_not_reported_as_a_worker_that_died(monkeypatch):
    """Two outages that drew one picture, and pointed at the wrong container.

    The worker's heartbeat is a key in the store, so a store that is gone
    takes the answer with it. Reporting that as "the worker is not answering"
    is an area that sends an operator to restart a container that may be
    perfectly healthy - and this is the failure they are most likely to be
    reading this page during. `alive` is null exactly when nothing was
    learned, and `store.reachable` names what to go and look at.
    """
    app = create_app(_admin_settings())

    async def unavailable(*_keys):
        from webapp.redis_backend import RedisUnavailable

        raise RedisUnavailable()

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.backend, "health", unavailable)
        gone = client.get("/admin/state", headers=FORWARDED).json()

    assert gone["store"]["reachable"] is False
    assert gone["worker"]["alive"] is None
    assert gone["worker"]["queueDepth"] is None


def test_a_store_that_answers_is_evidence_about_the_worker():
    """The other half: with the store up, a silent worker really is silent.

    Nothing is running a worker in a test client, so this is the deployment
    whose worker has genuinely not written a heartbeat - and it must read as
    a fact rather than as the absence of one.
    """
    with TestClient(create_app(_admin_settings())) as client:
        answered = client.get("/admin/state", headers=FORWARDED).json()

    assert answered["store"]["reachable"] is True
    assert answered["worker"]["alive"] is False
    assert answered["worker"]["queueDepth"] == 0


def test_the_tile_says_which_of_the_two_outages_it_is():
    """The distinction is only worth having if the page draws it.

    ADMIN.md's troubleshooting table had to explain in prose that a `/healthz`
    503 means the worker *or* the store; the tile can simply say which.
    """
    with TestClient(create_app(_admin_settings())) as client:
        page = client.get("/admin", headers=FORWARDED).text
        script = client.get("/static/js/admin.js").text

    from webapp.locales.en import MESSAGES

    # The third sentence is the server's, in the language the page is in.
    assert MESSAGES["admin.state.worker.unknown"] in page
    assert MESSAGES["admin.state.store.down"] in page
    # And the script reaches it from the reading rather than from a guess.
    assert "store.reachable === false" in script
    assert "worker.alive === null" in script


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


def _shipped_index(root, *, built_for, extra=()):
    """An index this build would call current, plus whatever is added to it.

    Derived from the pages and the catalogues rather than written out here,
    because a fixture listing them by hand goes stale the first time a page
    is added and then tests nothing.
    """
    from webapp.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES, Translator
    from webapp.search import SEARCH_PAGES

    static = root / "static"
    static.mkdir(parents=True, exist_ok=True)
    for locale in SUPPORTED_LOCALES:
        translate = Translator(locale)
        pages = [
            {
                "path": page.path,
                "title": translate(page.title_key) if page.title_key else page.title,
                "summary": (
                    translate(page.summary_key) if page.summary_key else page.summary
                ),
            }
            for page in SEARCH_PAGES
        ]
        document = {"pages": pages}
        if locale == DEFAULT_LOCALE:
            pages.extend(
                {"path": path, "title": "", "summary": ""} for path in extra
            )
            if built_for is not None:
                document["builtFor"] = built_for
        name = (
            "search-index.json"
            if locale == DEFAULT_LOCALE
            else f"search-index.{locale}.json"
        )
        (static / name).write_text(json.dumps(document), encoding="utf-8")
    return root


def test_an_index_holding_a_page_that_is_no_longer_served_is_not_current(tmp_path):
    """A search result leading to a page that is not there.

    The reading exists and has always been in the document; what it needs is
    to be a reason the card can state, because a verdict of "out of date"
    with no reason under it is a verdict nobody can act on.
    """
    from webapp import __version__
    from webapp.admin import index_freshness

    stale = index_freshness(
        _shipped_index(tmp_path / "gone", built_for=__version__, extra=("/removed",))
    )
    current = index_freshness(_shipped_index(tmp_path / "ok", built_for=__version__))

    assert stale.fresh is False
    assert stale.extra_paths == ("/removed",)
    # And the same index without the extra page is current, so the reason
    # above is the reason.
    assert current.fresh is True
    assert current.extra_paths == ()


def test_the_verdict_and_the_sentence_under_it_cannot_contradict_each_other():
    """Every reason the index is not current has a sentence, and every
    sentence the script asks for is one the server rendered.

    The card is a heading and one line, and they are written in two different
    places: a reason counted in the freshness test but never described leaves
    "Out of date" standing over "everything is indexed", and one of the two
    is being read with no way to tell which.
    """
    with TestClient(create_app(_admin_settings())) as client:
        page = client.get("/admin", headers=FORWARDED).text
        script = client.get("/static/js/admin.js").text

    # Every reading that makes an index stale is one the script consults.
    for reason in ("missingPaths", "missingLocales", "extraPaths", "changedPaths"):
        assert reason in script, f"{reason} makes an index stale and is never read"

    # And every sentence it looks up by name is one the page carries. The
    # dynamic lookups are concatenations and deliberately not matched here.
    for name in set(re.findall(r'text\("([a-z0-9-]+)"\)', script)):
        assert f'data-admin-{name}="' in page, f"admin.js reads {name}, page has none"


def test_an_index_that_does_not_say_which_release_it_was_built_for_says_so(tmp_path):
    """The colour honoured this and the word did not.

    An unstamped index was reported "Current" in the grey that means "no
    idea": the pages and the languages were compared, the copy could not be,
    because only the stamp says which release the copy was extracted from.
    """
    from webapp.admin import index_freshness

    unstamped = index_freshness(_shipped_index(tmp_path, built_for=None))

    # The backend asserts neither answer: nothing it compared was wrong.
    assert unstamped.built_for is None
    assert unstamped.fresh is True

    with TestClient(create_app(_admin_settings())) as client:
        page = client.get("/admin", headers=FORWARDED).text
        script = client.get("/static/js/admin.js").text

    from webapp.locales.en import MESSAGES

    # The verdict has a word of its own rather than borrowing "Current"...
    assert MESSAGES["admin.search.unknown"] in page
    assert MESSAGES["admin.search.unknown"] != MESSAGES["admin.search.fresh"]
    assert 'text("index-unknown")' in script
    # ...and the line under it does not claim the release it cannot know.
    assert _sentence("admin.search.detail.unstamped") in page
    assert 'text("index-unstamped")' in script


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
