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
import re
import urllib.request
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

from .fetch import DocumentTooLarge, decode_capped
from .versions import normalise_version, parse_version
from .vulndb import Advisory, parse_document
from .vulndb import _is_opencloud_package as is_opencloud_package

LOGGER = logging.getLogger("check_opencloud.advisory_source")

#: The OSV query API. Free, unauthenticated, and queried by package.
OSV_QUERY_URL = "https://api.osv.dev/v1/query"

#: OpenCloud is a Go module, and that is the name OSV indexes it under.
OSV_PACKAGE = "github.com/opencloud-eu/opencloud"
OSV_ECOSYSTEM = "Go"

#: OpenCloud's own repository advisories. OpenCloud has published advisories
#: here that never reached GitHub's global database, and so never reached OSV
#: either (GHSA-gf4p-7p27-26w7). Unauthenticated; one request a day. ADR 0071.
REPOSITORY_ADVISORIES_URL = (
    "https://api.github.com/repos/opencloud-eu/opencloud/security-advisories"
)

USER_AGENT = "check-opencloud-security/advisory-db"

# A repository advisory's range is free text. Only a comma-separated list of
# operator/version pairs is read; anything else ("stable releases 4.0.x") is
# prose, and guessing at prose is how a security check invents a finding.
# OpenCloud's first release. A range with no lower bound starts here rather
# than at zero, so that a version older than anything OpenCloud shipped stays
# outside every advisory (tests/test_vulndb.py relies on that).
FIRST_RELEASE = "1.0.0"

_BOUND = r"(>=|<=|>|<|=)\s*v?([0-9]+(?:\.[0-9]+)*)"
_BOUND_PART = re.compile(_BOUND)
_BOUND_LIST = re.compile(rf"\s*{_BOUND}(\s*,\s*{_BOUND})*\s*")

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
            document = json.loads(decode_capped(response))
    except OSError as exc:  # URLError and friends are all OSError
        raise AdvisoryFetchError(f"Could not read {url}: {exc}") from exc
    except DocumentTooLarge as exc:
        # Ahead of the ValueError branch below, which it is a subclass of: the
        # count guard further down cannot help here, because reaching it would
        # already have meant reading the whole answer into memory.
        raise AdvisoryFetchError(f"Refusing the answer from {url}: {exc}") from exc
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
        previous = current[index]
        merged = dict(previous)
        merged.update({key: value for key, value in entry.items() if value not in (None, "")})
        ranges = _merged_ranges(previous, entry)
        merged["introduced"], merged["fixed"] = ranges[0]
        if len(ranges) == 1:
            merged.pop("ranges", None)
        else:
            merged["ranges"] = [
                {"introduced": introduced, "fixed": fixed}
                for introduced, fixed in ranges
            ]
        current[index] = merged

    LOGGER.debug("Advisory merge: %d fetched, %d new", len(entries), added)
    document["advisories"] = current
    document["updated"] = datetime.now(tz=UTC).date().isoformat()
    document["comment"] = DOCUMENT_COMMENT
    return document


def _ranges(entry: dict[str, Any]) -> list[tuple[str | None, str | None]]:
    """Read all bounded ranges from either native representation."""
    listed = entry.get("ranges")
    if isinstance(listed, list):
        ranges = [
            (item.get("introduced"), item.get("fixed"))
            for item in listed
            if isinstance(item, dict)
            and (item.get("introduced") or item.get("fixed"))
        ]
        if ranges:
            return ranges
    return [(entry.get("introduced"), entry.get("fixed"))]


def _merged_ranges(
    previous: dict[str, Any], fetched: dict[str, Any]
) -> list[tuple[str | None, str | None]]:
    """Preserve every known affected range when a feed revises an advisory."""
    merged: list[tuple[str | None, str | None]] = []
    for version_range in [*_ranges(previous), *_ranges(fetched)]:
        if version_range not in merged:
            merged.append(version_range)
    return merged


def fetch_repository_records(
    url: str = REPOSITORY_ADVISORIES_URL, timeout: int = 30
) -> list[dict[str, Any]]:
    """Read OpenCloud's repository advisories from the GitHub REST API."""
    if not url.startswith(("http://", "https://")):
        raise AdvisoryFetchError(f"Refusing to fetch a non-HTTP URL: {url}")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - scheme validated above
            document = json.loads(decode_capped(response))
    except OSError as exc:
        raise AdvisoryFetchError(f"Could not read {url}: {exc}") from exc
    except DocumentTooLarge as exc:
        raise AdvisoryFetchError(f"Refusing the answer from {url}: {exc}") from exc
    except ValueError as exc:
        raise AdvisoryFetchError(f"{url} did not answer with JSON: {exc}") from exc

    if not isinstance(document, list):
        raise AdvisoryFetchError(f"{url} answered with {type(document).__name__}, not a list")
    if len(document) > MAX_ADVISORIES:
        raise AdvisoryFetchError(
            f"{url} returned {len(document)} advisories, more than the {MAX_ADVISORIES} "
            "this package expects for OpenCloud"
        )
    return [record for record in document if isinstance(record, dict)]


def _upper_bound(operator: str, version: str) -> str:
    """The first unaffected version for '< x' or '<= x'."""
    if operator == "<":
        return version
    parts = version.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def _line_after(version: str) -> str:
    """The first release of the release line after the one ``version`` is on."""
    parts = (*parse_version(version), 0, 0)
    return f"{parts[0]}.{parts[1] + 1}.0"


