"""
Advisory database used by the local scanner.

Three sources are merged, all of them optional:

* the advisory file bundled with this package,
* a user supplied JSON file (``scanner.vulnerability_db``),
* a remote JSON feed (``scanner.vulnerability_feed``).

Three formats are understood, so an air-gapped installation can mirror a
public feed to a file without any conversion:

``native``
    ``{"advisories": [{"id": ..., "introduced": ..., "fixed": ...}]}``
``GitHub Advisory API``
    a list of objects carrying ``ghsa_id`` and ``vulnerabilities``
``OSV``
    ``{"vulns": [...]}`` or a single OSV record with ``affected[].ranges[]``

OpenCloud is a Go module, so the package name to match against is
``github.com/opencloud-eu/opencloud``.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import requests

from .versions import is_in_range, normalise_version

LOGGER = logging.getLogger("check_opencloud.vulndb")

BUNDLED_DB = Path(__file__).with_name("data") / "vulnerabilities.json"

# Range expressions used by the GitHub Advisory API, e.g. ">= 7.0.0, < 7.1.2".
_RANGE_PART = re.compile(r"(>=|<=|>|<|=)\s*([0-9][0-9.]*)")

# Package names that identify OpenCloud in a public advisory feed. An entry
# without a package name is kept, because a hand written advisory file is not
# required to name the product at all.
PACKAGE_MARKERS = ("opencloud", "ocis", "infinite-scale")

SEVERITY_ORDER = {"low": 1, "moderate": 2, "medium": 2, "high": 3, "critical": 4}


@dataclass(frozen=True)
class Advisory:
    """A single known vulnerability affecting one or more OpenCloud releases.

    One advisory can affect several release lines that were patched
    separately - the public link exploit fixed in both ``4.0.3`` and ``5.0.2``
    is one advisory with two disjoint ranges, not two advisories. ``ranges``
    carries them; ``introduced`` and ``fixed`` are the first of them, which is
    what a single-range advisory has always been.
    """

    id: str
    title: str = ""
    description: str = ""
    severity: str = "unknown"
    url: str = ""
    cwe: str = ""
    introduced: str | None = None
    fixed: str | None = None
    #: Every affected range, as (introduced, fixed). Empty means the single
    #: range described by ``introduced`` and ``fixed``.
    ranges: tuple[tuple[str | None, str | None], ...] = ()

    def all_ranges(self) -> tuple[tuple[str | None, str | None], ...]:
        """Every affected range, however the advisory was written."""
        return self.ranges or ((self.introduced, self.fixed),)

    def affects(self, version: str | None) -> bool:
        """Return True when any of the advisory's ranges covers the version."""
        return any(
            is_in_range(version, introduced, fixed)
            for introduced, fixed in self.all_ranges()
        )

    def for_version(self, version: str | None) -> Advisory:
        """
        The advisory as it applies to one version.

        An advisory patched in both ``4.0.3`` and ``5.0.2`` must tell a ``5.0.1``
        instance to upgrade to ``5.0.2``. Reporting the first fix in the list
        would send half of them to a release that does not fix anything.
        """
        for introduced, fixed in self.all_ranges():
            if is_in_range(version, introduced, fixed):
                return replace(self, introduced=introduced, fixed=fixed, ranges=())
        return self

    def as_dict(self) -> dict[str, Any]:
        """Render the advisory the way a scan result lists vulnerabilities."""
        return {
            "id": self.id,
            "cwe": self.cwe,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "url": self.url,
            "fixedIn": self.fixed,
        }


def _is_opencloud_package(name: str) -> bool:
    """Whether a package name from a public feed refers to OpenCloud."""
    lowered = name.strip().lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in PACKAGE_MARKERS)


def _parse_range(expression: str | None) -> tuple[str | None, str | None]:
    """Translate a GitHub version range expression into (introduced, fixed)."""
    if not expression:
        return None, None
    introduced: str | None = None
    fixed: str | None = None
    for operator, version in _RANGE_PART.findall(expression):
        if operator in {">=", ">"}:
            introduced = version
        elif operator == "<":
            fixed = version
        elif operator == "<=":
            # Inclusive upper bound: treat the next patch level as fixed.
            parts = version.split(".")
            parts[-1] = str(int(parts[-1]) + 1) if parts[-1].isdigit() else parts[-1]
            fixed = ".".join(parts)
        elif operator == "=":
            introduced = version
            fixed = version + ".1"
    return introduced, fixed


