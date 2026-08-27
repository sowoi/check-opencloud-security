"""
The daily lifecycle refresh.

The schedule that ships in the wheel ages: a deployment that has been up for
six weeks rates instances against a six-week-old picture of the world, calls
a current release "ahead of the schedule" and an expired line "supported".
These tests hold the refresh to the three rules that make fixing that safe -
a refresh may only add knowledge, a failure changes nothing, and a newer
bundled file always wins - and to the rule that it never touches the
repository.

The lifecycle page is served by a real HTTP server rather than a mocked
fetch, and its content is rendered back out of the schedule that actually
ships, so a hand-written table cannot drift away from the real one.
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from opencloud_local_scan.versions import (
    RELEASE_SCHEDULE_FILE,
    load_release_schedule,
    schedule_from_document,
)
from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    MEMORY_URL,
    _isolated_backend,
    _offline_resolver,
    backend,
    settings,
)
from webapp.redis_backend import memory_backend
from webapp.schedule import (
    SCHEDULE_CHECKED_KEY,
    SCHEDULE_DOCUMENT_KEY,
    refresh_schedule,
    schedule_state,
    stored_schedule,
)
from webapp.tasks import reference_data_jobs

BUNDLED = json.loads(RELEASE_SCHEDULE_FILE.read_text(encoding="utf-8"))


def _page_date(iso: str) -> str:
    """'2026-08-03' as the documentation writes it: '2026 August 3'."""
    parsed = datetime.strptime(iso, "%Y-%m-%d").date()  # noqa: DTZ007
    return f"{parsed.year} {parsed.strftime('%B')} {parsed.day}"


def lifecycle_page(document: dict[str, Any]) -> str:
    """Render a release schedule document back into the published page.

    Docusaurus puts the track name in ``li[role=tab]`` elements and the tables in
    the ``div[role=tabpanel]`` elements that follow, in the same order.
    """
    labels = {"rolling": "rolling", "production": "production", "lts": "lts"}
    tabs: list[str] = []
    panels: list[str] = []
    for track, label in labels.items():
        rows = "".join(
            f"<tr><td>{entry['latest']}</td><td>{_page_date(entry['released'])}</td>"
            "<td><a href='https://example.invalid/notes'>Details</a></td></tr>"
            for entry in document["lines"]
            if track in entry["tracks"]
        )
        tabs.append(f'<li role="tab">{label}</li>')
        panels.append(
            f'<div role="tabpanel"><table><thead><tr><th>Version</th>'
            f"<th>Release Date</th></tr></thead><tbody>{rows}</tbody></table></div>"
        )
    body = "".join(tabs) + "".join(panels)
    return f"<html><body><div class='tabs'>{body}</div></body></html>"


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.server.requests += 1  # type: ignore[attr-defined]
        body = self.server.body.encode("utf-8")  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        """Keep the test output readable."""


class FakeLifecycleSite:
    """The documentation page, served over real HTTP on a real socket."""

    def __init__(self, body: str) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.body = body  # type: ignore[attr-defined]
        self._server.requests = 0  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> FakeLifecycleSite:  # noqa: PYI034 - a context manager, not a protocol
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/lifecycle/"

    @property
    def requests(self) -> int:
        return self._server.requests  # type: ignore[attr-defined]


def with_extra_release(version: str, released: date, track: str) -> dict[str, Any]:
    """The bundled schedule plus one release that has not shipped in it yet."""
    major, minor, _ = version.split(".")
    document = json.loads(json.dumps(BUNDLED))
    document["lines"].insert(
        0,
        {
            "line": f"{major}.{minor}",
            "tracks": [track],
            "released": released.isoformat(),
            "latest": version,
        },
    )
    return document


def refresh_settings(**overrides: Any):
    """Web settings with the refresh on and pointing at a test server."""
    options = {"schedule_refresh": True}
    options.update(overrides)
    return settings(**options)


def run(coro):
    """Run one coroutine, the way the worker's event loop would."""
    return asyncio.run(coro)


