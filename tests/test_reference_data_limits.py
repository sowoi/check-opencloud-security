"""
What the daily reference-data fetches will read, and what they refuse.

Both URLs behind these fetches are operator configuration and may name a
mirror, and both jobs run at worker startup - so an answer that is too big to
hold is not one skipped refresh, it is a worker that crashes, restarts, asks
again and crashes again. These tests serve real bodies over real sockets,
because the thing being tested is how much of a response gets read.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from opencloud_local_scan import advisory_source, schedule_source
from opencloud_local_scan.advisory_source import AdvisoryFetchError, fetch_records
from opencloud_local_scan.fetch import (
    MAX_DOCUMENT_BYTES,
    DocumentTooLarge,
    read_capped,
)
from opencloud_local_scan.schedule_source import ExtractionError, fetch


class _Handler(BaseHTTPRequestHandler):
    def _reply(self) -> None:
        body = self.server.body  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", self.server.content_type)  # type: ignore[attr-defined]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _reply
    do_POST = _reply

    def log_message(self, *args: Any) -> None:
        """Keep the test output readable."""


class FakeFeed:
    """A source that answers with exactly the bytes a test gives it."""

    def __init__(self, body: bytes, content_type: str = "text/html; charset=utf-8"):
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.body = body  # type: ignore[attr-defined]
        self._server.content_type = content_type  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> FakeFeed:  # noqa: PYI034 - a context manager, not a protocol
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/"


# --- the cap itself ---------------------------------------------------------


class _Response:
    """Just enough of an ``http.client`` response for the reader."""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self.reads: list[int] = []

    def read(self, size: int) -> bytes:
        self.reads.append(size)
        return self._body[:size]


def test_a_body_within_the_limit_is_returned_whole():
    """The cap must not truncate a document that was always going to fit."""
    response = _Response(b"x" * 1000)
    assert read_capped(response, limit=2000) == b"x" * 1000


def test_a_body_of_exactly_the_limit_is_still_accepted():
    """An off-by-one here would refuse a document that is precisely legal."""
    response = _Response(b"x" * 500)
    assert read_capped(response, limit=500) == b"x" * 500


def test_a_body_one_byte_over_the_limit_is_refused():
    """The negative case: a document that is too long is not silently cut."""
    response = _Response(b"x" * 501)
    with pytest.raises(DocumentTooLarge):
        read_capped(response, limit=500)


def test_the_reader_never_asks_for_more_than_the_limit_and_one():
    """
    The point of the cap is not reading the rest.

    A reader that asked for the whole body and measured it afterwards would
    have already spent the memory the limit exists to protect.
    """
    response = _Response(b"x" * 10_000)
    with pytest.raises(DocumentTooLarge):
        read_capped(response, limit=100)
    assert response.reads == [101]


# --- the lifecycle page -----------------------------------------------------


def test_the_lifecycle_page_is_fetched_when_it_is_a_reasonable_size():
    """The ordinary path, so the guard below is known to be the difference."""
    with FakeFeed(b"<html><body>lifecycle</body></html>") as site:
        assert "lifecycle" in fetch(site.url, timeout=5)


def test_an_oversized_lifecycle_page_fails_the_fetch_rather_than_the_process():
    """
    A mirror answering with more than a page is refused.

    ``ExtractionError`` matters as much as the refusal: every caller already
    treats it as "keep the schedule you have", so a hostile answer costs a
    refresh rather than a worker.
    """
    with (
        FakeFeed(b"<html>" + b"x" * (MAX_DOCUMENT_BYTES + 1)) as site,
        pytest.raises(ExtractionError) as raised,
    ):
        fetch(site.url, timeout=10)
    assert "Refusing" in str(raised.value)


def test_a_non_http_schedule_url_is_still_refused_before_anything_opens():
    """The older guard is not lost to the new one."""
    with pytest.raises(ExtractionError):
        fetch("file:///etc/passwd")


# --- the advisory feed ------------------------------------------------------


def test_the_advisory_feed_is_read_when_it_answers_normally():
    """The ordinary path, again as the baseline for the refusal below."""
    body = json.dumps({"vulns": [{"id": "GHSA-test"}]}).encode()
    with FakeFeed(body, content_type="application/json") as site:
        records = fetch_records(site.url, timeout=5)
    assert [record["id"] for record in records] == ["GHSA-test"]


def test_an_oversized_advisory_answer_is_refused_before_it_is_parsed():
    """
    ``MAX_ADVISORIES`` cannot help here.

    Reaching that count means the whole answer was already read and parsed,
    which is the cost this refuses to pay - so the size guard has to come
    first, and this asserts that it does.

    The body is padded to just past the cap rather than to something
    dramatically larger: ``read_capped`` only ever reads ``limit + 1`` bytes
    and the response is closed straight after, so a body that leaves
    megabytes of it undrained on the socket races the fake server's write
    against the client's close - occasionally surfacing as a connection
    reset instead of the clean refusal this asserts.
    """
    body = b'{"vulns": [' + b'{"id": "x"},' + b" " * MAX_DOCUMENT_BYTES + b']}'
    assert len(body) > MAX_DOCUMENT_BYTES
    with (
        FakeFeed(body, content_type="application/json") as site,
        pytest.raises(AdvisoryFetchError) as raised,
    ):
        fetch_records(site.url, timeout=10)
    assert "Refusing" in str(raised.value)


def test_a_non_http_advisory_url_is_still_refused():
    """The older guard is not lost to the new one."""
    with pytest.raises(AdvisoryFetchError):
        fetch_records("file:///etc/passwd")


def test_both_sources_read_through_the_same_cap():
    """
    One limit, not two that can drift.

    The two fetches are in different modules with different error types, and
    the bug being prevented is the next one growing its own ceiling.
    """
    assert schedule_source.decode_capped is advisory_source.decode_capped
