"""
OpenCloud's repository advisories as a second advisory source (ADR 0071).

GHSA-gf4p-7p27-26w7 was published only on OpenCloud's repository and never
reached OSV, so every affected instance was rated free of advisories. These
tests pin how the repository feed is read: strictly, adding only what OSV does
not know, and never at the cost of a refresh that already has OSV's answer.
"""

from __future__ import annotations

from typing import Any

import pytest

from opencloud_local_scan import advisory_source
from opencloud_local_scan.advisory_source import (
    AdvisoryFetchError,
    fetch_advisory_document,
    parse_repository_advisory,
    repository_ranges,
)
from opencloud_local_scan.vulndb import Advisory

# The shape of GitHub's answer for the two advisories OpenCloud has published.
METADATA = {
    "ghsa_id": "GHSA-gf4p-7p27-26w7",
    "cve_id": "CVE-2026-57500",
    "state": "published",
    "withdrawn_at": None,
    "severity": "medium",
    "summary": "Access to internal metadata",
    "description": "Patched versions are stable 4.0.8 and 7.2.0 releases.",
    "html_url": "https://github.com/opencloud-eu/opencloud/security/advisories/GHSA-gf4p-7p27-26w7",
    "cwes": [],
    "vulnerabilities": [
        {
            "package": {"ecosystem": "go", "name": "opencloud"},
            "vulnerable_version_range": "< 4.0.8, < 7.2.0",
            "patched_versions": "4.0.8, 7.2.0",
        }
    ],
}
PUBLIC_LINK = {
    "ghsa_id": "GHSA-vf5j-r2hw-2hrw",
    "cve_id": "CVE-2026-23989",
    "state": "published",
    "severity": "high",
    "summary": "Public Link Exploit",
    "vulnerabilities": [
        {
            "package": {"ecosystem": "opencloud", "name": "opencloud"},
            "vulnerable_version_range": "stable releases 4.0.x",
            "patched_versions": ">= 4.0.3",
        },
        {
            "package": {"ecosystem": "opencloud", "name": "opencloud"},
            "vulnerable_version_range": "rolling releases <= 5.0.1",
            "patched_versions": ">= 5.0.2",
        },
    ],
}
OSV_PUBLIC_LINK = {
    "id": "GHSA-vf5j-r2hw-2hrw",
    "aliases": ["GO-2026-4447"],
    "summary": "Public Link Exploit",
    "affected": [
        {
            "package": {"ecosystem": "Go", "name": "github.com/opencloud-eu/opencloud"},
            "ranges": [{"type": "SEMVER", "events": [{"introduced": "4.0.0"}, {"fixed": "4.0.3"}]}],
        }
    ],
}


def _advisory(record: dict[str, Any]) -> Advisory:
    advisory = parse_repository_advisory(record)
    assert advisory is not None
    return advisory


def test_an_advisory_fixed_on_two_lines_affects_each_line_up_to_its_own_fix():
    """'< 4.0.8, < 7.2.0' is two ranges; one range would flag the fixed 4.0.8."""
    advisory = _advisory(METADATA)

    assert advisory.id == "GHSA-gf4p-7p27-26w7"
    for affected in ("3.0.0", "4.0.7", "5.0.1", "7.1.9"):
        assert advisory.affects(affected), affected
    for fixed in ("0.0.1", "4.0.8", "4.0.9", "7.2.0", "7.2.4", "8.0.0"):
        assert not advisory.affects(fixed), fixed


def test_a_patch_on_the_same_major_starts_the_next_range_at_the_next_line():
    """Fixes in 7.1.3 and 7.2.0 leave 7.1.3 and later on the 7.1 line alone."""
    ranges = repository_ranges("< 7.1.3, < 7.2.0")

    assert ranges == [("1.0.0", "7.1.3"), ("7.2.0", "7.2.0")]


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        (">= 7.0.0, < 7.1.2", [("7.0.0", "7.1.2")]),
        ("<= 5.0.1", [("1.0.0", "5.0.2")]),
        ("< v4.0.3", [("1.0.0", "4.0.3")]),
        ("= 7.0.0", [("7.0.0", "7.0.0.1")]),
    ],
)
def test_an_operator_range_reads_as_one_range(expression, expected):
    """The forms GitHub's own advisories use keep their meaning."""
    assert repository_ranges(expression) == expected


