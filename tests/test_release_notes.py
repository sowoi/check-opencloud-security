"""
Tests for scripts/release_notes.py.

The release notes of a version are written while the changes are made, under
``## [Unreleased]``, and the release turns that section into the section of
the version from ``pyproject.toml``. Getting this wrong either publishes a
release with empty notes or silently drops what contributors wrote, so the
promotion is covered from both directions.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "release_notes", REPO_ROOT / "scripts" / "release_notes.py"
)
assert SPEC and SPEC.loader
script = importlib.util.module_from_spec(SPEC)
sys.modules["release_notes"] = script
SPEC.loader.exec_module(script)

HEADER = """# Changelog

All notable changes to this project are documented in this file.
"""

UNRELEASED_NOTES = """## [Unreleased]

### Added

- A brand new option nobody has released yet.

### Fixed

- A bug that only ever existed on main.
"""

OLD_RELEASE = """## [1.0.0] - 2026-08-12

### Added

- The first release.
"""


@pytest.fixture
def changelog(tmp_path, monkeypatch):
    """Point the script at a throwaway CHANGELOG.md and RELEASE.md."""
    path = tmp_path / "CHANGELOG.md"
    monkeypatch.setattr(script, "CHANGELOG", path)
    monkeypatch.setattr(script, "RELEASE", tmp_path / "RELEASE.md")
    # A generated fallback would reach for the real repository history.
    monkeypatch.setattr(script, "run_git", lambda *args: "")
    return path


def test_the_unreleased_section_becomes_the_release(changelog):
    """What contributors collected is exactly what gets published."""
    changelog.write_text(f"{HEADER}\n{UNRELEASED_NOTES}\n{OLD_RELEASE}")

    assert script.main(["--version", "1.1.0", "--date", "2026-09-01"]) == 0

    text = changelog.read_text()
    assert "## [1.1.0] - 2026-09-01" in text
    assert "A brand new option nobody has released yet." in text
    assert "A bug that only ever existed on main." in text
    # Promoted, not copied: the notes must not appear under both headings.
    assert text.count("A brand new option nobody has released yet.") == 1
    assert "Maintenance release without documented changes." not in text


def test_the_release_notes_file_carries_the_promoted_notes(changelog):
    """RELEASE.md is the body of the GitHub release, so it must not be empty."""
    changelog.write_text(f"{HEADER}\n{UNRELEASED_NOTES}\n{OLD_RELEASE}")

    script.main(["--version", "1.1.0", "--date", "2026-09-01"])

    release = script.RELEASE.read_text()
    assert release.startswith("## check-opencloud-security 1.1.0")
    assert "A brand new option nobody has released yet." in release
    assert "[Unreleased]" not in release


def test_a_fresh_unreleased_heading_is_left_behind(changelog):
    """The next change must have somewhere to go without recreating the heading."""
    changelog.write_text(f"{HEADER}\n{UNRELEASED_NOTES}\n{OLD_RELEASE}")

    script.main(["--version", "1.1.0", "--date", "2026-09-01"])

    text = changelog.read_text()
    assert text.count("## [Unreleased]") == 1
    # Empty, and above the release it just handed its content to.
    assert text.index("## [Unreleased]") < text.index("## [1.1.0]")
    assert script.unreleased_entry() is None


def test_older_releases_survive_the_promotion(changelog):
    """A changelog that loses its history is worse than no changelog."""
    changelog.write_text(f"{HEADER}\n{UNRELEASED_NOTES}\n{OLD_RELEASE}")

    script.main(["--version", "1.1.0", "--date", "2026-09-01"])

    text = changelog.read_text()
    assert "## [1.0.0] - 2026-08-12" in text
    assert "- The first release." in text
    assert text.index("## [1.1.0]") < text.index("## [1.0.0]")


def test_an_empty_unreleased_heading_is_not_published_as_notes(changelog):
    """The scaffold left by the previous release must not become a release."""
    changelog.write_text(f"{HEADER}\n## [Unreleased]\n\n{OLD_RELEASE}")

    assert script.unreleased_entry() is None
    assert script.main(["--version", "1.1.0", "--date", "2026-09-01"]) == 0

    text = changelog.read_text()
    # Fell back to generated notes, and they landed below the empty heading.
    assert "## [1.1.0] - 2026-09-01" in text
    assert text.index("## [Unreleased]") < text.index("## [1.1.0]")
    assert text.index("## [1.1.0]") < text.index("## [1.0.0]")


def test_a_section_headed_with_the_version_wins_over_unreleased(changelog):
    """Notes written for exactly this release are the most specific source."""
    written = "## [1.1.0] - 2026-09-01\n\n### Added\n\n- Written by hand.\n"
    changelog.write_text(f"{HEADER}\n{UNRELEASED_NOTES}\n{written}\n{OLD_RELEASE}")

    script.main(["--version", "1.1.0", "--date", "2026-09-02"])

    release = script.RELEASE.read_text()
    assert "- Written by hand." in release
    assert "A brand new option nobody has released yet." not in release
    # The unreleased notes are untouched, so they reach the version after this.
    assert script.unreleased_entry() is not None


def test_releasing_without_collected_notes_can_be_made_an_error(changelog):
    """
    The workflow should be able to insist on hand-written notes rather than
    quietly shipping a list of commit subjects.
    """
    changelog.write_text(f"{HEADER}\n## [Unreleased]\n\n{OLD_RELEASE}")

    assert script.main(["--version", "1.1.0", "--require-unreleased"]) == 1
    # Nothing was written, so the failure can simply be fixed and retried.
    assert "## [1.1.0]" not in changelog.read_text()


def test_collected_notes_still_release_with_require_unreleased(changelog):
    """The strict mode must not stand in the way of a normal release."""
    changelog.write_text(f"{HEADER}\n{UNRELEASED_NOTES}\n{OLD_RELEASE}")

    assert (
        script.main(["--version", "1.1.0", "--date", "2026-09-01", "--require-unreleased"])
        == 0
    )
    assert "## [1.1.0] - 2026-09-01" in changelog.read_text()


def test_the_version_is_read_from_pyproject_and_never_invented():
    """The release number comes from the file the maintainer edits by hand."""
    body = (
        (REPO_ROOT / "pyproject.toml")
        .read_text(encoding="utf-8")
        .split("[project]", 1)[1]
        .split("\n[", 1)[0]
    )
    expected = re.search(r'^version\s*=\s*"([^"]+)"', body, re.MULTILINE).group(1)

    assert script.project_version() == expected
