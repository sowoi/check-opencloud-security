"""
The daily advisory refresh.

The database that decides whether a scanned instance is called vulnerable is
frozen into the image at build time. An advisory published the day after that
build reaches nobody running it, and every visitor is told their instance is
fine - the one answer a security check must not get wrong by omission.

These tests hold the refresh to the rules that make fixing that safe, and
they are the mirror image of the schedule's. That one fails by *losing* a
line; this one can also fail by *gaining* an advisory. So: a refresh only ever
adds, a failure changes nothing, and nothing unbounded is ever believed -
because a single advisory with no version bounds would report every OpenCloud
instance in the world as vulnerable.

The feed is a real HTTP server answering real OSV JSON, not a mocked fetch,
so the parser is exercised the way the live API exercises it.
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from opencloud_local_scan.vulndb import BUNDLED_DB, is_in_range, parse_document
from tests.webapp_support import (  # noqa: F401 - the fixtures are autouse
    MEMORY_URL,
    _isolated_backend,
    _offline_resolver,
    backend,
    client,
    settings,
)
from webapp.advisories import (
    advisory_catalogue,
    advisory_state,
    refresh_advisories,
    stored_database,
)
from webapp.redis_backend import memory_backend
from webapp.reference_data import ADVISORY_CHECKED_KEY, ADVISORY_DOCUMENT_KEY
from webapp.tasks import reference_data_jobs

BUNDLED = json.loads(BUNDLED_DB.read_text(encoding="utf-8"))


def osv_record(
    identifier: str,
    ranges: list[tuple[str, str | None]],
    *,
    severity: str = "HIGH",
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    """One OSV record for OpenCloud, shaped the way the live API returns it."""
    affected = []
    for introduced, fixed in ranges:
        events: list[dict[str, str]] = [{"introduced": introduced}]
        if fixed is not None:
            events.append({"fixed": fixed})
        affected.append(
            {
                "package": {
                    "name": "github.com/opencloud-eu/opencloud",
                    "ecosystem": "Go",
                },
                "ranges": [{"type": "SEMVER", "events": events}],
            }
        )
    return {
        "id": identifier,
        "aliases": aliases or [],
        "summary": f"Test advisory {identifier}",
        "details": "A finding that exists only in this test.",
        "affected": affected,
        "database_specific": {"severity": severity, "cwe_ids": ["CWE-22"]},
    }


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self.server.requests += 1  # type: ignore[attr-defined]
        status = self.server.status  # type: ignore[attr-defined]
        body = self.server.body.encode("utf-8")  # type: ignore[attr-defined]
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        """Keep the test output readable."""


class FakeAdvisoryFeed:
    """The OSV query API, served over real HTTP on a real socket."""

    def __init__(self, vulns: list[dict[str, Any]], status: int = 200) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.body = json.dumps({"vulns": vulns})  # type: ignore[attr-defined]
        self._server.status = status  # type: ignore[attr-defined]
        self._server.requests = 0  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> FakeAdvisoryFeed:  # noqa: PYI034 - a context manager, not a protocol
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/v1/query"

    @property
    def requests(self) -> int:
        return self._server.requests  # type: ignore[attr-defined]


def refresh_settings(**overrides: Any):
    """Web settings with the advisory refresh on, pointing at a test feed."""
    options: dict[str, Any] = {"advisory_refresh": True, "schedule_refresh": False}
    options.update(overrides)
    return settings(**options)


def run(coro):
    """Run one coroutine, the way the worker's event loop would."""
    return asyncio.run(coro)


def test_an_advisory_published_today_reaches_a_scan_run_tomorrow():
    """The whole point: a finding newer than the image still gets reported."""
    store = memory_backend(MEMORY_URL)
    record = osv_record("TEST-9001", [("9.0.0", "9.0.4")])

    before = run(stored_database(store, refresh_settings()))
    assert before.matches("9.0.1") == [], (
        "the bundled database must not already know this advisory, or the "
        "test would pass with the refresh removed"
    )

    with FakeAdvisoryFeed([record]) as feed:
        outcome = run(
            refresh_advisories(store, refresh_settings(advisory_refresh_url=feed.url))
        )

    assert outcome == "updated"
    after = run(stored_database(store, refresh_settings()))
    matched = after.matches("9.0.1")
    assert [advisory.id for advisory in matched] == ["TEST-9001"]
    assert matched[0].fixed == "9.0.4"
    assert after.matches("9.0.4") == [], "the fixed release must come back clean"