@pytest.mark.parametrize(
    "expression",
    ["stable releases 4.0.x", "rolling releases <= 5.0.1", "all versions", "", "< 4.0.8 or so"],
)
def test_prose_is_never_guessed_at(expression):
    """'rolling releases <= 5.0.1' read as '< 5.0.2' would flag every older 4.0.x as affected."""
    assert repository_ranges(expression) == []


def test_a_patched_list_alone_bounds_the_advisory():
    """No range but patched versions: every release before each fix, per line."""
    assert repository_ranges("", "4.0.8, 7.2.0") == [("1.0.0", "4.0.8"), ("4.1.0", "7.2.0")]


def test_a_backport_named_only_in_the_patched_list_splits_the_range():
    """GHSA-p6cc-4vh9-2hjq says '< 9.1.0' and lists 7.2.5 and 4.0.9 only as patched."""
    ranges = repository_ranges("< 9.1.0", "9.1.0, 7.2.5, 4.0.9")

    assert ranges == [("1.0.0", "4.0.9"), ("4.1.0", "7.2.5"), ("7.3.0", "9.1.0")]
    advisory = parse_repository_advisory(
        {
            "ghsa_id": "GHSA-p6cc-4vh9-2hjq",
            "state": "published",
            "severity": "medium",
            "vulnerabilities": [
                {
                    "package": {"name": "OpenCloud"},
                    "vulnerable_version_range": "< 9.1.0",
                    "patched_versions": "9.1.0, 7.2.5, 4.0.9",
                }
            ],
        }
    )
    assert advisory is not None
    for affected in ("4.0.8", "4.1.0", "7.2.4", "8.1.0", "9.0.0"):
        assert advisory.affects(affected), affected
    for fixed in ("4.0.9", "7.2.5", "9.1.0"):
        assert not advisory.affects(fixed), fixed


def test_a_patched_list_never_widens_a_range_with_a_lower_bound():
    """'>= 7.0.0, < 7.1.2' stays one range, whatever older fix the patched list names."""
    assert repository_ranges(">= 7.0.0, < 7.1.2", "7.1.2, 6.0.5") == [("7.0.0", "7.1.2")]


def test_an_advisory_with_only_prose_ranges_is_dropped():
    """With nothing readable it would be unbounded, which matches every release."""
    assert parse_repository_advisory(PUBLIC_LINK) is None


@pytest.mark.parametrize(
    "change",
    [
        {"state": "draft"},
        {"withdrawn_at": "2026-07-04T00:00:00Z"},
        {"ghsa_id": None},
        {"vulnerabilities": [{"package": {"name": "reva"}, "vulnerable_version_range": "< 2.0.0"}]},
    ],
)
def test_withdrawn_unpublished_or_foreign_advisories_are_dropped(change):
    """Only a published advisory about OpenCloud itself may rate an instance."""
    assert parse_repository_advisory({**METADATA, **change}) is None


@pytest.fixture
def feeds(monkeypatch):
    """Stand-ins for both feeds; the lists can be replaced per test."""
    answers: dict[str, Any] = {"osv": [OSV_PUBLIC_LINK], "repository": [METADATA, PUBLIC_LINK]}
    calls: list[str] = []

    def osv(url, package, timeout):
        calls.append("osv")
        return answers["osv"]

    def repository(url, timeout):
        calls.append("repository")
        if isinstance(answers["repository"], Exception):
            raise answers["repository"]
        return answers["repository"]

    monkeypatch.setattr(advisory_source, "fetch_records", osv)
    monkeypatch.setattr(advisory_source, "fetch_repository_records", repository)
    answers["calls"] = calls
    return answers


def _ids(document: dict[str, Any]) -> list[str]:
    return [entry["id"] for entry in document["advisories"]]


