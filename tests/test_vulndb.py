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


# The bundled file is checked below, but the file is only one of the ways an
# advisory gets in: `--vulnerability-feed` reads an operator's own JSON, and
# the OSV refresh reads somebody else's. The parser is what all three go
# through, so the refusal belongs there rather than in a review of the file.


def test_a_native_advisory_with_no_version_range_is_refused(tmp_path):
    """
    An advisory that cannot say what it affects matches everything.

    `is_in_range(v, None, None)` is True for every version, so one such record
    reports every instance scanned with this database as critically
    vulnerable - and the native format is the one an operator writes by hand
    and points `--vulnerability-feed` at, where a forgotten bound is a typo
    rather than somebody else's feed quirk.
    """
    payload = {"advisories": [{"id": "OC-NO-BOUNDS", "severity": "critical"}]}

    database = vulndb.load_database(
        extra_files=(_write(tmp_path, "unbounded.json", payload),),
        include_bundled=False,
    )

    assert database.advisories == []
    assert database.matches("7.2.0") == []
    assert database.matches("99.99.99") == []


def test_a_native_advisory_keeps_a_single_open_bound(tmp_path):
    """
    The negative case: only *both* bounds open is meaningless.

    An advisory with no fix yet is the normal shape of a fresh one, and an
    advisory with no introduced version affects everything up to its fix.
    Refusing either would drop real advisories.
    """
    payload = {
        "advisories": [
            {"id": "OC-NO-FIX", "severity": "high", "introduced": "7.0.0"},
            {"id": "OC-NO-START", "severity": "high", "fixed": "7.2.1"},
        ]
    }

    database = vulndb.load_database(
        extra_files=(_write(tmp_path, "half-open.json", payload),),
        include_bundled=False,
    )

    assert {advisory.id for advisory in database.advisories} == {
        "OC-NO-FIX",
        "OC-NO-START",
    }
    assert {advisory.id for advisory in database.matches("7.1.0")} == {
        "OC-NO-FIX",
        "OC-NO-START",
    }
    # Bounded on the side that is stated, so neither matches everything.
    assert [advisory.id for advisory in database.matches("6.0.0")] == ["OC-NO-START"]
    assert [advisory.id for advisory in database.matches("8.0.0")] == ["OC-NO-FIX"]


def test_a_disabled_placeholder_is_not_mistaken_for_an_unbounded_advisory():
    """
    A record the parser never turns into an advisory has no range to judge.

    The bundled ``OC-EOL`` entry is exactly that: ``enabled: false``, no
    version bounds, there to document the end-of-life finding the scanner
    raises by itself. Judging it on its absent range would condemn every
    document this project ships, including the bundled one.
    """
    placeholder = {"id": "OC-EOL", "introduced": None, "fixed": None, "enabled": False}
    real = {"id": "OC-REAL", "introduced": None, "fixed": None}

    assert vulndb.is_unbounded_advisory(placeholder) is False
    assert vulndb.is_unbounded_advisory(real) is True
    # And the file that carries it is still readable.
    assert vulndb.load_database().advisories


def test_a_github_advisory_whose_range_cannot_be_parsed_is_refused(tmp_path):
    """
    Matching the package is not the same as knowing the versions.

    Matching the package proves the advisory is about OpenCloud and nothing
    about which releases it affects. An unparseable
    `vulnerable_version_range` with no patched version left it unbounded, and
    unbounded means every instance.
    """
    payload = {
        "advisories": [
            {
                "ghsa_id": "GHSA-aaaa-bbbb-cccc",
                "summary": "Unparseable range",
                "vulnerabilities": [
                    {
                        "package": {"name": "github.com/opencloud-eu/opencloud"},
                        "vulnerable_version_range": "whenever it feels like it",
                        "first_patched_version": None,
                    }
                ],
            }
        ]
    }

    database = vulndb.load_database(
        extra_files=(_write(tmp_path, "ghsa.json", payload),),
        include_bundled=False,
    )

    assert database.advisories == []
    assert database.matches("99.99.99") == []


def test_a_github_advisory_patched_on_two_lines_keeps_both_ranges(tmp_path):
    """
    One advisory, two release lines, two separately patched ranges.

    GitHub writes one ``vulnerabilities`` entry per affected range, so an issue
    fixed in both 4.0.3 and 5.0.2 arrives as two entries for the same package.
    Keeping only the first silently clears every instance on the other line -
    a false pass, which is the one direction this must not fail in - and it
    also reports the wrong fix to the instances it does flag.
    """
    payload = {
        "advisories": [
            {
                "ghsa_id": "GHSA-dddd-eeee-ffff",
                "summary": "Public link exploit",
                "severity": "high",
                "vulnerabilities": [
                    {
                        "package": {"name": "github.com/opencloud-eu/opencloud"},
                        "vulnerable_version_range": ">= 4.0.0, < 4.0.3",
                        "first_patched_version": "4.0.3",
                    },
                    {
                        "package": {"name": "github.com/opencloud-eu/opencloud"},
                        "vulnerable_version_range": ">= 5.0.0, < 5.0.2",
                        "first_patched_version": "5.0.2",
                    },
                ],
            }
        ]
    }

    database = vulndb.load_database(
        extra_files=(_write(tmp_path, "ghsa-two-lines.json", payload),),
        include_bundled=False,
    )
    (advisory,) = database.advisories

    assert advisory.all_ranges() == (("4.0.0", "4.0.3"), ("5.0.0", "5.0.2"))
    # Both lines are reported, each with the fix that belongs to it.
    assert advisory.affects("4.0.1") and advisory.affects("5.0.1")
    assert advisory.for_version("5.0.1").fixed == "5.0.2"
    assert advisory.for_version("4.0.1").fixed == "4.0.3"
    # And neither patched release, nor the gap between the lines, is flagged.
    assert not advisory.affects("4.0.3")
    assert not advisory.affects("5.0.2")
    assert not advisory.affects("4.5.0")


def test_an_exclusive_lower_bound_leaves_the_named_release_alone(tmp_path):
    """
    ``> 7.0.0`` says 7.0.0 is not affected, and must not report it.

    An advisory that spells its lower bound exclusively has gone out of its way
    to exclude one release; reading it as ``>=`` turns that release into a
    finding no upgrade can clear, because it is already the version the
    advisory considers safe.
    """
    payload = {
        "advisories": [
            {
                "ghsa_id": "GHSA-gggg-hhhh-iiii",
                "summary": "Exclusive lower bound",
                "vulnerabilities": [
                    {
                        "package": {"name": "github.com/opencloud-eu/opencloud"},
                        "vulnerable_version_range": "> 7.0.0, < 7.0.5",
                    }
                ],
            }
        ]
    }

    database = vulndb.load_database(
        extra_files=(_write(tmp_path, "ghsa-exclusive.json", payload),),
        include_bundled=False,
    )
    (advisory,) = database.advisories

    assert not advisory.affects("7.0.0")
    # Everything the advisory really does cover is still covered.
    assert advisory.affects("7.0.1")
    assert advisory.affects("7.0.4")
    assert not advisory.affects("7.0.5")


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