def repository_ranges(
    expression: str | None, patched: str | None = None
) -> list[tuple[str | None, str | None]]:
    """
    Read the affected ranges of one repository advisory entry.

    ``>= 7.0.0, < 7.1.2`` is one range. ``< 4.0.8, < 7.2.0`` - the way
    OpenCloud writes an advisory fixed on two release lines - is two: from
    :data:`FIRST_RELEASE` up to 4.0.8, and from the line after 4.0 up to 7.2.0. Reading it as one range
    (the last bound wins) would report the fixed 4.0.8 as vulnerable. Prose
    yields nothing, and an entry that yields nothing is dropped by the caller.
    """
    text = (expression or "").strip()
    if not text and patched:
        # No range at all but a patched list: every release before it.
        text = ", ".join(f"< {item.strip()}" for item in patched.split(",") if item.strip())
    if not _BOUND_LIST.fullmatch(text):
        return []
    bounds = _BOUND_PART.findall(text)
    if len(bounds) > 1 and all(operator in {"<", "<="} for operator, _ in bounds):
        fixes = sorted({_upper_bound(operator, version) for operator, version in bounds},
                       key=parse_version)
        ranges: list[tuple[str | None, str | None]] = [(FIRST_RELEASE, fixes[0])]
        ranges.extend((_line_after(previous), fixed) for previous, fixed in pairwise(fixes))
        return ranges
    introduced: str | None = None
    fixed: str | None = None
    for operator, version in bounds:
        if operator == ">=":
            introduced = version
        elif operator == ">":
            introduced = f"{version}.1"
        elif operator in {"<", "<="}:
            fixed = _upper_bound(operator, version)
        else:  # '='
            introduced, fixed = version, f"{version}.1"
    if not fixed and not introduced:
        return []
    return [(introduced or FIRST_RELEASE, fixed)]


def parse_repository_advisory(record: dict[str, Any]) -> Advisory | None:
    """Convert one repository advisory, or None when it is not usable."""
    identifier = str(record.get("ghsa_id") or "")
    if not identifier or record.get("state") not in (None, "published") or record.get("withdrawn_at"):
        return None
    ranges: list[tuple[str | None, str | None]] = []
    for affected in record.get("vulnerabilities") or []:
        if not isinstance(affected, dict):
            continue
        package = affected.get("package") or {}
        if not is_opencloud_package(str(package.get("name", ""))):
            continue
        found = repository_ranges(
            affected.get("vulnerable_version_range"), affected.get("patched_versions")
        )
        if not found:
            LOGGER.info("Skipping an unreadable range of %s: %r", identifier,
                        affected.get("vulnerable_version_range"))
        ranges.extend(item for item in found if item not in ranges)
    if not ranges:
        return None
    ranges = [(normalise_version(low), normalise_version(high)) for low, high in ranges]
    return Advisory(
        id=identifier,
        title=str(record.get("summary") or ""),
        description=str(record.get("description") or "")[:DESCRIPTION_LIMIT],
        severity=str(record.get("severity") or "unknown").lower(),
        url=str(record.get("html_url") or ""),
        cwe=",".join(
            str(item.get("cwe_id"))
            for item in (record.get("cwes") or [])
            if isinstance(item, dict) and item.get("cwe_id")
        ),
        introduced=ranges[0][0],
        fixed=ranges[0][1],
        ranges=tuple(ranges),
    )


def _known_identifiers(records: list[dict[str, Any]]) -> set[str]:
    """Every id and alias OSV answered with."""
    known: set[str] = set()
    for record in records:
        known.add(str(record.get("id") or ""))
        known |= {str(alias) for alias in record.get("aliases") or []}
    return known


def fetch_advisory_document(
    url: str = OSV_QUERY_URL,
    existing: dict[str, Any] | None = None,
    timeout: int = 30,
    package: str = OSV_PACKAGE,
    repository_url: str | None = None,
) -> dict[str, Any]:
    """
    Read the advisory feed and return the merged database document.

    Raises :class:`AdvisoryFetchError` when the feed cannot be read or does
    not look like an OSV answer. A caller that gets an exception keeps the
    database it already had.

    With ``repository_url``, OpenCloud's repository advisories are read as
    well and add the ones OSV does not know. OSV stays the primary source: an
    advisory it has keeps OSV's ranges, and a repository feed that cannot be
    read is logged and skipped rather than failing a refresh that already has
    OSV's answer (ADR 0071).
    """
    fetched = fetch_records(url, package=package, timeout=timeout)
    records = _without_aliases(fetched)
    advisories = parse_document({"vulns": records})
    entries = [to_native(advisory, url) for advisory in advisories]

    if repository_url:
        known = _known_identifiers(fetched)
        try:
            repository = fetch_repository_records(repository_url, timeout=timeout)
        except AdvisoryFetchError as exc:
            LOGGER.warning("Repository advisories not read, keeping OSV's answer: %s", exc)
            repository = []
        for record in repository:
            if str(record.get("ghsa_id")) in known or str(record.get("cve_id")) in known:
                continue
            advisory = parse_repository_advisory(record)
            if advisory is not None:
                entries.append(to_native(advisory, repository_url))

    entries.sort(key=lambda entry: str(entry["id"]))
    return merge_document(entries, existing)