def test_a_refreshed_advisory_reaches_the_public_catalogue_the_same_way():
    """
    The ``/catalogue`` page reads whatever ``stored_database`` returns, so an
    advisory the daily refresh just added must show up there with no second
    place to remember to update - the same guarantee the scan path above
    already has, checked from the catalogue's side instead.
    """
    store = memory_backend(MEMORY_URL)
    record = osv_record("TEST-9002", [("9.0.0", "9.0.4")])

    with FakeAdvisoryFeed([record]) as feed:
        outcome = run(
            refresh_advisories(store, refresh_settings(advisory_refresh_url=feed.url))
        )
    assert outcome == "updated"

    database = run(stored_database(store, refresh_settings()))
    catalogue = advisory_catalogue(database)

    assert "TEST-9002" in {entry["id"] for entry in catalogue}
    assert len(catalogue) == len(database.advisories)


def test_the_public_catalogue_never_renders_an_unsafe_advisory_url_as_a_link():
    """
    A feed-supplied reference URL is attacker-controlled once a feed is read.

    Before an external feed was wired in, every advisory URL came from the
    bundled, developer-controlled database, so its scheme was never worth
    checking. Now a compromised or malformed OSV entry can carry a
    'javascript:' reference straight through ``parse_document`` into
    ``advisory.url``, and the public, unauthenticated ``/catalogue`` page
    must never turn that into a clickable ``href`` - the same guard the scan
    result page already applies to this exact field.
    """
    store = memory_backend(MEMORY_URL)
    record = osv_record("TEST-9099", [("9.0.0", "9.0.4")])
    record["references"] = [{"type": "ADVISORY", "url": "javascript:alert(document.cookie)"}]

    with FakeAdvisoryFeed([record]) as feed:
        outcome = run(
            refresh_advisories(store, refresh_settings(advisory_refresh_url=feed.url))
        )
    assert outcome == "updated"

    body = client(advisory_refresh=True).get("/catalogue").text

    assert "TEST-9099" in body
    assert "javascript:" not in body


def test_an_advisory_with_two_patched_lines_flags_both_of_them():
    """
    One advisory, two release lines patched separately - as GHSA-vf5j-r2hw-2hrw was.

    Reading only the first affected range - as the parser once did - reports an
    instance on the second line as clean, which is a false pass on a live
    vulnerability. The versions here are ones the bundled database says nothing
    about, so a real advisory cannot make this pass by accident.
    """
    store = memory_backend(MEMORY_URL)
    record = osv_record("TEST-9002", [("9.0.0", "9.0.3"), ("11.0.0", "11.0.2")])

    with FakeAdvisoryFeed([record]) as feed:
        run(refresh_advisories(store, refresh_settings(advisory_refresh_url=feed.url)))

    database = run(stored_database(store, refresh_settings()))
    assert [a.fixed for a in database.matches("9.0.1")] == ["9.0.3"]
    assert [a.fixed for a in database.matches("11.0.1")] == ["11.0.2"]
    assert database.matches("9.0.3") == []
    assert database.matches("11.0.2") == []
    assert database.matches("10.0.0") == [], "the gap between the lines is untouched"


def test_an_advisory_without_version_bounds_is_never_believed():
    """
    An unbounded advisory would report every instance in the world as vulnerable.

    The Go database publishes exactly this shape: ``introduced: "0"`` with no
    fix. It has to be dropped before it reaches a scan, because
    ``is_in_range`` with no bounds at either end is true of every version.
    """
    assert is_in_range("7.2.3", None, None) is True, (
        "if this ever stops being true the guard below is testing nothing"
    )

    store = memory_backend(MEMORY_URL)
    record = osv_record("TEST-9003", [("0", None)])

    with FakeAdvisoryFeed([record]) as feed:
        outcome = run(
            refresh_advisories(store, refresh_settings(advisory_refresh_url=feed.url))
        )

    assert outcome in {"unchanged", "updated"}
    database = run(stored_database(store, refresh_settings()))
    assert database.matches("7.2.3") == []
    assert "TEST-9003" not in {a.id for a in database.advisories}