def _from_github(entry: dict[str, Any]) -> Advisory | None:
    """Convert a GitHub Advisory API record into an Advisory."""
    identifier = entry.get("cve_id") or entry.get("ghsa_id")
    if not identifier:
        return None

    introduced: str | None = None
    fixed: str | None = None
    for affected in entry.get("vulnerabilities") or []:
        if not isinstance(affected, dict):
            continue
        package = affected.get("package") or {}
        if not _is_opencloud_package(str(package.get("name", ""))):
            continue
        introduced, fixed = _parse_range(affected.get("vulnerable_version_range"))
        if not fixed:
            fixed = normalise_version(affected.get("first_patched_version")) or fixed
        break
    else:
        return None

    return Advisory(
        id=str(identifier),
        title=str(entry.get("summary") or ""),
        description=str(entry.get("description") or "")[:500],
        severity=str(entry.get("severity") or "unknown").lower(),
        url=str(entry.get("html_url") or ""),
        cwe=",".join(
            str(item.get("cwe_id"))
            for item in (entry.get("cwes") or [])
            if isinstance(item, dict) and item.get("cwe_id")
        ),
        introduced=introduced,
        fixed=fixed,
    )


def _osv_severity(entry: dict[str, Any]) -> str:
    """Read the severity of an OSV record from its database_specific block."""
    specific = entry.get("database_specific")
    if isinstance(specific, dict):
        severity = specific.get("severity")
        if severity:
            return str(severity).lower()
    return "unknown"


def _osv_cwes(entry: dict[str, Any]) -> list[str]:
    """The CWE identifiers an OSV record carries in database_specific."""
    specific = entry.get("database_specific")
    if not isinstance(specific, dict):
        return []
    return [str(item) for item in specific.get("cwe_ids") or [] if item]


def _from_osv(entry: dict[str, Any]) -> Advisory | None:
    """Convert an OSV record (api.osv.dev) into an Advisory."""
    identifier = entry.get("id")
    if not identifier:
        return None
    aliases = [str(alias) for alias in entry.get("aliases") or []]
    # A CVE identifier is more useful in an alert than the OSV id.
    identifier = next((alias for alias in aliases if alias.startswith("CVE-")), str(identifier))

    # OSV expresses disjoint affected ranges as separate 'affected' entries
    # for the same package: one advisory patched in both 4.0.3 and 5.0.2 has
    # two of them. Reading only the first one leaves every instance on the
    # other line unreported.
    ranges: list[tuple[str | None, str | None]] = []
    for affected in entry.get("affected") or []:
        if not isinstance(affected, dict):
            continue
        package = affected.get("package") or {}
        if not _is_opencloud_package(str(package.get("name", ""))):
            continue
        for version_range in affected.get("ranges") or []:
            if not isinstance(version_range, dict):
                continue
            introduced: str | None = None
            fixed: str | None = None
            for event in version_range.get("events") or []:
                if not isinstance(event, dict):
                    continue
                if event.get("introduced") and event["introduced"] != "0":
                    introduced = normalise_version(event["introduced"])
                if event.get("fixed"):
                    fixed = normalise_version(event["fixed"])
            if introduced or fixed:
                ranges.append((introduced, fixed))
    if not ranges:
        # Every bound is open, which would match every version there has ever
        # been. The Go vulnerability database publishes such a record beside
        # each reviewed GitHub advisory ('introduced: 0', no fix), and taking
        # it at face value would report every instance in the world as
        # vulnerable. An advisory that cannot say what it affects is not one.
        LOGGER.debug("Ignoring unbounded OSV record %s", identifier)
        return None

    references = entry.get("references") or []
    url = ""
    for reference in references:
        if isinstance(reference, dict) and reference.get("url"):
            url = str(reference["url"])
            break

    return Advisory(
        id=identifier,
        title=str(entry.get("summary") or ""),
        description=str(entry.get("details") or "")[:500],
        severity=_osv_severity(entry),
        url=url,
        cwe=",".join(_osv_cwes(entry)),
        introduced=ranges[0][0],
        fixed=ranges[0][1],
        ranges=tuple(ranges),
    )


