"""Tests for the advisory database and its three supported input formats."""

import json

import pytest
import requests

from opencloud_local_scan import vulndb

NATIVE = {
    "advisories": [
        {
            "id": "OC-2026-0001",
            "title": "Example flaw",
            "description": "An example advisory used in tests.",
            "severity": "high",
            "cwe": "CWE-79",
            "url": "https://example.com/advisory",
            "introduced": "7.0.0",
            "fixed": "7.2.1",
        }
    ]
}

GITHUB = {
    "advisories": [
        {
            "ghsa_id": "GHSA-xxxx-yyyy-zzzz",
            "cve_id": "CVE-2026-0002",
            "summary": "Example GitHub advisory",
            "description": "Reported through the GitHub Advisory API.",
            "severity": "critical",
            "html_url": "https://github.com/advisories/GHSA-xxxx-yyyy-zzzz",
            "vulnerabilities": [
                {
                    "package": {"ecosystem": "go", "name": "github.com/opencloud-eu/opencloud"},
                    "vulnerable_version_range": ">= 7.0.0, < 7.2.1",
                }
            ],
        }
    ]
}

OSV = {
    "vulns": [
        {
            "id": "GO-2026-0003",
            "aliases": ["CVE-2026-0003"],
            "summary": "Example OSV advisory",
            "details": "Reported through the OSV API.",
            "database_specific": {"severity": "MODERATE"},
            "affected": [
                {
                    "package": {
                        "ecosystem": "Go",
                        "name": "github.com/opencloud-eu/opencloud",
                    },
                    "ranges": [
                        {
                            "type": "SEMVER",
                            "events": [{"introduced": "7.0.0"}, {"fixed": "7.2.1"}],
                        }
                    ],
                }
            ],
        }
    ]
}


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_native_format_matches_a_vulnerable_version(tmp_path):
    """The plain format is the one operators write by hand."""
    database = vulndb.load_database(
        extra_files=(_write(tmp_path, "native.json", NATIVE),), include_bundled=False
    )

    matches = database.matches("7.1.0")

    assert [advisory.id for advisory in matches] == ["OC-2026-0001"]
    assert matches[0].severity == "high"
    assert matches[0].as_dict()["cwe"] == "CWE-79"


def test_native_format_does_not_match_a_fixed_version(tmp_path):
    """The range is half-open, so the fixing release is not affected."""
    database = vulndb.load_database(
        extra_files=(_write(tmp_path, "native.json", NATIVE),), include_bundled=False
    )

    assert database.matches("7.2.1") == []


def test_github_advisory_format_is_understood(tmp_path):
    """The GitHub Advisory API can be used as a feed directly."""
    database = vulndb.load_database(
        extra_files=(_write(tmp_path, "github.json", GITHUB),), include_bundled=False
    )

    matches = database.matches("7.1.0")

    assert len(matches) == 1
    assert matches[0].id == "CVE-2026-0002"
    assert matches[0].severity == "critical"


def test_osv_format_is_understood(tmp_path):
    """OSV is the only place OpenCloud advisories are likely to appear."""
    database = vulndb.load_database(
        extra_files=(_write(tmp_path, "osv.json", OSV),), include_bundled=False
    )

    matches = database.matches("7.1.0")

    assert len(matches) == 1
    # A CVE alias reads better in an alert than the OSV id.
    assert matches[0].id == "CVE-2026-0003"
    assert matches[0].severity in {"moderate", "medium"}


def test_a_bare_osv_record_is_accepted(tmp_path):
    """POST /v1/query returns a single record, not a list."""
    database = vulndb.load_database(
        extra_files=(_write(tmp_path, "one.json", OSV["vulns"][0]),),
        include_bundled=False,
    )

    assert [advisory.id for advisory in database.matches("7.1.0")] == ["CVE-2026-0003"]


def test_advisories_for_other_packages_are_ignored(tmp_path):
    """A Go advisory for some unrelated module must not raise an alert."""
    payload = json.loads(json.dumps(OSV))
    payload["vulns"][0]["affected"][0]["package"]["name"] = "github.com/other/thing"

    database = vulndb.load_database(
        extra_files=(_write(tmp_path, "other.json", payload),), include_bundled=False
    )

    assert database.matches("7.1.0") == []