def test_a_release_the_bundled_schedule_has_never_heard_of_reaches_a_scan():
    """The whole point: a new OpenCloud release without redeploying this one."""
    tomorrow = datetime.now(tz=timezone.utc).date() + timedelta(days=1)
    published = with_extra_release("99.9.0", tomorrow, "rolling")
    store = memory_backend(MEMORY_URL)

    with FakeLifecycleSite(lifecycle_page(published)) as site:
        configured = refresh_settings(schedule_refresh_url=site.url)
        assert run(refresh_schedule(store, configured)) == "updated"
        refreshed = run(stored_schedule(store, configured))

    assert refreshed.latest_for("rolling") == "99.9.0"
    # Without the refresh the very same deployment knows nothing about it.
    assert load_release_schedule().latest_for("rolling") != "99.9.0"


def test_an_unreachable_lifecycle_page_leaves_the_schedule_exactly_as_it_was():
    """A documentation site that is down must not change a single verdict."""
    store = memory_backend(MEMORY_URL)
    # A port nothing listens on: the socket is refused, not slow.
    configured = refresh_settings(schedule_refresh_url="http://127.0.0.1:1/lifecycle/")

    assert run(refresh_schedule(store, configured)) == "failed"

    assert run(store.get(SCHEDULE_DOCUMENT_KEY)) is None
    kept = run(stored_schedule(store, configured))
    assert kept.lines == load_release_schedule().lines


def test_a_page_that_has_lost_a_release_line_is_refused():
    """Losing a line would turn an end-of-life instance into an unknown one."""
    pruned = json.loads(json.dumps(BUNDLED))
    dropped = pruned["lines"].pop()
    store = memory_backend(MEMORY_URL)

    with FakeLifecycleSite(lifecycle_page(pruned)) as site:
        configured = refresh_settings(schedule_refresh_url=site.url)
        assert run(refresh_schedule(store, configured)) == "rejected"
        # The same page with the line back in place is accepted, so it is the
        # missing line that was refused and not the page.
        restored = json.loads(json.dumps(BUNDLED))
        assert dropped in restored["lines"]

    with FakeLifecycleSite(lifecycle_page(restored)) as site:
        configured = refresh_settings(schedule_refresh_url=site.url)
        assert run(refresh_schedule(store, configured)) in {"updated", "unchanged"}

    assert run(store.get(SCHEDULE_DOCUMENT_KEY)) is not None


def test_a_refresh_cannot_change_the_support_facts_of_a_known_line():
    """
    Track membership and first release date decide end-of-life, not just names.

    A parser regression that drops a production track would make a supported
    release appear unsupported, so a candidate may only add a newer patch.
    """
    changed = json.loads(json.dumps(BUNDLED))
    known = next(entry for entry in changed["lines"] if "production" in entry["tracks"])
    known["tracks"].remove("production")
    store = memory_backend(MEMORY_URL)

    with FakeLifecycleSite(lifecycle_page(changed)) as site:
        assert run(
            refresh_schedule(store, refresh_settings(schedule_refresh_url=site.url))
        ) == "rejected"

    assert run(store.get(SCHEDULE_DOCUMENT_KEY)) is None


def test_a_page_that_is_not_a_release_table_at_all_is_refused():
    """A redesigned documentation site must not empty the schedule."""
    store = memory_backend(MEMORY_URL)

    with FakeLifecycleSite("<html><body><p>Moved.</p></body></html>") as site:
        configured = refresh_settings(schedule_refresh_url=site.url)
        assert run(refresh_schedule(store, configured)) == "failed"

    assert run(stored_schedule(store, configured)).lines == load_release_schedule().lines


def test_a_stored_schedule_older_than_the_bundled_one_is_ignored():
    """A redeployment ships a schedule CI checked; Redis must not undo it."""
    stale = json.loads(json.dumps(BUNDLED))
    stale["updated"] = "2000-01-01"
    stale["latest_release"] = {"rolling": "1.0.0", "production": "1.0.0"}
    store = memory_backend(MEMORY_URL)
    run(store.set(SCHEDULE_DOCUMENT_KEY, json.dumps(stale)))

    configured = refresh_settings()
    assert run(stored_schedule(store, configured)).latest_for("rolling") == (
        load_release_schedule().latest_for("rolling")
    )
    # The stored document really would have said something else.
    assert schedule_from_document(stale).latest_for("rolling") == "1.0.0"


