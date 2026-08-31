"""Tests for scripts/security_advisories.py and the records it guards.

The point of the record directory is that a `### Security` changelog entry
cannot quietly go by without somebody deciding whether it owes the people
running the affected release an advisory. These tests protect that: that the
real tree is currently covered, and - the half that actually matters - that
the check fails when it should.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "security_advisories", REPO_ROOT / "scripts" / "security_advisories.py"
)
assert SPEC and SPEC.loader
script = importlib.util.module_from_spec(SPEC)
sys.modules["security_advisories"] = script
SPEC.loader.exec_module(script)


def record(**overrides: object) -> dict:
    """A valid published record, so a test can break exactly one thing."""
    base = {
        "slug": "example-finding",
        "state": "published",
        "ghsa": "GHSA-xxxx-xxxx-xxxx",
        "changelog_version": "1.14.0",
        "changelog_entry": "Something was wrong.",
        "shipped": True,
        "severity": "high",
        "cwe_ids": ["CWE-918"],
        "package": "plugin",
        "introduced": "1.0.0",
        "fixed": "1.14.0",
        "summary": "Something was wrong",
        "verified": "git show v1.13.0:file.py - the guard is absent.",
        "description": "### Impact\n\nSomething was wrong.",
        "_path": Path("example-finding.yml"),
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------- the real tree


def test_the_repository_records_are_all_well_formed() -> None:
    """Every committed record parses and satisfies its own schema."""
    assert script.validate(script.load_records()) == []


def test_every_recent_security_entry_has_a_record() -> None:
    """No `### Security` bullet from the baseline forward is undecided."""
    assert script.check_coverage(script.load_records()) == []


def test_no_two_records_claim_the_same_advisory() -> None:
    """A GHSA id belongs to one record, so a fix cannot be announced twice."""
    ids = [r["ghsa"] for r in script.load_records() if r.get("ghsa")]
    assert len(ids) == len(set(ids))


def test_the_web_application_is_never_filed_against_pypi() -> None:
    """webapp/ ships as a tarball, so an advisory about it must not alert pip users."""
    assert script.PACKAGES["web"]["ecosystem"] == "other"
    assert script.PACKAGES["plugin"]["ecosystem"] == "pip"

    web = script.advisory_payload(record(package="web"))
    assert web["vulnerabilities"][0]["package"]["ecosystem"] == "other"


def test_a_published_record_describes_the_range_it_affects() -> None:
    """The payload names an open-ended lower bound and the release that fixed it."""
    payload = script.advisory_payload(record(introduced="1.2.3", fixed="1.6.0"))
    vulnerability = payload["vulnerabilities"][0]
    assert vulnerability["vulnerable_version_range"] == ">= 1.2.3, < 1.6.0"
    assert vulnerability["patched_versions"] == "1.6.0"


# ------------------------------------------------------------- the negative half


def test_an_unclaimed_security_entry_fails_the_check(tmp_path, monkeypatch) -> None:
    """A new Security bullet with no record is what the check exists to catch."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "## [1.99.0] - 2026-09-01\n\n"
        "### Security\n\n"
        "- **A brand new hole.** Nobody has decided about this one yet.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(script, "CHANGELOG", changelog)

    problems = script.check_coverage([])
    assert len(problems) == 1
    assert "no record claims this Security entry" in problems[0]


def test_a_record_whose_wording_drifted_from_the_changelog_fails(tmp_path, monkeypatch) -> None:
    """A record must keep pointing at a bullet that still exists."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "## [1.99.0] - 2026-09-01\n\n### Security\n\n- **Reworded entirely.** Text.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(script, "CHANGELOG", changelog)

    problems = script.check_coverage(
        [record(changelog_version="1.99.0", changelog_entry="The old wording.")]
    )
    assert any("CHANGELOG.md does not have" in problem for problem in problems)


def test_an_entry_below_the_baseline_is_not_demanded(tmp_path, monkeypatch) -> None:
    """Older sections were reviewed by hand once; the check does not re-litigate them."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "## [1.2.3] - 2026-08-13\n\n### Security\n\n- An ancient, unrecorded entry.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(script, "CHANGELOG", changelog)

    assert script.check_coverage([]) == []


def test_an_unreleased_entry_is_not_demanded(tmp_path, monkeypatch) -> None:
    """An Unreleased bullet has no release to warn anybody about yet."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "## [Unreleased]\n\n### Security\n\n- **Not out yet.** Text.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(script, "CHANGELOG", changelog)

    assert script.check_coverage([]) == []


def test_an_advisory_for_something_that_never_shipped_is_refused() -> None:
    """A defect no release carried has nobody to warn, so it must not be an advisory."""
    problems = script.validate([record(shipped=False)])
    assert any("shipped: true" in problem for problem in problems)

    assert script.validate([record(shipped=True)]) == []


def test_a_published_record_without_a_ghsa_id_is_refused() -> None:
    """'published' is a claim about GitHub's state, not a wish."""
    problems = script.validate([record(ghsa=None)])
    assert any("carries no ghsa id" in problem for problem in problems)


