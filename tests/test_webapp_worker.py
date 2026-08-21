"""
The worker end of the web application.

The API only ever queues; this is where a queued uuid becomes a scan of a real
instance and a rendered dashboard. The instance is
``tests/fake_opencloud.py``, so the expectations come from an actual scan
rather than from a list that goes stale the next time a check is added.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from tests.fake_opencloud import FakeOpenCloud, InstanceBehaviour
from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    MEMORY_URL,
    REBOUND_HOST,
    _isolated_backend,
    _offline_resolver,
    backend,
    client,
    settings,
)
from webapp.catalog import summarise
from webapp.redis_backend import memory_backend
from webapp.schedule import SCHEDULE_DOCUMENT_KEY
from webapp.store import WORKER_HEARTBEAT_KEY, ScanStore
from webapp.tasks import HEARTBEAT_TTL_SECONDS, publish_worker_heartbeat, run_scan


def _worker_context(**overrides):
    """The context ARQ would build, without needing ARQ or a Redis server."""
    options = {"allow_private_targets": True, "verify_tls": False, "scan_timeout": 5}
    options.update(overrides)
    configured = settings(**options)
    store = ScanStore(backend=memory_backend(MEMORY_URL), ttl=configured.result_ttl)
    return {"web_settings": configured, "store": store}, store


def _queue(store: ScanStore, target: str, waivers: tuple[str, ...] = ()) -> str:
    identifier = "b6f2c0c5-1c4b-4f4e-9a3b-0d3f8b7c1a20"
    asyncio.run(
        store.create(
            identifier, target=target, ignore_hardenings=waivers, output_format="dashboard"
        )
    )
    return identifier


def test_a_worker_heartbeat_expires_when_the_worker_stops():
    """Health must not report a worker alive after its process has disappeared."""
    store = memory_backend(MEMORY_URL)

    asyncio.run(publish_worker_heartbeat(store))

    assert asyncio.run(store.ttl(WORKER_HEARTBEAT_KEY)) == HEARTBEAT_TTL_SECONDS
    store.advance(HEARTBEAT_TTL_SECONDS + 1)
    assert asyncio.run(store.ttl(WORKER_HEARTBEAT_KEY)) == -2


def test_a_queued_scan_becomes_a_result_document_under_its_own_uuid():
    """
    The whole point of the service, in one test.

    It also pins the layering: the document the worker stores is the scanner's
    own, key for key, so the dashboard is a view of the plugin's data rather
    than a second opinion.
    """
    context, store = _worker_context()

    with FakeOpenCloud() as instance:
        identifier = _queue(store, f"http://{instance.host}")
        outcome = asyncio.run(run_scan(context, identifier))

    assert outcome == "completed"

    record = asyncio.run(store.get(identifier))
    assert record is not None
    assert record.state == "completed"
    assert record.result is not None
    assert record.result["product"] == "OpenCloud"
    assert record.result["rating"] in range(6)
    assert "extraChecks" in record.result
    assert record.result["scanner"].startswith("check-opencloud-security")


def test_the_dashboard_summary_only_rearranges_what_the_scanner_reported():
    """
    The summary must not invent a verdict.

    Every count it shows has to be derivable from the document itself; if the
    two ever disagree, the page is lying about a scan that already happened.
    """
    context, store = _worker_context()

    with FakeOpenCloud() as instance:
        identifier = _queue(store, f"http://{instance.host}")
        asyncio.run(run_scan(context, identifier))

    record = asyncio.run(store.get(identifier))
    summary = summarise(record.result)

    assert summary["rating"] == record.result["rating"]
    assert summary["eol"] == bool(record.result["EOL"])
    assert summary["version"] == record.result["version"]
    assert summary["counts"]["vulnerabilities"] == len(record.result["vulnerabilities"])
    assert len(summary["issues"]) == (
        summary["counts"]["critical"]
        + summary["counts"]["warning"]
        + summary["counts"]["info"]
    )
    # Findings that nobody can act on stay out of the actionable list.
    assert all(item["id"] not in summary["unfixable"] for item in summary["issues"])


def test_a_waiver_chosen_in_the_form_reaches_the_scanner_and_is_marked():
    """
    A waived check has to stay visible, or the waiver becomes a blind spot.

    The negative half matters most: without the waiver the same check is a
    plain failure, so the test cannot pass if waivers stopped working.
    """
    behaviour = InstanceBehaviour(basic_auth=True)
    context, store = _worker_context()

    with FakeOpenCloud(behaviour) as instance:
        target = f"http://{instance.host}"
        plain = _queue(store, target)
        asyncio.run(run_scan(context, plain))
        without_waiver = asyncio.run(store.get(plain)).result

        asyncio.run(
            store.create(
                "0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa",
                target=target,
                ignore_hardenings=("basicAuthDisabled",),
                output_format="dashboard",
            )
        )
        asyncio.run(run_scan(context, "0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa"))
        with_waiver = asyncio.run(
            store.get("0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa")
        ).result

    def entry(document):
        return next(
            item
            for item in document["extraChecks"]
            if item["id"] == "basicAuthDisabled"
        )

    assert entry(without_waiver)["passed"] is False
    assert not entry(without_waiver).get("ignored")
    assert entry(with_waiver)["passed"] is False
    assert entry(with_waiver)["ignored"] is True
    assert with_waiver["rating"] >= without_waiver["rating"]


def test_an_unreachable_instance_fails_the_scan_rather_than_the_worker():
    """
    A bad target is somebody's typo, not an outage.

    The failure has to land in that scan's own state so the visitor is told,
    and the worker has to stay up for everybody else in the queue.
    """
    context, store = _worker_context()
    identifier = _queue(store, "http://127.0.0.1:9")

    outcome = asyncio.run(run_scan(context, identifier))

    record = asyncio.run(store.get(identifier))
    assert outcome == "failed"
    assert record.state == "failed"
    assert record.error
    assert record.result is None


def test_a_target_that_turned_private_since_submission_is_refused_by_the_worker():
    """
    The DNS rebinding answer, and the reason the guard runs twice.

    A name that resolved publicly when the request was accepted may resolve to
    an internal address by the time a worker is free. Checking again in the
    worker is what closes that window.
    """
    context, store = _worker_context(allow_private_targets=False)
    identifier = _queue(store, f"http://{REBOUND_HOST}")

    outcome = asyncio.run(run_scan(context, identifier))

    record = asyncio.run(store.get(identifier))
    assert outcome == "failed"
    assert record.state == "failed"
    assert "private" in record.error


def test_running_a_scan_takes_it_out_of_the_queue_it_was_waiting_in():
    """
    The position a waiting visitor is shown has to mean something.

    If a started scan stayed in the line, everybody behind it would be told
    they are further back than they are, forever.
    """
    context, store = _worker_context()

    with FakeOpenCloud() as instance:
        identifier = _queue(store, f"http://{instance.host}")
        assert asyncio.run(store.get(identifier)).queue_position == 1
        asyncio.run(run_scan(context, identifier))

    record = asyncio.run(store.get(identifier))
    assert record.queue_position is None
    assert record.queue_length == 0


def test_an_expired_scan_is_not_scanned_when_the_worker_finally_reaches_it():
    """
    A scan nobody can read any more must not be run.

    Otherwise a long queue turns an expired page into a request somebody
    else's instance still receives.
    """
    context, store = _worker_context(result_ttl=60)

    with FakeOpenCloud() as instance:
        identifier = _queue(store, f"http://{instance.host}")
        backend().advance(61)
        outcome = asyncio.run(run_scan(context, identifier))

    assert outcome == "expired"
    assert asyncio.run(store.get(identifier)) is None


@pytest.mark.parametrize("state", ["queued", "running", "completed"])
def test_the_scan_page_renders_every_state_it_can_be_in(state):
    """
    Each lifecycle state has a page, and none of them is a traceback.

    The progress panel disappears exactly when there is a result to replace
    it, which is the transition the polling script depends on.
    """
    test_client = client(allow_private_targets=True, verify_tls=False)
    identifier = test_client.post(
        "/api/scans", json={"target_url": "https://opencloud.example.com"}
    ).json()["uuid"]

    store = ScanStore(backend=memory_backend(MEMORY_URL), ttl=3600)
    if state == "running":
        asyncio.run(store.mark_running(identifier))
    elif state == "completed":
        with FakeOpenCloud() as instance:
            context, worker_store = _worker_context()
            scanned = _queue(worker_store, f"http://{instance.host}")
            asyncio.run(run_scan(context, scanned))
            document = asyncio.run(worker_store.get(scanned)).result
        asyncio.run(store.mark_completed(identifier, document))

    page = test_client.get(f"/scan/{identifier}")

    assert page.status_code == 200
    if state == "completed":
        assert "Overall rating" in page.text
        assert 'id="progress-card"' in page.text and "hidden" in page.text
    else:
        assert "progress-title" in page.text
        assert "Overall rating" not in page.text


def test_the_release_track_the_visitor_chose_reaches_the_scanner(monkeypatch):
    """
    The track decides how long a release is supported and what it upgrades to.

    Dropping it would rate a production instance against the rolling calendar
    and call a perfectly supported release end of life, so both halves are
    pinned: the choice arrives, and an unspecified one becomes 'auto' rather
    than silently becoming a track nobody asked for.
    """
    from webapp import runner

    seen: list[str | None] = []

    def _capture(host, *, settings, release_settings, database=None):
        seen.append(settings.release_track)
        return {"rating": 5, "productversion": "7.2.3", "extraChecks": []}

    monkeypatch.setattr(runner, "scan", _capture)
    context, store = _worker_context()

    chosen = "b6f2c0c5-1c4b-4f4e-9a3b-0d3f8b7c1a20"
    asyncio.run(
        store.create(
            chosen,
            target="http://opencloud.example.com",
            ignore_hardenings=(),
            output_format="dashboard",
            release_track="lts",
        )
    )
    asyncio.run(run_scan(context, chosen))

    unspecified = "0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa"
    asyncio.run(
        store.create(
            unspecified,
            target="http://opencloud.example.com",
            ignore_hardenings=(),
            output_format="dashboard",
        )
    )
    asyncio.run(run_scan(context, unspecified))

    assert seen == ["lts", "auto"]
    assert asyncio.run(store.get(chosen)).as_dict()["releaseTrack"] == "lts"


def test_a_refreshed_release_schedule_is_what_a_queued_scan_is_rated_against():
    """
    A release published after this deployment shipped must not look unknown.

    Without the daily refresh reaching the scan, an instance running a version
    the bundled schedule has never heard of is reported with a note telling
    the visitor the database is out of date - which is exactly the state the
    refresh exists to leave behind.
    """
    import json

    from tests.test_webapp_schedule import with_extra_release

    behaviour = InstanceBehaviour()
    behaviour.status_payload["productversion"] = "99.9.0"
    published = with_extra_release("99.9.0", datetime.now(tz=timezone.utc).date() + timedelta(days=1), "rolling")

    # First without the refresh: the scanner says the schedule is behind.
    context, store = _worker_context(schedule_refresh=False)
    with FakeOpenCloud(behaviour) as instance:
        identifier = _queue(store, f"http://{instance.host}")
        asyncio.run(run_scan(context, identifier))
    stale = asyncio.run(store.get(identifier))
    assert stale is not None and stale.result is not None
    assert stale.result["lifecycle"]["scheduleStale"] is True

    # Then with a refresh that has already run.
    context, store = _worker_context()
    asyncio.run(store.backend.set(SCHEDULE_DOCUMENT_KEY, json.dumps(published)))
    with FakeOpenCloud(behaviour) as instance:
        identifier = _queue(store, f"http://{instance.host}")
        asyncio.run(run_scan(context, identifier))
    fresh = asyncio.run(store.get(identifier))
    assert fresh is not None and fresh.result is not None
    assert fresh.result["lifecycle"]["scheduleStale"] is False


def test_a_refreshed_advisory_is_what_a_queued_scan_is_rated_against():
    """
    An advisory published after this deployment shipped must still be reported.

    This is the failure the refresh exists to prevent, and it is a silent one:
    without it the visitor is told their vulnerable instance is fine. So both
    halves are pinned - the same instance is clean against the bundled
    database and vulnerable against the refreshed one.
    """
    import json

    from webapp.reference_data import ADVISORY_DOCUMENT_KEY

    behaviour = InstanceBehaviour()
    behaviour.status_payload["productversion"] = "99.9.0"
    published = {
        "advisories": [
            {
                "id": "TEST-WORKER-1",
                "title": "A finding newer than this build",
                "description": "Reported only when the refresh reaches the scan.",
                "severity": "critical",
                "introduced": "99.0.0",
                "fixed": "99.9.1",
                "source": "https://osv.example.invalid/v1/query",
            }
        ]
    }

    context, store = _worker_context(advisory_refresh=False)
    with FakeOpenCloud(behaviour) as instance:
        identifier = _queue(store, f"http://{instance.host}")
        asyncio.run(run_scan(context, identifier))
    unaware = asyncio.run(store.get(identifier))
    assert unaware is not None and unaware.result is not None
    assert unaware.result["vulnerabilities"] == []

    context, store = _worker_context()
    asyncio.run(store.backend.set(ADVISORY_DOCUMENT_KEY, json.dumps(published)))
    with FakeOpenCloud(behaviour) as instance:
        identifier = _queue(store, f"http://{instance.host}")
        asyncio.run(run_scan(context, identifier))
    aware = asyncio.run(store.get(identifier))
    assert aware is not None and aware.result is not None
    assert [entry["id"] for entry in aware.result["vulnerabilities"]] == [
        "TEST-WORKER-1"
    ]
    assert aware.result["rating"] < unaware.result["rating"], (
        "a critical advisory has to cost the instance its grade, not just "
        "appear in the document"
    )