def test_duplicate_ids_are_collapsed(tmp_path):
    """The same advisory from two sources must be reported once."""
    database = vulndb.load_database(
        extra_files=(
            _write(tmp_path, "a.json", NATIVE),
            _write(tmp_path, "b.json", NATIVE),
        ),
        include_bundled=False,
    )

    assert len(database.matches("7.1.0")) == 1


def test_disabled_entries_never_match(tmp_path):
    """Documentation-only entries are inert."""
    payload = json.loads(json.dumps(NATIVE))
    payload["advisories"][0]["enabled"] = False

    database = vulndb.load_database(
        extra_files=(_write(tmp_path, "off.json", payload),), include_bundled=False
    )

    assert database.matches("7.1.0") == []


def test_no_bundled_advisory_can_match_every_version():
    """
    An advisory without bounds reports every instance in the world as vulnerable.

    OSV publishes exactly such a record beside each reviewed advisory, so this
    is not hypothetical: one unbounded entry reaching the bundled file would
    turn every scan into a critical finding.
    """
    database = vulndb.load_database()

    for advisory in database.advisories:
        for introduced, fixed in advisory.all_ranges():
            assert introduced or fixed, f"{advisory.id} affects every version"
    # A version older than anything OpenCloud ever shipped stands in for
    # "outside every range", and must come back clean however many advisories
    # the daily refresh has added by then.
    assert database.matches("0.0.1") == []


def test_every_bundled_advisory_matches_below_its_fix_and_not_at_it():
    """
    The bundled ranges are half-open, and the refresh must not blunt that.

    Derived from the file rather than from a list, so an advisory added by the
    daily refresh is held to the same rule as the ones written by hand.
    """
    database = vulndb.load_database()
    checked = 0

    for advisory in database.advisories:
        for introduced, fixed in advisory.all_ranges():
            if not (introduced and fixed):
                continue
            checked += 1
            assert advisory.affects(introduced), f"{advisory.id} misses {introduced}"
            assert not advisory.affects(fixed), f"{advisory.id} still flags {fixed}"
            # And the fix it reports is the one for *that* line, not the
            # first fix in the list.
            assert advisory.for_version(introduced).fixed == fixed

    assert checked, "the bundled database has no bounded advisory to check"


def test_unknown_version_matches_nothing(tmp_path):
    """Without a version, no advisory can be attributed."""
    database = vulndb.load_database(
        extra_files=(_write(tmp_path, "native.json", NATIVE),), include_bundled=False
    )

    assert database.matches(None) == []


def test_missing_file_is_skipped_with_a_recorded_source(tmp_path):
    """A typo in a path must not abort the whole check."""
    database = vulndb.load_database(
        extra_files=(str(tmp_path / "does-not-exist.json"),), include_bundled=False
    )

    assert database.matches("7.1.0") == []


def test_feed_is_fetched_and_parsed(monkeypatch):
    """A remote feed is just another source."""

    class _Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return NATIVE

    monkeypatch.setattr(vulndb.requests, "get", lambda *a, **k: _Response())

    database = vulndb.load_database(
        feed_url="https://example.com/advisories.json", include_bundled=False
    )

    assert [advisory.id for advisory in database.matches("7.1.0")] == ["OC-2026-0001"]
    assert "https://example.com/advisories.json" in " ".join(database.sources)


def test_unreachable_feed_is_tolerated(monkeypatch):
    """The check must keep working when the feed host is down."""

    def _boom(*args, **kwargs):
        raise requests.exceptions.ConnectionError("no route to host")

    monkeypatch.setattr(vulndb.requests, "get", _boom)

    database = vulndb.load_database(
        feed_url="https://example.com/advisories.json", include_bundled=False
    )

    assert database.matches("7.1.0") == []


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        (">= 7.0.0, < 7.2.1", ("7.0.0", "7.2.1")),
        ("< 7.2.1", (None, "7.2.1")),
        (">= 7.0.0", ("7.0.0", None)),
        # An exact pin becomes the smallest half-open range that holds it.
        ("= 7.1.0", ("7.1.0", "7.1.0.1")),
        (None, (None, None)),
    ],
)
def test_parse_range(expression, expected):
    """GitHub expresses ranges as a comma separated constraint string."""
    assert vulndb._parse_range(expression) == expected