def test_a_declined_record_must_say_why() -> None:
    """The reason is the whole value of the record; without it nothing was decided."""
    declined = {
        "slug": "example-finding",
        "state": "declined",
        "changelog_version": "1.14.0",
        "changelog_entry": "Something was wrong.",
        "shipped": False,
        "summary": "Something was wrong",
        "verified": "It never shipped.",
        "_path": Path("example-finding.yml"),
    }
    assert any("declined_because" in p for p in script.validate([dict(declined)]))

    declined["declined_because"] = "Never shipped: introduced and fixed in one cycle."
    assert script.validate([declined]) == []


def test_a_declined_record_may_not_carry_an_advisory_id() -> None:
    """Declining and having published are contradictory states."""
    problems = script.validate(
        [
            record(
                state="declined",
                declined_because="Hardening, not a fix.",
                ghsa="GHSA-xxxx-xxxx-xxxx",
            )
        ]
    )
    assert any("declined but carries a ghsa id" in problem for problem in problems)


def test_a_fix_version_must_match_the_changelog_section() -> None:
    """An advisory naming a different release than the entry it came from is wrong."""
    problems = script.validate([record(fixed="1.15.0", changelog_version="1.14.0")])
    assert any("but the changelog entry is under" in problem for problem in problems)


@pytest.mark.parametrize("severity", ["moderate", "important", "SEV-1", ""])
def test_a_severity_github_does_not_accept_is_refused(severity: str) -> None:
    """The API takes low/medium/high/critical; 'moderate' is the tempting mistake."""
    problems = script.validate([record(severity=severity)])
    assert any("is not one of" in problem or "missing required" in problem for problem in problems)


def test_the_slug_must_match_the_filename() -> None:
    """--publish addresses a record by slug, so the two cannot drift."""
    problems = script.validate([record(_path=Path("something-else.yml"))])
    assert any("does not match the filename" in problem for problem in problems)


# --------------------------------------------------------------------- parsing


def test_only_bullets_under_a_security_heading_are_collected(tmp_path, monkeypatch) -> None:
    """A Fixed entry is not a security claim, however security-adjacent it reads."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "## [1.99.0] - 2026-09-01\n\n"
        "### Security\n\n"
        "- **The real one.** Body.\n\n"
        "### Fixed\n\n"
        "- **A bug that is not a vulnerability.** Body.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(script, "CHANGELOG", changelog)

    bullets = script.changelog_security_bullets()
    assert len(bullets) == 1
    assert bullets[0][0] == "1.99.0"
    assert bullets[0][1].startswith("**The real one.**")


def test_a_wrapped_bullet_is_read_as_one_entry(tmp_path, monkeypatch) -> None:
    """Entries in this changelog run to several indented paragraphs."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "## [1.99.0] - 2026-09-01\n\n"
        "### Security\n\n"
        "- **One entry.** It continues\n"
        "  onto a second line.\n\n"
        "  And a second paragraph.\n\n"
        "- **A second entry.** Body.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(script, "CHANGELOG", changelog)

    bullets = script.changelog_security_bullets()
    assert len(bullets) == 2
    assert "second paragraph" in bullets[0][1]


def test_a_record_matches_its_bullet_despite_markdown(tmp_path, monkeypatch) -> None:
    """Records quote the entry as prose; the changelog wraps it in bold and code."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "## [1.99.0] - 2026-09-01\n\n"
        "### Security\n\n"
        "- **The `serve` command binds everything.** Body text.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(script, "CHANGELOG", changelog)

    covered = record(
        changelog_version="1.99.0",
        changelog_entry="The serve command binds everything.",
        fixed="1.99.0",
    )
    assert script.check_coverage([covered]) == []


def test_the_committed_records_quote_the_changelog_verbatim_enough_to_match() -> None:
    """Guards the normalisation itself: real records against the real changelog."""
    bullets = script.changelog_security_bullets()
    versions = {version for version, _ in bullets}
    for item in script.load_records():
        if script.parse_version(item["changelog_version"]) >= script.COVERAGE_BASELINE:
            assert item["changelog_version"] in versions, (
                f"{item['slug']} points at version {item['changelog_version']}, "
                "which has no Security section"
            )


def test_every_record_file_is_valid_yaml_with_a_comment_header() -> None:
    """The header is where a maintainer meeting the directory learns what it is."""
    for path in sorted((REPO_ROOT / "security" / "advisories").glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        assert text.startswith("#"), f"{path.name} has no explanatory header"
        assert isinstance(yaml.safe_load(text), dict)