def test_a_repository_only_advisory_is_added_to_osvs_answer(feeds):
    """The advisory OSV never received reaches the database."""
    document = fetch_advisory_document(repository_url="https://feed.example/advisories")

    assert _ids(document) == ["GHSA-gf4p-7p27-26w7", "GHSA-vf5j-r2hw-2hrw"]
    added = document["advisories"][0]
    assert added["source"] == "https://feed.example/advisories"
    assert added["ranges"] == [
        {"introduced": "1.0.0", "fixed": "4.0.8"},
        {"introduced": "4.1.0", "fixed": "7.2.0"},
    ]


def test_an_advisory_osv_knows_keeps_osvs_ranges(feeds):
    """OSV's structured ranges win; the repository record is not merged into them."""
    feeds["repository"] = [{**METADATA, "ghsa_id": "GHSA-vf5j-r2hw-2hrw"}]

    document = fetch_advisory_document(repository_url="https://feed.example/advisories")

    entry = document["advisories"][0]
    assert _ids(document) == ["GHSA-vf5j-r2hw-2hrw"]
    assert (entry["introduced"], entry["fixed"]) == ("4.0.0", "4.0.3")
    assert "ranges" not in entry


def test_an_osv_alias_counts_as_known(feeds):
    """A repository record named by a CVE OSV lists as an alias is that OSV advisory."""
    feeds["osv"] = [{**OSV_PUBLIC_LINK, "aliases": ["CVE-2026-23989"]}]
    feeds["repository"] = [{**METADATA, "ghsa_id": "GHSA-xxxx-xxxx-xxxx", "cve_id": "CVE-2026-23989"}]

    assert _ids(fetch_advisory_document(repository_url="https://feed.example/a")) == [
        "CVE-2026-23989"
    ]


def test_an_unreadable_repository_feed_keeps_osvs_answer(feeds, caplog):
    """GitHub being down must not cost a refresh the advisories OSV did answer with."""
    feeds["repository"] = AdvisoryFetchError("rate limited")

    document = fetch_advisory_document(repository_url="https://feed.example/advisories")

    assert _ids(document) == ["GHSA-vf5j-r2hw-2hrw"]
    assert "rate limited" in caplog.text


def test_without_a_repository_url_only_osv_is_asked(feeds):
    """Every existing caller keeps its behaviour, and a test suite stays offline."""
    document = fetch_advisory_document()

    assert _ids(document) == ["GHSA-vf5j-r2hw-2hrw"]
    assert feeds["calls"] == ["osv"]


def test_a_refresh_never_drops_the_hand_written_entry(feeds):
    """The entry bundled before this source existed survives a refresh that does not read it."""
    existing = {"advisories": [{**advisory_source.to_native(_advisory(METADATA), "hand")}]}

    document = fetch_advisory_document(existing=existing)

    assert "GHSA-gf4p-7p27-26w7" in _ids(document)


def test_a_non_http_repository_url_is_refused():
    """The URL is operator configuration, but file:// is never a feed."""
    with pytest.raises(AdvisoryFetchError):
        advisory_source.fetch_repository_records("file:///etc/passwd")


def test_the_bundled_database_reports_the_repository_only_advisory():
    """An instance on 7.1.x or 4.0.7 is told about GHSA-gf4p-7p27-26w7; 7.2.0 and 4.0.8 are not."""
    from opencloud_local_scan.vulndb import load_database

    database = load_database()

    assert "GHSA-gf4p-7p27-26w7" in [item.id for item in database.matches("7.1.0")]
    assert "GHSA-gf4p-7p27-26w7" in [item.id for item in database.matches("4.0.7")]
    assert "GHSA-gf4p-7p27-26w7" not in [item.id for item in database.matches("7.2.0")]
    assert "GHSA-gf4p-7p27-26w7" not in [item.id for item in database.matches("4.0.8")]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, advisory_source.REPOSITORY_ADVISORIES_URL), ("off", None), ("OFF", None),
     ("https://mirror.example/advisories", "https://mirror.example/advisories")],
)
def test_the_web_setting_defaults_on_and_can_be_switched_off(value, expected):
    """COS_WEB_ADVISORY_REPOSITORY_URL: unset reads GitHub, 'off' reads nothing."""
    pytest.importorskip("fastapi")
    from webapp.settings import _repository_url

    assert _repository_url(value) == expected