def test_a_stored_document_carrying_an_unbounded_advisory_is_refused():
    """
    The guard is checked on the way out as well as on the way in.

    A document written by an older build, or by anything else with access to
    the key, must not be able to turn every scan into a critical finding.
    """
    store = memory_backend(MEMORY_URL)
    poisoned = {
        "advisories": [
            {
                "id": "TEST-9004",
                "severity": "critical",
                "summary": "Everything is broken",
                "introduced": None,
                "fixed": None,
            }
        ]
    }
    assert any(
        advisory.introduced is None and advisory.fixed is None
        for advisory in parse_document(poisoned)
    ), "the document has to actually be unbounded for this test to mean anything"

    run(store.set(ADVISORY_DOCUMENT_KEY, json.dumps(poisoned)))
    database = run(stored_database(store, refresh_settings()))
    assert database.matches("7.2.3") == []
    assert "TEST-9004" not in {a.id for a in database.advisories}


def test_a_feed_that_has_forgotten_an_advisory_never_removes_it():
    """A retracted feed entry does not make anybody's instance safer."""
    store = memory_backend(MEMORY_URL)
    with FakeAdvisoryFeed([osv_record("TEST-9005", [("9.0.0", "9.0.4")])]) as feed:
        run(refresh_advisories(store, refresh_settings(advisory_refresh_url=feed.url)))

    with FakeAdvisoryFeed([]) as empty:
        outcome = run(
            refresh_advisories(
                store, refresh_settings(advisory_refresh_url=empty.url)
            )
        )

    assert outcome == "unchanged"
    database = run(stored_database(store, refresh_settings()))
    assert [a.fixed for a in database.matches("9.0.1")] == ["9.0.4"]


def test_a_revised_advisory_never_loses_an_earlier_affected_range():
    """
    A feed correction must not turn a previously vulnerable release into clean.

    Replacing an advisory range is a security regression unless a human has
    reviewed the withdrawal; refreshes therefore retain both known bounds.
    """
    store = memory_backend(MEMORY_URL)
    original = osv_record("TEST-9010", [("9.0.0", "9.0.4")])
    revised = osv_record("TEST-9010", [("9.0.2", "9.0.4")])

    with FakeAdvisoryFeed([original]) as feed:
        assert run(
            refresh_advisories(store, refresh_settings(advisory_refresh_url=feed.url))
        ) == "updated"
    with FakeAdvisoryFeed([revised]) as feed:
        assert run(
            refresh_advisories(store, refresh_settings(advisory_refresh_url=feed.url))
        ) == "updated"

    database = run(stored_database(store, refresh_settings()))
    assert [advisory.id for advisory in database.matches("9.0.1")] == ["TEST-9010"]
    assert [advisory.id for advisory in database.matches("9.0.3")] == ["TEST-9010"]
    assert database.matches("9.0.4") == []


def test_a_refresh_never_loses_the_advisories_that_shipped_in_the_image():
    """The bundled file is the floor, not a starting guess to be replaced."""
    bundled_ids = {str(entry["id"]) for entry in BUNDLED["advisories"]}
    assert bundled_ids, "the bundled database has to contain something"

    store = memory_backend(MEMORY_URL)
    with FakeAdvisoryFeed([osv_record("TEST-9006", [("9.0.0", "9.0.4")])]) as feed:
        run(refresh_advisories(store, refresh_settings(advisory_refresh_url=feed.url)))

    stored = json.loads(run(store.get(ADVISORY_DOCUMENT_KEY)))
    assert bundled_ids <= {str(entry["id"]) for entry in stored["advisories"]}


def test_an_unreachable_feed_leaves_the_database_exactly_as_it_was():
    """A firewall between the worker and OSV must not disarm the check."""
    store = memory_backend(MEMORY_URL)
    before = run(stored_database(store, refresh_settings()))

    unreachable = refresh_settings(
        advisory_refresh_url="http://127.0.0.1:9/v1/query"
    )
    assert run(refresh_advisories(store, unreachable)) == "failed"

    after = run(stored_database(store, refresh_settings()))
    assert {a.id for a in after.advisories} == {
        a.id for a in before.advisories
    }


def test_a_feed_answering_with_an_error_page_changes_nothing():
    """An HTML error page is not an empty advisory list."""
    store = memory_backend(MEMORY_URL)
    with FakeAdvisoryFeed([], status=503) as feed:
        outcome = run(
            refresh_advisories(store, refresh_settings(advisory_refresh_url=feed.url))
        )
    assert outcome == "failed"
    assert run(store.get(ADVISORY_DOCUMENT_KEY)) is None


