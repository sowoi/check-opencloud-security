"""
Reading a reference-data document off the network, with a ceiling.

The two daily refreshes - the release lifecycle page and the OSV advisory
feed - read a whole HTTP response into memory before they look at it. Both
URLs are operator configuration, so both may point at a mirror, and a mirror
that answers with a gigabyte takes the process with it. That matters more
than it looks: the refresh jobs run ``run_at_startup``, so a bad answer is a
worker that crashes, restarts, asks again and crashes again rather than one
skipped refresh.

The scanner already refuses to read an unbounded body from an instance it is
scanning - ``ScannerSettings.max_response_bytes``, enforced in
``_Probe._capped``. This is the same rule for the documents the scanner rates
*against*, and it is here rather than in either caller so the two cannot
drift.

Nothing here decides what a document means. It reads at most a fixed number
of bytes, and refuses the response outright when there are more - a truncated
release schedule would parse into a *shorter* schedule, which is exactly the
silent loss :mod:`webapp.schedule` exists to prevent.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPResponse

#: Both documents are tens of kilobytes. A megabyte is room for the lifecycle
#: page to grow a decade of releases and for OSV to answer with every advisory
#: ``MAX_ADVISORIES`` allows, and is still small enough that a hostile answer
#: costs nothing.
MAX_DOCUMENT_BYTES = 1_048_576


class DocumentTooLarge(ValueError):
    """The response body was longer than a reference document may be."""


def read_capped(response: object, limit: int = MAX_DOCUMENT_BYTES) -> bytes:
    """
    Read at most ``limit`` bytes from an open response, or refuse it.

    One byte past the limit is read deliberately: without it a body of exactly
    ``limit`` bytes and one of ``limit`` bytes plus a gigabyte are
    indistinguishable, and the second would be silently truncated into a
    document that parses.
    """
    body = response.read(limit + 1)  # type: ignore[attr-defined]
    if len(body) > limit:
        raise DocumentTooLarge(
            f"the response is longer than the {limit} bytes a reference "
            "document may be"
        )
    return body


def decode_capped(response: object, limit: int = MAX_DOCUMENT_BYTES) -> str:
    """The same, decoded with whatever charset the response declared."""
    charset = response.headers.get_content_charset() or "utf-8"  # type: ignore[attr-defined]
    return read_capped(response, limit).decode(charset, errors="replace")


@contextmanager
def open_document(request: urllib.request.Request, timeout: float) -> Iterator[HTTPResponse]:
    """
    ``urlopen`` for a reference document, closing an error answer as well.

    An HTTP error status arrives as an :class:`urllib.error.HTTPError` that
    holds the open response. The callers turn it into their own error and
    chain it, which keeps it - and its socket - alive until the garbage
    collector gets round to it, in a web service that refreshes every day.
    It is closed here before it travels on; its status and reason stay
    readable. The caller validates the scheme.
    """
    try:
        response = urllib.request.urlopen(request, timeout=timeout)  # nosec B310 - the caller validates the scheme
    except urllib.error.HTTPError as exc:
        exc.close()
        raise
    with response:
        yield response
