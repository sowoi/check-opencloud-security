"""
Read published OpenCloud advisories from OSV.

The advisory database that ships with this package is what decides whether a
scanned instance is reported as vulnerable, and until now nothing kept it
current: it was written by hand and shipped empty, so the first published
OpenCloud advisory reached nobody. This module is the other half of that -
the part that asks.

`OSV <https://osv.dev>`_ is the right source to ask. It aggregates the GitHub
Security Advisories for ``opencloud-eu/opencloud`` and the Go vulnerability
database into one schema that :mod:`opencloud_local_scan.vulndb` already
understands, it needs no token, and it is queried by package rather than by
repository, which is what an operator running a Go binary actually has.

Two things this module refuses to do, both of them because a false alarm from
a security tool is expensive:

* **Take an unbounded record at face value.** A record that does not say which
  versions it affects matches every version there has ever been. The parser
  drops those; the count guard here catches the case where a query somehow
  returns a whole ecosystem.
* **Lose an advisory.** A merge only ever adds. A feed that answers with an
  empty list - because it is down, because a package was renamed, because
  somebody typed the name wrong - leaves the database exactly as it was.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .vulndb import Advisory, parse_document

LOGGER = logging.getLogger("check_opencloud.advisory_source")

#: The OSV query API. Free, unauthenticated, and queried by package.
OSV_QUERY_URL = "https://api.osv.dev/v1/query"

#: OpenCloud is a Go module, and that is the name OSV indexes it under.
OSV_PACKAGE = "github.com/opencloud-eu/opencloud"
OSV_ECOSYSTEM = "Go"

USER_AGENT = "check-opencloud-security/advisory-db"

# Plausibility guard. OpenCloud has a handful of advisories; a response with
# hundreds means the query matched something other than what was asked for,
# and a database that flags everything is worse than one that flags nothing.
MAX_ADVISORIES = 200

# An advisory description in a monitoring alert is a paragraph, not a page.
DESCRIPTION_LIMIT = 500

DOCUMENT_COMMENT = (
    "Local advisory database used by the built-in scanner. Entries are "
    "matched against the detected OpenCloud version using the half-open "
    "range [introduced, fixed); an advisory that affects several release "
    "lines carries one entry per line in 'ranges'. Regenerate with "
    "scripts/update_vulnerability_db.py, which only ever adds to this file - "
    "a hand written entry is never removed by a refresh."
)


class AdvisoryFetchError(RuntimeError):
    """The advisory feed could not be read or made sense of."""


def fetch_records(
    url: str = OSV_QUERY_URL,
    package: str = OSV_PACKAGE,
    ecosystem: str = OSV_ECOSYSTEM,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """Ask OSV which advisories affect the OpenCloud package."""
    if not url.startswith(("http://", "https://")):
        raise AdvisoryFetchError(f"Refusing to fetch a non-HTTP URL: {url}")
    body = json.dumps({"package": {"name": package, "ecosystem": ecosystem}}).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - scheme validated above
            charset = response.headers.get_content_charset() or "utf-8"
            document = json.loads(response.read().decode(charset, errors="replace"))
    except OSError as exc:  # URLError and friends are all OSError
        raise AdvisoryFetchError(f"Could not read {url}: {exc}") from exc
    except ValueError as exc:
        raise AdvisoryFetchError(f"{url} did not answer with JSON: {exc}") from exc

    if not isinstance(document, dict):
        raise AdvisoryFetchError(f"{url} answered with {type(document).__name__}, not an object")
    records = document.get("vulns") or []
    if not isinstance(records, list):
        raise AdvisoryFetchError(f"{url} answered with a 'vulns' that is not a list")
    if len(records) > MAX_ADVISORIES:
        raise AdvisoryFetchError(
            f"{url} returned {len(records)} advisories, more than the {MAX_ADVISORIES} "
            "this package expects for OpenCloud - the query matched too much"
        )
    return [record for record in records if isinstance(record, dict)]


def _without_aliases(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Drop records that are another record's alias.

    OSV answers with the GitHub advisory *and* the Go vulnerability database's
    entry for the same issue, each naming the other in ``aliases``. They are
    one vulnerability, and reporting it twice would double-count it in the
    rating as well as in the alert.
    """
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    # A reviewed GitHub advisory carries the version ranges; the Go database's
    # mirror of it often does not, so prefer the record that says the most.
    ordered = sorted(records, key=lambda record: -len(record.get("affected") or []))
    for record in ordered:
        identifier = str(record.get("id") or "")
        aliases = {str(alias) for alias in record.get("aliases") or []}
        if identifier in seen or aliases & seen:
            continue
        seen.add(identifier)
        seen |= aliases
        kept.append(record)
    return kept


def to_native(advisory: Advisory, source: str) -> dict[str, Any]:
    """Render one advisory as an entry of the bundled database."""
    ranges = advisory.all_ranges()
    entry: dict[str, Any] = {
        "id": advisory.id,
        "cwe": advisory.cwe,
        "title": advisory.title,
        "description": advisory.description[:DESCRIPTION_LIMIT],
        "severity": advisory.severity,
        "url": advisory.url,
        "introduced": ranges[0][0],
        "fixed": ranges[0][1],
        "source": source,
    }
    if len(ranges) > 1:
        # Several release lines patched separately. The flat pair above stays
        # for a reader and for anything older; 'ranges' is what matches.
        entry["ranges"] = [
            {"introduced": introduced, "fixed": fixed} for introduced, fixed in ranges
        ]
    return entry


def merge_document(
    entries: list[dict[str, Any]], existing: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Fold fetched advisories into the database document, adding only.

    An entry already in the file keeps everything the fetched one does not
    state, so a hand written note survives a refresh; an entry the feed no
    longer mentions stays, because a feed that has forgotten an advisory has
    not made anybody safer. Removing one is a deliberate edit.
    """
    document = dict(existing or {})
    current = list(document.get("advisories") or [])
    by_id = {str(entry.get("id")): index for index, entry in enumerate(current)}

    added = 0
    for entry in entries:
        index = by_id.get(entry["id"])
        if index is None:
            current.append(entry)
            by_id[entry["id"]] = len(current) - 1
            added += 1
            continue
        merged = dict(current[index])
        merged.update({key: value for key, value in entry.items() if value not in (None, "")})
        # 'ranges' is authoritative or absent: a fetched single-range advisory
        # must not inherit a stale multi-range list from the file.
        if "ranges" in entry:
            merged["ranges"] = entry["ranges"]
        else:
            merged.pop("ranges", None)
            merged["introduced"] = entry["introduced"]
            merged["fixed"] = entry["fixed"]
        current[index] = merged

    LOGGER.debug("Advisory merge: %d fetched, %d new", len(entries), added)
    document["advisories"] = current
    document["updated"] = datetime.now(tz=timezone.utc).date().isoformat()
    document["comment"] = DOCUMENT_COMMENT
    return document


def fetch_advisory_document(
    url: str = OSV_QUERY_URL,
    existing: dict[str, Any] | None = None,
    timeout: int = 30,
    package: str = OSV_PACKAGE,
) -> dict[str, Any]:
    """
    Read the advisory feed and return the merged database document.

    Raises :class:`AdvisoryFetchError` when the feed cannot be read or does
    not look like an OSV answer. A caller that gets an exception keeps the
    database it already had.
    """
    records = _without_aliases(fetch_records(url, package=package, timeout=timeout))
    advisories = parse_document({"vulns": records})
    entries = [to_native(advisory, url) for advisory in advisories]
    entries.sort(key=lambda entry: str(entry["id"]))
    return merge_document(entries, existing)