def test_two_names_for_one_advisory_are_reported_once():
    """
    OSV answers with both the GHSA record and the Go database's alias of it.

    Counting them twice would show a visitor two findings where there is one,
    and the alias is the poorer record of the two.
    """
    store = memory_backend(MEMORY_URL)
    ghsa = osv_record("TEST-GHSA-9007", [("9.0.0", "9.0.3"), ("11.0.0", "11.0.2")])
    alias = osv_record("TEST-GO-9007", [("0", None)], aliases=["TEST-GHSA-9007"])

    with FakeAdvisoryFeed([ghsa, alias]) as feed:
        run(refresh_advisories(store, refresh_settings(advisory_refresh_url=feed.url)))

    database = run(stored_database(store, refresh_settings()))
    matched = [a.id for a in database.matches("9.0.1")]
    assert matched == ["TEST-GHSA-9007"]


def test_the_refresh_writes_nothing_into_the_repository():
    """The bundled file is read-only at runtime; CI is what edits it."""
    before = BUNDLED_DB.read_bytes()
    mtime = Path(BUNDLED_DB).stat().st_mtime

    store = memory_backend(MEMORY_URL)
    with FakeAdvisoryFeed([osv_record("TEST-9008", [("9.0.0", "9.0.4")])]) as feed:
        run(refresh_advisories(store, refresh_settings(advisory_refresh_url=feed.url)))

    assert BUNDLED_DB.read_bytes() == before
    assert Path(BUNDLED_DB).stat().st_mtime == mtime


def test_the_refresh_is_off_when_an_operator_turns_it_off():
    """An air-gapped deployment must not reach for a feed at all."""
    store = memory_backend(MEMORY_URL)
    with FakeAdvisoryFeed([osv_record("TEST-9009", [("9.0.0", "9.0.4")])]) as feed:
        off = refresh_settings(advisory_refresh=False, advisory_refresh_url=feed.url)
        assert run(refresh_advisories(store, off)) == "disabled"
        assert feed.requests == 0

    assert run(store.get(ADVISORY_DOCUMENT_KEY)) is None
    database = run(stored_database(store, refresh_settings(advisory_refresh=False)))
    assert {a.id for a in database.advisories} == {
        str(entry["id"])
        for entry in BUNDLED["advisories"]
        if entry.get("enabled", True)
    }


def test_the_daily_job_exists_only_when_the_refresh_is_enabled():
    """Each source is its own cron job, so one being down does not hide the other."""
    jobs = reference_data_jobs(
        refresh_settings(schedule_refresh=True, schedule_refresh_hour=3)
    )
    names = [job.name for job in jobs]
    assert names == ["refresh_release_schedule", "refresh_advisory_database"]
    assert {job.minute for job in jobs} == {17, 41}, (
        "the two must not fetch at the same minute"
    )
    assert all(job.run_at_startup for job in jobs)

    only_advisories = reference_data_jobs(refresh_settings())
    assert [job.name for job in only_advisories] == ["refresh_advisory_database"]
    assert reference_data_jobs(refresh_settings(advisory_refresh=False)) == []


def test_the_health_probe_reports_counts_and_dates_but_no_advisory_text():
    """An unauthenticated probe says whether the refresh works, nothing more."""
    store = memory_backend(MEMORY_URL)
    with FakeAdvisoryFeed([osv_record("TEST-9010", [("9.0.0", "9.0.4")])]) as feed:
        run(refresh_advisories(store, refresh_settings(advisory_refresh_url=feed.url)))

    state = run(advisory_state(store, refresh_settings()))
    assert state["refresh"] is True
    assert state["advisories"] >= 1
    assert state["checked"] == run(store.get(ADVISORY_CHECKED_KEY))
    assert "TEST-9010" not in json.dumps(state), (
        "the probe must not name what a scan would be rated against"
    )


@pytest.mark.parametrize("version", ["9.0.0", "9.0.3"])
def test_the_refreshed_database_says_where_its_verdict_came_from(version: str):
    """A result document that cites no source cannot be checked by a reader."""
    store = memory_backend(MEMORY_URL)
    with FakeAdvisoryFeed([osv_record("TEST-9011", [("9.0.0", "9.0.4")])]) as feed:
        run(refresh_advisories(store, refresh_settings(advisory_refresh_url=feed.url)))
        database = run(stored_database(store, refresh_settings()))
        assert any(feed.url in source for source in database.sources)

    assert [a.id for a in database.matches(version)] == ["TEST-9011"]