def test_a_corrupt_stored_document_falls_back_to_the_bundled_schedule():
    """Whatever is in Redis, a scan still gets a schedule to rate against."""
    store = memory_backend(MEMORY_URL)
    run(store.set(SCHEDULE_DOCUMENT_KEY, "{not json"))

    kept = run(stored_schedule(store, refresh_settings()))
    assert kept.lines == load_release_schedule().lines


def test_turning_the_refresh_off_asks_the_documentation_site_nothing():
    """A deployment without outbound access keeps working, and stays quiet."""
    store = memory_backend(MEMORY_URL)

    with FakeLifecycleSite(lifecycle_page(BUNDLED)) as site:
        configured = refresh_settings(schedule_refresh=False, schedule_refresh_url=site.url)
        assert run(refresh_schedule(store, configured)) == "disabled"
        assert site.requests == 0

        # And with it on, the very same page is fetched.
        enabled = refresh_settings(schedule_refresh_url=site.url)
        run(refresh_schedule(store, enabled))
        assert site.requests == 1


def test_the_daily_job_exists_only_when_the_refresh_is_enabled():
    """The switch has to reach the worker, not just the settings object."""
    pytest.importorskip("arq")

    jobs = reference_data_jobs(
        refresh_settings(schedule_refresh_hour=3, advisory_refresh=False)
    )
    assert [job.name for job in jobs] == ["refresh_release_schedule"]
    assert jobs[0].hour == 3
    assert jobs[0].run_at_startup is True

    off = refresh_settings(schedule_refresh=False, advisory_refresh=False)
    assert reference_data_jobs(off) == []


def test_the_refresh_writes_nothing_into_the_repository():
    """CI owns the checked-in schedule and the README; a running service does not."""
    readme = Path(RELEASE_SCHEDULE_FILE).resolve().parent.parent.parent / "README.md"
    before = (RELEASE_SCHEDULE_FILE.read_bytes(), readme.read_bytes())
    tomorrow = datetime.now(tz=timezone.utc).date() + timedelta(days=1)
    store = memory_backend(MEMORY_URL)

    with FakeLifecycleSite(lifecycle_page(with_extra_release("99.9.0", tomorrow, "rolling"))) as site:
        configured = refresh_settings(schedule_refresh_url=site.url)
        assert run(refresh_schedule(store, configured)) == "updated"

    assert (RELEASE_SCHEDULE_FILE.read_bytes(), readme.read_bytes()) == before


def test_a_second_identical_refresh_is_reported_as_unchanged():
    """An operator reading the log should see a daily no-op as a no-op."""
    store = memory_backend(MEMORY_URL)

    with FakeLifecycleSite(lifecycle_page(BUNDLED)) as site:
        configured = refresh_settings(schedule_refresh_url=site.url)
        assert run(refresh_schedule(store, configured)) == "updated"
        assert run(refresh_schedule(store, configured)) == "unchanged"


def test_the_health_probe_reports_when_the_schedule_was_last_read():
    """An operator needs to see that the daily refresh is actually happening."""
    store = memory_backend(MEMORY_URL)
    configured = refresh_settings()

    assert run(schedule_state(store, configured))["checked"] is None

    with FakeLifecycleSite(lifecycle_page(BUNDLED)) as site:
        configured = refresh_settings(schedule_refresh_url=site.url)
        run(refresh_schedule(store, configured))

    state = run(schedule_state(store, configured))
    assert state["refresh"] is True
    assert state["checked"] is not None
    assert state["checked"].startswith(datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"))
    assert run(store.get(SCHEDULE_CHECKED_KEY)) == state["checked"]


def test_a_refreshed_schedule_stops_calling_the_new_release_a_stale_database():
    """The notice a scan carries is the reason to refresh; it must clear."""
    tomorrow = datetime.now(tz=timezone.utc).date() + timedelta(days=1)
    published = with_extra_release("99.9.0", tomorrow, "rolling")
    store = memory_backend(MEMORY_URL)

    assert load_release_schedule().is_behind("99.9.0") is True

    with FakeLifecycleSite(lifecycle_page(published)) as site:
        configured = refresh_settings(schedule_refresh_url=site.url)
        run(refresh_schedule(store, configured))
        refreshed = run(stored_schedule(store, configured))

    assert refreshed.is_behind("99.9.0") is False
