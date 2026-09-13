"""
The one control in the operator's area that writes.

Everything else there reads a setting or presses one of the worker's two
refreshes. This changes what the service will do - and it has to do so
*immediately*, in an API process and a worker that were both started before
anybody typed the entry, or the control is a promise the service does not
keep.

So these tests are mostly about reach: that an entry added here refuses the
next submission with nothing restarted, that a job already queued is refused
rather than run, that what the environment declares cannot be withdrawn from
a browser, and that the area has not quietly acquired the ability to do
anything else.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    _isolated_backend,
    _offline_resolver,
    backend,
    settings,
)
from webapp.app import create_app
from webapp.blocklist import (
    BLOCKLIST_KEY,
    MAX_STORED_ENTRIES,
    EntryRejected,
    Exclusions,
    add_exclusion,
    effective_exclusions,
    read_exclusions,
)
from webapp.runner import execute_scan
from webapp.ssrf import TargetRejected, validate_target

SECRET = "b" * 48
OPERATOR = "okko"

FORWARDED = {
    "x-cos-admin-proxy": SECRET,
    "x-authentik-username": OPERATOR,
    "sec-fetch-site": "same-origin",
}

TARGET = "https://cloud.example.com"


def _admin_settings(**overrides):
    return settings(
        admin_enabled=True,
        admin_proxy_secret=SECRET,
        admin_users=(OPERATOR,),
        **overrides,
    )


def _exclude(client, entry: str, action: str = "add"):
    return client.post(
        "/admin/exclusions",
        data={"action": action, "entry": entry},
        headers={**FORWARDED, "accept": "application/json"},
    )


def test_an_entry_added_in_the_area_refuses_the_very_next_submission():
    """
    The whole point of the control, and the thing a restart would hide.

    The application here is one process that was started before the entry
    existed, so a list held from startup would still accept this target.
    """
    with TestClient(create_app(_admin_settings())) as client:
        before = client.post("/api/scans", json={"target_url": TARGET})
        added = _exclude(client, "cloud.example.com")
        after = client.post("/api/scans", json={"target_url": TARGET})

    assert before.status_code == 202
    assert added.status_code == 200
    assert added.json()["state"] == "excluded"
    assert after.status_code == 400
    assert "uuid" not in after.json()


def test_withdrawing_an_entry_lets_the_target_through_again():
    """
    A control that could only ever refuse more would be a ratchet.

    An exclusion is an answer to a request, and requests are withdrawn.
    """
    with TestClient(create_app(_admin_settings())) as client:
        _exclude(client, "cloud.example.com")
        refused = client.post("/api/scans", json={"target_url": TARGET})
        withdrawn = _exclude(client, "cloud.example.com", action="remove")
        allowed = client.post("/api/scans", json={"target_url": TARGET})

    assert refused.status_code == 400
    assert withdrawn.json()["state"] == "withdrawn"
    assert allowed.status_code == 202


def test_a_scan_already_queued_is_refused_rather_than_run():
    """
    "Immediately" has to include the job that was accepted a moment ago.

    The worker reads the exclusions when the job starts, so an operator who
    excludes a target while its scan waits in the queue has stopped that
    scan - not merely the next one.
    """
    store = backend()
    configured = _admin_settings()
    # The target as the submission accepted it, before anything was excluded.
    queued = validate_target(TARGET)
    assert asyncio.run(effective_exclusions(store, configured)) == ()

    asyncio.run(add_exclusion(store, configured, "cloud.example.com"))
    exclusions = asyncio.run(effective_exclusions(store, configured))

    # The worker's own entry point, which revalidates before it connects to
    # anything - so this raises rather than reaching the instance.
    with pytest.raises(TargetRejected):
        execute_scan(queued, (), configured, blocked_targets=exclusions)


def test_what_the_environment_declares_cannot_be_withdrawn_from_a_browser():
    """
    The compose file has to stay true whatever happens in the area.

    Refused rather than silently ignored: doing nothing would read as
    "removed" on the next page load, and an operator would believe an
    exclusion was gone that is still in force.
    """
    configured = _admin_settings(blocked_targets=("cloud.example.com",))
    with TestClient(create_app(configured)) as client:
        refused = _exclude(client, "cloud.example.com", action="remove")
        still = client.post("/api/scans", json={"target_url": TARGET})

    assert refused.status_code == 422
    assert refused.json()["key"] == "admin.blocklist.error.configured"
    assert still.status_code == 400


def test_the_two_halves_are_shown_apart_and_read_as_one_list():
    """
    An operator has to see which entries survive a restart and which do not.

    The guard is handed one list; the page shows two, because only one of
    them is the deployment's own promise.
    """
    store = backend()
    configured = _admin_settings(blocked_targets=("a.example.com",))

    asyncio.run(add_exclusion(store, configured, "b.example.com"))
    exclusions = asyncio.run(read_exclusions(store, configured))

    assert exclusions.configured == ("a.example.com",)
    assert exclusions.stored == ("b.example.com",)
    assert exclusions.effective == ("a.example.com", "b.example.com")


def test_an_entry_is_stored_in_one_spelling_however_it_is_typed():
    """
    Otherwise the list fills with three spellings of one exclusion.

    And, worse, withdrawing the one that is shown would leave the other two
    in force with nothing on the page to say so.
    """
    store = backend()
    configured = _admin_settings()

    for spelling in ("Cloud.Example.com", "cloud.example.com.", "cloud.example.com"):
        asyncio.run(add_exclusion(store, configured, spelling))
    asyncio.run(add_exclusion(store, configured, "*.example.org"))
    asyncio.run(add_exclusion(store, configured, "192.0.2.7/32"))

    stored = asyncio.run(read_exclusions(store, configured)).stored
    assert stored == ("cloud.example.com", ".example.org", "192.0.2.7")


def test_an_entry_nobody_could_act_on_is_refused_and_changes_nothing():
    """
    The startup check cannot help here: this entry arrives at runtime.

    So it is validated where it is written, and a list that could hold an
    entry the guard ignores would be a page showing a promise nothing keeps.
    """
    store = backend()
    configured = _admin_settings()

    with pytest.raises(EntryRejected):
        asyncio.run(add_exclusion(store, configured, "not a hostname!"))

    assert asyncio.run(read_exclusions(store, configured)).stored == ()


def test_the_area_stores_no_more_entries_than_it_says():
    """
    A control that writes to Redis must not be a way to fill it.

    The ceiling is the area's, not the guard's: an operator with a longer
    list has COS_WEB_BLOCKED_TARGETS, which is read once at startup.
    """
    store = backend()
    configured = _admin_settings()
    for index in range(MAX_STORED_ENTRIES):
        asyncio.run(add_exclusion(store, configured, f"host{index}.example.com"))

    with pytest.raises(EntryRejected):
        asyncio.run(add_exclusion(store, configured, "one-too-many.example.com"))

    assert len(asyncio.run(read_exclusions(store, configured)).stored) == MAX_STORED_ENTRIES


def test_a_stored_list_that_cannot_be_read_excludes_nothing_extra():
    """
    Somebody else's key, or a corrupted one, is not a list of exclusions.

    It must not crash a submission either - the environment's own half is
    still in force, and that is the half a deployment declared.
    """
    store = backend()
    configured = _admin_settings(blocked_targets=("a.example.com",))
    asyncio.run(store.set(BLOCKLIST_KEY, "not json at all"))

    exclusions = asyncio.run(read_exclusions(store, configured))

    assert exclusions.stored == ()
    assert exclusions.effective == ("a.example.com",)


def test_a_stranger_cannot_reach_the_control_at_all():
    """
    The area is 404 to anybody but the operator, and so is what it writes.

    A write endpoint that answered 401 would tell a stranger the area exists,
    which is the property ADR 0035 exists to keep.
    """
    with TestClient(create_app(_admin_settings())) as client:
        unsigned = client.post(
            "/admin/exclusions", data={"action": "add", "entry": "cloud.example.com"}
        )
        wrong_secret = client.post(
            "/admin/exclusions",
            data={"action": "add", "entry": "cloud.example.com"},
            headers={**FORWARDED, "x-cos-admin-proxy": "c" * 48},
        )
        allowed = client.post("/api/scans", json={"target_url": TARGET})

    assert unsigned.status_code == 404
    assert wrong_secret.status_code == 404
    # And neither attempt excluded anything.
    assert allowed.status_code == 202


def test_the_control_meets_the_cross_site_check_every_other_post_does():
    """
    The area is reachable from a browser, so a foreign page can post to it.

    An operator whose browser was borrowed would be excluding targets for
    somebody else - a denial of service against an instance they run,
    written in their own audit trail.
    """
    with TestClient(create_app(_admin_settings())) as client:
        refused = client.post(
            "/admin/exclusions",
            data={"action": "add", "entry": "cloud.example.com"},
            headers={**FORWARDED, "sec-fetch-site": "cross-site"},
        )
        allowed = client.post("/api/scans", json={"target_url": TARGET})

    assert refused.status_code != 200
    assert allowed.status_code == 202


def test_an_action_the_area_does_not_offer_is_refused():
    """The two verbs are add and remove; anything else is a caller guessing."""
    with TestClient(create_app(_admin_settings())) as client:
        answer = _exclude(client, "cloud.example.com", action="purge")

    assert answer.status_code == 422


def test_the_page_shows_the_list_and_never_a_target_anybody_scanned():
    """
    The card is the area's one window onto policy, not onto traffic.

    The property that makes the whole area safe to have is that no target,
    uuid or result is reachable from it; a card listing addresses is exactly
    where that could be lost.
    """
    identifier = "8c1d0e3c-9b2f-4c81-a7e6-2f0b4d9c1e73"
    configured = _admin_settings()
    app = create_app(configured)
    with TestClient(app) as client:
        asyncio.run(
            app.state.store.create(
                identifier,
                target="https://secret-instance.example.com",
                ignore_hardenings=(),
                output_format="dashboard",
            )
        )
        _exclude(client, "excluded.example.com")
        page = client.get("/admin", headers=FORWARDED).text

    assert "excluded.example.com" in page
    assert "secret-instance" not in page
    assert identifier not in page


def test_an_empty_list_is_said_rather_than_drawn_as_nothing():
    """
    A blank card and "nothing is excluded" look the same and mean differently.

    The second is a reading; the first is a page that failed to render one.
    """
    empty = Exclusions()

    assert empty.effective == ()
    with TestClient(create_app(_admin_settings())) as client:
        page = client.get("/admin", headers=FORWARDED).text

    assert "Nothing is excluded" in page