def _from_native(entry: dict[str, Any]) -> Advisory | None:
    """Convert a native advisory record into an Advisory."""
    identifier = entry.get("id")
    if not identifier or entry.get("enabled") is False:
        return None
    ranges = tuple(
        (item.get("introduced"), item.get("fixed"))
        for item in entry.get("ranges") or ()
        if isinstance(item, dict) and (item.get("introduced") or item.get("fixed"))
    )
    return Advisory(
        id=str(identifier),
        title=str(entry.get("title") or ""),
        description=str(entry.get("description") or ""),
        severity=str(entry.get("severity") or "unknown").lower(),
        url=str(entry.get("url") or ""),
        cwe=str(entry.get("cwe") or ""),
        introduced=entry.get("introduced") or (ranges[0][0] if ranges else None),
        fixed=entry.get("fixed") or (ranges[0][1] if ranges else None),
        ranges=ranges,
    )


def _convert(record: dict[str, Any]) -> Advisory | None:
    """Dispatch one record to the parser matching its format."""
    if "ghsa_id" in record:
        return _from_github(record)
    if "affected" in record and "id" in record:
        return _from_osv(record)
    return _from_native(record)


def parse_document(document: Any) -> list[Advisory]:
    """Parse any supported advisory format into a list of advisories."""
    if isinstance(document, dict):
        records = document.get("advisories")
        if records is None:
            records = document.get("vulns")
        if records is None:
            records = document.get("data")
        if records is None:
            # A single OSV record is a valid document of its own.
            records = [document] if "affected" in document else []
    else:
        records = document

    advisories: list[Advisory] = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        advisory = _convert(record)
        if advisory is not None:
            advisories.append(advisory)
    return advisories


@dataclass
class VulnerabilityDatabase:
    """Merged advisory database with version matching."""

    advisories: list[Advisory]
    sources: list[str]

    def matches(self, version: str | None) -> list[Advisory]:
        """Return every advisory affecting the given version, worst first."""
        hits = [
            advisory.for_version(version)
            for advisory in self.advisories
            if advisory.affects(version)
        ]
        return sorted(
            hits,
            key=lambda advisory: (-SEVERITY_ORDER.get(advisory.severity, 0), advisory.id),
        )

    def worst_severity(self, version: str | None) -> str | None:
        """Return the highest severity affecting the given version."""
        hits = self.matches(version)
        return hits[0].severity if hits else None


def _load_file(path: Path) -> list[Advisory]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        LOGGER.warning("Ignoring advisory file %s: %s", path, exc)
        return []
    return parse_document(document)


def _load_feed(
    url: str, timeout: int, verify: bool, proxies: dict[str, str] | None
) -> list[Advisory]:
    try:
        response = requests.get(
            url,
            timeout=timeout,
            verify=verify,
            proxies=proxies,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        document = response.json()
    except (requests.exceptions.RequestException, OSError, ValueError) as exc:
        # A stale or unreachable feed must never turn a healthy instance into
        # an UNKNOWN result: the local database still provides a verdict.
        LOGGER.warning("Ignoring advisory feed %s: %s", url, exc)
        return []
    return parse_document(document)


def load_database(
    *,
    extra_files: Iterable[str] = (),
    feed_url: str | None = None,
    include_bundled: bool = True,
    timeout: int = 10,
    verify: bool = True,
    proxies: dict[str, str] | None = None,
) -> VulnerabilityDatabase:
    """Load and merge every configured advisory source, de-duplicated by id."""
    advisories: dict[str, Advisory] = {}
    sources: list[str] = []

    if include_bundled and BUNDLED_DB.is_file():
        for advisory in _load_file(BUNDLED_DB):
            advisories[advisory.id] = advisory
        sources.append(str(BUNDLED_DB))

    for candidate in extra_files:
        path = Path(candidate).expanduser()
        if not path.is_file():
            LOGGER.warning("Advisory file %s does not exist.", path)
            continue
        for advisory in _load_file(path):
            advisories[advisory.id] = advisory
        sources.append(str(path))

    if feed_url:
        loaded = _load_feed(feed_url, timeout=timeout, verify=verify, proxies=proxies)
        for advisory in loaded:
            advisories[advisory.id] = advisory
        if loaded:
            sources.append(feed_url)

    return VulnerabilityDatabase(advisories=list(advisories.values()), sources=sources)
